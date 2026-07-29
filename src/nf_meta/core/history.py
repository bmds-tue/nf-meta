from .events import GraphEventHandler, Event, Command, Transaction


class History:
    def __init__(self):
        self.undo_stack: list[tuple[Event]] = []
        self.redo_stack: list[tuple[Event]] = []

    def undoable(self):
        return len(self.undo_stack) > 0
    
    def redoable(self):
        return len(self.redo_stack) > 0

    def execute(self, command: Command, graph: GraphEventHandler) -> tuple[Event]:
        try:
            command.apply(graph)
        except Exception as e:
            # attempt rollback
            events = graph.pop_events()
            inverse = self._get_inverse_command(events)

            # TODO: Logging!!
            print(f"[!] Error Caught while running {command}")
            print(f"... {e}")
            print(f"... Attempting to undo the completed events: {events}")
            inverse.apply(graph)

            # Clear emitted events
            _ = graph.pop_events()
            raise e

        events = graph.pop_events()
        self.undo_stack.append(events)
        self.redo_stack.clear()
        return events

    def _get_inverse_command(self, events: tuple[Event]) -> Command:
        commands = []
        for event in reversed(events):
            commands.append(event.get_undo_cmd())
        return Transaction(tuple(commands))

    def undo(self, graph: GraphEventHandler) -> tuple[Event]:
        events = self.undo_stack.pop()
        undo_cmd = self._get_inverse_command(events)
        try:
            undo_cmd.apply(graph)
        except Exception as e:
            partial = graph.pop_events()
            self._get_inverse_command(partial).apply(graph)
            _ = graph.pop_events()
            self.undo_stack.append(events)  # restore — undo didn't complete
            raise e
        new_events = graph.pop_events()
        self.redo_stack.append(new_events)
        return new_events

    def redo(self, graph: GraphEventHandler) -> tuple[Event]:
        events = self.redo_stack.pop()
        redo_cmd = self._get_inverse_command(events)
        try:
            redo_cmd.apply(graph)
        except Exception as e:
            partial = graph.pop_events()
            self._get_inverse_command(partial).apply(graph)
            _ = graph.pop_events()
            self.redo_stack.append(events)  # restore — redo didn't complete
            raise e
        new_events = graph.pop_events()
        self.undo_stack.append(new_events)
        return new_events
