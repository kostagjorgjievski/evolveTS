"""Exercise real diagnostic execution through the sandboxed Codex MCP relay."""
import asyncio,json,os,sys,datetime
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_socket_bridge import MCPRelay
ROOT=Path(__file__).resolve().parents[2]
async def main(run):
    attempt=run/'worker/explore_b0/attempt_98';(attempt/'artifact').mkdir(parents=True,exist_ok=True)
    (attempt/'artifact/diagnostic.py').write_text("import numpy as np,dfthcsos\nassert np.arange(6).reshape(2,3).shape==(2,3)\nprint('CODEX_CHEMISTRY_DIAGNOSTIC_READY')\n")
    profile=run/'private/preflight-worker.sb';profile.write_text('(version 1)\n(allow default)\n(deny file-read* (subpath '+json.dumps(str(ROOT/'runs'))+'))\n(allow file-read* (subpath '+json.dumps(str(run))+'))\n(allow file-read-metadata (subpath '+json.dumps(str(ROOT/'runs'))+'))\n')
    report=run/'private/codex-preflight.json';report.write_text(json.dumps({'status':'testing_real_diagnostic','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}))
    with (run/'private/preflight-server.log').open('a') as log:
        cmd=['/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME=/nonexistent','PYTHONDONTWRITEBYTECODE=1',str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/literature_acceptance/dfthcsos_server.py'),str(attempt)]
        relay=MCPRelay(cmd,log)
        try:
            params=StdioServerParameters(command='/usr/bin/sandbox-exec',args=['-f',str(profile),str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/literature_acceptance/mcp_socket_bridge.py'),str(relay.port)],env={'PATH':'/usr/bin:/bin','CHEMISTRY_MCP_BRIDGE_SECRET':relay.secret})
            async with stdio_client(params) as (rd,wr):
                async with ClientSession(rd,wr) as session:
                    await session.initialize();tools=await session.list_tools();result=await session.call_tool('diagnose_candidate',{})
                    data=getattr(result,'structured_content',None) or getattr(result,'structuredContent',None)
                    if not data:
                        data=json.loads(next(c.text for c in result.content if hasattr(c,'text')))
                    assert data['status']=='PASS',data
                    assert 'CODEX_CHEMISTRY_DIAGNOSTIC_READY' in json.dumps(data),data
                    report.write_text(json.dumps({'status':'PASS','tools':[t.name for t in tools.tools],'actual_diagnostic':data,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2)+'\n');print('REAL_DIAGNOSTIC_PASS',flush=True)
        except BaseException as exc:
            report.write_text(json.dumps({'status':'FAIL','error':str(exc)},indent=2)+'\n');raise
        finally:relay.close()
if __name__=='__main__':asyncio.run(main(Path(sys.argv[1]).resolve()))
