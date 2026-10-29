"""
Network-backed ("tier-2") validation checks, extracted from Pydantic field
validators so they can be invoked explicitly — once, at a controlled point —
instead of on every model construction.

Each ``check_*`` function is a plain function taking a fully-constructed
``Workflow`` and returning a list of ``Diagnostic``. Severity per branch is
preserved exactly as it was in the original Pydantic validators in
``models.py``: some failure modes are ERROR (hard gate), others are WARNING
(logged, non-blocking).
"""

import contextlib
import dataclasses
import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from .errors import Diagnostic, Severity
from .inputs import Binding, Input, InputDefinition, effective_input
from .models import NfModule, NfPipeline, Workflow
from .nf_param_validation import validate_params
from .registry import (
    ParamSpec,
    PipelineSchemaError,
    Schema,
    SchemaUnavailableError,
    get_module_schema,
    get_nfcore_module_releases,
    get_pipeline_schema,
    github_file_exists,
    url_exists,
)

logger = logging.getLogger()


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_pipeline_url_reachable(wf: NfPipeline) -> list[Diagnostic]:
    """From NfPipeline.validate_url's reachability block."""
    if wf.is_nfcore or not wf.url:
        return []

    if not url_exists(wf.url):
        return [
            Diagnostic(
                workflow_id=wf.id,
                field="url",
                message=(
                    f"Pipeline URL '{wf.url}' could not be reached. "
                    "Continuing — reachability may depend on network or authentication."
                ),
                severity=Severity.WARNING,
            )
        ]
    return []


def check_pipeline_main_script_exists(wf: NfPipeline) -> list[Diagnostic]:
    """From NfPipeline.validate_main_script's github_file_exists block."""
    if wf.main_script is None:
        return []

    if wf.url and "github.com" in wf.url and wf.version:
        if not github_file_exists(wf.url, wf.main_script, wf.version):
            return [
                Diagnostic(
                    workflow_id=wf.id,
                    field="main_script",
                    message=(
                        f"main_script '{wf.main_script}' not found in repository '{wf.url}' at ref '{wf.version}'"
                    ),
                    severity=Severity.ERROR,
                )
            ]
        return []

    return [
        Diagnostic(
            workflow_id=wf.id,
            field="main_script",
            message=(f"Cannot validate main_script '{wf.main_script}': '{wf.url}' is not a GitHub URL"),
            severity=Severity.WARNING,
        )
    ]


def check_pipeline_params_schema(wf: NfPipeline) -> list[Diagnostic]:
    """From NfPipeline.validate_params_against_schema, verbatim branch-by-branch."""
    url = wf.url
    version = wf.version
    node_id = wf.id
    params_file = wf.params_file
    name = wf.name
    value = wf.params

    if not url or not name or not version:
        return []

    try:
        schema = get_pipeline_schema(url, version)
    except PipelineSchemaError as e:
        return [
            Diagnostic(
                workflow_id=node_id,
                field="params",
                message=f"Cannot validate params for '{name}': {e}",
                severity=Severity.WARNING,
            )
        ]

    diagnostics: list[Diagnostic] = []

    # Start from params_file contents, then let value override. This gives the
    # full picture for required-param checks while honouring the precedence
    # rule (value wins on collision). Real scalar types are kept from both
    # sources -- validate_params checks the same types Nextflow will see.
    merged: dict[str, object] = {}
    skip_required = False

    if params_file is not None:
        try:
            with open(params_file) as fh:
                file_data = yaml.safe_load(fh) or {}
            if isinstance(file_data, dict):
                merged = {k: v for k, v in file_data.items() if v is not None}
            else:
                diagnostics.append(
                    Diagnostic(
                        workflow_id=node_id,
                        field="params_file",
                        message=(
                            f"params_file '{params_file}' does not contain a mapping — skipping required-param check"
                        ),
                        severity=Severity.WARNING,
                    )
                )
                skip_required = True
        except (OSError, yaml.YAMLError) as exc:
            diagnostics.append(
                Diagnostic(
                    workflow_id=node_id,
                    field="params_file",
                    message=(f"Could not read params_file '{params_file}': {exc} — skipping required-param check"),
                    severity=Severity.WARNING,
                )
            )
            skip_required = True

    merged.update(value or {})

    diagnostics.extend(
        validate_params(
            merged,
            schema,
            pipeline_id=node_id,
            skip_required=skip_required,
        )
    )

    return diagnostics


def check_module_version_in_registry(wf: NfModule) -> list[Diagnostic]:
    """From NfModule.validate_version_in_registry."""
    name = wf.name
    short_name = name.removeprefix("nf-core/")
    if not short_name or short_name == name:
        return []

    releases = get_nfcore_module_releases(short_name)
    valid_versions = {r["version"] for r in releases}
    if valid_versions and wf.version not in valid_versions:
        return [
            Diagnostic(
                workflow_id=wf.id,
                field="version",
                message=(
                    f"Version '{wf.version}' is not available in the Nextflow "
                    f"registry for module '{name}'. Use one of: {sorted(valid_versions)}"
                ),
                severity=Severity.ERROR,
            )
        ]
    return []


def check_module_params_schema(wf: NfModule) -> list[Diagnostic]:
    """From NfModule.validate_params_against_schema."""
    name = wf.name
    version = wf.version
    node_id = wf.id

    if not name or not version:
        return []

    try:
        schema = get_module_schema(name, version)
    except SchemaUnavailableError as e:
        return [
            Diagnostic(
                workflow_id=node_id,
                field="params",
                message=f"Cannot validate params for '{name}': {e}",
                severity=Severity.WARNING,
            )
        ]
    if not schema:
        return []

    return validate_params(
        wf.params or {},
        schema,
        pipeline_id=node_id,
        skip_required=False,
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

# Each entry: (check name, check fn, fields that trigger a re-check if changed).
# The Callable parameter type is intentionally erased (Callable[..., ...]) since
# NfPipeline- and NfModule-specific checks share this dispatch table; the
# isinstance dispatch in run_dynamic_checks ensures each fn only ever receives
# the workflow type it was written for.
_CheckEntry = tuple[str, Callable[..., list[Diagnostic]], tuple[str, ...]]

_PIPELINE_CHECKS: list[_CheckEntry] = [
    ("url_reachable", check_pipeline_url_reachable, ("url",)),
    (
        "main_script_exists",
        check_pipeline_main_script_exists,
        ("main_script", "url", "version"),
    ),
    (
        "params_schema",
        check_pipeline_params_schema,
        ("url", "version", "params", "params_file"),
    ),
]

_MODULE_CHECKS: list[_CheckEntry] = [
    ("version_in_registry", check_module_version_in_registry, ("name", "version")),
    ("params_schema", check_module_params_schema, ("name", "version", "params")),
]


def _fields_changed(wf: Workflow, previous: Workflow | None, fields: tuple[str, ...]) -> bool:
    if previous is None:
        return True
    return any(getattr(wf, f, None) != getattr(previous, f, None) for f in fields)


def run_dynamic_checks(wf: Workflow, previous: Workflow | None = None) -> list[Diagnostic]:
    """Run the checks applicable to wf's type.

    previous=None: run all checks unconditionally (fresh/CLI load path).
    previous=<Workflow>: only run a check if its trigger fields differ from
    previous — this is the skip-if-unchanged fast path used by the editor.
    """
    if isinstance(wf, NfPipeline):
        checks = _PIPELINE_CHECKS
    elif isinstance(wf, NfModule):
        checks = _MODULE_CHECKS
    else:
        return []

    to_run = [(name, fn) for name, fn, fields in checks if _fields_changed(wf, previous, fields)]
    if not to_run:
        return []

    if len(to_run) == 1:
        _, fn = to_run[0]
        return fn(wf)

    diagnostics: list[Diagnostic] = []
    with ThreadPoolExecutor(max_workers=len(to_run)) as executor:
        futures = [executor.submit(fn, wf) for _, fn in to_run]
        for future in futures:
            diagnostics.extend(future.result())
    return diagnostics


def _prefetch(workflows: list[Workflow]) -> None:
    """Warm the cached fetch functions once per unique key before running
    per-node checks below.

    functools.cache does not deduplicate concurrent calls for a key that's
    not yet cached, so a naive fan-out across nodes could fire redundant
    concurrent HTTP calls when the same nf-core module/pipeline is
    referenced by multiple nodes in one document. Pre-warming sequentially
    ahead of the per-node fan-out avoids that for the common case.
    """
    tasks: dict[tuple, tuple[Callable, tuple]] = {}

    for wf in workflows:
        if isinstance(wf, NfPipeline):
            if wf.url and not wf.is_nfcore:
                tasks[("url_exists", wf.url)] = (url_exists, (wf.url,))
            if wf.main_script and wf.url and "github.com" in wf.url and wf.version:
                tasks[("github_file_exists", wf.url, wf.main_script, wf.version)] = (
                    github_file_exists,
                    (wf.url, wf.main_script, wf.version),
                )
            if wf.url and wf.name and wf.version:
                tasks[("pipeline_schema", wf.url, wf.version)] = (
                    get_pipeline_schema,
                    (wf.url, wf.version),
                )
        elif isinstance(wf, NfModule):
            short_name = wf.name.removeprefix("nf-core/")
            if short_name and short_name != wf.name:
                tasks[("module_releases", short_name)] = (
                    get_nfcore_module_releases,
                    (short_name,),
                )
            if wf.name and wf.version:
                tasks[("module_schema", wf.name, wf.version)] = (
                    get_module_schema,
                    (wf.name, wf.version),
                )

    if not tasks:
        return

    def _safe_call(fn: Callable, args: tuple) -> None:
        # An unavailable schema surfaces again, via the real check, once it runs
        with contextlib.suppress(SchemaUnavailableError):
            fn(*args)

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = [executor.submit(_safe_call, fn, args) for fn, args in tasks.values()]
        for future in futures:
            future.result()


def check_all(workflows: Iterable[Workflow]) -> list[Diagnostic]:
    """Full, non-diffed run across all workflows — used by the CLI/batch load path.

    Always called against a whole config (never an isolated snippet — see
    its two call sites in graph.py), so each diagnostic's yaml_path is
    unconditionally re-stamped with its own workflow's `workflows.<id>.`
    prefix here, right where results are collected.
    """
    workflows = list(workflows)
    if not workflows:
        return []

    _prefetch(workflows)

    diagnostics: list[Diagnostic] = []
    with ThreadPoolExecutor(max_workers=len(workflows)) as executor:
        futures = [(wf, executor.submit(run_dynamic_checks, wf)) for wf in workflows]
        for wf, future in futures:
            diagnostics.extend(
                dataclasses.replace(d, yaml_path=f"workflows.{wf.id}.{d.field}") for d in future.result()
            )
    return diagnostics


def log_warnings(diagnostics: Iterable[Diagnostic]) -> None:
    for d in diagnostics:
        if d.severity == Severity.WARNING:
            logger.warning("[%s] %s: %s", d.workflow_id, d.field, d.message)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def workflow_schema(wf: Workflow) -> Schema | None:
    """`wf`'s flat param schema (see `get_pipeline_schema` /
    `get_module_schema`), or `None` if it can't be fetched."""
    try:
        if isinstance(wf, NfPipeline) and wf.url:
            return get_pipeline_schema(wf.url, wf.version)
        if isinstance(wf, NfModule):
            return get_module_schema(wf.name, wf.version)
    except SchemaUnavailableError:
        return None
    return None


def check_inputs(
    definitions: dict[str, InputDefinition],
    bindings: dict[str, tuple[Binding, ...]],
    whole_value: set[Binding],
    declared: set[Binding],
    workflows: dict[str, Workflow],
    project_dir: Path | None = None,
) -> tuple[dict[str, Input], list[Diagnostic]]:
    """Compute every input's effective schema and report problems that need
    the bound steps' param schemas.

    Args:
        definitions: Inputs as declared, by name.
        bindings: All bindings of each input (both directions).
        whole_value: Bindings whose param takes the input's value whole; only
            these pass their param's schema on to the input.
        declared: Bindings declared with `bind:` (checked to name a real param).
        workflows: The graph's workflows by id.
        project_dir: Where relative default paths are looked up.
    """
    schemas = {wf_id: workflow_schema(wf) for wf_id, wf in workflows.items()}
    inputs: dict[str, Input] = {}
    diagnostics: list[Diagnostic] = []
    for name, definition in definitions.items():
        specs: dict[Binding, ParamSpec | None] = {}
        for binding in bindings.get(name, ()):
            if binding.step_id not in workflows:
                continue  # reported by the graph's static input checks
            schema = schemas[binding.step_id]
            spec = schema.get(binding.param) if schema else None
            if schema is not None and spec is None and binding in declared:
                diagnostics.append(
                    Diagnostic(
                        workflow_id=None,
                        field="bind",
                        yaml_path=f"inputs.{name}.bind",
                        message=f"bound to '{binding}', but step '{binding.step_id}' has no param '{binding.param}'",
                        severity=Severity.ERROR,
                    )
                )
            if binding in whole_value:
                specs[binding] = spec
        inputs[name], input_diagnostics = effective_input(name, definition, bindings.get(name, ()), specs, project_dir)
        diagnostics.extend(input_diagnostics)
    return inputs, diagnostics
