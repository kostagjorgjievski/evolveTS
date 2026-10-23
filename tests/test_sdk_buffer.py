import sys,asyncio,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import backend_settings
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport,SDKJSONDecodeError
import pytest

class Process:
    async def wait(self):return 0
async def stream(message):yield message
async def decode(limit):
    transport=SubprocessCLITransport.__new__(SubprocessCLITransport)
    transport._process=Process();transport._exit_error=None;transport._max_buffer_size=limit
    transport._stdout_stream=stream(json.dumps({'payload':'x'*(2*1024*1024)}))
    return [message async for message in transport._read_messages_impl()]

def test_large_history_message_fits_configured_buffer():
    with pytest.raises(SDKJSONDecodeError):asyncio.run(decode(1024*1024))
    options=backend_settings.configured_options(cwd=str(Path.cwd()))
    assert options.max_buffer_size==16*1024*1024
    messages=asyncio.run(decode(options.max_buffer_size))
    assert len(messages[0]['payload'])==2*1024*1024

def test_explore_permissions_do_not_add_shell(tmp_path):
    branch=tmp_path/'explore_b0';node=branch/'attempt_00'
    rules=backend_settings.explore_restrictions(branch,node)
    assert 'Bash' not in rules['tools']
    assert rules['permission_mode']=='dontAsk'
    assert all(str(node) in rule for rule in rules['allowed_tools'] if rule.startswith(('Edit(','Write(')))
