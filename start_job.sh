#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x venv/bin/python ]]; then
  printf '%s\n' "The project virtual environment is missing. See docs/RUN_LINKEDIN_COLLECTION.md." >&2
  exit 1
fi
exec venv/bin/python -u -m workflow.daily_pipeline "$@"
