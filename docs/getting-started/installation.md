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

!!! note
    nf-meta orchestrates [Nextflow](https://nextflow.io) runs. The PyPI package does not bundle
    Nextflow, so running a metapipeline (`nf-meta run`) requires a working installation
    on `PATH`.
    Steps of type `nf-module` need Nextflow 26.04 or later (`nextflow module run`).
    Validating a config (`nf-meta validate`) and the editor (`nf-meta editor`) don't need
    Nextflow.

## Development setup

See [Contributing → Development setup](../contributing.md#development-setup) for installing from
a clone and running the editor in dev mode.
