from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from nf_meta.core.graph import MetaworkflowGraph
from nf_meta.core.models import GlobalOptions, Workflow, WorkflowType, load_params_file
from .errors import NfMetaRunnerError


@dataclass(frozen=True)
class StepSpec:
    """One step of a run with every value final: references resolved, globals
    merged in, and all locations decided. Runners hand it to an engine
    (`engines.engine_for`), which turns it into a command.

    Attributes:
        workflow: The step's workflow, with `${...}` references resolved.
        params: Content of the params file Nextflow receives: the step's
            `params_file`, overlaid with `globals.params`, overlaid with the
            step's own `params`.
        profiles: Nextflow profiles in order: the global profile (only if the
            step sets none), the step's profile, the run-level extra profile.
        config_files: Global config file, then the step's config file.
        launch_dir: Directory Nextflow is started from.
        work_dir: Nextflow work dir (`-w`), or `None` for Nextflow's default.
        state_dir: Directory for nf-meta's per-step files (params file, output
            and error logs).
        resume: Pass `-resume` to Nextflow.
        stub: Pass `-stub` to Nextflow.
    """

    workflow: Workflow
    params: dict[str, Any]
    profiles: tuple[str, ...]
    config_files: tuple[Path, ...]
    launch_dir: Path
    work_dir: Optional[Path]
    state_dir: Path
    resume: bool = False
    stub: bool = False

    @property
    def step_id(self) -> str:
        return self.workflow.id

    @property
    def workflow_type(self) -> WorkflowType:
        return WorkflowType(self.workflow.type)


def resolve_references(
    wf: Workflow,
    graph: MetaworkflowGraph,
    resolved: Optional[dict[str, dict]] = None,
) -> Workflow:
    """Return a copy of `wf` with every `${<id>:params:<key>}` reference in its
    params replaced by the referenced value.

    Values come from `resolved` (params of steps already resolved in this run,
    or loaded from the cache) when present, else from the referenced step's
    configured params.

    Raises:
        NfMetaRunnerError: for a reference namespace other than `params`.
        ValueError: when a referenced step, key, or value doesn't exist.
    """
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

        if ref_value is None:
            raise ValueError(
                f"Resolving reference {ref.name} failed: "
                f"key '{ref.target_key}' not found in workflow '{ref.target_wf_id}' {ref.namespace}"
            )
        if source_value is None:
            raise ValueError(
                f"Resolving reference {ref.name} failed: "
                f"source key '{ref.source_key}' not found in workflow '{ref.source_wf_id}' params"
            )

        wf_resolved.params[ref.source_key] = source_value.replace(ref.name, str(ref_value))

    return wf_resolved


def build_step_spec(
    wf: Workflow,
    globals: Optional[GlobalOptions],
    *,
    state_dir: Path,
    launch_dir: Path,
    work_dir: Optional[Path] = None,
    extra_profile: str = "",
    resume: bool = False,
    stub: bool = False,
) -> StepSpec:
    """Combine a step whose references are already resolved with the run's
    globals and locations into a `StepSpec`.

    Raises:
        NfMetaRunnerError: if the global config file doesn't exist.
    """
    params_file = getattr(wf, "params_file", None)
    params: dict[str, Any] = dict(load_params_file(params_file)) if params_file else {}
    if globals and globals.params:
        params.update(globals.params)
    params.update(wf.params or {})

    profile = getattr(wf, "profile", None)
    profiles: list[str] = []
    if globals and globals.profile and not profile:
        profiles.append(globals.profile)
    if profile:
        profiles.append(profile)
    if extra_profile:
        profiles.append(extra_profile)

    config_files: list[Path] = []
    if globals and globals.config_file:
        global_cfg = Path(globals.config_file)
        if not global_cfg.exists():
            raise NfMetaRunnerError(f"Global config file does not exist: {global_cfg}")
        config_files.append(global_cfg)
    if wf.config_file:
        config_files.append(Path(wf.config_file))

    return StepSpec(
        workflow=wf,
        params=params,
        profiles=tuple(profiles),
        config_files=tuple(config_files),
        launch_dir=launch_dir,
        work_dir=work_dir,
        state_dir=state_dir,
        resume=resume,
        stub=stub,
    )
