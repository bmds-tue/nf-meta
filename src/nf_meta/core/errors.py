from .models import Reference, WorkflowReference
from .line_linting import locate_field
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Optional

import click
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
class ConfigValidationError(Exception):
    """A workflow/config-definition-level validation failure — whether from
    tier-0/1 (pydantic construction) or tier-2 (network-backed) checks. Every
    consumer treats both tiers identically, so they share one exception type."""

    errors: list[Diagnostic]
    graph_messages: list[str] = field(default_factory=list)


def diagnostics_from_pydantic_error(
    e: ValidationError, workflow_id: str | None
) -> list[Diagnostic]:
    """Adapt a tier-0/1 pydantic.ValidationError into the Diagnostic vocabulary.

    workflow_id is taken explicitly since a ValidationError carries no reference
    to the (failed-to-construct) instance — the caller (e.g. graph.py's
    construct_workflow, constructing one workflow at a time) already knows which
    workflow this is.
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
        | ConfigValidationError,
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
        if isinstance(e, ConfigValidationError):
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
    | ConfigValidationError,
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
    elif isinstance(e, ConfigValidationError):
        diagnostics = e.errors
        graph_messages = e.graph_messages
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
