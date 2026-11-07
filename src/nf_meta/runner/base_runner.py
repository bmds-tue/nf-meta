import os
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

from nf_meta.core.graph import MetaworkflowGraph
from nf_meta.core.models import Workflow

from .engines import StepCommand
from .errors import NfMetaRunnerError
from .spec import StepSpec
from .utils import RunOptions

_REGISTRY: dict[str, type["BaseRunner"]] = {}


def step_outdir(spec: StepSpec) -> str | None:
    """The step's `outdir` param, a relative one under `spec.launch_dir`, or
    `None` if it has none. Remote outdirs (`s3://...`) are returned as given."""
    outdir = spec.params.get("outdir")
    if not isinstance(outdir, (str, Path)) or not str(outdir):
        return None
    outdir = str(outdir)
    if "://" in outdir:
        return outdir
    return os.path.normpath(spec.launch_dir / outdir)


@dataclass(frozen=True)
class PlannedStep:
    """One step of a planned run.

    Attributes:
        workflow: The step as configured (references unresolved).
        resolved_params: The step's params with references resolved, before
            globals are merged in.
        spec: The step's final settings.
        command: What would be executed.
        skip: The step already succeeded and would be skipped (resume only).
    """

    workflow: Workflow
    resolved_params: dict
    spec: StepSpec
    command: StepCommand
    skip: bool = False


@dataclass(frozen=True)
class RunPlan:
    """A planned run: its steps in order, plus the values it collected.

    Iterating, indexing and `len()` go over the steps.

    Attributes:
        steps: The planned steps, in DAG order.
        values: Value per input name, and per `<step_id>.<param>` for
            references to steps outside the run.
        missing: Names still without a value (only in a dry run; their
            commands show `<input: name>` placeholders).
    """

    steps: list[PlannedStep]
    values: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    def __iter__(self):
        return iter(self.steps)

    def __getitem__(self, index):
        return self.steps[index]

    def __len__(self) -> int:
        return len(self.steps)

    def to_dict(self) -> dict:
        """The plan as JSON-compatible data."""
        plan = {
            "steps": [
                {
                    "id": s.workflow.id,
                    "name": s.workflow.name,
                    "skip": s.skip,
                    "argv": s.command.argv,
                    "cwd": s.command.cwd,
                    "env": s.command.env,
                    "params": s.command.params,
                }
                for s in self.steps
            ],
            "values": self.values,
            "missing": self.missing,
        }
        return _jsonable(plan)


@dataclass(frozen=True)
class StepResult:
    """The outcome of one step of a finished run.

    Attributes:
        step_id: The step's ID.
        name: The step's pipeline or module name.
        params: The params the step ran with (references resolved, globals
            merged in).
        outdir: The step's `outdir` param as an absolute path, or `None` if
            it has none.
        state_dir: nf-meta's files for the step (params file, output and
            error logs).
        log_file: The Nextflow log file, if one was set.
        command: The command line that was run.
        skipped: The step had already succeeded and was skipped (resume).
    """

    step_id: str
    name: str
    params: dict[str, Any]
    outdir: Path | None
    state_dir: Path
    log_file: Path | None
    command: list[str]
    skipped: bool = False

    @classmethod
    def from_planned(cls, step: PlannedStep) -> "StepResult":
        """The result of running `step` as planned."""
        outdir = step_outdir(step.spec)
        return cls(
            step_id=step.workflow.id,
            name=step.workflow.name,
            params=step.spec.params,
            outdir=Path(outdir) if outdir and "://" not in outdir else None,
            state_dir=step.spec.state_dir,
            log_file=step.spec.log_file,
            command=step.command.argv,
            skipped=step.skip,
        )


class RunResults(Mapping[str, StepResult]):
    """The results of a finished run: a mapping of step ID to `StepResult`,
    in run order, plus the run's out dir."""

    def __init__(self, steps: list[StepResult], out_dir: Path):
        self._steps = {s.step_id: s for s in steps}
        self.out_dir = out_dir

    def __getitem__(self, step_id: str) -> StepResult:
        return self._steps[step_id]

    def __iter__(self) -> Iterator[str]:
        return iter(self._steps)

    def __len__(self) -> int:
        return len(self._steps)

    def __repr__(self) -> str:
        return f"RunResults(out_dir={str(self.out_dir)!r}, steps={list(self._steps)})"

    def to_dict(self) -> dict:
        """The results as JSON-compatible data."""
        return _jsonable(
            {
                "out_dir": self.out_dir,
                "steps": {
                    i: {
                        "name": s.name,
                        "params": s.params,
                        "outdir": s.outdir,
                        "state_dir": s.state_dir,
                        "log_file": s.log_file,
                        "command": s.command,
                        "skipped": s.skipped,
                    }
                    for i, s in self._steps.items()
                },
            }
        )


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


class BaseRunner(ABC):
    """Abstract base class for all metapipeline runner backends.

    Subclasses register themselves by defining a ``RUNNER_NAME`` class
    attribute. The value is the string name used to select the runner::

        class MyRunner(BaseRunner):
            RUNNER_NAME = "my-runner"

            def run(self, g): ...      # returns RunResults
            def resume(self, g): ...

    Registration happens automatically at class-definition time via
    ``__init_subclass__``. ``run_metapipeline`` looks up the concrete class
    from ``_REGISTRY``, so a new runner becomes available as soon as its
    module is imported, with no changes to ``run_metapipeline`` needed.

    Subclasses should not override ``__init__``. The ``RunOptions`` passed in
    is stored as ``self.run_options``, available to every runner without
    repeating the constructor.
    """

    RUNNER_NAME: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        runner_name = cls.__dict__.get("RUNNER_NAME")
        if runner_name is not None:
            _REGISTRY[runner_name] = cls

    def __init__(self, run_options: RunOptions) -> None:
        if "RUNNER_NAME" not in type(self).__dict__:
            raise TypeError(f"{type(self).__name__} must define RUNNER_NAME = '...' as a class attribute")
        self.run_options = run_options

    @abstractmethod
    def run(self, g: MetaworkflowGraph) -> RunResults:
        """Execute every workflow in `g` from scratch, in dependency order,
        and return the results.
        Called by `run_metapipeline` when `run_options.resume` is falsy.
        Exceptions are not caught by the caller -- let a failure raise rather
        than returning normally with partial results."""

    @abstractmethod
    def resume(self, g: MetaworkflowGraph) -> RunResults:
        """Continue a previously interrupted run of `g`, skipping whatever
        the implementation can determine already completed successfully.
        Called by `run_metapipeline` when `run_options.resume` is truthy.
        Same exception policy as `run`."""

    def plan(self, g: MetaworkflowGraph, resume: bool = False, dry_run: bool = False) -> RunPlan:
        """Return what `run` (or `resume`, with `resume=True`) would execute,
        in order, without running anything. With `dry_run`, missing values
        don't raise outside prompt mode; they show as placeholders. Runners
        that can't plan ahead keep this default, which raises
        `NfMetaRunnerError`."""
        raise NfMetaRunnerError(f"Runner '{self.RUNNER_NAME}' does not support dry runs.")
