import click
import pytest
import yaml
from pydantic import ValidationError

from nf_meta.core.line_linting import locate_field
from nf_meta.core.models import MetaworkflowConfig, NfPipeline, Reference, WorkflowReference
from nf_meta.core.errors import (
    Diagnostic,
    DynamicValidationError,
    GraphValidationError,
    Severity,
    WorkflowReferenceError,
    WorkflowReferenceErrors,
    SessionCommandError,
    diagnostics_from_config_validation_error,
    diagnostics_from_pydantic_error,
    diagnostics_from_reference_errors,
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
# diagnostics_from_config_validation_error
# ---------------------------------------------------------------------------


class TestDiagnosticsFromConfigValidationError:
    def test_resolves_dict_format_index_to_real_key(self):
        text = (
            "config_version: 0.0.2\n"
            "workflows:\n"
            "  wf_a:\n"
            "    name: nf-core/rnaseq\n"
            "    version: 3.14.0\n"
            "  wf_b:\n"
            "    version: 2.0.0\n"
            "transitions: []\n"
        )
        with pytest.raises(ValidationError) as exc_info:
            MetaworkflowConfig.model_validate(
                yaml.safe_load(text)
            )
        diagnostics = diagnostics_from_config_validation_error(exc_info.value, text)
        # wf_b is missing name/url -- both errors should resolve to workflow_id="wf_b",
        # not the numeric list index normalize_dict_to_list assigned internally.
        assert any(
            d.workflow_id == "wf_b" and d.field == "name" for d in diagnostics
        )
        assert any(
            d.workflow_id == "wf_b" and d.field == "url" for d in diagnostics
        )
        assert all(d.severity == Severity.ERROR for d in diagnostics)

    def test_strips_workflow_type_discriminator(self):
        text = (
            "config_version: 0.0.2\n"
            "workflows:\n"
            "  wf_a:\n"
            "    type: nf-module\n"
            "    version: not-a-version\n"
            "transitions: []\n"
        )
        with pytest.raises(ValidationError) as exc_info:
            MetaworkflowConfig.model_validate(
                yaml.safe_load(text)
            )
        diagnostics = diagnostics_from_config_validation_error(exc_info.value, text)
        # field should be "version", not "nf-module.version"
        assert any(
            d.workflow_id == "wf_a" and d.field == "version" for d in diagnostics
        )

    def test_top_level_field_error_has_no_workflow_id(self):
        text = (
            "config_version: not-a-version\n"
            "workflows:\n"
            "  wf_a:\n"
            "    name: nf-core/rnaseq\n"
            "    version: 3.14.0\n"
            "transitions: []\n"
        )
        with pytest.raises(ValidationError) as exc_info:
            MetaworkflowConfig.model_validate(
                yaml.safe_load(text)
            )
        diagnostics = diagnostics_from_config_validation_error(exc_info.value, text)
        assert any(
            d.workflow_id is None and d.field == "config_version" for d in diagnostics
        )

    def test_legacy_list_format_falls_back_without_workflow_id(self):
        text = (
            "config_version: 0.0.2\n"
            "workflows:\n"
            "- id: wf_a\n"
            "  version: not-a-version\n"
            "transitions: []\n"
        )
        with pytest.raises(ValidationError) as exc_info:
            MetaworkflowConfig.model_validate(
                yaml.safe_load(text)
            )
        diagnostics = diagnostics_from_config_validation_error(exc_info.value, text)
        # No dict-format workflows mapping to resolve against -- degrade gracefully,
        # no crash, no attributed workflow_id.
        assert len(diagnostics) >= 1
        assert all(d.workflow_id is None for d in diagnostics)


# ---------------------------------------------------------------------------
# diagnostics_from_reference_errors
# ---------------------------------------------------------------------------


class TestDiagnosticsFromReferenceErrors:
    def test_uses_source_key_for_field_granularity(self):
        ref = _make_ref()
        exc = WorkflowReferenceErrors(
            errors=[WorkflowReferenceError(reference=ref, message="unknown workflow")]
        )
        diagnostics = diagnostics_from_reference_errors(exc)
        assert len(diagnostics) == 1
        assert diagnostics[0].workflow_id == "wf_a"
        assert diagnostics[0].field == "params.input"
        assert diagnostics[0].severity == Severity.ERROR

    def test_falls_back_to_bare_params_for_non_workflow_reference(self):
        ref = Reference(name=None, source_wf_id="wf_a", target_wf_id="wf_b")
        exc = WorkflowReferenceErrors(
            errors=[WorkflowReferenceError(reference=ref, message="bad reference")]
        )
        diagnostics = diagnostics_from_reference_errors(exc)
        assert diagnostics[0].field == "params"


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

    def test_graph_validation_error_uses_header_and_aligned_layout(self):
        exc = GraphValidationError("cycle found in graph")
        output = click.unstyle(format_errors_for_cli(exc, filename="test.yaml"))
        lines = output.split("\n")
        assert lines[0] == "Validation failed:"
        assert lines[1] == " test.yaml: error: cycle found in graph"


# ---------------------------------------------------------------------------
# format_errors_for_cli — position resolution and column alignment
# ---------------------------------------------------------------------------


class TestFormatErrorsForCliPositions:
    def test_resolves_real_position_when_source_given(self):
        source = (
            "config_version: 0.0.2\n"
            "workflows:\n"
            "  wf_a:\n"
            "    name: nf-core/rnaseq\n"
            "    version: 3.14.0\n"
            "    params:\n"
            "      outdir: foo\n"
            "transitions: []\n"
        )
        expected = locate_field(source, "workflows.wf_a.params.outdir")
        assert expected is not None

        exc = DynamicValidationError(
            errors=[
                Diagnostic(
                    workflow_id="wf_a",
                    field="params.outdir",
                    message="bad param",
                    severity=Severity.ERROR,
                )
            ]
        )
        output = format_errors_for_cli(exc, source_text=source, filename="test.yaml")
        assert f"test.yaml:{expected.line}:{expected.column}" in output

    def test_no_position_falls_back_to_bare_filename(self):
        exc = DynamicValidationError(
            errors=[
                Diagnostic(
                    workflow_id="wf_a",
                    field="params.outdir",
                    message="bad param",
                    severity=Severity.ERROR,
                )
            ]
        )
        # No source_text given at all -- must not crash, no position attempted:
        # bare filename immediately followed by the "error:" marker, no
        # ":line:col" in between.
        output = click.unstyle(format_errors_for_cli(exc, filename="test.yaml"))
        lines = output.split("\n")
        assert lines[0] == "Validation failed:"
        assert lines[1] == " test.yaml: error: [wf_a/params.outdir] bad param"

    def test_no_workflow_id_skips_position_lookup(self):
        source = "config_version: 0.0.2\nworkflows: {}\ntransitions: []\n"
        exc = DynamicValidationError(
            errors=[
                Diagnostic(
                    workflow_id=None,
                    field="config_version",
                    message="bad version",
                    severity=Severity.ERROR,
                )
            ]
        )
        output = click.unstyle(
            format_errors_for_cli(exc, source_text=source, filename="test.yaml")
        )
        lines = output.split("\n")
        assert lines[0] == "Validation failed:"
        assert lines[1].startswith(" test.yaml:")

    def test_warning_severity_labeled_distinctly_from_error(self):
        exc = DynamicValidationError(
            errors=[
                Diagnostic(
                    workflow_id="wf_a",
                    field="url",
                    message="could not reach url",
                    severity=Severity.WARNING,
                )
            ]
        )
        output = format_errors_for_cli(exc)
        assert "warning" in output
        assert "could not reach url" in output

    def test_column_alignment_across_mixed_positions(self):
        source = "workflows:\n  wf_a:\n    name: nf-core/rnaseq\n"
        exc = DynamicValidationError(
            errors=[
                Diagnostic(
                    workflow_id="wf_a",
                    field="name",
                    message="short location",
                    severity=Severity.ERROR,
                ),
                Diagnostic(
                    workflow_id=None,
                    field="config_version",
                    message="no location at all",
                    severity=Severity.ERROR,
                ),
            ]
        )
        output = click.unstyle(
            format_errors_for_cli(exc, source_text=source, filename="x.yaml")
        )
        lines = output.split("\n")
        assert lines[0] == "Validation failed:"
        assert len(lines) == 3
        assert lines[1].index("error:") == lines[2].index("error:")
