from .history import History
from .graph import MetaworkflowGraph
from .models import Workflow, Transition, WorkflowOptions, MetaworkflowConfig
from pathlib import Path

SESSION = None

class Session:

    def __init__(self, config_file=None):

        self.config_file: Path = config_file
        self.graph: MetaworkflowGraph = None

        # Undo / Redo History
        self.history: History = None
        # TODO

    def load_config(self, config: Path):
        # TODO
        pass


def start_session(config: Path):
    global SESSION
    SESSION = Session(config_file=config)
