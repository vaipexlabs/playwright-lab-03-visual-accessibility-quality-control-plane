#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PROJECT_ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "Run ./scripts/setup.sh before installing the browser." >&2
  exit 1
fi

echo "Installing the pinned Playwright Chromium renderer..."
"${PYTHON}" -m playwright install chromium
