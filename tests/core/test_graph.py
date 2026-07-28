import pytest

from nf_meta.core.models import (  # type: ignore[import]
    NfModule,
    NfPipeline,
    BaseWorkflow,
    Transition,
)
from nf_meta.core.graph import (  # type: ignore[import]
    MetaworkflowGraph,
    dump_config,
    from_file,
    from_raw_dict,
    to_file,
)
from nf_meta.core.events import (  # type: ignore[import]
    WorkflowAdded,
    WorkflowRemoved,
    WorkflowUpdated,
    TransitionAdded,
    TransitionRemoved,
)
from nf_meta.core.errors import (  # type: ignore[import]
    ConfigValidationError,
    GraphValidationError,
    WorkflowReferenceErrors,
)


# ---------------------------------------------------------------------------
# add / update / remove workflow
# ---------------------------------------------------------------------------


class TestWorkflowMutations:
    def test_add_workflow_appears_in_graph(self, empty_graph, wf_rnaseq):
        empty_graph.add_workflow(wf_rnaseq)
        assert empty_graph.get_workflow_by_id(wf_rnaseq.id) is not None

    def test_add_workflow_emits_event(self, empty_graph, wf_rnaseq):
        empty_graph.add_workflow(wf_rnaseq)
        events = empty_graph.pop_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowAdded)
        assert events[0].workflow.id == wf_rnaseq.id

    def test_add_workflow_with_invalid_ref_raises_and_rolls_back(self, empty_graph):
        wf = NfPipeline(
            name="nf-core/rnaseq",
            version="3.14.0",
            params={"input": "${nonexistent:params:outdir}/file.csv"},
        )
        with pytest.raises(WorkflowReferenceErrors):
            empty_graph.add_workflow(wf)
        assert empty_graph.get_workflow_by_id(wf.id) is None

    def test_update_workflow(self, empty_graph, wf_rnaseq):
        empty_graph.add_workflow(wf_rnaseq)
        empty_graph.pop_events()
        updated = wf_rnaseq.model_copy(update={"version": "3.13.0"})
        empty_graph.update_workflow(updated)
        assert empty_graph.get_workflow_by_id(wf_rnaseq.id).version == "3.13.0"

    def test_update_workflow_emits_event(self, empty_graph, wf_rnaseq):
        empty_graph.add_workflow(wf_rnaseq)
        empty_graph.pop_events()
        updated = wf_rnaseq.model_copy(update={"version": "3.13.0"})
        empty_graph.update_workflow(updated)
        events = empty_graph.pop_events()
        assert isinstance(events[0], WorkflowUpdated)
        assert events[0].old_workflow.version == "3.14.0"
        assert events[0].new_workflow.version == "3.13.0"

    def test_update_workflow_invalid_id_raises(self, empty_graph, wf_rnaseq):
        with pytest.raises(ValueError):
            empty_graph.update_workflow(wf_rnaseq)

    def test_remove_workflow(self, empty_graph, wf_rnaseq):
        empty_graph.add_workflow(wf_rnaseq)
        empty_graph.pop_events()
        empty_graph.remove_workflow(wf_rnaseq.id)
        assert empty_graph.get_workflow_by_id(wf_rnaseq.id) is None

    def test_remove_workflow_emits_event(self, empty_graph, wf_rnaseq):
        empty_graph.add_workflow(wf_rnaseq)
        empty_graph.pop_events()
        empty_graph.remove_workflow(wf_rnaseq.id)
        events = empty_graph.pop_events()
        assert isinstance(events[0], WorkflowRemoved)

    def test_remove_workflow_also_removes_edges(
        self, two_node_graph, wf_rnaseq, wf_fetchngs
    ):
        two_node_graph.remove_workflow(wf_rnaseq.id)
        assert two_node_graph.get_transition(wf_rnaseq.id, wf_fetchngs.id) is None

    def test_remove_workflow_invalid_id_raises(self, empty_graph):
        with pytest.raises(ValueError):
            empty_graph.remove_workflow("not-a-real-id")


# ---------------------------------------------------------------------------
# add / remove transition
# ---------------------------------------------------------------------------


class TestTransitionMutations:
    def test_add_transition_creates_edge(self, empty_graph, wf_rnaseq, wf_fetchngs):
        empty_graph.add_workflow(wf_rnaseq)
        empty_graph.add_workflow(wf_fetchngs)
        empty_graph.pop_events()
        tr = Transition(source=wf_rnaseq.id, target=wf_fetchngs.id)
        empty_graph.add_transition(tr)
        assert empty_graph.get_transition(wf_rnaseq.id, wf_fetchngs.id) is not None

    def test_add_transition_emits_event(self, empty_graph, wf_rnaseq, wf_fetchngs):
        empty_graph.add_workflow(wf_rnaseq)
        empty_graph.add_workflow(wf_fetchngs)
        empty_graph.pop_events()
        empty_graph.add_transition(
            Transition(source=wf_rnaseq.id, target=wf_fetchngs.id)
        )
        events = empty_graph.pop_events()
        assert isinstance(events[0], TransitionAdded)

    def test_add_transition_unknown_source_raises(self, empty_graph, wf_fetchngs):
        empty_graph.add_workflow(wf_fetchngs)
        with pytest.raises(GraphValidationError):
            empty_graph.add_transition(
                Transition(source="ghost", target=wf_fetchngs.id)
            )

    def test_add_transition_unknown_target_raises(self, empty_graph, wf_rnaseq):
        empty_graph.add_workflow(wf_rnaseq)
        with pytest.raises(GraphValidationError):
            empty_graph.add_transition(Transition(source=wf_rnaseq.id, target="ghost"))

    def test_add_transition_cycle_raises(self, empty_graph, wf_rnaseq, wf_fetchngs):
        empty_graph.add_workflow(wf_rnaseq)
        empty_graph.add_workflow(wf_fetchngs)
        empty_graph.add_transition(
            Transition(source=wf_rnaseq.id, target=wf_fetchngs.id)
        )
        with pytest.raises(GraphValidationError):
            empty_graph.add_transition(
                Transition(source=wf_fetchngs.id, target=wf_rnaseq.id)
            )

    def test_remove_transition(self, two_node_graph, wf_rnaseq, wf_fetchngs):
        two_node_graph.remove_transition(wf_fetchngs.id, wf_rnaseq.id)
        assert two_node_graph.get_transition(wf_fetchngs.id, wf_rnaseq.id) is None

    def test_remove_transition_nonexistent_is_noop(self, empty_graph):
        empty_graph.remove_transition("a", "b")  # should not raise

    def test_remove_transition_emits_event(
        self, two_node_graph, wf_rnaseq, wf_fetchngs
    ):
        two_node_graph.remove_transition(wf_fetchngs.id, wf_rnaseq.id)
        events = two_node_graph.pop_events()
        assert isinstance(events[0], TransitionRemoved)


# ---------------------------------------------------------------------------
# Param reference validation
# ---------------------------------------------------------------------------


class TestParamReferenceValidation:
    def test_valid_ref_accepted(self, empty_graph, wf_fetchngs):
        empty_graph.add_workflow(wf_fetchngs)
        # Add a workflow that references wf_fetchngs via a transition
        wf_fetchngs_with_params = wf_fetchngs.model_copy(
            update={"params": {"outdir": "results"}}
        )
        empty_graph.update_workflow(wf_fetchngs_with_params)

        wf_rnaseq = NfPipeline(
            name="nf-core/rnaseq",
            version="3.14.0",
            params={"input": f"${{{wf_fetchngs.id}:params:outdir}}/samplesheet.csv"},
        )
        with empty_graph.deferred_validation():
            empty_graph.add_workflow(wf_rnaseq)
            empty_graph.add_transition(
                Transition(source=wf_fetchngs.id, target=wf_rnaseq.id)
            )

    def test_ref_to_unknown_workflow_raises(self, empty_graph):
        wf = NfPipeline(
            name="nf-core/rnaseq",
            version="3.14.0",
            params={"input": "${ghost:params:outdir}/file.csv"},
        )
        with pytest.raises(WorkflowReferenceErrors):
            empty_graph.add_workflow(wf)

    def test_ref_to_non_predecessor_raises(self, empty_graph, wf_rnaseq, wf_fetchngs):
        # Both workflows exist but no transition connecting them
        empty_graph.add_workflow(wf_fetchngs)
        fetchngs_with_params = wf_fetchngs.model_copy(
            update={"params": {"outdir": "results"}}
        )
        empty_graph.update_workflow(fetchngs_with_params)

        rnaseq_with_ref = NfPipeline(
            name="nf-core/rnaseq",
            version="3.14.0",
            params={"input": f"${{{wf_fetchngs.id}:params:outdir}}/file.csv"},
        )
        with pytest.raises(WorkflowReferenceErrors):
            empty_graph.add_workflow(rnaseq_with_ref)


# ---------------------------------------------------------------------------
# Deferred validation
# ---------------------------------------------------------------------------


class TestDeferredValidation:
    def test_deferred_allows_adding_ref_before_transition(
        self, empty_graph, wf_fetchngs
    ):
        fetchngs_with_params = wf_fetchngs.model_copy(
            update={"params": {"outdir": "results"}}
        )

        wf_rnaseq = NfPipeline(
            name="nf-core/rnaseq",
            version="3.14.0",
            params={"input": f"${{{wf_fetchngs.id}:params:outdir}}/file.csv"},
        )

        with empty_graph.deferred_validation():
            empty_graph.add_workflow(fetchngs_with_params)
            empty_graph.add_workflow(wf_rnaseq)
            empty_graph.add_transition(
                Transition(source=wf_fetchngs.id, target=wf_rnaseq.id)
            )

        assert empty_graph.get_workflow_by_id(wf_rnaseq.id) is not None

    def test_deferred_still_validates_on_exit(
        self, empty_graph, wf_rnaseq, wf_fetchngs
    ):
        with pytest.raises(GraphValidationError):
            with empty_graph.deferred_validation():
                empty_graph.add_workflow(wf_rnaseq)
                empty_graph.add_workflow(wf_fetchngs)
                empty_graph.add_transition(
                    Transition(source=wf_rnaseq.id, target=wf_fetchngs.id)
                )
                empty_graph.add_transition(
                    Transition(source=wf_fetchngs.id, target=wf_rnaseq.id)
                )


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
# from_raw_dict / dump_config — construction and serialization
# (migrated from the retired MetaworkflowConfig/load_config/dump_config tests)
# ---------------------------------------------------------------------------


class TestFromRawDict:
    def _make_config(self, workflows):
        return {"config_version": "0.3.0", "workflows": workflows}

    def test_list_format_workflows_rejected(self, wf_rnaseq):
        with pytest.raises(GraphValidationError, match="list-format"):
            from_raw_dict(
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

    def test_dict_format_workflows(self, wf_rnaseq):
        g = from_raw_dict(
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
        g = from_raw_dict(data)
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
            from_raw_dict(data)

    def test_mixing_from_and_top_level_transitions_raises(
        self, wf_rnaseq, wf_fetchngs
    ):
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
            from_raw_dict(data)

    def test_mixing_empty_from_and_top_level_transitions_raises(
        self, wf_rnaseq, wf_fetchngs
    ):
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
            from_raw_dict(data)

    def test_from_shorthand_creates_transition(self, wf_rnaseq, wf_fetchngs):
        g = from_raw_dict(
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

    def test_from_accepts_bare_string_as_single_predecessor(
        self, wf_rnaseq, wf_fetchngs
    ):
        g = from_raw_dict(
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
            from_raw_dict(data)

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
            from_raw_dict(data)

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
            from_raw_dict(data)

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
            from_raw_dict(data)

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
            from_raw_dict(data)

    def test_config_version_valid(self, wf_rnaseq):
        g = from_raw_dict(
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
            from_raw_dict(self._make_config({"wf_a": "not-a-mapping"}))

    def test_bad_workflow_field_raises_config_validation_error_with_real_id(self):
        data = self._make_config({"wf_a": {"version": "2.0.0"}})  # missing name/url
        with pytest.raises(ConfigValidationError) as excinfo:
            from_raw_dict(data)
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
        g1 = from_raw_dict(data)
        dumped = dump_config(g1)
        assert "transitions" not in dumped
        assert dumped["workflows"][wf_rnaseq.id]["from"] == [wf_fetchngs.id]
        g2 = from_raw_dict(dumped)
        assert {w.id for w in g1.get_workflows()} == {w.id for w in g2.get_workflows()}
        assert len(g1.get_transitions()) == len(g2.get_transitions())


# ---------------------------------------------------------------------------
# Dynamic validation on load (from_raw_dict)
# ---------------------------------------------------------------------------


class TestDynamicValidationOnLoad:
    def test_from_raw_dict_raises_dynamic_validation_error(self, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [{"version": "1.0.0-abcdefa"}],
        )
        module = NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")
        data = {
            "config_version": "0.3.0",
            "workflows": {
                module.id: {
                    "type": "nf-module",
                    "name": module.name,
                    "version": module.version,
                }
            },
        }
        with pytest.raises(ConfigValidationError) as excinfo:
            from_raw_dict(data)

        assert any(
            d.workflow_id == module.id and "not available" in d.message
            for d in excinfo.value.errors
        )

    def test_from_raw_dict_succeeds_when_dynamic_checks_pass(self, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [{"version": "0.0.0-6c4ed3a"}],
        )
        module = NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")
        data = {
            "config_version": "0.3.0",
            "workflows": {
                module.id: {
                    "type": "nf-module",
                    "name": module.name,
                    "version": module.version,
                }
            },
        }
        g = from_raw_dict(data)
        assert g.get_workflow_by_id(module.id) is not None


# ---------------------------------------------------------------------------
# Dynamic validation on direct mutation (add_workflow / update_workflow)
# ---------------------------------------------------------------------------


class TestDynamicValidationOnMutation:
    def test_add_workflow_raises_dynamic_validation_error(
        self, empty_graph, monkeypatch
    ):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [{"version": "1.0.0-abcdefa"}],
        )
        wf = NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")
        with pytest.raises(ConfigValidationError):
            empty_graph.add_workflow(wf)
        assert empty_graph.get_workflow_by_id(wf.id) is None

    def test_update_workflow_raises_dynamic_validation_error(
        self, empty_graph, module_fastqc, monkeypatch
    ):
        empty_graph.add_workflow(module_fastqc)
        empty_graph.pop_events()

        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [{"version": "1.0.0-abcdefa"}],
        )
        updated = module_fastqc.model_copy(update={"version": "0.0.0-badc0de"})
        with pytest.raises(ConfigValidationError):
            empty_graph.update_workflow(updated)

    def test_update_workflow_skip_if_unchanged(self, empty_graph, monkeypatch):
        """previous is now resolved internally via get_workflow_by_id — no
        caller needs to pass it in (unlike the old session-layer design)."""
        wf = NfPipeline(
            name="my-org/custom-pipeline",
            version="1.0.0",
            url="https://github.com/my-org/custom-pipeline",
        )
        empty_graph.add_workflow(wf)
        empty_graph.pop_events()

        calls = []
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.url_exists",
            lambda url, timeout=10: calls.append("url") or True,
        )
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_pipeline_schema",
            lambda url, version: calls.append("schema") or {},
        )

        updated = wf.model_copy(update={"description": "a new description"})
        empty_graph.update_workflow(updated)
        assert calls == []

    def test_update_workflow_reruns_check_for_changed_field(
        self, empty_graph, monkeypatch
    ):
        wf = NfPipeline(
            name="my-org/custom-pipeline",
            version="1.0.0",
            url="https://github.com/my-org/custom-pipeline",
        )
        empty_graph.add_workflow(wf)
        empty_graph.pop_events()

        calls = []
        schema = {"foo": {"type": "string", "required": False, "enum": None}}
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_pipeline_schema",
            lambda url, version: calls.append("schema") or schema,
        )

        updated = wf.model_copy(update={"params": {"foo": "bar"}})
        empty_graph.update_workflow(updated)
        assert calls == ["schema"]

    def test_deferred_validation_only_rechecks_touched_nodes(
        self, empty_graph, monkeypatch
    ):
        """A suspended block (Transaction/deferred_validation) that only
        touches one node must not re-run dynamic checks for the rest of the
        graph at exit — that's the whole point of touched-node scoping."""
        wf_a = NfPipeline(
            name="my-org/a", version="1.0.0", url="https://github.com/my-org/a"
        )
        wf_b = NfPipeline(
            name="my-org/b", version="1.0.0", url="https://github.com/my-org/b"
        )
        empty_graph.add_workflow(wf_a)
        empty_graph.add_workflow(wf_b)
        empty_graph.pop_events()

        checked_urls = []
        schema = {"x": {"type": "string", "required": False, "enum": None}}
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_pipeline_schema",
            lambda url, version: checked_urls.append(url) or schema,
        )

        with empty_graph.deferred_validation():
            updated_a = wf_a.model_copy(update={"params": {"x": "y"}})
            empty_graph.update_workflow(updated_a)

        assert wf_b.url not in checked_urls
        assert wf_a.url in checked_urls


class TestUtilities:
    def test_get_workflows_sorted_is_topological(
        self, two_node_graph, wf_rnaseq, wf_fetchngs
    ):
        sorted_wfs = two_node_graph.get_workflows_sorted()
        ids = [w.id for w in sorted_wfs]
        assert ids.index(wf_fetchngs.id) < ids.index(wf_rnaseq.id)

    def test_subset_start(self, two_node_graph, wf_rnaseq, wf_fetchngs):
        subset = two_node_graph.subset_workflows(start=wf_fetchngs.id)
        ids = {w.id for w in subset}
        assert wf_rnaseq.id in ids
        assert wf_fetchngs.id in ids

    def test_subset_target(self, two_node_graph, wf_rnaseq, wf_fetchngs):
        subset = two_node_graph.subset_workflows(target=wf_rnaseq.id)
        ids = {w.id for w in subset}
        assert wf_rnaseq.id in ids
        assert wf_fetchngs.id in ids

    def test_subset_start_excludes_predecessors(
        self, two_node_graph, wf_rnaseq, wf_fetchngs
    ):
        subset = two_node_graph.subset_workflows(start=wf_rnaseq.id)
        ids = {w.id for w in subset}
        assert wf_rnaseq.id in ids
        assert wf_fetchngs.id not in ids

    def test_get_start_workflow(self, two_node_graph, wf_fetchngs):
        assert two_node_graph.get_start_workflow().id == wf_fetchngs.id

    def test_get_start_workflow_empty_graph(self, empty_graph):
        assert empty_graph.get_start_workflow() is None

    def test_successors(self, two_node_graph, wf_rnaseq, wf_fetchngs):
        succs = two_node_graph.successors(wf_fetchngs)
        assert any(w.id == wf_rnaseq.id for w in succs)

    def test_predecessors(self, two_node_graph, wf_rnaseq, wf_fetchngs):
        preds = two_node_graph.predecessors(wf_rnaseq)
        assert any(w.id == wf_fetchngs.id for w in preds)

    def test_get_workflow_by_id_missing_returns_none(self, empty_graph):
        assert empty_graph.get_workflow_by_id("no-such-id") is None

    def test_get_transition_missing_returns_none(self, empty_graph):
        assert empty_graph.get_transition("a", "b") is None
