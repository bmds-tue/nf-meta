import os

from .serializers import serialize_graph, Node, Edge

from nf_meta.engine.session import SESSION
from nf_meta.engine.nf_core_utils import get_nfcore_pipelines
from nf_meta.engine.models import Workflow
from nf_meta.engine.events import (AddTransition, AddWorkflow, 
                                    RemoveWorkflow, RemoveTransition,
                                    EditWorkflow, EditTransition)

from fastapi import FastAPI, APIRouter, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
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


@app.api_route("/")
def serve_ui():
    if DEV_MODE:
        return RedirectResponse(f"http://localhost:{DEV_VITE_PORT}/")
    return FileResponse(DIST_DIR / "index.html")


@api_router.get("/graph/")
def get_graph():
    return serialize_graph(SESSION.graph)


@api_router.post("/graph/save/")
def save_graph(config: Path):
    SESSION.save_to_config(config)
    return serialize_graph(SESSION.graph)


@api_router.post("/graph/load/")
def load_graph(config: Path):
    SESSION.load_config(config)
    return serialize_graph(SESSION.graph)


@api_router.post("/node/add/")
def add_node(node: Node):
    wf = node.to_workflow()
    SESSION.handle_command(AddWorkflow(wf))
    return Response()


@api_router.post("/node/update/")
def update_node(node: Node):
    # TODO: Rework EditWorkflow, EditTransition apply()
    #wf = node.to_workflow()
    #SESSION.handle_command(EditWorkflow(wf))
    return Response()


@api_router.delete("/node/")
def remove_node(node: Node):
    wf = node.to_workflow()
    SESSION.handle_command(RemoveWorkflow(wf))
    return Response()


@api_router.post("/edge/add/")
def add_edge(edge: Edge):
    tr = edge.to_transition()
    SESSION.handle_command(AddTransition(tr))
    return Response()


@api_router.post("/edge/update/")
def update_edge(edge: Edge):
    # TODO: Rework EditWorkflow, EditTransition apply()
    # tr = edge.to_transition()
    # SESSION.handle_command(EditTransition(tr))
    return Response()


@api_router.delete("/edge/")
def delete_edge(edge: Edge):
    tr = edge.to_transition()
    SESSION.handle_command(RemoveTransition(tr))
    return Response()


@api_router.get("/nfcore/pipelines/")
def get_all_nfcore_pipelines():
    return get_nfcore_pipelines()


app.include_router(api_router, prefix="/api")
