from unittest.mock import MagicMock

import pytest
import yaml

from nf_meta.core.graph import MetaworkflowGraph  # type: ignore[import]
from nf_meta.core.models import GlobalOptions, Transition  # type: ignore[import]
from nf_meta.runner.errors import NfMetaRunnerError  # type: ignore[import]
from nf_meta.runner.python_runner import SimplePythonRunner  # type: ignore[import]
from nf_meta.runner.spec import resolve_references  # type: ignore[import]
from nf_meta.runner.utils import RunOptions  # type: ignore[import]


@pytest.fixture
def runner(mock_nextflow, tmp_path):
    return SimplePythonRunner(RunOptions(out_dir=tmp_path))


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
    def test_state_dir_is_under_out_dir_and_named_by_step_id(self, runner, graph_two, wf_rnaseq, tmp_path):
        state_dir = runner.plan(graph_two)[1].spec.state_dir
        assert state_dir.parent == tmp_path / ".nf-meta" / "steps"
        assert state_dir.name.startswith(f"{wf_rnaseq.id}_")

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
        fetchngs_with_params = wf_fetchngs.model_copy(update={"params": {"outdir": "results"}})
        rnaseq_with_ref = wf_rnaseq.model_copy(
            update={"params": {"input": f"${{{wf_fetchngs.id}:params:outdir}}/file.csv"}}
        )

        g = MetaworkflowGraph()
        with g.deferred_validation():
            g.add_workflow(fetchngs_with_params)
            g.add_workflow(rnaseq_with_ref)
            g.add_transition(Transition(source=wf_fetchngs.id, target=wf_rnaseq.id))
        g._events = []

        resolved = resolve_references(rnaseq_with_ref, g)
        assert resolved.params["input"] == "results/file.csv"

    def test_no_refs_returns_copy_unchanged(self, runner, wf_rnaseq, graph_two):
        resolved = resolve_references(wf_rnaseq, graph_two)
        assert resolved.params == wf_rnaseq.params

    def test_resolved_params_preferred_over_raw(self, runner, wf_rnaseq, wf_fetchngs):
        """resolved dict wins over raw workflow params."""
        fetchngs_with_raw = wf_fetchngs.model_copy(update={"params": {"outdir": "raw_value"}})
        rnaseq_with_ref = wf_rnaseq.model_copy(
            update={"params": {"input": f"${{{wf_fetchngs.id}:params:outdir}}/file.csv"}}
        )
        g = MetaworkflowGraph()
        with g.deferred_validation():
            g.add_workflow(fetchngs_with_raw)
            g.add_workflow(rnaseq_with_ref)
            g.add_transition(Transition(source=wf_fetchngs.id, target=wf_rnaseq.id))
        g.pop_events()

        resolved = resolve_references(
            rnaseq_with_ref,
            g,
            resolved={wf_fetchngs.id: {"outdir": "resolved_value"}},
        )
        assert resolved.params["input"] == "resolved_value/file.csv"

    def test_chain_resolution_via_resolved_params(self, runner, wf_fetchngs, wf_rnaseq, wf_sarek):
        """C references B's param; B's param was itself resolved from A — chain works."""
        a = wf_fetchngs.model_copy(update={"params": {"outdir": "/data/raw"}})
        b = wf_rnaseq.model_copy(update={"params": {"outdir": f"${{{wf_fetchngs.id}:params:outdir}}/processed"}})
        c = wf_sarek.model_copy(update={"params": {"input": f"${{{wf_rnaseq.id}:params:outdir}}/samples.csv"}})
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
        resolved_c = resolve_references(c, g, resolved=b_resolved_params)
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
        b = wf_rnaseq.model_copy(update={"params": {"input": f"${{{wf_fetchngs.id}:params:outdir}}/samples.csv"}})
        g = MetaworkflowGraph()
        with g.deferred_validation():
            g.add_workflow(a)
            g.add_workflow(b)
            g.add_transition(Transition(source=a.id, target=b.id))
        g.pop_events()
        return g, a, b

    def test_raises_when_cross_boundary_cache_missing(self, runner, wf_fetchngs, wf_rnaseq):
        g, a, b = self._graph_with_ref(wf_fetchngs, wf_rnaseq)
        subset = [b]
        subset_ids = {b.id}
        with pytest.raises(NfMetaRunnerError, match="cross-boundary"):
            runner._validate_cross_boundary_refs(g, subset, subset_ids)

    def test_passes_when_cross_boundary_cache_exists(self, runner, wf_fetchngs, wf_rnaseq):
        g, a, b = self._graph_with_ref(wf_fetchngs, wf_rnaseq)
        runner._write_resolved_params(a, {"outdir": "/data"})
        subset = [b]
        subset_ids = {b.id}
        runner._validate_cross_boundary_refs(g, subset, subset_ids)  # no raise

    def test_no_error_when_all_refs_in_subset(self, runner, wf_fetchngs, wf_rnaseq):
        g, a, b = self._graph_with_ref(wf_fetchngs, wf_rnaseq)
        subset_ids = {a.id, b.id}
        runner._validate_cross_boundary_refs(g, [a, b], subset_ids)  # no raise


class TestExecute:
    def _step(self, runner, wf, global_options=None):
        g = MetaworkflowGraph()
        g.add_workflow(wf)
        if global_options is not None:
            g.global_options = global_options
        g.pop_events()
        return runner.plan(g)[0]

    def test_success_writes_out_file(self, runner, wf_rnaseq):
        runner._stream_proc_out = MagicMock(return_value=(0, "stdout output", ""))
        step = self._step(runner, wf_rnaseq)
        assert runner._execute(step.spec, step.command) is True
        assert (step.spec.state_dir / SimplePythonRunner.OUT_FILE).exists()

    def test_failure_writes_error_file(self, runner, wf_rnaseq):
        runner._stream_proc_out = MagicMock(return_value=(1, "", "error text"))
        step = self._step(runner, wf_rnaseq)
        assert runner._execute(step.spec, step.command) is False
        assert (step.spec.state_dir / SimplePythonRunner.ERROR_FILE).read_text() == "error text"

    def test_writes_params_file_before_running(self, runner, wf_rnaseq):
        wf = wf_rnaseq.model_copy(update={"params": {"input": "samples.csv"}})
        seen = {}

        def capture(argv, **kwargs):
            params_file = argv[argv.index("-params-file") + 1]
            seen["params"] = yaml.safe_load(open(params_file))
            return (0, "out", "")

        runner._stream_proc_out = capture
        step = self._step(runner, wf)
        runner._execute(step.spec, step.command)
        assert seen["params"] == {"input": "samples.csv"}

    def test_globals_params_reach_params_file(self, runner, wf_rnaseq):
        wf = wf_rnaseq.model_copy(update={"params": {"input": "samples.csv"}})
        step = self._step(runner, wf, GlobalOptions(params={"max_cpus": 4}))
        assert step.command.params == {"max_cpus": 4, "input": "samples.csv"}

    def test_nonexistent_global_config_raises(self, runner, wf_rnaseq, tmp_path):
        bad = GlobalOptions(profile="docker")
        # Bypass the validator to inject a non-existent path
        bad.__dict__["config_file"] = tmp_path / "nonexistent.config"
        with pytest.raises(NfMetaRunnerError):
            self._step(runner, wf_rnaseq, bad)


# ---------------------------------------------------------------------------
# plan()
# ---------------------------------------------------------------------------


class TestPlan:
    def test_steps_in_dag_order(self, runner, graph_two, wf_fetchngs, wf_rnaseq):
        ids = [s.workflow.id for s in runner.plan(graph_two)]
        assert ids == [wf_fetchngs.id, wf_rnaseq.id]

    def test_writes_nothing(self, runner, graph_two, tmp_path):
        runner.plan(graph_two)
        assert list(tmp_path.iterdir()) == []

    def test_marks_succeeded_steps_skipped_on_resume(self, runner, graph_two, wf_fetchngs):
        state_dir = runner.plan(graph_two)[0].spec.state_dir
        state_dir.mkdir(parents=True)
        (state_dir / SimplePythonRunner.OUT_FILE).write_text("done")
        skips = {s.workflow.id: s.skip for s in runner.plan(graph_two, resume=True)}
        assert skips[wf_fetchngs.id] is True
        assert not any(s.skip for s in runner.plan(graph_two, resume=False))

    def test_resolves_references(self, runner, wf_fetchngs, wf_rnaseq):
        a = wf_fetchngs.model_copy(update={"params": {"outdir": "/data"}})
        b = wf_rnaseq.model_copy(update={"params": {"input": f"${{{a.id}:params:outdir}}/samples.csv"}})
        g = MetaworkflowGraph()
        with g.deferred_validation():
            g.add_workflow(a)
            g.add_workflow(b)
            g.add_transition(Transition(source=a.id, target=b.id))
        g.pop_events()
        assert runner.plan(g)[1].command.params == {"input": "/data/samples.csv"}


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


class TestRun:
    def _record(self, runner, success=True):
        executed = []

        def fake_execute(spec, command):
            executed.append(spec.workflow)
            return success

        runner._execute = fake_execute
        return executed

    def test_run_calls_workflows_in_dag_order(self, runner, graph_two, wf_rnaseq, wf_fetchngs):
        executed = self._record(runner)
        runner.run(graph_two)
        ids = [wf.id for wf in executed]
        assert ids.index(wf_fetchngs.id) < ids.index(wf_rnaseq.id)

    def test_run_skips_succeeded_workflow_when_resuming(self, runner, graph_two, wf_fetchngs):
        wf_dir = runner.plan(graph_two)[0].spec.state_dir
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / SimplePythonRunner.OUT_FILE).write_text("done")

        executed = self._record(runner)
        runner.run(graph_two, resume=True)
        assert wf_fetchngs.id not in [wf.id for wf in executed]

    def test_run_raises_on_first_failure(self, runner, graph_two, wf_fetchngs):
        executed = self._record(runner, success=False)
        with pytest.raises(NfMetaRunnerError, match=wf_fetchngs.id):
            runner.run(graph_two)
        assert len(executed) == 1

    def test_resume_delegates_to_run_with_flag(self, runner, graph_two):
        runner.run = MagicMock()
        runner.resume(graph_two)
        runner.run.assert_called_once_with(graph_two, resume=True)

    def test_run_applies_start_target_subset(self, runner, graph_two, wf_rnaseq, wf_fetchngs):
        runner.run_options.start = wf_rnaseq.id
        executed = self._record(runner)
        runner.run(graph_two)
        ids = [wf.id for wf in executed]
        assert wf_fetchngs.id not in ids
        assert wf_rnaseq.id in ids

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

        self._record(runner)
        runner.run(g)

        assert runner._load_resolved_params(a) == {"outdir": "/results"}
        assert runner._load_resolved_params(b) == {"input": "samples.csv"}

    def test_subset_run_resolves_cross_boundary_ref_from_cache(self, runner, wf_fetchngs, wf_rnaseq):
        """--start=B resolves B's reference to A using A's cached resolved params."""
        a = wf_fetchngs.model_copy(update={"params": {"outdir": "/data/results"}})
        b = wf_rnaseq.model_copy(update={"params": {"input": f"${{{wf_fetchngs.id}:params:outdir}}/samples.csv"}})
        g = MetaworkflowGraph()
        with g.deferred_validation():
            g.add_workflow(a)
            g.add_workflow(b)
            g.add_transition(Transition(source=a.id, target=b.id))
        g.pop_events()

        # Simulate A having been successfully run previously
        runner._write_resolved_params(a, a.params)

        runner.run_options.start = b.id
        executed = self._record(runner)
        runner.run(g)

        assert [wf.id for wf in executed] == [b.id]
        assert executed[0].params["input"] == "/data/results/samples.csv"

    def test_subset_run_fails_when_cross_boundary_cache_missing(self, runner, wf_fetchngs, wf_rnaseq):
        a = wf_fetchngs.model_copy(update={"params": {"outdir": "/data"}})
        b = wf_rnaseq.model_copy(update={"params": {"input": f"${{{wf_fetchngs.id}:params:outdir}}/samples.csv"}})
        g = MetaworkflowGraph()
        with g.deferred_validation():
            g.add_workflow(a)
            g.add_workflow(b)
            g.add_transition(Transition(source=a.id, target=b.id))
        g.pop_events()

        runner.run_options.start = b.id
        with pytest.raises(NfMetaRunnerError, match="cross-boundary"):
            runner.run(g)

    def test_module_step_needs_nextflow_26_04(self, runner, module_fastqc, monkeypatch):
        g = MetaworkflowGraph()
        g.add_workflow(module_fastqc)
        g.pop_events()
        monkeypatch.setattr(
            "nf_meta.runner.python_runner.get_installed_nextflow_version",
            lambda: (25, 10, 9, 0),
        )
        self._record(runner)
        with pytest.raises(NfMetaRunnerError, match="26.04"):
            runner.run(g)
