from click.testing import CliRunner

from nf_meta.__main__ import cli
from nf_meta.core.line_linting import locate_field


def _write(tmp_path, text):
    path = tmp_path / "metapipeline.yaml"
    path.write_text(text)
    return path


class TestValidateCommand:
    def test_reports_line_number_for_pydantic_error(self, tmp_path):
        text = "config_version: 0.3.0\nworkflows:\n  wf_a:\n    version: 2.0.0\n"
        path = _write(tmp_path, text)
        expected = locate_field(text, "workflows.wf_a.name")
        assert expected is not None

        result = CliRunner().invoke(cli, ["validate", str(path)])

        assert result.exit_code == 1
        assert f"Validation failed in {path}" in result.output
        assert f"{expected.line}:{expected.column}  workflows.wf_a.name  Field required" in result.output
        assert "workflows.wf_a.url" in result.output

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
        assert f"{expected.line}:{expected.column}  workflows.wf_a.params.foobar  Unknown parameter" in result.output

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
        text = "name: nf-core/rnaseq\nversion: 3.14.0\nparams:\n  input: samplesheet.csv\n  outdir: results\n"
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
        assert f"{expected.line}:{expected.column}  version  " in result.output

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
        assert f"{expected.line}:{expected.column}  config_file  " in result.output

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
        assert "workflows.wf_a.name" in result.output
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
            "config_version: 0.3.0\nworkflows:\n  n01:\n    name: nf-core/fetchngs\n    version: 1.12.0\n",
        )
        out = tmp_path / "results"
        result = CliRunner().invoke(cli, ["run", "-r", "python", "--dry-run", "--out", str(out), str(path)])
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
        assert f"Warnings in {path}:" in result.output
        assert " Warning  3:3  inputs.spare  not used by any step" in result.output
        assert "Config is valid with 1 warning" in result.output

    def test_errors_and_warnings_listed_together(self, tmp_path):
        path = _write(tmp_path, self.CONFIG + "input: {}\n")
        result = CliRunner().invoke(cli, ["validate", str(path)])
        assert result.exit_code == 1
        assert f"Validation failed in {path} (1 error, 1 warning):" in result.output
        assert " Error    12:1  input  Unknown key. Did you mean 'inputs'?" in result.output
        assert result.output.index("Error ") < result.output.index("Warning ")


class TestWarningsInOtherCommands:
    def test_run_prints_warnings_like_validate(self, tmp_path, monkeypatch):
        path = _write(tmp_path, TestValidateWarnings.CONFIG)
        (tmp_path / "ids.csv").write_text("")
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(cli, ["run", "-r", "python", "--dry-run", str(path)])
        assert result.exit_code == 0, result.output
        assert result.output.startswith(f"Warnings in {path}:\n")
        assert " Warning  3:3  inputs.spare  not used by any step" in result.output

    def test_validate_workflow_scope_reports_warnings(self, tmp_path, monkeypatch):
        from nf_meta.core.errors import Diagnostic, Severity

        warning = Diagnostic(None, "url", "unreachable", Severity.WARNING)
        monkeypatch.setattr("nf_meta.core.config.run_dynamic_checks", lambda wf, previous=None: [warning])
        path = _write(tmp_path, "name: nf-core/fetchngs\nversion: 1.12.0\n")
        result = CliRunner().invoke(cli, ["validate", "--scope", "workflow", str(path)])
        assert result.exit_code == 0, result.output
        assert "Warning  url  unreachable" in result.output
        assert "Workflow is valid with 1 warning" in result.output


class TestRunInputs:
    CONFIG = (
        "config_version: 0.4.0\n"
        "inputs:\n"
        "  genome:\n"
        "    bind: [n01.genome]\n"
        "    enum: [EB1, GRCh38]\n"
        "workflows:\n"
        "  n01:\n"
        "    name: nf-core/fetchngs\n"
        "    version: 1.12.0\n"
        "    params:\n"
        "      input: ids.csv\n"
        "      outdir: o\n"
    )

    def _invoke(self, tmp_path, monkeypatch, *args, stdin=None):
        schema = {
            "input": {"type": "string"},
            "outdir": {"type": "string"},
            "genome": {"type": "string"},
        }
        monkeypatch.setattr("nf_meta.core.dynamic_validation.get_pipeline_schema", lambda url, version: schema)
        path = _write(tmp_path, self.CONFIG)
        monkeypatch.chdir(tmp_path)
        return CliRunner().invoke(cli, ["run", "-r", "python", "--dry-run", *args, str(path)], input=stdin)

    def test_dry_run_without_terminal_shows_placeholders(self, tmp_path, monkeypatch):
        result = self._invoke(tmp_path, monkeypatch)
        assert result.exit_code == 0, result.output
        assert "genome: <input: genome>" in result.output
        assert "Missing values (shown as <input: ...>): genome." in result.output

    def test_input_option(self, tmp_path, monkeypatch):
        result = self._invoke(tmp_path, monkeypatch, "--input", "genome=GRCh38")
        assert result.exit_code == 0, result.output
        assert "genome: GRCh38" in result.output
        assert "Missing values" not in result.output

    def test_inputs_file(self, tmp_path, monkeypatch):
        values = tmp_path / "values.yaml"
        values.write_text("genome: EB1\n")
        result = self._invoke(tmp_path, monkeypatch, "--inputs-file", str(values))
        assert result.exit_code == 0, result.output
        assert "genome: EB1" in result.output

    def test_prompt_mode_asks_before_printing(self, tmp_path, monkeypatch):
        result = self._invoke(tmp_path, monkeypatch, "--input-mode", "prompt", stdin="nope\nGRCh38\n")
        assert result.exit_code == 0, result.output
        assert "genome: GRCh38" in result.output
        assert result.output.index("genome") < result.output.index("Step 1/1")

    def test_invalid_given_value(self, tmp_path, monkeypatch):
        result = self._invoke(tmp_path, monkeypatch, "--input", "genome=hg19")
        assert result.exit_code == 1
        assert "genome = 'hg19': must be one of EB1, GRCh38" in result.output

    def test_malformed_input_option(self, tmp_path, monkeypatch):
        result = self._invoke(tmp_path, monkeypatch, "--input", "genome")
        assert result.exit_code == 2
        assert "expected NAME=VALUE" in result.output


class TestScopeHint:
    def test_whole_config_with_workflow_scope_warns(self, tmp_path):
        path = _write(tmp_path, "config_version: 0.3.0\nworkflows:\n  n01:\n    name: nf-core/fetchngs\n")
        result = CliRunner().invoke(cli, ["validate", "--scope", "workflow", str(path)])
        assert result.exit_code == 1
        assert "Validation failed in" in result.output
        assert "Warning  2:1  workflows  This looks like a whole config, not a single workflow snippet" in result.output

    def test_whole_config_with_globals_scope_warns(self, tmp_path):
        path = _write(tmp_path, "config_version: 0.3.0\nworkflows: {}\n")
        result = CliRunner().invoke(cli, ["validate", "--scope", "globals", str(path)])
        assert "use --scope config" in result.output

    def test_snippet_gets_no_hint(self, tmp_path):
        path = _write(tmp_path, "name: nf-core/rnaseq\nversion: 3.14.0\n")
        result = CliRunner().invoke(cli, ["validate", "--scope", "workflow", str(path)])
        assert result.exit_code == 0
        assert "whole config" not in result.output


class TestQuestions:
    """Which questionary question each kind of input gets (no terminal needed)."""

    def _question(self, monkeypatch, **schema):
        from nf_meta.__main__ import _question_for_input
        from nf_meta.core.inputs import Input

        calls = {}
        for kind in ("select", "confirm", "path", "text"):
            monkeypatch.setattr(f"questionary.{kind}", lambda *a, _k=kind, **kw: calls.update(kind=_k, args=a, kw=kw))
        _question_for_input(Input(name="x", schema={"type": "string", **schema}))
        return calls

    def test_enum_is_a_selection(self, monkeypatch):
        calls = self._question(monkeypatch, enum=["EB1", "GRCh38"])
        assert calls["kind"] == "select"
        assert calls["kw"]["choices"] == ["EB1", "GRCh38"]

    def test_long_enum_is_searchable(self, monkeypatch):
        calls = self._question(monkeypatch, enum=[str(i) for i in range(20)])
        assert calls["kw"]["use_search_filter"] is True

    def test_boolean_is_a_confirm(self, monkeypatch):
        assert self._question(monkeypatch, type="boolean")["kind"] == "confirm"

    def test_path_completes_and_validates(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "ids.csv").write_text("")
        calls = self._question(monkeypatch, format="file-path", exists=True)
        assert calls["kind"] == "path"
        assert calls["kw"]["only_directories"] is False
        validate = calls["kw"]["validate"]
        assert validate("ids.csv") is True
        assert validate("nope.csv") == "does not exist"

    def test_directory_path_only_completes_directories(self, monkeypatch):
        assert self._question(monkeypatch, format="directory-path")["kw"]["only_directories"] is True

    def test_number_validates_while_typing(self, monkeypatch):
        calls = self._question(monkeypatch, type="integer", minimum=1)
        assert calls["kind"] == "text"
        assert calls["kw"]["validate"]("0") == "must be >= 1"
        assert calls["kw"]["validate"]("x") == "not a valid integer"
        assert calls["kw"]["validate"]("3") is True


class TestRunNfConfig:
    def _invoke(self, tmp_path, monkeypatch, *args):
        path = _write(
            tmp_path, "config_version: 0.4.0\nworkflows:\n  n01:\n    name: nf-core/fetchngs\n    version: 1.12.0\n"
        )
        monkeypatch.chdir(tmp_path)
        return CliRunner().invoke(cli, ["run", "--dry-run", *args, str(path)])

    def test_nf_config_relative_to_current_dir(self, tmp_path, monkeypatch):
        (tmp_path / "local.config").write_text("process.cpus = 2\n")
        result = self._invoke(tmp_path, monkeypatch, "-c", "local.config")
        assert result.exit_code == 0, result.output
        assert f"-c {tmp_path / 'local.config'}" in result.output

    def test_missing_nf_config_rejected(self, tmp_path, monkeypatch):
        result = self._invoke(tmp_path, monkeypatch, "--nf-config", "nope.config")
        assert result.exit_code == 2
        assert "does not exist" in result.output

    def test_nf_profile_short_form(self, tmp_path, monkeypatch):
        result = self._invoke(tmp_path, monkeypatch, "-p", "docker")
        assert result.exit_code == 0, result.output
        assert "-profile docker" in result.output

    def test_old_profile_option_removed(self, tmp_path, monkeypatch):
        assert self._invoke(tmp_path, monkeypatch, "--profile", "docker").exit_code == 2


class TestEditorCommand:
    def test_starting_with_a_config_remembers_it(self, tmp_path, monkeypatch):
        import nf_meta.editor
        from nf_meta.editor.backend import recent

        started = []
        monkeypatch.setattr(nf_meta.editor, "run_editor", started.append)
        config = tmp_path / "mp.yaml"
        config.write_text("config_version: 0.4.0\nworkflows: {}\n")
        result = CliRunner().invoke(cli, ["editor", "--no-browser", str(config)])
        assert result.exit_code == 0, result.output
        assert started[0].open_browser is False
        assert recent.recent_configs() == [str(config)]

    def test_starting_without_a_config_remembers_nothing(self, monkeypatch):
        import nf_meta.editor
        from nf_meta.editor.backend import recent

        monkeypatch.setattr(nf_meta.editor, "run_editor", lambda options: None)
        assert CliRunner().invoke(cli, ["editor"]).exit_code == 0
        assert recent.recent_configs() == []
