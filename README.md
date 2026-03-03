# nf-meta: metapipeline representation, editor, and runner

This project features a reproducible representation for meta-pipelines, featuring an interactive editor running locally in a browser, as well as a cli based validator and runner.

## Installing latest Release

**TODO**

## Running

**TODO**

## Running Dev Setup

Run the frontend
```
$ cd /src/nf_meta/editor/frontend
$ npm install
$ npm run dev
```

Run the cli in dev mode
```
NF_META_DEVMODE=1 uv run nf-meta editor [</path/to/metapipeline.yml>]
```

## Project Structure


* Engine: Config Validation, Editor Session with History and exposing API
* Runners
* Editor frontend for creating or editing a config


## Metapipeline Runners

Currently:
* Python Runner: Wraps nextflow commands, exectutes in dag order

Planned:
1. nf-cascade runner: compiles config into one nextflow daisy-chaining nextflow script
2. Seqera Platform runner:
Start and monitor locally, call and poll a Platform instance with run parameters via API to handle running Nextflow
3. Meta-Pipeline runner:
compile config into new monolithic nextflow project, that imports required workflows to achieve most efficient orchestration + graceful errors handling
