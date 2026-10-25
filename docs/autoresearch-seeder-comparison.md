# AutoResearch Seeder — Controlled Backend Comparison (PREPARED, NOT STARTED)

Status: **prepared, disabled, not launched.** No paid comparison session has
run. Both arm configs ship with `enabled: false`; nothing in this document
has been executed against a provider.

Purpose: a fair head-to-head of the two researcher backends driving the SAME
model, endpoint and requested effort, on the same task, with the same trusted
tools — Claude Code (arm A) vs Hermes Agent (arm B).

## What differs between the arms — and nothing else

Both arms share, by construction of the seeder:

- Same task: `dfthcsos` (the existing small chemistry-lookup task — pinned
  official inputs, offline library namespace, unchanged official verifier;
  see `tasks/dfthcsos/README.md`. No new dependency was invented for the
  comparison).
- Same frozen starting artifact (`init` copies the official seed program).
- Same neutral prepared context (`scripts/autoresearch_seeder/context.py` is
  backend-independent; the worker prompt template is identical).
- Same trusted MCP tools (the dispatcher server `mcp_server.py` under a
  validated interpreter; scoring, validation and receipts never run inside
  either agent runtime).
- Same budgets: 1200 s (20 minutes) of model-session time for development,
  identical tool/search/retry caps, 25 USD SDK-reported cost ceiling.
- Same GLM-5.3 endpoint (`.credentials/glm.env`, machine-local) and requested
  effort `medium`.

The ONLY difference is `provider.backend`: `claude_code` (arm A) vs `hermes`
(arm B, pinned release v0.22.5, commit bf0203a, docs verified 2026-10-25).
No strong-model advisor exists in either arm — neither backend receives
suggestions, reviews or hints from any other model.

## Arm configurations

- Arm A: `configs/comparison/arm-a-claude-glm53.json`
- Arm B: `configs/comparison/arm-b-hermes-glm53.json`

Both are `enabled: false`. Arm B additionally requires the Hermes CLI on the
evaluation machine. Both reference `.credentials/glm.env` (never committed).

## Protocol (per arm, run back-to-back under identical conditions)

1. **Preflight** (no model calls): `preflight --live --offline-probe` must
   pass, including the backend-specific checks (hermes binary + version probe
   for arm B). Any preflight failure aborts that arm before money is spent.
2. **Init**: one job per arm, same task, own job directory.
3. **Development**: one bounded run (the job's session loop, 20 minutes of
   model-session time). Interruption handling is part of what is measured:
   if a job crashes, `resume` recovers it; crash-time budget accounting is
   already durable (orphan-session recovery charges an upper bound).
4. **Final validation outside the development allowance**: official
   development and confirmation validation run through the trusted task
   adapter in the controller — never inside the model session — and their
   queue/execution time is accounted separately in the budget ledger
   (`queue`/`execution` categories vs `model`).
5. **Export**: `export` evaluates the gates; both receipts must pass under
   both salts. Nothing is installed into any campaign.

## Metrics (all from durable job records — no model self-reports)

| Metric | Source of truth |
| --- | --- |
| Time to first useful diagnostic | first `diagnostic` experiment with `status: pass` timestamp minus first `session_started` (research store events) |
| Time to first verified improvement | first `development_validation` PASS whose official score exceeds the baseline ratio 1.0 |
| Final verified reward | confirmation receipt `combined_score` (official evaluator, final salt, frozen submission bytes) |
| Repeated / wasted work | experiments grouped by artifact bundle hash: repeated = same hash re-measured; wasted = same hash, same outcome, no intervening decision |
| Knowledge preservation | hypotheses/decisions/sources present in the store and carried into the next session's prepared context (fresh-session recovery test below) |
| Provider/tool failures | `provider_error` events (with class) and tool-call error records |
| Tokens / cost | backend usage reports (SDK result message for arm A; `--usage-file` JSON for arm B), plus budget-ledger seconds |

Cost comparison caveat (applies to both arms): cost figures are what each
runtime's SDK reports, post-hoc. They are not reconciled against provider
billing, and the two runtimes may account tokens differently (e.g. cache
hits, reasoning tokens). Treat token/cost comparisons as indicative; wall
clock and official scores are the hard endpoints.

## Fresh-session knowledge-preservation check (offline, per arm)

After the development run (or a simulated crash mid-run), start a fresh
`resume` and inspect the first prepared context written under
`private/prepared-context.md`: it must contain the neutral task/API prep, the
job's own current source, actual development/confirmation results so far,
hypotheses tested including failures with receipt IDs, compatibility findings
with provenance, remaining budgets, and a concrete next action — with
verified measurements distinguishable from model interpretations (receipt
IDs mark the former).

## Machine prerequisites (Mac Mini; the MacBook Air dev machine lacks these)

Official chemistry data and the task runtime are NOT on the MacBook Air.
On the Mac Mini they already exist (verified by the passing real-chemistry
suite). Preflight commands for Codex to run there, in repo order:

```bash
cd /path/to/evolveTS
git switch implementation/autoresearch-seeder && git pull --ff-only

# 1. Task runtime + official data (already present on the Mac Mini; verifies):
.dfthcsos-venv/bin/python -m pytest -q tasks/dfthcsos/test_task.py

# 2. Python deps for the seeder MCP server (already present on the Mac Mini):
python3 -c "import mcp, claude_agent_sdk" && echo deps-ok

# 3. Hermes CLI for arm B (skip if `command -v hermes` already finds it):
command -v hermes || pipx install hermes-agent
hermes --version   # record the exact version; backend pins v0.22.5

# 4. GLM credentials (machine-local, never committed):
test -s .credentials/glm.env && echo glm-credentials-present
```

## Launch sequence (DO NOT RUN without explicit operator approval)

When the operator approves starting the paid comparison:

```bash
# Arm A — Claude Code + GLM-5.3 (medium):
python3 -m scripts.autoresearch_seeder init --task dfthcsos \
    --config configs/comparison/arm-a-claude-glm53.json --job-id armA-glm53
python3 -m scripts.autoresearch_seeder preflight --job runs/autoresearch-seeder/dfthcsos/armA-glm53 --live --offline-probe
# then set "enabled": true in the config (the ONLY manual step) and:
python3 -m scripts.autoresearch_seeder run --job runs/autoresearch-seeder/dfthcsos/armA-glm53

# Arm B — Hermes + same GLM-5.3 endpoint/effort:
python3 -m scripts.autoresearch_seeder init --task dfthcsos \
    --config configs/comparison/arm-b-hermes-glm53.json --job-id armB-glm53-hermes
python3 -m scripts.autoresearch_seeder preflight --job runs/autoresearch-seeder/dfthcsos/armB-glm53-hermes --live --offline-probe
# then enable the config and:
python3 -m scripts.autoresearch_seeder run --job runs/autoresearch-seeder/dfthcsos/armB-glm53-hermes

# Post-run, per arm (no model calls):
python3 -m scripts.autoresearch_seeder status --job <job-dir>
python3 -m scripts.autoresearch_seeder export --job <job-dir>
```

Run arms sequentially on the same machine, not concurrently, so queue and
execution accounting is comparable. `run` re-checks preflight and refuses to
start a paid session unless the config is enabled — the enabled flag is the
operator's switch, and both configs are shipped disabled.
