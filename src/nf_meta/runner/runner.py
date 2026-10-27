import logging

from nf_meta.core.graph import MetaworkflowGraph

from .base_runner import _REGISTRY, BaseRunner, PlannedStep
from .errors import NfMetaRunnerError
from .utils import RunOptions

logger = logging.getLogger(__name__)


def _make_runner(run_options: RunOptions) -> BaseRunner:
    runner_cls = _REGISTRY.get(run_options.runner_name)
    if runner_cls is None:
        available = ", ".join(f"'{k}'" for k in _REGISTRY)
        raise NfMetaRunnerError(f"Unknown runner '{run_options.runner_name}'. Available: {available}")
    return runner_cls(run_options)


def _check_start_target(g: MetaworkflowGraph, run_options: RunOptions) -> None:
    errors = []
    if run_options.start:
        if not g.get_workflow_by_id(run_options.start):
            errors.append(f"Starting workflow {run_options.start} is not a valid workflow id!")
        else:
            logger.info(f"Starting workflow: {run_options.start}")

    if run_options.target:
        if not g.get_workflow_by_id(run_options.target):
            errors.append(f"Target workflow {run_options.target} is not a valid workflow id!")
        else:
            logger.info(f"Target workflow: {run_options.target}")

    if errors:
        raise NfMetaRunnerError("\n".join(errors))


def plan_metapipeline(
    g: MetaworkflowGraph,
    run_options: RunOptions | None = None,
) -> list[PlannedStep]:
    """Return the steps `run_metapipeline` would execute with these options
    (default: `RunOptions()`), without running anything."""
    run_options = run_options or RunOptions()
    _check_start_target(g, run_options)
    return _make_runner(run_options).plan(g, resume=run_options.resume)


def run_metapipeline(
    g: MetaworkflowGraph,
    run_options: RunOptions | None = None,
) -> None:
    run_options = run_options or RunOptions()
    logger.info("Started runner")
    _check_start_target(g, run_options)
    runner = _make_runner(run_options)

    if run_options.resume:
        runner.resume(g)
    else:
        runner.run(g)
