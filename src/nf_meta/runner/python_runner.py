import hashlib
import logging
import os
import re
import shutil
import subprocess
import uuid
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

from nf_meta.engine.graph import MetaworkflowGraph
from nf_meta.engine.models import Workflow, GlobalOptions
from .errors import NfMetaRunnerError
from .utils import check_nextflow, check_nextflow_version


logger = logging.getLogger(__name__)
console = Console()


class SimplePythonRunner:
    """
    Simple default runner for Metapipelines.
    Executes workflows in dag order from this Python runtime.
    """
    OUT_FILE = "OUT.txt"
    ERROR_FILE = "ERROR.txt"

    def __init__(self, 
                 tempdir = ".nf-meta-cache",
                 output_window_size = 20,
                 start: Optional[str] = None,
                 target: Optional[str] = None,
                 extra_profile: Optional[str] = None):
        self.tempdir = Path(tempdir)
        self.tempdir.mkdir(parents=True, exist_ok=True)
        self.executable = check_nextflow()
        self.output_window_size = output_window_size
        self.start_wf_id = start
        self.target_wf_id = target
        self.extra_profile = extra_profile.replace(" ", "") if extra_profile else ""
    
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
        return Path(run_dir / self.OUT_FILE).exists() \
            and not Path(run_dir / self.ERROR_FILE).exists()

    def _merge_params(self, specific_params: dict, default_params: dict):
        return {**default_params, **specific_params}

    def _create_params_file(self, params: dict, filename: Optional[Path] = None) -> Path:
        if filename is None:
            params_file = f"params-{uuid.uuid4()}.yaml"
            filename = Path(self.tempdir / params_file)
        
        with open(filename, "w") as f:
            f.write(yaml.dump(params))

        return Path(filename)

    def _workflow_dir(self, wf: Workflow) -> Path:
        safe_name = wf.name.replace("/", "_")
        return (self.tempdir / f"{safe_name}_{wf.version}_{wf.hash()}").resolve()

    def _resolve_param_references(self, 
                                 wf: Workflow, 
                                 graph: MetaworkflowGraph, 
                                 work_directories: Optional[dict[str, str]] = None
                                 ) -> Workflow:
        wf_resolved = wf.model_copy(deep=True)
        refs = wf_resolved.field_refs
        for ref in refs:
            wf_ref = graph.get_workflow_by_id(ref.target_wf_id)
            ref_value = wf_ref.params.get(ref.target_key)
            source_value = wf_resolved.params.get(ref.source_key)

            if not ref_value:
                raise ValueError(f"Resolving param reference {ref.name} failed: "
                                 + f"Referenced key {ref.target_key} not found "
                                 + f"in workflow {ref.target_wf_id}")
            
            if not source_value:
                raise ValueError(f"Resolving param reference {ref.reference_name} failed: "
                                 + f"Source key {ref.source_key} not found "
                                 + f"in workflow {ref.source_wf_id}")
            
            resolved_value = source_value.replace(ref.name, ref_value)
            if work_directories:
                resolved_value = str(work_directories[ref.target_wf_id] / resolved_value)
            wf_resolved.params[ref.source_key] = resolved_value
        
        return wf_resolved

    def _stream_proc_out(
                self,
                cmd: list[str],
            ) -> tuple[int, str, str]:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    
        tail = deque(maxlen=self.output_window_size)
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        # Read stderr in a background thread so it never blocks the process.
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
                live.update(Group(
                    Panel("\n".join(tail), title="Workflow Output"),
                    Spinner("dots", text="Running Workflow ...")
                ))

            process.wait()
            stderr_thread.join()
            stderr = "".join(stderr_lines)
            stdout = "".join(stdout_lines)

            if process.returncode > 0 and stderr:
                live.update(Panel(stderr, title="Errors"))
            else:
                live.update(Text("Running Workflow ... Done"))

        return (process.returncode, stdout, stderr)

    def _run_workflow(self, wf: Workflow, globals: Optional[GlobalOptions] = None, resume: bool = True):
        wf_dir = Path(self._workflow_dir(wf))
        wf_dir.mkdir(exist_ok=True, parents=True)

        cmd = [self.executable, "run", "-ansi-log", "false"]

        if resume:
            cmd += ["-resume"]

        wf_params = dict(wf.params or {})
        profiles = []
        if globals is not None:
            if globals.config_file is not None:
                nf_cfg = Path(globals.config_file)
                if not nf_cfg.exists():
                    raise NfMetaRunnerError(f"Global config file does not exist: {nf_cfg}")
                cmd += ["-c", str(nf_cfg)]

            if globals.params:
                wf_params = self._merge_params(wf_params, globals.params)

            if globals.profile and not wf.profile:
                profiles.append(globals.profile)

        if wf.profile:
            profiles.append(wf.profiles)
        
        if self.extra_profile:
            profiles.append(self.extra_profile)
        
        cmd += ["-profile", ",".join(profiles)]
        logger.info(f"Profiles added: {cmd[-1]}")

        if wf_params:
            params_file = self._create_params_file(wf_params, wf_dir / "params.yaml")
            cmd += ["-params-file", str(params_file)]

        if wf.config_file:
            if not wf.config_file.exists():
                raise NfMetaRunnerError(f"Config file referenced by workflow {wf.id} does not exists: {wf.config_file}")
            cmd += ["-c", str(wf.config_file)]

        cmd += [wf.url, "-r", wf.version, "-latest"]

        logger.info(f"Running nextflow command: {cmd}")
        exit_code, out, err = self._stream_proc_out(cmd)

        with (wf_dir / self.OUT_FILE).open("w") as f:
            f.write(out)

        if exit_code != 0:
            logger.error(f"Command exited with code {exit_code}. Workflow dir: {wf_dir.absolute()}")
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
        if graph.global_options.nextflow_version:
            _ = check_nextflow_version(graph.global_options.nextflow_version)

        workflows = graph.get_workflows_sorted()
        if self.start_wf_id or self.target_wf_id:
            logger.info(f"Calculating subset of graph from workflow {self.start_wf_id} to {self.target_wf_id}")
            workflows = graph.subset_workflows(self.start_wf_id, self.target_wf_id, workflows)
            logger.info(f"Subset workflow DAG: {" -> ".join([f'{wf.name} ({wf.id})' for wf in workflows])}")

        for i, wf in enumerate(workflows):
            step_label = f"Step {i+1}/{len(workflows)} - {wf.name}"

            wf = self._resolve_param_references(wf, graph)
            logger.debug(f"Resolved workflow {wf.id}")

            if resume and self._check_run_success(run_dir=self._workflow_dir(wf)):
                logger.info(f"{step_label}: Skipping (already succseded)")
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
