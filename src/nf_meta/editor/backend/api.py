import os
from typing import Annotated, Optional

from .serializers import serialize_state, serialize_events, Selection

from nf_meta.core.errors import SessionCommandError
from nf_meta.core.session import SESSION
from nf_meta.core.nf_core_utils import (
    get_nfcore_pipelines,
    get_nfcore_modules,
    get_nfcore_module_releases,
    get_module_schema,
    get_pipeline_schema,
    PipelineSchemaError,
)
from nf_meta.core.models import Workflow, Transition, GlobalOptions
from nf_meta.core.events import (
    AddTransition,
    AddWorkflow,
    Command,
    EditWorkflow,
    RemoveWorkflow,
    RemoveTransition,
    Transaction,
    UpdateGlobalOptions,
)

from fastapi import FastAPI, APIRouter, Body, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from pathlib import Path


DEV_MODE = os.getenv("NF_META_DEVMODE", 0) == "1"
DEV_HOST = "127.0.0.1"
DEV_PORT = 8080
DEV_VITE_PORT = 5180
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend_dist"

app = FastAPI(title="metapipeline_editor")
api_router = APIRouter()

# serve static files for deployment through fastapi
app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")


@app.exception_handler(SessionCommandError)
def handle_session_error(request: Request, exc: SessionCommandError):
    return JSONResponse(status_code=422, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
def handle_request_validation(request: Request, exc: RequestValidationError):
    err = SessionCommandError(
        graph_errors=[],
        field_errors=[
            SessionCommandError.FieldError(
                workflow_id=None,  # frontend infers from context
                field=".".join(str(l) for l in err["loc"] if l != "body"),
                message=err["msg"],
            )
            for err in exc.errors()
        ],
    )
    return JSONResponse(status_code=422, content=err.to_dict())


@app.api_route("/")
def serve_ui():
    if DEV_MODE:
        return RedirectResponse(f"http://localhost:{DEV_VITE_PORT}/")
    return FileResponse(DIST_DIR / "index.html")


@api_router.get("/graph/")
def get_graph():
    return serialize_state(SESSION)


@api_router.post("/graph/save/")
def save_graph(config: Path = Body(embed=True)):
    SESSION.save_to_config(config)
    return JSONResponse(dict())


@api_router.post("/graph/load/")
def load_graph(config: Path = Body(embed=True)):
    SESSION.load_config(config)
    return JSONResponse(dict())


@api_router.get("/graph/undo/")
def undo_most_recent():
    events = SESSION.handle_undo()
    return JSONResponse({"events": serialize_events(events)})


@api_router.get("/graph/redo/")
def redo_most_recent():
    events = SESSION.handle_redo()
    return JSONResponse({"events": serialize_events(events)})


@api_router.post("/globals/update/")
def update_global_config(globals: GlobalOptions):
    events = SESSION.handle_command(UpdateGlobalOptions(globals))
    return JSONResponse({"events": serialize_events(events)})


@api_router.post("/node/add/")
def add_node(wf: Workflow):
    events = SESSION.handle_command(AddWorkflow(workflow=wf))
    return JSONResponse({"events": serialize_events(events)})


@api_router.post("/node/update/")
def update_node(wf: Workflow):
    events = SESSION.handle_command(EditWorkflow(workflow=wf))
    return JSONResponse({"events": serialize_events(events)})


@api_router.delete("/delete/")
def remove(selection: Selection):
    cmds: list[Command] = []
    for edge_id in selection.edges:
        src, tgt = edge_id.split("->")
        cmds.append(RemoveTransition(src, tgt))

    for node_id in selection.nodes:
        cmds.append(RemoveWorkflow(node_id))

    events = SESSION.handle_command(Transaction(tuple(cmds)))
    return JSONResponse({"events": serialize_events(events)})


@api_router.post("/edge/add/")
def add_edge(tr: Transition):
    events = SESSION.handle_command(AddTransition(tr))
    return JSONResponse({"events": serialize_events(events)})


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
def get_nfcore_module_meta(name: str, version: Optional[str] = None):
    releases = get_nfcore_module_releases(name)
    if not releases:
        return JSONResponse(
            status_code=404,
            content={
                "detail": f"Module '{name}' not found or has no published releases"
            },
        )

    if version is not None:
        release = next((r for r in releases if r["version"] == version), None)
        if release is None:
            return JSONResponse(
                status_code=404,
                content={
                    "detail": f"Version '{version}' not found for module '{name}'"
                },
            )
    else:
        release = max(releases, key=lambda r: r.get("createdAt", ""))

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
    schema = get_module_schema(f"nf-core/{name}", version)
    if not schema:
        return JSONResponse(
            status_code=404,
            content={
                "detail": (
                    f"No schema available for module '{name}' at version '{version}'. "
                    "Ensure the version contains a commit SHA (e.g. '0.0.0-6c4ed3a')."
                )
            },
        )
    return schema


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
