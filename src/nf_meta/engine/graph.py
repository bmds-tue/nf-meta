from typing import Dict, Any, Optional
from pathlib import Path
import yaml
import logging

import networkx as nx

from .models import MetaworkflowConfig, Workflow, WorkflowOptions, Transition, dump_config, CONFIG_VERSION_MAX
from .events import GraphEventHandler, Event, WorkflowAdded, WorkflowRemoved, WorkflowUpdated, TransitionAdded, TransitionUpdated, TransitionRemoved

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
        self.workflow_opts: Optional[WorkflowOptions] = None
        self.workflow_opts_custom: Optional[WorkflowOptions] = None
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
        
        return cls.from_config(data)

    @classmethod
    def from_config(cls, cfg_dict: Dict[str, Any]) -> "MetaworkflowGraph":
        # Validate config structure using Pydantic
        cfg = MetaworkflowConfig(**cfg_dict)

        obj = cls()

        # Add workflow nodes
        for wf in cfg.workflows:
            obj.G.add_node(wf.id, **wf.model_dump())

        # Add transition metadata
        for t in cfg.transitions:
            src = t.source
            tgt = t.target

            if tgt not in obj.G.nodes:
                raise ValueError(f"Unknown node {tgt} found in transition {src}->{tgt}")

            if src not in obj.G.nodes:
                raise ValueError(f"Unknown node {src} found in transition {src}->{tgt}")

            if not obj.G.has_edge(src, tgt):
                # Transition not declared in metalayout → auto-add
                # TODO: Be more specific with keys once they are stable-ish
                obj.G.add_edge(src, tgt, **t.model_dump())

        obj.workflow_opts = cfg.workflow_opts
        obj.workflow_opts_custom = cfg.workflow_opts_custom
        obj.config_version = cfg.config_version

        # Run graph validation
        obj.validate()

        return obj

    def add_workflow(self, wf: Workflow):
        self.G.add_node(wf.id, **wf.model_dump())
        self._emit(WorkflowAdded(wf))

    def update_workflow(self, wf: Workflow):
        try:
            old_wf_data = self.G.nodes[wf.id]
            self.G.nodes[wf.id].update(wf.model_dump())
            self._emit(WorkflowUpdated(old_workflow=Workflow(**old_wf_data), new_workflow=wf))
        except KeyError as e:
            raise ValueError("Workflow has invalid id. Update unsuccessful!")

    def remove_workflow(self, wf_id: str, recursive=False):
        if wf_id not in self.G.nodes:
            raise ValueError("Invalid wf_id")
        
        for edge in list(self.G.in_edges(wf_id)):
            edge_data = self.G.edges[edge]
            self.G.remove_edge(*edge)
            self._emit(TransitionRemoved(Transition(**edge_data)))

        for edge in list(self.G.out_edges(wf_id)):
            edge_data = self.G.edges[edge]
            self.G.remove_edge(*edge)
            self._emit(TransitionRemoved(Transition(**edge_data)))

        node_data = self.G.nodes[wf_id]
        self.G.remove_node(wf_id)
        self._emit(WorkflowRemoved(Workflow(**node_data)))

    def add_transition(self, tr: Transition):
        assert tr.source in self.G.nodes and tr.target in self.G.nodes
        self.G.add_edge(tr.source, tr.target, **tr.model_dump())
        self._emit(TransitionAdded(tr))

    def update_transition(self, tr: Transition):
        # TODO: Add update
        # TODO: Think about nodes without a predecessor!
        pass

    def remove_transition(self, tr_id: str, recursive=False):
        matches = list(filter(lambda edge: self.G.edges[edge].get("id", "") == tr_id, self.G.edges))
        if len(matches) != 0:
            raise ValueError("Invalid or ambiguous tr_id")

        edge = matches[0]
        edge_data = self.G.edges[edge]
        self.G.remove_edge(edge)
        self._emit(TransitionRemoved(**edge_data))

    # ===========================
    #        VALIDATION
    # ===========================
    def validate(self):
        # 1. Detect cycles
        if not nx.is_directed_acyclic_graph(self.G):
            cycle = nx.find_cycle(self.G)
            raise ValueError(f"Workflow graph contains a cycle: {cycle}")

        # 2. Detect missing workflow nodes
        for src, tgt in self.G.edges():
            if src not in self.G or tgt not in self.G:
                raise ValueError(f"Edge refers to nonexistent node: {src}->{tgt}")

        # 3. Ensure workflow IDs are valid (non-empty)
        for n in self.G.nodes:
            if not isinstance(n, str) or not n:
                raise ValueError("Workflow id must be a non-empty string.")

    # ===========================
    #   EXPORT BACK TO CONFIG
    # ===========================
    def to_config(self) -> Dict[str, Any]:
        workflows = self.get_workflows()
        transitions = self.get_transitions()

        return MetaworkflowConfig.model_validate({
            "config_version": self.config_version,
            "workflow_opts": self.workflow_opts,
            "workflow_opts_custom": self.workflow_opts_custom,
            "workflows": workflows,
            "transitions": transitions,
        })

    def to_file(self, file: Path|str) -> None:
        dump_config(self.to_config(), Path(file))

    # ===========================
    #        UTILITIES
    # ===========================
    def get_workflow_by_id(self, id) -> Workflow:
        pass

    def get_transition_by_id(self, id) -> Transition:
        pass

    def get_transitions(self) -> list[Transition]:
        return [Transition(**self.G.edges[e]) for e in self.G.edges]

    def get_workflows(self) -> list[Workflow]:
        return [Workflow(**self.G.nodes[n]) for n in self.G.nodes]

    def get_workflows_sorted(self) -> list[Workflow]:
        """Returns workflows in valid execution order."""
        nodes_sorted = list(nx.topological_sort(self.G))
        workflows = [Workflow(**self.G.nodes[n]) for n in nodes_sorted]
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
        return [Workflow(**self.G.nodes[n]) for n in self.G.successors(wf.id)]

    def predecessors(self, wf: Workflow) -> list[Workflow]:
        return [Workflow(**self.G.nodes[n]) for n in self.G.predecessors(wf.id)]
