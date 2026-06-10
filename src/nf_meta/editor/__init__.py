import logging
from importlib.metadata import entry_points

from .base_editor import BaseEditor, _REGISTRY
from .browser_editor import BrowserEditor
from .utils import EditorOptions
from .editor import run_editor


logger = logging.getLogger(__name__)

__all__ = ["BaseEditor", "BrowserEditor", "EditorOptions", "run_editor", "get_registered_editors"]


def get_registered_editors() -> list[str]:
    """Return the names of all editor backends registered at import time."""
    return list(_REGISTRY.keys())


def _load_editor_plugins() -> None:
    """Discover and load external editor backends via entry points.

    Third-party packages advertise editors under the ``nf_meta.editors``
    entry-point group. Loading the entry point executes the module, which
    triggers ``BaseEditor.__init_subclass__`` and adds the editor to
    ``_REGISTRY`` automatically.

    Example ``pyproject.toml`` for a plugin package::

        [project.entry-points."nf_meta.editors"]
        my-editor = "my_package.editor:MyEditor"
    """
    for ep in entry_points(group="nf_meta.editors"):
        try:
            ep.load()
            logger.debug("Loaded editor plugin: %s", ep.name)
        except Exception as exc:
            logger.warning("Failed to load editor plugin '%s': %s", ep.name, exc)


_load_editor_plugins()