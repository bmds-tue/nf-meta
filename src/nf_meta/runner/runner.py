from .base_runner import _REGISTRY
from .errors import NfMetaRunnerError
from .utils import RunOptions

import logging
from nf_meta.core.graph import MetaworkflowGraph


logger = logging.getLogger(__name__)


def run_metapipeline(
    g: MetaworkflowGraph,
    run_options: RunOptions = RunOptions(),
) -> None:
    logger.info("Started runner")

    errors = []
    if run_options.start:
        if not g.get_workflow_by_id(run_options.start):
            errors.append(
                f"Starting workflow {run_options.start} is not a valid workflow id!"
            )
        else:
            logger.info(f"Starting workflow: {run_options.start}")

    if run_options.target:
        if not g.get_workflow_by_id(run_options.target):
            errors.append(
                f"Target workflow {run_options.target} is not a valid workflow id!"
            )
        else:
            logger.info(f"Target workflow: {run_options.target}")

    if errors:
        raise NfMetaRunnerError("\n".join(errors))

    runner_cls = _REGISTRY.get(run_options.runner_name)
    if runner_cls is None:
        available = ", ".join(f"'{k}'" for k in _REGISTRY)
        raise NfMetaRunnerError(
            f"Unknown runner '{run_options.runner_name}'. Available: {available}"
        )

    runner = runner_cls(run_options)

    if run_options.resume:
        runner.resume(g)
    else:
        runner.run(g)
