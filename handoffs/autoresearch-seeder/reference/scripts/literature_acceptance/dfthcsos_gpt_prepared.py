"""One prepared-context GPT-6.1 Sol chemistry attempt through the provider."""
import json,sys
from pathlib import Path
import dfthcsos_pilot as pilot
import dfthcsos_opus_prepared as prepared
ROOT=pilot.ROOT

def initialize(run):
    meta=prepared.initialize(run)
    meta.update(provider='gpt_proxy',worker_model='gpt-6.1-sol',effort='xhigh',experiment='gpt_prepared_context_single_attempt',status='prepared')
    (run/'pilot.json').write_text(json.dumps(meta,indent=2)+'\n')

if __name__=='__main__':
    run=Path(sys.argv[1]).resolve()
    if not run.is_relative_to(ROOT/'runs/dfthcsos'):raise ValueError('Chemistry pilot required')
    pilot.work(run)
