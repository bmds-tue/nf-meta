# Editor

The `nf-meta` package ships a browser-based editor for interactively visualizing and editing metapipeline configs.
Autocompleted and validated forms for updating workflow attributes can make creating or extending workflow chains easier, if you are not used to hand-writing YAML directly.
Because mistakes can happen, the edit history allows going back to a previous state or reapplying a change you made.

![nf-meta editor](nf-meta-screenshot.png)

## Usage

```bash
# start fresh
nf-meta editor 

# or open some existing work
nf-meta editor [path/to/metapipeline.yaml]
```

!!! note
    The `editor` starts and continues to run a session which essential for the browser page to work.
    It keeps the terminal busy until you stop it: **Quit editor** in the page's file menu, or
    `Ctrl` + `C` in the terminal. Every change is saved as you make it, so nothing is lost either
    way. A page whose editor has stopped says so; run `nf-meta editor` again and open the new link.


This serves the editor's frontend and automaatically opens it in a browser tab, backed by a local session and state.
(`nf_meta.core.session`)
The session tracks graph mutations by updating the internal history, fetches data while keeping a local cache, and responds to validation requests.
Passing no path starts a new, empty metapipeline.

!!! tip "Configs on a cluster?"
    Run the editor on the cluster and use it in your own browser through an SSH tunnel:
    see [Running the editor on a remote machine](#running-the-editor-on-a-remote-machine).

### The editor link

On start, the editor prints its address with an access token, for example
`Editor running at: http://127.0.0.1:8080/?token=…`, and opens that link in your browser. The page
keeps the token for the tab and sends it with every request; without it, the editor refuses to
read or write anything. This keeps other users of a shared machine (and websites open in your
browser) out of your configs. If a tab shows "Cannot reach the editor backend", open the printed
link again; each start of `nf-meta editor` makes a new token.

The browser gets the link through a small file only you can read (in `$XDG_RUNTIME_DIR` or
`~/.cache/nf-meta/editor`, removed when the editor stops), so the token doesn't show up in the process list
of a shared machine. When the browser runs on another machine (VS Code Remote-SSH, dev containers,
Codespaces), that file doesn't exist there: start with `--no-redirect-file` to open the link
directly, or open the printed link yourself.

The editor also only answers requests addressed to `localhost` or `127.0.0.1` (or the name given
with `--host`).

## Editor backends

The editor is extensible via plugins in the same way runners are: `--editor <name>` selects a registered
`BaseEditor` subclass.
The one described above is the only one shipped with nf-meta right now and opens by default.
See [Writing an editor plugin](../guides/writing-an-editor-plugin.md)
to add another.

## Running the editor on a remote machine

Your configs and data often live on a cluster, while your browser runs on your own computer. Run
the editor on the cluster and use it from your computer through an **SSH tunnel**. The editor
listens only on the cluster machine itself (`127.0.0.1`), so it never opens a port to the cluster
network. The tunnel carries your browser's requests to it over your SSH login.

On the cluster (a login node is fine):

```bash
nf-meta editor --port 8080
```

```text
Editor running at: http://127.0.0.1:8080/?token=Xq3…
Started over SSH: to use the editor from your own computer, forward its port there
    ssh -N -L 8080:localhost:8080 alice@login01
(with the host name you log in with), then open the link above in your browser.
```

On your computer, in a second terminal, run the printed command with the host name you use to log
in:

```bash
ssh -N -L 8080:localhost:8080 alice@hpc.example.org
```

It prints nothing and keeps running: that's the tunnel. Now open the printed link
(`http://127.0.0.1:8080/?token=…`) in your browser. Every change is saved to the file on the
cluster.

To stop: **Quit editor** in the page's file menu (or `Ctrl` + `C` in the cluster terminal), then
`Ctrl` + `C` in the tunnel terminal.

### Good to know

- **Pick a port with `--port`.** Without it, the editor takes a random free port each time and
  the tunnel has to change with it. Ports are shared by everyone on a login node. If yours is
  taken, the editor stops with `address already in use`. Pick another one (e.g. `8642`) on both
  sides.
- **The port on your computer can differ.** If `8080` is busy on your computer, forward another
  local port, `ssh -N -L 9000:localhost:8080 …`, and open the link with `9000` instead of `8080`
  (same token).
- **No browser opens on the cluster.** Without a display, the editor doesn't try to start one.
  `--no-browser` makes that explicit anywhere.

### VS Code Remote-SSH

In a terminal of a VS Code Remote-SSH window, VS Code forwards the port by itself and offers to
open it. Start the editor with `--no-redirect-file`, so the link it opens is one your computer's
browser can use:

```bash
nf-meta editor --port 8080 --no-redirect-file
```
