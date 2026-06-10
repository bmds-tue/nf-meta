from .base_editor import _REGISTRY
from .utils import EditorOptions


def run_editor(options: EditorOptions) -> None:
    """Resolve and launch an editor backend from the registry.

    Args:
        options: Editor runtime options including the editor name to look up.

    Raises:
        ValueError: If ``options.editor_name`` does not match any registered editor.
    """
    editor_cls = _REGISTRY.get(options.editor_name)
    if editor_cls is None:
        available = ", ".join(f"'{k}'" for k in _REGISTRY)
        raise ValueError(
            f"Unknown editor '{options.editor_name}'. Available: {available}"
        )
    editor_cls(options).start()
