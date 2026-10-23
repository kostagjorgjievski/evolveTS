#!/usr/bin/env bash
# Linux CUDA + Docker setup. Build/download steps intentionally require network.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
test "$(uname -s)" = Linux || { echo 'Forecasting v2 currently requires Linux CUDA and Docker.' >&2; exit 1; }
[ -x .gift-venv/bin/python ] || uv venv --seed --python 3.12 .gift-venv
uv pip install --python .gift-venv/bin/python -r tasks/gift_forecasting_v2/requirements.txt psutil==7.0.0 pytest==8.3.5
.gift-venv/bin/python tasks/gift_forecasting_v2/prepare_data.py --full
.venv/bin/python scripts/fetch_worker_sources.py
docker build -f tasks/gift_forecasting_v2/Dockerfile.sp1 -t evolvets-gift-v2:local tasks/gift_forecasting_v2
.gift-venv/bin/python scripts/download_models.py
.gift-venv/bin/python - <<'PY'
import json,socket,subprocess
from pathlib import Path
p=Path('configs/hosts')/(socket.gethostname().split('.')[0]+'.json');j=json.loads(p.read_text())
j['gift_v2_worker_image']=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}','evolvets-gift-v2:local'],text=True).strip()
j.setdefault('gift_v2_physical_gpus',j.get('physical_gpus',['0']))
p.write_text(json.dumps(j,indent=2)+'\n')
PY
.gift-venv/bin/python tasks/gift_forecasting_v2/make_reference.py
