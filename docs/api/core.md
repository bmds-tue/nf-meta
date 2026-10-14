# Core

## Workflows

`Workflow` is the discriminated union `NfPipeline | NfModule`, selected on each entry's
`type:` field. Internal plumbing (the graph, events, runners) is typed against `Workflow`;
construct a concrete `NfPipeline`/`NfModule` directly, or build one from raw config data via
[`validated_workflow`](#nf_meta.core.config.validated_workflow).

::: nf_meta.core.models.NfPipeline

::: nf_meta.core.models.NfModule

::: nf_meta.core.models.WorkflowType

## Globals and transitions

::: nf_meta.core.models.GlobalOptions

::: nf_meta.core.models.Transition

## The graph

::: nf_meta.core.graph.MetaworkflowGraph

## Parsing, construction, and serialization

Free functions at the config-file-format boundary: parsing raw YAML-shaped dicts,
constructing/validating individual workflows or a whole graph from them, and serializing a
graph back to a dict or file.

::: nf_meta.core.config.from_file

::: nf_meta.core.config.to_file

::: nf_meta.core.config.dump_config

::: nf_meta.core.config.validated_graph

::: nf_meta.core.config.validated_workflow

::: nf_meta.core.config.validated_globals

## Errors and diagnostics

::: nf_meta.core.errors.Diagnostic

::: nf_meta.core.errors.Severity

::: nf_meta.core.errors.ConfigValidationError

::: nf_meta.core.errors.GraphValidationError
