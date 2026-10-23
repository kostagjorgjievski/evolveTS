#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
test "$(uname -s)" = Darwin
test "$(git -C upstream/dream-rsi rev-parse HEAD)" = 8ec35bd2538220517ce1bfca4282db21b8c518db
command -v uv >/dev/null
uv python install 3.12
[ -x .tsb-venv/bin/python ] || uv venv --python 3.12 .tsb-venv
[ -x .venv/bin/python ] || uv venv --python 3.12 .venv
uv pip install --python .tsb-venv/bin/python pip
bash tasks/tsb_ad_u/setup_libraryts.sh
uv pip install --python .tsb-venv/bin/python torch==2.10.0 psutil==7.0.0
uv pip install --python .venv/bin/python -e upstream/dream-rsi claude-agent-sdk==0.1.50 psutil==7.0.0
.tsb-venv/bin/python tasks/tsb_ad_u/prepare_data.py
.tsb-venv/bin/python - <<'INNER'
import json, pathlib, shutil, socket, torch
assert torch.backends.mps.is_available(), "MPS unavailable"
host = socket.gethostname().split('.')[0]
path = pathlib.Path('configs/hosts') / (host+'.json')
path.write_text(json.dumps({'device':'mps','physical_gpu':'mps','physical_gpus':['mps'],
 'claude_cli':shutil.which('claude'),'isolation':'macOS sandbox-exec: file allowlist and network denied',
 'mps_fallback':True,'evaluation_parallelism':1},indent=2)+'\n')
INNER
.tsb-venv/bin/python -m pip freeze > tasks/tsb_ad_u/requirements-macos.lock.txt
