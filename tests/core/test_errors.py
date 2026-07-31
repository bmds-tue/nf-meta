import click
import pytest
from pydantic import ValidationError

from nf_meta.core.line_linting import locate_field
from nf_meta.core.models import NfPipeline
from nf_meta.core.errors import (
    ConfigValidationError,
    Diagnostic,
    GraphValidationError,
    Severity,
    SessionCommandError,
    diagnostics_from_pydantic_error,
    format_errors_for_cli,
)


# ---------------------------------------------------------------------------
# Diagnostic.yaml_path
# ---------------------------------------------------------------------------


class TestDiagnosticYamlPath:
    def test_defaults_to_field_when_omitted(self):
        d = Diagnostic(
            workflow_id="wf_a",
            field="params.outdir",
            message="bad param",
            severity=Severity.ERROR,
        )
        assert d.yaml_path == "params.outdir"

    def test_explicit_yaml_path_is_kept_distinct_from_field(self):
        """field stays short (for the [workflow_id/field] tag); yaml_path can
        be a different, fully-qualified path (for position lookup)."""
        d = Diagnostic(
            workflow_id="wf_a",
            field="params.outdir",
            yaml_path="workflows.wf_a.params.outdir",
            message="bad param",
            severity=Severity.ERROR,
        )
        assert d.field == "params.outdir"
        assert d.yaml_path == "workflows.wf_a.params.outdir"


# ---------------------------------------------------------------------------
# SessionCommandError.from_exception
# ---------------------------------------------------------------------------

class TestSessionCommandError:
    def test_from_config_validation_error_delegates_to_from_diagnostics(self):
        """ConfigValidationError is now the only exception type carrying
        multiple errors -- from_exception's dispatch to from_diagnostics is
        what used to need separate single-vs-collection normalization for
        WorkflowReferenceError/WorkflowReferenceErrors; that distinction no
        longer exists since ConfigValidationError.errors is always a list."""
        exc = ConfigValidationError(
            errors=[
                Diagnostic(
                    workflow_id="wf_a",
                    field="params",
                    message="msg1",
                    severity=Severity.ERROR,
                ),
                Diagnostic(
                    workflow_id="wf_a",
                    field="params",
                    message="msg2",
                    severity=Severity.ERROR,
                ),
            ]
        )
        err = SessionCommandError.from_exception(exc)
        assert len(err.field_errors) == 2
        assert err.field_errors[0].workflow_id == "wf_a"
        assert err.graph_errors == []

    def test_from_generic_graph_validation_error(self):
        exc = GraphValidationError("cycle detected")
        err = SessionCommandError.from_exception(exc)
        assert err.field_errors == []
        assert len(err.graph_errors) == 1
        assert "cycle" in err.graph_errors[0]

    def test_to_dict_structure(self):
        exc = ConfigValidationError(
            errors=[
                Diagnostic(
                    workflow_id="wf_a",
                    field="params",
                    message="test",
                    severity=Severity.ERROR,
                )
            ]
        )
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

    def test_yaml_path_defaults_to_field_without_prefix(self):
        """Correct for an isolated snippet -- no wrapping document at all."""
        with pytest.raises(ValidationError) as exc_info:
            NfPipeline(name="my-org/custom", version="not-a-version", url="https://github.com/my-org/custom")
        diagnostics = diagnostics_from_pydantic_error(exc_info.value, workflow_id="wf_1")
        assert diagnostics[0].yaml_path == diagnostics[0].field == "version"

    def test_yaml_path_prefix_qualifies_for_whole_config(self):
        with pytest.raises(ValidationError) as exc_info:
            NfPipeline(name="my-org/custom", version="not-a-version", url="https://github.com/my-org/custom")
        diagnostics = diagnostics_from_pydantic_error(
            exc_info.value, workflow_id="wf_1", yaml_path_prefix="workflows.wf_1."
        )
        assert diagnostics[0].field == "version"
        assert diagnostics[0].yaml_path == "workflows.wf_1.version"


# ---------------------------------------------------------------------------
# format_errors_for_cli — ConfigValidationError
# ---------------------------------------------------------------------------


class TestFormatErrorsForCliConfig:
    def test_formats_config_validation_error(self):
        exc = ConfigValidationError(
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

    def test_formats_error_from_pydantic_construction_failure(self):
        exc = ConfigValidationError(
            errors=[
                Diagnostic(
                    workflow_id="wf_a",
                    field="name",
                    message="Field required",
                    severity=Severity.ERROR,
                )
            ]
        )
        output = format_errors_for_cli(exc)
        assert "wf_a" in output
        assert "Field required" in output


# ---------------------------------------------------------------------------
# format_errors_for_cli
# ---------------------------------------------------------------------------

class TestFormatErrorsForCli:
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

        exc = ConfigValidationError(
            errors=[
                Diagnostic(
                    workflow_id="wf_a",
                    field="params.outdir",
                    yaml_path="workflows.wf_a.params.outdir",
                    message="bad param",
                    severity=Severity.ERROR,
                )
            ]
        )
        output = format_errors_for_cli(exc, source_text=source, filename="test.yaml")
        assert f"test.yaml:{expected.line}:{expected.column}" in output

    def test_no_position_falls_back_to_bare_filename(self):
        exc = ConfigValidationError(
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

    def test_no_workflow_id_still_resolves_via_default_yaml_path(self):
        """A diagnostic with no workflow_id (e.g. a top-level config_version
        error) still resolves a real position: yaml_path defaults to field,
        and "config_version" is a real root-level key here -- no workflow_id
        special-casing is needed for this to work."""
        source = "config_version: 0.0.2\nworkflows: {}\ntransitions: []\n"
        expected = locate_field(source, "config_version")
        assert expected is not None

        exc = ConfigValidationError(
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
        assert lines[1] == f" test.yaml:{expected.line}:{expected.column}: error: [config_version] bad version"

    def test_warning_severity_labeled_distinctly_from_error(self):
        exc = ConfigValidationError(
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
        exc = ConfigValidationError(
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
