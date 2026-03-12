from pathlib import Path
from nf_meta.engine.session import EditorSession
from nf_meta.engine.models import Workflow, Transition

from nf_meta.engine.events import Event

from pydantic import BaseModel


class Selection(BaseModel):
    edges: list[str]
    nodes: list[str]


def serialize_state(session: EditorSession) -> dict:
    d = {
        "filename": session.config_file or "",
        "undoable": session.history.undoable(),
        "redoable": session.history.redoable(),
        "nodes": session.graph.get_workflows(),
        "transitions": session.graph.get_transitions(),
        "globals": session.graph.global_options
    }
    return d


def serialize_events(events: tuple[Event]) -> list[dict]:
    return []
