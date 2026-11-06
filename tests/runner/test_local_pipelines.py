"""Local pipelines (`path:`): a pipeline folder used while developing it."""

import json

import pytest
import yaml

from nf_meta import NfPipeline
from nf_meta.core.config import dump_config, from_file
from nf_meta.core.errors import ConfigValidationError, Severity
from nf_meta.runner.python_runner import SimplePythonRunner
from nf_meta.runner.utils import RunOptions

SCHEMA = {
    "$defs": {
        "main": {
            "properties": {
                "input": {"type": "string", "format": "file-path"},
                "outdir": {"type": "string", "format": "directory-path"},
            },
            "required": ["outdir"],
        }
    }
}


@pytest.fixture
def project(tmp_path):
    project = tmp_path / "project"
    pipeline = tmp_path / "pipelines" / "connector"
    pipeline.mkdir(parents=True)
    project.mkdir()
    (pipeline / "main.nf").write_text("workflow { }\n")
    (pipeline / "nextflow_schema.json").write_text(json.dumps(SCHEMA))
    return project


def write_config(project, **step):
    data = {
        "config_version": "0.5.0",
        "steps": {"n01": {"name": "connector", "path": "../pipelines/connector", "params": {"outdir": "out"}, **step}},
    }
    path = project / "metapipeline.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


@pytest.fixture
def connectors(tmp_path):
    """A folder with two connectors, each its own pipeline, and a root schema
    that Nextflow doesn't read for them."""
    repo = tmp_path / "pipelines" / "connectors"
    a2b, c2d = repo / "connectors" / "a2b", repo / "connectors" / "c2d"
    a2b.mkdir(parents=True)
    c2d.mkdir(parents=True)
    (a2b / "main.nf").write_text("workflow { }\n")
    (c2d / "run.nf").write_text("workflow { }\n")
    root = {"$defs": {"main": {"properties": {"outdir": {"type": "string"}, "root_only": {"type": "string"}}}}}
    (repo / "nextflow_schema.json").write_text(json.dumps(root))
    a2b_schema = {"$defs": {"main": {"properties": {"outdir": {"type": "string"}, "a2b_only": {"type": "string"}}}}}
    (a2b / "nextflow_schema.json").write_text(json.dumps(a2b_schema))
    (c2d / "nextflow_schema.json").write_text(json.dumps(SCHEMA))
    project = tmp_path / "project"
    project.mkdir()
    return project


def write_connector_config(project, main_script, **params):
    return write_config(
        project, path="../pipelines/connectors", main_script=main_script, params={"outdir": "out", **params}
    )


class TestModel:
    def test_path_instead_of_url_and_version(self):
        assert NfPipeline(name="connector", path="../p").model_dump_config() == {"name": "connector", "path": "../p"}

    @pytest.mark.parametrize(
        ("fields", "field"),
        [
            ({"version": "1.0.0"}, "path"),
            ({"url": "https://github.com/org/repo"}, "url"),
        ],
    )
    def test_path_excludes_url_and_version(self, fields, field):
        with pytest.raises(ValueError) as exc:
            NfPipeline(name="connector", path="../p", **fields)
        assert [e["loc"] for e in exc.value.errors()] == [(field,)]

    def test_a_remote_pipeline_needs_a_version(self):
        with pytest.raises(ValueError, match="A version is needed"):
            NfPipeline(name="connector", url="https://github.com/org/repo")


class TestLoad:
    def test_path_is_kept_as_written(self, project):
        g = from_file(write_config(project))
        assert g.get_workflow_by_id("n01").path == "../pipelines/connector"
        assert dump_config(g)["steps"]["n01"]["path"] == "../pipelines/connector"

    def test_warns_that_the_config_is_not_reproducible(self, project):
        g = from_file(write_config(project), collect_errors=True)
        path_warnings = [d for d in g.warnings if d.field == "path"]
        assert [d.severity for d in path_warnings] == [Severity.WARNING]
        assert "can't be reproduced elsewhere" in path_warnings[0].message

    def test_params_are_checked_against_the_local_schema(self, project):
        with pytest.raises(ConfigValidationError) as exc:
            from_file(write_config(project, params={"outdir": "out", "bogus": 1}))
        assert [d.field for d in exc.value.errors] == ["params.bogus"]

    def test_a_missing_folder_is_an_error(self, project):
        with pytest.raises(ConfigValidationError) as exc:
            from_file(write_config(project, path="../pipelines/missing"))
        assert [(d.field, d.message.split(":")[0]) for d in exc.value.errors] == [("path", "No such folder")]

    def test_a_missing_main_script_is_an_error(self, project):
        with pytest.raises(ConfigValidationError) as exc:
            from_file(write_config(project, main_script="other.nf"))
        assert [d.field for d in exc.value.errors] == ["path"]


class TestRun:
    def plan(self, path):
        return SimplePythonRunner(RunOptions()).plan(from_file(path))

    def test_runs_the_folder_without_a_revision(self, project, tmp_path, monkeypatch):
        path = write_config(project)
        monkeypatch.chdir(tmp_path)
        (step,) = self.plan(path)
        argv = step.command.argv
        assert str((tmp_path / "pipelines" / "connector").resolve()) in argv
        assert "-r" not in argv

    def test_a_code_change_changes_the_step_key(self, project):
        path = write_config(project)
        before = self.plan(path)[0].spec.state_dir
        main = project.parent / "pipelines" / "connector" / "main.nf"
        main.write_text("workflow { println 'changed' }\n")
        assert self.plan(path)[0].spec.state_dir != before

    def test_run_state_in_the_folder_does_not_change_it(self, project):
        path = write_config(project)
        before = self.plan(path)[0].spec.state_dir
        work = project.parent / "pipelines" / "connector" / "work"
        work.mkdir()
        (work / "task.log").write_text("x")
        (project.parent / "pipelines" / "connector" / ".nextflow.log").write_text("x")
        assert self.plan(path)[0].spec.state_dir == before


class TestMainScript:
    """With `main_script`, the script's folder is the pipeline (as for Nextflow)."""

    def test_params_are_checked_against_the_script_folders_schema(self, connectors):
        from_file(write_connector_config(connectors, "connectors/a2b/main.nf", a2b_only="x"))
        with pytest.raises(ConfigValidationError) as exc:
            from_file(write_connector_config(connectors, "connectors/a2b/main.nf", root_only="x"))
        assert [d.field for d in exc.value.errors] == ["params.root_only"]

    def test_a_script_not_named_main_nf(self, connectors, tmp_path, monkeypatch):
        path = write_connector_config(connectors, "connectors/c2d/run.nf")
        monkeypatch.chdir(tmp_path)
        (step,) = SimplePythonRunner(RunOptions()).plan(from_file(path))
        script = (tmp_path / "pipelines" / "connectors" / "connectors" / "c2d" / "run.nf").resolve()
        assert step.command.argv[-1] == str(script)
        assert "-main-script" not in step.command.argv
