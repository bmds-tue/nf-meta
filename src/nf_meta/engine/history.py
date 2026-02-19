from .events import GraphEventHandler, Event, Command, Transaction


class History:
    def __init__(self):
        self.undo_stack: list[tuple[Event]] = []
        self.redo_stack: list[tuple[Event]] = []

    def execute(self, command: Command, graph: GraphEventHandler) -> tuple[Event]:
        command.apply(graph)
        events = graph.pop_events()
        self.undo_stack.append(events)
        self.redo_stack.clear()
        return events

    def _get_inverse_command(self, events: tuple[Event]) -> Command:
        commands = []
        for event in reversed(events):
            commands.append(event.get_undo_cmd())
        return Transaction(commands)

    def undo(self, graph: GraphEventHandler) -> tuple[Event]:
        events = self.undo_stack.pop()
        undo = self._get_inverse_command(events)
        undo.apply()
        new_events = graph.pop_events()
        self.redo_stack.append(new_events)
        return new_events

    def redo(self, graph: GraphEventHandler) -> tuple[Event]:
        events = self.redo_stack.pop()
        redo = self._get_inverse_command(events)
        redo.apply()
        new_events = graph.pop_events()
        self.undo_stack.append(new_events)
        return new_events
