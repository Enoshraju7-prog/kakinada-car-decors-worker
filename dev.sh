#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -d frontend/node_modules ]]; then
  echo "Install frontend dependencies first: cd frontend && npm ci --ignore-scripts"
  exit 1
fi
(cd frontend && npm run build)
cd backend
if [[ ! -x .venv/bin/python ]]; then
  echo "Install dependencies first: cd backend && uv sync --locked"
  exit 1
fi
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${KCD_PORT:-8000}"
