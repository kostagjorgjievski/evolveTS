# rca_re1 champion B — the method Dream-RSI developed

This directory documents the best program evolved by the `rca_re1` Dream-RSI campaign
(branch `rca`). It is a **research artifact added on this branch**; the fresh-start
statement in the root README (no discovered programs shipped) refers to `main`.

## Files

- **`program.py`** — the exact frozen champion program (2,046 lines, pure NumPy).
  SHA-256 `a6bf5b99ff9f5095f0f914d7a2a1b373089cdd2350a7e144159a3449764fbbc1`.
  The module docstring (first ~60 lines) is the pipeline summary; every stage is
  annotated in the code. Entry point: `rank(data, inject_time, metadata) -> list[str]`.
- **`proposal.md`** — the 451-line mechanism document written by the discovering agent:
  the measured history it relied on, the residual it targeted, the mechanism, the guards,
  and why each design decision is not a repeat of anything in the 313-proposal archive.
- **`novelty_assessment.md`** — mechanism-by-mechanism comparison against published
  methods (BARO, NSigma, ε-Diagnosis, CIRCA/RCD/CausalRCA/MicroCause, varsortability, …).
- **`frontier_comparison.md`** — full-RE1 results vs the published frontier.

## Provenance

- Campaign: `runs/rca_re1/{e0,dream_rsi}/20261023T161649Z-1715357`, backend
  MiniMax-M3.1-Flash via Claude Code, upstream Dream-RSI paper defaults
  (10 rounds, 10 branches × 11 attempts, 10 workers).
- Origin: `history/iter003/explore_b8/attempt_00` (cycle 4 exploration seed of the
  cycle-3 champion lineage); evaluated unchanged through the frozen final-eval path.
- Lineage (development split, 75 cases, official service-level Avg@5):
  seed 0.3840 → iter000 b6/a06 **0.9733** (own-scale visibility + upstream demotion +
  exclusive-cell origin) → iter001 **0.9787** (cone-head origin) → iter002 b6/a01
  **0.98933** (containment-anchored arbitration + certified rotation) →
  iter003 b8/a00 (whole-wave containment source; champion B, kept 0.98933).

## Results (official RCAEval RE1, service level)

| Scope | Avg@5 | AC@1 | AC@5 | metric Avg@5 |
|---|---|---|---|---|
| Development 75 | 0.98933 | 0.960 | 1.000 | 0.616 |
| Full 375 | **0.9637** | 0.899 | 0.992 | 0.597 |
| Held-out 300 (reps 2–5) | **0.9573** | 0.883 | — | — |

Published frontier on the same 375 cases: BARO 0.895. Champion B beats the best
published method in 14/15 (system × fault) cells; see `frontier_comparison.md`.

## Reproducing the evaluation

```bash
HASH=$(sha256sum docs/rca_re1_champion_b/program.py | cut -d ' ' -f 1)
.rca-venv/bin/python tasks/rca_re1/evaluate_cli.py \
  --program docs/rca_re1_champion_b/program.py \
  --test --full --frozen-sha256 "$HASH" --output /tmp/fresh-output-dir
```

Requires `bash tasks/rca_re1/setup.sh` first (pinned data + worker image).
Budget: 120 s/case, 1 thread, 8 GiB, offline.
