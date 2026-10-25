"""Frozen-library retrieval and scoped asynchronous advisor mailboxes."""
import asyncio,datetime,hashlib,json,re,uuid
from pathlib import Path

def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()

def retrieve(snapshot,query,limit=3):
    snapshot=Path(snapshot);index=json.loads((snapshot/'index.json').read_text())
    words=set(re.findall(r'[a-z0-9]+',query.lower()))
    scored=[]
    for item in index['methods']:
        entry=json.loads((snapshot/item['file']).read_text())
        body=json.dumps(entry).lower();score=sum(min(body.count(w),5) for w in words if len(w)>2)
        scored.append((score,item['id'],entry,item['revision']))
    scored.sort(key=lambda row:(-row[0],row[1]))
    return [{'revision':r,'method':e} for _,_,e,r in scored[:limit]]

def submit(run,branch,question):
    if not isinstance(question,str) or not question.strip() or len(question)>12000:
        raise ValueError('A nonempty question of at most 12000 characters is required')
    run=Path(run);inbox=run/'advisor/questions';inbox.mkdir(parents=True,exist_ok=True)
    # Actor and snapshot are supplied by the bound server, never by worker input.
    snapshot=run/'library';snapshot_hash=hashlib.sha256((snapshot/'index.json').read_bytes()).hexdigest()
    key=hashlib.sha256(json.dumps([branch,snapshot_hash,question]).encode()).hexdigest()
    for path in inbox.glob('*.question.json'):
        old=json.loads(path.read_text())
        if old.get('cache_key')==key:return old
    q={'id':uuid.uuid4().hex,'branch':branch,'question':question,'created_utc':utc(),'snapshot_sha256':snapshot_hash,'cache_key':key,'retrieved':retrieve(snapshot,question)}
    dest=inbox/(q['id']+'.question.json');temp=dest.with_suffix('.tmp');temp.write_text(json.dumps(q,indent=2));temp.replace(dest)
    return q

async def ask(run,branch,question,timeout=180):
    q=submit(run,branch,question);answer=Path(run)/'advisor/questions'/(q['id']+'.answer.json')
    loop=asyncio.get_running_loop();deadline=loop.time()+timeout
    while loop.time()<deadline:
        if answer.exists():
            data=json.loads(answer.read_text())
            if data.get('question_id')!=q['id']:raise ValueError('Answer identity mismatch')
            return {'status':'answered','question_id':q['id'],'advice':data,'retrieved':q['retrieved']}
        await asyncio.sleep(1)
    return {'status':'pending','question_id':q['id'],'message':'Research is pending. Use retrieved evidence and continue useful work; repeat the same question to retrieve the answer.','retrieved':q['retrieved']}
