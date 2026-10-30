import getpass
import html
import http.client
import logging
import os
import signal
import socket
import sys
import tempfile
import threading
import time
from collections.abc import Mapping
from pathlib import Path

import click
import uvicorn

from .backend import DEV_HOST, DEV_MODE, DEV_PORT, DEV_VITE_PORT, app, configure_access, configure_shutdown, new_token
from .backend.guard import LOOPBACK_HOSTS, WILDCARD_HOSTS
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


def _redirect_folder() -> Path:
    """A folder only the current user can read: `$XDG_RUNTIME_DIR/nf-meta-editor`,
    else `~/.cache/nf-meta/editor`."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    folder = Path(runtime) / "nf-meta-editor" if runtime else Path.home() / ".cache" / "nf-meta" / "editor"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.chmod(0o700)
    return folder


def _process_running(pid: int) -> bool:
    if os.name == "nt":
        return True  # os.kill would stop the process on Windows
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _write_redirect_file(url: str, folder: Path) -> Path:
    """A page, readable only by the current user, that forwards the browser to
    `url`; the caller removes it when the editor stops. Removes the pages of
    editors that ended without doing so."""
    for old in folder.glob("editor-*.html"):
        pid = old.name.split("-")[1]
        if not pid.isdigit() or not _process_running(int(pid)):
            old.unlink(missing_ok=True)
    fd, name = tempfile.mkstemp(prefix=f"editor-{os.getpid()}-", suffix=".html", dir=folder)
    with os.fdopen(fd, "w") as f:
        target = html.escape(url, quote=True)
        f.write(
            f'<!doctype html><meta http-equiv="refresh" content="0;url={target}"><a href="{target}">Open the editor</a>\n'
        )
    return Path(name)


def _open_browser_when_ready(host: str, port: int, target: str) -> None:
    _wait_for_backend(host, port)
    click.launch(target)


def _can_open_browser(env: Mapping[str, str] = os.environ, platform: str = sys.platform) -> bool:
    """False on a Linux machine without a display (e.g. an HPC login node) unless `$BROWSER` names
    a way to open links (as VS Code's remote terminals do)."""
    if env.get("BROWSER"):
        return True
    if platform.startswith("linux"):
        # without a display, xdg-open falls back to text browsers (lynx, w3m) in this terminal
        return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))
    return True


def _tunnel_hint(port: int, env: Mapping[str, str] = os.environ) -> str | None:
    """For an editor started over SSH: how to reach it from the user's own computer."""
    if "SSH_CONNECTION" not in env:
        return None
    return (
        "Started over SSH: to use the editor from your own computer, forward its port there\n"
        f"    ssh -N -L {port}:localhost:{port} {getpass.getuser()}@{socket.gethostname()}\n"
        "(with the host name you log in with), then open the link above in your browser."
    )


def _exit_on_signal(signum, frame) -> None:
    raise SystemExit(128 + signum)


def _exit_cleanly_on_signals() -> None:
    """Turn SIGTERM and SIGHUP into a normal exit, so clean-up code runs. An ignored SIGHUP
    (started with `nohup`) stays ignored, so the editor outlives the terminal or SSH session."""
    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)  # no SIGHUP on Windows
        if sig is not None and signal.getsignal(sig) is not signal.SIG_IGN:
            signal.signal(sig, _exit_on_signal)


class BrowserEditor(BaseEditor):
    """The default editor (`EDITOR_NAME = "browser"`). Serves the bundled Vue
    single-page app via a local FastAPI backend and opens it in a browser tab
    once the server is reachable.

    With `NF_META_DEVMODE=1` set, proxies to a separately-running frontend
    dev server (`npm run dev` under `editor/frontend`) instead of the bundled
    build -- see `docs/contributing.md`.
    """

    EDITOR_NAME = "browser"

    _server: uvicorn.Server | None = None

    def stop(self) -> None:
        """Stop the running editor; it answers the requests in progress first.
        Does nothing when it isn't running."""
        if self._server is None:
            return
        click.echo("Stopping the editor backend")
        self._server.should_exit = True

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
                        f"Listening on all network interfaces ({host}): anyone with access to this machine "
                        "can reach the editor.",
                        fg="yellow",
                    )
                )
            hint = _tunnel_hint(port) if host.strip("[]") in LOOPBACK_HOSTS else None
            self._serve(host, port, _editor_url(host, port, token), wait_on=(host, port), hint=hint)

    def _serve(self, host: str, port: int, url: str, wait_on: tuple[str, int], hint: str | None = None) -> None:
        open_browser = self.options.open_browser and _can_open_browser()
        page = None
        if open_browser:
            page = _write_redirect_file(url, _redirect_folder()) if self.options.use_redirect_file else None
            # The browser gets a local file, so the token doesn't show in a process's arguments
            target = page.as_uri() if page else url
            thread = threading.Thread(target=_open_browser_when_ready, args=(*wait_on, target), daemon=True)
            thread.start()
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        click.echo(f"Editor running at: {url}")
        if page:
            click.echo("If no browser tab opens, open this link, or start with --no-redirect-file.")
        if hint:
            click.echo(hint)
        # uvicorn re-sends the SIGTERM it stopped on, and doesn't handle SIGHUP (terminal or SSH
        # connection closed); either would end the process without the clean-up below
        _exit_cleanly_on_signals()
        self._server = uvicorn.Server(config)
        configure_shutdown(app, self.stop)
        try:
            self._server.run()
        finally:
            if page:
                page.unlink(missing_ok=True)
