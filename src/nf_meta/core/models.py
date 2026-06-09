from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from packaging.version import Version
from typing import Optional, List, Any, Annotated, Literal
import logging
import re
import uuid
import hashlib
import json

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
import yaml

from nf_meta.core.nf_core_utils import (
    get_nfcore_pipelines,
    url_exists,
    github_file_exists,
)

logger = logging.getLogger()

CONFIG_VERSION_MIN = "0.0.1"
CONFIG_VERSION_MAX = "0.2.0"


class WorkflowType(StrEnum):
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


def coerce_param_values_to_str(v: Any) -> Optional[dict[str, str]]:
    if v is None:
        return None

    if not isinstance(v, dict):
        raise ValueError(
            f"Params must be a key-value mapping, got {type(v).__name__!r}"
        )

    COERCIBLE = (str, int, float, bool)
    coerced = {}
    errors = []
    for key, value in v.items():
        if not isinstance(value, COERCIBLE):
            errors.append(
                f"\tParam '{key}' has unsupported type {type(value).__name__}"
            )
        else:
            coerced[key] = str(value)

    if errors:
        raise ValueError("\n" + "\n".join(errors))

    return coerced


CoercedParams = Annotated[
    Optional[dict[str, str]], BeforeValidator(coerce_param_values_to_str)
]


def create_id():
    return str(uuid.uuid4())[:8]


class Position(BaseModel):
    x: int
    y: int


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


class Workflow(BaseModel):
    """
    Base class for all metapipeline steps.
    Concrete types: NfPipeline, NfModule.
    """

    type: WorkflowType
    id: str = Field(default_factory=lambda: "n" + create_id())
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    position: Optional[Position] = Field(default=Position(x=0, y=0))
    params: Optional[CoercedParams] = None
    config_file: Optional[ExistingNfConfigFile] = None

    @computed_field  # type: ignore[misc]
    @property
    def field_refs(self) -> list[WorkflowReference]:
        if not self.params:
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

    @model_validator(mode="after")
    def warn_malformed_refs(self) -> "Workflow":
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

    def model_dump_config(self) -> dict:
        raise NotImplementedError

    def model_dump_display(self) -> dict:
        raise NotImplementedError

    def model_dump(self, **kwargs: Any):
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)


# ---------------------------------------------------------------------------
# NfPipeline — nextflow run
# ---------------------------------------------------------------------------


class NfPipeline(Workflow):
    """A Nextflow pipeline step executed with 'nextflow run'."""

    type: Literal[WorkflowType.NF_PIPELINE] = WorkflowType.NF_PIPELINE
    url: str
    description: Optional[str] = None
    params_file: Optional[ExistingYamlFile] = None
    profile: Optional[str] = None
    main_script: Optional[str] = None

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

        if not is_nfcore and not url_exists(value):
            raise ValueError("Invalid or inaccessible pipeline url")

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

        url = info.data.get("url")
        version = info.data.get("version")

        if url and "github.com" in url and version:
            if not github_file_exists(url, value, version):
                raise ValueError(
                    f"main_script '{value}' not found in repository '{url}' at ref '{version}'"
                )
        else:
            logger.warning(
                "Cannot validate main_script '%s': '%s' is not a GitHub URL",
                value,
                url,
            )

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
            "position",
            "config_file",
            "profile",
            "main_script",
        }
        return self.model_dump(include=fields, exclude_none=False)


# ---------------------------------------------------------------------------
# NfModule — nextflow module run
# ---------------------------------------------------------------------------


class NfModule(Workflow):
    """A Nextflow module step executed with 'nextflow module run'."""

    type: Literal[WorkflowType.NF_MODULE] = WorkflowType.NF_MODULE
    container_engine: Optional[Literal["docker", "singularity", "conda", "podman"]] = (
        None
    )

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
            "position",
            "config_file",
            "container_engine",
        }
        return self.model_dump(include=fields, exclude_none=False)


# Discriminated union used at deserialization boundaries (API, config load).
# Internal plumbing (graph, events, runner) uses the Workflow base class.
AnyWorkflow = Annotated[NfPipeline | NfModule, Field(discriminator="type")]


# ---------------------------------------------------------------------------
# GlobalOptions
# ---------------------------------------------------------------------------


class GlobalOptions(BaseModel):
    profile: Optional[str] = None
    config_file: Optional[ExistingNfConfigFile] = None
    params: Optional[CoercedParams] = None
    nextflow_version: Optional[tuple[int, int, int, int]] = None

    @field_validator("profile", mode="after")
    @classmethod
    def validate_profile(cls, profile: Optional[str]):
        if not profile:
            return None
        return profile.replace(" ", "")

    @field_validator("nextflow_version", mode="before")
    @classmethod
    def extract_nextflow_tuple(cls, v: Any) -> Optional[tuple[int, int, int, int]]:
        if v is None:
            return v

        if isinstance(v, (tuple, list)):
            if len(v) == 4 and all(isinstance(x, int) for x in v):
                return tuple(v)
            raise ValueError(
                f"nextflow_version tuple must have exactly 4 int elements, got {v!r}."
            )

        if isinstance(v, (int, float)):
            v = str(v)

        if not isinstance(v, str):
            raise ValueError(
                f"nextflow_version must be a string or 4-tuple of ints, got {type(v).__name__!r}."
            )

        edge_flag = 1 if v.endswith("-edge") else 0
        numeric_part = v.removesuffix("-edge")

        raw_parts = numeric_part.split(".")
        if not 1 <= len(raw_parts) <= 3:
            raise ValueError(
                f"Invalid nextflow_version '{v}'. "
                "Expected 1-3 dot-separated integers with an optional '-edge' suffix, "
                "e.g. '25', '25.10', '25.10.4-edge'."
            )

        try:
            numeric = [int(p) for p in raw_parts]
        except ValueError:
            raise ValueError(f"Non-integer component in nextflow_version '{v}'.")

        major = numeric[0]
        minor = numeric[1] if len(numeric) > 1 else 0
        patch = numeric[2] if len(numeric) > 2 else 0

        return (major, minor, patch, edge_flag)


# ---------------------------------------------------------------------------
# Transition
# ---------------------------------------------------------------------------


class Transition(BaseModel):
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


# ---------------------------------------------------------------------------
# MetaworkflowConfig
# ---------------------------------------------------------------------------


class MetaworkflowConfig(BaseModel):
    config_version: str
    workflows: List[AnyWorkflow]
    globals: Optional[GlobalOptions] = None
    transitions: List[Transition]

    @model_validator(mode="before")
    @classmethod
    def normalize_dict_to_list(cls, data: dict) -> dict:
        """
        Accept either list format (legacy) or dict format (new), where
        dict keys become the `id` field of each item.
        Missing `type` defaults to WorkflowType.NF_PIPELINE for backward compatibility.
        """
        value = data.get("workflows")
        if isinstance(value, dict):
            items = []
            for key, item in value.items():
                if not isinstance(item, dict):
                    raise ValueError(
                        f"Invalid definition of workflow {key}: Must be a key-value mapping, got '{str(item)}' instead"
                    )
                item.setdefault("type", WorkflowType.NF_PIPELINE)
                items.append({"id": key, **item})
            data["workflows"] = items
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    item.setdefault("type", WorkflowType.NF_PIPELINE)
        return data

    @model_validator(mode="after")
    def transitions_valid(self):
        all_ids = {w.id for w in self.workflows}
        for tr in self.transitions:
            if tr.target not in all_ids:
                raise ValueError(
                    f"transition 'target' references unknown workflow id: {tr.target}"
                )
            if tr.source and tr.source not in all_ids:
                raise ValueError(
                    f"transition 'source' references unknown workflow id: {tr.source}"
                )
        return self

    @field_validator("config_version")
    @classmethod
    def config_version_valid(cls, config_version):
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


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def load_config(path: Path) -> MetaworkflowConfig:
    with open(path) as fh:
        data = yaml.safe_load(fh)
    return MetaworkflowConfig.model_validate(data)


def dump_config(config: MetaworkflowConfig, path: Path):
    config_dict = {
        "config_version": config.config_version,
        "globals": config.globals.model_dump(exclude_none=True)
        if config.globals
        else None,
        "workflows": {
            w.id: {k: v for k, v in w.model_dump_config().items()}
            for w in config.workflows
        },
        "transitions": [t.model_dump() for t in config.transitions],
    }
    if not config_dict["globals"]:
        del config_dict["globals"]

    with open(path, "w") as fh:
        yaml.safe_dump(config_dict, fh, sort_keys=False)
