"""Engines turn a `StepSpec` into the command that runs it, one engine per
`WorkflowType`. Engines register themselves by passing `workflow_type=...` in
the class statement; `engine_for()` looks them up.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

from nf_meta.core.models import NfModule, NfPipeline, WorkflowType
from nf_meta.core.registry import registry_module_name

from .errors import NfMetaRunnerError
from .spec import StepSpec

PARAMS_FILE = "params.yaml"

_REGISTRY: dict[WorkflowType, "Engine"] = {}


@dataclass(frozen=True)
class StepCommand:
    """A step's command, ready to execute.

    Attributes:
        argv: The command line. `argv[0]` is the bare executable name
            (`"nextflow"`); executors resolve it on `PATH`.
        cwd: Directory to run the command in.
        env: Environment variables to set on top of the current environment.
        params_file: Where the params file must be written before running,
            or `None` if the step has no params.
        params: Content of the params file.
    """

    argv: list[str]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)
    params_file: Path | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def write_files(self) -> None:
        """Write the params file, if any, creating its directory."""
        if self.params_file is None:
            return
        self.params_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.params_file, "w") as fh:
            yaml.dump(self.params, fh)


class Engine(ABC):
    """Builds commands for one `WorkflowType`. `build` has no side effects."""

    def __init_subclass__(cls, workflow_type: WorkflowType | None = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if workflow_type is not None:
            _REGISTRY[workflow_type] = cls()

    @abstractmethod
    def build(self, spec: StepSpec) -> StepCommand: ...

    @staticmethod
    def _params_file(spec: StepSpec) -> Path | None:
        return spec.state_dir / PARAMS_FILE if spec.params else None


def _nextflow(spec: StepSpec, *subcommand: str) -> list[str]:
    """`nextflow [-log <file>] <subcommand...> -ansi-log false [-w <dir>]`.
    `-log` is a global option and must precede the subcommand."""
    argv = ["nextflow"]
    if spec.log_file:
        argv += ["-log", str(spec.log_file)]
    argv += [*subcommand, "-ansi-log", "false"]
    if spec.work_dir:
        argv += ["-w", str(spec.work_dir)]
    return argv


def _env(spec: StepSpec) -> dict[str, str]:
    if spec.nextflow_cache_dir is None:
        return {}
    return {"NXF_CACHE_DIR": str(spec.nextflow_cache_dir)}


def engine_for(workflow_type: WorkflowType) -> Engine:
    """Return the engine registered for `workflow_type`.

    Raises:
        NfMetaRunnerError: if no engine is registered for it.
    """
    engine = _REGISTRY.get(WorkflowType(workflow_type))
    if engine is None:
        raise NfMetaRunnerError(
            f"No engine registered for step type '{workflow_type}'. Known types: {[str(t) for t in _REGISTRY]}"
        )
    return engine


class NextflowPipelineEngine(Engine, workflow_type=WorkflowType.NF_PIPELINE):
    """`nextflow run <url> -r <version>`."""

    def build(self, spec: StepSpec) -> StepCommand:
        wf = cast(NfPipeline, spec.workflow)
        params_file = self._params_file(spec)

        argv = _nextflow(spec, "run")
        if spec.resume:
            argv += ["-resume"]
        for cfg in spec.config_files:
            argv += ["-c", str(cfg)]
        if spec.profiles:
            argv += ["-profile", ",".join(spec.profiles)]
        if params_file:
            argv += ["-params-file", str(params_file)]
        if wf.main_script:
            argv += ["-main-script", wf.main_script]
        if not wf.url:
            raise NfMetaRunnerError(f"Step '{wf.id}' has no URL to run.")
        # No -latest: versions are pinned tags/commits, which Nextflow fetches
        # when missing; -latest's pull fails for commits checked out detached.
        argv += [wf.url, "-r", wf.version]
        # -stub must come after the pipeline url/-r args: placed earlier,
        # some Nextflow versions (e.g. 26.04.x) mis-parse it and clobber the
        # pipeline's positional argument with -stub's own resolved value.
        if spec.stub:
            argv += ["-stub"]

        return StepCommand(
            argv=argv,
            cwd=spec.launch_dir,
            env=_env(spec),
            params_file=params_file,
            params=spec.params,
        )


class NextflowModuleEngine(Engine, workflow_type=WorkflowType.NF_MODULE):
    """`nextflow module run <name> -version <version>` (Nextflow >= 26.04)."""

    def build(self, spec: StepSpec) -> StepCommand:
        wf = cast(NfModule, spec.workflow)
        params_file = self._params_file(spec)

        argv = _nextflow(spec, "module", "run")
        if spec.resume:
            argv += ["-resume"]
        for cfg in spec.config_files:
            argv += ["-c", str(cfg)]
        if wf.container_engine:
            argv += [f"-with-{wf.container_engine}"]
        if params_file:
            argv += ["-params-file", str(params_file)]
        # Nextflow rejects `<name>@<version>` ("Invalid module reference")
        argv += [registry_module_name(wf.name), "-version", wf.version]
        # -stub after the positional module arg -- see NextflowPipelineEngine.build.
        if spec.stub:
            argv += ["-stub"]

        return StepCommand(
            argv=argv,
            cwd=spec.launch_dir,
            env=_env(spec),
            params_file=params_file,
            params=spec.params,
        )
