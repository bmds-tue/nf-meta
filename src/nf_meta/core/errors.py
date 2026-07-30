from .line_linting import locate_field, TextPosition
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
    # Document-relative path of keys. Callers that know their diagnostics sit
    # inside a whole config (e.g. under `workflows.<id>.`/`globals.`) pass the
    # fully-qualified path
    yaml_path: str | None = None

    def __post_init__(self):
        if self.yaml_path is None:
            object.__setattr__(self, "yaml_path", self.field)


@dataclass
class ConfigValidationError(Exception):
    """A workflow/config-definition-level validation failure — whether from
    tier-0/1 (pydantic construction), tier-2 (network-backed) checks, or
    cross-workflow reference validation. Every consumer treats all of these
    identically, so they share one exception type."""

    errors: list[Diagnostic]
    graph_messages: list[str] = field(default_factory=list)


def diagnostics_from_pydantic_error(
    e: ValidationError, workflow_id: str | None, yaml_path_prefix: str = ""
) -> list[Diagnostic]:
    """Adapt a tier-0/1 pydantic.ValidationError into the Diagnostic vocabulary.

    workflow_id is taken explicitly since a ValidationError carries no reference
    to the (failed-to-construct) instance — the caller (e.g. graph.py's
    construct_workflow, constructing one workflow at a time) already knows which
    workflow this is. yaml_path_prefix is prepended to each field to produce
    the document-relative yaml_path -- pass e.g. "workflows.<id>." when this
    error belongs to a workflow embedded in a whole config; leave it empty
    (the default) for an isolated snippet, where the field is already
    document-relative.
    """
    return [
        Diagnostic(
            workflow_id=workflow_id,
            field=".".join(str(loc) for loc in err["loc"]),
            yaml_path=f"{yaml_path_prefix}{'.'.join(str(loc) for loc in err['loc'])}",
            message=err["msg"],
            severity=Severity.ERROR,
        )
        for err in e.errors()
    ]


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
        e: GraphValidationError | ValueError | ConfigValidationError,
    ):
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


@dataclass(frozen=True)
class PositionedDiagnostic:
    diagnostic: Diagnostic
    position: TextPosition | None


def collect_positioned_diagnostics(
    e: GraphValidationError | ConfigValidationError,
    source_text: str | None = None,
) -> tuple[list[PositionedDiagnostic], list[str]]:
    """Normalize any CLI-facing validation exception into positioned
    diagnostics + bare graph-level messages.

    Each diagnostic's position is resolved via its own yaml_path (already
    document-relative, set at creation time) -- no context about the
    document's shape is needed here.
    """
    diagnostics: list[Diagnostic] = []
    graph_messages: list[str] = []

    if isinstance(e, ConfigValidationError):
        diagnostics = e.errors
        graph_messages = e.graph_messages
    elif isinstance(e, GraphValidationError):
        graph_messages = [str(e)]

    positioned = []
    for d in diagnostics:
        position = None
        if source_text is not None:
            assert d.yaml_path is not None  # always set by __post_init__
            position = locate_field(source_text, d.yaml_path)
        positioned.append(PositionedDiagnostic(d, position))
    return positioned, graph_messages


def render_positioned_diagnostics(
    positioned: list[PositionedDiagnostic], graph_messages: list[str], filename: str
) -> str:
    """Render compiler-style, column-aligned CLI output from already-resolved
    diagnostics: "<file>:<line>:<col>: <severity>: [<tag>] <message>". Lines
    with no resolved position fall back to a bare filename prefix.
    """
    located: list[tuple[str, Diagnostic]] = [
        (
            f"{filename}:{pd.position.line}:{pd.position.column}"
            if pd.position is not None
            else filename,
            pd.diagnostic,
        )
        for pd in positioned
    ]

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


def format_errors_for_cli(
    e: GraphValidationError | ConfigValidationError,
    source_text: str | None = None,
    filename: str = "",
) -> str:
    """Render any of the CLI-facing validation exceptions in one consistent,
    compiler-style format. Convenience wrapper over
    collect_positioned_diagnostics + render_positioned_diagnostics.
    """
    positioned, graph_messages = collect_positioned_diagnostics(e, source_text)
    return render_positioned_diagnostics(positioned, graph_messages, filename)
