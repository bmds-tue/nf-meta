import os
import stat
import time

import pytest

from nf_meta.editor import browser_editor
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


def test_browser_opens_the_redirect_file_and_removes_it(monkeypatch, tmp_path):
    launched = []
    monkeypatch.setattr(browser_editor, "_wait_for_backend", lambda host, port: None)
    monkeypatch.setattr(browser_editor.click, "launch", launched.append)
    page = _write_redirect_file("http://127.0.0.1:8080/?token=abc", tmp_path)
    browser_editor._open_browser_when_ready("127.0.0.1", 8080, page.as_uri(), page, keep_page=0)
    assert launched == [page.as_uri()]
    assert not page.exists()


def test_redirect_file_is_private_and_forwards_to_the_url(tmp_path):
    page = _write_redirect_file("http://127.0.0.1:8080/?token=a&b", tmp_path)
    assert page.parent == tmp_path
    assert stat.S_IMODE(page.stat().st_mode) == 0o600
    assert 'url=http://127.0.0.1:8080/?token=a&amp;b"' in page.read_text()


def test_redirect_files_of_earlier_runs_are_removed(tmp_path):
    old = tmp_path / "editor-old.html"
    old.write_text("x")
    an_hour_ago = time.time() - 3600
    os.utime(old, (an_hour_ago, an_hour_ago))
    recent = tmp_path / "editor-recent.html"
    recent.write_text("x")
    _write_redirect_file("http://127.0.0.1:8080/?token=abc", tmp_path)
    assert not old.exists()
    assert recent.exists()


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
