import pytest

from nf_meta.core.models import Workflow, Transition  # type: ignore[import]
from nf_meta.core.graph import MetaworkflowGraph  # type: ignore[import]
from nf_meta.core.events import (  # type: ignore[import]
    WorkflowAdded,
    WorkflowRemoved,
    WorkflowUpdated,
    TransitionAdded,
    TransitionRemoved,
)
from nf_meta.core.errors import GraphValidationError, WorkflowReferenceErrors  # type: ignore[import]


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
        wf = Workflow(
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
        with pytest.raises(ValueError):
            empty_graph.add_transition(
                Transition(source="ghost", target=wf_fetchngs.id)
            )

    def test_add_transition_unknown_target_raises(self, empty_graph, wf_rnaseq):
        empty_graph.add_workflow(wf_rnaseq)
        with pytest.raises(ValueError):
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

        wf_rnaseq = Workflow(
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
        wf = Workflow(
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

        rnaseq_with_ref = Workflow(
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

        wf_rnaseq = Workflow(
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
        g = MetaworkflowGraph.from_file(minimal_yaml_path)
        assert len(g.get_workflows()) == 2
        assert len(g.get_transitions()) == 1

    def test_to_file_round_trip(self, two_node_graph, tmp_path):
        out = tmp_path / "out.yaml"
        two_node_graph.to_file(out)
        g2 = MetaworkflowGraph.from_file(out)
        ids1 = {w.id for w in two_node_graph.get_workflows()}
        ids2 = {w.id for w in g2.get_workflows()}
        assert ids1 == ids2


# ---------------------------------------------------------------------------
# Utility methods
# ---------------------------------------------------------------------------


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
