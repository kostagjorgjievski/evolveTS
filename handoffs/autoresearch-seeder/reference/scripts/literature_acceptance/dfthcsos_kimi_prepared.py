"""One prepared-context Kimi chemistry attempt, sharing the global model slots."""
import datetime,json,os,sys
from pathlib import Path
import dfthcsos_pilot as pilot
import dfthcsos_opus_prepared as prepared
ROOT=pilot.ROOT
sys.path.insert(0,str(ROOT/'scripts/seeded_rsi'))
import controller

def initialize(run):
    meta=prepared.initialize(run)
    meta.update(provider='kimi_proxy',worker_model='k3.1-pro',effort='medium',experiment='kimi_prepared_context_single_attempt',status='queued',queue_reason='Shared maximum of two active Kimi sessions, including DQI workers')
    (run/'pilot.json').write_text(json.dumps(meta,indent=2)+'\n')

def work(run):
    cfg=pilot.runner.environment(ROOT/'.credentials/kimi-proxy.env')
    pilot.work(run,config_override=cfg)

if __name__=='__main__':
    run=Path(sys.argv[1]).resolve()
    if not run.is_relative_to(ROOT/'runs/dfthcsos'):raise ValueError('Chemistry pilot required')
    if '--work' in sys.argv:work(run)
    else:
        m=json.loads((run/'pilot.json').read_text());m.update(status='queued',queue_pid=os.getpid());(run/'pilot.json').write_text(json.dumps(m,indent=2)+'\n')
        proc=controller.spawn_with_slot([str(ROOT/'.venv/bin/python'),'-u',str(Path(__file__).resolve()),str(run),'--work'],run,'kimi_proxy',run/'controller.log')
        pointer=ROOT/'runs/dfthcsos/active-kimi-prepared.json';p=json.loads(pointer.read_text());p.update(pid=proc.pid,status='launched');pointer.write_text(json.dumps(p,indent=2)+'\n')
        proc.wait()
