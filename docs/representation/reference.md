# Config reference

Key-by-key reference for the metapipeline `.yaml` format. See
[YAML representation overview](overview.md) for how these fit together and
[Cross-workflow references](interpolation.md) for the `${...}` syntax usable in `params`
values.

## Top level

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `config_version` | string | yes | — | Must be between `0.0.1` and the current maximum (`0.3.0`). Rejected outside that range. |
| `workflows` | mapping (id → workflow) | yes | — | See [Workflow (common fields)](#workflow-common-fields) below. A list form exists for backward compatibility but is deprecated. |
| `globals` | mapping | no | none | See [`globals`](#globals) below. |
| `transitions` | list | no | none | Legacy edge list (`{source, target}` pairs). Deprecated in favor of each workflow's own `from:`; still readable but triggers a warning. |

## `globals`

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `profile` | string | no | none | Nextflow `-profile` applied to every workflow that doesn't set its own `profile`. Whitespace is stripped. |
| `config_file` | path to an existing `.config` file | no | none | Passed as a Nextflow `-c` to every workflow, in addition to any per-workflow `config_file`. |
| `params` | mapping (str → scalar) | no | none | Merged under each workflow's own `params`, with the workflow's values taking precedence on key collision. Values must be `str`/`int`/`float`/`bool`. |
| `nextflow_version` | string, int, or float | no | none | e.g. `"25.10"`, `"25.10.4-edge"`, `25`. Checked against the actually-installed `nextflow -version` before a run; mismatch is reported, not silently ignored. |

## Workflow (common fields)

Every entry under `workflows:` is one of two types, selected by `type:` (default
`nf-pipeline` when omitted). These fields apply to both:

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `type` | `nf-pipeline` \| `nf-module` | no | `nf-pipeline` | Selects [`NfPipeline`](#nf-pipeline-additional-fields) vs. [`NfModule`](#nf-module-additional-fields) below. |
| *(id)* | — | yes | — | Not a field inside the entry; it's the entry's own key under `workflows:`, e.g. `n01:`. Referenced by `from:`, `${id:params:key}`, and the CLI's `--start`/`--target`. |
| `name` | string, non-empty | yes | — | Pipeline/module name, e.g. `nf-core/rnaseq`. For nf-core pipelines, also used to auto-resolve `url`/`description`. |
| `version` | string, non-empty | yes | — | A release tag (`1.12.0`, `v1.12.0`) or a full/short commit SHA (7-40 hex chars). A branch name (e.g. `dev`, `master`) is rejected, since reproducibility requires a pinned revision. |
| `from` | string or list of strings | no | none | Id(s) of the workflow(s) that must complete before this one runs. Determines execution (DAG) order. |
| `params` | mapping (str → scalar) | no | none | Passed to the pipeline as `-params-file`. Values must be `str`/`int`/`float`/`bool`; real types are preserved through to the generated params file, not stringified. May contain `${...}` references (string values only). |
| `config_file` | path to an existing `.config` file | no | none | Workflow-specific Nextflow `-c`, in addition to `globals.config_file`. |

## `nf-pipeline` additional fields

For a `nextflow run`-style pipeline step (the default `type`):

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `url` | string | conditional | auto-resolved for nf-core pipelines | Required for non-nf-core pipelines (must start with `https://`). For an nf-core pipeline matched by `name`, auto-filled from the nf-core pipeline list; an explicit mismatching `url` is rejected. |
| `description` | string | no | auto-filled for nf-core pipelines | Free text; auto-populated from nf-core's own description when available. |
| `params_file` | path to an existing `.yaml`/`.yml` file | no | none | An external base params file. Merged with `params` at run time (`params` overrides on key collision) and included in schema validation. |
| `profile` | string | no | none | Overrides `globals.profile` for this workflow specifically. |
| `main_script` | string | no | none | Alternate entry script within the pipeline repo. Not settable for nf-core pipelines. |

## `nf-module` additional fields

For a `nextflow module run`-style step:

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `container_engine` | `docker` \| `singularity` \| `conda` \| `podman` | no | none | Passed as `-with-<engine>`. |

## Legacy `transitions:` entries

Each entry is `{source: <id>, target: <id>}`, equivalent to adding `from: <source>` to the
`target` workflow. Prefer `from:` in new configs; opening and saving a config with legacy
`transitions:` in the editor rewrites it automatically.
