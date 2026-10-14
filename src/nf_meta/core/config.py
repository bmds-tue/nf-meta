"""
Construction / serialization — free functions, not methods.

MetaworkflowGraph (core/graph.py) itself stays "a validated graph with
mutation methods"; the YAML/dict-boundary concerns (parsing raw data into one,
projecting one back to a dict, constructing individual workflows/globals) live
here instead, alongside the file/config-format boundary they're all about.
There is no top-level pydantic model for the whole document -- construction
happens directly, one workflow at a time, so a single broken workflow no
longer blocks the others from being added.
"""

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from .graph import MetaworkflowGraph
from .models import (
    GlobalOptions,
    NfModule,
    NfPipeline,
    Transition,
    Workflow,
    WorkflowType,
    validate_config_version,
    CONFIG_VERSION_MAX,
)
from .errors import (
    ConfigValidationError,
    Diagnostic,
    GraphValidationError,
    Severity,
    diagnostics_from_pydantic_error,
)
from .dynamic_validation import check_all, log_warnings, run_dynamic_checks

logger = logging.getLogger()


def _warn_about_module_executor(g: "MetaworkflowGraph") -> None:
    if g.global_options and g.global_options.config_file:
        return

    for wf in g.get_workflows():
        if not wf.type == WorkflowType.NF_MODULE:
            continue
        if wf.container_engine:  # type: ignore[union-attr]
            continue
        logger.warning(
            "Running Nextflow module(s) without specifying an executor "
            "or a global Nextflow config relies on the local environment.\n"
            "This will cause errors, if module dependencies are not "
            "available locally and breaks reproducibility"
        )


def _extract_items_and_transitions(
    data: dict,
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Normalize `workflows:`/`transitions:`/`from:` into a flat list of
    workflow-definition dicts (`type`/`id` defaulted) and a list of pending
    `(source, target)` transitions.

    Raises `GraphValidationError` immediately for malformed input shapes (a
    `workflows:` value that's neither a mapping nor a list, a non-dict item, a
    malformed `from:` value, mixed legacy-`transitions:`-and-`from:` usage, a
    malformed legacy transition entry) -- these represent invalid input, not
    ordinary per-workflow mistakes, so every caller lets them raise immediately
    rather than aggregating around them.
    """
    has_top_level_transitions = "transitions" in data
    if has_top_level_transitions:
        logger.warning(
            "Legacy top-level 'transitions:' key is deprecated -- declare each "
            "workflow's predecessors via its own 'from:' key instead. Update by "
            "opening and saving the config in the editor."
        )

    raw_workflows = data.get("workflows") or {}
    if isinstance(raw_workflows, dict):
        raw_items: list[tuple[str | None, object]] = list(raw_workflows.items())
    elif isinstance(raw_workflows, list):
        logger.warning(
            "Legacy list-format for 'workflows' is deprecated -- use the dict-"
            "format keyed by workflow id instead. Update by opening and saving the "
            "config in the editor."
        )
        raw_items = [
            (item.get("id") if isinstance(item, dict) else None, item)
            for item in raw_workflows
        ]
    else:
        raise GraphValidationError(
            f"'workflows:' must be a mapping keyed by workflow id or a list "
            f"of workflow definitions, got {type(raw_workflows).__name__!r}"
        )

    items: list[dict] = []
    pending_transitions: list[tuple[str, str]] = []
    any_from_key_present = False
    for key, item in raw_items:
        if not isinstance(item, dict):
            raise GraphValidationError(
                f"Invalid definition of workflow {key}: Must be a key-value "
                f"mapping, got '{item}' instead"
            )
        item = {**item}
        item.setdefault("type", WorkflowType.NF_PIPELINE)
        if key is not None:
            item.setdefault("id", key)  # dict form: the mapping key is authoritative
        any_from_key_present = any_from_key_present or "from" in item
        from_ids = item.pop("from", None) or []
        if isinstance(from_ids, str):
            from_ids = [from_ids]  # a single predecessor id, not wrapped in a list
        if not isinstance(from_ids, list) or not all(
            isinstance(f, str) for f in from_ids
        ):
            raise GraphValidationError(
                f"Invalid 'from' value for workflow {item.get('id', '<unknown>')}: "
                f"expected a workflow id or a list of workflow ids, got "
                f"'{from_ids}' instead"
            )
        target_id = item.get("id", "<unknown>")
        pending_transitions.extend((source_id, target_id) for source_id in from_ids)
        items.append(item)

    if has_top_level_transitions and any_from_key_present:
        raise GraphValidationError(
            "Cannot mix the legacy top-level 'transitions:' key with "
            "per-workflow 'from:' declarations in the same file — use one "
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
    `(None, diagnostics)` on failure -- a reusable building block for
    validating one workflow at a time, whether inside a full-graph build or a
    standalone snippet. yaml_path_prefix is forwarded to
    diagnostics_from_pydantic_error -- pass e.g. "workflows.<id>." when this
    workflow is embedded in a whole config; leave it empty (the default) for
    an isolated snippet.
    """
    try:
        if item.get("type") == WorkflowType.NF_MODULE:
            return NfModule(**item), []
        return NfPipeline(**item), []
    except ValidationError as e:
        return None, diagnostics_from_pydantic_error(
            e, workflow_id=workflow_id, yaml_path_prefix=yaml_path_prefix
        )


def validated_workflow(data: dict) -> Workflow:
    """Construct and fully validate a single workflow from a flat, raw dict
    (`id` optional -- the model's own `default_factory` generates one if
    omitted). Runs the same tier-0/1 construction plus tier-2 dynamic checks
    a workflow gets as part of a full config build. Returns the validated
    Workflow, or raises `GraphValidationError`/`ConfigValidationError`.
    """
    if not data:
        raise GraphValidationError("No config data provided")
    if not isinstance(data, dict):
        raise GraphValidationError(
            f"Expected a flat mapping, got {type(data).__name__!r}"
        )
    wf, diagnostics = construct_workflow(data, data.get("id", "<unknown>"))
    if wf is None:
        raise ConfigValidationError(diagnostics)
    dynamic_diagnostics = run_dynamic_checks(wf, previous=None)
    errors = [d for d in dynamic_diagnostics if d.severity == Severity.ERROR]
    if errors:
        raise ConfigValidationError(errors)
    log_warnings(dynamic_diagnostics)
    return wf


def validated_globals(data: dict) -> GlobalOptions:
    """Construct and validate a `GlobalOptions` block from a flat, raw dict.
    Returns the validated `GlobalOptions`, or raises
    `GraphValidationError`/`ConfigValidationError`.
    """
    if not data:
        raise GraphValidationError("No config data provided")
    if not isinstance(data, dict):
        raise GraphValidationError(
            f"Expected a flat mapping, got {type(data).__name__!r}"
        )
    try:
        return GlobalOptions(**data)
    except ValidationError as e:
        raise ConfigValidationError(
            diagnostics_from_pydantic_error(e, workflow_id=None)
        ) from e


def validated_workflow_from_file(cfg_file: Path) -> Workflow:
    """Read `cfg_file` as YAML and validate it as a standalone workflow
    snippet. See `validated_workflow`."""
    with open(cfg_file) as fh:
        data = yaml.safe_load(fh)
    return validated_workflow(data)


def validated_globals_from_file(cfg_file: Path) -> GlobalOptions:
    """Read `cfg_file` as YAML and validate it as a standalone globals
    snippet. See `validated_globals`."""
    with open(cfg_file) as fh:
        data = yaml.safe_load(fh)
    return validated_globals(data)


def _fast_validated_graph(data: dict) -> "MetaworkflowGraph":
    """Construct a MetaworkflowGraph from a raw, parsed-YAML config dict,
    failing fast: raises immediately on the first problem found (a workflow's
    construction, graph topology, cross-workflow references, or a tier-2
    check). See `_full_validated_graph` for the collect-everything alternative
    used by the CLI's `validate` command. Not called directly -- use
    `validated_graph(data)` (the default, `collect_errors=False`).
    """
    if not data:
        raise GraphValidationError("No config data provided")

    try:
        config_version = validate_config_version(data.get("config_version", ""))
    except ValueError as e:
        raise GraphValidationError(str(e)) from e

    items, pending_transitions = _extract_items_and_transitions(data)

    g = MetaworkflowGraph()
    g.config_version = config_version

    with g.deferred_validation():
        for item in items:
            wf_id = item.get("id", "<unknown>")
            wf, diagnostics = construct_workflow(
                item, wf_id, yaml_path_prefix=f"workflows.{wf_id}."
            )
            if wf is None:
                raise ConfigValidationError(diagnostics)
            g.add_workflow(wf)

        for source_id, target_id in pending_transitions:
            g.add_transition(Transition(source=source_id, target=target_id))

        if data.get("globals") is not None:
            try:
                g.global_options = GlobalOptions(**data["globals"])
            except ValidationError as e:
                raise ConfigValidationError(
                    diagnostics_from_pydantic_error(
                        e, workflow_id=None, yaml_path_prefix="globals."
                    )
                ) from e

        _warn_about_module_executor(g)

    # Reset events accumulated by add_workflow/add_transition during initial load
    g._events = []

    return g


def _full_validated_graph(data: dict) -> "MetaworkflowGraph":
    """Construct a MetaworkflowGraph from a raw, parsed-YAML config dict,
    collecting every problem instead of stopping at the first -- used by the
    CLI's `validate` command so one run can show a construction error, a
    dangling edge, a cycle, and reference errors together. Returns a fully
    valid MetaworkflowGraph if nothing was wrong, or raises one
    `ConfigValidationError` carrying every diagnostic and graph-level message
    found -- the same "always fully succeeds or raises" contract as
    `_fast_validated_graph`, just without stopping along the way. Shape-level
    errors (malformed `workflows:`/`from:`/`transitions:`) still raise
    immediately, same as `_fast_validated_graph` -- aggregation only applies to
    per-workflow and graph-level problems. Not called directly -- use
    `validated_graph(data, collect_errors=True)`.
    """
    if not data:
        raise GraphValidationError("No config data provided")

    graph_messages: list[str] = []
    try:
        config_version = validate_config_version(data.get("config_version", ""))
    except ValueError as e:
        graph_messages.append(str(e))
        config_version = CONFIG_VERSION_MAX

    items, pending_transitions = _extract_items_and_transitions(data)

    g = MetaworkflowGraph()
    g.config_version = config_version

    diagnostics: list[Diagnostic] = []
    attempted_ids = {item.get("id") for item in items}
    constructed: list[Workflow] = []
    for item in items:
        wf_id = item.get("id", "<unknown>")
        wf, item_diagnostics = construct_workflow(
            item, wf_id, yaml_path_prefix=f"workflows.{wf_id}."
        )
        if wf is None:
            diagnostics.extend(item_diagnostics)
            continue
        constructed.append(wf)
        g.G.add_node(wf.id, workflow=wf)

    for source_id, target_id in pending_transitions:
        if source_id not in g.G or target_id not in g.G:
            # A missing endpoint that was attempted but failed to construct is
            # already reported above -- re-reporting it as "unknown node" would
            # be a confusing secondary symptom of the same problem. Only a
            # genuinely undeclared id gets its own message here.
            never_declared = [
                i
                for i in (source_id, target_id)
                if i not in g.G and i not in attempted_ids
            ]
            if never_declared:
                graph_messages.append(
                    f"Edge refers to nonexistent node: {source_id}->{target_id}"
                )
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

    for wf in constructed:
        try:
            g.validate_param_references(wf)
        except ConfigValidationError as e:
            diagnostics.extend(e.errors)

    tier2_diagnostics = check_all(constructed)
    diagnostics.extend(d for d in tier2_diagnostics if d.severity == Severity.ERROR)
    log_warnings(tier2_diagnostics)

    if data.get("globals") is not None:
        try:
            g.global_options = GlobalOptions(**data["globals"])
        except ValidationError as e:
            diagnostics.extend(
                diagnostics_from_pydantic_error(
                    e, workflow_id=None, yaml_path_prefix="globals."
                )
            )

    _warn_about_module_executor(g)

    if diagnostics or graph_messages:
        raise ConfigValidationError(errors=diagnostics, graph_messages=graph_messages)

    return g


def validated_graph(data: dict, *, collect_errors: bool = False) -> "MetaworkflowGraph":
    """Construct a MetaworkflowGraph from a raw, parsed-YAML config dict.

    Workflows can be declared as a dict keyed by id (`workflows: {<id>: {...}}`,
    the preferred form) or as a legacy list of definitions each carrying their
    own `id`. Transitions are declared per-workflow via `from: <id>` or
    `from: [<id>, ...]`; a top-level `transitions:` key is also still accepted,
    but mixing both styles in the same file raises rather than merging them.

    Both the list-format `workflows:` and the top-level `transitions:` key are
    deprecated -- reading either logs a CLI warning. Fix by opening and saving
    the config in the editor, which always writes the current dict-keyed
    `workflows:` + per-workflow `from:` form.

    By default (`collect_errors=False`) this fails fast, raising on the first
    problem found. Pass `collect_errors=True` for a best-effort pass that
    collects every problem instead of stopping at the first -- used by the
    CLI's `validate` command.
    """
    if collect_errors:
        return _full_validated_graph(data)
    return _fast_validated_graph(data)


def from_file(cfg_file: Path, *, collect_errors: bool = False) -> "MetaworkflowGraph":
    """Read `cfg_file` as YAML and build+validate a `MetaworkflowGraph` from
    it. Reads the whole file into memory; makes no other side effects. See
    `validated_graph` for the validation contract and `collect_errors`."""
    with open(cfg_file) as fh:
        data = yaml.safe_load(fh)
    return validated_graph(data, collect_errors=collect_errors)


def dump_config(g: "MetaworkflowGraph") -> dict:
    """Project a `MetaworkflowGraph` back to the config's dict shape (the
    inverse of `validated_graph`): `config_version`, `globals` (omitted if
    empty), and `workflows` keyed by id with each workflow's own `from:` list
    reconstructed from the graph's edges. Always writes the current
    dict-keyed `workflows:` + per-workflow `from:` form, never the legacy
    list/top-level-`transitions:` shapes, even if the graph was loaded from
    one of those."""
    from_by_target: dict[str, list[str]] = {}
    for tr in g.get_transitions():
        from_by_target.setdefault(tr.target, []).append(tr.source)

    workflows_dict = {}
    for w in g.get_workflows():
        wf_dict = {k: v for k, v in w.model_dump_config().items()}
        if w.id in from_by_target:
            wf_dict["from"] = from_by_target[w.id]
        workflows_dict[w.id] = wf_dict

    config_dict = {
        "config_version": g.config_version,
        "globals": g.global_options.model_dump(exclude_none=True)
        if g.global_options
        else None,
        "workflows": workflows_dict,
    }

    if not config_dict["globals"]:
        del config_dict["globals"]

    return config_dict


SCHEMA_URL = (
    "https://raw.githubusercontent.com/bmds-tue/nf-meta/refs/heads/main/"
    "schemas/metapipeline.schema.json"
)


def to_file(g: "MetaworkflowGraph", file: Path | str) -> None:
    """Write `g` to `file` as YAML (via `dump_config`), prefixed with a
    `# yaml-language-server: $schema=...` comment pointing at the published
    JSON Schema for editor autocompletion. Overwrites `file` if it exists."""
    with open(file, "w") as fh:
        fh.write(f"# yaml-language-server: $schema={SCHEMA_URL}\n")
        yaml.safe_dump(dump_config(g), fh, sort_keys=False)
