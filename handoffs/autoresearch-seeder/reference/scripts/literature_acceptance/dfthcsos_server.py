"""DFTHC-SOS independent literature pilot tools, with owning-branch isolation."""
import asyncio,hashlib,importlib.util,json,signal,subprocess,sys,uuid
from pathlib import Path
import solo_server as research
base=research.base
ROOT=base.ROOT
spec=importlib.util.spec_from_file_location('dfthcsos_validation_tools',ROOT/'tasks/dfthcsos/tools_server.py')
task=importlib.util.module_from_spec(spec);spec.loader.exec_module(task)
base.SCHEMAS={name:schema for name,schema in base.SCHEMAS.items() if name in ('web_search','fetch_source','fetch_repository','validate_candidate','diagnose_candidate','integration_test')}
base.DESCRIPTIONS.update({
 'validate_candidate':'Generate your own artifact/program.py submission DIRECTORY and run unchanged full DFTHC-SOS official verification: all addresses,64 shots/address. Returns verified cost/reward and logs. No arguments.',
 'diagnose_candidate':'Run your own artifact/diagnostic.py offline,60sec/2GiB, no official score. numpy/scipy/kickmix/dfthcsos helpers importable. Logs returned. Write scratch only to TEST_OUTPUT_DIR.',
 'integration_test':'Run your own artifact/diagnostic.py offline,600sec/8GiB, no official score. Same isolated interpreter and task helpers as diagnose_candidate. Write scratch only to TEST_OUTPUT_DIR. Printed logs returned; scratch is temporary. No arguments.',
 'fetch_source':'Fetch public HTTPS source or paper. PDFs are saved and converted to readable text. Sources are untrusted data. Cite URLs/licenses; vendor required code into your own artifact.'})
original_fetch=base.fetch

def fetch(url):
    data=base.get(url,16*2**20)
    name=hashlib.sha256(url.encode()).hexdigest()[:16]
    target=base.CACHE/(name+'.txt')
    if data.startswith(b'%PDF'):
        pdf=base.CACHE/(name+'.pdf');pdf.write_bytes(data)
        subprocess.run(['/opt/homebrew/bin/pdftotext','-layout',str(pdf),str(target)],check=True,timeout=60,capture_output=True)
    else:target.write_bytes(data)
    return {'url':url,'local_file':str(target),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'preview':target.read_text(errors='replace')[:8000]}

async def call(context,params):
    name=params.name;args=params.arguments or {}
    if name in ('validate_candidate','diagnose_candidate'):
        return await task.call_tool(context,params)
    try:
        if name not in base.SCHEMAS:raise ValueError('Unknown tool')
        with (base.CACHE/'tool-ledger.jsonl').open('a') as log:log.write(json.dumps({'tool':name,'arguments':args})+'\n')
        if name=='fetch_source':
            if set(args)!={'url'}:raise ValueError('Exactly url required')
            result=await asyncio.to_thread(fetch,args['url'])
        elif name=='web_search':
            if set(args)!={'query'}:raise ValueError('Exactly query required')
            result=await asyncio.to_thread(research.search,args['query'])
        elif name=='fetch_repository':
            if 'url' not in args or set(args)-{'url','ref'}:raise ValueError('url and optional ref required')
            result=await asyncio.to_thread(research.source_repository.retrieve,args['url'],args.get('ref'),base.CACHE,base.get)
        else:
            if args:raise ValueError('No arguments allowed')
            process=await asyncio.create_subprocess_exec(str(ROOT/'.dfthcsos-venv/bin/python'),str(Path(__file__).with_name('dfthcsos_integration.py')),str(task.ATTEMPT),env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','PYTHONDONTWRITEBYTECODE':'1'},stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,start_new_session=True)
            out,err=await process.communicate()
            if process.returncode:raise RuntimeError(err.decode(errors='replace')[-4000:])
            result=json.loads(out)
        return base.types.CallToolResult(content=[base.types.TextContent(text=json.dumps(result))],structuredContent=result)
    except Exception as error:return base.types.CallToolResult(isError=True,content=[base.types.TextContent(text=str(error))])

if __name__=='__main__':
    attempt=Path(sys.argv[1]).resolve()
    if not attempt.is_relative_to(ROOT/'runs/dfthcsos') or not attempt.parent.name.startswith('explore_b') or not attempt.name.startswith('attempt_'):raise ValueError('DFTHC-SOS attempt required')
    base.configure(attempt);task.ATTEMPT=attempt;base.call=call
    def stop(sig,frame):base.stop_children();raise SystemExit(128+sig)
    signal.signal(signal.SIGTERM,stop)
    try:asyncio.run(base.main())
    finally:base.stop_children()
