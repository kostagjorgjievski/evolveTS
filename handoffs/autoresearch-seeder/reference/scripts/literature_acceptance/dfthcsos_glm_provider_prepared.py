"""Prepared-context GLM5.3 chemistry worker through the user's model gateway."""
import json,sys
from pathlib import Path
import dfthcsos_pilot as pilot
import dfthcsos_opus_prepared as prepared
ROOT=pilot.ROOT

def initialize(run):
    meta=prepared.initialize(run)
    meta.update(provider='glm_proxy',worker_model='glm-5.3',effort='max',experiment='chemistry_RSI_E0_prepared',status='prepared')
    (run/'pilot.json').write_text(json.dumps(meta,indent=2)+'\n')
if __name__=='__main__':
    run=Path(sys.argv[1]).resolve()
    if not run.is_relative_to(ROOT/'runs/dfthcsos'):raise ValueError('Chemistry pilot required')
    meta=json.loads((run/'pilot.json').read_text())
    consumed=meta.get('session_seconds_used',0)
    if consumed:
        meta['max_session_seconds']=12000-consumed;meta['original_attempt_seconds']=12000
        (run/'pilot.json').write_text(json.dumps(meta,indent=2)+'\n')
    pilot.work(run,config_override=pilot.runner.environment(ROOT/'.credentials/kimi-proxy.env'))
