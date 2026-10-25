"""Credential-free MCP endpoint with exactly one argument-free validation tool."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
import sys

import psutil
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp import types

ROOT=Path(__file__).resolve().parents[1]
SCHEMA={'type':'object','properties':{},'additionalProperties':False}


def stop_children():
    for process in psutil.Process().children(recursive=True):
        try:os.killpg(os.getpgid(process.pid),signal.SIGTERM)
        except (ProcessLookupError,psutil.Error):pass


async def main(attempt):
    async def list_tools(context,params):
        return types.ListToolsResult(tools=[types.Tool(name='validate_candidate',inputSchema=SCHEMA,
            description='Validate your saved artifact/program.py. Takes no arguments. Returns sandboxed syntax/import errors, full official DQI verification, elapsed time and score. Calls count toward development cost; full validations share the campaign CPU lock.'),types.Tool(name='diagnose_candidate',inputSchema=SCHEMA,description='Run your saved artifact/diagnostic.py in a credential-free, network-free sandbox, with official dqi helpers importable. No arguments. Limit 60 seconds and 2 GiB. Returns printed diagnostics; no circuit verification or score. Logged development cost.')])
    async def call_tool(context,params):
        if params.name not in ('validate_candidate','diagnose_candidate') or params.arguments not in ({},None):
            return types.CallToolResult(isError=True,content=[types.TextContent(
                text='validate_candidate takes no arguments and cannot accept a path or command')])
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LC_ALL':'en_US.UTF-8','LANG':'en_US.UTF-8',
             'PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(ROOT/'outputs/dqi-validation/tmp')}
        process=await asyncio.create_subprocess_exec(str(ROOT/'.venv/bin/python'),
            str(ROOT/'scripts/candidate_validation_worker.py'),'--attempt',str(attempt),*(['--diagnostic'] if params.name=='diagnose_candidate' else []),
            cwd=ROOT,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,
            start_new_session=True)
        try:
            stdout,stderr=await process.communicate()
        except BaseException:
            stop_children()
            raise
        if process.returncode:
            result={'status':'FAIL','error':stderr.decode(errors='replace')[-3000:]}
        else:result=json.loads(stdout)
        return types.CallToolResult(content=[types.TextContent(text=json.dumps(result))],
                                    structuredContent=result)
    server=Server('candidate-validation',get_tool_input_schema=lambda name:SCHEMA,
                  on_list_tools=list_tools,on_call_tool=call_tool)
    async with stdio_server() as (read,write):
        await server.run(read,write,server.create_initialization_options())


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=Path,required=True)
    args=parser.parse_args()
    def terminate(signum,frame):
        stop_children();raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,terminate)
    try:asyncio.run(main(args.attempt))
    finally:stop_children()
