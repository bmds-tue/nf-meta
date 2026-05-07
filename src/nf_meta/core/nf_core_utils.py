import functools
import logging

import requests


logger = logging.getLogger()


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
        return [
            {
                "name": p.get("full_name", ""),
                "url": p.get("repository_url", ""),
                "description": p.get("description", ""),
                "releases": [
                    {
                        "tag_name": r.get("tag_name"),
                        "tag_sha": r.get("tag_sha"),
                        "published_at": r.get("published_at"),
                    }
                    for r in p.get("releases", [])
                ],
            }
            for p in repos
        ]


@functools.cache
def url_exists(url: str, timeout: float = 10) -> bool:
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
