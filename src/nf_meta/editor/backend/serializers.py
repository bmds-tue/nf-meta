import dataclasses

from pydantic import BaseModel

from nf_meta.core.config import current_warnings
from nf_meta.core.errors import Diagnostic
from nf_meta.core.events import Event
from nf_meta.core.graph import MetaworkflowGraph
from nf_meta.core.session import EditorSession


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
        "globals": session.graph.global_options,
        "inputs": serialize_inputs(session.graph),
        "warnings": serialize_warnings(session),
    }
    return d


def serialize_warnings(session: EditorSession) -> list[dict]:
    """The warnings about the session's config: its old forms (until it is
    written) and the ones that hold for the graph now (see
    `current_warnings`), each with its step (`None` for the whole config)."""
    return [
        {"workflow_id": d.workflow_id, "yaml_path": d.yaml_path, "message": d.message}
        for d in session.format_warnings + current_warnings(session.graph)
    ]


def serialize_inputs(graph: MetaworkflowGraph) -> list[dict]:
    """Every input of `graph`, declared or implicit, with its effective schema
    and default, the params it fills, how it is bound (`"bind"`,
    `"reference"`, or `None` when unused) and the problems found with it.
    Fetches the bound steps' param schemas (cached)."""
    inputs = graph.all_inputs()
    if not inputs:
        return []
    effective, schema_diagnostics = graph.effective_inputs()
    diagnostics = graph.input_diagnostics() + schema_diagnostics
    bindings = graph.input_bindings()

    result = []
    for name, definition in inputs.items():
        found = bindings.get(name, ())
        inp = effective.get(name)
        declared = name in graph.inputs
        result.append(
            {
                "name": name,
                "declared": declared,
                "definition": definition.model_dump_config() if declared else None,
                "bound_by": ("bind" if definition.bind else "reference") if found else None,
                "bindings": [str(b) for b in found],
                "schema": inp.schema if inp else {},
                "default": inp.default if inp else None,
                "description": inp.description if inp else "",
                "diagnostics": [
                    {"severity": d.severity.value, "message": d.message, "yaml_path": d.yaml_path}
                    for d in diagnostics
                    if _is_about(d, name, found)
                ],
            }
        )
    return result


def _is_about(d: Diagnostic, name: str, bindings) -> bool:
    path = d.yaml_path or ""
    if path == f"inputs.{name}" or path.startswith(f"inputs.{name}."):
        return True
    return path in {f"steps.{b.step_id}.params.{b.param}" for b in bindings}


def _serialize_event(event) -> dict:
    result: dict = {"type": type(event).__name__}
    for field in dataclasses.fields(event):
        value = getattr(event, field.name)
        if hasattr(value, "model_dump_display"):
            result[field.name] = value.model_dump_display()
        elif hasattr(value, "model_dump_config"):
            result[field.name] = value.model_dump_config()
        elif isinstance(value, BaseModel):
            result[field.name] = value.model_dump()
        else:
            result[field.name] = value
    return result


def serialize_events(events: tuple[Event, ...]) -> list[dict]:
    return [_serialize_event(e) for e in events]
