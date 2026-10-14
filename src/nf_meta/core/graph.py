from contextlib import contextmanager
from typing import Optional

import networkx as nx

from .models import (
    GlobalOptions,
    Transition,
    Workflow,
    WorkflowReference,
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
    Diagnostic,
    GraphValidationError,
    Severity,
)
from .dynamic_validation import check_all, log_warnings, run_dynamic_checks


class MetaworkflowGraph:
    """The in-memory representation of a metapipeline: a directed graph of
    `Workflow` nodes plus shared `GlobalOptions`.

    Mutating methods (`add_workflow`, `add_transition`, ...) validate the
    change immediately and raise `GraphValidationError`/`ConfigValidationError`
    rather than leaving the graph in an invalid state -- a failed mutation
    has no effect. Wrap a batch of mutations in `deferred_validation()` to
    validate once at the end instead of after each call.

    Construct one via `nf_meta.core.config.from_file`/`validated_graph`
    rather than composing an empty graph by hand, unless you're building it
    up programmatically from scratch.
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
        """Return and clear the events emitted by mutations since the last call.

        Used by `nf_meta.core.session.Session` to drive undo/redo history;
        most consumers don't need to call this directly.
        """
        events = tuple(self._events)
        self._events = []
        return events

    def add_workflow(self, wf: Workflow):
        """Add a new workflow node.

        Runs dynamic (network-backed) validation immediately unless inside
        `deferred_validation()`. Raises `ConfigValidationError` and leaves the
        graph unchanged if `wf`'s id already has unresolved param references,
        or if dynamic validation reports an error.
        """
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
        except (GraphValidationError, ConfigValidationError) as e:
            self.G.remove_node(wf.id)
            raise e

    def update_workflow(self, wf: Workflow):
        """Replace the workflow with `wf.id` with `wf`.

        Same validation behavior as `add_workflow`. Raises `ValueError` if no
        workflow with that id exists yet -- use `add_workflow` to create one.
        """
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
        """Remove the workflow `wf_id` and every transition touching it.

        Raises `ValueError` if `wf_id` doesn't exist. Does not remove
        workflows that only reference the removed one via `${wf_id:params:...}`
        -- those become dangling references, caught on their own next
        validation.
        """
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
        """Add an edge marking `tr.source` as a predecessor of `tr.target`.

        Raises `GraphValidationError` if either endpoint doesn't exist yet,
        or if adding the edge would introduce a cycle.
        """
        self.validate_edge(tr.source, tr.target)

        if self.G.has_edge(tr.source, tr.target):
            print(f"[warning] Edge already exists: {tr.source}->{tr.target}")

        self.G.add_edge(tr.source, tr.target, transition=tr.model_copy())
        self._emit(TransitionAdded(tr))

        # can only be validated after-the-fact with the node in the graph
        if self._validation_suspended is None:
            self.validate_graph_topology()

    def remove_transition(self, source: str, target: str):
        """Remove the edge `source -> target`, if present.

        No-op (returns without raising) if the edge doesn't exist.
        """
        tr = self.get_transition(source, target)
        if not tr:
            return

        self.G.remove_edge(source, target)
        self._emit(TransitionRemoved(tr))

        if self._validation_suspended is None:
            source_wf = self.get_workflow_by_id(source)
            self.validate_param_references(source_wf)  # type: ignore

    def update_global_options(self, glob: GlobalOptions):
        """Replace the graph's `GlobalOptions` wholesale. Not validated against
        individual workflows -- per-workflow effects (e.g. a shared `profile`)
        are only checked when that workflow is itself next validated."""
        old_globals = self.global_options
        self.global_options = glob
        self._emit(GlobalOptionsUpdated(new_globals=glob, old_globals=old_globals))

    # ===========================
    #        VALIDATION
    # ===========================
    def validate_param_references(self, wf: Workflow):
        """Check that every `${wf_id:params:key}` reference in `wf.params`
        points at a real, already-resolvable predecessor param.

        Raises `ConfigValidationError` (carrying one `Diagnostic` per bad
        reference) if any reference targets an unknown workflow, a workflow
        that isn't actually a predecessor of `wf`, or a param with no value.
        """

        def diagnostic(ref, message: str) -> Diagnostic:
            field = (
                f"params.{ref.source_key}"
                if isinstance(ref, WorkflowReference)
                else "params"
            )
            return Diagnostic(
                workflow_id=ref.source_wf_id,
                field=field,
                yaml_path=f"workflows.{ref.source_wf_id}.{field}",
                message=message,
                severity=Severity.ERROR,
            )

        diagnostics: list[Diagnostic] = []
        for ref in wf.field_refs:
            if ref.namespace != "params":
                continue  # output references not yet validated
            referenced_wf = self.get_workflow_by_id(ref.target_wf_id)
            if not referenced_wf:
                diagnostics.append(
                    diagnostic(ref, f"Reference to unknown workflow: {ref.target_wf_id}")
                )
                continue

            if ref.target_wf_id not in list(self.G.predecessors(wf.id)):
                diagnostics.append(
                    diagnostic(
                        ref,
                        f"Reference to workflow {ref.target_wf_id} that is not a predecessor of {wf.id}",
                    )
                )
                continue

            if not referenced_wf.params or not ref.target_key:
                diagnostics.append(
                    diagnostic(ref, f"No referencable params in workflow {referenced_wf.id}")
                )
                continue

            if not referenced_wf.params.get(ref.target_key):
                diagnostics.append(
                    diagnostic(ref, f"Reference to unresolvable param: {ref.target_key}")
                )

        if diagnostics:
            raise ConfigValidationError(diagnostics)

    def validate_graph_topology(self):
        """Raise `GraphValidationError` if the graph contains a cycle."""
        # Detect cycles
        if not nx.is_directed_acyclic_graph(self.G):
            cycle = nx.find_cycle(self.G)
            raise GraphValidationError(f"Workflow graph contains a cycle: {cycle}")

    def validate_edge(self, src, tgt):
        """Raise `GraphValidationError` if `src` or `tgt` isn't a node in the graph."""
        if src not in self.G or tgt not in self.G:
            raise GraphValidationError(f"Edge refers to nonexistent node: {src}->{tgt}")

    def validate(self, touched: Optional[set[str]] = None):
        """Fully re-validate the graph: topology, edge endpoints, workflow
        ids, and every workflow's param references.

        Pass `touched` (a set of workflow ids) to also run a single batched
        dynamic (network-backed) validation pass scoped to just those
        workflows -- this is what `deferred_validation()` uses on exit, rather
        than dynamic-validating the whole graph on every batch. Raises
        `GraphValidationError`/`ConfigValidationError` on the first failure
        found; does not collect all errors across the whole graph in one
        call.
        """
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
        """Return the workflow with this id, or `None` if it doesn't exist."""
        try:
            return self.G.nodes[id].get("workflow")
        except KeyError:
            return None

    def get_transition(self, source: str, target: str) -> Optional[Transition]:
        """Return the `source -> target` transition, or `None` if no such edge exists."""
        try:
            return self.G.edges[(source, target)].get("transition")
        except KeyError:
            return None

    def get_transitions(self) -> list[Transition]:
        """Return every transition in the graph, in no particular order."""
        return [self.get_transition(*e) for e in self.G.edges]  # type: ignore

    def get_workflows(self) -> list[Workflow]:
        """Return every workflow in the graph, in no particular order."""
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
        """Filter `workflows` (default: `get_workflows_sorted()`) down to the
        sub-DAG reachable from `start` and able to reach `target` (inclusive
        on both ends). Omit either bound to leave that side unrestricted."""

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
        """Return `wf`'s direct successors (workflows with `from: wf.id`)."""
        return [self.get_workflow_by_id(n) for n in self.G.successors(wf.id)]  # type: ignore

    def predecessors(self, wf: Workflow) -> list[Workflow]:
        """Return `wf`'s direct predecessors (the workflows in `wf.from`)."""
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
