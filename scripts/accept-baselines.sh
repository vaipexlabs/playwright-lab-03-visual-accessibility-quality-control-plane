#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${PROJECT_ROOT}/scripts/ensure-toolchain.sh"
exec "${PROJECT_ROOT}/.venv/bin/python" \
  -m vaipex_visual_accessibility.baselines accept
