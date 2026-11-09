"""Registry lookups: error contract, failure memo, module metadata."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from nf_meta.core import registry
from nf_meta.core.dynamic_validation import check_module_version_in_registry, check_pipeline_main_script_exists
from nf_meta.core.errors import Severity
from nf_meta.core.models import NfModule, NfPipeline
from nf_meta.core.registry import (
    NotInRegistryError,
    RegistryUnavailableError,
    _fetch_json,
    get_module_metadata,
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


class TestModuleMetadata:
    RELEASES = [
        {"version": "0.0.0-aaaaaaa", "createdAt": "2025-01-01", "metadata": {"description": "old"}},
        {"version": "0.0.0-bbbbbbb", "createdAt": "2026-01-01", "metadata": {"description": "new"}},
    ]

    @pytest.fixture(autouse=True)
    def releases(self, monkeypatch):
        monkeypatch.setattr(registry, "get_nfcore_module_releases", lambda name: self.RELEASES if name else [])

    def test_latest_by_default(self):
        assert get_module_metadata("fastqc")["version"] == "0.0.0-bbbbbbb"

    def test_given_version(self):
        assert get_module_metadata("fastqc", "0.0.0-aaaaaaa")["metadata"]["description"] == "old"

    def test_unknown_version(self):
        with pytest.raises(NotInRegistryError, match="Version"):
            get_module_metadata("fastqc", "9.9.9")

    def test_unknown_module(self):
        with pytest.raises(NotInRegistryError, match="not found"):
            get_module_metadata("")


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

        monkeypatch.setattr("nf_meta.core.dynamic_validation.repo_file_exists", unreachable)
        wf = wf_custom.model_copy(update={"main_script": "main.nf"})
        [d] = check_pipeline_main_script_exists(wf)
        assert d.severity == Severity.WARNING


def test_editor_answers_503_when_unavailable():
    from nf_meta.editor.backend.api import handle_registry_unavailable

    resp = handle_registry_unavailable(None, RegistryUnavailableError("offline"))  # type: ignore[arg-type]
    assert resp.status_code == 503
    assert json.loads(resp.body) == {"detail": "offline"}


class TestRegistryModuleName:
    @pytest.mark.parametrize(
        ("config_name", "registry_name"),
        [
            ("nf-core/fastqc", "nf-core/fastqc"),
            ("nf-core/samtools_stats", "nf-core/samtools/stats"),
            ("nf-core/plastid_make_wiggle", "nf-core/plastid/make_wiggle"),
            ("nf-core/samtools/stats", "nf-core/samtools/stats"),
            ("my-custom-module", "my-custom-module"),
            ("nf-core/notincatalog_sub", "nf-core/notincatalog/sub"),
        ],
    )
    def test_mapping(self, config_name, registry_name):
        assert registry.registry_module_name(config_name) == registry_name

    def test_without_the_catalog_underscores_become_slashes(self, monkeypatch):
        def unreachable():
            raise RegistryUnavailableError("offline")

        monkeypatch.setattr(registry, "_get_nfcore_components_raw", unreachable)
        assert registry.registry_module_name("nf-core/plastid_make_wiggle") == "nf-core/plastid/make/wiggle"

    def test_releases_use_the_registry_name(self, monkeypatch):
        urls = []

        def get(url, **k):
            urls.append(url)
            return response(200, {"releases": []})

        monkeypatch.setattr(registry.requests, "get", get)
        get_nfcore_module_releases("plastid_make_wiggle")
        assert urls[0].endswith("/nf-core%2Fplastid%2Fmake_wiggle/releases")

    def test_schema_uses_the_repository_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr("nf_meta.core.cache.read_schema_cache", lambda *a: None)
        monkeypatch.setattr("nf_meta.core.cache.write_schema_cache", lambda *a: None)
        registry.get_module_schema.cache_clear()
        urls = []

        def get(url, **k):
            urls.append(url)
            resp = response(200)
            resp.text = "input: []"
            return resp

        monkeypatch.setattr(registry.requests, "get", get)
        registry.get_module_schema("nf-core/plastid_make_wiggle", "0.0.0-6c4ed3a")
        registry.get_module_schema.cache_clear()
        assert urls[0].endswith("/6c4ed3a/modules/nf-core/plastid/make_wiggle/meta.yml")


class TestRepoFileExists:
    @pytest.fixture
    def host(self, monkeypatch):
        """Answers each HEAD request with `host.status` and records it in `host.calls`."""
        host = SimpleNamespace(status=200, calls=[])

        def head(url, **kwargs):
            host.calls.append((url, kwargs))
            return MagicMock(status_code=host.status, headers={})

        monkeypatch.setattr(registry.requests, "head", head)
        registry.repo_file_exists.cache_clear()
        yield host
        registry.repo_file_exists.cache_clear()

    @pytest.mark.parametrize(
        ("url", "raw"),
        [
            ("https://github.com/org/my.repo", "https://raw.githubusercontent.com/org/my.repo/v1/sub/main.nf"),
            ("https://github.com/org/my.repo.git", "https://raw.githubusercontent.com/org/my.repo/v1/sub/main.nf"),
            ("https://gitlab.com/org/repo", "https://gitlab.com/org/repo/-/raw/v1/sub/main.nf"),
            ("https://bitbucket.org/org/repo", "https://bitbucket.org/org/repo/raw/v1/sub/main.nf"),
        ],
    )
    def test_asks_for_the_raw_file(self, host, url, raw):
        assert registry.repo_file_exists(url, "sub/main.nf", "v1")
        assert host.calls[0][0] == raw
        assert host.calls[0][1]["allow_redirects"] is False

    @pytest.mark.parametrize(
        ("url", "env", "header", "value"),
        [
            ("https://github.com/org/private", "GITHUB_TOKEN", "Authorization", "Bearer secret"),
            ("https://gitlab.com/org/private", "GITLAB_TOKEN", "PRIVATE-TOKEN", "secret"),
        ],
    )
    def test_sends_the_token(self, host, monkeypatch, url, env, header, value):
        monkeypatch.setenv(env, "secret")
        registry.repo_file_exists(url, "main.nf", "v1")
        assert host.calls[0][1]["headers"][header] == value

    def test_missing_file(self, host):
        host.status = 404
        assert not registry.repo_file_exists("https://github.com/org/repo", "main.nf", "v1")

    @pytest.mark.parametrize("status", [302, 403, 429, 500])
    def test_unclear_answers_are_unavailable(self, host, status):
        host.status = status
        with pytest.raises(RegistryUnavailableError):
            registry.repo_file_exists("https://gitlab.com/org/repo", "main.nf", "v1")

    def test_network_error_is_unavailable(self, host, monkeypatch):
        def head(url, **kwargs):
            raise requests.exceptions.ConnectionError("offline")

        monkeypatch.setattr(registry.requests, "head", head)
        with pytest.raises(RegistryUnavailableError, match="offline"):
            registry.repo_file_exists("https://github.com/org/repo", "main.nf", "v1")

    def test_falls_back_to_get_without_head(self, host, monkeypatch):
        host.status = 405
        get = MagicMock(return_value=MagicMock(status_code=200))
        monkeypatch.setattr(registry.requests, "get", get)
        assert registry.repo_file_exists("https://bitbucket.org/org/repo", "main.nf", "v1")
        assert get.call_args.kwargs["stream"] is True

    def test_other_hosts_are_not_asked(self, host):
        with pytest.raises(registry.PipelineSchemaError):
            registry.repo_file_exists("https://example.org/org/repo", "main.nf", "v1")
        assert host.calls == []
