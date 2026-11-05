import pytest


@pytest.fixture(autouse=True)
def nextflow_on_path(monkeypatch):
    """Runner tests fake the Nextflow process; they don't need Nextflow installed."""
    monkeypatch.setattr("nf_meta.runner.python_runner.check_nextflow", lambda: "nextflow")
