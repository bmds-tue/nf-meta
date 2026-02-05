from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel

from .graph import MetaworkflowGraph
from .models import Workflow, Transition


# TODO: Is this needed
class EventTypes(StrEnum):
    AddWorkflow = "add_workflow"
    RemoveWorkflow = "remove_workflow"
    AddTransition = "add_transition"
    RemoveTransition = "remove_transition"

# TODO: Is this needed
class Event(BaseModel):
    type: EventTypes
    payload: dict


class Command(ABC):

    @abstractmethod
    def apply(self, graph: MetaworkflowGraph):
        pass

    @abstractmethod
    def undo(self, graph: MetaworkflowGraph):
        pass


@dataclass(frozen=True)
class AddWorkflow(Command):
    workflow: Workflow

    def apply(self, g: MetaworkflowGraph):
        g.add_workflow(self.workflow)

    def undo(self, g: MetaworkflowGraph):
        g.remove_workflow(self.workflow)


@dataclass(frozen=True)
class RemoveWorkflow(Command):
    # TODO: Think about removing single nodes (Command design) vs whole subgraphs (Memento / subgraph caching)
    workflow: Workflow

    def apply(self, g: MetaworkflowGraph):
        g.remove_workflow(self.workflow)

    def undo(self, g: MetaworkflowGraph):
        g.remove_workflow(self.workflow)


@dataclass(frozen=True)
class AddTransition(Command):
    transition: Transition

    def apply(self, g: MetaworkflowGraph):
        g.add_transition(self.transition)

    def undo(self, g: MetaworkflowGraph):
        g.remove_workflow(self.transition)


@dataclass(frozen=True)
class RemoveTransition(Command):
    transition: Transition

    def apply(self, g: MetaworkflowGraph):
        g.remove_workflow(self.transition)

    def undo(self, g: MetaworkflowGraph):
        g.add_transition(self.transition)


@dataclass(frozen=True)
class EditWorkflow(Command):
    new_workflow: Workflow
    old_workflow: Workflow

    def __post_init__(self):
        if self.new_workflow.id != self.old_workflow.id:
            raise ValueError("Id must not be edited!")

    def apply(self, g: MetaworkflowGraph):
        g.update_workflow(self.new_workflow)

    def undo(self, g: MetaworkflowGraph):
        g.update_workflow(self.old_workflow)


@dataclass(frozen=True)
class EditTransition(Command):
    new_transition: Transition
    old_transition: Transition

    def __post_init__(self):
        if self.new_transition.id != self.old_transition.id:
            raise ValueError("Id must not be edited!")

    def apply(self, g: MetaworkflowGraph):
        g.update_workflow(self.new_transition)

    def undo(self, g: MetaworkflowGraph):
        g.update_workflow(self.old_transition)
