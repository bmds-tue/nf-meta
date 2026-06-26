import dataclasses

from pydantic import BaseModel

from nf_meta.core.session import EditorSession
from nf_meta.core.events import Event


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


def _serialize_event(event) -> dict:
    result: dict = {"type": type(event).__name__}
    for field in dataclasses.fields(event):
        value = getattr(event, field.name)
        if hasattr(value, "model_dump_display"):
            result[field.name] = value.model_dump_display()
        elif isinstance(value, BaseModel):
            result[field.name] = value.model_dump()
        else:
            result[field.name] = value
    return result


def serialize_events(events: tuple[Event, ...]) -> list[dict]:
    return [_serialize_event(e) for e in events]
