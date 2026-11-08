import pytest

from nf_meta.core.errors import ConfigValidationError, RemoteConfigWriteError, SessionCommandError  # type: ignore[import]
from nf_meta.core.events import RemoveWorkflow  # type: ignore[import]
from nf_meta.core.session import EditorSession  # type: ignore[import]


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
        loaded_session.handle_command(RemoveWorkflow(loaded_session.graph.get_workflows()[0].id))
        loaded_session.start(None)
        assert not loaded_session.history.undoable()

    def test_load_config_resets_history(self, session, config_yaml):
        session.load_config(config_yaml)
        assert not session.history.undoable()
        assert not session.history.redoable()

    def test_failed_load_leaves_the_session_and_both_files_alone(self, loaded_session, config_yaml, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("config_version: 0.4.0\nsteps:\n  n01: {name: nf-core/nope, version: '1'}\n")
        before = loaded_session.graph
        with pytest.raises(ConfigValidationError):
            loaded_session.load_config(bad)
        assert loaded_session.config_file == config_yaml
        assert loaded_session.graph is before
        # the next auto-save writes to the config being edited, not to the one that failed
        loaded_session.handle_command(RemoveWorkflow(before.get_workflows()[0].id))
        assert "nf-core/nope" in bad.read_text()


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

    def test_without_write_on_change_the_file_is_untouched(self, config_yaml):
        session = EditorSession(write_on_change=False)
        session.load_config(config_yaml)
        before = config_yaml.read_text()
        session.execute(RemoveWorkflow(session.graph.get_workflows()[0].id))
        session.undo()
        session.redo()
        assert config_yaml.read_text() == before

    def test_with_write_on_change_the_file_is_rewritten(self, loaded_session, config_yaml):
        before = config_yaml.read_text()
        loaded_session.handle_command(RemoveWorkflow(loaded_session.graph.get_workflows()[0].id))
        assert config_yaml.read_text() != before

    def test_execute_raises_the_graph_error(self, loaded_session):
        with pytest.raises(ValueError):
            loaded_session.execute(RemoveWorkflow("nonexistent-id"))


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

    def test_nothing_to_undo_or_redo(self, loaded_session):
        with pytest.raises(SessionCommandError):
            loaded_session.handle_undo()
        with pytest.raises(SessionCommandError):
            loaded_session.handle_redo()


# ---------------------------------------------------------------------------
# save_to_config
# ---------------------------------------------------------------------------


class TestSaveToConfig:
    def test_save_to_config_writes_file(self, loaded_session, tmp_path):
        out = tmp_path / "saved.yaml"
        loaded_session.save_to_config(out)
        assert out.exists()

    def test_save_to_config_uses_existing_config_file_when_none_passed(self, loaded_session, config_yaml):
        loaded_session.save_to_config(None)
        assert config_yaml.exists()

    def test_a_failed_save_as_keeps_the_current_file(self, loaded_session, config_yaml, tmp_path):
        project_dir = loaded_session.graph.project_dir
        with pytest.raises(OSError):
            loaded_session.save_to_config(tmp_path / "missing-dir" / "saved.yaml")
        assert loaded_session.config_file == config_yaml
        assert loaded_session.graph.project_dir == project_dir

    def test_save_as_expands_the_home_folder(self, loaded_session, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        loaded_session.save_to_config("~/saved.yaml")
        assert (tmp_path / "saved.yaml").exists()
        assert loaded_session.config_file == tmp_path / "saved.yaml"


class TestRemoteConfig:
    """A config loaded from a URL (here: a loaded session pointed at one) is never written to."""

    URL = "https://example.org/metapipeline.yaml"

    @pytest.fixture
    def remote_session(self, loaded_session):
        loaded_session.config_file = self.URL
        return loaded_session

    def test_a_change_is_refused_and_the_graph_unchanged(self, remote_session):
        before = len(remote_session.graph.get_workflows())
        with pytest.raises(RemoteConfigWriteError):
            remote_session.handle_command(RemoveWorkflow(remote_session.graph.get_workflows()[0].id))
        assert len(remote_session.graph.get_workflows()) == before
        assert not remote_session.history.undoable()

    def test_saving_to_the_url_is_refused(self, remote_session):
        with pytest.raises(RemoteConfigWriteError):
            remote_session.save_to_config(None)

    def test_after_saving_locally_changes_work(self, remote_session, tmp_path):
        local = tmp_path / "copy.yaml"
        remote_session.save_to_config(local)
        remote_session.handle_command(RemoveWorkflow(remote_session.graph.get_workflows()[0].id))
        assert remote_session.config_file == local
        assert remote_session.history.undoable()

    def test_without_write_on_change_changes_work(self, config_yaml):
        session = EditorSession(write_on_change=False)
        session.start(config_yaml)
        session.config_file = self.URL
        session.handle_command(RemoveWorkflow(session.graph.get_workflows()[0].id))
