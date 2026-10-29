# evolveTS rca_re1 vs published RCA frontiers (RCAEval RE1)

Protocol match: same 375 RE1 cases (OB/SS/TT x 5 faults x 5 reps x 5 services), official RCAEval
preprocessing + pinned Evaluator, service-level Avg@5, exact injection time (published t_delta=0 rows).
Published numbers: ASE 2024 "How Far Are We?" Table 5 (the benchmark paper, 21 methods; t_delta=0 rows).
No official RE1 leaderboard exists since; 2025-26 RCAEval-family papers (TORAI, EventADL, DecompRCA)
evaluate RE2/RE3 or decompositions, not RE1 rankings.

## Champion A: cycle-1 champion (dev 0.9787)
- Full 375: **Avg@5 0.9627** | AC@1 0.8987 | AC@3 0.9733 | AC@5 0.9920 | metric-level Avg@5 0.5947
- Held-out 300 (reps 2-5, never used for selection): **Avg@5 0.9587**

| system | cpu | mem | disk | delay | loss | mean | best published mean |
|---|---|---|---|---|---|---|---|
| ob | 0.960 | 1.000 | 1.000 | 1.000 | 0.800 | **0.952** | 0.906 (BARO) |
| ss | 1.000 | 1.000 | 1.000 | 0.992 | 0.944 | **0.987** | 0.956 (NSigma) |
| tt | 1.000 | 1.000 | 1.000 | 0.824 | 0.920 | **0.949** | 0.826 (BARO) |
| **overall** | | | | | | **0.9627** | 0.895 (BARO) |

- vs best published method per (system x fault) cell: wins **14/15**; below on: ob-cpu (0.960 vs 0.970)

## Champion B: cycle-2 champion, final (dev 0.9893)
- Full 375: **Avg@5 0.9637** | AC@1 0.8987 | AC@3 0.9733 | AC@5 0.9920 | metric-level Avg@5 0.5968
- Held-out 300 (reps 2-5, never used for selection): **Avg@5 0.9573**

| system | cpu | mem | disk | delay | loss | mean | best published mean |
|---|---|---|---|---|---|---|---|
| ob | 0.960 | 1.000 | 1.000 | 1.000 | 0.824 | **0.957** | 0.906 (BARO) |
| ss | 1.000 | 1.000 | 1.000 | 0.992 | 0.944 | **0.987** | 0.956 (NSigma) |
| tt | 1.000 | 1.000 | 1.000 | 0.816 | 0.920 | **0.947** | 0.826 (BARO) |
| **overall** | | | | | | **0.9637** | 0.895 (BARO) |

- vs best published method per (system x fault) cell: wins **14/15**; below on: ob-cpu (0.960 vs 0.970)

## Overall service-level Avg@5 on full RE1 (375 cases)

| method | OB | SS | TT | RE1 overall | runtime (ASE Tab.6) |
|---|---|---|---|---|---|
| BARO (published) | 0.906 | 0.954 | 0.826 | **0.895** | 0.01 s/case |
| NSigma (published) | 0.898 | 0.956 | 0.786 | **0.880** | 0.01 s/case |
| CIRCA (published) | 0.816 | 0.946 | 0.688 | **0.817** | 3792 s (TT) |
| CausalRCA (published) | 0.820 | 0.626 | 0.248 | **0.565** | 1326 s (TT) |
| RCD (published) | 0.634 | 0.510 | 0.122 | **0.422** | 12.4 s (TT) |
| Dummy (published) | 0.252 | 0.366 | 0.070 | **0.229** | - |
| evolveTS A (full 375) | 0.952 | 0.987 | 0.949 | **0.9627** | 15-20 s/case (sandboxed Docker, 1 thread) |
| evolveTS B (full 375) | 0.957 | 0.987 | 0.947 | **0.9637** | 15-20 s/case (sandboxed Docker, 1 thread) |
| evolveTS A (held-out 300) | 0.948 | 0.986 | 0.942 | **0.9587** | |
| evolveTS B (held-out 300) | 0.950 | 0.986 | 0.936 | **0.9573** | |

## Caveats
- Published RE1 tables report Avg@5 only (no per-method RE1 AC@1); our AC@1 is reported for completeness.
- Champions were selected on the 75-case dev split (rep 1); the held-out rows are the unbiased estimate.
- Both champions use a single fixed program (no per-system tuning); 120 s/case budget incl. container start.
- Remaining headroom for both champions: OB loss (~0.82) and TT delay (~0.82); all other cells are at or near 1.0.
