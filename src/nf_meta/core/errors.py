from dataclasses import dataclass, field
from enum import StrEnum

import click
from pydantic import ValidationError

from .line_linting import TextPosition, locate_field


class GraphValidationError(Exception):
    """A structural problem with the graph itself: a cycle, an edge to a
    nonexistent node, or a malformed `workflows:`/`from:`/`transitions:`
    shape. Distinct from `ConfigValidationError`, which carries per-field
    `Diagnostic`s about individual workflow/globals content."""


class RemoteConfigWriteError(Exception):
    """A config loaded from a URL can't be written to; save it to a local file first."""


class Severity(StrEnum):
    """A `Diagnostic`'s severity: `ERROR` blocks (raises
    `ConfigValidationError`); `WARNING` is logged but doesn't stop
    construction."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Diagnostic:
    """One validation problem with a single field of a single workflow (or of
    `globals`, when `workflow_id` is `None`). The common vocabulary every
    validation tier (pydantic construction, dynamic/network checks,
    cross-workflow reference checks) reports through, so callers handle one
    shape regardless of where a problem originated."""

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
    """A workflow/config-definition-level validation failure, whether from
    tier-0/1 (pydantic construction), tier-2 (network-backed) checks, or
    cross-workflow reference validation. Every consumer treats all of these
    identically, so they share one exception type."""

    errors: list[Diagnostic]
    graph_messages: list[str] = field(default_factory=list)
    # Warnings found alongside the errors (only collected by the
    # collect-everything validation path).
    warnings: list[Diagnostic] = field(default_factory=list)


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
        workflow_id: str | None
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
        """The errors among `diagnostics`. Errors about an input (not about a
        step) get the input's yaml path as their field, e.g.
        `inputs.ids.bind`."""
        return cls(
            field_errors=[
                cls.FieldError(workflow_id=d.workflow_id, field=_field_for(d), message=d.message)
                for d in diagnostics
                if d.severity == Severity.ERROR
            ],
            graph_errors=[],
        )

    def to_dict(self):
        return {
            "field_errors": [
                {"workflow_id": e.workflow_id, "field": e.field, "message": e.message} for e in self.field_errors
            ],
            "graph_errors": self.graph_errors,
        }


def _field_for(d: Diagnostic) -> str:
    if d.workflow_id is None and d.yaml_path and d.yaml_path.split(".")[0] == "inputs":
        return d.yaml_path
    return d.field


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
        diagnostics = [*e.errors, *e.warnings]
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


# 256-colour orange: stands out from red errors more than yellow does
WARNING_COLOR = 208


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


_LABELS: dict[Severity, tuple[str, int | str]] = {
    Severity.ERROR: ("Error", "red"),
    Severity.WARNING: ("Warning", WARNING_COLOR),
}


def render_positioned_diagnostics(
    positioned: list[PositionedDiagnostic], graph_messages: list[str], filename: str
) -> str:
    """Render diagnostics as aligned lines, one per problem:
    "<Severity>  <line>:<col>  <config path>  <message>". Errors come first,
    then warnings, each in document order; the position is dimmed and left
    blank when unknown, and graph-level messages have no config path. The
    header names the file and counts errors and warnings ("Warnings in …:"
    when there are no errors).
    """

    def order(pd: PositionedDiagnostic):
        is_warning = pd.diagnostic.severity == Severity.WARNING
        position = (pd.position.line, pd.position.column) if pd.position else (0, 0)
        return (is_warning, position)

    rows: list[tuple[Severity, str, str, str]] = [
        (
            pd.diagnostic.severity,
            f"{pd.position.line}:{pd.position.column}" if pd.position else "",
            pd.diagnostic.yaml_path or pd.diagnostic.field,
            pd.diagnostic.message,
        )
        for pd in sorted(positioned, key=order)
    ]
    # Graph-level messages (e.g. a cycle) have no field to attribute them to
    rows[0:0] = [(Severity.ERROR, "", "", message) for message in graph_messages]
    if not rows:
        return ""

    width = max(len(position) for _, position, _, _ in rows)
    lines = []
    for severity, position, path, message in rows:
        text, color = _LABELS[severity]
        parts = [click.style(text.ljust(7), fg=color, bold=True)]
        if width:
            parts.append(click.style(position.ljust(width), dim=True))
        if path:
            parts.append(path)
        parts.append(message)
        lines.append("  ".join(parts))

    n_errors = sum(1 for severity, *_ in rows if severity == Severity.ERROR)
    n_warnings = len(rows) - n_errors
    where = f" in {filename}" if filename else ""
    if n_errors:
        counts = _plural(n_errors, "error") + (f", {_plural(n_warnings, 'warning')}" if n_warnings else "")
        header = click.style(f"Validation failed{where} ({counts}):", fg="red", bold=True)
    else:
        header = click.style(f"Warnings{where}:", fg=WARNING_COLOR, bold=True)
    return header + "\n" + "\n".join(f" {line}" for line in lines)


def format_warnings_for_cli(warnings: list[Diagnostic], source_text: str | None = None, filename: str = "") -> str:
    """Render warnings in the same format as `format_errors_for_cli`."""
    positioned, graph_messages = collect_positioned_diagnostics(
        ConfigValidationError(errors=[], warnings=warnings), source_text
    )
    return render_positioned_diagnostics(positioned, graph_messages, filename)


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
