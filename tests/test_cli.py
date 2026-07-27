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
            "config_version: 0.0.2\n"
            "workflows:\n"
            "  wf_a:\n"
            "    version: 2.0.0\n"
            "transitions: []\n"
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
            "config_version: 0.0.2\n"
            "workflows:\n"
            "  wf_a:\n"
            "    name: nf-core/rnaseq\n"
            "    version: 3.14.0\n"
            "    params:\n"
            "      foobar: true\n"
            "transitions: []\n"
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
            "config_version: 0.0.2\n"
            "workflows:\n"
            "  wf_a:\n"
            "    name: nf-core/rnaseq\n"
            "    version: 3.14.0\n"
            "    params:\n"
            "      input: samplesheet.csv\n"
            "transitions: []\n"
        )
        path = _write(tmp_path, text)

        result = CliRunner().invoke(cli, ["validate", str(path)])

        assert result.exit_code == 0
        assert "valid" in result.output
