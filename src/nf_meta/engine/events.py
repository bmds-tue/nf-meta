from typing import Protocol
from dataclasses import dataclass
from enum import StrEnum

from .models import Workflow, Transition


# TODO: Is this needed
class EventTypes(StrEnum):
    AddWorkflow = "add_workflow"
    RemoveWorkflow = "remove_workflow"
    AddTransition = "add_transition"
    RemoveTransition = "remove_transition"


# Event Handler
class GraphEventHandler(Protocol):

    def pop_events(self) -> tuple["Event"]: ...

    def get_workflow_by_id(self, id: str) -> Workflow: ...

    def get_transition_by_id(self, id: str) -> Transition: ...

    def add_workflow(self, w: Workflow) -> None: ...

    def remove_workflow(self, w: Workflow) -> None: ...

    def update_workflow(self, w: Workflow) -> None: ...

    def add_transition(self, t: Transition) -> None: ...

    def remove_transition(self, t: Transition) -> None: ...

    def update_transition(self, t: Transition) -> None: ...


# ------------------------------------------
# ----- Events: State Changes --------------
# ------------------------------------------

class Event(Protocol):
    def get_undo_cmd(self, graph: GraphEventHandler) -> "Command": ...


@dataclass(frozen=True)
class WorkflowAdded:
    workflow: Workflow

    def get_undo_cmd(self):
        return RemoveWorkflow(self.workflow)


@dataclass(frozen=True)
class WorkflowRemoved:
    workflow: Workflow

    def get_undo_cmd(self, graph: GraphEventHandler):
        return AddWorkflow(self.workflow)


@dataclass(frozen=True)
class WorkflowUpdated:
    workflow: Workflow

    def get_undo_cmd(self, graph: GraphEventHandler): ...


@dataclass(frozen=True)
class TransitionAdded:
    transition: Transition

    def get_undo_cmd(self, graph: GraphEventHandler):
        return RemoveTransition(self.transition)


@dataclass(frozen=True)
class TransitionRemoved:
    transition: Transition

    def get_undo_cmd(self, graph: GraphEventHandler):
        return AddTransition(self.transition)


@dataclass(frozen=True)
class TransitionUpdated:
    transition: Transition

    def get_undo_cmd(self, graph: GraphEventHandler): ...


# ------------------------------------------
# ----- COMMANDS: State Change Intents -----
# ------------------------------------------

class Command(Protocol):

    def apply(self, graph: GraphEventHandler) -> None: ...


@dataclass(frozen=True)
class Transaction:
    commands: list[Command]

    def apply(self, graph: GraphEventHandler):
        # TODO: Handle errors?
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
    transition_id: str

    def apply(self, g: GraphEventHandler):
        g.remove_workflow(self.transition_id)


@dataclass(frozen=True)
class EditWorkflow:
    new_workflow: Workflow
    old_workflow: Workflow

    # TODO: move __post_init__ validation to the graph logic
    # TODO: Is old_workflow really needed?
    # TODO: Can old_workflow be added at the time of calling apply()

    def __post_init__(self):
        if self.new_workflow.id != self.old_workflow.id:
            raise ValueError("Id must not be edited!")

    def apply(self, g: GraphEventHandler):
        g.update_workflow(self.new_workflow)


@dataclass(frozen=True)
class EditTransition:
    new_transition: Transition
    old_transition: Transition

    # Same as above:
    # TODO: move __post_init__ validation to the graph logic
    # TODO: Is old_transition really needed?
    # TODO: Can old_transition be added at the time of calling apply()

    def __post_init__(self):
        if self.new_transition.id != self.old_transition.id:
            raise ValueError("Id must not be edited!")

    def apply(self, g: GraphEventHandler):
        g.update_workflow(self.new_transition)
