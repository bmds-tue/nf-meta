"""
WorkflowRun hierarchy: one class per WorkflowType, registered automatically.

Usage:
    run = WorkflowRun.for_step(wf, workdir, globals)
    run.prepare(resolved_params)
    cmd = run.get_cmd(resume=True, stub=False)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, cast

import yaml

from nf_meta.core.models import (
    GlobalOptions,
    NfModule,
    NfPipeline,
    Workflow,
    WorkflowType,
)
from .errors import NfMetaRunnerError
from .utils import check_nextflow

logger = logging.getLogger(__name__)

_REGISTRY: dict[WorkflowType, type["WorkflowRun"]] = {}


class WorkflowRun:
    """
    Abstract base for per-step command builders.

    Subclasses register themselves by passing `workflow_type=...` in the class
    statement.  The factory `WorkflowRun.for_step()` looks up the right subclass
    in `_REGISTRY` and returns an initialised instance.
    """

    def __init_subclass__(cls, workflow_type: Optional[WorkflowType] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if workflow_type is not None:
            _REGISTRY[workflow_type] = cls

    def __init__(
        self,
        wf: Workflow,
        workdir: Path,
        globals: Optional[GlobalOptions],
        extra_profile: str = "",
    ):
        self.wf = wf
        self.workdir = workdir
        self.globals = globals
        self.extra_profile = extra_profile
        self._params_file: Optional[Path] = None

    @classmethod
    def for_step(
        cls,
        wf: Workflow,
        workdir: Path,
        globals: Optional[GlobalOptions],
        extra_profile: str = "",
    ) -> "WorkflowRun":
        run_cls = _REGISTRY.get(WorkflowType(wf.type))
        if run_cls is None:
            raise NfMetaRunnerError(
                f"No WorkflowRun implementation registered for workflow type '{wf.type}'. "
                f"Known types: {list(_REGISTRY)}"
            )
        return run_cls(wf, workdir, globals, extra_profile)

    def prepare(self) -> None:
        """Create workdir and write params file from wf.params. Call before get_cmd()."""
        self.workdir.mkdir(parents=True, exist_ok=True)
        if self.wf.params:
            self._params_file = self.workdir / "params.yaml"
            with open(self._params_file, "w") as fh:
                yaml.dump(self.wf.params, fh)

    def get_cmd(self, resume: bool = False, stub: bool = False) -> list[str]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# NfPipeline — nextflow run <url> -r <version>
# ---------------------------------------------------------------------------


class NfPipelineRun(WorkflowRun, workflow_type=WorkflowType.NF_PIPELINE):
    def get_cmd(self, resume: bool = False, stub: bool = False) -> list[str]:
        wf = cast(NfPipeline, self.wf)

        cmd = [check_nextflow(), "run", "-ansi-log", "false"]

        if resume:
            cmd += ["-resume"]
        if stub:
            cmd += ["-stub"]

        if self.globals and self.globals.config_file:
            nf_cfg = Path(self.globals.config_file)
            if not nf_cfg.exists():
                raise NfMetaRunnerError(
                    f"Global config file does not exist: {nf_cfg}"
                )
            cmd += ["-c", str(nf_cfg)]

        if wf.config_file:
            cmd += ["-c", str(wf.config_file)]

        profiles: list[str] = []
        if self.globals and self.globals.profile and not wf.profile:
            profiles.append(self.globals.profile)
        if wf.profile:
            profiles.append(wf.profile)
        if self.extra_profile:
            profiles.append(self.extra_profile)

        cmd += ["-profile", ",".join(profiles)]

        if self._params_file:
            cmd += ["-params-file", str(self._params_file)]

        if wf.main_script:
            cmd += ["-main-script", wf.main_script]

        cmd += [wf.url, "-r", wf.version, "-latest"]
        return cmd


# ---------------------------------------------------------------------------
# NfModule — nextflow module run <name>@<version>
# ---------------------------------------------------------------------------


class NfModuleRun(WorkflowRun, workflow_type=WorkflowType.NF_MODULE):
    def get_cmd(self, resume: bool = False, stub: bool = False) -> list[str]:
        wf = cast(NfModule, self.wf)

        cmd = [check_nextflow(), "module", "run", "-ansi-log", "false"]

        if resume:
            cmd += ["-resume"]
        if stub:
            cmd += ["-stub"]

        if self.globals and self.globals.config_file:
            nf_cfg = Path(self.globals.config_file)
            if not nf_cfg.exists():
                raise NfMetaRunnerError(
                    f"Global config file does not exist: {nf_cfg}"
                )
            cmd += ["-c", str(nf_cfg)]

        if wf.config_file:
            cmd += ["-c", str(wf.config_file)]

        if wf.container_engine:
            cmd += [f"-with-{wf.container_engine}"]

        if self._params_file:
            cmd += ["-params-file", str(self._params_file)]

        cmd += [f"{wf.name}@{wf.version}"]
        return cmd
