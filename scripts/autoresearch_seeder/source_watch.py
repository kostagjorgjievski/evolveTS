"""Unpaid public-source freshness checks, independent of model/reproducer slots.

A successful check means a validated listing was saved and delivered to each
agenda, not merely HTTP200. Errors retain last success and retry in five minutes.
"""
import datetime
import fcntl
import hashlib
import json
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


def enqueue(root, origin, topic, inputs=None):
    root=Path(root); cfg=json.loads((root/'config.json').read_text())
    agenda=Investigations(root/'investigations.sqlite')
    try:
        if any(r['origin']==origin for r in agenda.list()): return
        item=agenda.create(topic, origin=origin, priority=80,
                          budgets=cfg.get('agenda',{}).get('default_budgets'))
        if inputs:
            checkpoint=item['checkpoint'];checkpoint['public_inputs']=inputs
            agenda.db.execute('UPDATE investigations SET checkpoint=? WHERE id=?',
                              (json.dumps(checkpoint),item['id']));agenda.db.commit()
    finally: agenda.close()


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
            digest=hashlib.sha256(json.dumps(sorted(keys)).encode()).hexdigest()[:20]
            bundle=directory/'listings'/digest
            write(bundle/'listing.json',{'endpoint':ENDPOINT,'checked_utc':stamp,
                'notebooks':rows,'new_notebooks':new,'label':'Public metadata; scores unverified locally'})
            if new:
                for root in roots:
                    enqueue(root,'kaggle-freshness:'+digest,
                        'Review the new or updated public Kaggle notebooks in sources/provided-0/listing.json. '
                        'You select promising task-compatible directions, retrieve original source and dependencies, '
                        'check attribution and reproduce through unchanged official gates. Metadata scores are claims. '
                        'Consult own research memory; do not repeat existing validated methods. A failed fetch is '
                        'unresolved retrieval, not evidence that an account is required.',
                        [{'path':str(bundle.resolve()),'url':ENDPOINT,'license':'Inspect original source licenses',
                          'attribution':'Kaggle public notebook authors in listing'}])
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
        while True:
            try:
                tick(directory,roots)
            except Exception as exc:
                write(directory/'watch-error.json', {'requires_attention': True,
                    'error': type(exc).__name__+': '+str(exc)[:1000], 'epoch': time.time()})
            time.sleep(30)


if __name__=='__main__':main()
