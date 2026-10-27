import pytest
import yaml

from nf_meta.core.models import GlobalOptions, WorkflowType
from nf_meta.runner.engines import (
    NextflowModuleEngine,
    NextflowPipelineEngine,
    StepCommand,
    engine_for,
)
from nf_meta.runner.errors import NfMetaRunnerError
from nf_meta.runner.spec import build_step_spec


@pytest.fixture
def state_dir(tmp_path):
    return tmp_path / "state"


@pytest.fixture
def build(state_dir, tmp_path):
    """Build a step's command the way the runner does."""

    def _build(wf, globals=None, **kwargs) -> StepCommand:
        spec = build_step_spec(wf, globals, state_dir=state_dir, launch_dir=tmp_path, **kwargs)
        return engine_for(spec.workflow_type).build(spec)

    return _build


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestEngineFor:
    def test_pipeline(self):
        assert isinstance(engine_for(WorkflowType.NF_PIPELINE), NextflowPipelineEngine)

    def test_module(self):
        assert isinstance(engine_for(WorkflowType.NF_MODULE), NextflowModuleEngine)


# ---------------------------------------------------------------------------
# Params file
# ---------------------------------------------------------------------------


class TestParamsFile:
    def test_not_written_by_build(self, build, wf_rnaseq, state_dir):
        build(wf_rnaseq.model_copy(update={"params": {"input": "samples.csv"}}))
        assert not state_dir.exists()

    def test_write_files_creates_params_yaml(self, build, wf_rnaseq, state_dir):
        cmd = build(wf_rnaseq.model_copy(update={"params": {"input": "samples.csv"}}))
        cmd.write_files()
        assert cmd.params_file == state_dir / "params.yaml"
        assert yaml.safe_load(cmd.params_file.read_text()) == {"input": "samples.csv"}

    def test_none_without_params(self, build, wf_rnaseq, state_dir):
        cmd = build(wf_rnaseq)
        cmd.write_files()
        assert cmd.params_file is None
        assert not state_dir.exists()

    def test_globals_params_under_step_params(self, build, wf_rnaseq):
        wf = wf_rnaseq.model_copy(update={"params": {"a": 1, "b": 2}})
        cmd = build(wf, GlobalOptions(params={"b": 0, "c": 3}))
        assert cmd.params == {"a": 1, "b": 2, "c": 3}

    def test_runs_in_launch_dir(self, build, wf_rnaseq, tmp_path):
        assert build(wf_rnaseq).cwd == tmp_path


# ---------------------------------------------------------------------------
# nf-pipeline
# ---------------------------------------------------------------------------


class TestPipelineCommand:
    def test_base_command_structure(self, build, wf_rnaseq):
        argv = build(wf_rnaseq).argv
        assert argv[:2] == ["nextflow", "run"]
        assert "-ansi-log" in argv

    def test_url_and_version_at_end(self, build, wf_rnaseq):
        argv = build(wf_rnaseq).argv
        assert argv[-4:] == [wf_rnaseq.url, "-r", wf_rnaseq.version, "-latest"]

    def test_resume_adds_flag(self, build, wf_rnaseq):
        assert "-resume" in build(wf_rnaseq, resume=True).argv

    def test_no_resume_by_default(self, build, wf_rnaseq):
        assert "-resume" not in build(wf_rnaseq).argv

    def test_stub_adds_flag_last(self, build, wf_rnaseq):
        assert build(wf_rnaseq, stub=True).argv[-1] == "-stub"

    def test_no_stub_by_default(self, build, wf_rnaseq):
        assert "-stub" not in build(wf_rnaseq).argv

    def test_globals_profile_used_when_wf_has_none(self, build, wf_rnaseq):
        argv = build(wf_rnaseq, GlobalOptions(profile="docker")).argv
        assert argv[argv.index("-profile") + 1] == "docker"

    def test_wf_profile_replaces_globals_profile(self, build, wf_rnaseq):
        wf = wf_rnaseq.model_copy(update={"profile": "singularity"})
        argv = build(wf, GlobalOptions(profile="docker")).argv
        assert argv[argv.index("-profile") + 1] == "singularity"

    def test_no_profile_flag_without_profiles(self, build, wf_rnaseq):
        assert "-profile" not in build(wf_rnaseq).argv

    def test_wf_and_extra_profile_combined(self, build, wf_rnaseq):
        wf = wf_rnaseq.model_copy(update={"profile": "docker"})
        argv = build(wf, extra_profile="test").argv
        assert argv[argv.index("-profile") + 1] == "docker,test"

    def test_globals_config_file_adds_c_flag(self, build, wf_rnaseq, tmp_path):
        cfg = tmp_path / "global.config"
        cfg.write_text("")
        argv = build(wf_rnaseq, GlobalOptions(config_file=str(cfg))).argv
        assert argv[argv.index("-c") + 1] == str(cfg.resolve())

    def test_global_then_wf_config_file(self, build, wf_rnaseq, tmp_path):
        g_cfg, w_cfg = tmp_path / "global.config", tmp_path / "wf.config"
        g_cfg.write_text("")
        w_cfg.write_text("")
        wf = wf_rnaseq.model_copy(update={"config_file": str(w_cfg)})
        argv = build(wf, GlobalOptions(config_file=str(g_cfg))).argv
        configs = [argv[i + 1] for i, a in enumerate(argv) if a == "-c"]
        assert configs == [str(g_cfg.resolve()), str(w_cfg)]

    def test_params_file_flag(self, build, wf_rnaseq, state_dir):
        argv = build(wf_rnaseq.model_copy(update={"params": {"input": "s.csv"}})).argv
        assert argv[argv.index("-params-file") + 1] == str(state_dir / "params.yaml")

    def test_no_params_file_flag_without_params(self, build, wf_rnaseq):
        assert "-params-file" not in build(wf_rnaseq).argv

    def test_main_script_adds_flag(self, build, wf_rnaseq):
        wf = wf_rnaseq.model_copy(update={"main_script": "workflows/special.nf"})
        argv = build(wf).argv
        assert argv[argv.index("-main-script") + 1] == "workflows/special.nf"

    def test_no_main_script_omits_flag(self, build, wf_rnaseq):
        assert "-main-script" not in build(wf_rnaseq).argv

    def test_nonexistent_globals_config_raises(self, build, wf_rnaseq, tmp_path):
        g = GlobalOptions()
        g.__dict__["config_file"] = tmp_path / "nonexistent.config"
        with pytest.raises(NfMetaRunnerError):
            build(wf_rnaseq, g)


# ---------------------------------------------------------------------------
# nf-module
# ---------------------------------------------------------------------------


class TestModuleCommand:
    def test_base_command_structure(self, build, module_fastqc):
        argv = build(module_fastqc).argv
        assert argv[:3] == ["nextflow", "module", "run"]
        assert "-ansi-log" in argv

    def test_module_ref_is_last_arg(self, build, module_fastqc):
        assert build(module_fastqc).argv[-1] == f"{module_fastqc.name}@{module_fastqc.version}"

    def test_resume_adds_flag(self, build, module_fastqc):
        assert "-resume" in build(module_fastqc, resume=True).argv

    def test_stub_adds_flag_last(self, build, module_fastqc):
        assert build(module_fastqc, stub=True).argv[-1] == "-stub"

    def test_params_file_flag(self, build, module_fastqc):
        wf = module_fastqc.model_copy(update={"params": {"input": "file.fastq"}})
        assert "-params-file" in build(wf).argv

    def test_no_params_file_flag_without_params(self, build, module_fastqc):
        assert "-params-file" not in build(module_fastqc).argv

    def test_globals_config_file_adds_c_flag(self, build, module_fastqc, tmp_path):
        cfg = tmp_path / "global.config"
        cfg.write_text("")
        argv = build(module_fastqc, GlobalOptions(config_file=str(cfg))).argv
        assert str(cfg.resolve()) in argv

    def test_no_profile_flag(self, build, module_fastqc):
        assert "-profile" not in build(module_fastqc, GlobalOptions(profile="docker")).argv

    def test_nonexistent_globals_config_raises(self, build, module_fastqc, tmp_path):
        g = GlobalOptions()
        g.__dict__["config_file"] = tmp_path / "nonexistent.config"
        with pytest.raises(NfMetaRunnerError):
            build(module_fastqc, g)


# ---------------------------------------------------------------------------
# Locations: -log, -w, NXF_CACHE_DIR (plans/P0-findings.md, H5/H3/H12)
# ---------------------------------------------------------------------------


class TestLocations:
    def test_log_file_is_global_option_before_subcommand(self, build, wf_rnaseq, tmp_path):
        argv = build(wf_rnaseq, log_file=tmp_path / "nf.log").argv
        assert argv[:4] == ["nextflow", "-log", str(tmp_path / "nf.log"), "run"]

    def test_log_file_before_module_subcommand(self, build, module_fastqc, tmp_path):
        argv = build(module_fastqc, log_file=tmp_path / "nf.log").argv
        assert argv[:5] == ["nextflow", "-log", str(tmp_path / "nf.log"), "module", "run"]

    def test_work_dir_adds_w_flag(self, build, wf_rnaseq, tmp_path):
        argv = build(wf_rnaseq, work_dir=tmp_path / "work").argv
        assert argv[argv.index("-w") + 1] == str(tmp_path / "work")

    def test_nextflow_cache_dir_sets_env(self, build, wf_rnaseq, tmp_path):
        cmd = build(wf_rnaseq, nextflow_cache_dir=tmp_path / "nxf")
        assert cmd.env == {"NXF_CACHE_DIR": str(tmp_path / "nxf")}

    def test_defaults_leave_nextflow_defaults(self, build, wf_rnaseq):
        cmd = build(wf_rnaseq)
        assert cmd.env == {}
        assert "-w" not in cmd.argv
        assert "-log" not in cmd.argv
