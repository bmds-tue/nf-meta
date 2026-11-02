import os
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
