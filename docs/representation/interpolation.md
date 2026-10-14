# Cross-workflow references

A param value can reference another workflow's own param via:

```
${<workflow-id>:<namespace>:<key>}
```

For example, `input: ${n01:params:outdir}/samplesheet/samplesheet.csv` takes `n01`'s `outdir`
param and substrings it into `n02`'s `input` param at run time.

- **`<workflow-id>`** must be an id defined under `workflows:` elsewhere in the same config.
- **`<namespace>`**: only `params` is currently supported. `outputs` is reserved syntax for a
  future capability (referencing a pipeline's declared outputs rather than its input params)
  and is not yet resolved.
- **`<key>`** is the referenced workflow's own param name.

## Validation

nf-meta checks references statically as part of `nf-meta validate`/on every graph mutation:
the referenced workflow must exist, and (where the target pipeline's schema is reachable) the
referenced key must be a real parameter on it. A reference to a workflow that doesn't (yet)
exist, or that would only exist "after" the referencing workflow in the DAG, is rejected.

## Resolution at run time

References are only ever resolved inside **string-valued** params. The token is matched via
a regex against the value's text, so a reference can be embedded inside a larger string
(`${n01:params:outdir}/samplesheet/samplesheet.csv`) or be the entire value. Numeric/boolean
param values can never contain a reference, since they can't contain the literal `${...}`
text.

The runner resolves each reference just before executing the referencing workflow, preferring
an already-resolved (or cached, on `--resume`) value for the target workflow over its raw
config value. See [Python runner](../runners/python-runner.md).
