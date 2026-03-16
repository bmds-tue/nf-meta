from typing import Dict, Any, Optional
from pathlib import Path
import yaml
import logging

import networkx as nx

from .models import MetaworkflowConfig, Workflow, GlobalOptions, Transition, dump_config, CONFIG_VERSION_MAX
from .events import GraphEventHandler, Event, WorkflowAdded, WorkflowRemoved, WorkflowUpdated, TransitionAdded, TransitionRemoved, GlobalOptionsUpdated

logger = logging.getLogger()


class GraphValidationError(Exception):
    pass


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

    def _emit(self, event: Event):
        self._events.append(event)

    def pop_events(self):
        events = tuple(self._events)
        self._events = []
        return events

    @classmethod
    def from_file(cls, cfg_file: Path) -> "MetaworkflowGraph":
        with open(cfg_file) as fh:
            data = yaml.safe_load(fh)

        if not data:
            raise ValueError(f"No config data loaded from {cfg_file}")
    
        return cls.from_config(data)

    @classmethod
    def from_config(cls, cfg_dict: Dict[str, Any]) -> "MetaworkflowGraph":
        # Validate config structure using Pydantic
        cfg = MetaworkflowConfig(**cfg_dict)

        obj = cls()

        # Add workflow nodes
        for wf in cfg.workflows:
            obj.add_workflow(wf, skip_param_validation=True)

        # Add transition metadata
        for t in cfg.transitions:
            obj.add_transition(t)

        obj.global_options = cfg.globals or GlobalOptions()
        obj.config_version = cfg.config_version

        # Run graph validation
        obj.validate()

        # Reset Events added by add_workflow and add_transition methods
        obj._events = []

        return obj

    def add_workflow(self, wf: Workflow, skip_param_validation=False):
        if wf.params and not skip_param_validation:
            self.validate_param_references(wf)

        self.G.add_node(wf.id, workflow=wf.model_copy())
        self._emit(WorkflowAdded(wf))

    def update_workflow(self, wf: Workflow):
        # TODO: Skip update if node unchanged? -> adds junk to history otherwise
        if wf.params:
            self.validate_param_references(wf)

        try:
            old_wf = self.get_workflow_by_id(wf.id)
            self.G.nodes[wf.id]["workflow"] = wf.model_copy()
            self._emit(WorkflowUpdated(old_workflow=old_wf, new_workflow=wf))
        except KeyError as e:
            raise ValueError("Workflow has invalid id. Update unsuccessful!")

    def remove_workflow(self, wf_id: str, recursive=False):
        if wf_id not in self.G.nodes:
            raise ValueError("Invalid wf_id")
        
        for edge in list(self.G.in_edges(wf_id)):
            tr = self.get_transition(*edge)
            self.remove_transition(tr.id)

        for edge in list(self.G.out_edges(wf_id)):
            tr = self.get_transition(*edge)
            self.remove_transition(tr.id)

        removed_wf = self.get_workflow_by_id(wf_id)
        self.G.remove_node(wf_id)
        self._emit(WorkflowRemoved(removed_wf))

    def add_transition(self, tr: Transition):
        if tr.source not in self.G.nodes:
            raise ValueError(f"Unknown node {tr.source} found in transition {tr.source}->{tr.target}")

        if tr.target not in self.G.nodes:
            raise ValueError(f"Unknown node {tr.source} found in transition {tr.source}->{tr.target}")

        if self.G.has_edge(tr.source, tr.target):
            print("[warning] Edge already exists: {tr.source}->{tr.target}")

        self.G.add_edge(tr.source, tr.target, transition=tr.model_copy())
        self._emit(TransitionAdded(tr))

    def remove_transition(self, tr_id: str, recursive=False):
        tr = self.get_transition_by_id(tr_id)
        self.G.remove_edge(tr.source, tr.target)
        self._emit(TransitionRemoved(tr))

    def update_global_options(self, glob: GlobalOptions):
        old_globals = self.global_options
        self.global_options = glob
        self._emit(GlobalOptionsUpdated(new_globals=glob, old_globals=old_globals))

    # ===========================
    #        VALIDATION
    # ===========================
    def validate_param_references(self, wf: Workflow):
        for ref in wf.field_refs:
            if ref.referenced_wf_id not in self.G.nodes:
                raise GraphValidationError(f"Reference to unknown workflow: {ref.referenced_wf_id}")
            
            if ref.referenced_wf_id not in self.predecessors(wf):
                raise GraphValidationError(f"Reference to workflow {ref.referenced_wf_id} that is not a predecessor of {wf.id}")
            
            referenced_wf = self.get_workflow_by_id(ref.referenced_wf_id)
            d = referenced_wf.params
            if not d:
                raise GraphValidationError(f"No referencable params in workflow {referenced_wf.id}")
            
            if not ref.referenced_key:
                raise GraphValidationError(f"No param reference named in {ref.referenced_key}")

            d = d.get(ref.referenced_key, None)
            if not d:
                raise GraphValidationError(f"Reference to unresolvable param: {ref.referenced_key}")

    def validate(self):
        # Detect cycles
        if not nx.is_directed_acyclic_graph(self.G):
            cycle = nx.find_cycle(self.G)
            raise GraphValidationError(f"Workflow graph contains a cycle: {cycle}")

        # Detect missing workflow nodes
        for src, tgt in self.G.edges():
            if src not in self.G or tgt not in self.G:
                raise GraphValidationError(f"Edge refers to nonexistent node: {src}->{tgt}")

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

        print("TOCONFIG: ", self.global_options)
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
        return self.G.nodes[id].get("workflow")

    def get_transition_by_id(self, id: str) -> Transition:
        try:
            # tuple unpacking trick ;)
            matching_edge, = filter(lambda edge: self.get_transition(*edge).id == id, self.G.edges)
            return self.get_transition(*matching_edge)
        except ValueError:
            raise ValueError("Invalid or ambiguous tr_id")

    def get_transition(self, source: str, target: str) -> Transition:
        return self.G.edges[(source, target)].get("transition")

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
