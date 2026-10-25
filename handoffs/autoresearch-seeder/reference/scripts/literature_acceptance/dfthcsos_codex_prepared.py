"""Native Codex chemistry worker with branch isolation and official final grading."""
import datetime,json,os,signal,subprocess,sys,time,socket,threading,secrets
from pathlib import Path
import dfthcsos_pilot as pilot
ROOT=pilot.ROOT

def save(run,meta):(run/'pilot.json').write_text(json.dumps(meta,indent=2)+'\n')

def work(run):
    meta=json.loads((run/'pilot.json').read_text());consumed=meta.get('session_seconds_used',0);remaining=meta['max_session_seconds']-consumed
    if remaining<=0:raise RuntimeError('Original development allowance exhausted')
    meta.update(harness='codex',effort='medium',status='running',pid=os.getpid(),segment_started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save(run,meta)
    branch,attempt,prompt=pilot.prepare(run)
    prompt+='\nThis attempt runs in native Codex with MEDIUM reasoning effort. The former Claude Code harness was stopped by user request. Preserve any own existing drafts, but use a fresh Codex conversation. Do not inspect other runs, other branches, or their transcripts. Use the acceptance MCP tools for diagnostics and official validation; direct shell is available for your own files only. Your remaining development allowance is '+str(round(remaining/60,1))+' minutes. Finish with your best verified program.py and proposal.md.\n'
    if meta.get('codex_recovery_context'):
        prompt+='\nInfrastructure recovery within the SAME attempt: read '+str(run/'private/codex-recovery-history.jsonl')+' for your complete prior Codex tool calls and results. Own source and proposal are preserved. Validation was blocked by runner infrastructure (usage-ledger access or nested sandbox startup); the task-server execution path has been repaired. Continue your own work without resetting time or repeating completed research.\n'
    meta.pop('worker_error',None);save(run,meta)
    profile=run/'private/codex-isolation.sb'
    # Outer OS policy also applies to shell commands and MCP descendants. Other
    # runs cannot be read, while own source and shared task validation remain usable.
    profile.write_text('(version 1)\n(allow default)\n(deny file-read* (subpath '+json.dumps(str(ROOT/'runs'))+'))\n(allow file-read* (subpath '+json.dumps(str(run))+'))\n(deny file-write* (subpath '+json.dumps(str(ROOT))+'))\n'+''.join('(allow file-write* (subpath '+json.dumps(str(p))+'))\n' for p in [run,ROOT/'outputs',ROOT/'work/runtime-locks',ROOT/'runs/dfthcsos-accounting']))
    with profile.open('a') as handle:handle.write('(allow file-read-metadata (subpath '+json.dumps(str(ROOT/'runs'))+'))\n')
    cfg=pilot.runner.environment(ROOT/'.credentials/kimi-proxy.env');env={k:v for k,v in os.environ.items() if not k.startswith(('ANTHROPIC_','CLAUDE_'))};env['CHEMISTRY_PROVIDER_KEY']=cfg['ANTHROPIC_AUTH_TOKEN'];env['PYTHONDONTWRITEBYTECODE']='1'
    args=['/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME=/nonexistent','PYTHONDONTWRITEBYTECODE=1','TMPDIR='+str(ROOT/'outputs/dqi-validation/tmp'),str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/literature_acceptance/dfthcsos_server.py'),str(attempt)]
    from mcp_socket_bridge import MCPRelay
    mcp_log=(run/'private/codex-mcp-stderr.log').open('a')
    relay=MCPRelay(args,mcp_log)
    bridge_secret=relay.secret;env['CHEMISTRY_MCP_BRIDGE_SECRET']=bridge_secret
    args=[str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/literature_acceptance/mcp_socket_bridge.py'),str(relay.port)]
    command=['/usr/bin/sandbox-exec','-f',str(profile),str(Path.home()/'.local/bin/codex'),'exec','--ignore-user-config','--ignore-rules','--ephemeral','--skip-git-repo-check','--json','--dangerously-bypass-approvals-and-sandbox','-C',str(branch),'-m','gpt-6.1-sol']
    settings={'model_provider':'chemistry_gateway','model_reasoning_effort':'medium','approval_policy':'never','model_providers.chemistry_gateway.name':'Chemistry GPT provider','model_providers.chemistry_gateway.base_url':'https://yyt.s-flag.com/v1','model_providers.chemistry_gateway.env_key':'CHEMISTRY_PROVIDER_KEY','model_providers.chemistry_gateway.wire_api':'responses','mcp_servers.acceptance.command':'/usr/bin/env','mcp_servers.acceptance.args':args,'mcp_servers.acceptance.env.CHEMISTRY_MCP_BRIDGE_SECRET':bridge_secret,'mcp_servers.acceptance.tool_timeout_sec':28800,'mcp_servers.acceptance.required':True}
    for key,value in settings.items():command+=['-c',key+'='+json.dumps(value)]
    command+=['-o',str(run/'private/codex-last-message.txt'),'-']
    (run/'private/codex-launch.json').write_text(json.dumps({'harness':'codex','model':'gpt-6.1-sol','reasoning_effort':'medium','provider_base_url':'https://yyt.s-flag.com/v1','remaining_seconds':remaining,'branch_isolation':'outer OS sandbox denies reading other runs','settings':{k:v for k,v in settings.items() if not k.endswith('CHEMISTRY_MCP_BRIDGE_SECRET')}},indent=2)+'\n')
    event_log=run/'private/codex-events.jsonl';stderr_log=run/'private/codex-stderr.log'
    event_offset=event_log.stat().st_size if event_log.exists() else 0
    stderr_offset=stderr_log.stat().st_size if stderr_log.exists() else 0
    started=time.monotonic()
    with (run/'private/codex-events.jsonl').open('a') as events,(run/'private/codex-stderr.log').open('a') as err:
        proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=events,stderr=err,env=env,start_new_session=True)
        meta['codex_pid']=proc.pid;save(run,meta)
        try:proc.communicate(prompt.encode(),timeout=remaining)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(10)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
            meta['development_stop_reason']='Original200-minute allowance exhausted'
    relay.close()
    mcp_log.close()
    meta.update(session_seconds_used=consumed+time.monotonic()-started,codex_exit_code=proc.returncode)
    if proc.returncode and time.monotonic()-started<60:
        meta.update(status='error',worker_error='Codex failed during startup; see private/codex-stderr.log');save(run,meta);return
    with event_log.open('rb') as log:log.seek(event_offset);segment=log.read().decode(errors='replace')
    with stderr_log.open('rb') as log:log.seek(stderr_offset);segment_err=log.read().decode(errors='replace')
    tool_results=[json.loads(line).get('item',{}) for line in segment.splitlines() if line.startswith('{')]
    tool_errors=[json.dumps(item) for item in tool_results if item.get('type')=='mcp_tool_call' and item.get('status') in ('completed','failed')]
    infra_tool_error=any('sandbox_apply: Operation not permitted' in text or ('Operation not permitted' in text and 'tool-calls.jsonl' in text) for text in tool_errors)
    if 'MCP server startup failed' in segment_err or infra_tool_error:
        meta.update(status='error',worker_error='Infrastructure blocked candidate tools; preserve this attempt for recovery, do not score/advance');save(run,meta);return
    meta['status']='grading';save(run,meta)
    sys.path.insert(0,str(ROOT/'tasks/dfthcsos'));import evaluator
    results=[]
    for label,salt in [('final-development',evaluator.PROTOCOL['development_salt']),('final-confirmation',evaluator.PROTOCOL['final_salt'])]:
        output=run/'private'/label
        try:
            result=evaluator.evaluate_program(attempt/'artifact/program.py',output,salt=salt)
            results.append({'label':label,'status':result['status'],'reward':result['combined_score'],'cost':result['official']['score'],'receipt':str(output/'result.json'),'submission_sha256':result['official']['submission_sha256']})
        except Exception as exc:results.append({'label':label,'status':'ERROR','error':str(exc)})
    passed=all(r.get('status')=='PASS' for r in results);meta.update(status='completed' if passed else 'validation_failed',results=results,improved=passed and all(r['reward']>1 for r in results),finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save(run,meta)

if __name__=='__main__':
    run=Path(sys.argv[1]).resolve()
    if not run.is_relative_to(ROOT/'runs/dfthcsos'):raise ValueError('Chemistry pilot required')
    work(run)
