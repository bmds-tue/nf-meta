import logging
from importlib.metadata import entry_points

from .python_runner import SimplePythonRunner
from .cascade_runner import NfCascadeRunner
from .errors import NfMetaRunnerError
from .runner import run_metapipeline
from .base_runner import BaseRunner, _REGISTRY
from .utils import RunOptions, check_nextflow, check_nextflow_version


logger = logging.getLogger(__name__)


def get_registered_runners() -> list[str]:
    """Return the names of all runner backends registered at import time."""
    return list(_REGISTRY.keys())


def _load_runner_plugins() -> None:
    """Discover and load external runner backends via entry points.

    Third-party packages advertise runners under the ``nf_meta.runners``
    entry-point group. Loading the entry point executes the module, which
    triggers ``BaseRunner.__init_subclass__`` and adds the runner to
    ``_REGISTRY`` automatically.

    Example ``pyproject.toml`` for a plugin package::

        [project.entry-points."nf_meta.runners"]
        my-runner = "my_package.runner:MyRunner"
    """
    for ep in entry_points(group="nf_meta.runners"):
        try:
            ep.load()
            logger.debug("Loaded runner plugin: %s", ep.name)
        except Exception as exc:
            logger.warning("Failed to load runner plugin '%s': %s", ep.name, exc)


_load_runner_plugins()
