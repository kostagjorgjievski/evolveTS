"""Unpaid public-source freshness checks, independent of model/reproducer slots.

A successful check means a validated listing was saved and delivered to each
agenda, not merely HTTP200. Errors retain last success and retry in five minutes.
"""
import datetime
import fcntl
import hashlib
import json
import math
import re
import sys
import time
import urllib.request
from pathlib import Path
from .investigations import Investigations

ENDPOINT = 'https://www.kaggle.com/api/i/kernels.KernelsService/ListKernels'


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp'); tmp.write_text(json.dumps(value, indent=2)+'\n'); tmp.replace(path)


def fetch_page(page):
    body = {'kernelFilterCriteria': {'listRequest': {
        'competitionId': 161954, 'pageSize': 100, 'page': page, 'sortBy': 'dateCreated'}}}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': 'Hermes-public-source-watch/1'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def listing(fetch=fetch_page):
    rows = []; seen = set()
    for page in range(1, 11):
        result = fetch(page)
        batch = result.get('kernels')
        if not isinstance(batch, list) or (page == 1 and not batch):
            raise ValueError('Missing notebook listing; HTML/login shells are not success')
        fresh = []
        for item in batch:
            if not item.get('scriptUrl') or not item.get('scriptVersionId'):
                raise ValueError('Notebook URL/version missing')
            key = str(item['id'])+':'+str(item['scriptVersionId'])
            if key not in seen: fresh.append(item); seen.add(key)
        if batch and not fresh:
            raise ValueError('Pagination repeated; cannot certify listing coverage')
        rows.extend(fresh)
        if len(batch) < 100: return rows
    raise ValueError('Listing pagination limit reached; coverage unresolved')


def enqueue(root, origin, topic, inputs=None, scheduling=None):
    root=Path(root); cfg=json.loads((root/'config.json').read_text())
    agenda=Investigations(root/'investigations.sqlite')
    try:
        previous=next((r for r in agenda.list() if r['origin']==origin),None)
        if previous:
            if previous['status']=='queued' and scheduling:
                checkpoint={**previous['checkpoint'],'scheduling':scheduling,'public_inputs':inputs}
                agenda.db.execute('UPDATE investigations SET checkpoint=? WHERE id=?',
                    (json.dumps(checkpoint),previous['id']));agenda.db.commit()
            return agenda.get(previous['id'])
        item=agenda.create(topic, origin=origin, priority=80,
                          budgets=cfg.get('agenda',{}).get('default_budgets'))
        if inputs or scheduling:
            checkpoint=item['checkpoint']
            if inputs:checkpoint['public_inputs']=inputs
            if scheduling:checkpoint['scheduling']=scheduling
            agenda.db.execute('UPDATE investigations SET checkpoint=? WHERE id=?',
                              (json.dumps(checkpoint),item['id']));agenda.db.commit()
        return agenda.get(item['id'])
    finally: agenda.close()


def score_claim(notebook):
    claims=[]
    public=notebook.get('bestPublicScore')
    if not isinstance(public,bool) and isinstance(public,(int,float)) and math.isfinite(public) and public>0:
        claims.append({'score':public,'kind':'platform_best_public_score','version_specific':False})
    # Require a decimal: v15, 76 qubits and dates are not score claims.
    for value in re.findall(r'(?<![\w.])(\d{1,3}\.\d+)(?![\w.])',notebook.get('title','')):
        score=float(value)
        if math.isfinite(score) and score>0:claims.append({'score':score,'kind':'title_claim','version_specific':True})
    best=max(claims,key=lambda c:c['score']) if claims else None
    return {'claimed_score':best['score'] if best else None,'claims':claims,
            'label':'Unverified overall portfolio score; scheduling only, not a task reward',
            'notebook_url':'https://www.kaggle.com'+notebook['scriptUrl'],
            'notebook_id':notebook['id'],'version_id':notebook['scriptVersionId']}


def enqueue_notebooks(directory, roots, rows, stamp):
    """One idempotent candidate per public notebook version, ordered by claim."""
    delivered=[]
    for notebook in rows:
        origin='kaggle-notebook:'+str(notebook['id'])+':'+str(notebook['scriptVersionId'])
        scheduling=score_claim(notebook)
        metadata_digest=hashlib.sha256(json.dumps([notebook.get('title'),scheduling],sort_keys=True).encode()).hexdigest()[:12]
        bundle=Path(directory)/'notebooks'/(str(notebook['id'])+'-'+str(notebook['scriptVersionId'])+'-'+metadata_digest)
        if not (bundle/'listing.json').exists():write(bundle/'listing.json',{'endpoint':ENDPOINT,'checked_utc':stamp,
            'notebooks':[notebook],'new_notebooks':[notebook],
            'scheduling':scheduling,'label':'Public metadata; scores unverified locally'})
        for root in roots:
            record=enqueue(root,origin,
                'Investigate this specific public notebook: '+scheduling['notebook_url']+'. '
                'Read sources/provided-0/listing.json, retrieve original source and dependencies, '
                'audit the task-specific mechanism, compatibility and licenses, and reproduce '
                'through unchanged official gates. Claimed overall portfolio score is scheduling '
                'metadata, not a task reward or verified result. Preserve negative evidence; '
                'an unresolved fetch is not proof that an account is required.',
                [{'path':str(bundle.resolve()),'url':scheduling['notebook_url'],
                  'license':'Inspect original source licenses','attribution':notebook.get('author',{}).get('userName','Kaggle author')}],
                scheduling=scheduling)
            # Supersede only untouched older versions; running research keeps
            # its frozen sources, receipts and consumed budget.
            agenda=Investigations(Path(root)/'investigations.sqlite')
            try:
                prefix='kaggle-notebook:'+str(notebook['id'])+':'
                for old in agenda.list('queued'):
                    if (old['origin'].startswith(prefix) and old['id']!=record['id']
                            and int(old['origin'].rsplit(':',1)[1])<int(notebook['scriptVersionId'])
                            and not old['consumed']['sessions']):
                        checkpoint={**old['checkpoint'],'superseded_by':record['id']}
                        agenda.db.execute('UPDATE investigations SET status=?,checkpoint=? WHERE id=?',
                            ('superseded',json.dumps(checkpoint),old['id']))
                agenda.db.commit()
            finally:agenda.close()
            delivered.append(record['id'])
    return delivered


def migrate_queued_listings(directory, roots):
    """Split idle legacy batches without touching active work or its budgets."""
    for root in roots:
        agenda=Investigations(Path(root)/'investigations.sqlite')
        try:
            batches=[];latest={}
            for record in agenda.list('queued'):
                if not record['origin'].startswith('kaggle-freshness:'):continue
                inputs=record['checkpoint'].get('public_inputs',[])
                if not inputs:continue
                source=Path(inputs[0]['path'])/'listing.json'
                if not source.exists():continue
                data=json.loads(source.read_text());rows=data.get('notebooks',data.get('new_notebooks',[]))
                if not rows:continue
                batches.append(record)
                for row in rows:
                    old=latest.get(str(row['id']))
                    if old is None or int(row['scriptVersionId'])>int(old['scriptVersionId']):latest[str(row['id'])]=row
            children=enqueue_notebooks(directory,[root],list(latest.values()),utc_stamp())
            for record in batches:
                checkpoint={**record['checkpoint'],'split_into_notebook_candidates':children}
                agenda.db.execute('UPDATE investigations SET status=?,checkpoint=? WHERE id=?',
                    ('superseded',json.dumps(checkpoint),record['id']))
            agenda.db.commit()
        finally:agenda.close()


def utc_stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def tick(directory, roots, fetch=fetch_page, now=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    statefile=directory/'status.json'
    state=json.loads(statefile.read_text()) if statefile.exists() else {}
    now=time.time() if now is None else now
    stamp=datetime.datetime.fromtimestamp(now,datetime.timezone.utc).isoformat()
    if now >= state.get('next_attempt_epoch',0):
        state['last_attempt_utc']=stamp
        try:
            rows=listing(fetch)
            keys={str(x['id'])+':'+str(x['scriptVersionId']) for x in rows}
            previous=set(state.get('seen_versions',[]))
            new=[x for x in rows if str(x['id'])+':'+str(x['scriptVersionId']) not in previous]
            fingerprint=sorted((str(x['id']),str(x['scriptVersionId']),x.get('title',''),str(x.get('bestPublicScore'))) for x in rows)
            digest=hashlib.sha256(json.dumps(fingerprint).encode()).hexdigest()[:20]
            bundle=directory/'listings'/digest
            if not (bundle/'listing.json').exists():write(bundle/'listing.json',{'endpoint':ENDPOINT,'checked_utc':stamp,
                'notebooks':rows,'new_notebooks':new,'label':'Public metadata; scores unverified locally'})
            enqueue_notebooks(directory,roots,rows,stamp)
            state.update(state='healthy',last_successful_check_utc=stamp,
                last_successful_check_epoch=now,next_attempt_epoch=now+1800,
                seen_versions=sorted(previous|keys),notebook_count=len(rows),new_count=len(new),
                consecutive_failures=0,last_error=None,requires_attention=False,latest_listing=str(bundle/'listing.json'))
        except Exception as exc:
            state.update(state='retrieval_unresolved',next_attempt_epoch=now+300,
                consecutive_failures=state.get('consecutive_failures',0)+1,
                last_error=type(exc).__name__+': '+str(exc)[:1000],
                requires_attention=True)
        write(statefile,state)
    day=datetime.datetime.fromtimestamp(now,datetime.timezone.utc).date().isoformat()
    for root in roots:
        cfg=json.loads((Path(root)/'config.json').read_text())
        for i,topic in enumerate(cfg.get('daily_paper_topics',[])):
            enqueue(root,f'daily-papers:{day}:{i}',topic)
    return state


def main():
    directory=Path(sys.argv[1]); roots=[Path(p) for p in sys.argv[2:]]
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/'watch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        migrate_queued_listings(directory,roots)
        while True:
            try:
                tick(directory,roots)
            except Exception as exc:
                write(directory/'watch-error.json', {'requires_attention': True,
                    'error': type(exc).__name__+': '+str(exc)[:1000], 'epoch': time.time()})
            time.sleep(30)


if __name__=='__main__':main()
