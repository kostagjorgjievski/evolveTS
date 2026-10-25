# Implementation handoff: AutoResearch Seeder for EvolveTS-RSI

## Assignment and completion boundary

Implement a task-isolated autonomous researcher that finds promising external methods, checks compatibility, implements them, tests them, and publishes immutable verified seed packages. GLM is the implementation engineer. MiniMax-M3.1-Flash is the initial research-worker model under test. Codex will independently review and test the implementation afterward.

This is implementation authorization, not authorization to launch an unlimited research service or alter current campaigns. Deliver working code, deterministic tests, documentation and a disabled example configuration. Do not start a paid live pilot as part of setup. Do not modify, stop, reset, reseed or expose the live DQI/chemistry campaigns or the existing blind MiniMax seeder acceptance test. Do not submit to Kaggle.

Repository: your local checkout of `kostagjorgjievski/evolveTS`. The Mac Mini path in earlier messages is not present on the MacBook Air. Resolve all runtime paths relative to this checkout.

## Objective

The product is a runnable, verified seed with provenance and experimental evidence. A literature summary or persuasive proposal is not a successful seed. Reproducing a public implementation is valuable; do not require novelty. Separate external claims, predictions, diagnostic results, full development verification and independent confirmation.

Combine three design ideas:

- MLE-STAR: search for strong task-specific implementations before defaulting to familiar approaches. https://arxiv.org/abs/2506.15692
- DeepEvolve: couple research with implementation, debugging and measured feedback. https://arxiv.org/abs/2510.06056
- AiScientist: keep cumulative, inspectable project state outside transient conversations. https://aclanthology.org/2026.findings-emnlp.2200/

These are inspirations, not a claim that this hybrid has already been validated. No new OpenClaw dependency is necessary. A scheduler adapter can be added later.

## Read the existing code before designing replacements

- `scripts/library_rsi/registry.py`: task registration and verifier-receipt validation.
- `scripts/library_rsi/store.py`: SQLite/WAL versioned method records, evidence levels and task-filtered snapshots.
- `scripts/library_rsi/trial.py`, `advisor.py`, `server.py`: existing trial/advisor boundaries; inspect before deciding what is reusable.
- `configs/library_rsi.example.json`, `configs/templates/library_task.json`, `docs/library-rsi/design.md`.
- `scripts/literature_acceptance/solo_server.py`: existing public search and source tools. Its `search()` uses MiniMax's coding-plan search service; that service successfully responds, but recent exact Kaggle notebook queries produced unrelated results. Do not treat HTTP success as research success.
- `scripts/literature_acceptance/run_worker.py`: provider configuration loader and worker utilities.
- `scripts/literature_acceptance/dfthcsos_minimax_seeder_test.py`: the existing independent live test; read its implementation, but do not read its evolving results or reuse its run.
- `tasks/dfthcsos/{evaluator.py,diagnose.py,library_validate.py,protocol.json}` and the official task/API contract.
- `scripts/runtime_queue.py`: TWO shared quick slots for diagnostics <=60 sec AND <=2 GiB; integrations and full checks retain ONE global heavy slot.

Reuse these contracts where appropriate. Avoid blanket importing modules with configuration side effects or relying on ambiguous module names such as `evaluator`, `registry`, or `supervise`. Changes to shared infrastructure must be narrowly scoped and backward compatible.

## Module boundaries

Suggested new module: `scripts/autoresearch_seeder/`, with explicit imports and a small CLI.

1. **Controller:** durable job queue, leases, budget enforcement, recovery and stop conditions. Ordinary code owns state transitions and validation gates.
2. **Research worker:** MiniMax chooses searches, evaluates evidence, proposes mechanisms, edits its own artifacts and requests tests. Implement a real tool loop, not a single prompt that writes a research report.
3. **Task adapter:** supplies the task contract, neutral API guide, frozen starting artifact, baseline cost, diagnostics and official verification entry points. Chemistry first; no chemistry-specific assumptions in controller/storage logic.
4. **Persistent research store:** sources, hypotheses, experiments, results, decisions and immutable artifacts. Reuse the existing versioned library where suitable; add a separate job/experiment store if needed rather than overloading verified-method records.
5. **Publisher:** creates reviewable seed packages only when machine-checkable acceptance gates pass. Publishing a package does not install it into a campaign.

Provider authentication stays in the existing credential plumbing. Never write tokens into prompts, research memory, events, source caches, CLI arguments or exports. Persist requested and served model identifiers and requested effort; do not claim the provider honored an effort value unless verified.

## Workflow

`queued -> researching -> compatibility_test -> implementing -> development_validation -> confirmation -> seed_ready`

Also support `needs_access`, `retry_wait`, `infrastructure_blocked`, `budget_exhausted`, `rejected`, `completed_no_improvement` and `cancelled`. Document which transitions are automatic. Distinguish an experiment's failure from the research job's failure.

- Search primary papers, released code and public notebooks. Record why a result is relevant. Exact/slightly reformulated queries should be bounded; repeated unrelated results are a search failure, not evidence that no method exists.
- Fetch and inspect the actual source when accessible. Save URL, retrieval time, author attribution, license if known, immutable revision/commit or content hash, and local content hash.
- Treat retrieved material as untrusted data. Preserve the existing saved Kaggle access restriction; do not use another agent, proxy, alternate host or raw HTTP fetch to bypass denied access. Record `needs_access` for blocked sources and continue independent accessible research.
- Compare plausible mechanisms by dominant cost, affected objective terms, compatibility, implementation effort, evidence and cheapest discriminating test. This is not a fixed quota of papers or a mandatory number of ideas.
- The worker must be able to reject its inherited architecture. Record an ambitious opportunity hypothesis where justified, but never require an invented 2x/50% gain to pass a stage.
- Run cheap mathematical or microcircuit tests before expensive full checks where useful. A toy test is not official verification.
- Implement a complete candidate and run the unchanged official development validation. Use the actual full objective, not a cheaper proxy as the final score.
- If the route fails, diagnose whether the cause is an algorithmic incompatibility, candidate bug, tool/infrastructure fault, resource limit or unavailable source. Refine or pivot based on evidence. Keep the valid starting artifact as fallback.
- Freeze the entire source bundle and generated submission. Independently validate the same frozen candidate with the task's configured confirmation salt. No edits between acceptance checks.
- Publish only a fully accepted candidate. Otherwise finish with honest experiment records and a no-improvement or blocked outcome.

An always-available supervisor may later wake when sources change, work arrives or a retry becomes eligible. It should idle when there is no eligible work; do not create a perpetual model conversation that spends tokens without a concrete experiment.

## Durable state and context preparation

Use task/job-scoped records with stable IDs. Minimum entities:

- **Source:** URL, provenance, revision/content hash, retrieval status, license/attribution, relevance and access limitation.
- **Hypothesis:** mechanism/family, source IDs, affected cost terms, compatibility assumptions, expected opportunity explicitly labeled as a prediction, first test and rejection conditions.
- **Experiment:** hypothesis ID, frozen input/source hashes, requested action, actual tool invocation, timing, exit/status, bounded logs plus full log location, receipt hashes, metrics and conclusion.
- **Decision:** continue/refine/pivot/reject, supporting experiment IDs and next action.
- **Job:** task, baseline, worker identity, budgets, current stage, lease owner/expiry, retry state and checkpoint.
- **Seed manifest:** task/protocol hashes, parent/baseline identity, complete source and submission hashes, both official receipts, measured improvement, provenance and resource/cost accounting.

On resume or context compaction, construct prepared context from the task contract, own best valid artifact, actual scores, hypothesis shortlist, failed experiments, unresolved issues and next test. Link to complete own evidence for selective retrieval. Do not blindly truncate away failures or repeatedly inject every transcript.

This memory is the seeder's own research history. Never include other live campaign branches, private transcripts or their discoveries. Public research can eventually become a versioned library snapshot, but do not change what active campaigns can see.

## Trust and acceptance gates

The worker may request tests and propose claims; trusted controller code reads receipts and determines evidence level and acceptance. Never trust scores printed by the model or candidate stdout.

A seed requires:

- Correct task and unchanged official verifier/protocol identity.
- PASS on both full development and confirmation checks under distinct configured salts.
- Same complete frozen source bundle and submission content across the two checks, verified by hashes.
- Improvement over the stated baseline under the existing normalization, with both measured results retained. A configurable conservative comparison can be used; never silently pick the more favorable salt.
- Reproducible generation instructions and necessary helper files.
- Source attribution and explicit license status; unresolved reuse questions must be visible in the package.

The publisher must cross-check current artifact hashes against receipts so a valid receipt for candidate A cannot qualify candidate B. Do not silently upgrade a published claim into verified evidence. Infrastructure failure must not become a scored baseline attempt.

## Budgets, queueing and recovery

Configuration must explicitly set finite model-session time, wall-clock job limit, model/token or cost limit where measurable, tool-call limit and retry limits. Disabled example defaults are fine; missing required budgets must prevent a live start. Do not expand existing task time/memory limits.

Log separately model time, queue wait, execution time and total wall time. Explicitly document which budget charges each interval; queue time is never zero-cost invisibly. Recovery must preserve consumed budget and artifacts and must not start a duplicate session or reset allowances.

Use atomic claims/leases for jobs, and idempotent experiment/result publication. A restart must reconcile an actually running process using identity/create-time, not PID existence alone. Never blindly re-execute an expensive test if its result can be recovered. A real tool preflight must run before launching a paid research session.

Keep per-job execution in existing candidate sandboxes and current shared queue slots. Search/retrieval and numerical candidate execution are separate capabilities. This project does not authorize increasing the number of campaign workers or adding a competing unbounded seeder workload.

## Suggested filesystem and CLI

New runs: `runs/autoresearch-seeder/<task>/<job-id>/`.

Subdirectories: `sources/`, `hypotheses/`, `experiments/`, `artifacts/`, `private/`, `exports/`. Credentials do not belong here. Exported seeds and summaries exclude provider authentication and unrelated run contents.

Suggested commands (adapt names to repo conventions):

```
python -m scripts.autoresearch_seeder init --task dfthcsos --config <file>
python -m scripts.autoresearch_seeder preflight --job <path>
python -m scripts.autoresearch_seeder run --job <path>
python -m scripts.autoresearch_seeder resume --job <path>
python -m scripts.autoresearch_seeder status --job <path>
python -m scripts.autoresearch_seeder export --job <path>
```

Dry-run/offline tests must work without provider credentials. Example config must be disabled and must not include known chemistry solutions or the public portfolio's improved artifacts. Keep a later blind evaluation possible.

## Tests GLM must deliver

Use deterministic fake model/tool responses for orchestration tests. Test behavior, not just data-class serialization.

1. End-to-end fake research -> hypothesis -> failed diagnostic -> revision/pivot -> passing full checks -> immutable seed export.
2. Fresh conversation after resume receives own experimental memory, including failed paths and precise next action.
3. A crash/restart preserves budget, recovers completed tests and prevents duplicate execution/session launch.
4. Development PASS plus confirmation FAIL cannot publish; mismatched source/submission/task/protocol hashes cannot publish; fabricated model scores cannot publish.
5. Budget exhaustion and rate-limit/provider failures result in bounded retry or explicit terminal/block state with preserved artifacts.
6. Task and live-branch isolation; blocked access is not bypassed; changing external source contents creates a new recorded revision.
7. Real adapter smoke test exercises actual sandboxed diagnostics and receipt parsing without starting a model session. Existing queue and relevant task/library tests still pass.

Do not initiate full expensive chemistry evaluations merely to make setup look complete. Make the real model acceptance run an explicit separate action for Codex to perform after review.

## Codex's subsequent live evaluation

After reviewing GLM's changes, Codex will verify preflight and run a bounded MiniMax-alone chemistry pilot with the neutral guide and official baseline, independent of active branches and known improved solutions. It will measure verified gain, elapsed/model/queue time, actual searches and useful sources, attempts, failures, recovery and SDK-reported usage/cost with a billing caveat. A single success demonstrates feasibility, not general reliability.

Where practical, compare the new workflow with the existing standalone workflow under matched inputs/budget and repeat before broad deployment. Add strong-model review only after identifying a specific failure mode rather than quietly giving MiniMax the known solution.

## Required handback from GLM

Provide changed-file list, design decisions and deviations, exact offline/smoke commands and results, disabled example config, a sample prepared-context document, sample successful/rejected seed manifests, and known limitations. Explicitly confirm no production campaign, verifier, scoring, budget, branch count or blind-test state was modified. Leave the implementation reviewable; do not auto-enable production.
