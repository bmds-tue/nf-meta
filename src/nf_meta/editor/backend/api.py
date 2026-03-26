import os
from typing import Annotated

from .serializers import serialize_state, Selection

from nf_meta.engine.errors import SessionCommandError
from nf_meta.engine.session import SESSION
from nf_meta.engine.nf_core_utils import get_nfcore_pipelines
from nf_meta.engine.models import Workflow, Transition, GlobalOptions
from nf_meta.engine.events import (AddTransition, AddWorkflow, 
                                    RemoveWorkflow, RemoveTransition,
                                    EditWorkflow, EditTransition,
                                    Transaction, UpdateGlobalOptions)

from fastapi import FastAPI, APIRouter, Body, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from pathlib import Path


DEV_MODE = os.getenv("NF_META_DEVMODE", 0) == "1"
DEV_HOST = "localhost"
DEV_PORT = "8080"
DEV_VITE_PORT = "5173"
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend_dist"

app = FastAPI(title="metapipeline_editor")
api_router = APIRouter()

# serve static files for deployment through fastapi
app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")


@app.exception_handler(SessionCommandError)
def handle_session_error(request: Request, exc: SessionCommandError):
    return JSONResponse(
        status_code=422,
        content=exc.to_dict()
    )


@app.exception_handler(RequestValidationError)
def handle_request_validation(request: Request, exc: RequestValidationError):
    err = SessionCommandError(
                graph_errors=[],
                field_errors=[
                    {
                        "workflow_id": None,  # frontend infers from context
                        "field": ".".join(str(l) for l in err["loc"] if l != "body"),
                        "message": err["msg"],
                    }
                    for err in exc.errors()
                ])
    return JSONResponse(
        status_code=422,
        content=err.to_dict()
    )


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
    SESSION.handle_undo()
    return JSONResponse(dict())


@api_router.get("/graph/redo/")
def redo_most_recent():
    SESSION.handle_redo()
    return JSONResponse(dict())


@api_router.post("/globals/update/")
def update_global_config(globals: GlobalOptions):
    SESSION.handle_command(UpdateGlobalOptions(globals))
    pass


@api_router.post("/node/add/")
def add_node(wf: Workflow):
    SESSION.handle_command(AddWorkflow(workflow=wf))
    return JSONResponse(dict())


@api_router.post("/node/update/")
def update_node(wf: Workflow):
    SESSION.handle_command(EditWorkflow(workflow=wf))
    return JSONResponse(dict())


@api_router.delete("/delete/")
def remove_node(selection: Selection):
    cmds = []
    for edge_id in selection.edges:
        cmds.append(RemoveTransition(edge_id))

    for node_id in selection.nodes:
        cmds.append(RemoveWorkflow(node_id))

    SESSION.handle_command(Transaction(tuple(cmds)))
    return JSONResponse(dict())


@api_router.post("/edge/add/")
def add_edge(tr: Transition):
    SESSION.handle_command(AddTransition(tr))
    return JSONResponse(dict())


@api_router.post("/edge/update/")
def update_edge(tr: Transition):
    SESSION.handle_command(EditTransition(transition=tr))
    return JSONResponse(dict())


@api_router.get("/nfcore/pipelines/")
def get_all_nfcore_pipelines():
    return get_nfcore_pipelines()


app.include_router(api_router, prefix="/api")
