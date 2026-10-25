# Standalone literature-discovery pilot

One fresh implementation branch receives the official task, reference and verifier.
There is no seeded method library, researcher handoff or advisor. Public research
is available through web_search, fetch_source and pinned source-only fetch_repository.
The coding allowance is 200 minutes across resumptions. Provider requests explicitly
set max effort; actual request metadata and served model are recorded.

## Execution modes

| Tool | Script | Limits | Network and credentials | Purpose |
|---|---|---|---|---|
| diagnose_candidate | artifact/diagnostic.py | 60 seconds, 2 GiB | Offline, no credentials | Small Python probes |
| integration_test | artifact/diagnostic.py | 600 seconds, 10 GiB | Network enabled; branch's provider credential in environment | Arbitrary Python, dependencies, subprocesses, circuit builds, small simulations and benchmarks |
| validate_candidate | artifact/program.py | Existing generation and full verifier limits | Candidate generation offline, no credentials | Unchanged official full score |

All modes import snapshotted candidate/helpers and fetched public source. Integration
tests additionally read/write their own branch via BRANCH_WORKSPACE. They receive
ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL and ANTHROPIC_MODEL. pip is available;
PIP_TARGET defaults to branch/dependencies, included in integration imports. Necessary
final dependencies must be vendored into artifact for offline official generation.

Other branch/project histories, results, libraries and credentials files are not
mounted. Selected provider credentials are explicitly user-authorized. The global
official sources and executing code snapshot remain read-only. Scores are computed
by the independent trusted evaluator, not by a test's stdout or writable local copy.

Integration scratch goes to TEST_OUTPUT_DIR. Small text/array outputs (up to 4 MiB
per file, 16 MiB exported total) are copied into branch/test-results/<call_id>/ and
returned with hashes. Large disposable circuits are not retained by this tool.
Branch plus test scratch is limited to 2 GiB/20000 files; at least 3 GiB of host
disk space must remain. Process-tree memory/time/log limits and the shared CPU
lock apply. Successful integration tests carry no official reward.

DQI has generated random test cases rather than a conventional held-out dataset.
Agents may inspect the task verifier and generate their own cases. Final checking
uses a fresh local salt; it is a robustness check, not hidden real-world data.

## Comparison boundaries

The original MiniMax run used the repaired source/import tools without integration_test.
The GLM run began under that same condition. The user then authorized adding the
broader integration mode to GLM. Its session is refreshed with history/drafts intact
and its remaining original allowance, and the harness change is logged. A final
comparison must distinguish model effects from this additional tool access.

## Persistent branch and preparation pilots

`continuity_pilot.py prepare RUN` then `continuity_pilot.py run RUN` runs three
scored attempts in one MiniMax max-effort conversation. Each next attempt receives
the official score/diagnostics and a copy of its previous artifact. Private
snapshots preserve every submitted candidate; later working files cannot change
those snapshots. Conversation ID changes fail closed. There is no short attempt
time target: all coding sessions share 200 minutes; controller scoring time is
reported separately. Context uses the installed CLI's normal management; forced
compaction behavior has not been acceptance-tested.

Adding `--seeded` to both commands first runs an orientation-only session on the
official task, reference, verifier and small API tests. Literature tools are not
exposed in preparation. The guide, helper files and transcript are frozen privately.
The first optimization attempt uses native `fork_session=True`: its ID must differ
from preparation, later attempts must retain that new ID, and the preparation
transcript must remain unchanged. Preparation time is reported separately and
counts against the pilot's shared working allowance. This tests one child at the
same workspace; deploying a checkpoint to multiple isolated workspaces requires
an additional session/file relocation test.

`smoke RUN --seeded` verifies actual parent-memory recall without repeating the
marker in the child prompt, distinct parent/child IDs, later continuation and
unchanged parent transcript. It does not measure DQI implementation speed.

Compare preparation time, coding time per attempt, verifier/queue time and verified
reward. Concurrent pilots share the CPU validation queue, and these single runs
are exploratory evidence rather than a controlled model ranking.
