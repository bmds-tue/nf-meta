import os
import httpx

from .serializers import serialize_graph, Node, Edge

from nf_meta.engine.session import SESSION
from nf_meta.engine.nf_core_utils import get_nfcore_pipelines
from nf_meta.engine.models import Workflow
from nf_meta.engine.events import AddTransition, AddWorkflow, RemoveWorkflow

from fastapi import FastAPI, APIRouter, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pathlib import Path


DEV_MODE = int(os.getenv("NF_META_DEVMODE", 0)) == 1
VITE_URL = "http://localhost:5173"
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend_dist"

app = FastAPI(title="metapipeline_editor")
api_router = APIRouter()

def setup_dev_proxy(app: FastAPI):
    """
    Setup up a proxy to serve statics via vite dev server
    """
    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def vite_proxy(path: str, request: Request):
        
        url = f"{VITE_URL}/{path}"

        client = httpx.AsyncClient()

        upstream = await client.send(
            client.build_request(
                request.method,
                url,
                headers=request.headers.raw,
                content=await request.body(),
            ),
            stream=True
        )

        return StreamingResponse(
            upstream.aiter_raw(),
            status_code=upstream.status_code,
            headers=dict(upstream.headers),
            background=lambda: client.aclose()
        )


def setup_static(app: FastAPI):
    """
    Setup static file serving for production from local dir
    """
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/")
    def serve_ui():
        return FileResponse(DIST_DIR / "index.html")

    # SPA fallback
    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
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


@api_router.post("/node/add")
def add_node(node: Node):
    wf = node.to_workflow()
    return SESSION.handle_command(AddWorkflow(wf))


@api_router.post("node/remove")
def remove_node(node: Node):
    wf = node.to_workflow()
    return SESSION.handle_command(RemoveWorkflow(wf))


@api_router.get("nfcore/pipelines")
def get_nfcore_pipelines():
    return get_nfcore_pipelines()


app.include_router(api_router, prefix="/api")
if DEV_MODE:
    setup_dev_proxy(app)
else:
    setup_static(app)
