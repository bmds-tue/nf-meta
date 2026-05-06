from .python_runner import SimplePythonRunner
from .cascade_runner import NfCascadeRunner
from .errors import NfMetaRunnerError

import logging
from enum import StrEnum
from typing import Protocol
from nf_meta.core.graph import MetaworkflowGraph
from nf_meta.core.models import Workflow, GlobalOptions


logger = logging.getLogger(__name__)


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
        runner_name: Runners = Runners.PYTHON,
        resume = False,
        verbose = True,
        output_lines = 20,
        start: str = None,
        target: str = None,
        profile: str = None
    ) -> None:
    logger.info("Started runner")

    errors = []
    if start:
        if not g.get_workflow_by_id(start):
            errors.append(f"Starting workflow {start} is not a valid workflow id!")
        else:
            logger.info(f"Starting workflow: {start}")
        
    if target:
        if not g.get_workflow_by_id(target):
            errors.append(f"Target workflow {target} is not a valid workflow id!")
        else:
            logger.info(f"Target workflow: {target}")
    
    if errors:
        raise NfMetaRunnerError("\n".join(errors))

    runner = None
    match runner_name:
        case Runners.PYTHON:
            runner = SimplePythonRunner(output_window_size=output_lines, start=start, target=target, extra_profile=profile)
        case _:
            raise NotImplementedError("Requested runner not implemented yet")
    
    if resume:
        runner.resume(g)
    else:
        runner.run(g)
