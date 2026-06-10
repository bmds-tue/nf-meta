import hashlib
import logging
import os
import subprocess
import threading
from collections import deque
from contextlib import contextmanager
from typing import Optional
from pathlib import Path

import yaml
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from rich.panel import Panel
from rich.console import Console, Group

from nf_meta.core.graph import MetaworkflowGraph
from nf_meta.core.models import Workflow, GlobalOptions
from nf_meta.core.errors import WorkflowReferenceError
from .errors import NfMetaRunnerError
from .utils import check_nextflow_version
from .base_runner import BaseRunner
from .workflow_run import WorkflowRun


logger = logging.getLogger(__name__)
console = Console()


class SimplePythonRunner(BaseRunner):
    """
    Simple default runner for Metapipelines.
    Executes workflows in dag order from this Python runtime.
    """

    RUNNER_TYPE = "python"
    OUT_FILE = "OUT.txt"
    ERROR_FILE = "ERROR.txt"

    @contextmanager
    def _chdir(self, path: Path):
        origin = Path()
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.chdir(path)
            yield
        finally:
            os.chdir(origin)

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

    def _resolve_field_refs(
        self,
        wf: Workflow,
        graph: MetaworkflowGraph,
        resolved: Optional[dict[str, dict]] = None,
        work_directories: Optional[dict[str, Path]] = None,
    ) -> Workflow:
        wf_resolved = wf.model_copy(deep=True)
        for ref in wf_resolved.field_refs:
            if ref.namespace != "params":
                raise NfMetaRunnerError(
                    f"Unsupported reference namespace '{ref.namespace}' in '{ref.name}'. "
                    "Only 'params' references are currently supported."
                )
            wf_ref = graph.get_workflow_by_id(ref.target_wf_id)
            if not wf_ref:
                raise ValueError(
                    f"Resolving reference {ref.name} failed: "
                    f"referenced workflow '{ref.target_wf_id}' does not exist"
                )

            # Prefer already-resolved values (from prior steps or cache) over raw config
            values_source: dict = (resolved or {}).get(ref.target_wf_id) or (
                wf_ref.params or {}
            )

            if not values_source:
                raise ValueError(
                    f"Resolving reference {ref.name} failed: "
                    f"source workflow '{wf_ref.id}' has no resolved values for namespace '{ref.namespace}'"
                )
            if not wf_resolved.params:
                raise ValueError(
                    f"Resolving reference {ref.name} failed: "
                    f"referencing workflow '{wf_resolved.id}' has no params to substitute into"
                )

            ref_value = values_source.get(ref.target_key)
            source_value = wf_resolved.params.get(ref.source_key)

            if not ref_value:
                raise ValueError(
                    f"Resolving reference {ref.name} failed: "
                    f"key '{ref.target_key}' not found in workflow '{ref.target_wf_id}' {ref.namespace}"
                )
            if not source_value:
                raise ValueError(
                    f"Resolving reference {ref.name} failed: "
                    f"source key '{ref.source_key}' not found in workflow '{ref.source_wf_id}' params"
                )

            resolved_value = source_value.replace(ref.name, ref_value)
            if work_directories:
                resolved_value = str(
                    work_directories[ref.target_wf_id] / resolved_value
                )
            wf_resolved.params[ref.source_key] = resolved_value

        return wf_resolved

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
                    raise WorkflowReferenceError(
                        ref, f"Reference to unknown workflow: {ref.target_wf_id}"
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

    def _run_workflow(
        self, wf: Workflow, globals: Optional[GlobalOptions] = None, resume: bool = True
    ) -> bool:
        wf_dir = self._workflow_dir(wf)

        # Merge global params into wf for this run. This happens after _write_resolved_params
        # so the cache only holds wf-specific params (used for cross-step reference resolution).
        if globals and globals.params:
            merged = {**globals.params, **(wf.params or {})}
            wf = wf.model_copy(update={"params": merged})

        run = WorkflowRun.for_step(
            wf, wf_dir, globals, extra_profile=self.run_options.nf_profile or ""
        )
        run.prepare()

        cmd = run.get_cmd(resume=resume, stub=self.run_options.stub)
        logger.info(f"Running nextflow command: {cmd}")

        exit_code, out, err = self._stream_proc_out(cmd)

        with (wf_dir / self.OUT_FILE).open("w") as f:
            f.write(out)

        if exit_code != 0:
            logger.error(
                f"Command exited with code {exit_code}. Workflow dir: {wf_dir.absolute()}"
            )
            with (wf_dir / self.ERROR_FILE).open("w") as f:
                f.write(err)
        else:
            (wf_dir / self.ERROR_FILE).unlink(missing_ok=True)

        return exit_code == 0

    def _hash_graph(self, graph: MetaworkflowGraph) -> str:
        config_str = str(graph.to_config())
        hash = hashlib.sha256(config_str.encode()).hexdigest()[:8]
        return hash

    def run(self, graph: MetaworkflowGraph, resume=False):

        self.run_options.cachedir = Path(self.run_options.cachedir)
        self.run_options.cachedir.mkdir(parents=True, exist_ok=True)

        if graph.global_options.nextflow_version:
            _ = check_nextflow_version(graph.global_options.nextflow_version)

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

        subset_ids = {wf.id for wf in workflows}

        self._validate_cross_boundary_refs(graph, workflows, subset_ids)

        # Cache of resolved field values per workflow id, seeded from excluded-workflow cache files
        resolved: dict[str, dict] = {}
        for wf in graph.get_workflows():
            if wf.id not in subset_ids:
                cached = self._load_resolved_params(wf)
                if cached is not None:
                    resolved[wf.id] = cached

        for i, wf in enumerate(workflows):
            step_label = f"Step {i + 1}/{len(workflows)} - {wf.name}"

            raw_wf = wf
            wf = self._resolve_field_refs(wf, graph, resolved=resolved)
            logger.debug(f"Resolved workflow {wf.id}")

            resolved[wf.id] = wf.params or {}
            self._write_resolved_params(raw_wf, wf.params or {})

            if resume and self._check_run_success(run_dir=self._workflow_dir(wf)):
                logger.info(f"{step_label}: Skipping (already succeeded)")
                console.print(f"[green]↩[/green] {step_label}: Skipping (already done)")
                continue

            console.print(f"[bold blue]▶[/bold blue] {step_label}")
            success = self._run_workflow(wf, graph.global_options, resume=resume)

            if not success:
                console.print(f"[bold red]✗[/bold red] {step_label}: Workflow failed")
                return

            console.print(f"[green]✓[/green] {step_label}: Done")

        console.print("[bold green]All workflows completed successfully[/bold green]")
        logger.info("All workflows completed")

    def resume(self, graph: MetaworkflowGraph):
        self.run(graph, resume=True)
