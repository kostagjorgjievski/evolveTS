#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v uv >/dev/null || { echo 'Install uv first: https://docs.astral.sh/uv/' >&2; exit 1; }
mkdir -p upstream configs/hosts
pin_repo() {
  local name="$1" url="$2" revision="$3"
  if [ ! -e "upstream/$name" ]; then git clone "$url" "upstream/$name"; fi
  if [ "$(git -C "upstream/$name" rev-parse HEAD)" != "$revision" ]; then
    test -z "$(git -C "upstream/$name" status --porcelain)" || { echo "Refusing to modify dirty upstream/$name" >&2; exit 1; }
    git -C "upstream/$name" checkout --detach "$revision"
  fi
}
pin_repo dream-rsi https://github.com/google-research/dream-rsi.git 8ec35bd2538220517ce1bfca4282db21b8c518db
pin_repo tsb-ad https://github.com/TheDatumOrg/TSB-AD.git 303dffbfc11612995b17b06633f8c9d0ea0e38e5
pin_repo gift-eval https://github.com/SalesforceAIResearch/gift-eval.git 3c7be6deffb0046e1c08f9103db8bc84b3cf7ebd
pin_repo rcaeval https://github.com/phamquiluan/RCAEval.git 2fca61b9730a69c21ef72411844735634dbb010f
uv python install 3.12
[ -x .venv/bin/python ] || uv venv --seed --python 3.12 .venv
uv pip install --python .venv/bin/python -e 'upstream/dream-rsi[claude,dev]' claude-agent-sdk==0.1.50 psutil==7.0.0
command -v claude >/dev/null || { echo 'Install the Claude Code CLI before launching a search.' >&2; exit 1; }
.venv/bin/python - <<'PY'
import json,shutil,socket
from pathlib import Path
p=Path('configs/hosts')/(socket.gethostname().split('.')[0]+'.json')
if not p.exists():
 p.write_text(json.dumps({'device':'cuda:0','physical_gpu':'0','physical_gpus':['0'],'claude_cli':shutil.which('claude')},indent=2)+'\n')
PY
