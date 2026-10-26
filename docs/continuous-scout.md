# Continuous MiniMax scouting and durable Kimi queue

The operator can remove session-count caps independently of checkpoint duration.
For the parallel research service, set:

```json
{
  "budgets": {"daily_sessions": null},
  "agenda": {"default_budgets": {"max_sessions": null}},
  "service": {"scout_ahead_queue": true, "continuous_discovery": true}
}
```

Merge these settings into an otherwise complete service config; they are not a
standalone configuration. Bounded defaults remain for new operators.

In this mode one MiniMax scout per benchmark can continue discovery even while
Kimi is occupied or its time allowance is exhausted. It has no daily model-time
cutoff and no session-count cap. Twenty-minute saved checkpoints, per-investigation
time/cost ceilings, reported-dollar ceilings, disk guards, branch privacy and
source/validation checks remain. An investigation can end or be shelved; the
scout then selects another distinct direction. No measured price is inferred
when the provider omits billing.

Only source-pinned packets labelled ready_for_review enter the reproduction lane.
Incomplete leads stay with the scout. Kimi selects from the durable investigations
queue and checks the science before implementation. Ready means structurally
complete, not scientifically certified. The queue survives a restart; no extra
Kimi concurrency is enabled. The existing Kimi daily model-time and cost budgets
remain; scout usage no longer consumes Kimi's time allocation.

Aggregate historical usage is retained, plus per-role daily ledgers. Migration
reconstructs lane usage from saved settled sessions and live reservations; any
unattributed historical usage is conservatively charged to reproduction. Existing
model children are reattached. Removing a count limit never resets consumption,
reopens stopped/completed work, or modifies an active investigation mid-session.
Session-cap-only shelving can resume after a boundary if its other budgets remain
and it was not stale. Other scientific, cost, time and infrastructure shelving
remains preserved.
