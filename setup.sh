#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
export PATH="$PWD/.tools/node/bin:$PATH"
command -v npm >/dev/null || { echo "Install Node.js 22 LTS (includes npm), then rerun ./setup.sh"; exit 1; }
if [ ! -x .venv/bin/python ]; then
  python3 -m venv --without-pip .venv
fi
if .venv/bin/python -m pip --version >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r backend/requirements.txt
else
  python3 -m pip --python .venv/bin/python install pip -r backend/requirements.txt
fi
(cd frontend && npm ci && npm run build)
echo "Setup complete. Run ./start.sh"
