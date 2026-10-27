"""Task-score triage and model-time exploration allocation; never scientific grading."""
import datetime,json,math,time
from pathlib import Path
from .scout_leads import task_score
_cache={}

def best_confirmed(root,task):
    root=Path(root);host=root.parents[2]
    key=(str(host),task)
    if key in _cache and time.monotonic()-_cache[key][0]<60:return _cache[key][1]
    import sys
    portable=Path(__file__).resolve().parents[3]/'RSI'
    if not (portable/'dashboard/collect.py').is_file():raise RuntimeError('Verified-score collector requires the sibling RSI source checkout')
    if str(portable) not in sys.path:sys.path.insert(0,str(portable))
    from dashboard.collect import sealed_seeds,campaign
    seeds,_,_=sealed_seeds(root,task)
    scores=[s['score'] for s in seeds]+[campaign(host,task).get('best_score') or 1.0]
    best=max(scores,default=1.0);_cache[key]=(time.monotonic(),best);return best

def classify(record,best,task):
    cp=record.get('checkpoint',{});lead=cp.get('scout_lead',{})
    if cp.get('reproduction_policy_grandfathered'):return {'bucket':'continuation','mode':'full','reason':'Preserved active reproduction'}
    score=task_score(cp.get('scheduling',{}),task)
    if score is not None and score>best:return {'bucket':'exploit','mode':'full','reason':'Reported task factor exceeds confirmed best'}
    distinct=bool(lead.get('distinct_approach') and lead.get('distinct_reason','').strip())
    if score is None:return {'bucket':'explore','mode':'assessment','reason':'Unknown or incomparable task factor: short assessment only'}
    if not distinct:return {'bucket':'skip','mode':'skip','reason':'Lower/equal factor without a stated distinct mechanism'}
    if score>=.9*best:return {'bucket':'explore','mode':'full','reason':'Distinct approach within10% of best'}
    return {'bucket':'explore','mode':'assessment','reason':'Distinct approach more than10% below best: cheap test only'}

def usage(root):
    day=datetime.datetime.now(datetime.timezone.utc).date().isoformat();used={'exploit':0.,'explore':0.}
    for p in (Path(root)/'parallel-sessions').glob('*/settled.json'):
        x=json.loads(p.read_text());bucket=x.get('policy_bucket')
        if x.get('day')==day and bucket in used:used[bucket]+=x.get('actual_model_seconds',x.get('reserved_seconds',0))
    state=Path(root)/'parallel-state.json'
    if state.exists():
        for x in json.loads(state.read_text()).get('active',{}).values():
            if x.get('day')==day and x.get('policy_bucket') in used:used[x['policy_bucket']]+=x.get('reserved_seconds',0)
    return used

def exploration_allowance(used):
    # Up to one ten-minute assessment initially; thereafter cap at20% of
    # allocated model time, with the same bounded startup allowance.
    return max(0,600+used['exploit']/4-used['explore'])

def annotate(root,config,record):
    best=best_confirmed(root,config['task']);decision=classify(record,best,config['task'])
    decision.update(best_confirmed=best,reported_task_factor=task_score(record.get('checkpoint',{}).get('scheduling',{}),config['task']))
    record['checkpoint']['reproduction_policy']=decision
    return decision
