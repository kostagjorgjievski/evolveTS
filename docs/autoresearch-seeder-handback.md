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

## Changed / added files

**New module `scripts/autoresearch_seeder/`** — `__init__.py`, `models.py`,
`config.py`, `store.py`, `adapter.py`, `tools.py`, `transport.py`,
`worker.py`, `controller.py`, `publisher.py`, `context.py`, `mcp_server.py`,
`selftest.py`, `samples.py`, `testing.py`, `__main__.py`.

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
