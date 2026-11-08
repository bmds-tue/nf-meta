# Editor

The `nf-meta` package ships a browser-based editor for building and changing metapipeline
configs visually: steps as a graph, schema-based forms for their params, references and inputs
picked from menus, and validation as you edit. Every change is saved to the config file right
away, and the history (undo, redo) takes you back to any earlier state.

![nf-meta editor](nf-meta-screenshot-light.png#only-light)
![nf-meta editor](nf-meta-screenshot.png#only-dark)

## Usage

```bash
# start fresh
nf-meta editor

# or open some existing work
nf-meta editor path/to/metapipeline.yaml
```

`nf-meta editor` runs the editor's backend, which exposes an api and serves a one-page frontend application
that can be accessed from the browser.
It tries to open the frontend as a new tab in your local browser automatically.
You can always access the editor also by copy-pasting the printed url and token in the address bar of
new tab in a local web browser. 

![The browser page talks to the editor backend, which reads and saves the config](editor-local-light.svg#only-light)
![The browser page talks to the editor backend, which reads and saves the config](editor-local.svg#only-dark)

The nf-meta editor backend blocks the terminal by listening to requests until you stop it manually `Ctrl` + `C`
in the terminal or via the **Quit editor** button in the page's file menu.
Every change is gets automatically saved, so nothing is lost either way. 

Started without a config, the editor shows a start screen, asking to open a config, pick one of the configs you recently opened, or
start a new metapipeline. 
The list of recent configs is tracked per user in (`~/.local/state/nf-meta/recent-configs.json`).

A new config, or one opened from a URL (`nf-meta editor https://…`), asks for a path to save to before your first change.
Cancelling leaves the change unsaved and your edit form open.

## Working with the editor

The graph shows the steps and the flow between them; the sidebar on the right has three tabs.
Drag its edge to make it wider.

**Steps.** One card per step; click a node or a card to open it. A step's form has the pipeline
or module (nf-core names and versions are completed from the nf-core catalog), and its params:

- **The params form** is built from the pipeline's `nextflow_schema.json` (or the module's
  `meta.yml`): a field per param, with its type, description and allowed values. "Add param"
  lists the params not set yet, required ones first. **Form/YAML** switches to editing the
  params as YAML, with completion and checks for references and inputs.
- **A reference** (the blue button next to a param) fills the param from another step's param:
  pick the step, then the param. The editor adds the edge between the steps when you save. A
  reference can have text after it, e.g. `/samplesheet/samplesheet.csv`.
- **An input** (the purple button) makes the param a value supplied at run time; see
  [Inputs](../representation/inputs.md).
- **More options** holds the params file, Nextflow config and profile, the main script and, for
  pipelines you develop yourself, a **local folder** instead of the repository (marked "local";
  see [Developing a pipeline locally](../representation/overview.md#developing-a-pipeline-locally)).

Problems show at the field they belong to; a change the checks refuse is not saved.

Warnings don't block a change: an old key name, two steps sharing an outdir, a local pipeline, a
repository that couldn't be checked. The yellow button in the toolbar lists all warnings about the
config, grouped by key. Each step's warnings show as a yellow count on its node: click it to open
the list with that step's warnings marked. Warnings about old key
names go away once the editor has saved the file in the current form.

**Inputs.** Lists all run-time inputs of the metapipeline, with the params they fill. Hovering an input
highlights its steps on the graph. An input's form sets its description, default and rules
(type, format, allowed values, …), and the step params it fills: "Add step param" picks the step,
then the param, with each param's description, type and default. A choice at the top writes all
inputs in the steps' params or all in the `inputs:` section.

![The Inputs tab](editor-inputs-light.png#only-light)
![The Inputs tab](editor-inputs.png#only-dark)

**Globals.** Settings for every step: Nextflow version, profile and config, and shared params (deprecated, see the [config reference](../representation/reference.md)).

Fields that take a path (a step's params file and Nextflow config, the global Nextflow config,
params and input defaults with a path format) have a folder button that browses the machine
running the editor and fills in the absolute path of the file or folder you pick. You can also
type the path, relative to the config's folder, or a URL for params and input defaults. Whatever
is in the field is saved as it is. `outdir` has no button: a relative `outdir` is placed in the
run's output folder.

!!! tip "Configs on a cluster?"
    Run the editor on the cluster and use it in your own browser through an SSH tunnel:
    see [Running the editor on a remote machine](#running-the-editor-on-a-remote-machine).

### The editor link

On start, the editor backend prints a url where the frontend can be reached along with an access token that is regenerated on every startup. It looks like this: `Editor running at: http://127.0.0.1:8080/?token=…`.
The token is saved and resend by the editor on every request, or the editor backend refuses access.
This keeps other users of a shared machine (and websites open in your
browser) out of your configs. 
The browser gets the link through a small file only you can read (in `$XDG_RUNTIME_DIR` or `~/.cache/nf-meta/editor`, removed when the editor stops), so the token isn't leaked in the process monitor of a shared machine.
When the browser runs on a remote machine (VS Code Remote-SSH, dev containers, Codespaces), that file can't be reached. 
You can start with `--no-redirect-file` or open the printed link manually.


## Running the editor on a remote machine

Data and pipelines usually live on a cluster with no access to a display server or a browser.
To use the editor there anyway, run its backend on the cluster and connect to it through an **SSH tunnel**.

![An SSH tunnel connects the browser on the local computer to the editor backend on the cluster](editor-ssh-light.svg#only-light)
![An SSH tunnel connects the browser on the local computer to the editor backend on the cluster](editor-ssh.svg#only-dark)

On the cluster start the editor backend:

```bash
$ nf-meta editor --port 8080
Editor running at: http://127.0.0.1:8080/?token=Xq3…
Started over SSH: to use the editor from your own computer, forward its port there
    ssh -N -L 8080:localhost:8080 alice@login01
(with the host name you log in with), then open the link above in your browser.
```

On the computer with a browser, run the following command with the host name of your remote machine to start the tunnel:

```bash
$ ssh -N -L 8080:localhost:8080 alice@hpc.example.org
```

You will now be able to visit the printed link in your local browser.

### VS Code Remote-SSH

In the terminal of a VS Code Remote-SSH window, the port is forwarded automatically.
Start the editor with `--no-redirect-file`, so the link can be opened on your computer's browser:

```bash
nf-meta editor --port 8080 --no-redirect-file
```

## Editor backends

The editor is extensible via plugins in the same way runners are: `--editor <name>` selects a registered
`BaseEditor` subclass.
The one described above is the only one shipped with nf-meta right now and opens by default.
See [Writing an editor plugin](../guides/writing-an-editor-plugin.md)
to add a new third-party-editor.
