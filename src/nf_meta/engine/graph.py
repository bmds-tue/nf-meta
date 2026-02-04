from typing import Dict, Any, Optional
from pathlib import Path
import yaml
import logging

import networkx as nx

from .models import MetaworkflowConfig, CONFIG_VERSION_MIN, dump_config
from nf_meta.engine.nf_core_utils import get_nfcore_pipelines


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

        nfcore_pipelines = get_nfcore_pipelines()

        # Add workflow nodes
        for wf in cfg.workflows:
            nfcore_matches = list(filter(lambda p: p.get("name") == wf.name, nfcore_pipelines))
            if len(nfcore_matches) > 0:
                match = nfcore_matches.pop()
                obj.G.add_node(
                    wf.id,
                    id=wf.id,
                    is_nfcore=True,
                    pipeline_location=match.get("location"),
                    pipeline_description=match.get("description"),
                    name=wf.name,
                    version=wf.version,
                )
            else:
                obj.G.add_node(
                    wf.id,
                    id=wf.id,
                    is_nfcore=False,
                    name=wf.name,
                    pipeline_location=wf.pipeline_location,
                    version=wf.version
                )

        # Add transition metadata
        for t in cfg.transitions:
            src = t.from_ if t.from_ else None
            tgt = t.run

            if src != None and src not in obj.G.nodes:
                raise ValueError(f"Unknown node {src} found in transition {src}->{tgt}")
            
            if tgt not in obj.G.nodes:
                raise ValueError(f"Unknown node {tgt} found in transition {src}->{tgt}")

            if not obj.G.has_edge(src, tgt):
                # Transition not declared in metalayout → auto-add
                # TODO: Be more specific with keys once they are stable-ish
                obj.G.add_edge(src, tgt, data=t.model_dump())

        # Run graph validation
        obj.validate()

        return obj

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
        nodes = [n for n in self.G.nodes]

        workflows = [
            {
                "id": n,
                "name": self.G.nodes[n]["name"],
                "pipeline_location": self.G.nodes[n].get("pipeline_location", None),
                "version": self.G.nodes[n].get("version", None),
            }
            for n in nodes
        ]

        transitions = []
        for src, tgt, data in self.G.edges(data=True):
            meta = data.get("data", {})
            if src is None:
                t = {"run": tgt}
            else:
                t = {"from": src, "run": tgt}

            # TODO: This potentially adds unwanted fields!
            t.update(meta)
            transitions.append(t)

        return MetaworkflowConfig.model_validate({
            "config_version": CONFIG_VERSION_MIN,
            "workflows": workflows,
            "transitions": transitions,
        })

    def to_file(self, file: Path|str) -> None:
        dump_config(self.to_config(), Path(file))
        

    # ===========================
    #        UTILITIES
    # ===========================
    def get_nodes_execution_order(self):
        """Returns workflow ids in valid execution order."""
        return list(nx.topological_sort(self.G))

    def get_start_node(self):
        """
        Return the first order in topological sorting or None if no nodes exist
        """
        nodes_ordered = self.execution_order()
        if not len(nodes_ordered):
            return None
        else:
            return nodes_ordered[0]

    def successors(self, workflow_id: str):
        return list(self.G.successors(workflow_id))

    def predecessors(self, workflow_id: str):
        return list(self.G.predecessors(workflow_id))
