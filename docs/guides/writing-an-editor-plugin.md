# Writing an editor plugin

An editor backend is what `nf-meta editor --editor <name>` launches. This walks through adding
one as an installable plugin. See [`BaseEditor`](../api/editor.md) for the full contract.

## 1. Subclass `BaseEditor`

```python
# my_editor_package/editor.py
from nf_meta.editor import BaseEditor


class MyEditor(BaseEditor):
    EDITOR_NAME = "my-editor"

    def start(self) -> None:
        ...  # block until the user is done editing
```

- `EDITOR_NAME` is required. Defining it registers the class (via
  `BaseEditor.__init_subclass__`) and is the string users pass to `--editor`.
- Don't override `__init__`. `self.options` (an `EditorOptions`) is already set; read
  `self.options.host`/`.port` from there if your backend serves over HTTP.
- `start()` should block until the user is finished (the built-in `BrowserEditor` runs its
  server synchronously in the calling thread). It isn't expected to return while editing is
  still in progress.

## 2. Advertise it as a plugin

nf-meta discovers editor plugins via the `nf_meta.editors` entry-point group:

```toml
[project.entry-points."nf_meta.editors"]
my-editor = "my_editor_package.editor:MyEditor"
```

Once installed alongside nf-meta, `my-editor` appears in `nf-meta editor --editor` without any
change to nf-meta itself.

## 3. Verify

```bash
pip install -e .   # or however your plugin package installs
nf-meta editor --editor my-editor metapipeline.yaml
```

As with runner plugins, a plugin module that fails to import is skipped with a logged warning
rather than a hard failure. Check that first if `my-editor` doesn't show up as a choice.
