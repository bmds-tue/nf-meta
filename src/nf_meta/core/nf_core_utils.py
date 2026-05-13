import functools
import logging

import requests


logger = logging.getLogger()

_GITHUB_API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


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
def github_file_exists(repo_url: str, path: str, ref: str) -> bool:
    """
    Check whether a file exists at `path` in a GitHub repository at `ref`
    using the GitHub Contents API.
    """
    try:
        after_host = repo_url.rstrip("/").split("github.com/", 1)[-1]
        parts = after_host.split("/")
        if len(parts) < 2:
            return False
        owner, repo = parts[0], parts[1]
        api_url = (
            f"https://api.github.com/repos/{owner}/{repo}"
            f"/contents/{path.lstrip('/')}?ref={ref}"
        )
        response = requests.get(api_url, timeout=10, headers=_GITHUB_API_HEADERS)
        return response.status_code == 200
    except requests.RequestException:
        return False


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
