#!/usr/bin/env bash
set -euo pipefail

echo ">>> Ensuring pip is available..."
python -m ensurepip --upgrade
python -m pip install --upgrade pip

echo ">>> Installing uv..."
pip install --upgrade uv

echo ">>> Syncing project dependencies"
uv sync

echo ">>> Installing Nextflow ${NXF_VER:=25.10.9} into ~/.local/bin..."
mkdir -p "$HOME/.local/bin"
(cd "$HOME/.local/bin" && curl -fsSL https://get.nextflow.io | NXF_VER="$NXF_VER" bash && chmod +x nextflow)

echo ">>> Installing mypy typing stub packages. (Installed as extension)"
mypy --install-types --non-interactive

echo ">>> Installing Claude Code CLI..."
npm install -g @anthropic-ai/claude-code

