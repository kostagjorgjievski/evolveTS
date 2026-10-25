"""Independent ongoing chemistry chains, with fresh prepared-context attempts."""
import datetime,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/literature_acceptance'))
import dfthcsos_opus_prepared as prepared

ENTRIES={'opus':'dfthcsos_opus_prepared.py','kimi':'dfthcsos_kimi_prepared.py','gpt':'dfthcsos_codex_prepared.py','glm':'dfthcsos_glm_provider_prepared.py'}
PROVIDERS={'opus':('anthropic_oauth','claude-opus-5-5'),'kimi':('kimi_proxy','k3.1-pro'),'gpt':('gpt_proxy','gpt-6.1-sol'),'glm':('glm_proxy','glm-5.3')}

def read(p):return json.loads(Path(p).read_text())
def save(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(p)
def live(run,meta):
    try:return str(run) in psutil.Process(meta['pid']).cmdline() and psutil.Process(meta['pid']).status()!=psutil.STATUS_ZOMBIE
    except (KeyError,psutil.Error):return False

def candidate_reward(meta):
    results=meta.get('results',[])
    if len(results)!=2 or any(r.get('status')!='PASS' for r in results):return None
    return min(r['reward'] for r in results)

def freeze(branch,run,meta):
    reward=candidate_reward(meta)
    if reward is None:return False
    best=read(branch/'best.json') if (branch/'best.json').exists() else {'reward':1.0}
    if reward<=best['reward']:return False
    source=run/'worker/explore_b0/attempt_00/artifact';dest=branch/'frozen'/run.name
    if any(p.is_symlink() for p in source.rglob('*')):raise RuntimeError('Candidate contains links; refusing snapshot')
    if not dest.exists():shutil.copytree(source,dest,ignore=shutil.ignore_patterns('__pycache__'))
    manifest={str(p.relative_to(dest)):hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.rglob('*') if p.is_file()}
    save(branch/'best.json',{'reward':reward,'source_run':str(run),'artifact':str(dest),'results':meta['results'],'manifest':manifest})
    return True

def worker_path(campaign,name,index):
    cfg=read(campaign/'campaign.json') if (campaign/'campaign.json').exists() else {}
    generation=cfg.get('run_generations',{}).get(name)
    prefix=name+'_'+generation if generation else name
    return campaign/'branches'/name/f'{prefix}_round_{index:04d}'

def new_attempt(campaign,name,index):
    branch=campaign/'branches'/name;run=worker_path(campaign,name,index);meta=prepared.initialize(run)
    provider,model=PROVIDERS[name]
    meta.update(provider=provider,worker_model=model,effort='max' if name=='glm' else 'medium',harness='codex' if name=='gpt' else 'claude_code',experiment='ongoing_prepared_chemistry',campaign=str(campaign),round=index,max_session_seconds=12000,session_seconds_used=0,prepared_parent_context=True,conversation_memory=False)
    if (branch/'best.json').exists():
        best=read(branch/'best.json');artifact=run/'worker/explore_b0/attempt_00/artifact';shutil.rmtree(artifact);shutil.copytree(best['artifact'],artifact)
        save(run/'worker/explore_b0/parent-result.json',{'development':best['results'][0],'confirmation':best['results'][1],'best_confirmed_reward':best['reward'],'parent':'own branch best verified source'})
        meta['parent_best_reward']=best['reward']
    else:meta['parent_best_reward']=1.0
    save(run/'pilot.json',meta)
    assert not (run/'private/sdk').exists()
    return run

def launch(run,name):
    cmd=[str(ROOT/'.venv/bin/python'),'-u',str(ROOT/'scripts/literature_acceptance'/ENTRIES[name]),str(run)]
    if name=='kimi':cmd+=['--work']
    with (run/'controller.log').open('a') as log:proc=subprocess.Popen(cmd,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    m=read(run/'pilot.json');m.update(status='starting',pid=proc.pid);save(run/'pilot.json',m)
    save(ROOT/('runs/dfthcsos/active-glm-provider-prepared.json' if name=='glm' else f'runs/dfthcsos/active-{name}-prepared.json'),{'run':str(run),'pid':proc.pid,'status':'launched','campaign':str(run.parents[2]),'provider':PROVIDERS[name][0],'effort':'max' if name=='glm' else 'medium','harness':'codex' if name=='gpt' else 'claude_code'})
    return proc.pid

def main(campaign):
    cfg=read(campaign/'campaign.json');states=read(campaign/'status.json') if (campaign/'status.json').exists() else {'branches':{n:{'run':p,'round':1} for n,p in cfg['initial_runs'].items()}}
    states.update(status='running',pid=os.getpid());save(campaign/'status.json',states)
    while True:
        for name,state in states['branches'].items():
            if state.get('status')=='needs_attention':continue
            run=Path(state['run']);meta=read(run/'pilot.json')
            if live(run,meta):state['status']=meta['status'];continue
            if meta.get('status') not in ['completed','validation_failed']:
                state.update(status='needs_attention',error='Worker ended without final grading; preserved drafts and allowance for recovery');continue
            branch=campaign/'branches'/name;branch.mkdir(parents=True,exist_ok=True)
            freeze(branch,run,meta)
            if state.get('processed_run')!=str(run):
                with (campaign/'transitions.jsonl').open('a') as log:log.write(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'branch':name,'finished_round':state['round'],'run':str(run),'status':meta['status'],'verified_reward':candidate_reward(meta)})+'\n')
                state['processed_run']=str(run)
            index=state['round']+1;next_run=new_attempt(campaign,name,index);pid=launch(next_run,name)
            state.update(run=str(next_run),round=index,status='starting',pid=pid)
        states['updated_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save(campaign/'status.json',states);time.sleep(10)

if __name__=='__main__':main(Path(sys.argv[1]).resolve())
