import hashlib
import json
import logging
import os
import subprocess
import threading
from collections import deque
from typing import Optional
from pathlib import Path

import yaml
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from rich.panel import Panel
from rich.console import Console, Group

from nf_meta.core.graph import MIN_NEXTFLOW_FOR_MODULES, MetaworkflowGraph
from nf_meta.core.config import dump_config
from nf_meta.core.models import GlobalOptions, Workflow, WorkflowType
from .errors import NfMetaRunnerError
from .utils import check_nextflow, check_nextflow_version, get_installed_nextflow_version
from .base_runner import BaseRunner, PlannedStep
from .engines import StepCommand, engine_for
from .paths import absolutize_input_paths, declared_path, is_url, param_schema
from .spec import StepSpec, build_step_spec, resolve_references


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
    files, the globals and all upstream step keys) is skipped; a step that
    runs is started with `-resume`, and each step has its own Nextflow cache
    dir, so Nextflow resumes that step's last run.
    """

    RUNNER_NAME = "python"
    OUT_FILE = "OUT.txt"
    ERROR_FILE = "ERROR.txt"

    def _check_run_success(self, run_dir: Path = Path(".")):
        return (
            Path(run_dir / self.OUT_FILE).exists()
            and not Path(run_dir / self.ERROR_FILE).exists()
        )

    def __init__(self, run_options) -> None:
        super().__init__(run_options)
        self.out_dir: Optional[Path] = (
            Path(run_options.out_dir).resolve() if run_options.out_dir else None
        )

    @property
    def state_root(self) -> Path:
        if self.out_dir is None:
            raise NfMetaRunnerError("Out dir not set; call plan() first.")
        return self.out_dir / ".nf-meta"

    def _resolve_out_dir(self, graph: MetaworkflowGraph) -> Path:
        if self.out_dir is not None:
            return self.out_dir
        if graph.project_dir is None:
            raise NfMetaRunnerError(
                "An out dir is required for a config loaded from a URL (--out)."
            )
        return (graph.project_dir / DEFAULT_OUT_DIR).resolve()

    def _state_dir(self, wf: Workflow, step_key: str) -> Path:
        return self.state_root / "steps" / f"{wf.id}_{step_key}"

    def _nextflow_cache_dir(self, wf: Workflow) -> Path:
        return self.state_root / "nextflow" / wf.id

    def _step_key(
        self,
        wf: Workflow,
        globals: Optional[GlobalOptions],
        upstream_keys: list[str],
    ) -> str:
        """Hash of everything that defines a step's result: the resolved step,
        the content of its config and params files, the globals, run-level
        profile and stub flag, and the keys of all upstream steps."""
        data = {
            "workflow": wf.hash(),
            "config_file": _file_digest(wf.config_file),
            "params_file": _file_digest(getattr(wf, "params_file", None)),
            "globals": globals.model_dump(mode="json") if globals else None,
            "globals_config": _file_digest(globals.config_file if globals else None),
            "profile": self.run_options.nf_profile or "",
            "stub": self.run_options.stub,
            "upstream": sorted(upstream_keys),
        }
        blob = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:8]

    def _resolved_params_path(self, wf: Workflow) -> Path:
        return self.state_root / "resolved" / f"{wf.id}_{wf.hash()}.yaml"

    def _write_resolved_params(self, raw_wf: Workflow, params: dict) -> None:
        path = self._resolved_params_path(raw_wf)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(params, f)

    def _load_resolved_params(self, wf: Workflow) -> Optional[dict]:
        path = self._resolved_params_path(wf)
        if not path.exists():
            return None
        with open(path) as f:
            return yaml.safe_load(f) or {}

    def _validate_cross_boundary_refs(
        self,
        graph: MetaworkflowGraph,
        subset_workflows: list[Workflow],
        subset_ids: set[str],
    ) -> None:
        errors = []
        for wf in subset_workflows:
            for ref in wf.field_refs:
                if ref.target_wf_id in subset_ids:
                    continue
                ref_wf = graph.get_workflow_by_id(ref.target_wf_id)
                if not ref_wf:
                    raise NfMetaRunnerError(
                        f"Reference to unknown workflow: {ref.target_wf_id}"
                    )
                if not self._resolved_params_path(ref_wf).exists():
                    errors.append(
                        f"  '{wf.id}' → '{ref.target_wf_id}' (param '{ref.target_key}'): "
                        f"no successful cached run of '{ref.target_wf_id}' found"
                    )
        if errors:
            raise NfMetaRunnerError(
                "Cannot resolve cross-boundary references — run the excluded workflows first:\n"
                + "\n".join(errors)
            )

    def _stream_proc_out(
        self,
        cmd: list[str],
        cwd: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
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
                        Panel("\n".join(tail), title="Workflow Output"),
                        Spinner("dots", text="Running Workflow ..."),
                    )
                )

            process.wait()
            stderr_thread.join()
            stderr = "".join(stderr_lines)
            stdout = "".join(stdout_lines)

            if process.returncode > 0 and stderr:
                live.update(Panel(stderr, title="Errors"))
            else:
                live.update(Text("Running Workflow ... Done"))

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
            logger.error(
                f"Command exited with code {exit_code}. Workflow dir: {spec.state_dir}"
            )
            with (spec.state_dir / self.ERROR_FILE).open("w") as f:
                f.write(err)
        else:
            (spec.state_dir / self.ERROR_FILE).unlink(missing_ok=True)

        return exit_code == 0

    def _hash_graph(self, graph: MetaworkflowGraph) -> str:
        config_str = str(dump_config(graph))
        hash = hashlib.sha256(config_str.encode()).hexdigest()[:8]
        return hash

    def _selected_workflows(self, graph: MetaworkflowGraph) -> list[Workflow]:
        workflows = graph.get_workflows_sorted()
        if self.run_options.start or self.run_options.target:
            logger.info(
                f"Calculating subset of graph from workflow {self.run_options.start} to {self.run_options.target}"
            )
            workflows = graph.subset_workflows(
                self.run_options.start, self.run_options.target, workflows
            )
            logger.info(
                f"Subset workflow DAG: {' -> '.join([f'{wf.name} ({wf.id})' for wf in workflows])}"
            )
        return workflows

    def plan(self, graph: MetaworkflowGraph, resume: bool = False) -> list[PlannedStep]:
        """Resolve every selected step to its spec and command, in DAG order,
        without writing files or running anything.

        Raises:
            NfMetaRunnerError: if a step outside the selection is referenced
                but has no cached run, if no out dir can be determined, or if
                a config loaded from a URL has relative input paths.
        """
        self.out_dir = self._resolve_out_dir(graph)
        project_dir = graph.project_dir
        globals = graph.global_options
        workflows = self._selected_workflows(graph)
        subset_ids = {wf.id for wf in workflows}
        self._validate_cross_boundary_refs(graph, workflows, subset_ids)

        # Resolved params and step keys per workflow id, seeded from cached runs
        # of excluded workflows
        resolved: dict[str, dict] = {}
        keys: dict[str, str] = {}
        for wf in graph.get_workflows():
            if wf.id not in subset_ids:
                keys[wf.id] = wf.hash()
                cached = self._load_resolved_params(wf)
                if cached is not None:
                    resolved[wf.id] = cached

        planned: list[PlannedStep] = []
        for wf in workflows:
            schema = param_schema(wf)
            if project_dir is not None and wf.params:
                wf = wf.model_copy(
                    update={"params": absolutize_input_paths(wf.params, project_dir, schema)}
                )
            elif project_dir is None:
                self._reject_relative_inputs(wf, schema)

            wf_resolved = resolve_references(wf, graph, resolved=resolved)
            resolved[wf.id] = wf_resolved.params or {}

            upstream = [keys[p.id] for p in graph.predecessors(wf) if p.id in keys]
            key = self._step_key(wf_resolved, globals, upstream)
            keys[wf.id] = key
            state_dir = self._state_dir(wf, key)

            spec = build_step_spec(
                wf_resolved,
                globals,
                state_dir=state_dir,
                launch_dir=self.out_dir,
                work_dir=self.out_dir / "work",
                log_file=state_dir / "nextflow.log",
                nextflow_cache_dir=self._nextflow_cache_dir(wf),
                project_dir=project_dir,
                schema=schema,
                extra_profile=self.run_options.nf_profile or "",
                resume=resume,
                stub=self.run_options.stub,
            )
            planned.append(
                PlannedStep(
                    workflow=graph.get_workflow_by_id(wf.id) or wf,
                    resolved_params=wf_resolved.params or {},
                    spec=spec,
                    command=engine_for(spec.workflow_type).build(spec),
                    skip=resume and self._check_run_success(run_dir=state_dir),
                )
            )
        return planned

    @staticmethod
    def _reject_relative_inputs(wf: Workflow, schema: dict[str, dict]) -> None:
        relative = [
            f"{wf.id}.{key} = {value!r}"
            for key, value in (wf.params or {}).items()
            if declared_path(schema.get(key))
            and key != "outdir"
            and isinstance(value, str)
            and value
            and "${" not in value
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
            if installed[:2] < MIN_NEXTFLOW_FOR_MODULES:
                raise NfMetaRunnerError(
                    "nf-module steps need Nextflow >= 26.04, installed: "
                    + ".".join(str(v) for v in installed[:3])
                )

    def run(self, graph: MetaworkflowGraph, resume=False):
        steps = self.plan(graph, resume=resume)
        self._check_nextflow(graph, steps)
        self._notice_legacy_cache(graph)

        for i, step in enumerate(steps):
            step_label = f"Step {i + 1}/{len(steps)} - {step.workflow.name}"
            self._write_resolved_params(step.workflow, step.resolved_params)

            if step.skip:
                logger.info(f"{step_label}: Skipping (already succeeded)")
                console.print(f"[green]↩[/green] {step_label}: Skipping (already done)")
                continue

            console.print(f"[bold blue]▶[/bold blue] {step_label}")
            if not self._execute(step.spec, step.command):
                console.print(f"[bold red]✗[/bold red] {step_label}: Workflow failed")
                raise NfMetaRunnerError(
                    f"Workflow '{step.workflow.id}' ({step.workflow.name}) failed. "
                    f"Output and errors: {step.spec.state_dir}"
                )

            console.print(f"[green]✓[/green] {step_label}: Done")

        console.print("[bold green]All workflows completed successfully[/bold green]")
        logger.info("All workflows completed")

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

    def resume(self, graph: MetaworkflowGraph):
        self.run(graph, resume=True)
