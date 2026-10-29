# Proposal — the **whole-wave containment source**: resolve the leader's own chain over the *entire* wave, read its source, and deliver it with a set-preserving rotation

**Base.** `history/iter002/explore_b6/attempt_01/artifact/program.py` — the **measured-best program
in the whole archive** (**0.98933** service-level `Avg@5` on the 75 development cases).
Everything inherited is kept **byte-identical**; one new block is added; **not one inherited
constant is changed**.

---

## 1. The history I read, and what it measures

### 1.1 Scope of the reading — stated honestly

The linked archive holds **180 completed proposals** in three cycles (`history/iter000`: 109
proposals over ten branches; `history/iter001`: 38 over nine branches; `history/iter002`: 33 over
eight branches). Recursive search does not descend the archive's directory symlinks, so every path
was taken from the resolved index `attempt_00/agent_log/history-files.md`.

* I read the **measured result of every one of the 180 archived attempts** — the
  `combined_score` header of each `eval/score.json` — and the **full 75-row per-case body** of
  the score files of the champion branch and of the attempts whose residual this proposal quotes.
  **Where a proposal's account of itself disagrees with its score file, the score file wins.**
* I read the **complete mechanism inventory of all 180 archived proposals** — the heading line of
  every archived `proposal.md`, extracted from the archived files themselves — together with every
  archived score. This inventory is what §3 compares against.
* I read **in full**: this branch's `problem.txt`, `baseline/{proposal.md, artifact/program.py,
  eval/score.json}`; the complete `artifact/program.py` of the champion
  (`history/iter002/explore_b6/attempt_01`); and the proposals of
  `history/iter002/explore_b6/attempt_01`, `_05`, `_06`, `history/iter002/explore_b8/attempt_00`,
  `history/iter002/explore_b3/attempt_00`.
* I did **not** read all 180 proposal bodies word for word. The inventory over them is complete,
  and the proposals I did read each carry their own "why this is not a repeat" table over the
  whole archive, so the cross-branch mechanism space is covered from both directions. I say this
  plainly rather than claim otherwise.
* The three `error.txt` files of the first cycle and the four of the second/third were read: five
  archived attempts died of a **one-character `SyntaxError`** at import (score 0), one produced no
  proposal, and the rest died of harness overflow. **A one-character slip is worth the entire
  candidate**, which is why the submitted file was written out in full and read back region by
  region (§5.4).

### 1.2 The measured ladder (development split, 75 cases; objective = service-level `Avg@5`)

`Avg@5_service = mean(AC@1…AC@5)` with `AC@k = 1[rank ≤ k]`, so a cause at service rank *r*
scores `(6−r)/5` and a case pays out in uniform 0.2 steps.

| cycle / branch | best measured program | score |
|---|---|---|
| iter000 `b6` | own-scale change visibility + level-oriented upstream demotion + exclusive-cell origin | **0.9733** |
| iter000 `b1` | change-family attribution + pass-through depth + **rotation** delivery | 0.9413 |
| iter000 `b8` | effect size + pre-fault novelty + change-point ancestor attribution | 0.9413 |
| iter000 `b4` | single-source wave model selection + direct-channel provenance | 0.9360 |
| iter000 `b3` | calibrated two-sample change + relative-change attribution | 0.8613 |
| iter000 `b5` | scale-free locality + continuous evidence + causal attribution | 0.8320 |
| iter000 `b2` | local-contrast relative shift | 0.8053 |
| iter000 `b9` | family locality + ownership of the unexplained deviation | 0.7733 |
| iter000 `b0` | containment-flow root detection | 0.7333 |
| iter000 `b7` | propagation containment | 0.7333 |
| iter001 `b0` | **cone-head origin** | **0.97867** |
| iter001 `b2` | **containment-explained symptom demotion** / joint wave-source fit | **0.97867** |
| iter001 `b1` | unexplained-family ownership | 0.9760 |
| iter001 `b4` | the precedent deficit | 0.9760 |
| iter001 `b8` | crowd-relative dependence | 0.9760 |
| iter002 `b6/a01` | **+ containment-anchored arbitration, + certified rotation** | **0.98933** |
| iter002 `b6/a04`, `b6/a05`, `b6/a06` | + quiet fault site / leader-anchored chain / shared-trace origin | 0.98933 (inert) |
| iter002 `b6/a02` | + certified self-failure origin, wave-family fallback | 0.98667 (**−0.00267**) |
| iter002 `b8/a00` | upstream-carrier rotation (chain root, leading-five delivery) | 0.97333 (on a 0.97867 base: **−0.0053**) |
| iter002 `b3/a00` | the uninherited head | 0.984 (inert) |
| — | seed `baseline` | `max|post − median(pre)| / (1.4826·MAD(pre))` | **0.3840** |

**The archive's ceiling is 0.98933 and it was reached by exactly one mechanism family**: the raw-unit
containment identity used *inside the leading group*.

### 1.3 The residual of the champion, read off its own per-case rows

`history/iter002/explore_b6/attempt_01/eval/score.json`:
`AC@1_service = 0.9600` (72 of 75 at rank 1), `AC@3_service = 1.000`, `AC@5_service = 1.000`,
`Avg@5_service = 0.98933`, `Avg@5_metric = 0.616`.

**74.2 of 75 case-points are earned; 0.8 points are lost across exactly three cases** (identical in
`b6/a06`'s score file):

| case | system | fault | window | AC@1 | AC@3 | AC@5 | Avg@5 | ⇒ rank of the true service |
|---|---|---|---|---|---|---|---|---|
| `dev-315e24b9921bc3b7` | ob | loss | **600 rows** | 0 | 1 | 1 | 0.6 | **3** |
| `dev-18392340d0259140` | ss | loss | 721 | 0 | 1 | 1 | 0.8 | **2** |
| `dev-2e28415fe63c9ea1` | tt | delay | 721 | 0 | 1 | 1 | 0.8 | **2** |

Five facts define the whole opportunity.

1. **The residual is 100 % `delay`/`loss`.** All 45 `cpu`/`mem`/`disk` cases are at
   `AC@1_service = 1`; they are 60 % of the split and are the dominant downside risk.
2. **It is purely an *ordering* loss.** `AC@3 = AC@5 = 1.000`: the true service is inside the
   leading **three** services of *every* development case. It is simply not first, and the
   competitor at rank 1 is always a **victim** of the same propagation.
3. **The whole prize is 0.8 case-points = 0.0107 of the objective**, and a wrong decision that
   displaces a correct leader costs 0.2 of one case = 0.0027 — a *quarter* of the prize. The
   intervention must therefore be set-preserving or nothing.
4. `dev-315e24b9921bc3b7` has a window of exactly **600 rows**, i.e. no post-incident rows at all
   (its "post" half is the 60/40 fallback split of the whole window), so the incident is not
   visible in it. I do **not** count that case.
5. The **two reachable** residual cases have the cause at **rank 2** — one position from the top.

### 1.4 The measured lessons of the archive that this attempt obeys

Each is a **measurement** quoted from the archive's own score files and proposals.

* **L1 — "a bounded causal factor cannot cross a magnitude gap."** (`b6/a10`, `b8/a04`, `b9/a08`.)
  The causal factor of the leading programmes spans ≈2.33×, while a propagated symptom routinely
  exceeds the cause's normalised change by 4–5×. *⇒ the delivery must be a **permutation**.*
* **L2 — "a conjunction of rare preconditions produces inertness, not robustness."** Measured at
  least ten times. *⇒ a gate must be satisfiable in the regime the mechanism is built for; the
  failure mode of inertness is no change, the failure mode of a *relaxed* gate is damage.*
* **L3 — "within-incident timing is anti-correlated with causality on this data."** `b8/a03`
  collapsed to **0.3200** because of it. *⇒ no timing channel.*
* **L4 — "a placement that is not confined to the group it reasoned about is destructive."**
  `b6/a09` (0.9733 → **0.9280**) broke ≈20 already-perfect cases. *⇒ every intervention must be a
  permutation of a fixed leading set.*
* **L5 — "demotion is dangerous."** `b8/a02`'s peer factor broke six solved cases; `b2/a04`'s
  change-point demotion lost 0.077; `b1/a07`'s victim veto cost 2.1 points. *⇒ nothing is demoted
  here; services are only moved.*
* **L6 — "contemporaneous dependence is direction-blind."** For a linear chain `X → A → B` the
  covariance matrix is identical for every orientation, so seven instruments built on that family
  plateaued at 0.92. The **only** orientation that ever survived measurement is the **composition
  law**: along a call chain the observable of a caller *contains* the observable of the callee, so
  in the **raw units** of the healthy window `gain(X|Y) = cov(X,Y)/var(Y) ≈ 1` and `var(X) >
  var(Y)`. *⇒ the raw-unit containment identity is the instrument to build on.*
* **L7 — "the delivery, not the detection, is where the points are lost, and the safe delivery is
  a *set-preserving* one."** An *exchange* sent a correct rank-1 answer down to rank 3, costing
  0.4 per case; a **rotation** costs 0.2 and keeps the top-five *set* invariant. *⇒ rotation,
  always.*
* **L8 — "a magnitude criterion is not a criterion."** The archive tried the private-signature veto
  three times with a magnitude and measured it **not to fire** on a saturated resource metric
  (a metric that saturates at 90 % moves by ≈11 % of its own baseline) — which is exactly the
  `tt`/`disk` case that a rotation broke. The repair that worked was the **magnitude free**
  isolation test ("does the leader own a change *alone* in its `(family, direction)` cell?").
  *⇒ the veto used here is magnitude free.*

---

## 2. The defect this attempt repairs, located in the champion's **code**

The champion has exactly **two** delivery mechanisms, and both are *scope limited*:

```python
# artifact/program.py, the arbitration (measured +0.0053 on its own)
sink = _containment_sink(P, shift, suffix, svc, cmask2, ordered)
#   -> inside _containment_sink:  cand = [s for s in top if s in by_svc]
#      with  top = list(ordered[:_CA_TOP])      # _CA_TOP = 3
#   -> the edges are computed ONLY between services of `cand`, i.e. only
#      between the leading three services.

# artifact/program.py, the certified rotation (measured +0.0053 on its own)
if _containment_reaches(P, shift, suffix, svc, cmask3, ordered,
                        lead, cand, _ROT_CA_TOP):   # _ROT_CA_TOP = 8
    ordered = _rotate_within(ordered, cand, _ROT_TOP)
#   -> the edges are computed over  group = list(ordered[:8])
```

Both mechanisms are the **right** instrument (they are the only two that ever moved the residual,
and they are the only ones that ever produced a *gain*), but they can only see a containment
relation whose **endpoints and intermediate members all lie inside a window of three or eight
services**.

A propagation chain does not respect that window. The affected set of a `tt` case has 64
services and the chain that carries the fault's perturbation to the leader may run through
members that are *not* among the eight loudest. When that happens:

* the arbitration cannot certify the leader as a descendant of the fault site, because the
  *path* is invisible to it (it only ever tests pairs inside the leading three); and
* the certified rotation cannot certify it either, because its reachability closure is computed
  over the leading eight and the intermediate member is outside that window.

The consequence is exactly the shape of the residual: the champion **sees** the cause — it is
inside the leading three of every development case — but it cannot *prove* that the leader is a
victim of it, so the cause stays at rank 2 or 3 behind a victim.

**The fix.** Resolve the leader's chain over the **whole wave**, not over a window of three or
eight services; read the **source** of that chain; deliver it with the champion's own
set-preserving rotation.

---

## 3. The mechanism

Everything the champion does is inherited **unchanged**: the split, the family scales, the robust
statistics, the monotone soft saturations, the persistence factor, the self-relative impact, the
own-scale change visibility, the confounder-adjusted direct-effect attribution, the level-oriented
driver filter, the peer isolation, the SLI co-movement, the exclusive-cell origin *detector*, the
level-oriented upstream demotion, the cone-head origin, the containment-explained symptom
demotion, the containment-anchored arbitration, the certified rotation of the detected origin, the
service aggregation and the interleaved metric emission. **Not one inherited constant is changed**,
and every inherited block keeps its behaviour byte-for-byte.

**One block is added**, applied after the two inherited deliveries.

### 3.1 The object: the **whole wave**

The **wave** is the set of services that carry the **leader's own channel** — the metric family
of the leader's loudest changed metric (by absolute incident shift). This is the channel in which
the leader is a victim, and it is the channel in which the fault's perturbation travels.

The wave is *not* the leading group. In a `tt` case it can hold dozens of services; in an `ob`
case a handful.

### 3.2 The relation: the raw-unit containment identity, over the wave

The relation is the champion's own, with one widened tolerance:

```
gain(X | Y) = cov(X, Y) / var(Y)  in  [0.85, 1.60]     (X contains Y)
var(X) >= 1.10 * var(Y)                                (X is the accumulator)
|corr(X, Y)| >= 0.30
sign(shift_X) == sign(shift_Y)
|shift_X - gain * shift_Y| <= _WC_FIT * (|shift_X| + |gain * shift_Y|)   (wave-fit)
```

Two deliberate differences from the inherited `_containment_edges`:

* **the group is the whole wave**, not the leading three or eight — this is the fix;
* **`_WC_FIT = 0.60` instead of the inherited `_CA_FIT = 0.35`**: a container may accumulate the
  contained change from *several* branches, or add its own delay, so its observed shift may
  legitimately be two or three times the contained one. The inherited tolerance admits only a
  one-to-one reproduction.

Everything else — the gain band, the variance ratio, the correlation floor, the sign agreement,
and the requirement that *both* endpoints changed — is the inherited criterion.

### 3.3 The question: the **source** of the leader's chain

The relation is closed transitively over the wave, and the services the leader *transitively
contains* are read off that closure:

```
desc  = { Y in wave : (leader, Y) in reach }        # leader contains Y
srcs  = { Y in desc : Y contains no other member of desc }
```

`srcs` are the **sources** of the leader's chain — the upstream end of it. Under the physical
picture (a network fault hands one perturbation along the request path, every service above it
inherits it unchanged) the source of the leader's chain is the fault site, provided the fault
site's own harm-family metric moved.

If `srcs` has more than one member, the **level law** — the archive's only validated orientation
principle (L6/`b6/a03`) — breaks the tie (the upstream member of a chain carries the smaller
baseline), and a **flat** hierarchy abstains (a flat hierarchy carries no order).

### 3.4 The two guards that decide whether anything is delivered

* **G1 — the magnitude-free private-cell veto.** The leader must own **no** changed metric that
  lies **alone** in its `(metric family, direction)` cell of the affected set. A propagated
  symptom is a change that many services share; a *local* fault leaves a change alone in its
  cell, and the fault site of a resource fault always does. So a leader that owns such a change
  is the origin of a local fault and is **never displaced**. This is the *magnitude free* form of
  the champion's `_leader_private_signature`, and it is the repair the archive measured to be
  necessary (L8): the magnitude-gated version does not fire on a saturated resource metric, which
  is the case a rotation is known to break.
* **G2 — the source must show a trace of its own.** A *pure* victim of the propagation carries only
  the shared wave. The fault site carries something the wave cannot explain: its own counter
  falling (or stalling) in another metric family. So the source must own at least one changed
  metric **outside** the wave family whose `(family, direction)` cell holds at most
  `_WC_CELL_MAX = 3` services. The allowance of three services is deliberate: the archive
  measured that in the `loss` regime the fault site's own trace is *shared with the services it
  calls*, so a test that demanded a private trace would be inert exactly where the residual lives;
  what the test forbids is a trace the *whole wave* shares, which would make it vacuous.

### 3.5 The delivery

The source is moved to the front of the leading group by the champion's **set-preserving
rotation**, confined to the leading three services:

```python
ordered = [cand] + ordered[:pos] + ordered[pos + 1:]     # pos in {1, 2}
```

Every service that was above the source moves down by **exactly one** position and every other
service keeps its place, so the **set** of the leading three — and therefore of the leading five —
is invariant: `AC@3` and `AC@5` cannot be lost by construction, and a wrong decision costs the
leader **exactly one position** (0.2 of one case).

The **contender floor** is the champion's own `_ROT_MIN_REL = 0.10`: the source must already carry
at least a tenth of the leader's aggregated score, so a distant service is never lifted into the
leading group.

### 3.6 Where the block runs

It runs **only where both inherited deliveries abstained** (`ordered == ordered_base`, the order
as it stood before any rotation). It therefore can never fight the inherited arbitration or the
inherited certified rotation, and it fires only in the regime where the champion is blind.

---

## 4. Why this is not a repeat, a rename, or a parameter sweep

| programme | how the origin is named | what orients it | what certifies the victim | delivery | measured |
|---|---|---|---|---|---|
| `b6/a06` (iter000) | a change **alone** in its `(family, direction)` cell | the isolation of the cell | — | bounded ×1.5 | 0.9733 |
| `b0/a00` (iter001) | the **cone head** = smallest baseline in the **global** dominant cell | the level law, applied **globally** | — | bounded ×1.7 | 0.97867 |
| `b0/a01` (iter001) | the cone head, **rotated** | the level law, applied globally | — | rotation | 0.97867 (broke `tt`/`disk`) |
| `b2/a02` (iter001) | — | — | the **pairwise** wave-fit (a *cap* on the causal factor) | demotion only | 0.97867 |
| `b2/a04` (iter001) | the **joint** wave-source fit | coverage of the whole wave | coverage + error + margin | demotion only | 0.97867 |
| `b0/a03` (iter001) | **leader-anchored** upstream certification | the level law + residual correlation | near-tie + own-relative consistency | rotation | 0.9680 |
| `b7/a01` (iter001) | **harm-absence** (the service showing none of the harm) | — | — | **unbounded** anchor | 0.9627 |
| `b8/a01` (iter001) | the largest own-relative footprint **outside** the symptom family | — | an exclusive-owner veto | rotation | 0.9707 |
| `b6/a00` (iter002) | the **sink** of the leading three | raw-unit containment | the leader is its descendant | rotation | 0.9840 |
| `b6/a01` (iter002) | the inherited detectors' origin, **certified** | the cone head / the exclusive cell | the **transitive** closure, **over the leading eight** | rotation | **0.98933** |
| `b6/a05` (iter002) | a **direct** leader→candidate containment edge | the level law | the direct edge + the wave-fit | rotation | 0.98933 (inert) |
| `b8/a00` (iter002) | the **chain root** of a parent map built from the leader's *strongest* metric, in **any** family | the parent map | the *magnitude free* isolation veto | rotation inside the leading **five** | 0.97333 (**−0.0053**) |
| `b3/a00` (iter002) | the **uninherited head** (a share of zero) | the containment relation | the absence of inheritance | rotation | 0.984 (inert) |
| **this attempt** | the **source of the leader's chain**, resolved over the **whole wave** and read in the **leader's own channel** | the raw-unit containment identity, closed transitively over the wave | the leader provably **contains** the source (the victimhood proof), plus the magnitude-free isolation veto and the source's own trace | rotation inside the leading **three** | *not yet measured* |

**Three things are new relative to everything above.**

1. **A targeted fix to a specific, located defect — the *scope* of the certification.** Both
   inherited deliveries compute the containment relation over a window of three or eight services
   (`_CA_TOP = 3`, `_ROT_CA_TOP = 8`). The champion's own code therefore cannot see a chain whose
   intermediate members lie outside that window, and that is precisely the configuration in which
   the residual lives. This attempt resolves the same relation over the **whole wave** and reads
   the chain's **source**. The *question* ("which service is the source of the leader's chain?")
   has never been asked in the archive over a complete scope: `b8/a00` walked a parent map
   (a *different* object: one parent per metric, in any family, from the leader's *strongest*
   metric) and delivered it inside the leading five, and it was **measured to regress by 0.0053**.
2. **A new combination of previously-successful pieces.** The *relation* is the champion's own
   (measured: the arbitration and the certified rotation are the only two mechanisms that ever
   moved the residual). The *victimhood certificate* is the champion's own transitive closure
   (measured). The *level law* as a tie-break is the archive's only validated orientation
   (measured: +3.5 points in `b6/a03`, +1.6 in `b6/a05`, +1.9 in `b6/a06`). The *magnitude-free
   isolation veto* is the guard the archive measured to be necessary (L8). The *rotation* is the
   delivery the archive measured to pay (L7). **The whole-wave scope over the leader's own
   channel, with the source's own trace as the second certificate, is new.**
3. **A new object.** Every inherited origin detector names a service by a property of *that
   service* (an exclusive cell, the smallest baseline, the absence of the harm, an
   opposite-direction trace). This attempt names it by the **structure of the wave it lives in**:
   the service at the **source** of the leader's chain. The source is a *relational* object — it
   is defined by the closure of the containment relation over the wave — and it is the only
   archive mechanism that is defined over a **complete** scope rather than over a window.

**Explicitly not repeated:** the timing family (`b6/a02`, `b8/a03`, `b9/a04` — three measured
collapses); every *unbounded* placement (`b6/a07`–`b6/a09`, `b7/a01`–`b7/a04`, `b4/a04`); every
additive per-metric re-score (`b1/a03` = 0.3200, `b0/a04`, `b9/a06`); every demotion for a
positive reason (`b2/a04` = −0.077, `b1/a07`, `b8/a02`); the responsibility-weighted aggregation
(`iter001/b6/a01`, measured **−5.2 points**); the healthy-window pass-through asymmetry (`b1/a10`,
`iter001/b0/a04`); the crowd-relative dependence gate (`iter001/b8/a00`); the replication count
(`iter001/b4/a05`); the joint wave-source fit (`iter001/b2/a04`); the level-hierarchy depth laws
(`b3/a07`, `b7/a10`); every metric-kind vocabulary (`b8/a10`); the harm-absence / self-failure /
quiet-fault-site family (`b7/a01`, `b7/a02/03/05`, `b4/a01/05`, `b8/a01`, `b6/a02`, `b6/a04`) —
all of which look for a fault site **outside** the leading group or by a property of one service,
whereas this mechanism deliberately works on the **relation between the leader and the wave**; and
the champion's own two deliveries, which are kept byte-identical and are never fought.

---

## 5. Expected benefit, risk, and what is **not** claimed

### 5.1 Expected benefit

The whole prize is the champion's **0.8 case-points = 0.0107** of the objective.

* **`dev-18392340d0259140`** (ss/`loss`, rank 2 → 1) is worth **+0.2** of a case = **+0.0027**.
  The `ss` system has 11 services, so its wave is small and the chain is short; the mechanism
  should have the best chance here.
* **`dev-2e28415fe63c9ea1`** (tt/`delay`, rank 2 → 1) is worth **+0.2** = **+0.0027**. This is the
  case in which the *scope* matters most (64 services), and it is exactly the configuration the
  inherited windows of three and eight services cannot see.
* **`dev-315e24b9921bc3b7`** (ob/`loss`, rank 3 → 1) is worth **+0.4** = **+0.0053**, but its
  window has **no post-incident rows** (the "post" half is a fallback split of pre-incident data),
  so the incident is not observable in it and I do **not** count it.

A realistic band is therefore **+0.000 … +0.0053** on the development objective (0.98933 →
0.989 … 0.995), with the **designed floor** being the champion's own **0.98933** reproduced case
for case whenever the new block abstains. I deliberately do not claim more: this residual has
defeated more than twenty consecutive mechanisms.

### 5.2 Risks, and what bounds each one

1. **The source is not the fault site.** The main exposure. It is bounded by the *delivery*: the
   rotation is a permutation of a fixed leading-three set, so `AC@3` and `AC@5` cannot be lost and
   the damage is **one position of one case** (0.2 = 0.0027 of the objective). The two guards
   narrow the exposure further: the source must be *provably* contained by the leader (the
   victimhood proof) and must show a trace of its own outside the wave (it is not a pure victim).
2. **The rule fires on a currently-correct case.** The main downside. Bounded structurally:
   (i) the block runs only where *both* inherited deliveries abstained, so it never fights them;
   (ii) **G1** withholds the delivery whenever the leader owns a change alone in its cell, which
   is the signature of the fault site of a *local* fault — and that is precisely the signature of
   the leader in the 45 `cpu`/`mem`/`disk` cases and of the correctly identified `delay`/`loss`
   cases; (iii) the source must sit inside the leading three and carry a tenth of the leader's
   score.
3. **The 45 currently-perfect `cpu`/`mem`/`disk` cases are damaged.** Protected three times over:
   (i) in the resource regime the fault site's own saturated resource metric lies alone in its
   cell, so **G1** fires and the delivery is withheld; (ii) in the resource regime the
   inherited exclusive-cell detector names the fault site, and the inherited certified rotation
   delivers it, so `ordered != ordered_base` and the new block never runs; (iii) a resource metric
   has no containment parent — nothing contains another service's CPU series — so the wave
   relation never links a resource fault site to the leader.
4. **The mechanism is inert.** The failure mode is *inertness*, not damage: the program then
   reproduces the champion's ranking case for case and scores **0.98933**. Given L2 and the
   archive's record this is the **most likely single outcome**, and it is the designed floor.
5. **Any exception zeroes the whole candidate.** Safeguards: every new helper is individually
   wrapped in `try/except` with a neutral default (`None` = no source, `False` = no veto, an
   empty edge set); the delivery block has its own `try/except`; the final scores still pass
   through `nan_to_num` so that a non-finite value can never sort to the front; `rank()` falls
   back to a hardened plain robust-deviation ranking and then to the raw column order; and the
   output always contains every metric column exactly once, as strings. The file was written out
   in full and **read back region by region** — bracket nesting, indentation, index types, the
   numpy shapes of every operation, the `try/except` boundaries and the definition-before-use
   order of every name were checked against the champion's code, which is known to run.
6. **Cost.** One extra `m × m` raw covariance product (`m ≤ 189`, `T ≤ 1200`: ≈4·10⁷ flops,
   milliseconds) plus `O(|wave|²·k²)` pair tests over the wave and a *linear* transitive closure
   (the inherited `_closure` is quadratic in the number of edges and would be too slow for a wave
   of dozens of services, so a depth-first closure is used instead). The block sits behind its own
   92 s wall-clock guard; the inherited blocks keep their own.
7. **Overfitting to 75 development cases.** The new constants (`_WC_TOP`, `_WC_GAIN`,
   `_WC_GAIN_MAX`, `_WC_VAR`, `_WC_CORR`, `_WC_FIT`, `_WC_MINPRE`, `_WC_MIN_REL`,
   `_WC_LEVEL_GAP`, `_WC_CELL_MAX`, `_WC_DEADLINE`) are each a restatement of an **inherited**
   constant of the same physical relation — `_WC_TOP` = `_CA_TOP` = `_ROT_TOP` = 3 (the leading
   group the whole archive protects), `_WC_GAIN` = `_CA_GAIN` = 0.85, `_WC_VAR` = `_CA_VAR` = 1.10,
   `_WC_CORR` = `_CA_CORR` = 0.30, `_WC_MINPRE` = `_CA_MINPRE` = `_CD_MINPRE` = 30, `_WC_MIN_REL` =
   `_ROT_MIN_REL` = `_CA_MIN_REL` = 0.10, `_WC_LEVEL_GAP` = `_CONE_GAP` = 0.10. The three genuinely
   new numbers are `_WC_GAIN_MAX = 1.60` (the mirror of `_CA_GAIN` on the other side of the
   identity: a *containment* gain is ≈1, so a gain far above 1 is not a containment — the same
   number `iter002/b6/a05` used for the same reason), `_WC_FIT = 0.60` (the wave-fit tolerance
   widened because a container may accumulate the contained change from several branches) and
   `_WC_CELL_MAX = 3` (the source's own trace may be shared with the services the fault site
   calls). **None was fitted against the development score**, and **all** of the champion's
   constants are untouched.
8. **Determinism / contract.** No randomness, no new imports, no I/O, no network, no GPU, no state
   between cases, no change to the seed outside the EVOLVE block. The metric families are derived
   at run time from the column names by the inherited suffix rule and are used only as a grouping;
   `metadata['sli']` keeps its inherited weak co-movement role and is never read as a hint about
   the root cause. **No service name, fault type, case identity, per-system constant or dataset
   identity is used anywhere.**

### 5.3 Honest status

**This program has not been executed.** This session exposes **no execution tool** and no copy of
the development windows, so the program has never been run on a development case. Every number
quoted in §1 is **measured** — read out of the archived `eval/score.json` files — and every
expectation in §5 is a *design expectation* derived from those measurements and from reading the
champion's code. **I make no claim that this program compiles, that it runs, that it is faster
than the base, or that it beats 0.98933**; only the evaluator's run can settle that.

What *can* be said about the code is that it is the measured-best program plus **one** added,
individually exception-isolated block, whose delivery reuses the champion's own rotation, whose
victimhood proof reuses the champion's own transitive closure over a **wider scope**, whose
victimhood veto is the magnitude-free isolation test the archive measured to be necessary, and
which is an **exact no-op** whenever the inherited deliveries have already spoken or the
certificates are absent — in which case the ranking is the champion's ranking case for case.

### 5.4 Files

* `attempt_00/artifact/program.py` — the implementation (NumPy only; no new imports, no I/O, no
  randomness, no GPU, fully deterministic).
