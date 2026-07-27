import pytest
from pydantic import ValidationError

from nf_meta.core.models import NfPipeline, Reference, WorkflowReference
from nf_meta.core.errors import (
    Diagnostic,
    DynamicValidationError,
    GraphValidationError,
    Severity,
    WorkflowReferenceError,
    WorkflowReferenceErrors,
    SessionCommandError,
    diagnostics_from_pydantic_error,
    format_errors_for_cli,
)


def _make_ref(source_wf_id="wf_a", target_wf_id="wf_b"):
    return WorkflowReference(
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
# SessionCommandError.from_diagnostics
# ---------------------------------------------------------------------------


class TestSessionCommandErrorFromDiagnostics:
    def test_only_error_severity_included(self):
        diagnostics = [
            Diagnostic(
                workflow_id="wf_a",
                field="params",
                message="bad param",
                severity=Severity.ERROR,
            ),
            Diagnostic(
                workflow_id="wf_a",
                field="url",
                message="could not reach url",
                severity=Severity.WARNING,
            ),
        ]
        err = SessionCommandError.from_diagnostics(diagnostics)
        assert len(err.field_errors) == 1
        assert err.field_errors[0].workflow_id == "wf_a"
        assert err.field_errors[0].field == "params"
        assert err.field_errors[0].message == "bad param"
        assert err.graph_errors == []

    def test_no_errors_yields_empty_field_errors(self):
        diagnostics = [
            Diagnostic(
                workflow_id="wf_a",
                field="url",
                message="warn only",
                severity=Severity.WARNING,
            ),
        ]
        err = SessionCommandError.from_diagnostics(diagnostics)
        assert err.field_errors == []

    def test_empty_diagnostics_list(self):
        err = SessionCommandError.from_diagnostics([])
        assert err.field_errors == []
        assert err.graph_errors == []


# ---------------------------------------------------------------------------
# diagnostics_from_pydantic_error
# ---------------------------------------------------------------------------


class TestDiagnosticsFromPydanticError:
    def test_single_field_failure(self):
        with pytest.raises(ValidationError) as exc_info:
            NfPipeline(name="my-org/custom", version="not-a-version", url="https://github.com/my-org/custom")
        diagnostics = diagnostics_from_pydantic_error(exc_info.value, workflow_id="wf_1")
        assert len(diagnostics) == 1
        assert diagnostics[0].workflow_id == "wf_1"
        assert diagnostics[0].field == "version"
        assert diagnostics[0].severity == Severity.ERROR
        assert "branch name" in diagnostics[0].message

    def test_multiple_field_failures(self):
        with pytest.raises(ValidationError) as exc_info:
            NfPipeline(name="", version="not-a-version", url="not-a-url")
        diagnostics = diagnostics_from_pydantic_error(exc_info.value, workflow_id="wf_2")
        fields = {d.field for d in diagnostics}
        assert "name" in fields
        assert "version" in fields
        assert "url" in fields
        assert all(d.workflow_id == "wf_2" for d in diagnostics)
        assert all(d.severity == Severity.ERROR for d in diagnostics)


# ---------------------------------------------------------------------------
# format_errors_for_cli — DynamicValidationError
# ---------------------------------------------------------------------------


class TestFormatErrorsForCliDynamic:
    def test_formats_dynamic_validation_error(self):
        exc = DynamicValidationError(
            errors=[
                Diagnostic(
                    workflow_id="wf_a",
                    field="version",
                    message="version not in registry",
                    severity=Severity.ERROR,
                )
            ]
        )
        output = format_errors_for_cli(exc)
        assert "wf_a" in output
        assert "version not in registry" in output


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
