# Inputs

An input is a value that can be supplied at the time of running the metapipeline, such as 
the sample sheet, a genome, a contrasts file. 
Inputs keep those values out of the step definitions, so the same metapipeline config runs on new
data without editing it. `nf-meta run` asks for them (optionally prompting for them), and
the editor displays them in its **Inputs** tab.

## Global and implicit inputs

An input can fill one or more step params and there are two ways to define them.
Use only **one** of them per input.

**Implicitly in the step's params**, with `${inputs:<name>}` instead of writing the value:

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

The second way is **in the `inputs:` section**, with `bind:` listing `<step-id>.<param>`:

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

Both describe the same thing. The `inputs:` section keeps all run-time values in one place at the top of
the config, whereas the params notation keeps them inside the respective step.
The editor can move all inputs from one form to the other.

Whichever method is chosen, the input declaration will fill the **whole** param value and cannot be
embedded in a string, the way a [step reference](interpolation.md) can.

An input may also be declared in `inputs:` without `bind:` and referenced with
`${inputs:ids}` in params. The declaration can then be used to add a description, a default or schema
rules. But an input with `bind:` cannot also be referrenced with `${inputs:...}`.

Several params can reference the same input and will all get its value,
but an unreferenced input leads to a warning.


## Supplying values when running

```bash
nf-meta run metapipeline.yaml --input ids=ids.csv --input genome=GRCh38
nf-meta run metapipeline.yaml --inputs-file values.yaml   # a YAML mapping of name: value
```

Inputs specified in the metapipeline config, but not supplied via the CLI, are handled according to `--input-mode`:

| `--input-mode` | Missing values | Given values |
|---|---|---|
| `prompt` (default in a terminal) | asked for before the first step, with selection lists, path completion and checks as you type | used |
| `fail` (default otherwise) | the run stops and lists them | used |
| `reproduce` | the run uses exactly the values of the last run | refused |

Every value is checked against the input's rules before anything runs, and all problems are
reported together. Relative paths given on the command line are relative to the current folder,
as usual for a command; defaults written in the config are relative to the config's folder.

See [Resume](../runners/index.md#resume) for how inputs impact re-runs.
