import logging
import re

logger = logging.getLogger(__name__)

# Matches ${<wf_id>:<namespace>:<key>} — same pattern as models.py
_VALID_REF_PATTERN = re.compile(r"\$\{([^}]+):(params|outputs):([^}]+)\}")


def _check_type(
    param_name: str, value: str, expected_type: str, pipeline_id: str
) -> str | None:
    """Return an error message if value fails the expected_type check, else None."""
    if expected_type == "integer":
        try:
            int(value)
        except ValueError:
            return (
                f"[{pipeline_id}] Parameter '{param_name}' = {value!r} "
                "is not a valid integer"
            )
    elif expected_type in ("number", "float"):
        try:
            float(value)
        except ValueError:
            return (
                f"[{pipeline_id}] Parameter '{param_name}' = {value!r} "
                "is not a valid number"
            )
    elif expected_type == "boolean":
        if value.lower() not in {"true", "false", "1", "0", "yes", "no"}:
            return (
                f"[{pipeline_id}] Parameter '{param_name}' = {value!r} "
                "is not a valid boolean (expected true/false/yes/no/0/1)"
            )
    # string, array, object, path formats — cannot reliably validate from str
    return None


def validate_params(
    params: dict[str, str],
    schema: dict[str, dict],
    *,
    pipeline_id: str,
    skip_required: bool = False,
) -> list[str]:
    """
    Validate pipeline params against a flat param-spec dict from nextflow_schema.json.

    Returns a list of error message strings. An empty list means all params are valid.
    Cross-workflow reference tokens (``${...}``) skip type and enum checks.

    Args:
        params: Resolved param dict (all values already coerced to str).
        schema: Flat {param_name: spec} dict from ``get_pipeline_schema``.
        pipeline_id: Workflow ID used in error messages.
        skip_required: When True, omit the required-param check (use when
            a params_file is set and may supply the missing values).
    """
    errors: list[str] = []

    # Check for unknown params; enforce map-type params use dot-key expansion
    _map_keys = {k for k, s in schema.items() if s.get("type") == "map"}
    for param_name in params:
        if param_name in _map_keys:
            errors.append(
                f"[{pipeline_id}] Parameter '{param_name}' is a map — "
                f"use dot-notation sub-keys (e.g. '{param_name}.id') instead of a raw value"
            )
        elif param_name not in schema:
            if not any(param_name.startswith(f"{k}.") for k in _map_keys):
                errors.append(f"[{pipeline_id}] Unknown parameter '{param_name}'")

    # Check required params (only when no params_file is covering them)
    if not skip_required:
        for param_name, spec in schema.items():
            is_truly_required = (
                spec.get("required", False)
                and not spec.get("hidden", False)
                and spec.get("default") is None
            )
            if not is_truly_required:
                continue
            # map-type inputs are represented as flattened dot-keys (e.g. meta.id,
            # meta.sample), so check for any key with the expected prefix.
            if spec.get("type") == "map":
                prefix = f"{param_name}."
                present = param_name in params or any(
                    k.startswith(prefix) for k in params
                )
            else:
                present = param_name in params
            if not present:
                errors.append(
                    f"[{pipeline_id}] Required parameter '{param_name}' is not set. "
                    "Provide it in the params dict or via a params_file."
                )

    # Check types and enum values for provided params
    for param_name, value in params.items():
        spec: dict | None = schema.get(param_name)
        if spec is None:
            continue  # already flagged as unknown above

        # Reference tokens are resolved at runtime — skip checks
        if _VALID_REF_PATTERN.search(value):
            continue

        enum_values = spec.get("enum")
        expected_type = spec.get("type")

        if enum_values is not None:
            str_enum = [str(v) for v in enum_values]
            if value not in str_enum:
                errors.append(
                    f"[{pipeline_id}] Parameter '{param_name}' = {value!r} "
                    f"is not one of the allowed values: {enum_values}"
                )
        elif expected_type is not None:
            type_error = _check_type(param_name, value, expected_type, pipeline_id)
            if type_error:
                errors.append(type_error)

    return errors
