import functools
import logging
import os
import re

import click
import requests
import yaml


logger = logging.getLogger(__name__)

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
    All published releases for nf-core module `name` (short name, e.g. "fastqc") available
    in the nextflow registry. (registry.nextflow.io)

    Each release contains: version, createdAt, status, checksum, size, url,
    and a metadata dict with description, keywords, input, output, and tools.

    Returns [] for unknown modules (404) or on any network/parse error.
    Results are cached for the process lifetime — restart the editor to refresh.
    """
    # The registry endpoints expects underscore ("_")
    # characters in the name to be urlencoded!
    name_enc = name.replace("_", "%2F")
    url = f"{_NXF_REGISTRY_BASE}/nf-core%2F{name_enc}/releases"
    data = _fetch_json(url, f"releases for nf-core/{name}")
    if not isinstance(data, dict):
        return []
    return data.get("releases", [])


# ---------------------------------------------------------------------------
# Module schema fetching and parsing
# ---------------------------------------------------------------------------

_MODULE_SHA_SUFFIX_PATTERN = re.compile(r"-([0-9a-fA-F]{7,40})$")
_PLAIN_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")
_MODULES_RAW_BASE = "https://raw.githubusercontent.com/nf-core/modules"
_NFCORE_MODULES_META_PATH = "modules/{name}/meta.yml"


def _extract_module_sha(version: str) -> str | None:
    """Return the hex SHA embedded in a module version string, or None."""
    if _PLAIN_SHA_PATTERN.match(version):
        return version
    match = _MODULE_SHA_SUFFIX_PATTERN.search(version)
    return match.group(1) if match else None


def _parse_module_schema(meta_yml: dict) -> dict[str, dict]:
    """
    Convert a parsed meta.yml into a flat {param_name: spec} dict.

    All inputs are marked required=True. The type field uses the meta.yml
    vocabulary (file, map, list, string, integer, boolean, number, directory).
    Callers must handle map/list types specially in required checks.
    """
    result: dict[str, dict] = {}
    for entry in meta_yml.get("input", []):
        if isinstance(entry, dict):
            elements = [entry]
        elif isinstance(entry, list):
            elements = entry  # tuple input: flatten channel members
        else:
            continue
        for element in elements:
            if not isinstance(element, dict):
                continue
            for param_name, spec in element.items():
                spec = spec or {}
                result[param_name] = {
                    "type": spec.get("type"),
                    "required": True,
                    "enum": spec.get("enum"),
                    "pattern": spec.get("pattern"),
                }
    return result


@functools.cache
def get_module_schema(name: str, version: str) -> dict[str, dict]:
    """
    Fetch and parse ``meta.yml`` for the nf-core module ``name`` at ``version``.

    The version string is inspected for an embedded commit SHA (e.g.
    ``0.0.0-6c4ed3a`` → ``6c4ed3a``). SHA-pinned fetches are cached on disk.
    When no SHA is extractable, ``master`` is used with a warning and the
    result is NOT cached to disk (master is mutable). Returns ``{}`` on any
    fetch or parse failure after emitting a yellow warning.
    """
    from nf_meta.core.cache import read_schema_cache, write_schema_cache

    sha = _extract_module_sha(version)
    ref = sha if sha else "master"
    cache_key = f"module:{name}@{ref}"

    if not sha:
        click.echo(
            click.style(
                f"Warning: no commit SHA found in module version '{version}' for '{name}'. "
                "Cannot fetch module schema",
                fg="yellow",
            )
        )
        return {}

    cached = read_schema_cache(cache_key, "")
    if cached is not None:
        return cached

    path = _NFCORE_MODULES_META_PATH.format(name=name)
    url = f"{_MODULES_RAW_BASE}/{ref}/{path}"
    auth_headers = _get_auth_headers("github.com")

    try:
        response = requests.get(url, timeout=_REQUEST_TIMEOUT, headers=auth_headers)
    except requests.exceptions.RequestException as e:
        click.echo(
            click.style(
                f"Warning: cannot fetch meta.yml for '{name}@{version}': {e}",
                fg="yellow",
            )
        )
        return {}

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "unknown")
        click.echo(
            click.style(
                f"Warning: rate-limited fetching meta.yml for '{name}@{version}'. "
                f"Retry-After: {retry_after}. Set GITHUB_TOKEN to increase the rate limit.",
                fg="yellow",
            )
        )
        return {}

    if response.status_code != 200:
        click.echo(
            click.style(
                f"Warning: cannot fetch meta.yml for '{name}@{version}' "
                f"(HTTP {response.status_code}) — skipping param validation.",
                fg="yellow",
            )
        )
        return {}

    try:
        meta_yml = yaml.safe_load(response.text)
    except Exception as e:
        click.echo(
            click.style(
                f"Warning: failed to parse meta.yml for '{name}@{version}': {e}",
                fg="yellow",
            )
        )
        return {}

    schema = _parse_module_schema(meta_yml or {})

    if sha:
        write_schema_cache(cache_key, "", schema)

    return schema


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


# ---------------------------------------------------------------------------
# Pipeline schema fetching and validation helpers
# ---------------------------------------------------------------------------


class PipelineSchemaError(Exception):
    """Raised when nextflow_schema.json cannot be fetched or parsed."""


_REPO_URL_PATTERN = re.compile(
    r"https?://(?P<host>(?:github\.com|gitlab\.com|bitbucket\.org))"
    r"/(?P<owner>[^/]+)/(?P<repo>[^/?.#]+)"
)


def _parse_repo_url(url: str) -> tuple[str, str, str]:
    """Return (host, owner, repo) from a repository URL."""
    url = url.rstrip("/").removesuffix(".git")
    match = _REPO_URL_PATTERN.match(url)
    if not match:
        raise PipelineSchemaError(
            f"Cannot parse repository URL '{url}'. "
            "Supported hosts: github.com, gitlab.com, bitbucket.org."
        )
    return match.group("host"), match.group("owner"), match.group("repo")


def _raw_url(host: str, owner: str, repo: str, version: str, path: str) -> str:
    """Construct the raw file URL for the given host."""
    path = path.lstrip("/")
    if host == "github.com":
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{version}/{path}"
    if host == "gitlab.com":
        return f"https://gitlab.com/{owner}/{repo}/-/raw/{version}/{path}"
    if host == "bitbucket.org":
        return f"https://bitbucket.org/{owner}/{repo}/raw/{version}/{path}"
    raise PipelineSchemaError(f"Unsupported host: {host}")


def _get_auth_headers(host: str) -> dict:
    if host == "github.com":
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            return {"Authorization": f"Bearer {token}"}
    elif host == "gitlab.com":
        token = os.environ.get("GITLAB_TOKEN")
        if token:
            return {"PRIVATE-TOKEN": token}
    return {}


def _parse_nextflow_schema(data: dict) -> dict[str, dict]:
    """
    Flatten a nextflow_schema.json into {param_name: spec}.

    Handles both ``definitions`` (draft-07) and ``$defs`` (2020-12) keys.
    Each spec dict contains: type, required, enum, pattern, format, default, hidden.
    """
    result: dict[str, dict] = {}

    definitions = data.get("definitions") or data.get("$defs") or {}
    for _, group in definitions.items():
        if not isinstance(group, dict):
            continue
        required_in_group = set(group.get("required", []))
        for param_name, spec in group.get("properties", {}).items():
            if not isinstance(spec, dict):
                continue
            result[param_name] = {
                "type": spec.get("type"),
                "required": param_name in required_in_group,
                "enum": spec.get("enum"),
                "pattern": spec.get("pattern"),
                "format": spec.get("format"),
                "default": spec.get("default"),
                "hidden": spec.get("hidden", False),
            }

    top_required = set(data.get("required", []))
    for param_name, spec in data.get("properties", {}).items():
        if not isinstance(spec, dict) or param_name in result:
            continue
        result[param_name] = {
            "type": spec.get("type"),
            "required": param_name in top_required,
            "enum": spec.get("enum"),
            "pattern": spec.get("pattern"),
            "format": spec.get("format"),
            "default": spec.get("default"),
            "hidden": spec.get("hidden", False),
        }

    return result


@functools.cache
def get_pipeline_schema(url: str, version: str) -> dict[str, dict]:
    """
    Fetch and parse ``nextflow_schema.json`` for the pipeline at ``url@version``.

    Results are cached in memory (per process) and on disk via
    ``nf_meta.core.cache``. Raises ``PipelineSchemaError`` if the schema
    cannot be fetched or parsed for any reason. Set the ``GITHUB_TOKEN``
    environment variable to increase GitHub API rate limits.
    """
    from nf_meta.core.cache import read_schema_cache, write_schema_cache

    cached = read_schema_cache(url, version)
    if cached is not None:
        return cached

    host, owner, repo = _parse_repo_url(url)
    schema_url = _raw_url(host, owner, repo, version, "nextflow_schema.json")
    auth_headers = _get_auth_headers(host)

    try:
        response = requests.get(
            schema_url, timeout=_REQUEST_TIMEOUT, headers=auth_headers
        )
    except requests.exceptions.Timeout:
        raise PipelineSchemaError(
            f"Timeout fetching nextflow_schema.json for {url}@{version}"
        )
    except requests.exceptions.RequestException as e:
        raise PipelineSchemaError(
            f"Network error fetching nextflow_schema.json for {url}@{version}: {e}"
        )

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "unknown")
        token_hint = (
            "Set GITHUB_TOKEN to increase the rate limit."
            if host == "github.com"
            else "Set GITLAB_TOKEN to authenticate."
            if host == "gitlab.com"
            else "Authenticate to increase the rate limit."
        )
        raise PipelineSchemaError(
            f"Rate-limited (429) fetching nextflow_schema.json for {url}@{version}. "
            f"Retry-After: {retry_after}. {token_hint}"
        )
    if response.status_code == 404:
        raise PipelineSchemaError(
            f"nextflow_schema.json not found for {url}@{version}. "
            "Ensure the pipeline includes a nextflow_schema.json at its root."
        )
    if response.status_code != 200:
        raise PipelineSchemaError(
            f"Unexpected HTTP {response.status_code} fetching nextflow_schema.json "
            f"for {url}@{version}"
        )

    try:
        data = response.json()
    except ValueError as e:
        raise PipelineSchemaError(
            f"Failed to parse nextflow_schema.json for {url}@{version} as JSON: {e}"
        )

    schema = _parse_nextflow_schema(data)
    write_schema_cache(url, version, schema)
    return schema


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
