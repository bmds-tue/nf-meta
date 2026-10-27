"""Input values at run time: defaults only, until P4 adds prompts and flags."""

import pytest
import yaml

from nf_meta.core.config import from_file
from nf_meta.runner.errors import NfMetaRunnerError
from nf_meta.runner.python_runner import SimplePythonRunner
from nf_meta.runner.utils import RunOptions


def spec(type_, **kw):
    return {
        "type": type_,
        "required": False,
        "enum": None,
        "pattern": None,
        "format": None,
        "default": None,
        "hidden": False,
        **kw,
    }


SCHEMA = {
    "input": spec("string", format="file-path", exists=True),
    "outdir": spec("string", format="directory-path"),
    "genome": spec("string"),
    "count": spec("integer"),
}


@pytest.fixture(autouse=True)
def schema(monkeypatch):
    for target in (
        "nf_meta.core.dynamic_validation.get_pipeline_schema",
        "nf_meta.runner.paths.get_pipeline_schema",
    ):
        monkeypatch.setattr(target, lambda url, version: SCHEMA)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "ids.csv").write_text("SRR1\n")
    (tmp_path / "data").mkdir()
    return tmp_path


def config(project, inputs, params, extra_steps=None):
    workflows = {
        "n01": {"name": "nf-core/fetchngs", "version": "1.12.0", "params": {"outdir": "o", **params}},
        **(extra_steps or {}),
    }
    path = project / "metaconfig.yaml"
    path.write_text(yaml.safe_dump({"config_version": "0.4.0", "inputs": inputs, "workflows": workflows}))
    return path


def plan(path, **options):
    return SimplePythonRunner(RunOptions(**options)).plan(from_file(path))


def test_bound_default_filled_in_and_made_absolute(project):
    path = config(project, {"ids": {"bind": ["n01.input"], "default": "ids.csv"}}, {})
    assert plan(path)[0].command.params["input"] == str(project / "ids.csv")


def test_param_side_reference_keeps_type(project):
    path = config(
        project,
        {"n": {"default": 4}},
        {"input": "ids.csv", "count": "${inputs:n}"},
    )
    assert plan(path)[0].command.params["count"] == 4


def test_embedded_reference(project):
    path = config(
        project,
        {"dir": {"type": "string", "default": "data"}},
        {"input": "${inputs:dir}/../ids.csv"},
    )
    assert plan(path)[0].command.params["input"] == str(project / "data/../ids.csv")


def test_missing_value_is_an_error(project):
    path = config(project, {"genome": {"bind": ["n01.genome"]}}, {"input": "ids.csv"})
    with pytest.raises(NfMetaRunnerError, match="No value for input.*genome"):
        plan(path)


def test_default_that_must_exist_is_checked(project):
    path = config(project, {"ids": {"bind": ["n01.input"], "default": "nope.csv"}}, {})
    with pytest.raises(NfMetaRunnerError, match="nope.csv' does not exist"):
        plan(path)


def test_inputs_of_unselected_steps_not_needed(project):
    path = config(
        project,
        {"genome": {"bind": ["n02.genome"]}},
        {"input": "ids.csv"},
        extra_steps={
            "n02": {"name": "nf-core/rnaseq", "version": "3.14.0", "params": {"input": "ids.csv", "outdir": "o2"}}
        },
    )
    steps = plan(path, target="n01")
    assert [s.workflow.id for s in steps] == ["n01"]
