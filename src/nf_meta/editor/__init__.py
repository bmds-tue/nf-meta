import threading
import time
import socket
import click
import uvicorn
import logging

from .backend import app, DEV_MODE, DEV_PORT, DEV_VITE_PORT


logger = logging.getLogger()


def find_free_port():
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def wait_for_backend(host, port, timeout=5):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Server did not start")


def open_browser_when_ready(host, port):
    wait_for_backend(host, port)
    click.launch(f"http://{host}:{port}")


def start_editor_backend(host: str, port: int|None):
    api_port = port
    editor_port = port
    if DEV_MODE:
        logger.debug(f"DEV_MODE is set. Overwriting port preferences to {DEV_PORT} (api) and {DEV_VITE_PORT} (vite)")
        api_port = DEV_PORT
        editor_port = DEV_VITE_PORT
    if port is None:
        port = find_free_port()
        api_port = port
        editor_port = port

    thread = threading.Thread(
        target=open_browser_when_ready,
        args=(host, editor_port),
        daemon=False
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
