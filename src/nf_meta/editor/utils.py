from dataclasses import dataclass
from typing import Optional


@dataclass
class EditorOptions:
    """Runtime options that control how a metapipeline editor is launched.

    Attributes:
        editor_name: Name of the editor backend to use. Must match a key
            registered in ``base_editor._REGISTRY``.
        host: Hostname or IP address the editor server binds to. Only used
            by server-based editors such as the browser editor.
        port: Port the editor server listens on. When ``None``, a free port
            is chosen automatically.
    """

    editor_name: str = "browser"
    host: str = "127.0.0.1"
    port: Optional[int] = None
