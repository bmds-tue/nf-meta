from unittest.mock import MagicMock

import pytest
import yaml

from nf_meta.core.graph import MetaworkflowGraph  # type: ignore[import]
from nf_meta.core.models import Transition, GlobalOptions  # type: ignore[import]
from nf_meta.runner.python_runner import SimplePythonRunner  # type: ignore[import]
from nf_meta.runner.errors import NfMetaRunnerError  # type: ignore[import]


@pytest.fixture
def runner(mock_nextflow, tmp_path):
    return SimplePythonRunner(tempdir=str(tmp_path / "cache"))


@pytest.fixture
def graph_two(wf_rnaseq, wf_fetchngs):
    g = MetaworkflowGraph()
    with g.deferred_validation():
        g.add_workflow(wf_fetchngs)
        g.add_workflow(wf_rnaseq)
        g.add_transition(Transition(source=wf_fetchngs.id, target=wf_rnaseq.id))
    g._events = []
    return g


# ---------------------------------------------------------------------------
# Helper / utility methods
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_merge_params_specific_overrides_default(self, runner):
        result = runner._merge_params(
            {"a": "1", "b": "override"}, {"b": "default", "c": "3"}
        )
        assert result == {"a": "1", "b": "override", "c": "3"}

    def test_create_params_file_writes_valid_yaml(self, runner, tmp_path):
        params = {"input": "samples.csv", "outdir": "results"}
        path = runner._create_params_file(params, tmp_path / "params.yaml")
        assert path.exists()
        loaded = yaml.safe_load(path.read_text())
        assert loaded == params

    def test_create_params_file_auto_names_when_no_path(self, runner):
        path = runner._create_params_file({"k": "v"})
        assert path.exists()
        assert path.suffix == ".yaml"

    def test_workflow_dir_contains_name_and_version(self, runner, wf_rnaseq):
        d = runner._workflow_dir(wf_rnaseq)
        assert "rnaseq" in str(d)
        assert wf_rnaseq.version in str(d)

    def test_check_run_success_true(self, runner, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / SimplePythonRunner.OUT_FILE).write_text("ok")
        assert runner._check_run_success(run_dir) is True

    def test_check_run_success_false_when_error_file_present(self, runner, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / SimplePythonRunner.OUT_FILE).write_text("ok")
        (run_dir / SimplePythonRunner.ERROR_FILE).write_text("fail")
        assert runner._check_run_success(run_dir) is False

    def test_check_run_success_false_when_no_out_file(self, runner, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        assert runner._check_run_success(run_dir) is False


# ---------------------------------------------------------------------------
# _resolve_param_references
# NOTE: python_runner.py:102 references ref.reference_name which does not exist
# on ParamsReference — should be ref.name. The test below describes correct
# behaviour and will pass once that attribute name is fixed.
# ---------------------------------------------------------------------------


class TestResolveParamReferences:
    def test_resolves_reference(self, runner, wf_rnaseq, wf_fetchngs):
        fetchngs_with_params = wf_fetchngs.model_copy(
            update={"params": {"outdir": "results"}}
        )
        rnaseq_with_ref = wf_rnaseq.model_copy(
            update={
                "params": {"input": f"${{{wf_fetchngs.id}:params:outdir}}/file.csv"}
            }
        )

        g = MetaworkflowGraph()
        with g.deferred_validation():
            g.add_workflow(fetchngs_with_params)
            g.add_workflow(rnaseq_with_ref)
            g.add_transition(Transition(source=wf_fetchngs.id, target=wf_rnaseq.id))
        g._events = []

        resolved = runner._resolve_param_references(rnaseq_with_ref, g)
        assert resolved.params["input"] == "results/file.csv"

    def test_no_refs_returns_copy_unchanged(self, runner, wf_rnaseq, graph_two):
        resolved = runner._resolve_param_references(wf_rnaseq, graph_two)
        assert resolved.params == wf_rnaseq.params


# ---------------------------------------------------------------------------
# _run_workflow command construction
# NOTE: python_runner.py:184 uses wf.profiles (wrong) instead of wf.profile.
# The profile-related tests will pass only after that typo is fixed.
# ---------------------------------------------------------------------------


class TestRunWorkflow:
    def _mock_stream(self, runner, returncode=0):
        runner._stream_proc_out = MagicMock(
            return_value=(returncode, "stdout output", "")
        )

    def test_run_workflow_success_writes_out_file(self, runner, wf_rnaseq, tmp_path):
        self._mock_stream(runner)
        result = runner._run_workflow(wf_rnaseq)
        assert result is True
        wf_dir = runner._workflow_dir(wf_rnaseq)
        assert (wf_dir / SimplePythonRunner.OUT_FILE).exists()

    def test_run_workflow_failure_writes_error_file(self, runner, wf_rnaseq):
        runner._stream_proc_out = MagicMock(return_value=(1, "", "error text"))
        result = runner._run_workflow(wf_rnaseq)
        assert result is False
        wf_dir = runner._workflow_dir(wf_rnaseq)
        assert (wf_dir / SimplePythonRunner.ERROR_FILE).exists()

    def test_run_workflow_cmd_includes_url_and_version(self, runner, wf_rnaseq):
        captured = {}

        def capture(cmd):
            captured["cmd"] = cmd
            return (0, "out", "")

        runner._stream_proc_out = capture
        runner._run_workflow(wf_rnaseq)
        assert wf_rnaseq.url in captured["cmd"]
        assert wf_rnaseq.version in captured["cmd"]

    def test_run_workflow_with_params_adds_params_file_flag(self, runner, wf_rnaseq):
        wf = wf_rnaseq.model_copy(update={"params": {"input": "samples.csv"}})
        captured = {}

        def capture(cmd):
            captured["cmd"] = cmd
            return (0, "out", "")

        runner._stream_proc_out = capture
        runner._run_workflow(wf)
        assert "-params-file" in captured["cmd"]

    def test_run_workflow_nonexistent_global_config_raises(
        self, runner, wf_rnaseq, tmp_path
    ):
        runner._stream_proc_out = MagicMock(return_value=(0, "out", ""))
        globals_with_bad_config = GlobalOptions(profile="docker")
        # Bypass the validator to inject a non-existent path
        globals_with_bad_config.__dict__["config_file"] = (
            tmp_path / "nonexistent.config"
        )
        with pytest.raises(NfMetaRunnerError):
            runner._run_workflow(wf_rnaseq, globals=globals_with_bad_config)


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


class TestRun:
    def _mock_run_workflow(self, runner, success=True):
        runner._run_workflow = MagicMock(return_value=success)

    def test_run_calls_workflows_in_dag_order(
        self, runner, graph_two, wf_rnaseq, wf_fetchngs
    ):
        call_order = []

        def fake_run(wf, *args, **kwargs):
            call_order.append(wf.id)
            return True

        runner._run_workflow = fake_run
        runner.run(graph_two)
        assert call_order.index(wf_fetchngs.id) < call_order.index(wf_rnaseq.id)

    def test_run_skips_succeeded_workflow_when_resuming(
        self, runner, graph_two, wf_fetchngs
    ):
        # Pre-create a "success" marker in the cache dir for wf_fetchngs
        wf_dir = runner._workflow_dir(wf_fetchngs)
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / SimplePythonRunner.OUT_FILE).write_text("done")

        call_ids = []

        def fake_run(wf, *args, **kwargs):
            call_ids.append(wf.id)
            return True

        runner._run_workflow = fake_run
        runner.run(graph_two, resume=True)
        assert wf_fetchngs.id not in call_ids

    def test_run_stops_on_first_failure(
        self, runner, graph_two, wf_fetchngs, wf_rnaseq
    ):
        call_ids = []

        def fake_run(wf, *args, **kwargs):
            call_ids.append(wf.id)
            return False  # always fail

        runner._run_workflow = fake_run
        runner.run(graph_two)
        assert len(call_ids) == 1  # stopped after first failure

    def test_resume_delegates_to_run_with_flag(self, runner, graph_two):
        runner.run = MagicMock()
        runner.resume(graph_two)
        runner.run.assert_called_once_with(graph_two, resume=True)

    def test_run_applies_start_target_subset(
        self, runner, graph_two, wf_rnaseq, wf_fetchngs
    ):
        runner.start_wf_id = wf_rnaseq.id
        call_ids = []

        def fake_run(wf, *args, **kwargs):
            call_ids.append(wf.id)
            return True

        runner._run_workflow = fake_run
        runner.run(graph_two)
        assert wf_fetchngs.id not in call_ids
        assert wf_rnaseq.id in call_ids
