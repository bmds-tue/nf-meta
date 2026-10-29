"""The Python API: load, edit, save, plan and run a metapipeline."""

import warnings
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from nf_meta.core.events import (
    AddInput,
    AddTransition,
    AddWorkflow,
    Command,
    EditWorkflow,
    RemoveInput,
    RemoveWorkflow,
    Transaction,
    UpdateGlobalOptions,
    UpdateInput,
)
from nf_meta.core.graph import MetaworkflowGraph
from nf_meta.core.inputs import InputDefinition
from nf_meta.core.models import GlobalOptions, Transition, Workflow
from nf_meta.core.session import EditorSession
from nf_meta.runner import RunOptions, RunPlan, RunResults, plan_metapipeline, run_metapipeline

StepOrId = Workflow | str


class Metapipeline:
    """A metapipeline being built or edited, which can be saved, planned and
    run.

    Every change is validated when it is made; an invalid change raises
    (`ConfigValidationError` or `GraphValidationError`) and leaves the
    metapipeline unchanged. Nothing is written to disk before `save()`.

    Steps are `NfPipeline`/`NfModule` models. The metapipeline keeps its own
    copy of each: to change a step, change the model (the one passed to
    `add`, or one from `steps` or `mp[step_id]`) and pass it to `update`.

        mp = Metapipeline()
        fetch = mp.add(NfPipeline(name="nf-core/fetchngs", version="1.12.0",
                                  params={"input": "ids.csv", "outdir": "fetchngs"}))
        mp.add(NfPipeline(name="nf-core/rnaseq", version="3.26.0", params={
            "input": Ref(fetch, "outdir") / "samplesheet/samplesheet.csv",
            "outdir": "rnaseq"}))
        mp.save("metaconfig.yaml")
        results = mp.run(out_dir="results")

    Args:
        project_dir: Folder that relative paths in params resolve against
            (default: the current directory).
    """

    def __init__(self, project_dir: str | Path | None = None):
        self._session = EditorSession(write_on_change=False)
        self._session.start(None)
        self.graph.project_dir = Path(project_dir or Path.cwd()).resolve()

    @classmethod
    def load(cls, config: str | Path) -> "Metapipeline":
        """Load and validate the config at `config` (a path or an `http(s)://`
        URL). Its folder becomes the project dir. Warnings found while loading
        are issued with `warnings.warn`."""
        mp = cls.__new__(cls)
        mp._session = EditorSession(write_on_change=False)
        mp._session.load_config(config)
        for d in mp.graph.warnings:
            warnings.warn(f"{config}: {d.yaml_path}: {d.message}", stacklevel=2)
        return mp

    @property
    def graph(self) -> MetaworkflowGraph:
        """The underlying graph. Changing it directly bypasses undo."""
        return self._session.graph

    @property
    def path(self) -> Path | str | None:
        """The config this metapipeline was loaded from (a path or URL) or
        last saved to."""
        return self._session.config_file

    def save(self, path: str | Path | None = None) -> None:
        """Write the config to `path` (default: `self.path`)."""
        self._session.save_to_config(Path(path) if path else None)

    # --- steps ---

    @property
    def steps(self) -> list[Workflow]:
        """The steps in run order."""
        return [wf.model_copy(deep=True) for wf in self.graph.get_workflows_sorted()]

    def __getitem__(self, step_id: str) -> Workflow:
        wf = self.graph.get_workflow_by_id(step_id)
        if wf is None:
            raise KeyError(step_id)
        return wf.model_copy(deep=True)

    def add(self, step: Workflow, after: Iterable[StepOrId] = ()) -> Workflow:
        """Add `step` and return it. It runs after the steps it references
        (`Ref(...)` or `${...}` in its params) and after the steps in
        `after`."""
        self._execute([AddWorkflow(step), *self._edges_to(step, after)])
        return step

    def update(self, step: Workflow, after: Iterable[StepOrId] = ()) -> Workflow:
        """Replace the step with `step.id` by `step` and return it. Edges for
        new references and for `after` are added; existing edges stay."""
        self._execute([EditWorkflow(step), *self._edges_to(step, after)])
        return step

    def remove(self, step: StepOrId) -> None:
        """Remove a step (a model or an ID) and its edges."""
        self._execute([RemoveWorkflow(_step_id(step))])

    # --- globals and inputs ---

    @property
    def globals(self) -> GlobalOptions:
        """The global options (a copy; apply changes with `set_globals`)."""
        return self.graph.global_options.model_copy(deep=True)

    def set_globals(self, global_options: GlobalOptions) -> None:
        """Replace the global options."""
        self._execute([UpdateGlobalOptions(global_options)])

    @property
    def inputs(self) -> dict[str, InputDefinition]:
        """Every input by name, declared or implicit (only referenced with
        `Ref.input(name)` / `${inputs:name}` in params; an empty definition)."""
        return {name: d.model_copy(deep=True) for name, d in self.graph.all_inputs().items()}

    def add_input(self, name: str, definition: InputDefinition | None = None) -> None:
        """Declare the input `name`: either bind it with `definition.bind`, or
        reference it in params with `Ref.input(name)` and use the declaration
        for metadata only (description, default, ...). An input referenced in
        params needs no declaration."""
        self._execute([AddInput(name, definition or InputDefinition())])

    def update_input(self, name: str, definition: InputDefinition) -> None:
        """Replace the definition of the input `name`."""
        self._execute([UpdateInput(name, definition)])

    def remove_input(self, name: str) -> None:
        """Remove the input `name`."""
        self._execute([RemoveInput(name)])

    # --- history ---

    def undo(self) -> None:
        """Undo the last change. Raises `ValueError` if there is none."""
        self._session.undo()

    def redo(self) -> None:
        """Redo the last undone change. Raises `ValueError` if there is
        none."""
        self._session.redo()

    # --- running ---

    def plan(self, **options: Any) -> RunPlan:
        """What `run` would execute, without running anything (a dry run).
        Takes the same options as `run`."""
        return plan_metapipeline(self.graph, _run_options(options))

    def run(self, **options: Any) -> RunResults:
        """Run the metapipeline, blocking until it finishes, and return the
        results. `options` are `RunOptions` fields: `out_dir`, `nf_profile`,
        `nf_config`, `stub`, `resume`, `start`, `target` (a step or an ID),
        `inputs`, `input_mode`, ... Raises `NfMetaRunnerError` on the first
        step that fails."""
        return run_metapipeline(self.graph, _run_options(options))

    # --- internals ---

    def _edges_to(self, step: Workflow, after: Iterable[StepOrId]) -> list[Command]:
        sources = [ref.target_wf_id for ref in step.field_refs] + [_step_id(s) for s in after]
        return [
            AddTransition(Transition(source=source, target=step.id))
            for source in dict.fromkeys(sources)
            if not self.graph.get_transition(source, step.id)
        ]

    def _execute(self, commands: list[Command]) -> None:
        self._session.execute(commands[0] if len(commands) == 1 else Transaction(tuple(commands)))

    def __repr__(self) -> str:
        steps = ", ".join(f"{wf.id}: {wf.name}" for wf in self.graph.get_workflows_sorted())
        return f"Metapipeline([{steps}])"


def _step_id(step: StepOrId) -> str:
    return step if isinstance(step, str) else step.id


def _run_options(options: dict[str, Any]) -> RunOptions:
    for key in ("start", "target"):
        if options.get(key) is not None:
            options[key] = _step_id(options[key])
    return RunOptions(**options)
