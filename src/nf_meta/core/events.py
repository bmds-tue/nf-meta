from dataclasses import dataclass
from typing import Protocol

from .inputs import InputDefinition
from .models import GlobalOptions, Transition, Workflow


# Event Handler
# TODO: Test that Metaworkflow implements GraphEventHandler: isinstance(graph, GraphEventHandler)
class GraphEventHandler(Protocol):
    def pop_events(self) -> tuple["Event"]: ...

    def add_workflow(self, w: Workflow) -> None: ...

    def remove_workflow(self, wf_id: str) -> None: ...

    def update_workflow(self, w: Workflow) -> None: ...

    def add_transition(self, t: Transition) -> None: ...

    def remove_transition(self, source: str, target: str) -> None: ...

    def update_global_options(self, g: GlobalOptions) -> None: ...

    def add_input(self, name: str, definition: InputDefinition) -> None: ...

    def update_input(self, name: str, definition: InputDefinition) -> None: ...

    def remove_input(self, name: str) -> None: ...

    def deferred_validation(self): ...


# ------------------------------------------
# ----- Events: State Changes --------------
# ------------------------------------------


class Event(Protocol):
    def get_undo_cmd(self) -> "Command": ...


@dataclass(frozen=True)
class WorkflowAdded:
    workflow: Workflow

    def get_undo_cmd(self):
        return RemoveWorkflow(self.workflow.id)


@dataclass(frozen=True)
class WorkflowRemoved:
    workflow: Workflow

    def get_undo_cmd(self):
        return AddWorkflow(self.workflow)


@dataclass(frozen=True)
class WorkflowUpdated:
    new_workflow: Workflow
    old_workflow: Workflow

    def get_undo_cmd(self):
        return EditWorkflow(workflow=self.old_workflow)


@dataclass(frozen=True)
class TransitionAdded:
    transition: Transition

    def get_undo_cmd(self):
        return RemoveTransition(self.transition.source, self.transition.target)


@dataclass(frozen=True)
class TransitionRemoved:
    transition: Transition

    def get_undo_cmd(self):
        return AddTransition(self.transition)


@dataclass(frozen=True)
class GlobalOptionsUpdated:
    new_globals: GlobalOptions
    old_globals: GlobalOptions

    def get_undo_cmd(self):
        return UpdateGlobalOptions(globals=self.old_globals)


@dataclass(frozen=True)
class InputAdded:
    name: str
    definition: InputDefinition

    def get_undo_cmd(self):
        return RemoveInput(self.name)


@dataclass(frozen=True)
class InputRemoved:
    name: str
    definition: InputDefinition

    def get_undo_cmd(self):
        return AddInput(self.name, self.definition)


@dataclass(frozen=True)
class InputUpdated:
    name: str
    new_definition: InputDefinition
    old_definition: InputDefinition

    def get_undo_cmd(self):
        return UpdateInput(self.name, self.old_definition)


# ------------------------------------------
# ----- COMMANDS: State Change Intents -----
# ------------------------------------------


class Command(Protocol):
    def apply(self, graph: GraphEventHandler) -> None: ...


@dataclass(frozen=True)
class Transaction:
    commands: tuple[Command, ...]

    def apply(self, graph: GraphEventHandler):
        # TODO: Handle errors?
        with graph.deferred_validation():
            for cmd in self.commands:
                cmd.apply(graph)


@dataclass(frozen=True)
class AddWorkflow:
    workflow: Workflow

    def apply(self, g: GraphEventHandler):
        g.add_workflow(self.workflow)


@dataclass(frozen=True)
class RemoveWorkflow:
    # TODO: Think about removing single nodes (Command design) vs whole subgraphs (Memento / subgraph caching)
    workflow_id: str

    def apply(self, g: GraphEventHandler):
        g.remove_workflow(self.workflow_id)


@dataclass(frozen=True)
class AddTransition:
    transition: Transition

    def apply(self, g: GraphEventHandler):
        g.add_transition(self.transition)


@dataclass(frozen=True)
class RemoveTransition:
    source: str
    target: str

    def apply(self, g: GraphEventHandler):
        g.remove_transition(self.source, self.target)


@dataclass(frozen=True)
class EditWorkflow:
    workflow: Workflow

    def apply(self, g: GraphEventHandler):
        g.update_workflow(self.workflow)


@dataclass(frozen=True)
class UpdateGlobalOptions:
    globals: GlobalOptions

    def apply(self, g: GraphEventHandler):
        g.update_global_options(self.globals)


@dataclass(frozen=True)
class AddInput:
    name: str
    definition: InputDefinition

    def apply(self, g: GraphEventHandler):
        g.add_input(self.name, self.definition)


@dataclass(frozen=True)
class UpdateInput:
    name: str
    definition: InputDefinition

    def apply(self, g: GraphEventHandler):
        g.update_input(self.name, self.definition)


@dataclass(frozen=True)
class RemoveInput:
    name: str

    def apply(self, g: GraphEventHandler):
        g.remove_input(self.name)
