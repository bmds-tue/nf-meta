import logging
import os
import shutil
import subprocess
import uuid
import threading
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional, Protocol
from pathlib import Path
from nf_meta.engine.graph import MetaworkflowGraph
from nf_meta.engine.models import Workflow, GlobalOptions

import click
import yaml
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from rich.panel import Panel
from rich.console import Console, Group

# TODO: Use logging everywhere
logger = logging.getLogger()
console = Console()

class Runners(StrEnum):
    PYTHON = "python"
    PLATFORM = "platform"
    DAISY_CHAIN = "daisy_chain"
    NEXTFLOW_MONO = "nextflow_mono"


class Runner(Protocol):
    def run(self, graph) -> None: ...
    def resume(self, graph) -> None: ...


def run_metapipeline(
        g: MetaworkflowGraph,
        runner_name: Runners,
        resume=False,
        verbose=True
    ) -> None:
    logger.info("Started runner")

    runner = None
    match runner_name:
        case Runners.PYTHON:
            runner = SimplePythonRunner()
        case _:
            raise NotImplementedError("Requested runner not implemented yet")
    
    if resume:
        runner.resume(g)
    else:
        runner.run(g)


@dataclass
class NfMetaRunnerError(Exception):
    message: str
   
    def __str__(self) -> str:
        return self.message


class SimplePythonRunner:
    """
    Simple default runner for Metapipelines.
    Executes workflows in dag order from this Python runtime.
    """
    OUT_FILE = "OUT.txt"
    ERROR_FILE = "ERROR.txt"

    def __init__(self, tempdir=".nf-meta-cache"):
        self.tempdir = Path(tempdir)
        self.tempdir.mkdir(parents=True, exist_ok=True)
        self.executable = self.check_nextflow()
    
    @contextmanager
    def chdir_context(self, path: Path):
        origin = Path()
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.chdir(path)
            yield
        finally:
            os.chdir(origin)

    def check_nextflow(self):
        executable = shutil.which("nextflow")
        if executable is None:
            raise NfMetaRunnerError("No nextflow installation found")
        return executable
    
    def check_run_success(self, run_dir: Path = Path(".")):
        return Path(run_dir / self.OUT_FILE).exists() \
            and not Path(run_dir / self.ERROR_FILE).exists()

    def merge_params(self, specific_params: dict, default_params: dict):
        return {**default_params, **specific_params}

    def create_params_file(self, params: dict, filename: Optional[Path] = None) -> Path:
        if filename is None:
            params_file = f"params-{uuid.uuid4()}.yaml"
            filename = Path(self.tempdir / params_file)
        
        with open(filename, "w") as f:
            f.write(yaml.dump(params))

        return Path(filename)

    def create_workdir_names(self, workflows: list[Workflow]) -> dict[str, Path]:
        dirs = dict()
        for wf in workflows:
            wf_dir = Path(self.tempdir) / Path(f"{wf.name.replace("/", "_")}_{wf.version}_{wf.hash()}")
            dirs[wf.id] = wf_dir.resolve()
        return dirs

    def resolve_param_references(self, 
                                 wf: Workflow, 
                                 graph: MetaworkflowGraph, 
                                 work_directories: Optional[dict[str, str]]
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

    def stream_proc_out(
                self,
                cmd: list[str],
                output_lines=10
            ) -> tuple[int, str, str]:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    
        tail = deque(maxlen=output_lines)
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        # Read stderr in a background thread so it never blocks the process.
        def _collect_stderr() -> None:
            assert process.stderr is not None
            print(process)
            for line in process.stderr:
                print(line)
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
                    Spinner("dots", text="[SimplePythonRunner] Running Workflow ...")
                ))

            process.wait()
            stderr_thread.join()
            stderr = "".join(stderr_lines)
            stdout = "".join(stdout_lines)

            if process.returncode > 0:
                live.update(Panel(stderr, title="Errors"))
            else:
                live.update(Text("[SimplePythonRunner] Running Workflow ... Done"))

        return (process.returncode, stdout, stderr)

    def run_workflow(self, wf: Workflow, globals: Optional[GlobalOptions]):
        cmd = [self.executable, "run", "-resume", "-ansi-log", "false"]
        wf_params = dict(wf.params or {})

        if globals is not None:
            if globals.nf_profile:
                cmd += ["-profile", globals.nf_profile]

            if globals.nf_config_file is not None:
                nf_cfg = Path(globals.nf_config_file)
                if not nf_cfg.exists():
                    raise NfMetaRunnerError(f"Global config file does not exist: {nf_cfg}")
                cmd += ["-c", str(nf_cfg)]

            if globals.nf_params:
                wf_params = self.merge_params(wf_params, globals.nf_params)

        if wf_params:
            params_file = self.create_params_file(wf_params, Path("params.yaml"))
            cmd += ["-params-file", str(params_file)]

        if wf.config_file:
            if not wf.config_file.exists():
                raise NfMetaRunnerError(f"Config file referenced by workflow {wf.id} does not exists: {wf.config_file}")
            cmd += ["-c", str(wf.config_file)]

        cmd += [wf.url, "-r", wf.version, "-latest"]

        print(f"[INFO] Nextflow command: {cmd}")
        exit_code, out, err = self.stream_proc_out(cmd)

        with Path(self.OUT_FILE).open("w") as f:
            f.write(out)

        if exit_code != 0:
            print(f"[Error] Command exited with error code {exit_code}. Workdir: {Path(".").absolute()}")
            with Path(self.ERROR_FILE).open("w") as f:
                f.write(err)
        
        return exit_code == 0

    def run(self, graph: MetaworkflowGraph, resume=False):
        workflows = graph.get_workflows_sorted()
        workdirs = self.create_workdir_names(workflows)

        for i, wf in enumerate(workflows):
            wf = self.resolve_param_references(wf, graph, work_directories=workdirs)
            with self.chdir_context(workdirs[wf.id]):
                if resume and self.check_run_success():
                    print(f"[SimplePythonRunner] Step {i+1}/{len(workflows)} - {wf.name}: Skipping")
                    continue

                print(f"[SimplePythonRunner] Step {i+1}/{len(workflows)} - {wf.name}")
                if not self.run_workflow(wf, graph.global_options):
                    print("[SimplePythonRunner] Workflow completed with errors!")
                    return

        print("[SimplePythonRunner] All workflows completed")

    def resume(self, graph: MetaworkflowGraph):
        self.run(graph, resume=True)
