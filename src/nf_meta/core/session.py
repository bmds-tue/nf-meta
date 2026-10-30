from pathlib import Path

from .config import from_file, to_file
from .errors import (
    ConfigValidationError,
    Diagnostic,
    GraphValidationError,
    SessionCommandError,
)
from .events import Command
from .graph import MetaworkflowGraph
from .history import History


class EditorSession:
    """A graph being edited, with undo/redo history.

    With `write_on_change` (the default, used by the editor), every
    successful command, undo and redo writes the graph to `config_file`, if
    one is set.
    """

    def __init__(self, config_file: Path | str | None = None, *, write_on_change: bool = True):

        self.config_file = config_file
        self.write_on_change = write_on_change
        self.graph = MetaworkflowGraph()
        self.history = History()
        # Warnings found when the config was loaded
        self.warnings: list[Diagnostic] = []

    def load_config(self, config: Path | str):
        self.start(config)
        self.history = History()

    def start(self, config: Path | str | None):
        """Start editing `config` (a path or URL), or an empty graph. If the
        config can't be read or is invalid, the session stays as it was."""
        # Kept as given: a URL must not go through Path
        config_file = config or None
        graph = from_file(config_file, collect_errors=True) if config_file else MetaworkflowGraph()
        self.config_file = config_file
        self.graph = graph
        self.warnings = self.graph.warnings
        self.history = History()

    def execute(self, c: Command):
        """Apply `c` to the graph and record it for undo. Returns the events
        it emitted. On failure the graph is unchanged and the graph's own
        error (`ConfigValidationError`, `GraphValidationError`, `ValueError`)
        is raised."""
        events = self.history.execute(c, self.graph)
        self._write_if_enabled()
        return events

    def handle_command(self, c: Command):
        """`execute`, with errors raised as `SessionCommandError`."""
        try:
            return self.execute(c)
        except (GraphValidationError, ValueError, ConfigValidationError) as e:
            raise SessionCommandError.from_exception(e) from e

    def undo(self):
        """Undo the last command. Returns the events it emitted. Raises
        `ValueError` if there is nothing to undo."""
        if not self.history.undoable():
            raise ValueError("Nothing to undo")
        events = self.history.undo(self.graph)
        self._write_if_enabled()
        return events

    def redo(self):
        """Redo the last undone command. Returns the events it emitted.
        Raises `ValueError` if there is nothing to redo."""
        if not self.history.redoable():
            raise ValueError("Nothing to redo")
        events = self.history.redo(self.graph)
        self._write_if_enabled()
        return events

    def handle_undo(self):
        """`undo`, with errors raised as `SessionCommandError`."""
        try:
            return self.undo()
        except ValueError as e:
            raise SessionCommandError.from_exception(e) from e

    def handle_redo(self):
        """`redo`, with errors raised as `SessionCommandError`."""
        try:
            return self.redo()
        except ValueError as e:
            raise SessionCommandError.from_exception(e) from e

    def _write_if_enabled(self):
        if self.write_on_change and self.config_file:
            self.save_to_config(self.config_file)

    def save_to_config(self, config: Path | str | None):
        target = config or self.config_file
        if not target:
            raise ValueError("No config file to write to specified")

        self.config_file = target
        to_file(self.graph, target)


SESSION = EditorSession()


def start_session(config: Path):
    global SESSION
    SESSION.start(config)
    return SESSION
