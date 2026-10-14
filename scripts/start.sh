#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_dir"
if [[ ! -x .venv/bin/qualidock || ! -f frontend/dist/index.html ]]; then
  echo "Install the Python package and build the frontend first. See README.md." >&2
  exit 1
fi
exec .venv/bin/qualidock "$@"
