"""
Maps a dot-path field (the same convention Diagnostic.field already uses,
e.g. "params.outdir") to a line/column position in a workflow node's raw
YAML text, via PyYAML's lower-level compose() API.

Deliberately takes a plain `field: str` rather than a Diagnostic — this
module has no knowledge of the Diagnostic/error vocabulary, only of YAML
text and dotted paths, so it stays independently testable and reusable.
"""

from dataclasses import dataclass

import yaml
from yaml.nodes import MappingNode, Node


@dataclass(frozen=True)
class TextPosition:
    line: int
    column: int


def _find_key(node: MappingNode, name: str) -> tuple[Node, Node] | None:
    for key_node, value_node in node.value:
        if key_node.value == name:
            return key_node, value_node
    return None


def locate_field(text: str, field: str) -> TextPosition | None:
    """Locate `field` (a dot-path, e.g. "params.meta.id") in `text`.

    At each level, the full remaining dotted path is tried as a single
    literal key first (covers nf-core's flattened map-key convention, e.g.
    a literal key "meta.id"), falling back to matching just the next
    segment and descending. If the exact field can't be found (e.g. a
    required param that's simply absent from the source), the position of
    the last successfully resolved ancestor key is returned instead — the
    same convention LSPs use for anchoring "missing field" diagnostics to
    their containing object. Returns None if not even the first segment
    resolves.
    """
    root = yaml.compose(text)
    if not isinstance(root, MappingNode):
        return None

    segments = field.split(".")
    current = root
    last_resolved: TextPosition | None = None

    for i, segment in enumerate(segments):
        remaining = ".".join(segments[i:])
        match = _find_key(current, remaining) or _find_key(current, segment)
        if match is None:
            return last_resolved

        key_node, value_node = match
        last_resolved = TextPosition(
            line=key_node.start_mark.line + 1,
            column=key_node.start_mark.column + 1,
        )

        if match[0].value == remaining or not isinstance(value_node, MappingNode):
            # Either the full remaining path matched a single flat key, or
            # there's nowhere left to descend — either way, we're done.
            return last_resolved

        current = value_node

    return last_resolved
