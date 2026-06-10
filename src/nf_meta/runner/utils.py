import functools
import logging
import re
import shutil
import subprocess

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .errors import NfMetaRunnerError


logger = logging.getLogger(__name__)


@dataclass
class RunOptions:
    """Runtime options that control how a metapipeline run is executed.

    Constructed from CLI arguments and passed to the runner. All fields have
    sensible defaults so the dataclass can be instantiated without arguments
    for programmatic use.

    Attributes:
        runner_name: Name of the runner backend to use. Must match a key
            registered in ``base_runner._REGISTRY``.
        tempdir: Directory used for all per-workflow working directories,
            resolved-param cache files, and Nextflow work directories.
            Created automatically if it does not exist.
        verbose: Enables verbose logging output.
        output_lines: Number of most-recent output lines shown in the live
            scrolling panel while a workflow step is running. Only has an
            effect in the Python runner.
        start: Workflow ID at which execution begins. Workflows topologically
            upstream of this node are skipped. Cross-boundary parameter
            references must be satisfiable from previously cached runs.
            ``None`` means start from all source nodes.
        target: Workflow ID at which execution ends. Workflows topologically
            downstream of this node are skipped. ``None`` means run until
            all sink nodes.
        nf_profile: Nextflow profile name (or comma-separated list of names)
            appended globally to every workflow invocation, taking precedence
            over per-workflow profile settings. Whitespace is stripped before
            passing to Nextflow.
        stub: When ``True``, passes ``-stub`` to every Nextflow invocation so
            that only the ``stub`` block of each process is executed. Useful
            for validating pipeline structure without real computation.
        resume: When ``True``, skips any workflow step whose working directory
            already contains a successful result (``OUT.txt`` present,
            ``ERROR.txt`` absent) and passes ``-resume`` to Nextflow for
            workflow-level checkpoint resumption.
    """

    runner_name: str = "python"
    tempdir: Path = Path(".nf-meta-cache")
    verbose: bool = False
    output_lines: int = 20
    start: Optional[str] = None
    target: Optional[str] = None
    nf_profile: Optional[str] = None
    stub: bool = False
    resume: bool = False


@functools.cache
def check_nextflow():
    """Checks for a local installation of nextflow.

    Raises:
        NfMetaRunnerError when nextflow is not installed

    Returns:
        The nextflow executable string
    """
    executable = shutil.which("nextflow")
    if executable is None:
        raise NfMetaRunnerError("No nextflow installation found")
    return executable


def get_installed_nextflow_version():
    """Call `nextflow -version` and parse the version into a comparable tuple.

    Returns:
        A tuple of (major, minor, patch, is_edge), e.g. (25, 10, 4, 0).
        The fourth element is 1 if the version string contains '-edge', else 0.
    """
    cmd = ["nextflow", "-version"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        raise NfMetaRunnerError(
            "Nextflow is not installed or not found on PATH. "
            "Please install Nextflow: https://www.nextflow.io/docs/latest/install.html"
        )
    except subprocess.TimeoutExpired:
        raise NfMetaRunnerError("Timed out waiting for `nextflow -version` to respond.")
    except OSError as e:
        raise NfMetaRunnerError(f"Failed to invoke Nextflow: {e}")

    output = result.stdout or result.stderr
    if result.returncode != 0:
        raise NfMetaRunnerError(
            f"`nextflow -version` exited with code {result.returncode}.\n{output.strip()}"
        )

    # Match e.g. "version 25.10.4 build 11173"
    #         or "version 25.10.4-edge build 11173"
    match = re.search(r"version\s+(\d+)\.(\d+)\.(\d+)(-edge)?", output)
    if not match:
        raise NfMetaRunnerError(
            f"Could not parse Nextflow version from output:\n{output.strip()}"
        )

    major, minor, patch, edge_flag = match.groups()
    is_edge = 1 if edge_flag else 0

    return (int(major), int(minor), int(patch), is_edge)


def check_nextflow_version(required_version: tuple[int, int, int, int]) -> bool:
    """Validate the installed Nextflow version against a required version.

    Args:
        required_version: A version tuple of (major, minor, patch, is_edge).

    Raises:
        NfMetaRunnerError: If the major version does not match, or if Nextflow
            cannot be executed or parsed.

    Returns:
        True if the installed version is compatible with the required version.
    """
    installed_version = get_installed_nextflow_version()

    for i, (inst, req) in enumerate(zip(installed_version, required_version)):
        if inst == req:
            continue

        required_str = ".".join([str(e) for e in required_version])
        installed_str = ".".join([str(e) for e in installed_version])
        msg = f"Nextflow version mismatch. Required from config: '{required_str}', Installed: '{installed_str}'."
        if i == 0:
            raise NfMetaRunnerError(msg)
        else:
            logger.warning(msg)
        break

    return True
