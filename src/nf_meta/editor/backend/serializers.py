from nf_meta.engine.graph import MetaworkflowGraph
from nf_meta.engine.models import Workflow, Transition


def serialize_graph(g: MetaworkflowGraph) -> dict:
    cfg = g.to_config()
    d = {
        "nodes": cfg.workflows,
        "transitions": cfg.transitions
        # TODO: Add global extra config
    }
    return d
