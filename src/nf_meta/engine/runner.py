import logging
import shutil
import subprocess
import uuid
from enum import StrEnum
from typing import Optional, Protocol
from pathlib import Path
from nf_meta.engine.graph import MetaworkflowGraph
from nf_meta.engine.models import Workflow, GlobalOptions
import yaml

logger = logging.getLogger()

class Runners(StrEnum):
    PYTHON = "python"
    PLATFORM = "platform"
    DAISY_CHAIN = "daisy_chain"
    NEXTFLOW_MONO = "nextflow_mono"

class Runner(Protocol):

    def run(self, graph) -> None: ...

    def resume(self, graph) -> None: ...


# ToDO: Receive a Metawf_graph
def run_metapipeline(g: MetaworkflowGraph, runner: Runners, resume=False) -> None:
    logger.info("Started runner")
    if resume:
        runner.resume(g)
    else:
        runner.run(g)


class SimplePythonRunner:
    """
    Simple default runner for Metapipelines.
    Executes workflows in dag order from this Python runtime.
    """

    def __init__(self, tempdir=".nf-meta-cache"):
        self.tempdir = Path(tempdir)
        if not self.tempdir.exists():
            self.tempdir.mkdir(exist_ok=True)

        self.executable = self.check_nextflow()

    def check_nextflow(self):
        executable = shutil.which("nextflow")
        if executable is None:
            raise RuntimeError("No nextflow installation found")
        return executable

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

        return filename

    def run_workflow(self, wf: Workflow, globals: Optional[GlobalOptions]):
        cmd = [self.executable, "run", "-resume"]
        wf_params = wf.params

        if globals is not None:
            if globals.nf_profile is not None:
                cmd += ["-profile", globals.nf_profile]
            
            if globals.nf_config_file is not None:
                nf_cfg = Path(globals.nf_config_file)
                if not nf_cfg.exists():
                    raise RuntimeError(f"Nextflow config file does not exist: {nf_cfg}")
                cmd += ["-c", nf_cfg.absolute()]

            if globals.nf_params is not None:
                wf_params = self.merge_params()
        
        if wf_params:
            params_file: Path = self.create_params_file(wf_params)
            cmd += ["-params-file", params_file.absolute()]

        cmd.append(wf.url)
        cmd += ["-r", wf.version, "-latest"]

        print(f"[INFO] Nextflow command for {wf.name}:{wf.version} ({wf.id}): {cmd}")
        # TODO: Capture stdout, print stderr
        subprocess.run(cmd)

    def run(self, graph: MetaworkflowGraph):
        workflows = graph.get_workflows_sorted()

        for i, wf in enumerate(workflows):
            print(f"[DefaultRunner]: Step {i}/{len(workflows)} - {wf.name}")
            self.run_workflow(wf, graph.global_options)
            # TODO: Add checkpoint to tempdir

    def resume(self, graph: MetaworkflowGraph):
        # TODO: Check checkpoints in tempdir
        # TODO: Skip workflows where checkpoint is reached.
        pass
