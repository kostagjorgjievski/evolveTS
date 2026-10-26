"""Stdio MCP shim exposing the ToolDispatcher to a live model session.

Runs as a child of the model CLI with the job directory as argv[1]; opens the
same durable research store as the controller (SQLite WAL). The provider
credential never passes through this process and is never logged.
"""
import json
import os
import signal
import sys
from pathlib import Path


def main():
    try:
        from mcp.server.lowlevel import Server
        from mcp.server.stdio import stdio_server
        from mcp import types
    except ImportError as exc:  # pragma: no cover - live-only dependency
        raise SystemExit(f'mcp package required for live sessions: {exc}')

    job_dir = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.autoresearch_seeder import config as config_module
    from scripts.autoresearch_seeder.adapter import TaskAdapter
    from scripts.autoresearch_seeder.store import ResearchStore
    from scripts.autoresearch_seeder.tools import (TOOL_DESCRIPTIONS, TOOL_SCHEMAS,
                                                   ToolDispatcher)

    job = json.loads((job_dir / 'job.json').read_text())
    config = config_module.load(job['config_path'])
    adapter = TaskAdapter(job['task'], job.get('task_root') or
                          Path(job['config_path']).resolve().parents[1])
    store = ResearchStore(job_dir / 'private' / 'research.sqlite')
    dispatcher = ToolDispatcher(store, adapter, config, job_dir)

    requested=json.loads(os.environ['SEEDER_ALLOWED_TOOLS']) if 'SEEDER_ALLOWED_TOOLS' in os.environ else list(TOOL_SCHEMAS)
    if not isinstance(requested,list) or any(name not in TOOL_SCHEMAS for name in requested):raise ValueError('Invalid allowed tools')
    allowed=set(requested)

    async def list_tools(context, params):
        return types.ListToolsResult(tools=[
            types.Tool(name=name, description=TOOL_DESCRIPTIONS[name],
                       inputSchema=TOOL_SCHEMAS[name])
            for name in TOOL_SCHEMAS if name in allowed])

    async def call_tool(context, params):
        try:
            if params.name not in allowed:raise ValueError('Tool not allowed for this session')
            outcome = dispatcher.execute(params.name, params.arguments or {})
            return types.CallToolResult(
                content=[types.TextContent(text=json.dumps(outcome))],
                structuredContent=outcome,
                isError=outcome.get('status') == 'error')
        except Exception as exc:
            return types.CallToolResult(isError=True,
                                         content=[types.TextContent(text=str(exc))])

    server = Server('autoresearch-seeder',
                    get_tool_input_schema=lambda name: TOOL_SCHEMAS[name],
                    on_list_tools=list_tools, on_call_tool=call_tool)
    import asyncio

    def stop(sig, frame):
        raise SystemExit(128 + sig)

    signal.signal(signal.SIGTERM, stop)
    async def serve():
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    asyncio.run(serve())


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: mcp_server.py <job-dir>')
    main()
