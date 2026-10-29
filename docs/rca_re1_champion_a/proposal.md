# Proposal — cone-head origin attribution (most-upstream member of a verified propagation cone)

Branch `explore_b0`, attempt `b0_a0`.

## 1. History read, and what it measures

The archive `history/iter000` holds **109 completed attempts** across ten branches.
`history/iter000/raw_scores.json` is the run's own export of every node's measured
`combined_score`; I used it to reconstruct the whole ladder, and I read the
proposals and the per-case `eval/score.json` rows of the artefacts that matter for
this proposal. Measured ladder (development split, 75 cases, **service** Avg@5,
from `raw_scores.json` and from each attempt's own `eval/score.json`):

| branch | attempt_00 | … | best attempt | best score |
|---|---|---|---|---|
| `b0` | 0.6853 | … | a6/a7 | **0.7333** |
| `b1` | 0.9147 | … | a10 | **0.9413** |
| `b2` | 0.3200 | … | a8 | **0.8053** |
| `b3` | 0.8400 | … | a4 | **0.8613** |
| `b4` | 0.9147 | … | a10 | **0.9360** |
| `b5` | 0.3360 | … | a8 | **0.8320** |
| `b6` | 0.8960 | … | **a6** | **0.9733** |
| `b7` | 0.5840 | … | a9/a10 | **0.7333** |
| `b8` | 0.9147 | … | a1/a5/a7/a10 | **0.9413** |
| `b9` | 0.5120 | … | a10 | **0.7733** |

baseline = **0.384**. So `explore_b6/attempt_06` is the incumbent (SOTA) at **0.9733**
(AC@1 0.920, AC@3 0.987, AC@5 **1.000**, metric-level Avg@5 0.605).

Every one of the 109 proposals was surveyed for its mechanism and its *measured*
outcome (the archive's own `raw_scores.json` export plus each attempt's
`eval/score.json`), and the ones that shaped this proposal were read **in full,
together with their code**: `b6/a0…a10` (all eleven), `b1/a0`, `b1/a1`, `b1/a3`,
`b1/a6`, `b1/a10`, `b4/a0`, `b8/a0`, `b0/a0`, `b0/a1`, plus the measured per-case rows
of `b1/a10`, `b4/a10`, `b8/a10` and `b6/a6`. Three attempts died with a `SyntaxError`
(`b0/a1`, `b3/a9`, `b5/a2`) and one with a missing `proposal.md` (`b7/a7`); four
attempts across four *different* branches collapsed to exactly **0.3200** (`b1/a3`,
`b2/a0`, `b5/a1`, `b8/a3`).

## 2. The measured residual, and why the obvious fixes failed

`Avg@5_service` is the mean of `AC@1…AC@5`; a cause at service rank *r* scores
`(6−r)/5`. Reading the 75 rows of `b6/a6/eval/score.json`: **73.0 of 75 points are
earned; 2.0 points are lost across exactly 6 cases**, and *nothing else is lost*:

| case | system | fault | AC@1 | AC@3 | AC@5 | Avg@5 | rank |
|---|---|---|---|---|---|---|---|
| `315e24b9` | ob | loss | 0 | 1 | 1 | 0.6 | 3 |
| `2dac18fc` | ob | loss | 0 | 1 | 1 | 0.6 | 3 |
| `18392340` | ss | loss | 0 | 0 | 1 | 0.4 | 4 |
| `2e28415f` | tt | delay | 0 | 1 | 1 | 0.8 | 2 |
| `c8de8f8c` | tt | delay | 0 | 1 | 1 | 0.8 | 2 |
| `c9c88d38` | tt | loss | 0 | 1 | 1 | 0.8 | 2 |

Three facts follow and they define the target:

1. **The residual is 100 % `delay`/`loss`.** All 45 `cpu`/`mem`/`disk` cases are perfect
   (`AC@1_service = 1` in every one).
2. **It is an ordering problem, not a detection problem.** `AC@5_service = 1.000`: the
   cause is inside the top five services of *every* case and inside the top three in 74
   of 75. It is simply not *first*.
3. **The cause is in the top five because it is part of a propagation cone.** A network
   fault is injected at one service's interface and the perturbation is handed on
   unchanged along the request path, so the fault site and its callers move by
   *roughly the same absolute amount*. The magnitude therefore cannot separate them;
   only the **position** in the chain can.

### 2.1 What the four attempts after the incumbent measured, and the lessons they leave

`b6/a7`–`b6/a10` are the only attempts in the whole archive that attack this exact
residual on top of the incumbent, and **all four regressed**
(0.9680, 0.9680, 0.9280, 0.9600 against 0.9733). Their own analyses locate why, and
the three lessons are the design rules of this proposal:

* **`b6/a7` (0.9680) — "explanation-verified symptom demotion + global anchor".** Its
  symptom test asked whether a symptom's change is *reproduced* by an upstream change
  and accepted **"same absolute amount, same direction"** as reproduction. But that
  equality is precisely what *every* member of a propagation cone shares, so the test
  cannot orient the cone and demoted cone members at random (it broke two previously
  perfect cases). Its second half — a **global level-setting anchor** — could lift a
  service out of the cone it reasons about.
* **`b6/a8` (0.9680) — "incident-coherence cone + cone-confined anchor".** It grouped
  the cone by *shift value* and nominated the *most upstream* member of it, then
  anchored it above the group's leader. It fixed the two cases `a7` had broken and broke
  one new one, but **converted none of the six** — the anchor is a *level-setting*
  operation, the form the archive shows to be destructive.
* **`b6/a9` (0.9280) — "cell-structured dissensus origin + hierarchy-root placement".**
  It read the oriented relation as a set of *roots* and placed the root above the group.
  It broke ~20 previously perfect resource cases (`cpu`/`mem`/`disk` dropping from 1.0
  to 0.8): the placement was applied outside the population it was designed for.
* **`b6/a10` (0.9600) — "service-level self-relative impact ordering".** It reordered
  *all* near-tied contenders of the dominant family by their own-baseline-relative
  change, as a continuous factor of at most 1.8×. Reordering a whole group by a proxy
  that is not always right is a no-no; a single, clearly-separated candidate is safer.

Two further lessons come from *other* branches and are directly relevant:

* **`b1/a6` (0.9307) measured the axis this proposal uses.** Its "axis A" is exactly
  the chain-depth law: in the *equal-shift* regime (the shifts of the moved services
  are indistinguishable) **the source is the member with the smallest healthy baseline
  level**, accepted only when that level is clearly below the runner-up's. Measured
  effect in that (much weaker) base: **5 fixes, 2 breaks, +0.008**. The two breaks
  were *not* caused by the identification — its own analysis shows they were caused by
  the **delivery** (an unconditional *exchange* that sent a correct leader down to
  rank 3). Its "axis B" (a private footprint) was measured separately and added
  +0.005.
* **`b1/a3` (0.3200) is the archive's cautionary tale.** Its two blocks were a
  per-metric persistence multiplier and a healthy-window counterfactual attribution.
  The multiplier is what destroyed it. But the measurement also shows why a *promotion*
  needs a bound: `b1/a3` has **37 of 75 cases with `AC@5_service = 0`** — the true
  cause was pushed *out of the top five* — where its parent `b1/a1` has **0** such
  cases. A promotion that lifts a wrongly identified service into the leading group
  does displace the true cause; "promotion-only" does **not** protect `AC@5`, contrary
  to that attempt's own claim.

### 2.2 What the other strong programmes do on these six cases

The per-case rows of the other strong programmes (all measured) show that this residual
is *not* specific to the incumbent — but also that it is not universal:

| case | `b6/a6` (0.9733) | `b1/a10` (0.9413) | `b4/a10` (0.9360) | `b8/a10` (0.9413) |
|---|---|---|---|---|
| `315e24b9` ob/loss | 0.6 | 0.6 | 0.8 | 0.4 |
| `2dac18fc` ob/loss | 0.6 | **1.0** | 0.8 | 0.8 |
| `18392340` ss/loss | 0.4 | 0.6 | 0.8 | 0.4 |
| `2e28415f` tt/delay | 0.8 | 0.2 | 0.6 | 0.0 |
| `c8de8f8c` tt/delay | 0.8 | 0.8 | **1.0** | **1.0** |
| `c9c88d38` tt/loss | 0.8 | 0.8 | **1.0** | 0.6 |

`b4/a10` (a completely different family: kind-isolation + onset-gated causal
asymmetry + percentile-rank fusion) puts two of the six first and two at rank 2. So
the information needed to separate the cause from *its own cone* exists in the data —
it is a matter of reading the cone's **position** rather than its loudness.

## 3. The mechanism

Everything `b6/a6` does is inherited **unchanged**: the split at `inject_time`, the
family scales, the robust statistics, the monotone soft saturations, the persistence
factor, the self-relative impact, the own-scale change visibility, the
confounder-adjusted direct-effect attribution, the level-oriented driver filter, the
peer isolation, the SLI co-movement, the exclusive-cell origin *detector*, the
level-oriented upstream demotion and the interleaved metric emission (so the
evaluator's first-occurrence service ranking still reproduces our service ranking
exactly). **Not one inherited constant is changed.**

One new service-level mechanism is added: **cone-head origin attribution**.

### 3.1 The physical statement

A fault injected at the network interface of one service adds a perturbation `d` to
every service on the request path. Two consequences are used:

* **equal-shift law** — the members of the propagation cone move by *the same absolute
  amount*, so their change magnitudes are indistinguishable;
* **level accumulation law** — along a call chain the observable's level accumulates
  towards the caller (`caller_latency = callee_latency + own_processing`), so the
  **most upstream** member of the cone — the fault site — carries the **smallest
  healthy baseline level** of the cone, and therefore the largest change *relative to
  its own level*.

The level accumulation law is the single most valuable *measured* orientation signal in
the whole archive: `b6/a3` used it as a per-metric factor and gained **+3.5 points**
(0.904 → 0.9387); `b6/a5` used it to orient the driver relation (+1.6) and `b6/a6`
used it to demote the downstream members of the affected set (+1.9). It has never been
used to *name* the origin inside the cone.

### 3.2 The rule (conjunctive, therefore inert by construction)

For the affected set (metrics with `change ≥ 1.5 σ`, `persist ≥ 0.40` and an
own-baseline-relative change `≥ 0.10` — the incumbent's own definition):

1. **Cone.** Group the affected metrics into cells `(metric family, direction)`; the
   cell spanned by the **most services** is the propagated symptom and must span at
   least **3** services — otherwise there is no cone and the block abstains.
2. **Propagation check.** The members of the cone must be near-tied in the **absolute**
   size of their shift: no member may exceed **4×** the median absolute shift of the
   cone. This is the *verification* that the change was handed on unchanged rather than
   being a local fault plus its consequences; it is what `b1/a7` lacked when it used
   the same equality as a *direction* test.
3. **Orientation.** The head of the cone is the member with the **smallest healthy
   baseline level** (the metric's own `|median(pre)|`), and it is accepted only when
   that level is at least **10 %** below the runner-up's — a flat hierarchy carries no
   order, and a tie carries no information.
4. **Dominance-of-the-propagation check.** The affected metric with the **largest
   overall score** must belong to the cone. This says: *the propagation is the dominant
   effect of this incident*. It is the guard that keeps the rule out of the resource
   regime, where the fault site's own resource metric changes by an order of magnitude
   more than any propagated symptom and lives in a different family — the resource
   cases, which are 45 of 75 and all perfect, are therefore untouched.
5. **Delivery.** The head's service score is multiplied by `1 + 0.70·w`, where `w ∈
   [0,1]` grows with the size of the level gap. The promotion is applied **only if the
   head is already comparable with the leader** (its aggregated score is at least
   **25 %** of the leader's), which is the bound that `b1/a5`'s measured regressions
   demanded and the bound that protects `AC@5` against the `b1/a3` failure mode. The
   block runs **only when the inherited exclusive-cell detector found nothing**, so
   every case in which the incumbent's own origin rule fires is bit-for-bit unchanged.

### 3.3 Why the delivery is a multiplication and not an anchor

`b6/a7` and `b6/a8` both used a **level-setting anchor** ("put the origin just above
the leader of the cone") and both regressed; `b6/a9` used one too and broke ~20
perfect cases. An anchor can move a service from rank 5 to rank 1 — a *leapfrog*, and
`b1/a3` measured exactly that failure mode (37/75 cases with the cause pushed out of
the top five). A bounded multiplication, applied to a service that is already a
contender, can at worst reorder two neighbours inside the affected set: the damage of
a wrong promotion is one swap, and the set of leading services cannot change.

## 4. Why this is not a repeat

* It is **not the incumbent**: the incumbent's origin rule (`_origin_service`) looks for
  a change that is *alone* in its `(family, direction)` cell — the fault's **private
  signature**. It cannot fire in the propagation regime, because the branch's own
  diagnosis is that the fault site's trace there is *shared* with the services it
  calls. The new rule looks at the **propagated** cell itself and names its **most
  upstream** member, which is the opposite choice of cell.
* It is **not `b6/a8`**: `a8` grouped the cone by *shift value* and used a
  *level-setting* anchor; it also carried a second, "discordant metric" signature
  detector that is the likely source of the one case it broke. This proposal uses the
  incumbent's own `(family, direction)` cell definition, adds the near-tie
  *verification*, the *dominance-of-the-propagation* guard and the
  *comparable-with-the-leader* bound, and uses a bounded multiplication instead of an
  anchor.
* It is **not `b6/a9`**: `a9` read the oriented relation as a set of *roots* of the
  whole affected hierarchy and placed a root above the group — an unconfined placement
  that broke the resource cases. This rule never uses the hierarchy graph, never
  promotes outside the cone, and is blocked in the resource regime by the
  dominance-of-the-propagation check.
* It is **not `b6/a10`**: `a10` re-ordered *every* near-tied contender of the dominant
  family by a continuous self-relative proxy. This rule promotes **one** candidate
  that is separated from the runner-up by a clear level gap, and only when four
  independent conditions hold.
* It is **not `b1/a6`/`b1/a10`**: those are the same *idea* in a much weaker base
  (0.9227/0.9360) with a different delivery (an unconditional *exchange*, later a
  *rotation*). What is new here is the combination with the incumbent's own machinery
  — its own-scale view, its exclusive-cell detector (which is kept and given priority)
  and its level-oriented upstream demotion — plus the three guards that the archive's
  measured failures show are needed, and a delivery that cannot leapfrog.
* It is **not the classical causal-discovery family**: no graph is estimated, no lag is
  used, no Granger test is computed, and nothing is oriented by a regression on the
  incident window.

## 5. Expected benefit and risk

**Expected benefit.** The whole prize is the incumbent's 2.0 points across six cases.
The three cases at rank 2 need only a small relative advantage to convert; a ×1.7
promotion of a service that is already within a factor of two of the leader supplies
far more than that. The two `loss` cases at rank 3 and the `ss/loss` case at rank 4
need the same identification to work but a larger margin. A realistic expectation is
**+0.005 … +0.020** on the development objective (0.973 → 0.978–0.993). I do **not**
expect 1.0: `18392340` sits at rank 4, and a fault whose site leaves *no* trace in the
telemetry cannot be recovered by any ranking — `b1/a10`'s own analysis measured that in
7 of its 11 residual cases the cause's own metric is not even in the metric-level top
five.

**Risks and mitigations.**

1. *The level hierarchy points at the wrong cone member.* This is the main exposure.
   Mitigated by (i) the 10 % separation requirement (a flat hierarchy abstains),
   (ii) the near-tie verification of the cone (a cone whose members differ wildly in
   absolute shift is not a propagation cone and abstains), (iii) the
   dominance-of-the-propagation check, (iv) the comparable-with-the-leader bound, and
   (v) the bounded ×1.7 multiplication, whose worst case is a single swap inside the
   affected set.
2. *The rule fires on the 45 currently perfect resource cases.* It cannot: in a
   resource fault the fault site's own resource metric is the top-scoring affected
   metric and it does not live in the propagated latency cell, so check 4 abstains;
   and if the fault site's latency *does* join the cone, it is the most upstream
   member, so the head is the fault site and the promotion is a no-op.
3. *A wrong promotion displaces the leader.* `b1/a3` measured that a promotion can push
   the true cause out of the top five. Mitigated by the comparable-with-the-leader
   bound (the head is already in the leading group) and by the bounded factor: the
   promoted service cannot leapfrog more than one neighbour, and the set of leading
   services is unchanged.
4. *Any exception zeroes the whole candidate.* The new block is wrapped in
   `try/except` with the neutral default (no head, no promotion); the aggregation was
   split into two passes so that the leader is known before the promotion is applied,
   which is behaviourally identical for the inherited path (the promotions and the
   demotion are per-service multiplicative factors); the final score passes through
   `nan_to_num`; and the whole program falls back to a hardened plain robust-deviation
   ranking. The output always contains every metric exactly once, as strings.
5. *Cost.* The new block is one extra pass over the affected metrics and a few
   dictionary operations — negligible next to the inherited per-metric least-squares
   loops, which use 10–33 s of the 120 s per-case budget.
6. *Overfitting to 75 development cases.* The five new constants (`_CONE_TIE`,
   `_CONE_GAP`, `_CONE_GAP_FULL`, `_CONE_W`, `_CONE_MIN_REL`) each have a stated
   structural justification rather than a fitted value; none was tuned against the
   development score, and **all** of the incumbent's constants are untouched.

**Not claimed.** This proposal has not been scored: this session exposes no execution
tool and the branch has no local copy of the data. Every number quoted for the
incumbent and for the other programmes is read out of their measured `eval/score.json`
files; the physical account of the propagation cone (one perturbation, equal absolute
amounts, levels accumulating along the chain) is the account the archive has used
since `b6/a3` and that the next evaluation will test.
