"""Own-scale change visibility + level-oriented upstream demotion + cone-head origin.

This is the measured-best lineage of ``explore_b6`` (attempt_06, service
Avg@5 = 0.9733 on the 75 development cases) with **one** new service-level
mechanism added: *cone-head origin attribution*.

Everything the inherited program does is kept unchanged -- the split, the
family scales, the robust statistics, the monotone soft saturations, the
persistence factor, the self-relative impact, the own-scale change
visibility, the confounder-adjusted direct-effect attribution, the
level-oriented driver filter, the peer isolation, the SLI co-movement, the
exclusive-cell origin *detector*, the level-oriented upstream demotion and
the interleaved metric emission.

The new mechanism (details in proposal.md):

  * A fault injected at the network interface of one service moves every
    service of the affected chain by roughly the **same absolute amount**, so
    the members of the propagation cone are near-tied in their shift; the
    only thing that separates them is the **baseline level**, because along
    a call chain the level of the observable accumulates towards the caller,
    so the fault site carries the smallest baseline of the cone and hence
    the largest change relative to its own level.
  * The *cone-head* rule therefore names the most upstream member of the
    dominant affected cell.  It is conjunctive and inert unless the cone
    exists, the members are near-tied in absolute shift, the level hierarchy
    separates the head clearly, and the propagation is the dominant effect
    of the incident (which is what keeps it away from the resource faults).
  * The head is promoted at the **service** level by a bounded factor.
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

# --- new: own-scale change visibility ----------------------------------------
_OWN_FLOOR_SD = 3.0   # the own level is floored at 3 robust sigmas of its own
_OWN_GATE = 0.15      # own-level-relative change that counts as "changed"
_OWN_SIGMA = 1.5      # noise-relative significance of an own-scale change
_OWN_CAP = 50.0       # cap of the own-level-relative ratio

# --- new: level-oriented upstream demotion -----------------------------------
_UP_CORR = 0.45       # min |residual correlation| for a dependency relation
_UP_LEVEL = 0.30      # the downstream level must be this much larger
_UP_OWN = 0.80        # the upstream member must be at least as anomalous
_UP_DEMOTE = 0.85     # factor of a service one upstream step below another
_UP_MAX_DEPTH = 3     # at most this many upstream steps are counted
_UP_SIGMA = 1.5       # noise-relative significance of an affected metric
_UP_PERSIST = 0.30    # and the change must be sustained, not a fluctuation

# --- new: relaxed membership of the origin -----------------------------------
_CELL_STRONG = 0.35        # own-relative magnitude of a strong signature
_CELL_STRONG_SIGMA = 2.0   # its noise-relative significance
_CELL_STRONG_PERSIST = 0.50  # its persistence

# --- new: cone-head origin ----------------------------------------------------
_CONE_TIE = 4.0        # no cone member may exceed this multiple of the
                        # median absolute shift of the cone
_CONE_GAP = 0.10       # the head's baseline must be this much below the
                        # next member's baseline
_CONE_GAP_FULL = 0.30  # a level gap of this size gives full strength
_CONE_W = 0.70         # service-level promotion of the cone head
_CONE_MIN_REL = 0.25   # the cone head must already be within this fraction of
                       # the leader's score, so that the promotion can never
                       # lift a deep service into the top five


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
    "explaining" the fault site it was caused by.  This matters exactly in the
    propagation regime, where the size rule alone is vacuous because every
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
        service whose throughput is the fault's own signature.

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
    # NEW: when the inherited exclusive-cell detector finds nothing, the most
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
    # after this pass is identical to applying them inside it; the point of
    # the two passes is that the leader's score is known before the cone head
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
    for s, idxs in svc_idx.items():
        base = base_map[s]
        if origin_svc is not None and s == origin_svc and origin_w > 0.0:
            base *= (1.0 + _CELL_W * origin_w)
        if (cone_svc is not None and s == cone_svc and cone_w > 0.0
                and leader > 0.0 and base >= _CONE_MIN_REL * leader):
            base *= (1.0 + _CONE_W * cone_w)
        base *= float(demote.get(s, 1.0))
        order_svc.append((-base, s))
    order_svc.sort()
    ordered = [s for _, s in order_svc]

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
