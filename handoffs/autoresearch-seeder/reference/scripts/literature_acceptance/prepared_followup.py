"""Queue one fresh-context DQI attempt after the current controller finishes."""
import argparse,datetime,hashlib,json,shutil,subprocess,time
from pathlib import Path
import psutil
import solo_pilot
ROOT=solo_pilot.ROOT

def save(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(path)

def start(parent,queue,pointer):
    request=json.loads(queue.read_text());pid=request['previous_pid'];created=request['previous_create_time']
    while True:
        try:
            p=psutil.Process(pid)
            if p.create_time()!=created or p.status()==psutil.STATUS_ZOMBIE:break
        except psutil.NoSuchProcess:break
        time.sleep(5)
    meta=json.loads((parent/'pilot.json').read_text())
    if meta.get('status') in ('stopped_by_user','stopped_superseded'):
        request.update(status='cancelled',reason='Parent was stopped');save(queue,request);return
    dev=json.loads((parent/'private/final-development.json').read_text())
    held=json.loads((parent/'private/held-out.json').read_text())
    if dev.get('status')!='PASS' or held.get('status')!='PASS':raise RuntimeError('Parent needs passing final development and confirmation receipts')
    index=meta.get('continuation_attempt_index',meta.get('initial_attempt_index',0))
    source=parent/f'worker/explore_b0/attempt_{index:02d}/artifact'
    if hashlib.sha256((source/'program.py').read_bytes()).hexdigest()!=dev['source_sha256']:raise RuntimeError('Parent source does not match verified receipt')
    run=ROOT/'runs/dqi-solo'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-kimi31pro-prepared-attempt2')
    new=solo_pilot.initialize(run,provider=meta['provider']);branch=run/'worker/explore_b0'
    shutil.rmtree(branch/'attempt_00');artifact=branch/f'attempt_{index+1:02d}/artifact'
    shutil.copytree(source,artifact,ignore=shutil.ignore_patterns('diagnostic*.py','__pycache__'))
    guide=Path(request['guide']).read_text()
    if '## 1. Objective' in guide:guide=guide[guide.index('## 1. Objective'):]
    guide='# DQI task/API preparation\n\nThe candidate is inherited verified parent source. No prior conversation, proposal\nor research history is supplied. Historical self-check transcript references\nbelow are not provided; verify uncertain API details against live tools. Current\ntool descriptions govern sandbox limits and import conventions.\n\n'+guide
    (branch/'preparation-guide.md').write_text(guide)
    result={label:{k:receipt.get(k) for k in ('status','combined_score','official','source_sha256','artifact_bundle_sha256','call_id')} for label,receipt in [('development',dev),('fresh_salt',held)]}
    (branch/'parent-result.json').write_text(json.dumps(result,indent=2)+'\n')
    new.update(prepared_parent_context=True,initial_attempt_index=index+1,logical_attempt=index+2,attempts=index+2,budget_scope='per_attempt',harness_revision='integration_v2',parent_run=str(parent),parent_reward=dev['combined_score'],conversation_memory=False,worker_model=meta['worker_model'],effort=meta['effort'])
    save(run/'pilot.json',new)
    assert not (run/'private/sdk/sdk-session.json').exists()
    with (run/'controller.log').open('a') as log:
        proc=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-u',str(ROOT/'scripts/literature_acceptance/solo_pilot.py'),'run',str(run)],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    save(pointer,{'run':str(run),'pid':proc.pid,'create_time':psutil.Process(proc.pid).create_time(),'status':'running','logical_attempt':index+2,'context':'prepared_fresh_conversation','parent_run':str(parent),'parent_reward':dev['combined_score']})
    request.update(status='started',next_run=str(run),next_pid=proc.pid);save(queue,request)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('parent',type=Path);p.add_argument('queue',type=Path);p.add_argument('pointer',type=Path);a=p.parse_args()
    try:start(a.parent.resolve(),a.queue.resolve(),a.pointer.resolve())
    except Exception as error:
        d=json.loads(a.queue.read_text());d.update(status='error',error=str(error));save(a.queue,d);raise
