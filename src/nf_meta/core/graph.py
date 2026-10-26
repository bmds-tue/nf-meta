from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import networkx as nx
from packaging.version import Version

from .models import (
    GlobalOptions,
    NfModule,
    Transition,
    Workflow,
    WorkflowReference,
    CONFIG_VERSION_MAX,
    INPUTS_MIN_CONFIG_VERSION,
)
from .events import (
    InputAdded,
    InputRemoved,
    InputUpdated,
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
from .dynamic_validation import check_all, check_inputs, log_warnings, run_dynamic_checks
from .inputs import Binding, Input, InputDefinition, input_refs
from .refs import ANY_BRACE_PATTERN, INPUT_REF_PATTERN, STEP_REF_PATTERN


MIN_NEXTFLOW_FOR_MODULES = (26, 4)


def _nextflow_too_old_for_modules(nextflow_version) -> bool:
    """Whether a configured `nextflow_version` is known to predate `nextflow
    module` (26.04). A bare major version (`26`) is not known to be too old."""
    parts = str(nextflow_version).removesuffix("-edge").split(".")
    major = int(parts[0])
    if major != MIN_NEXTFLOW_FOR_MODULES[0]:
        return major < MIN_NEXTFLOW_FOR_MODULES[0]
    return len(parts) > 1 and int(parts[1]) < MIN_NEXTFLOW_FOR_MODULES[1]


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
        # Folder that relative paths in the config resolve against; None for a
        # config loaded from a URL.
        self.project_dir: Optional[Path] = None
        self.G: nx.DiGraph = nx.DiGraph()
        self.global_options = GlobalOptions()
        self.config_version: str = CONFIG_VERSION_MAX
        self.inputs: dict[str, InputDefinition] = {}
        # Warnings found when the graph was loaded with collect_errors=True
        self.warnings: list[Diagnostic] = []
        self._events: list[Event] = []
        # None = not suspended. A set = suspended, accumulating the ids of
        # workflows touched while suspended, so deferred_validation's exit
        # can scope the batched dynamic check to only those (see validate()).
        self._validation_suspended: Optional[set[str]] = None
        self._inputs_touched = False

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
            self.validate_module_nextflow_version(self.global_options, [wf])
            diagnostics = run_dynamic_checks(self.with_input_placeholders(wf), previous=None)
            if any(d.severity == Severity.ERROR for d in diagnostics):
                raise ConfigValidationError(diagnostics)
            log_warnings(diagnostics)

        self.G.add_node(wf.id, workflow=wf.model_copy())

        try:
            if self._validation_suspended is None:
                if wf.params:
                    self.validate_param_references(wf)
                self.validate_inputs(dynamic=False)
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
            self.validate_module_nextflow_version(self.global_options, [wf])
            diagnostics = run_dynamic_checks(
                self.with_input_placeholders(wf),
                previous=self.with_input_placeholders(old_wf),  # type: ignore[arg-type]
            )
            if any(d.severity == Severity.ERROR for d in diagnostics):
                raise ConfigValidationError(diagnostics)
            log_warnings(diagnostics)
            if wf.params:
                self.validate_param_references(wf)

        self.G.nodes[wf.id]["workflow"] = wf.model_copy()
        if self._validation_suspended is None:
            try:
                self.validate_inputs(dynamic=False)
            except ConfigValidationError:
                self.G.nodes[wf.id]["workflow"] = old_wf
                raise
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
        """Replace the graph's `GlobalOptions` wholesale. Raises
        `ConfigValidationError` if `nextflow_version` is too old for the
        graph's `nf-module` steps; otherwise not validated against individual
        workflows."""
        self.validate_module_nextflow_version(glob, self.get_workflows())
        old_globals = self.global_options
        self.global_options = glob
        self._emit(GlobalOptionsUpdated(new_globals=glob, old_globals=old_globals))

    # ===========================
    #          INPUTS
    # ===========================
    def add_input(self, name: str, definition: InputDefinition):
        """Declare input `name`. Raises `ValueError` if it already exists and
        `ConfigValidationError` if it makes the graph invalid (the graph is
        then unchanged). Raises the config version to the first one that
        supports inputs if needed."""
        if name in self.inputs:
            raise ValueError(f"Input '{name}' already exists")
        self.inputs[name] = definition
        try:
            self._after_input_change([b.step_id for b in definition.bindings])
        except Exception:
            del self.inputs[name]
            raise
        self._ensure_inputs_config_version()
        self._emit(InputAdded(name, definition))

    def update_input(self, name: str, definition: InputDefinition):
        """Replace input `name`'s declaration. Same validation as `add_input`;
        raises `ValueError` if it doesn't exist."""
        if name not in self.inputs:
            raise ValueError(f"Input '{name}' does not exist")
        old = self.inputs[name]
        self.inputs[name] = definition
        affected = [b.step_id for b in (*old.bindings, *definition.bindings)]
        try:
            self._after_input_change(affected)
        except Exception:
            self.inputs[name] = old
            raise
        self._emit(InputUpdated(name, new_definition=definition, old_definition=old))

    def remove_input(self, name: str):
        """Remove input `name`. Raises `ValueError` if it doesn't exist and
        `ConfigValidationError` if a param still refers to it."""
        if name not in self.inputs:
            raise ValueError(f"Input '{name}' does not exist")
        old = self.inputs.pop(name)
        try:
            self._after_input_change([b.step_id for b in old.bindings])
        except Exception:
            self.inputs[name] = old
            raise
        self._emit(InputRemoved(name, old))

    def _after_input_change(self, affected_step_ids: list[str]) -> None:
        if self._validation_suspended is not None:
            self._validation_suspended.update(affected_step_ids)
            self._inputs_touched = True
            return
        self.validate_inputs(dynamic=True)
        workflows = [
            self.with_input_placeholders(wf)
            for wf in (self.get_workflow_by_id(i) for i in set(affected_step_ids))
            if wf is not None
        ]
        diagnostics = check_all(workflows)
        if any(d.severity == Severity.ERROR for d in diagnostics):
            raise ConfigValidationError(diagnostics)

    def _ensure_inputs_config_version(self) -> None:
        if Version(self.config_version) < Version(INPUTS_MIN_CONFIG_VERSION):
            self.config_version = INPUTS_MIN_CONFIG_VERSION

    def input_bindings(self) -> dict[str, tuple[Binding, ...]]:
        """Every input's bindings, from `bind:` and from `${inputs:<name>}`
        tokens in step params, sorted."""
        found: dict[str, set[Binding]] = {
            name: set(d.bindings) for name, d in self.inputs.items()
        }
        for wf in self.get_workflows():
            for param, names in input_refs(getattr(wf, "params", None)).items():
                for name in names:
                    found.setdefault(name, set()).add(Binding(wf.id, param))
        return {name: tuple(sorted(bindings)) for name, bindings in found.items()}

    def bound_params(self, wf_id: str) -> dict[str, str]:
        """Params of step `wf_id` filled via an input's `bind:`, as
        param → input name."""
        return {
            b.param: name
            for name, d in self.inputs.items()
            for b in d.bindings
            if b.step_id == wf_id
        }

    def with_input_placeholders(self, wf: Workflow) -> Workflow:
        """`wf` with a `${inputs:<name>}` placeholder for every param filled via
        `bind:` that has no value of its own, so param validation treats it as
        set."""
        missing = {
            param: f"${{inputs:{name}}}"
            for param, name in self.bound_params(wf.id).items()
            if param not in (wf.params or {})
        }
        if not missing:
            return wf
        return wf.model_copy(update={"params": {**(wf.params or {}), **missing}})

    def effective_inputs(self) -> tuple[dict[str, Input], list[Diagnostic]]:
        """Every input with its effective schema (inherited from the params it
        fills; needs their schemas, so this may use the network), plus the
        problems found doing so."""
        bindings = self.input_bindings()
        declared = {b for d in self.inputs.values() for b in d.bindings}
        whole_value = set(declared)
        for wf in self.get_workflows():
            for param, value in (getattr(wf, "params", None) or {}).items():
                if isinstance(value, str) and INPUT_REF_PATTERN.fullmatch(value):
                    whole_value.add(Binding(wf.id, param))
        workflows = {wf.id: wf for wf in self.get_workflows()}
        return check_inputs(
            {n: d for n, d in self.inputs.items()},
            {n: b for n, b in bindings.items() if n in self.inputs},
            whole_value,
            declared,
            workflows,
            self.project_dir,
        )

    def input_diagnostics(self) -> list[Diagnostic]:
        """Problems with inputs that need no network: bindings to missing
        steps, references to undeclared inputs, params bound twice (errors);
        unused inputs and bound params that also have their own value
        (warnings)."""
        diagnostics: list[Diagnostic] = []

        def add(message, *, name=None, wf_id=None, param=None, severity=Severity.ERROR):
            if wf_id is not None:
                field, yaml_path = f"params.{param}", f"workflows.{wf_id}.params.{param}"
            else:
                field = "bind" if param else ""
                yaml_path = f"inputs.{name}.bind" if param else f"inputs.{name}"
            diagnostics.append(
                Diagnostic(
                    workflow_id=wf_id,
                    field=field,
                    yaml_path=yaml_path,
                    message=message,
                    severity=severity,
                )
            )

        bindings = self.input_bindings()
        for name, found in bindings.items():
            if name not in self.inputs:
                for b in found:
                    add(f"Reference to undeclared input '{name}'", wf_id=b.step_id, param=b.param)

        owners: dict[Binding, set[str]] = {}
        for name, found in bindings.items():
            for b in found:
                owners.setdefault(b, set()).add(name)
        for b, names in sorted(owners.items()):
            if len(names) > 1:
                add(
                    f"Param '{b}' is bound to more than one input: {', '.join(sorted(names))}",
                    wf_id=b.step_id if b.step_id in self.G else None,
                    name=sorted(names)[0],
                    param=b.param,
                )

        for name, definition in self.inputs.items():
            if not bindings.get(name):
                add(f"Input '{name}' is not used by any step", name=name, severity=Severity.WARNING)
            for b in definition.bindings:
                wf = self.get_workflow_by_id(b.step_id)
                if wf is None:
                    add(
                        f"Input '{name}' is bound to '{b}', but there is no step '{b.step_id}'",
                        name=name,
                        param=b.param,
                    )
                    continue
                value = (getattr(wf, "params", None) or {}).get(b.param)
                if value is not None and value != f"${{inputs:{name}}}":
                    add(
                        f"Param '{b}' has its own value but is bound to input '{name}'; "
                        "the input's value is used",
                        wf_id=b.step_id,
                        param=b.param,
                        severity=Severity.WARNING,
                    )
        return diagnostics

    def validate_inputs(self, dynamic: bool = True):
        """Raise `ConfigValidationError` for any input error (see
        `input_diagnostics`, and with `dynamic`, `effective_inputs`); log
        warnings."""
        if not self.inputs and not any(
            input_refs(getattr(wf, "params", None)) for wf in self.get_workflows()
        ):
            return
        diagnostics = self.input_diagnostics()
        if dynamic and self.inputs:
            diagnostics += self.effective_inputs()[1]
        if any(d.severity == Severity.ERROR for d in diagnostics):
            raise ConfigValidationError(
                [d for d in diagnostics if d.severity == Severity.ERROR]
            )
        log_warnings(diagnostics)

    # ===========================
    #        VALIDATION
    # ===========================
    def validate_param_references(self, wf: Workflow):
        """Check that every `${...}` token in `wf.params` is a well-formed step
        or input reference, and that every `${wf_id:params:key}` reference
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
        for key, value in (getattr(wf, "params", None) or {}).items():
            for token in ANY_BRACE_PATTERN.findall(str(value)):
                if STEP_REF_PATTERN.fullmatch(token) or INPUT_REF_PATTERN.fullmatch(token):
                    continue
                hint = ""
                if token.startswith("${input:"):
                    hint = f" Did you mean '${{inputs:{token[len('${input:'):]}'?"
                diagnostics.append(
                    Diagnostic(
                        workflow_id=wf.id,
                        field=f"params.{key}",
                        yaml_path=f"workflows.{wf.id}.params.{key}",
                        message=(
                            f"Invalid reference '{token}': expected "
                            "${<workflow_id>:params:<key>} or ${inputs:<name>}." + hint
                        ),
                        severity=Severity.ERROR,
                    )
                )
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

    def module_nextflow_version_diagnostics(
        self, glob: Optional[GlobalOptions], workflows: list[Workflow]
    ) -> list[Diagnostic]:
        """Return an error if `glob.nextflow_version` predates `nextflow
        module` (26.04) while `workflows` contains an `nf-module` step."""
        version = glob.nextflow_version if glob else None
        if version is None or not _nextflow_too_old_for_modules(version):
            return []
        modules = [wf.id for wf in workflows if isinstance(wf, NfModule)]
        if not modules:
            return []
        return [
            Diagnostic(
                workflow_id=None,
                field="nextflow_version",
                yaml_path="globals.nextflow_version",
                message=(
                    f"nextflow_version '{version}' is too old for nf-module steps "
                    f"({', '.join(modules)}): `nextflow module` needs Nextflow >= 26.04"
                ),
                severity=Severity.ERROR,
            )
        ]

    def validate_module_nextflow_version(
        self, glob: Optional[GlobalOptions], workflows: list[Workflow]
    ):
        """Raise `ConfigValidationError` for the problem described in
        `module_nextflow_version_diagnostics`."""
        diagnostics = self.module_nextflow_version_diagnostics(glob, workflows)
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

        self.validate_module_nextflow_version(self.global_options, self.get_workflows())
        self.validate_inputs(dynamic=bool(touched) or self._inputs_touched)
        self._inputs_touched = False

        if touched:
            # Batched, concurrent dynamic check scoped to only the workflows
            # touched while suspended — not the whole graph. A node removed
            # later in the same suspended block is filtered out (nothing to
            # check).
            raw = [self.get_workflow_by_id(n) for n in touched if n in self.G.nodes]
            workflows = [self.with_input_placeholders(wf) for wf in raw if wf is not None]
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
        except BaseException:
            # Don't validate a half-built graph: its errors would replace the
            # one being raised.
            self._validation_suspended = None
            self._inputs_touched = False
            raise
        touched = self._validation_suspended
        self._validation_suspended = None
        self.validate(touched)
