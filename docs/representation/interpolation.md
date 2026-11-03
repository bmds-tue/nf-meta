# Cross-step references

A param value can take the value of another step's param:

```
${<step-id>:<namespace>:<key>}
```

For example, `input: ${n01:params:outdir}/samplesheet/samplesheet.csv` takes `n01`'s `outdir`
param and puts it into `n02`'s `input` param at run time.

- **`<step-id>`** is the id of another step under `steps:` in the same config.
- **`<namespace>`**: only `params` is supported today. `outputs` is reserved for a future
  capability (referencing a pipeline's declared outputs rather than its params).
- **`<key>`** is the referenced step's param name. It may be a param the step sets itself, or
  one an [input](inputs.md) fills.

A param value can contain **one** step reference, with any text around it
(`results/${n01:params:outdir}/n02`). A value with two references is an error. (To take a value
from the person running the metapipeline instead, use an [input](inputs.md):
`${inputs:<name>}`.)

## The flow between steps

A reference also means "run after": the referenced step must finish first. Steps declare that
with `from:`, and a reference to a step that isn't upstream is an error. The editor and the
Python API add the needed `from:` entries when a step is saved, so you only pick the reference.
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
