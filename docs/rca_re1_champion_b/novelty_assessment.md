# Novelty assessment — evolveTS champion B (rca_re1)

Champion B = `history/iter003/explore_b8/attempt_00` (dev Avg@5 0.98933; full-375 0.9637;
held-out 0.9573; 2,046-line NumPy program). Lineage: seed 0.384 → iter000 b6/a06 0.9733 →
iter001 cone-head 0.9787 → iter002 b6/a01 0.98933 → iter003 b8/a00 (champion B).

## 0. What it actually drew on

- Zero citations of any published method anywhere in the lineage's proposals or code
  (grep over the four lineage proposals + program: no method names, no "et al.", no arXiv).
- Explore agents are offline (file tools only; no shell/network); transcripts show reads of
  workspace files only. Inputs were: the seed program, `rca.txt` (which lists permitted
  families: "statistical, causal-discovery, graph, residual, correlation, ... neural"), and the
  campaign's own measured archive (up to 313 proposals).
- So any similarity to published methods is pretraining echo (MiniMax M3.1 Flash), not retrieval.
  The comparison below maps every mechanism to its closest published antecedent.

## 1. Mechanism-by-mechanism mapping

| # | Champion B mechanism | Closest published antecedent(s) | Verdict |
|---|---|---|---|
| 1 | Robust pre/post two-sample change scoring: median/MAD(+IQR) z of shift and peak, per series | **NSigma** (z-score pre/post, max; benchmark impl = StandardScaler z) · **BARO**, FSE'24, arXiv:2405.09330 (RobustScaler = median/IQR z; BOCPD front end) · **ε-Diagnosis** (Sun et al., two-sample ε-statistics) | **Rediscovery.** Near-identical family to the benchmark's top baselines; almost certainly pretraining echo (and the seed itself was a MAD-z). |
| 2 | Per-family scales (cpu/mem/latency/error) + persistence (fraction of post-rows beyond p05/p95) + monotone soft saturation | BARO's family-aware `preprocess` (mem-unit conversion, near-constant drops) · CIRCA (metric-category mapping) · change-detection dwell/run-length (BOCPD) | Known families; order-preserving saturation is an engineering detail. |
| 3 | Own-scale visibility: judge each series against its own baseline (floor = 3 robust σ) | BARO's counter-vs-utilization metric-type analysis (per-type normalization); per-series baselining folklore in AIOps | Known idea (self-relative change), crisp formulation. |
| 4 | Confounder-adjusted direct-effect attribution: pre-window driver regression, strip leading PCs of the healthy window (shared load), split incident shift into explained/unexplained | Partial-correlation causal discovery (PC/FCI arms of the benchmark) · factor-model deconfounding (classical) · residual-vs-dependency-model attribution (dependency-graph RCA folklore; cf. CauseInfer's stage-2 regression) | Known family (linear adjustment + residual); the specific common-mode stripping is a standard instrument. |
| 5 | **Containment identity (the core):** in raw healthy units, `gain(X|Y)=cov(X,Y)/var(Y) ∈ [0.85,1.6]`, `var(X) ≥ 1.1·var(Y)`, corr/sign gates → direction = variance/level accumulates downstream | (a) **varsortability** — Reisach et al., NeurIPS'21, arXiv:2102.13647: in linear SEMs with comparable noise scales, marginal variance grows along the causal order (they exposed it as a benchmark artifact; B *uses* it as an instrument on real telemetry) · (b) unit-gain transfer = flow conservation/queueing accumulation along call chains (variance of a sum ≥ parts) · (c) additive-noise cause-effect asymmetry (Hoyer et al. '09): direction from distributional asymmetry, different instrument · (d) metric-dependency graphs + random walk/PageRank (MicroDiag, MS-Rank, MicroRank, MonitorRank, CauseInfer) — adjacency + centrality, *no* variance-direction, and they rank by centrality, not chain source | **Novel as an instrument and combination.** No published RCA method orients edges by unit-gain + variance accumulation, closes the relation transitively over the incident wave, and reads the chain *source* (minimal element of the reachability poset) instead of a centrality score. |
| 6 | Whole-wave transitive closure + source selection; abstain on flat hierarchy | Graph reachability/poset minimal elements (classical); vs PageRank/random-walk root finding (CausalRCA, RUN, MicroDiag, MicroRank) | Novel application (source-of-closure replaces centrality). |
| 7 | Exclusive-cell origin / magnitude-free private-cell veto: a change alone in its (family, direction) cell = local fault fingerprint; network fault site shows counter-directional own trace | BARO's counter-vs-utilization insight; AIOps folklore "fault site's throughput falls while callers' latency rises"; direction-flip fingerprints in multi-source voting (PDiagnose) | Known intuition; the (family,direction)-cell exclusivity test is a crisp novel formalization. |
| 8 | Cone-head origin / level law (upstream member carries the smallest baseline) | Same variance/level-accumulation principle as (5); no direct published RCA analog found | Novel packaging of a known principle. |
| 9 | Set-preserving rotation delivery: worst-case cost bounded by construction (AC@3/AC@5 invariant), never demote, contender floor, abstention | Conservative/off-policy safeguards in RL; top-k stability constraints in ranking; no published RCA method formalizes metric-aware safe promotion | **Novel packaging** (decision-theoretic safeguard aware of Avg@5's (6−r)/5 payoff). |
| 10 | Service aggregation (max + 0.2·second) + interleaved emission so official first-occurrence dedup reproduces the intended order | — | Engineering, benchmark-aware; not a methodological claim. |

## 2. Corroborating evidence for the split verdict

- The base scoring layer (rows 1–4) is where B overlaps published work — and it is exactly the
  layer that solves cpu/mem/disk (all 45 dev cases at AC@1 = 1.0), which BARO/NSigma already
  largely solve (0.88–0.99 per cell).
- B's *measured* advantage over BARO is concentrated in delay/loss cells (TT +0.12, OB loss
  +0.15), i.e. precisely the ordering-of-the-propagation-chain problem that the novel core
  (rows 5–9) addresses — consistent with the delta being the novel part.
- Independent convergence signal: a 2026 controlled study (arXiv:2609.27069) finds no reliable
  graph-specific effect on RCAEval (flat robust features match GNN arms). Champion B is a flat,
  graph-free method — same conclusion, reached by measurement inside the campaign.

## 3. Overall verdict

- **Not novel:** robust two-sampler scoring, family normalization, persistence, regression
  residualization (the BARO/NSigma/ε-Diagnosis/PC families).
- **Novel as instruments and as a combination:** (i) the raw-unit unit-gain containment identity
  with variance/level-accumulation direction, transitively closed over the whole incident wave,
  with source-of-chain readout; (ii) the magnitude-free (family,direction)-cell exclusivity
  tests; (iii) the set-preserving, worst-case-bounded promotion delivery. No counterpart was
  found in the benchmark's own 21-method study (ASE'24), its baselines' code, or targeted
  searches (varsortability, BARO, dependency-graph walk methods, 2025–26 RCAEval follow-ups).
- **Confidence:** high for rows 1–4 (rediscovery); moderate for "no counterpart" on rows 5–9 —
  absence of a similar paper cannot be proven, only asserted against the searched literature
  (ASE'24 study + its 21 baselines, arXiv searches, domain knowledge).

## 4. Papers most similar to champion B

1. Pham, Ha, Zhang — *BARO: Robust Root Cause Analysis for Microservices via Multivariate
   Bayesian Online Change Point Detection*, FSE 2024 (arXiv:2405.09330). Closest published
   *system*: robust pre/post comparison, SLI anchoring, metric-type awareness. B ≈ BARO's base
   layer + novel orientation/delivery layers (+0.069 Avg@5 over BARO on full RE1).
2. Pham, Ha, Zhang — *Root Cause Analysis for Microservice Systems based on Causal Inference:
   How Far Are We?*, ASE 2024 (arXiv:2408.13729). The 21-method evaluation B is measured
   against; also documents that CI-test/graph methods ≈ chance here.
3. Reisach, Seiler, Weichwald — *Beware of the Simulated DAG!*, NeurIPS 2021
   (arXiv:2102.13647). varsortability: variance grows along the causal order in linear SEMs —
   the general principle B's containment identity exploits deliberately.
4. Sun et al. — *ε-Diagnosis* (two-sample testing for small-window localization): the
   pre/post two-sample family B's row-1 layer echoes.
5. Ma et al. — *CIRCA* (IWQoS 2021); Ikram et al. — *RCD* (2022); Li et al. — *CausalRCA*
   (2022); Wu et al. — *MicroCause* (IWQoS 2020); and the PC/FCI/Granger/LiNGAM+fGES+NTLR
   PageRank/random-walk arms — the causal-graph family B *deliberately avoids* after the
   archive measured L6 ("contemporaneous dependence is direction-blind").
6. *Does Graph Structure Earn Its Place in Microservice Root-Cause Analysis?* (arXiv:2609.27069,
   2026) — independently corroborates B's graph-free design choice on RCAEval.
7. Dependency-graph walk lineage (MicroDiag, MS-Rank, MonitorRank, CauseInfer): metric
   dependency + centrality — the closest published *graph* framing, against which B's
   source-of-poset readout is the differing instrument.
