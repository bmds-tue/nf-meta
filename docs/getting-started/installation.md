# Installation

## From PyPI

The package is published to the [Python Package Index](https://pypi.org/project/nf-meta/) and can be installed with your favorite dependency tool:

```bash
# with pip
pip install nf-meta

# with uv
uv add nf-meta
```

!!! note
    nf-meta orchestrates [Nextflow](https://nextflow.io) runs. It does not bundle
    Nextflow itself. Running a metapipeline (`nf-meta run`) requires a working `nextflow`
    on `PATH`, matching whatever `globals.nextflow_version` your config declares (if set).
    Validating a config (`nf-meta validate`) does not require Nextflow to be installed.

## Development setup

See [Contributing → Development setup](../contributing.md#development-setup) for installing from
a clone and running the editor in dev mode.
