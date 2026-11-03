# Installation

## From PyPI

The package is published to the [Python Package Index](https://pypi.org/project/nf-meta/) and can be installed with your favorite dependency tool:

```bash
# with pip
pip install nf-meta

# as a command-line tool with uv
uv tool install nf-meta

# as a dependency of your project with uv
uv add nf-meta
```

nf-meta needs Python 3.12 or later.

!!! note
    nf-meta orchestrates [Nextflow](https://nextflow.io) runs. It does not bundle
    Nextflow itself. Running a metapipeline (`nf-meta run`) requires a working `nextflow`
    on `PATH`, matching whatever `globals.nextflow_version` your config declares (if set).
    Steps of type `nf-module` need Nextflow 26.04 or later (`nextflow module run`).
    Validating a config (`nf-meta validate`) and the editor (`nf-meta editor`) don't need
    Nextflow.

## Development setup

See [Contributing → Development setup](../contributing.md#development-setup) for installing from
a clone and running the editor in dev mode.
