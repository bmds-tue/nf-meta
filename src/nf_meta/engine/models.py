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
    id: str
    pipeline_description: Optional[str] = None
    name: str
    pipeline_location: Optional[str] = None
    version: str
    is_nfcore: Optional[bool] = None
    layout_coords: Optional[tuple[float, float]] = None


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
    
    # ------------------------------
    # Validation: transitions refer to nf-core workflow IDs
    # ------------------------------
    @field_validator("workflows")
    @classmethod
    def workflows_exist_in_nfcore_or_have_location(cls, workflows):
        nf_core_pipelines = get_nfcore_pipelines()
        nf_core_pipeline_names = {w.get("name") for w in nf_core_pipelines}

        if not len(nf_core_pipelines):
            logger.warning("Workflows could not be validated against nf-core")
            return workflows
        
        for w in workflows:
            w.is_nfcore = w.name in nf_core_pipeline_names

            # For nf-core pipelines, make an attempt to read the description           
            if w.is_nfcore:
                nfcore_wf_info = list(filter(lambda wf: wf.get("name") == w.name, nf_core_pipelines))[0]
                w.pipeline_description = nfcore_wf_info.get("description", "")

        non_nfcore_wfs = list(filter(lambda wf: not wf.is_nfcore, workflows))
        if len(non_nfcore_wfs):
            names = list(map(lambda w: w.name, non_nfcore_wfs))
            logger.warning(f"Potentially uncompatible workflows found, which are not officially supported by nf-core: {", ".join(names)}")

            no_repo_wfs = list(filter(lambda wf: not wf.pipeline_location, workflows))
            if len(no_repo_wfs):
                names = list(map(lambda w: w.name, no_repo_wfs))
                raise ValueError(f"Workflows from outside nf-core must specify a repository! No `pipeline_location` found for: {", ".join(names)}")
        return workflows

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
