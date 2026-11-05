"""Collecting a run's values (plans/P4-run-input-resolution.md)."""

import pytest

from nf_meta.core.inputs import Input
from nf_meta.runner.collect import InputMode, Request, coerce, collect, is_placeholder
from nf_meta.runner.errors import NfMetaRunnerError


def inp(name, **schema):
    return Input(name=name, schema={"type": "string", **schema})


def test_given_beats_fallback():
    got = collect([Request(inp("a"), fallback="default")], {"a": "given"}, InputMode.FAIL)
    assert got.values == {"a": "given"}


def test_fallback_used_without_given():
    got = collect([Request(inp("a"), fallback="default")], {}, InputMode.FAIL)
    assert got.values == {"a": "default"}


def test_fail_mode_lists_every_missing_value():
    requests = [Request(inp("a")), Request(inp("n03.matrix"), is_reference=True)]
    with pytest.raises(NfMetaRunnerError) as exc:
        collect(requests, {}, InputMode.FAIL)
    assert "a (input)" in exc.value.message
    assert "n03.matrix (reference to a step outside this run)" in exc.value.message


def test_dry_run_uses_placeholders_instead_of_failing():
    got = collect([Request(inp("a"))], {}, InputMode.FAIL, dry_run=True)
    assert got.values == {"a": "<input: a>"}
    assert is_placeholder(got.values["a"])
    assert [r.name for r in got.missing] == ["a"]


def test_prompt_mode_asks_and_reasks_until_valid():
    answers = iter(["x", "B"])
    problems = []

    def prompter(i, problem):
        problems.append(problem)
        return next(answers)

    got = collect([Request(inp("g", enum=["A", "B"]))], {}, InputMode.PROMPT, prompter=prompter)
    assert got.values == {"g": "B"}
    assert problems == [None, "'x': must be one of A, B"]


def test_prompt_mode_asks_even_in_a_dry_run():
    got = collect([Request(inp("a"))], {}, InputMode.PROMPT, prompter=lambda i, p: "typed", dry_run=True)
    assert got.values == {"a": "typed"}
    assert got.missing == []


def test_prompt_only_for_missing_values():
    asked = []
    collect(
        [Request(inp("a"), fallback="d"), Request(inp("b"))],
        {},
        InputMode.PROMPT,
        prompter=lambda i, p: asked.append(i.name) or "v",
    )
    assert asked == ["b"]


def test_unknown_given_name_rejected():
    with pytest.raises(NfMetaRunnerError, match="Unknown input"):
        collect([Request(inp("a"))], {"b": "x"}, InputMode.FAIL)


def test_reproduce_rejects_given_values():
    with pytest.raises(NfMetaRunnerError, match="reproduce"):
        collect([Request(inp("a"), fallback="x")], {"a": "y"}, InputMode.REPRODUCE)


def test_reproduce_missing_value_hint():
    with pytest.raises(NfMetaRunnerError, match="previous run"):
        collect([Request(inp("a"))], {}, InputMode.REPRODUCE)


def test_invalid_values_reported_together():
    requests = [Request(inp("n", type="integer")), Request(inp("g", enum=["A"]))]
    with pytest.raises(NfMetaRunnerError) as exc:
        collect(requests, {"n": "x", "g": "B"}, InputMode.FAIL)
    assert "n = 'x': not a valid integer" in exc.value.message
    assert "g = 'B': must be one of A" in exc.value.message


def test_given_relative_path_is_relative_to_the_current_dir(tmp_path):
    (tmp_path / "ids.csv").write_text("")
    request = Request(inp("ids", format="file-path", exists=True))
    got = collect([request], {"ids": "ids.csv"}, InputMode.FAIL, given_dir=tmp_path)
    assert got.values == {"ids": str(tmp_path / "ids.csv")}


def test_cached_reference_values_are_not_path_checked():
    request = Request(inp("n02.input", format="file-path", exists=True), fallback="out/x.csv", is_reference=True)
    assert collect([request], {}, InputMode.FAIL).values == {"n02.input": "out/x.csv"}


@pytest.mark.parametrize(
    ("type_", "raw", "expected"),
    [
        ("integer", "3", 3),
        ("number", "1.5", 1.5),
        ("boolean", "yes", True),
        ("boolean", "False", False),
        ("integer", "x", "x"),
        ("string", "3", "3"),
    ],
)
def test_coerce(type_, raw, expected):
    assert coerce(inp("v", type=type_), raw) == expected


def test_value_checked_as_typed_then_made_absolute(tmp_path):
    request = Request(inp("ids", format="file-path", pattern=r"\.csv$", exists=True))
    with pytest.raises(NfMetaRunnerError) as exc:
        collect([request], {"ids": "bar"}, InputMode.FAIL, given_dir=tmp_path)
    assert exc.value.message.splitlines()[1] == "  ids = 'bar': must match \\.csv$; does not exist"


def test_several_values_in_one_input_rejected():
    requests = [Request(inp("a")), Request(inp("b"))]
    with pytest.raises(NfMetaRunnerError, match="pass --input once per value"):
        collect(requests, {"a": "x,b=y"}, InputMode.FAIL)


def test_commas_in_a_value_are_fine():
    got = collect([Request(inp("cols"))], {"cols": "sample,condition"}, InputMode.FAIL)
    assert got.values == {"cols": "sample,condition"}
