import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from nf_meta.core.models import Workflow
from nf_meta.core.dynamic_validation import workflow_schema

PATH_FORMATS = frozenset({"file-path", "directory-path", "path", "file-path-pattern"})
# nf-core module meta.yml input types that denote files
PATH_TYPES = frozenset({"file", "directory", "path"})
OUTPUT_PARAMS = frozenset({"outdir"})

_URL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def is_url(value: str) -> bool:
    return bool(_URL.match(value))


def param_schema(wf: Workflow) -> dict[str, dict]:
    """Return the flat param schema of `wf`'s pipeline or module, or `{}`
    when none can be fetched."""
    return workflow_schema(wf) or {}


def declared_path(spec: dict | None) -> bool:
    """Whether a param spec from a pipeline/module schema declares a path."""
    spec = spec or {}
    return spec.get("format") in PATH_FORMATS or spec.get("type") in PATH_TYPES


def is_input_path(key: str, value: Any, schema: dict[str, dict], project_dir: Path) -> bool:
    """Whether param `key` = `value` is a relative path to an input that lives
    in the project dir: a relative string whose schema declares a path (see
    `declared_path`), or which names an existing file or directory under `project_dir`.
    Output locations (`outdir`) and URLs never are."""
    if key in OUTPUT_PARAMS or not isinstance(value, str) or not value:
        return False
    if is_url(value) or Path(value).is_absolute() or "${" in value:
        return False
    if declared_path(schema.get(key)):
        return True
    return (project_dir / value).exists()


def absolutize_input_paths(
    params: dict[str, Any],
    project_dir: Path,
    schema: dict[str, dict] | None = None,
    skip: Iterable[str] = (),
) -> dict[str, Any]:
    """Return a copy of `params` with every relative input path (see
    `is_input_path`) made absolute against `project_dir`. Keys in `skip` are
    left unchanged."""
    skipped = set(skip)
    return {
        key: str(project_dir / value)
        if key not in skipped and is_input_path(key, value, schema or {}, project_dir)
        else value
        for key, value in params.items()
    }
