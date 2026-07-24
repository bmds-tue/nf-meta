"""
Tests for the extracted network-backed ("tier-2") validation checks in
nf_meta.core.dynamic_validation.

The autouse mock_nfcore fixture (tests/conftest.py) already stubs out the
underlying HTTP-backed helpers on nf_meta.core.dynamic_validation.*, so
NfPipeline/NfModule construction never hits the network. Individual tests
override those same targets per-test to exercise specific check branches.
"""

import pytest

from nf_meta.core.dynamic_validation import (
    check_module_params_schema,
    check_module_version_in_registry,
    check_pipeline_main_script_exists,
    check_pipeline_params_schema,
    check_pipeline_url_reachable,
    check_all,
    run_dynamic_checks,
)
from nf_meta.core.errors import Severity
from nf_meta.core.models import NfModule, NfPipeline
from nf_meta.core.nf_core_utils import PipelineSchemaError


# ---------------------------------------------------------------------------
# check_pipeline_url_reachable
# ---------------------------------------------------------------------------


class TestCheckPipelineUrlReachable:
    def test_nfcore_workflow_skipped(self, wf_rnaseq, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.url_exists",
            lambda url, timeout=10: calls.append(url) or True,
        )
        assert check_pipeline_url_reachable(wf_rnaseq) == []
        assert calls == []

    def test_reachable_url_no_diagnostic(self, wf_custom, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.url_exists", lambda url, timeout=10: True
        )
        assert check_pipeline_url_reachable(wf_custom) == []

    def test_unreachable_url_warns(self, wf_custom, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.url_exists", lambda url, timeout=10: False
        )
        diagnostics = check_pipeline_url_reachable(wf_custom)
        assert len(diagnostics) == 1
        assert diagnostics[0].severity == Severity.WARNING
        assert "could not be reached" in diagnostics[0].message


# ---------------------------------------------------------------------------
# check_pipeline_main_script_exists
# ---------------------------------------------------------------------------


class TestCheckPipelineMainScriptExists:
    def test_no_main_script_returns_empty(self, wf_custom):
        assert check_pipeline_main_script_exists(wf_custom) == []

    def test_github_file_found_no_diagnostic(self, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.github_file_exists",
            lambda url, path, ref: True,
        )
        wf = NfPipeline(
            name="my-org/custom-pipeline",
            version="1.0.0",
            url="https://github.com/my-org/custom-pipeline",
            main_script="workflows/special.nf",
        )
        assert check_pipeline_main_script_exists(wf) == []

    def test_github_file_missing_raises_error(self, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.github_file_exists",
            lambda url, path, ref: False,
        )
        wf = NfPipeline(
            name="my-org/custom-pipeline",
            version="1.0.0",
            url="https://github.com/my-org/custom-pipeline",
            main_script="workflows/missing.nf",
        )
        diagnostics = check_pipeline_main_script_exists(wf)
        assert len(diagnostics) == 1
        assert diagnostics[0].severity == Severity.ERROR
        assert "not found" in diagnostics[0].message

    def test_non_github_url_warns(self):
        wf = NfPipeline(
            name="my-org/custom-pipeline",
            version="1.0.0",
            url="https://gitlab.com/my-org/custom-pipeline",
            main_script="workflows/special.nf",
        )
        diagnostics = check_pipeline_main_script_exists(wf)
        assert len(diagnostics) == 1
        assert diagnostics[0].severity == Severity.WARNING
        assert "Cannot validate" in diagnostics[0].message


# ---------------------------------------------------------------------------
# check_pipeline_params_schema
# ---------------------------------------------------------------------------


class TestCheckPipelineParamsSchema:
    SCHEMA = {
        "input": {
            "type": "string",
            "required": True,
            "enum": None,
            "pattern": None,
            "format": None,
            "default": None,
            "hidden": False,
        }
    }

    def test_missing_url_or_version_returns_empty(self, wf_rnaseq):
        # wf_rnaseq has url/version/name populated — force one missing via copy
        wf = wf_rnaseq.model_copy(update={"url": None})
        assert check_pipeline_params_schema(wf) == []

    def test_schema_fetch_error_warns(self, wf_rnaseq, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_pipeline_schema",
            lambda url, version: (_ for _ in ()).throw(PipelineSchemaError("boom")),
        )
        diagnostics = check_pipeline_params_schema(wf_rnaseq)
        assert len(diagnostics) == 1
        assert diagnostics[0].severity == Severity.WARNING
        assert "boom" in diagnostics[0].message

    def test_valid_params_no_diagnostics(self, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_pipeline_schema",
            lambda url, version: self.SCHEMA,
        )
        wf = NfPipeline(
            name="nf-core/rnaseq", version="3.14.0", params={"input": "/data/x.csv"}
        )
        assert check_pipeline_params_schema(wf) == []

    def test_required_param_missing_raises_error(self, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_pipeline_schema",
            lambda url, version: self.SCHEMA,
        )
        wf = NfPipeline(name="nf-core/rnaseq", version="3.14.0")
        diagnostics = check_pipeline_params_schema(wf)
        assert any(
            d.severity == Severity.ERROR and "Required parameter" in d.message
            for d in diagnostics
        )

    def test_malformed_params_file_warns_and_skips_required(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_pipeline_schema",
            lambda url, version: self.SCHEMA,
        )
        pf = tmp_path / "params.yaml"
        pf.write_text("- not\n- a\n- mapping\n")
        wf = NfPipeline(
            name="nf-core/rnaseq", version="3.14.0", params_file=str(pf)
        )
        diagnostics = check_pipeline_params_schema(wf)
        assert any(
            d.severity == Severity.WARNING and "does not contain a mapping" in d.message
            for d in diagnostics
        )
        # required-param check was skipped, so no ERROR about missing 'input'
        assert not any(d.severity == Severity.ERROR for d in diagnostics)


# ---------------------------------------------------------------------------
# check_module_version_in_registry
# ---------------------------------------------------------------------------


class TestCheckModuleVersionInRegistry:
    def test_non_nfcore_module_skipped(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: calls.append(name) or [],
        )
        wf = NfModule(name="my-custom-module", version="1.0.0")
        assert check_module_version_in_registry(wf) == []
        assert calls == []

    def test_no_releases_returned_skips_check(self, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [],
        )
        wf = NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")
        assert check_module_version_in_registry(wf) == []

    def test_valid_version_no_diagnostic(self, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [{"version": "0.0.0-6c4ed3a"}, {"version": "1.0.0-abcdefa"}],
        )
        wf = NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")
        assert check_module_version_in_registry(wf) == []

    def test_invalid_version_raises_error(self, monkeypatch):
        """Gap-fill: no prior test exercised this raising branch."""
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [{"version": "1.0.0-abcdefa"}, {"version": "2.0.0-fedcbaa"}],
        )
        wf = NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")
        diagnostics = check_module_version_in_registry(wf)
        assert len(diagnostics) == 1
        assert diagnostics[0].severity == Severity.ERROR
        assert diagnostics[0].field == "version"
        assert "not available in the Nextflow registry" in diagnostics[0].message


# ---------------------------------------------------------------------------
# check_module_params_schema
# ---------------------------------------------------------------------------


class TestCheckModuleParamsSchema:
    def test_empty_schema_returns_empty(self, module_fastqc, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_module_schema",
            lambda name, version: {},
        )
        assert check_module_params_schema(module_fastqc) == []

    def test_invalid_params_raises_error(self, monkeypatch):
        schema = {"reads": {"type": "file", "required": True}}
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_module_schema",
            lambda name, version: schema,
        )
        wf = NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")
        diagnostics = check_module_params_schema(wf)
        assert any(
            d.severity == Severity.ERROR and "Required parameter" in d.message
            for d in diagnostics
        )


# ---------------------------------------------------------------------------
# run_dynamic_checks — dispatch + skip-if-unchanged diffing
# ---------------------------------------------------------------------------


class TestRunDynamicChecks:
    def test_pipeline_dispatch_runs_pipeline_checks(self, wf_rnaseq, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.url_exists", lambda url, timeout=10: True
        )
        # wf_rnaseq is nf-core, so no checks should fail
        diagnostics = run_dynamic_checks(wf_rnaseq)
        assert not any(d.severity == Severity.ERROR for d in diagnostics)

    def test_module_dispatch_runs_module_checks(self, module_fastqc, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [],
        )
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_module_schema",
            lambda name, version: {},
        )
        assert run_dynamic_checks(module_fastqc) == []

    def test_previous_none_runs_all_checks(self, wf_custom, monkeypatch):
        calls = {"url": 0, "schema": 0}
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.url_exists",
            lambda url, timeout=10: calls.__setitem__("url", calls["url"] + 1) or True,
        )
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_pipeline_schema",
            lambda url, version: calls.__setitem__("schema", calls["schema"] + 1) or {},
        )
        run_dynamic_checks(wf_custom, previous=None)
        assert calls["url"] == 1
        assert calls["schema"] == 1

    def test_unchanged_fields_skip_all_checks(self, wf_custom, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.url_exists",
            lambda url, timeout=10: calls.append("url") or True,
        )
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_pipeline_schema",
            lambda url, version: calls.append("schema") or {},
        )
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.github_file_exists",
            lambda url, path, ref: calls.append("github") or True,
        )
        previous = wf_custom
        # Only an untracked field (description) changes — no check depends on it
        updated = wf_custom.model_copy(update={"description": "a new description"})
        diagnostics = run_dynamic_checks(updated, previous=previous)
        assert diagnostics == []
        assert calls == []

    def test_changed_params_only_triggers_schema_check(self, wf_custom, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.url_exists",
            lambda url, timeout=10: calls.append("url") or True,
        )
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_pipeline_schema",
            lambda url, version: calls.append("schema") or {},
        )
        previous = wf_custom
        updated = wf_custom.model_copy(update={"params": {"foo": "bar"}})
        run_dynamic_checks(updated, previous=previous)
        assert calls == ["schema"]


# ---------------------------------------------------------------------------
# check_all — batch/CLI-load path
# ---------------------------------------------------------------------------


class TestCheckAll:
    def test_empty_list_returns_empty(self):
        assert check_all([]) == []

    def test_aggregates_diagnostics_across_workflows(
        self, wf_custom, module_fastqc, monkeypatch
    ):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.url_exists", lambda url, timeout=10: False
        )
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [],
        )
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_pipeline_schema",
            lambda url, version: {},
        )
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_module_schema",
            lambda name, version: {},
        )
        diagnostics = check_all([wf_custom, module_fastqc])
        # wf_custom's url is unreachable -> one WARNING diagnostic expected
        assert any(
            d.workflow_id == wf_custom.id and d.severity == Severity.WARNING
            for d in diagnostics
        )
