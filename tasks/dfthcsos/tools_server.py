"""Task-specific no-shell MCP broker, scoped to one DFTHC-SOS attempt."""
import argparse
import asyncio
import json
import os
import signal
import psutil
from pathlib import Path
import sys
import uuid
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp import types
ROOT=Path(__file__).resolve().parents[2]
ATTEMPT=None

async def list_tools(context,params):
    return types.ListToolsResult(tools=[types.Tool(name=name,description=description,inputSchema={'type':'object','properties':{},'additionalProperties':False}) for name,description in [
        ('validate_candidate','Verify this attempt artifact/program.py: generate complete DFTHC-SOS submission, run unchanged official64-shot/address verifier and Kaggle input preflight, return actual reward and logs. No arguments.'),
        ('diagnose_candidate','Run this attempt artifact/diagnostic.py for60sec/2GiB, with numpy/scipy/kickmix and official dfthcsos helpers. Offline, no credentials, no official score. Print diagnostic results; successful logs are returned. No arguments.')]])

async def call_tool(context,params):
    name=params.name;arguments=params.arguments
    if arguments or name not in ('validate_candidate','diagnose_candidate'):raise ValueError('Known no-argument task tool required')
    call_id=uuid.uuid4().hex
    ledger=ROOT/'runs/dfthcsos-accounting/tool-calls.jsonl';ledger.parent.mkdir(parents=True,exist_ok=True)
    command=[str(ROOT/'.dfthcsos-venv/bin/python'),str(Path(__file__).with_name('library_validate.py')),str(ATTEMPT)]
    if name=='diagnose_candidate':command.append('--diagnostic')
    process=await asyncio.create_subprocess_exec(*command,env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','PYTHONDONTWRITEBYTECODE':'1'},stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,start_new_session=True)
    out,err=await process.communicate()
    try:
        if process.returncode:raise RuntimeError(err.decode(errors='replace')[-4000:])
        result=json.loads(out)
    except Exception as exc:result={'status':'ERROR','error':str(exc),'combined_score':0} if name=='validate_candidate' else {'status':'ERROR','error':str(exc),'diagnostic_only':True}
    result.update(call_id=call_id,development_cost=True,automatic_final_evaluation_still_required=True)
    with ledger.open('a') as handle:handle.write(json.dumps({'call_id':call_id,'tool':name,'attempt':str(ATTEMPT),'status':result['status']})+'\n')
    return types.CallToolResult(content=[types.TextContent(type='text',text=json.dumps(result))],structuredContent=result)

async def main():
    server=Server('candidate-validation',get_tool_input_schema=lambda name:{'type':'object','properties':{},'additionalProperties':False},on_list_tools=list_tools,on_call_tool=call_tool)
    async with stdio_server() as (read,write):await server.run(read,write,server.create_initialization_options())

def stop_children():
    for process in psutil.Process().children(recursive=True):
        try:os.killpg(os.getpgid(process.pid),signal.SIGTERM)
        except (ProcessLookupError,psutil.Error):pass


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True);a=p.parse_args();ATTEMPT=a.attempt.resolve()
    if not ATTEMPT.is_relative_to(ROOT/'runs/dfthcsos') or ATTEMPT.parent.name.startswith('explore_b') is False or not ATTEMPT.name.startswith('attempt_'):
        p.error('Only a DFTHC-SOS run attempt is allowed')
    def stop(signum,frame):
        stop_children();raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,stop)
    try:asyncio.run(main())
    finally:stop_children()
