# YAML representation overview

The nf-meta toolkit allows representing a metapipeline of individual Nextflow pipeline or module steps, as a single
`.yaml` file.
The top-level keys of the YAML are:

- **`config_version`** pins the format this document follows, so the representation can
  evolve without breaking older configs. See [Config reference](reference.md) for the
  supported range.
- **`steps`** is a mapping of step id to step definition. Each step is one Nextflow pipeline
  or module run. The flow between steps is declared per step via `from:`. (Configs from before
  0.5.0 call this key `workflows`; it is still read, see
  [Old key names](reference.md#old-key-names).)
- **`globals`** holds settings applied to every step (Nextflow version, profile, shared
  params, ...).
- **`inputs`** declares values supplied when the metapipeline runs, such as the sample sheet.
  See [Inputs](inputs.md).

## Example

```yaml
config_version: 0.5.0
globals:
  nextflow_version: "25.10"
steps:
  n01:
    name: nf-core/fetchngs
    version: 1.12.0
    params:
      input: ${inputs:fetchngs_ids}
      outdir: out_fetchngs
      nf_core_pipeline: rnaseq
      nf_core_rnaseq_strandedness: auto
  n02:
    from: n01
    name: nf-core/rnaseq
    version: 3.14.0
    params:
      input: ${n01:params:outdir}/samplesheet/samplesheet.csv
      genome: GRCh38
      outdir: out_rnaseq
```

Step `n01` runs the nf-core/fetchngs pipeline first, reading its samplesheet via an [input](inputs.md) declaration.
The step `n02` (nf-core/rnaseq) runs after `n01` (nf-core/fetchngs) as ordered by the `from: n01`.
It reads reads its input from `n01`'s own `outdir` param via the reference `${n01:params:outdir}`. 
See [Cross-step references](interpolation.md) for the full syntax.
A reference is checked topologically, and against both pipeline's metadata, if a `nextflow_schema.json` can be accessed.

## Configs from a URL

`nf-meta run` and `nf-meta editor` also take a config's URL, so a published metapipeline runs
without downloading it first:

```bash
nf-meta run https://raw.githubusercontent.com/<org>/<repo>/<commit>/metapipeline.yaml --out results
```

A config from a URL has no folder of its own, so:

- `--out` is required for `run`;
- relative `params_file`/`nf_config` paths in it are an error (use absolute paths, download the
  files, or make them [inputs](inputs.md));
- the editor never writes back to the URL. Before the first change, the editor asks to save the metapipeline locally.

## Developing a pipeline locally

While you write a pipeline of your own (for example a small connector between two nf-core
pipelines), a step can run it from a local folder with `path:` instead of `url:` and `version:`:

```yaml
steps:
  n02:
    name: fetchngs2rnaseq
    path: ../pipelines/fetchngs2rnaseq   # relative to this config's folder
    from: n01
```

nf-meta runs `nextflow run <folder>` and reads the param schema from the folder's
`nextflow_schema.json`. The folder must hold `main.nf` (or the step's `main_script`). With
`--resume`, a change to the pipeline's files re-runs the step.

!!! warning "Not reproducible"
    A config referencing a local pipeline only runs where that folder exists and its code can change
    between runs, so `validate`, `run` and the editor always warn about it. To share the
    metapipeline, publish the pipeline to a public repository described with `url:` and `version:`.

## Validating and running

```bash
nf-meta validate metapipeline.yaml   # static + schema checks
nf-meta run metapipeline.yaml        # executes the chain in dependency order, requires Nextflow
```

As the name indicates, `nf-meta validate` checks the correctness of a metapipeline config.
It checks if the YAML shape, i.e. top-level keys described by the [schema](#editor-autocompletion-json-schema)
and individual steps, represented by Pydantic models, parse correctly.
It also validates the urls and versions of steps, as well as graph topology, references and input declarations.
Where available, the pipeline metadata in the form of nextflow schemas is used to further validate
the individual param declarations.

See the [quickstart](../getting-started/quickstart.md) for a minimal end-to-end walkthrough,
and [Runners](../runners/index.md) for more information

## Editor autocompletion (JSON Schema)

nf-meta publishes a [JSON Schema](https://json-schema.org/) for static checks of the config format. 
It can be used to drive inline validation and autocomplete in editors that support the
[`yaml-language-server` schema convention](https://github.com/redhat-developer/yaml-language-server).

The schema only covers the config's _static_ shape: Top-level keys, per-workflow fields like
`name`/`version`/`from`, required-ness, types. 
Since nf-meta describes a structurally flexible declaration format, the schema has **no way** to know
what's valid inside a given workflow's `params:`.

Any config saved through the editor has the following line added automatically, which enables these static checks
in VSCode when using the YAML extension (`redhat.vscdoe-yaml`):
```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/bmds-tue/nf-meta/refs/heads/main/schemas/metapipeline.schema.json
steps:
  ...
```

To utilize it in VSCode:

1. Install the [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml)
   (`redhat.vscode-yaml`).
2. Point the extension at the nf-meta schema: `# yaml-language-server: $schema=...`
3. Start typing, see static validation hints, and use `Ctrl+Space` to auto-complete keys

The schema can be re-generated via an `nf-meta` installation and the extension be pointed at a local path.

```bash
nf-meta export-schema schemas/metapipeline.schema.json
```
