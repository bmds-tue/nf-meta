from click.testing import CliRunner

from nf_meta.__main__ import cli
from nf_meta.core.line_linting import locate_field


def _write(tmp_path, text):
    path = tmp_path / "metapipeline.yaml"
    path.write_text(text)
    return path


class TestValidateCommand:
    def test_reports_line_number_for_pydantic_error(self, tmp_path):
        text = (
            "config_version: 0.3.0\n"
            "workflows:\n"
            "  wf_a:\n"
            "    version: 2.0.0\n"
        )
        path = _write(tmp_path, text)
        expected = locate_field(text, "workflows.wf_a.name")
        assert expected is not None

        result = CliRunner().invoke(cli, ["validate", str(path)])

        assert result.exit_code == 1
        assert f"{path}:{expected.line}:{expected.column}" in result.output
        assert "wf_a/name" in result.output
        assert "wf_a/url" in result.output

    def test_reports_line_number_for_dynamic_error(self, tmp_path):
        text = (
            "config_version: 0.3.0\n"
            "workflows:\n"
            "  wf_a:\n"
            "    name: nf-core/rnaseq\n"
            "    version: 3.14.0\n"
            "    params:\n"
            "      foobar: true\n"
        )
        path = _write(tmp_path, text)
        expected = locate_field(text, "workflows.wf_a.params.foobar")
        assert expected is not None

        result = CliRunner().invoke(cli, ["validate", str(path)])

        assert result.exit_code == 1
        assert f"{path}:{expected.line}:{expected.column}" in result.output
        assert "Unknown parameter" in result.output

    def test_valid_config_reports_success(self, tmp_path):
        text = (
            "config_version: 0.3.0\n"
            "workflows:\n"
            "  wf_a:\n"
            "    name: nf-core/rnaseq\n"
            "    version: 3.14.0\n"
            "    params:\n"
            "      input: samplesheet.csv\n"
        )
        path = _write(tmp_path, text)

        result = CliRunner().invoke(cli, ["validate", str(path)])

        assert result.exit_code == 0
        assert "valid" in result.output

    def test_legacy_top_level_transitions_still_accepted(self, tmp_path):
        text = (
            "config_version: 0.3.0\n"
            "workflows:\n"
            "  wf_a:\n"
            "    name: nf-core/fetchngs\n"
            "    version: 1.12.0\n"
            "  wf_b:\n"
            "    name: nf-core/rnaseq\n"
            "    version: 3.14.0\n"
            "transitions:\n"
            "- source: wf_a\n"
            "  target: wf_b\n"
        )
        path = _write(tmp_path, text)

        result = CliRunner().invoke(cli, ["validate", str(path)])

        assert result.exit_code == 0
        assert "valid" in result.output

    def test_scope_workflow_valid_snippet(self, tmp_path):
        text = (
            "name: nf-core/rnaseq\n"
            "version: 3.14.0\n"
            "params:\n"
            "  input: samplesheet.csv\n"
            "  outdir: results\n"
        )
        path = _write(tmp_path, text)

        result = CliRunner().invoke(cli, ["validate", "--scope", "workflow", str(path)])

        assert result.exit_code == 0
        assert "Workflow is valid" in result.output

    def test_scope_workflow_reports_line_number_against_snippet_root(self, tmp_path):
        text = "name: nf-core/rnaseq\nversion: main\n"
        path = _write(tmp_path, text)
        expected = locate_field(text, "version")
        assert expected is not None

        result = CliRunner().invoke(cli, ["validate", "--scope", "workflow", str(path)])

        assert result.exit_code == 1
        assert f"{path}:{expected.line}:{expected.column}" in result.output
        assert "version" in result.output

    def test_scope_workflow_missing_required_field_does_not_crash(self, tmp_path):
        text = "version: 3.14.0\n"
        path = _write(tmp_path, text)

        result = CliRunner().invoke(cli, ["validate", "--scope", "workflow", str(path)])

        assert result.exit_code == 1
        assert "name" in result.output

    def test_scope_workflow_id_optional_for_new_workflow(self, tmp_path):
        """Flat snippet form: id may be omitted entirely (auto-generated),
        unlike a `workflows: {<id>: {...}}` excerpt from a full config."""
        text = "name: nf-core/rnaseq\nversion: 3.14.0\n"
        path = _write(tmp_path, text)

        result = CliRunner().invoke(cli, ["validate", "--scope", "workflow", str(path)])

        assert result.exit_code == 0

    def test_scope_globals_valid_snippet(self, tmp_path):
        text = "profile: docker\n"
        path = _write(tmp_path, text)

        result = CliRunner().invoke(cli, ["validate", "--scope", "globals", str(path)])

        assert result.exit_code == 0
        assert "Global options are valid" in result.output

    def test_scope_globals_reports_line_number_against_snippet_root(self, tmp_path):
        text = "config_file: /nonexistent/path.config\n"
        path = _write(tmp_path, text)
        expected = locate_field(text, "config_file")
        assert expected is not None

        result = CliRunner().invoke(cli, ["validate", "--scope", "globals", str(path)])

        assert result.exit_code == 1
        assert f"{path}:{expected.line}:{expected.column}" in result.output

    def test_multiple_errors_reported_together(self, tmp_path):
        text = (
            "config_version: 0.3.0\n"
            "workflows:\n"
            "  wf_a:\n"
            "    version: 2.0.0\n"  # missing name -> construction error
            "  wf_b:\n"
            "    name: nf-core/rnaseq\n"
            "    version: 3.14.0\n"
            "    from: [wf_c, nonexistent]\n"  # dangling edge to 'nonexistent'
            "  wf_c:\n"
            "    name: nf-core/fetchngs\n"
            "    version: 1.12.0\n"
            "    from: wf_b\n"  # wf_b <-> wf_c cycle
            "    params:\n"
            "      input: samplesheet.csv\n"
            "      outdir: results\n"
        )
        path = _write(tmp_path, text)

        result = CliRunner().invoke(cli, ["validate", str(path)])

        assert result.exit_code == 1
        assert "wf_a/name" in result.output
        assert "nonexistent" in result.output
        assert "cycle" in result.output

    def test_mixing_from_and_top_level_transitions_rejected(self, tmp_path):
        text = (
            "config_version: 0.3.0\n"
            "workflows:\n"
            "  wf_a:\n"
            "    name: nf-core/fetchngs\n"
            "    version: 1.12.0\n"
            "  wf_b:\n"
            "    name: nf-core/rnaseq\n"
            "    version: 3.14.0\n"
            "    from: wf_a\n"
            "transitions:\n"
            "- source: wf_a\n"
            "  target: wf_b\n"
        )
        path = _write(tmp_path, text)

        result = CliRunner().invoke(cli, ["validate", str(path)])

        assert result.exit_code == 1
        assert "ix" in result.output  # "Mix"/"mix"
