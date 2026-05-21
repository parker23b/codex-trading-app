#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PIP_TOOLS_CACHE_DIR="${PIP_TOOLS_CACHE_DIR:-$ROOT_DIR/.tmp/pip-tools-cache}"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    PYTHON_BIN="$(command -v python)"
  fi
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Expected Python interpreter at $PYTHON_BIN" >&2
  echo "Set PYTHON_BIN or create backend/.venv first." >&2
  exit 1
fi

cd "$BACKEND_DIR"
mkdir -p "$PIP_TOOLS_CACHE_DIR"

"$PYTHON_BIN" -m piptools compile \
  --resolver=backtracking \
  --strip-extras \
  --no-header \
  --cache-dir "$PIP_TOOLS_CACHE_DIR" \
  pyproject.toml \
  --output-file requirements.txt

"$PYTHON_BIN" -m piptools compile \
  --resolver=backtracking \
  --no-header \
  --cache-dir "$PIP_TOOLS_CACHE_DIR" \
  requirements-dev.in \
  --output-file requirements-dev.txt
