#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
if [ "$(uname -s)" = Darwin ]; then exec bash tasks/tsb_ad_u/setup_macos.sh "$@"; fi
[ -x .tsb-venv/bin/python ] || uv venv --seed --python 3.12 .tsb-venv
bash tasks/tsb_ad_u/setup_libraryts.sh
uv pip install --python .tsb-venv/bin/python torch==2.10.0 --index-url https://download.pytorch.org/whl/cu126
uv pip install --python .tsb-venv/bin/python psutil==7.0.0
.tsb-venv/bin/python tasks/tsb_ad_u/prepare_data.py "$@"
docker build -f tasks/tsb_ad_u/Dockerfile.sp1 -t evolvets-tsb-u:local tasks/tsb_ad_u
.tsb-venv/bin/python - <<'PY'
from pathlib import Path
import json,socket,subprocess
host=socket.gethostname().split('.')[0]
p=Path('configs/hosts')/(host+'.json');j=json.loads(p.read_text())
j['worker_image']=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}','evolvets-tsb-u:local'],text=True).strip()
p.write_text(json.dumps(j,indent=2)+'\n')
(Path('tasks/tsb_ad_u')/('runtime-'+host+'.json')).write_text(json.dumps({'worker_image':j['worker_image']},indent=2)+'\n')
PY
