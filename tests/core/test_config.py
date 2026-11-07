import pytest
import yaml

from nf_meta.core.config import (  # type: ignore[import]
    construct_workflow,
    dump_config,
    from_file,
    to_file,
    validated_globals,
    validated_graph,
    validated_workflow,
)
from nf_meta.core.errors import (  # type: ignore[import]
    ConfigValidationError,
    GraphValidationError,
    Severity,
    collect_positioned_diagnostics,
)
from nf_meta.core.graph import MetaworkflowGraph  # type: ignore[import]
from nf_meta.core.models import NfModule, WorkflowType  # type: ignore[import]

# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


class TestFileIO:
    def test_from_file(self, minimal_yaml_path):
        g = from_file(minimal_yaml_path)
        assert len(g.get_workflows()) == 2
        assert len(g.get_transitions()) == 1

    def test_to_file_round_trip(self, two_node_graph, tmp_path):
        out = tmp_path / "out.yaml"
        to_file(two_node_graph, out)
        g2 = from_file(out)
        ids1 = {w.id for w in two_node_graph.get_workflows()}
        ids2 = {w.id for w in g2.get_workflows()}
        assert ids1 == ids2


# ---------------------------------------------------------------------------
# validated_graph (default, fail-fast) / dump_config — construction and
# serialization (migrated from the retired MetaworkflowConfig/load_config/
# dump_config tests)
# ---------------------------------------------------------------------------


class TestValidatedGraphFastPath:
    def _make_config(self, workflows):
        return {"config_version": "0.3.0", "steps": workflows}

    def test_list_format_workflows_accepted_with_deprecation_warning(self, wf_rnaseq, caplog):
        g = validated_graph(
            self._make_config(
                [
                    {
                        "id": wf_rnaseq.id,
                        "name": wf_rnaseq.name,
                        "version": wf_rnaseq.version,
                        "url": wf_rnaseq.url,
                    }
                ]
            )
        )
        assert g.get_workflow_by_id(wf_rnaseq.id) is not None
        assert any("deprecated" in record.message for record in caplog.records)

    def test_dict_format_workflows(self, wf_rnaseq):
        g = validated_graph(
            self._make_config(
                {
                    wf_rnaseq.id: {
                        "name": wf_rnaseq.name,
                        "version": wf_rnaseq.version,
                        "url": wf_rnaseq.url,
                    }
                }
            )
        )
        assert len(g.get_workflows()) == 1
        assert g.get_workflow_by_id(wf_rnaseq.id) is not None

    def test_legacy_top_level_transitions_logs_deprecation_warning(self, wf_rnaseq, wf_fetchngs, caplog):
        data = self._make_config(
            {
                wf_fetchngs.id: {
                    "name": wf_fetchngs.name,
                    "version": wf_fetchngs.version,
                    "url": wf_fetchngs.url,
                },
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "url": wf_rnaseq.url,
                },
            }
        )
        data["transitions"] = [{"source": wf_fetchngs.id, "target": wf_rnaseq.id}]
        validated_graph(data)
        assert any("deprecated" in record.message for record in caplog.records)

    def test_legacy_top_level_transitions_accepted_alone(self, wf_rnaseq, wf_fetchngs):
        data = self._make_config(
            {
                wf_fetchngs.id: {
                    "name": wf_fetchngs.name,
                    "version": wf_fetchngs.version,
                    "url": wf_fetchngs.url,
                },
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "url": wf_rnaseq.url,
                },
            }
        )
        data["transitions"] = [{"source": wf_fetchngs.id, "target": wf_rnaseq.id}]
        g = validated_graph(data)
        assert g.get_transition(wf_fetchngs.id, wf_rnaseq.id) is not None

    def test_malformed_legacy_transition_entry_raises(self, wf_rnaseq):
        data = self._make_config(
            {
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "url": wf_rnaseq.url,
                }
            }
        )
        data["transitions"] = [{"source": wf_rnaseq.id}]  # missing 'target'
        with pytest.raises(GraphValidationError, match="transition"):
            validated_graph(data)

    def test_mixing_from_and_top_level_transitions_raises(self, wf_rnaseq, wf_fetchngs):
        data = self._make_config(
            {
                wf_fetchngs.id: {
                    "name": wf_fetchngs.name,
                    "version": wf_fetchngs.version,
                    "url": wf_fetchngs.url,
                },
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "url": wf_rnaseq.url,
                    "from": [wf_fetchngs.id],
                },
            }
        )
        data["transitions"] = [{"source": wf_fetchngs.id, "target": wf_rnaseq.id}]
        with pytest.raises(GraphValidationError, match="[Mm]ix"):
            validated_graph(data)

    def test_mixing_empty_from_and_top_level_transitions_raises(self, wf_rnaseq, wf_fetchngs):
        """Presence of the 'from' key alone (even empty) counts as mixing —
        not just a populated one."""
        data = self._make_config(
            {
                wf_fetchngs.id: {
                    "name": wf_fetchngs.name,
                    "version": wf_fetchngs.version,
                    "url": wf_fetchngs.url,
                },
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "url": wf_rnaseq.url,
                    "from": [],
                },
            }
        )
        data["transitions"] = [{"source": wf_fetchngs.id, "target": wf_rnaseq.id}]
        with pytest.raises(GraphValidationError, match="[Mm]ix"):
            validated_graph(data)

    def test_from_shorthand_creates_transition(self, wf_rnaseq, wf_fetchngs):
        g = validated_graph(
            self._make_config(
                {
                    wf_fetchngs.id: {
                        "name": wf_fetchngs.name,
                        "version": wf_fetchngs.version,
                        "url": wf_fetchngs.url,
                    },
                    wf_rnaseq.id: {
                        "name": wf_rnaseq.name,
                        "version": wf_rnaseq.version,
                        "url": wf_rnaseq.url,
                        "from": [wf_fetchngs.id],
                    },
                }
            )
        )
        assert g.get_transition(wf_fetchngs.id, wf_rnaseq.id) is not None

    def test_from_accepts_bare_string_as_single_predecessor(self, wf_rnaseq, wf_fetchngs):
        g = validated_graph(
            self._make_config(
                {
                    wf_fetchngs.id: {
                        "name": wf_fetchngs.name,
                        "version": wf_fetchngs.version,
                        "url": wf_fetchngs.url,
                    },
                    wf_rnaseq.id: {
                        "name": wf_rnaseq.name,
                        "version": wf_rnaseq.version,
                        "url": wf_rnaseq.url,
                        "from": wf_fetchngs.id,  # bare string, not a list
                    },
                }
            )
        )
        assert g.get_transition(wf_fetchngs.id, wf_rnaseq.id) is not None

    def test_from_referencing_unknown_workflow_raises(self, wf_rnaseq):
        data = self._make_config(
            {
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "url": wf_rnaseq.url,
                    "from": ["nonexistent"],
                }
            }
        )
        with pytest.raises(GraphValidationError):
            validated_graph(data)

    def test_malformed_from_value_raises(self, wf_rnaseq):
        data = self._make_config(
            {
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "url": wf_rnaseq.url,
                    "from": 123,  # neither a string nor a list
                }
            }
        )
        with pytest.raises(GraphValidationError, match="'from'"):
            validated_graph(data)

    def test_from_list_with_non_string_entry_raises(self, wf_rnaseq):
        data = self._make_config(
            {
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "url": wf_rnaseq.url,
                    "from": [123],
                }
            }
        )
        with pytest.raises(GraphValidationError, match="'from'"):
            validated_graph(data)

    def test_config_version_too_old_raises(self, wf_rnaseq):
        data = self._make_config(
            {
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "url": wf_rnaseq.url,
                }
            }
        )
        data["config_version"] = "0.0.0"
        with pytest.raises(GraphValidationError):
            validated_graph(data)

    def test_config_version_too_new_raises(self, wf_rnaseq):
        data = self._make_config(
            {
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "url": wf_rnaseq.url,
                }
            }
        )
        data["config_version"] = "9.9.9"
        with pytest.raises(GraphValidationError):
            validated_graph(data)

    def test_config_version_valid(self, wf_rnaseq):
        g = validated_graph(
            self._make_config(
                {
                    wf_rnaseq.id: {
                        "name": wf_rnaseq.name,
                        "version": wf_rnaseq.version,
                        "url": wf_rnaseq.url,
                    }
                }
            )
        )
        assert g.config_version == "0.3.0"

    def test_malformed_workflow_item_raises(self):
        with pytest.raises(GraphValidationError, match="key-value mapping"):
            validated_graph(self._make_config({"wf_a": "not-a-mapping"}))

    def test_bad_workflow_field_raises_config_validation_error_with_real_id(self):
        data = self._make_config({"wf_a": {"version": "2.0.0"}})  # missing name/url
        with pytest.raises(ConfigValidationError) as excinfo:
            validated_graph(data)
        assert any(d.workflow_id == "wf_a" for d in excinfo.value.errors)

    def test_round_trip_via_dump_config(self, tmp_path, wf_rnaseq, wf_fetchngs):
        data = self._make_config(
            {
                wf_fetchngs.id: {
                    "name": wf_fetchngs.name,
                    "version": wf_fetchngs.version,
                },
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "from": [wf_fetchngs.id],
                },
            }
        )
        g1 = validated_graph(data)
        dumped = dump_config(g1)
        assert "transitions" not in dumped
        assert dumped["steps"][wf_rnaseq.id]["from"] == [wf_fetchngs.id]
        g2 = validated_graph(dumped)
        assert {w.id for w in g1.get_workflows()} == {w.id for w in g2.get_workflows()}
        assert len(g1.get_transitions()) == len(g2.get_transitions())


# ---------------------------------------------------------------------------
# construct_workflow / validated_graph(collect_errors=True) -- collect-
# everything construction used only by the CLI's `validate` command;
# validated_graph's default (collect_errors=False, fail-fast) is covered above
# and unaffected.
# ---------------------------------------------------------------------------


class TestConstructWorkflow:
    def test_success_returns_workflow_and_no_diagnostics(self, wf_rnaseq):
        item = {
            "type": WorkflowType.NF_PIPELINE,
            "name": wf_rnaseq.name,
            "version": wf_rnaseq.version,
        }
        wf, diagnostics = construct_workflow(item, "wf_a")
        assert wf is not None
        assert wf.name == wf_rnaseq.name
        assert diagnostics == []

    def test_failure_returns_none_and_diagnostics(self):
        item = {"type": WorkflowType.NF_PIPELINE, "version": "1.0.0"}  # missing name
        wf, diagnostics = construct_workflow(item, "wf_a")
        assert wf is None
        assert len(diagnostics) >= 1
        assert all(d.workflow_id == "wf_a" for d in diagnostics)
        assert any(d.field == "name" for d in diagnostics)

    def test_module_type_dispatches_to_nfmodule(self, module_fastqc):
        item = {
            "type": WorkflowType.NF_MODULE,
            "name": module_fastqc.name,
            "version": module_fastqc.version,
        }
        wf, diagnostics = construct_workflow(item, "wf_a")
        assert wf is not None
        assert wf.type == WorkflowType.NF_MODULE
        assert diagnostics == []


class TestValidatedWorkflow:
    def test_valid_snippet_returns_workflow(self, wf_rnaseq):
        data = {
            "name": wf_rnaseq.name,
            "version": wf_rnaseq.version,
            "params": {"input": "samplesheet.csv", "outdir": "results"},
        }
        wf = validated_workflow(data)
        assert wf.name == wf_rnaseq.name

    def test_id_optional_auto_generated(self, wf_rnaseq):
        data = {"name": wf_rnaseq.name, "version": wf_rnaseq.version}
        wf = validated_workflow(data)
        assert wf.id  # auto-generated, non-empty

    def test_explicit_id_preserved(self, wf_rnaseq):
        data = {"id": "my_custom_id", "name": wf_rnaseq.name, "version": wf_rnaseq.version}
        wf = validated_workflow(data)
        assert wf.id == "my_custom_id"

    def test_construction_failure_raises_config_validation_error(self):
        with pytest.raises(ConfigValidationError):
            validated_workflow({"version": "1.0.0"})  # missing name

    def test_tier2_failure_raises_config_validation_error(self, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [{"version": "9.9.9-ffffff9"}],
        )
        with pytest.raises(ConfigValidationError):
            validated_workflow(
                {
                    "type": WorkflowType.NF_MODULE,
                    "name": "nf-core/fastqc",
                    "version": "0.0.0-6c4ed3a",
                }
            )

    def test_empty_data_raises(self):
        with pytest.raises(GraphValidationError):
            validated_workflow({})

    def test_non_mapping_data_raises(self):
        with pytest.raises(GraphValidationError):
            validated_workflow("not-a-mapping")  # type: ignore[arg-type]


class TestValidatedGlobals:
    def test_valid_snippet_returns_globals(self):
        globals_ = validated_globals({"profile": "docker"})
        assert globals_.nf_profile == "docker"

    def test_invalid_snippet_raises_config_validation_error(self):
        with pytest.raises(ConfigValidationError):
            validated_globals({"config_file": "/nonexistent/path.config"})

    def test_empty_data_raises(self):
        with pytest.raises(GraphValidationError):
            validated_globals({})

    def test_non_mapping_data_raises(self):
        with pytest.raises(GraphValidationError):
            validated_globals("not-a-mapping")  # type: ignore[arg-type]


class TestValidatedGraphCollectErrors:
    def _make_config(self, workflows):
        return {"config_version": "0.3.0", "steps": workflows}

    def test_valid_config_returns_graph(self, wf_rnaseq, wf_fetchngs):
        data = self._make_config(
            {
                wf_fetchngs.id: {
                    "name": wf_fetchngs.name,
                    "version": wf_fetchngs.version,
                },
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "from": wf_fetchngs.id,
                },
            }
        )
        g = validated_graph(data, collect_errors=True)
        assert isinstance(g, MetaworkflowGraph)
        assert len(g.get_workflows()) == 2
        assert len(g.get_transitions()) == 1

    def test_multiple_broken_workflows_reported_together(self):
        data = self._make_config(
            {
                "wf_a": {"version": "1.0.0"},  # missing name
                "wf_b": {"name": "also broken"},  # missing version
            }
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validated_graph(data, collect_errors=True)
        workflow_ids = {d.workflow_id for d in exc_info.value.errors}
        assert workflow_ids == {"wf_a", "wf_b"}

    def test_cycle_and_bad_reference_and_dangling_edge_reported_together(self, wf_rnaseq, wf_fetchngs):
        data = self._make_config(
            {
                wf_fetchngs.id: {
                    "name": wf_fetchngs.name,
                    "version": wf_fetchngs.version,
                    "from": wf_rnaseq.id,  # + wf_rnaseq's own "from" below -> cycle
                },
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "from": [wf_fetchngs.id, "totally_unknown"],
                    "params": {
                        "input": "${nonexistent_wf:params:outdir}",
                    },
                },
            }
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validated_graph(data, collect_errors=True)
        exc = exc_info.value
        assert any("cycle" in m for m in exc.graph_messages)
        assert any("totally_unknown" in m for m in exc.graph_messages)
        assert any("nonexistent_wf" in d.message for d in exc.errors)

    def test_from_referencing_failed_construction_skipped_silently(self, wf_fetchngs):
        """A `from:` id that was declared but failed to construct is not
        re-reported as a dangling edge -- that would just be a confusing
        secondary symptom of the already-reported construction diagnostic."""
        data = self._make_config(
            {
                "broken": {"version": "1.0.0"},  # missing name -> fails construction
                wf_fetchngs.id: {
                    "name": wf_fetchngs.name,
                    "version": wf_fetchngs.version,
                    "from": "broken",
                },
            }
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validated_graph(data, collect_errors=True)
        exc = exc_info.value
        assert exc.graph_messages == []
        assert len(exc.errors) >= 1
        assert all(d.workflow_id == "broken" for d in exc.errors)

    def test_shape_level_error_still_raises_immediately(self, wf_rnaseq, wf_fetchngs):
        data = self._make_config(
            {
                wf_fetchngs.id: {
                    "name": wf_fetchngs.name,
                    "version": wf_fetchngs.version,
                },
                wf_rnaseq.id: {
                    "name": wf_rnaseq.name,
                    "version": wf_rnaseq.version,
                    "from": [wf_fetchngs.id],
                },
            }
        )
        data["transitions"] = [{"source": wf_fetchngs.id, "target": wf_rnaseq.id}]
        with pytest.raises(GraphValidationError, match="[Mm]ix"):
            validated_graph(data, collect_errors=True)


# ---------------------------------------------------------------------------
# Dynamic validation on load (validated_graph)
# ---------------------------------------------------------------------------


class TestDynamicValidationOnLoad:
    def test_validated_graph_raises_dynamic_validation_error(self, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [{"version": "1.0.0-abcdefa"}],
        )
        module = NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")
        data = {
            "config_version": "0.3.0",
            "steps": {
                module.id: {
                    "type": "nf-module",
                    "name": module.name,
                    "version": module.version,
                }
            },
        }
        with pytest.raises(ConfigValidationError) as excinfo:
            validated_graph(data)

        assert any(d.workflow_id == module.id and "not available" in d.message for d in excinfo.value.errors)

    def test_validated_graph_succeeds_when_dynamic_checks_pass(self, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [{"version": "0.0.0-6c4ed3a"}],
        )
        module = NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")
        data = {
            "config_version": "0.3.0",
            "steps": {
                module.id: {
                    "type": "nf-module",
                    "name": module.name,
                    "version": module.version,
                }
            },
        }
        g = validated_graph(data)
        assert g.get_workflow_by_id(module.id) is not None


# ---------------------------------------------------------------------------
# nf-module steps need Nextflow >= 26.04
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("collect_errors", [False, True])
def test_module_with_old_nextflow_version_rejected(collect_errors):
    data = {
        "config_version": "0.3.0",
        "globals": {"nextflow_version": "25.10"},
        "steps": {"m1": {"type": "nf-module", "name": "nf-core/fastqc", "version": "0.0.0-6c4ed3a"}},
    }
    with pytest.raises(ConfigValidationError) as exc:
        validated_graph(data, collect_errors=collect_errors)
    assert any(d.yaml_path == "globals.nextflow_version" for d in exc.value.errors)


# ---------------------------------------------------------------------------
# Unknown keys, malformed references, collected warnings
# ---------------------------------------------------------------------------


def _config(**extra):
    data = {
        "config_version": "0.4.0",
        "steps": {
            "n01": {"name": "nf-core/fetchngs", "version": "1.12.0", "params": {"input": "ids.csv", "outdir": "o"}},
        },
    }
    data.update(extra)
    return data


@pytest.mark.parametrize("collect_errors", [False, True])
def test_unknown_top_level_key_rejected_with_suggestion(collect_errors):
    with pytest.raises(ConfigValidationError) as exc:
        validated_graph(_config(input={}), collect_errors=collect_errors)
    assert [d.yaml_path for d in exc.value.errors] == ["input"]
    assert "Did you mean 'inputs'?" in exc.value.errors[0].message


@pytest.mark.parametrize("collect_errors", [False, True])
def test_unknown_keys_in_globals_and_workflows_rejected(collect_errors):
    data = _config(globals={"profle": "docker"})
    data["steps"]["n01"]["parms"] = {}
    with pytest.raises(ConfigValidationError) as exc:
        validated_graph(data, collect_errors=collect_errors)
    paths = {d.yaml_path for d in exc.value.errors}
    assert "globals.profle" in paths or "steps.n01.parms" in paths
    if collect_errors:
        assert paths == {"globals.profle", "steps.n01.parms"}


@pytest.mark.parametrize("collect_errors", [False, True])
def test_malformed_reference_is_an_error(collect_errors):
    data = _config()
    data["steps"]["n01"]["params"]["input"] = "${input:ids}"
    with pytest.raises(ConfigValidationError) as exc:
        validated_graph(data, collect_errors=collect_errors)
    assert exc.value.errors[0].yaml_path == "steps.n01.params.input"
    assert "Did you mean '${inputs:ids}'?" in exc.value.errors[0].message


def test_collect_errors_returns_warnings_on_the_graph():
    data = _config(inputs={"spare": {"type": "string"}})
    g = validated_graph(data, collect_errors=True)
    assert [(d.severity, d.yaml_path) for d in g.warnings] == [(Severity.WARNING, "inputs.spare")]


def test_legacy_transitions_reported_as_warning():
    data = _config()
    data["steps"]["n02"] = {
        "name": "nf-core/rnaseq",
        "version": "3.14.0",
        "params": {"input": "s.csv", "outdir": "o2"},
    }
    data["transitions"] = [{"source": "n01", "target": "n02"}]
    g = validated_graph(data, collect_errors=True)
    assert [d.yaml_path for d in g.warnings] == ["transitions"]


def test_errors_carry_warnings_too():
    data = _config(inputs={"spare": {"type": "string"}}, input={})
    with pytest.raises(ConfigValidationError) as exc:
        validated_graph(data, collect_errors=True)
    assert [d.yaml_path for d in exc.value.warnings] == ["inputs.spare"]


# ---------------------------------------------------------------------------
# nf_config / nf_profile (renamed from config_file / profile)
# ---------------------------------------------------------------------------


def _with_nf_keys(tmp_path, globals_, step):
    cfg = tmp_path / "any_name.txt"  # no .config suffix required
    cfg.write_text("")
    data = _config(globals={k: (str(cfg) if v == "CFG" else v) for k, v in globals_.items()})
    data["steps"]["n01"].update({k: (str(cfg) if v == "CFG" else v) for k, v in step.items()})
    return data, cfg


def test_new_keys_load_and_dump(tmp_path):
    data, cfg = _with_nf_keys(tmp_path, {"nf_config": "CFG", "nf_profile": "docker"}, {"nf_profile": "test"})
    g = validated_graph(data, collect_errors=True)
    assert g.global_options.nf_config == str(cfg) and g.global_options.nf_profile == "docker"
    assert g.warnings == []
    dumped = dump_config(g)
    assert dumped["globals"] == {"nf_profile": "docker", "nf_config": str(cfg)}
    assert dumped["steps"]["n01"]["nf_profile"] == "test"


def test_legacy_keys_still_load_with_a_warning_and_save_as_new(tmp_path):
    data, cfg = _with_nf_keys(tmp_path, {"config_file": "CFG", "profile": "docker"}, {"profile": "test"})
    g = validated_graph(data, collect_errors=True)
    assert g.global_options.nf_config == str(cfg) and g.global_options.nf_profile == "docker"
    assert sorted(d.yaml_path for d in g.warnings) == [
        "globals.config_file",
        "globals.profile",
        "steps.n01.profile",
    ]
    assert all("Deprecated key, use 'nf_" in d.message for d in g.warnings)
    dumped = dump_config(g)
    assert "config_file" not in dumped["globals"] and "profile" not in dumped["steps"]["n01"]


def test_missing_nf_config_is_an_error(tmp_path):
    data = _config(globals={"nf_config": str(tmp_path / "missing.config")})
    with pytest.raises(ConfigValidationError) as exc:
        validated_graph(data, collect_errors=True)
    assert [d.yaml_path for d in exc.value.errors] == ["globals.nf_config"]


@pytest.mark.parametrize(("version", "warned"), [("0ae5518", True), ("0ae5518" + "0" * 33, False), ("1.12.0", False)])
def test_abbreviated_commit_hash_warns(version, warned):
    data = _config()
    data["steps"]["n01"]["version"] = version
    g = validated_graph(data, collect_errors=True)
    assert [d.yaml_path for d in g.warnings] == (["steps.n01.version"] if warned else [])


# ---------------------------------------------------------------------------
# `steps:` and its old name `workflows:`
# ---------------------------------------------------------------------------


def _legacy(data: dict) -> dict:
    return {("workflows" if key == "steps" else key): value for key, value in data.items()}


@pytest.mark.parametrize("collect_errors", [False, True])
def test_workflows_key_still_loads(collect_errors):
    g = validated_graph(_legacy(_config()), collect_errors=collect_errors)
    assert [wf.id for wf in g.get_workflows()] == ["n01"]


def test_workflows_key_warns():
    g = validated_graph(_legacy(_config()), collect_errors=True)
    assert [(d.yaml_path, d.message) for d in g.warnings] == [
        ("workflows", "Deprecated in favor of 'steps:'. Saving from the editor updates it.")
    ]


@pytest.mark.parametrize("collect_errors", [False, True])
def test_steps_and_workflows_together_rejected(collect_errors):
    data = {**_config(), "workflows": {}}
    with pytest.raises(GraphValidationError, match="not both"):
        validated_graph(data, collect_errors=collect_errors)


def test_dump_writes_steps_and_a_version_allowing_it():
    dumped = dump_config(validated_graph(_legacy(_config()), collect_errors=True))
    assert "workflows" not in dumped
    assert list(dumped["steps"]) == ["n01"]
    assert dumped["config_version"] == "0.5.0"


def test_legacy_config_keeps_its_line_numbers():
    text = "config_version: 0.4.0\nworkflows:\n  n01:\n    name: nf-core/fetchngs\n    version: 1.12.0\n    bogus: 1\n"
    with pytest.raises(ConfigValidationError) as exc:
        validated_graph(yaml.safe_load(text), collect_errors=True)
    positioned, _ = collect_positioned_diagnostics(exc.value, text)
    bogus = next(p for p in positioned if p.diagnostic.yaml_path == "steps.n01.bogus")
    assert (bogus.position.line, bogus.position.column) == (6, 5)


class TestStepIds:
    def test_the_mapping_key_wins_over_an_explicit_id(self):
        g = validated_graph(
            {
                "config_version": "0.5.0",
                "steps": {"n01": {"id": "other", "name": "nf-core/rnaseq", "version": "3.14.0"}},
            }
        )
        assert [wf.id for wf in g.get_workflows()] == ["n01"]

    def test_a_repeated_id_in_list_form_is_an_error(self):
        step = {"id": "n01", "name": "nf-core/rnaseq", "version": "3.14.0"}
        with pytest.raises(GraphValidationError, match="more than once"):
            validated_graph({"config_version": "0.5.0", "steps": [step, dict(step)]})


def test_the_collecting_loader_checks_implicit_inputs():
    data = {
        "config_version": "0.5.0",
        "steps": {"n01": {"name": "nf-core/rnaseq", "version": "3.14.0", "params": {"count": "${inputs:x}"}}},
    }
    data["steps"]["n02"] = {"name": "nf-core/rnaseq", "version": "3.14.0", "params": {"flag": "${inputs:x}"}}
    with pytest.raises(ConfigValidationError) as fast:
        validated_graph(data)
    with pytest.raises(ConfigValidationError) as collected:
        validated_graph(data, collect_errors=True)
    assert {d.yaml_path for d in collected.value.errors} == {d.yaml_path for d in fast.value.errors}
