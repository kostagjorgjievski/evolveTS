"""Invoke upstream CLI with per-invocation agent accounting and an access guard."""
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import sys
import time
import backend_settings  # SDK configuration and exploration tool limits, not engine modification.
if os.environ.get('RESUME') == '1':
    import resume_settings  # Retain scored attempts across infrastructure restarts.
if os.environ.get("DQI_INDEPENDENT_BRANCHES") == "1":
    import independent_branches  # E0 baseline scheduling only; no cross-branch reads.
from history_access import history_access_note
from key_pool import KeyPool, load_keys

from dream_rsi.agents.base import AgentResult
from dream_rsi.agents.base import SHUTDOWN
from dream_rsi.agents.claude import ClaudeAgent
from dream_rsi.cli.main import main

original_run = ClaudeAgent.run
# Provider refusals (credentials, model access, exhausted quota or balance) are
# not attempt outcomes. Rate limits and server errors are transient and excluded.
ACCESS_ERROR = re.compile(
    r"API Error: 40[123]\b|Failed to authenticate|team_model_access_denied|not allowed to access model"
    r"|invalid[ _-]?api[ _-]?key|insufficient[ _-]?(quota|balance)|quota[ _-]?exceeded|余额不足",
    re.IGNORECASE)
# A session that still fails on the provider's rate limit after the CLI's own
# retries is rerun on the same attempt after a growing pause, so throttling is
# never recorded as an attempt outcome.
RATE_LIMIT = re.compile(r"API Error: 429|\(429\)|rate[ _-]?limit|\[1302\]", re.IGNORECASE)
RATE_LIMIT_PAUSES = [120, 240, 360, 480, 600]
POOL_KEYS = load_keys()
# DRSI_KEY_POOL_STATE lets runs with separate accounting share one key's session cap.
POOL_STATE = Path(os.environ.get("DRSI_KEY_POOL_STATE")
                  or Path(os.environ["DRSI_AGENT_BUDGET_FILE"]).parent / "key-pool.json")
POOL = (KeyPool(POOL_KEYS, POOL_STATE, int(os.environ.get("DRSI_KEY_MAX_SESSIONS", "3")))
        if POOL_KEYS else None)


def stop_run(marker, reason):
    """Stop this run before upstream records the refused call as a failed attempt.

    Killing the launcher's process group leaves every unfinished attempt
    unmarked, so RESUME=1 retries exactly those attempts once access works.
    The marker also stops any other run sharing this accounting directory.
    """
    if not marker.exists():
        marker.write_text(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                      "pid": os.getpid(), "reason": reason[:2000]}, indent=2))
    print(f"[access-guard] provider refused the agent: {reason[:300]}\n"
          f"[access-guard] stopping this run; see {marker}. Restore access, then rerun with RESUME=1.",
          file=sys.stderr, flush=True)
    os.killpg(os.getpgid(0), signal.SIGKILL)


def counted_run(self, kwargs):
    budget = Path(os.environ["DRSI_AGENT_BUDGET_FILE"])
    budget.parent.mkdir(parents=True, exist_ok=True)
    marker = budget.parent / "ACCESS_ERROR.json"
    if marker.exists():
        stop_run(marker, "an earlier call was refused: " + marker.read_text())
    with budget.open("a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        state = json.loads(f.read() or '{"calls": 0}')
        # GLM usage is uncapped by explicit user instruction; record every invocation.
        state["calls"] += 1
        call = state["calls"]
        f.seek(0)
        f.truncate()
        json.dump(state, f)
    key_index = POOL.acquire() if POOL else None
    if POOL and key_index is None:
        stop_run(marker, "every key in the pool was refused")
    started = time.time()
    backend_settings.current.stage = kwargs.get("stage")
    backend_settings.current.node_dir = kwargs.get("node_dir")
    backend_settings.current.auth_token = POOL_KEYS[key_index] if POOL else None
    backend_settings.current.provider_error = None
    backend_settings.current.stderr_lines = []
    backend_settings.current.log_dir = kwargs['log_dir']
    try:
        result = original_run(self, **kwargs)
        detail = backend_settings.current.provider_error
        if not detail and result.status != 'ok':
            stderr = '\n'.join(backend_settings.current.stderr_lines)
            if RATE_LIMIT.search(stderr) or ACCESS_ERROR.search(stderr):
                detail = stderr[-2000:]
        if detail:
            if POOL_KEYS:
                for secret in POOL_KEYS:
                    detail = detail.replace(secret, '[REDACTED]')
            result = AgentResult(status='failed', message=detail)
    finally:
        backend_settings.current.stage = None
        backend_settings.current.node_dir = None
        backend_settings.current.auth_token = None
        backend_settings.current.provider_error = None
        backend_settings.current.stderr_lines = None
        backend_settings.current.log_dir = None
        if POOL:
            POOL.release(key_index)
    refused = result.status != "ok" and ACCESS_ERROR.search(result.message or "")
    logs = Path(kwargs["log_dir"])
    metrics = logs / "claude_messages.json"
    reported = json.loads(metrics.read_text()) if metrics.exists() else {}
    record = {"call": call, "backend": os.environ.get("DRSI_BACKEND", "glm_cli"), "model": os.environ.get("ANTHROPIC_MODEL"),
              "stage": kwargs.get("stage"), "status": result.status,
              "elapsed_seconds": time.time() - started, "log_dir": str(logs),
              "sdk_reported_cost_usd": reported.get("total_cost_usd"),
              "num_turns": reported.get("num_turns"), "key_index": key_index,
              "message": None if result.status == "ok" else (result.message or "")[:500],
              "note": "SDK cost estimates are not verified provider billing."}
    (budget.parent / f"agent-call-{call:02d}.json").write_text(json.dumps(record, indent=2))
    if refused and POOL:
        remaining = POOL.refuse(key_index, result.message)
        print(f"[access-guard] key {key_index} refused: {result.message[:200]}; {remaining} key(s) left",
              file=sys.stderr, flush=True)
        if remaining == 0:
            stop_run(marker, "every key in the pool was refused; last: " + result.message)
    elif refused:
        stop_run(marker, result.message)
    return result, bool(refused)


def bounded_run(self, **kwargs):
    if kwargs.get("stage") == "explore":
        kwargs["prompt"] += history_access_note(kwargs["workspace"], kwargs["node_dir"])
        node=Path(kwargs['node_dir'])
        if os.environ.get('RESUME')=='1' and ((node/'artifact/program.py').exists() or (node/'proposal.md').exists()):
            kwargs['prompt'] += (
                '\nThis attempt was interrupted for an infrastructure/tool update. '
                'Its existing draft files have been preserved. Read them and continue '
                'your work using the tools currently available; do not discard a draft '
                'merely because this is a resumed session.\n')
    if kwargs.get("stage") == "learning" and "OptimalPolicy" in kwargs.get("prompt", ""):
        project = Path(__file__).resolve().parents[1]
        kwargs["prompt"] += (
            "\n\nRuntime compatibility: the learning workspace contains a partial framework copy. "
            f"The complete read-only upstream framework is at {project / 'upstream/dream-rsi'}, "
            f"and the active Python executable is {sys.executable}. "
            "For an actual import check, run outside the partial package directory with PYTHONPATH "
            "pointing to the full upstream checkout and call dream_rsi.policy.load.load_policy_class "
            "on the absolute path of your method.py. Do not mock missing framework dependencies. "
            "The pinned dynamic policy loader cannot import dataclasses with postponed annotations; "
            "use ordinary classes with explicit __init__ instead. This is a runtime compatibility "
            "constraint; preserve the requested policy API and prefix-only behavior.\n"
        )
    retry = 0
    while True:
        result, refused = counted_run(self, kwargs)
        if refused:
            continue  # rerun the same attempt on another pool key
        if result.status == "ok" or not RATE_LIMIT.search(result.message or ""):
            return result
        pause = RATE_LIMIT_PAUSES[min(retry, len(RATE_LIMIT_PAUSES)-1)]
        retry += 1
        print(f"[rate-limit] {kwargs.get('stage')} session hit the provider rate limit; "
              f"rerunning the same attempt in {pause} s", file=sys.stderr, flush=True)
        if SHUTDOWN.wait(pause):
            return AgentResult(status='failed', message='campaign interrupted during provider cooldown')


ClaudeAgent.run = bounded_run
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
