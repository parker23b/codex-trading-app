#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

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

echo "Installing hash-verified third-party runtime dependencies"
"$PYTHON_BIN" -m pip install --require-hashes -r requirements-hashed.txt

echo "Installing hash-verified third-party developer dependencies"
"$PYTHON_BIN" -m pip install --require-hashes -r requirements-dev-hashed.txt

echo "Installing local editable backend package without dependency resolution"
"$PYTHON_BIN" -m pip install --no-deps -e .
