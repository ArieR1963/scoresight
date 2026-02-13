#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "Usage: ./scripts/checkpoint.sh [message]"
  exit 0
fi

msg="${*:-checkpoint}"
stamp="$(date '+%Y-%m-%d %H:%M:%S')"

if [[ -z "$(git status --porcelain)" ]]; then
  echo "No changes to commit."
  exit 0
fi

git add -A
git commit -m "checkpoint: ${msg} (${stamp})"
echo "Checkpoint committed."
