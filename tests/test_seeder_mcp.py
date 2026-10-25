"""Real MCP stdio integration: the dispatcher server an actual model session
would spawn, exercised with a genuine MCP client — initialize, list tools,
execute a sandboxed diagnostic, parse the structured result. No model call.
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

mcp_client = pytest.importorskip('mcp.client.session')

from scripts.autoresearch_seeder.backends import mcp_server_command, \
    resolve_interpreter, server_env
from scripts.autoresearch_seeder.testing import GOOD_DIAGNOSTIC, build_job


def test_interpreter_resolves_and_imports_mcp():
    interpreter = resolve_interpreter(REPO)
    assert interpreter.is_file()


def test_mcp_command_uses_validated_interpreter(tmp_path):
    job = build_job(tmp_path, [])
    command = mcp_server_command(job.job_dir, REPO)
    assert command[1].endswith('mcp_server.py')
    assert command[2] == str(job.job_dir)
    assert Path(command[0]).is_file()


def test_real_mcp_stdio_session_initialize_list_and_diagnostic(tmp_path):
    """The exact server config a live backend spawns, spoken to as a client."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    job = build_job(tmp_path, [])
    (job.dispatcher.artifact / 'diagnostic.py').write_text(GOOD_DIAGNOSTIC)
    command = mcp_server_command(job.job_dir, REPO)

    async def session():
        server = StdioServerParameters(command=command[0], args=command[1:],
                                       env=server_env(REPO))
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as client:
                init = await client.initialize()
                tools = await client.list_tools()
                # A real tool round-trip: sandboxed diagnostic execution.
                outcome = await client.call_tool('run_diagnostic', {})
                return init, tools, outcome

    init, tools, outcome = asyncio.run(session())
    assert init.server_info.name == 'autoresearch-seeder'
    names = {tool.name for tool in tools.tools}
    assert {'web_search', 'fetch_source', 'propose_hypothesis',
            'run_diagnostic', 'run_development_validation', 'record_decision',
            'finish'} <= names
    payload = json.loads(outcome.content[0].text)
    assert payload['status'] == 'ok'
    assert payload['result']['status'] == 'pass'
    # The receipt landed in the shared durable store, not just the wire reply.
    experiments = job.store.list_experiments('diagnostic')
    assert len(experiments) == 1 and experiments[0]['status'] == 'pass'
    # Calling the identical tool again recovers, never re-executes.
    async def again():
        server = StdioServerParameters(command=command[0], args=command[1:],
                                       env=server_env(REPO))
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                return await client.call_tool('run_diagnostic', {})
    repeat = asyncio.run(again())
    payload = json.loads(repeat.content[0].text)
    assert payload['result']['recovered'] is True


def test_mcp_server_rejects_unknown_job(tmp_path):
    """A malformed job directory fails clearly instead of hanging a session."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    command = mcp_server_command(tmp_path, REPO)

    async def session():
        server = StdioServerParameters(command=command[0], args=command[1:],
                                       env=server_env(REPO))
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                return await client.list_tools()

    with pytest.raises(Exception):
        asyncio.run(session())
