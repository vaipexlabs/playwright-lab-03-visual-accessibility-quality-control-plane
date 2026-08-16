#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"

"${PROJECT_ROOT}/scripts/ensure-toolchain.sh"

echo "Starting the deterministic reference app at http://127.0.0.1:${PORT}"
exec "${PROJECT_ROOT}/.venv/bin/uvicorn" \
  vaipex_visual_accessibility.app:app \
  --app-dir "${PROJECT_ROOT}/src" \
  --host 127.0.0.1 \
  --port "${PORT}" \
  --no-access-log
