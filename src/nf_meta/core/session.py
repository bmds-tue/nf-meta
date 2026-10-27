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
    def __init__(self, config_file=None):

        self.config_file: Path = config_file
        self.graph: MetaworkflowGraph = None
        self.history: History = None
        # Warnings found when the config was loaded
        self.warnings: list[Diagnostic] = []

    def load_config(self, config: Path):
        self.start(config)
        self.history = History()

    def start(self, config: Path):

        self.config_file = config
        if self.config_file:
            self.graph = from_file(self.config_file, collect_errors=True)
        else:
            self.graph = MetaworkflowGraph()
        self.warnings = self.graph.warnings

        self.history = History()

    def handle_command(self, c: Command):
        try:
            events = self.history.execute(c, self.graph)
        except (GraphValidationError, ValueError, ConfigValidationError) as e:
            raise SessionCommandError.from_exception(e)

        if self.config_file:
            self.save_to_config(self.config_file)

        return events

    def handle_undo(self):
        events = self.history.undo(self.graph)
        try:
            self.save_to_config(self.config_file)
        except ValueError as e:
            raise SessionCommandError.from_exception(e)
        return events

    def handle_redo(self):
        events = self.history.redo(self.graph)
        try:
            self.save_to_config(self.config_file)
        except ValueError as e:
            raise SessionCommandError.from_exception(e)
        return events

    def save_to_config(self, config: Path | None):
        if not (config or self.config_file):
            raise ValueError("No config file to write to specified")

        if config:
            self.config_file = config

        to_file(self.graph, self.config_file)


SESSION = EditorSession()


def start_session(config: Path):
    global SESSION
    SESSION.start(config)
    return SESSION
