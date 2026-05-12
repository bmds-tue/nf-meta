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

    def test_resolved_params_preferred_over_raw(self, runner, wf_rnaseq, wf_fetchngs):
        """resolved_params dict wins over raw workflow params."""
        fetchngs_with_raw = wf_fetchngs.model_copy(
            update={"params": {"outdir": "raw_value"}}
        )
        rnaseq_with_ref = wf_rnaseq.model_copy(
            update={
                "params": {"input": f"${{{wf_fetchngs.id}:params:outdir}}/file.csv"}
            }
        )
        g = MetaworkflowGraph()
        with g.deferred_validation():
            g.add_workflow(fetchngs_with_raw)
            g.add_workflow(rnaseq_with_ref)
            g.add_transition(Transition(source=wf_fetchngs.id, target=wf_rnaseq.id))
        g.pop_events()

        resolved = runner._resolve_param_references(
            rnaseq_with_ref,
            g,
            resolved_params={wf_fetchngs.id: {"outdir": "resolved_value"}},
        )
        assert resolved.params["input"] == "resolved_value/file.csv"

    def test_chain_resolution_via_resolved_params(
        self, runner, wf_fetchngs, wf_rnaseq, wf_sarek
    ):
        """C references B's param; B's param was itself resolved from A — chain works."""
        a = wf_fetchngs.model_copy(update={"params": {"outdir": "/data/raw"}})
        b = wf_rnaseq.model_copy(
            update={
                "params": {"outdir": f"${{{wf_fetchngs.id}:params:outdir}}/processed"}
            }
        )
        c = wf_sarek.model_copy(
            update={
                "params": {"input": f"${{{wf_rnaseq.id}:params:outdir}}/samples.csv"}
            }
        )
        g = MetaworkflowGraph()
        with g.deferred_validation():
            g.add_workflow(a)
            g.add_workflow(b)
            g.add_workflow(c)
            g.add_transition(Transition(source=a.id, target=b.id))
            g.add_transition(Transition(source=b.id, target=c.id))
        g._events = []

        # Simulate B having already been resolved
        b_resolved_params = {b.id: {"outdir": "/data/raw/processed"}}
        resolved_c = runner._resolve_param_references(
            c, g, resolved_params=b_resolved_params
        )
        assert resolved_c.params["input"] == "/data/raw/processed/samples.csv"


class TestResolvedParamsCache:
    def test_write_and_load_resolved_params(self, runner, wf_rnaseq):
        wf = wf_rnaseq.model_copy(update={"params": {"outdir": "/results"}})
        runner._write_resolved_params(wf, {"outdir": "/results"})
        loaded = runner._load_resolved_params(wf)
        assert loaded == {"outdir": "/results"}

    def test_load_resolved_params_returns_none_when_missing(self, runner, wf_rnaseq):
        assert runner._load_resolved_params(wf_rnaseq) is None

    def test_different_params_produce_different_cache_paths(self, runner, wf_rnaseq):
        wf_a = wf_rnaseq.model_copy(update={"params": {"outdir": "/v1"}})
        wf_b = wf_rnaseq.model_copy(update={"params": {"outdir": "/v2"}})
        assert runner._resolved_params_path(wf_a) != runner._resolved_params_path(wf_b)

    def test_changed_version_produces_different_cache_path(self, runner, wf_rnaseq):
        wf_a = wf_rnaseq.model_copy(update={"version": "3.14.0"})
        wf_b = wf_rnaseq.model_copy(update={"version": "3.15.0"})
        assert runner._resolved_params_path(wf_a) != runner._resolved_params_path(wf_b)


class TestValidateCrossBoundaryRefs:
    def _graph_with_ref(self, wf_fetchngs, wf_rnaseq):
        """fetchngs → rnaseq where rnaseq references fetchngs.outdir."""
        a = wf_fetchngs.model_copy(update={"params": {"outdir": "/data"}})
        b = wf_rnaseq.model_copy(
            update={
                "params": {"input": f"${{{wf_fetchngs.id}:params:outdir}}/samples.csv"}
            }
        )
        g = MetaworkflowGraph()
        with g.deferred_validation():
            g.add_workflow(a)
            g.add_workflow(b)
            g.add_transition(Transition(source=a.id, target=b.id))
        g.pop_events()
        return g, a, b

    def test_raises_when_cross_boundary_cache_missing(
        self, runner, wf_fetchngs, wf_rnaseq
    ):
        g, a, b = self._graph_with_ref(wf_fetchngs, wf_rnaseq)
        subset = [b]
        subset_ids = {b.id}
        with pytest.raises(NfMetaRunnerError, match="cross-boundary"):
            runner._validate_cross_boundary_refs(g, subset, subset_ids)

    def test_passes_when_cross_boundary_cache_exists(
        self, runner, wf_fetchngs, wf_rnaseq
    ):
        g, a, b = self._graph_with_ref(wf_fetchngs, wf_rnaseq)
        runner._write_resolved_params(a, {"outdir": "/data"})
        subset = [b]
        subset_ids = {b.id}
        runner._validate_cross_boundary_refs(g, subset, subset_ids)  # no raise

    def test_no_error_when_all_refs_in_subset(self, runner, wf_fetchngs, wf_rnaseq):
        g, a, b = self._graph_with_ref(wf_fetchngs, wf_rnaseq)
        subset_ids = {a.id, b.id}
        runner._validate_cross_boundary_refs(g, [a, b], subset_ids)  # no raise


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

    def test_run_writes_resolved_params(self, runner, wf_fetchngs, wf_rnaseq):
        """Successful run writes _resolved.yaml for each workflow."""
        a = wf_fetchngs.model_copy(update={"params": {"outdir": "/results"}})
        b = wf_rnaseq.model_copy(update={"params": {"input": "samples.csv"}})
        g = MetaworkflowGraph()
        with g.deferred_validation():
            g.add_workflow(a)
            g.add_workflow(b)
            g.add_transition(Transition(source=a.id, target=b.id))
        g.pop_events()

        runner._run_workflow = MagicMock(return_value=True)
        runner.run(g)

        assert runner._load_resolved_params(a) == {"outdir": "/results"}
        assert runner._load_resolved_params(b) == {"input": "samples.csv"}

    def test_subset_run_resolves_cross_boundary_ref_from_cache(
        self, runner, wf_fetchngs, wf_rnaseq
    ):
        """--start=B resolves B's reference to A using A's cached resolved params."""
        a = wf_fetchngs.model_copy(update={"params": {"outdir": "/data/results"}})
        b = wf_rnaseq.model_copy(
            update={
                "params": {"input": f"${{{wf_fetchngs.id}:params:outdir}}/samples.csv"}
            }
        )
        g = MetaworkflowGraph()
        with g.deferred_validation():
            g.add_workflow(a)
            g.add_workflow(b)
            g.add_transition(Transition(source=a.id, target=b.id))
        g.pop_events()

        # Simulate A having been successfully run previously
        runner._write_resolved_params(a, a.params)

        runner.start_wf_id = b.id
        resolved_wfs = []

        def fake_run(wf, *args, **kwargs):
            resolved_wfs.append(wf)
            return True

        runner._run_workflow = fake_run
        runner.run(g)

        assert len(resolved_wfs) == 1
        assert resolved_wfs[0].params["input"] == "/data/results/samples.csv"

    def test_subset_run_fails_when_cross_boundary_cache_missing(
        self, runner, wf_fetchngs, wf_rnaseq
    ):
        a = wf_fetchngs.model_copy(update={"params": {"outdir": "/data"}})
        b = wf_rnaseq.model_copy(
            update={
                "params": {"input": f"${{{wf_fetchngs.id}:params:outdir}}/samples.csv"}
            }
        )
        g = MetaworkflowGraph()
        with g.deferred_validation():
            g.add_workflow(a)
            g.add_workflow(b)
            g.add_transition(Transition(source=a.id, target=b.id))
        g.pop_events()

        runner.start_wf_id = b.id
        with pytest.raises(NfMetaRunnerError, match="cross-boundary"):
            runner.run(g)
