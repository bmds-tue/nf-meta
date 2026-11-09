"""
Construction and serialization functions.

There is no top-level pydantic model for the whole configuration document,
just the major building blocks like global options and steps. (Pipeline, Module, ...)
A MetaworkflowGraph is instad constructed by parsing the top level keys and then these
building blocks from a nf-meta YAML configuration.
"""

import dataclasses
import difflib
import logging
import posixpath
import re
from pathlib import Path

import requests
import yaml
from packaging.version import Version
from pydantic import ValidationError

from .dynamic_validation import check_all, check_config_files, log_warnings, run_dynamic_checks
from .errors import (
    ConfigValidationError,
    Diagnostic,
    GraphValidationError,
    Severity,
    diagnostics_from_pydantic_error,
)
from .graph import MetaworkflowGraph
from .inputs import InputDefinition, input_refs
from .models import (
    CONFIG_VERSION_MAX,
    INPUTS_MIN_CONFIG_VERSION,
    LEGACY_KEYS,
    LEGACY_STEPS_KEY,
    STEPS_KEY,
    STEPS_MIN_CONFIG_VERSION,
    GlobalOptions,
    NfModule,
    NfPipeline,
    Transition,
    Workflow,
    WorkflowType,
    validate_config_version,
    with_absolute_config_paths,
)
from .refs import INPUT_REF_PATTERN

logger = logging.getLogger()


def _module_executor_warnings(g: "MetaworkflowGraph") -> list[Diagnostic]:
    if g.global_options and g.global_options.nf_config:
        return []
    return [
        Diagnostic(
            workflow_id=wf.id,
            field="container_engine",
            yaml_path=f"steps.{wf.id}",
            message=(
                "Module runs without a container_engine or a global Nextflow config "
                "rely on the local environment: missing dependencies cause errors, "
                "and results aren't reproducible"
            ),
            severity=Severity.WARNING,
        )
        for wf in g.get_workflows()
        if wf.type == WorkflowType.NF_MODULE and not wf.container_engine  # type: ignore[union-attr]
    ]


_ABBREVIATED_SHA = re.compile(r"^[0-9a-fA-F]{7,39}$")


def _abbreviated_sha_warnings(g: "MetaworkflowGraph") -> list[Diagnostic]:
    """Pipeline versions given as abbreviated commit hashes: Nextflow 26 can't
    fetch those (it fetches each revision separately, by full id)."""
    return [
        Diagnostic(
            workflow_id=wf.id,
            field="version",
            yaml_path=f"steps.{wf.id}.version",
            message="Abbreviated commit hash; Nextflow 26+ can't fetch these. Use the full 40-character hash.",
            severity=Severity.WARNING,
        )
        for wf in g.get_workflows()
        if wf.type == WorkflowType.NF_PIPELINE and wf.version and _ABBREVIATED_SHA.match(wf.version)
    ]


def _shared_outdir_warnings(g: "MetaworkflowGraph") -> list[Diagnostic]:
    """Steps whose literal `outdir` params are the same folder or one inside
    the other, one warning per step involved, with the same text for each.
    Values with references or inputs are left to the runner."""
    by_path: dict[str, list[tuple[str, str]]] = {}
    for wf in g.get_workflows():
        value = (wf.params or {}).get("outdir")
        if isinstance(value, str) and value and "${" not in value:
            by_path.setdefault(posixpath.normpath(value), []).append((wf.id, value))
    found: list[tuple[list[str], str]] = []
    for steps in by_path.values():
        if len(steps) > 1:
            ids = [step_id for step_id, _ in steps]
            names = ", ".join(f"'{step_id}'" for step_id in ids)
            found.append((ids, f"Steps {names} write to the same outdir '{steps[0][1]}': nf-meta run refuses this."))
    for outer, outer_steps in by_path.items():
        for inner, inner_steps in by_path.items():
            if "://" in inner or inner == outer or not inner.startswith(outer.rstrip("/") + "/"):
                continue
            for inner_id, inner_value in inner_steps:
                for outer_id, outer_value in outer_steps:
                    message = (
                        f"Step '{inner_id}' writes inside step '{outer_id}''s outdir "
                        f"('{inner_value}' in '{outer_value}'): their results may mix."
                    )
                    found.append(([inner_id, outer_id], message))
    return [
        Diagnostic(
            workflow_id=step_id,
            field="params",
            yaml_path=f"steps.{step_id}.params.outdir",
            message=message,
            severity=Severity.WARNING,
        )
        for ids, message in found
        for step_id in ids
    ]


def _deprecated_key_warnings(g: "MetaworkflowGraph") -> list[Diagnostic]:
    if not (g.global_options and g.global_options.params):
        return []
    return [
        Diagnostic(
            workflow_id=None,
            field="params",
            yaml_path="globals.params",
            message=(
                "Deprecated key, it will be removed in a later version: "
                "set params per step, and declare shared values as inputs."
            ),
            severity=Severity.WARNING,
        )
    ]


def _graph_warnings(g: "MetaworkflowGraph") -> list[Diagnostic]:
    return (
        _deprecated_key_warnings(g)
        + _module_executor_warnings(g)
        + _abbreviated_sha_warnings(g)
        + _shared_outdir_warnings(g)
    )


def current_warnings(g: "MetaworkflowGraph") -> list[Diagnostic]:
    """The warnings that hold for `g` as it is now: each step's own checks
    (from when it was loaded, added or last changed) and the checks across
    steps and globals. Input warnings are reported with the inputs instead."""
    step_warnings = [
        dataclasses.replace(d, yaml_path=f"steps.{wf_id}.{d.field}")
        for wf_id, found in g.step_warnings.items()
        for d in found
    ]
    return step_warnings + _graph_warnings(g)


def _log_graph_warnings(g: "MetaworkflowGraph") -> None:
    log_warnings(_graph_warnings(g))


TOP_LEVEL_KEYS = ("config_version", "globals", "inputs", STEPS_KEY, LEGACY_STEPS_KEY, "transitions")


def _with_steps_key(data: dict) -> tuple[dict, list[Diagnostic]]:
    """`data` with its steps under `steps:`, and a deprecation warning if they
    were under the old name `workflows:`. Raises `GraphValidationError` if both
    keys are given."""
    if LEGACY_STEPS_KEY not in data:
        return data, []
    if STEPS_KEY in data:
        raise GraphValidationError("Use one of 'steps:' and 'workflows:', not both")
    data = {(STEPS_KEY if key == LEGACY_STEPS_KEY else key): value for key, value in data.items()}
    warning = Diagnostic(
        workflow_id=None,
        field=LEGACY_STEPS_KEY,
        yaml_path=LEGACY_STEPS_KEY,
        message="Deprecated in favor of 'steps:'. Saving from the editor updates it.",
        severity=Severity.WARNING,
    )
    return data, [warning]


def legacy_key_warnings(data: dict) -> list[Diagnostic]:
    """A deprecation warning for each legacy key (see `models.LEGACY_KEYS`)
    in `globals` and workflow entries."""
    sections: list[tuple[str, dict]] = []
    if isinstance(data.get("globals"), dict):
        sections.append(("globals.", data["globals"]))
    sections += [(f"steps.{wf_id}.", item) for wf_id, item in _workflow_items(data)]
    return [w for prefix, section in sections for w in _legacy_section_warnings(section, prefix)]


def _legacy_section_warnings(section: dict, prefix: str = "") -> list[Diagnostic]:
    return [
        Diagnostic(
            workflow_id=None,
            field=old,
            yaml_path=f"{prefix}{old}",
            message=f"Deprecated key, use '{new}' instead. Saving from the editor updates it.",
            severity=Severity.WARNING,
        )
        for old, new in LEGACY_KEYS.items()
        if old in section
    ]


# Keys a workflow entry may have besides its model's fields
_EXTRA_WORKFLOW_KEYS = ("from", "id", "type")


def _unknown_key(key: str, allowed, yaml_path: str, workflow_id=None) -> Diagnostic:
    close = difflib.get_close_matches(str(key), list(allowed), n=1, cutoff=0.6)
    hint = f" Did you mean '{close[0]}'?" if close else ""
    return Diagnostic(
        workflow_id=workflow_id,
        field=str(key),
        yaml_path=yaml_path,
        message=f"Unknown key.{hint}",
        severity=Severity.ERROR,
    )


def unknown_key_diagnostics(data: dict) -> list[Diagnostic]:
    """Errors for keys the config format doesn't know: at the top level, in
    `globals`, and in each workflow entry. (Unknown keys in `inputs` entries
    are reported when they are parsed.)"""
    diagnostics = [_unknown_key(key, TOP_LEVEL_KEYS, str(key)) for key in data if key not in TOP_LEVEL_KEYS]
    globals_ = data.get("globals")
    if isinstance(globals_, dict):
        global_keys = [*GlobalOptions.model_fields, *LEGACY_KEYS]
        diagnostics += [_unknown_key(key, global_keys, f"globals.{key}") for key in globals_ if key not in global_keys]
    for wf_id, item in _workflow_items(data):
        model = NfModule if item.get("type") == WorkflowType.NF_MODULE else NfPipeline
        allowed = [*model.model_fields, *_EXTRA_WORKFLOW_KEYS, *LEGACY_KEYS]
        diagnostics += [_unknown_key(key, allowed, f"steps.{wf_id}.{key}", wf_id) for key in item if key not in allowed]
    return diagnostics


def _extract_items_and_transitions(
    data: dict, warnings: list[Diagnostic] | None = None
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Normalize `steps:`/`transitions:`/`from:` into a flat list of
    workflow-definition dicts (`type`/`id` defaulted) and a list of pending
    `(source, target)` transitions.

    Raises `GraphValidationError` immediately for shape-errors with the YAML file,
    which represent invalid input. They cannot be meaningfully recovered and
    attempting to parse step-models is likely to fail without useful errors.
    """

    def warn(yaml_path: str, message: str) -> None:
        if warnings is None:
            logger.warning(message)
        else:
            warnings.append(
                Diagnostic(
                    workflow_id=None,
                    field=yaml_path,
                    yaml_path=yaml_path,
                    message=message,
                    severity=Severity.WARNING,
                )
            )

    has_top_level_transitions = "transitions" in data
    if has_top_level_transitions:
        warn(
            "transitions",
            "Legacy top-level key 'transitions:' is deprecated. Declare each "
            "step's predecessors via its own 'from:' key instead. Update by "
            "saving the config from the editor.",
        )

    raw_workflows = data.get(STEPS_KEY) or {}
    if isinstance(raw_workflows, dict):
        raw_items: list[tuple[str | None, object]] = list(raw_workflows.items())
    elif isinstance(raw_workflows, list):
        warn(
            STEPS_KEY,
            "Legacy list-format for 'steps' is deprecated. Use the dict-"
            "format the step-id as key instead. Update by saving the "
            "config from the editor.",
        )
        raw_items = [(item.get("id") if isinstance(item, dict) else None, item) for item in raw_workflows]
    else:
        raise GraphValidationError(
            f"'steps:' must be a mapping keyed by step id or a list "
            f"of step definitions, got {type(raw_workflows).__name__!r}"
        )

    items: list[dict] = []
    pending_transitions: list[tuple[str, str]] = []
    any_from_key_present = False
    seen_ids: set[str] = set()
    for key, item in raw_items:
        if not isinstance(item, dict):
            raise GraphValidationError(
                f"Invalid definition of step {key}: Must be a key-value mapping, got '{item}' instead"
            )
        item = {**item}
        item.setdefault("type", WorkflowType.NF_PIPELINE)
        if key is not None:
            item["id"] = key  # dict form: the mapping key is authoritative
        if "id" in item:
            if not isinstance(item["id"], str) or not item["id"]:
                raise GraphValidationError("Step id must be a non-empty string.")
            if item["id"] in seen_ids:
                raise GraphValidationError(f"Step id '{item['id']}' is used more than once.")
            seen_ids.add(item["id"])
        any_from_key_present = any_from_key_present or "from" in item
        from_ids = item.pop("from", None) or []
        if isinstance(from_ids, str):
            from_ids = [from_ids]  # a single predecessor id, not wrapped in a list
        if not isinstance(from_ids, list) or not all(isinstance(f, str) for f in from_ids):
            raise GraphValidationError(
                f"Invalid 'from' value for step {item.get('id', '<unknown>')}: "
                f"expected a step id or a list of step ids, got "
                f"'{from_ids}' instead"
            )
        target_id = item.get("id", "<unknown>")
        pending_transitions.extend((source_id, target_id) for source_id in from_ids)
        items.append(item)

    if has_top_level_transitions and any_from_key_present:
        raise GraphValidationError(
            "Cannot mix the legacy top-level 'transitions:' key with "
            "per-step 'from:' declarations in the same file — use one "
            "style consistently."
        )

    if has_top_level_transitions:
        for tr_data in data.get("transitions") or []:
            if (
                not isinstance(tr_data, dict)
                or not isinstance(tr_data.get("source"), str)
                or not isinstance(tr_data.get("target"), str)
            ):
                raise GraphValidationError(
                    f"Invalid transition entry: expected a mapping with "
                    f"string 'source'/'target' keys, got '{tr_data}' instead"
                )
            pending_transitions.append((tr_data["source"], tr_data["target"]))

    return items, pending_transitions


def construct_workflow(
    item: dict, workflow_id: str, yaml_path_prefix: str = ""
) -> tuple[Workflow | None, list[Diagnostic]]:
    """Attempt to construct one `NfPipeline`/`NfModule` from a raw dict
    (discriminated on `type`). Returns `(workflow, [])` on success, or
    `(None, diagnostics)` on failure. yaml_path_prefix is forwarded to
    diagnostics_from_pydantic_error. Pass "steps.<id>." when this
    workflow is embedded in a whole config or leave it empty for
    an isolated snippet.
    """
    try:
        if item.get("type") == WorkflowType.NF_MODULE:
            return NfModule(**item), []
        return NfPipeline(**item), []
    except ValidationError as e:
        return None, diagnostics_from_pydantic_error(e, workflow_id=workflow_id, yaml_path_prefix=yaml_path_prefix)


def validated_workflow(
    data: dict, warnings: list[Diagnostic] | None = None, project_dir: Path | None = None
) -> Workflow:
    """Construct and fully validate a single workflow from a flat, raw dict
    (`id` is optional and will be generated).
    Runs the same tier-0/1 construction plus tier-2 dynamic checks
    a workflow gets as part of a full config build. Returns the validated
    Workflow, or raises `GraphValidationError`/`ConfigValidationError`.

    Warnings are appended to `warnings` when given, else logged. Relative
    `params_file`/`nf_config` are looked up in `project_dir` (default: the
    current directory).
    """
    if not data:
        raise GraphValidationError("No config data provided")
    if not isinstance(data, dict):
        raise GraphValidationError(f"Expected a flat mapping, got {type(data).__name__!r}")
    legacy = _legacy_section_warnings(data)
    if warnings is None:
        log_warnings(legacy)
    else:
        warnings.extend(legacy)
    wf, diagnostics = construct_workflow(data, data.get("id", "<unknown>"))
    if wf is None:
        raise ConfigValidationError(diagnostics)
    dynamic_diagnostics = run_dynamic_checks(with_absolute_config_paths(wf, project_dir), previous=None)
    errors = [d for d in dynamic_diagnostics if d.severity == Severity.ERROR]
    found_warnings = [d for d in dynamic_diagnostics if d.severity == Severity.WARNING]
    if errors:
        raise ConfigValidationError(errors, warnings=found_warnings)
    if warnings is None:
        log_warnings(found_warnings)
    else:
        warnings.extend(found_warnings)
    return wf


def validated_globals(data: dict, project_dir: Path | None = None) -> GlobalOptions:
    """Construct and validate a `GlobalOptions` block from a flat, raw dict.
    Returns the validated `GlobalOptions`, or raises
    `GraphValidationError`/`ConfigValidationError`. A relative `nf_config` is
    looked up in `project_dir` (default: the current directory).
    """
    if not data:
        raise GraphValidationError("No config data provided")
    if not isinstance(data, dict):
        raise GraphValidationError(f"Expected a flat mapping, got {type(data).__name__!r}")
    try:
        log_warnings(_legacy_section_warnings(data))
        globals_ = GlobalOptions(**data)
    except ValidationError as e:
        raise ConfigValidationError(diagnostics_from_pydantic_error(e, workflow_id=None)) from e
    missing = check_config_files(globals_, project_dir, yaml_path_prefix="")
    if missing:
        raise ConfigValidationError(missing)
    return globals_


def validated_workflow_from_file(cfg_file: Path, warnings: list[Diagnostic] | None = None) -> Workflow:
    """Read `cfg_file` as YAML and validate it as a standalone workflow
    snippet. See `validated_workflow`."""
    with open(cfg_file) as fh:
        data = yaml.safe_load(fh)
    return validated_workflow(data, warnings, project_dir=Path(cfg_file).resolve().parent)


def validated_globals_from_file(cfg_file: Path) -> GlobalOptions:
    """Read `cfg_file` as YAML and validate it as a standalone globals
    snippet. See `validated_globals`."""
    with open(cfg_file) as fh:
        data = yaml.safe_load(fh)
    return validated_globals(data, project_dir=Path(cfg_file).resolve().parent)


def parse_inputs(data: dict, config_version: str) -> tuple[dict[str, InputDefinition], list[Diagnostic]]:
    """Parse the config's `inputs:` section. Returns the definitions that
    parsed and a diagnostic per problem (malformed entries, or `inputs:` or
    `${inputs:...}` in a config version that predates them)."""
    version_diagnostics = _input_refs_before_inputs(data, config_version)
    definitions, diagnostics = _parse_inputs_section(data, config_version)
    return definitions, version_diagnostics + diagnostics


def _input_refs_before_inputs(data: dict, config_version: str) -> list[Diagnostic]:
    if Version(config_version) >= Version(INPUTS_MIN_CONFIG_VERSION):
        return []
    workflows = data.get(STEPS_KEY)
    if isinstance(workflows, dict):
        items = [(str(k), v) for k, v in workflows.items()]
    elif isinstance(workflows, list):
        items = [(str(w.get("id", "")), w) for w in workflows if isinstance(w, dict)]
    else:
        return []
    diagnostics = []
    for wf_id, wf in items:
        params = wf.get("params") if isinstance(wf, dict) else None
        for key, value in (params or {}).items() if isinstance(params, dict) else ():
            if isinstance(value, str) and INPUT_REF_PATTERN.search(value):
                diagnostics.append(
                    Diagnostic(
                        workflow_id=wf_id,
                        field=f"params.{key}",
                        yaml_path=f"steps.{wf_id}.params.{key}",
                        message=f"'${{inputs:...}}' needs config_version {INPUTS_MIN_CONFIG_VERSION} or later",
                        severity=Severity.ERROR,
                    )
                )
    return diagnostics


def _parse_inputs_section(data: dict, config_version: str) -> tuple[dict[str, InputDefinition], list[Diagnostic]]:
    raw = data.get("inputs")
    if raw is None:
        return {}, []
    if not isinstance(raw, dict):
        return {}, [
            Diagnostic(
                workflow_id=None,
                field="inputs",
                yaml_path="inputs",
                message=f"'inputs:' must be a mapping keyed by input name, got {type(raw).__name__!r}",
                severity=Severity.ERROR,
            )
        ]

    diagnostics: list[Diagnostic] = []
    if raw and Version(config_version) < Version(INPUTS_MIN_CONFIG_VERSION):
        diagnostics.append(
            Diagnostic(
                workflow_id=None,
                field="inputs",
                yaml_path="inputs",
                message=f"'inputs:' needs config_version {INPUTS_MIN_CONFIG_VERSION} or later",
                severity=Severity.ERROR,
            )
        )

    definitions: dict[str, InputDefinition] = {}
    for name, entry in raw.items():
        try:
            definitions[str(name)] = InputDefinition.from_config(entry)
        except ValidationError as e:
            diagnostics.extend(diagnostics_from_pydantic_error(e, workflow_id=None, yaml_path_prefix=f"inputs.{name}."))
        except (TypeError, ValueError) as e:
            diagnostics.append(
                Diagnostic(
                    workflow_id=None,
                    field=str(name),
                    yaml_path=f"inputs.{name}",
                    message=str(e),
                    severity=Severity.ERROR,
                )
            )
    return definitions, diagnostics


def _fast_validated_graph(data: dict, project_dir: Path | None = None) -> "MetaworkflowGraph":
    """Construct a MetaworkflowGraph from a raw, parsed-YAML config dict
    raising immediately on the first problem found. (e.g. construction,
    metadata-based validation, graph topology, cross-step references)
    See `_full_validated_graph` for the variant collecting all error if possible.
    The public interface `validated_graph(data, collect_errors=True)` wraps both
    `_full_validated_graph` and `_fast_validated_graph`.
    """
    if not data:
        raise GraphValidationError("No config data provided")

    try:
        config_version = validate_config_version(data.get("config_version", ""))
    except ValueError as e:
        raise GraphValidationError(str(e)) from e

    data, steps_warnings = _with_steps_key(data)
    log_warnings(steps_warnings + legacy_key_warnings(data))
    unknown = unknown_key_diagnostics(data)
    if unknown:
        raise ConfigValidationError(unknown)

    items, pending_transitions = _extract_items_and_transitions(data)

    g = MetaworkflowGraph()
    g.project_dir = project_dir
    g.config_version = config_version

    with g.deferred_validation():
        for item in items:
            wf_id = item.get("id", "<unknown>")
            wf, diagnostics = construct_workflow(item, wf_id, yaml_path_prefix=f"steps.{wf_id}.")
            if wf is None:
                raise ConfigValidationError(diagnostics)
            g.add_workflow(wf)

        for source_id, target_id in pending_transitions:
            g.add_transition(Transition(source=source_id, target=target_id))

        if data.get("globals") is not None:
            try:
                g.global_options = GlobalOptions.model_validate(data["globals"])
            except ValidationError as e:
                raise ConfigValidationError(
                    diagnostics_from_pydantic_error(e, workflow_id=None, yaml_path_prefix="globals.")
                ) from e
            missing = check_config_files(g.global_options, project_dir)
            if missing:
                raise ConfigValidationError(missing)

        inputs, input_errors = parse_inputs(data, config_version)
        if input_errors:
            raise ConfigValidationError(input_errors)
        g.inputs = inputs
        g._inputs_touched = bool(inputs)

        _log_graph_warnings(g)

    # Reset events accumulated by add_workflow/add_transition during initial load
    g._events = []

    return g


def _full_validated_graph(data: dict, project_dir: Path | None = None) -> "MetaworkflowGraph":
    """Construct a MetaworkflowGraph from a raw, parsed-YAML config dict and
    collect every validation issue, instead of stopping early.
    Returns a valid MetaworkflowGraph if nothing was wrong, or raises one
    `ConfigValidationError` carrying every diagnostic and graph-level message
    that occured. (see also `_fast_validated_graph` for the early-stopping variant)
    Shape-errors like malformed `steps:`/`from:`/`transitions:` still raise
    immediately just as in `_fast_validated_graph`.
    The public interface `validated_graph(data, collect_errors=True)` wraps both
    `_full_validated_graph` and `_fast_validated_graph`.
    """
    if not data:
        raise GraphValidationError("No config data provided")

    graph_messages: list[str] = []
    try:
        config_version = validate_config_version(data.get("config_version", ""))
    except ValueError as e:
        graph_messages.append(str(e))
        config_version = CONFIG_VERSION_MAX

    data, warnings = _with_steps_key(data)
    warnings += legacy_key_warnings(data)
    items, pending_transitions = _extract_items_and_transitions(data, warnings)
    format_warnings = list(warnings)

    g = MetaworkflowGraph()
    g.project_dir = project_dir
    g.config_version = config_version

    diagnostics: list[Diagnostic] = unknown_key_diagnostics(data)
    attempted_ids = {item.get("id") for item in items}
    constructed: list[Workflow] = []
    for item in items:
        wf_id = item.get("id", "<unknown>")
        wf, item_diagnostics = construct_workflow(item, wf_id, yaml_path_prefix=f"steps.{wf_id}.")
        if wf is None:
            diagnostics.extend(item_diagnostics)
            continue
        constructed.append(wf)
        g.G.add_node(wf.id, workflow=wf)

    for source_id, target_id in pending_transitions:
        if source_id not in g.G or target_id not in g.G:
            # A missing endpoint that was attempted but failed to construct is
            # already reported above. re-reporting it as "unknown node" would
            # be a confusing secondary symptom of the same problem. Only a
            # genuinely undeclared id gets its own message here.
            never_declared = [i for i in (source_id, target_id) if i not in g.G and i not in attempted_ids]
            if never_declared:
                graph_messages.append(f"Edge refers to nonexistent node: {source_id}->{target_id}")
            continue
        g.G.add_edge(
            source_id,
            target_id,
            transition=Transition(source=source_id, target=target_id),
        )

    try:
        g.validate_graph_topology()
    except GraphValidationError as e:
        graph_messages.append(str(e))

    # Inputs first: a reference may point at a param an input fills with `bind:`
    inputs, input_errors = parse_inputs(data, config_version)
    diagnostics.extend(input_errors)
    g.inputs = inputs

    for wf in constructed:
        try:
            g.validate_param_references(wf)
        except ConfigValidationError as e:
            diagnostics.extend(e.errors)

    input_diagnostics = g.input_diagnostics()
    if inputs or any(input_refs(wf.params) for wf in constructed):  # also implicit inputs
        input_diagnostics += g.effective_inputs()[1]
    tier2_diagnostics = check_all([g.for_checks(wf) for wf in constructed])
    g.set_step_warnings(tier2_diagnostics, [wf.id for wf in constructed])
    for found in (input_diagnostics, tier2_diagnostics):
        diagnostics.extend(d for d in found if d.severity == Severity.ERROR)
        warnings.extend(d for d in found if d.severity == Severity.WARNING)

    if data.get("globals") is not None:
        try:
            g.global_options = GlobalOptions.model_validate(data["globals"])
            diagnostics.extend(check_config_files(g.global_options, project_dir))
        except ValidationError as e:
            diagnostics.extend(diagnostics_from_pydantic_error(e, workflow_id=None, yaml_path_prefix="globals."))

    diagnostics.extend(g.module_nextflow_version_diagnostics(g.global_options, g.get_workflows()))
    warnings.extend(_graph_warnings(g))

    if diagnostics or graph_messages:
        raise ConfigValidationError(errors=diagnostics, graph_messages=graph_messages, warnings=warnings)

    g.warnings = warnings
    g.format_warnings = format_warnings
    return g


# Legacy "config_file" is still accepted (models alias it to "nf_config")
_PATH_KEYS = ("nf_config", "config_file", "params_file")


def _workflow_items(data: dict) -> list[tuple[str, dict]]:
    workflows = data.get(STEPS_KEY, data.get(LEGACY_STEPS_KEY))
    if isinstance(workflows, dict):
        return [(str(k), v) for k, v in workflows.items() if isinstance(v, dict)]
    if isinstance(workflows, list):
        return [(str(w.get("id", "<unknown>")), w) for w in workflows if isinstance(w, dict)]
    return []


def _reject_relative_config_paths(data: dict) -> None:
    """Raise `ConfigValidationError` for each relative `nf_config`/`params_file`
    in `data`, a config loaded from a URL: it has no folder to be relative to."""
    sections: list[tuple[str, dict]] = []
    if isinstance(data.get("globals"), dict):
        sections.append(("globals.", data["globals"]))
    sections += [(f"steps.{wf_id}.", item) for wf_id, item in _workflow_items(data)]

    diagnostics = []
    for prefix, section in sections:
        for key in _PATH_KEYS:
            value = section.get(key)
            if not isinstance(value, str) or not value or Path(value).is_absolute():
                continue
            diagnostics.append(
                Diagnostic(
                    workflow_id=None if prefix == "globals." else prefix.split(".")[1],
                    field=key,
                    yaml_path=f"{prefix}{key}",
                    message=(
                        f"Relative path '{value}' in a config loaded from a URL: "
                        "use an absolute path, download the file, or declare it as an input"
                    ),
                    severity=Severity.ERROR,
                )
            )
    if diagnostics:
        raise ConfigValidationError(diagnostics)


def validated_graph(
    data: dict, *, collect_errors: bool = False, project_dir: Path | None = None
) -> "MetaworkflowGraph":
    """Construct a MetaworkflowGraph from a raw, parsed-YAML config dict.

    Steps can be declared as a dict keyed by id (`steps: {<id>: {...}}`,
    the preferred form) or in list notation each with an `id` key.
    Transitions, describing directed dependencies in the MetaworkflowGraph
    is defined via `from:` keys in each step definition, where a single id string
    or a list of ids is accepted.

    By default the graph construction fails fast, raising on the first parsing error
    found. For a best-effort pass that collects every problem instead of stopping
    at the first use `collect_errors=True`.

    All paths, unless they are absolute, are interpreted relative to the `project_dir`,
    where the YAML config lives. `project_dir` defaults to the current workdir.

    Deprecations: the old key names `workflows:` (for `steps:`), `config_file` and
    `profile`, the list form of `steps:` and the top-level `transitions:` key are
    still read, with a warning. Automatically fix this by opening and saving the
    config via the editor.
    """
    project_dir = (project_dir or Path.cwd()).resolve()
    if collect_errors:
        return _full_validated_graph(data, project_dir)
    return _fast_validated_graph(data, project_dir)


def is_remote_config(location: str | Path) -> bool:
    return str(location).startswith(("https://", "http://"))


def from_file(cfg_file: str | Path, *, collect_errors: bool = False) -> "MetaworkflowGraph":
    """Read the config at `cfg_file` (a path, or an `http(s)://` URL) and
    build+validate a `MetaworkflowGraph` from it. See `validated_graph` for
    the validation contract and `collect_errors`.

    Relative paths in a local config resolve against the config's folder,
    which becomes the graph's `project_dir`. A config loaded from a URL has
    no project dir, and relative `nf_config`/`params_file` paths in it are
    an error.
    """
    if is_remote_config(cfg_file):
        response = requests.get(str(cfg_file), timeout=30)
        response.raise_for_status()
        data = yaml.safe_load(response.text)
        if isinstance(data, dict):
            _reject_relative_config_paths(data)
        if collect_errors:
            return _full_validated_graph(data)
        return _fast_validated_graph(data)

    path = Path(cfg_file)
    with open(path) as fh:
        data = yaml.safe_load(fh)
    return validated_graph(data, collect_errors=collect_errors, project_dir=path.parent.resolve())


def dump_config(g: "MetaworkflowGraph") -> dict:
    """Project a `MetaworkflowGraph` back to the config's dict shape (the
    inverse of `validated_graph`): `config_version`, `globals` and `inputs`
    (each omitted if empty), and `steps` keyed by id with each step's own `from:` list
    reconstructed from the graph's edges. Always writes the current
    dict-keyed `steps:` + per-step `from:` form (and a config_version that
    allows it), never the legacy `workflows:`, list or top-level-`transitions:`
    shapes, even if the graph was loaded from one of those."""
    from_by_target: dict[str, list[str]] = {}
    for tr in g.get_transitions():
        from_by_target.setdefault(tr.target, []).append(tr.source)

    workflows_dict = {}
    for w in g.get_workflows():
        wf_dict = dict(w.model_dump_config())
        if w.id in from_by_target:
            wf_dict["from"] = _FlowList(from_by_target[w.id])
        workflows_dict[w.id] = wf_dict

    config_dict = {
        "config_version": max(g.config_version, STEPS_MIN_CONFIG_VERSION, key=Version),
        "globals": g.global_options.model_dump(exclude_none=True) if g.global_options else None,
        "inputs": {name: _flow_bind(d.model_dump_config()) for name, d in g.inputs.items()},
        STEPS_KEY: workflows_dict,
    }

    if not config_dict["globals"]:
        del config_dict["globals"]
    if not config_dict["inputs"]:
        del config_dict["inputs"]

    return config_dict


class _FlowList(list):
    """A list that `to_file` writes in flow style: `[a, b]`."""


class _ConfigDumper(yaml.SafeDumper):
    pass


_ConfigDumper.add_representer(
    _FlowList, lambda dumper, data: dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)
)


def _flow_bind(entry: dict) -> dict:
    if "bind" in entry:
        return {**entry, "bind": _FlowList(entry["bind"])}
    return entry


SCHEMA_URL = "https://raw.githubusercontent.com/bmds-tue/nf-meta/refs/heads/main/schemas/metapipeline.schema.json"


def to_file(g: "MetaworkflowGraph", file: Path | str) -> None:
    """Write `g` to `file` as YAML (via `dump_config`; `from:` and `bind:`
    lists in flow style, `[n01, n02]`), prefixed with a
    `# yaml-language-server: $schema=...` comment pointing at the published
    JSON Schema for editor autocompletion. Overwrites `file` if it exists."""
    text = yaml.dump(dump_config(g), Dumper=_ConfigDumper, sort_keys=False)
    with open(file, "w") as fh:
        fh.write(f"# yaml-language-server: $schema={SCHEMA_URL}\n")
        fh.write(text)
