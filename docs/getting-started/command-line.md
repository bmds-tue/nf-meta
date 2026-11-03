# Command line

`nf-meta` has four commands. `nf-meta <command> --help` lists every option.

## `nf-meta validate`

```bash
nf-meta validate metapipeline.yaml
nf-meta validate https://raw.githubusercontent.com/<org>/<repo>/<commit>/metapipeline.yaml
```

Checks a config without running it: its shape, references and inputs, and each step against its
pipeline's or module's schema (this needs the network). Problems are listed with their line,
their place in the config and a message; the exit code is 1 if there is an error.

`--scope step` or `--scope globals` checks a snippet instead of a whole config: one step's or the
`globals` fields at the root of the file.

## `nf-meta run`

```bash
nf-meta run metapipeline.yaml [--resume] [--out DIR] [--input NAME=VALUE ...]
```

Runs the steps in dependency order. The main options:

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

See [Running a metapipeline](../runners/python-runner.md) for what each does in detail.

## `nf-meta editor`

```bash
nf-meta editor [metapipeline.yaml]
```

Starts the [editor](../editor/index.md) and opens it in the browser.

| Option | Effect |
|---|---|
| `--port PORT` | The port to listen on (a free one if omitted). |
| `--host HOST` | The address to listen on (default `127.0.0.1`). |
| `--no-browser` | Don't open a browser; open the printed link yourself. |
| `--no-redirect-file` | Open the link directly, for browsers on another machine (VS Code Remote, dev containers). |

## `nf-meta export-schema`

```bash
nf-meta export-schema [OUTPUT]
```

Writes the config format's JSON Schema (default: `schemas/metapipeline.schema.json`), for
editor completion and checks; see
[Editor autocompletion](../representation/overview.md#editor-autocompletion-json-schema).
