import os
import signal
import stat

import pytest

from nf_meta.editor import EditorOptions, browser_editor
from nf_meta.editor.backend.guard import host_name
from nf_meta.editor.browser_editor import _editor_url, _redirect_folder, _write_redirect_file


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", "http://127.0.0.1:8080/?token=abc"),
        ("0.0.0.0", "http://127.0.0.1:8080/?token=abc"),
        ("::1", "http://[::1]:8080/?token=abc"),
        ("csdnode1", "http://csdnode1:8080/?token=abc"),
    ],
)
def test_editor_url(host, expected):
    assert _editor_url(host, 8080, "abc") == expected


@pytest.mark.parametrize(
    ("header", "name"),
    [("localhost:8080", "localhost"), ("127.0.0.1", "127.0.0.1"), ("[::1]:8080", "::1"), ("::1", "::1")],
)
def test_host_name(header, name):
    assert host_name(header) == name


def test_browser_opens_the_link(monkeypatch):
    launched = []
    monkeypatch.setattr(browser_editor, "_wait_for_backend", lambda host, port: None)
    monkeypatch.setattr(browser_editor.click, "launch", launched.append)
    browser_editor._open_browser_when_ready("127.0.0.1", 8080, "http://127.0.0.1:8080/?token=abc")
    assert launched == ["http://127.0.0.1:8080/?token=abc"]


def test_redirect_file_is_private_and_forwards_to_the_url(tmp_path):
    page = _write_redirect_file("http://127.0.0.1:8080/?token=a&b", tmp_path)
    assert page.parent == tmp_path
    assert stat.S_IMODE(page.stat().st_mode) == 0o600
    assert 'url=http://127.0.0.1:8080/?token=a&amp;b"' in page.read_text()


def test_redirect_files_of_ended_editors_are_removed(tmp_path):
    ended = tmp_path / "editor-999999999-abc.html"
    running = tmp_path / f"editor-{os.getpid()}-abc.html"
    unknown = tmp_path / "editor-abc.html"
    for page in (ended, running, unknown):
        page.write_text("x")
    _write_redirect_file("http://127.0.0.1:8080/?token=abc", tmp_path)
    assert not ended.exists()
    assert not unknown.exists()
    assert running.exists()


@pytest.mark.parametrize("runtime", [True, False])
def test_redirect_folder_is_private(monkeypatch, tmp_path, runtime):
    if runtime:
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
        expected = tmp_path / "run" / "nf-meta-editor"
    else:
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        expected = tmp_path / ".cache" / "nf-meta" / "editor"
    folder = _redirect_folder()
    assert folder == expected
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700


class FakeServer:
    should_exit = False


def test_stop_asks_the_server_to_exit(capsys):
    editor = browser_editor.BrowserEditor(EditorOptions())
    editor._server = FakeServer()
    editor.stop()
    assert editor._server.should_exit
    assert capsys.readouterr().out == "Stopping the editor backend\n"


def test_stop_without_a_running_server_does_nothing(capsys):
    editor = browser_editor.BrowserEditor(EditorOptions())
    editor.stop()
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("env", "platform", "expected"),
    [
        ({}, "linux", False),  # e.g. an HPC login node
        ({"DISPLAY": ":0"}, "linux", True),
        ({"WAYLAND_DISPLAY": "wayland-0"}, "linux", True),
        ({"BROWSER": "/vscode/helpers/browser.sh"}, "linux", True),  # VS Code remote terminal
        ({}, "darwin", True),
    ],
)
def test_can_open_browser(env, platform, expected):
    assert browser_editor._can_open_browser(env, platform) is expected


def test_tunnel_hint_over_ssh(monkeypatch):
    monkeypatch.setattr(browser_editor.getpass, "getuser", lambda: "alice")
    monkeypatch.setattr(browser_editor.socket, "gethostname", lambda: "login01")
    hint = browser_editor._tunnel_hint(8080, {"SSH_CONNECTION": "10.0.0.2 51000 10.0.0.1 22"})
    assert "ssh -N -L 8080:localhost:8080 alice@login01" in hint


def test_no_tunnel_hint_without_ssh():
    assert browser_editor._tunnel_hint(8080, {}) is None


@pytest.fixture
def restore_signals():
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}
    yield
    for sig, handler in saved.items():
        signal.signal(sig, handler)


def test_signals_exit_cleanly(restore_signals):
    signal.signal(signal.SIGHUP, signal.SIG_DFL)
    browser_editor._exit_cleanly_on_signals()
    assert signal.getsignal(signal.SIGTERM) is browser_editor._exit_on_signal
    assert signal.getsignal(signal.SIGHUP) is browser_editor._exit_on_signal


def test_ignored_sighup_stays_ignored(restore_signals):
    signal.signal(signal.SIGHUP, signal.SIG_IGN)  # as under nohup
    browser_editor._exit_cleanly_on_signals()
    assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
