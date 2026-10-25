# AutoResearch Seeder

Status: implementation complete, **production disabled**. No campaign,
verifier, scoring rule, budget, branch count or blind-test state was modified.
The example configuration ships with `enabled: false`.

The AutoResearch seeder is a task-isolated autonomous researcher. Per job it:
finds promising external methods (papers, released code, public notebooks),
checks compatibility against the exact official task, implements a candidate,
tests it with cheap sandboxed diagnostics, runs the unchanged official
development validation, independently confirms the same frozen candidate under
the task's final salt, and publishes an immutable, hash-sealed seed package
with full provenance — or an honest terminal record (rejected /
no-improvement / blocked) with all evidence retained.

Design inspirations (not validated claims): MLE-STAR's search-first
implementation strategy, DeepEvolve's research/implementation/feedback
coupling, AiScientist's cumulative inspectable project state.

## Module boundaries

All new code lives in `scripts/autoresearch_seeder/`:

| Module | Responsibility |
|---|---|
| `models.py` | Stable entities (Source, Hypothesis, Experiment, Decision), canonical hashing, bundle freezing, error classes |
| `config.py` | Explicit finite budgets; missing budgets prevent a live start |
| `store.py` | Job-scoped SQLite/WAL research store — sources, hypotheses, experiments, decisions, events, budget ledger |
| `adapter.py` | Task contract loader over the existing `tasks/<id>/library.json` registry; trusted diagnostic/validation wrappers with candidate-vs-infrastructure failure classification |
| `tools.py` | The worker tool dispatcher (search, fetch, propose, decide, diagnose, validate, report-access, claim, finish) shared by offline tests and the live MCP server |
| `transport.py` | Deterministic `FakeTransport` for tests; SDK-backed `RealTransport` (Claude Code backend, lazy imports) |
| `backends.py` | Backend abstraction (`Backend`, `session_metadata`), validated MCP-server interpreter/env, and the optional `HermesBackend` (Hermes Agent CLI) |
| `worker.py` | One research session: prepared context -> batched tool loop -> accounted outcome |
| `controller.py` | Durable job state, atomic leases, budget enforcement, stage machine, recovery |
| `knowledge.py` | Scoped research knowledge base: provenance/taint-enforced audiences, level-boundary releases, reviewed infrastructure corrections, frozen+auditable finding handoffs, nonblocking `check_findings` |
| `investigations.py` | Autonomous research agenda: multi-session investigations, checkpoints, finite budgets, auto-shelving, scoped session prompts |
| `scheduler.py` | Bounded, disabled-by-default single-pass scheduler over eligible queued jobs (and, when enabled, the idle research agenda) |
| `publisher.py` | Machine-checkable acceptance gates and immutable seed export |
| `context.py` | Prepared-context construction for fresh conversations |
| `mcp_server.py` | stdio MCP shim exposing the dispatcher to a live model session |
| `selftest.py`, `samples.py`, `testing.py` | Real smoke test, offline sample generation, shared test scaffolding |

The job/experiment store is deliberately separate from the verified-method
library (`scripts/library_rsi/store.py`): seeder bookkeeping never masquerades
as curated, verified methods. The existing library, registry and runtime queue
are reused unchanged (one narrowly-scoped, backward-compatible change:
`library_rsi/registry.validate_receipt` gained an optional `root` parameter).

## Workflow and state machine

```
queued -> researching -> compatibility_test -> implementing
       -> development_validation -> confirmation -> seed_ready
```

Hold/terminal states: `needs_access`, `retry_wait`, `infrastructure_blocked`,
`budget_exhausted`, `rejected`, `completed_no_improvement`, `cancelled`.

Automatic transitions ([auto]) vs. manual:

- `queued -> researching` — [auto] on `run`/`resume` after lease claim and budget check.
- `researching -> compatibility_test` — [auto] once a diagnostic experiment exists.
- `compatibility_test -> implementing` — [auto] on a recorded continue/refine
  decision after diagnostics (the worker decides; the controller only verifies
  the prerequisites exist).
- `implementing -> development_validation` — [auto] when the worker's
  `run_development_validation` produced a receipt for the current bundle.
- `development_validation -> implementing` — [auto] on receipt FAIL with
  attempts remaining. An experiment failing is **not** the job failing.
- `development_validation -> confirmation` — [auto] on PASS with improvement;
  `-> completed_no_improvement` — [auto] on PASS without improvement.
- `confirmation -> seed_ready` — [auto] when every publisher gate passes.
- `confirmation -> implementing` — [auto] on FAIL with attempts remaining;
  `-> rejected` — [auto] when attempts are exhausted.
- any `-> retry_wait -> previous stage` — [auto] on provider rate-limit
  (bounded by `max_provider_retries` / `retry_wait_seconds`).
- any `-> infrastructure_blocked` — [auto] on sandbox/queue/provider-refusal
  faults; never a scored attempt.
- any `-> budget_exhausted` — [auto] when any finite budget is consumed.
- `needs_access` — [auto] recording when sources are blocked; research
  continues on accessible sources; the state is informational.
- `cancelled` — manual only.

## Trust model

The worker may search, fetch, propose, claim and request tests. Trusted
controller code reads receipts and decides. Concretely:

- Scores parsed from model text or candidate stdout never reach a gate.
  `submit_claim` records claims and always answers that claims are not
  evidence.
- Receipts come only from the task's unchanged official paths:
  `diagnose(attempt)` for diagnostics, `evaluator.evaluate_program(...)` for
  full validation. Official files, limits and scoring are untouched.
- Failure classification: official-source corruption / missing runtime is
  `ToolInfrastructureError` (job-level, never scored); a candidate that
  crashes, times out or exceeds memory is a FAIL receipt (experiment-level).
- A seed requires: unchanged task+protocol hashes; development PASS and
  confirmation PASS under distinct salts through the task's own receipt
  adapter; identical frozen bundle and submission content across both checks
  *and* equal to the current artifact (a receipt for candidate A cannot
  qualify candidate B); improvement over baseline on **both** salts
  (conservative comparison, no favorable pick); `artifact/GENERATION.md`
  reproducible generation instructions; at least one accessed source with
  explicit license status.

## Budgets, queueing and recovery

`budgets` (all required, finite, positive — a config missing any of them
cannot start a live job): `model_session_seconds`, `job_wall_clock_seconds`,
`max_total_cost_usd`, `max_tool_calls`, `max_web_searches`,
`max_provider_retries`, `retry_wait_seconds`.

Interval accounting (all persisted in the budget ledger and job state):

| Category | Charged interval |
|---|---|
| `model` | wall time of model sessions (transport-measured) plus SDK-reported cost where available |
| `queue` | estimated slot wait outside the task engine (wall − engine seconds) |
| `execution` | task-engine seconds from official receipts (note: the heavy `dqi-cpu.lock` wait inside dfthcsos' evaluator is counted under execution — its receipt seconds include lock wait) |
| `wall` | whole-job wall clock across restarts (per-process segments summed into `consumed.wall_seconds`) |

Queue time is therefore never zero-cost invisibly, and the one known
over-attribution (heavy-lock wait inside engine receipts) is documented here
rather than guessed at.

Execution reuses the existing sandboxes and slots: diagnostics go through the
task's `diagnose()` and the shared two quick slots (`<=60 s, <=2 GiB`);
full validations go through the unchanged task evaluator and its exclusive
heavy lock. Nothing widens task time/memory limits or worker counts.

Recovery: jobs are claimed with file-locked compare-and-swap leases whose
owner records hostname, PID, command line and process start time; a restart
reconciles liveness by that identity (PID reuse is detected by mismatched
start time/command), reclaims dead-owner leases as audit events, and refuses
to start when a live owner exists. Experiment IDs are deterministic hashes of
(kind, protocol hash, frozen bundle hash, parameters), so a restart recovers
completed results instead of re-executing them; budgets are read from durable
state and never reset. `preflight` must pass (offline checks always; with
`--live`, credential presence without reading or printing token contents)
before `run` will start a paid session.

## Researcher backends

`provider.backend` selects how a model session talks to the seeder's tools.
Both backends spawn the SAME dispatcher MCP server under the SAME validated
interpreter, so scoring, validation, budgets and receipts are recorded by
trusted code in both cases; the backend only changes the agent runtime that
drives the session.

- **`claude_code`** (default) — `transport.RealTransport`, a
  `claude_agent_sdk` session against the Claude Code CLI. Provider
  configuration comes from the credential env file (`ANTHROPIC_AUTH_TOKEN`,
  `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL`), with an isolated per-job
  `CLAUDE_CONFIG_DIR`.
- **`hermes`** — `backends.HermesBackend`, driving the Hermes Agent CLI
  (Nous Research; pinned release **v0.22.5**, commit `bf0203a`, official
  docs at hermes-agent.nousresearch.com verified 2026-10-25). Invoked
  headless as `hermes chat --oneshot --quiet --format stream-json
  --usage-file … --query-file … --provider custom:<name> -m <model>
  --ignore-rules --in <worker dir>`. Each job gets its own isolated
  `HERMES_HOME` (`private/hermes-home/`: `config.yaml` + 0600 `.env`), so no
  Hermes memory, session or setting is shared between jobs. The GLM endpoint
  is registered as a named custom provider with the `anthropic_messages`
  transport; requested effort goes in `agent.reasoning_effort`. Requires the
  Hermes CLI on the machine — preflight states the prerequisite and
  **enforces the release pin** (`provider.hermes_pin`, default v0.22.5: a
  detected version mismatch or unparseable output fails the live preflight
  with both versions shown, and `run` refuses a failed preflight). Nothing
  is auto-installed, and there is no silent model fallback (the requested
  model is passed explicitly; requested-vs-served is recorded in job
  metadata, effort is never claimed attested).

  Two enforcement layers keep a Hermes session inside the scoped-knowledge
  interface (an isolated HERMES_HOME alone scopes only what Hermes
  remembers): (1) the documented `platform_toolsets` config key restricts
  native toolsets to `cli: [todo]` — no file, terminal, browser, web,
  memory or session_search tools, so the seeder MCP dispatcher is the only
  research path; (2) the launcher wraps the process in `sandbox-exec` with
  deny-read rules on the scoped-knowledge root and credentials
  (`provider.filesystem_isolation`, default enabled on darwin) — an
  OS-level backstop that survives toolset regressions. A regression test
  runs the real wrapper against a binary that attempts the read and must be
  denied, with an unisolated control proving the wrapper is what denies it.

Backend selection is per job config; an unknown value fails factory
construction immediately. `preflight --live` runs the selected backend's own
checks (credential presence, CLI presence/version, isolated home generation,
MCP interpreter) in addition to the task-level checks.

## Autonomous research layer (knowledge + agenda)

Optional, disabled by default (`configs/hermes_research.example.json`). Two
durable stores under a machine-local research root (default
`<run-root>/autoresearch-seeder-research/`, never committed):

**Scoped knowledge base** (`knowledge.py`) — every research record carries a
COMPUTED audience, never a caller-claimed one:

- `external` (public sources): everyone at/above its level.
- `branch_private`: one RSI branch only — code, discoveries, failed
  hypotheses, scores, summaries. A branch receives its own history
  immediately (including failed experiments and next actions); other
  branches cannot retrieve it, before or after release of derived work.
- `package` (finding/handoff): audience = intersection of its input
  audiences PLUS its authoring branch — any private input taints it to that
  branch FOREVER, even when public sources later support the same mechanism.
- `released`: the controller promotes private records/findings at an
  explicit level/dreaming boundary (`research-release`); the release is a
  new level-public record, the original stays private, both stay auditable.
- `infrastructure`: confirmed faults and neutral API corrections;
  distributable only after controller review (`research-review`), and the
  payload schema physically cannot carry scores, methods, evidence or
  receipts, so distribution cannot leak science.

Cross-branch separation is enforced in storage and retrieval
(`eligible_records`), not by prompts: a session's prompt is built ONLY from
records its scope may see. Direction assignments (`assign_direction`)
distribute externally-sourced directions as metadata only — the schema has
nowhere to put outcomes — reducing accidental duplication without steering
branches away from methods via another branch's private failures.

**Finding handoffs** — a ready finding states mechanism+sources,
compatibility with the target parent (code hash/task lineage), evidence
level + receipt IDs (`diagnostic_supported` vs `verified_seed` are different
output classes; verified seeds MUST cite receipts), opportunity/uncertainty/
risks, and the cheapest useful first experiment. Delivery
(`check_findings`/`deliver`) freezes a snapshot beside the attempt record
with a content hash; re-delivery is idempotent; every delivery is auditable.

**Nonblocking attempt check** — `research-check --branch B --level N
--parent-json ... [--attempt-record ...]` returns immediately: ready
compatible findings (frozen into the attempt record if given), or an empty
result — never a wait, never an error (a missing/corrupt knowledge base
yields `blocked: false, findings: []`). The worker may reject delivered
advice; nothing auto-injects findings into campaigns.

**Investigation agenda** (`investigations.py`) — autonomous, multi-session
research items with preserved checkpoints, finite budgets
(sessions/model-seconds/USD) and automatic shelving (budget exhaustion or
repeated sessions with no new activity; shelved items stay durable and
resumable). `next_eligible` is a pure storage read — idle scheduling never
costs model calls. When `schedule --research-config` is enabled and no
seeder job is eligible, at most ONE bounded investigation session runs per
pass; jobs always take priority over research.

CLI: `research-agenda` (list/`--add`), `research-status`, `research-run`
(one session; requires an ENABLED research config), `research-release`,
`research-review`, `research-check`.

## Filesystem and CLI

Jobs live at `runs/autoresearch-seeder/<task>/<job-id>/` with `sources/`,
`hypotheses/`, `experiments/`, `artifacts/`, `private/`, `exports/`.
Credentials never belong there; exports exclude provider authentication.

```
python -m scripts.autoresearch_seeder init --task dfthcsos --config configs/autoresearch_seeder.example.json
python -m scripts.autoresearch_seeder preflight --job <path> [--live] [--offline-probe]
python -m scripts.autoresearch_seeder run --job <path>       # requires enabled config + passing preflight
python -m scripts.autoresearch_seeder resume --job <path>
python -m scripts.autoresearch_seeder status --job <path>
python -m scripts.autoresearch_seeder export --job <path>
python -m scripts.autoresearch_seeder selftest [--fixture | --task dfthcsos]
python -m scripts.autoresearch_seeder sample-export --output docs/autoresearch-seeder/samples
python -m scripts.autoresearch_seeder schedule [--run-root runs] [--loop-passes N] [--sleep-seconds S]
                                             [--research-config configs/hermes_research.example.json]
python -m scripts.autoresearch_seeder research-agenda --root <research-root> [--add TOPIC --branch B]
python -m scripts.autoresearch_seeder research-status  --root <research-root>
python -m scripts.autoresearch_seeder research-run     --root <research-root> --config <research config>
python -m scripts.autoresearch_seeder research-release --root <research-root> --record ID --at-level N
python -m scripts.autoresearch_seeder research-review  --root <research-root> --record ID --reviewer NAME
python -m scripts.autoresearch_seeder research-check   --root <research-root> --branch B --level N
                                                      [--parent-json parent.json --attempt-record record.json]
```

`schedule` is the bounded scheduler: a single pass scans
`<run-root>/autoresearch-seeder/*/*/job.json`, starts at most the oldest
ELIGIBLE job (`queued`, or `retry_wait` past its deadline, config enabled,
not terminal/active), and exits. Idle checks are pure filesystem reads —
no transport is constructed, no model is called. Starting still goes through
the controller's lease claim (duplicate starts impossible with a live owner)
and `run`'s enabled/preflight gating. `--loop-passes` bounds repeated passes
and stops early once no eligible work remains; there is no daemon, and the
scheduler is not registered anywhere as a recurring job.

`init` copies the official seed program unchanged into the job's
`worker/attempt_00/artifact/program.py` (the frozen fallback). `--task-root`
selects an alternate repository tree holding `tasks/` (used by the offline
fixture). The exported package contains `MANIFEST.json`, `SEAL.json` (hashes
of every file), `source-bundle/`, `receipts/{development,confirmation}.json`,
`submission/`, `SOURCES.json`, and `LICENSE-STATUS.md`; re-publishing the
same accepted seed is idempotent, and the package never installs into any
campaign (`installed_into_campaign: false`).

## Worker tool surface

The live session gets native file tools scoped to its own branch (reads in
`worker/`, writes in `worker/attempt_00/`) plus the MCP dispatcher tools:
`web_search`, `fetch_source`, `fetch_repository`, `propose_hypothesis`,
`record_decision`, `run_diagnostic`, `run_development_validation`,
`report_access_needed`, `submit_claim`, `finish`. Confirmation validation is
controller-owned and never worker-callable. Identical search queries are
cached and bounded; HTTP success is never treated as research success; fetched
content is untrusted data with URL, retrieval time, content hash, revision,
attribution and license status recorded; a changed external document creates a
new recorded source revision. The configured host restrictions (the saved
Kaggle access restriction by default) are enforced in one place for every
fetch path — public HTTPS only, private addresses blocked, no proxy or raw-HTTP
bypass exists — and blocked sources are recorded via `report_access_needed`
while research continues elsewhere.

## Offline testing

- `tests/test_autoresearch_seeder.py` — the six deterministic orchestration
  scenarios (end-to-end to immutable seed; resume memory with failures and
  next action; crash/restart budget+result recovery without duplicate
  execution; publish gates; budget/provider-failure outcomes; isolation,
  access denial and source revisions) plus config and idempotency guards.
- `tests/test_seeder_smoke.py` — scenario 7: real sandboxed diagnostics and
  receipt parsing through the actual adapter, including a negative test that
  the sandbox denies reading private files, honest prerequisite reporting for
  dfthcsos, and the CLI surface.
- `tests/fixtures/seed_demo_repo/` — an offline demo task implementing the
  same `library.json`/evaluator/diagnose/receipt contract with a real
  `sandbox-exec` profile and deterministic salt-dependent scoring. It is a
  test fixture, not a benchmark.
- `tests/test_seeder_mcp.py` — the MCP server over a REAL stdio client
  session: initialize, tool discovery, executing a diagnostic through the
  wire, durable store effects, unknown-job rejection.
- `tests/test_seeder_leases.py` — lease ownership with two real OS
  processes: expiry never overrides a live owner, PID-reuse detection,
  token-gated release, stale owners cannot release the replacement's lease.
- `tests/test_seeder_export.py` — seal covers full relative paths (duplicate
  basenames included), tamper detection, interrupted-publication recovery,
  immutability of verified exports.
- `tests/test_seeder_accounting.py` — crash-time orphan-session charging
  (bounded by session budget), provider-error events, honest model/effort
  metadata, cost-enforcement caveat in status.
- `tests/test_seeder_backends.py` — backend selection factory, Hermes
  profile generation/isolation (two jobs share nothing), preflight honesty
  (missing binary/credential/model fail clearly, no secrets in output), and
  the FULL Hermes run path against a scripted fake `hermes` binary (CLI
  surface, isolated HERMES_HOME, stream-json parsing, usage accounting,
  wall-clock kill on session-budget overrun, provider-error classification).
  The real-Hermes discovery test skips with an explicit machine prerequisite
  when the CLI is absent.
- `tests/test_seeder_scheduler.py` — eligibility from durable state only,
  idle checks construct no transport, lease-guarded start, busy-owner skip,
  finished jobs never rescheduled, disabled-config block, bounded loop.
- `python -m scripts.autoresearch_seeder selftest --fixture` — the standalone
  smoke command (identical checks to the pytest smoke).

Everything above runs without provider credentials, network or model sessions.
Sample artifacts (prepared context, accepted and rejected manifests) are
regenerated deterministically into `docs/autoresearch-seeder/samples/`.

## Live pilot (for Codex; NOT performed here)

1. Set up the dfthcsos task on the target machine (venv, official data,
   calibration) and verify `selftest --task dfthcsos` passes.
2. Create a real config with `enabled: true`, complete budgets, provider
   credential file, and the intended `blocked_hosts`.
3. `init` + `preflight --live`, then `run` (this starts a paid model
   session). `status`/`export` afterwards; `resume` after interruption.
4. Measure verified gain, model/queue/execution/wall time, searches, useful
   sources, attempts, failures, recovery and SDK-reported usage (billing
   caveat: SDK cost is not independently reconciled).
5. For the backend comparison, follow `docs/autoresearch-seeder-comparison.md`
   (both arm configs are shipped DISABLED; no comparison session has run).

No live pilot was started as part of this implementation.
