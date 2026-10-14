# Runners

A runner takes a validated metapipeline graph and actually executes it. nf-meta selects a
runner by name (`nf-meta run --runner <name>`, default `python`) and dispatches to a
registered `BaseRunner` subclass.

## Available today

- **[Python runner](python-runner.md)** (`python`, default): wraps `nextflow run`/`nextflow
  module run` per workflow from this Python process, in DAG order.

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
itself. See [Writing a runner](../guides/writing-a-runner.md).
