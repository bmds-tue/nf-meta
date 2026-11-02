"""The configs recently opened or saved in the editor, kept per user on the
machine running it (where the paths are valid)."""

import json
import os
import tempfile
from pathlib import Path

MAX_RECENT = 8


def recent_file() -> Path:
    """`$XDG_STATE_HOME/nf-meta/recent-configs.json` (`~/.local/state/...` by default)."""
    state = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(state) / "nf-meta" / "recent-configs.json"


def recent_configs() -> list[str]:
    """The recent configs' absolute paths, most recent first; none if the list can't be read."""
    try:
        paths = json.loads(recent_file().read_text())
    except (OSError, ValueError):
        return []
    return [p for p in paths if isinstance(p, str)] if isinstance(paths, list) else []


def remember(config: Path | str) -> None:
    """Put `config` first in the list. URLs aren't kept; failures to write are ignored."""
    if "://" in str(config):
        return
    path = str(Path(config).expanduser().resolve())
    _write([path] + [p for p in recent_configs() if p != path])


def forget(config: str) -> None:
    """Remove `config` from the list."""
    _write([p for p in recent_configs() if p != config])


def _write(paths: list[str]) -> None:
    target = recent_file()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # written aside and moved into place, so two editors never leave a half-written file
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".recent-", suffix=".json")
    except OSError:
        return
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(paths[:MAX_RECENT], f, indent=1)
        Path(tmp).replace(target)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
