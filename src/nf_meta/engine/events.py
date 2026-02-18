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
    pass


@dataclass(frozen=True)
class WorkflowAdded:
    workflow: Workflow


@dataclass(frozen=True)
class WorkflowRemoved:
    workflow: Workflow


@dataclass(frozen=True)
class WorkflowAltered:
    workflow: Workflow


@dataclass(frozen=True)
class TransitionAdded:
    transition: Transition


@dataclass(frozen=True)
class TransitionRemoved:
    transition: Transition


@dataclass(frozen=True)
class TransitionAltered:
    transition: Transition


# ------------------------------------------
# ----- COMMANDS: State Change Intents -----
# ------------------------------------------

class Command(Protocol):

    def apply(self, graph: GraphEventHandler) -> None: ...

    def undo(self, graph: GraphEventHandler) -> None: ...


@dataclass(frozen=True)
class AddWorkflow:
    workflow: Workflow

    def apply(self, g: GraphEventHandler):
        g.add_workflow(self.workflow)

    def undo(self, g: GraphEventHandler):
        g.remove_workflow(self.workflow)


@dataclass(frozen=True)
class RemoveWorkflow:
    # TODO: Think about removing single nodes (Command design) vs whole subgraphs (Memento / subgraph caching)
    workflow: Workflow

    def apply(self, g: GraphEventHandler):
        g.remove_workflow(self.workflow)

    def undo(self, g: GraphEventHandler):
        g.remove_workflow(self.workflow)


@dataclass(frozen=True)
class AddTransition:
    transition: Transition

    def apply(self, g: GraphEventHandler):
        g.add_transition(self.transition)

    def undo(self, g: GraphEventHandler):
        g.remove_workflow(self.transition)


@dataclass(frozen=True)
class RemoveTransition:
    transition: Transition

    def apply(self, g: GraphEventHandler):
        g.remove_workflow(self.transition)

    def undo(self, g: GraphEventHandler):
        g.add_transition(self.transition)


@dataclass(frozen=True)
class EditWorkflow:
    new_workflow: Workflow
    old_workflow: Workflow

    def __post_init__(self):
        if self.new_workflow.id != self.old_workflow.id:
            raise ValueError("Id must not be edited!")

    def apply(self, g: GraphEventHandler):
        g.update_workflow(self.new_workflow)

    def undo(self, g: GraphEventHandler):
        g.update_workflow(self.old_workflow)


@dataclass(frozen=True)
class EditTransition:
    new_transition: Transition
    old_transition: Transition

    def __post_init__(self):
        if self.new_transition.id != self.old_transition.id:
            raise ValueError("Id must not be edited!")

    def apply(self, g: GraphEventHandler):
        g.update_workflow(self.new_transition)

    def undo(self, g: GraphEventHandler):
        g.update_workflow(self.old_transition)
