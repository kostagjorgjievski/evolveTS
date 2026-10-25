"""Read-only BigModel research tools for exploration, using its leased API key."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import candidate_validation_tools

ROOT = Path(__file__).resolve().parents[1]
TOOL_RULES = ['mcp__web-search-prime__web_search_prime', 'mcp__web-reader__webReader']


def enabled():
    path = ROOT/'configs/exploration_web.json'
    return path.exists() and json.loads(path.read_text()).get('enabled') is True


def server_config(token, attempt=None):
    if enabled() and not token:
        raise ValueError('Web research requires the coding session API key')
    token=token or ''
    servers = {
        'web-search-prime': {'type':'http', 'url':'https://open.bigmodel.cn/api/mcp/web_search_prime/mcp',
                             'headers':{'Authorization':'Bearer '+token}},
        'web-reader': {'type':'http', 'url':'https://open.bigmodel.cn/api/mcp/web_reader/mcp',
                       'headers':{'Authorization':'Bearer '+token}},
    }
    if not enabled():servers={}
    if candidate_validation_tools.enabled_for(attempt):
        servers['candidate-validation']=candidate_validation_tools.server_config(attempt)
    directory = ROOT/'.credentials/web-mcp'
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    identity=(token or '')+'\0'+str(attempt or '')
    path = directory/(hashlib.sha256(identity.encode()).hexdigest()[:20]+'.json')
    # Pass a protected file path to the CLI, keeping API keys out of process arguments.
    fd, temporary = tempfile.mkstemp(dir=directory, prefix='.config-')
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump({'mcpServers':servers}, out)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path
