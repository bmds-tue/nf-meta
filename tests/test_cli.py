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


class TestRunDryRun:
    def test_prints_commands_without_running(self, tmp_path, monkeypatch):
        text = (
            "config_version: 0.3.0\n"
            "workflows:\n"
            "  n01:\n"
            "    name: nf-core/fetchngs\n"
            "    version: 1.12.0\n"
            "    params:\n"
            "      outdir: out_fetchngs\n"
            "  n02:\n"
            "    name: nf-core/rnaseq\n"
            "    version: 3.14.0\n"
            "    from: n01\n"
            "    params:\n"
            "      input: ${n01:params:outdir}/samplesheet.csv\n"
        )
        path = _write(tmp_path, text)
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(cli, ["run", "-r", "python", "--dry-run", str(path)])

        assert result.exit_code == 0, result.output
        assert "Step 1/2: n01 (nf-core/fetchngs)" in result.output
        assert f"cwd: {tmp_path / 'nf-meta-out'}" in result.output
        assert "NXF_CACHE_DIR=" in result.output
        assert " run -ansi-log false -w " in result.output
        assert "input: out_fetchngs/samplesheet.csv" in result.output
        assert sorted(p.name for p in tmp_path.iterdir()) == ["metapipeline.yaml"]

    def test_out_option_sets_launch_dir(self, tmp_path, monkeypatch):
        path = _write(
            tmp_path,
            "config_version: 0.3.0\nworkflows:\n  n01:\n    name: nf-core/fetchngs\n"
            "    version: 1.12.0\n",
        )
        out = tmp_path / "results"
        result = CliRunner().invoke(
            cli, ["run", "-r", "python", "--dry-run", "--out", str(out), str(path)]
        )
        assert result.exit_code == 0, result.output
        assert f"cwd: {out}" in result.output


class TestValidateWarnings:
    CONFIG = (
        "config_version: 0.4.0\n"
        "inputs:\n"
        "  spare:\n"
        "    type: string\n"
        "workflows:\n"
        "  n01:\n"
        "    name: nf-core/fetchngs\n"
        "    version: 1.12.0\n"
        "    params:\n"
        "      input: ids.csv\n"
        "      outdir: o\n"
    )

    def test_valid_with_warnings(self, tmp_path):
        path = _write(tmp_path, self.CONFIG)
        result = CliRunner().invoke(cli, ["validate", str(path)])
        assert result.exit_code == 0, result.output
        assert f"{path}:3:3: warning: Input 'spare' is not used by any step" in result.output
        assert "Config is valid with 1 warning" in result.output

    def test_errors_and_warnings_listed_together(self, tmp_path):
        path = _write(tmp_path, self.CONFIG + "input: {}\n")
        result = CliRunner().invoke(cli, ["validate", str(path)])
        assert result.exit_code == 1
        assert "Validation failed (1 error, 1 warning):" in result.output
        assert result.output.index("error:") < result.output.index("warning:")
