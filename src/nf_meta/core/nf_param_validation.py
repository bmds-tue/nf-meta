import logging
import re

from .errors import Diagnostic, Severity

logger = logging.getLogger(__name__)

# Matches ${<wf_id>:<namespace>:<key>} — same pattern as models.py
_VALID_REF_PATTERN = re.compile(r"\$\{([^}]+):(params|outputs):([^}]+)\}")


def _check_type(param_name: str, value: object, expected_type: str) -> str | None:
    """Return an error message if value fails the expected_type check, else None.

    Checks the value's real type (bool/int/float/str), the same type Nextflow's
    ``-params-file`` will hand to nf-schema -- not whether a stringified form of
    it happens to be parseable, since a quoted numeric string is accepted here
    but still rejected by nf-schema.
    """
    # bool is a subtype of int in Python, so it must be checked before int/float.
    if expected_type == "boolean":
        if not isinstance(value, bool):
            return f"Parameter '{param_name}' = {value!r} is not a valid boolean"
    elif expected_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return f"Parameter '{param_name}' = {value!r} is not a valid integer"
    elif expected_type in ("number", "float"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"Parameter '{param_name}' = {value!r} is not a valid number"
    # string, array, object, path formats — no further check
    return None


def validate_params(
    params: dict[str, object],
    schema: dict[str, dict],
    *,
    pipeline_id: str,
    skip_required: bool = False,
) -> list[Diagnostic]:
    """
    Validate pipeline params against a flat param-spec dict from nextflow_schema.json.

    Returns a list of Diagnostic, one per failing param (field=f"params.{param_name}",
    message still names the param explicitly). An empty list means all params are
    valid. Cross-workflow reference tokens (``${...}``) skip type and enum checks.

    Args:
        params: Resolved param dict. Values are real scalars (str/int/float/bool)
            e.g. a params_file entry may be ``str`` while a workflow-level
            override is ``int``.
        schema: Flat {param_name: spec} dict from ``get_pipeline_schema``.
        pipeline_id: Workflow ID, used as Diagnostic.workflow_id.
        skip_required: When True, omit the required-param check (use when
            a params_file is set and may supply the missing values).
    """
    diagnostics: list[Diagnostic] = []

    def _diagnostic(param_name: str, message: str) -> Diagnostic:
        return Diagnostic(
            workflow_id=pipeline_id,
            field=f"params.{param_name}",
            message=message,
            severity=Severity.ERROR,
        )

    # Check for unknown params; enforce map-type params use dot-key expansion
    _map_keys = {k for k, s in schema.items() if s.get("type") == "map"}
    for param_name in params:
        if param_name in _map_keys:
            diagnostics.append(
                _diagnostic(
                    param_name,
                    f"Parameter '{param_name}' is a map — "
                    f"use dot-notation sub-keys (e.g. '{param_name}.id') instead of a raw value",
                )
            )
        elif param_name not in schema and not any(
            param_name.startswith(f"{k}.") for k in _map_keys
        ):
            diagnostics.append(
                _diagnostic(param_name, f"Unknown parameter '{param_name}'")
            )

    # Check required params (only when no params_file is covering them)
    if not skip_required:
        for param_name, required_spec in schema.items():
            is_truly_required = (
                required_spec.get("required", False)
                and not required_spec.get("hidden", False)
                and required_spec.get("default") is None
            )
            if not is_truly_required:
                continue
            # map-type inputs are represented as flattened dot-keys (e.g. meta.id,
            # meta.sample), so check for any key with the expected prefix.
            if required_spec.get("type") == "map":
                prefix = f"{param_name}."
                present = param_name in params or any(
                    k.startswith(prefix) for k in params
                )
            else:
                present = param_name in params
            if not present:
                diagnostics.append(
                    _diagnostic(
                        param_name,
                        f"Required parameter '{param_name}' is not set. "
                        "Provide it in the params dict or via a params_file.",
                    )
                )

    # Check types and enum values for provided params
    for param_name, value in params.items():
        spec: dict | None = schema.get(param_name)
        if spec is None:
            continue  # already flagged as unknown above

        # Reference tokens are resolved at runtime — skip checks
        if isinstance(value, str) and _VALID_REF_PATTERN.search(value):
            continue

        enum_values = spec.get("enum")
        expected_type = spec.get("type")

        if enum_values is not None:
            str_enum = [str(v) for v in enum_values]
            if str(value) not in str_enum:
                diagnostics.append(
                    _diagnostic(
                        param_name,
                        f"Parameter '{param_name}' = {value!r} "
                        f"is not one of the allowed values: {enum_values}",
                    )
                )
        elif expected_type is not None:
            type_error = _check_type(param_name, value, expected_type)
            if type_error:
                diagnostics.append(_diagnostic(param_name, type_error))

    return diagnostics
