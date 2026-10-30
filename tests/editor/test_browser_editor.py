import pytest

from nf_meta.editor import browser_editor
from nf_meta.editor.backend.guard import host_name
from nf_meta.editor.browser_editor import _editor_url


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
