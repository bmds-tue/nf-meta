import logging
import os
import shutil
import subprocess
import sys
import uuid
import time
from collections import deque
from contextlib import contextmanager
from enum import StrEnum
from typing import Optional, Protocol
from pathlib import Path
from nf_meta.engine.graph import MetaworkflowGraph
from nf_meta.engine.models import Workflow, GlobalOptions
import yaml

import click
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


def run_metapipeline(g: MetaworkflowGraph, runner_name: Runners, resume=False, verbose=True) -> None:
    logger.info("Started runner")

    runner = None
    match runner_name:
        case Runners.PYTHON:
            runner = SimplePythonRunner()
        case _:
            raise NotImplementedError("Requested runner not implemented yet")
    
    if runner:
        if resume:
            runner.resume(g)
        else:
            runner.run(g)


class SimplePythonRunner:
    """
    Simple default runner for Metapipelines.
    Executes workflows in dag order from this Python runtime.
    """
    OUT_FILE = "OUT.txt"
    ERROR_FILE = "ERROR.txt"

    def __init__(self, tempdir=".nf-meta-cache"):
        self.tempdir = Path(tempdir)
        if not self.tempdir.exists():
            self.tempdir.mkdir(exist_ok=True)

        self.executable = self.check_nextflow()
    
    @contextmanager
    def chdir_context(self, path: Path):
        origin = Path()
        try:
            if not path.exists():
                path.mkdir()
            os.chdir(path)
            yield
        finally:
            os.chdir(origin)

    def check_nextflow(self):
        executable = shutil.which("nextflow")
        if executable is None:
            raise RuntimeError("No nextflow installation found")
        return executable
    
    def check_run_success(self, run_dir: Path = Path(".")):
        return Path(run_dir / self.OUT_FILE).exists() \
            and not Path(run_dir / self.ERROR_FILE).exists()

    def merge_params(self, specific_params: dict, default_params: dict):
        merged_params = default_params
        merged_params.update(specific_params)
        return merged_params

    def create_params_file(self, params: dict, filename: Optional[Path] = None) -> Path:
        if filename is None:
            params_file = f"params-{uuid.uuid4()}.yaml"
            filename = Path(self.tempdir / params_file)
        
        with open(filename, "w") as f:
            f.write(yaml.dump(params))

        return Path(filename)

    def run_cmd_tail(self, cmd: list[str], output_lines=10) -> tuple[int, str, str]:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    
        last_lines = deque(maxlen=output_lines)

        with Live(console=console, refresh_per_second=4) as live:
            for line in process.stdout:
                last_lines.append(line.rstrip())
                live.update(Group(
                    Panel("\n".join(last_lines), title="Workflow Output"),
                    Spinner("dots", text="[SimplePythonRunner] Running Workflow ...")
                ))

            process.wait()
            error = process.stderr.read()
            out = process.stdout.read()

            if process.returncode > 0:
                live.update(Panel(error, title="Errors"))
            else:
                live.update(Text("[SimplePythonRunner] Running Workflow ... Done"))

        return (process.returncode, out, error)

    def run_workflow(self, wf: Workflow, globals: Optional[GlobalOptions]):
        cmd = [self.executable, "run", "-resume", "-ansi-log", "false"]
        wf_params = wf.params

        if globals is not None:
            if globals.nf_profile is not None:
                cmd += ["-profile", globals.nf_profile]
            
            if globals.nf_config_file is not None:
                nf_cfg = Path(globals.nf_config_file)
                if not nf_cfg.exists():
                    raise RuntimeError(f"Nextflow config file does not exist: {nf_cfg}")
                cmd += ["-c", str(nf_cfg.absolute())]

            if globals.nf_params is not None:
                wf_params = self.merge_params(wf_params, globals.nf_params)
        
        if wf_params:
            params_file = self.create_params_file(wf_params, Path("params.yaml"))
            cmd += ["-params-file", params_file.absolute()]

        if wf.config_file:
            if not wf.config_file.exists():
                raise RuntimeError(f"Nexflow config file does not exists: {wf.config_file}")
            cmd += ["-c", str(wf.config_file.absolute())]

        cmd.append(wf.url)
        cmd += ["-r", wf.version, "-latest"]

        print(f"[INFO] Nextflow command: {cmd}")
        exit_code, out, err = self.run_cmd_tail(cmd)

        with Path(self.OUT_FILE).open("w") as f:
            f.write(out)

        if exit_code != 0:
            print(f"[Error] Command exited with error code {exit_code}. Workdir: {Path(".").absolute()}")
            with Path(self.ERROR_FILE).open("w") as f:
                f.write(err)
        
        return exit_code == 0

    def run(self, graph: MetaworkflowGraph, resume=False):
        workflows = graph.get_workflows_sorted()

        for i, wf in enumerate(workflows):
            wf_dir = Path(f"{wf.name.replace("/", "_")}_{wf.version}_{wf.hash()}")
            with self.chdir_context(self.tempdir / wf_dir):
                if resume and self.check_run_success():
                    print(f"[SimplePythonRunner] Step {i+1}/{len(workflows)} - {wf.name}: Skipping")
                    continue

                print(f"[SimplePythonRunner] Step {i+1}/{len(workflows)} - {wf.name}")
                # TODO: resolve field references to params in predecessor workflows!
                if not self.run_workflow(wf, graph.global_options):
                    print("[SimplePythonRunner] Workflow completed with errors!")
                    return

        print("[SimplePythonRunner] All workflows completed")

    def resume(self, graph: MetaworkflowGraph):
        self.run(graph, resume=True)
