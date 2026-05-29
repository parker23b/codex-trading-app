#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
ARTIFACT_DIR="${SBOM_OUTPUT_DIR:-$ROOT_DIR/artifacts/sbom}"
SCOPE="${1:-all}"

mkdir -p "$ARTIFACT_DIR"

generate_backend_sbom() {
  local cyclonedx_py_bin

  if [[ -x "$BACKEND_DIR/.venv/bin/cyclonedx-py" ]]; then
    cyclonedx_py_bin="$BACKEND_DIR/.venv/bin/cyclonedx-py"
  elif command -v cyclonedx-py >/dev/null 2>&1; then
    cyclonedx_py_bin="$(command -v cyclonedx-py)"
  else
    echo "Missing cyclonedx-py on PATH and under $BACKEND_DIR/.venv/bin/" >&2
    echo "Install backend dev dependencies first." >&2
    exit 1
  fi

  "$cyclonedx_py_bin" requirements \
    "$BACKEND_DIR/requirements-hashed.txt" \
    --pyproject "$BACKEND_DIR/pyproject.toml" \
    --output-reproducible \
    --of JSON \
    -o "$ARTIFACT_DIR/backend.cyclonedx.json"
}

generate_frontend_sbom() {
  (
    cd "$FRONTEND_DIR"
    npm sbom \
      --package-lock-only \
      --sbom-format cyclonedx \
      > "$ARTIFACT_DIR/frontend.cyclonedx.json"
  )
}

case "$SCOPE" in
  all)
    generate_backend_sbom
    generate_frontend_sbom
    ;;
  backend)
    generate_backend_sbom
    ;;
  frontend)
    generate_frontend_sbom
    ;;
  *)
    echo "Usage: $0 [all|backend|frontend]" >&2
    exit 1
    ;;
esac
