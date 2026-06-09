import functools
import logging

import requests


logger = logging.getLogger()

_GITHUB_API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

_NFCORE_PIPELINES_URL = "https://nf-co.re/pipelines.json"
_NFCORE_COMPONENTS_URL = "https://nf-co.re/components.json"
_NXF_REGISTRY_BASE = "https://registry.nextflow.io/api/v1/modules"
_REQUEST_TIMEOUT = 10


def _fetch_json(
    url: str,
    label: str,
    headers: dict | None = None,
) -> dict | list | None:
    """
    Shared HTTP GET helper. Returns parsed JSON or None on any failure.

    Handles: timeout, connection error, rate-limiting (429), not-found (404),
    no-content (204 / empty body), unexpected status codes, and malformed JSON.
    Callers are responsible for caching; this function is not cached itself.
    """
    try:
        response = requests.get(url, timeout=_REQUEST_TIMEOUT, headers=headers)
    except requests.exceptions.Timeout:
        logger.warning("Timeout fetching %s from %s", label, url)
        return None
    except requests.exceptions.RequestException as e:
        logger.warning("Network error fetching %s from %s: %s", label, url, e)
        return None

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "unknown")
        logger.warning(
            "Rate-limited (429) fetching %s from %s — Retry-After: %s",
            label,
            url,
            retry_after,
        )
        return None
    if response.status_code == 404:
        logger.debug("Not found (404) for %s at %s", label, url)
        return None
    if response.status_code == 204 or not response.content:
        logger.debug("No content for %s at %s", label, url)
        return None
    if response.status_code != 200:
        logger.warning(
            "Unexpected status %d fetching %s from %s",
            response.status_code,
            label,
            url,
        )
        return None

    try:
        return response.json()
    except ValueError:
        logger.warning("Invalid JSON in response for %s from %s", label, url)
        return None


# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------


@functools.cache
def get_nfcore_pipelines() -> list[dict]:
    """
    Adapted from nf-core/tools `nf_core.pipelines.list.Workflows:get_remote_workflows` method
    """
    data = _fetch_json(_NFCORE_PIPELINES_URL, "nf-core pipelines")
    if not isinstance(data, dict):
        return []
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
        for p in data.get("remote_workflows", [])
    ]


# ---------------------------------------------------------------------------
# Modules  (nf-co.re/components.json + Nextflow registry)
# ---------------------------------------------------------------------------


@functools.cache
def _get_nfcore_components_raw() -> list[dict]:
    """Raw list of components from nf-co.re/components.json. Cached once per process."""
    data = _fetch_json(_NFCORE_COMPONENTS_URL, "nf-core components")
    if not isinstance(data, dict):
        return []
    return data.get("modules", [])


@functools.cache
def get_nfcore_module_lookup() -> dict[str, dict]:
    """
    Returns {short_name: module_entry} built from components.json.
    Useful for O(1) name-existence checks during validation.
    """
    return {m["name"]: m for m in _get_nfcore_components_raw()}


@functools.cache
def get_nfcore_modules() -> list[dict]:
    """
    Summary list (name, description, keywords) for all nf-core modules.
    Suitable for the browse/search UI without shipping full I/O schemas.
    """
    return [
        {
            "name": m["name"],
            "description": m.get("meta", {}).get("description", ""),
            "keywords": m.get("meta", {}).get("keywords", []),
        }
        for m in _get_nfcore_components_raw()
    ]


@functools.cache
def get_nfcore_module_releases(name: str) -> list[dict]:
    """
    All published releases for nf-core module `name` (short name, e.g. "fastqc").

    Each release contains: version, createdAt, status, checksum, size, url,
    and a metadata dict with description, keywords, input, output, and tools.

    Returns [] for unknown modules (404) or on any network/parse error.
    Results are cached for the process lifetime — restart the editor to refresh.
    """
    url = f"{_NXF_REGISTRY_BASE}/nf-core%2F{name}/releases"
    data = _fetch_json(url, f"releases for nf-core/{name}")
    if not isinstance(data, dict):
        return []
    return data.get("releases", [])


# ---------------------------------------------------------------------------
# GitHub / generic URL helpers
# ---------------------------------------------------------------------------


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
    except Exception:
        return False

    return (
        _fetch_json(api_url, f"GitHub file {path}@{ref}", headers=_GITHUB_API_HEADERS)
        is not None
    )


@functools.cache
def url_exists(url: str, timeout: float = 10) -> bool:
    """
    Check whether a URL exists by making a lightweight HTTP request.

    Uses HEAD when possible. Falls back to GET if HEAD is not allowed.
    Results are cached for performance.
    """
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout)

        # Some servers don't support HEAD properly
        if response.status_code == 405:
            response = requests.get(
                url,
                stream=True,
                allow_redirects=True,
                timeout=timeout,
            )

        return 200 <= response.status_code < 400

    except requests.exceptions.RequestException:
        return False
