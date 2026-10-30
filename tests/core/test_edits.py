"""Edits: commands that work out their changes from the graph (plans/P6-editor-inputs.md)."""

import pytest

from nf_meta.core.edits import (
    DeleteInput,
    EditInput,
    SaveWorkflow,
    SetInputsStyle,
    declare_step_inputs_commands,
    delete_input_commands,
    edit_input_commands,
    referenced_steps,
    set_inputs_style_commands,
)
from nf_meta.core.errors import ConfigValidationError, GraphValidationError
from nf_meta.core.events import Transaction
from nf_meta.core.history import History
from nf_meta.core.inputs import Binding, InputDefinition

from .test_inputs import graph, pipeline, schema  # noqa: F401  (schema: autouse fixture)


def apply(g, commands, *args, **kwargs):
    """Work out an edit's commands from `g` and apply them as one history step."""
    History().execute(commands(g, *args, **kwargs), g)


def b(text):
    return Binding.parse(text)


def run(g, command):
    history = History()
    history.execute(command, g)
    return history


class TestEditInput:
    def test_create_in_params_writes_references_only(self):
        g = graph(pipeline("n01", input="a.csv"), pipeline("n02", input="ids.csv"))
        apply(
            g,
            edit_input_commands,
            "ids",
            InputDefinition(),
            (b("n01.input"), b("n02.input")),
            in_params=True,
            create=True,
        )
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:ids}"}
        assert g.get_workflow_by_id("n02").params == {"input": "${inputs:ids}"}
        assert g.inputs == {}
        assert g.input_bindings() == {"ids": (b("n01.input"), b("n02.input"))}

    def test_details_in_params_style_are_declared_without_bind(self):
        g = graph(pipeline("n01", input="a.csv"))
        apply(
            g,
            edit_input_commands,
            "ids",
            InputDefinition(description="Run ids"),
            (b("n01.input"),),
            in_params=True,
            create=True,
        )
        assert g.inputs == {"ids": InputDefinition(description="Run ids")}
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:ids}"}

    def test_switch_from_params_to_bind(self):
        g = graph(pipeline("n01", input="${inputs:ids}", outdir="out"))
        apply(g, edit_input_commands, "ids", InputDefinition(), (b("n01.input"),), in_params=False)
        assert g.get_workflow_by_id("n01").params == {"outdir": "out"}
        assert g.inputs == {"ids": InputDefinition(bind=("n01.input",))}

    def test_switch_from_bind_to_params(self):
        g = graph(pipeline("n01", input="a.csv"), inputs={"ids": {"bind": ["n01.input"], "description": "Run ids"}})
        apply(g, edit_input_commands, "ids", InputDefinition(description="Run ids"), (b("n01.input"),), in_params=True)
        assert g.inputs == {"ids": InputDefinition(description="Run ids")}
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:ids}"}

    def test_rebind_removes_old_references(self):
        g = graph(pipeline("n01", input="a.csv", genome="${inputs:g}"), pipeline("n02", input="b.csv"))
        apply(g, edit_input_commands, "g", InputDefinition(), (b("n02.genome"),), in_params=True)
        assert g.get_workflow_by_id("n01").params == {"input": "a.csv"}
        assert g.get_workflow_by_id("n02").params == {"input": "b.csv", "genome": "${inputs:g}"}

    def test_rename(self):
        g = graph(pipeline("n01", input="${inputs:ids}"), inputs={"ids": {"description": "Run ids"}})
        apply(
            g,
            edit_input_commands,
            "ids",
            InputDefinition(description="Run ids"),
            (b("n01.input"),),
            in_params=True,
            new_name="runs",
        )
        assert g.inputs == {"runs": InputDefinition(description="Run ids")}
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:runs}"}

    def test_unbound_input_is_declared(self):
        g = graph(pipeline("n01", input="${inputs:ids}"))
        apply(g, edit_input_commands, "extra", InputDefinition(), (), in_params=True, create=True)
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
            apply(g, edit_input_commands, name, InputDefinition(), (b("n01.input"),), in_params=True, **kwargs)

    def test_binding_to_missing_step(self):
        g = graph(pipeline("n01", input="a.csv"))
        with pytest.raises(ValueError, match="no step 'n09'"):
            apply(g, edit_input_commands, "ids", InputDefinition(), (b("n09.input"),), in_params=True, create=True)

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
        apply(g, delete_input_commands, "genome")
        assert g.inputs == {}
        assert g.get_workflow_by_id("n01").params == {"input": "ids.csv"}

    def test_required_param_left_without_value_is_refused(self):
        g = graph(pipeline("n01", input="${inputs:ids}"))
        with pytest.raises(ConfigValidationError):
            run(g, DeleteInput("ids"))
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:ids}"}

    def test_unknown(self):
        with pytest.raises(ValueError, match="does not exist"):
            apply(graph(pipeline("n01", input="a.csv")), delete_input_commands, "nope")


class TestSetInputsStyle:
    def graph(self):
        return graph(
            pipeline("n01", input="${inputs:ids}", outdir="out"),
            pipeline("n02", input="b.csv", genome="${inputs:genome}"),
            inputs={"genome": {"description": "g"}, "extra": {}, "outdir": {"bind": ["n02.outdir"]}},
        )

    def test_all_to_bind(self):
        g = self.graph()
        apply(g, set_inputs_style_commands, in_params=False)
        assert g.inputs == {
            "genome": InputDefinition(description="g", bind=("n02.genome",)),
            "extra": InputDefinition(),
            "outdir": InputDefinition(bind=("n02.outdir",)),
            "ids": InputDefinition(bind=("n01.input",)),
        }
        assert g.get_workflow_by_id("n01").params == {"outdir": "out"}

    def test_all_to_params(self):
        g = self.graph()
        apply(g, set_inputs_style_commands, in_params=True)
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
        apply(g, declare_step_inputs_commands, "n01")
        assert g.inputs == {"ids": InputDefinition(description="Run ids", bind=("n01.input", "n02.input"))}
        assert g.get_workflow_by_id("n01").params == {"outdir": "out"}
        assert g.get_workflow_by_id("n02").params is None

    def test_step_without_input_references(self):
        with pytest.raises(ValueError, match="uses no inputs"):
            apply(graph(pipeline("n01", input="a.csv")), declare_step_inputs_commands, "n01")


class TestCommands:
    def test_bulk_edit_of_one_step_changes_it_once(self):
        # two inputs fill params of the same step: both changes end up in one EditWorkflow
        g = graph(pipeline("n01", input="${inputs:ids}", genome="${inputs:genome}", outdir="out"))
        transaction = set_inputs_style_commands(g, in_params=False)
        assert [type(c).__name__ for c in transaction.commands] == ["EditWorkflow", "AddInput", "AddInput"]
        transaction.apply(g)
        assert g.get_workflow_by_id("n01").params == {"outdir": "out"}
        assert g.inputs == {
            "ids": InputDefinition(bind=("n01.input",)),
            "genome": InputDefinition(bind=("n01.genome",)),
        }

    def test_nothing_to_change_is_an_empty_transaction(self):
        g = graph(pipeline("n01", input="${inputs:ids}"))
        assert set_inputs_style_commands(g, in_params=True) == Transaction(())

    def test_changes_are_worked_out_when_applied(self):
        # the command reads the graph when it runs, not when it is created
        g = graph(pipeline("n01", input="a.csv"))
        command = EditInput("ids", InputDefinition(), (Binding.parse("n01.input"),), in_params=True, create=True)
        history = History()
        history.execute(command, g)
        assert g.get_workflow_by_id("n01").params == {"input": "${inputs:ids}"}
        history.undo(g)
        assert g.get_workflow_by_id("n01").params == {"input": "a.csv"}


class TestSaveWorkflow:
    def test_new_step_gets_edges_for_its_references(self):
        g = graph(pipeline("n01", input="a.csv", outdir="out1"), pipeline("n02", input="b.csv", outdir="out2"))
        new = pipeline("n03", input="${n01:params:outdir}/samplesheet.csv", outdir="${n02:params:outdir}/n03")
        run(g, SaveWorkflow(new, create=True))
        assert {(t.source, t.target) for t in g.get_transitions()} == {("n01", "n03"), ("n02", "n03")}

    def test_update_adds_missing_edges_and_keeps_existing(self):
        g = graph(pipeline("n01", input="a.csv", outdir="out1"), pipeline("n02", input="b.csv", outdir="out2"))
        run(g, SaveWorkflow(pipeline("n03", input="${n01:params:outdir}/x.csv"), create=True))
        run(g, SaveWorkflow(pipeline("n03", input="${n02:params:outdir}/x.csv"), create=False))
        assert {(t.source, t.target) for t in g.get_transitions()} == {("n01", "n03"), ("n02", "n03")}

    def test_reference_that_makes_a_cycle_changes_nothing(self):
        g = graph(pipeline("n01", input="a.csv", outdir="out1"))
        run(g, SaveWorkflow(pipeline("n02", input="${n01:params:outdir}/x.csv", outdir="out2"), create=True))
        with pytest.raises(GraphValidationError):
            run(g, SaveWorkflow(pipeline("n01", input="${n02:params:outdir}/x.csv", outdir="out1"), create=False))
        assert g.get_workflow_by_id("n01").params == {"input": "a.csv", "outdir": "out1"}
        assert [(t.source, t.target) for t in g.get_transitions()] == [("n01", "n02")]

    def test_one_undo_step(self):
        g = graph(pipeline("n01", input="a.csv", outdir="out1"))
        history = run(g, SaveWorkflow(pipeline("n02", input="${n01:params:outdir}/x.csv"), create=True))
        history.undo(g)
        assert [wf.id for wf in g.get_workflows()] == ["n01"]
        assert g.get_transitions() == []

    def test_referenced_steps(self):
        wf = pipeline(
            "n03", input="${n01:params:outdir}/${n02:params:x}", other="${n01:params:y}", own="${n03:params:z}"
        )
        assert referenced_steps(wf) == ["n01", "n02"]
