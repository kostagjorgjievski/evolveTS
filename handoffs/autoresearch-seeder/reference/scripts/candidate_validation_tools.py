"""Configure a credential-free broker; submitted code runs in sandboxed children."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOOL_RULE='mcp__candidate-validation__validate_candidate'


def enabled_for(attempt):
    if attempt is None:return False
    config=ROOT/'configs/candidate_validation.json'
    return (config.exists() and json.loads(config.read_text()).get('enabled') is True
            and any(Path(attempt).is_relative_to(ROOT/'runs'/task) for task in ('dqi','dfthcsos')))


def server_config(attempt):
    attempt=Path(attempt).absolute()
    if attempt.is_relative_to(ROOT/'runs/dfthcsos'):
        return {'command':'/usr/bin/env','args':['-i','PATH=/usr/bin:/bin','HOME=/nonexistent','PYTHONDONTWRITEBYTECODE=1',str(ROOT/'.venv/bin/python'),str(ROOT/'tasks/dfthcsos/tools_server.py'),'--attempt',str(attempt)]}
    output=ROOT/'outputs/dqi-validation';(output/'tmp').mkdir(parents=True,exist_ok=True)
    # macOS disallows applying a second sandbox to an already sandboxed process.
    # The fixed broker never imports submitted code. Its syntax/import checker,
    # generator and unchanged official verifier each run under sandbox-exec.
    return {'command':'/usr/bin/env', 'args':['-i',
        'PATH=/usr/bin:/bin','HOME=/nonexistent','PYTHONDONTWRITEBYTECODE=1',
        'LC_ALL=en_US.UTF-8','LANG=en_US.UTF-8','TMPDIR='+str(output/'tmp'),
        str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/candidate_validation_server.py'),
        '--attempt',str(attempt)]}
