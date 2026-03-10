from pathlib import Path
from nf_meta.engine.session import EditorSession
from nf_meta.engine.models import Workflow, Transition

from nf_meta.engine.events import Event

from pydantic import BaseModel


class Selection(BaseModel):
    edges: list[str]
    nodes: list[str]


def serialize_state(session: EditorSession) -> dict:
    cfg = session.graph.to_config()
    d = {
        "filename": session.config_file or "",
        "undoable": session.history.undoable(),
        "redoable": session.history.redoable(),
        "nodes": cfg.workflows,
        "transitions": cfg.transitions,
        "globals": cfg.globals
    }
    return d


def serialize_events(events: tuple[Event]) -> list[dict]:
    return []
