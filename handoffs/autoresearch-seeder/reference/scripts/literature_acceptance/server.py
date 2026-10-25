"""Bound public-source retrieval and sandboxed execution; no model shell tool."""
import signal,psutil
import asyncio,json,sys,urllib.request,urllib.parse,hashlib,tarfile,io,re,socket,ipaddress,os,tempfile,shutil
from pathlib import Path
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp import types
ROOT=Path(__file__).resolve().parents[2]
ATTEMPT=None;CACHE=None
def configure(attempt):
 global ATTEMPT,CACHE
 ATTEMPT=Path(attempt);CACHE=ATTEMPT.parent/'research';CACHE.mkdir(exist_ok=True)
def check(url):
 p=urllib.parse.urlparse(url)
 if p.scheme!='https' or not p.hostname or p.username or p.password:raise ValueError('Public HTTPS only')
 if any(not ipaddress.ip_address(x[4][0]).is_global for x in socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)):raise ValueError('Private addresses blocked')
 return url
class Redirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return super().redirect_request(req,fp,code,msg,headers,check(newurl))
def get(url,limit=4*2**20):
 req=urllib.request.Request(check(url),headers={'User-Agent':'DQI-literature-acceptance/1.0'})
 with urllib.request.build_opener(Redirect).open(req,timeout=45) as r:
  data=r.read(limit+1)
  if len(data)>limit:raise ValueError('Response too large')
  return data

def fetch(url):
 data=get(url);name=hashlib.sha256(url.encode()).hexdigest()[:16];dest=CACHE/(name+'.txt');dest.write_bytes(data)
 return {'url':url,'local_file':str(dest),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'preview':data[:8000].decode(errors='replace')}
def repo(url):
 m=re.fullmatch(r'https://github.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?',url)
 if not m:raise ValueError('Provide a GitHub repository root URL')
 owner,name=m.groups();meta=json.loads(get(f'https://api.github.com/repos/{owner}/{name}/commits/HEAD'));sha=meta['sha'];target=CACHE/f'{owner}__{name}__{sha[:12]}'
 if not target.exists():
  data=get(f'https://codeload.github.com/{owner}/{name}/tar.gz/{sha}',100*2**20)
  with tempfile.TemporaryDirectory(dir=CACHE,prefix='.download-') as tmp:
   total=0
   with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
    for item in archive:
     parts=Path(item.name).parts[1:]
     if not parts or '..' in parts or not item.isfile():continue
     relative=Path(*parts)
     if relative.suffix not in ('.py','.json','.md','.toml','.txt','.c','.h') and relative.name not in ('LICENSE','Makefile'):continue
     if item.size>4*2**20:continue
     total+=item.size
     if total>50*2**20:raise ValueError('Source exceeds 50 MiB')
     dest=Path(tmp)/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(archive.extractfile(item).read())
   Path(tmp).rename(target)
  # TemporaryDirectory tolerates a renamed temporary directory.
 files=[str(p.relative_to(target)) for p in target.rglob('*') if p.is_file()]
 return {'repository':url,'commit':sha,'directory':str(target),'files':files[:2500],'file_count':len(files)}
SCHEMAS={'validate_candidate':{'type':'object','properties':{},'additionalProperties':False},'diagnose_candidate':{'type':'object','properties':{},'additionalProperties':False},'fetch_source':{'type':'object','properties':{'url':{'type':'string'}},'required':['url'],'additionalProperties':False},'ask_researcher':{'type':'object','properties':{'question':{'type':'string'}},'required':['question'],'additionalProperties':False},'fetch_repository':{'type':'object','properties':{'url':{'type':'string'}},'required':['url'],'additionalProperties':False}}
DESCRIPTIONS={'ask_researcher':'Ask the designated literature researcher a focused technical question. It cannot write your candidate. Questions and answers are logged. Waits for the researcher response.', 'validate_candidate':'Fully validate your saved artifact/program.py with the unchanged official DQI verifier. No arguments. Returns score and errors.','diagnose_candidate':'Run saved artifact/diagnostic.py sandboxed for 60 seconds, 2 GiB. No arguments. No score.','fetch_source':'Fetch a public HTTPS source and cache it locally for Read. JSON, HTML and raw source supported.','fetch_repository':'Cache a public GitHub repository source tree at a pinned commit, rejecting links. Returns a file index. Repository sources are copied read-only into candidate sandbox under Path(__file__).parent/research/<directory-name>. Package roots are on sys.path. No network in execution sandbox.'}
async def listing(context,params):return types.ListToolsResult(tools=[types.Tool(name=n,inputSchema=s,description=DESCRIPTIONS[n]) for n,s in SCHEMAS.items()])
async def call(context,params):
 try:
  name=params.name;args=params.arguments or {}
  if name not in SCHEMAS:raise ValueError('Unknown tool')
  with (CACHE/'fetch-ledger.jsonl').open('a') as f:f.write(json.dumps({'tool':name,'arguments':args})+'\n')
  if name=='ask_researcher':
   import uuid,time
   if set(args)!={'question'} or not isinstance(args['question'],str) or len(args['question'])>12000:raise ValueError('One bounded question required')
   inbox=ATTEMPT.parents[2]/'private/questions';inbox.mkdir(parents=True,exist_ok=True)
   qid=uuid.uuid4().hex;(inbox/(qid+'.question.json')).write_text(json.dumps({'id':qid,'question':args['question'],'time':time.time()}))
   answer=inbox/(qid+'.answer.json')
   for _ in range(1200):
    if answer.exists():break
    await asyncio.sleep(1)
   if not answer.exists():raise TimeoutError('Researcher response not yet available; continue other work')
   result=json.loads(answer.read_text())
  elif name.startswith('fetch_'):
   if set(args)!={'url'}:raise ValueError('Exactly url is required')
   result=await asyncio.to_thread(repo if name=='fetch_repository' else fetch,args['url'])
  else:
   if args:raise ValueError('No arguments allowed')
   env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(ROOT/'outputs/dqi-validation/tmp')}
   process=await asyncio.create_subprocess_exec(str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/literature_acceptance/worker.py'),str(ATTEMPT),*(['--diagnostic'] if name=='diagnose_candidate' else []),env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,start_new_session=True)
   out,err=await process.communicate()
   if process.returncode:raise RuntimeError(err.decode(errors='replace')[-4000:])
   result=json.loads(out)
  return types.CallToolResult(content=[types.TextContent(text=json.dumps(result))],structuredContent=result)
 except Exception as e:return types.CallToolResult(isError=True,content=[types.TextContent(text=str(e))])
async def main():
 server=Server('acceptance',get_tool_input_schema=lambda n:SCHEMAS[n],on_list_tools=listing,on_call_tool=call)
 async with stdio_server() as (r,w):await server.run(r,w,server.create_initialization_options())
def stop_children():
 for p in psutil.Process().children(recursive=True):
  try:os.killpg(os.getpgid(p.pid),signal.SIGTERM)
  except (ProcessLookupError,psutil.Error):pass
if __name__=='__main__':
 configure(sys.argv[1])
 def stop(sig,frame):stop_children();raise SystemExit(128+sig)
 signal.signal(signal.SIGTERM,stop)
 try:asyncio.run(main())
 finally:stop_children()
