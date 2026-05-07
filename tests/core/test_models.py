import pytest
import yaml
from pydantic import ValidationError
from pathlib import Path

from nf_meta.core.models import (
    Workflow, GlobalOptions, Transition, MetaworkflowConfig,
    load_config, dump_config, Position,
)


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
            Workflow(name="my-org/no-url-pipeline", version="1.0.0")

    def test_nfcore_url_mismatch_raises(self):
        with pytest.raises(ValidationError):
            Workflow(
                name="nf-core/rnaseq",
                version="3.14.0",
                url="https://github.com/wrong/url",
            )

    def test_id_auto_generated(self, wf_rnaseq):
        assert wf_rnaseq.id.startswith("n")
        assert len(wf_rnaseq.id) == 9  # "n" + 8 hex chars

    def test_default_position(self, wf_rnaseq):
        assert wf_rnaseq.position == Position(x=0, y=0)


class TestParamCoercion:
    def test_int_coerced_to_str(self):
        wf = Workflow(name="nf-core/rnaseq", version="3.14.0", params={"count": 42})
        assert wf.params["count"] == "42"

    def test_float_coerced_to_str(self):
        wf = Workflow(name="nf-core/rnaseq", version="3.14.0", params={"threshold": 0.5})
        assert wf.params["threshold"] == "0.5"

    def test_bool_coerced_to_str(self):
        wf = Workflow(name="nf-core/rnaseq", version="3.14.0", params={"flag": True})
        assert wf.params["flag"] == "True"

    def test_unsupported_type_raises(self):
        with pytest.raises(ValidationError):
            Workflow(name="nf-core/rnaseq", version="3.14.0", params={"bad": {"nested": "dict"}})


class TestFieldRefs:
    def test_field_refs_empty_without_params(self, wf_rnaseq):
        assert wf_rnaseq.field_refs == []

    def test_field_refs_parses_reference(self):
        wf = Workflow(
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
        wf = Workflow(name="nf-core/rnaseq", version="3.14.0", params={"input": "samples.csv"})
        assert wf.field_refs == []


class TestWorkflowHash:
    def test_hash_is_deterministic(self, wf_rnaseq):
        assert wf_rnaseq.hash() == wf_rnaseq.hash()

    def test_hash_differs_by_version(self):
        wf1 = Workflow(name="nf-core/rnaseq", version="3.14.0")
        wf2 = Workflow(name="nf-core/rnaseq", version="3.13.0")
        assert wf1.hash() != wf2.hash()


class TestWorkflowDump:
    def test_model_dump_config_has_correct_fields(self, wf_rnaseq):
        d = wf_rnaseq.model_dump_config()
        assert "id" in d
        assert "name" in d
        assert "version" in d
        assert "url" in d
        assert "position" not in d
        assert "description" not in d

    def test_model_dump_display_has_display_fields(self, wf_rnaseq):
        d = wf_rnaseq.model_dump_display()
        assert "description" in d
        assert "is_nfcore" in d
        assert "position" in d


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
        assert g.nextflow_version == (25, 10, 4, 0)

    def test_nextflow_version_partial(self):
        g = GlobalOptions(nextflow_version="25")
        assert g.nextflow_version == (25, 0, 0, 0)

    def test_nextflow_version_edge(self):
        g = GlobalOptions(nextflow_version="25.10.4-edge")
        assert g.nextflow_version == (25, 10, 4, 1)

    def test_nextflow_version_tuple_passthrough(self):
        g = GlobalOptions(nextflow_version=(25, 10, 4, 0))
        assert g.nextflow_version == (25, 10, 4, 0)

    def test_nextflow_version_none(self):
        g = GlobalOptions(nextflow_version=None)
        assert g.nextflow_version is None

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


# ---------------------------------------------------------------------------
# MetaworkflowConfig
# ---------------------------------------------------------------------------

class TestMetaworkflowConfig:
    def _make_config(self, workflows, transitions=None):
        return {
            "config_version": "0.0.1",
            "workflows": workflows,
            "transitions": transitions or [],
        }

    def test_list_format_workflows(self, wf_rnaseq):
        cfg = MetaworkflowConfig.model_validate(self._make_config(
            [{"id": wf_rnaseq.id, "name": wf_rnaseq.name, "version": wf_rnaseq.version, "url": wf_rnaseq.url}]
        ))
        assert len(cfg.workflows) == 1
        assert cfg.workflows[0].id == wf_rnaseq.id

    def test_dict_format_workflows(self, wf_rnaseq):
        cfg = MetaworkflowConfig.model_validate(self._make_config(
            {wf_rnaseq.id: {"name": wf_rnaseq.name, "version": wf_rnaseq.version, "url": wf_rnaseq.url}}
        ))
        assert len(cfg.workflows) == 1
        assert cfg.workflows[0].id == wf_rnaseq.id

    def test_transition_invalid_target_raises(self, wf_rnaseq):
        with pytest.raises(ValidationError):
            MetaworkflowConfig.model_validate(self._make_config(
                [{"id": wf_rnaseq.id, "name": wf_rnaseq.name, "version": wf_rnaseq.version, "url": wf_rnaseq.url}],
                transitions=[{"source": wf_rnaseq.id, "target": "nonexistent"}],
            ))

    def test_config_version_too_old_raises(self, wf_rnaseq):
        data = self._make_config(
            [{"id": wf_rnaseq.id, "name": wf_rnaseq.name, "version": wf_rnaseq.version, "url": wf_rnaseq.url}]
        )
        data["config_version"] = "0.0.0"
        with pytest.raises(ValidationError):
            MetaworkflowConfig.model_validate(data)

    def test_config_version_too_new_raises(self, wf_rnaseq):
        data = self._make_config(
            [{"id": wf_rnaseq.id, "name": wf_rnaseq.name, "version": wf_rnaseq.version, "url": wf_rnaseq.url}]
        )
        data["config_version"] = "9.9.9"
        with pytest.raises(ValidationError):
            MetaworkflowConfig.model_validate(data)

    def test_config_version_valid(self, wf_rnaseq):
        cfg = MetaworkflowConfig.model_validate(self._make_config(
            [{"id": wf_rnaseq.id, "name": wf_rnaseq.name, "version": wf_rnaseq.version, "url": wf_rnaseq.url}]
        ))
        assert cfg.config_version == "0.0.1"


# ---------------------------------------------------------------------------
# load_config / dump_config round-trip
# ---------------------------------------------------------------------------

class TestLoadDump:
    def test_load_config(self, minimal_yaml_path):
        cfg = load_config(minimal_yaml_path)
        assert len(cfg.workflows) == 2
        assert len(cfg.transitions) == 1

    def test_round_trip(self, tmp_path, config_yaml):
        cfg1 = load_config(config_yaml)
        out = tmp_path / "out.yaml"
        dump_config(cfg1, out)
        cfg2 = load_config(out)
        assert {w.id for w in cfg1.workflows} == {w.id for w in cfg2.workflows}
        assert len(cfg1.transitions) == len(cfg2.transitions)
