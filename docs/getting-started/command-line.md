# Command line

`nf-meta` has four subcommand commands. `nf-meta <command> --help` lists every option.

## `nf-meta validate`

```bash
nf-meta validate metapipeline.yaml
nf-meta validate https://raw.githubusercontent.com/<org>/<repo>/<commit>/metapipeline.yaml
```

Checks a config without running it, validating its YAML keys, the references between steps,
global inputs, and also validates each pipeline against a schema if one exists.
The retrieval of the pipeline schema requires a network connection, but will enable confirming
urls and verison extist, required params are given, and all params have the correct type.
Problems are listed by line and key in the YAML along with an error message.

By passing `--scope step` or `--scope globals` only a snippet of YAML can be validated,
instead of a whole config.

## `nf-meta run`

```bash
nf-meta run metapipeline.yaml [--resume] [--out DIR] [--input NAME=VALUE ...]
```

Runs the steps in the order declared by the graph. The main options:

| Option | Effect |
|---|---|
| `--resume` | Skip steps that already succeeded unchanged; resume Nextflow's tasks for the rest. |
| `-o`, `--out DIR` | Where to run and write results (default: `nf-meta-out` next to the config). |
| `-i`, `--input NAME=VALUE` | A value for an input (once per value), or `<step-id>.<param>` for a step outside the run. |
| `--inputs-file FILE` | Input values as a YAML mapping. |
| `--input-mode prompt\|fail\|reproduce` | What to do with values the run needs but doesn't have. |
| `-s`, `--start ID`, `-t`, `--target ID` | Run only the steps from one step to another. |
| `--dry-run` | Print each step's command and params file, run nothing. |
| `--stub` | Pass `-stub` to Nextflow. |
| `-p`, `--nf-profile`, `-c`, `--nf-config` | A Nextflow profile or config for every step. |

See [Runners](../runners/index.md#python-runner) for what each does in detail.

## `nf-meta editor`

```bash
nf-meta editor [metapipeline.yaml]
```

Starts the [editor](../editor/index.md) and opens it in the browser.

| Option | Effect |
|---|---|
| `--port PORT` | The port to listen on (a free one if omitted). |
| `--host HOST` | The address to listen on (default `127.0.0.1`). |
| `--no-browser` | Do not attempt to open in a browser automatically |
| `--no-redirect-file` | Do not write a redirect file. (e.g. in a remote session) Requires opening the link manually. |

## `nf-meta export-schema`

```bash
nf-meta export-schema [OUTPUT]
```

Exports the config format's JSON Schema (default: `schemas/metapipeline.schema.json`) to a file.
See [Editor autocompletion](../representation/overview.md#editor-autocompletion-json-schema) for how to use it in VSCode.
