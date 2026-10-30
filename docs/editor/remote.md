# Editor on a remote machine (HPC)

Your configs and data often live on a cluster, while your browser runs on your own computer. Run
the editor on the cluster and use it from your computer through an **SSH tunnel**. The editor
listens only on the cluster machine itself (`127.0.0.1`), so it never opens a port to the cluster
network; the tunnel carries your browser's requests to it over your SSH login.

## In short

On the cluster (a login node is fine, see [below](#login-node-or-compute-node)):

```bash
nf-meta editor --port 8080 metapipeline.yaml
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

It prints nothing and keeps running; that's the tunnel. Now open the printed link
(`http://127.0.0.1:8080/?token=…`) in your browser. Every change is saved to the file on the
cluster.

To stop: **Quit editor** in the page's file menu (or `Ctrl` + `C` in the cluster terminal), then
`Ctrl` + `C` in the tunnel terminal.

## Example: one terminal with an SSH host entry

Instead of two terminals, let your login open the tunnel as well. Add a host entry to
`~/.ssh/config` on your computer:

```text
Host hpc-editor
    HostName hpc.example.org
    User alice
    LocalForward 8080 localhost:8080
```

Then a session looks like this:

```console
you@laptop:~$ ssh hpc-editor
alice@login01:~$ cd projects/rnaseq-study
alice@login01:~/projects/rnaseq-study$ nf-meta editor --port 8080 metapipeline.yaml
Editor running at: http://127.0.0.1:8080/?token=Xq3…
Started over SSH: ...
```

Open the link on your computer. When you're done, choose **Quit editor** in the page (or press
`Ctrl` + `C`) and log out.

## Good to know

- **Pick a port with `--port`.** Without it, the editor takes a random free port each time and
  the tunnel has to change with it. Ports are shared by everyone on a login node: if yours is
  taken, the editor stops with `address already in use`; pick another one (e.g. `8642`) on both
  sides.
- **The port on your computer can differ.** If `8080` is busy on your computer, forward another
  local port, `ssh -N -L 9000:localhost:8080 …`, and open the link with `9000` instead of `8080`
  (same token).
- **No browser opens on the cluster.** Without a display, the editor doesn't try to start one;
  `--no-browser` makes that explicit anywhere.
- **Logging out stops the editor.** Closing the SSH session ends it (your changes are already
  saved). To keep it running after you log out, start it with `nohup` and read the link from the
  log; stop it later with **Quit editor**:

    ```bash
    nohup nf-meta editor --port 8080 metapipeline.yaml > editor.log 2>&1 &
    cat editor.log
    ```

    `tmux` or `screen` work as well.

- **The link is the key.** Other users of the login node can reach the port, but the editor
  refuses every request without the token in your link. Don't share the link; each start makes
  a new one (see [The editor link](index.md#the-editor-link)).

## Login node or compute node

The editor needs little CPU or memory, and it looks up nf-core pipeline and module information
online, which login nodes usually allow and compute nodes often don't. Run it on a login node
unless your site says otherwise.

If you do run it on a compute node (e.g. `cn042` in an interactive job) and your cluster lets you
SSH to the nodes of your jobs, tunnel through the login node:

```bash
ssh -N -J alice@hpc.example.org -L 8080:localhost:8080 alice@cn042
```

## VS Code Remote-SSH

In a terminal of a VS Code Remote-SSH window, VS Code forwards the port by itself and offers to
open it. Start the editor with `--no-redirect-file`, so the link it opens is one your computer's
browser can use:

```bash
nf-meta editor --port 8080 --no-redirect-file metapipeline.yaml
```

## Troubleshooting

| You see | Meaning | What to do |
|---|---|---|
| `error while attempting to bind on address ('127.0.0.1', 8080): address already in use` (on the cluster) | Someone already uses that port on this node. | Start with another `--port`, and forward that one. |
| `bind [127.0.0.1]:8080: Address already in use` (from `ssh` on your computer) | The port is busy on your computer. | Forward another local port: `-L 9000:localhost:8080`, then use `9000` in the link. |
| `channel 2: open failed: connect failed: Connection refused` (in the tunnel terminal, when you open the page) | No editor runs on that port on the cluster. | Check the editor is running and that both port numbers match. |
| The page says **Cannot reach the editor backend** | The link's token is from an earlier start. | Open the link the editor printed last. |
| The page says **The editor is not running** | The editor stopped, or the tunnel closed. | Start the editor (and the tunnel) again and open the new link. |
