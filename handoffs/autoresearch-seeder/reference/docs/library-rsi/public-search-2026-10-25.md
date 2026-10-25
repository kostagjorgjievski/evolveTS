# Public search and seed candidates — 25 October 2026

Research notes only. No active worker prompt, seed, algorithm, or library registry was changed. The blind MiniMax acceptance test remains isolated.

## Evidence boundary

Exact searches for 8.95303, invsqrt 13.1573, DQI 16.5807, and dfthcsos 3.2896 found no indexed source. Those numbers remain screenshot claims, not reproduced artifacts or verified leaderboard results. Direct Kaggle browser access was denied by a saved permission setting; this search used indexed results and accessible external primary sources without bypassing that restriction.

The indexed Kaggle notebook directory lists compact arithmetic/banked QROM, direct polynomial phasing, and signed-digit memory notebooks. Titles do not establish implementations, compatibility, or scores. Source: https://www.kaggle.com/code/

## Comparison with our frozen verified results

| Task | Our improvement factor | Screenshot factor | Extra cost reduction from our result to screenshot |
|---|---:|---:|---:|
| invsqrt | Baseline 1 assumed for combination | 13.1573 | 92.40% |
| DQI | 13.774092377870447 | 16.5807 | 16.93% |
| chemistry | 1.0667681987449842 | 3.2896 | 67.57% |

Our combined estimate with baseline invsqrt is 2.449313. Matching only the screenshot chemistry gives 3.565075. Matching its invsqrt and chemistry while retaining our DQI gives 8.416360. This is arithmetic, not a new submission evaluation.

## Primary sources worth testing

1. Motlagh and Pocrnic, **Halving the cost of QROM** (May 2026): https://arxiv.org/abs/2605.20334 . SelectCopy and sequential bit packets reduce repeated table passes using dirty workspace. Candidate chemistry mechanism; no task-specific gain established. Cheapest test: a small table, all addresses, arbitrary target words, both directions, clean workspace and phase; then measure exact qubits and gates against unary iteration under the 128-qubit cap.

2. Motlagh, **Halving the cost of QROM again via dense encoding** (October 2026): https://arxiv.org/html/2610.02321v1 . Strong headline savings, but its selected-bit read uses Hadamard gates. Compatibility warning: kickmix does not supply unrestricted coherent Hadamards. A compatible equivalent must be established before treating this as an implementable seed. Do not assume its leading-term reduction applies to our total chemistry cost.

3. Low et al., **Fast quantum simulation of electronic structure by spectrum amplification**, Physical Review X 15, 041016 (2025): https://arxiv.org/abs/2502.15882 . Foundational chemistry factorization source. Test numerical representation changes separately from circuit lookup changes, then evaluate the full official objective. This source is not a newly discovered competition solution.

4. Gu et al., **Discovering state-of-the-art quantum circuits with large language models**, released code: https://github.com/andigu/uncompute . Existing DQI family source, not independent evidence of a new approach. Its chemistry benchmark is Fe2S2, not our FeMoCo DFTHC-SOS problem; its reported chemistry gain cannot be transplanted numerically.

5. Authors' Coulomb circuit explanation: https://andigu.github.io/projects/uncompute/coulomb-potential.html . Table-based approximation and measurement-based unlookup are useful invsqrt design references. Its coordinate-to-accumulator contract differs from our phase oracle; conversion requires new approximation/error analysis and official validation.

## Priority

First obtain the screenshot's original notebook URL and immutable code/version. Reproduce its invsqrt and chemistry artifacts separately before considering a new frozen campaign seed. In parallel, the sequential-packet QROM paper is a concrete source for a small compatibility experiment. Keep dense encoding behind a gate-set compatibility check. Do not copy the Fe2S2 headline gain into our score forecast.
