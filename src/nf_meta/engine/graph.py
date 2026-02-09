from typing import Dict, Any, Optional
from pathlib import Path
import yaml
import logging

import networkx as nx

from .models import MetaworkflowConfig, Workflow, WorkflowOptions, Transition, dump_config


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
        self.config_version: str = None

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
            src = t.from_ if t.from_ else None
            tgt = t.run

            if tgt not in obj.G.nodes:
                raise ValueError(f"Unknown node {tgt} found in transition {src}->{tgt}")

            if src is not None: 
                if src not in obj.G.nodes:
                    raise ValueError(f"Unknown node {src} found in transition {src}->{tgt}")

                if not obj.G.has_edge(src, tgt):
                    # Transition not declared in metalayout → auto-add
                    # TODO: Be more specific with keys once they are stable-ish
                    obj.G.add_edge(src, tgt, data=t.model_dump())

        obj.workflow_opts = cfg.workflow_opts
        obj.workflow_opts_custom = cfg.workflow_opts_custom
        obj.config_version = cfg.config_version

        # Run graph validation
        obj.validate()

        return obj

    def add_workflow(self, wf: Workflow):
        self.G.add_node(wf.id, **wf.model_dump())

    def update_workflow(self, wf: Workflow):
        try:
            self.G.nodes[wf.id] = wf.model_dump()
        except KeyError as e:
            raise ValueError("Workflow has invalid id. Update unsuccessful!")

    def remove_workflow(self, wf_id: str, recursive=False):
        # TODO: check id
        # TODO: implement removal
        # TODO: if recursive, then avoid disconnected graph, by recursively deleting all children nodes
        pass

    def add_transition(self, tr: Transition):
        # TODO: whats important for adding?
        pass

    def update_transition(self, tr: Transition):
        # TODO: Add update
        # TODO: Think about nodes without a predecessor!
        pass

    def remove_transition(self, tr_id: str, recursive=False):
        # TODO: check id
        # TODO: implement removal
        # TODO: if recursive, then avoid disconnected graph, by recursively deleting all connected nodes
        pass

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
    def get_transitions(self) -> list[Transition]:
        return [Transition(**data.get("data")) for _, _, data in self.G.edges(data=True)]

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
