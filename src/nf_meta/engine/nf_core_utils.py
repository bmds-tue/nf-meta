import os
import json
import functools
from dataclasses import dataclass

import requests
import networkx as nx
from networkx.readwrite import json_graph


def save_graph_to_file(graph: nx.DiGraph, file: str):
    data = json_graph.adjacency_data(graph)
    s = json.dumps(data, indent=2)

    with open(file, "w") as f:
        f.write(s)

def load_graph_from_file(file: str):
    
    with open(file, "r") as f:
        data = json.loads(f.read())
    
    g = json_graph.adjacency_graph(data)

    return g

@functools.cache
def get_nfcore_pipelines() -> list[dict]:

    """
    Adapted from nf-core/tools `nf_core.pipelines.list.Workflows:get_remote_workflows` method
    """

    # List all repositories at nf-core
    nfcore_url = "https://nf-co.re/pipelines.json"
    
    response = requests.get(nfcore_url, timeout=10)
    if response.status_code != 200:
        return []
    else:
        repos = response.json()["remote_workflows"]
        return [{"name": p.get("full_name", ""), "location": p.get("url", ""), "description": p.get("description", "")} for p in repos]
