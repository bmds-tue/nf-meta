# YAML representation overview

The nf-meta tooling allows representing a metapipeline, a chain of Nextflow pipeline/module runs, as a single
`.yaml` file.
The four top-level keys are:

- **`config_version`** pins the schema this document follows, so the representation can
  evolve without breaking older configs. See [Config reference](reference.md) for the
  supported range.
- **`workflows`** is a mapping of workflow id to workflow definition. Each entry is one
  Nextflow pipeline or module run. The flow between workflows is declared per-workflow via
  `from:`, not as a separate edge list.
- **`globals`** holds settings applied to every workflow (Nextflow version, profile, shared
  params, ...).
- **`transitions`** *(deprecated)* is an older, separate edge-list format, superseded by each
  workflow's own `from:` key. It's still readable, but nf-meta logs a deprecation warning and
  rewrites it to `from:` the next time the config is saved via the editor.

## Example

```yaml
config_version: 0.3.0
globals:
  nextflow_version: "25.10"
workflows:
  n01:
    name: nf-core/fetchngs
    version: 1.12.0
    params:
      input: fetchngs-ids.csv
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

The step `n02` runs after `n01` (`from: n01`) and reads its input from `n01`'s own `outdir` param via
the reference `${n01:params:outdir}`. 
See [Cross-workflow references](interpolation.md) for the full syntax.
A workflow reference is validated in statically by checking if the connection is possible topologically.
An attempt is made to check the workflow references also against each pipeline's own `nextflow_schema.json` to validate the parameter correctness and types.

## Validating and running

```bash
nf-meta validate metapipeline.yaml   # static + schema checks
nf-meta run metapipeline.yaml        # executes the chain in dependency order, requires Nextflow
```

`nf-meta validate` is the authoritative check: it runs the real Pydantic models plus the
tier-2 pipeline-schema checks described above. The config's static shape is also published as a
[JSON Schema](#editor-autocompletion-json-schema), so your editor can catch structural problems
(missing/unknown fields, wrong types) as you type, before you even run `validate`. It won't
catch the `params:`-level checks though, since those need a network lookup against the
pipeline's own schema.

See the [quickstart](../getting-started/quickstart.md) for a minimal end-to-end walkthrough,
and [Runners](../runners/index.md) for what "executes" actually means (currently: wraps
`nextflow run`/`nextflow module run` per workflow, in DAG order).

## Editor autocompletion (JSON Schema)

nf-meta publishes a [JSON Schema](https://json-schema.org/) for the config format. It's what
powers inline validation and autocomplete in editors that support the
[`yaml-language-server` schema convention](https://github.com/redhat-developer/yaml-language-server).
VS Code's [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml)
is the common case.

The schema only covers the config's _static_ shape: Top-level keys, per-workflow fields like
`name`/`version`/`from`, required-ness, types. 
Since this is a structurally flexible declaration format, the schema has **no way** to know what's valid inside a given
workflow's `params:`. 
That's checked against the pipeline's own `nextflow_schema.json` when `nf-meta validate` is called. 
This _dynamic_ validation via the cli command gives you information about lines and keys where something is wrong,
but you cannot currently use this in your text editor.


Any config saved through the editor has this line added, which enables the static validation in VSCode with the YAML extension (`redhat.vscdoe-yaml`) by pointing to the JSON-schema:
```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/bmds-tue/nf-meta/refs/heads/main/schemas/metapipeline.schema.json
workflows:
  ...
```


To utilize it in VSCode:

1. Install the [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml)
   (`redhat.vscode-yaml`).
2. Add the same `# yaml-language-server: $schema=...` line as the first line of your `.yaml`
   file.
3. Start typing. Unknown keys, missing required fields, and wrong types are flagged inline,
   and `Ctrl+Space` completes valid keys/enum values.


The schema can be re-generated locally with your `nf-meta` installation.

```bash
nf-meta export-schema schemas/metapipeline.schema.json
```

The `$schema=...` can also point at a local path relative to the config file instead of the GitHub URL.
