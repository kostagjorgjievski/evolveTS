"""Prepared chemistry tools; full validation deferred outside development clock."""
import asyncio
import hashlib
import json
import signal
import sys
from pathlib import Path

HOST=Path('/Users/kostagj/Documents/ChatGPT/EvolveTS-RSI')
sys.path[:0]=[str(HOST/'scripts'),str(HOST/'scripts/literature_acceptance')]
import dfthcsos_server as server
base=server.base
base.DESCRIPTIONS['validate_candidate']='Freeze your current source and request full official development plus exact-file independent confirmation after this model session ends. End this session without changing the bundle after requesting. No immediate score; final trusted grading is outside the20-minute model clock.'

async def call(context,params):
    if params.name!='validate_candidate':return await server.call(context,params)
    if params.arguments:return base.types.CallToolResult(isError=True,content=[base.types.TextContent(text='No arguments allowed')])
    artifact=server.task.ATTEMPT/'artifact'
    files={}
    for p in artifact.rglob('*'):
        if p.is_symlink():raise ValueError('Artifact links are forbidden')
        if p.is_file():files[str(p.relative_to(artifact))]=hashlib.sha256(p.read_bytes()).hexdigest()
    receipt={'status':'requested','files':files,'note':'End this model session now; full unchanged official grading follows outside your development timer. Do not edit the bundle after this request.'}
    (server.task.ATTEMPT.parent/'full-validation-request.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return base.types.CallToolResult(content=[base.types.TextContent(text=json.dumps(receipt))],structuredContent=receipt)

if __name__=='__main__':
    attempt=Path(sys.argv[1]).resolve()
    if not attempt.is_relative_to(HOST/'runs/dfthcsos') or attempt.name!='attempt_00':raise ValueError('Own short-pilot attempt required')
    base.configure(attempt);server.task.ATTEMPT=attempt;base.call=call
    def stop(sig,frame):base.stop_children();raise SystemExit(128+sig)
    signal.signal(signal.SIGTERM,stop)
    try:asyncio.run(base.main())
    finally:base.stop_children()
