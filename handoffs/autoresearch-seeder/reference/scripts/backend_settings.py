"""Use the existing GLM-compatible Claude CLI through the SDK's cli_path option.

Exploration sessions get the paper's Gemini contract (upstream's default
without --explore-shell): file tools only, no shell, reads confined to the
agent's own branch folder and the shared history, writes to its attempt folder.
"""
import os
import re
import json
from pathlib import Path
import threading
import claude_agent_sdk as sdk
import web_research
import candidate_validation_tools

original_options = sdk.ClaudeAgentOptions
original_query = sdk.query
# run_bounded records each call's stage here; the SDK builds options in the same thread.
current = threading.local()
EXPLORE_TOOLS = ["Read", "Grep", "Glob", "Edit", "Write"]
PROVIDER_FAILURE = re.compile(r'^\s*API Error:\s*[45]\d\d\b', re.I)


def observe_provider_message(message):
    """Keep terminal provider errors even if the SDK later raises a generic exit."""
    if not isinstance(message, sdk.AssistantMessage):
        return
    text = '\n'.join(block.text for block in message.content if isinstance(block, sdk.TextBlock))
    if PROVIDER_FAILURE.search(text) or getattr(message, 'error', None):
        detail = text or str(message.error)
        token = getattr(current, 'auth_token', None)
        if token:
            detail = detail.replace(token, '[REDACTED]')
        current.provider_error = detail[:2000]
        log_dir = getattr(current, 'log_dir', None)
        if log_dir:
            path = Path(log_dir)/'provider_errors.jsonl'
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a') as out:
                out.write(json.dumps({'error': current.provider_error}, ensure_ascii=False)+'\n')
    elif text.strip():
        current.provider_error = None  # The CLI recovered and produced a real answer.


async def observed_query(*args, **kwargs):
    async for message in original_query(*args, **kwargs):
        if isinstance(message,sdk.SystemMessage) and message.subtype=='init':
            session_id=message.data.get('session_id')
            log_dir=getattr(current,'log_dir',None)
            if session_id and log_dir:
                path=Path(log_dir)/'sdk-session.json';path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps({'session_id':session_id})+'\n')
        observe_provider_message(message)
        yield message


def explore_restrictions(cwd, node_dir=None):
    branch = Path(cwd).resolve()
    # Branch history entries link into <workspace>/history (DRSI_HISTORY_SEED_MODE=symlink).
    history = branch.parent / "history"
    # Writes go only to the attempt's own folder, the two files the explore prompt
    # names; a save one level up (branch/artifact/) would otherwise score as a failure.
    attempt = Path(node_dir).resolve() if node_dir else branch
    rules = [f"{tool}(/{root}/**)" for root in (branch, history) for tool in ("Read", "Grep", "Glob")]
    rules += [f"{tool}(/{attempt}/**)" for tool in ("Edit", "Write")]
    if web_research.enabled():
        rules += web_research.TOOL_RULES
    if candidate_validation_tools.enabled_for(attempt):
        rules.append(candidate_validation_tools.TOOL_RULE)
        rules.append("mcp__candidate-validation__diagnose_candidate")
    # dontAsk denies every tool use that these scoped rules do not pre-approve.
    return {"tools": EXPLORE_TOOLS, "allowed_tools": rules, "permission_mode": "dontAsk"}


def configured_options(*args, **kwargs):
    # Full-history tool results can exceed the SDK's 1 MiB JSON-message default.
    # This is a transport buffer, not a model context/output allowance.
    kwargs.setdefault("max_buffer_size", 16 * 1024 * 1024)
    stderr_lines = getattr(current, 'stderr_lines', None)
    if stderr_lines is not None:
        def capture_stderr(line):
            stderr_lines.append(line[-2000:])
            del stderr_lines[:-20]
        kwargs.setdefault('stderr', capture_stderr)
    if os.environ.get("DRSI_CLAUDE_CLI"):
        kwargs.setdefault("cli_path", os.environ["DRSI_CLAUDE_CLI"])
    if getattr(current, "auth_token", None):
        # Key-pool lease for this session (run_bounded); overrides the inherited key.
        kwargs["env"] = {**(kwargs.get("env") or {}), "ANTHROPIC_AUTH_TOKEN": current.auth_token}
    log_dir=getattr(current,'log_dir',None)
    if log_dir:
        session_file=Path(log_dir)/'sdk-session.json'
        if session_file.exists():
            kwargs.setdefault('resume',json.loads(session_file.read_text())['session_id'])
    if getattr(current, "stage", None) == "explore" and os.environ.get("DRSI_EXPLORE_SHELL") != "1":
        kwargs.update(explore_restrictions(kwargs["cwd"], getattr(current, "node_dir", None)))
        attempt=getattr(current,'node_dir',None)
        validation=candidate_validation_tools.enabled_for(attempt)
        if web_research.enabled() or validation:
            token = getattr(current, 'auth_token', None) or os.environ.get('ANTHROPIC_AUTH_TOKEN')
            kwargs['mcp_servers'] = web_research.server_config(token,attempt)
            if validation:
                kwargs['env']={**kwargs.get('env',{}),'MCP_TOOL_TIMEOUT':'28800000'}
            prompt = kwargs.get('system_prompt')
            if isinstance(prompt, dict):
                prompt = dict(prompt)
                prompt['append'] = prompt.get('append', '') + (
                    '\nWeb research is allowed using web-search-prime and web-reader. '
                    'Research public algorithms and library documentation as useful; cite '
                    'source URLs in your proposal and distinguish researched claims from '
                    'measured results. Keep following the branch file permissions and fixed '
                    'evaluation contract.\n')
                kwargs['system_prompt'] = prompt
        if validation and isinstance(kwargs.get('system_prompt'),dict):
            prompt=dict(kwargs['system_prompt'])
            prompt['append']=prompt.get('append','')+(
                '\nYou have validate_candidate, a task-specific tool taking NO arguments. '
                'Save artifact/program.py, then call it to check sandboxed syntax/imports, '
                'generate the full circuit, and receive unchanged official verification and '
                'score feedback. Fix errors or improve the implementation using that feedback. '
                'Calls share the campaign validation queue and count as additional development '
                'cost. Final automatic evaluation still runs. Record validation call IDs in '
                'your proposal. This does not enable shell access. '
                'For small calculations save artifact/diagnostic.py and call diagnose_candidate '
                'with no arguments (60 seconds, 2 GiB, no verifier or score). Both modes '
                'support from dqi import dqi_reference_circuit and return bounded printed logs.\n')
            if Path(attempt).is_relative_to(Path(__file__).resolve().parents[1]/'runs/dfthcsos'):
                prompt['append']=prompt.get('append','').replace('from dqi import dqi_reference_circuit','import dfthcsos')
                prompt['append']+='\nFor DFTHC-SOS, program.py takes an output DIRECTORY and writes submission.npz plus angle_k_*.kmb; validation uses64 shots per address, not DQI shots. diagnose_candidate runs artifact/diagnostic.py offline for60sec/2GiB and returns successful logs too. Official dfthcsos helpers and scipy are importable.\n'
            kwargs['system_prompt']=prompt
    if os.environ.get("DRSI_CLAUDE_PERMISSION_MODE"):
        kwargs.setdefault("permission_mode", os.environ["DRSI_CLAUDE_PERMISSION_MODE"])
    if os.environ.get("GLM_MAX_TURNS"):
        kwargs.setdefault("max_turns", int(os.environ["GLM_MAX_TURNS"]))
    if os.environ.get("GLM_REASONING_EFFORT"):
        kwargs.setdefault("effort", os.environ["GLM_REASONING_EFFORT"])
    return original_options(*args, **kwargs)


sdk.ClaudeAgentOptions = configured_options
sdk.query = observed_query
