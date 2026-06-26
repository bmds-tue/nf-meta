#!/usr/bin/env bash
set -euo pipefail

echo ">>> Ensuring pip is available..."
python -m ensurepip --upgrade
python -m pip install --upgrade pip

echo ">>> Installing uv..."
pip install --upgrade uv

echo ">>> Syncing project dependencies"
uv sync

echo ">>> Installing mypy typing stub packages. (Installed as extension)"
mypy --install-types --non-interactive

echo ">>> Installing Claude Code CLI..."
npm install -g @anthropic-ai/claude-code

