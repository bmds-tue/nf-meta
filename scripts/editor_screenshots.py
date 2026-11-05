"""Take the editor screenshots used by the docs and the README.

Starts `nf-meta editor` on `assets/metapipeline.yaml` and saves the main view (the rnaseq step
open for editing) in the dark and the light theme:

    docs/editor/nf-meta-screenshot.png        assets/nf-meta-screenshot.png
    docs/editor/nf-meta-screenshot-light.png  assets/nf-meta-screenshot-light.png

Run from anywhere (needs the network, for the nf-core catalog and schemas):

    uv run --with playwright playwright install chromium   # once
    uv run --with playwright python scripts/editor_screenshots.py
"""

import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "assets" / "metapipeline.yaml"
TARGETS = [ROOT / "docs" / "editor", ROOT / "assets"]
THEMES = {"graphite": "nf-meta-screenshot.png", "light": "nf-meta-screenshot-light.png"}
VIEWPORT = {"width": 1500, "height": 860}
TIMEOUT_MS = 60_000


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_editor(state_dir: str) -> tuple[subprocess.Popen, str]:
    """Start the editor and return it with the link it prints."""
    env = {**os.environ, "XDG_STATE_HOME": state_dir}
    env.pop("NF_META_DEVMODE", None)
    cmd = [sys.executable, "-m", "nf_meta", "editor", "--port", str(free_port())]
    cmd += ["--no-browser", "--no-redirect-file", CONFIG.name]  # by name: the footer shows it
    proc = subprocess.Popen(
        cmd, cwd=CONFIG.parent, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in proc.stdout], daemon=True).start()  # type: ignore[union-attr]
    output = []
    while True:
        try:
            line = lines.get(timeout=TIMEOUT_MS / 1000)
        except queue.Empty:
            proc.kill()
            sys.exit("The editor didn't print its link in time:\n" + "".join(output))
        output.append(line)
        if match := re.search(r"Editor running at: (\S+)", line):
            return proc, match.group(1)
        if proc.poll() is not None:
            sys.exit("The editor stopped:\n" + "".join(output))


def shoot(page_url: str, theme: str, path: Path, browser) -> None:
    context = browser.new_context(viewport=VIEWPORT, device_scale_factor=1.5)
    context.set_default_timeout(TIMEOUT_MS)
    context.add_init_script(f"localStorage.setItem('theme', '{theme}')")
    page = context.new_page()
    page.goto(page_url)
    page.locator("[title='Show or hide the sidebar']").click()
    steps = page.locator(".v-window-item--active")
    steps.locator(".node-title", has_text="nf-core/rnaseq").click()
    steps.get_by_role("button", name="Edit").first.click()
    # the params form is built from the pipeline's schema, fetched from GitHub
    steps.locator(".v-text-field", has_text="outdir").first.wait_for()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)  # let the sidebar's transitions finish
    page.screenshot(path=path)
    context.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as state_dir, tempfile.TemporaryDirectory() as shots:
        proc, url = start_editor(state_dir)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                for theme, name in THEMES.items():
                    shoot(url, theme, Path(shots) / name, browser)
                browser.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        for name in THEMES.values():
            for target in TARGETS:
                shutil.copy(Path(shots) / name, target / name)
                print(f"wrote {(target / name).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
