#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TASK="$ROOT/tasks/tsb_ad_u"
PYTHON="$ROOT/.tsb-venv/bin/python"
if [ ! -f "$TASK/libraryts.json" ] || [ ! -f "$TASK/vendor/sktime-0.40.1-py3-none-any.whl" ]; then
  "$PYTHON" "$ROOT/scripts/build_libraryts.py"
fi
"$PYTHON" - "$TASK" <<'PY'
import hashlib, json, sys
from pathlib import Path
p = Path(sys.argv[1]); m = json.loads((p/'libraryts.json').read_text())
assert m['commit'] == '904bb75717d5f83e9d8177affae2113c9ee3f6b3'
assert hashlib.sha256((p/'vendor'/m['wheel']).read_bytes()).hexdigest() == m['wheel_sha256']
PY
"$PYTHON" -m pip install -r "$TASK/requirements.txt" -r "$TASK/requirements-libraryts.txt" \
  "$TASK/vendor/sktime-0.40.1-py3-none-any.whl"
"$PYTHON" -m pip check
