# DFTHC-SOS for RSI

Independent task adapter for the Google verifiable quantum circuit compilation
chemistry benchmark. This task has its own task specification, pinned inputs,
runtime, library namespace, run folders and accounting. Preparing it does not
start a model campaign or change existing DQI pilots.

The unchanged Apache-2.0 verifier is in
`data/quantum-compilation/official/verifiers/dfthcsos`. Its complete contract is
copied to `OFFICIAL_SCORING.md`. The official reference generator is exposed by
`init_program.py`, which rebuilds the supplied ten ANGLE circuits and copies the
baseline numerical factorization. Both factorization and circuit optimization
are allowed. Fixed symmetry shifts and all acceptance gates stay official.

## Runtime and validation

```bash
bash tasks/dfthcsos/setup.sh
.dfthcsos-venv/bin/python -m pytest -q tasks/dfthcsos/test_task.py
.dfthcsos-venv/bin/python tasks/dfthcsos/evaluator.py \
  --program tasks/dfthcsos/init_program.py --output outputs/dfthcsos-reference-check
```

A candidate takes one output-directory argument and writes `submission.npz` plus
consecutively numbered `angle_k_0.kmb` ... (or `.kmx`). NumPy, SciPy, kickmix and
the official dfthcsos modules import directly. Artifact-local Python helpers and
numerical files are copied with the generator. The official sample NPZ remains
available read-only; it includes angle words useful for reference regeneration.

The generator runs offline without provider credentials, with only output
writable, up to600 seconds/8GiB. The trusted verifier runs separately, up to3600
seconds/8GiB. All quantum tasks share `work/runtime-locks/dqi-cpu.lock` to avoid
simultaneous memory-heavy evaluations. Model coding sessions remain independent.
The original Kaggle circuit and NPZ readers are extracted from the hash-pinned
metric without changing their logic, including dtype, shape and size checks.

Full scoring uses64 shots at every address. For baseline R=65/B=60, that means
254,464 verified address-shots (each circuit family is exercised). A smoke check
uses1 shot/address and never supplies a search reward:

```bash
.dfthcsos-venv/bin/python tasks/dfthcsos/evaluator.py \
  --program tasks/dfthcsos/init_program.py --output outputs/dfthcsos-smoke --smoke
.dfthcsos-venv/bin/python tasks/dfthcsos/library_validate.py ATTEMPT --held-out
```

Reward is `reference_cost / (lambda_eff * T_total * Q_total)`. This is this task's
improvement ratio, not the competition's three-task leaderboard aggregate.
Fresh-salt verification reports no search reward. The native Mac build has not
been established equivalent to the Kaggle Linux build; local PASS is not a Kaggle
submission. No submission has been sent.

Pin the full baseline receipt before launching:

```bash
.dfthcsos-venv/bin/python tasks/dfthcsos/calibrate.py
```

## Launch preparation

```bash
DRY_RUN=1 bash tasks/dfthcsos/launch.sh e0
BACKEND=glm WORKSPACE=runs/dfthcsos/e0/my-run bash tasks/dfthcsos/launch.sh e0
```

The second command makes billable model calls. Default E0 is10 branches with11
attempts each, using the existing upstream runner. `BRANCHES`, `REFINE`,
`DFTHCSOS_MAX_WORKERS`, `WORKSPACE`, `ROUNDS`, and `BACKEND` are configurable.
`dream_rsi` and `baseline` stages are supported, as is
`bash scripts/run_fresh.sh dfthcsos`. Launch requires a full hash-pinned local
baseline calibration. This adapter does not silently enable the experimental
DQI-only conversation-continuity controller or DQI candidate-validation MCP tool.
Workers receive task-specific no-argument `validate_candidate` and
`diagnose_candidate` tools. Successful diagnostics return printed logs too;
the diagnostic sandbox supports small numerical and API tests without full
verification. Calls are logged under `runs/dfthcsos-accounting/`. Public search
uses the existing research-tool configuration when enabled.

Library metadata is in `library.json`; `library/dfthcsos` starts empty. DQI
literature, candidates and history are not seeded into this task.

## Baseline verified on this computer

The rebuilt official generator passed254,464 address-shots (64/address), with
cost3,355,599,588.3155375, total93,237 Toffolis and730 total logical qubits
(ANGLE circuits use119). The normalized baseline reward is1.0. The pinned full
receipt is `outputs/dfthcsos-calibration/result.json`; elapsed time includes
waiting for the shared validation lock, so it is not a standalone runtime benchmark.
