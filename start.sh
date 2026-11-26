#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [ ! -f frontend/dist/index.html ] || [ ! -x .venv/bin/uvicorn ]; then
  echo "Run ./setup.sh first."
  exit 1
fi
exec .venv/bin/uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
