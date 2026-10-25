"""One isolated OAuth Opus attempt, using the existing neutral chemistry guide."""
import asyncio,dataclasses,datetime,json,os,shutil,sys,time
from pathlib import Path
import dfthcsos_pilot as pilot
import claude_agent_sdk as sdk
ROOT=pilot.ROOT
MODEL='claude-opus-5-5'

def save(run,meta):
    (run/'pilot.json').write_text(json.dumps(meta,indent=2)+'\n')

def initialize(run):
    meta=pilot.initialize(run)
    guide=ROOT/'runs/dfthcsos/solo/20261024T194014Z-glm-max-prepared/worker/explore_b0/preparation-guide.md'
    branch=run/'worker/explore_b0'
    shutil.copyfile(guide,branch/'preparation-guide.md')
    baseline=json.loads((branch/'baseline-result.json').read_text())
    (branch/'parent-result.json').write_text(json.dumps({'development':baseline,'parent':'official baseline'},indent=2)+'\n')
    meta.update(provider='anthropic_oauth',worker_model=MODEL,effort='medium',experiment='opus_prepared_context_single_attempt',prepared_parent_context=True,conversation_memory=False,preparation_guide_source=str(guide),budget_scope='per_attempt',attempts=1)
    save(run,meta)
    return meta

async def develop(run,meta,token):
    branch,attempt,prompt=pilot.prepare(run)
    # Use the native Anthropic transport, with no alternate-provider routing.
    for key in list(os.environ):
        if key.startswith(('ANTHROPIC_','CLAUDE_')):os.environ.pop(key)
    auth=ROOT/'.credentials'/('opus-chemistry-'+run.name);auth.mkdir(mode=0o700,exist_ok=True)
    os.environ.update(CLAUDE_CODE_OAUTH_TOKEN=token,CLAUDE_CONFIG_DIR=str(auth/'cli'),CLAUDE_CODE_DISABLE_AUTO_MEMORY='1',CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',CLAUDE_CODE_EFFORT_LEVEL=meta['effort'],ENABLE_TOOL_SEARCH='false',MCP_TOOL_TIMEOUT='28800000')
    mcp=auth/'mcp.json'
    mcp.write_text(json.dumps({'mcpServers':{'acceptance':{'command':'/usr/bin/env','args':['-i','PATH=/usr/bin:/bin','HOME=/nonexistent','PYTHONDONTWRITEBYTECODE=1','TMPDIR='+str(ROOT/'outputs/dqi-validation/tmp'),str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/literature_acceptance/dfthcsos_server.py'),str(attempt)]}}}));mcp.chmod(0o600)
    rules=[f'{t}(/{branch}/**)' for t in ('Read','Grep','Glob')]+[f'{t}(/{attempt}/artifact/**)' for t in ('Edit','Write')]+[f'{t}(/{attempt}/proposal.md)' for t in ('Edit','Write')]+['mcp__acceptance__'+n for n in pilot.TOOLS]
    # Bypass the shared proxy runner's automatic conversation lookup. This is
    # a new conversation; transient retries may resume only this own session.
    session=json.loads((run/'private/session.json').read_text())['session_id'] if meta.get('resume_saved_session') else None
    if session:
        prompt='Continue this SAME chemistry attempt with your existing context, drafts and findings. The user changed reasoning effort to MEDIUM. This is not a new attempt or a reset budget. Use the remaining original allowance to research, implement and validate.'
    deadline=time.monotonic()+meta['max_session_seconds']-meta.get('session_seconds_used',0);retry=0
    while time.monotonic()<deadline:
        options=pilot.runner.backend.original_options(cwd=str(branch),model=MODEL,cli_path=str(ROOT/'runs/library-rsi/runtime/node_modules/.bin/claude'),tools=['Read','Grep','Glob','Edit','Write'],allowed_tools=rules,permission_mode='dontAsk',mcp_servers=str(mcp),max_turns=1000,effort=meta['effort'],thinking={'type':'adaptive'},setting_sources=[],resume=session,max_buffer_size=16*1024*1024,system_prompt={'type':'preset','preset':'claude_code','append':'Follow this task and own branch boundaries. Do not inspect other runs or credentials.'})
        try:
            async with asyncio.timeout(max(1,deadline-time.monotonic())):
                async for message in pilot.runner.backend.original_query(prompt=prompt if retry==0 else 'Continue your own saved attempt after a transient provider interruption. Preserve drafts and findings.',options=options):
                    data=dataclasses.asdict(message) if dataclasses.is_dataclass(message) else str(message)
                    with (run/'private/sdk-events.jsonl').open('a') as log:log.write(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'type':type(message).__name__,'data':data},default=str).replace(token,'[REDACTED]')+'\n')
                    if isinstance(message,sdk.SystemMessage) and message.subtype=='init':
                        session=message.data.get('session_id');(run/'private/session.json').write_text(json.dumps({'session_id':session}))
                    if isinstance(message,sdk.AssistantMessage):
                        meta['served_model']=message.model;save(run,meta)
                        if getattr(message,'error',None):raise RuntimeError(str(message.error))
                    if isinstance(message,sdk.ResultMessage) and message.is_error:raise RuntimeError(str(data))
            return
        except TimeoutError:raise
        except Exception as exc:
            detail=str(exc).replace(token,'[REDACTED]');retry+=1
            with (run/'private/retries.jsonl').open('a') as log:log.write(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'retry':retry,'error':detail})+'\n')
            if not any(s in detail.lower() for s in ['429','rate','500','502','503','504','overload']):raise
            await asyncio.sleep(min(120, max(0,deadline-time.monotonic())))

def work(run):
    meta=json.loads((run/'pilot.json').read_text());token=pilot.runner.environment(ROOT/'.credentials/claude-research.env')['CLAUDE_CODE_OAUTH_TOKEN']
    consumed=meta.get('session_seconds_used',0)
    meta.update(status='running',pid=os.getpid(),segment_started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());meta.setdefault('started_utc',meta['segment_started_utc']);save(run,meta);started=time.monotonic()
    try:asyncio.run(develop(run,meta,token))
    except Exception as exc:
        meta['worker_error']=(type(exc).__name__+': '+str(exc)).replace(token,'[REDACTED]')
        # Authentication/model errors are setup failures, not baseline results.
        if 'served_model' not in meta:
            meta.update(status='error',finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save(run,meta);return
    meta.update(status='grading',session_seconds_used=consumed+time.monotonic()-started);save(run,meta)
    sys.path.insert(0,str(ROOT/'tasks/dfthcsos'));import evaluator
    results=[]
    for label,salt in [('final-development',evaluator.PROTOCOL['development_salt']),('final-confirmation',evaluator.PROTOCOL['final_salt'])]:
        output=run/'private'/label
        try:
            result=evaluator.evaluate_program(run/'worker/explore_b0/attempt_00/artifact/program.py',output,salt=salt)
            results.append({'label':label,'status':result['status'],'reward':result['combined_score'],'cost':result['official']['score'],'receipt':str(output/'result.json'),'submission_sha256':result['official']['submission_sha256']})
        except Exception as exc:results.append({'label':label,'status':'ERROR','error':str(exc)})
    passed=all(r.get('status')=='PASS' for r in results)
    meta.update(status='completed' if passed else 'validation_failed',results=results,improved=passed and all(r['reward']>1 for r in results),finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save(run,meta)

if __name__=='__main__':
    run=Path(sys.argv[1]).resolve()
    if not run.is_relative_to(ROOT/'runs/dfthcsos'):raise ValueError('Chemistry pilot directory required')
    work(run)
