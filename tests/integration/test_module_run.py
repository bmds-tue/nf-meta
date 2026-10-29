"""The module engine's command resolves real modules in the Nextflow module
registry (plans/ISSUES.md I2, I3).

Needs Nextflow >= 26.04 and network. The modules are run without inputs, so
the run fails on missing params -- after the module was resolved and
installed, which is what is checked.

Run with ``uv run pytest -m nextflow``.
"""

import os
import shutil
import subprocess

import pytest
import requests

from nf_meta.core import registry
from nf_meta.core.models import NfModule
from nf_meta.runner.engines import engine_for
from nf_meta.runner.spec import build_step_spec
from nf_meta.runner.utils import get_installed_nextflow_version


def _registry_reachable() -> bool:
    try:
        return requests.head("https://registry.nextflow.io", timeout=10).status_code < 500
    except requests.exceptions.RequestException:
        return False


pytestmark = [
    pytest.mark.nextflow,
    pytest.mark.skipif(shutil.which("nextflow") is None, reason="nextflow not installed"),
]

# Taken at import, before conftest's autouse fixture stubs it out
_REAL_COMPONENTS = registry._get_nfcore_components_raw

UNRESOLVED = ("Invalid module reference", "Unable to install module", "No release information")


@pytest.fixture(scope="module", autouse=True)
def requirements():
    if get_installed_nextflow_version()[:2] < (26, 4):
        pytest.skip("nextflow module needs Nextflow >= 26.04")
    if not _registry_reachable():
        pytest.skip("Nextflow module registry not reachable")


@pytest.fixture(autouse=True)
def real_component_catalog(monkeypatch):
    """Undo conftest's offline stub: these tests need the real catalog."""
    monkeypatch.setattr(registry, "_get_nfcore_components_raw", _REAL_COMPONENTS)


@pytest.mark.parametrize(
    "name",
    [
        "nf-core/fastqc",
        "nf-core/samtools_stats",  # nested: nf-core/samtools/stats
        "nf-core/plastid_make_wiggle",  # underscore in the subtool: nf-core/plastid/make_wiggle
    ],
)
def test_module_command_resolves(name, tmp_path):
    version = registry.get_module_metadata(name)["version"]
    wf = NfModule(name=name, version=version)
    spec = build_step_spec(
        wf,
        None,
        state_dir=tmp_path / "state",
        launch_dir=tmp_path,
        nextflow_cache_dir=tmp_path / "cache",
        stub=True,
    )
    command = engine_for(spec.workflow_type).build(spec)
    command.write_files()

    proc = subprocess.run(
        command.argv,
        cwd=command.cwd,
        env={**os.environ, **command.env, "NXF_HOME": str(tmp_path / "nxf_home")},
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = proc.stdout + proc.stderr
    assert not any(marker in output for marker in UNRESOLVED), output
    assert (tmp_path / "modules").is_dir() or "required" in output.lower(), output
