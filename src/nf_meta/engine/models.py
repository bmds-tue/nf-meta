from pathlib import Path
from packaging.version import Version
from typing import Optional, Dict, List, Any
import logging
import re
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator
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
    is_nfcore: Optional[bool] = None
    position: Optional[Position] = Field(default=Position(x=0, y=0))

    @model_validator(mode="after")
    def is_nfcore_workflow(self):
        nfcore_pipelines = get_nfcore_pipelines()
        nfcore_wf_info = list(filter(lambda wf: wf.get("name") == self.name, nfcore_pipelines))
        self.is_nfcore = bool(len(nfcore_wf_info))

        if self.is_nfcore:
            nfcore_wf_info = nfcore_wf_info[0]
            self.description = nfcore_wf_info.get("description", "")
        else:
            logger.warning(f"Potentially uncompatible workflow, not officially supported by nf-core: {self.name}")

            if not self.url:
                raise ValueError(f"No `url` specified for '{self.name}'. Workflows from outside nf-core must specify a repository!")
        
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
