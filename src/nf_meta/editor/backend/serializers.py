from nf_meta.engine.graph import MetaworkflowGraph
from nf_meta.engine.models import Workflow, Transition

from nf_meta.engine.events import Event

from pydantic import BaseModel


def Selection(BaseMode):
    edges: list[str]
    nodes: list[str]


def serialize_graph(g: MetaworkflowGraph) -> dict:
    cfg = g.to_config()
    d = {
        "nodes": cfg.workflows,
        "transitions": cfg.transitions
        # TODO: Add global extra config
    }
    return d


def serialize_events(events: tuple[Event]) -> list[dict]:
    return []
