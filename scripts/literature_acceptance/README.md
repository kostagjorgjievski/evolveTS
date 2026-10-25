# Blind literature-to-implementation acceptance test

The first fixture is `runs/dqi-acceptance/20261024T075625Z`.

A fresh GPT-6.1 Sol researcher receives only the official task, reference source,
verifier and license. It discovers literature independently and supplies sources,
compatibility analysis and an implementation plan, without a candidate or adapter.
A fresh GLM-5.3 worker receives that handoff and its public snapshots. MiniMax's
configured token was empty; the user explicitly allowed GLM as an alternative.
The worker can query the same researcher, fetch pinned public repository sources,
run sandboxed diagnostics and call the unchanged full verifier. The coordinator
must not provide algorithmic fixes or a prior private solution.

The worker has no Bash, no access to other runs, and a clean interpreter without
research-specific packages. Fetched source roots are read-only in execution;
network, credentials and official-file writes are denied. Source caches and all
conversations/questions are retained. Public-source reuse must be attributed.

Precommitted performance threshold: 95% of reward 9.348319382172171, namely
8.88090341306356, on BOTH 102400-shot full development verification and a
fresh-salt check of the same frozen source. The official repetition penalty is
included. A human audit must also confirm independent discovery and no solution
leakage; numeric scores alone do not authorize production deployment.

`run_worker.py` runs the worker and grading. `supervise.py` writes `report.json`
and stops the on-demand researcher when the worker finishes. Current state lives
in `runs/dqi-acceptance/active.json`. Production remains disabled throughout.
The researcher discovery audit, handoff and interactions are stored separately
from the worker's candidate. No existing experiment binary or adapter is supplied.
