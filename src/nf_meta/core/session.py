from .errors import GraphValidationError, SessionCommandError
from .events import Command
from .history import History
from .graph import MetaworkflowGraph
from pathlib import Path


class EditorSession:
    def __init__(self, config_file=None):

        self.config_file: Path = config_file
        self.graph: MetaworkflowGraph = None
        self.history: History = None

    def load_config(self, config: Path):
        self.start(config)
        self.history = History()

    def start(self, config: Path):

        self.config_file = config
        if self.config_file:
            self.graph = MetaworkflowGraph.from_file(self.config_file)
        else:
            self.graph = MetaworkflowGraph()

        self.history = History()

    def handle_command(self, c: Command):
        try:
            _ = self.history.execute(c, self.graph)
        except (GraphValidationError, ValueError) as e:
            raise SessionCommandError.from_exception(e)

        if self.config_file:
            self.save_to_config(self.config_file)

    def handle_undo(self):
        _ = self.history.undo(self.graph)
        try:
            self.save_to_config(self.config_file)
        except ValueError as e:
            raise SessionCommandError.from_exception(e)

    def handle_redo(self):
        _ = self.history.redo(self.graph)
        try:
            self.save_to_config(self.config_file)
        except ValueError as e:
            raise SessionCommandError.from_exception(e)

    def save_to_config(self, config: Path | None):
        if not (config or self.config_file):
            raise ValueError("No config file to write to specified")

        if config:
            self.config_file = config

        self.graph.to_file(self.config_file)


SESSION = EditorSession()


def start_session(config: Path):
    global SESSION
    SESSION.start(config)
    return SESSION
