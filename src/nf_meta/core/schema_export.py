"""
Assembles the JSON Schema for the nf-meta representation from the core
Pydantic models (NfPipeline, NfModule, GlobalOptions) wrapped in a outer
layer describing the YAML file as a whole.
"""

from pydantic import TypeAdapter

from .models import GlobalOptions, Workflow

_FROM_FIELD_SCHEMA = {
    "anyOf": [
        {"type": "string"},
        {"type": "array", "items": {"type": "string"}},
    ],
    "description": (
        "Workflow id(s) this workflow directly depends on (its predecessors) "
        "-- a single id, or a list of ids."
    ),
}


def _patch_from_field(defs: dict) -> None:
    """Add the `from:` shorthand to each concrete workflow type's schema, and
    remove `id` -- the one place the file format and the construction-time
    models genuinely diverge: `validated_graph` pops `from` before constructing
    a Workflow (neither NfPipeline nor NfModule has that field), and injects
    `id` from the surrounding mapping key rather than reading it as a nested
    field, so users never write either of these where the schema would
    otherwise put them.
    """
    for def_schema in defs.values():
        properties = def_schema.get("properties")
        if properties is None:
            continue
        properties["from"] = _FROM_FIELD_SCHEMA
        properties.pop("id", None)
        if "required" in def_schema:
            def_schema["required"] = [r for r in def_schema["required"] if r != "id"]


def generate_schema() -> dict:
    """Build the full JSON Schema document for metapipeline.yaml."""
    workflow_schema = TypeAdapter(Workflow).json_schema()
    # Hoist $defs to the document root -- the oneOf/discriminator's $ref
    # pointers ("#/$defs/NfPipeline") resolve against the schema *document's*
    # root, not wherever this sub-schema happens to be nested, so $defs must
    # live at the top level once workflow_schema is embedded inside a bigger
    # wrapper document below.
    defs = workflow_schema.pop("$defs", {})
    _patch_from_field(defs)

    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "nf-meta metapipeline configuration",
        "$defs": defs,
        "type": "object",
        "required": ["config_version", "workflows"],
        "properties": {
            "config_version": {"type": "string"},
            "workflows": {
                "type": "object",
                "additionalProperties": workflow_schema,
            },
            "globals": GlobalOptions.model_json_schema(),
        },
    }
