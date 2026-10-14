# Writing a runner

A runner turns a validated [`MetaworkflowGraph`](../api/core.md) into actual Nextflow
execution. This walks through the minimum needed to add one as an installable plugin. See
[`BaseRunner`](../api/runners.md) for the full contract.

## 1. Subclass `BaseRunner`

```python
# my_runner_package/runner.py
from nf_meta.core.graph import MetaworkflowGraph
from nf_meta.runner import BaseRunner


class MyRunner(BaseRunner):
    RUNNER_NAME = "my-runner"

    def run(self, g: MetaworkflowGraph) -> None:
        for wf in g.get_workflows_sorted():
            ...  # execute wf, in dependency order

    def resume(self, g: MetaworkflowGraph) -> None:
        ...  # continue a previously interrupted run
```

- `RUNNER_NAME` is required. Defining it is what registers the class (via
  `BaseRunner.__init_subclass__`), and it's the string users pass to `--runner`.
- Don't override `__init__`. `self.run_options` (a `RunOptions`) is already set by
  `BaseRunner.__init__`; read `self.run_options.cachedir`, `.stub`, `.start`/`.target`, etc.
  from there.
- Let failures raise. `run_metapipeline` doesn't catch exceptions from `run`/`resume`, so a
  workflow failure should propagate rather than being swallowed into a silent partial result.

## 2. Advertise it as a plugin

Registration only happens when the module defining `MyRunner` is actually imported.
nf-meta discovers runner plugins via the `nf_meta.runners` entry-point group. Add this to
your package's `pyproject.toml`:

```toml
[project.entry-points."nf_meta.runners"]
my-runner = "my_runner_package.runner:MyRunner"
```

Once installed alongside nf-meta, `my-runner` appears in `nf-meta run --runner` without any
change to nf-meta itself.

## 3. Verify

```bash
pip install -e .   # or however your plugin package installs
nf-meta run metapipeline.yaml --runner my-runner
```

If it doesn't show up, check that the entry point's module actually imports without error.
`_load_runner_plugins` logs a warning (not a hard failure) and skips a plugin that fails to
load, which can silently hide a broken import.
