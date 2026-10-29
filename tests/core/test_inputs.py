"""Inputs (plans/P3-inputs-model.md)."""

import jsonschema
import pytest
import yaml
from pydantic import ValidationError

from nf_meta.core.config import dump_config, to_file, validated_graph
from nf_meta.core.errors import ConfigValidationError, Severity
from nf_meta.core.events import AddInput, DeleteInput, EditInput, SetInputsStyle
from nf_meta.core.graph import MetaworkflowGraph
from nf_meta.core.history import History
from nf_meta.core.inputs import (
    Binding,
    InputDefinition,
    effective_input,
    substitute_inputs,
)
from nf_meta.core.models import NfPipeline, Transition
from nf_meta.core.nf_param_validation import validate_params
from nf_meta.core.registry import _parse_nextflow_schema
from nf_meta.core.schema_export import generate_schema

# Shaped like nf-core/fetchngs 1.12.0's `input` param, as get_pipeline_schema returns it
FETCHNGS_INPUT = {
    "type": "string",
    "required": True,
    "enum": None,
    "pattern": r"^\S+\.(csv|tsv|txt)$",
    "format": "file-path",
    "default": None,
    "hidden": False,
    "exists": True,
    "mimetype": "text/csv",
    "schema": "assets/schema_input.json",
}


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
    "input": FETCHNGS_INPUT,
    "outdir": spec("string", format="directory-path"),
    "genome": spec("string"),
    "count": spec("integer", default=3),
    "threshold": spec("number", default=1.0),
}


@pytest.fixture(autouse=True)
def schema(monkeypatch):
    monkeypatch.setattr("nf_meta.core.dynamic_validation.get_pipeline_schema", lambda url, version: SCHEMA)


def pipeline(wf_id="n01", **params):
    return NfPipeline(id=wf_id, name="nf-core/fetchngs", version="1.12.0", params=params or None)


def graph(*workflows, inputs=None):
    g = MetaworkflowGraph()
    with g.deferred_validation():
        for name, definition in (inputs or {}).items():
            g.add_input(name, InputDefinition.from_config(definition))
        for wf in workflows:
            g.add_workflow(wf)
    g.pop_events()
    return g


# ---------------------------------------------------------------------------
# InputDefinition
# ---------------------------------------------------------------------------


class TestDefinition:
    def test_bind_accepts_single_string(self):
        assert InputDefinition.from_config({"bind": "n01.input"}).bind == ("n01.input",)

    def test_bind_syntax_checked(self):
        with pytest.raises(ValidationError):
            InputDefinition.from_config({"bind": ["n01"]})

    def test_unknown_keyword_rejected(self):
        with pytest.raises(ValidationError):
            InputDefinition.from_config({"widget": "slider"})

    def test_none_entry_is_empty_input(self):
        assert InputDefinition.from_config(None) == InputDefinition()

    def test_config_round_trip(self):
        data = {
            "bind": ["n01.input"],
            "default": "ids.csv",
            "type": "string",
            "format": "file-path",
            "schema": "assets/s.json",
            "enum": ["a", "b"],
        }
        assert InputDefinition.from_config(data).model_dump_config() == data


# ---------------------------------------------------------------------------
# Effective schema
# ---------------------------------------------------------------------------


class TestEffectiveInput:
    b1, b2 = Binding("n01", "input"), Binding("n02", "input")

    def test_inherits_from_bound_param(self):
        inp, diags = effective_input("ids", InputDefinition(), (self.b1,), {self.b1: FETCHNGS_INPUT})
        assert inp.schema["format"] == "file-path"
        assert inp.schema["exists"] is True
        assert inp.is_path
        assert diags == []

    def test_own_keywords_narrow(self):
        inp, _ = effective_input("g", InputDefinition(enum=("EB1", "GRCh38")), (self.b1,), {self.b1: spec("string")})
        assert inp.schema == {"type": "string", "enum": ["EB1", "GRCh38"]}

    def test_input_default_overrides_schema_default(self):
        inp, _ = effective_input("c", InputDefinition(default=5), (self.b1,), {self.b1: spec("integer", default=3)})
        assert inp.default == 5

    def test_schema_default_used_without_own(self):
        inp, _ = effective_input("c", InputDefinition(), (self.b1,), {self.b1: spec("integer", default=3)})
        assert inp.default == 3

    def test_conflicting_bindings_error(self):
        _, diags = effective_input(
            "x",
            InputDefinition(),
            (self.b1, self.b2),
            {self.b1: spec("string"), self.b2: spec("integer")},
        )
        assert any(d.severity == Severity.ERROR and "conflicting types" in d.message for d in diags)

    def test_format_and_none_compatible(self):
        _, diags = effective_input(
            "x",
            InputDefinition(),
            (self.b1, self.b2),
            {self.b1: spec("string", format="file-path"), self.b2: spec("string")},
        )
        assert diags == []

    def test_type_contradiction_error(self):
        _, diags = effective_input("x", InputDefinition(type="integer"), (self.b1,), {self.b1: spec("string")})
        assert [d.yaml_path for d in diags] == ["inputs.x.type"]

    def test_no_type_warns_and_assumes_string(self):
        inp, diags = effective_input("x", InputDefinition(), (), {})
        assert inp.schema["type"] == "string"
        assert [d.severity for d in diags] == [Severity.WARNING]

    def test_invalid_default_error(self):
        _, diags = effective_input("g", InputDefinition(enum=("a",), default="b"), (), {})
        assert [d.yaml_path for d in diags if d.severity == Severity.ERROR] == ["inputs.g.default"]

    def test_module_file_type_becomes_file_path(self):
        inp, _ = effective_input("r", InputDefinition(), (self.b1,), {self.b1: {"type": "file", "required": True}})
        assert inp.schema == {"type": "string", "format": "file-path"}


class TestValidateValue:
    def _input(self, **schema):
        inp, _ = effective_input("x", InputDefinition(**schema), (), {})
        return inp

    def test_type(self):
        assert self._input(type="integer").validate("3")
        assert not self._input(type="integer").validate(3)

    def test_pattern_and_bounds(self):
        assert self._input(type="string", pattern=r"\.csv$").validate("a.tsv")
        assert self._input(type="number", minimum=0).validate(-1)
        assert not self._input(type="number", minimum=0, maximum=1).validate(0.5)

    def test_missing_default_path_is_a_warning(self, tmp_path):
        inp, diags = effective_input(
            "ids",
            InputDefinition(default="missing.csv", type="string", format="file-path", exists=True),
            (),
            {},
            project_dir=tmp_path,
        )
        assert [(d.severity, d.yaml_path) for d in diags] == [(Severity.WARNING, "inputs.ids.default")]

    def test_exists_relative_to_project_dir(self, tmp_path):
        (tmp_path / "ids.csv").write_text("")
        inp = self._input(type="string", format="file-path", exists=True)
        assert not inp.validate("ids.csv", project_dir=tmp_path)
        assert inp.validate("missing.csv", project_dir=tmp_path)


def test_substitute_inputs():
    params = {"a": "${inputs:n}", "c": "keep"}
    result = substitute_inputs(params, {"bound": "n"}, {"n": 5})
    assert result == {"a": 5, "c": "keep", "bound": 5}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


class TestGraph:
    def test_bindings_from_both_directions(self):
        g = graph(
            pipeline("n01", outdir="o"),
            pipeline("n02", input="a.csv", outdir="o", genome="${inputs:genome}"),
            inputs={"ids": {"bind": "n01.input"}, "genome": {}},
        )
        assert g.input_bindings() == {
            "ids": (Binding("n01", "input"),),
            "genome": (Binding("n02", "genome"),),
        }

    def test_bind_satisfies_required_param(self):
        g = graph(pipeline("n01", outdir="o"), inputs={"ids": {"bind": "n01.input"}})
        assert g.with_input_placeholders(g.get_workflow_by_id("n01")).params["input"] == "${inputs:ids}"

    def test_required_param_without_value_or_binding_still_errors(self):
        with pytest.raises(ConfigValidationError, match="Required parameter 'input'"):
            graph(pipeline("n01", outdir="o"))

    def test_input_ref_skips_type_check(self):
        assert validate_params({"count": "${inputs:c}"}, SCHEMA, pipeline_id="n01", skip_required=True) == []

    def test_reference_to_undeclared_input_declares_it(self):
        g = graph(pipeline("n01", input="${inputs:ids}", outdir="o"))
        assert g.inputs == {}
        assert g.all_inputs() == {"ids": InputDefinition()}
        assert g.input_bindings() == {"ids": (Binding("n01", "input"),)}

    def test_implicit_input_inherits_the_param_schema(self):
        g = graph(pipeline("n01", input="${inputs:ids}", outdir="o"))
        inputs, _ = g.effective_inputs()
        assert inputs["ids"].schema["type"] == "string"

    def test_params_share_an_implicit_input(self):
        g = graph(
            pipeline("n01", input="${inputs:ids}", outdir="o"),
            pipeline("n02", input="${inputs:ids}", outdir="p"),
        )
        assert g.input_bindings()["ids"] == (Binding("n01", "input"), Binding("n02", "input"))

    def test_declaration_without_bind_adds_metadata(self):
        g = graph(
            pipeline("n01", input="${inputs:ids}", outdir="o"),
            inputs={"ids": {"description": "Accessions", "default": "ids.csv"}},
        )
        assert g.all_inputs()["ids"].description == "Accessions"
        assert not [d for d in g.input_diagnostics() if "not used" in d.message]

    def test_bind_and_reference_for_one_input_rejected(self):
        with pytest.raises(ConfigValidationError, match="bind it in one place"):
            graph(
                pipeline("n01", input="${inputs:ids}", outdir="o"),
                inputs={"ids": {"bind": "n01.input"}},
            )

    def test_bind_and_reference_on_different_params_rejected(self):
        with pytest.raises(ConfigValidationError, match="bind it in one place"):
            graph(
                pipeline("n01", input="${inputs:ids}", outdir="o", genome="x"),
                inputs={"ids": {"bind": "n01.genome"}},
            )

    def test_implicit_input_problems_point_at_the_param(self, monkeypatch):
        from nf_meta.core.registry import PipelineSchemaError

        def unavailable(url, version):
            raise PipelineSchemaError("offline")

        g = graph(pipeline("n01", input="${inputs:ids}", outdir="o"))
        monkeypatch.setattr("nf_meta.core.dynamic_validation.get_pipeline_schema", unavailable)
        _, diagnostics = g.effective_inputs()
        assert {d.yaml_path for d in diagnostics} == {"workflows.n01.params.input"}

    def test_partial_reference_declares_no_input(self):
        g = MetaworkflowGraph()
        with pytest.raises(ConfigValidationError), g.deferred_validation():
            g.add_workflow(pipeline("n01", input="${inputs:dir}/x.csv", outdir="o"))
            assert g.all_inputs() == {}  # checked before validation runs on exit

    def test_partial_reference_rejected(self):
        with pytest.raises(ConfigValidationError, match=r"'\$\{inputs:dir\}' must be the whole value of 'input'"):
            graph(pipeline("n01", input="${inputs:dir}/x.csv", outdir="o"))

    def test_bind_to_missing_step_rejected_and_rolled_back(self):
        g = graph(pipeline("n01", input="ids.csv", outdir="o"))
        with pytest.raises(ConfigValidationError, match="no step 'n09'"):
            g.add_input("x", InputDefinition(bind=("n09.input",)))
        assert g.inputs == {}

    def test_bind_to_unknown_param_rejected(self):
        g = graph(pipeline("n01", input="ids.csv", outdir="o"))
        with pytest.raises(ConfigValidationError, match="no param 'nope'"):
            g.add_input("x", InputDefinition(bind=("n01.nope",)))

    def test_param_bound_twice_rejected(self):
        g = graph(pipeline("n01", input="${inputs:a}", outdir="o"), inputs={"a": {"default": "x.csv"}})
        with pytest.raises(ConfigValidationError, match="more than one input"):
            g.add_input("b", InputDefinition(bind=("n01.input",)))

    def test_unused_input_is_a_warning(self):
        g = graph(pipeline("n01", input="ids.csv", outdir="o"), inputs={"spare": {"type": "string"}})
        diags = g.input_diagnostics()
        assert [(d.severity, d.yaml_path) for d in diags] == [(Severity.WARNING, "inputs.spare")]

    def test_bound_param_with_own_value_is_a_warning(self):
        g = graph(pipeline("n01", input="ids.csv", outdir="o"), inputs={"ids": {"bind": "n01.input"}})
        assert [d.severity for d in g.input_diagnostics()] == [Severity.WARNING]

    def test_removing_a_referenced_declaration_leaves_an_implicit_input(self):
        g = graph(pipeline("n01", input="${inputs:ids}", outdir="o"), inputs={"ids": {"default": "a.csv"}})
        g.remove_input("ids")
        assert g.inputs == {}
        assert g.all_inputs() == {"ids": InputDefinition()}

    def test_update_rolls_back_on_error(self):
        g = graph(pipeline("n01", input="ids.csv", outdir="o"), inputs={"g": {"bind": "n01.genome"}})
        before = g.inputs["g"]
        with pytest.raises(ConfigValidationError):
            g.update_input("g", InputDefinition(bind=("n01.genome",), type="integer"))
        assert g.inputs["g"] is before

    def test_input_reference_needs_config_version_0_4(self):
        data = {
            "config_version": "0.3.0",
            "workflows": {
                "n01": {"name": "nf-core/fetchngs", "version": "1.12.0", "params": {"input": "${inputs:ids}"}}
            },
        }
        with pytest.raises(ConfigValidationError, match="needs config_version 0.4.0"):
            validated_graph(data)

    def test_adding_a_step_with_an_input_reference_raises_config_version(self):
        g = graph(pipeline("n01", input="ids.csv", outdir="o"))
        g.config_version = "0.3.0"
        g.add_workflow(pipeline("n02", input="${inputs:ids}", outdir="p"))
        assert g.config_version == "0.4.0"

    def test_add_input_raises_config_version(self):
        g = graph(pipeline("n01", input="ids.csv", outdir="o"))
        g.config_version = "0.3.0"
        g.add_input("x", InputDefinition(bind=("n01.genome",)))
        assert g.config_version == "0.4.0"

    def test_undo_add_input(self):
        g = graph(pipeline("n01", input="ids.csv", outdir="o"))
        history = History()
        history.execute(AddInput("x", InputDefinition(bind=("n01.genome",))), g)
        assert "x" in g.inputs
        history.undo(g)
        assert g.inputs == {}
        history.redo(g)
        assert "x" in g.inputs

    def test_inputs_is_a_reserved_step_id(self):
        with pytest.raises(ValidationError, match="reserved"):
            NfPipeline(id="inputs", name="nf-core/fetchngs", version="1.12.0")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


CONFIG = {
    "config_version": "0.4.0",
    "inputs": {
        "ids": {"bind": ["n01.input"], "default": "ids.csv"},
        "genome": {"enum": ["EB1", "GRCh38"], "default": "EB1"},
    },
    "workflows": {
        "n01": {
            "name": "nf-core/fetchngs",
            "version": "1.12.0",
            "params": {"outdir": "o", "genome": "${inputs:genome}"},
        }
    },
}


class TestConfig:
    def test_round_trip(self):
        dumped = dump_config(validated_graph(CONFIG))
        assert dumped["inputs"] == CONFIG["inputs"]
        assert dumped["workflows"]["n01"]["params"] == CONFIG["workflows"]["n01"]["params"]

    def test_dump_matches_json_schema(self):
        jsonschema.validate(dump_config(validated_graph(CONFIG)), generate_schema())

    def test_inputs_need_config_version_0_4(self):
        with pytest.raises(ConfigValidationError, match="0.4.0"):
            validated_graph({**CONFIG, "config_version": "0.3.0"})

    @pytest.mark.parametrize("collect_errors", [False, True])
    def test_malformed_entry_reported_with_path(self, collect_errors):
        data = {**CONFIG, "inputs": {**CONFIG["inputs"], "bad": {"widget": 1}}}
        with pytest.raises(ConfigValidationError) as exc:
            validated_graph(data, collect_errors=collect_errors)
        assert any(d.yaml_path.startswith("inputs.bad") for d in exc.value.errors)

    def test_collect_errors_reports_input_problems(self):
        data = yaml.safe_load(yaml.safe_dump(CONFIG))
        data["inputs"]["ids"]["bind"] = ["n09.input"]
        with pytest.raises(ConfigValidationError) as exc:
            validated_graph(data, collect_errors=True)
        assert any(d.yaml_path == "inputs.ids.bind" for d in exc.value.errors)


def test_schema_extraction_keeps_input_keywords():
    parsed = _parse_nextflow_schema(
        {
            "properties": {
                "input": {
                    "type": "string",
                    "format": "file-path",
                    "exists": True,
                    "mimetype": "text/csv",
                    "schema": "a.json",
                }
            }
        }
    )
    assert parsed["input"]["exists"] is True
    assert parsed["input"]["mimetype"] == "text/csv"
    assert parsed["input"]["schema"] == "a.json"


# ---------------------------------------------------------------------------
# Editing inputs as a whole (edit_input / delete_input / declare_step_inputs)
# ---------------------------------------------------------------------------


def b(text):
    return Binding.parse(text)


def run(g, command):
    history = History()
    history.execute(command, g)
    return history


class TestEditInput:
    def test_create_in_params_writes_references_only(self):
        g = graph(pipeline("n01", input="a.csv"), pipeline("n02", input="ids.csv"))
        g.edit_input("ids", InputDefinition(), (b("n01.input"), b("n02.input")), in_params=True, create=True)
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:ids}"}
        assert g.get_workflow_by_id("n02").params == {"input": "${inputs:ids}"}
        assert g.inputs == {}
        assert g.input_bindings() == {"ids": (b("n01.input"), b("n02.input"))}

    def test_details_in_params_style_are_declared_without_bind(self):
        g = graph(pipeline("n01", input="a.csv"))
        g.edit_input("ids", InputDefinition(description="Run ids"), (b("n01.input"),), in_params=True, create=True)
        assert g.inputs == {"ids": InputDefinition(description="Run ids")}
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:ids}"}

    def test_switch_from_params_to_bind(self):
        g = graph(pipeline("n01", input="${inputs:ids}", outdir="out"))
        g.edit_input("ids", InputDefinition(), (b("n01.input"),), in_params=False)
        assert g.get_workflow_by_id("n01").params == {"outdir": "out"}
        assert g.inputs == {"ids": InputDefinition(bind=("n01.input",))}

    def test_switch_from_bind_to_params(self):
        g = graph(pipeline("n01", input="a.csv"), inputs={"ids": {"bind": ["n01.input"], "description": "Run ids"}})
        g.edit_input("ids", InputDefinition(description="Run ids"), (b("n01.input"),), in_params=True)
        assert g.inputs == {"ids": InputDefinition(description="Run ids")}
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:ids}"}

    def test_rebind_removes_old_references(self):
        g = graph(pipeline("n01", input="a.csv", genome="${inputs:g}"), pipeline("n02", input="b.csv"))
        g.edit_input("g", InputDefinition(), (b("n02.genome"),), in_params=True)
        assert g.get_workflow_by_id("n01").params == {"input": "a.csv"}
        assert g.get_workflow_by_id("n02").params == {"input": "b.csv", "genome": "${inputs:g}"}

    def test_rename(self):
        g = graph(pipeline("n01", input="${inputs:ids}"), inputs={"ids": {"description": "Run ids"}})
        g.edit_input("ids", InputDefinition(description="Run ids"), (b("n01.input"),), in_params=True, new_name="runs")
        assert g.inputs == {"runs": InputDefinition(description="Run ids")}
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:runs}"}

    def test_unbound_input_is_declared(self):
        g = graph(pipeline("n01", input="${inputs:ids}"))
        g.edit_input("extra", InputDefinition(), (), in_params=True, create=True)
        assert "extra" in g.inputs

    @pytest.mark.parametrize(
        ("name", "kwargs", "message"),
        [
            ("ids", {"create": True}, "already exists"),
            ("nope", {}, "does not exist"),
            ("ids", {"new_name": "genome"}, "already exists"),
            ("ids", {"new_name": "a b"}, "Invalid input name"),
        ],
    )
    def test_invalid_names(self, name, kwargs, message):
        g = graph(pipeline("n01", input="${inputs:ids}", genome="${inputs:genome}"))
        with pytest.raises(ValueError, match=message):
            g.edit_input(name, InputDefinition(), (b("n01.input"),), in_params=True, **kwargs)

    def test_binding_to_missing_step(self):
        g = graph(pipeline("n01", input="a.csv"))
        with pytest.raises(ValueError, match="no step 'n09'"):
            g.edit_input("ids", InputDefinition(), (b("n09.input"),), in_params=True, create=True)

    def test_invalid_result_rolls_back_and_undo_restores(self):
        g = graph(pipeline("n01", input="${inputs:ids}"))
        history = History()
        with pytest.raises(ConfigValidationError):
            history.execute(EditInput("ids", InputDefinition(type="integer"), (b("n01.input"),), in_params=False), g)
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:ids}"}
        assert g.inputs == {}

    def test_one_undo_step(self):
        g = graph(pipeline("n01", input="${inputs:ids}"))
        history = run(g, EditInput("ids", InputDefinition(description="d"), (b("n01.input"),), in_params=False))
        assert g.inputs["ids"].bind == ("n01.input",)
        history.undo(g)
        assert g.inputs == {}
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:ids}"}


class TestDeleteInput:
    def test_removes_references_and_declaration(self):
        g = graph(pipeline("n01", input="ids.csv", genome="${inputs:genome}"), inputs={"genome": {"description": "g"}})
        g.delete_input("genome")
        assert g.inputs == {}
        assert g.get_workflow_by_id("n01").params == {"input": "ids.csv"}

    def test_required_param_left_without_value_is_refused(self):
        g = graph(pipeline("n01", input="${inputs:ids}"))
        with pytest.raises(ConfigValidationError):
            run(g, DeleteInput("ids"))
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:ids}"}

    def test_unknown(self):
        with pytest.raises(ValueError, match="does not exist"):
            graph(pipeline("n01", input="a.csv")).delete_input("nope")


class TestSetInputsStyle:
    def graph(self):
        return graph(
            pipeline("n01", input="${inputs:ids}", outdir="out"),
            pipeline("n02", input="b.csv", genome="${inputs:genome}"),
            inputs={"genome": {"description": "g"}, "extra": {}, "outdir": {"bind": ["n02.outdir"]}},
        )

    def test_all_to_bind(self):
        g = self.graph()
        g.set_inputs_style(in_params=False)
        assert g.inputs == {
            "genome": InputDefinition(description="g", bind=("n02.genome",)),
            "extra": InputDefinition(),
            "outdir": InputDefinition(bind=("n02.outdir",)),
            "ids": InputDefinition(bind=("n01.input",)),
        }
        assert g.get_workflow_by_id("n01").params == {"outdir": "out"}

    def test_all_to_params(self):
        g = self.graph()
        g.set_inputs_style(in_params=True)
        assert g.inputs == {"genome": InputDefinition(description="g"), "extra": InputDefinition()}
        assert g.get_workflow_by_id("n02").params == {
            "input": "b.csv",
            "genome": "${inputs:genome}",
            "outdir": "${inputs:outdir}",
        }

    def test_one_undo_step(self):
        g = self.graph()
        history = run(g, SetInputsStyle(in_params=False))
        history.undo(g)
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:ids}", "outdir": "out"}
        assert "ids" not in g.inputs


class TestDeclareStepInputs:
    def test_moves_a_steps_inputs_to_the_inputs_section(self):
        g = graph(
            pipeline("n01", input="${inputs:ids}", outdir="out"),
            pipeline("n02", input="${inputs:ids}"),
            inputs={"ids": {"description": "Run ids"}},
        )
        g.declare_step_inputs("n01")
        assert g.inputs == {"ids": InputDefinition(description="Run ids", bind=("n01.input", "n02.input"))}
        assert g.get_workflow_by_id("n01").params == {"outdir": "out"}
        assert g.get_workflow_by_id("n02").params is None

    def test_step_without_input_references(self):
        with pytest.raises(ValueError, match="uses no inputs"):
            graph(pipeline("n01", input="a.csv")).declare_step_inputs("n01")


def test_bind_and_from_are_written_in_flow_style(tmp_path):
    g = graph(
        pipeline("n01", input="a.csv"),
        pipeline("n02", input="b.csv"),
        inputs={"ids": {"bind": ["n01.input", "n02.input"], "description": "Run ids"}},
    )
    g.add_transition(Transition(source="n01", target="n02"))
    path = tmp_path / "mp.yaml"
    to_file(g, path)
    text = path.read_text()
    assert "bind: [n01.input, n02.input]" in text
    assert "from: [n01]" in text
    data = yaml.safe_load(text)
    assert data["inputs"]["ids"] == {"bind": ["n01.input", "n02.input"], "description": "Run ids"}
    assert data["workflows"]["n02"]["from"] == ["n01"]
