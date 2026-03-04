from pathlib import Path
from packaging.version import Version
from typing import Optional, Dict, List, Any
import logging
import re
import uuid

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator, ValidationInfo
import yaml

from nf_meta.engine.nf_core_utils import get_nfcore_pipelines

logger = logging.getLogger()

CONFIG_VERSION_MIN = "0.0.1"
CONFIG_VERSION_MAX = "0.9.9"


def create_id():
    return str(uuid.uuid4())[:8]


class Position(BaseModel):
    x: int
    y: int


class Workflow(BaseModel):
    """
    Workflow representation for internal use 
    """

    id: str = Field(default_factory=create_id)
    name: str
    version: str
    url: Optional[str] = None
    description: Optional[str] = None
    position: Optional[Position] = Field(default=Position(x=0, y=0))

    @computed_field
    @property
    def is_nfcore(self) -> bool:
        nfcore_pipelines = get_nfcore_pipelines()
        return any(p.get("name") == self.name for p in nfcore_pipelines)

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
            raise ValueError("Nf-core workflow referenced, but url does not match!")
        
        # TODO: Actually check the url!?

        return value

    @model_validator(mode="after")
    def populate_nfcore_fields(self):
        nfcore_wf_info = self.get_nfcore_info(self.name)
        is_nfcore = bool(nfcore_wf_info)

        if is_nfcore:
            self.description = nfcore_wf_info.get("description", "")
        
        return self

    def model_dump_config(self) -> dict:
        fields = {"id", "name", "version", "url"}
        return self.model_dump(include=fields, exclude_none=True)
    
    def model_dump_display(self) -> dict:
        fields = {"id", "name", "version", "url",
                  "description", "is_nfcore", "position"}
        return self.model_dump(include=fields, exclude_none=False)
    
    def model_dump(self, **kwargs: Any):
        # overwrite default serialization behavior
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)


class WorkflowOptions(BaseModel):
    wf_opts: str


class Transition(BaseModel):
    id: str = Field(default_factory=create_id)
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
    workflow_opts: Optional[WorkflowOptions] = None
    workflow_opts_custom: Optional[WorkflowOptions] = None
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
        "workflows": [w.model_dump_config() for w in config.workflows],
        "workflow_opts": config.workflow_opts.model_dump(exclude_none=True) if config.workflow_opts else None,
        "workflow_opts_custom": config.workflow_opts_custom.model_dump(exclude_none=True) if config.workflow_opts_custom else None,
        "transitions": [t.model_dump(by_alias=True, exclude_none=True) for t in config.transitions],
    }
    with open(path, "w") as fh:
        yaml.safe_dump(config_dict, fh, sort_keys=False)
