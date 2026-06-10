import http.client
import logging
import socket
import threading
import time

import click
import uvicorn

from .backend import app, DEV_MODE, DEV_HOST, DEV_PORT, DEV_VITE_PORT
from .base_editor import BaseEditor


logger = logging.getLogger(__name__)


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _is_http_server_reachable(host: str, port: int, timeout: int = 1) -> bool:
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("GET", "/")
        conn.getresponse()
        conn.close()
        return True
    except Exception:
        return False


def _wait_for_backend(host: str, port: int, timeout: int = 5) -> None:
    start = time.time()
    while time.time() - start < timeout:
        if _is_http_server_reachable(host, port):
            return
        time.sleep(0.1)
    raise RuntimeError("Server did not start")


def _open_browser_when_ready(host: str, port: int) -> None:
    _wait_for_backend(host, port)
    click.launch(f"http://{host}:{port}")


class BrowserEditor(BaseEditor):
    """Default editor: serves the Vue SPA via FastAPI and opens a browser tab."""

    EDITOR_NAME = "browser"

    def start(self) -> None:
        host = self.options.host
        port = self.options.port

        if DEV_MODE:
            logger.debug(
                "DEV_MODE is set: ignoring host/port preferences and running on "
                "%s:%s (api) and %s:%s (vite)",
                DEV_HOST,
                DEV_PORT,
                DEV_HOST,
                DEV_VITE_PORT,
            )
            if not _is_http_server_reachable(DEV_HOST, DEV_VITE_PORT):
                click.echo(
                    click.style(
                        f"[DEV_MODE] Vite dev server not reachable on {DEV_HOST}:{DEV_VITE_PORT}. "
                        "Start it first: cd src/nf_meta/editor/frontend && npm run dev",
                        fg="yellow",
                    )
                )
                raise SystemExit(1)

            thread = threading.Thread(
                target=_open_browser_when_ready,
                args=(DEV_HOST, DEV_VITE_PORT),
                daemon=True,
            )
            thread.start()

            config = uvicorn.Config(
                app, host=DEV_HOST, port=DEV_PORT, log_level="warning"
            )
            print(f"Starting editor on: http://{DEV_HOST}:{DEV_VITE_PORT}/")
            uvicorn.Server(config).run()
        else:
            if port is None:
                port = _find_free_port()

            thread = threading.Thread(
                target=_open_browser_when_ready, args=(host, port), daemon=True
            )
            thread.start()

            config = uvicorn.Config(app, host=host, port=port, log_level="warning")
            print(f"Starting editor on: http://{host}:{port}/")
            uvicorn.Server(config).run()
