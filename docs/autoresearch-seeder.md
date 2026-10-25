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
| `transport.py` | Deterministic `FakeTransport` for tests; SDK-backed `RealTransport` (lazy imports) |
| `worker.py` | One research session: prepared context -> batched tool loop -> accounted outcome |
| `controller.py` | Durable job state, atomic leases, budget enforcement, stage machine, recovery |
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
```

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
3. `init` + `preflight --live`, then `run` (this starts a paid MiniMax
   session). `status`/`export` afterwards; `resume` after interruption.
4. Measure verified gain, model/queue/execution/wall time, searches, useful
   sources, attempts, failures, recovery and SDK-reported usage (billing
   caveat: SDK cost is not independently reconciled).

No live pilot was started as part of this implementation.
