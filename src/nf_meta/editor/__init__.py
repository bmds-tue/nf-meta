import threading
import time
import socket
import http.client
import click
import uvicorn
import logging

from .backend import app, DEV_MODE, DEV_PORT, DEV_VITE_PORT


logger = logging.getLogger()


def find_free_port():
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def is_http_server_reachable(host, port, timeout=1) -> bool:
    try:
        conn = http.client.HTTPConnection(host, int(port), timeout=timeout)
        conn.request("GET", "/")
        conn.getresponse()
        conn.close()
        return True
    except Exception:
        return False


def wait_for_backend(host, port, timeout=5):
    start = time.time()
    while time.time() - start < timeout:
        if is_http_server_reachable(host, port):
            return
        time.sleep(0.1)
    raise RuntimeError("Server did not start")


def open_browser_when_ready(host, port):
    wait_for_backend(host, port)
    click.launch(f"http://{host}:{port}")


def start_editor_backend(host: str, port: int | None):
    if DEV_MODE:
        logger.debug(
            f"DEV_MODE is set: Ignoring port preferences and running on {DEV_PORT} (api) and {DEV_VITE_PORT} (vite)"
        )
        api_port = DEV_PORT
        editor_port = DEV_VITE_PORT

        if not is_http_server_reachable(host, editor_port):
            click.echo(
                click.style(
                    f"[DEV_MODE] Vite dev server not reachable on {host}:{editor_port}. "
                    "Start it first: cd src/nf_meta/editor/frontend && npm run dev",
                    fg="yellow",
                )
            )
            raise SystemExit(1)
    elif port is None:
        logger.debug("Automatically assigning free port")
        port = find_free_port()
        api_port = port
        editor_port = port
    else:
        api_port = port
        editor_port = port

    thread = threading.Thread(
        target=open_browser_when_ready, args=(host, editor_port), daemon=True
    )
    thread.start()

    config = uvicorn.Config(
        app,
        host=host,
        port=api_port,
        log_level="warning",
    )

    print(f"Starting editor on: http://{host}:{editor_port}/")
    server = uvicorn.Server(config)
    server.run()
