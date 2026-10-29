"""Metapipeline inputs: values meant to be set per run, bound to step params
either by a declaration under the config's top-level `inputs:` key with
`bind:`, or by `${inputs:<name>}` as a param's whole value (which declares the
input implicitly if there is no declaration).

An input is typed with a small JSON-Schema fragment using nf-schema's
vocabulary. Its effective schema starts from the schema of the param(s) it is
bound to; keywords on the input itself override or narrow it.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from .errors import Diagnostic, Severity
from .nf_param_validation import _check_type
from .refs import INPUT_REF_PATTERN
from .registry import ParamSpec

PATH_FORMATS = frozenset({"file-path", "directory-path", "path", "file-path-pattern"})
SCHEMA_KEYWORDS = (
    "type",
    "format",
    "enum",
    "pattern",
    "minimum",
    "maximum",
    "exists",
    "mimetype",
    "schema",
)
# nf-core module meta.yml types that translate to a JSON-Schema type + format
_MODULE_TYPES = {
    "file": {"type": "string", "format": "file-path"},
    "directory": {"type": "string", "format": "directory-path"},
    "path": {"type": "string", "format": "path"},
}
_JSON_TYPES = frozenset({"string", "integer", "number", "boolean"})
_BINDING = re.compile(r"^([^.\s]+)\.(\S+)$")

Scalar = bool | int | float | str


@dataclass(frozen=True, order=True)
class Binding:
    """A step param an input fills: `<step_id>.<param>`."""

    step_id: str
    param: str

    @classmethod
    def parse(cls, text: str) -> "Binding":
        match = _BINDING.match(text)
        if not match:
            raise ValueError(f"Invalid binding '{text}': expected '<step_id>.<param>'")
        return cls(match.group(1), match.group(2))

    def __str__(self) -> str:
        return f"{self.step_id}.{self.param}"


class InputDefinition(BaseModel):
    """One entry of the config's `inputs:` section, as written."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bind: tuple[str, ...] = ()
    default: Scalar | None = None
    description: str | None = None
    type: Literal["string", "integer", "number", "boolean"] | None = None
    format: str | None = None
    enum: tuple[Scalar, ...] | None = None
    pattern: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    exists: bool | None = None
    mimetype: str | None = None
    schema_: str | None = None

    @field_validator("bind", mode="before")
    @classmethod
    def _bind_list(cls, value: Any) -> Any:
        if isinstance(value, str):
            return (value,)
        return value

    @field_validator("bind", mode="after")
    @classmethod
    def _bind_syntax(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for entry in value:
            Binding.parse(entry)
        return value

    @property
    def bindings(self) -> tuple[Binding, ...]:
        return tuple(Binding.parse(b) for b in self.bind)

    def keywords(self) -> dict[str, Any]:
        """The schema keywords set on this input."""
        values = {k: getattr(self, k) for k in SCHEMA_KEYWORDS if k != "schema"}
        values["schema"] = self.schema_
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in values.items() if v is not None}

    def model_dump_config(self) -> dict:
        """This input as written in a config file."""
        data = self.model_dump(exclude_none=True, exclude_defaults=True, by_alias=True)
        if "schema_" in data:
            data["schema"] = data.pop("schema_")
        if "bind" in data:
            data["bind"] = list(data["bind"])
        if "enum" in data:
            data["enum"] = list(data["enum"])
        return data

    @classmethod
    def from_config(cls, data: Any) -> "InputDefinition":
        """Parse an `inputs:` entry. `None` stands for an input with no keys."""
        data = dict(data or {})
        if "schema" in data:
            data["schema_"] = data.pop("schema")
        return cls(**data)


def param_spec_keywords(spec: ParamSpec | None) -> dict[str, Any]:
    """Translate a param spec (as returned by `get_pipeline_schema` /
    `get_module_schema`) into input schema keywords."""
    if not spec:
        return {}
    keywords = {k: spec.get(k) for k in SCHEMA_KEYWORDS if spec.get(k) is not None}
    module_type = _MODULE_TYPES.get(spec.get("type") or "")
    if module_type:
        keywords.update(module_type)
    elif keywords.get("type") not in _JSON_TYPES:
        keywords.pop("type", None)
    return keywords


@dataclass(frozen=True)
class Input:
    """An input with its effective schema (inherited keywords overlaid with
    the input's own) and effective default.

    Attributes:
        name: The input's name in `inputs:`.
        schema: Effective schema keywords (`type`, `format`, `enum`, ...).
        default: Effective default, or `None` if there is none.
        description: Description shown to users.
        bindings: Step params this input fills, from both binding directions.
    """

    name: str
    schema: dict[str, Any]
    default: Scalar | None = None
    description: str = ""
    bindings: tuple[Binding, ...] = field(default_factory=tuple)

    @property
    def is_path(self) -> bool:
        return self.schema.get("format") in PATH_FORMATS

    def missing_path(self, value: Any, project_dir: Path | None = None) -> str | None:
        """For a path input requiring `exists`, why `value` fails that check
        (relative paths are looked up in `project_dir`), else `None`."""
        if not (self.is_path and self.schema.get("exists") and isinstance(value, str)):
            return None
        if "://" in value:
            return None
        path = Path(value)
        if not path.is_absolute() and project_dir is not None:
            path = project_dir / path
        return None if path.exists() else "does not exist"

    def validate(self, value: Any, *, project_dir: Path | None = None, check_exists: bool = True) -> list[str]:
        """Return why `value` is not acceptable for this input, as short
        reasons such as "must match …" (empty if it is acceptable). With
        `check_exists`, a path that must exist is looked up (relative paths in
        `project_dir`)."""
        expected = self.schema.get("type")
        if expected and _check_type(self.name, value, expected):
            return [f"not a valid {expected}"]

        problems: list[str] = []
        enum = self.schema.get("enum")
        if enum is not None and str(value) not in [str(e) for e in enum]:
            problems.append(f"must be one of {', '.join(str(e) for e in enum)}")

        pattern = self.schema.get("pattern")
        if pattern and isinstance(value, str) and not re.search(pattern, value):
            problems.append(f"must match {pattern}")

        for bound, op, ok in (
            ("minimum", ">=", lambda v, b: v >= b),
            ("maximum", "<=", lambda v, b: v <= b),
        ):
            limit = self.schema.get(bound)
            if (
                limit is not None
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and not ok(value, limit)
            ):
                problems.append(f"must be {op} {limit}")

        missing = self.missing_path(value, project_dir) if check_exists else None
        if missing:
            problems.append(missing)
        return problems

    def describe_problems(self, value: Any, problems: list[str]) -> str:
        """One line naming this input, the value and why it's not acceptable."""
        return f"{self.name} = {value!r}: {'; '.join(problems)}"


def effective_input(
    name: str,
    definition: InputDefinition,
    bindings: tuple[Binding, ...],
    param_specs: dict[Binding, ParamSpec | None],
    project_dir: Path | None = None,
) -> tuple[Input, list[Diagnostic]]:
    """Combine an input's own keywords with the specs of the params it fills.

    `param_specs` maps each binding whose param takes the input's value whole
    to that param's spec (`None` if unknown). Returns the effective `Input`
    and any problems: bound params whose schemas conflict, an input keyword
    contradicting the inherited `type`/`format`, a default the effective
    schema rejects (errors), no known type at all (warning; `string` is
    assumed), or a default path that must exist but doesn't, looked up in
    `project_dir` (warning; it is an error only when running).
    """
    diagnostics: list[Diagnostic] = []

    def problem(field_: str, message: str, severity=Severity.ERROR) -> None:
        diagnostics.append(
            Diagnostic(
                workflow_id=None,
                field=field_,
                yaml_path=f"inputs.{name}.{field_}" if field_ else f"inputs.{name}",
                message=message,
                severity=severity,
            )
        )

    inherited: dict[str, Any] = {}
    inherited_default = None
    for binding, spec in sorted(param_specs.items()):
        keywords = param_spec_keywords(spec)
        for key in ("type", "format"):
            if key in keywords and key in inherited and keywords[key] != inherited[key]:
                problem(
                    "bind",
                    f"bound params have conflicting {key}s: '{inherited[key]}' and '{keywords[key]}' ({binding})",
                )
        for key, value in keywords.items():
            inherited.setdefault(key, value)
        if inherited_default is None and spec and spec.get("default") not in (None, ""):
            inherited_default = spec.get("default")

    own = definition.keywords()
    for key in ("type", "format"):
        if key in own and key in inherited and own[key] != inherited[key]:
            problem(
                key,
                f"declared {key} '{own[key]}', but the bound param's schema says '{inherited[key]}'",
            )

    schema = {**inherited, **own}
    if "type" not in schema:
        problem("type", "no known type; assuming 'string'", Severity.WARNING)
        schema["type"] = "string"

    default = definition.default if definition.default is not None else inherited_default
    result = Input(
        name=name,
        schema=schema,
        default=default,
        description=definition.description or "",
        bindings=bindings,
    )
    if definition.default is not None:
        problems = result.validate(definition.default, check_exists=False)
        if problems:
            problem("default", f"{definition.default!r}: {'; '.join(problems)}")
        missing = result.missing_path(definition.default, project_dir)
        if missing:
            problem("default", f"{definition.default!r}: {missing}", Severity.WARNING)
    return result, diagnostics


def input_refs(params: dict | None) -> dict[str, list[str]]:
    """Map each param key to the input names referenced in its value."""
    refs: dict[str, list[str]] = {}
    for key, value in (params or {}).items():
        if isinstance(value, str):
            names = INPUT_REF_PATTERN.findall(value)
            if names:
                refs[key] = names
    return refs


def substitute_inputs(
    params: dict | None,
    bound: dict[str, str],
    values: dict[str, Any],
) -> dict | None:
    """Return `params` with input values filled in: params named in `bound`
    (param → input name, from `bind:`) and params whose whole value is
    `${inputs:<name>}` are set to the input's value, keeping its type."""
    if params is None and not bound:
        return params
    result = dict(params or {})
    for param, name in bound.items():
        result[param] = values[name]
    for key, value in list(result.items()):
        whole = INPUT_REF_PATTERN.fullmatch(value) if isinstance(value, str) else None
        if whole:
            result[key] = values[whole.group(1)]
    return result
