import pytest

from nf_meta.core.graph import MetaworkflowGraph  # type: ignore[import]
from nf_meta.core.models import Transition  # type: ignore[import]
from nf_meta.runner.runner import run_metapipeline, Runners  # type: ignore[import]
from nf_meta.runner.errors import NfMetaRunnerError  # type: ignore[import]


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
    """Patch SimplePythonRunner.run so no subprocesses are launched."""
    monkeypatch.setattr(
        "nf_meta.runner.runner.SimplePythonRunner.run",
        lambda self, g: None,
    )
    monkeypatch.setattr(
        "nf_meta.runner.runner.SimplePythonRunner.resume",
        lambda self, g: None,
    )


class TestRunMetapipeline:
    def test_valid_call_completes(self, graph, mock_nextflow, silent_runner):
        run_metapipeline(graph, runner_name=Runners.PYTHON)

    def test_invalid_start_raises(self, graph, mock_nextflow, silent_runner):
        with pytest.raises(NfMetaRunnerError, match="not a valid workflow id"):
            run_metapipeline(graph, start="nonexistent-id")

    def test_invalid_target_raises(self, graph, mock_nextflow, silent_runner):
        with pytest.raises(NfMetaRunnerError, match="not a valid workflow id"):
            run_metapipeline(graph, target="nonexistent-id")

    def test_valid_start_does_not_raise(
        self, graph, mock_nextflow, silent_runner, wf_fetchngs
    ):
        run_metapipeline(graph, start=wf_fetchngs.id)
