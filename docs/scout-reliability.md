# Scout retrieval and handoff reliability

The scout searches and interprets sources; the independent reproducer audits,
implements and runs official verification. A fetched source, a draft, and an
accepted packet are separate stages. None certifies a seed.

## Updated workflow

1. Retrieve original sources. `fetch_repository` resolves a commit, verifies Git
   blob hashes and records a hashed manifest under the requested URL. For a large
   repository, inspect its tree and pass an exact `paths` list. Selected-file
   caches are separate from complete-tree caches; existing resource limits stay.
2. Once a mechanism and first test are known, call `save_scout_draft`. Partial
   drafts survive checkpoints but cannot advance to reproduction or publication.
3. Register a hypothesis with exact fetched source URLs. Call `check_scout_packet`
   with the proposed packet. This checks without submitting a packet, approving
   it, or manufacturing quotations. Errors identify the span, cached file, allowed
   source URLs and citation format.
4. Repair the draft. Individual-file citations omit `relative_path`; repository
   citations name a manifest-listed path. If the hypothesis cites the wrong URL,
   verify source/version identity and call `repair_hypothesis_citations`.
5. Submit `record_scout_packet` and finish once useful evidence is ready. Required
   unresolved dependencies still block readiness. A separately testable mechanism
   can have its own scoped hypothesis; do not hide a necessary dependency.
6. Reproducer review, unchanged official development and independent exact-byte
   confirmation remain mandatory. Scouts do not receive copy/implementation
   staging, full-validation, review or claim-submission operations.

The dashboard distinguishes a daily reproduction-budget wait from an available
slot waiting for a handoff. Budget reset is midnight UTC. This patch does not
increase quotas, reset consumed time, or interrupt productive sessions. Fresh
sessions adopt code/tool/prompt changes at the next checkpoint.

## Measuring benefit

Each patched scout records a `scout_handoff_patch` adoption marker. The existing
`scout-quality-latest.json` report adds post-adoption draft counts, packet errors,
ready handoffs, reviewer corrections/rejections and time to first ready handoff.
Existing verified-export and review metrics remain available. Compare subsequent
batches with preserved prior evidence. Faster handoffs alone do not establish
scientific quality; independent reproduction and certified seeds are the outcome.
Wall times include queue waits; different sources and providers confound causal
comparisons.

## Parallel gateway isolation

Every headless researcher sets `HERMES_GATEWAY_LOCK_DIR` inside its own
`HERMES_HOME`. Upstream Hermes otherwise uses one OS-user gateway singleton
across all homes, which can reject a parallel reproducer before it makes any
model/tool call. This uses the upstream-supported scope override, not force mode.
Same-job duplicate owners still contend on the same lock. Separate jobs retain
separate profiles, histories and cleanup identities. A real pinned-upstream lock
test verifies two job scopes can coexist while a duplicate owner is refused.
