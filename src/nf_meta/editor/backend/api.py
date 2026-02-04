from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

DIST_DIR = Path(__file__).resolve().parent.parent / "frontend_dist"


app = FastAPI(title="metapipeline_editor")
app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

# entrypoint, serves the vue application
@app.get("/")
def serve_ui():
    return FileResponse(DIST_DIR / "index.html")

