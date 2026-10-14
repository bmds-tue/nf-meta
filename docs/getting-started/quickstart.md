# Quickstart

This small guide will walk you through the smallest possible metapipeline that actually runs: a single workflow step, that executes the `fetchngs` pipeline to fetch some data from a public repository.
The resulting metapipeline is validated and executed via the CLI.

## Prerequisites

- nf-meta installed (see [Installation](installation.md))
- [Nextflow](https://nextflow.io) installed, required for `nf-meta run` but not for the
  `nf-meta validate` or `editor` commands.

## 1. Write a config

Create `metapipeline.yaml`:

```yaml
config_version: 0.3.0
workflows:
  fetch:
    name: nf-core/fetchngs
    version: 1.12.0
    params:
      input: https://raw.githubusercontent.com/nf-core/test-datasets/2732b911c57e607fa7aea5ba0c3d91b25bafb662/testdata/v1.12.0/sra_ids_test.csv
      outdir: results
```

- `config_version` pins the representation's schema version. See
  [Config reference](../representation/reference.md).
- `fetch` is the workflow's id, which can be referenced by another workflow step (see
  [Cross-workflow references](../representation/interpolation.md)) and while running by `--start`/`--target` on the CLI.
- `name`/`version` uniquely describe an nf-core pipeline. 
For a non-nf-core pipeline, the `url` field is required as well.

## 2. Validate it

```bash
nf-meta validate metapipeline.yaml
```

During validation, first the config shape is checked statically for required keys, references, and graph layout.
The config's static shape is also available as a JSON Schema your editor can check as you type. (See
[Editor autocompletion](../representation/overview.md#editor-autocompletion-json-schema))
Next, `nf-meta` tries to incorporate metadata provided by nf-core as well as in each pipeline's `nextflow_schema.json` file to validate urls, versions, and required parameters or types.
You will get summarized validation feedback with line numbers and keys in your console.

## 3. Run it

```bash
nf-meta run metapipeline.yaml --stub
```

To just see that everything runs as expected, we use Nextflow's stub-run mechanism which replaces each process script with a no-op stub that requires no containers or environment.
This Nextflow run options is resurfaced to the `nf-meta run` cli interface as the `--stub` flag.
This can be useful to confirm the structure and parameter wiring resolves correctly without waiting on real compute or container pulls.

## Next steps

- A metapipeline with more than one steps, chained via references: see
  [YAML representation overview](../representation/overview.md).
- Editing configs visually instead of by hand: see [Editor](../editor/index.md).
- `nf-meta run --resume` and per-workflow caching: see [Python runner](../runners/python-runner.md).
