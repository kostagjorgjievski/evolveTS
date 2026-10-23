"""Use the existing GLM-compatible Claude CLI through the SDK's cli_path option.

Exploration sessions get the paper's Gemini contract (upstream's default
without --explore-shell): file tools only, no shell, reads confined to the
agent's own branch folder and the shared history, writes to its attempt folder.
"""
import os
from pathlib import Path
import threading
import claude_agent_sdk as sdk

original_options = sdk.ClaudeAgentOptions
# run_bounded records each call's stage here; the SDK builds options in the same thread.
current = threading.local()
EXPLORE_TOOLS = ["Read", "Grep", "Glob", "Edit", "Write"]


def explore_restrictions(cwd, node_dir=None):
    branch = Path(cwd).resolve()
    # Branch history entries link into <workspace>/history (DRSI_HISTORY_SEED_MODE=symlink).
    history = branch.parent / "history"
    # Writes go only to the attempt's own folder, the two files the explore prompt
    # names; a save one level up (branch/artifact/) would otherwise score as a failure.
    attempt = Path(node_dir).resolve() if node_dir else branch
    rules = [f"{tool}(/{root}/**)" for root in (branch, history) for tool in ("Read", "Grep", "Glob")]
    rules += [f"{tool}(/{attempt}/**)" for tool in ("Edit", "Write")]
    # dontAsk denies every tool use that these scoped rules do not pre-approve.
    return {"tools": EXPLORE_TOOLS, "allowed_tools": rules, "permission_mode": "dontAsk"}


def configured_options(*args, **kwargs):
    # Full-history tool results can exceed the SDK's 1 MiB JSON-message default.
    # This is a transport buffer, not a model context/output allowance.
    kwargs.setdefault("max_buffer_size", 16 * 1024 * 1024)
    if os.environ.get("DRSI_CLAUDE_CLI"):
        kwargs.setdefault("cli_path", os.environ["DRSI_CLAUDE_CLI"])
    if getattr(current, "auth_token", None):
        # Key-pool lease for this session (run_bounded); overrides the inherited key.
        kwargs["env"] = {**(kwargs.get("env") or {}), "ANTHROPIC_AUTH_TOKEN": current.auth_token}
    if getattr(current, "stage", None) == "explore" and os.environ.get("DRSI_EXPLORE_SHELL") != "1":
        kwargs.update(explore_restrictions(kwargs["cwd"], getattr(current, "node_dir", None)))
    if os.environ.get("DRSI_CLAUDE_PERMISSION_MODE"):
        kwargs.setdefault("permission_mode", os.environ["DRSI_CLAUDE_PERMISSION_MODE"])
    if os.environ.get("GLM_MAX_TURNS"):
        kwargs.setdefault("max_turns", int(os.environ["GLM_MAX_TURNS"]))
    if os.environ.get("GLM_REASONING_EFFORT"):
        kwargs.setdefault("effort", os.environ["GLM_REASONING_EFFORT"])
    return original_options(*args, **kwargs)


sdk.ClaudeAgentOptions = configured_options
