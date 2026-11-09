import pytest

from nf_meta.core.graph import MetaworkflowGraph
from nf_meta.core.models import Transition
from nf_meta.runner.errors import NfMetaRunnerError
from nf_meta.runner.runner import run_metapipeline
from nf_meta.runner.utils import RunOptions


@pytest.fixture
def graph(mock_nextflow, wf_rnaseq, wf_fetchngs):
    g = MetaworkflowGraph()
    with g.deferred_validation():
        g.add_workflow(wf_fetchngs)
        g.add_workflow(wf_rnaseq)
        g.add_transition(Transition(source=wf_fetchngs.id, target=wf_rnaseq.id))
    g.pop_events()
    return g


@pytest.fixture
def silent_runner(monkeypatch):
    """Patch SimplePythonRunner so no subprocesses are launched."""
    monkeypatch.setattr(
        "nf_meta.runner.python_runner.SimplePythonRunner.run",
        lambda self, g: None,
    )
    monkeypatch.setattr(
        "nf_meta.runner.python_runner.SimplePythonRunner.resume",
        lambda self, g: None,
    )


class TestRunMetapipeline:
    def test_valid_call_completes(self, graph, mock_nextflow, silent_runner):
        run_metapipeline(graph, RunOptions())

    def test_invalid_start_raises(self, graph, mock_nextflow, silent_runner):
        with pytest.raises(NfMetaRunnerError, match="not a valid step id"):
            run_metapipeline(graph, RunOptions(start="nonexistent-id"))

    def test_invalid_target_raises(self, graph, mock_nextflow, silent_runner):
        with pytest.raises(NfMetaRunnerError, match="not a valid step id"):
            run_metapipeline(graph, RunOptions(target="nonexistent-id"))

    def test_valid_start_does_not_raise(self, graph, mock_nextflow, silent_runner, wf_fetchngs):
        run_metapipeline(graph, RunOptions(start=wf_fetchngs.id))

    def test_unknown_runner_raises(self, graph):
        with pytest.raises(NfMetaRunnerError, match="Unknown runner"):
            run_metapipeline(graph, RunOptions(runner_name="not-a-runner"))


def test_default_run_options_not_shared(graph, monkeypatch):
    seen = []
    monkeypatch.setattr(
        "nf_meta.runner.python_runner.SimplePythonRunner.plan",
        lambda self, g, resume=False, dry_run=False: seen.append(self.run_options) or [],
    )
    from nf_meta.runner.runner import plan_metapipeline

    plan_metapipeline(graph)
    plan_metapipeline(graph)
    assert seen[0] is not seen[1]


def test_start_after_target_selects_nothing_and_fails(tmp_path):
    from nf_meta.core.models import NfPipeline
    from nf_meta.runner.python_runner import SimplePythonRunner

    g = MetaworkflowGraph()
    a = NfPipeline(name="nf-core/fetchngs", version="1.12.0")
    b = NfPipeline(name="nf-core/rnaseq", version="3.14.0")
    g.add_workflow(a)
    g.add_workflow(b)
    g.add_transition(Transition(source=a.id, target=b.id))
    with pytest.raises(NfMetaRunnerError, match="No steps between"):
        SimplePythonRunner(RunOptions(out_dir=tmp_path, start=b.id, target=a.id)).plan(g)
