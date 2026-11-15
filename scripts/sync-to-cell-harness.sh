#!/bin/bash
# Copies a skill from this repo into the Cell Harness app's skills folder, so the app runs the reviewed version.
set -euo pipefail
skill="${1:-comic-translator}"
here="$(cd "$(dirname "$0")/.." && pwd)"
target="${CELL_HARNESS_SKILLS:-$HOME/Library/Application Support/Cell Harness/skills}"
[ -d "$here/$skill" ] || { echo "error: no skill named $skill in $here" >&2; exit 1; }
mkdir -p "$target/$skill"
rsync -a --delete --itemize-changes \
  --exclude .venv --exclude __pycache__ --exclude '*.pyc' \
  --exclude .pytest_cache --exclude .ruff_cache --exclude .coverage \
  "$here/$skill/" "$target/$skill/"
echo "synced $skill into $target/$skill"
