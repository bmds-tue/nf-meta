"""
Tests for pipeline and module parameter validation:
  - _parse_nextflow_schema   (nf_core_utils)
  - _parse_module_schema     (nf_core_utils)
  - validate_params           (nf_param_validation)
  - get_pipeline_schema       (nf_core_utils — HTTP layer mocked)
  - NfPipeline model-level validation (integration, autouse mock_nfcore fixture)
  - NfModule  model-level validation  (integration, schema mock per-test)
  - Workflow version validator
"""

import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock, patch

from nf_meta.core.nf_core_utils import (
    _parse_nextflow_schema,
    _parse_module_schema,
    _parse_repo_url,
    _raw_url,
    get_pipeline_schema,
    PipelineSchemaError,
)
from nf_meta.core.nf_param_validation import validate_params
from nf_meta.core.models import NfPipeline, NfModule


# ---------------------------------------------------------------------------
# Shared schema fixture
# ---------------------------------------------------------------------------

SAMPLE_SCHEMA_JSON = {
    "definitions": {
        "input_output_options": {
            "title": "Input/output options",
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "string",
                    "format": "file-path",
                },
                "outdir": {
                    "type": "string",
                    "default": "results",
                },
            },
        },
        "alignment_options": {
            "title": "Alignment options",
            "type": "object",
            "properties": {
                "aligner": {
                    "type": "string",
                    "enum": ["star", "hisat2", "salmon"],
                    "default": "star",
                },
                "max_cpus": {
                    "type": "integer",
                    "default": 16,
                },
                "save_unaligned": {
                    "type": "boolean",
                    "default": False,
                },
                "help": {
                    "type": "boolean",
                    "hidden": True,
                    "default": False,
                },
            },
        },
    }
}

PARSED_SCHEMA = _parse_nextflow_schema(SAMPLE_SCHEMA_JSON)


# ---------------------------------------------------------------------------
# _parse_nextflow_schema
# ---------------------------------------------------------------------------

class TestParseNextflowSchema:
    def test_known_params_present(self):
        assert "input" in PARSED_SCHEMA
        assert "outdir" in PARSED_SCHEMA
        assert "aligner" in PARSED_SCHEMA
        assert "max_cpus" in PARSED_SCHEMA

    def test_required_flag(self):
        assert PARSED_SCHEMA["input"]["required"] is True
        assert PARSED_SCHEMA["outdir"]["required"] is False

    def test_default_values(self):
        assert PARSED_SCHEMA["outdir"]["default"] == "results"
        assert PARSED_SCHEMA["aligner"]["default"] == "star"
        assert PARSED_SCHEMA["max_cpus"]["default"] == 16

    def test_enum_values(self):
        assert PARSED_SCHEMA["aligner"]["enum"] == ["star", "hisat2", "salmon"]
        assert PARSED_SCHEMA["input"]["enum"] is None

    def test_type_values(self):
        assert PARSED_SCHEMA["input"]["type"] == "string"
        assert PARSED_SCHEMA["max_cpus"]["type"] == "integer"
        assert PARSED_SCHEMA["save_unaligned"]["type"] == "boolean"

    def test_hidden_flag(self):
        assert PARSED_SCHEMA["help"]["hidden"] is True
        assert PARSED_SCHEMA["input"]["hidden"] is False

    def test_defs_key_also_works(self):
        schema_with_defs = {"$defs": SAMPLE_SCHEMA_JSON["definitions"]}
        parsed = _parse_nextflow_schema(schema_with_defs)
        assert "input" in parsed
        assert "max_cpus" in parsed

    def test_top_level_properties(self):
        schema = {
            "properties": {"top_param": {"type": "string"}},
            "required": ["top_param"],
        }
        parsed = _parse_nextflow_schema(schema)
        assert parsed["top_param"]["required"] is True

    def test_empty_schema(self):
        assert _parse_nextflow_schema({}) == {}


# ---------------------------------------------------------------------------
# _parse_repo_url / _raw_url
# ---------------------------------------------------------------------------

class TestParseRepoUrl:
    def test_github(self):
        host, owner, repo = _parse_repo_url("https://github.com/nf-core/rnaseq")
        assert host == "github.com"
        assert owner == "nf-core"
        assert repo == "rnaseq"

    def test_gitlab(self):
        host, owner, repo = _parse_repo_url("https://gitlab.com/my-org/my-pipeline")
        assert host == "gitlab.com"
        assert owner == "my-org"
        assert repo == "my-pipeline"

    def test_bitbucket(self):
        host, owner, repo = _parse_repo_url("https://bitbucket.org/owner/repo")
        assert host == "bitbucket.org"
        assert owner == "owner"
        assert repo == "repo"

    def test_trailing_slash_stripped(self):
        _, _, repo = _parse_repo_url("https://github.com/nf-core/rnaseq/")
        assert repo == "rnaseq"

    def test_git_suffix_stripped(self):
        _, _, repo = _parse_repo_url("https://github.com/nf-core/rnaseq.git")
        assert repo == "rnaseq"

    def test_unsupported_host_raises(self):
        with pytest.raises(PipelineSchemaError, match="Cannot parse"):
            _parse_repo_url("https://example.com/org/repo")


class TestRawUrl:
    def test_github_raw_url(self):
        url = _raw_url("github.com", "nf-core", "rnaseq", "3.14.0", "nextflow_schema.json")
        assert url == "https://raw.githubusercontent.com/nf-core/rnaseq/3.14.0/nextflow_schema.json"

    def test_gitlab_raw_url(self):
        url = _raw_url("gitlab.com", "my-org", "pipeline", "1.0.0", "nextflow_schema.json")
        assert url == "https://gitlab.com/my-org/pipeline/-/raw/1.0.0/nextflow_schema.json"

    def test_bitbucket_raw_url(self):
        url = _raw_url("bitbucket.org", "owner", "repo", "v2.0.0", "nextflow_schema.json")
        assert url == "https://bitbucket.org/owner/repo/raw/v2.0.0/nextflow_schema.json"


# ---------------------------------------------------------------------------
# validate_params
# ---------------------------------------------------------------------------

class TestValidateParams:
    def test_valid_params_no_errors(self):
        params = {"input": "/data/samplesheet.csv", "aligner": "star"}
        errors = validate_params(params, PARSED_SCHEMA, pipeline_id="p1")
        assert errors == []

    def test_unknown_param_flagged(self):
        params = {"nonexistent_param": "value"}
        errors = validate_params(params, PARSED_SCHEMA, pipeline_id="p1")
        assert any("Unknown parameter" in e and "nonexistent_param" in e for e in errors)

    def test_required_missing_raises(self):
        # input is required (no default), not in params
        errors = validate_params({}, PARSED_SCHEMA, pipeline_id="p1")
        assert any("Required parameter" in e and "input" in e for e in errors)

    def test_required_with_default_not_flagged(self):
        # outdir is in required=False and has a default — no error
        errors = validate_params({}, PARSED_SCHEMA, pipeline_id="p1")
        assert not any("outdir" in e for e in errors)

    def test_skip_required_suppresses_check(self):
        errors = validate_params({}, PARSED_SCHEMA, pipeline_id="p1", skip_required=True)
        assert errors == []

    def test_hidden_required_not_flagged(self):
        # 'help' is hidden — even if it were required it should be skipped
        schema_with_hidden_required = {
            **PARSED_SCHEMA,
            "internal_param": {
                "type": "string",
                "required": True,
                "enum": None,
                "pattern": None,
                "format": None,
                "default": None,
                "hidden": True,
            },
        }
        errors = validate_params({}, schema_with_hidden_required, pipeline_id="p1")
        assert not any("internal_param" in e for e in errors)

    def test_wrong_integer_type(self):
        params = {"input": "/data/sheet.csv", "max_cpus": "not-a-number"}
        errors = validate_params(params, PARSED_SCHEMA, pipeline_id="p1")
        assert any("max_cpus" in e and "integer" in e for e in errors)

    def test_valid_integer(self):
        params = {"input": "/data/sheet.csv", "max_cpus": "8"}
        errors = validate_params(params, PARSED_SCHEMA, pipeline_id="p1")
        assert not any("max_cpus" in e for e in errors)

    def test_invalid_enum(self):
        params = {"input": "/data/sheet.csv", "aligner": "bowtie2"}
        errors = validate_params(params, PARSED_SCHEMA, pipeline_id="p1")
        assert any("aligner" in e and "allowed" in e for e in errors)

    def test_valid_enum(self):
        params = {"input": "/data/sheet.csv", "aligner": "hisat2"}
        errors = validate_params(params, PARSED_SCHEMA, pipeline_id="p1")
        assert not any("aligner" in e for e in errors)

    def test_invalid_boolean(self):
        params = {"input": "/data/sheet.csv", "save_unaligned": "maybe"}
        errors = validate_params(params, PARSED_SCHEMA, pipeline_id="p1")
        assert any("save_unaligned" in e and "boolean" in e for e in errors)

    def test_valid_booleans(self):
        for val in ("true", "false", "True", "False", "1", "0"):
            params = {"input": "/data/sheet.csv", "save_unaligned": val}
            errors = validate_params(params, PARSED_SCHEMA, pipeline_id="p1")
            assert not any("save_unaligned" in e for e in errors), f"Failed for value {val!r}"

    def test_reference_token_skips_type_check(self):
        # A cross-step reference should not be type-checked
        params = {"max_cpus": "${other_wf:params:threads}"}
        errors = validate_params(params, PARSED_SCHEMA, pipeline_id="p1")
        assert not any("max_cpus" in e for e in errors)

    def test_empty_schema_flags_all_params_unknown(self):
        params = {"input": "x"}
        errors = validate_params(params, {}, pipeline_id="p1")
        assert any("Unknown parameter" in e and "input" in e for e in errors)

    def test_map_subkey_not_flagged_as_unknown(self):
        schema = {"meta": {"type": "map", "required": True}}
        errors = validate_params({"meta.id": "s1", "meta.sample": "sA"}, schema, pipeline_id="p1")
        assert not any("Unknown parameter" in e for e in errors)

    def test_map_raw_value_flagged_as_error(self):
        schema = {"meta": {"type": "map", "required": True}}
        errors = validate_params({"meta": "[id:'s1']"}, schema, pipeline_id="p1")
        assert any("dot-notation" in e and "meta" in e for e in errors)

    def test_non_map_dotkey_flagged_as_unknown(self):
        schema = {"outdir": {"type": "string", "required": False, "default": "results"}}
        errors = validate_params({"outdir.sub": "x"}, schema, pipeline_id="p1")
        assert any("Unknown parameter" in e and "outdir.sub" in e for e in errors)


# ---------------------------------------------------------------------------
# get_pipeline_schema — HTTP layer
# ---------------------------------------------------------------------------

class TestGetPipelineSchema:
    def setup_method(self):
        get_pipeline_schema.cache_clear()

    def teardown_method(self):
        get_pipeline_schema.cache_clear()

    def _mock_response(self, status_code, json_data=None, headers=None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.headers = headers or {}
        if json_data is not None:
            resp.json.return_value = json_data
        return resp

    # Cache functions are imported locally inside get_pipeline_schema, so we
    # patch them via the cache module (from nf_meta.core.cache import ...).

    def test_successful_fetch_and_parse(self):
        mock_resp = self._mock_response(200, json_data=SAMPLE_SCHEMA_JSON)
        with patch("nf_meta.core.nf_core_utils.requests.get", return_value=mock_resp):
            with patch("nf_meta.core.cache.read_schema_cache", return_value=None):
                with patch("nf_meta.core.cache.write_schema_cache") as mock_write:
                    schema = get_pipeline_schema("https://github.com/my-org/my-pipeline", "1.0.0")
        assert "input" in schema
        assert mock_write.called

    def test_cache_hit_skips_http(self):
        with patch("nf_meta.core.cache.read_schema_cache", return_value=PARSED_SCHEMA):
            with patch("nf_meta.core.nf_core_utils.requests.get") as mock_get:
                schema = get_pipeline_schema("https://github.com/my-org/pipeline", "2.0.0")
        mock_get.assert_not_called()
        assert schema == PARSED_SCHEMA

    def test_404_raises_schema_error(self):
        mock_resp = self._mock_response(404)
        with patch("nf_meta.core.nf_core_utils.requests.get", return_value=mock_resp):
            with patch("nf_meta.core.cache.read_schema_cache", return_value=None):
                with pytest.raises(PipelineSchemaError, match="not found"):
                    get_pipeline_schema("https://github.com/my-org/pipeline", "3.0.0")

    def test_429_raises_with_token_hint(self):
        mock_resp = self._mock_response(429, headers={"Retry-After": "60"})
        with patch("nf_meta.core.nf_core_utils.requests.get", return_value=mock_resp):
            with patch("nf_meta.core.cache.read_schema_cache", return_value=None):
                with pytest.raises(PipelineSchemaError, match="GITHUB_TOKEN"):
                    get_pipeline_schema("https://github.com/my-org/pipeline", "4.0.0")

    def test_network_error_raises(self):
        import requests as req
        with patch("nf_meta.core.nf_core_utils.requests.get", side_effect=req.exceptions.ConnectionError("down")):
            with patch("nf_meta.core.cache.read_schema_cache", return_value=None):
                with pytest.raises(PipelineSchemaError, match="Network error"):
                    get_pipeline_schema("https://github.com/my-org/pipeline", "5.0.0")


# ---------------------------------------------------------------------------
# NfPipeline model-level integration  (uses autouse mock_nfcore fixture)
# ---------------------------------------------------------------------------

class TestNfPipelineParamValidation:
    """Integration tests using a custom schema mock that exercises validation paths."""

    def _pipeline_with_schema(self, monkeypatch, schema, **kwargs):
        monkeypatch.setattr(
            "nf_meta.core.models.get_pipeline_schema", lambda url, version: schema
        )
        return NfPipeline(
            name="nf-core/rnaseq",
            version="3.14.0",
            **kwargs,
        )

    def test_valid_params_pass(self, monkeypatch):
        wf = self._pipeline_with_schema(
            monkeypatch,
            PARSED_SCHEMA,
            params={"input": "/data/sheet.csv"},
        )
        assert wf.params["input"] == "/data/sheet.csv"

    def test_unknown_param_raises(self, monkeypatch):
        with pytest.raises(ValidationError, match="Unknown parameter"):
            self._pipeline_with_schema(
                monkeypatch,
                PARSED_SCHEMA,
                params={"not_a_real_param": "value"},
            )

    def test_required_missing_raises(self, monkeypatch):
        with pytest.raises(ValidationError, match="Required parameter.*input"):
            self._pipeline_with_schema(monkeypatch, PARSED_SCHEMA)

    def test_params_file_satisfies_required(self, monkeypatch, tmp_path):
        pf = tmp_path / "params.yaml"
        pf.write_text("input: /data/sheet.csv\n")
        # Required param comes from the file — should not raise
        wf = self._pipeline_with_schema(
            monkeypatch,
            PARSED_SCHEMA,
            params_file=str(pf),
        )
        assert wf.params_file is not None

    def test_params_file_missing_required_raises(self, monkeypatch, tmp_path):
        pf = tmp_path / "params.yaml"
        pf.write_text("outdir: /results\n")  # input is still missing
        with pytest.raises(ValidationError, match="Required parameter.*input"):
            self._pipeline_with_schema(monkeypatch, PARSED_SCHEMA, params_file=str(pf))

    def test_params_overrides_params_file(self, monkeypatch, tmp_path):
        pf = tmp_path / "params.yaml"
        pf.write_text("input: /from/file.csv\naligner: hisat2\n")
        wf = self._pipeline_with_schema(
            monkeypatch,
            PARSED_SCHEMA,
            params={"input": "/from/params.csv"},  # overrides file
            params_file=str(pf),
        )
        assert wf.params["input"] == "/from/params.csv"

    def test_params_file_unknown_param_raises(self, monkeypatch, tmp_path):
        pf = tmp_path / "params.yaml"
        pf.write_text("input: /data/sheet.csv\nnot_a_real_param: value\n")
        with pytest.raises(ValidationError, match="Unknown parameter.*not_a_real_param"):
            self._pipeline_with_schema(monkeypatch, PARSED_SCHEMA, params_file=str(pf))

    def test_schema_error_warns_and_skips_validation(self, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.core.models.get_pipeline_schema",
            lambda url, version: (_ for _ in ()).throw(
                PipelineSchemaError("schema unavailable")
            ),
        )
        output = []
        monkeypatch.setattr("nf_meta.core.models.click.echo", lambda msg: output.append(msg))
        # Should not raise — schema unavailability is a warning, not a hard error
        wf = NfPipeline(name="nf-core/rnaseq", version="3.14.0")
        assert wf is not None
        assert any("cannot validate params" in str(m).lower() for m in output)

    def test_invalid_enum_raises(self, monkeypatch):
        with pytest.raises(ValidationError, match="allowed values"):
            self._pipeline_with_schema(
                monkeypatch,
                PARSED_SCHEMA,
                params={"input": "/data/sheet.csv", "aligner": "bowtie2"},
            )

    def test_wrong_type_raises(self, monkeypatch):
        with pytest.raises(ValidationError, match="integer"):
            self._pipeline_with_schema(
                monkeypatch,
                PARSED_SCHEMA,
                params={"input": "/data/sheet.csv", "max_cpus": "lots"},
            )

    def test_reference_token_skips_type_check(self, monkeypatch):
        wf = self._pipeline_with_schema(
            monkeypatch,
            PARSED_SCHEMA,
            params={
                "input": "/data/sheet.csv",
                "max_cpus": "${fetch:params:thread_count}",
            },
        )
        assert "${fetch:params:thread_count}" in wf.params["max_cpus"]


# ---------------------------------------------------------------------------
# Workflow version validator
# ---------------------------------------------------------------------------

class TestVersionValidator:
    def _make_pipeline(self, version):
        return NfPipeline(
            name="nf-core/rnaseq",
            version=version,
        )

    def test_semver_accepted(self):
        assert self._make_pipeline("3.14.0").version == "3.14.0"

    def test_v_prefix_accepted(self):
        assert self._make_pipeline("v1.2.3").version == "v1.2.3"

    def test_commit_sha_7_chars_accepted(self):
        assert self._make_pipeline("abc1234").version == "abc1234"

    def test_commit_sha_40_chars_accepted(self):
        sha = "a" * 40
        assert self._make_pipeline(sha).version == sha

    def test_branch_name_rejected(self):
        for branch in ("main", "master", "develop", "feature/my-feature"):
            with pytest.raises(ValidationError, match="branch"):
                self._make_pipeline(branch)

    def test_nf_module_version_also_validated(self):
        wf = NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")
        assert wf.version == "0.0.0-6c4ed3a"

    def test_branch_rejected_on_module(self):
        with pytest.raises(ValidationError, match="branch"):
            NfModule(name="nf-core/fastqc", version="main")


# ---------------------------------------------------------------------------
# _parse_module_schema
# ---------------------------------------------------------------------------

SAMPLE_META_YML = {
    "input": [
        {"meta":  {"type": "map",  "description": "Sample metadata"}},
        {"reads": {"type": "file", "pattern": "*_{1,2}.fastq.gz"}},
    ]
}

TUPLE_META_YML = {
    "input": [
        [
            {"bam": {"type": "file", "pattern": "*.bam"}},
            {"bai": {"type": "file", "pattern": "*.bai"}},
        ]
    ]
}

ENUM_META_YML = {
    "input": [
        {"mode": {"type": "string", "enum": ["paired", "single"]}},
    ]
}


class TestParseModuleSchema:
    def test_single_entries_parsed(self):
        schema = _parse_module_schema(SAMPLE_META_YML)
        assert "meta" in schema
        assert "reads" in schema

    def test_all_inputs_required(self):
        schema = _parse_module_schema(SAMPLE_META_YML)
        assert schema["meta"]["required"] is True
        assert schema["reads"]["required"] is True

    def test_type_preserved(self):
        schema = _parse_module_schema(SAMPLE_META_YML)
        assert schema["meta"]["type"] == "map"
        assert schema["reads"]["type"] == "file"

    def test_pattern_preserved(self):
        schema = _parse_module_schema(SAMPLE_META_YML)
        assert schema["reads"]["pattern"] == "*_{1,2}.fastq.gz"
        assert schema["meta"]["pattern"] is None

    def test_enum_read_from_spec(self):
        schema = _parse_module_schema(ENUM_META_YML)
        assert schema["mode"]["enum"] == ["paired", "single"]

    def test_enum_none_when_absent(self):
        schema = _parse_module_schema(SAMPLE_META_YML)
        assert schema["reads"]["enum"] is None

    def test_tuple_inputs_flattened(self):
        schema = _parse_module_schema(TUPLE_META_YML)
        assert "bam" in schema
        assert "bai" in schema
        assert schema["bam"]["type"] == "file"
        assert schema["bai"]["pattern"] == "*.bai"

    def test_empty_input_list(self):
        assert _parse_module_schema({"input": []}) == {}

    def test_missing_input_key(self):
        assert _parse_module_schema({}) == {}

    def test_mixed_single_and_tuple(self):
        meta_yml = {
            "input": [
                {"meta": {"type": "map"}},
                [
                    {"bam": {"type": "file", "pattern": "*.bam"}},
                    {"bai": {"type": "file", "pattern": "*.bai"}},
                ],
            ]
        }
        schema = _parse_module_schema(meta_yml)
        assert set(schema.keys()) == {"meta", "bam", "bai"}


# ---------------------------------------------------------------------------
# NfModule model-level integration
# ---------------------------------------------------------------------------

class TestNfModuleParamValidation:
    """Integration tests for NfModule.validate_params_against_schema.

    The autouse mock_nfcore fixture returns {} for get_module_schema by default,
    so tests that want real validation override it per-test via monkeypatch.
    """

    def _module_with_schema(self, monkeypatch, schema, **kwargs):
        monkeypatch.setattr(
            "nf_meta.core.models.get_module_schema", lambda name, version: schema
        )
        return NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a", **kwargs)

    def test_empty_schema_always_passes(self):
        wf = NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a")
        assert wf.version == "0.0.0-6c4ed3a"

    def test_required_param_missing_raises(self, monkeypatch):
        schema = {
            "meta":  {"type": "map",  "required": True},
            "reads": {"type": "file", "required": True},
        }
        with pytest.raises(ValidationError, match="Required parameter"):
            self._module_with_schema(monkeypatch, schema)

    def test_all_required_params_present_passes(self, monkeypatch):
        schema = {
            "meta":  {"type": "map",  "required": True},
            "reads": {"type": "file", "required": True},
        }
        wf = self._module_with_schema(
            monkeypatch,
            schema,
            params={"meta.id": "s1", "reads": "/data/r1.fastq.gz"},
        )
        assert wf.params["reads"] == "/data/r1.fastq.gz"

    def test_map_subkey_satisfies_required(self, monkeypatch):
        schema = {
            "meta":  {"type": "map",  "required": True},
            "reads": {"type": "file", "required": True},
        }
        wf = self._module_with_schema(
            monkeypatch,
            schema,
            params={"meta.id": "sample1", "reads": "/data/r1.fastq.gz"},
        )
        assert wf.params["meta.id"] == "sample1"

    def test_unknown_param_raises(self, monkeypatch):
        schema = {
            "meta":  {"type": "map",  "required": True},
            "reads": {"type": "file", "required": True},
        }
        with pytest.raises(ValidationError, match="Unknown parameter"):
            self._module_with_schema(
                monkeypatch,
                schema,
                params={"meta.id": "s1", "reads": "/r.fastq.gz", "extra": "nope"},
            )

    def test_map_raw_value_raises(self, monkeypatch):
        schema = {
            "meta":  {"type": "map",  "required": True},
            "reads": {"type": "file", "required": True},
        }
        with pytest.raises(ValidationError, match="dot-notation"):
            self._module_with_schema(
                monkeypatch,
                schema,
                params={"meta": "[id:'s1']", "reads": "/data/r1.fastq.gz"},
            )

    def test_enum_enforced(self, monkeypatch):
        schema = {
            "mode": {"type": "string", "required": True, "enum": ["paired", "single"]},
        }
        with pytest.raises(ValidationError, match="allowed values"):
            self._module_with_schema(monkeypatch, schema, params={"mode": "interleaved"})

    def test_float_type_validated(self, monkeypatch):
        schema = {"threshold": {"type": "float", "required": True}}
        with pytest.raises(ValidationError, match="number"):
            self._module_with_schema(monkeypatch, schema, params={"threshold": "not-a-float"})

    def test_eval_type_skips_check(self, monkeypatch):
        schema = {"expr": {"type": "eval", "required": True}}
        wf = self._module_with_schema(monkeypatch, schema, params={"expr": "params.flag ? 'a' : 'b'"})
        assert wf.params["expr"] is not None

    def test_reference_token_skips_validation(self, monkeypatch):
        schema = {
            "meta":  {"type": "map",  "required": True},
            "reads": {"type": "file", "required": True},
        }
        wf = self._module_with_schema(
            monkeypatch,
            schema,
            params={"meta.id": "s", "reads": "${fetch:params:samplesheet}"},
        )
        assert "${fetch:params:samplesheet}" in wf.params["reads"]
