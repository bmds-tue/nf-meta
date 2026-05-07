import pytest

from nf_meta.core.session import EditorSession  # type: ignore[import]
from nf_meta.core.events import RemoveWorkflow  # type: ignore[import]
from nf_meta.core.errors import SessionCommandError  # type: ignore[import]


@pytest.fixture
def session():
    return EditorSession()


@pytest.fixture
def loaded_session(session, config_yaml):
    session.start(config_yaml)
    return session


# ---------------------------------------------------------------------------
# start / load
# ---------------------------------------------------------------------------


class TestSessionStart:
    def test_start_without_config_creates_empty_graph(self, session):
        session.start(None)
        assert session.graph is not None
        assert session.graph.get_workflows() == []

    def test_start_with_config_loads_graph(self, session, config_yaml):
        session.start(config_yaml)
        assert len(session.graph.get_workflows()) == 2

    def test_start_resets_history(self, loaded_session, wf_rnaseq):
        # Execute a command, then start again — history should be fresh
        loaded_session.handle_command(
            RemoveWorkflow(loaded_session.graph.get_workflows()[0].id)
        )
        loaded_session.start(None)
        assert not loaded_session.history.undoable()

    def test_load_config_resets_history(self, session, config_yaml):
        session.load_config(config_yaml)
        assert not session.history.undoable()
        assert not session.history.redoable()


# ---------------------------------------------------------------------------
# handle_command
# ---------------------------------------------------------------------------


class TestHandleCommand:
    def test_handle_command_mutates_graph(self, loaded_session):
        wf_count_before = len(loaded_session.graph.get_workflows())
        wf_to_remove = loaded_session.graph.get_workflows()[0]
        loaded_session.handle_command(RemoveWorkflow(wf_to_remove.id))
        assert len(loaded_session.graph.get_workflows()) == wf_count_before - 1

    def test_handle_command_records_in_history(self, loaded_session):
        wf_to_remove = loaded_session.graph.get_workflows()[0]
        loaded_session.handle_command(RemoveWorkflow(wf_to_remove.id))
        assert loaded_session.history.undoable()

    def test_handle_command_saves_to_config_file(self, loaded_session, config_yaml):
        wf_to_remove = loaded_session.graph.get_workflows()[0]
        mtime_before = config_yaml.stat().st_mtime
        loaded_session.handle_command(RemoveWorkflow(wf_to_remove.id))
        mtime_after = config_yaml.stat().st_mtime
        assert mtime_after >= mtime_before

    def test_handle_command_raises_session_error_on_invalid(self, loaded_session):
        with pytest.raises(SessionCommandError):
            loaded_session.handle_command(RemoveWorkflow("nonexistent-id"))


# ---------------------------------------------------------------------------
# undo / redo
# ---------------------------------------------------------------------------


class TestUndoRedo:
    def test_handle_undo_reverts_last_command(self, loaded_session):
        wf_to_remove = loaded_session.graph.get_workflows()[0]
        loaded_session.handle_command(RemoveWorkflow(wf_to_remove.id))
        loaded_session.handle_undo()
        assert loaded_session.graph.get_workflow_by_id(wf_to_remove.id) is not None

    def test_handle_redo_reapplies_command(self, loaded_session):
        wf_to_remove = loaded_session.graph.get_workflows()[0]
        loaded_session.handle_command(RemoveWorkflow(wf_to_remove.id))
        loaded_session.handle_undo()
        loaded_session.handle_redo()
        assert loaded_session.graph.get_workflow_by_id(wf_to_remove.id) is None


# ---------------------------------------------------------------------------
# save_to_config
# ---------------------------------------------------------------------------


class TestSaveToConfig:
    def test_save_to_config_writes_file(self, loaded_session, tmp_path):
        out = tmp_path / "saved.yaml"
        loaded_session.save_to_config(out)
        assert out.exists()

    def test_save_to_config_uses_existing_config_file_when_none_passed(
        self, loaded_session, config_yaml
    ):
        loaded_session.save_to_config(None)
        assert config_yaml.exists()
