import pytest

from nf_meta.core.graph import MetaworkflowGraph  # type: ignore[import]
from nf_meta.core.history import History  # type: ignore[import]
from nf_meta.core.models import NfModule, Transition, GlobalOptions  # type: ignore[import]
from nf_meta.core.errors import DynamicValidationError  # type: ignore[import]
from nf_meta.core.events import (  # type: ignore[import]
    WorkflowAdded,
    WorkflowRemoved,
    WorkflowUpdated,
    TransitionAdded,
    TransitionRemoved,
    GlobalOptionsUpdated,
)
from nf_meta.core.events import (
    AddWorkflow,
    RemoveWorkflow,
    EditWorkflow,
    AddTransition,
    RemoveTransition,
    UpdateGlobalOptions,
    Transaction,
)


@pytest.fixture
def history():
    return History()


@pytest.fixture
def graph(wf_rnaseq, wf_fetchngs):
    g = MetaworkflowGraph()
    g.add_workflow(wf_rnaseq)
    g.add_workflow(wf_fetchngs)
    g.pop_events()
    return g


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


class TestExecute:
    def test_execute_stores_in_undo_stack(self, history, graph, wf_rnaseq):
        cmd = RemoveWorkflow(wf_rnaseq.id)
        history.execute(cmd, graph)
        assert history.undoable()

    def test_execute_clears_redo_stack(self, history, graph, wf_rnaseq, wf_fetchngs):
        # Put something in the redo stack first
        history.execute(RemoveWorkflow(wf_rnaseq.id), graph)
        history.undo(graph)
        assert history.redoable()
        # New command clears it
        history.execute(RemoveWorkflow(wf_fetchngs.id), graph)
        assert not history.redoable()

    def test_execute_returns_events(self, history, graph, wf_rnaseq):
        events = history.execute(RemoveWorkflow(wf_rnaseq.id), graph)
        assert len(events) == 1
        assert isinstance(events[0], WorkflowRemoved)

    def test_execute_rolls_back_on_error(self, history, graph):
        initial_nodes = set(graph.G.nodes)
        with pytest.raises(ValueError):
            history.execute(RemoveWorkflow("nonexistent-id"), graph)
        # Graph state should be unchanged
        assert set(graph.G.nodes) == initial_nodes
        assert not history.undoable()


# ---------------------------------------------------------------------------
# undo / redo
# ---------------------------------------------------------------------------


class TestUndoRedo:
    def test_undo_reverts_remove_workflow(self, history, graph, wf_rnaseq):
        history.execute(RemoveWorkflow(wf_rnaseq.id), graph)
        assert graph.get_workflow_by_id(wf_rnaseq.id) is None
        history.undo(graph)
        assert graph.get_workflow_by_id(wf_rnaseq.id) is not None

    def test_undo_moves_to_redo_stack(self, history, graph, wf_rnaseq):
        history.execute(RemoveWorkflow(wf_rnaseq.id), graph)
        history.undo(graph)
        assert history.redoable()
        assert not history.undoable()

    def test_redo_reapplies_command(self, history, graph, wf_rnaseq):
        history.execute(RemoveWorkflow(wf_rnaseq.id), graph)
        history.undo(graph)
        history.redo(graph)
        assert graph.get_workflow_by_id(wf_rnaseq.id) is None

    def test_redo_moves_back_to_undo_stack(self, history, graph, wf_rnaseq):
        history.execute(RemoveWorkflow(wf_rnaseq.id), graph)
        history.undo(graph)
        history.redo(graph)
        assert history.undoable()
        assert not history.redoable()

    def test_full_undo_redo_cycle(self, history, graph, wf_rnaseq):
        history.execute(RemoveWorkflow(wf_rnaseq.id), graph)
        history.undo(graph)
        history.redo(graph)
        history.undo(graph)
        assert graph.get_workflow_by_id(wf_rnaseq.id) is not None

    def test_undoable_false_when_empty(self, history):
        assert not history.undoable()

    def test_redoable_false_when_empty(self, history):
        assert not history.redoable()


# ---------------------------------------------------------------------------
# undo / redo rollback-on-exception
# ---------------------------------------------------------------------------
#
# Mirrors TestExecute.test_execute_rolls_back_on_error, extended to undo/redo:
# History.execute() already catches, rolls back via the inverted just-emitted
# events, and re-raises; undo()/redo() call Command.apply() directly with no
# equivalent. The first two tests force a generic failure to prove the
# mechanism works regardless of *why* apply() fails; the last two exercise
# the real trigger this matters for — a dynamic (network-backed) check can
# legitimately fail during replay if external state (the nf-core registry)
# drifted between the original action and the undo/redo, unlike tier-1
# checks, which can't fail on replay since undo/redo only ever move between
# previously-validated states.


class TestUndoRedoRollback:
    def test_undo_rolls_back_on_partial_failure_and_restores_stack(
        self, history, graph, wf_rnaseq, wf_fetchngs, monkeypatch
    ):
        history.execute(
            Transaction((RemoveWorkflow(wf_rnaseq.id), RemoveWorkflow(wf_fetchngs.id))),
            graph,
        )
        assert graph.get_workflow_by_id(wf_rnaseq.id) is None
        assert graph.get_workflow_by_id(wf_fetchngs.id) is None

        # Force the second of the two resurrections undo's inverse Transaction
        # will attempt to fail, so there's a partial success to roll back.
        original_add_workflow = MetaworkflowGraph.add_workflow
        calls = []

        def flaky_add_workflow(self, wf):
            calls.append(wf.id)
            if len(calls) == 2:
                raise RuntimeError("simulated failure")
            return original_add_workflow(self, wf)

        monkeypatch.setattr(MetaworkflowGraph, "add_workflow", flaky_add_workflow)

        with pytest.raises(RuntimeError):
            history.undo(graph)

        # Rollback: the first (successful) resurrection must not be left
        # orphaned in the graph.
        assert graph.get_workflow_by_id(wf_rnaseq.id) is None
        assert graph.get_workflow_by_id(wf_fetchngs.id) is None
        # The failed undo is restored so it can be retried.
        assert history.undoable()
        assert not history.redoable()

    def test_redo_rolls_back_on_failure_and_restores_stack(
        self, history, graph, wf_rnaseq, monkeypatch
    ):
        history.execute(RemoveWorkflow(wf_rnaseq.id), graph)
        history.undo(graph)
        assert graph.get_workflow_by_id(wf_rnaseq.id) is not None

        def failing_remove_workflow(self, wf_id, recursive=False):
            raise RuntimeError("simulated failure")

        monkeypatch.setattr(
            MetaworkflowGraph, "remove_workflow", failing_remove_workflow
        )

        with pytest.raises(RuntimeError):
            history.redo(graph)

        # redo failed before anything succeeded — graph unchanged.
        assert graph.get_workflow_by_id(wf_rnaseq.id) is not None
        # The failed redo is restored so it can be retried.
        assert history.redoable()
        assert not history.undoable()

    def test_undo_rolls_back_on_dynamic_check_failure(self, history, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [{"version": "0.0.0-6c4ed3a"}, {"version": "1.0.0-aaaaaaa"}],
        )
        module_a = NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")
        module_b = NfModule(name="nf-core/fastqc", version="1.0.0-aaaaaaa")

        graph = MetaworkflowGraph()
        graph.add_workflow(module_a)
        graph.add_workflow(module_b)
        graph.pop_events()

        history.execute(
            Transaction((RemoveWorkflow(module_a.id), RemoveWorkflow(module_b.id))),
            graph,
        )
        assert graph.get_workflow_by_id(module_a.id) is None
        assert graph.get_workflow_by_id(module_b.id) is None

        # External drift: module_a's version is no longer valid by the time
        # undo resurrects it (module_b's still is).
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [{"version": "1.0.0-aaaaaaa"}],
        )

        with pytest.raises(DynamicValidationError):
            history.undo(graph)

        # Both nodes are part of the same suspended batch (Transaction wraps
        # the whole undo in deferred_validation), so a failure anywhere in
        # the batch rolls the whole batch back — neither is left orphaned.
        assert graph.get_workflow_by_id(module_a.id) is None
        assert graph.get_workflow_by_id(module_b.id) is None
        # The failed undo is restored so it can be retried.
        assert history.undoable()
        assert not history.redoable()

    def test_redo_rolls_back_on_dynamic_check_failure(self, history, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [{"version": "0.0.0-6c4ed3a"}],
        )
        graph = MetaworkflowGraph()
        module = NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")

        history.execute(AddWorkflow(module), graph)
        assert graph.get_workflow_by_id(module.id) is not None

        history.undo(graph)
        assert graph.get_workflow_by_id(module.id) is None

        # External drift: the version is no longer valid by the time redo
        # resurrects it.
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_nfcore_module_releases",
            lambda name: [{"version": "9.9.9-ffffff9"}],
        )

        with pytest.raises(DynamicValidationError):
            history.redo(graph)

        assert graph.get_workflow_by_id(module.id) is None
        # The failed redo is restored so it can be retried.
        assert history.redoable()
        assert not history.undoable()


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------


class TestTransaction:
    def test_transaction_applies_all_commands(
        self, history, graph, wf_rnaseq, wf_fetchngs
    ):
        cmd = Transaction(
            (
                RemoveWorkflow(wf_rnaseq.id),
                RemoveWorkflow(wf_fetchngs.id),
            )
        )
        history.execute(cmd, graph)
        assert graph.get_workflow_by_id(wf_rnaseq.id) is None
        assert graph.get_workflow_by_id(wf_fetchngs.id) is None

    def test_transaction_undo_reverts_all(self, history, graph, wf_rnaseq, wf_fetchngs):
        cmd = Transaction(
            (
                RemoveWorkflow(wf_rnaseq.id),
                RemoveWorkflow(wf_fetchngs.id),
            )
        )
        history.execute(cmd, graph)
        history.undo(graph)
        assert graph.get_workflow_by_id(wf_rnaseq.id) is not None
        assert graph.get_workflow_by_id(wf_fetchngs.id) is not None


# ---------------------------------------------------------------------------
# Event.get_undo_cmd() correctness
# ---------------------------------------------------------------------------


class TestEventUndoCommands:
    def test_workflow_added_undo_is_remove(self, wf_rnaseq):
        event = WorkflowAdded(wf_rnaseq)
        cmd = event.get_undo_cmd()
        assert isinstance(cmd, RemoveWorkflow)
        assert cmd.workflow_id == wf_rnaseq.id

    def test_workflow_removed_undo_is_add(self, wf_rnaseq):
        event = WorkflowRemoved(wf_rnaseq)
        cmd = event.get_undo_cmd()
        assert isinstance(cmd, AddWorkflow)
        assert cmd.workflow.id == wf_rnaseq.id

    def test_workflow_updated_undo_restores_old(self, wf_rnaseq, wf_fetchngs):
        event = WorkflowUpdated(old_workflow=wf_rnaseq, new_workflow=wf_fetchngs)
        cmd = event.get_undo_cmd()
        assert isinstance(cmd, EditWorkflow)
        assert cmd.workflow.id == wf_rnaseq.id

    def test_transition_added_undo_is_remove(self, wf_rnaseq, wf_fetchngs):
        tr = Transition(source=wf_rnaseq.id, target=wf_fetchngs.id)
        event = TransitionAdded(tr)
        cmd = event.get_undo_cmd()
        assert isinstance(cmd, RemoveTransition)
        assert cmd.source == wf_rnaseq.id
        assert cmd.target == wf_fetchngs.id

    def test_transition_removed_undo_is_add(self, wf_rnaseq, wf_fetchngs):
        tr = Transition(source=wf_rnaseq.id, target=wf_fetchngs.id)
        event = TransitionRemoved(tr)
        cmd = event.get_undo_cmd()
        assert isinstance(cmd, AddTransition)
        assert cmd.transition.source == wf_rnaseq.id

    def test_global_options_updated_undo_restores_old(self):
        old = GlobalOptions(profile="docker")
        new = GlobalOptions(profile="singularity")
        event = GlobalOptionsUpdated(new_globals=new, old_globals=old)
        cmd = event.get_undo_cmd()
        assert isinstance(cmd, UpdateGlobalOptions)
        assert cmd.globals.profile == "docker"
