# Quickstart

This small guide walks you through the smallest metapipeline that actually runs: a single step that executes the `fetchngs` pipeline to fetch some data from a public repository.
The resulting metapipeline is validated and executed via the CLI.

## Prerequisites

- nf-meta installed (see [Installation](installation.md))
- [Nextflow](https://nextflow.io) installed, required for `nf-meta run` but not for the
  `nf-meta validate` or `editor` commands.

## 1. Write a config

Create `metapipeline.yaml`:

```yaml
config_version: 0.5.0
steps:
  fetch:
    name: nf-core/fetchngs
    version: 1.12.0
    params:
      input: https://raw.githubusercontent.com/nf-core/test-datasets/2732b911c57e607fa7aea5ba0c3d91b25bafb662/testdata/v1.12.0/sra_ids_test.csv
      outdir: results
```

- `config_version` pins the representation's schema version. See
  [Config reference](../representation/reference.md).
- `fetch` is the step's id. Other steps reference it (see
  [Cross-step references](../representation/interpolation.md)), and `--start`/`--target` select
  it on the command line.
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

The results land in `nf-meta-out/results/` next to the config: every step runs in the out dir
(`--out` sets another one).

## Next steps

- A metapipeline with more than one step, chained via references: see
  [YAML representation overview](../representation/overview.md).
- Editing configs visually instead of by hand: see [Editor](../editor/index.md).
- Leaving values such as the sample sheet to the person running it: see
  [Inputs](../representation/inputs.md).
- Where results go and how `nf-meta run --resume` decides what to re-run: see
  [Running a metapipeline](../runners/python-runner.md).
