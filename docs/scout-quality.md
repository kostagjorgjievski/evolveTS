# Scout quality and benefit evaluation

MiniMax discovers and proposes; the reproducer checks original sources and tests.
Only unchanged official dual-salt validation of the identical frozen submission
can certify an exported seed. A research packet is never certification.

## Changes

Every scout window gets a scope-filtered known-method index. Exact mechanism
text, shared URLs and identical content hashes identify possible duplicates;
none automatically rejects a direction. New source revisions remain distinct.
There is no cross-task index or other RSI branch access.

The scout should call `propose_hypothesis`, then `record_scout_packet` before its
checkpoint. A packet requires original code sections, compatibility, explicit
uncertainty, a cheap falsifying test, rejection conditions and a next action.
The host pins fetched citations and dependencies by content hash. Missing
original citations refuse the packet; missing dependencies label it
`needs_dependency_recovery`. Structure and source presence can be checked;
correct interpretation still requires independent review.

DQI resource comparisons calculate R*Q^2*T from finite positive, cited inputs.
Inputs are model-transcribed author claims, not verified circuit resources.
Chemistry never inherits that formula. The reproducer must remeasure candidate
resources through the actual task. Predicted cost alone must not kill a method.

A failed fetch records the exact URL/error and suggests public notebook source,
public dependencies and upstream code as recovery routes. It cannot establish a
blanket account requirement. Existing access boundaries stay enforced.

Kimi reads the packet and calls `record_scout_review`, citing original fetched
sources, corrections and the first test. A scout role cannot self-review.
Incomplete scout windows still preserve full durable state for reproduction;
they are visibly incomplete rather than silently counted as successful handoffs.
A deterministic 20% sample of jobs with rejected directions is marked for an
independent review within its existing budget. It does not launch extra sessions.
No-promising-direction is a legitimate checkpoint: record a sourced rejection,
uncertainty and next action; do not manufacture hypotheses to fill a form.

## Evaluation plan, registered before new results

Baseline snapshots are stored in each live task root as
`scout-quality-baseline.json`; active sessions are not restarted. New windows
adopt v2 at their next boundary, retaining budgets and drafts. The first review
is after six v2 scout checkpoints per benchmark, or after one daily budget ends
if fewer complete. Chemistry and DQI are evaluated separately.

Operational target: at least five of six scout checkpoints should contain a
complete, source-pinned packet **or an explicitly sourced negative conclusion**.
The dashboard's complete-packet counter does not include negative conclusions;
review those decisions separately. Check each packet against Kimi's review:
track incorrect assumptions, missing dependencies and corrections. Any fabricated
source claim or certification bypass blocks declaring operational success.

Measure useful distinct mechanisms, repeated unchanged packets, correction rate,
full official reproduction results, sealed exports and model time to those
outcomes. Report provider errors and fetch errors separately; wall elapsed time
includes queues. A larger number of fetched sources is not a success criterion.
Count source families, not repeated exports, when assessing diversity.

The legacy jobs were not instrumented for packets or reviewer outcomes. Missing
legacy fields mean **unknown**, not zero mistakes. Snapshots give descriptive
before/after evidence, not a randomized causal estimate. If throughput or quality
fails the target, inspect the actual packets and revise or revert the policy;
do not expand spending or weaken validation to meet a number. True research
benefit requires successful official reproduction or cheaper rejection of an
unsound direction supported by receipts, not merely complete paperwork.

Each completed research window refreshes `scout-quality-latest.json` in its task root; `review_due` becomes true after six instrumented scout checkpoints. This flags review, not proven benefit or automatic spending changes.

Generate a read-only report:

```sh
python -m scripts.autoresearch_seeder.scout_quality /absolute/task-research-root --output /absolute/report.json
```

The report separates legacy and v2 jobs, scout-created packets, independent review
corrections, provider failures and model seconds. Jobs upgraded in place can contain
legacy work, so their full lifetime totals must not be interpreted as v2-only cost.
No extra paid evaluation runs, budgets or campaign seed installations are enabled.
