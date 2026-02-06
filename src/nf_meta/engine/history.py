from .events import Command
from .graph import MetaworkflowGraph


class History:
    def __init__(self):
        self.undo_stack: list[Command] = []
        self.redo_stack: list[Command] = []

    def execute(self, command: Command, graph: MetaworkflowGraph):
        command.apply(graph)
        self.undo_stack.append(command)
        self.redo_stack.clear()

    def undo(self, graph: MetaworkflowGraph):
        cmd = self.undo_stack.pop()
        cmd.undo(graph)
        self.redo_stack.append(cmd)

    def redo(self, graph: MetaworkflowGraph):
        cmd = self.redo_stack.pop()
        cmd.apply(graph)
        self.undo_stack.append(cmd)
