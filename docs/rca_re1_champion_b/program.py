"""Own-scale change visibility + level-oriented upstream demotion + cone-head
origin, extended with a *containment-anchored service arbitration*, a
*certified rotation of a detected origin* and a *whole-wave containment
source*.

This is the measured-best lineage of ``explore_b6`` (attempt_06 of the first
cycle and the cone-head refinement of the second cycle, service Avg@5 =
0.9733 / 0.9787 on the 75 development cases) with **four** additions:

  * a **containment-explained symptom demotion**, which uses the *raw units*
    of the healthy window to recognise that a metric's incident shift was
    inherited from the service it calls, and

  * a **containment-anchored service arbitration**, a new mechanism that runs
    a *dedicated contest among the leading services* and moves the deepest
    member of that group to the front by a set-preserving rotation, and

  * a **certified rotation of a detected origin**: the inherited program
    *identifies* an origin in two regimes -- the fault's own exclusive
    signature (the resource regime) and the most upstream member of the
    propagation cone (the network regime) -- but delivers it with a
    *bounded multiplicative promotion* (at most x1.5 / x1.7).  The archive
    measured that a bounded factor cannot cross the magnitude gap between a
    quiet fault site and a loud victim, so in the network regime the delivery
    is inert: the origin is found and then dropped again.  This program
    delivers the detected origin by the archive's *set-preserving rotation*
    instead, and only after the program's own **containment relation has
    certified** that the leader of the ranking is a *descendant* of the
    candidate -- i.e. that the candidate is provably upstream of the service
    that currently occupies the first row.  The certification uses the same
    raw-unit containment identity the arbitration uses.

  * a **whole-wave containment source** (new in this attempt): the two
    inherited delivery mechanisms are *scope limited*.  The arbitration
    estimates the containment relation **only among the leading three
    services**, and the certified rotation estimates it **only among the
    leading eight**, so a propagation chain whose intermediate members lie
    outside those windows is invisible to both, and the true fault site --
    which the development split always places inside the leading three --
    stays at rank 2 or 3 behind a victim.  This attempt resolves the
    leader's own chain over the **whole wave** (every service that carries
    the leader's channel), reads the **source** of that chain, and delivers
    it with the same set-preserving rotation.  The delivery is guarded by a
    *magnitude free* private-cell test: a leader that owns a change alone
    in its (metric family, direction) cell is the origin of a local fault
    and is never displaced.

Everything the inherited program does is kept unchanged -- the split, the
family scales, the robust statistics, the monotone soft saturations, the
persistence factor, the self-relative impact, the own-scale change
visibility, the confounder-adjusted direct-effect attribution, the
level-oriented driver filter, the peer isolation, the SLI co-movement, the
exclusive-cell origin *detector*, the level-oriented upstream demotion, the
cone-head origin and the interleaved metric emission.
"""
import numpy as np

# EVOLVE-BLOCK-START
import time as _clock

_A_STD_K = 3.0     # soft-saturation knee of the standardised excursion
_A_FAM_K = 2.0     # soft-saturation knee of the family-normalised shift
_GATE = 0.15       # a metric counts as "changed" at 15% of its family scale
_IMP_W = 0.35      # weight of the propagation-impact term

# --- self-relative impact (inherited) ----------------------------------------
_REL_LO = 0.80     # factor of a metric with no self-relative impact
_REL_HI = 1.20     # factor of the metric with the largest self-relative impact
_REL_FLOOR = 0.20  # fallback floor of the own level (20% of the family scale)
_REL_SIG = 0.05    # a metric takes part in the reference only above 5%
_REL_CAP = 50.0    # cap of the self-relative ratio (guards degenerate series)

# --- confounder-adjusted direct-effect attribution (inherited) ----------------
_NCONF = 3         # number of common modes (principal directions) removed
_DRIVER_CORR = 0.30   # minimum |partial correlation| of a candidate driver
_NDRIVER = 10      # maximum number of candidate drivers per metric
_MAG_RULE = 0.75   # a driver must move at least this much as much as its target

# --- inherited: level-oriented driver filtering ------------------------------
_LVL_MARGIN = 0.20  # a driver clearly larger in baseline level is not upstream

# --- inherited: exclusive-cell origin ----------------------------------------
_CELL_W = 0.50      # service-level promotion of the origin service
_CELL_CONC = 0.80   # mass concentration of an exclusive cell in one service
_CELL_ISOL = 2      # a cell with at most this many services may be exclusive
_CELL_REL = 0.10    # minimum own-level-relative change of a signature metric
_CELL_SIGMA = 1.5   # minimum noise-relative change of a signature metric
_CELL_PERSIST = 0.40  # minimum persistence of a signature metric
_CELL_DOM = 3       # the dominant cell must span at least this many services
_CELL_REF = 0.40    # signature magnitude relative to the dominant cell that
                    # counts as full strength
_OWN_REL_CAP = 10.0  # cap of the own-level-relative magnitude

# --- inherited: own-scale change visibility -----------------------------------
_OWN_FLOOR_SD = 3.0   # the own level is floored at 3 robust sigmas of its own
_OWN_GATE = 0.15      # own-level-relative change that counts as "changed"
_OWN_SIGMA = 1.5      # noise-relative significance of an own-scale change
_OWN_CAP = 50.0       # cap of the own-level-relative ratio

# --- inherited: level-oriented upstream demotion -------------------------------
_UP_CORR = 0.45       # min |residual correlation| for a dependency relation
_UP_LEVEL = 0.30      # the downstream level must be this much larger
_UP_OWN = 0.80        # the upstream member must be at least as anomalous
_UP_DEMOTE = 0.85     # factor of a service one upstream step below another
_UP_MAX_DEPTH = 3     # at most this many upstream steps are counted
_UP_SIGMA = 1.5       # noise-relative significance of an affected metric
_UP_PERSIST = 0.30    # and the change must be sustained, not a fluctuation

# --- inherited: relaxed membership of the origin -------------------------------
_CELL_STRONG = 0.35        # own-relative magnitude of a strong signature
_CELL_STRONG_SIGMA = 2.0   # its noise-relative significance
_CELL_STRONG_PERSIST = 0.50  # its persistence

# --- inherited: cone-head origin ------------------------------------------------
_CONE_TIE = 4.0        # no cone member may exceed this multiple of the
                        # median absolute shift of the cone
_CONE_GAP = 0.10       # the head's baseline must be this much below the
                        # next member's baseline
_CONE_GAP_FULL = 0.30  # a level gap of this size gives full strength
_CONE_W = 0.70         # service-level promotion of the cone head
_CONE_MIN_REL = 0.25   # the cone head must already be within this fraction of
                        # the leader's score, so that the promotion can never
                        # lift a deep service into the top five

# --- new: containment-explained symptom demotion ------------------------------
_CD_GAIN = 0.80     # minimum containment gain  cov(i,k) / var(k)
_CD_VAR = 1.15      # the containing series must have clearly more variance
_CD_CORR = 0.30     # minimum |raw correlation| of the candidate pair
_CD_FIT = 0.50      # maximum relative residual of the wave-fit test
_CD_W = 0.60        # how far the causal factor of a reproduced symptom is cut
_CD_MINPRE = 30     # minimum number of pre-window rows for the raw moments

# --- new: containment-anchored service arbitration -----------------------------
_CA_GAIN = 0.85     # minimum raw containment gain  cov(X,Y) / var(Y)
_CA_VAR = 1.10      # the containing series must have clearly more variance
_CA_CORR = 0.30     # minimum |raw correlation| of the pair
_CA_FIT = 0.35      # maximum relative residual of the wave-fit test
_CA_MINPRE = 30     # minimum number of pre-window rows
_CA_MIN_REL = 0.10  # the sink must already be within this fraction of the
                    # leader's aggregated score
_CA_TOP = 3         # only the leading services take part in the contest

# --- new: certified rotation of a detected origin ------------------------------
_ROT_TOP = 3         # the rotation is confined to the leading three services
_ROT_MIN_REL = 0.10  # the candidate must be within this fraction of the
                      # leader's aggregated score
_ROT_CA_TOP = 8      # the containment relation is estimated on the leading
                      # eight services, so that a chain whose intermediate
                      # member lies outside the leading three is still visible
_ROT_VETO_OWN = 0.50  # a private signature must be this large in own units
_ROT_VETO_FR = 0.50   # ... and this large in family units

# --- new: whole-wave containment source ----------------------------------------
_WC_TOP = 3         # the delivery group: the leading three services
_WC_GAIN = 0.85     # minimum raw containment gain  cov(X,Y) / var(Y)
_WC_GAIN_MAX = 1.60  # maximum raw containment gain: a containment gain is
                      # about one, so a much larger gain is not a containment
_WC_VAR = 1.10      # the containing series must have clearly more variance
_WC_CORR = 0.30     # minimum |raw correlation| of the pair
_WC_FIT = 0.60      # maximum relative residual of the wave-fit test.  Wider
                    # than the inherited _CA_FIT = 0.35 because a container may
                    # accumulate the contained change from several branches or
                    # add its own delay, so its own shift may legitimately be
                    # larger than the contained one.
_WC_MINPRE = 30     # minimum number of pre-window rows
_WC_MIN_REL = 0.10  # the candidate must carry this share of the leader's score
_WC_LEVEL_GAP = 0.10  # a flat hierarchy carries no order
_WC_CELL_MAX = 3     # the source's own trace may be shared with this many
                      # services (the loss regime shares the fault site's trace
                      # with the services it calls), but not with the wave
_WC_DEADLINE = 92.0  # wall-clock guard of the new block (of 120 s per case)


def _service_of(name):
    """Service key exactly as the evaluator derives it."""
    head = name.split("_")[0]
    if head.endswith("-db"):
        head = head[:-3]
    return head


def _time_vec(data):
    for i, c in enumerate(data.columns):
        if str(c) == "time":
            return data.iloc[:, i].to_numpy(dtype=np.float64)
    return np.arange(len(data), dtype=np.float64)


def _prep(data):
    """Return (metric names, numeric matrix, time vector) with duplicates removed."""
    cols = list(data.columns)
    pos = [i for i, c in enumerate(cols) if str(c) != "time"]
    if not pos:
        return [], np.zeros((len(data), 0)), _time_vec(data)
    raw = [str(cols[i]) for i in pos]
    keep, seen = [], set()
    for i, n in enumerate(raw):
        if n not in seen:
            seen.add(n)
            keep.append(i)
    pos = [pos[i] for i in keep]
    names = [raw[i] for i in keep]
    X = data.iloc[:, pos].to_numpy(dtype=np.float64, copy=True)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    t = _time_vec(data)
    if t.shape[0] != X.shape[0]:
        t = np.arange(X.shape[0], dtype=np.float64)
    return names, X, t


def _rank_fallback(data, inject_time):
    """Last-resort ranking: plain robust deviation, never raises."""
    try:
        names, X, t = _prep(data)
        if not names:
            return []
        pre = X[t < inject_time]
        post = X[t >= inject_time]
        if pre.shape[0] < 2 or post.shape[0] < 1:
            return list(names)
        m0 = np.median(pre, axis=0)
        s = 1.4826 * np.median(np.abs(pre - m0), axis=0)
        s = np.where(s > 1e-9, s, 1e-9)
        sc = np.max(np.abs(post - m0) / s, axis=0)
        order = np.argsort(-sc, kind="stable")
        return [names[i] for i in order]
    except Exception:
        try:
            return [str(c) for c in data.columns if str(c) != "time"]
        except Exception:
            return []


def _structure(P, m0, sd, m):
    """Normal-regime structure of the pre-incident window.

    Returns ``(Z, F, R)``:

      * ``Z``: the standardised, mean-centred pre-window,
      * ``F``: the system-wide common modes (the leading principal
        directions of the pre-window), which carry the shared load factor,
      * ``R``: the correlation matrix of the residuals after the common modes
        have been projected out.

    The structure is estimated on the pre-window only; nothing from the
    incident window enters it.
    """
    T = P.shape[0]
    Z = np.clip((P - m0) / sd, -25.0, 25.0)
    Z = Z - Z.mean(axis=0, keepdims=True)
    sdz = Z.std(axis=0)
    sdz = np.where(sdz > 1e-12, sdz, 1.0)
    Zs = Z / sdz
    C = (Zs.T @ Zs) / max(T - 1, 1)
    C = 0.5 * (C + C.T)
    np.fill_diagonal(C, 1.0)

    q = int(min(_NCONF, max(m - 1, 1)))
    if q >= 1:
        try:
            _, evecs = np.linalg.eigh(C)
            V = evecs[:, -q:]
            F = Z @ V
            F = F - F.mean(axis=0, keepdims=True)
        except Exception:
            q = 0
            F = np.zeros((T, 0), dtype=np.float64)
    else:
        F = np.zeros((T, 0), dtype=np.float64)

    if q >= 1:
        try:
            coef = np.linalg.lstsq(F, Z, rcond=None)[0]
            Zr = Z - F @ coef
        except Exception:
            Zr = Z
    else:
        Zr = Z
    sdr = Zr.std(axis=0)
    sdr = np.where(sdr > 1e-12, sdr, 1.0)
    Rs = Zr / sdr
    R = (Rs.T @ Rs) / max(T - 1, 1)
    R = 0.5 * (R + R.T)
    np.fill_diagonal(R, 1.0)
    return Z, F, R


def _direct_effects(P, m0, sd, svc, a, changed_idx, changed_mask,
                     level=None, suffix=None, use_level=False, struct=None):
    """Confounder-adjusted direct-effect attribution of the incident shift.

    The pre-incident window defines the normal dependency structure.  The
    leading principal directions of that window are the system-wide common
    modes (a shared load factor); they are removed from every series before
    the relations between services are estimated, so that a metric which only
    co-moves with everything else is not mistaken for a direct driver.

    For every metric that changed, the candidate drivers are the *changed*
    metrics of *other* services whose partial correlation with it (after the
    common modes are removed) is large.  A small least-squares fit on the
    pre-window gives the direct effect of each driver on the target.  The
    incident shift of the target is then compared with the shift its drivers
    would produce.

    A driver may only explain a target whose own change is *smaller*: a
    symptom cannot be the cause of a larger change elsewhere.  This breaks
    the symmetry that a purely linear normal-regime model leaves between a
    cause and its propagated symptom.

    ``use_level`` additionally orients the relation with the *baseline level*
    of the two metrics.  Inside one metric family the level of the observable
    accumulates along a call chain towards the caller, so the upstream metric
    is the one with the smaller baseline.  A candidate whose baseline level is
    clearly larger than the target's is therefore downstream of the target and
    cannot be its driver; excluding it stops a propagated symptom from
    "explaining" the fault site it was caused by.  This matters exactly in
    the propagation regime, where the size rule alone is vacuous because every
    member of the chain moves by the same absolute amount.

    Returns ``(explained, csum)``:

      * ``explained[i]`` in [0, 1]: the fraction of metric ``i``'s own shift
        that its drivers account for (same direction and comparable size),
      * ``csum[j]``: the total direct effect metric ``j`` exerts on the other
        services (its propagation mass).
    """
    T, m = P.shape
    explained = np.zeros(m, dtype=np.float64)
    csum = np.zeros(m, dtype=np.float64)
    if T < 40 or m < 4 or changed_idx.size < 2:
        return explained, csum

    if struct is None:
        Z, F, R = _structure(P, m0, sd, m)
    else:
        Z, F, R = struct
    q = F.shape[1]
    absR = np.abs(R)

    have_level = bool(use_level) and level is not None and suffix is not None

    for i in changed_idx:
        ai = abs(float(a[i]))
        if ai <= 1e-12:
            continue
        order = np.argsort(-absR[i])
        cand = []
        for j in order:
            j = int(j)
            if j == i:
                continue
            if svc[j] == svc[i]:
                continue
            if absR[i, j] < _DRIVER_CORR:
                break
            if not changed_mask[j]:
                continue          # only a metric that moved can explain
            if have_level and suffix[j] == suffix[i]:
                li = float(level[i])
                lj = float(level[j])
                if li > 0.0 and lj > 0.0 and lj > li * (1.0 + _LVL_MARGIN):
                    # the candidate's baseline is clearly larger: inside one
                    # family it is downstream of the target, not upstream.
                    continue
            cand.append(j)
            if len(cand) >= _NDRIVER:
                break
        if not cand:
            continue
        # a driver has to move at least as much as the target it explains
        cand = [j for j in cand if abs(float(a[j])) >= _MAG_RULE * ai]
        if not cand:
            continue
        cidx = np.asarray(cand, dtype=np.intp)
        design = np.column_stack([F, Z[:, cidx], np.ones(T, dtype=np.float64)])
        try:
            beta, _, _, _ = np.linalg.lstsq(design, Z[:, i], rcond=None)
        except Exception:
            continue
        if not np.all(np.isfinite(beta)):
            continue
        cj = beta[q:q + cidx.size]
        pred = float(np.dot(cj, a[cidx]))
        if not np.isfinite(pred):
            continue
        # the fraction of the target's own shift that the drivers account for
        frac = (pred * float(a[i])) / (float(a[i]) ** 2 + 1e-12)
        if np.isfinite(frac):
            explained[i] = float(np.clip(frac, 0.0, 1.0))
        np.add.at(csum, cidx, np.abs(cj))
    return explained, csum


def _containment_explained(P, shift, suffix, svc, changed_mask, m):
    """How much of each metric's incident shift its *parent* reproduces.

    A caller's reported latency contains the latency of the service it calls,
    so in the **raw units** of the healthy window the containing series
    carries the contained one with a gain of one:

        gain(i | k) = cov(i, k) / var(k)  ~=  1     (i contains k)
        gain(k | i) = cov(i, k) / var(i)  <  1     (attenuated)

    and the containing series has the larger variance.  This is an exact
    signature of composition, unlike a correlation, and -- crucially -- it is
    not destroyed by removing the system-wide common modes: the common offset
    of a caller and its callee *is* the containment.

    For every changed metric ``i`` the block looks for a changed metric ``k``
    of **another service** in the **same metric family** such that

      * the raw gain ``cov(i, k) / var(k)`` is at least ``_CD_GAIN``,
      * ``var(i) >= _CD_VAR * var(k)`` (i is the accumulator),
      * the raw correlation of the pair is at least ``_CD_CORR``,
      * the observed shifts have the same sign, and
      * the parent's observed shift **reproduces** the target's observed
        shift through the gain (the wave-fit test).

    The returned value is the fraction of the target's own shift that the
    parent accounts for: one for a clean reproduction.  A metric whose shift
    is inherited from the service it calls is a propagated symptom; the fault
    site's own change is inherited by nobody and therefore scores zero.

    Returns an array of length ``m`` with values in [0, 1]; zeros whenever
    the structure cannot be measured.
    """
    expl = np.zeros(m, dtype=np.float64)
    try:
        T = P.shape[0]
        if T < _CD_MINPRE or m < 4:
            return expl
        idx = np.flatnonzero(changed_mask)
        if idx.size < 2:
            return expl
        Pm = P - P.mean(axis=0, keepdims=True)
        C = (Pm.T @ Pm) / max(T - 1, 1)
        var = np.diag(C).copy()          # raw variance of every metric
        svc_arr = np.asarray(svc, dtype=object)
        suf_arr = np.asarray(suffix, dtype=object)
        for ii in range(idx.size):
            i = int(idx[ii])
            si = float(shift[i])
            if not np.isfinite(si) or abs(si) <= 0.0:
                continue
            vi = float(var[i])
            if not np.isfinite(vi) or vi <= 0.0:
                continue
            cand = idx[(svc_arr[idx] != svc_arr[i]) & (suf_arr[idx] == suf_arr[i])]
            if cand.size < 1:
                continue
            vk = var[cand]
            cov = C[i, cand]
            with np.errstate(divide="ignore", invalid="ignore"):
                gain = cov / vk
                corr = np.abs(cov) / np.sqrt(np.maximum(vi, 1e-300) * np.maximum(vk, 1e-300))
            ok = np.isfinite(gain) & np.isfinite(corr)
            ok &= (cov > 0.0)
            ok &= (vk > 0.0)
            ok &= (gain >= _CD_GAIN)
            ok &= (vi >= _CD_VAR * vk)
            ok &= (corr >= _CD_CORR)
            with np.errstate(divide="ignore", invalid="ignore"):
                pred = gain * shift[cand]
                denom = np.abs(si) + np.abs(pred)
                frac = np.where(denom > 0.0, np.abs(pred) / np.maximum(denom, 1e-300), 0.0)
                resid = np.abs(si - pred)
                tol = _CD_FIT * denom
            ok &= (np.sign(pred) == np.sign(si))
            ok &= (resid <= tol)
            ok &= np.isfinite(frac)
            if not np.any(ok):
                continue
            best = float(np.max(frac[ok]))
            if best > 0.0:
                expl[i] = best
    except Exception:
        return np.zeros(m, dtype=np.float64)
    return expl


def _containment_edges(P, shift, suffix, svc, changed_mask, group):
    """Directed containment edges among ``group`` under the raw-unit identity.

    ``group`` is a list of service names.  For every ordered pair ``(X, Y)``
    of services of the group the edge ``X contains Y`` is admitted when some
    changed metric ``i`` of ``X`` and some changed metric ``k`` of ``Y`` of
    the **same metric family** satisfy

      * the raw gain ``cov(i, k) / var(k)`` is at least ``_CA_GAIN``,
      * ``var(i) >= _CA_VAR * var(k)`` (the accumulator has the larger
        variance),
      * the raw correlation of the pair is at least ``_CA_CORR``,
      * the observed shifts have the same sign, and
      * the wave-fit test: the observed shift of ``i`` is reproduced by the
        observed shift of ``k`` through the gain.

    Returns the set of edges ``(X, Y)`` meaning "X contains Y".  Every edge
    is therefore about *this* incident and not about the healthy structure
    alone.
    """
    edges = set()
    try:
        T = P.shape[0]
        if T < _CA_MINPRE or len(group) < 2:
            return edges
        idx = np.flatnonzero(changed_mask)
        if idx.size < 2:
            return edges
        Pm = P - P.mean(axis=0, keepdims=True)
        C = (Pm.T @ Pm) / max(T - 1, 1)
        var = np.diag(C).copy()
        suf_arr = np.asarray(suffix, dtype=object)
        by_svc = {}
        for jj in idx:
            j = int(jj)
            by_svc.setdefault(svc[j], []).append(j)
        for X in group:
            for Y in group:
                if X == Y:
                    continue
                ok_pair = False
                for i in by_svc.get(X, ()):
                    if ok_pair:
                        break
                    vi = float(var[i])
                    if not np.isfinite(vi) or vi <= 0.0:
                        continue
                    for k in by_svc.get(Y, ()):
                        if suf_arr[i] != suf_arr[k]:
                            continue
                        vk = float(var[k])
                        if not np.isfinite(vk) or vk <= 0.0:
                            continue
                        cov = float(C[i, k])
                        if not np.isfinite(cov) or cov <= 0.0:
                            continue
                        gain = cov / vk
                        corr = abs(cov) / np.sqrt(vi * vk)
                        if gain < _CA_GAIN or corr < _CA_CORR:
                            continue
                        if vi < _CA_VAR * vk:
                            continue
                        si = float(shift[i])
                        sk = float(shift[k])
                        if not (np.isfinite(si) and np.isfinite(sk)):
                            continue
                        pred = gain * sk
                        denom = abs(si) + abs(pred)
                        if denom <= 0.0:
                            continue
                        if abs(si - pred) > _CA_FIT * denom:
                            continue
                        if np.sign(si) != np.sign(sk):
                            continue
                        ok_pair = True
                        break
                if ok_pair:
                    edges.add((X, Y))
    except Exception:
        return set()
    return edges


def _closure(edges, n):
    """Transitive closure of a small directed edge set."""
    reach = set(edges)
    for _ in range(max(n, 1)):
        grown = False
        for x, y in list(reach):
            for u, v in list(reach):
                if y == u and (x, v) not in reach:
                    reach.add((x, v))
                    grown = True
        if not grown:
            break
    return reach


def _containment_sink(P, shift, suffix, svc, changed_mask, ordered):
    """The deepest service of the leading group: the one that contains nobody.

    A caller's reported latency contains the latency of the service it calls,
    so in the **raw units** of the healthy window the containing series
    carries the contained one with a gain of about one and has the larger
    variance:

        gain(X | Y) = cov(X, Y) / var(Y)  ~=  1     (X contains Y)
        var(X) > var(Y)

    This identity is *directional* -- unlike a correlation it says which
    series contains which -- and it is not destroyed by removing the
    system-wide common modes, because the common offset of a caller and its
    callee *is* the containment.

    Under an additive propagation (a delay or a loss injected at one
    service's network interface) the affected services form a chain whose
    deepest member is the fault site: every caller of the fault site
    inherits its change and the fault site inherits nothing.  The deepest
    member is therefore the **unique** service of the leading group that
    contains no other member of that group, and the leader of the group is a
    *descendant* of it -- the leader is a victim of the very change it is
    loudest in.

    Every relation used here must also *reproduce* the incident shift of the
    contained series (the wave-fit test), so the relation is about *this*
    incident and not about the healthy structure alone.

    The contest is run **inside the leading group only**: the measurement of
    the inherited program shows the true service to be inside the leading
    three in every development case, so a *local* contest between two or
    three candidates is enough, and a mis-detection can then cost at most
    one position.

    Returns the name of the deepest service, or ``None`` whenever the
    evidence is not unambiguous.
    """
    try:
        T = P.shape[0]
        if T < _CA_MINPRE or len(svc) < 4:
            return None
        top = list(ordered[:_CA_TOP])
        if len(top) < 2:
            return None
        leader = top[0]
        idx = np.flatnonzero(changed_mask)
        if idx.size < 2:
            return None
        Pm = P - P.mean(axis=0, keepdims=True)
        C = (Pm.T @ Pm) / max(T - 1, 1)
        var = np.diag(C).copy()

        # the changed metrics, grouped by metric family
        fams = {}
        for jj in idx:
            j = int(jj)
            fams.setdefault(suffix[j], []).append(j)

        found = {}
        for suf, members in fams.items():
            by_svc = {}
            for j in members:
                by_svc.setdefault(svc[j], []).append(j)
            cand = [s for s in top if s in by_svc]
            if len(cand) < 2:
                continue
            # the representative of every candidate: its changed metric of
            # this family with the largest absolute incident shift
            rep = {}
            for s in cand:
                best = None
                for j in by_svc[s]:
                    if best is None:
                        best = j
                    elif abs(float(shift[j])) > abs(float(shift[best])):
                        best = j
                rep[s] = best

            edges = set()
            for a in range(len(cand)):
                for b in range(len(cand)):
                    if a == b:
                        continue
                    X = cand[a]
                    Y = cand[b]
                    i = rep[X]
                    k = rep[Y]
                    vi = float(var[i])
                    vk = float(var[k])
                    if not (np.isfinite(vi) and np.isfinite(vk)):
                        continue
                    if vi <= 0.0 or vk <= 0.0:
                        continue
                    cov = float(C[i, k])
                    if not np.isfinite(cov) or cov <= 0.0:
                        continue
                    gain = cov / vk
                    corr = abs(cov) / np.sqrt(vi * vk)
                    if gain < _CA_GAIN or corr < _CA_CORR:
                        continue
                    if vi < _CA_VAR * vk:
                        continue
                    si = float(shift[i])
                    sk = float(shift[k])
                    if not (np.isfinite(si) and np.isfinite(sk)):
                        continue
                    pred = gain * sk
                    denom = abs(si) + abs(pred)
                    if denom <= 0.0:
                        continue
                    if abs(si - pred) > _CA_FIT * denom:
                        continue
                    edges.add((X, Y))

            if not edges:
                continue

            # transitive closure of the containment relation
            reach = set(edges)
            for _ in range(len(cand)):
                grown = False
                for x, y in list(reach):
                    for u, v in list(reach):
                        if y == u and (x, v) not in reach:
                            reach.add((x, v))
                            grown = True
                if not grown:
                    break

            # the sink: the unique member that contains nobody of the group
            sinks = [s for s in cand
                     if not any(y == s for (_x, y) in edges)
                     and any(y == s for (_x, y) in reach)]
            if len(sinks) != 1:
                continue
            sink = sinks[0]
            if sink == leader:
                continue
            # the leader must be provably *downstream* of the sink, i.e. the
            # leader is a descendant of the sink and therefore a victim
            if (leader, sink) not in reach:
                continue
            found[suf] = sink

        vals = set(found.values())
        if len(vals) != 1:
            return None
        return vals.pop()
    except Exception:
        return None


def _containment_reaches(P, shift, suffix, svc, changed_mask, ordered,
                         want, source, top):
    """True iff ``want`` transitively contains ``source``.

    The relation is the raw-unit containment identity of the healthy window:
    the containing series carries the contained one with a gain of about one
    and has the larger variance, and the relation is only admitted when it
    *reproduces* the observed incident shift of the contained series.

    It is used as a **certification**: a candidate may only be moved to the
    front of the ranking when the program's own relation says that the
    current leader of the ranking is a *descendant* of the candidate, i.e.
    that the leader is a victim of the very change the candidate carries.
    The relation is estimated on the leading ``top`` services so that a chain
    whose intermediate member lies outside the leading group is still seen.
    """
    try:
        if want is None or source is None or want == source:
            return False
        group = [s for s in list(ordered[:top])]
        if want not in group or source not in group:
            return False
        edges = _containment_edges(P, shift, suffix, svc, changed_mask, group)
        if not edges:
            return False
        reach = _closure(edges, len(group))
        return (want, source) in reach
    except Exception:
        return False


def _leader_private_signature(suffix, svc, shift, own_rel, change, persist,
                              fam_ratio, leader):
    """True iff the leader owns a change that lies *alone* in its cell.

    A victim of a propagation carries the **shared** symptom channel: the
    change that many services show together.  It cannot carry a change that
    lies alone in its ``(metric family, direction)`` cell of the affected
    set, because nobody else is affected by *its* fault.  A local fault does
    leave exactly such a trace -- the saturated ``cpu``/``mem``/``disk``
    metric of the fault site, a cell no other service occupies.

    So a leader that owns a private signature is the origin of a local fault
    and no other origin hypothesis may be delivered.  The signature must also
    be *substantial*: at least ``_ROT_VETO_OWN`` of the metric's own baseline
    **and** at least ``_ROT_VETO_FR`` of the family's typical magnitude, so
    that an incidental private blip of a victim cannot veto a good rotation.
    """
    try:
        moved = ((change >= _CELL_SIGMA)
                 & (persist >= _CELL_PERSIST)
                 & (own_rel >= _CELL_REL))
        idx = np.flatnonzero(moved)
        if idx.size < 2:
            return False
        cell = {}
        for jj in idx:
            j = int(jj)
            s = svc[j]
            if shift[j] > 0.0:
                sg = 1.0
            elif shift[j] < 0.0:
                sg = -1.0
            else:
                continue
            key = (suffix[j], sg)
            d = cell.setdefault(key, {})
            v = float(own_rel[j])
            if v > d.get(s, (0.0, -1))[0]:
                d[s] = (v, j)
        for _key, d in cell.items():
            if leader in d:
                v, j = d[leader]
                if len(d) == 1 and v >= _ROT_VETO_OWN \
                        and float(fam_ratio[j]) >= _ROT_VETO_FR:
                    return True
        return False
    except Exception:
        return False


def _leader_isolated_cell(suffix, svc, shift, change, persist, leader):
    """True iff the leader owns a change that lies *alone* in its cell.

    This is the **magnitude free** form of the private-signature test.  The
    inherited ``_leader_private_signature`` additionally requires the private
    change to be at least half of the metric's own baseline and half of the
    family's typical magnitude; the archive measured that this magnitude
    requirement is exactly what defeats the test on a saturated resource
    metric (a metric that saturates at 90 % moves by only about a tenth of
    its own baseline, and the inherited test then abstains although the
    metric is an unambiguous private signature).

    The test here keeps the *isolation* -- a change that lies alone in its
    ``(metric family, direction)`` cell of the affected set -- and drops the
    magnitude.  A propagated symptom is a change that many services share; a
    local fault leaves a change alone in its cell.  A leader that owns such a
    change is the origin of a local fault and is never displaced.

    The significance floor is the inherited one (``_CELL_SIGMA`` noise
    sigmas and ``_CELL_PERSIST`` persistence), so an incidental blip does not
    qualify.
    """
    try:
        moved = ((change >= _CELL_SIGMA) & (persist >= _CELL_PERSIST))
        idx = np.flatnonzero(moved)
        if idx.size < 2:
            return False
        cell = {}
        for jj in idx:
            j = int(jj)
            s = svc[j]
            if shift[j] > 0.0:
                sg = 1.0
            elif shift[j] < 0.0:
                sg = -1.0
            else:
                continue
            key = (suffix[j], sg)
            cell.setdefault(key, set()).add(s)
        for _key, members in cell.items():
            if leader in members and len(members) == 1:
                return True
        return False
    except Exception:
        return False


def _wc_own_trace(suffix, svc, shift, change, persist, fam, source):
    """True iff ``source`` shows a trace of its own outside the wave family.

    A pure victim of a propagation carries only the **shared** wave: the
    change that every service of the chain shows together.  The fault site
    carries something the wave cannot explain -- its own counter falling (or
    stalling) in another metric family.

    The trace is allowed to be shared with a few services, because the
    archive measured that in the loss regime the fault site's own trace is
    shared with the services the fault site *calls*; what is not allowed is a
    trace that the whole wave shares, because that is the wave again and
    would make the test vacuous.  The significance floor is the inherited
    one (``_CELL_SIGMA`` noise sigmas and ``_CELL_PERSIST`` persistence), so
    an incidental blip does not qualify.
    """
    try:
        moved = ((change >= _CELL_SIGMA) & (persist >= _CELL_PERSIST))
        idx = np.flatnonzero(moved)
        if idx.size < 2:
            return False
        cell = {}
        for jj in idx:
            j = int(jj)
            if shift[j] > 0.0:
                sg = 1.0
            elif shift[j] < 0.0:
                sg = -1.0
            else:
                continue
            key = (suffix[j], sg)
            d = cell.setdefault(key, set())
            d.add(svc[j])
        for jj in idx:
            j = int(jj)
            if svc[j] != source or suffix[j] == fam:
                continue
            sg = 1.0 if shift[j] > 0.0 else -1.0
            members = cell.get((suffix[j], sg), ())
            if len(members) <= _WC_CELL_MAX:
                return True
        return False
    except Exception:
        return False


def _rotate_within(ordered, pick, top):
    """Move ``pick`` to the front of the leading group by a rotation.

    The services that were above ``pick`` move down by exactly one position
    and every other service keeps its place, so the **set** of the leading
    services is unchanged.  The operation is a no-op when ``pick`` is already
    first or lies outside the leading group.
    """
    try:
        if pick is None or len(ordered) < 2:
            return ordered
        pos = ordered.index(pick)
        if pos <= 0 or pos >= top:
            return ordered
        return [pick] + ordered[:pos] + ordered[pos + 1:]
    except Exception:
        return ordered


def _wc_edges(P, shift, suffix, svc, changed_mask, group):
    """Containment edges (X contains Y) over an arbitrary ``group``.

    This is the inherited raw-unit containment identity

        gain(X | Y) = cov(X, Y) / var(Y)  ~=  1     (X contains Y)
        var(X) > var(Y)                              (X is the accumulator)

    with two differences from the inherited ``_containment_edges``:

      * the group is not restricted to the leading services -- the whole
        wave is admitted -- so a chain whose intermediate members are not
        among the loudest services is still visible; and

      * the wave-fit tolerance is wider (``_WC_FIT``) because a container may
        accumulate the contained change from several branches, or add its own
        delay, so its own observed shift may legitimately be several times
        the contained one.

    Everything else -- the gain band, the variance ratio, the correlation
    floor, the sign agreement and the requirement that *both* endpoints
    changed -- is the inherited criterion.
    """
    edges = set()
    try:
        T = P.shape[0]
        if T < _WC_MINPRE or len(group) < 2:
            return edges
        idx = np.flatnonzero(changed_mask)
        if idx.size < 2:
            return edges
        Pm = P - P.mean(axis=0, keepdims=True)
        C = (Pm.T @ Pm) / max(T - 1, 1)
        var = np.diag(C).copy()
        suf_arr = np.asarray(suffix, dtype=object)
        by_svc = {}
        for jj in idx:
            j = int(jj)
            by_svc.setdefault(svc[j], []).append(j)
        for X in group:
            for Y in group:
                if X == Y:
                    continue
                ok_pair = False
                for i in by_svc.get(X, ()):
                    if ok_pair:
                        break
                    vi = float(var[i])
                    if not np.isfinite(vi) or vi <= 0.0:
                        continue
                    for k in by_svc.get(Y, ()):
                        if suf_arr[i] != suf_arr[k]:
                            continue
                        vk = float(var[k])
                        if not np.isfinite(vk) or vk <= 0.0:
                            continue
                        cov = float(C[i, k])
                        if not np.isfinite(cov) or cov <= 0.0:
                            continue
                        gain = cov / vk
                        if gain < _WC_GAIN or gain > _WC_GAIN_MAX:
                            continue
                        corr = abs(cov) / np.sqrt(vi * vk)
                        if corr < _WC_CORR:
                            continue
                        if vi < _WC_VAR * vk:
                            continue
                        si = float(shift[i])
                        sk = float(shift[k])
                        if not (np.isfinite(si) and np.isfinite(sk)):
                            continue
                        if np.sign(si) != np.sign(sk):
                            continue
                        pred = gain * sk
                        denom = abs(si) + abs(pred)
                        if denom <= 0.0:
                            continue
                        if abs(si - pred) > _WC_FIT * denom:
                            continue
                        ok_pair = True
                        break
                if ok_pair:
                    edges.add((X, Y))
    except Exception:
        return set()
    return edges


def _wc_reach(edges, nodes):
    """Transitive closure of a directed edge set (depth first, linear).

    The inherited ``_closure`` is quadratic in the number of edges and is
    therefore only usable for the tiny groups of the inherited blocks; the
    whole wave can have dozens of services, so this closure is used here.
    """
    reach = set(edges)
    adj = {}
    for (x, y) in edges:
        adj.setdefault(x, []).append(y)
    for s in nodes:
        seen = set()
        stack = list(adj.get(s, ()))
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            for v in adj.get(u, ()):
                if (s, v) not in reach:
                    reach.add((s, v))
                if v not in seen:
                    stack.append(v)
    return reach


def _wc_source(P, shift, suffix, svc, changed_mask, level, change, persist,
               ordered):
    """The **source of the leader's own wave**.

    The physical statement.  A network fault hands one perturbation along the
    request path.  The service that holds the perturbation is the fault site;
    every service above it in the chain inherits the perturbation unchanged,
    which is why the victim's change is as loud as the origin's and why the
    magnitude channel cannot separate them.  The leader of the ranking is
    the *downstream* end of that chain and the fault site is its *upstream*
    end.

    The instrument.  The raw-unit containment identity of the healthy window
    -- the only relation in the archive that survives an additive
    propagation -- says which series contains which:

        gain(X | Y) = cov(X, Y) / var(Y)  ~=  1     (X contains Y)
        var(X) > var(Y)

    applied to the **whole wave** rather than to the leading group.  The
    wave is the set of services that carry the leader's own channel (the
    metric family of the leader's loudest changed metric), because that is
    the channel in which the leader is a victim; the leader's chain is then
    resolved *through* the wave, so a chain whose intermediate members are
    not among the loudest services is still visible.

    The question.  Among the services the leader transitively contains, the
    **source** is the one that contains no other of them: the upstream end
    of the leader's chain.  If the wave has several such sources the level
    law breaks the tie (the upstream member of a chain carries the smaller
    baseline), and a flat hierarchy abstains.

    Returns the name of the source service, or ``None`` whenever the
    evidence is not unambiguous.
    """
    try:
        T = P.shape[0]
        if T < _WC_MINPRE or len(ordered) < 2:
            return None
        leader = ordered[0]
        m = len(svc)

        # the leader's own channel: the family of its loudest changed metric
        li = -1
        best = -1.0
        for j in range(m):
            if svc[j] != leader or not changed_mask[j]:
                continue
            a = abs(float(shift[j]))
            if a > best + 1e-12:
                best = a
                li = j
        if li < 0:
            return None
        fam = suffix[li]

        # the wave: every service that carries the leader's channel
        wave = []
        seen = set()
        levels = {}
        for j in range(m):
            if not changed_mask[j] or suffix[j] != fam:
                continue
            s = svc[j]
            if s not in seen:
                seen.add(s)
                wave.append(s)
                levels[s] = float(level[j])
        if len(wave) < 3:
            return None

        edges = _wc_edges(P, shift, suffix, svc, changed_mask, wave)
        if not edges:
            return None
        reach = _wc_reach(edges, wave)

        # the services the leader transitively contains
        desc = [y for y in wave if (leader, y) in reach]
        if not desc:
            return None

        # the source of that chain: a member that contains no other member
        srcs = []
        for y in desc:
            inner = False
            for z in desc:
                if z == y:
                    continue
                if (y, z) in reach:
                    inner = True
                    break
            if not inner:
                srcs.append(y)
        if not srcs:
            return None
        cand = None
        if len(srcs) == 1:
            cand = srcs[0]
        else:
            # several sources: the level law (the upstream member of a chain
            # carries the smaller baseline) breaks the tie, and a flat
            # hierarchy carries no order at all
            vals = sorted(levels[s] for s in srcs
                          if s in levels and levels[s] > 0.0)
            if not vals:
                return None
            if len(vals) > 1 and vals[0] > (1.0 - _WC_LEVEL_GAP) * vals[1]:
                return None
            for s in srcs:
                if (s in levels and levels[s] > 0.0
                        and levels[s] <= vals[0] + 1e-12):
                    cand = s
                    break
        if cand is None:
            return None
        # the source of the chain must not be a pure victim of the wave: it
        # has to show a trace of its own outside the wave's family
        if not _wc_own_trace(suffix, svc, shift, change, persist, fam, cand):
            return None
        return cand
    except Exception:
        return None


def _upstream_factors(svc, suffix, level, own_rel, aff_mask, R):
    """Bounded demotion of the services that sit downstream in the affected set.

    Along a call chain the observable's level accumulates towards the caller,
    so the *upstream* member of a dependency pair is the one with the smaller
    baseline.  That principle is used here as an explicit orientation of the
    affected set:

      * a relation is only considered inside one metric family (levels are
        only comparable inside a family),
      * it is only accepted when the two services' metrics are strongly
        related in the pre-incident window (residual correlation, i.e. after
        the shared load factor has been removed),
      * it is only accepted when the baseline levels differ clearly (the
        downstream level must be at least 30 % larger), and when the upstream
        member is at least as anomalous relative to *its own* baseline as the
        downstream one (the same principle the self-relative view uses).

    The transitive closure of the accepted relations gives, for every service
    of the affected set, the number of affected services that precede it.  A
    service with ``d`` upstream services loses a factor of
    ``_UP_DEMOTE ** min(d, _UP_MAX_DEPTH)``; a service that nothing precedes
    keeps its full score.  The intervention is at the **service** level,
    which is what the objective scores.

    Returns a dict ``{service: factor}``; empty when the affected set is too
    small to carry any relation.
    """
    out = {}
    try:
        aff = np.flatnonzero(aff_mask)
        if aff.size < 2:
            return out
        usvc = []
        by_svc = {}
        for j in aff:
            j = int(j)
            s = svc[j]
            if s not in by_svc:
                by_svc[s] = []
                usvc.append(s)
            by_svc[s].append(j)
        n = len(usvc)
        if n < 2:
            return out
        down = np.zeros((n, n), dtype=bool)
        for ia in range(n):
            sa = usvc[ia]
            for ib in range(n):
                if ia == ib:
                    continue
                sb = usvc[ib]
                best = None
                for i in by_svc[sa]:
                    for k in by_svc[sb]:
                        if suffix[i] != suffix[k]:
                            continue
                        r = abs(float(R[i, k]))
                        if r < _UP_CORR:
                            continue
                        if best is None or r > best[0]:
                            best = (r, i, k)
                if best is None:
                    continue
                _r, i, k = best
                li = float(level[i])
                lk = float(level[k])
                if li <= 0.0 or lk <= 0.0:
                    continue
                oi = float(own_rel[i])
                ok = float(own_rel[k])
                if li < lk * (1.0 - _UP_LEVEL) and oi >= _UP_OWN * ok:
                    down[ia, ib] = True      # sa is upstream of sb
                elif lk < li * (1.0 - _UP_LEVEL) and ok >= _UP_OWN * oi:
                    down[ib, ia] = True      # sb is upstream of sa
        if not down.any():
            return out
        df = down.astype(np.float64)
        reach = df.copy()
        for _ in range(3):
            reach = ((reach @ df) > 0.0)
            reach = reach | (df > 0.0)
        depth = reach.sum(axis=0)
        for ib, s in enumerate(usvc):
            d = int(min(depth[ib], _UP_MAX_DEPTH))
            if d > 0:
                out[s] = _UP_DEMOTE ** d
        return out
    except Exception:
        return {}


def _origin_service(suffix, svc, shift, own_rel, change, persist):
    """The service that carries the fault's own, isolated signature.

    A fault produces a **propagated** symptom (a change that many services
    share) *and* a **direct signature** at the fault site.  For a network
    fault the direct signature has the opposite direction to the propagated
    one -- the fault site's own throughput drops while every caller's latency
    rises -- and it belongs to a different metric family.  The signature is
    therefore the only change in its (family, direction) *cell* of the
    affected set, and the service that owns such an exclusive cell is the
    origin of the incident.

    Every guard is conjunctive, so the rule is inert unless the evidence is
    unambiguous:

      * the metric must have moved (noise-relative change, persistence and a
        non-trivial own-level-relative change),
      * the dominant cell (the change shared by the most services) must span
        at least ``_CELL_DOM`` services, i.e. there must be a propagated cone
        for a signature to dissent from,
      * the candidate cell must be isolated (at most ``_CELL_ISOL`` services)
        and concentrated in the candidate service,
      * the candidate service must belong to the incident: it either moved in
        more than one cell, or it is a member of a widely propagated cell, or
        it carries a **strong** isolated signature of its own (a large
        own-baseline-relative change that is significant in noise terms and
        persistent).  The last alternative matters because a fault injected
        at a network interface can leave the fault site's own latency
        untouched, in which case the only trace of the origin is its own
        throughput -- one cell, one service,
      * the signature's magnitude is measured **relative to the metric's own
        baseline**, not to the family scale, because the family scale is
        dominated by the big services and would suppress exactly the small
        service whose throughput drop is the fault's own signature.

    Returns ``(service, weight)`` with ``weight`` in [0, 1]; ``(None, 0.0)``
    whenever the evidence is not unambiguous.
    """
    moved = ((change >= _CELL_SIGMA)
             & (persist >= _CELL_PERSIST)
             & (own_rel >= _CELL_REL))
    idx = np.flatnonzero(moved)
    if idx.size < 2:
        return None, 0.0

    # cells of the affected set: (metric family, direction) -> service -> mass
    cells = {}
    footprint = {}
    for jj in idx:
        j = int(jj)
        s = svc[j]
        if shift[j] > 0.0:
            sg = 1.0
        elif shift[j] < 0.0:
            sg = -1.0
        else:
            continue
        key = (suffix[j], sg)
        d = cells.setdefault(key, {})
        v = float(own_rel[j])
        if v > d.get(s, (0.0, -1))[0]:
            d[s] = (v, j)
        footprint.setdefault(s, set()).add(key)
    if len(cells) < 2:
        return None, 0.0

    # the dominant cell: the change that the most services share
    dom_key = None
    dom_n = 0
    dom_mass = 0.0
    for k, d in cells.items():
        n = len(d)
        mass = float(sum(v for v, _ in d.values()))
        if dom_key is None or (n, mass) > (dom_n, dom_mass):
            dom_key = k
            dom_n = n
            dom_mass = mass
    if dom_key is None or dom_n < _CELL_DOM:
        return None, 0.0
    dom = cells[dom_key]
    dom_med = float(np.median(np.asarray([v for v, _ in dom.values()],
                                         dtype=np.float64)))

    best_s = None
    best_mass = 0.0
    for key, d in cells.items():
        if key == dom_key:
            continue
        if key[0] == dom_key[0]:
            # the fault's own signature belongs to a *different* metric family
            # than the propagated symptom; a same-family cell that moved the
            # other way is not a signature.
            continue
        n = len(d)
        if n > _CELL_ISOL:
            continue                       # not isolated
        tot = float(sum(v for v, _ in d.values()))
        if tot <= 0.0:
            continue
        for s, (v, j) in d.items():
            conc = 1.0 if n == 1 else v / tot
            if conc < _CELL_CONC:
                continue                   # not concentrated in this service
            fp = footprint.get(s, ())
            propagated = False
            for k in fp:
                if len(cells[k]) >= _CELL_DOM:
                    propagated = True
                    break
            strong = (v >= _CELL_STRONG
                      and change[j] >= _CELL_STRONG_SIGMA
                      and persist[j] >= _CELL_STRONG_PERSIST)
            if len(fp) < 2 and not propagated and not strong:
                continue                   # not part of the incident
            mass = v * conc
            if mass > best_mass:
                best_mass = mass
                best_s = s
    if best_s is None or best_mass <= 0.0:
        return None, 0.0

    ref = dom_med if dom_med > 0.0 else best_mass
    w = float(min(1.0, best_mass / (_CELL_REF * ref))) if ref > 0.0 else 0.0
    if w <= 0.0:
        return None, 0.0
    return best_s, w


def _cone_origin(suffix, svc, shift, own_rel, change, persist, level, score):
    """The most upstream member of the propagation cone.

    A fault injected at the network interface of one service moves every
    service of the affected chain by roughly the **same absolute amount**,
    so the members of the propagation cone are near-tied in the size of their
    shift and the magnitude of the change cannot separate them.  What does
    separate them is the **baseline level**: along a call chain the level of
    the observable accumulates towards the caller, so the most upstream
    member of the cone -- the fault site -- carries the smallest baseline of
    the cone and therefore the largest change relative to its own level.

    The rule is conjunctive and therefore inert unless *all* of the following
    hold:

      * the dominant cell of the affected set (the change that the most
        services share) spans at least ``_CELL_DOM`` services, i.e. there is
        a propagation cone at all;
      * the members of the cone are near-tied in the **absolute** size of
        their shift (no member exceeds ``_CONE_TIE`` times the median), i.e.
        the change really was handed on unchanged rather than being a local
        fault plus its consequences;
      * the smallest baseline of the cone is clearly below the next one (at
        least ``_CONE_GAP``), i.e. the level hierarchy carries an order at
        all -- a flat hierarchy carries no information;
      * the affected metric with the **largest overall score** belongs to
        the cone, i.e. the propagation is the dominant effect of the
        incident.  This is the guard that keeps the rule away from the
        resource faults, where the fault site's own resource metric changes
        by an order of magnitude more than any propagated symptom and does
        not live in the latency cone.

    The head is returned together with a weight in [0, 1] that grows with
    the size of the level gap.  ``(None, 0.0)`` is returned whenever the
    evidence is not unambiguous.
    """
    try:
        moved = ((change >= _CELL_SIGMA)
                 & (persist >= _CELL_PERSIST)
                 & (own_rel >= _CELL_REL))
        idx = np.flatnonzero(moved)
        if idx.size < 2:
            return None, 0.0

        # cells of the affected set: (metric family, direction) -> service
        cells = {}
        for jj in idx:
            j = int(jj)
            s = svc[j]
            if shift[j] > 0.0:
                sg = 1.0
            elif shift[j] < 0.0:
                sg = -1.0
            else:
                continue
            key = (suffix[j], sg)
            d = cells.setdefault(key, {})
            v = float(own_rel[j])
            if v > d.get(s, (0.0, -1))[0]:
                d[s] = (v, j)
        if len(cells) < 2:
            return None, 0.0

        # the dominant cell: the change that the most services share
        dom_key = None
        dom_n = 0
        dom_mass = 0.0
        for k, d in cells.items():
            n = len(d)
            mass = float(sum(v for v, _ in d.values()))
            if dom_key is None or (n, mass) > (dom_n, dom_mass):
                dom_key = k
                dom_n = n
                dom_mass = mass
        if dom_key is None or dom_n < _CELL_DOM:
            return None, 0.0
        cone = cells[dom_key]
        if len(cone) < 2:
            return None, 0.0

        # the absolute size and the baseline level of every cone member
        rep = {}
        for s, (v, j) in cone.items():
            rep[s] = (abs(float(shift[j])), float(level[j]))
        mags = sorted(x[0] for x in rep.values())
        med = float(np.median(np.asarray(mags, dtype=np.float64)))
        if med <= 0.0 or mags[-1] > _CONE_TIE * med:
            return None, 0.0

        # the head: the cone member with the smallest baseline level
        order = sorted(rep.items(), key=lambda kv: (kv[1][1], kv[0]))
        head = order[0][0]
        if len(order) > 1:
            l0 = order[0][1][1]
            l1 = order[1][1][1]
            if l0 <= 0.0 or l1 <= 0.0:
                return None, 0.0
            if l0 > (1.0 - _CONE_GAP) * l1:
                return None, 0.0
            gap = (l1 - l0) / max(l1, 1e-12)
        else:
            gap = 1.0

        # the propagation must be the dominant effect of the incident
        best = None
        for jj in idx:
            j = int(jj)
            if best is None or float(score[j]) > float(score[best]):
                best = j
        if best is None:
            return None, 0.0
        if svc[best] not in cone:
            return None, 0.0

        w = float(min(1.0, gap / _CONE_GAP_FULL))
        if w <= 0.0:
            return None, 0.0
        return head, w
    except Exception:
        return None, 0.0


def _rank_impl(data, inject_time, metadata):
    start = _clock.time()
    names, X, t = _prep(data)
    m = len(names)
    if m == 0:
        return []

    # ---------------------------------------------------------------- split
    try:
        it = float(inject_time)
    except Exception:
        it = float(np.median(t))
    pre_idx = np.flatnonzero(t < it)
    post_idx = np.flatnonzero(t >= it)
    if pre_idx.size < 20 or post_idx.size < 10:
        order = np.argsort(t, kind="stable")
        cut = int(0.6 * order.size)
        if cut < 5 or order.size - cut < 5:
            return list(names)
        pre_idx = order[:cut]
        post_idx = order[cut:]
    P = X[pre_idx]
    Q = X[post_idx]
    T = P.shape[0]

    # ------------------------------------------------------- family scales
    suffix = []
    for n in names:
        suffix.append(n.rsplit("_", 1)[-1] if "_" in n else n)
    fam_members = {}
    for j, suf in enumerate(suffix):
        fam_members.setdefault(suf, []).append(j)
    fs = np.zeros(m, dtype=np.float64)
    for suf, idxs in fam_members.items():
        vals = np.abs(P[:, idxs]).ravel()
        nz = vals[vals > 0.0]
        s1 = float(np.percentile(vals, 75.0)) if vals.size else 0.0
        s2 = float(np.median(nz)) if nz.size else 0.0
        v = s1 if s1 > s2 else s2
        for j in idxs:
            fs[j] = v
    allv = np.abs(P).ravel()
    allnz = allv[allv > 0.0]
    gscale = float(np.median(allnz)) if allnz.size else 0.0
    if gscale <= 0.0:
        gscale = 1.0
    fs = np.where(fs > 0.0, fs, gscale)
    svc = [_service_of(n) for n in names]

    # -------------------------------------------------- robust statistics
    m0 = np.median(P, axis=0)
    mad = np.median(np.abs(P - m0), axis=0)
    q25 = np.percentile(P, 25.0, axis=0)
    q75 = np.percentile(P, 75.0, axis=0)
    p05 = np.percentile(P, 5.0, axis=0)
    p95 = np.percentile(P, 95.0, axis=0)
    s_raw = np.maximum(1.4826 * mad, (q75 - q25) / 1.349)
    # A metric may never be judged against a scale smaller than 0.1% of the
    # typical magnitude of its own metric type: this is what stops a constant
    # (or near constant) series from producing an unbounded z-score.
    s_eff = np.maximum(s_raw, 1e-3 * fs)
    s_eff = np.where(s_eff > 0.0, s_eff, 1e-12)

    shift = np.median(Q, axis=0) - m0           # signed raw shift
    z_med = np.abs(shift) / s_eff
    peak = np.maximum(np.max(Q, axis=0) - p95, p05 - np.min(Q, axis=0)) / s_eff
    change = np.maximum(z_med, 0.7 * np.maximum(peak, 0.0))
    fam_ratio = np.abs(shift) / (fs + 1e-12)

    # Strictly monotone soft saturation: unlike a clip this keeps the relative
    # order of the saturated metrics, which is where the hard cases live.
    a_std = change / (change + _A_STD_K)
    a_fam = fam_ratio / (fam_ratio + _A_FAM_K)
    above = (Q > p95).mean(axis=0)
    below = (Q < p05).mean(axis=0)
    persist = np.maximum(above, below)
    mag = (0.5 * a_std + 0.5 * a_fam) * (0.55 + 0.45 * persist)

    # ------------------------------------------------------ own-scale view
    # The own scale of a metric is its own baseline, floored at three robust
    # sigmas of its own noise.  It is the right normaliser for the question
    # "did *this* series change?", because the family scale is a cross-service
    # quantity: a service whose own magnitude is far below the family's
    # typical magnitude (the small service whose own throughput drop is the
    # direct signature of a network fault) is invisible to every family-scaled
    # test.
    level = np.abs(np.median(P, axis=0))
    own_scale = np.maximum(level, _OWN_FLOOR_SD * s_raw)
    own_valid = own_scale > 1e-12
    own_ratio = np.zeros(m, dtype=np.float64)
    if own_valid.any():
        own_ratio[own_valid] = np.minimum(
            np.abs(shift[own_valid]) / own_scale[own_valid], _OWN_CAP)
    own_sig = own_valid & (change >= _OWN_SIGMA)
    own_moved = own_sig & (own_ratio >= _OWN_GATE)

    # ------------------------------------------------- self-relative impact
    # A fault that propagates along a call chain moves every service of the
    # chain by roughly the same absolute amount, so the chain members are
    # near-tied in every scale-relative magnitude above and the fault site is
    # pushed down the list by the tie-break.  They differ in their baseline:
    # along a chain the level of the observable accumulates towards the
    # service level indicator, so the fault site has the smallest baseline of
    # the affected set and hence the largest change relative to its own
    # level.  This view therefore breaks the tie in the right direction.
    level_eff = np.maximum(level, _REL_FLOOR * fs)
    rel_old = np.minimum(np.abs(shift) / (level_eff + 1e-12), _REL_CAP)
    rel = np.where(own_valid, own_ratio, rel_old)
    sig = (fam_ratio >= _REL_SIG) | own_moved
    strong_sig = sig & (change >= _OWN_SIGMA)
    pool = np.flatnonzero(strong_sig) if strong_sig.any() else np.flatnonzero(sig)
    if pool.size:
        ref = float(rel[pool].max())
    else:
        ref = float(rel.max()) if rel.size else 0.0
    if ref > 0.0:
        rel_norm = np.clip(rel / ref, 0.0, 1.0)
    else:
        rel_norm = np.zeros(m, dtype=np.float64)
    mag = mag * (_REL_LO + (_REL_HI - _REL_LO) * rel_norm)

    # The own-level-relative magnitude, measured against the metric's *own*
    # baseline rather than against the family scale.  The family scale is
    # dominated by the large services and therefore suppresses exactly the
    # small service whose own throughput drop is a fault's direct signature.
    own_rel = np.zeros(m, dtype=np.float64)
    pos_level = level > 0.0
    if pos_level.any():
        own_rel[pos_level] = np.minimum(
            np.abs(shift[pos_level]) / level[pos_level], _OWN_REL_CAP)

    # -------------------------------------------- direct-effect attribution
    # ``causal`` combines two scale-free pieces: the fraction of a metric's
    # own change that its normal drivers do not account for, and the
    # propagation mass, i.e. how much of the incident-wide deviation this
    # metric accounts for in the *other* services.  The origin of the incident
    # keeps a large unexplained change and the largest propagation mass; a
    # propagated symptom is explained away by its cause.
    causal = np.zeros(m, dtype=np.float64)
    struct = None
    try:
        gate_fam = np.minimum(1.0, np.abs(shift) / (_GATE * fs + 1e-12))
        # The "did it change" test is normalised by the metric's own scale as
        # well: a metric that moved by a large fraction of its own baseline is
        # changed, even when the family it belongs to is dominated by much
        # larger services.  Without this a small service's own signature is
        # treated as "no change at all" and the causal factor demotes it.
        gate_own = np.where(own_sig, np.minimum(1.0, own_ratio / _GATE), 0.0)
        gate = np.maximum(gate_fam, gate_own)
        # defaults: every metric is unexplained and exerts no influence, so the
        # term degenerates to the plain "did it change" gate of the inherited
        # program when the structure cannot be estimated.
        uf = np.ones(m, dtype=np.float64)
        imp = np.zeros(m, dtype=np.float64)
        if T >= 40 and m >= 4 and (_clock.time() - start) < 55.0:
            sd = np.maximum(P.std(axis=0), 1e-2 * fs)
            sd = np.maximum(sd, 1e-12)
            a_vec = np.clip(shift / sd, -25.0, 25.0)
            # A metric that moved may explain another one.  The family-scaled
            # gate alone misses the small service whose own drop is the
            # fault's direct signature, so the own-scaled test is used as well.
            changed = np.flatnonzero((fam_ratio >= _GATE) | own_moved)
            if changed.size >= 2:
                changed_mask = np.zeros(m, dtype=bool)
                changed_mask[changed] = True
                struct = _structure(P, m0, sd, m)
                explained, csum = _direct_effects(
                    P, m0, sd, svc, a_vec, changed, changed_mask,
                    level=level, suffix=suffix, use_level=True, struct=struct)
                if not np.any(explained > 0.0):
                    # The level orientation found nothing at all in this
                    # window, i.e. it carries no information here; fall back
                    # to the inherited (unoriented) attribution.
                    explained, csum = _direct_effects(
                        P, m0, sd, svc, a_vec, changed, changed_mask,
                        struct=struct)
                uf = 1.0 - explained
                impact = np.abs(a_vec) * csum
                imax = float(impact.max()) if impact.size else 0.0
                imp = impact / imax if imax > 0.0 else np.zeros(m)
        causal = gate * np.minimum(1.0, uf + _IMP_W * imp)
    except Exception:
        try:
            causal = np.minimum(1.0, np.abs(shift) / (_GATE * fs + 1e-12))
        except Exception:
            causal = np.zeros(m, dtype=np.float64)

    # ------------------------------------- new: containment-explained demotion
    # A propagated symptom's incident shift is *inherited* from the service it
    # calls.  The inherited attribution can only recognise that inheritance
    # when the driver is strongly correlated with the target in the healthy
    # window *after* the common modes have been removed, which is exactly what
    # an additive propagation destroys.  The raw-unit containment signature
    # (the containing series carries the contained one with a gain of one) is
    # not destroyed that way, so it can find the inheritance the inherited
    # block misses.  The result is applied as a *cap* on the inherited causal
    # factor: a symptom that has been positively identified as inherited can
    # no longer keep the full causal factor it wrongly had, and every decision
    # the inherited block already made is preserved.
    try:
        if (_clock.time() - start) < 70.0:
            cmask = (fam_ratio >= _GATE) | own_moved
            if int(np.count_nonzero(cmask)) >= 2:
                expl_cont = _containment_explained(
                    P, shift, suffix, svc, cmask, m)
                if np.any(expl_cont > 0.0):
                    cap = 1.0 - _CD_W * expl_cont
                    causal = np.minimum(causal, cap)
    except Exception:
        pass

    # ------------------------------------------- symmetric peer isolation
    # Kept at a small weight: it is informative when a change is isolated
    # (resource faults) and only mildly misleading when the change propagates.
    nov = np.ones(m, dtype=np.float64)
    if m > 1 and (_clock.time() - start) < 45.0:
        try:
            Pc = (P - m0) / s_eff
            Pc = Pc - Pc.mean(axis=0, keepdims=True)
            sdv = np.sqrt((Pc * Pc).sum(axis=0))
            good = np.flatnonzero(sdv > 1e-12)
            C = np.zeros((m, m), dtype=np.float64)
            if good.size > 1:
                A = Pc[:, good] / sdv[good]
                C[np.ix_(good, good)] = A.T @ A
            absC = np.abs(C)
            D = (Q - m0) / s_eff
            for j in range(m):
                cand = np.argsort(-absC[j])[:8]
                peers = [i for i in cand if i != j and svc[i] != svc[j] and absC[j, i] >= 0.3]
                if not peers:
                    continue
                y = D[:, j]
                sy = float(np.std(y))
                if sy < 1e-12:
                    nov[j] = 0.0
                    continue
                A = D[:, peers]
                design = np.column_stack([A, np.ones(A.shape[0])])
                coef, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
                resid = y - design @ coef
                ss_res = float((resid * resid).sum())
                ss_tot = float(((y - y.mean()) ** 2).sum())
                r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
                if np.isfinite(r2):
                    nov[j] = float(np.clip(1.0 - r2, 0.0, 1.0))
        except Exception:
            nov = np.ones(m, dtype=np.float64)

    # ------------------------------------------------------- SLI co-movement
    co = np.full(m, 0.5, dtype=np.float64)
    sli = None
    try:
        if isinstance(metadata, dict):
            sli = metadata.get("sli")
    except Exception:
        sli = None
    if sli is not None:
        try:
            sli = str(sli)
            if sli in names and (_clock.time() - start) < 60.0:
                k = names.index(sli)
                ys = (Q[:, k] - m0[k]) / s_eff[k]
                nb = 12 if Q.shape[0] >= 24 else 6
                chunks = np.array_split(np.arange(Q.shape[0]), nb)
                ybin = np.array([ys[ch].mean() if ch.size else 0.0 for ch in chunks])
                if float(np.std(ybin)) > 1e-12:
                    for j in range(m):
                        if j == k:
                            continue
                        yj = (Q[:, j] - m0[j]) / s_eff[j]
                        jbin = np.array([yj[ch].mean() if ch.size else 0.0 for ch in chunks])
                        if float(np.std(jbin)) <= 1e-12:
                            continue
                        r = float(np.corrcoef(ybin, jbin)[0, 1])
                        if np.isfinite(r):
                            co[j] = min(1.0, abs(r))
        except Exception:
            co = np.full(m, 0.5, dtype=np.float64)

    # ----------------------------------------------------- score combination
    score = (mag
             * (0.55 + 0.45 * causal)
             * (0.90 + 0.10 * nov)
             * (0.85 + 0.15 * co))
    # A non-finite score would sort to the front of the ranking; drop it to
    # the bottom instead so that a numerical accident can never put an
    # arbitrary metric on top.
    score = np.nan_to_num(score, nan=0.0, posinf=0.0, neginf=0.0)

    # ----------------------------------------------------- exclusive-cell origin
    # The fault's own signature is the change that is alone in its (metric
    # family, direction) cell of the affected set; the service that owns it is
    # the origin of the incident and is promoted at the service level.
    origin_svc = None
    origin_w = 0.0
    try:
        if (_clock.time() - start) < 70.0:
            origin_svc, origin_w = _origin_service(
                suffix, svc, shift, own_rel, change, persist)
    except Exception:
        origin_svc = None
        origin_w = 0.0

    # ------------------------------------------------------------ cone head
    # When the inherited exclusive-cell detector finds nothing, the most
    # upstream member of the propagation cone is the origin.  The rule is
    # applied only when the propagation is the dominant effect of the
    # incident, so it stays inert in the resource regime.
    cone_svc = None
    cone_w = 0.0
    try:
        if (_clock.time() - start) < 74.0 and origin_svc is None:
            cone_svc, cone_w = _cone_origin(
                suffix, svc, shift, own_rel, change, persist, level, score)
    except Exception:
        cone_svc = None
        cone_w = 0.0

    # ------------------------------------------------ level-oriented upstream
    # Inside the affected set the dependency relation is oriented by the
    # baseline levels (the upstream member of a pair is the one with the
    # smaller baseline); the downstream member of the relation loses a
    # bounded factor.  This is the service-level version of the principle the
    # self-relative view already uses, and it is applied where the residual
    # of the inherited program lives: the ordering *inside* the affected cone.
    demote = {}
    try:
        if struct is not None and (_clock.time() - start) < 80.0:
            aff = ((change >= _UP_SIGMA) & (persist >= _UP_PERSIST)
                   & ((fam_ratio >= _GATE) | own_moved))
            demote = _upstream_factors(svc, suffix, level, own_rel, aff,
                                       struct[2])
    except Exception:
        demote = {}

    # --------------------------------------------------- service aggregation
    svc_idx = {}
    for j, s in enumerate(svc):
        svc_idx.setdefault(s, []).append(j)
    # First pass: the raw aggregated score of every service.  The promotions
    # and the demotion are per-service multiplicative factors, so applying them
    # after this pass is identical to applying them inside it; the point of the
    # two passes is that the leader's score is known before the cone head
    # is promoted, which is what bounds the promotion.
    base_map = {}
    for s, idxs in svc_idx.items():
        sub = score[idxs]
        srt = np.sort(sub)[::-1]
        b = float(srt[0])
        if srt.size > 1:
            b += 0.2 * float(srt[1])
        base_map[s] = b
    leader = max(base_map.values()) if base_map else 0.0
    order_svc = []
    final_map = {}
    for s, idxs in svc_idx.items():
        base = base_map[s]
        if origin_svc is not None and s == origin_svc and origin_w > 0.0:
            base *= (1.0 + _CELL_W * origin_w)
        if (cone_svc is not None and s == cone_svc and cone_w > 0.0
                and leader > 0.0 and base >= _CONE_MIN_REL * leader):
            base *= (1.0 + _CONE_W * cone_w)
        base *= float(demote.get(s, 1.0))
        final_map[s] = base
        order_svc.append((-base, s))
    order_svc.sort()
    ordered = [s for _, s in order_svc]
    # the order before any delivery: the new block below runs only where the
    # inherited deliveries abstained, so that it can never fight them
    ordered_base = list(ordered)

    # ---------------------------- new: containment-anchored service arbitration
    # The inherited ranking is right but not *first* in the network-fault
    # regime: the leader is a victim whose latency contains the fault site's
    # and therefore moves by at least as much.  The raw-unit containment
    # identity is the instrument that can say which of the leading services is
    # the deepest one -- the one that contains nobody -- and the leader is
    # then provably a *descendant* of it, i.e. a victim.  When that relation
    # is unambiguous the deepest member of the leading group is moved to the
    # front by a rotation, which leaves the leading set (and therefore AC@3
    # and AC@5) invariant.
    #
    # The contest is deliberately restricted to the leading services and is
    # only run when the inherited exclusive-cell detector abstained, i.e. in
    # the propagation regime where the inherited origin rule is blind; and it
    # abstains whenever the inherited cone head names a *different* service,
    # so that two independent relation channels must agree before anything is
    # moved.
    try:
        if (_clock.time() - start) < 78.0 and origin_svc is None:
            if len(ordered) >= 2:
                cmask2 = (fam_ratio >= _GATE) | own_moved
                if int(np.count_nonzero(cmask2)) >= 2:
                    sink = _containment_sink(
                        P, shift, suffix, svc, cmask2, ordered)
                    if sink is not None and sink != ordered[0]:
                        agree = (cone_svc is None or cone_svc == sink)
                        lead_score = float(final_map.get(ordered[0], 0.0))
                        sink_score = float(final_map.get(sink, 0.0))
                        if (agree and lead_score > 0.0
                                and sink_score >= _CA_MIN_REL * lead_score):
                            ordered = _rotate_within(ordered, sink, _CA_TOP)
    except Exception:
        pass

    # ------------------- new: certified rotation of a detected origin
    # The inherited program *identifies* an origin in two regimes -- the
    # fault's own exclusive signature (the resource regime) and the most
    # upstream member of the propagation cone (the network regime) -- but
    # delivers it with a *bounded multiplicative promotion* (at most x1.5 and
    # x1.7).  The archive measured that a bounded factor cannot cross the
    # magnitude gap between a quiet fault site and a loud victim, so in the
    # network regime the delivery is inert: the origin is found and then
    # dropped again by the tie-break.  This block delivers the detected
    # origin by the archive's *set-preserving rotation* instead, but only
    # after the program's own **containment relation has certified** that the
    # leader of the ranking is a *descendant* of the candidate -- i.e. that
    # the leader is a victim of the very change the candidate carries.
    #
    # Three guards make it safe:
    #   * the private-signature veto: a leader that owns a change alone in
    #     its (family, direction) cell is the origin of a *local* fault, so
    #     no other origin hypothesis may be delivered;
    #   * the contender floor: the candidate must already carry a real share
    #     of the leader's score, so the rotation never lifts a distant
    #     service into the leading group;
    #   * the containment certification itself, which is the same relation
    #     the arbitration uses and which is only admitted when it reproduces
    #     the observed incident shift of the contained series.
    #
    # The rotation is confined to the leading three services, so the set of
    # the leading three (and hence of the leading five) is invariant: AC@3 and
    # AC@5 cannot be lost, and a wrong decision costs the leader exactly one
    # position.
    try:
        if (_clock.time() - start) < 84.0:
            cand = None
            if origin_svc is not None and origin_w > 0.0:
                cand = origin_svc
            elif cone_svc is not None and cone_w > 0.0:
                cand = cone_svc
            if cand is not None and len(ordered) >= 2 and cand != ordered[0]:
                pos = ordered.index(cand)
                if 1 <= pos < _ROT_TOP:
                    lead = ordered[0]
                    lead_score = float(final_map.get(lead, 0.0))
                    cand_score = float(final_map.get(cand, 0.0))
                    ok = lead_score > 0.0 and cand_score >= _ROT_MIN_REL * lead_score
                    if ok and _leader_private_signature(
                            suffix, svc, shift, own_rel, change, persist,
                            fam_ratio, lead):
                        ok = False
                    if ok:
                        cmask3 = (fam_ratio >= _GATE) | own_moved
                        if int(np.count_nonzero(cmask3)) >= 2:
                            if _containment_reaches(
                                    P, shift, suffix, svc, cmask3, ordered,
                                    lead, cand, _ROT_CA_TOP):
                                ordered = _rotate_within(ordered, cand, _ROT_TOP)
    except Exception:
        pass

    # ------------------- new: whole-wave containment source
    # The two inherited deliveries are *scope limited*: the arbitration
    # estimates the containment relation only among the leading three
    # services and the certified rotation only among the leading eight, so a
    # propagation chain whose intermediate members lie outside those windows
    # is invisible to both, and the true fault site -- which the development
    # split always places inside the leading three -- stays behind a victim.
    #
    # This block resolves the leader's own chain over the **whole wave** (the
    # services that carry the leader's channel), reads the **source** of that
    # chain (the member that contains no other member of it) and delivers it
    # with the same set-preserving rotation.
    #
    # Guards:
    #   * it runs only where both inherited deliveries abstained, so it can
    #     never fight them;
    #   * the leader must own **no** change that lies alone in its
    #     (metric family, direction) cell -- the *magnitude free* form of the
    #     private-signature veto, which is the test the archive measured to
    #     fire on a saturated resource metric where the magnitude-gated
    #     inherited veto abstains.  A leader that owns a private change is
    #     the origin of a local fault and is never displaced;
    #   * the source must already carry a real share of the leader's score
    #     and must sit inside the leading three services, so the delivery is
    #     a permutation of a fixed leading set and a wrong decision costs the
    #     leader exactly one position.
    try:
        if (_clock.time() - start) < _WC_DEADLINE and ordered == ordered_base:
            if len(ordered) >= 2:
                cmask5 = (fam_ratio >= _GATE) | own_moved
                if int(np.count_nonzero(cmask5)) >= 2:
                    lead = ordered[0]
                    if not _leader_isolated_cell(
                            suffix, svc, shift, change, persist, lead):
                        cand3 = _wc_source(
                            P, shift, suffix, svc, cmask5, level, change,
                            persist, ordered)
                        if cand3 is not None and cand3 != lead:
                            pos = ordered.index(cand3)
                            if 1 <= pos < _WC_TOP:
                                lead_score = float(final_map.get(lead, 0.0))
                                cand_score = float(final_map.get(cand3, 0.0))
                                if (lead_score > 0.0
                                        and cand_score >= _WC_MIN_REL * lead_score):
                                    ordered = _rotate_within(ordered, cand3,
                                                             _WC_TOP)
    except Exception:
        pass

    per_svc = []
    for s in ordered:
        idxs = sorted(svc_idx[s], key=lambda j: (-score[j], names[j]))
        per_svc.append([names[j] for j in idxs])

    # Interleaved emission: the k-th metric of every service is emitted in
    # service order, so the first occurrence of each service prefix follows our
    # service ranking exactly while metric level keeps its best candidates.
    out = []
    depth = 0
    while True:
        added = False
        for lst in per_svc:
            if depth < len(lst):
                out.append(lst[depth])
                added = True
        if not added:
            break
        depth += 1
    return out


def rank(data, inject_time, metadata):
    """Rank metric series by suspicion, most suspicious first."""
    try:
        return _rank_impl(data, inject_time, metadata)
    except Exception:
        return _rank_fallback(data, inject_time)
# EVOLVE-BLOCK-END
