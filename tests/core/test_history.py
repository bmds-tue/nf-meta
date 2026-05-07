import pytest

from nf_meta.core.graph import MetaworkflowGraph  # type: ignore[import]
from nf_meta.core.history import History  # type: ignore[import]
from nf_meta.core.models import Transition, GlobalOptions  # type: ignore[import]
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
