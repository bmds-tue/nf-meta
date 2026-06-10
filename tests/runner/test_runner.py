import pytest

from nf_meta.core.graph import MetaworkflowGraph
from nf_meta.core.models import Transition
from nf_meta.runner.runner import run_metapipeline
from nf_meta.runner.utils import RunOptions
from nf_meta.runner.errors import NfMetaRunnerError


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
        with pytest.raises(NfMetaRunnerError, match="not a valid workflow id"):
            run_metapipeline(graph, RunOptions(start="nonexistent-id"))

    def test_invalid_target_raises(self, graph, mock_nextflow, silent_runner):
        with pytest.raises(NfMetaRunnerError, match="not a valid workflow id"):
            run_metapipeline(graph, RunOptions(target="nonexistent-id"))

    def test_valid_start_does_not_raise(
        self, graph, mock_nextflow, silent_runner, wf_fetchngs
    ):
        run_metapipeline(graph, RunOptions(start=wf_fetchngs.id))

    def test_unknown_runner_raises(self, graph):
        with pytest.raises(NfMetaRunnerError, match="Unknown runner"):
            run_metapipeline(graph, RunOptions(runner_name="not-a-runner"))
