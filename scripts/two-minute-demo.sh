#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Vaipex Visual & Accessibility Quality Control Plane"
echo "====================================================="
echo
echo "1/4 Validate the locked automation toolchain"
"${PROJECT_ROOT}/scripts/validate-toolchain.sh"
echo
echo "2/4 Verify the reviewed baseline approval boundary"
"${PROJECT_ROOT}/scripts/verify-baselines.sh"
echo
echo "3/4 Run unit-level policy and control-plane checks"
"${PROJECT_ROOT}/.venv/bin/python" -m pytest -q tests/unit
echo
echo "4/4 Evaluate visual and accessibility quality as one decision"
"${PROJECT_ROOT}/scripts/test-quality.sh"
echo
echo "Demo complete: the combined decision is reports/quality-gate.json"
echo "Visual evidence: reports/visual/ and artifacts/visual/"
echo "Accessibility evidence: reports/accessibility/"
