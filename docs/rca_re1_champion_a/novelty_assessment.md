# Novelty assessment — evolveTS champion A (rca_re1, cone-head origin)

Champion A = `history/iter001/explore_b0/attempt_00` (dev Avg@5 0.97867; full-375 0.9627;
held-out 0.9587; 1,034-line NumPy program). Direct ancestor of champion B (B = A + four
containment layers; see `../rca_re1_champion_b/`).

## 0. What it drew on

- Zero citations of published methods in the proposal or the code; the single occurrence
  of "Granger" (proposal §4) is an explicit *negation* ("no Granger test is computed").
- Explore agents are offline (file tools only); the discovering agent read the seed, the
  task text (`rca.txt` lists permitted families), and the campaign's own 109-proposal
  archive of cycle 0. Any similarity to published work is pretraining echo
  (MiniMax M3.1-Flash), not retrieval.

## 1. Mechanism-by-mechanism mapping

| # | Champion A mechanism | Closest published antecedent(s) | Verdict |
|---|---|---|---|
| 1 | Robust pre/post two-sample scoring (median/MAD z of shift + peak, per series) | **NSigma** (z-score pre/post) · **BARO**, FSE'24, arXiv:2405.09330 (median/IQR robust z) · **ε-Diagnosis** (two-sample tests) | **Rediscovery** of the benchmark's top-baseline family. |
| 2 | Per-family scales + persistence + monotone soft saturation | BARO family-aware preprocessing · CIRCA metric categories · change-detection dwell (BOCPD run-lengths) | Known families; saturation is an engineering detail. |
| 3 | Own-scale visibility (own-baseline normalization, 3σ floor) | BARO's counter-vs-utilization metric-type treatment; per-series baselining folklore | Known idea, crisp formulation. |
| 4 | Self-relative impact + **level-accumulation direction** (upstream member carries the smallest baseline; levels accumulate toward the SLI) | **varsortability** (Reisach et al., NeurIPS'21, arXiv:2102.13647): in linear SEMs marginal variance/level grows along the causal order — exposed there as a benchmark artifact, used here as an instrument · queueing additivity (`caller_latency = callee_latency + own_processing`) · classic fault-propagation/source reasoning (signed-digraph diagnosis in process control, FDI fault propagation) — those need a known topology; A infers direction from levels alone | **Novel as an instrument** for metric-based RCA: no published method orients by baseline-level accumulation without a topology or lag. |
| 5 | Confounder-adjusted direct-effect attribution (pre-window regression after stripping 3 leading principal common modes; explained/unexplained split; level-oriented driver filter) | Partial-correlation causal discovery (PC/FCI arms of the benchmark) · factor-model deconfounding (classical) · residual-vs-dependency-model attribution folklore | Known family; the specific common-mode stripping is a standard instrument. |
| 6 | Exclusive-cell origin (a change alone in its (family,direction) cell = local-fault fingerprint) | BARO metric-type insight; "own throughput falls while callers' latency rises" AIOps folklore | Known intuition; the cell-exclusivity formalization is new. |
| 7 | **Cone-head origin** (A's addition): cone = dominant (family,direction) cell spanning ≥3 services; **equal-shift near-tie verification** (≤4× median — "one perturbation handed on unchanged"); head = smallest baseline with ≥10% separation; dominance check keeps it out of resource faults | Fault-propagation "cone/source" reasoning (FDI, signed digraphs — topology given, not inferred) · co-movement clustering / correlation-based dependency graphs (CauseInfer, MonitorRank — adjacency, no level direction) · queueing composition for the level law | **Novel combination**: cone *verified by the equal-shift physical check*, oriented by the level law, with regime guards. No counterpart in the 21 ASE'24 baselines. |
| 8 | Bounded multiplicative promotion ×(1+0.7·w) with comparable-with-leader bound (≥25%), applied only when the exclusive-cell detector abstains | Conservative re-ranking safeguards; no published RCA analog found; weaker guarantee than B's set-preserving rotation (which the archive designed *after* measuring A's delivery failure modes) | Novel packaging, informal guarantee. |
| 9 | Service aggregation (max + 0.2·second) + interleaved emission | — | Benchmark-aware engineering. |

Explicitly avoided by design (and measured ≈ chance in ASE'24): graph/lag-based causal
discovery (Granger, PC/FCI, LiNGAM, fGES, NTLR ± PageRank/random walk), GNNs — consistent
with the 2026 controlled study (arXiv:2609.27069) finding no graph-specific effect on RCAEval.

## 2. Overall verdict

- **Not novel** (rows 1–3, 5): the BARO/NSigma/ε-Diagnosis scoring family plus standard
  residualization — the layer that solves cpu/mem/disk (all 45 dev cases at AC@1 = 1).
- **Novel as instruments/combination** (rows 4, 6, 7): orientation by level accumulation
  without topology or lags; the equal-shift-verified propagation cone with smallest-baseline
  head and regime guards. This is the layer that attacks the delay/loss ordering residual,
  which is exactly where A's measured edge over BARO lives (TT +0.12, OB loss +0.15 on full RE1).
- Row 8 (bounded promotion) is a pragmatic safeguard, later superseded inside the campaign by
  B's provably set-preserving rotation.
- **A vs B**: identical 14/15 cell wins; statistically tied on full RE1 (0.9627 vs 0.9637;
  held-out A ahead 0.9587 vs 0.9573). B's containment layers add +0.011 dev only. A is the
  more parsimonious artifact (1,034 vs 2,046 lines, no containment machinery).
- Confidence: high for the rediscovery rows; moderate for "no counterpart" on rows 4/6/7
  (asserted against the ASE'24 21-method study, its baselines' code, targeted arXiv
  searches and domain knowledge; absence cannot be proven).

## 3. Papers most similar to champion A

1. Pham, Ha, Zhang — *BARO*, FSE 2024 (arXiv:2405.09330): closest published system
   (robust pre/post scoring, SLI anchoring, metric-type awareness).
2. Pham, Ha, Zhang — *How Far Are We?*, ASE 2024 (arXiv:2408.13729): evaluation context;
   documents that CI-test/graph methods ≈ chance on this data.
3. Reisach, Seiler, Weichwald — *Beware of the Simulated DAG!*, NeurIPS 2021
   (arXiv:2102.13647): variance/level growth along causal order — the direction principle
   A's level law exploits.
4. Sun et al. — *ε-Diagnosis*: the two-sample family echoed by row 1.
5. CauseInfer / MonitorRank / MicroDiag / MS-Rank (metric-dependency graphs + walk):
   nearest graph framing; they infer adjacency, A infers *direction from levels*.
6. *Does Graph Structure Earn Its Place in Microservice RCA?* (arXiv:2609.27069, 2026):
   independently corroborates A's graph-free design.
7. Classic fault-propagation / signed-digraph diagnosis (process-control FDI lineage):
   the conceptual ancestor of "find the source of the propagation cone" — but with the
   topology *given*, whereas A reconstructs the cone from co-movement and levels alone.
