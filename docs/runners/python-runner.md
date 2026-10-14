# Python runner

`RUNNER_NAME = "python"` (the default). Executes a metapipeline directly from this Python
process: for each workflow in dependency (DAG) order, it builds and runs the corresponding
`nextflow run` or `nextflow module run` command as a subprocess, streaming its output.

## Caching and `--resume`

Each workflow's *resolved* params (after substituting any `${...}` references) are cached
under `--cachedir` (default `.nf-meta-cache/`), keyed by the workflow and a content hash of
its definition. `nf-meta run --resume`:

- skips a workflow entirely if its working directory already recorded a successful prior run
- still passes `-resume` through to Nextflow for workflows that do run, so a partially-completed
  step doesn't restart from scratch either

This means a failure partway through a long chain doesn't require re-running everything that
already succeeded; only the failing step onward, once fixed.

## Subsetting with `--start`/`--target`

`--start <id>` / `--target <id>` run only the sub-DAG between two workflow ids (inclusive).
Cross-boundary references (a workflow inside the subset referencing one excluded from it) are
validated before anything runs: if the excluded workflow has no successful cached run to read a
resolved value from, the runner refuses to start rather than fail partway through.

## `--stub`

Passes `-stub` to Nextflow, replacing each process's script with a no-op stub, which is useful
for validating a metapipeline's structure and parameter wiring without real compute. Note:
nf-meta places `-stub` after the pipeline's URL/revision in the generated Nextflow command
deliberately, working around a Nextflow CLI argument-order bug (reported upstream) where
`-stub` placed immediately before another option can cause Nextflow to resolve the wrong
pipeline.

## Global params merging

`globals.params` is merged into each workflow's own `params` before the run (the workflow's
own values win on key collision). This happens after caching, so the cache only ever holds
workflow-specific resolved values.
