from contextlib import contextmanager
from typing import Optional
from pathlib import Path
import logging

import networkx as nx
import yaml
from pydantic import ValidationError

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
from .events import (
    Event,
    WorkflowAdded,
    WorkflowRemoved,
    WorkflowUpdated,
    TransitionAdded,
    TransitionRemoved,
    GlobalOptionsUpdated,
)
from .errors import (
    ConfigValidationError,
    GraphValidationError,
    Severity,
    WorkflowReferenceError,
    WorkflowReferenceErrors,
    diagnostics_from_pydantic_error,
)
from .dynamic_validation import check_all, log_warnings, run_dynamic_checks

logger = logging.getLogger()


class MetaworkflowGraph:
    """
    A wrapper around networkx.DiGraph that provides:
    - validation
    - config ↔ graph conversion
    - utilities for workflow orchestration
    """

    def __init__(self):
        self.G: nx.DiGraph = nx.DiGraph()
        self.global_options = GlobalOptions()
        self.config_version: str = CONFIG_VERSION_MAX
        self._events: list[Event] = []
        # None = not suspended. A set = suspended, accumulating the ids of
        # workflows touched while suspended, so deferred_validation's exit
        # can scope the batched dynamic check to only those (see validate()).
        self._validation_suspended: Optional[set[str]] = None

    def _emit(self, event: Event):
        self._events.append(event)

    def pop_events(self):
        events = tuple(self._events)
        self._events = []
        return events

    def add_workflow(self, wf: Workflow):
        if self._validation_suspended is not None:
            self._validation_suspended.add(wf.id)
        else:
            diagnostics = run_dynamic_checks(wf, previous=None)
            if any(d.severity == Severity.ERROR for d in diagnostics):
                raise ConfigValidationError(diagnostics)
            log_warnings(diagnostics)

        self.G.add_node(wf.id, workflow=wf.model_copy())

        try:
            if wf.params and self._validation_suspended is None:
                self.validate_param_references(wf)
            self._emit(WorkflowAdded(wf))
        except GraphValidationError as e:
            self.G.remove_node(wf.id)
            raise e

    def update_workflow(self, wf: Workflow):
        # TODO: Skip update if node unchanged? -> adds junk to history otherwise
        if wf.id not in self.G.nodes:
            raise ValueError("Workflow has invalid id. Update unsuccessful!")

        old_wf = self.get_workflow_by_id(wf.id)

        if self._validation_suspended is not None:
            self._validation_suspended.add(wf.id)
        else:
            diagnostics = run_dynamic_checks(wf, previous=old_wf)
            if any(d.severity == Severity.ERROR for d in diagnostics):
                raise ConfigValidationError(diagnostics)
            log_warnings(diagnostics)
            if wf.params:
                self.validate_param_references(wf)

        self.G.nodes[wf.id]["workflow"] = wf.model_copy()
        self._emit(WorkflowUpdated(old_workflow=old_wf, new_workflow=wf))  # type: ignore

    def remove_workflow(self, wf_id: str, recursive=False):
        if wf_id not in self.G.nodes:
            raise ValueError("Invalid wf_id")

        for edge in list(self.G.in_edges(wf_id)):
            self.remove_transition(*edge)

        for edge in list(self.G.out_edges(wf_id)):
            self.remove_transition(*edge)

        removed_wf = self.get_workflow_by_id(wf_id)
        self.G.remove_node(wf_id)
        self._emit(WorkflowRemoved(removed_wf))  # type: ignore

    def add_transition(self, tr: Transition):
        self.validate_edge(tr.source, tr.target)

        if self.G.has_edge(tr.source, tr.target):
            print(f"[warning] Edge already exists: {tr.source}->{tr.target}")

        self.G.add_edge(tr.source, tr.target, transition=tr.model_copy())
        self._emit(TransitionAdded(tr))

        # can only be validated after-the-fact with the node in the graph
        if self._validation_suspended is None:
            self.validate_graph_topology()

    def remove_transition(self, source: str, target: str):
        tr = self.get_transition(source, target)
        if not tr:
            return

        self.G.remove_edge(source, target)
        self._emit(TransitionRemoved(tr))

        if self._validation_suspended is None:
            source_wf = self.get_workflow_by_id(source)
            self.validate_param_references(source_wf)  # type: ignore

    def update_global_options(self, glob: GlobalOptions):
        old_globals = self.global_options
        self.global_options = glob
        self._emit(GlobalOptionsUpdated(new_globals=glob, old_globals=old_globals))

    # ===========================
    #        VALIDATION
    # ===========================
    def validate_param_references(self, wf: Workflow):
        errors = []
        for ref in wf.field_refs:
            if ref.namespace != "params":
                continue  # output references not yet validated
            referenced_wf = self.get_workflow_by_id(ref.target_wf_id)
            if not referenced_wf:
                errors.append(
                    WorkflowReferenceError(
                        ref, f"Reference to unknown workflow: {ref.target_wf_id}"
                    )
                )
                continue

            if ref.target_wf_id not in list(self.G.predecessors(wf.id)):
                errors.append(
                    WorkflowReferenceError(
                        ref,
                        f"Reference to workflow {ref.target_wf_id} that is not a predecessor of {wf.id}",
                    )
                )
                continue

            if not referenced_wf.params or not ref.target_key:
                errors.append(
                    WorkflowReferenceError(
                        ref, f"No referencable params in workflow {referenced_wf.id}"
                    )
                )
                continue

            if not referenced_wf.params.get(ref.target_key):
                errors.append(
                    WorkflowReferenceError(
                        ref, f"Reference to unresolvable param: {ref.target_key}"
                    )
                )

        if errors:
            raise WorkflowReferenceErrors(errors)

    def validate_graph_topology(self):
        # Detect cycles
        if not nx.is_directed_acyclic_graph(self.G):
            cycle = nx.find_cycle(self.G)
            raise GraphValidationError(f"Workflow graph contains a cycle: {cycle}")

    def validate_edge(self, src, tgt):
        if src not in self.G or tgt not in self.G:
            raise GraphValidationError(f"Edge refers to nonexistent node: {src}->{tgt}")

    def validate(self, touched: Optional[set[str]] = None):
        self.validate_graph_topology()

        # Detect missing workflow nodes
        for src, tgt in self.G.edges():
            self.validate_edge(src, tgt)

        # Ensure workflow IDs are valid (non-empty)
        for n in self.G.nodes:
            if not isinstance(n, str) or not n:
                raise GraphValidationError("Workflow id must be a non-empty string.")

        for n in self.G.nodes:
            wf = self.get_workflow_by_id(n)
            self.validate_param_references(wf)  # type: ignore

        if touched:
            # Batched, concurrent dynamic check scoped to only the workflows
            # touched while suspended — not the whole graph. A node removed
            # later in the same suspended block is filtered out (nothing to
            # check).
            raw = [self.get_workflow_by_id(n) for n in touched if n in self.G.nodes]
            workflows = [wf for wf in raw if wf is not None]
            diagnostics = check_all(workflows)
            if any(d.severity == Severity.ERROR for d in diagnostics):
                raise ConfigValidationError(diagnostics)
            log_warnings(diagnostics)

    # ===========================
    #        UTILITIES
    # ===========================
    def get_workflow_by_id(self, id: str) -> Optional[Workflow]:
        try:
            return self.G.nodes[id].get("workflow")
        except KeyError:
            return None

    def get_transition(self, source: str, target: str) -> Optional[Transition]:
        try:
            return self.G.edges[(source, target)].get("transition")
        except KeyError:
            return None

    def get_transitions(self) -> list[Transition]:
        return [self.get_transition(*e) for e in self.G.edges]  # type: ignore

    def get_workflows(self) -> list[Workflow]:
        return [self.get_workflow_by_id(n) for n in self.G.nodes]  # type: ignore

    def get_workflows_sorted(self) -> list[Workflow]:
        """Returns workflows in valid execution order."""
        nodes_sorted = list(nx.topological_sort(self.G))
        workflows = [self.get_workflow_by_id(n) for n in nodes_sorted]
        return workflows  # type: ignore

    def subset_workflows(
        self,
        start: Optional[str] = None,
        target: Optional[str] = None,
        workflows: Optional[list[Workflow]] = None,
    ):

        if workflows is None:
            workflows = self.get_workflows_sorted()

        if not len(workflows):
            return []

        if start:
            fw_reachable = nx.descendants(self.G, start) | {start}
            workflows = [wf for wf in workflows if wf.id in fw_reachable]

        if target:
            bw_reachable = nx.ancestors(self.G, target) | {target}
            workflows = [wf for wf in workflows if wf.id in bw_reachable]

        return workflows

    def get_start_workflow(self) -> Optional[Workflow]:
        """
        Return the first order in topological sorting or None if no nodes exist
        """
        workflows_sorted = self.get_workflows_sorted()
        if not len(workflows_sorted):
            return None
        else:
            return workflows_sorted[0]

    def successors(self, wf: Workflow) -> list[Workflow]:
        return [self.get_workflow_by_id(n) for n in self.G.successors(wf.id)]  # type: ignore

    def predecessors(self, wf: Workflow) -> list[Workflow]:
        return [self.get_workflow_by_id(n) for n in self.G.predecessors(wf.id)]  # type: ignore

    @contextmanager
    def deferred_validation(self):
        """
        Suspend per-operation validation; on exit, run a full graph
        validation plus a single batched, concurrent dynamic-check pass
        scoped to the workflows touched while suspended (not the whole
        graph).
        """
        self._validation_suspended = set()
        try:
            yield self
        finally:
            touched = self._validation_suspended
            self._validation_suspended = None
            self.validate(touched)


# ---------------------------------------------------------------------------
# Construction / serialization — free functions, not methods
#
# MetaworkflowGraph itself stays "a validated graph with mutation methods";
# the YAML/dict-boundary concerns (parsing raw data into one, projecting one
# back to a dict) live alongside it in this module instead of on the class,
# per the retired-MetaworkflowConfig redesign. There is no longer a top-level
# pydantic model for the whole document — MetaworkflowGraph constructs each
# workflow directly, one at a time, so a single broken workflow no longer
# blocks the others from being added.
# ---------------------------------------------------------------------------


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


def from_raw_dict(data: dict) -> "MetaworkflowGraph":
    """Construct a MetaworkflowGraph directly from a raw, parsed-YAML dict.

    Constructs each workflow individually (not via one atomic list-validation
    call), so the error for a broken workflow already carries its real id —
    no need to recover it from a pydantic list-index afterward. Preserves
    today's fail-fast behavior: raises on the first bad workflow.
    """
    if not data:
        raise GraphValidationError("No config data provided")

    try:
        config_version = validate_config_version(data.get("config_version", ""))
    except ValueError as e:
        raise GraphValidationError(str(e)) from e

    raw_workflows = data.get("workflows") or {}
    items: list[dict] = []
    if isinstance(raw_workflows, dict):
        for key, item in raw_workflows.items():
            if not isinstance(item, dict):
                raise GraphValidationError(
                    f"Invalid definition of workflow {key}: Must be a key-value "
                    f"mapping, got '{item}' instead"
                )
            item = {**item}
            item.setdefault("type", WorkflowType.NF_PIPELINE)
            items.append({"id": key, **item})
    elif isinstance(raw_workflows, list):
        for item in raw_workflows:
            if isinstance(item, dict):
                item = {**item}
                item.setdefault("type", WorkflowType.NF_PIPELINE)
            items.append(item)

    g = MetaworkflowGraph()
    g.config_version = config_version

    with g.deferred_validation():
        for item in items:
            wf_id = item.get("id", "<unknown>")
            wf: Workflow
            try:
                if item.get("type") == WorkflowType.NF_MODULE:
                    wf = NfModule(**item)
                else:
                    wf = NfPipeline(**item)
            except ValidationError as e:
                raise ConfigValidationError(
                    diagnostics_from_pydantic_error(e, workflow_id=wf_id)
                ) from e
            g.add_workflow(wf)

        for tr_data in data.get("transitions") or []:
            g.add_transition(Transition(**tr_data))

        if data.get("globals") is not None:
            try:
                g.global_options = GlobalOptions(**data["globals"])
            except ValidationError as e:
                raise ConfigValidationError(
                    diagnostics_from_pydantic_error(e, workflow_id=None)
                ) from e

        _warn_about_module_executor(g)

    # Reset events accumulated by add_workflow/add_transition during initial load
    g._events = []

    return g


def from_file(cfg_file: Path) -> "MetaworkflowGraph":
    with open(cfg_file) as fh:
        data = yaml.safe_load(fh)
    return from_raw_dict(data)


def dump_config(g: "MetaworkflowGraph") -> dict:
    config_dict = {
        "config_version": g.config_version,
        "globals": g.global_options.model_dump(exclude_none=True)
        if g.global_options
        else None,
        "workflows": {
            w.id: {k: v for k, v in w.model_dump_config().items()}
            for w in g.get_workflows()
        },
        "transitions": [t.model_dump() for t in g.get_transitions()],
    }

    if not config_dict["globals"]:
        del config_dict["globals"]

    return config_dict


def to_file(g: "MetaworkflowGraph", file: Path | str) -> None:
    with open(file, "w") as fh:
        yaml.safe_dump(dump_config(g), fh, sort_keys=False)
