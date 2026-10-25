"""Run chemistry E0 (3x11), actual DreamRSI dreaming, then stop at level boundary."""
import json,os,subprocess,sys
from pathlib import Path
from supervise import ROOT,read,save

def run(c):
    count=len(read(c/'campaign.json')['initial_runs']);budget=count*11
    env={**os.environ,'DQI_INDEPENDENT_BRANCHES':'1','CLAUDE_EXEC_TIMEOUT_SEC':'12000','DRSI_PRESERVE_DRAFTS':'1','DRSI_HISTORY_SEED_MODE':'copy','DRSI_EVAL_PYTHON':str(ROOT/'.dfthcsos-venv/bin/python')}
    entry=[str(ROOT/'.venv/bin/python'),'-u',str(ROOT/'scripts/chemistry_campaign/rsi_controller.py'),str(c)];w=c/'workspace'
    save(c/'status.json',{'status':'exploring','pid':os.getpid(),'branches':count,'attempts_per_branch':11,'budget':budget,'next_stage':f'dream_after_all{budget}'})
    cmd=entry+['explore','run','-w',str(w),'-a','claude','--policy-source','baseline','--cycle','0','--branches',str(count),'--refine','10','--max-workers',str(count),'--eval-program','artifact/program.py','--eval-timeout','172800','--no-explore-shell','--direction-mode','off','--problem',str(ROOT/'tasks/dfthcsos/dfthcsos.txt'),'--evaluator',str(ROOT/'tasks/dfthcsos/evaluator.py'),'--init-program',str(ROOT/'tasks/dfthcsos/init_program.py')]
    with (c/'exploration.log').open('a') as log:code=subprocess.call(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    if code:raise RuntimeError(f'Chemistry E0 engine exited {code}; drafts retained')
    if len(read(w/'raw_scores.json').get('nodes',[]))!=budget:raise RuntimeError('Incomplete chemistry replay; refusing early dreaming')
    save(c/'status.json',{'status':'dreaming','pid':os.getpid(),'completed_nodes':budget})
    with (c/'dreaming.log').open('a') as log:code=subprocess.call(entry+['learning','discover','-w',str(w),'-a','claude','--rounds','3','--retry-rounds','1','--max-retry-batches','1','--eval-timeout','3600','--max-workers','1'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    if code:raise RuntimeError(f'Actual DreamRSI dreaming exited {code}; no policy promoted')
    from dream_rsi.learning.allocate import promote_method_to_workspace
    jobs=sorted((w/'learning').glob('*/manifest.json'))
    if not jobs:raise RuntimeError('No actual policy learning manifest')
    policy=promote_method_to_workspace(jobs[-1].parent,w)
    save(c/'status.json',{'status':'level_complete','completed_nodes':budget,'dreaming':'complete','promoted_policy':str(policy),'next_level':'ready; E1 not automatically started'})
if __name__=='__main__':
    c=Path(sys.argv[1]).resolve()
    try:run(c)
    except BaseException as e:save(c/'status.json',{'status':'error','error':str(e),'pid':os.getpid()});raise
