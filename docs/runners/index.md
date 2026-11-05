# Runners

A runner executes a validated metapipeline. `nf-meta run --runner <name>` selects one (default
`python`); runners are registered `BaseRunner` subclasses, and other packages can add their own.

## Python runner

`nf-meta run` uses the Python runner (`--runner python`, the default). It runs the steps in
dag order from this Python process, each as a `nextflow run` (pipelines) or
`nextflow module run` (modules) subprocess, and streams their output.

```bash
nf-meta run metapipeline.yaml                 # run everything
nf-meta run metapipeline.yaml --resume        # skip what already succeeded, resume the rest
nf-meta run metapipeline.yaml --dry-run       # print each step's command and params, run nothing
```

### Where results go

Every step runs in one **out dir**: `nf-meta-out/` next to the config, or the folder given with
`--out`. A relative `outdir` param therefore lands inside it, and references to an upstream
step's `outdir` find its results there.

```
nf-meta-out/                       every step's Nextflow launch folder
  out_fetchngs/  out_rnaseq/  ...  relative step outdirs
  work/                            Nextflow's work dir (-w), shared by all steps
  .nf-meta/
    steps/<id>_<step key>/         params.yaml, nextflow.log, OUT.txt, ERROR.txt
    nextflow/<id>/                 the step's own Nextflow history and task cache
    inputs.yaml                    the input values of the last run (for --input-mode reproduce)
```

Relative input paths in params are made absolute against the config's folder before a step
runs, so they work from the out dir: a param counts as an input path when its schema declares a
path, or when its value names a file or folder that exists in the config's folder. `outdir`,
URLs and references are left alone. See
[Paths](../representation/reference.md#paths).

A step that fails stops the run: later steps don't start, and the message names the step's
folder under `.nf-meta/steps/` with its Nextflow log.

### Resume

`nf-meta run --resume` works on two levels.

**1. Steps (nf-meta).** A step is **skipped** when it already finished successfully with the
same **step key**. The step key covers everything that defines the step's result:

- the step as configured, after its references are resolved (name, version, params, …);
- the **content** of its `nf_config` and `params_file`, and of the global and `--nf-config`
  configs;
- the `globals`, the `--nf-profile` and `--stub` options;
- the **local input files** its params name: path, size and modification time (for a folder,
  those of its entries);
- for a [local pipeline](../representation/overview.md#developing-a-pipeline-locally), its files;
- the step keys of its upstream steps.

So a change to a step re-runs that step **and every step downstream of it**; steps before it
stay skipped.

**2. Tasks (Nextflow).** A step that does run is started with Nextflow's `-resume`, against that
step's own Nextflow cache (`.nf-meta/nextflow/<id>/`). Nextflow then reuses every task whose
script and inputs are unchanged. A step that failed at task 10 of 15, run again after a fix,
only redoes the tasks the fix affects.

What resume can't see:

- files named **inside** an input file (e.g. the FASTQ files listed in a sample sheet) and files
  named in a `params_file`; only the sample sheet or params file itself counts;
- remote inputs (`https://`, `s3://`);
- tasks **across** steps: each pipeline is one unit for nf-meta. After an upstream step re-ran,
  Nextflow can only reuse a downstream task when its input files are unchanged, which is rare.

### Inputs

Values for the config's [inputs](../representation/inputs.md) come from `--input name=value`
(once per value), `--inputs-file values.yaml`, an input's default, or a prompt. All of them are
collected and checked **before the first step runs**. `--input-mode` decides what happens with
missing ones: `prompt` (ask; the default in a terminal), `fail` (stop with a list; the default
otherwise), or `reproduce` (use exactly the values of the last run).

A changed input value changes the step key, so the steps it reaches re-run.

### Running part of a metapipeline

`--start <id>` and `--target <id>` run only the steps between two steps (inclusive). A step
inside the selection that references a step outside it takes that value from the other step's
last run. If it never ran, the value is asked for like an input, or given as
`--input <step-id>.<param>=<value>`. With `--input-mode reproduce`, the steps outside must have
run before.

### Other options

| Option | Effect |
|---|---|
| `--out DIR` | The out dir (required for a config from a URL). |
| `--dry-run` | Print each step's command and params file without running anything. In `prompt` mode it asks for missing values, so the commands are the real ones; otherwise missing values show as placeholders. |
| `--stub` | Pass `-stub` to Nextflow: each process runs its stub instead of its script, to check the wiring without real compute. |
| `--nf-profile`, `-p` | A Nextflow profile for every step, after the configured ones. |
| `--nf-config`, `-c` | A Nextflow config for every step, taking precedence over the global and step configs. |
| `--output-lines`, `-l` | How many lines of each step's output to show while it runs. |

`globals.params` are merged under each step's own `params` (the step's values win).

## Planned

- **nf-cascade runner**: compile the config into a single daisy-chained Nextflow script,
  delegating orchestration to [nf-cascade](https://github.com/mahesh-panchal/nf-cascade/). A
  stub (`NfCascadeRunner`) exists in the codebase but is not yet implemented.
- **Seqera Platform runner**: start and monitor runs by calling a Seqera Platform instance's
  API with the resolved parameters, rather than shelling out to `nextflow` locally.
- **Meta-pipeline runner**: compile the config into a monolithic Nextflow project that imports the required workflows directly, for the most efficient orchestration and graceful cross-workflow error handling.
- **Notebook runner**: transpile the meta-pipeline config into its most interactive form: A Jupyter notebook moving the Workflow runs closer to your downstream analysis.


## Writing your own

Runners are pluggable via the same entry-point mechanism as third-party packages: a package
registers a `BaseRunner` subclass under the `nf_meta.runners` entry-point group, and it
becomes selectable via `--runner <name>` as soon as it's installed, with no changes to nf-meta
itself. See [Writing a runner plugin](../guides/writing-a-runner.md).
