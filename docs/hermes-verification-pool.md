# Concurrent Hermes reproduction and score-prioritized research

Each task has one MiniMax scout and a configurable pool of isolated reproducers.
Set `service.reproducer_workers` to a positive integer (default 1). For example,
2 admits `reproducer` and `reproducer_2` on distinct investigations. Each keeps
its own job, source bundle, lease, experimental memory and validation receipts.
The existing daily reproduction budget is shared across the pool, not multiplied
per worker. Provider admission remains global across Hermes and RSI processes.

The runtime operator can set `work/runtime-locks/provider-limits.json`, for example
`{"kimi_proxy": 6}`, to authorize six total Kimi model sessions. Unspecified
providers keep their existing defaults. Active workers are not killed to migrate
or change concurrency; supervisors adopt their identity and account reservations.
Change `reproducer` provider configuration at saved session boundaries.

The Kaggle watcher creates one investigation per notebook version. Scheduling
uses the highest positive finite score claimed in the decimal title or platform
best-public-score field, descending, then explicit priority and age. Both claim
sources remain recorded; platform best scores can belong to earlier versions.
Integer labels such as v15, dates and qubit counts are not parsed as scores.
An overall portfolio claim is not a task-specific reward and has no authority
at any validation or publication gate. Papers without claims remain eligible.
An in-flight session finishes before selection is reconsidered.

On watcher startup, untouched legacy listing batches split into individual
notebook candidates, using the latest listed version of each notebook. Their
parent batch records remain as superseded provenance. Already active research,
consumed budgets and certified exports are preserved. Newer versions supersede
only untouched queued older-version candidates. Scouts must still produce an
evidence-backed handoff before reproducers can implement a method. Full unchanged
official development and independent exact-file confirmation remain mandatory.
