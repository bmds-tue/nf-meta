"""The `${...}` syntax usable inside param values."""

import re
from typing import Protocol

# ${<wf_id>:<namespace>:<key>} -- namespace "params" (resolved) or "outputs" (reserved)
STEP_REF_PATTERN = re.compile(r"\$\{([^}:]+):(params|outputs):([^}]+)\}")
# ${inputs:<name>} -- the value of a declared input
INPUT_REF_PATTERN = re.compile(r"\$\{inputs:([^}:]+)\}")
ANY_BRACE_PATTERN = re.compile(r"\$\{[^}]*\}")

RESERVED_STEP_IDS = frozenset({"inputs"})


def contains_reference(value: object) -> bool:
    """Whether `value` is a string containing a step or input reference."""
    return isinstance(value, str) and bool(STEP_REF_PATTERN.search(value) or INPUT_REF_PATTERN.search(value))


class _HasId(Protocol):
    id: str


class Ref(str):
    """A reference to another step's param or to an input, usable as a param
    value. It is a `str` holding the reference syntax, and `/` appends a path:

        Ref(fetch, "outdir") / "samplesheet/samplesheet.csv"
        # '${n01:params:outdir}/samplesheet/samplesheet.csv'
        Ref.input("ids")
        # '${inputs:ids}'

    `step` is a step model or a step ID.
    """

    def __new__(cls, step: "_HasId | str", key: str, *, namespace: str = "params") -> "Ref":
        step_id = step if isinstance(step, str) else step.id
        return super().__new__(cls, f"${{{step_id}:{namespace}:{key}}}")

    @classmethod
    def input(cls, name: str) -> "Ref":
        """A reference to the input `name`."""
        return cls._of(f"${{inputs:{name}}}")

    @classmethod
    def _of(cls, text: str) -> "Ref":
        return str.__new__(cls, text)

    def __truediv__(self, path: object) -> "Ref":
        return self._of(f"{self.rstrip('/')}/{str(path).lstrip('/')}")
