"""Registry lookups: error contract, failure memo."""

import json
from unittest.mock import MagicMock

import pytest
import requests

from nf_meta.core import registry
from nf_meta.core.dynamic_validation import check_module_version_in_registry, check_pipeline_main_script_exists
from nf_meta.core.errors import Severity
from nf_meta.core.models import NfModule, NfPipeline
from nf_meta.core.registry import (
    RegistryUnavailableError,
    _fetch_json,
    get_nfcore_module_releases,
    get_nfcore_pipelines,
)


@pytest.fixture(autouse=True)
def clean_registry_state():
    registry._recent_failures.clear()
    get_nfcore_pipelines.cache_clear()
    get_nfcore_module_releases.cache_clear()
    yield
    registry._recent_failures.clear()
    get_nfcore_pipelines.cache_clear()
    get_nfcore_module_releases.cache_clear()


def response(status: int, body: object = None, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.content = b"" if body is None else json.dumps(body).encode()
    resp.json.return_value = body
    return resp


class TestFetchJson:
    def test_returns_parsed_json(self, monkeypatch):
        monkeypatch.setattr(registry.requests, "get", lambda *a, **k: response(200, {"a": 1}))
        assert _fetch_json("https://x/a", "thing") == {"a": 1}

    def test_not_found_is_none(self, monkeypatch):
        monkeypatch.setattr(registry.requests, "get", lambda *a, **k: response(404))
        assert _fetch_json("https://x/a", "thing") is None

    @pytest.mark.parametrize(
        "behavior",
        [
            requests.exceptions.ConnectionError("down"),
            requests.exceptions.Timeout("slow"),
            response(429, headers={"Retry-After": "60"}),
            response(500, {"error": "x"}),
        ],
    )
    def test_failures_raise(self, monkeypatch, behavior):
        def get(*a, **k):
            if isinstance(behavior, Exception):
                raise behavior
            return behavior

        monkeypatch.setattr(registry.requests, "get", get)
        with pytest.raises(RegistryUnavailableError):
            _fetch_json("https://x/a", "thing")

    def test_malformed_json_raises(self, monkeypatch):
        resp = response(200, {"a": 1})
        resp.json.side_effect = ValueError("bad")
        monkeypatch.setattr(registry.requests, "get", lambda *a, **k: resp)
        with pytest.raises(RegistryUnavailableError, match="Invalid JSON"):
            _fetch_json("https://x/a", "thing")

    def test_a_failure_is_not_retried_right_away(self, monkeypatch):
        calls = []

        def get(*a, **k):
            calls.append(1)
            raise requests.exceptions.ConnectionError("down")

        monkeypatch.setattr(registry.requests, "get", get)
        for _ in range(3):
            with pytest.raises(RegistryUnavailableError, match="down"):
                _fetch_json("https://x/a", "thing")
        assert len(calls) == 1

    def test_failure_is_retried_after_the_memo_expires(self, monkeypatch):
        calls = []

        def get(*a, **k):
            calls.append(1)
            raise requests.exceptions.ConnectionError("down")

        monkeypatch.setattr(registry.requests, "get", get)
        monkeypatch.setattr(registry, "_FAILURE_TTL", 0.0)
        for _ in range(2):
            with pytest.raises(RegistryUnavailableError):
                _fetch_json("https://x/a", "thing")
        assert len(calls) == 2


class TestCatalogs:
    def test_unreachable_pipeline_catalog_raises(self, monkeypatch):
        monkeypatch.setattr(registry.requests, "get", lambda *a, **k: response(503))
        with pytest.raises(RegistryUnavailableError):
            get_nfcore_pipelines()

    def test_unknown_module_has_no_releases(self, monkeypatch):
        monkeypatch.setattr(registry.requests, "get", lambda *a, **k: response(404))
        assert get_nfcore_module_releases("nosuchmodule") == []

    def test_module_releases_accept_the_nf_core_prefix(self, monkeypatch):
        urls = []

        def get(url, **k):
            urls.append(url)
            return response(200, {"releases": []})

        monkeypatch.setattr(registry.requests, "get", get)
        get_nfcore_module_releases("nf-core/fastqc")
        assert urls[0].endswith("/nf-core%2Ffastqc/releases")


class TestPipelineLookupErrors:
    def test_custom_pipeline_does_not_need_the_catalog(self, monkeypatch):
        def unreachable():
            raise RegistryUnavailableError("offline")

        monkeypatch.setattr("nf_meta.core.models.get_nfcore_pipelines", unreachable)
        wf = NfPipeline(name="my-org/pipeline", version="1.0.0", url="https://github.com/my-org/pipeline")
        assert wf.is_nfcore is False

    def test_unreachable_catalog_is_reported(self, monkeypatch):
        def unreachable():
            raise RegistryUnavailableError("offline")

        monkeypatch.setattr("nf_meta.core.models.get_nfcore_pipelines", unreachable)
        with pytest.raises(ValueError, match="Can't look up 'nf-core/rnaseq' in the nf-core catalog: offline"):
            NfPipeline(name="nf-core/rnaseq", version="3.14.0")

    def test_unknown_name_suggests_a_close_one(self):
        with pytest.raises(
            ValueError, match="'nf-core/rnaseqq' is not an nf-core pipeline. Did you mean 'nf-core/rnaseq'"
        ):
            NfPipeline(name="nf-core/rnaseqq", version="3.14.0")

    def test_mismatching_url(self):
        with pytest.raises(ValueError, match="doesn't match nf-core's url"):
            NfPipeline(name="nf-core/rnaseq", version="3.14.0", url="https://github.com/someone/rnaseq")


class TestChecksWhenUnavailable:
    def test_module_version_check_warns(self, monkeypatch):
        def unreachable(name):
            raise RegistryUnavailableError("offline")

        monkeypatch.setattr("nf_meta.core.dynamic_validation.get_nfcore_module_releases", unreachable)
        [d] = check_module_version_in_registry(NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a"))
        assert d.severity == Severity.WARNING
        assert "offline" in d.message

    def test_main_script_check_warns(self, monkeypatch, wf_custom):
        def unreachable(url, path, ref):
            raise RegistryUnavailableError("rate-limited")

        monkeypatch.setattr("nf_meta.core.dynamic_validation.github_file_exists", unreachable)
        wf = wf_custom.model_copy(update={"main_script": "main.nf"})
        [d] = check_pipeline_main_script_exists(wf)
        assert d.severity == Severity.WARNING
