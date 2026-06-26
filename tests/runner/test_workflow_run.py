import pytest
import yaml

from nf_meta.core.models import GlobalOptions
from nf_meta.runner.workflow_run import WorkflowRun, NfPipelineRun, NfModuleRun
from nf_meta.runner.errors import NfMetaRunnerError


@pytest.fixture
def workdir(tmp_path):
    return tmp_path / "workdir"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestForStep:
    def test_returns_pipeline_run_for_nf_pipeline(self, mock_nextflow, wf_rnaseq, workdir):
        run = WorkflowRun.for_step(wf_rnaseq, workdir, globals=None)
        assert isinstance(run, NfPipelineRun)

    def test_returns_module_run_for_nf_module(self, mock_nextflow, module_fastqc, workdir):
        run = WorkflowRun.for_step(module_fastqc, workdir, globals=None)
        assert isinstance(run, NfModuleRun)

    def test_extra_profile_forwarded(self, mock_nextflow, wf_rnaseq, workdir):
        run = WorkflowRun.for_step(wf_rnaseq, workdir, None, extra_profile="test")
        assert run.extra_profile == "test"


# ---------------------------------------------------------------------------
# prepare()
# ---------------------------------------------------------------------------


class TestPrepare:
    def test_creates_workdir(self, mock_nextflow, wf_rnaseq, workdir):
        NfPipelineRun(wf_rnaseq, workdir, None).prepare()
        assert workdir.exists()

    def test_writes_params_yaml(self, mock_nextflow, wf_rnaseq, workdir):
        wf = wf_rnaseq.model_copy(update={"params": {"input": "samples.csv"}})
        NfPipelineRun(wf, workdir, None).prepare()
        loaded = yaml.safe_load((workdir / "params.yaml").read_text())
        assert loaded == {"input": "samples.csv"}

    def test_params_file_path_set_after_prepare(self, mock_nextflow, wf_rnaseq, workdir):
        wf = wf_rnaseq.model_copy(update={"params": {"outdir": "results"}})
        run = NfPipelineRun(wf, workdir, None)
        run.prepare()
        assert run._params_file == workdir / "params.yaml"

    def test_no_params_file_when_wf_has_no_params(self, mock_nextflow, wf_rnaseq, workdir):
        run = NfPipelineRun(wf_rnaseq, workdir, None)
        run.prepare()
        assert run._params_file is None
        assert not (workdir / "params.yaml").exists()


# ---------------------------------------------------------------------------
# NfPipelineRun
# ---------------------------------------------------------------------------


class TestNfPipelineRunCmd:
    @pytest.fixture
    def run(self, mock_nextflow, wf_rnaseq, workdir):
        return NfPipelineRun(wf_rnaseq, workdir, None)

    def test_base_command_structure(self, run, wf_rnaseq):
        cmd = run.get_cmd()
        assert cmd[:2] == ["nextflow", "run"]
        assert "-ansi-log" in cmd

    def test_url_and_version_at_end(self, run, wf_rnaseq):
        cmd = run.get_cmd()
        assert cmd[-4] == wf_rnaseq.url
        assert cmd[-3] == "-r"
        assert cmd[-2] == wf_rnaseq.version
        assert cmd[-1] == "-latest"

    def test_resume_adds_flag(self, run):
        assert "-resume" in run.get_cmd(resume=True)

    def test_no_resume_by_default(self, run):
        assert "-resume" not in run.get_cmd()

    def test_stub_adds_flag(self, run):
        assert "-stub" in run.get_cmd(stub=True)

    def test_no_stub_by_default(self, run):
        assert "-stub" not in run.get_cmd()

    def test_globals_profile_used_when_wf_has_none(self, mock_nextflow, wf_rnaseq, workdir):
        run = NfPipelineRun(wf_rnaseq, workdir, GlobalOptions(profile="docker"))
        cmd = run.get_cmd()
        profile_str = cmd[cmd.index("-profile") + 1]
        assert "docker" in profile_str

    def test_wf_profile_replaces_globals_profile(self, mock_nextflow, wf_rnaseq, workdir):
        wf = wf_rnaseq.model_copy(update={"profile": "singularity"})
        run = NfPipelineRun(wf, workdir, GlobalOptions(profile="docker"))
        cmd = run.get_cmd()
        profile_str = cmd[cmd.index("-profile") + 1]
        assert "singularity" in profile_str
        assert "docker" not in profile_str

    def test_extra_profile_appended(self, mock_nextflow, wf_rnaseq, workdir):
        run = NfPipelineRun(wf_rnaseq, workdir, None, extra_profile="test")
        cmd = run.get_cmd()
        assert "test" in cmd[cmd.index("-profile") + 1]

    def test_wf_and_extra_profile_combined(self, mock_nextflow, wf_rnaseq, workdir):
        wf = wf_rnaseq.model_copy(update={"profile": "docker"})
        run = NfPipelineRun(wf, workdir, None, extra_profile="test")
        parts = run.get_cmd()[run.get_cmd().index("-profile") + 1].split(",")
        assert "docker" in parts
        assert "test" in parts

    def test_globals_config_file_adds_c_flag(self, mock_nextflow, wf_rnaseq, workdir, tmp_path):
        cfg = tmp_path / "global.config"
        cfg.write_text("")
        run = NfPipelineRun(wf_rnaseq, workdir, GlobalOptions(config_file=str(cfg)))
        cmd = run.get_cmd()
        assert "-c" in cmd
        assert str(cfg.resolve()) in cmd

    def test_wf_config_file_adds_c_flag(self, mock_nextflow, wf_rnaseq, workdir, tmp_path):
        cfg = tmp_path / "wf.config"
        cfg.write_text("")
        wf = wf_rnaseq.model_copy(update={"config_file": str(cfg)})
        run = NfPipelineRun(wf, workdir, None)
        cmd = run.get_cmd()
        assert "-c" in cmd
        assert str(cfg) in cmd

    def test_params_file_flag_after_prepare(self, mock_nextflow, wf_rnaseq, workdir):
        wf = wf_rnaseq.model_copy(update={"params": {"input": "samples.csv"}})
        run = NfPipelineRun(wf, workdir, None)
        run.prepare()
        assert "-params-file" in run.get_cmd()

    def test_no_params_file_flag_without_params(self, run):
        run.prepare()
        assert "-params-file" not in run.get_cmd()

    def test_main_script_adds_flag(self, mock_nextflow, wf_rnaseq, workdir):
        wf = wf_rnaseq.model_copy(update={"main_script": "workflows/special.nf"})
        run = NfPipelineRun(wf, workdir, None)
        cmd = run.get_cmd()
        assert "-main-script" in cmd
        assert cmd[cmd.index("-main-script") + 1] == "workflows/special.nf"

    def test_no_main_script_omits_flag(self, run):
        assert "-main-script" not in run.get_cmd()

    def test_nonexistent_globals_config_raises(self, mock_nextflow, wf_rnaseq, workdir, tmp_path):
        g = GlobalOptions()
        g.__dict__["config_file"] = tmp_path / "nonexistent.config"
        run = NfPipelineRun(wf_rnaseq, workdir, g)
        with pytest.raises(NfMetaRunnerError):
            run.get_cmd()


# ---------------------------------------------------------------------------
# NfModuleRun
# ---------------------------------------------------------------------------


class TestNfModuleRunCmd:
    @pytest.fixture
    def run(self, mock_nextflow, module_fastqc, workdir):
        return NfModuleRun(module_fastqc, workdir, None)

    def test_base_command_structure(self, run):
        cmd = run.get_cmd()
        assert cmd[:3] == ["nextflow", "module", "run"]
        assert "-ansi-log" in cmd

    def test_module_ref_is_last_arg(self, run, module_fastqc):
        cmd = run.get_cmd()
        assert cmd[-1] == f"{module_fastqc.name}@{module_fastqc.version}"

    def test_resume_adds_flag(self, run):
        assert "-resume" in run.get_cmd(resume=True)

    def test_no_resume_by_default(self, run):
        assert "-resume" not in run.get_cmd()

    def test_stub_adds_flag(self, run):
        assert "-stub" in run.get_cmd(stub=True)

    def test_no_stub_by_default(self, run):
        assert "-stub" not in run.get_cmd()

    def test_params_file_flag_after_prepare(self, mock_nextflow, module_fastqc, workdir):
        wf = module_fastqc.model_copy(update={"params": {"input": "file.fastq"}})
        run = NfModuleRun(wf, workdir, None)
        run.prepare()
        assert "-params-file" in run.get_cmd()

    def test_no_params_file_flag_without_params(self, run):
        run.prepare()
        assert "-params-file" not in run.get_cmd()

    def test_globals_config_file_adds_c_flag(self, mock_nextflow, module_fastqc, workdir, tmp_path):
        cfg = tmp_path / "global.config"
        cfg.write_text("")
        run = NfModuleRun(module_fastqc, workdir, GlobalOptions(config_file=str(cfg)))
        cmd = run.get_cmd()
        assert "-c" in cmd
        assert str(cfg.resolve()) in cmd

    def test_wf_config_file_adds_c_flag(self, mock_nextflow, module_fastqc, workdir, tmp_path):
        cfg = tmp_path / "wf.config"
        cfg.write_text("")
        wf = module_fastqc.model_copy(update={"config_file": str(cfg)})
        run = NfModuleRun(wf, workdir, None)
        cmd = run.get_cmd()
        assert "-c" in cmd
        assert str(cfg) in cmd

    def test_no_profile_flag(self, run):
        assert "-profile" not in run.get_cmd()

    def test_nonexistent_globals_config_raises(self, mock_nextflow, module_fastqc, workdir, tmp_path):
        g = GlobalOptions()
        g.__dict__["config_file"] = tmp_path / "nonexistent.config"
        run = NfModuleRun(module_fastqc, workdir, g)
        with pytest.raises(NfMetaRunnerError):
            run.get_cmd()
