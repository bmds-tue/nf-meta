from contextlib import contextmanager
from typing import Dict, Any, Optional
from pathlib import Path
import yaml
import logging

import networkx as nx

from .models import MetaworkflowConfig, Workflow, GlobalOptions, Transition, load_config, dump_config, CONFIG_VERSION_MAX
from .events import GraphEventHandler, Event, WorkflowAdded, WorkflowRemoved, WorkflowUpdated, TransitionAdded, TransitionRemoved, GlobalOptionsUpdated
from .errors import GraphValidationError, WorkflowReferenceError, WorkflowReferenceErrors

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
        self.global_options: Optional[GlobalOptions] = None
        self.config_version: str = CONFIG_VERSION_MAX
        self._events: list[Event] = []
        self._validation_suspended = False

    def _emit(self, event: Event):
        self._events.append(event)

    def pop_events(self):
        events = tuple(self._events)
        self._events = []
        return events

    @classmethod
    def from_file(cls, cfg_file: Path) -> "MetaworkflowGraph":
        cfg = load_config(cfg_file)

        if not cfg:
            raise ValueError(f"No config data loaded from {cfg_file}")
    
        return cls.from_config(cfg)

    @classmethod
    def from_config(cls, cfg: MetaworkflowConfig) -> "MetaworkflowGraph":
        obj = cls()

        with obj.deferred_validation():
            # Add workflow nodes
            for wf in cfg.workflows:
                obj.add_workflow(wf)

            # Add transition metadata
            for t in cfg.transitions:
                obj.add_transition(t)

            obj.global_options = cfg.globals or GlobalOptions()
            obj.config_version = cfg.config_version

        # Reset Events added by add_workflow and add_transition methods
        obj._events = []

        return obj

    def add_workflow(self, wf: Workflow):

        self.G.add_node(wf.id, workflow=wf.model_copy())

        try:
            if wf.params and not self._validation_suspended:
                self.validate_param_references(wf)
            self._emit(WorkflowAdded(wf))
        except GraphValidationError as e:
            self.G.remove_node(wf.id)
            raise e

    def update_workflow(self, wf: Workflow):
        # TODO: Skip update if node unchanged? -> adds junk to history otherwise
        if wf.params and not self._validation_suspended:
            self.validate_param_references(wf)

        if not wf.id in self.G.nodes:
            raise ValueError("Workflow has invalid id. Update unsuccessful!")

        old_wf = self.get_workflow_by_id(wf.id)
        self.G.nodes[wf.id]["workflow"] = wf.model_copy()
        self._emit(WorkflowUpdated(old_workflow=old_wf, new_workflow=wf))

    def remove_workflow(self, wf_id: str, recursive=False):
        if wf_id not in self.G.nodes:
            raise ValueError("Invalid wf_id")
        
        for edge in list(self.G.in_edges(wf_id)):
            self.remove_transition(*edge)

        for edge in list(self.G.out_edges(wf_id)):
            self.remove_transition(*edge)

        removed_wf = self.get_workflow_by_id(wf_id)
        self.G.remove_node(wf_id)
        self._emit(WorkflowRemoved(removed_wf))

    def add_transition(self, tr: Transition):
        if tr.source not in self.G.nodes:
            raise ValueError(f"Unknown node {tr.source} found in transition {tr.source}->{tr.target}")

        if tr.target not in self.G.nodes:
            raise ValueError(f"Unknown node {tr.source} found in transition {tr.source}->{tr.target}")

        if self.G.has_edge(tr.source, tr.target):
            print(f"[warning] Edge already exists: {tr.source}->{tr.target}")

        self.G.add_edge(tr.source, tr.target, transition=tr.model_copy())
        self._emit(TransitionAdded(tr))

        # can only be validated after-the-fact with the node in the graph
        if not self._validation_suspended:
            self.validate_graph_topology()

    def remove_transition(self, source: str, target: str):
        tr = self.get_transition(source, target)
        if not tr:
            return

        self.G.remove_edge(source, target)
        self._emit(TransitionRemoved(tr))

        if not self._validation_suspended:
            source_wf = self.get_workflow_by_id(source)
            self.validate_param_references(source_wf)

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
            if ref.target_wf_id not in self.G.nodes:
                errors.append(WorkflowReferenceError(ref, f"Reference to unknown workflow: {ref.target_wf_id}"))
                continue
            
            if ref.target_wf_id not in list(self.G.predecessors(wf.id)):
                errors.append(WorkflowReferenceError(ref, f"Reference to workflow {ref.target_wf_id} that is not a predecessor of {wf.id}"))
                continue

            referenced_wf = self.get_workflow_by_id(ref.target_wf_id)
            if not referenced_wf.params or not ref.target_key:
                errors.append(WorkflowReferenceError(ref, f"No referencable params in workflow {referenced_wf.id}"))
                continue
       
            if not referenced_wf.params.get(ref.target_key):
                errors.append(WorkflowReferenceError(ref, f"Reference to unresolvable param: {ref.target_key}"))
        
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

    def validate(self):
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
            self.validate_param_references(wf)

    # ===========================
    #   EXPORT BACK TO CONFIG
    # ===========================
    def to_config(self) -> Dict[str, Any]:
        workflows = self.get_workflows()
        transitions = self.get_transitions()

        return MetaworkflowConfig.model_validate({
            "config_version": self.config_version,
            "globals": self.global_options,
            "workflows": workflows,
            "transitions": transitions,
        })

    def to_file(self, file: Path|str) -> None:
        dump_config(self.to_config(), Path(file))

    # ===========================
    #        UTILITIES
    # ===========================
    def get_workflow_by_id(self, id: str) -> Workflow:
        try:
            return self.G.nodes[id].get("workflow")
        except KeyError:
            return None

    def get_transition(self, source: str, target: str) -> Transition:
        try:
            return self.G.edges[(source, target)].get("transition")
        except KeyError:
            return None

    def get_transitions(self) -> list[Transition]:
        return [self.get_transition(*e) for e in self.G.edges]

    def get_workflows(self) -> list[Workflow]:
        return [self.get_workflow_by_id(n) for n in self.G.nodes]

    def get_workflows_sorted(self) -> list[Workflow]:
        """Returns workflows in valid execution order."""
        nodes_sorted = list(nx.topological_sort(self.G))
        workflows = [self.get_workflow_by_id(n) for n in nodes_sorted]
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
        return [self.get_workflow_by_id(n) for n in self.G.successors(wf.id)]

    def predecessors(self, wf: Workflow) -> list[Workflow]:
        return [self.get_workflow_by_id(n) for n in self.G.predecessors(wf.id)]

    @contextmanager
    def deferred_validation(self):
        """
        Suspend per-operation vaidation; run a full graph validation on exit
        """
        self._validation_suspended = True
        try:
            yield self
        finally:
            self._validation_suspended = False
            self.validate()
