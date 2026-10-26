"""Evidence-linked scout packets and descriptive, never causal, outcome metrics."""
import json
import math
import re
from pathlib import Path
from .models import atomic_write, digest, utc

VERSION = 'scout-v2'
TEXT_FIELDS = ('mechanism', 'code_sections', 'compatibility', 'uncertainty',
               'first_test', 'rejection_conditions', 'next_action')


def known_methods(facts):
    """Only already scope-filtered knowledge may enter a worker's index."""
    result=[]
    for fact in facts:
        payload=fact.get('payload',{})
        memory=payload.get('research_memory',payload)
        for h in memory.get('hypotheses',[]):
            result.append({'record_id':fact['id'],'mechanism':h.get('mechanism',''),
                           'source_urls':h.get('source_urls',[])})
        saved=payload.get('scout_packet')
        if saved:
            result.append({'record_id':fact['id'],'mechanism':saved['mechanism'],
                'source_urls':[s['url'] for s in saved['citations']],
                'content_hashes':[s['content_sha256'] for s in saved['citations']]})
        if payload.get('mechanism'):
            result.append({'record_id':fact['id'],'mechanism':payload['mechanism'],
                           'source_urls':[s['url'] for s in payload.get('sources',[])],
                           'content_hashes':[s.get('content_sha256') for s in payload.get('sources',[]) if s.get('content_sha256')]})
    return result


def normalize(text):
    return re.sub(r'\W+',' ',text.casefold()).strip()


def packet(store, args, task, known=()):
    """Validate citations and structure; the scientific content stays unverified."""
    allowed=set(TEXT_FIELDS)|{'hypothesis_id','dependency_urls','resource_estimates'}
    if set(args)-allowed:raise ValueError('Unknown packet fields')
    for field in TEXT_FIELDS:
        if not isinstance(args.get(field),str) or not args[field].strip():
            raise ValueError('Nonempty '+field+' required; explicitly state unknowns')
    hypothesis=store.get_hypothesis(args.get('hypothesis_id',''))
    if not hypothesis:raise ValueError('Record a hypothesis first')
    urls=hypothesis.get('source_urls',[])
    if not urls:raise ValueError('Original fetched source URLs required')
    dependencies=args.get('dependency_urls',[])
    if not isinstance(dependencies,list) or any(not isinstance(u,str) for u in dependencies):
        raise ValueError('dependency_urls must be a list of URLs')
    citations=[];unresolved=[]
    for url in dict.fromkeys(urls+dependencies):
        source=store.get_source(url)
        if not source or source.get('status')!='accessed' or not source.get('content_sha256'):
            unresolved.append(url);continue
        citations.append({k:source.get(k,'') for k in
                          ('url','content_sha256','license','attribution')})
    if any(u not in {s['url'] for s in citations} for u in urls):
        raise ValueError('Every hypothesis citation must have a fetched, hashed receipt')
    estimates=[]
    for entry in args.get('resource_estimates',[]):
        if task!='dqi':raise ValueError('Resource formula available only for DQI')
        if set(entry)!={'source_url','Q','T','R'}:raise ValueError('DQI estimate requires source_url,Q,T,R')
        if entry['source_url'] not in {s['url'] for s in citations}:raise ValueError('Estimate needs fetched citation')
        vals=[entry[k] for k in ('Q','T','R')]
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in vals):
            raise ValueError('Finite positive resource inputs required')
        cost=entry['R']*entry['Q']**2*entry['T']
        if not math.isfinite(cost):raise ValueError('Resource estimate overflow')
        estimates.append({**entry,'estimated_cost':cost,'formula':'R*Q^2*T',
                          'label':'arithmetic from model-transcribed source claims; not official measurement'})
    matches=[]
    for other in known:
        same_method=normalize(other['mechanism'])==normalize(args['mechanism'])
        shared=sorted(set(other.get('source_urls',[])) & set(urls))
        shared_hashes=sorted(set(other.get('content_hashes',[])) & {s['content_sha256'] for s in citations})
        if same_method or shared or shared_hashes:matches.append({'record_id':other['record_id'],
            'reason':'same mechanism text' if same_method else 'shared source; may be a different method',
            'shared_urls':shared,'shared_content_hashes':shared_hashes})
    content={k:args[k] for k in TEXT_FIELDS}
    roles=store.list_events('research_role')
    content.update(recorded_role=roles[-1]['role'] if roles else 'unspecified',version=VERSION,hypothesis_id=hypothesis['id'],citations=citations,
                   unresolved_dependencies=unresolved,resource_estimates=sorted(estimates,key=lambda x:x['estimated_cost']),
                   duplicate_candidates=matches,science_status='requires independent reproduction',
                   handoff_status='needs_dependency_recovery' if unresolved else 'ready_for_review',
                   certification=False)
    content['fingerprint']=digest({'mechanism':normalize(args['mechanism']),
        'sources':sorted(s['content_sha256'] for s in citations)})
    previous=store.list_events('scout_packet')
    if any(e['packet']['fingerprint']==content['fingerprint'] for e in previous):
        content['duplicate_packet']=True
    else:content['duplicate_packet']=False
    store.event('scout_packet',{'packet':content})
    return content


def checkpoint(store, job, role):
    packets=store.list_events('scout_packet');decisions=store.list_decisions()
    rejects=[d for d in decisions if d['action']=='reject']
    result={'version':VERSION,'utc':utc(),'role':role,'packet_count':len(packets),
        'handoff_complete':bool(packets and packets[-1]['packet']['handoff_status']=='ready_for_review'),
        'latest_packet':packets[-1]['packet'] if packets else None,
        'missing_packet':not bool(packets),'rejection_audit_required':bool(rejects and int(digest(str(job))[:8],16)%5==0),
        'note':'Structure is checked, scientific claims are not certified. Audit sample is deterministic 20%, not an extra paid authorization.'}
    store.event('scout_checkpoint',{'role':role,'packet_present':bool(packets),'handoff_complete':result['handoff_complete']})
    atomic_write(Path(job)/'worker/scout-checkpoint.json',json.dumps(result,indent=2))
    return result


def metrics(root):
    """Read-only summary. Group by activation marker; do not claim causal uplift."""
    import sqlite3
    root=Path(root);fingerprints={};summary={'utc':utc(),'cohorts':{},'comparison':'observational; different sources and provider outages confound benefit'}
    for statepath in root.glob('jobs/autoresearch-seeder/*/*/job.json'):
        job=statepath.parent;db=job/'private/research.sqlite'
        if not db.exists():continue
        con=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
        try:
            events=[(k,json.loads(v)) for k,v in con.execute('select kind,payload from events')]
            cohort='scout-v2' if any(k=='scout_policy' for k,v in events) else 'legacy'
            s=summary['cohorts'].setdefault(cohort,dict(jobs=0,packets=0,ready_packets=0,duplicate_packets=0,
                 hypotheses=0,decisions=0,provider_errors=0,fetch_errors=0,model_seconds=0,verified_exports=0,
                 reviews=0,review_corrections=0,rejected_reviews=0,seed_elapsed_seconds=[],
                 scout_checkpoints=0,complete_scout_checkpoints=0,ready_scout_packets=0))
            fingerprints.setdefault(cohort,set())
            s['jobs']+=1;s['hypotheses']+=con.execute('select count(*) from hypotheses').fetchone()[0]
            s['decisions']+=con.execute('select count(*) from decisions').fetchone()[0]
            s['model_seconds']+=con.execute("select coalesce(sum(seconds),0) from budget_ledger where category='model'").fetchone()[0]
            for k,v in events:
                if k=='scout_packet':
                    p=v['packet'];fingerprints[cohort].add(p['fingerprint']);s['packets']+=1;s['ready_packets']+=p['handoff_status']=='ready_for_review';s['duplicate_packets']+=p.get('duplicate_packet',False)
                if k=='scout_checkpoint' and v['role']=='scout':
                    s['scout_checkpoints']+=1;s['complete_scout_checkpoints']+=v['handoff_complete']
                if k=='scout_packet' and v['packet'].get('recorded_role')=='scout' and v['packet']['handoff_status']=='ready_for_review':
                    s['ready_scout_packets']+=1
                if k=='scout_review':
                    s['reviews']+=1;s['review_corrections']+=v.get('outcome')=='corrected';s['rejected_reviews']+=v.get('outcome')=='rejected'
                s['provider_errors']+=k=='provider_error'
                s['fetch_errors']+=k=='tool' and v.get('tool')=='fetch_source' and v.get('status')=='error'
            exports=list((job/'exports').glob('seed-*/SEAL.json'));s['verified_exports']+=len(exports)
            # Wall elapsed includes queues; model_seconds is reported separately.
            from datetime import datetime
            state=json.loads(statepath.read_text());started=state.get('created_utc')
            if started:
                for seal in exports:
                    manifest=json.loads((seal.parent/'MANIFEST.json').read_text())
                    if manifest.get('created_utc'):
                        s['seed_elapsed_seconds'].append((datetime.fromisoformat(manifest['created_utc'])-datetime.fromisoformat(started)).total_seconds())
        finally:con.close()
    for cohort,s in summary['cohorts'].items():
        s['distinct_source_mechanism_packets']=len(fingerprints[cohort])
    summary['review_due']=summary['cohorts'].get('scout-v2',{}).get('scout_checkpoints',0)>=6
    return summary


def update_report(root):
    """Two model lanes may finish together; serialize the dashboard write."""
    import fcntl
    root=Path(root)
    with (root/'scout-quality-report.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        result=metrics(root)
        atomic_write(root/'scout-quality-latest.json',json.dumps(result,indent=2))
        return result


def review(store, args):
    roles=store.list_events('research_role')
    if roles and roles[-1]['role']!='reproducer':raise ValueError('Independent reproducer must review, not the scout')
    required={'fingerprint','outcome','source_urls','mistakes','first_test','next_action'}
    if set(args)!=required:raise ValueError('Complete review fields required')
    if args['outcome'] not in ('accepted_for_test','corrected','rejected'):
        raise ValueError('Review is not official acceptance')
    packets=[e['packet'] for e in store.list_events('scout_packet')]
    if args['fingerprint'] not in {p['fingerprint'] for p in packets}:raise ValueError('Unknown packet fingerprint')
    if not args['source_urls'] or any(not store.get_source(u) or store.get_source(u).get('status')!='accessed' for u in args['source_urls']):
        raise ValueError('Review must cite fetched original sources')
    if not args['first_test'] or not args['next_action']:raise ValueError('Test and next action required')
    if args['outcome']=='corrected' and not args['mistakes']:raise ValueError('Describe corrections')
    store.event('scout_review',{**args,'label':'independent model review; not scientific certification'})
    return {'recorded':True,'officially_validated':False}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('root');parser.add_argument('--output')
    args=parser.parse_args();result=metrics(args.root)
    if args.output:atomic_write(args.output,json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
