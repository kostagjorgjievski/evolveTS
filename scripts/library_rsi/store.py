"""Versioned research library. No campaign scheduling or model calls."""
import argparse,datetime,hashlib,json,re,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import registry as task_registry
ROOT=Path(__file__).resolve().parents[2]
DEFAULT_DB=ROOT/'runs/library-rsi/library.sqlite'
LEVELS={'published_claim','algebra_checked','microcircuit_checked','development_verified','independently_verified'}
SCHEMA='''
CREATE TABLE IF NOT EXISTS methods(id TEXT PRIMARY KEY, latest_revision TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS revisions(hash TEXT PRIMARY KEY,method_id TEXT NOT NULL,payload TEXT NOT NULL,curator TEXT NOT NULL,created_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,url TEXT NOT NULL,revision TEXT,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,method_revision TEXT NOT NULL,level TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY,method_id TEXT NOT NULL,reviewer TEXT NOT NULL,payload TEXT NOT NULL,created_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,created_utc TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS method_search USING fts5(method_id UNINDEXED,body);
'''
def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def connect(path=DEFAULT_DB):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(path,timeout=30);db.execute('PRAGMA journal_mode=WAL');db.executescript(SCHEMA);return db

def validate(entry):
 if not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',entry.get('id','')):raise ValueError('Stable slug id required')
 for field in ('title','task','mechanism','family'):
  if not isinstance(entry.get(field),str) or not entry[field].strip():raise ValueError('Missing '+field)
 if not task_registry.TASK_ID.fullmatch(entry['task']):raise ValueError('Invalid task id')
 if not entry.get('sources'):raise ValueError('Primary sources required')
 for source in entry['sources']:
  if not source.get('url','').startswith('https://'):raise ValueError('HTTPS source URLs required')
 advisor=entry.get('advisor',{})
 for field in ('continue_when','pivot_when','explore_when'):
  if not isinstance(advisor.get(field),list):raise ValueError('Decision field missing: '+field)
 if not advisor.get('first_test'):raise ValueError('Smallest useful test required')
 for evidence in entry.get('evidence',[]):
  if evidence.get('level') not in LEVELS:raise ValueError('Unknown evidence level')
  if evidence['level'] in ('development_verified','independently_verified'):
   artifact=evidence.get('artifact')
   if not artifact:raise ValueError('Verified claim requires a local verifier receipt')
   path=(ROOT/artifact).resolve()
   if not any(path.is_relative_to(ROOT/base) for base in ('outputs','runs')):raise ValueError('Receipt outside results folders')
   receipt=json.loads(path.read_text())
   task_registry.validate_receipt(entry['task'],receipt,evidence['level'])
   evidence['receipt_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
 return entry

def ingest(db,entries,curator):
 prepared=[validate(json.loads(canonical(e))) for e in entries]
 with db:
  for entry in prepared:
   previous=show(db,entry['id'])
   if previous and previous['task']!=entry['task']:raise ValueError('Method id already belongs to another task; use task-prefixed ids')
   revision=digest(entry)
   db.execute('INSERT OR IGNORE INTO revisions VALUES (?,?,?,?,?)',(revision,entry['id'],canonical(entry),curator,now()))
   db.execute('INSERT INTO methods VALUES (?,?) ON CONFLICT(id) DO UPDATE SET latest_revision=excluded.latest_revision',(entry['id'],revision))
   for source in entry['sources']:
    sid=digest({'url':source['url'],'commit':source.get('commit')})
    db.execute('INSERT OR IGNORE INTO sources VALUES (?,?,?,?)',(sid,source['url'],source.get('commit'),canonical(source)))
   for evidence in entry.get('evidence',[]):db.execute('INSERT OR IGNORE INTO evidence VALUES (?,?,?,?)',(digest([revision,evidence]),revision,evidence['level'],canonical(evidence)))
   db.execute('DELETE FROM method_search WHERE method_id=?',(entry['id'],))
   db.execute('INSERT INTO method_search VALUES (?,?)',(entry['id'],canonical(entry)))
  db.execute('INSERT INTO events(kind,payload,created_utc) VALUES (?,?,?)',('ingest',canonical({'curator':curator,'ids':[e['id'] for e in prepared]}),now()))
 return [{'id':e['id'],'revision':digest(e)} for e in prepared]

def show(db,method_id):
 row=db.execute('SELECT payload FROM methods m JOIN revisions r ON r.hash=m.latest_revision WHERE m.id=?',(method_id,)).fetchone()
 return json.loads(row[0]) if row else None

def search(db,query,task='dqi',limit=10):
 words=re.findall(r'[\w-]+',query)
 if not words:return []
 expression=' OR '.join('"'+w+'"' for w in words)
 rows=db.execute('SELECT method_id FROM method_search WHERE method_search MATCH ? ORDER BY rank',(expression,))
 results=[]
 for (mid,) in rows:
  e=show(db,mid)
  if e['task']==task:results.append(e)
  if len(results)>=limit:break
 return results

def snapshot(db,directory,task='dqi'):
 if not task_registry.TASK_ID.fullmatch(task):raise ValueError('Invalid task id')
 directory=Path(directory)
 existing=directory/'index.json'
 if existing.exists() and json.loads(existing.read_text()).get('task_id',task)!=task:raise ValueError('Snapshot directory belongs to another task')
 directory.mkdir(parents=True,exist_ok=True);index=[]
 for mid,revision in db.execute('SELECT id,latest_revision FROM methods ORDER BY id'):
  entry=show(db,mid)
  if entry['task']!=task:continue
  path=directory/(mid+'.json');path.write_text(json.dumps(entry,indent=2,ensure_ascii=False)+'\n')
  index.append({'id':mid,'title':entry['title'],'revision':revision,'file':path.name,'family':entry['family']})
 (directory/'index.json').write_text(json.dumps({'generated_utc':now(),'task_id':task,'production_enabled':False,'methods':index},indent=2)+'\n')
 return index

def main():
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,default=DEFAULT_DB);sub=p.add_subparsers(dest='command',required=True)
 sub.add_parser('init');i=sub.add_parser('ingest');i.add_argument('file',type=Path);i.add_argument('--curator',required=True)
 s=sub.add_parser('search');s.add_argument('query');s.add_argument('--task',default='dqi');s.add_argument('--limit',type=int,default=10)
 sh=sub.add_parser('show');sh.add_argument('id');sn=sub.add_parser('snapshot');sn.add_argument('directory',type=Path);sn.add_argument('--task',default='dqi')
 a=p.parse_args();db=connect(a.db)
 if a.command=='init':result={'database':str(a.db),'production_enabled':False}
 elif a.command=='ingest':result=ingest(db,json.loads(a.file.read_text()),a.curator)
 elif a.command=='search':result=search(db,a.query,a.task,a.limit)
 elif a.command=='show':result=show(db,a.id)
 else:result=snapshot(db,a.directory,a.task)
 print(json.dumps(result,indent=2,ensure_ascii=False));db.close()
if __name__=='__main__':main()
