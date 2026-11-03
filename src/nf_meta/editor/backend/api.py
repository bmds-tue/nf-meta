import itertools
import os
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from nf_meta.core.dynamic_validation import get_step_schema, run_dynamic_checks
from nf_meta.core.edits import DeclareStepInputs, DeleteInput, DeleteSteps, EditInput, SaveWorkflow, SetInputsStyle
from nf_meta.core.errors import (
    ConfigValidationError,
    GraphValidationError,
    RemoteConfigWriteError,
    SessionCommandError,
    Severity,
    diagnostics_from_pydantic_error,
)
from nf_meta.core.events import (
    AddTransition,
    Command,
    RemoveTransition,
    Transaction,
    UpdateGlobalOptions,
)
from nf_meta.core.inputs import Binding, InputDefinition
from nf_meta.core.models import GlobalOptions, Transition, Workflow
from nf_meta.core.registry import (
    ModuleSchemaError,
    NotInRegistryError,
    PipelineSchemaError,
    RegistryUnavailableError,
    SchemaUnavailableError,
    get_module_metadata,
    get_module_schema,
    get_nfcore_module_releases,
    get_nfcore_modules,
    get_nfcore_pipelines,
    get_pipeline_schema,
)
from nf_meta.core.session import SESSION

from . import recent
from .files import list_folder
from .guard import guard
from .serializers import Selection, serialize_events, serialize_state

DEV_MODE = os.getenv("NF_META_DEVMODE", 0) == "1"
DEV_HOST = "127.0.0.1"
DEV_PORT = 8080
DEV_VITE_PORT = 5180
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend_dist"

app = FastAPI(title="metapipeline_editor")
app.middleware("http")(guard)
api_router = APIRouter()

# serve static files for deployment through fastapi
app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")


@app.exception_handler(SessionCommandError)
def handle_session_error(request: Request, exc: SessionCommandError):
    return JSONResponse(status_code=422, content=exc.to_dict())


@app.exception_handler(RemoteConfigWriteError)
def handle_remote_config_write(request: Request, exc: RemoteConfigWriteError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(RegistryUnavailableError)
def handle_registry_unavailable(request: Request, exc: RegistryUnavailableError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
def handle_request_validation(request: Request, exc: RequestValidationError):
    err = SessionCommandError(
        graph_errors=[],
        field_errors=[
            SessionCommandError.FieldError(
                workflow_id=None,  # frontend infers from context
                field=".".join(str(part) for part in err["loc"] if part != "body"),
                message=err["msg"],
            )
            for err in exc.errors()
        ],
    )
    return JSONResponse(status_code=422, content=err.to_dict())


@app.api_route("/")
def serve_ui(request: Request):
    if DEV_MODE:
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"http://localhost:{DEV_VITE_PORT}/{query}")
    return FileResponse(DIST_DIR / "index.html")


@api_router.get("/ping/")
def ping():
    return {"ok": True}


def configure_shutdown(app: FastAPI, stop: Callable[[], None] | None) -> None:
    """Let the page stop the editor: `POST /api/shutdown/` calls `stop`."""
    app.state.stop_server = stop


@api_router.post("/shutdown/")
def shutdown(request: Request):
    # set by the editor that runs the server; missing when something else serves the app
    stop = getattr(request.app.state, "stop_server", None)
    if stop is None:
        return JSONResponse(status_code=503, content={"detail": "This editor can't be stopped from the page"})
    # the server finishes this response before it stops
    stop()
    return {"ok": True}


_first_graph_request = itertools.chain([True], itertools.repeat(False))


def initial_startup() -> bool:
    """Returns True for the first graph request after editor start and false afterwards."""
    return next(_first_graph_request)


@api_router.get("/graph/")
def get_graph():
    """The session's state, and `start_screen`: whether the page should offer
    the start screen (only on the first request of a run without a config)."""
    first = initial_startup()
    start_screen = first and not SESSION.config_file and not SESSION.graph.get_workflows()
    return {**serialize_state(SESSION), "start_screen": start_screen}


@api_router.get("/files/")
def list_files(path: str | None = None, all_files: bool = False):
    """A folder of the machine running the editor, for the open and save
    dialogs (see `list_folder`). Without `path`, the folder of the config
    being edited, or where the editor was started. Anyone who can reach the
    editor can list folders this way; it listens on 127.0.0.1 by default."""
    config = SESSION.config_file
    local = config and not str(config).startswith(("http://", "https://"))
    start = Path(str(config)).resolve().parent if local else Path.cwd()
    try:
        return list_folder(path, start, all_files=all_files)
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"detail": f"No such folder: {path}"})
    except PermissionError:
        return JSONResponse(status_code=403, content={"detail": f"Can't read the folder {path}"})


@api_router.post("/graph/save/")
def save_graph(config: Path = Body(embed=True)):
    try:
        SESSION.save_to_config(config)
    except OSError as exc:
        return JSONResponse(status_code=400, content={"detail": f"Can't write {config}: {exc.strerror or exc}"})
    recent.remember(config)
    return JSONResponse({})


@api_router.post("/graph/load/")
def load_graph(config: Path = Body(embed=True)):
    """Load the config at `config` (relative to where the editor was
    started). Answers 404 for a missing file and 422 with the first problems
    for an invalid config; the current graph stays as it was."""
    if not config.is_file():
        return JSONResponse(status_code=404, content={"detail": f"No such file: {config}"})
    try:
        SESSION.load_config(config)
    except (ConfigValidationError, GraphValidationError) as exc:
        problems = [f"{d.yaml_path}: {d.message}" for d in getattr(exc, "errors", [])] or [str(exc)]
        more = f" (and {len(problems) - 3} more)" if len(problems) > 3 else ""
        return JSONResponse(status_code=422, content={"detail": f"Invalid config: {'; '.join(problems[:3])}{more}"})
    recent.remember(config)
    return JSONResponse({})


@api_router.get("/recent/")
def list_recent():
    """The recently opened or saved configs, most recent first, each with
    whether the file still exists."""
    return [{"path": p, "exists": Path(p).is_file()} for p in recent.recent_configs()]


@api_router.post("/recent/forget/")
def forget_recent(path: str = Body(embed=True)):
    recent.forget(path)
    return {"ok": True}


@api_router.get("/graph/undo/")
def undo_most_recent():
    events = SESSION.handle_undo()
    return JSONResponse({"events": serialize_events(events)})


@api_router.get("/graph/redo/")
def redo_most_recent():
    events = SESSION.handle_redo()
    return JSONResponse({"events": serialize_events(events)})


@api_router.post("/globals/update/")
def update_global_config(global_options: GlobalOptions):
    events = SESSION.handle_command(UpdateGlobalOptions(global_options))
    return JSONResponse({"events": serialize_events(events)})


@api_router.post("/node/validate/")
def validate_node(wf: Workflow):
    """Validate a single workflow in isolation -- same body shape as
    `/node/add/`, but non-mutating: no session command, no auto-save."""
    diagnostics = run_dynamic_checks(wf, previous=None)
    errors = [d for d in diagnostics if d.severity == Severity.ERROR]
    if errors:
        raise SessionCommandError.from_diagnostics(errors)
    return JSONResponse({"field_errors": [], "graph_errors": []})


@api_router.post("/globals/validate/")
def validate_globals(global_options: GlobalOptions):
    """Validate the globals block in isolation -- same body shape as
    `/globals/update/`, but non-mutating. Globals have no tier-2 checks, so a
    body that parses into GlobalOptions is already fully valid."""
    return JSONResponse({"field_errors": [], "graph_errors": []})


@api_router.post("/node/add/")
def add_node(wf: Workflow):
    events = SESSION.handle_command(SaveWorkflow(wf, create=True))
    return JSONResponse({"events": serialize_events(events)})


@api_router.post("/node/update/")
def update_node(wf: Workflow):
    events = SESSION.handle_command(SaveWorkflow(wf, create=False))
    return JSONResponse({"events": serialize_events(events)})


@api_router.delete("/delete/")
def remove(selection: Selection):
    commands: list[Command] = [RemoveTransition(*edge_id.split("->", 1)) for edge_id in selection.edges]
    commands.append(DeleteSteps(tuple(selection.nodes)))
    events = SESSION.handle_command(Transaction(tuple(commands)))
    return JSONResponse({"events": serialize_events(events)})


@api_router.post("/edge/add/")
def add_edge(tr: Transition):
    events = SESSION.handle_command(AddTransition(tr))
    return JSONResponse({"events": serialize_events(events)})


class InputBody(BaseModel):
    """An input as edited in the inputs panel: its details (`definition`,
    without `bind`), the params it fills, and whether it is written as
    `${inputs:<name>}` in those params (`in_params`) or with `bind:`."""

    name: str
    definition: dict = {}
    bindings: list[str] = []
    in_params: bool = True
    new_name: str | None = None
    create: bool = False


def _edit_input_command(body: InputBody) -> EditInput:
    target = body.new_name or body.name
    try:
        definition = InputDefinition.from_config({k: v for k, v in body.definition.items() if k != "bind"})
    except ValidationError as exc:
        raise SessionCommandError.from_diagnostics(
            diagnostics_from_pydantic_error(exc, None, yaml_path_prefix=f"inputs.{target}.")
        ) from exc
    try:
        bindings = tuple(Binding.parse(text) for text in body.bindings)
    except ValueError as exc:
        raise SessionCommandError(
            field_errors=[
                SessionCommandError.FieldError(workflow_id=None, field=f"inputs.{target}.bind", message=str(exc))
            ],
            graph_errors=[],
        ) from exc
    return EditInput(body.name, definition, bindings, body.in_params, body.new_name, body.create)


@api_router.post("/inputs/save/")
def save_input(body: InputBody):
    events = SESSION.handle_command(_edit_input_command(body))
    return JSONResponse({"events": serialize_events(events)})


@api_router.delete("/inputs/delete/")
def delete_input(name: str = Body(embed=True)):
    events = SESSION.handle_command(DeleteInput(name))
    return JSONResponse({"events": serialize_events(events)})


@api_router.post("/inputs/style/")
def set_inputs_style(in_params: bool = Body(embed=True)):
    events = SESSION.handle_command(SetInputsStyle(in_params))
    return JSONResponse({"events": serialize_events(events)})


@api_router.post("/node/{wf_id}/declare-inputs/")
def declare_step_inputs(wf_id: str):
    events = SESSION.handle_command(DeclareStepInputs(wf_id))
    return JSONResponse({"events": serialize_events(events)})


@api_router.get("/node/{wf_id}/schema/")
def get_node_schema(wf_id: str):
    """The flat param schema of step `wf_id` (see `get_step_schema`)."""
    step = SESSION.graph.get_workflow_by_id(wf_id)
    if step is None:
        return JSONResponse(status_code=404, content={"detail": f"No step '{wf_id}'"})
    try:
        return get_step_schema(step)
    except SchemaUnavailableError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})


@api_router.get("/nfcore/pipelines/")
def get_all_nfcore_pipelines():
    return get_nfcore_pipelines()


@api_router.get("/nfcore/modules/")
def get_all_nfcore_modules():
    return get_nfcore_modules()


@api_router.get("/nfcore/modules/{name}/versions/")
def get_nfcore_module_versions(name: str):
    releases = get_nfcore_module_releases(name)
    return [
        {
            "version": r["version"],
            "createdAt": r.get("createdAt"),
            "status": r.get("status"),
        }
        for r in releases
    ]


@api_router.get("/nfcore/modules/{name}/meta/")
def get_nfcore_module_meta(name: str, version: str | None = None):
    try:
        release = get_module_metadata(name, version)
    except NotInRegistryError as exc:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    return {
        "name": name,
        "version": release["version"],
        "metadata": release.get("metadata", {}),
    }


@api_router.get("/nfcore/modules/{name}/schema/")
def get_nfcore_module_schema(name: str, version: str):
    """Return the parsed input schema for nf-core module `name` at `version`.

    `version` must contain an extractable commit SHA (e.g. ``0.0.0-6c4ed3a``).
    Returns a flat ``{param_name: spec}`` dict with ``type``, ``required``,
    ``enum``, and ``pattern`` fields per parameter.
    """
    try:
        return get_module_schema(f"nf-core/{name}", version)
    except ModuleSchemaError as exc:
        return JSONResponse(status_code=404, content={"detail": str(exc)})


@api_router.get("/nfcore/pipelines/schema/")
def get_nfcore_pipeline_schema(url: str, version: str):
    """Return the parsed param schema for the pipeline at ``url`` at ``version``.

    ``url`` must be a GitHub, GitLab, or Bitbucket repository URL.
    Returns a flat ``{param_name: spec}`` dict with ``type``, ``required``,
    ``enum``, ``pattern``, ``format``, ``default``, and ``hidden`` fields.
    """
    try:
        return get_pipeline_schema(url, version)
    except PipelineSchemaError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})


app.include_router(api_router, prefix="/api")
