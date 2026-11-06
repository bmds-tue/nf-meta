import difflib
import hashlib
import json
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, ClassVar, Literal, TypeVar

import yaml
from packaging.version import Version
from pydantic import (
    AfterValidator,
    AliasChoices,
    BaseModel,
    BeforeValidator,
    Field,
    ValidationInfo,
    computed_field,
    field_validator,
    model_validator,
)

from nf_meta.core.refs import RESERVED_STEP_IDS, STEP_REF_PATTERN
from nf_meta.core.registry import PipelineInfo, RegistryUnavailableError, get_nfcore_pipelines

NFCORE_PREFIX = "nf-core/"

CONFIG_VERSION_MIN = "0.0.1"
CONFIG_VERSION_MAX = "0.5.0"
# First config version that may declare `inputs:`
INPUTS_MIN_CONFIG_VERSION = "0.4.0"
# The config's steps; `workflows:` is the deprecated name, still read
STEPS_KEY = "steps"
LEGACY_STEPS_KEY = "workflows"
# First config version that names them `steps:`
STEPS_MIN_CONFIG_VERSION = "0.5.0"


class WorkflowType(StrEnum):
    """Discriminates the two workflow shapes a config's `type:` key selects
    between: a full `nextflow run` pipeline, or a single `nextflow module run`."""

    NF_PIPELINE = "nf-pipeline"
    NF_MODULE = "nf-module"


# Accepted keys for renamed fields; the old names are deprecated (config_version 0.4.0)
NF_CONFIG_KEYS = AliasChoices("nf_config", "config_file")
NF_PROFILE_KEYS = AliasChoices("nf_profile", "profile")
LEGACY_KEYS = {"config_file": "nf_config", "profile": "nf_profile"}


def _as_text(value: Any) -> Any:
    """A path given as `Path` is kept as text, exactly as written."""
    return str(value) if isinstance(value, Path) else value or None


def _yaml_suffix(value: str | None) -> str | None:
    if value is not None and Path(value).suffix not in (".yaml", ".yml"):
        raise ValueError("Path must end with .yaml or .yml")
    return value


# `params_file`/`nf_config`: kept as written, relative to the config's folder when relative
YamlFilePath = Annotated[str | None, BeforeValidator(_as_text), AfterValidator(_yaml_suffix)]
FilePath = Annotated[str | None, BeforeValidator(_as_text)]

CONFIG_PATH_FIELDS = ("params_file", "nf_config")


def config_path(value: str, project_dir: Path | None) -> Path:
    """`value` (a `params_file`/`nf_config`) as an absolute path: a relative
    one is relative to `project_dir`, or to the current folder without one."""
    path = Path(value).expanduser()
    return (path if path.is_absolute() else (project_dir or Path.cwd()) / path).resolve()


# A workflow or `GlobalOptions`: the copy has the same type as the item
_Model = TypeVar("_Model", bound=BaseModel)


def with_absolute_config_paths(item: _Model, project_dir: Path | None) -> _Model:
    """`item` (a workflow or `GlobalOptions`) with its `params_file`/`nf_config`
    (and a local pipeline's `path`) made absolute with `config_path`, for
    reading them."""
    fields = (*CONFIG_PATH_FIELDS, "path")  # `path`: a local pipeline's folder
    update = {f: str(config_path(v, project_dir)) for f in fields if (v := getattr(item, f, None))}
    return item.model_copy(update=update) if update else item


_SCALAR_TYPES = (str, int, float, bool)


def validate_param_scalars(v: Any) -> dict[str, Any] | None:
    """Validate that every param value is a scalar, preserving its type.
    Values of `str` subclasses (e.g. `Ref`) are stored as plain `str`."""
    if v is None:
        return None

    if not isinstance(v, dict):
        raise ValueError(f"Params must be a key-value mapping, got {type(v).__name__!r}")

    errors = [
        f"\tParam '{key}' has unsupported type {type(value).__name__}"
        for key, value in v.items()
        if not isinstance(value, _SCALAR_TYPES)
    ]

    if errors:
        raise ValueError("\n" + "\n".join(errors))

    return {key: str(value) if isinstance(value, str) else value for key, value in v.items()}


CoercedParams = Annotated[dict[str, Any] | None, BeforeValidator(validate_param_scalars)]


def load_params_file(path: Path) -> dict:
    """Load a YAML params-file into a dict ({} if empty or not a mapping)."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    return data if isinstance(data, dict) else {}


def _params_last(data: dict) -> dict:
    """Move `params` to the end, where it reads best in a config file."""
    if "params" in data:
        data["params"] = data.pop("params")
    return data


def create_id():
    return str(uuid.uuid4())[:8]


@dataclass
class Reference:
    name: str | None
    source_wf_id: str
    target_wf_id: str


@dataclass
class WorkflowReference(Reference):
    """A cross-step parameter or output reference parsed from a param value."""

    name: str
    source_key: str
    target_key: str
    namespace: str = "params"  # "params" (supported) | "outputs" (future)


# ---------------------------------------------------------------------------
# Base step class
# ---------------------------------------------------------------------------


class BaseWorkflow(BaseModel, ABC, use_enum_values=True):
    """Base class for one step in a metapipeline. Concrete types: `NfPipeline`
    (a `nextflow run` pipeline) and `NfModule` (a `nextflow module run`).

    `params` values keep their declared scalar type (`str`/`int`/`float`/`bool`)
    through to the generated Nextflow params file, rather than being
    stringified -- this matters because Nextflow's own schema validation is
    strict about, e.g., a quoted `"9"` where an integer is expected.
    """

    type: WorkflowType
    id: str = Field(default_factory=lambda: "n" + create_id())
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    nf_config: FilePath = Field(default=None, validation_alias=NF_CONFIG_KEYS)
    # validate_default=True ensures the params validator runs even when params
    # is absent from the input (Pydantic skips field validators for defaults otherwise).
    params: CoercedParams | None = Field(default=None, validate_default=True)

    @computed_field  # type: ignore[misc]
    @property
    def field_refs(self) -> list[WorkflowReference]:
        if not self.params:
            return []
        refs = []
        for k, v in self.params.items():
            match = STEP_REF_PATTERN.search(str(v))
            if match:
                refs.append(
                    WorkflowReference(
                        name=match.group(0),
                        source_wf_id=self.id,
                        source_key=k,
                        target_wf_id=match.group(1),
                        namespace=match.group(2),
                        target_key=match.group(3),
                    )
                )
        return refs

    @field_validator("id", mode="after")
    @classmethod
    def validate_id_not_reserved(cls, value: str) -> str:
        if value in RESERVED_STEP_IDS:
            raise ValueError(f"'{value}' is reserved and can't be used as a step id")
        return value

    @field_validator("version", mode="after")
    @classmethod
    def validate_version_ref(cls, value: str | None) -> str | None:
        if value is None:  # a local pipeline (`path`) has none
            return value
        if not value:
            raise ValueError("A version is needed: a release tag or commit (or, while developing it, a local `path`).")
        if re.match(r"^v?\d", value) or re.match(r"^[0-9a-fA-F]{7,40}$", value):
            return value
        raise ValueError(
            f"Version '{value}' looks like a branch name. "
            "Use a release tag (e.g. '1.2.3', 'v1.2.3') or a commit SHA "
            "to ensure reproducibility."
        )

    @abstractmethod
    def hash(self) -> str:
        """Short content hash of everything that defines this step's result."""

    @abstractmethod
    def model_dump_config(self) -> dict: ...

    @abstractmethod
    def model_dump_display(self) -> dict: ...

    def model_dump(self, **kwargs: Any):
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)


# ---------------------------------------------------------------------------
# NfPipeline — nextflow run
# ---------------------------------------------------------------------------


def script_folder(main_script: str | None) -> str:
    """The folder of a pipeline's `main_script` within the pipeline, where its
    `nextflow_schema.json` is (`""` for the root)."""
    if not main_script:
        return ""
    folder = PurePosixPath(main_script).parent.as_posix()
    return "" if folder == "." else folder


class NfPipeline(BaseWorkflow):
    """A Nextflow pipeline step executed with 'nextflow run'."""

    type: Literal[WorkflowType.NF_PIPELINE] = WorkflowType.NF_PIPELINE
    # None only for a local pipeline (`path`)
    version: str | None = None  # type: ignore[assignment]
    # A local pipeline folder, for development: used instead of `url` and `version`
    path: FilePath = None
    url: str
    description: str | None = None
    params_file: YamlFilePath = None
    nf_profile: str | None = Field(default=None, validation_alias=NF_PROFILE_KEYS)
    main_script: str | None = None

    @computed_field  # type: ignore[misc]
    @property
    def is_nfcore(self) -> bool:
        # Validation guarantees that a name with the prefix is in the nf-core catalog
        return self.name.startswith(NFCORE_PREFIX)

    @classmethod
    def get_nfcore_info(cls, name: str) -> PipelineInfo | None:
        """The catalog entry for an `nf-core/...` pipeline name, or `None` for
        other names and names not in the catalog. Raises
        `RegistryUnavailableError` if the catalog can't be fetched."""
        if not name.startswith(NFCORE_PREFIX):
            return None
        return next((wf for wf in get_nfcore_pipelines() if wf.get("name") == name), None)

    @field_validator("name", mode="after")
    @classmethod
    def validate_nfcore_name(cls, value: str) -> str:
        if not value.startswith(NFCORE_PREFIX):
            return value
        try:
            nfcore_wf_info = cls.get_nfcore_info(value)
        except RegistryUnavailableError as e:
            raise ValueError(
                f"Can't look up '{value}' in the nf-core catalog: {e}. Check the network connection."
            ) from e
        if nfcore_wf_info is None:
            names = [p["name"] for p in get_nfcore_pipelines()]
            close = difflib.get_close_matches(value, names, n=1)
            hint = f" Did you mean '{close[0]}'?" if close else ""
            raise ValueError(f"'{value}' is not an nf-core pipeline.{hint}")
        return value

    @field_validator("path", mode="after")
    @classmethod
    def validate_path(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        name = info.data.get("name")
        if name and name.startswith(NFCORE_PREFIX):
            raise ValueError("nf-core pipelines run from their repository; leave out path.")
        if info.data.get("version") is not None:
            raise ValueError("A local pipeline has no version; leave out version (or path).")
        return value

    @field_validator("url", mode="after")
    @classmethod
    def validate_url(cls, value: str, info: ValidationInfo):
        if info.data.get("path") or "path" not in info.data:  # local, or path failed (its error says why)
            if value and info.data.get("path"):
                raise ValueError("Use either url (with version) or a local path, not both.")
            return value
        name = info.data.get("name")
        if name and name.startswith(NFCORE_PREFIX):
            nfcore_wf_info = cls.get_nfcore_info(name)
            assert nfcore_wf_info is not None  # checked by validate_nfcore_name
            if value and value != nfcore_wf_info["url"]:
                raise ValueError(
                    f"url '{value}' doesn't match nf-core's url for '{name}' ({nfcore_wf_info['url']}); "
                    "leave it out for nf-core pipelines."
                )
            return nfcore_wf_info["url"]

        if not value:
            raise ValueError("Pipelines outside nf-core need a repository url (https://...).")
        if not value.startswith("http"):
            raise ValueError("Url should start with https://")
        return value

    @field_validator("main_script", mode="after")
    @classmethod
    def validate_main_script(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None

        name = info.data.get("name")
        if name and name.startswith(NFCORE_PREFIX):
            raise ValueError("main_script cannot be set for nf-core pipelines")

        return value

    @model_validator(mode="before")
    @classmethod
    def populate_nfcore_fields(cls, data: dict) -> dict:
        # "" instead of a missing url or version, so their validators report it with a clear message
        if data.get("url") is None:
            data["url"] = ""
        if data.get("path"):
            return data
        if data.get("version") is None:
            data["version"] = ""

        name = data.get("name")
        if not isinstance(name, str) or not name:
            return data

        try:
            nfcore_info = cls.get_nfcore_info(name)
        except RegistryUnavailableError:
            nfcore_info = None
        if nfcore_info is None and name.startswith(NFCORE_PREFIX):
            # validate_nfcore_name reports the name; a stand-in url keeps that
            # the only error
            data["url"] = data["url"] or f"https://github.com/{name}"
            return data

        if nfcore_info:
            if not data.get("url"):
                data["url"] = nfcore_info["url"]
            if not data.get("description"):
                data["description"] = nfcore_info.get("description", "")

        return data

    def hash(self) -> str:
        data = f"{self.url}{self.version}" if not self.path else self.path
        data += self.nf_config or ""
        data += self.params_file or ""
        data += json.dumps(self.params, sort_keys=True, default=str)
        data += self.main_script or ""
        return hashlib.sha256(data.encode()).hexdigest()[:8]

    def model_dump_config(self) -> dict:
        fields = {
            "name",
            "version",
            "path",
            "url",
            "params_file",
            "nf_config",
            "params",
            "nf_profile",
            "main_script",
        }
        result = _params_last(self.model_dump(include=fields, exclude_none=True))
        if self.is_nfcore or not self.url:
            result.pop("url", None)
        # type omitted for pipelines — loader defaults to WorkflowType.NF_PIPELINE
        return result

    def model_dump_display(self) -> dict:
        fields = {
            "id",
            "name",
            "type",
            "version",
            "path",
            "url",
            "params_file",
            "params",
            "description",
            "is_nfcore",
            "nf_config",
            "nf_profile",
            "main_script",
        }
        return self.model_dump(include=fields, exclude_none=False)


# ---------------------------------------------------------------------------
# NfModule — nextflow module run
# ---------------------------------------------------------------------------


class NfModule(BaseWorkflow):
    """A Nextflow module step executed with 'nextflow module run'."""

    type: Literal[WorkflowType.NF_MODULE] = WorkflowType.NF_MODULE
    container_engine: Literal["docker", "singularity", "conda", "podman"] | None = None

    # `nextflow module` exists from this Nextflow version (major, minor) on
    MIN_NEXTFLOW_VERSION: ClassVar[tuple[int, int]] = (26, 4)

    def hash(self) -> str:
        data = f"{self.name}{self.version}"
        data += self.nf_config or ""
        data += json.dumps(self.params, sort_keys=True, default=str)
        data += self.container_engine or ""
        return hashlib.sha256(data.encode()).hexdigest()[:8]

    def model_dump_config(self) -> dict:
        fields = {"name", "version", "params", "nf_config", "container_engine"}
        result = _params_last(self.model_dump(include=fields, exclude_none=True))
        result["type"] = self.type  # always written — required to distinguish from NfPipeline on load
        return result

    def model_dump_display(self) -> dict:
        fields = {
            "id",
            "name",
            "type",
            "version",
            "params",
            "nf_config",
            "container_engine",
        }
        return self.model_dump(include=fields, exclude_none=False)


# Discriminated union used at deserialization boundaries (API, config load).
# Internal plumbing (graph, events, runner) uses the Workflow base class.
Workflow = Annotated[NfPipeline | NfModule, Field(discriminator="type")]


# ---------------------------------------------------------------------------
# GlobalOptions
# ---------------------------------------------------------------------------


class GlobalOptions(BaseModel):
    """Settings applied across every workflow in a metapipeline (the config's
    `globals:` key). `params` is merged under each workflow's own `params` at
    run time, with the workflow's own values winning on key collision;
    `nf_profile`/`nf_config` likewise act as a fallback a workflow can
    override, not a value forced onto it."""

    nf_profile: str | None = Field(default=None, validation_alias=NF_PROFILE_KEYS)
    nf_config: FilePath = Field(default=None, validation_alias=NF_CONFIG_KEYS)
    params: CoercedParams | None = None
    nextflow_version: str | int | float | None = None

    @field_validator("nf_profile", mode="after")
    @classmethod
    def validate_profile(cls, nf_profile: str | None):
        if not nf_profile:
            return None
        return nf_profile.replace(" ", "")

    @field_validator("nextflow_version", mode="before")
    @classmethod
    def validate_nextflow_version(cls, v: Any) -> str | tuple[int, int, int, int] | int | None:
        if v is None:
            return v

        if isinstance(v, (int, float)):
            return str(v)

        if not isinstance(v, str):
            raise ValueError(f"nextflow_version must be a string, integer, or float, got {type(v).__name__!r}.")

        numeric_part = v.removesuffix("-edge")

        raw_parts = numeric_part.split(".")
        if not 1 <= len(raw_parts) <= 3:
            raise ValueError(
                f"Invalid nextflow_version '{v}'. "
                "Expected 1-3 dot-separated integers with an optional '-edge' suffix, "
                "e.g. '25', '25.10', '25.10.4-edge'."
            )

        if not all(isinstance(x, int) for x in [int(p) for p in raw_parts]):
            raise ValueError(f"Non-integer component in nextflow_version '{v}'.")

        return v

    def nextflow_version_below(self, minimum: tuple[int, int]) -> bool:
        """Whether `nextflow_version` is known to be older than `minimum`
        (major, minor). A bare major version (`26`) only counts as older if
        its major is lower."""
        version = self.nextflow_version_tuple
        if version is None:
            return False
        if version[0] != minimum[0]:
            return version[0] < minimum[0]
        has_minor = "." in str(self.nextflow_version)
        return has_minor and version[1] < minimum[1]

    @property
    def nextflow_version_tuple(self) -> tuple[int, int, int, int] | None:
        """`nextflow_version` as `(major, minor, patch, is_edge)`, or `None`
        if unset. Missing minor/patch components default to `0`."""
        v = self.nextflow_version
        if v is None:
            return None

        v = str(v)
        edge_flag = 1 if v.endswith("-edge") else 0
        numeric_part = v.removesuffix("-edge")
        raw_parts = numeric_part.split(".")
        numeric = [int(p) for p in raw_parts]
        major = numeric[0]
        minor = numeric[1] if len(numeric) > 1 else 0
        patch = numeric[2] if len(numeric) > 2 else 0
        version_tuple = (major, minor, patch, edge_flag)
        return version_tuple


# ---------------------------------------------------------------------------
# Transition
# ---------------------------------------------------------------------------


class Transition(BaseModel):
    """A directed `source -> target` edge between two workflow ids.

    The legacy top-level `transitions:` representation; equivalent to the
    target workflow declaring `from: source`. Prefer `from:` in new configs.
    """

    target: str
    source: str

    @computed_field  # type: ignore[misc]
    @property
    def id(self) -> str:
        return f"{self.source}->{self.target}"

    def model_dump(self, *args, **kwargs) -> dict:
        fields = {"target", "source"}
        kwargs.setdefault("include", fields)
        return super().model_dump(*args, **kwargs)


def validate_config_version(config_version: str) -> str:
    result = re.match(r"^\d+\.\d+\.\d$", config_version)
    if not result:
        raise ValueError(f"Invalid config version: {config_version}")

    version = Version(result.string)
    if version < Version(CONFIG_VERSION_MIN):
        raise ValueError(f"Incompatible config version! Config version must be at least {CONFIG_VERSION_MIN}")

    if version > Version(CONFIG_VERSION_MAX):
        raise ValueError(f"Incompatible config version! Config version can be at most {CONFIG_VERSION_MAX}")

    return str(version)
