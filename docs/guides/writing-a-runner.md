# Writing a runner

A runner turns a validated [`MetaworkflowGraph`](../api/core.md) into actual Nextflow
execution. This walks through the minimum needed to add one as an installable plugin. See
[`BaseRunner`](../api/runners.md) for the full contract.

## 1. Subclass `BaseRunner`

```python
# my_runner_package/runner.py
from nf_meta.core.graph import MetaworkflowGraph
from nf_meta.runner import BaseRunner, RunResults


class MyRunner(BaseRunner):
    RUNNER_NAME = "my-runner"

    def run(self, g: MetaworkflowGraph) -> RunResults:
        for step in g.get_workflows_sorted():
            ...  # execute the step, in dependency order

    def resume(self, g: MetaworkflowGraph) -> RunResults:
        ...  # continue a previous run, skipping what already succeeded
```

- `RUNNER_NAME` is required. Defining it is what registers the class (via
  `BaseRunner.__init_subclass__`), and it's the string users pass to `--runner`.
- Don't override `__init__`. `self.run_options` (a `RunOptions`) is already set by
  `BaseRunner.__init__`; read `self.run_options.out_dir`, `.stub`, `.start`/`.target`,
  `.inputs`, etc. from there.
- Return a `RunResults` (one `StepResult` per step), and let failures raise
  (`NfMetaRunnerError`): `run_metapipeline` doesn't catch exceptions from `run`/`resume`, so a
  step failure should propagate rather than being swallowed into a silent partial result.
- Optionally implement `plan(g, resume, dry_run)` returning a `RunPlan`: that is what
  `nf-meta run --dry-run` prints. Without it, a dry run with your runner says it isn't supported.

To run steps with Nextflow the way the built-in runner does, reuse its pieces:
`nf_meta.runner.spec.build_step_spec` turns a step (with references resolved) into a `StepSpec`
(params, configs, profiles, launch and work folders), and `nf_meta.runner.engines.engine_for(
step.type).build(spec)` gives the `StepCommand` (argv, folder, environment) to execute.

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
