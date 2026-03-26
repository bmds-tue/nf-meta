from dataclasses import dataclass
from pathlib import Path
from packaging.version import Version
from typing import Optional, Dict, List, Any, Annotated, TypeAlias
import logging
import re
import uuid
import hashlib
import json
import re

from pydantic import (BaseModel, Field, computed_field,
                        field_validator, model_validator, ValidationInfo,
                        AfterValidator)
from pydantic.functional_serializers import PlainSerializer
from pydantic_core import InitErrorDetails, PydanticCustomError, ValidationError

import yaml

from nf_meta.engine.nf_core_utils import get_nfcore_pipelines, url_exists

logger = logging.getLogger()

CONFIG_VERSION_MIN = "0.0.1"
CONFIG_VERSION_MAX = "0.9.9"


def is_existing_file_abs(path: Optional[Path] = None, allowed_extensions: Optional[tuple[str]] = None) -> Optional[Path]:
    if not path:
        return None

    path = Path(path).resolve()
    if not path.exists():
        raise ValueError("Path does not exist")

    if not path.is_file():
        raise ValueError("Path must be a file")
    
    if allowed_extensions is not None:
        if not path.suffix in allowed_extensions:
            raise ValueError(f"Path must end with {allowed_extensions}")
    
    return path


SerializeToStr = PlainSerializer(lambda v: str(v) if v else None, return_type=Optional[str])
ExistingAbsoluteFile = Annotated[Optional[Path], 
                                 AfterValidator(lambda v: is_existing_file_abs(v)),
                                 SerializeToStr]
ExistingYamlFile = Annotated[Optional[Path], 
                             AfterValidator(lambda v: is_existing_file_abs(v, (".yaml", ".yml"))),
                             SerializeToStr]
ExistingNfConfigFile = Annotated[Optional[Path], 
                                 AfterValidator(lambda v: is_existing_file_abs(v, (".config"))),
                                 SerializeToStr]


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
class ParamsReference(Reference):
    name: str
    source_key: str
    target_key: str


class Workflow(BaseModel):
    """
    Workflow representation for internal use 
    """

    id: str = Field(default_factory=lambda: "n" + create_id())
    name: str
    version: str
    url: str = "FOO"
    description: Optional[str] = None
    position: Optional[Position] = Field(default=Position(x=0, y=0))
    params_file: Optional[ExistingYamlFile] = None
    params: Optional[dict[str, str]] = None
    config_file: Optional[ExistingNfConfigFile] = None

    @computed_field
    @property
    def is_nfcore(self) -> bool:
        nfcore_pipelines = get_nfcore_pipelines()
        return any(p.get("name") == self.name for p in nfcore_pipelines)
    
    @computed_field
    @property
    def field_refs(self) -> list[ParamsReference]:
        if not self.params:
            return []

        pattern = re.compile(r'\$\{([^}]+):params:([^}]+)\}')

        refs = []
        for k, v in self.params.items():
            match = pattern.search(str(v))
            if match:
                refs.append(
                    ParamsReference(reference_name=match.group(0),
                                    source_wf_id=self.id,
                                    source_key=k,
                                    target_wf_id=match.group(1),
                                    target_key=match.group(2))
                )
        return refs

    @classmethod
    def get_nfcore_info(cls, name: str) -> Optional[dict]:
        nfcore_pipelines = get_nfcore_pipelines()
        nfcore_info = next(
            (wf for wf in nfcore_pipelines if wf.get("name") == name),
            None)
        return nfcore_info
    
    @field_validator("url", mode="after")
    @classmethod
    def validate_url(cls, value: Optional[str], info: ValidationInfo):
        name = info.data.get("name")
        if not name:
            return value
        
        nfcore_wf_info = cls.get_nfcore_info(name)
        is_nfcore = bool(nfcore_wf_info)

        if not value:
            if not is_nfcore:
                raise ValueError("Workflows from outside nf-core must specify a repository!") 
            return nfcore_wf_info.get("url")
        
        if is_nfcore and value != nfcore_wf_info.get("url"):
            raise ValueError("nf-core workflow referenced, but url does not match!")
        
        if (not is_nfcore 
            and not value.startswith("http")):
            raise ValueError("Url should start with https://")

        if not is_nfcore and not url_exists(value):
            raise ValueError("Invalid or inaccessible pipeline url")

        return value

    @model_validator(mode="before")
    @classmethod
    def populate_nfcore_fields(cls, data: dict) -> dict:
        
        # For non nf-core workflows: Explicitly mark url as provided
        # (even if None) so the field_validator is not skipped!
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

    def hash(self):
        data = f"{self.url}{self.version}"
        data += str(self.config_file.absolute()) if self.config_file else ""
        data += str(self.params_file.absolute()) if self.params_file else ""
        data += json.dumps(self.params, sort_keys=True, default=str)
        hashed = hashlib.sha256(data.encode()).hexdigest()[:8]
        return hashed

    def model_dump_config(self) -> dict:
        fields = {"id", "name", "version", "url", "params_file", "config_file", "params"}
        return self.model_dump(include=fields, exclude_none=True)
    
    def model_dump_display(self) -> dict:
        fields = {"id", "name", "version", "url", "params_file", "params",
                  "description", "is_nfcore", "position", "config_file"}
        return self.model_dump(include=fields, exclude_none=False)
    
    def model_dump(self, **kwargs: Any):
        # overwrite default serialization behavior
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)


class GlobalOptions(BaseModel):
    nf_profile: Optional[str] = None
    nf_config_file: Optional[ExistingNfConfigFile] = None
    nf_params: Optional[dict[str, Any]] = None

    @field_validator("nf_profile", mode="after")
    def validate_profile(cls, profile: Optional[str], info: ValidationInfo):
        if not profile:
            return None

        return profile.replace(" ", "")


class Transition(BaseModel):
    id: str = Field(default_factory=lambda: "e" + create_id())
    target: str
    source: str
    params_file: Optional[Path] = Field(default=None, alias="params-file")
    config_file: Optional[Path] = Field(default=None, alias="config-file")
    adapter: Optional[str] = None
    params: Optional[List[Dict[str, Any]]] = None

    def model_dump_display(self) -> dict:
        return self.model_dump(exclude_none=False)


class MetaworkflowConfig(BaseModel):
    config_version: str
    workflows: List[Workflow]
    globals: Optional[GlobalOptions] = None
    transitions: List[Transition]

    # ------------------------------
    # Validation: transitions refer to real workflow IDs
    # ------------------------------
    @model_validator(mode="after")
    def transitions_valid(self):
        all_ids = {w.id for w in self.workflows}
        for tr in self.transitions:
            if tr.target not in all_ids:
                raise ValueError(f"transition 'target' references unknown workflow id: {tr.target}")
            if tr.source and tr.source not in all_ids:
                raise ValueError(f"transition 'source' references unknown workflow id: {tr.source}")
        return self

    @field_validator("config_version")
    @classmethod
    def config_version_valid(cls, config_version):
        result = re.match(r"^\d+\.\d+\.\d$", config_version)
        if not result:
            raise ValueError(f"Invalid config version: {config_version}")
        
        version = Version(result.string)
        if version < Version(CONFIG_VERSION_MIN):
            raise ValueError(f"Incompatible config version! Config version must be at least {CONFIG_VERSION_MIN}")

        if version > Version(CONFIG_VERSION_MAX):
            raise ValueError(f"Incompatible config version! Config version can be at most {CONFIG_VERSION_MAX}")

        return str(version)


def load_config(path: Path) -> MetaworkflowConfig:
    with open(path) as fh:
        data = yaml.safe_load(fh)
    return MetaworkflowConfig.model_validate(data)


def dump_config(config: MetaworkflowConfig, path: Path):
    config_dict = {
        "config_version": config.config_version,
        "globals": config.globals.model_dump(exclude_none=True) if config.globals else None,
        "workflows": [w.model_dump_config() for w in config.workflows],
        "transitions": [t.model_dump(by_alias=True, exclude_none=True) for t in config.transitions],
    }
    with open(path, "w") as fh:
        yaml.safe_dump(config_dict, fh, sort_keys=False)
