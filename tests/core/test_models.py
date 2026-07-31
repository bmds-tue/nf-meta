import pytest
from pydantic import ValidationError

from nf_meta.core.models import (
    NfPipeline,
    GlobalOptions,
    Transition,
)
from nf_meta.core.dynamic_validation import check_pipeline_main_script_exists
from nf_meta.core.errors import Severity


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


class TestWorkflowConstruction:
    def test_nfcore_url_auto_populated(self, wf_rnaseq):
        assert wf_rnaseq.url == "https://github.com/nf-core/rnaseq"

    def test_nfcore_description_auto_populated(self, wf_rnaseq):
        assert "RNA" in wf_rnaseq.description

    def test_is_nfcore_true(self, wf_rnaseq):
        assert wf_rnaseq.is_nfcore is True

    def test_is_nfcore_false(self, wf_custom):
        assert wf_custom.is_nfcore is False

    def test_custom_workflow_requires_url(self):
        with pytest.raises(ValidationError):
            NfPipeline(name="my-org/no-url-pipeline", version="1.0.0")

    def test_nfcore_url_mismatch_raises(self):
        with pytest.raises(ValidationError):
            NfPipeline(
                name="nf-core/rnaseq",
                version="3.14.0",
                url="https://github.com/wrong/url",
            )

    def test_id_auto_generated(self, wf_rnaseq):
        assert wf_rnaseq.id.startswith("n")
        assert len(wf_rnaseq.id) == 9  # "n" + 8 hex chars


class TestParamCoercion:
    def test_int_type_preserved(self):
        wf = NfPipeline(name="nf-core/rnaseq", version="3.14.0", params={"count": 42})
        assert wf.params["count"] == 42
        assert isinstance(wf.params["count"], int)

    def test_float_type_preserved(self):
        wf = NfPipeline(
            name="nf-core/rnaseq", version="3.14.0", params={"threshold": 0.5}
        )
        assert wf.params["threshold"] == 0.5
        assert isinstance(wf.params["threshold"], float)

    def test_bool_type_preserved(self):
        wf = NfPipeline(name="nf-core/rnaseq", version="3.14.0", params={"flag": True})
        assert wf.params["flag"] is True

    def test_str_type_preserved(self):
        wf = NfPipeline(
            name="nf-core/rnaseq", version="3.14.0", params={"input": "samples.csv"}
        )
        assert wf.params["input"] == "samples.csv"
        assert isinstance(wf.params["input"], str)

    def test_unsupported_type_raises(self):
        with pytest.raises(ValidationError):
            NfPipeline(
                name="nf-core/rnaseq",
                version="3.14.0",
                params={"bad": {"nested": "dict"}},
            )


class TestFieldRefs:
    def test_field_refs_empty_without_params(self, wf_rnaseq):
        assert wf_rnaseq.field_refs == []

    def test_field_refs_parses_reference(self):
        wf = NfPipeline(
            name="nf-core/rnaseq",
            version="3.14.0",
            params={"input": "${fetch:params:outdir}/samplesheet.csv"},
        )
        assert len(wf.field_refs) == 1
        ref = wf.field_refs[0]
        assert ref.target_wf_id == "fetch"
        assert ref.target_key == "outdir"
        assert ref.source_key == "input"

    def test_no_refs_without_brace_pattern(self):
        wf = NfPipeline(
            name="nf-core/rnaseq", version="3.14.0", params={"input": "samples.csv"}
        )
        assert wf.field_refs == []


class TestWorkflowHash:
    def test_hash_is_deterministic(self, wf_rnaseq):
        assert wf_rnaseq.hash() == wf_rnaseq.hash()

    def test_hash_differs_by_version(self):
        wf1 = NfPipeline(name="nf-core/rnaseq", version="3.14.0")
        wf2 = NfPipeline(name="nf-core/rnaseq", version="3.13.0")
        assert wf1.hash() != wf2.hash()

    def test_hash_differs_by_main_script(self):
        wf1 = NfPipeline(
            name="my-org/custom-pipeline",
            version="1.0.0",
            url="https://github.com/my-org/custom-pipeline",
        )
        wf2 = NfPipeline(
            name="my-org/custom-pipeline",
            version="1.0.0",
            url="https://github.com/my-org/custom-pipeline",
            main_script="workflows/special.nf",
        )
        assert wf1.hash() != wf2.hash()


class TestWorkflowMainScript:
    def test_main_script_raises_for_nfcore(self):
        with pytest.raises(ValidationError, match="nf-core"):
            NfPipeline(
                name="nf-core/rnaseq",
                version="3.14.0",
                main_script="workflows/special.nf",
            )

    def test_main_script_raises_when_file_not_found_on_github(self, monkeypatch):
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
        assert any(
            d.severity == Severity.ERROR and "not found" in d.message
            for d in diagnostics
        )

    def test_main_script_warns_for_non_github_url(self):
        wf = NfPipeline(
            name="my-org/custom-pipeline",
            version="1.0.0",
            url="https://gitlab.com/my-org/custom-pipeline",
            main_script="workflows/special.nf",
        )
        diagnostics = check_pipeline_main_script_exists(wf)
        assert any(
            d.severity == Severity.WARNING and "Cannot validate" in d.message
            for d in diagnostics
        )


class TestWorkflowDump:
    def test_model_dump_config_has_correct_fields(self, wf_rnaseq):
        d = wf_rnaseq.model_dump_config()
        assert "id" not in d
        assert "name" in d
        assert "version" in d
        assert "url" not in d
        assert "description" not in d

    def test_model_dump_config_includes_url_for_non_nfcore(self, wf_custom):
        d = wf_custom.model_dump_config()
        assert "url" in d
        assert "id" not in d

    def test_model_dump_display_has_display_fields(self, wf_rnaseq):
        d = wf_rnaseq.model_dump_display()
        assert "description" in d
        assert "is_nfcore" in d


# ---------------------------------------------------------------------------
# GlobalOptions
# ---------------------------------------------------------------------------


class TestGlobalOptions:
    def test_profile_whitespace_stripped(self):
        g = GlobalOptions(profile="docker, singularity")
        assert g.profile == "docker,singularity"

    def test_profile_none(self):
        g = GlobalOptions()
        assert g.profile is None

    def test_nextflow_version_full_string(self):
        g = GlobalOptions(nextflow_version="25.10.4")
        assert g.nextflow_version_tuple == (25, 10, 4, 0)

    def test_nextflow_version_partial(self):
        g = GlobalOptions(nextflow_version=25)
        assert g.nextflow_version_tuple == (25, 0, 0, 0)

    def test_nextflow_version_edge(self):
        g = GlobalOptions(nextflow_version="25.10.4-edge")
        assert g.nextflow_version_tuple == (25, 10, 4, 1)

    def test_nextflow_version_none(self):
        g = GlobalOptions(nextflow_version=None)
        assert g.nextflow_version_tuple is None

    def test_nextflow_version_invalid_raises(self):
        with pytest.raises(ValidationError):
            GlobalOptions(nextflow_version="not-a-version")

    def test_nextflow_version_too_many_parts_raises(self):
        with pytest.raises(ValidationError):
            GlobalOptions(nextflow_version="25.10.4.5")


# ---------------------------------------------------------------------------
# Transition
# ---------------------------------------------------------------------------


class TestTransition:
    def test_id_computed(self):
        tr = Transition(source="wf_a", target="wf_b")
        assert tr.id == "wf_a->wf_b"

    def test_model_dump_excludes_id(self):
        tr = Transition(source="wf_a", target="wf_b")
        d = tr.model_dump()
        assert "id" not in d
        assert d == {"source": "wf_a", "target": "wf_b"}


# Note: MetaworkflowConfig-level tests (list/dict format, transition validity,
# config_version bounds) and load_config/dump_config round-trip tests have been
# migrated to tests/core/test_graph.py's TestValidatedGraphFastPath, TestFileIO,
# and TestDynamicValidationOnLoad — MetaworkflowGraph's validated_graph/
# dump_config/from_file/to_file are now the construction/serialization entry
# points.
