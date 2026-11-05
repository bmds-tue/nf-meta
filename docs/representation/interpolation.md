# Step references

A param value can read the value of another step's param with a construct like this:

```
${<step-id>:<namespace>:<key>}
```
Here, 

- **`<step-id>`** is the id of another step under `steps:` in the same config.
- **`<namespace>`**: only `params` is supported currently.
- **`<key>`** is the referenced step's param name.

For example, `samplesheet: ${n01:params:outdir}/samplesheet/samplesheet.csv` reads the param `outdir` from the step `n01` and uses it to construct the value of `samplesheet` at run time.

Each param value can reference and read from only **one** other param in a predecessor step, a value containing two references parses with an error.
To expose a param value as a metapipline input, instead, use use an [input](inputs.md) `${inputs:<name>}`.

## The flow between steps

A reference requires a directed from the referenced to referencing step.
Steps declare their predecessors with `from:`, and a reference to a step that isn't upstream is an error.
The editor and the Python API add the needed `from:` entries when a step is saved, so you only pick the reference.
A reference that would create a cycle is refused.

## Validation

`nf-meta validate` (and every change in the editor) checks each reference: the step must exist
and be upstream, and the key must be a param of that step (where its schema can be fetched, or
it sets the param itself).

## Resolution at run time

References are resolved in **string** params only, just before the referencing step runs, from
the value the referenced step ran with. A reference to an upstream `outdir` stays relative, so it
points into the run's output folder where that step wrote its results.

When only part of a metapipeline runs (`--start`/`--target`), a reference to a step outside the
run takes the value from that step's last run. If there is none, the run asks for it, or takes
it from `--input <step-id>.<param>=<value>` (see [Running](../runners/python-runner.md)).
