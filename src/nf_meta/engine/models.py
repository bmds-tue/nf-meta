from pathlib import Path
from packaging.version import Version
from typing import Optional, Dict, List, Any
import logging
import re

from pydantic import BaseModel, Field, field_validator, model_validator, ValidationError, ValidationInfo
import yaml

from nf_meta.engine.nf_core_utils import get_nfcore_pipelines

logger = logging.getLogger()

CONFIG_VERSION_MIN = "0.0.1"
CONFIG_VERSION_MAX = "0.9.9"


class Workflow(BaseModel):
    def model_dump(self, **kwargs: Any):
        # overwrite default serialization behavior
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)

    id: str
    name: str
    pipeline_description: Optional[str] = Field(default=None, exclude=True)
    pipeline_location: Optional[str] = None
    version: str
    is_nfcore: Optional[bool] = Field(default=None, exclude=True)
    layout_coords: Optional[tuple[float, float]] = Field(default=None, exclude=True)

    # TODO: do nf-core validation here:
    # Is it nfcore pipeline? -> set is_nfcore
    # -> add pipeline_description if possible

    @model_validator(mode="after")
    def is_nfcore_workflow(self):
        nfcore_pipelines = get_nfcore_pipelines()
        nfcore_wf_info = list(filter(lambda wf: wf.get("name") == self.name, nfcore_pipelines))
        self.is_nfcore = bool(len(nfcore_wf_info))

        if self.is_nfcore:
            nfcore_wf_info = nfcore_wf_info[0]
            self.pipeline_description = nfcore_wf_info.get("description", "")
        else:
            logger.warning(f"Potentially uncompatible workflows, which is not officially supported by nf-core: {self.name}")
            if not self.pipeline_location:
                raise ValueError(f"No `pipeline_location` specified for '{self.name}'. Workflows from outside nf-core must specify a repository!")
        
        return self


class VerboseWorkflow(Workflow):
    # Includes the optional fields in the parent definition
    pipeline_description: Optional[str] = None
    layout_coords: Optional[tuple[float, float]] = None
    is_nfcore: Optional[bool] = None


class WorkflowOptions(BaseModel):
    wf_opts: str


class Transition(BaseModel):
    run: str
    from_: Optional[str] = Field(default=None, alias="from")
    params_file: Optional[Path] = Field(default=None, alias="params-file")
    config_file: Optional[Path] = Field(default=None, alias="config-file")
    adapter: Optional[str] = None
    params: Optional[List[Dict[str, Any]]] = None


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
            if tr.run not in all_ids:
                raise ValueError(f"transition 'run' references unknown workflow id: {tr.run}")
            if tr.from_ and tr.from_ not in all_ids:
                raise ValueError(f"transition 'from' references unknown workflow id: {tr.from_}")
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
    with open(path, "w") as fh:
        yaml.safe_dump(config.model_dump(by_alias=True, exclude_none=True), fh, sort_keys=False)


def dump_config_dict(config: dict, path: Path):
    with open(path, "w") as fh:
        yaml.safe_dump(config, fh, sort_keys=False)
