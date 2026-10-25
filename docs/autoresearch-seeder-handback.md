# AutoResearch Seeder — GLM implementation handback

Branch: `implementation/autoresearch-seeder` (from `origin/handoff/autoresearch-seeder`)
Repository: `kostagjorgjievski/evolveTS`. Full architecture documentation:
[docs/autoresearch-seeder.md](autoresearch-seeder.md).

## Confirmation

- **No production campaign, verifier, scoring rule, task budget, branch count
  or blind-test state was modified.** The blind MiniMax seeder acceptance test
  file was read (implementation only) and integrated verbatim, byte-identical
  to the transfer manifest hash; its runs were never read or reused.
- No paid research session, provider call or Kaggle submission was made.
- The shipped example config is disabled (`enabled: false`,
  `production.automatic_enable: false`).

## Phase 2 — review fixes, Hermes backend, comparison preparation

Phase 2 code commit: **`4e79cda`** on `implementation/autoresearch-seeder`
(this documentation-only commit sits on top of it). Phase 2 continues from
phase-1 commit `a226827` after Codex's Mac Mini review (40 tests, zero skips
there, including real chemistry; the blocking findings below were outside
that suite). All six findings are fixed with regression tests, Hermes is an
optional researcher backend, the scheduler is bounded and disabled by
default, and the backend comparison is prepared but NOT started.

### The six review findings and their fixes

1. **Broken MCP executable** — the MCP stdio server now launches under an
   explicitly validated interpreter (`backends.resolve_interpreter`: repo
   venv → current interpreter, each probed by actually importing `mcp` in a
   subprocess; failure lists what was tried). Verified by a REAL stdio MCP
   client round-trip in `tests/test_seeder_mcp.py` (initialize → tool
   discovery → execute a diagnostic → durable store effect).
2. **Wrong credential root** — credentials resolve from an explicit
   application root (`backends.credential_path`), never from job-dir
   arithmetic; contents are never printed (tests assert token absence from
   preflight output, metadata and child environments).
3. **Confirmation regenerated submissions** — `run_validation` now REQUIRES
   the frozen development submission directory for confirmation and re-feeds
   its exact bytes to the official evaluator under the final salt; a missing
   submission raises instead of regenerating. Regression test
   `test_confirmation_reverifies_frozen_submission_not_regenerated` uses a
   genuinely nondeterministic generator and proves generation happened once
   (different generator logs, identical frozen submission hashes, both
   receipts preserved).
4. **Expired leases allowed duplicate live owners** — lease ownership is
   (process identity, secret token): a live same-host owner blocks takeover
   REGARDLESS of expiry (identity = hostname + PID + command + process start
   time, so PID reuse is detected); renew/release are token-gated, so a
   stale owner cannot release the replacement's lease. Tested with two real
   OS processes in `tests/test_seeder_leases.py`.
5. **Export seals lost duplicate filenames** — seals now cover full relative
   paths; `verify_export` independently re-verifies every sealed member
   before success is returned; interrupted publications are detected and
   rebuilt. Tests: duplicate basenames, tampering, recovery, immutability.
6. **Bundle hashing rejected ordinary folders** — ordinary nested helper
   directories are allowed; symlinks (including directory symlinks), hard
   links and special files are still rejected; limits preserved.

Additionally: requested-vs-served model/effort is recorded honestly
(effort never claimed attested), crash-time model budget is recovered from
orphan-session markers (upper bound, capped by the session budget),
provider errors are recorded with class, and status output states that cost
caps are post-hoc SDK-reported only — not a real-time spend limit.

### Hermes researcher backend (optional; Claude Code preserved)

- `provider.backend` selects the backend: `claude_code` (default, unchanged
  behavior) or `hermes`. The controller, tools, validation, receipts and
  publication are backend-agnostic; there is ONE controller, no duplicated
  validator/scoring/source DB. Both backends spawn the same dispatcher MCP
  server under the same validated interpreter.
- **Pinned Hermes Agent release: v0.22.5** (commit
  `bf0203a794a07aac3ff764972ab9087baa4e4f4e`, released 2026-10-23; official
  docs hermes-agent.nousresearch.com, verified 2026-10-25). The pin and the
  version the installed binary reports are both recorded in job metadata.
- Configuration was taken from the official docs, not invented: headless
  `hermes chat --oneshot --quiet --format stream-json --usage-file …
  --query-file … --provider custom:<name> -m <model> --ignore-rules --in
  <dir>`; per-profile home via `HERMES_HOME` (each job gets
  `private/hermes-home/` with `config.yaml` and 0600 `.env` — no shared
  memory, sessions or settings between jobs); named custom provider with
  `api`/`key_env`/`transport: anthropic_messages` for the Anthropic-compatible
  GLM endpoint; `mcp_servers` stdio entries with `tools.include` filtering on
  original tool names; `agent.reasoning_effort` for requested effort.
  `--ignore-user-config`/`--safe-mode` are deliberately NOT passed (they
  would discard the per-job provider/MCP configuration; isolation comes from
  HERMES_HOME itself).
- No silent fallback: the requested model is passed explicitly; requested vs
  served models are recorded separately; effort honoring is never claimed
  attested. Wall-clock session kills (process group) enforce the
  model-session budget; provider errors are classified like the Claude
  backend (rate limit / refusal / crash).

### Bounded scheduler (disabled by default)

`scheduler.py` + CLI `schedule`: a single bounded pass scans job records,
starts at most the oldest eligible job (queued, or retry_wait past its
deadline; config enabled; never terminal/active), and exits. Idle checks
are pure filesystem reads (tests prove no transport is constructed).
Duplicate starts are impossible (lease claim); finished experiments are
never repeated (terminal jobs are never eligible). `--loop-passes` bounds
repetition and stops early when idle; there is no daemon and nothing
recurring during development.

### Backend comparison — PREPARED, NOT STARTED

`configs/comparison/arm-a-claude-glm53.json` (Claude Code + GLM-5.3 medium)
and `configs/comparison/arm-b-hermes-glm53.json` (Hermes + same endpoint,
effort, budgets, tools) — both `enabled: false`, differing ONLY in
`provider.backend`. Protocol, metrics (from durable records, not model
self-reports), billing caveats, the fresh-session knowledge-preservation
check, Mac Mini prerequisites and exact launch commands:
[docs/autoresearch-seeder-comparison.md](autoresearch-seeder-comparison.md).
The comparison task is the existing dfthcsos chemistry task itself (pinned
inputs, offline library namespace, official verifier) — no new dependency
was invented, and none is missing.

## Changed / added files

**New module `scripts/autoresearch_seeder/`** — `__init__.py`, `models.py`,
`config.py`, `store.py`, `adapter.py`, `tools.py`, `transport.py`,
`worker.py`, `controller.py`, `publisher.py`, `context.py`, `mcp_server.py`,
`selftest.py`, `samples.py`, `testing.py`, `__main__.py`; phase 2 added
`backends.py` (backend abstraction, validated MCP interpreter/env, Hermes
backend) and `scheduler.py` (bounded, disabled-by-default).

**Phase 2 configuration and docs** — `configs/comparison/arm-a-claude-glm53.json`
and `configs/comparison/arm-b-hermes-glm53.json` (both DISABLED);
`docs/autoresearch-seeder-comparison.md` (protocol, metrics, Mac Mini
prerequisites and launch commands); backend documentation folded into
`docs/autoresearch-seeder.md`.

**Integrated verbatim from the handoff reference snapshot** (SHA-256 verified
against `handoffs/autoresearch-seeder/MANIFEST.sha256.json`; 21/21 match):
`scripts/runtime_queue.py`; `scripts/library_rsi/registry.py`,
`store.py`; `scripts/literature_acceptance/source_repository.py`,
`README.md`; `tasks/dfthcsos/*` (14 files: evaluator, diagnose,
library_validate, library_receipts, library.json, protocol.json,
init_program.py, verify_runner, metric_preflight, calibrate, README,
OFFICIAL_SCORING, tools_server, test_task.py); `tasks/dqi/evaluator.py`,
`protocol.json` (dfthcsos' pinned process-limiter dependency);
`configs/templates/library_task.json`; `tests/test_runtime_queue.py`;
`docs/library-rsi-design.md` (as `docs/library-rsi-design.md`).

**Modified within integrated files (two, both narrowly scoped):**

- `scripts/library_rsi/registry.py` — `validate_receipt` gained an optional
  `root=ROOT` parameter (backward compatible; default behavior unchanged) so
  fixture-rooted tasks can validate receipts through the same adapter.
- `tasks/dfthcsos/test_task.py` — added `skipif` guards for the two tests
  that need machine-local official data / the task runtime (absent on a fresh
  checkout). Everything else in the file is byte-identical, so its manifest
  hash differs from the snapshot by exactly this documented edit.

**Reconstructed:** `tasks/dfthcsos/dfthcsos.txt` — the task description was
omitted from the transfer snapshot but required by the `library.json`
contract; rebuilt from the task README and OFFICIAL_SCORING, clearly marked
as a reconstruction with no scoring authority.

**New configuration:** `configs/autoresearch_seeder.example.json` (disabled).

**New tests:** `tests/test_autoresearch_seeder.py` (22 tests, scenarios 1–6
plus config/idempotency guards), `tests/test_seeder_smoke.py` (4 tests,
scenario 7).

**New fixture:** `tests/fixtures/seed_demo_repo/tasks/seed_demo/` — offline
demo task implementing the identical adapter contract with a real
`sandbox-exec` profile and deterministic salt-dependent verification.

**Docs and samples:** `docs/autoresearch-seeder.md`,
`docs/autoresearch-seeder/samples/{prepared-context.md,
seed-manifest-success.json, seed-seal-success.json,
seed-manifest-rejected.json, seed-license-status.md}`, this handback.

## Design decisions and deviations

1. **One generic task adapter, no chemistry assumptions in the core.**
   `adapter.py` loads any task through the existing `library.json` registry
   contract and calls the task's own `diagnose(attempt)` /
   `evaluator.evaluate_program(program, output, salt=...)` via importlib —
   the same entry points the task's MCP tools and tests already use.
   dfthcsos and the demo fixture are instances of the same contract; the
   controller, store and publisher contain no task-specific logic.
2. **Failure classification lives in the adapter.** `ValueError('Official
   source mismatch…')` (and a missing runtime) is infrastructure; candidate
   crashes/timeouts/memory are FAIL receipts. This mirrors how dfthcsos'
   own `evaluate()` wrapper treats candidate faults and keeps "infrastructure
   failure must not become a scored baseline attempt" true by construction.
3. **Worker tool loop is dispatcher-mediated and shared.** The deterministic
   offline loop and the live MCP server call the same `ToolDispatcher`; the
   tested behavior is the paid behavior. Confirmation validation is
   controller-owned and not exposed to the worker.
4. **Fake transports carry simulated artifact writes.** In live sessions the
   model edits its attempt with native file tools; in fake sessions the
   transport's `writes` field simulates them (path-checked inside the
   attempt). This keeps file-editing outside the dispatcher's trusted tool
   surface.
5. **Wall-clock budgeting across restarts.** `time.monotonic()` is meaningless
   across processes, so each run segment sums its elapsed wall time into
   `consumed.wall_seconds` on exit; budgets therefore survive restarts
   without ever resetting.
6. **Queue-wait accounting is explicit about its limit.** Engine receipts
   (dfthcsos) include heavy-lock wait inside their `seconds`; the ledger
   records engine seconds under `execution` and wall-minus-engine under
   `queue`, with the over-attribution documented in
   docs/autoresearch-seeder.md rather than silently estimated.
7. **No library writing.** The publisher never writes into the versioned
   method library; `publishing.library_snapshot` exists in config but is
   disabled, and a future integration should go through the library's own
   ingest validation.
8. **Live transport reuses the repo's established SDK pattern**
   (scoped tools, `dontAsk`, MCP child server, retry classification regexes
   mirroring `scripts/run_bounded.py`) but was necessarily only
   structurally verified offline — see limitations.

Deviations from the handoff's suggestions: none of substance. The CLI keeps
the suggested names plus `selftest` and `sample-export`; the supervisor
("wake on changes") is deliberately not implemented — the handoff permits a
later scheduler adapter, and an idle supervisor with no eligible work would
violate the no-token-spend-without-experiment rule.

## Exact offline commands and results (all run on the MacBook Air checkout)

```bash
cd evolveTS

# Full suite (existing tests + seeder tests + smoke + dfthcsos task tests)
python3 -m pytest tests tasks/dfthcsos/test_task.py -q
# -> 38 passed, 2 skipped in ~4 s
#    (the 2 skips are dfthcsos tests needing machine-local official data/venv;
#     they run fully on a machine with the task setup)

# Scenario 7 standalone: real sandboxed diagnostics + receipt parsing
python3 -m scripts.autoresearch_seeder selftest --fixture
# -> {"mode": "fixture", "ok": true, ...} all 8 checks pass
#    (real sandbox-exec diagnostic, real development + confirmation
#     validations under distinct salts, receipt validation through the task
#     adapter, deterministic-verification check)

# dfthcsos mode on this machine (prerequisites honestly reported):
python3 -m scripts.autoresearch_seeder selftest --task dfthcsos
# -> exit 1: task runtime + official verifier inputs missing (expected here;
#    data and .dfthcsos-venv are machine-local setup, not in the transfer)

# Sample artifacts regeneration (deterministic, offline)
python3 -m scripts.autoresearch_seeder sample-export --output docs/autoresearch-seeder/samples
```

The two dfthcsos-integration skips and the failed dfthcsos selftest mode on
this machine are prerequisite reporting, not test failures: on the machine
with the full task setup (Codex's environment) the same commands exercise the
real chemistry adapter.

### Phase 2 results (MacBook Air, this continuation)

```bash
python3 -m pytest tests -q
# -> 75 passed, 1 skipped in ~10 s
#    (the 1 skip is the real-Hermes discovery test: the Hermes CLI is not
#     installed on this machine; the skip message states the prerequisite
#     and that the fake-binary tests already cover the full run path)

python3 -m pytest tasks/dfthcsos/test_task.py -q
# -> 2 passed, 2 skipped (official metric file / Mac isolation not on this
#    machine — the same tests pass fully on the Mac Mini)

python3 -m scripts.autoresearch_seeder selftest --fixture
# -> ok: true, all checks pass (confirmation now re-feeds frozen bytes)
```

Test-file breakdown (fixture vs chemistry):

| File | Tests | Real substrate |
| --- | --- | --- |
| `tests/test_autoresearch_seeder.py` | 24 | seed_demo fixture via real sandbox-exec; includes the frozen-submission confirmation regression |
| `tests/test_seeder_smoke.py` | 4 | real sandbox diagnostics + CLI surface |
| `tests/test_seeder_mcp.py` | 4 | REAL stdio MCP client session against the dispatcher |
| `tests/test_seeder_leases.py` | 5 | two real OS processes |
| `tests/test_seeder_export.py` | 4 | real export directories, real hashing |
| `tests/test_seeder_accounting.py` | 6 | real store ledgers/events |
| `tests/test_seeder_backends.py` | 10 (+1 skip) | real config files/0600 modes; full Hermes run path vs scripted fake binary |
| `tests/test_seeder_scheduler.py` | 8 | real job directories + fixture task to completion |
| `tasks/dfthcsos/test_task.py` | 2 here / 4 on Mac Mini | REAL chemistry (official verifier + data) — chemistry tests run where the setup exists; nothing on the MacBook Air substitutes for them |

No test in this suite claims real-chemistry validation: the fixture demo
task is clearly a fixture, and the chemistry tests either run against the
official task setup or skip with the machine prerequisite stated.

## Sample artifacts

- `docs/autoresearch-seeder/samples/prepared-context.md` — what a fresh
  conversation receives mid-research: task contract and hashes, baseline,
  budgets, hypothesis shortlist, the **failed** diagnostic with its cause,
  the precise next action, and an evidence index (failures retained, full
  transcripts not re-injected).
- `docs/autoresearch-seeder/samples/seed-manifest-success.json` — an accepted
  seed: distinct dev/confirmation salts, both measured ratios retained
  (4.90 / 4.76 over baseline 1.0 on the demo fixture), bundle and receipt
  hashes, provenance, resource accounting, `production_enabled: false`,
  `installed_into_campaign: false`; with `seed-seal-success.json` (per-file
  hashes) and `seed-license-status.md`.
- `docs/autoresearch-seeder/samples/seed-manifest-rejected.json` — a
  rejection record: development PASS but confirmation FAIL cannot publish,
  with machine-readable reasons.

## Known limitations

- **The live SDK transport (`transport.RealTransport`) and the MCP shim are
  structurally verified only.** They mirror `run_worker.py`'s proven loop and
  the task's existing MCP servers, but no paid session was run (by design).
  Codex's pilot is their first live exercise; expect integration-level, not
  architecture-level, fixes if anything surfaces.
- **dfthcsos prerequisites are machine-local.** This checkout has no
  `.dfthcsos-venv`, official data or calibration receipt (excluded from the
  transfer); the chemistry path runs where those exist.
- **Queue-wait attribution** for dfthcsos full validations is approximate
  (engine receipts embed the heavy-lock wait); documented, and total wall
  time is always exact.
- **The web_search service** wraps MiniMax's coding-plan search exactly as
  `solo_server.search()` does; per the handoff's warning, the dispatcher
  treats it as unverified input (cached, bounded, relevance recorded by the
  worker) — HTTP success is never research success.
- **`fetch_repository` success-path** is exercised only through its
  upstream-tested implementation (`source_repository.py`, integrated
  verbatim); the offline tests cover its access-restriction enforcement, not
  a live GitHub fetch.
- **The demo fixture is not a benchmark**; its purpose is exercising the
  orchestration and trust gates deterministically.
- Sandbox isolation is macOS `sandbox-exec`; on other platforms the fixture
  runs unsandboxed and the isolation test skips (dfthcsos itself requires
  darwin already).

### Phase 2 limitations and untested live behavior

- **The real Hermes CLI was never executed** (not installed on the MacBook
  Air). Everything except the binary itself is tested offline against a
  scripted stand-in: the generated profile, the exact CLI surface, the
  isolated HERMES_HOME environment the child receives, stream parsing,
  usage accounting, wall-clock kills and error classification. Remaining
  live unknowns for the Mac Mini: (a) whether release v0.22.5 accepts
  `--provider custom:<name>` together with `--query-file`/`--format
  stream-json` in one invocation exactly as documented; (b) the shape of its
  stream-json events (the parser is deliberately shape-agnostic: any `model`
  field is recorded); (c) whether `--usage-file` cost fields match the docs'
  example. The real-binary discovery test will run there and preflight
  reports the version probe.
- **Hermes wall-clock budgeting is coarser than turn-based budgeting**: the
  Claude backend clamps `max_turns` to the remaining tool-call budget;
  Hermes receives only the wall-clock session budget (its chat command
  documents no `--max-turns`; the legacy `hermes-agent` runner has one but
  is a different entry point). Tool-call budgets are still enforced exactly
  by the trusted dispatcher, so this affects pacing, not accounting.
- **No comparison session has run**; both arm configs are disabled and the
  scheduler is disabled by default. Nothing recurring is registered
  anywhere.
- **Hermes reasoning-effort transmission over the Anthropic-compatible
  transport is unverified**: the docs attest `agent.reasoning_effort`
  reaches the provider on `chat_completions`/`codex_responses` transports;
  for `anthropic_messages` the seeder records effort as requested-only and
  never claims it was honored (metadata `effort_attested: false`).
