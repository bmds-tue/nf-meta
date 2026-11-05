"""Collecting the values a run needs before any step starts: declared inputs,
and references to steps outside the selected range (`--start`/`--target`)."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from nf_meta.core.inputs import Input

from .errors import NfMetaRunnerError

PLACEHOLDER = "<input: {name}>"

# Called with the input to ask for and, on a repeated ask, why the last answer
# was rejected; returns the value.
Prompter = Callable[[Input, str | None], Any]


def plain_prompter(inp: Input, problem: str | None) -> str:
    """Ask for `inp` with the built-in `input()`; the prompter used in
    `prompt` mode when none is given."""
    if problem:
        print(f"  {problem}")
    label = inp.name + (f" ({inp.description})" if inp.description else "")
    return input(f"{label}: ")


_TRUE = {"true", "yes", "y", "1"}
_FALSE = {"false", "no", "n", "0"}


class InputMode(StrEnum):
    """What happens with values a run needs but doesn't have.

    `prompt`: ask for them before the first step starts. `fail`: stop with a
    list of them. `reproduce`: use exactly the values of the last run (input
    values recorded then, references from the cache); no values may be given.
    """

    PROMPT = "prompt"
    FAIL = "fail"
    REPRODUCE = "reproduce"


@dataclass(frozen=True)
class Request:
    """One value a run needs.

    Attributes:
        input: Name and schema; the name is an input's name, or
            `<step_id>.<param>` for a reference to a step outside the run.
        fallback: Value used when none is given (an input's default, a
            recorded value in reproduce mode, a cached reference value);
            `None` if there is none.
        is_reference: Whether this stands for a reference to another step.
    """

    input: Input
    fallback: Any = None
    is_reference: bool = False

    @property
    def name(self) -> str:
        return self.input.name


@dataclass
class Collected:
    """The outcome of `collect`.

    Attributes:
        values: Value per request name. In a dry run, missing values are
            placeholders (`<input: name>`).
        missing: Requests that had no value (only non-empty in a dry run).
    """

    values: dict[str, Any] = field(default_factory=dict)
    missing: list[Request] = field(default_factory=list)


def is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("<input: ") and value.endswith(">")


def coerce(inp: Input, value: Any) -> Any:
    """Convert a string given on the command line to the input's type. Values
    that don't convert are returned unchanged (validation reports them)."""
    if not isinstance(value, str):
        return value
    expected = inp.schema.get("type")
    try:
        if expected == "integer":
            return int(value)
        if expected == "number":
            return float(value)
    except ValueError:
        return value
    if expected == "boolean" and value.lower() in _TRUE | _FALSE:
        return value.lower() in _TRUE
    return value


def collect(
    requests: list[Request],
    given: dict[str, Any],
    mode: InputMode,
    *,
    project_dir: Path | None = None,
    given_dir: Path | None = None,
    prompter: Prompter | None = None,
    dry_run: bool = False,
) -> Collected:
    """Find a value for every request: the given one, else its fallback, else
    (depending on `mode`) prompt for it or report it missing. All values are
    validated; all problems are reported together.

    Relative paths given or typed in are relative to `given_dir` (default: the
    current directory) and returned absolute; fallbacks (defaults written in
    the config) are checked against `project_dir`.

    In a dry run outside `prompt` mode, missing values become placeholders
    instead of an error. `prompter` defaults to `plain_prompter`.

    Raises:
        NfMetaRunnerError: for unknown given names, given values in
            `reproduce` mode, missing values (except in a dry run), or invalid
            values.
    """
    by_name = {r.name: r for r in requests}
    unknown = sorted(set(given) - set(by_name))
    if unknown:
        known = ", ".join(sorted(by_name)) or "none"
        raise NfMetaRunnerError(f"Unknown input(s): {', '.join(unknown)}. This run takes: {known}.")
    if mode == InputMode.REPRODUCE and given:
        raise NfMetaRunnerError("Input mode 'reproduce' uses the recorded values; values can't be given.")
    _reject_packed_values(given, set(by_name))

    given_dir = given_dir or Path.cwd()
    result = Collected()
    problems: list[str] = []
    for request in requests:
        inp = request.input
        if request.name in given:
            typed = coerce(inp, given[request.name])
            found = inp.validate(typed, project_dir=given_dir)
            if found:
                problems.append(inp.describe_problems(typed, found))
            value = _absolute(inp, typed, given_dir)
        elif request.fallback is not None:
            value = request.fallback
            # Cached reference values point into the out dir; only check inputs
            found = [] if request.is_reference else inp.validate(value, project_dir=project_dir)
            if found:
                problems.append(inp.describe_problems(value, found))
        elif mode == InputMode.PROMPT:
            value = _prompt(inp, prompter or plain_prompter, given_dir)
        elif dry_run:
            result.values[request.name] = PLACEHOLDER.format(name=request.name)
            result.missing.append(request)
            continue
        else:
            result.missing.append(request)
            continue
        result.values[request.name] = value

    if result.missing and not dry_run:
        raise NfMetaRunnerError(_missing_message(result.missing, mode))
    if problems:
        raise NfMetaRunnerError("Invalid input values:\n  " + "\n  ".join(problems))
    return result


def _absolute(inp: Input, value: Any, base: Path) -> Any:
    if inp.is_path and isinstance(value, str) and value and "://" not in value and not Path(value).is_absolute():
        return str(base / value)
    return value


def _prompt(inp: Input, prompter: Prompter, given_dir: Path) -> Any:
    problem = None
    while True:
        typed = coerce(inp, prompter(inp, problem))
        found = inp.validate(typed, project_dir=given_dir)
        if not found:
            return _absolute(inp, typed, given_dir)
        problem = f"{typed!r}: {'; '.join(found)}"


def _reject_packed_values(given: dict[str, Any], names: set[str]) -> None:
    """Catch `--input a=1,b=2`: one value that contains another `name=`."""
    for name, value in given.items():
        if not isinstance(value, str):
            continue
        packed = [m for m in re.findall(r",\s*([^,=\s]+)=", value) if m in names]
        if packed:
            raise NfMetaRunnerError(
                f"The value given for '{name}' contains '{packed[0]}=': pass --input once per value, "
                f"e.g. --input {name}=... --input {packed[0]}=..."
            )


def _missing_message(missing: list[Request], mode: InputMode) -> str:
    lines = []
    for request in missing:
        what = "reference to a step outside this run" if request.is_reference else "input"
        lines.append(f"  {request.name} ({what})")
    if mode == InputMode.REPRODUCE:
        hint = "Reproduce needs a previous run of these steps with recorded values."
    else:
        hint = "Give values with --input name=value or --inputs-file, or use --input-mode prompt."
    return "Missing values:\n" + "\n".join(lines) + f"\n{hint}"
