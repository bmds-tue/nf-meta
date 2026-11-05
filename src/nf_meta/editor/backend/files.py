"""Folder listings for the editor's open and save dialogs.

They show the file system of the machine running `nf-meta editor`, which is
not the browser's machine when the editor is reached over SSH.
"""

from pathlib import Path

CONFIG_SUFFIXES = (".yaml", ".yml")


def list_folder(path: str | None, start: Path, *, all_files: bool = False) -> dict:
    """The folders and config files (`.yaml`/`.yml`, or every file with
    `all_files`) in the folder `path`, without hidden entries. A relative
    `path` is taken from the current directory; a file's own folder is listed
    for a file; no `path` lists `start`.

    Returns `{"path", "parent", "entries"}` with absolute paths; `parent` is
    `None` at the root, entries are folders first, then by name. Raises
    `FileNotFoundError` for a folder that doesn't exist and
    `PermissionError` for one that can't be read.
    """
    folder = Path(path).expanduser() if path else start
    if not folder.is_absolute():
        folder = Path.cwd() / folder
    folder = folder.resolve()
    if folder.is_file():
        folder = folder.parent
    if not folder.is_dir():
        raise FileNotFoundError(str(folder))

    entries = []
    for child in folder.iterdir():
        if child.name.startswith("."):
            continue
        try:
            is_dir = child.is_dir()
        except OSError:
            continue  # e.g. a broken link
        if is_dir:
            entries.append({"name": child.name, "path": str(child), "kind": "folder"})
        elif all_files or child.suffix.lower() in CONFIG_SUFFIXES:
            entries.append({"name": child.name, "path": str(child), "kind": "file"})
    entries.sort(key=lambda e: (e["kind"] != "folder", e["name"].casefold()))
    return {
        "path": str(folder),
        "parent": str(folder.parent) if folder.parent != folder else None,
        "entries": entries,
    }
