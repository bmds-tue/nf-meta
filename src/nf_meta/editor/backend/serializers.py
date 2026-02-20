import uuid

from typing import Optional

from nf_meta.engine.graph import MetaworkflowGraph
from nf_meta.engine.models import Workflow, Transition
from nf_meta.engine.events import Event

from pydantic import BaseModel, Field


def random_bytes():
    return str(uuid.uuid4())[:4]


class Position(BaseModel):
    x: int
    y: int


class Node(Workflow):
    id: Optional[str] = Field(default=None)
    position: Position

    @classmethod
    def from_workflow(cls, wf: Workflow) -> "Node":
        pos = Position(x=0, y=0)
        if wf.layout_coords is not None:
            pos = Position(x=wf.layout_coords[0], y=wf.layout_coords[1])
        obj = cls(position=pos,
                  **wf.model_dump_display())
        return obj
        

    def to_workflow(self) -> Workflow:
        if not self.id:
            name = self.data.get("name", "").split("/")[-1]
            version = self.data.get("version", "")
            self.id = f"{random_bytes()}-{name}-{version}"
        return Workflow(**self.model_dump())


class Edge(Transition):
    id: Optional[str]

    @classmethod
    def from_transition(cls, t: Transition) -> "Edge":
        tid = f"{t.source}->{t.target}"
        return cls(id=tid,
                   **t.model_dump_display())

    def to_transition(self) -> Transition:
        return Transition(**self.model_dump())


def serialize_graph(g: MetaworkflowGraph) -> dict:
    cfg = g.to_config()
    d = {
        "nodes": [Node.from_workflow(wf) for wf in cfg.workflows],
        "transitions": [Edge.from_transition(t) for t in cfg.transitions],
        # TODO: Add global extra config
    }
    return d
