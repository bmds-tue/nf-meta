import dataclasses
import logging
from contextlib import contextmanager
from pathlib import Path

import networkx as nx
from packaging.version import Version

from .dynamic_validation import check_all, check_config_files, check_inputs, log_warnings, run_dynamic_checks
from .errors import (
    ConfigValidationError,
    Diagnostic,
    GraphValidationError,
    Severity,
)
from .events import (
    Event,
    GlobalOptionsUpdated,
    InputAdded,
    InputRemoved,
    InputUpdated,
    TransitionAdded,
    TransitionRemoved,
    WorkflowAdded,
    WorkflowRemoved,
    WorkflowUpdated,
)
from .inputs import Binding, Input, InputDefinition, input_refs
from .models import (
    CONFIG_VERSION_MAX,
    INPUTS_MIN_CONFIG_VERSION,
    GlobalOptions,
    NfModule,
    Transition,
    Workflow,
    WorkflowReference,
    with_absolute_config_paths,
)
from .refs import ANY_BRACE_PATTERN, INPUT_NAME_PATTERN, INPUT_REF_PATTERN, STEP_REF_PATTERN

logger = logging.getLogger(__name__)


def _format_version(version: tuple[int, int]) -> str:
    return f"{version[0]}.{version[1]:02d}"


class MetaworkflowGraph:
    """The in-memory representation of a metapipeline as a directed graph of
    `step` nodes, global options, and inputs.

    Mutating methods are validated and emit change on success or are rolled back
    on failure, leaving the graph always in a valid state.

    Batches of mutations are applied in a context of `deferred_validation()`
    and validated once at the end instead of after each call.

    The factory methods `nf_meta.core.config.from_file`/`validated_graph` create
    a validated MetaworkflowGraph from a YAML configuration.
    """

    def __init__(self):
        # Folder that relative paths in the config resolve against; None for a
        # config loaded from a URL.
        self.project_dir: Path | None = None
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
        self._validation_suspended: set[str] | None = None
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
        """Add a new workflow node. Raises `ValueError` if a step with its id
        already exists.

        Runs dynamic (network-backed) validation immediately unless inside
        `deferred_validation()`. Raises `ConfigValidationError` and leaves the
        graph unchanged if `wf`'s id already has unresolved param references,
        or if dynamic validation reports an error.
        """
        if wf.id in self.G:
            raise ValueError(f"A step with id '{wf.id}' already exists")
        if self._validation_suspended is not None:
            self._validation_suspended.add(wf.id)
        else:
            self.validate_module_nextflow_version(self.global_options, [wf])
            diagnostics = run_dynamic_checks(self.for_checks(wf), previous=None)
            if any(d.severity == Severity.ERROR for d in diagnostics):
                raise ConfigValidationError(diagnostics)
            log_warnings(diagnostics)

        self.G.add_node(wf.id, workflow=wf.model_copy(deep=True))

        try:
            if self._validation_suspended is None:
                if wf.params:
                    self.validate_param_references(wf)
                self.validate_inputs(dynamic=False)
            if input_refs(wf.params):
                self._ensure_inputs_config_version()
            self._emit(WorkflowAdded(wf))
        except (GraphValidationError, ConfigValidationError) as e:
            self.G.remove_node(wf.id)
            raise e

    def update_workflow(self, wf: Workflow):
        """Replaces the workflow with `wf.id` with `wf`.
        Validates in the same way as `add_workflow`.
        Raises `ValueError` if no workflow with that id exists yet.
        """
        # TODO: Skip update if node unchanged? -> adds junk to history otherwise
        if wf.id not in self.G.nodes:
            raise ValueError("Step has invalid id. Update unsuccessful!")

        old_wf = self.get_workflow_by_id(wf.id)

        if self._validation_suspended is not None:
            self._validation_suspended.add(wf.id)
        else:
            self.validate_module_nextflow_version(self.global_options, [wf])
            diagnostics = run_dynamic_checks(
                self.for_checks(wf),
                previous=self.for_checks(old_wf),  # type: ignore[arg-type]
            )
            if any(d.severity == Severity.ERROR for d in diagnostics):
                raise ConfigValidationError(diagnostics)
            log_warnings(diagnostics)
            if wf.params:
                self.validate_param_references(wf)

        self.G.nodes[wf.id]["workflow"] = wf.model_copy(deep=True)
        if self._validation_suspended is None:
            try:
                self.validate_inputs(dynamic=False)
            except ConfigValidationError:
                self.G.nodes[wf.id]["workflow"] = old_wf
                raise
        if input_refs(wf.params):
            self._ensure_inputs_config_version()
        self._emit(WorkflowUpdated(old_workflow=old_wf, new_workflow=wf))  # type: ignore

    def remove_workflow(self, wf_id: str):
        """Remove the workflow `wf_id` and every transition from or to it.

        Raises `ValueError` if `wf_id` doesn't exist. Does not remove
        workflows that only reference the removed one via `${wf_id:params:...}`,
        but would result in dangling references in that case.
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

        Raises `GraphValidationError` if either endpoint does not exist yet,
        or if adding the edge would introduce a cycle. An existing edge is left
        as it is, without an event.
        """
        self.validate_edge(tr.source, tr.target)

        if self.G.has_edge(tr.source, tr.target):
            logger.warning("Edge already exists: %s->%s", tr.source, tr.target)
            return

        self.G.add_edge(tr.source, tr.target, transition=tr.model_copy())
        self._emit(TransitionAdded(tr))

        # can only be validated after-the-fact with the node in the graph
        if self._validation_suspended is None:
            self.validate_graph_topology()

    def remove_transition(self, source: str, target: str):
        """Remove the edge `source -> target`, if present."""
        tr = self.get_transition(source, target)
        if not tr:
            return

        self.G.remove_edge(source, target)
        self._emit(TransitionRemoved(tr))

        if self._validation_suspended is None:
            source_wf = self.get_workflow_by_id(source)
            self.validate_param_references(source_wf)  # type: ignore

    def update_global_options(self, glob: GlobalOptions):
        """Replace the graph's `GlobalOptions`.
        Raises a `ConfigValidationError` if `nextflow_version` is too old for the
        graph's `nf-module` steps or any referenced config or params files
        do not exist."""
        self.validate_module_nextflow_version(glob, self.get_workflows())
        missing = check_config_files(glob, self.project_dir)
        if missing:
            raise ConfigValidationError(missing)
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
        if not INPUT_NAME_PATTERN.fullmatch(name):
            raise ValueError(f"Invalid input name '{name}': it can't be empty or contain '}}', ':' or whitespace")
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
            self.for_checks(wf) for wf in (self.get_workflow_by_id(i) for i in set(affected_step_ids)) if wf is not None
        ]
        diagnostics = check_all(workflows)
        if any(d.severity == Severity.ERROR for d in diagnostics):
            raise ConfigValidationError(diagnostics)

    def _ensure_inputs_config_version(self) -> None:
        if Version(self.config_version) < Version(INPUTS_MIN_CONFIG_VERSION):
            self.config_version = INPUTS_MIN_CONFIG_VERSION

    def all_inputs(self) -> dict[str, InputDefinition]:
        """Every input, declared or implicit: the `inputs:` declarations, plus
        an empty definition for each input that is only referenced with
        `${inputs:<name>}` as a step param's whole value."""
        result = dict(self.inputs)
        for wf in self.get_workflows():
            for value in (wf.params or {}).values():
                whole = INPUT_REF_PATTERN.fullmatch(value) if isinstance(value, str) else None
                if whole:
                    result.setdefault(whole.group(1), InputDefinition())
        return result

    def input_bindings(self) -> dict[str, tuple[Binding, ...]]:
        """Every input's bindings, from `bind:` and from `${inputs:<name>}`
        tokens in step params, sorted."""
        found: dict[str, set[Binding]] = {name: set(d.bindings) for name, d in self.inputs.items()}
        for wf in self.get_workflows():
            for param, names in input_refs(wf.params).items():
                for name in names:
                    found.setdefault(name, set()).add(Binding(wf.id, param))
        return {name: tuple(sorted(bindings)) for name, bindings in found.items()}

    def bound_params(self, wf_id: str) -> dict[str, str]:
        """Params of step `wf_id` filled via an input's `bind:`, as
        param → input name."""
        return {b.param: name for name, d in self.inputs.items() for b in d.bindings if b.step_id == wf_id}

    def for_checks(self, wf: Workflow) -> Workflow:
        """`wf` as the dynamic checks see it: with input placeholders (see
        `with_input_placeholders`) and its config files' absolute paths."""
        return with_absolute_config_paths(self.with_input_placeholders(wf), self.project_dir)

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
            for param, value in (wf.params or {}).items():
                if isinstance(value, str) and INPUT_REF_PATTERN.fullmatch(value):
                    whole_value.add(Binding(wf.id, param))
        workflows = {wf.id: wf for wf in self.get_workflows()}
        inputs, diagnostics = check_inputs(
            self.all_inputs(),
            bindings,
            whole_value,
            declared,
            workflows,
            self.project_dir,
        )
        return inputs, [self._at_reference(d, bindings) for d in diagnostics]

    def _at_reference(self, d: Diagnostic, bindings: dict[str, tuple[Binding, ...]]) -> Diagnostic:
        """`d` moved to the first param referencing its input, if it is about
        an implicit input (which has no `inputs.<name>` entry to point at)."""
        parts = d.yaml_path.split(".") if d.yaml_path else []
        if len(parts) < 2 or parts[0] != "inputs" or parts[1] in self.inputs or not bindings.get(parts[1]):
            return d
        b = bindings[parts[1]][0]
        return dataclasses.replace(
            d, workflow_id=b.step_id, field=f"params.{b.param}", yaml_path=f"steps.{b.step_id}.params.{b.param}"
        )

    def input_diagnostics(self) -> list[Diagnostic]:
        """Problems with inputs that need no network (errors): bindings to
        missing steps, `${inputs:...}` that isn't a param's whole value, an
        input bound both with `bind:` and with `${inputs:...}`, params bound
        twice; (warnings): unused inputs, bound params that also have their
        own value."""
        diagnostics: list[Diagnostic] = []

        def add(message, *, name=None, wf_id=None, param=None, severity=Severity.ERROR):
            if wf_id is not None:
                field, yaml_path = f"params.{param}", f"steps.{wf_id}.params.{param}"
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

        for step in self.get_workflows():
            for param, value in (step.params or {}).items():
                if not isinstance(value, str) or not INPUT_REF_PATTERN.search(value):
                    continue
                if not INPUT_REF_PATTERN.fullmatch(value):
                    token = INPUT_REF_PATTERN.search(value).group(0)  # type: ignore[union-attr]
                    add(
                        f"'{token}' must be the whole value of '{param}'; declare an input for the full value instead",
                        wf_id=step.id,
                        param=param,
                    )
                    continue
                name = INPUT_REF_PATTERN.fullmatch(value).group(1)  # type: ignore[union-attr]
                if name in self.inputs and self.inputs[name].bind:
                    add(
                        f"input '{name}' is bound with 'bind:' in inputs.{name}; bind it in one place "
                        f"(remove this reference or the 'bind:' entry)",
                        wf_id=step.id,
                        param=param,
                    )

        bindings = self.input_bindings()

        owners: dict[Binding, set[str]] = {}
        for name, found in bindings.items():
            for b in found:
                owners.setdefault(b, set()).add(name)
        for b, names in sorted(owners.items()):
            if len(names) > 1:
                in_graph = b.step_id in self.G
                add(
                    f"{'' if in_graph else f'{b} is '}bound to more than one input: {', '.join(sorted(names))}",
                    wf_id=b.step_id if in_graph else None,
                    name=sorted(names)[0],
                    param=b.param,
                )

        for name, definition in self.inputs.items():
            if not bindings.get(name):
                add("not used by any step", name=name, severity=Severity.WARNING)
            for b in definition.bindings:
                wf = self.get_workflow_by_id(b.step_id)
                if wf is None:
                    add(f"bound to '{b}', but there is no step '{b.step_id}'", name=name, param=b.param)
                    continue
                value = (wf.params or {}).get(b.param)
                if value is not None and not (isinstance(value, str) and INPUT_REF_PATTERN.search(value)):
                    add(
                        f"has its own value but is bound to input '{name}'; the input's value is used",
                        wf_id=b.step_id,
                        param=b.param,
                        severity=Severity.WARNING,
                    )
        return diagnostics

    def validate_inputs(self, dynamic: bool = True):
        """Raise `ConfigValidationError` for any input error (see
        `input_diagnostics`, and with `dynamic`, `effective_inputs`); log
        warnings."""
        if not self.inputs and not any(input_refs(wf.params) for wf in self.get_workflows()):
            return
        diagnostics = self.input_diagnostics()
        if dynamic:
            diagnostics += self.effective_inputs()[1]
        if any(d.severity == Severity.ERROR for d in diagnostics):
            raise ConfigValidationError([d for d in diagnostics if d.severity == Severity.ERROR])
        log_warnings(diagnostics)

    # ===========================
    #        VALIDATION
    # ===========================
    def validate_param_references(self, wf: Workflow):
        """Check that every `${...}` token in `wf.params` is a well-formed step
        or input reference, and that every `${wf_id:params:key}` reference
        points at a real, already-resolvable predecessor param.

        Raises `ConfigValidationError` (carrying one `Diagnostic` per bad
        reference) if a param value contains more than one step reference, or
        a reference targets an unknown workflow, a workflow that isn't
        actually a predecessor of `wf`, or a param with no value (a param
        filled by a `bind:` input counts as having one).
        """

        def diagnostic(ref, message: str) -> Diagnostic:
            field = f"params.{ref.source_key}" if isinstance(ref, WorkflowReference) else "params"
            return Diagnostic(
                workflow_id=ref.source_wf_id,
                field=field,
                yaml_path=f"steps.{ref.source_wf_id}.{field}",
                message=message,
                severity=Severity.ERROR,
            )

        diagnostics: list[Diagnostic] = []
        for key, value in (wf.params or {}).items():
            step_refs = STEP_REF_PATTERN.findall(value) if isinstance(value, str) else []
            if len(step_refs) > 1:
                diagnostics.append(
                    Diagnostic(
                        workflow_id=wf.id,
                        field=f"params.{key}",
                        yaml_path=f"steps.{wf.id}.params.{key}",
                        message=(
                            f"'{key}' contains {len(step_refs)} references; a param value can contain one "
                            "reference to another step's param, with text around it"
                        ),
                        severity=Severity.ERROR,
                    )
                )
            for token in ANY_BRACE_PATTERN.findall(str(value)):
                if STEP_REF_PATTERN.fullmatch(token) or INPUT_REF_PATTERN.fullmatch(token):
                    continue
                hint = ""
                if token.startswith("${input:"):
                    hint = f" Did you mean '${{inputs:{token[len('${input:') :]}'?"
                diagnostics.append(
                    Diagnostic(
                        workflow_id=wf.id,
                        field=f"params.{key}",
                        yaml_path=f"steps.{wf.id}.params.{key}",
                        message=(
                            f"Invalid reference '{token}': expected "
                            "${<step_id>:params:<key>} or ${inputs:<name>}." + hint
                        ),
                        severity=Severity.ERROR,
                    )
                )
        for ref in wf.field_refs:
            if ref.namespace != "params":
                continue  # output references not yet validated
            referenced_wf = self.get_workflow_by_id(ref.target_wf_id)
            if not referenced_wf:
                diagnostics.append(diagnostic(ref, f"Reference to unknown step: {ref.target_wf_id}"))
                continue

            if ref.target_wf_id not in list(self.G.predecessors(wf.id)):
                diagnostics.append(
                    diagnostic(
                        ref,
                        f"Reference to step {ref.target_wf_id} that is not a predecessor of {wf.id}",
                    )
                )
                continue

            # A param filled by a `bind:` input has a value at run time too
            referenced_params = self.with_input_placeholders(referenced_wf).params
            if not referenced_params or not ref.target_key:
                diagnostics.append(diagnostic(ref, f"No referencable params in step {referenced_wf.id}"))
                continue

            if not referenced_params.get(ref.target_key):
                diagnostics.append(diagnostic(ref, f"Reference to unresolvable param: {ref.target_key}"))

        if diagnostics:
            raise ConfigValidationError(diagnostics)

    def module_nextflow_version_diagnostics(
        self, glob: GlobalOptions | None, workflows: list[Workflow]
    ) -> list[Diagnostic]:
        """Return an error if `glob.nextflow_version` predates `nextflow
        module` (26.04) while `workflows` contains an `nf-module` step."""
        if glob is None or not glob.nextflow_version_below(NfModule.MIN_NEXTFLOW_VERSION):
            return []
        version = glob.nextflow_version
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
                    f"({', '.join(modules)}): `nextflow module` needs Nextflow >= "
                    f"{_format_version(NfModule.MIN_NEXTFLOW_VERSION)}"
                ),
                severity=Severity.ERROR,
            )
        ]

    def validate_module_nextflow_version(self, glob: GlobalOptions | None, workflows: list[Workflow]):
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
            raise GraphValidationError(f"The steps contain a cycle: {cycle}")

    def validate_edge(self, src, tgt):
        """Raise `GraphValidationError` if `src` or `tgt` isn't a node in the graph."""
        if src not in self.G or tgt not in self.G:
            raise GraphValidationError(f"Edge refers to nonexistent node: {src}->{tgt}")

    def validate(self, touched: set[str] | None = None):
        """Validate the graph topology, edges, workflow
        ids, and every workflow's param references.

        Pass a set of workflow ids to `touched` to also run a
        dynamic (network-backed) validation, e.g. for use after a `deferred_validation()`
        context. Raises `GraphValidationError` for the first structural problem (cycle,
        dangling edge, bad id) or bad reference.
        Raise a `ConfigValidationError` for collected errors with the Nextflow version,
        input and param checks.
        """
        self.validate_graph_topology()

        # Detect missing workflow nodes
        for src, tgt in self.G.edges():
            self.validate_edge(src, tgt)

        # Ensure workflow IDs are valid (non-empty)
        for n in self.G.nodes:
            if not isinstance(n, str) or not n:
                raise GraphValidationError("Step id must be a non-empty string.")

        for n in self.G.nodes:
            wf = self.get_workflow_by_id(n)
            self.validate_param_references(wf)  # type: ignore

        # The remaining checks report together, so one save shows every problem
        diagnostics = list(self.module_nextflow_version_diagnostics(self.global_options, self.get_workflows()))
        try:
            self.validate_inputs(dynamic=bool(touched) or self._inputs_touched)
        except ConfigValidationError as e:
            diagnostics += e.errors
        self._inputs_touched = False

        if touched:
            # Batched, concurrent dynamic check scoped to only the workflows
            # touched while suspended, instead of the whole graph.
            # Non-existent workflow-ids are ignored here
            raw = [self.get_workflow_by_id(n) for n in touched if n in self.G.nodes]
            workflows = [self.for_checks(wf) for wf in raw if wf is not None]
            diagnostics += check_all(workflows)
        if any(d.severity == Severity.ERROR for d in diagnostics):
            raise ConfigValidationError([d for d in diagnostics if d.severity == Severity.ERROR])
        log_warnings([d for d in diagnostics if d.severity == Severity.WARNING])

    # ===========================
    #        UTILITIES
    # ===========================
    def get_workflow_by_id(self, wf_id: str) -> Workflow | None:
        """Return the workflow with this id, or `None` if it doesn't exist."""
        try:
            return self.G.nodes[wf_id].get("workflow")
        except KeyError:
            return None

    def get_transition(self, source: str, target: str) -> Transition | None:
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
        start: str | None = None,
        target: str | None = None,
        workflows: list[Workflow] | None = None,
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

        Can be nested (a `Transaction` containing an edit that applies its
        own): only the outermost batch validates, once, at its end.
        """
        if self._validation_suspended is not None:
            # Already deferred: the outer batch records the changes and validates
            yield self
            return
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
