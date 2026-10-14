# API reference

This covers `nf_meta.core` (the config representation, validation, and graph), the runner
plugin surface (`nf_meta.runner`), and the editor plugin surface (`nf_meta.editor`). Anything
not listed here or in the [config reference](../representation/reference.md) is internal:
not part of the supported API, and may change without notice.

## Stability

nf-meta is beta: **everything here can still change.** Within that:

- **`BaseRunner`/`RunOptions`** and **`BaseEditor`/`EditorOptions`** are the intended plugin
  extension points. See [Writing a runner](../guides/writing-a-runner.md) and
  [Writing an editor plugin](../guides/writing-an-editor-plugin.md). These are the most
  deliberately designed part of the surface and change the least often, but are not yet under
  a formal compatibility guarantee.
- **`nf_meta.core`** (the config model, validation, and graph) is documented so embedders can
  parse/construct/inspect metapipelines programmatically, but its shape still tracks the
  config format's own evolution (`config_version`) and is more likely to shift.
- **The built-in `SimplePythonRunner` and `BrowserEditor`** are documented for reference, not
  as a base to subclass from. Extend `BaseRunner`/`BaseEditor` directly instead.

See the [config reference](../representation/reference.md) for the `.yaml` format itself,
which is the most stable part of the project: it has its own explicit version key
(`config_version`) precisely so it can evolve without breaking existing configs.
