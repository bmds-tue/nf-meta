"""Lookups in the nf-core catalog, the Nextflow module registry and pipeline
repositories: pipeline and module lists, module releases, param schemas."""

import functools
import logging
import os
import re
import time
from typing import Any, Required, TypedDict, cast
from urllib.parse import quote

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
NFCORE_MODULE_PREFIX = "nf-core/"


class PipelineRelease(TypedDict):
    """One release of an nf-core pipeline."""

    tag_name: str
    tag_sha: str
    published_at: str


class PipelineInfo(TypedDict):
    """An nf-core pipeline in the catalog. `name` is the full name
    (`nf-core/rnaseq`)."""

    name: str
    url: str
    description: str
    releases: list[PipelineRelease]


class ModuleInfo(TypedDict):
    """An nf-core module in the catalog. `name` is nf-core's short name
    (`fastqc`, `samtools_stats`)."""

    name: str
    description: str
    keywords: list[str]


class ModuleRelease(TypedDict, total=False):
    """One release of a module in the Nextflow module registry, as the
    registry returns it. `metadata` holds description, keywords, input,
    output and tools."""

    version: Required[str]
    createdAt: str
    status: str
    checksum: str
    size: int
    url: str
    metadata: dict[str, Any]


class ParamSpec(TypedDict, total=False):
    """One param of a pipeline or module schema. `type` is a JSON Schema type
    for pipelines and a meta.yml type (`file`, `map`, ...) for modules; the
    other keys besides `type`, `required`, `enum` and `pattern` are only set
    for pipelines."""

    type: str | None
    required: bool
    enum: list[Any] | None
    pattern: str | None
    format: str | None
    default: Any
    hidden: bool
    exists: bool
    mimetype: str
    schema: str
    minimum: float
    maximum: float
    description: str


Schema = dict[str, ParamSpec]
"""A flat param schema: param name → `ParamSpec`."""


class RegistryError(Exception):
    """A lookup in the nf-core catalog, the Nextflow module registry or a
    pipeline repository failed."""


class RegistryUnavailableError(RegistryError):
    """The service can't be reached or gave no usable answer (network error,
    timeout, rate limit, server error, malformed response)."""


class NotInRegistryError(RegistryError, LookupError):
    """The requested module or release doesn't exist."""


# A failed request is not repeated for this many seconds; the stored error is
# raised again instead, so an offline run doesn't wait for every timeout.
_FAILURE_TTL = 30.0
_recent_failures: dict[str, tuple[float, str]] = {}


def _fetch_json(
    url: str,
    label: str,
    headers: dict | None = None,
) -> dict | list | None:
    """
    Shared HTTP GET helper. Returns the parsed JSON, or `None` for a 404 or
    an empty response.

    Raises `RegistryUnavailableError` on timeouts, connection errors, rate
    limiting (429), other unexpected status codes and malformed JSON.
    Callers are responsible for caching; this function is not cached itself.
    """
    failed = _recent_failures.get(url)
    if failed and time.monotonic() - failed[0] < _FAILURE_TTL:
        raise RegistryUnavailableError(failed[1])
    try:
        return _fetch_json_once(url, label, headers)
    except RegistryUnavailableError as e:
        _recent_failures[url] = (time.monotonic(), str(e))
        raise


def _fetch_json_once(url: str, label: str, headers: dict | None) -> dict | list | None:
    try:
        response = requests.get(url, timeout=_REQUEST_TIMEOUT, headers=headers)
    except requests.exceptions.Timeout as e:
        raise RegistryUnavailableError(f"Timeout fetching {label} from {url}") from e
    except requests.exceptions.RequestException as e:
        raise RegistryUnavailableError(f"Network error fetching {label} from {url}: {e}") from e

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "unknown")
        hint = " Set GITHUB_TOKEN to increase the rate limit." if "github.com" in url else ""
        raise RegistryUnavailableError(
            f"Rate-limited (429) fetching {label} from {url}. Retry-After: {retry_after}.{hint}"
        )
    if response.status_code == 404:
        logger.debug("Not found (404) for %s at %s", label, url)
        return None
    if response.status_code == 204 or not response.content:
        logger.debug("No content for %s at %s", label, url)
        return None
    if response.status_code != 200:
        raise RegistryUnavailableError(f"Unexpected status {response.status_code} fetching {label} from {url}")

    try:
        return response.json()
    except ValueError as e:
        raise RegistryUnavailableError(f"Invalid JSON in response for {label} from {url}") from e


# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------


@functools.cache
def get_nfcore_pipelines() -> list[PipelineInfo]:
    """All nf-core pipelines with their releases, from the nf-core catalog.
    Cached for the process lifetime. Raises `RegistryUnavailableError` if the
    catalog can't be fetched.

    Adapted from nf-core/tools `nf_core.pipelines.list.Workflows:get_remote_workflows` method
    """
    data = _fetch_json(_NFCORE_PIPELINES_URL, "nf-core pipelines")
    if not isinstance(data, dict):
        raise RegistryUnavailableError(f"No usable nf-core pipeline catalog at {_NFCORE_PIPELINES_URL}")
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
        raise RegistryUnavailableError(f"No usable nf-core component catalog at {_NFCORE_COMPONENTS_URL}")
    return data.get("modules", [])


def registry_module_name(name: str) -> str:
    """The Nextflow module registry name of module `name` as written in a
    config. nf-core's short form names nested modules with an underscore
    (`nf-core/samtools_stats`); the registry uses the repository path
    (`nf-core/samtools/stats`). Names that already contain a path, and
    modules outside nf-core, are returned unchanged.

    The path comes from nf-core's component catalog, since a tool name can
    itself contain an underscore (`plastid_make_wiggle` is
    `plastid/make_wiggle`). Without the catalog (unreachable, or a module
    not in it), every underscore is taken as a path separator.
    """
    short = name.removeprefix(NFCORE_MODULE_PREFIX)
    if short == name or "/" in short:
        return name
    try:
        entry = next((m for m in _get_nfcore_components_raw() if m.get("name") == short), None)
    except RegistryUnavailableError:
        entry = None
    path = (entry or {}).get("path", "")
    if path.startswith("modules/nf-core/") and path.endswith("/meta.yml"):
        return NFCORE_MODULE_PREFIX + path.removeprefix("modules/nf-core/").removesuffix("/meta.yml")
    return NFCORE_MODULE_PREFIX + short.replace("_", "/")


@functools.cache
def get_nfcore_modules() -> list[ModuleInfo]:
    """
    Summary list (name, description, keywords) for all nf-core modules.
    Suitable for the browse/search UI without shipping full I/O schemas.
    Raises `RegistryUnavailableError` if the catalog can't be fetched.
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
def get_nfcore_module_releases(name: str) -> list[ModuleRelease]:
    """
    All published releases of nf-core module `name` (`fastqc`, `samtools_stats`;
    an `nf-core/` prefix is accepted) in the Nextflow module registry
    (registry.nextflow.io).

    Returns [] for unknown modules. Raises `RegistryUnavailableError` if the
    registry can't be reached. Results are cached for the process lifetime --
    restart the editor to refresh.
    """
    name = name.removeprefix(NFCORE_MODULE_PREFIX)
    # The registry endpoints expects underscore ("_")
    # characters in the name to be urlencoded!
    # The registry expects the name URL-encoded, "/" included
    registry_name = registry_module_name(NFCORE_MODULE_PREFIX + name)
    url = f"{_NXF_REGISTRY_BASE}/{quote(registry_name, safe='')}/releases"
    data = _fetch_json(url, f"releases for nf-core/{name}")
    if not isinstance(data, dict):
        return []
    return cast(list[ModuleRelease], data.get("releases", []))


def get_module_metadata(name: str, version: str | None = None) -> ModuleRelease:
    """The registry release of nf-core module `name` (as for
    `get_nfcore_module_releases`) at `version`, or the latest one. Its
    `metadata` holds description, keywords, input, output and tools.

    Raises `NotInRegistryError` if the module has no releases or not
    `version`, and `RegistryUnavailableError` if the registry can't be
    reached.
    """
    releases = get_nfcore_module_releases(name)
    if not releases:
        raise NotInRegistryError(f"Module '{name}' not found or has no published releases")
    if version is None:
        return max(releases, key=lambda r: r.get("createdAt", ""))
    release = next((r for r in releases if r["version"] == version), None)
    if release is None:
        raise NotInRegistryError(f"Version '{version}' not found for module '{name}'")
    return release


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


class SchemaUnavailableError(RegistryError):
    """A pipeline's or module's param schema can't be fetched or parsed."""


class ModuleSchemaError(SchemaUnavailableError):
    """Raised when a module's meta.yml cannot be fetched or parsed."""


def _parse_module_schema(meta_yml: dict) -> Schema:
    """
    Convert a parsed meta.yml into a flat {param_name: spec} dict.

    All inputs are marked required=True. The type field uses the meta.yml
    vocabulary (file, map, list, string, integer, boolean, number, directory).
    Callers must handle map/list types specially in required checks.
    """
    result: Schema = {}
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
def get_module_schema(name: str, version: str) -> Schema:
    """
    Fetch and parse ``meta.yml`` for the nf-core module ``name`` at ``version``.

    The version string must contain a commit SHA (e.g. ``0.0.0-6c4ed3a`` →
    ``6c4ed3a``); results are cached on disk. Returns ``{}`` for a module
    that declares no inputs. Raises ``ModuleSchemaError`` if the schema
    cannot be fetched or parsed.
    """
    from nf_meta.core.cache import read_schema_cache, write_schema_cache

    sha = _extract_module_sha(version)
    if not sha:
        raise ModuleSchemaError(
            f"No commit SHA in module version '{version}' for '{name}' (e.g. '0.0.0-6c4ed3a'); cannot fetch its meta.yml"
        )

    cache_key = f"module:{name}@{sha}"
    cached = read_schema_cache(cache_key, "")
    if cached is not None:
        return cached

    path = _NFCORE_MODULES_META_PATH.format(name=registry_module_name(name))
    url = f"{_MODULES_RAW_BASE}/{sha}/{path}"
    auth_headers = _get_auth_headers("github.com")

    try:
        response = requests.get(url, timeout=_REQUEST_TIMEOUT, headers=auth_headers)
    except requests.exceptions.RequestException as e:
        raise ModuleSchemaError(f"Cannot fetch meta.yml for '{name}@{version}': {e}") from e

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "unknown")
        raise ModuleSchemaError(
            f"Rate-limited fetching meta.yml for '{name}@{version}'. "
            f"Retry-After: {retry_after}. Set GITHUB_TOKEN to increase the rate limit."
        )

    if response.status_code != 200:
        raise ModuleSchemaError(f"Cannot fetch meta.yml for '{name}@{version}' (HTTP {response.status_code})")

    try:
        meta_yml = yaml.safe_load(response.text)
    except yaml.YAMLError as e:
        raise ModuleSchemaError(f"Failed to parse meta.yml for '{name}@{version}': {e}") from e

    schema = _parse_module_schema(meta_yml or {})

    write_schema_cache(cache_key, "", schema)

    return schema


# ---------------------------------------------------------------------------
# GitHub / generic URL helpers
# ---------------------------------------------------------------------------


@functools.cache
def github_file_exists(repo_url: str, path: str, ref: str) -> bool:
    """
    Check whether a file exists at `path` in a GitHub repository at `ref`
    using the GitHub Contents API. Raises `RegistryUnavailableError` if
    GitHub can't be reached or rate-limits the request.
    """
    after_host = repo_url.rstrip("/").split("github.com/", 1)[-1]
    parts = after_host.split("/")
    if len(parts) < 2:
        return False
    owner, repo = parts[0], parts[1]
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path.lstrip('/')}?ref={ref}"

    return _fetch_json(api_url, f"GitHub file {path}@{ref}", headers=_GITHUB_API_HEADERS) is not None


# ---------------------------------------------------------------------------
# Pipeline schema fetching and validation helpers
# ---------------------------------------------------------------------------


class PipelineSchemaError(SchemaUnavailableError):
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
            f"Cannot parse repository URL '{url}'. Supported hosts: github.com, gitlab.com, bitbucket.org."
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


_EXTRA_SPEC_KEYWORDS = ("exists", "mimetype", "schema", "minimum", "maximum", "description")


def _extra_spec_keywords(spec: dict) -> dict:
    return {k: spec[k] for k in _EXTRA_SPEC_KEYWORDS if k in spec}


def _parse_nextflow_schema(data: dict) -> Schema:
    """
    Flatten a nextflow_schema.json into {param_name: spec}.

    Handles both ``definitions`` (draft-07) and ``$defs`` (2020-12) keys.
    Each spec dict contains: type, required, enum, pattern, format, default,
    hidden, plus exists, mimetype, schema, minimum, maximum and description
    where the schema sets them.
    """
    result: Schema = {}

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
                **_extra_spec_keywords(spec),
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
            **_extra_spec_keywords(spec),
            "format": spec.get("format"),
            "default": spec.get("default"),
            "hidden": spec.get("hidden", False),
        }

    return result


@functools.cache
def get_pipeline_schema(url: str, version: str) -> Schema:
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
        response = requests.get(schema_url, timeout=_REQUEST_TIMEOUT, headers=auth_headers)
    except requests.exceptions.Timeout as e:
        raise PipelineSchemaError(f"Timeout fetching nextflow_schema.json for {url}@{version}") from e
    except requests.exceptions.RequestException as e:
        raise PipelineSchemaError(f"Network error fetching nextflow_schema.json for {url}@{version}: {e}") from e

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
            f"Unexpected HTTP {response.status_code} fetching nextflow_schema.json for {url}@{version}"
        )

    try:
        data = response.json()
    except ValueError as e:
        raise PipelineSchemaError(f"Failed to parse nextflow_schema.json for {url}@{version} as JSON: {e}") from e

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
