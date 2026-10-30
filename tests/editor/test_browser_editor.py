import stat

import pytest

from nf_meta.editor.backend.guard import host_name
from nf_meta.editor.browser_editor import _editor_url, _write_redirect_file


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


def test_redirect_file_is_private_and_forwards_to_the_url():
    page = _write_redirect_file("http://127.0.0.1:8080/?token=a&b")
    try:
        assert stat.S_IMODE(page.stat().st_mode) == 0o600
        assert 'url=http://127.0.0.1:8080/?token=a&amp;b"' in page.read_text()
    finally:
        page.unlink()


@pytest.mark.parametrize(
    ("header", "name"),
    [("localhost:8080", "localhost"), ("127.0.0.1", "127.0.0.1"), ("[::1]:8080", "::1"), ("::1", "::1")],
)
def test_host_name(header, name):
    assert host_name(header) == name
