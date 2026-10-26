"""Project dir vs out dir (plans/P2-project-out-dir-layout.md)."""

from unittest.mock import MagicMock

import pytest
import yaml

from nf_meta.core.config import from_file, validated_graph
from nf_meta.core.errors import ConfigValidationError
from nf_meta.runner.errors import NfMetaRunnerError
from nf_meta.runner.python_runner import SimplePythonRunner
from nf_meta.runner.utils import RunOptions


SCHEMA = {
    name: {"type": "string", "required": False, "enum": None, "pattern": None,
           "format": None, "default": None, "hidden": False}
    for name in ("input", "outdir", "contrasts", "genome", "nf_core_pipeline", "extra")
}


@pytest.fixture(autouse=True)
def schema(monkeypatch):
    """A schema knowing every param used here, none of them declared as paths."""
    for target in (
        "nf_meta.core.dynamic_validation.get_pipeline_schema",
        "nf_meta.runner.paths.get_pipeline_schema",
    ):
        monkeypatch.setattr(target, lambda url, version: SCHEMA)


def with_path_format(monkeypatch, param):
    schema = {**SCHEMA, param: {**SCHEMA[param], "format": "file-path"}}
    monkeypatch.setattr("nf_meta.runner.paths.get_pipeline_schema", lambda url, version: schema)


@pytest.fixture
def project(tmp_path):
    d = tmp_path / "project"
    d.mkdir()
    (d / "ids.csv").write_text("SRR1\n")
    (d / "contrasts.csv").write_text("id\n")
    return d


def write_config(project, workflows: dict, globals: dict | None = None):
    data = {"config_version": "0.3.0", "workflows": workflows}
    if globals:
        data["globals"] = globals
    path = project / "metaconfig.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def two_steps(**overrides):
    workflows = {
        "n01": {
            "name": "nf-core/fetchngs",
            "version": "1.12.0",
            "params": {"input": "ids.csv", "outdir": "out_fetchngs"},
        },
        "n02": {
            "name": "nf-core/rnaseq",
            "version": "3.14.0",
            "from": "n01",
            "params": {
                "input": "${n01:params:outdir}/samplesheet/samplesheet.csv",
                "contrasts": "contrasts.csv",
                "genome": "EB1",
            },
        },
    }
    for wf_id, params in overrides.items():
        workflows[wf_id]["params"].update(params)
    return workflows


def plan(path, resume=False, **options):
    return SimplePythonRunner(RunOptions(**options)).plan(from_file(path), resume=resume)


class TestOutDir:
    def test_default_is_next_to_the_config(self, project, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        steps = plan(write_config(project, two_steps()))
        assert {s.command.cwd for s in steps} == {project / "nf-meta-out"}

    def test_out_option_overrides(self, project, tmp_path):
        steps = plan(write_config(project, two_steps()), out_dir=tmp_path / "results")
        assert {s.command.cwd for s in steps} == {tmp_path / "results"}

    def test_shared_work_dir(self, project):
        steps = plan(write_config(project, two_steps()))
        work = {s.command.argv[s.command.argv.index("-w") + 1] for s in steps}
        assert work == {str(project / "nf-meta-out" / "work")}

    def test_per_step_nextflow_cache_dir(self, project):
        steps = plan(write_config(project, two_steps()))
        cache = [s.command.env["NXF_CACHE_DIR"] for s in steps]
        state = project / "nf-meta-out" / ".nf-meta" / "nextflow"
        assert cache == [str(state / "n01"), str(state / "n02")]

    def test_commands_do_not_depend_on_current_dir(self, project, tmp_path, monkeypatch):
        path = write_config(project, two_steps())
        monkeypatch.chdir(project)
        here = [(s.command.argv, s.command.params) for s in plan(path)]
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        assert [(s.command.argv, s.command.params) for s in plan(path)] == here

    def test_plan_writes_nothing(self, project):
        plan(write_config(project, two_steps()))
        assert not (project / "nf-meta-out").exists()


class TestInputPaths:
    def test_existing_relative_inputs_made_absolute(self, project):
        n01, n02 = plan(write_config(project, two_steps()))
        assert n01.command.params["input"] == str(project / "ids.csv")
        assert n02.command.params["contrasts"] == str(project / "contrasts.csv")

    def test_outdir_and_references_stay_relative(self, project):
        n01, n02 = plan(write_config(project, two_steps()))
        assert n01.command.params["outdir"] == "out_fetchngs"
        assert n02.command.params["input"] == "out_fetchngs/samplesheet/samplesheet.csv"

    def test_non_path_values_untouched(self, project):
        _, n02 = plan(write_config(project, two_steps()))
        assert n02.command.params["genome"] == "EB1"

    def test_urls_and_absolute_paths_untouched(self, project):
        cfg = two_steps(n01={"input": "s3://bucket/ids.csv"}, n02={"contrasts": "/data/c.csv"})
        n01, n02 = plan(write_config(project, cfg))
        assert n01.command.params["input"] == "s3://bucket/ids.csv"
        assert n02.command.params["contrasts"] == "/data/c.csv"

    def test_schema_path_format_made_absolute_even_if_missing(self, project, monkeypatch):
        with_path_format(monkeypatch, "input")
        n01, _ = plan(write_config(project, two_steps(n01={"input": "not_yet.csv"})))
        assert n01.command.params["input"] == str(project / "not_yet.csv")

    def test_reference_to_upstream_input_is_absolute(self, project):
        cfg = two_steps(n02={"contrasts": "${n01:params:input}"})
        _, n02 = plan(write_config(project, cfg))
        assert n02.command.params["contrasts"] == str(project / "ids.csv")

    def test_params_file_and_global_params_made_absolute(self, project):
        (project / "params.yaml").write_text("contrasts: contrasts.csv\n")
        cfg = two_steps()
        cfg["n01"]["params_file"] = "params.yaml"
        n01, _ = plan(write_config(project, cfg, globals={"params": {"extra": "ids.csv"}}))
        assert n01.command.params["contrasts"] == str(project / "contrasts.csv")
        assert n01.command.params["extra"] == str(project / "ids.csv")


class TestConfigPaths:
    def test_relative_config_file_resolves_against_config_folder(
        self, project, tmp_path, monkeypatch
    ):
        (project / "step.config").write_text("")
        cfg = two_steps()
        cfg["n01"]["config_file"] = "step.config"
        path = write_config(project, cfg)
        monkeypatch.chdir(tmp_path)
        g = from_file(path)
        assert g.get_workflow_by_id("n01").config_file == project / "step.config"
        assert g.project_dir == project

    def test_validated_graph_does_not_modify_input(self, project, monkeypatch):
        (project / "step.config").write_text("")
        monkeypatch.chdir(project)
        data = {
            "config_version": "0.3.0",
            "workflows": {
                "n01": {"name": "nf-core/fetchngs", "version": "1.12.0",
                        "config_file": "step.config"}
            },
        }
        validated_graph(data)
        assert data["workflows"]["n01"]["config_file"] == "step.config"


class TestStepKey:
    def _keys(self, path, **options):
        return {s.workflow.id: s.spec.state_dir.name for s in plan(path, **options)}

    def test_upstream_change_changes_downstream_key(self, project):
        before = self._keys(write_config(project, two_steps()))
        after = self._keys(write_config(project, two_steps(n01={"nf_core_pipeline": "rnaseq"})))
        assert before["n01"] != after["n01"]
        assert before["n02"] != after["n02"]

    def test_config_file_content_changes_key(self, project):
        cfg_file = project / "step.config"
        cfg_file.write_text("process.cpus = 1\n")
        cfg = two_steps()
        cfg["n02"]["config_file"] = "step.config"
        path = write_config(project, cfg)
        before = self._keys(path)
        cfg_file.write_text("process.cpus = 2\n")
        after = self._keys(path)
        assert before["n01"] == after["n01"]
        assert before["n02"] != after["n02"]

    def test_stub_changes_key(self, project):
        path = write_config(project, two_steps())
        assert self._keys(path) != self._keys(path, stub=True)

    def test_nextflow_cache_dir_survives_param_change(self, project):
        """A fixed step must find its last Nextflow run (P0 H10/H11)."""
        before = plan(write_config(project, two_steps()))[1]
        after = plan(write_config(project, two_steps(n02={"genome": "GRCh38"})))[1]
        assert before.spec.state_dir != after.spec.state_dir
        assert before.command.env == after.command.env

    def test_resume_skips_only_unchanged_steps(self, project):
        path = write_config(project, two_steps())
        runner = SimplePythonRunner(RunOptions())
        runner._stream_proc_out = MagicMock(return_value=(0, "out", ""))
        runner.run(from_file(path))

        changed = write_config(project, two_steps(n02={"genome": "GRCh38"}))
        skips = {s.workflow.id: s.skip for s in plan(changed, resume=True)}
        assert skips == {"n01": True, "n02": False}


class TestRemoteConfig:
    @pytest.fixture
    def serve(self, monkeypatch):
        def _serve(data: dict):
            response = MagicMock(text=yaml.safe_dump(data))
            monkeypatch.setattr("nf_meta.core.config.requests.get", lambda url, timeout: response)

        return _serve

    def test_relative_config_file_is_an_error(self, serve):
        serve({
            "config_version": "0.3.0",
            "workflows": {"n01": {"name": "nf-core/fetchngs", "version": "1.12.0",
                                  "config_file": "step.config"}},
        })
        with pytest.raises(ConfigValidationError, match="URL"):
            from_file("https://example.org/metaconfig.yaml")

    def test_out_dir_required(self, serve):
        serve({"config_version": "0.3.0", "workflows": two_steps()})
        g = from_file("https://example.org/metaconfig.yaml")
        assert g.project_dir is None
        with pytest.raises(NfMetaRunnerError, match="--out"):
            SimplePythonRunner(RunOptions()).plan(g)

    def test_relative_declared_path_param_is_an_error(self, serve, monkeypatch, tmp_path):
        with_path_format(monkeypatch, "input")
        serve({"config_version": "0.3.0", "workflows": two_steps()})
        g = from_file("https://example.org/metaconfig.yaml")
        with pytest.raises(NfMetaRunnerError, match="n01.input"):
            SimplePythonRunner(RunOptions(out_dir=tmp_path)).plan(g)
