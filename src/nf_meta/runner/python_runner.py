import hashlib
import logging
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
from nf_meta.core.models import Workflow, WorkflowType
from .errors import NfMetaRunnerError
from .utils import check_nextflow, check_nextflow_version, get_installed_nextflow_version
from .base_runner import BaseRunner, PlannedStep
from .engines import StepCommand, engine_for
from .spec import StepSpec, build_step_spec, resolve_references


logger = logging.getLogger(__name__)
console = Console()


class SimplePythonRunner(BaseRunner):
    """The default runner (`RUNNER_NAME = "python"`). Executes each workflow
    as a `nextflow run`/`nextflow module run` subprocess directly from this
    Python process, in DAG order, streaming output as it runs.

    Caches each workflow's resolved params (after `${...}` substitution)
    under `run_options.cachedir`, keyed by a content hash of the workflow's
    definition. `resume=True` skips any workflow whose working directory
    already recorded success, and passes Nextflow's own `-resume` through for
    the ones that do run.
    """

    RUNNER_NAME = "python"
    OUT_FILE = "OUT.txt"
    ERROR_FILE = "ERROR.txt"

    def _check_run_success(self, run_dir: Path = Path(".")):
        return (
            Path(run_dir / self.OUT_FILE).exists()
            and not Path(run_dir / self.ERROR_FILE).exists()
        )

    def _workflow_dir(self, wf: Workflow) -> Path:
        safe_name = wf.name.replace("/", "_")
        return (
            self.run_options.cachedir / f"{safe_name}_{wf.version}_{wf.hash()}"
        ).resolve()

    def _resolved_params_path(self, wf: Workflow) -> Path:
        return self.run_options.cachedir / f"{wf.id}_{wf.hash()}_resolved.yaml"

    def _write_resolved_params(self, raw_wf: Workflow, params: dict) -> None:
        with open(self._resolved_params_path(raw_wf), "w") as f:
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

    def _stream_proc_out(self, cmd: list[str]) -> tuple[int, str, str]:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
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
        command.write_files()

        argv = [check_nextflow(), *command.argv[1:]]
        logger.info(f"Running nextflow command: {argv}")
        exit_code, out, err = self._stream_proc_out(argv)

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
                but has no cached run.
        """
        self.run_options.cachedir = Path(self.run_options.cachedir)
        workflows = self._selected_workflows(graph)
        subset_ids = {wf.id for wf in workflows}
        self._validate_cross_boundary_refs(graph, workflows, subset_ids)

        # Resolved params per workflow id, seeded from cached runs of excluded workflows
        resolved: dict[str, dict] = {}
        for wf in graph.get_workflows():
            if wf.id not in subset_ids:
                cached = self._load_resolved_params(wf)
                if cached is not None:
                    resolved[wf.id] = cached

        planned: list[PlannedStep] = []
        for wf in workflows:
            wf_resolved = resolve_references(wf, graph, resolved=resolved)
            resolved[wf.id] = wf_resolved.params or {}

            spec = build_step_spec(
                wf_resolved,
                graph.global_options,
                state_dir=self._workflow_dir(wf_resolved),
                launch_dir=Path.cwd(),
                extra_profile=self.run_options.nf_profile or "",
                resume=resume,
                stub=self.run_options.stub,
            )
            planned.append(
                PlannedStep(
                    workflow=wf,
                    resolved_params=wf_resolved.params or {},
                    spec=spec,
                    command=engine_for(spec.workflow_type).build(spec),
                    skip=resume and self._check_run_success(run_dir=spec.state_dir),
                )
            )
        return planned

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
        self.run_options.cachedir.mkdir(parents=True, exist_ok=True)

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

    def resume(self, graph: MetaworkflowGraph):
        self.run(graph, resume=True)
