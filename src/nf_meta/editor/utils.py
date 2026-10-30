from dataclasses import dataclass


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
        use_redirect_file: Open the editor's link in the browser through a
            local file readable only by the user, so the link's token doesn't
            show in process listings. Turn off when the browser runs on another
            machine (VS Code Remote, dev containers), where that file doesn't exist.
    """

    editor_name: str = "browser"
    host: str = "127.0.0.1"
    port: int | None = None
    use_redirect_file: bool = True
