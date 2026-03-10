from .events import Command
from .history import History
from .graph import MetaworkflowGraph
from .models import Workflow, Transition, GlobalOptions, MetaworkflowConfig
from pathlib import Path


class EditorSession:

    def __init__(self, config_file=None):

        self.config_file: Path = config_file
        self.graph: MetaworkflowGraph = None
        self.history: History = None

    def load_config(self, config: Path):
        self.start(config)

    def start(self, config: Path):

        self.config_file = config
        if self.config_file:
            self.graph = MetaworkflowGraph.from_file(self.config_file)
        else:
            self.graph = MetaworkflowGraph()

        self.history = History()

    def handle_command(self, c: Command):
        events = self.history.execute(c, self.graph)

    def handle_undo(self):
        events = self.history.undo(self.graph)

    def handle_redo(self):
        events = self.history.redo(self.graph)

    def save_to_config(self, config: Path|None):
        if not (config or self.config):
            raise ValueError("No config file to write to specified")

        if config:
            self.config_file = config

        self.graph.to_file(self.config_file)


SESSION = EditorSession()


def start_session(config: Path):
    global SESSION
    SESSION.start(config)
    return SESSION
