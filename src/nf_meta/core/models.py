from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from packaging.version import Version
from typing import Optional, Any, Annotated, Literal
import logging
import re
import uuid
import hashlib
import json

import yaml
from pydantic import (
    BaseModel,
    Field,
    computed_field,
    field_validator,
    model_validator,
    ValidationInfo,
    AfterValidator,
    BeforeValidator,
)
from pydantic.functional_serializers import PlainSerializer

from nf_meta.core.nf_core_utils import get_nfcore_pipelines

logger = logging.getLogger()

CONFIG_VERSION_MIN = "0.0.1"
CONFIG_VERSION_MAX = "0.3.0"


class WorkflowType(StrEnum):
    """Discriminates the two workflow shapes a config's `type:` key selects
    between: a full `nextflow run` pipeline, or a single `nextflow module run`."""

    NF_PIPELINE = "nf-pipeline"
    NF_MODULE = "nf-module"


# Captures: ${<wf_id>:<namespace>:<key>}  where namespace is "params" or "outputs"
_VALID_REF_PATTERN = re.compile(r"\$\{([^}]+):(params|outputs):([^}]+)\}")
_ANY_BRACE_PATTERN = re.compile(r"\$\{[^}]*\}")


def is_existing_file_abs(
    path: Optional[Path] = None, allowed_extensions: Optional[tuple[str]] = None
) -> Optional[Path]:
    if not path:
        return None

    path = Path(path).resolve()
    if not path.exists():
        raise ValueError("Path does not exist")

    if not path.is_file():
        raise ValueError("Path must be a file")

    if allowed_extensions is not None:
        if path.suffix not in allowed_extensions:
            raise ValueError(f"Path must end with {allowed_extensions}")

    return path


SerializeToStr = PlainSerializer(
    lambda v: str(v) if v else None, return_type=Optional[str]
)
ExistingAbsoluteFile = Annotated[
    Optional[Path], AfterValidator(lambda v: is_existing_file_abs(v)), SerializeToStr
]
ExistingYamlFile = Annotated[
    Optional[Path],
    AfterValidator(lambda v: is_existing_file_abs(v, (".yaml", ".yml"))),
    SerializeToStr,
]
ExistingNfConfigFile = Annotated[
    Optional[Path],
    AfterValidator(lambda v: is_existing_file_abs(v, (".config"))),
    SerializeToStr,
]


def validate_param_scalars(v: Any) -> Optional[dict[str, Any]]:
    """Validate that every param value is a scalar, preserving its type."""
    if v is None:
        return None

    if not isinstance(v, dict):
        raise ValueError(
            f"Params must be a key-value mapping, got {type(v).__name__!r}"
        )

    SCALAR = (str, int, float, bool)
    errors = [
        f"\tParam '{key}' has unsupported type {type(value).__name__}"
        for key, value in v.items()
        if not isinstance(value, SCALAR)
    ]

    if errors:
        raise ValueError("\n" + "\n".join(errors))

    return v


CoercedParams = Annotated[
    Optional[dict[str, Any]], BeforeValidator(validate_param_scalars)
]


def load_params_file(path: Path) -> dict:
    """Load a YAML params-file into a dict ({} if empty or not a mapping)."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    return data if isinstance(data, dict) else {}


def create_id():
    return str(uuid.uuid4())[:8]


@dataclass
class Reference:
    name: Optional[str]
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
    config_file: Optional[ExistingNfConfigFile] = None

    @computed_field  # type: ignore[misc]
    @property
    def field_refs(self) -> list[WorkflowReference]:
        if not getattr(self, "params", False):
            return []
        refs = []
        for k, v in self.params.items():
            match = _VALID_REF_PATTERN.search(str(v))
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

    @field_validator("version", mode="after")
    @classmethod
    def validate_version_ref(cls, value: str) -> str:
        if re.match(r"^v?\d", value) or re.match(r"^[0-9a-fA-F]{7,40}$", value):
            return value
        raise ValueError(
            f"Version '{value}' looks like a branch name. "
            "Use a release tag (e.g. '1.2.3', 'v1.2.3') or a commit SHA "
            "to ensure reproducibility."
        )

    @model_validator(mode="after")
    def warn_malformed_refs(self) -> "BaseWorkflow":
        if not self.params:
            return self
        for k, v in self.params.items():
            for token in _ANY_BRACE_PATTERN.findall(str(v)):
                if not _VALID_REF_PATTERN.search(token):
                    logger.warning(
                        "Potentially invalid reference in workflow %s, "
                        "param '%s': %s — expected ${<wf_id>:(params|outputs):<key>}",
                        self.id,
                        k,
                        token,
                    )
        return self

    def hash(self) -> str:
        data = f"{self.name}{self.version}"
        data += json.dumps(self.params, sort_keys=True, default=str)
        data += str(self.config_file.absolute()) if self.config_file else ""
        return hashlib.sha256(data.encode()).hexdigest()[:8]

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


class NfPipeline(BaseWorkflow):
    """A Nextflow pipeline step executed with 'nextflow run'."""

    type: Literal[WorkflowType.NF_PIPELINE] = WorkflowType.NF_PIPELINE
    url: str
    description: Optional[str] = None
    params_file: Optional[ExistingYamlFile] = None
    profile: Optional[str] = None
    main_script: Optional[str] = None
    # Declared after url/params_file so that field_validator("params") can access
    # both via info.data (Pydantic validates fields in declaration order).
    # validate_default=True ensures the validator runs even when params is omitted.
    params: Optional[CoercedParams] = Field(default=None, validate_default=True)

    @computed_field  # type: ignore[misc]
    @property
    def is_nfcore(self) -> bool:
        nfcore_pipelines = get_nfcore_pipelines()
        return any(p.get("name") == self.name for p in nfcore_pipelines)

    @classmethod
    def get_nfcore_info(cls, name: str) -> Optional[dict]:
        nfcore_pipelines = get_nfcore_pipelines()
        return next((wf for wf in nfcore_pipelines if wf.get("name") == name), None)

    @field_validator("url", mode="after")
    @classmethod
    def validate_url(cls, value: Optional[str], info: ValidationInfo):
        name = info.data.get("name")
        nfcore_wf_info = cls.get_nfcore_info(name) if name else None
        is_nfcore = bool(nfcore_wf_info)

        if not value:
            if not is_nfcore:
                raise ValueError(
                    "Workflows from outside nf-core must specify a repository!"
                )
            return nfcore_wf_info.get("url")  # type: ignore

        if is_nfcore and value != nfcore_wf_info.get("url"):  # type: ignore
            raise ValueError("nf-core workflow referenced, but url does not match!")

        if not is_nfcore and not value.startswith("http"):
            raise ValueError("Url should start with https://")

        return value

    @field_validator("main_script", mode="after")
    @classmethod
    def validate_main_script(
        cls, value: Optional[str], info: ValidationInfo
    ) -> Optional[str]:
        if value is None:
            return None

        name = info.data.get("name")
        if name and cls.get_nfcore_info(name):
            raise ValueError("main_script cannot be set for nf-core workflows")

        return value

    @model_validator(mode="before")
    @classmethod
    def populate_nfcore_fields(cls, data: dict) -> dict:
        data.setdefault("url", None)

        name = data.get("name")
        if not name:
            return data

        nfcore_info = cls.get_nfcore_info(name)

        if nfcore_info:
            if not data.get("url"):
                data["url"] = nfcore_info["url"]
            if not data.get("description"):
                data["description"] = nfcore_info.get("description", "")

        return data

    def hash(self) -> str:
        data = f"{self.url}{self.version}"
        data += str(self.config_file.absolute()) if self.config_file else ""
        data += str(self.params_file.absolute()) if self.params_file else ""
        data += json.dumps(self.params, sort_keys=True, default=str)
        data += self.main_script or ""
        return hashlib.sha256(data.encode()).hexdigest()[:8]

    def model_dump_config(self) -> dict:
        fields = {
            "name",
            "version",
            "url",
            "params_file",
            "config_file",
            "params",
            "profile",
            "main_script",
        }
        result = self.model_dump(include=fields, exclude_none=True)
        if self.is_nfcore:
            result.pop("url", None)
        # type omitted for pipelines — loader defaults to WorkflowType.NF_PIPELINE
        return result

    def model_dump_display(self) -> dict:
        fields = {
            "id",
            "name",
            "type",
            "version",
            "url",
            "params_file",
            "params",
            "description",
            "is_nfcore",
            "config_file",
            "profile",
            "main_script",
        }
        return self.model_dump(include=fields, exclude_none=False)


# ---------------------------------------------------------------------------
# NfModule — nextflow module run
# ---------------------------------------------------------------------------


class NfModule(BaseWorkflow):
    """A Nextflow module step executed with 'nextflow module run'."""

    type: Literal[WorkflowType.NF_MODULE] = WorkflowType.NF_MODULE
    container_engine: Optional[Literal["docker", "singularity", "conda", "podman"]] = (
        None
    )
    # validate_default=True ensures the params field_validator runs even when
    # params is absent from the input (Pydantic skips field validators for defaults otherwise).
    params: Optional[CoercedParams] = Field(default=None, validate_default=True)

    def hash(self) -> str:
        data = f"{self.name}{self.version}"
        data += str(self.config_file.absolute()) if self.config_file else ""
        data += json.dumps(self.params, sort_keys=True, default=str)
        data += self.container_engine or ""
        return hashlib.sha256(data.encode()).hexdigest()[:8]

    def model_dump_config(self) -> dict:
        fields = {"name", "version", "params", "config_file", "container_engine"}
        result = self.model_dump(include=fields, exclude_none=True)
        result["type"] = (
            self.type
        )  # always written — required to distinguish from NfPipeline on load
        return result

    def model_dump_display(self) -> dict:
        fields = {
            "id",
            "name",
            "type",
            "version",
            "params",
            "config_file",
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
    `profile`/`config_file` likewise act as a fallback a workflow can
    override, not a value forced onto it."""

    profile: Optional[str] = None
    config_file: Optional[ExistingNfConfigFile] = None
    params: Optional[CoercedParams] = None
    nextflow_version: Optional[str | int | float] = None

    @field_validator("profile", mode="after")
    @classmethod
    def validate_profile(cls, profile: Optional[str]):
        if not profile:
            return None
        return profile.replace(" ", "")

    @field_validator("nextflow_version", mode="before")
    @classmethod
    def validate_nextflow_version(
        cls, v: Any
    ) -> Optional[str | tuple[int, int, int, int] | int]:
        if v is None:
            return v

        if isinstance(v, int) or isinstance(v, float):
            return str(v)

        if not isinstance(v, str):
            raise ValueError(
                f"nextflow_version must be a string, integer, or float, got {type(v).__name__!r}."
            )

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

    @property
    def nextflow_version_tuple(self) -> Optional[tuple[int, int, int, int]]:
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
        raise ValueError(
            f"Incompatible config version! Config version must be at least {CONFIG_VERSION_MIN}"
        )

    if version > Version(CONFIG_VERSION_MAX):
        raise ValueError(
            f"Incompatible config version! Config version can be at most {CONFIG_VERSION_MAX}"
        )

    return str(version)
