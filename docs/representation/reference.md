# Config reference

Key-by-key reference for the metapipeline `.yaml` format. See
[YAML representation overview](overview.md) for how these fit together,
[Cross-step references](interpolation.md) for the `${...}` syntax usable in `params` values, and
[Inputs](inputs.md) for the `inputs:` section.

## Paths

A relative path in a config (`params_file`, `nf_config`, a local pipeline's `path`, path params
and input defaults) is always interpreted as relative to the folder containing the metapipeline config file.
This is regardless of where `nf-meta` is run from with the exception of a step's `outdir` which is relative
to the run's output folder (`--out`, see [Where results go](../runners/index.md#where-results-go)).
Paths are kept as written when saved via the editor.

## Top level YAML keys

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `config_version` | string | yes | — | The format version the config follows, between `0.0.1` and the current `0.5.0`. Saving from the editor writes `0.5.0`. |
| `steps` | mapping (id → step definition) | yes | — | See [Steps](#steps) below. A list form exists for backward compatibility but is deprecated. |
| `globals` | mapping | no | none | See [Globals](#globals) below. |
| `inputs` | mapping (name → input) | no | none | Values supplied when the metapipeline runs. See [Inputs](inputs.md). Requires config_version 0.4.0 or later. |

## Globals

Settings for every step. A step's own settings take precedence over them.

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `nf_profile` | string | no | none | Nextflow `-profile` for every step that doesn't set its own `nf_profile`. Whitespace is stripped. |
| `nf_config` | path to an existing file | no | none | Passed as a Nextflow `-c` to every step, before a step's own `nf_config`. |
| `params` | mapping (str → scalar) | no | none | Merged under each step's own `params`; the step's values win on a key collision. Values must be `str`/`int`/`float`/`bool`. |
| `nextflow_version` | string, int or float | no | none | e.g. `"25.10"`, `"25.10.4-edge"`, `25`. Checked against `nextflow -version` before a run; a mismatch is reported. Steps of type `nf-module` need 26.04 or later. |

## Steps

Every entry under `steps:` is one of two types, selected by `type:`, `nf-pipeline` or `nf-module`.
These fields apply to both:

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| *(id)* | — | yes | — | The steps mapping key under the top-level `steps:`, e.g. `n01:`. Referenced by `from:`, `${id:params:key}` and the CLI's `--start`/`--target`. |
| `type` | `nf-pipeline` \| `nf-module` | no | `nf-pipeline` | Selects the [pipeline](#nf-pipeline-steps) or [module](#nf-module-steps) fields below. |
| `name` | string, non-empty | yes | — | Pipeline or module name, e.g. `nf-core/rnaseq`. An `nf-core/…` name must be in the nf-core catalog; its `url` and `description` are filled in from it. |
| `version` | string | yes (except for a local pipeline) | — | A release tag (`1.12.0`, `v1.12.0`) or a commit hash. A branch name (`dev`, `master`) is rejected, since a reproducible run needs a pinned revision. Use the full 40-character hash: Nextflow 26 can't fetch abbreviated ones (a warning says so). |
| `from` | string or list of strings | no | none | Id(s) of the steps that must finish before this one runs. Saving a step that references another step's params adds the edge it needs. |
| `params` | mapping (str → scalar) | no | none | Passed to Nextflow in a params file. Values must be `str`/`int`/`float`/`bool` and keep their types. A value may be one [step reference](interpolation.md) (with text after it) or one whole [input reference](inputs.md). |
| `nf_config` | path to an existing file | no | none | The step's own Nextflow `-c`, after `globals.nf_config`. |


### `nf-pipeline` steps

For a `nextflow run` pipeline (the default `type`):

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `url` | string | for non-nf-core pipelines | from the nf-core catalog | The pipeline's repository (`https://…`). For an nf-core pipeline it is filled in from the catalog; a different `url` is rejected. |
| `path` | path to a folder | no | none | A **local pipeline folder, for development**, used instead of `url` and `version`. See [Developing a pipeline locally](overview.md#developing-a-pipeline-locally). Not for nf-core pipelines. |
| `description` | string | no | from the nf-core catalog | Free text. |
| `params_file` | path to an existing `.yaml`/`.yml` file | no | none | Base params, merged under `params` (`params` wins on a key collision) and included in the params check. |
| `nf_profile` | string | no | none | Overrides `globals.nf_profile` for this step. |
| `main_script` | string | no | none | Another entry script of the pipeline (`-main-script`). Not for nf-core pipelines. |

### `nf-module` steps

For a `nextflow module run` step (Nextflow 26.04 or later):

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `container_engine` | `docker` \| `singularity` \| `conda` \| `podman` | no | none | Passed as `-with-<engine>`. Without it (and without a global `nf_config`), a warning says the module runs without a container. |

!!! warning "Not fully supported yet"
    Modules can only be run as leaf-nodes in the metapipeline graph at this time. 
    No steps can refernce from a step of type `nf-module`, yet.

## Key names from previous versions

Configs written for earlier versions still load. Each old form gives a deprecation warning, and
saving from the editor writes the current form.

| Old | Current | Since |
|---|---|---|
| `workflows:` | `steps:` | config_version 0.5.0 |
| `config_file` | `nf_config` | config_version 0.4.0 |
| `profile` | `nf_profile` | config_version 0.4.0 |
| `steps:` as a list of entries with their own `id` | a mapping keyed by id | earlier versions |
| top-level `transitions:` (`{source, target}` pairs) | each step's `from:` | earlier versions |
