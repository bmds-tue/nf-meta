# nf-meta: metapipeline representation, editor, and runner

A reproducible representation for Nextflow metapipelines — chains of nf-core/Nextflow pipeline
and module runs — with an interactive browser-based editor and a CLI validator/runner.

**This is a beta version: things can be unstable and change.**

📖 **[Documentation](https://bmds-tue.github.io/nf-meta/)** — installation, quickstart, the
full config reference, and the API reference.

Find a growing collection of examples in the dedicated
[showcase repository](https://github.com/bmds-tue/nf-meta-showcases/tree/main).

![nf-meta editor](assets/nf-meta-screenshot.png)

## Representation

A metapipeline is a `.yaml` file. The most important keys are:

* `config_version` — allows the representation to change over time without breaking
* `workflows` — the nextflow / nf-core pipeline _runs_. The flow from workflow to workflow is
  described by each workflow's own `from:` key
* `globals` — settings that apply to all workflows

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

Fields can reference another workflow's own params, so you write
`input: ${n01:params:outdir}/samplesheet/samplesheet.csv` instead of hardcoding
`input: fetchngs_out/samplesheet/samplesheet.csv`.

See the [config reference](https://bmds-tue.github.io/nf-meta/latest/representation/reference/)
for every key, and [cross-workflow references](https://bmds-tue.github.io/nf-meta/latest/representation/interpolation/)
for the full `${...}` syntax.

## Runners

Currently:
* **Python runner** — wraps `nextflow` commands, executes in DAG order.

Planned:
1. [nf-cascade](https://github.com/mahesh-panchal/nf-cascade/) runner — convert the config into
   one daisy-chained Nextflow script.
2. Seqera Platform runner — start and monitor locally, calling a Platform instance's API with
   run parameters to handle running Nextflow.
3. Meta-pipeline runner — compile the config into a new monolithic Nextflow project that
   imports the required workflows, for the most efficient orchestration and graceful error
   handling.

Runners are pluggable — see the [runner docs](https://bmds-tue.github.io/nf-meta/latest/runners/)
to write your own.

## Install from PyPI

```bash
# with pip
pip install nf-meta

# with uv
uv add nf-meta
```

See the [docs](https://bmds-tue.github.io/nf-meta/) for the development setup, the editor, and
the full API reference.
