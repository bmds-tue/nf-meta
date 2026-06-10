from .python_runner import SimplePythonRunner
from .cascade_runner import NfCascadeRunner
from .errors import NfMetaRunnerError
from .runner import run_metapipeline
from .base_runner import BaseRunner, _REGISTRY
from .utils import RunOptions, check_nextflow, check_nextflow_version


def get_registered_runners() -> list[str]:
    """Return the names of all runner backends registered at import time."""
    return list(_REGISTRY.keys())
