#!/usr/bin/env bash
# Prepare the tsf_fleet_cap_v1 task environment: create .tsf-venv, verify the
# verifier end-to-end, pin the starter reference and run the task checks.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [ ! -x .tsf-venv/bin/python ]; then
  echo "[setup] creating .tsf-venv (numpy, pandas, torch cu126, scikit-learn, scipy)"
  uv venv .tsf-venv
  uv pip install --python .tsf-venv/bin/python \
    numpy pandas scikit-learn scipy
  uv pip install --python .tsf-venv/bin/python \
    --torch-backend cu126 torch
fi
.tsf-venv/bin/python -c "import numpy, torch; assert torch.cuda.is_available(), 'CUDA unavailable'"

if [ ! -f tasks/tsf_fleet_cap_v1/reference_starter.json ]; then
  echo "[setup] computing starter reference (development replay)"
  .tsf-venv/bin/python tasks/tsf_fleet_cap_v1/make_reference.py
fi

echo "[setup] running task checks"
.tsf-venv/bin/python -m pytest tasks/tsf_fleet_cap_v1/test_task.py -q
echo "[setup] done"
