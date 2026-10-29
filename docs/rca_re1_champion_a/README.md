# rca_re1 champion A — cone-head origin attribution

The cycle-2 champion of the `rca_re1` Dream-RSI campaign (branch `rca`), and the
**direct ancestor of champion B** (`docs/rca_re1_champion_b/`): B = A + four
containment-based delivery layers. Research artifact added on this branch only.

## Files

- **`program.py`** — the exact frozen champion program (1,034 lines, pure NumPy).
  SHA-256 `8a75bc726123b9ebc1ca2158d4f8488e1b268bdce4de294176051c0ddb1d89ad`.
  Entry point: `rank(data, inject_time, metadata) -> list[str]`.
- **`proposal.md`** — the 294-line mechanism document written by the discovering
  agent (measured archive survey, residual analysis, the cone-head rule, guards,
  delivery rationale, anti-repeat table, risk register).
- **`novelty_assessment.md`** — mechanism-by-mechanism comparison to published work.

## Provenance

- Campaign: `runs/rca_re1/{e0,dream_rsi}/20261023T161649Z-1715357`, MiniMax-M3.1-Flash
  via Claude Code, upstream Dream-RSI paper defaults.
- Origin: `history/iter001/explore_b0/attempt_00`, evaluated unchanged through the
  frozen final-eval path.
- Lineage: seed 0.3840 → iter000 `b6/a06` **0.9733** (own-scale visibility,
  confounder-adjusted attribution, exclusive-cell origin, level-oriented upstream
  demotion) → **A (this program) 0.97867** = that base + **cone-head origin**.

## Pipeline (top to bottom)

1. **Split** at `inject_time` (60/40 fallback for degenerate windows).
2. **Per-family robust scales** (cpu / mem / latency / error …) from the healthy window.
3. **Robust change statistics**: median/MAD z of the median shift and peak excursion,
   family-relative shift, persistence (share of post-rows beyond p05/p95), monotone
   soft saturation → per-metric magnitude.
4. **Own-scale visibility**: each series also judged against its own baseline
   (floor = 3 robust σ) so small services are visible.
5. **Self-relative impact**: chain members shift by the same absolute amount; levels
   accumulate downstream, so the fault site has the smallest baseline → largest
   change relative to its own level (tie-break toward the origin).
6. **Confounder-adjusted direct-effect attribution**: healthy-window driver regression
   after removing the 3 leading principal common modes; each incident shift is split
   into driver-explained vs unexplained; level-oriented driver filter.
7. **Peer isolation + SLI co-movement** terms.
8. **Origin detection**, in priority order:
   a. **Exclusive-cell origin** — a change alone in its (family, direction) cell is a
      local fault's private fingerprint (fires on resource faults);
   b. **Cone-head origin** (A's addition; fires only if (a) abstains) — the
      propagation regime: the affected (family, direction) cell spanning ≥3 services
      **is** the propagation cone; members must be near-tied in absolute shift
      (≤4× median — "one perturbation handed on unchanged"); the head is the member
      with the **smallest healthy baseline** (level-accumulation law), accepted only
      with a ≥10 % gap to the runner-up; a dominance check (top affected metric must
      be inside the cone) keeps the rule out of resource faults.
9. **Delivery**: bounded multiplicative promotion of the head's service score,
   ×(1 + 0.7·w), only if the head already holds ≥25 % of the leader's score
   (cannot leapfrog, protects AC@5); plus the inherited level-oriented upstream
   demotion.
10. **Aggregation**: service score = max + 0.2·second metric; interleaved emission so
    the official first-occurrence dedup reproduces the intended service order.

## Results (official RCAEval RE1, service level)

| Scope | Avg@5 | AC@1 | AC@5 | metric Avg@5 |
|---|---|---|---|---|
| Development 75 | 0.97867 | 0.920 | 1.000 | 0.605 |
| Full 375 | **0.9627** | 0.899 | 0.992 | 0.595 |
| Held-out 300 (reps 2–5) | **0.9587** | 0.893 | 0.990 | 0.591 |

Published frontier (BARO, ASE'24): 0.895. A beats the best published method in 14/15
(system × fault) cells — identical win profile to B; see
`../rca_re1_champion_b/frontier_comparison.md`.

**A vs B**: on the full 375 the two are statistically tied (0.9627 vs 0.9637; held-out
0.9587 vs 0.9573 — A marginally ahead). B's containment layers buy +0.011 on the
development split only. A is the simpler program (1,034 vs 2,046 lines) and contains
no containment machinery at all — the parsimonious choice at equal held-out quality.

## Reproducing the evaluation

```bash
HASH=$(sha256sum docs/rca_re1_champion_a/program.py | cut -d ' ' -f 1)
.rca-venv/bin/python tasks/rca_re1/evaluate_cli.py \
  --program docs/rca_re1_champion_a/program.py \
  --test --full --frozen-sha256 "$HASH" --output /tmp/fresh-output-dir
```

Requires `bash tasks/rca_re1/setup.sh` first. Budget: 120 s/case, 1 thread, 8 GiB, offline.
