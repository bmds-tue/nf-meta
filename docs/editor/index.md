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
    It will not terminate and block the current prompt until you do so manually. (`Ctrl` + `C` or `Cmd` + `C`)


This serves the editor's frontend and automaatically opens it in a browser tab, backed by a local session and state.
(`nf_meta.core.session`)
The session tracks graph mutations by updating the internal history, fetches data while keeping a local cache, and responds to validation requests.
Passing no path starts a new, empty metapipeline.

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
