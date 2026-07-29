from nf_meta.core.line_linting import TextPosition, locate_field


class TestLocateField:
    def test_top_level_field(self):
        text = "name: nf-core/rnaseq\nversion: 3.14.0\n"
        assert locate_field(text, "version") == TextPosition(line=2, column=1)

    def test_nested_params_field(self):
        text = (
            "name: nf-core/rnaseq\n"
            "version: 3.14.0\n"
            "params:\n"
            "  input: samplesheet.csv\n"
            "  outdir: results\n"
        )
        assert locate_field(text, "params.outdir") == TextPosition(line=5, column=3)

    def test_flat_dotted_map_key(self):
        # nf-core's map-type flattening convention: a literal key "meta.id",
        # not a nested "meta: {id: ...}" mapping.
        text = "params:\n  meta.id: s1\n  meta.sample: sA\n"
        assert locate_field(text, "params.meta.id") == TextPosition(line=2, column=3)
        assert locate_field(text, "params.meta.sample") == TextPosition(line=3, column=3)

    def test_genuinely_nested_mapping_still_resolves(self):
        # If someone hand-wrote real nesting instead of the flattened
        # convention, the segment-by-segment fallback should still work.
        text = "params:\n  meta:\n    id: s1\n"
        assert locate_field(text, "params.meta.id") == TextPosition(line=3, column=5)

    def test_missing_leaf_falls_back_to_parent_key(self):
        # "outdir" isn't set at all — no node for it — fall back to the
        # position of "params" itself.
        text = "params:\n  input: samplesheet.csv\n"
        assert locate_field(text, "params.outdir") == TextPosition(line=1, column=1)

    def test_missing_top_level_field_returns_none(self):
        text = "name: nf-core/rnaseq\n"
        assert locate_field(text, "version") is None

    def test_cannot_descend_into_scalar_falls_back(self):
        # "params" resolves but is a scalar, not a mapping — further
        # segments can't be resolved, fall back to "params" itself.
        text = "params: not-a-mapping\n"
        assert locate_field(text, "params.outdir") == TextPosition(line=1, column=1)

    def test_empty_text_returns_none(self):
        assert locate_field("", "version") is None

    def test_non_mapping_document_returns_none(self):
        assert locate_field("- just\n- a\n- list\n", "version") is None
