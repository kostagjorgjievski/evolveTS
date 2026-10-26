#!/usr/bin/env bash
# Linux CUDA + Docker setup. Download and image-build steps require network.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
test "$(uname -s)" = Linux || { echo 'rca_re1 requires Linux CUDA and Docker.' >&2; exit 1; }
[ -x .rca-venv/bin/python ] || uv venv --seed --python 3.12 .rca-venv
uv pip install --python .rca-venv/bin/python -r tasks/rca_re1/requirements.txt
# Resolve the pinned data revision through whichever Hub endpoint is reachable.
if [ -z "${HF_ENDPOINT:-}" ] && ! curl -sfI --max-time 8 https://huggingface.co >/dev/null 2>&1; then
  export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
  echo "[setup] huggingface.co unreachable; using $HF_ENDPOINT"
fi
.rca-venv/bin/python tasks/rca_re1/prepare_data.py
DOCKER=(docker)
docker info >/dev/null 2>&1 || DOCKER=(sudo -n docker)
"${DOCKER[@]}" build -f tasks/rca_re1/Dockerfile.sp1 -t evolvets-rca:local tasks/rca_re1
RCA_DOCKER="${DOCKER[*]}" .rca-venv/bin/python - <<'PY'
import json, os, shlex, socket, subprocess
from pathlib import Path
host = socket.gethostname().split('.')[0]
docker = shlex.split(os.environ['RCA_DOCKER'])
p = Path('configs/hosts') / (host + '.json')
profile = json.loads(p.read_text())
profile['rca_worker_image'] = subprocess.check_output(
    docker + ['image', 'inspect', '--format', '{{.Id}}', 'evolvets-rca:local'], text=True).strip()
p.write_text(json.dumps(profile, indent=2) + '\n')
(Path('tasks/rca_re1') / ('runtime-' + host + '.json')).write_text(
    json.dumps({'worker_image': profile['rca_worker_image'],
                'rca_worker_image': profile['rca_worker_image']}, indent=2) + '\n')
PY
echo "[setup] done. Launch with: BACKEND=minimax bash scripts/run_fresh.sh rca_re1"
