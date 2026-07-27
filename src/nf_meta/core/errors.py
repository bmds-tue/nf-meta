from .models import Reference, WorkflowReference, WorkflowType
from .line_linting import locate_field
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

import click
import yaml
from pydantic import ValidationError


class GraphValidationError(Exception):
    pass


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Diagnostic:
    workflow_id: str | None
    field: str
    message: str
    severity: Severity


@dataclass
class DynamicValidationError(Exception):
    errors: list[Diagnostic]


def diagnostics_from_pydantic_error(
    e: ValidationError, workflow_id: str
) -> list[Diagnostic]:
    """Adapt a tier-0/1 pydantic.ValidationError into the tier-2 Diagnostic vocabulary.

    workflow_id is taken explicitly since a ValidationError carries no reference
    to the (failed-to-construct) instance. For errors against a single, already
    known workflow (e.g. round-trip single-node validation) — not for a whole
    MetaworkflowConfig, see diagnostics_from_config_validation_error for that.
    """
    return [
        Diagnostic(
            workflow_id=workflow_id,
            field=".".join(str(loc) for loc in err["loc"]),
            message=err["msg"],
            severity=Severity.ERROR,
        )
        for err in e.errors()
    ]


_WORKFLOW_TYPE_DISCRIMINATORS = {t.value for t in WorkflowType}


def diagnostics_from_config_validation_error(
    e: ValidationError, raw_text: str
) -> list[Diagnostic]:
    """Adapt a whole-MetaworkflowConfig ValidationError into Diagnostics.

    Pydantic's error `loc` for a workflow field looks like
    ("workflows", 3, "nf-pipeline", "name") — the "3" is a list index, not the
    workflow's real id, because MetaworkflowConfig.normalize_dict_to_list
    converts the dict-format `workflows:` mapping into a list before
    validation. Dict iteration order is preserved from yaml.safe_load, so the
    Nth list item corresponds exactly to the Nth key of the original
    `workflows:` mapping — recovered here by re-parsing raw_text.

    Only the dict-format `workflows:` case is resolved to a real workflow_id
    and position-lookup-ready field. Anything else (top-level errors,
    `transitions`, legacy list-format `workflows`) falls back to a plain
    dotted-loc field with workflow_id=None — no crash, just no attributable
    workflow/position.
    """
    try:
        raw = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError:
        raw = {}
    raw_workflows = raw.get("workflows") if isinstance(raw, dict) else None
    index_to_key: dict[int, str] | None = None
    if isinstance(raw_workflows, dict):
        index_to_key = dict(enumerate(raw_workflows.keys()))

    diagnostics = []
    for err in e.errors():
        loc = err["loc"]
        workflow_id: str | None = None
        field_loc = loc

        if (
            index_to_key is not None
            and len(loc) >= 2
            and loc[0] == "workflows"
            and isinstance(loc[1], int)
            and loc[1] in index_to_key
        ):
            workflow_id = index_to_key[loc[1]]
            field_loc = loc[2:]
            if field_loc and str(field_loc[0]) in _WORKFLOW_TYPE_DISCRIMINATORS:
                field_loc = field_loc[1:]

        field = ".".join(str(x) for x in field_loc) or err.get("type", "")
        diagnostics.append(
            Diagnostic(
                workflow_id=workflow_id,
                field=field,
                message=err["msg"],
                severity=Severity.ERROR,
            )
        )
    return diagnostics


def diagnostics_from_reference_errors(e: "WorkflowReferenceErrors") -> list[Diagnostic]:
    """Adapt cross-workflow reference errors into Diagnostics, using the actual
    param name (source_key) for field granularity when available."""
    diagnostics = []
    for ref_err in e.errors:
        ref = ref_err.reference
        field = (
            f"params.{ref.source_key}" if isinstance(ref, WorkflowReference) else "params"
        )
        diagnostics.append(
            Diagnostic(
                workflow_id=ref.source_wf_id,
                field=field,
                message=ref_err.message,
                severity=Severity.ERROR,
            )
        )
    return diagnostics


@dataclass
class WorkflowReferenceError(GraphValidationError):
    reference: Reference
    message: str


@dataclass
class WorkflowReferenceErrors(GraphValidationError):
    errors: list[WorkflowReferenceError]


@dataclass
class SessionCommandError(Exception):
    @dataclass
    class FieldError:
        workflow_id: Optional[str]
        field: str
        message: str

    field_errors: list[FieldError]
    graph_errors: list[str]

    @classmethod
    def from_exception(
        cls,
        e: WorkflowReferenceError
        | WorkflowReferenceErrors
        | GraphValidationError
        | ValueError
        | DynamicValidationError,
    ):
        if isinstance(e, WorkflowReferenceError):
            e = WorkflowReferenceErrors([e])
        if isinstance(e, WorkflowReferenceErrors):
            return cls(
                field_errors=[
                    cls.FieldError(
                        workflow_id=ref_error.reference.source_wf_id,
                        field="params",  # TODO: For now ok. Think about more finegrained errors for Workflow output/input references
                        message=ref_error.message,
                    )
                    for ref_error in e.errors
                ],
                graph_errors=[],
            )
        if isinstance(e, DynamicValidationError):
            return cls.from_diagnostics(e.errors)
        return cls(field_errors=[], graph_errors=[str(e)])

    @classmethod
    def from_diagnostics(cls, diagnostics: list[Diagnostic]) -> "SessionCommandError":
        return cls(
            field_errors=[
                cls.FieldError(
                    workflow_id=d.workflow_id, field=d.field, message=d.message
                )
                for d in diagnostics
                if d.severity == Severity.ERROR
            ],
            graph_errors=[],
        )

    def to_dict(self):
        return {
            "field_errors": [
                {"workflow_id": e.workflow_id, "field": e.field, "message": e.message}
                for e in self.field_errors
            ],
            "graph_errors": self.graph_errors,
        }


def format_errors_for_cli(
    e: WorkflowReferenceError
    | WorkflowReferenceErrors
    | GraphValidationError
    | ValidationError
    | DynamicValidationError,
    source_text: str | None = None,
    filename: str = "",
) -> str:
    """Render any of the CLI-facing validation exceptions in one consistent,
    compiler-style format: "<file>:<line>:<col>: <severity>: [<tag>] <message>",
    column-aligned across every line. Lines with no resolvable position (no
    source_text given, no workflow_id, or the field just isn't found in the
    text) fall back to a bare filename prefix instead of crashing.
    """
    diagnostics: list[Diagnostic] = []
    graph_messages: list[str] = []

    if isinstance(e, WorkflowReferenceError):
        e = WorkflowReferenceErrors([e])
    if isinstance(e, WorkflowReferenceErrors):
        diagnostics = diagnostics_from_reference_errors(e)
    elif isinstance(e, DynamicValidationError):
        diagnostics = e.errors
    elif isinstance(e, ValidationError):
        if source_text is not None:
            diagnostics = diagnostics_from_config_validation_error(e, source_text)
        else:
            diagnostics = [
                Diagnostic(
                    workflow_id=None,
                    field=".".join(str(loc) for loc in err["loc"]),
                    message=err["msg"],
                    severity=Severity.ERROR,
                )
                for err in e.errors()
            ]
    elif isinstance(e, GraphValidationError):
        graph_messages = [str(e)]

    located: list[tuple[str, Diagnostic]] = []
    for d in diagnostics:
        position = None
        if source_text is not None and d.workflow_id is not None:
            position = locate_field(source_text, f"workflows.{d.workflow_id}.{d.field}")
        location = (
            f"{filename}:{position.line}:{position.column}"
            if position is not None
            else filename
        )
        located.append((location, d))

    # Graph-level messages (e.g. a cycle) have no workflow/field to attribute
    # them to, but still get a bare-filename location so they participate in
    # the same column alignment as every other line.
    location_lengths = [len(location) for location, _ in located]
    if graph_messages:
        location_lengths.append(len(filename))
    width = max(location_lengths, default=0)

    lines = []
    for location, d in located:
        tag = f"{d.workflow_id}/{d.field}" if d.workflow_id is not None else d.field
        severity_color = "red" if d.severity == Severity.ERROR else "yellow"
        severity_label = click.style(d.severity.value, fg=severity_color, bold=True)
        lines.append(f"{location.ljust(width)}: {severity_label}: [{tag}] {d.message}")

    for message in graph_messages:
        severity_label = click.style("error", fg="red", bold=True)
        lines.append(f"{filename.ljust(width)}: {severity_label}: {message}")

    if not lines:
        return ""

    header = click.style("Validation failed:", fg="red", bold=True)
    body = "\n".join(f" {line}" for line in lines)
    return f"{header}\n{body}"
