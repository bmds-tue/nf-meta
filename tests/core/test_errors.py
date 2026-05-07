import pytest

from nf_meta.core.models import Reference, ParamsReference
from nf_meta.core.errors import (
    GraphValidationError,
    WorkflowReferenceError,
    WorkflowReferenceErrors,
    SessionCommandError,
    format_errors_for_cli,
)


def _make_ref(source_wf_id="wf_a", target_wf_id="wf_b"):
    return ParamsReference(
        name="${wf_b:params:outdir}",
        source_wf_id=source_wf_id,
        target_wf_id=target_wf_id,
        source_key="input",
        target_key="outdir",
    )


# ---------------------------------------------------------------------------
# SessionCommandError.from_exception
# ---------------------------------------------------------------------------

class TestSessionCommandError:
    def test_from_single_reference_error(self):
        ref = _make_ref()
        exc = WorkflowReferenceError(reference=ref, message="unknown workflow")
        err = SessionCommandError.from_exception(exc)
        assert len(err.field_errors) == 1
        assert err.field_errors[0].workflow_id == "wf_a"
        assert err.field_errors[0].field == "params"
        assert err.graph_errors == []

    def test_from_reference_errors_collection(self):
        refs = [WorkflowReferenceError(_make_ref(), "msg1"), WorkflowReferenceError(_make_ref(), "msg2")]
        exc = WorkflowReferenceErrors(errors=refs)
        err = SessionCommandError.from_exception(exc)
        assert len(err.field_errors) == 2

    def test_from_generic_graph_validation_error(self):
        exc = GraphValidationError("cycle detected")
        err = SessionCommandError.from_exception(exc)
        assert err.field_errors == []
        assert len(err.graph_errors) == 1
        assert "cycle" in err.graph_errors[0]

    def test_to_dict_structure(self):
        ref = _make_ref()
        exc = WorkflowReferenceError(reference=ref, message="test")
        err = SessionCommandError.from_exception(exc)
        d = err.to_dict()
        assert "field_errors" in d
        assert "graph_errors" in d
        assert isinstance(d["field_errors"], list)
        assert d["field_errors"][0]["workflow_id"] == "wf_a"


# ---------------------------------------------------------------------------
# format_errors_for_cli
# ---------------------------------------------------------------------------

class TestFormatErrorsForCli:
    def test_formats_reference_error(self):
        ref = _make_ref()
        exc = WorkflowReferenceError(reference=ref, message="missing predecessor")
        output = format_errors_for_cli(exc)
        assert "wf_a" in output
        assert "missing predecessor" in output

    def test_formats_reference_errors_collection(self):
        refs = [WorkflowReferenceError(_make_ref(), "err1"), WorkflowReferenceError(_make_ref(), "err2")]
        exc = WorkflowReferenceErrors(errors=refs)
        output = format_errors_for_cli(exc)
        assert "err1" in output
        assert "err2" in output

    def test_formats_graph_validation_error(self):
        exc = GraphValidationError("cycle found in graph")
        output = format_errors_for_cli(exc)
        assert "cycle found in graph" in output