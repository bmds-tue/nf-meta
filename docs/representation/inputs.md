# Inputs

An input is a value the person running the metapipeline supplies: the sample sheet, a genome, a
contrasts file. Inputs keep those values out of the step definitions, so one config runs on new
data without editing it. `nf-meta run` asks for them (or takes them from the command line), and
the editor shows them in its **Inputs** tab.

Inputs need `config_version` 0.4.0 or later.

## Two ways to write one input

An input fills one or more step params. There are two spellings for that binding; use **one** of
them per input.

**In the step's params**, with `${inputs:<name>}` as the whole value:

```yaml
steps:
  n01:
    name: nf-core/fetchngs
    version: 1.12.0
    params:
      input: ${inputs:ids}
      outdir: out_fetchngs
```

This declares the input `ids` on the spot. It gets its type, format and description from the
param it fills (`input` in fetchngs's schema: a `file-path` that must exist).

**In the `inputs:` section**, with `bind:` listing `<step-id>.<param>`:

```yaml
inputs:
  ids:
    description: SRA ids to fetch, one per line
    bind: [n01.input]
steps:
  n01:
    name: nf-core/fetchngs
    version: 1.12.0
    params:
      outdir: out_fetchngs
```

Both mean the same. The `inputs:` section keeps all run-time values in one place at the top of
the config; the params form keeps them next to the step. The editor can move all inputs from one
form to the other.

An input may also be declared in `inputs:` without `bind:` and referenced with
`${inputs:ids}` in params: the declaration then only adds a description, a default or narrower
rules. Several params can reference the same input; they then all get its value.

Rules:

- `${inputs:x}` must be the **whole** value. `"${inputs:dir}/samplesheet.csv"` is an error: the
  input takes its type, checks and prompt from the param it fills, which a partial value can't
  give. (A [step reference](interpolation.md) may have text around it.)
- An input with `bind:` can't also be referenced with `${inputs:...}`.
- A declared input that fills no param gives a warning.

## Keys of an `inputs:` entry

| Key | Notes |
|---|---|
| `bind` | `<step-id>.<param>` entries the input fills. |
| `description` | Shown in prompts and in the editor. |
| `default` | Used when the run gets no value. A relative path is relative to the config's folder. |
| `type` | `string`, `integer`, `number` or `boolean`. |
| `format` | For paths: `file-path`, `directory-path`, `path` (a file or a folder) or `file-path-pattern` (a glob). |
| `exists` | `true`: a path value must exist. |
| `enum` | The allowed values. |
| `pattern` | A regular expression a string value must match. |
| `minimum`, `maximum` | Bounds for numbers. |
| `mimetype`, `schema` | Kept from nf-core schemas, passed through. |

Keys you leave out are **inherited** from the schema of the param the input fills. Keys you set
must narrow that schema, never widen it: an `enum` that picks a few genomes is fine, a `type`
that contradicts the param's is an error. For paths, `file-path` and `directory-path` narrow
`path`; declaring `path` for a param that takes only a `file-path` is an error. When an input
fills several params, their schemas must agree (or one must narrow the other).

## Giving values when running

```bash
nf-meta run metapipeline.yaml --input ids=ids.csv --input genome=GRCh38
nf-meta run metapipeline.yaml --inputs-file values.yaml   # a YAML mapping of name: value
```

Values the run needs but doesn't get are handled by `--input-mode`:

| Mode | Missing values | Given values |
|---|---|---|
| `prompt` (default in a terminal) | asked for before the first step, with selection lists, path completion and checks as you type | used |
| `fail` (default otherwise) | the run stops and lists them | used |
| `reproduce` | the run uses exactly the values of the last run | refused |

Every value is checked against the input's rules before anything runs, and all problems are
reported together. Relative paths given on the command line are relative to the current folder,
as usual for a command; defaults written in the config are relative to the config's folder.

See [Resume](../runners/index.md#resume) for how inputs interact with `--resume`.
