import logging
import shutil
import subprocess
from typing import Optional

from .errors import NfMetaRunnerError


logger = logging.getLogger(__name__)


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


def get_installed_nextflow_version(self):
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


def check_nextflow_version(required_version: tuple[int,int,int,int]) -> bool:
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
        msg = (f"Nextflow version mismatch. Required from config: '{required_str}', Installed: '{installed_str}'.")
        if i == 0:
            raise NfMetaRunnerError(msg)
        else:
            logger.warning(msg)
        break

    return True
