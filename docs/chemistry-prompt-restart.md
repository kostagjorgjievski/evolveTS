# Chemistry E0 prompt integration correction

The previous seeded 20-minute campaign used a replacement worker prompt. The
upstream DreamRSI controller still scheduled E0 and policy discovery, but its
exploration prompt was discarded by the worker adapter. It therefore cannot be
used as a faithful test of upstream exploration behavior.

The user authorized a clean restart: the same five branch/model/seed assignments,
eleven fresh 20-minute attempts per branch, own new-branch experimental memory,
unchanged full development and exact-file independent confirmation. The earlier
campaign is archived in place with its traces, budgets and measured results.
It is not resumed, and none of its attempt memory is injected into the restart.
E1 remains unauthorized; actual discovery/replay follows all 55 completed nodes.

The corrected worker prepends the frozen upstream `explore.txt` instructions.
Only history scope, task-relative paths and the multi-file write contract are
adapted. The sections on learning from failures, avoiding local optima, favoring
structurally different mechanisms and implementing a genuinely new idea remain.
The task/API/tool instructions are appended. Early stopping must explain its
blocker; one failed cheap test is not itself a reason to stop exploration.

Every worker saves `private/delivered-prompt.txt` and
`private/prompt-integration.json` with upstream and delivered hashes. The saved
prompt includes the own-memory attachment actually passed to the model. Upstream
instruction changes that break the adaptation fail before a paid model start.
Own history includes the drivers' actual candidate-/fallback-development and
confirmation receipts, not only proposal summaries.

A provider error AssistantMessage cannot satisfy development startup. Actual
`diagnose_candidate` tool activity and advertised MCP tools are required before
trusted grading can turn a worker into a scored node. Provider-only failures
remain infrastructure-blocked with drafts and metadata preserved; they cannot
advance by validating an unchanged starting artifact.

Eight regressions cover branch models/budgets, deferred grading, appended grid
preservation, OAuth Opus, inclusion of upstream instructions in the delivered
prompt, provider-only false completion, and full own receipt inheritance.
