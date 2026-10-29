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
    monkeypatch.setattr("nf_meta.core.dynamic_validation.get_pipeline_schema", lambda url, version: SCHEMA)


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


def test_implicit_input_given_at_run(project):
    path = config(project, {}, {"input": "${inputs:ids}"})
    given = str(project / "ids.csv")
    assert plan(path, inputs={"ids": given})[0].command.params["input"] == given


def test_implicit_input_missing_is_an_error(project):
    path = config(project, {}, {"input": "${inputs:ids}"})
    with pytest.raises(NfMetaRunnerError, match=r"Missing values:\n  ids"):
        plan(path)


def test_implicit_input_in_a_dry_run_is_a_placeholder(project):
    path = config(project, {}, {"input": "${inputs:ids}"})
    steps = SimplePythonRunner(RunOptions()).plan(from_file(path), dry_run=True)
    assert steps[0].command.params["input"] == "<input: ids>"


def test_missing_value_is_an_error(project):
    path = config(project, {"genome": {"bind": ["n01.genome"]}}, {"input": "ids.csv"})
    with pytest.raises(NfMetaRunnerError, match=r"Missing values:\n  genome \(input\)"):
        plan(path)


def test_default_that_must_exist_is_checked(project):
    path = config(project, {"ids": {"bind": ["n01.input"], "default": "nope.csv"}}, {})
    with pytest.raises(NfMetaRunnerError, match="nope.csv': does not exist"):
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


# ---------------------------------------------------------------------------
# Modes and given values (P4)
# ---------------------------------------------------------------------------


def _runner(**options):
    from unittest.mock import MagicMock

    runner = SimplePythonRunner(RunOptions(**options))
    runner._stream_proc_out = MagicMock(return_value=(0, "out", ""))
    return runner


def test_given_value_replaces_default_and_changes_the_step_key(project):
    path = config(project, {"genome": {"bind": ["n01.genome"], "default": "EB1"}}, {"input": "ids.csv"})
    default = plan(path)[0]
    given = plan(path, inputs={"genome": "GRCh38"})[0]
    assert given.command.params["genome"] == "GRCh38"
    assert given.spec.state_dir != default.spec.state_dir


def test_reproduce_uses_the_values_of_the_last_run(project):
    path = config(project, {"genome": {"bind": ["n01.genome"], "default": "EB1"}}, {"input": "ids.csv"})
    _runner(inputs={"genome": "GRCh38"}).run(from_file(path))
    again = plan(path, input_mode="reproduce")[0]
    assert again.command.params["genome"] == "GRCh38"


def test_reproduce_without_a_recorded_run_fails(project):
    path = config(project, {"genome": {"bind": ["n01.genome"], "default": "EB1"}}, {"input": "ids.csv"})
    with pytest.raises(NfMetaRunnerError, match="previous run"):
        plan(path, input_mode="reproduce")


def test_dry_run_lists_missing_values(project):
    path = config(project, {"genome": {"bind": ["n01.genome"]}}, {"input": "ids.csv"})
    from nf_meta.runner import plan_metapipeline

    result = plan_metapipeline(from_file(path), RunOptions())
    assert result.missing == ["genome"]
    assert result[0].command.params["genome"] == "<input: genome>"


def test_prompted_value_used(project):
    path = config(project, {"genome": {"bind": ["n01.genome"], "enum": ["EB1", "GRCh38"]}}, {"input": "ids.csv"})
    step = plan(path, input_mode="prompt", prompter=lambda inp, problem: "GRCh38")[0]
    assert step.command.params["genome"] == "GRCh38"
