# nf-meta

**A reproducible representation, runner, and editor for metapipelines**:
Create chains of existing [Nextflow](https://nextflow.io) pipelines and modules in an interactive browser-based editor and export into a YAML-based representation format.
Validate and run the representation format with the integrated CLI tooling.

<div class="feature-list" markdown>

:material-replay:{ .lg .middle } **End-to-end Reproducibility**
:   Community projects like [nf-core](https://nf-co.re) curate a large number of reproducible best-practice pipelines,
    but projects frequently require running many pipelines back to back to produce insights.
    This typically involves ad-hoc scripting or manual intervention to start the next step, breaking the end-to-end reproducibility.

    **`nf-meta` represents the chain of analysis steps as a single `.yaml` file, declaring how one pipeline's outputs are consumed by the next to restore reproducibility.**

:material-wrench:{ .lg .middle } **Reduce complexity of pipelines**
:   Pipelines should focus on their core analysis objective, instead of
    being concerned with what could possibly be run before or after.
    To facilitate multi-step analyses, there is pressure on individual pipelines to incorporate connection logic,
    potentially increasing their complexity and ultimately the maintenance burden.

    **`nf-meta` allows moving the connecting logic outside the scope of individual pipelines to reduce their complexity.**

:material-robot:{ .lg .middle } **Runnable Provenance**
:   Delegating data analysis work to agentic systems can take work off the shoulders of researchers.
    However, the interpretation of results requires knowing what exactly was run by the agent.

    **`nf-meta` can provide provenance of what was run that can be re-run if needed.**

:material-check:{ .lg .middle } **Harnessing by Validation**
:   Agentic systems can handle the details of workflows like versions and param types better when given mechanisms to query for metadata and validate produced artifacts,
    rather than relying only on their internal state.

    **`nf-meta` offers metadata retrieval, caching of the important information, as well as upfront validation.**

:material-repeat:{ .lg .middle } **Automate the Repetitive**
:   Some project types require frequently running the same set of workflows in sequence.
    While the transitions are well defined, this requires manual intervention at every step.

    **`nf-meta` offers a way to represent the full sequence of workflows with automated handoffs, and run it over the weekend.**

</div>


## At a glance

```yaml
config_version: 0.3.0
workflows:
  n01:
    name: nf-core/fetchngs
    version: 1.12.0
    params:
      input: samples.csv
      outdir: out_fetchngs
  n02:
    from: n01
    name: nf-core/rnaseq
    version: 3.14.0
    params:
      input: ${n01:params:outdir}/samplesheet/samplesheet.csv
      outdir: out_rnaseq
```

```bash
nf-meta validate metapipeline.yaml   # catch problems before running anything
nf-meta run metapipeline.yaml        # execute the chain in dependency order
nf-meta editor metapipeline.yaml     # or edit it visually instead
```

## What you get

- **Validation before running.** Static checks (does this reference a real workflow and
  param?) and, where reachable, checks against each pipeline's own `nextflow_schema.json`,
  before any compute is spent.
- **Cross-workflow references**, so step N+1's params can point at step N's own resolved
  values instead of duplicating them.
- **A visual editor** for building and updating configs as a graph, with full undo/redo,
  instead of hand-editing YAML.
- **Pluggable runners**, so how the chain actually executes (wrap `nextflow` locally today,
  compile to one script or drive Seqera Platform tomorrow) is separate from the representation
  itself.

## Next

- [Install](getting-started/installation.md) and run the [quickstart](getting-started/quickstart.md).
- Read the full [config reference](representation/reference.md).
- See [why this is beta](https://github.com/bmds-tue/nf-meta#readme) and browse
  [example metapipelines](https://github.com/bmds-tue/nf-meta-showcases).

