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
    nf-meta orchestrates [Nextflow](https://www.nextflow.io/) runs. It does not bundle
    Nextflow itself. Running a metapipeline (`nf-meta run`) requires a working `nextflow`
    on `PATH`, matching whatever `globals.nextflow_version` your config declares (if set).
    Validating a config (`nf-meta validate`) does not require Nextflow to be installed.

## Development setup

Clone the repository and install with the dev dependency group:

```bash
git clone https://github.com/bmds-tue/nf-meta
cd nf-meta
uv sync --group dev
```

### Editor frontend

The browser editor's frontend lives under `src/nf_meta/editor/frontend` and runs as a separate node server during development:

```bash
cd src/nf_meta/editor/frontend
npm install
npm run dev
```

With the frontend dev server running, launch the CLI in dev mode so it proxies to it instead of the bundled build:

```bash
NF_META_DEVMODE=1 uv run nf-meta editor [</path/to/metapipeline.yml>]
```

### Running the tests

```bash
uv run pytest
```
