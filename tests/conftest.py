"""
Shared fixtures for the nf-meta test suite.

The most important fixture here is `mock_nfcore` (autouse=True):
every test runs with network calls to nf-co.re and url_exists
replaced by fast in-process stubs so tests are deterministic and offline.
"""

from pathlib import Path

import pytest
import yaml

from nf_meta.core.models import NfPipeline, NfModule, Transition  # type: ignore[import]
from nf_meta.core.graph import MetaworkflowGraph  # type: ignore[import]


# ---------------------------------------------------------------------------
# Static fake nf-core pipeline catalogue used by all tests
# ---------------------------------------------------------------------------

FAKE_NFCORE_PIPELINES = [
    {
        "name": "nf-core/rnaseq",
        "url": "https://github.com/nf-core/rnaseq",
        "description": "RNA sequencing analysis pipeline",
        "releases": [
            {"tag_name": "3.14.0", "tag_sha": "abc123", "published_at": "2024-01-01"}
        ],
    },
    {
        "name": "nf-core/fetchngs",
        "url": "https://github.com/nf-core/fetchngs",
        "description": "Fetch NGS data from public databases",
        "releases": [
            {"tag_name": "1.12.0", "tag_sha": "def456", "published_at": "2024-01-01"}
        ],
    },
    {
        "name": "nf-core/sarek",
        "url": "https://github.com/nf-core/sarek",
        "description": "Variant calling pipeline",
        "releases": [],
    },
]


# ---------------------------------------------------------------------------
# Autouse: patch out all network calls for every test
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Fake pipeline schema used by all tests — covers params used in unit tests
# ---------------------------------------------------------------------------

def _make_spec(type_, *, required=False, default=None, enum=None, hidden=False):
    return {
        "type": type_,
        "required": required,
        "enum": enum,
        "pattern": None,
        "format": None,
        "default": default,
        "hidden": hidden,
    }


FAKE_PIPELINE_SCHEMA: dict[str, dict] = {
    # Real nf-core/rnaseq params used in unit tests
    "input": _make_spec("string", default=""),
    "outdir": _make_spec("string", default="results"),
    # Fictional param names used specifically in coercion tests
    "count": _make_spec("integer", default=0),
    "threshold": _make_spec("number", default=0.0),
    "flag": _make_spec("boolean", default=False),
}

# Module schema shaped like fastqc's meta.yml inputs.
# Matches what _parse_module_schema produces (no format/default/hidden keys).
FAKE_MODULE_SCHEMA: dict[str, dict] = {
    "meta":  {"type": "map",  "required": True, "enum": None, "pattern": None},
    "reads": {"type": "file", "required": True, "enum": None, "pattern": "*_{1,2}.fastq.gz"},
}


@pytest.fixture(autouse=True)
def mock_nfcore(monkeypatch):
    """Replace HTTP-backed helpers with static stubs for every test."""
    monkeypatch.setattr(
        "nf_meta.core.models.get_nfcore_pipelines", lambda: FAKE_NFCORE_PIPELINES
    )
    monkeypatch.setattr("nf_meta.core.models.url_exists", lambda url, timeout=10: True)
    monkeypatch.setattr(
        "nf_meta.core.models.github_file_exists", lambda url, path, ref: True
    )
    monkeypatch.setattr(
        "nf_meta.core.models.get_pipeline_schema",
        lambda url, version: FAKE_PIPELINE_SCHEMA,
    )
    monkeypatch.setattr(
        "nf_meta.core.models.get_module_schema",
        lambda name, version: {},
    )
    monkeypatch.setattr(
        "nf_meta.core.models.get_nfcore_module_releases",
        lambda name: [],
    )


# ---------------------------------------------------------------------------
# Workflow fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def wf_rnaseq():
    return NfPipeline(name="nf-core/rnaseq", version="3.14.0")


@pytest.fixture
def wf_fetchngs():
    return NfPipeline(name="nf-core/fetchngs", version="1.12.0")


@pytest.fixture
def wf_sarek():
    return NfPipeline(name="nf-core/sarek", version="3.4.0")


@pytest.fixture
def wf_custom():
    """A non-nf-core workflow with an explicit URL."""
    return NfPipeline(
        name="my-org/custom-pipeline",
        version="1.0.0",
        url="https://github.com/my-org/custom-pipeline",
    )


@pytest.fixture
def module_fastqc():
    return NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")


# ---------------------------------------------------------------------------
# Graph fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_graph():
    return MetaworkflowGraph()


@pytest.fixture
def two_node_graph(wf_fetchngs, wf_rnaseq):
    """Graph: wf_1 → wf_2 , events cleared after setup."""
    g = MetaworkflowGraph()
    g.add_workflow(wf_fetchngs)
    g.add_workflow(wf_rnaseq)
    g.add_transition(Transition(target=wf_rnaseq.id, source=wf_fetchngs.id))
    g.pop_events()
    return g


# ---------------------------------------------------------------------------
# File fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def minimal_yaml_path():
    """Path to the static minimal.yaml fixture (read-only)."""
    return FIXTURES_DIR / "minimal.yaml"


@pytest.fixture
def config_yaml(tmp_path, wf_fetchngs, wf_rnaseq):
    """Write a minimal config YAML to a temp file and return its path."""
    data = {
        "config_version": "0.0.1",
        "workflows": {
            wf_fetchngs.id: {
                "name": wf_fetchngs.name,
                "version": wf_fetchngs.version,
                "url": wf_fetchngs.url,
            },
            wf_rnaseq.id: {
                "name": wf_rnaseq.name,
                "version": wf_rnaseq.version,
                "url": wf_rnaseq.url,
            },
        },
        "transitions": [{"source": wf_fetchngs.id, "target": wf_rnaseq.id}],
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


# ---------------------------------------------------------------------------
# Runner fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_nextflow(monkeypatch):
    """Stub out all nextflow binary interactions."""
    from nf_meta.runner import utils as runner_utils

    runner_utils.check_nextflow.cache_clear()
    monkeypatch.setattr(
        "nf_meta.runner.workflow_run.check_nextflow", lambda: "nextflow"
    )
    monkeypatch.setattr(
        "nf_meta.runner.utils.shutil.which", lambda name: "/usr/bin/nextflow"
    )
