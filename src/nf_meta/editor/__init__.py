import threading
import time
import socket
import click
import uvicorn

from .backend import app

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
    if port is None:
        port = find_free_port()

    thread = threading.Thread(
        target=open_browser_when_ready,
        args=(host, port),
        daemon=False
    )

    thread.start()

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
    )

    print(f"Starting editor on: http://{host}:{port}/")
    server = uvicorn.Server(config)

    server.run()
