import json
from pathlib import Path

import jsonschema
import pytest

from nf_meta.core.graph import dump_config, from_raw_dict
from nf_meta.core.schema_export import generate_schema

SCHEMA_PATH = (
    Path(__file__).parent.parent.parent / "schemas" / "metapipeline.schema.json"
)


class TestGenerateSchema:
    def test_matches_committed_schema(self):
        """Drift check: forces a contributor who changes a model to also
        regenerate and commit schemas/metapipeline.schema.json in the same PR."""
        committed = json.loads(SCHEMA_PATH.read_text())
        assert generate_schema() == committed, (
            "schemas/metapipeline.schema.json is out of date -- regenerate it "
            "via `nf-meta export-schema` and commit the result."
        )

    def test_defs_hoisted_to_document_root(self):
        """The oneOf/discriminator $ref pointers ('#/$defs/NfPipeline') must
        resolve against the document root, not a nested sub-schema."""
        schema = generate_schema()
        assert "NfPipeline" in schema["$defs"]
        assert "NfModule" in schema["$defs"]
        assert "$defs" not in schema["properties"]["workflows"]["additionalProperties"]

    def test_from_field_present_and_id_absent(self):
        schema = generate_schema()
        for def_name in ("NfPipeline", "NfModule"):
            properties = schema["$defs"][def_name]["properties"]
            assert "from" in properties
            assert "id" not in properties
            assert "id" not in schema["$defs"][def_name].get("required", [])

    def test_rejects_missing_config_version(self):
        schema = generate_schema()
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"workflows": {}}, schema)

    def test_round_trip_sanity_against_real_output(self, monkeypatch):
        """Construct a graph covering both workflow types, from: (both bare
        string and list forms), and globals, then confirm dump_config's real
        output validates against the schema -- catches drift the generation
        function can't self-detect (e.g. dump_config's shape changing without
        the wrapper being updated to match). Only proves the schema doesn't
        *reject* this example, not exhaustive correctness."""
        monkeypatch.setattr(
            "nf_meta.core.dynamic_validation.get_module_schema",
            lambda name, version: {},
        )
        data = {
            "config_version": "0.3.0",
            "globals": {"profile": "docker", "nextflow_version": "25.10.4"},
            "workflows": {
                "wf_a": {
                    "name": "nf-core/fetchngs",
                    "version": "1.12.0",
                    "url": "https://github.com/nf-core/fetchngs",
                    "params": {"input": "samples.csv", "outdir": "results"},
                },
                "wf_b": {
                    "name": "nf-core/rnaseq",
                    "version": "3.14.0",
                    "url": "https://github.com/nf-core/rnaseq",
                    "from": "wf_a",  # bare-string form
                    "params": {"input": "samples.csv", "outdir": "results"},
                },
                "wf_c": {
                    "type": "nf-module",
                    "name": "my-org/custom-module",
                    "version": "1.0.0",
                    "container_engine": "docker",
                    "from": ["wf_a", "wf_b"],  # list form
                },
            },
        }
        g = from_raw_dict(data)
        dumped = dump_config(g)
        assert "transitions" not in dumped

        jsonschema.validate(dumped, generate_schema())
