# EvolveTS

Time-series task adapters for the original [Dream-RSI](https://github.com/google-research/dream-rsi) engine. Start from a minimal program, let a coding agent propose approaches, score them with a fixed evaluator, and use recorded discovery trees to improve the search controller through replay.

This is a **fresh-start source distribution**. It contains no API keys, experiment histories, learned controllers, discovered programs, progress reports, datasets, checkpoint weights or local machine configuration. Every new campaign starts at E0. Anomaly and forecasting have separate evaluators, controllers, histories and replay pools. No agent skills workflow is required.

## Tasks

| Task | Seed | Development objective | Frozen final evaluation |
|---|---|---|---|
| `tsb_ad_u` | Median/MAD | Mean official VUS-PR on all 48 tuning series | Official 350-series list; optional full 822 list |
| `gift_forecasting_v2` | Seasonal naive, point-mass quantiles | Inverse geometric mean of relative CRPS across 24 configurations, up to 32 series each; MASE diagnostic only | All 97 configurations, all series and original test windows |

Task metrics, data/source pins, permitted inputs and resource budgets live in each task's `protocol.json` and task description. Final test results never feed discovery. A development score is not a leaderboard result.

## 1. Install the engine

Prerequisites: Git, [uv](https://docs.astral.sh/uv/), and the Claude Code CLI (`claude` on PATH). The CLI/SDK supplies agent tools; your configured provider supplies the model. Linux tasks require CUDA and Docker with NVIDIA Container Toolkit. Anomaly detection also has an Apple Silicon macOS/MPS setup.

```bash
git clone https://github.com/kostagjorgjievski/evolveTS.git
cd evolveTS
bash scripts/bootstrap.sh
```

The bootstrap fetches three clean, pinned upstream checkouts into ignored `upstream/` directories. It never imports an existing campaign or learned policy. See [dependency pins](docs/dependencies.md).

## 2. Configure your own provider

```bash
mkdir -p .credentials
cp configs/provider.env.example .credentials/minimax.env
chmod 600 .credentials/minimax.env
# Edit this local file: set your own key, endpoint and model.
```

The example contains an empty key. Use the global or China endpoint appropriate to **your** account; keys are not universally interchangeable. Never commit this directory. `BACKEND=minimax` is the default; `glm` uses `.credentials/glm.env` with the same three exported variables, and `deepseek` uses its launcher-specific variables. No provider requests occur during the basic engine installation or unit tests; launching discovery does make billable requests.

## 3. Prepare a task

### Anomaly detection: Mac / MPS

```bash
bash tasks/tsb_ad_u/setup.sh
```

On macOS this dispatches to `setup_macos.sh`. It creates the task environment, builds the pinned LibraryTS wheel without bundled datasets/tests/skills, installs optional toolboxes, downloads the checksum-verified anomaly archive and prepares only tuning data for search. MPS must be available. CPU statistical methods remain permitted. Candidate isolation uses macOS `sandbox-exec`.

### Anomaly detection: Linux / CUDA

Run the same setup command on a CUDA host with Docker. It builds a local standalone worker image and records its ID in your ignored host profile. It does not depend on anyone else's Docker cache or host-local environment.

### Forecasting v2: Linux / CUDA

```bash
bash scripts/setup_forecasting.sh
```

This downloads pinned GIFT-Eval data, fetches pinned source archives for worker dependencies, builds the Docker worker, downloads the seven optional checkpoints and computes **your own** seasonal-naive reference. Check model licences before downloading; some weights have research/non-commercial conditions. Weights are mounted read-only during candidate evaluation; runtime network access is denied.

The unified worker deliberately overrides conflicting dependency ranges for TiRex, Toto and FlowState's dependencies. This reproduces the adaptation's integration strategy, not each package author's exact environment. Run the restricted model probes on your GPU before search:

```bash
bash tasks/gift_forecasting_v2/smoke_models.sh
```

Setup is substantial (multiple GB and a Docker build). Forecasting v2 is not configured for Mac/MPS. The release packaging has source/unit checks; a fresh GPU image build is required on the recipient's machine.

## 4. Choose your GPUs

Bootstrap creates `configs/hosts/<hostname>.json`, ignored by Git. Start with GPU 0; change `physical_gpu`, `physical_gpus` and `gift_v2_physical_gpus` to GPUs you are authorised to use. Each evaluation leases one GPU. The coding-worker count is independent of evaluation parallelism. Do not copy another person's host profile.

## 5. Start from E0

```bash
BACKEND=minimax bash scripts/run_fresh.sh tsb_ad_u
# Or, independently:
BACKEND=minimax bash scripts/run_fresh.sh gift_forecasting_v2
```

Each command creates unique empty workspaces, runs E0, then continues through the upstream Dream-RSI loop. Defaults: **10 total rounds including E0**, **10 coding workers**, E0 **10 branches × 11 attempts**, and three controller rewrites per dreaming phase. These are full searches, not smoke tests.

Upstream launch overrides such as `ROUNDS`, `BRANCHES`, `REFINE` and `MAX_WORKERS` remain available. For a small integration run, use two total rounds and a smaller grid; it is not a scientific comparison:

```bash
ROUNDS=2 BRANCHES=3 REFINE=1 MAX_WORKERS=3 \
  BACKEND=minimax bash scripts/run_fresh.sh tsb_ad_u
```

For separate stages or resuming an existing workspace, use `tasks/<task>/launch.sh e0|dream_rsi|baseline` with `WORKSPACE`, `E0_WORKSPACE` and `RESUME=1`. Preserve accounting and failed-attempt artifacts. No automatic shell access is granted to exploration agents; learning agents retain the upstream shell interface.

## Compatibility changes

- Provider selection and per-invocation accounting wrap the unchanged pinned upstream engine.
- Exploration file reads are scoped to its branch and archived history; writes are scoped to the current attempt. Auto-memory is disabled.
- A complete path index makes linked archives discoverable even when recursive file-search tools do not follow symlink directories. The original read-all-history instruction remains; this is **not** summary-based retrieval.
- The SDK JSON message buffer is 16 MiB, to accommodate large tool responses. This does not enlarge the model's context window.
- Request retries are bounded; provider/network failures can still fail agent sessions. These should be distinguished from evaluated program failures when analysing a campaign. The source distribution does not claim to eliminate provider outages.

## Checks

```bash
.venv/bin/python -m pytest tests -q
# After task setup, run the appropriate task checks separately:
.tsb-venv/bin/python -m pytest tasks/tsb_ad_u/test_task.py -q
.gift-venv/bin/python -m pytest tasks/gift_forecasting_v2/test_task.py -q
```

Task checks require the downloaded data, upstream checkouts and matching hardware isolation/runtime. They do not launch LLM discovery. Final evaluation additionally requires a frozen program hash and a new output directory; see each task README.

## Attribution

Dream-RSI's original engine is fetched at its pinned revision and remains under its upstream Apache-2.0 licence. GIFT-Eval, TSB-AD, LibraryTS and checkpoint packages retain their own licences. See [NOTICE](NOTICE).
