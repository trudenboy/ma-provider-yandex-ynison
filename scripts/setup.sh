#!/usr/bin/env bash
set -euo pipefail

echo "Setting up development environment..."

if ! command -v uv &>/dev/null; then
  echo "Error: uv is not installed. Install it from https://docs.astral.sh/uv/"
  exit 1
fi

uv sync --extra test
uv run pre-commit install

echo "Done! Run 'uv run pytest' to verify."
