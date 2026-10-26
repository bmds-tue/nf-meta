"""The `${...}` syntax usable inside param values."""

import re

# ${<wf_id>:<namespace>:<key>} -- namespace "params" (resolved) or "outputs" (reserved)
STEP_REF_PATTERN = re.compile(r"\$\{([^}:]+):(params|outputs):([^}]+)\}")
# ${inputs:<name>} -- the value of a declared input
INPUT_REF_PATTERN = re.compile(r"\$\{inputs:([^}:]+)\}")
ANY_BRACE_PATTERN = re.compile(r"\$\{[^}]*\}")

RESERVED_STEP_IDS = frozenset({"inputs"})


def contains_reference(value: object) -> bool:
    """Whether `value` is a string containing a step or input reference."""
    return isinstance(value, str) and bool(
        STEP_REF_PATTERN.search(value) or INPUT_REF_PATTERN.search(value)
    )
