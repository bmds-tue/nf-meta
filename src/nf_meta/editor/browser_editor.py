import http.client
import logging
import socket
import threading
import time

import click
import uvicorn

from .backend import DEV_HOST, DEV_MODE, DEV_PORT, DEV_VITE_PORT, app, configure_access, new_token
from .backend.guard import WILDCARD_HOSTS
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
    except (OSError, http.client.HTTPException):
        return False


def _wait_for_backend(host: str, port: int, timeout: int = 5) -> None:
    start = time.time()
    while time.time() - start < timeout:
        if _is_http_server_reachable(host, port):
            return
        time.sleep(0.1)
    raise RuntimeError("Server did not start")


def _editor_url(host: str, port: int, token: str) -> str:
    """The page's address with the session token; a wildcard host is shown as `127.0.0.1`."""
    if host.strip("[]") in WILDCARD_HOSTS:
        host = "127.0.0.1"
    elif ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{port}/?token={token}"


def _open_browser_when_ready(host: str, port: int, url: str) -> None:
    _wait_for_backend(host, port)
    click.launch(url)


class BrowserEditor(BaseEditor):
    """The default editor (`EDITOR_NAME = "browser"`). Serves the bundled Vue
    single-page app via a local FastAPI backend and opens it in a browser tab
    once the server is reachable.

    With `NF_META_DEVMODE=1` set, proxies to a separately-running frontend
    dev server (`npm run dev` under `editor/frontend`) instead of the bundled
    build -- see `docs/contributing.md`.
    """

    EDITOR_NAME = "browser"

    def start(self) -> None:
        host = self.options.host
        port = self.options.port
        token = new_token()

        if DEV_MODE:
            logger.debug(
                "DEV_MODE is set: ignoring host/port preferences and running on %s:%s (api) and %s:%s (vite)",
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

            configure_access(app, token)
            self._serve(
                DEV_HOST, DEV_PORT, _editor_url(DEV_HOST, DEV_VITE_PORT, token), wait_on=(DEV_HOST, DEV_VITE_PORT)
            )
        else:
            if port is None:
                port = _find_free_port()
            configure_access(app, token, bind_host=host)
            if host.strip("[]") in WILDCARD_HOSTS:
                click.echo(
                    click.style(
                        f"Listening on all network interfaces ({host}): anyone who can reach this machine "
                        "can reach the editor; the token in the link is its only protection.",
                        fg="yellow",
                    )
                )
            self._serve(host, port, _editor_url(host, port, token), wait_on=(host, port))

    def _serve(self, host: str, port: int, url: str, wait_on: tuple[str, int]) -> None:
        thread = threading.Thread(target=_open_browser_when_ready, args=(*wait_on, url), daemon=True)
        thread.start()
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        click.echo(f"Editor running at: {url}")
        uvicorn.Server(config).run()
