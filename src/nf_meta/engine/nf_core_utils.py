import os
import json
import functools
import logging
from dataclasses import dataclass

import requests
import networkx as nx
from networkx.readwrite import json_graph


logger = logging.getLogger()


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
    try:
        response = requests.get(nfcore_url, timeout=10)
    except ConnectionError as e:
        logger.warning(f"Error while attempting to access {nfcore_url}", e)
        return []
    
    if response.status_code != 200:
        return []
    else:
        repos = response.json()["remote_workflows"]
        return [{
                "name": p.get("full_name", ""),
                "url": p.get("url", ""),
                "description": p.get("description", ""),
                "releases": p.get("releases", [])
            } for p in repos]

@functools.cache
def url_exists(url: str, timeout: float=10) -> bool:
    """
    Check whether a URL exists by making a lightweight HTTP request.

    Uses HEAD when possible. Falls back to GET if HEAD is not allowed.
    Results are cached for performance.
    """
    try:
        # Try HEAD first (fast, no body download)
        response = requests.head(
            url,
            allow_redirects=True,
            timeout=timeout,
        )

        # Some servers don't support HEAD properly
        if response.status_code == 405:
            response = requests.get(
                url,
                stream=True,
                allow_redirects=True,
                timeout=timeout,
            )

        return 200 <= response.status_code < 400

    except requests.RequestException:
        return False
