import hashlib
import json
import logging
import os
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from nf_meta.core.graph import MetaworkflowGraph
from nf_meta.core.inputs import Binding, InputDefinition, effective_input, input_refs, substitute_inputs
from nf_meta.core.models import GlobalOptions, NfModule, Workflow, WorkflowType, with_absolute_config_paths
from nf_meta.core.registry import Schema

from .base_runner import BaseRunner, PlannedStep, RunPlan, RunResults, StepResult
from .collect import InputMode, Request, collect, is_placeholder
from .engines import StepCommand, engine_for
from .errors import NfMetaRunnerError
from .paths import absolutize_input_paths, declared_path, folder_fingerprint, input_fingerprints, is_url, param_schema
from .spec import StepSpec, build_step_spec, resolve_references
from .utils import check_nextflow, check_nextflow_version, get_installed_nextflow_version

logger = logging.getLogger(__name__)
console = Console()

DEFAULT_OUT_DIR = "nf-meta-out"
LEGACY_CACHE_DIR = ".nf-meta-cache"


def _file_digest(path) -> str:
    if not path:
        return ""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return f"missing:{path}"


class SimplePythonRunner(BaseRunner):
    """The default runner (`RUNNER_NAME = "python"`). Executes each workflow
    as a `nextflow run`/`nextflow module run` subprocess directly from this
    Python process, in DAG order, streaming output as it runs.

    Every step runs Nextflow from the out dir (`run_options.out_dir`, default
    `<project dir>/nf-meta-out`), sharing its `work/` dir. Relative input
    paths are made absolute against the project dir first. nf-meta's own state
    lives in `<out dir>/.nf-meta/`.

    `resume=True` works on two levels: a step that already succeeded with an
    identical step key (its definition, the content of its config and params
    files, size and modification time of its local input files, the globals
    and all upstream step keys) is skipped; a step that
    runs is started with `-resume`, and each step has its own Nextflow cache
    dir, so Nextflow resumes that step's last run.
    """

    RUNNER_NAME = "python"
    OUT_FILE = "OUT.txt"
    ERROR_FILE = "ERROR.txt"

    def _check_run_success(self, run_dir: Path = Path()):
        return Path(run_dir / self.OUT_FILE).exists() and not Path(run_dir / self.ERROR_FILE).exists()

    def __init__(self, run_options) -> None:
        super().__init__(run_options)
        self.out_dir: Path | None = Path(run_options.out_dir).resolve() if run_options.out_dir else None

    @property
    def state_root(self) -> Path:
        if self.out_dir is None:
            raise NfMetaRunnerError("Out dir not set; call plan() first.")
        return self.out_dir / ".nf-meta"

    def _resolve_out_dir(self, graph: MetaworkflowGraph) -> Path:
        if self.out_dir is not None:
            return self.out_dir
        if graph.project_dir is None:
            raise NfMetaRunnerError("An out dir is required for a config loaded from a URL (--out).")
        return (graph.project_dir / DEFAULT_OUT_DIR).resolve()

    def _state_dir(self, wf: Workflow, step_key: str) -> Path:
        return self.state_root / "steps" / f"{wf.id}_{step_key}"

    def _current_key_file(self, wf: Workflow) -> Path:
        return self.state_root / "current" / wf.id

    def _last_run_was(self, wf: Workflow, state_dir: Path) -> bool:
        """Whether the step's last run used `state_dir` (also when nf-meta didn't
        record it yet)."""
        current = self._current_key_file(wf)
        return not current.exists() or current.read_text().strip() == state_dir.name

    def _nextflow_cache_dir(self, wf: Workflow) -> Path:
        return self.state_root / "nextflow" / wf.id

    def _step_key(
        self,
        wf: Workflow,
        global_options: GlobalOptions | None,
        upstream_keys: list[str],
        input_files: dict[str, list] | None = None,
    ) -> str:
        """Hash of everything that defines a step's result: the resolved step,
        the content of its config and params files, the local input files its
        params name (see `input_fingerprints`), a local pipeline's files (see
        `folder_fingerprint`), the globals, run-level profile, Nextflow config
        and stub flag, and the keys of all upstream steps."""
        data: dict[str, Any] = {
            "workflow": wf.hash(),
            "input_files": input_files or {},
            "nf_config": _file_digest(wf.nf_config),
            "params_file": _file_digest(getattr(wf, "params_file", None)),
            "globals": global_options.model_dump(mode="json") if global_options else None,
            "globals_config": _file_digest(global_options.nf_config if global_options else None),
            "run_config": _file_digest(self.run_options.nf_config),
            "profile": self.run_options.nf_profile or "",
            "stub": self.run_options.stub,
            "upstream": sorted(upstream_keys),
        }
        local = getattr(wf, "path", None)
        if local:  # only then, so other steps keep their keys
            data["pipeline_files"] = folder_fingerprint(local, skip=[self.out_dir] if self.out_dir else [])
        blob = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:8]

    def _resolved_params_path(self, wf: Workflow) -> Path:
        return self.state_root / "resolved" / f"{wf.id}_{wf.hash()}.yaml"

    def _write_resolved_params(self, raw_wf: Workflow, params: dict) -> None:
        path = self._resolved_params_path(raw_wf)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(params, f)

    def _load_resolved_params(self, wf: Workflow) -> dict | None:
        path = self._resolved_params_path(wf)
        if not path.exists():
            return None
        with open(path) as f:
            return yaml.safe_load(f) or {}

    def _stream_proc_out(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env={**os.environ, **env} if env else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        tail: deque[str] = deque(maxlen=self.run_options.output_lines)
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        def _collect_stderr() -> None:
            assert process.stderr is not None
            for line in process.stderr:
                stderr_lines.append(line)

        stderr_thread = threading.Thread(target=_collect_stderr, daemon=True)
        stderr_thread.start()

        assert process.stdout is not None
        with Live(console=console, refresh_per_second=4) as live:
            for raw_line in process.stdout:
                stdout_lines.append(raw_line)
                tail.append(raw_line.strip())
                live.update(
                    Group(
                        Panel("\n".join(tail), title="Step output"),
                        Spinner("dots", text="Running step ..."),
                    )
                )

            process.wait()
            stderr_thread.join()
            stderr = "".join(stderr_lines)
            stdout = "".join(stdout_lines)

            if process.returncode > 0 and stderr:
                live.update(Panel(stderr, title="Errors"))
            else:
                live.update(Text("Running step ... Done"))

        return (process.returncode, stdout, stderr)

    def _execute(self, spec: StepSpec, command: StepCommand) -> bool:
        """Run one step's command, streaming its output. Writes `OUT_FILE`
        and, on failure, `ERROR_FILE` to the step's state dir."""
        spec.state_dir.mkdir(parents=True, exist_ok=True)
        command.cwd.mkdir(parents=True, exist_ok=True)
        command.write_files()

        argv = [check_nextflow(), *command.argv[1:]]
        logger.info(f"Running nextflow command: {argv}")
        exit_code, out, err = self._stream_proc_out(argv, cwd=command.cwd, env=command.env)

        with (spec.state_dir / self.OUT_FILE).open("w") as f:
            f.write(out)

        if exit_code != 0:
            logger.error(f"Command exited with code {exit_code}. Step dir: {spec.state_dir}")
            with (spec.state_dir / self.ERROR_FILE).open("w") as f:
                f.write(err)
        else:
            (spec.state_dir / self.ERROR_FILE).unlink(missing_ok=True)

        return exit_code == 0

    def _selected_workflows(self, graph: MetaworkflowGraph) -> list[Workflow]:
        workflows = graph.get_workflows_sorted()
        if self.run_options.start or self.run_options.target:
            logger.info(f"Calculating subset of graph from step {self.run_options.start} to {self.run_options.target}")
            workflows = graph.subset_workflows(self.run_options.start, self.run_options.target, workflows)
            if not workflows:
                raise NfMetaRunnerError(
                    f"No steps between start {self.run_options.start} and target {self.run_options.target}: "
                    "the target must come after the start."
                )
            logger.info(f"Steps to run: {' -> '.join([f'{wf.name} ({wf.id})' for wf in workflows])}")
        return workflows

    def plan(self, graph: MetaworkflowGraph, resume: bool = False, dry_run: bool = False) -> RunPlan:
        """Resolve every selected step to its spec and command, in DAG order,
        without writing files or running anything. Values the run needs are
        collected first (see `RunOptions.input_mode`); in prompt mode this
        asks for them, even in a dry run.

        Raises:
            NfMetaRunnerError: if values are missing (except in a dry run
                outside prompt mode, where they become placeholders) or
                invalid, if no out dir can be determined, or if a config loaded
                from a URL has relative input paths.
        """
        self.out_dir = self._resolve_out_dir(graph)
        project_dir = graph.project_dir
        # params_file/nf_config are read from here on: as absolute paths
        global_options = graph.global_options and with_absolute_config_paths(graph.global_options, project_dir)
        workflows = [with_absolute_config_paths(wf, project_dir) for wf in self._selected_workflows(graph)]
        subset_ids = {wf.id for wf in workflows}

        # Resolved params and step keys per workflow id, seeded from cached runs
        # of excluded workflows
        resolved: dict[str, dict] = {}
        keys: dict[str, str] = {}
        for wf in graph.get_workflows():
            if wf.id not in subset_ids:
                wf = with_absolute_config_paths(wf, project_dir)
                keys[wf.id] = wf.hash()
                cached = self._load_resolved_params(wf)
                if cached is not None:
                    resolved[wf.id] = cached

        requests = self._input_requests(graph, workflows, subset_ids, resolved)
        collected = collect(
            requests,
            self.run_options.inputs,
            InputMode(self.run_options.input_mode),
            project_dir=project_dir,
            prompter=self.run_options.prompter,
            dry_run=dry_run,
        )
        input_values = {r.name: collected.values[r.name] for r in requests if not r.is_reference}
        reference_values = {Binding.parse(r.name): collected.values[r.name] for r in requests if r.is_reference}

        planned: list[PlannedStep] = []
        for wf in workflows:
            bound = graph.bound_params(wf.id)
            if bound or input_refs(wf.params):
                wf = wf.model_copy(update={"params": substitute_inputs(wf.params, bound, input_values)})
            overrides = {b.param: v for b, v in reference_values.items() if b.step_id == wf.id}
            if overrides:
                wf = wf.model_copy(update={"params": {**(wf.params or {}), **overrides}})
            schema = param_schema(wf)
            if project_dir is not None and wf.params:
                wf = wf.model_copy(update={"params": absolutize_input_paths(wf.params, project_dir, schema)})
            elif project_dir is None:
                self._reject_relative_inputs(wf, schema)

            # Before references are resolved: other steps' outputs are covered by
            # their step keys, and may not exist yet
            global_params = (global_options.params if global_options else None) or {}
            if project_dir is not None and global_params:
                global_params = absolutize_input_paths(global_params, project_dir, schema)
            input_files = input_fingerprints({**global_params, **(wf.params or {})})
            wf_resolved = resolve_references(wf, graph, resolved=resolved)
            resolved[wf.id] = wf_resolved.params or {}

            upstream = [keys[p.id] for p in graph.predecessors(wf) if p.id in keys]
            key = self._step_key(wf_resolved, global_options, upstream, input_files)
            keys[wf.id] = key
            state_dir = self._state_dir(wf, key)

            spec = build_step_spec(
                wf_resolved,
                global_options,
                state_dir=state_dir,
                launch_dir=self.out_dir,
                work_dir=self.out_dir / "work",
                log_file=state_dir / "nextflow.log",
                nextflow_cache_dir=self._nextflow_cache_dir(wf),
                project_dir=project_dir,
                schema=schema,
                extra_profile=self.run_options.nf_profile or "",
                nf_config=self.run_options.nf_config,
                resume=resume,
                stub=self.run_options.stub,
            )
            planned.append(
                PlannedStep(
                    # as configured, with the config files' absolute paths (as its resolved params' cache key)
                    workflow=with_absolute_config_paths(graph.get_workflow_by_id(wf.id) or wf, project_dir),
                    resolved_params=wf_resolved.params or {},
                    spec=spec,
                    command=engine_for(spec.workflow_type).build(spec),
                    # The step's outdir holds the last run's results, so an older
                    # success with this key counts only if no other key ran since.
                    skip=resume and self._check_run_success(run_dir=state_dir) and self._last_run_was(wf, state_dir),
                )
            )
        return RunPlan(
            steps=planned,
            values=dict(collected.values),
            missing=[r.name for r in collected.missing],
        )

    def _input_requests(
        self,
        graph: MetaworkflowGraph,
        workflows: list[Workflow],
        subset_ids: set[str],
        resolved: dict[str, dict],
    ) -> list[Request]:
        """Every value the selected steps need: the inputs bound to them, and
        each param that references a step outside the selection."""
        reproduce = InputMode(self.run_options.input_mode) == InputMode.REPRODUCE
        recorded = self._load_recorded_inputs() if reproduce else {}

        requests: list[Request] = []
        if graph.all_inputs():
            inputs, _ = graph.effective_inputs()
            for inp in inputs.values():
                if any(b.step_id in subset_ids for b in inp.bindings):
                    fallback = recorded.get(inp.name) if reproduce else inp.default
                    requests.append(Request(inp, fallback=fallback))

        for wf in workflows:
            outside = [r for r in wf.field_refs if r.namespace == "params" and r.target_wf_id not in subset_ids]
            for param in sorted({r.source_key for r in outside}):
                binding = Binding(wf.id, param)
                inp, _ = effective_input(
                    str(binding),
                    InputDefinition(description=f"Value of {binding} (normally taken from another step's run)"),
                    (binding,),
                    {binding: param_schema(wf).get(param)},
                )
                requests.append(Request(inp, fallback=self._cached_reference(wf, param, resolved), is_reference=True))
        return requests

    @staticmethod
    def _cached_reference(wf: Workflow, param: str, resolved: dict[str, dict]):
        """The value of `wf.params[param]` with its references to other steps
        filled from cached runs, or `None` if one isn't cached."""
        value = (wf.params or {}).get(param)
        if not isinstance(value, str):
            return None
        for ref in wf.field_refs:
            if ref.source_key != param:
                continue
            cached = resolved.get(ref.target_wf_id, {}).get(ref.target_key)
            if cached is None:
                return None
            value = value.replace(ref.name, str(cached))
        return value

    def _recorded_inputs_path(self) -> Path:
        return self.state_root / "inputs.yaml"

    def _load_recorded_inputs(self) -> dict:
        path = self._recorded_inputs_path()
        if not path.exists():
            return {}
        with open(path) as f:
            return yaml.safe_load(f) or {}

    def _record_inputs(self, plan: RunPlan, graph: MetaworkflowGraph) -> None:
        """Remember the input values of this run for `reproduce` mode, keeping
        recorded values of inputs this run didn't use (e.g. a partial run)."""
        inputs = graph.all_inputs()
        values = {name: v for name, v in plan.values.items() if name in inputs}
        if not values:
            return
        recorded = {name: v for name, v in self._load_recorded_inputs().items() if name in inputs}
        values = {**recorded, **values}
        path = self._recorded_inputs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(values, f)

    @staticmethod
    def _reject_relative_inputs(wf: Workflow, schema: Schema) -> None:
        relative = [
            f"{wf.id}.{key} = {value!r}"
            for key, value in (wf.params or {}).items()
            if declared_path(schema.get(key))
            and key != "outdir"
            and isinstance(value, str)
            and value
            and "${" not in value
            and not is_placeholder(value)
            and not is_url(value)
            and not Path(value).is_absolute()
        ]
        if relative:
            raise NfMetaRunnerError(
                "Relative input paths in a config loaded from a URL: "
                + ", ".join(relative)
                + ". Use absolute paths or URLs, or declare them as inputs."
            )

    def _check_nextflow(self, graph: MetaworkflowGraph, steps: list[PlannedStep]) -> None:
        if graph.global_options.nextflow_version_tuple:
            check_nextflow_version(graph.global_options.nextflow_version_tuple)

        if any(s.spec.workflow_type == WorkflowType.NF_MODULE for s in steps):
            installed = get_installed_nextflow_version()
            minimum = NfModule.MIN_NEXTFLOW_VERSION
            if installed[:2] < minimum:
                raise NfMetaRunnerError(
                    f"nf-module steps need Nextflow >= {minimum[0]}.{minimum[1]:02d}, installed: "
                    + ".".join(str(v) for v in installed[:3])
                )

    def run(self, graph: MetaworkflowGraph, resume=False) -> RunResults:
        steps = self.plan(graph, resume=resume)
        self._check_nextflow(graph, list(steps))
        self._notice_legacy_cache(graph)
        self._record_inputs(steps, graph)

        for i, step in enumerate(steps):
            step_label = f"Step {i + 1}/{len(steps)} - {step.workflow.name}"
            self._write_resolved_params(step.workflow, step.resolved_params)

            current = self._current_key_file(step.workflow)
            current.parent.mkdir(parents=True, exist_ok=True)
            current.write_text(step.spec.state_dir.name)

            if step.skip:
                logger.info(f"{step_label}: Skipping (already succeeded)")
                console.print(f"[green]↩[/green] {step_label}: Skipping (already done)")
                continue

            console.print(f"[bold blue]▶[/bold blue] {step_label}")
            if not self._execute(step.spec, step.command):
                console.print(f"[bold red]✗[/bold red] {step_label}: Step failed")
                raise NfMetaRunnerError(
                    f"Step '{step.workflow.id}' ({step.workflow.name}) failed. Output and errors: {step.spec.state_dir}"
                )

            console.print(f"[green]✓[/green] {step_label}: Done")

        console.print("[bold green]All steps completed successfully[/bold green]")
        logger.info("All steps completed")
        assert self.out_dir is not None  # set by plan()
        return RunResults([StepResult.from_planned(step) for step in steps], out_dir=self.out_dir)

    def _notice_legacy_cache(self, graph: MetaworkflowGraph) -> None:
        candidates = {Path.cwd() / LEGACY_CACHE_DIR}
        if graph.project_dir is not None:
            candidates.add(graph.project_dir / LEGACY_CACHE_DIR)
        for old in candidates:
            if old.is_dir():
                console.print(
                    f"[yellow]Note:[/yellow] {old} is from an older nf-meta and is no "
                    f"longer used; results now go to {self.out_dir}."
                )

    def resume(self, graph: MetaworkflowGraph) -> RunResults:
        return self.run(graph, resume=True)
