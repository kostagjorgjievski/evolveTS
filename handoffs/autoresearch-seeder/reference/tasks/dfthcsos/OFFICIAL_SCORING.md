# `dfthcsos`: the DFTHC-SOS competition verifier

This package scores submissions to the Qaggle DFTHC-SOS competition. It is the
`verifier/` directory of the dfthc-sos repository, copied here and reduced to
the one system the competition is scored against:

| | |
| --- | --- |
| System | **FeMoCo76o113e**: `N = 76` spatial orbitals, `eta = 113` electrons |
| `E_upper` | `-22140.27335` Ha |
| Provided baseline | `R, B, C = 65, 60, 60` |
| Fixed symmetry shift | `S, beta_1` of the provided baseline, from [FeMoCo76o113e.fixed_shifts.npz](FeMoCo76o113e.fixed_shifts.npz) (SHA-256 `7b7facf63fe35a9d9d3d00787ffdb700c863fa845fe4724d7f7c54778151cd87`); submitted `H1_I` and `Hsym_lower` are ignored |
| Strict acceptance thresholds | Raw LCU normalization `Lambda > 49.0` and `E_gap > 3.914898` Ha; equality is rejected |
| Reference integrals | [FeMoCo76o113e.fcidump](FeMoCo76o113e.fcidump), shipped in this directory (128,128,348 bytes, SHA-256 `e5a48af746fd075026dec9e8f5df2d363802a121e8c53af9a0b984bde695e1bd`) |

The system constants live in [scoreinfra/reference.py](scoreinfra/reference.py), and
the acceptance thresholds in [verify.py](verify.py). The package is
self-contained: it imports nothing from the `dfthc` training library and needs
only **numpy, scipy and kickmix**.

A submission is a family of `ANGLE_k` kickmix circuits together with the
factorization and the Givens tree they were built from
([Submission files](#submission-files)). There is one entry point:

```text
verify(circuits, factorization)  ->  {"status": "PASS", "score": lambda_eff * T_total * Q_total, ...}
```

Lower is better; a rejected submission raises (`InvalidCircuits` or
`AssertionError` with the reason; the command line prints
`{"status": "FAIL", "error": ...}` and exits 1). The accuracy of the factorization and of the angle words the
circuits load (the dfthc-sos Tasks 1 and 2) enters through `lambda_eff` and
the rejection gates; they are not scored on their own.

## Contents

`verify.py` is the entry point; the modules it builds on are in `scoreinfra/`.
`example_submission/` holds the script that writes the example submission's
circuits; the example itself is the sample submission, `../../sample_submission/dfthcsos/`.

| File | Contents |
| --- | --- |
| [verify.py](verify.py) | `verify(...)` and its command line; the metrics of the loaded words (`evaluate_words`), the accuracy gates, the ANGLES + heuristic costs (`resource_costs`), `evaluate_circuits`, `score_from_metrics` |
| [scoreinfra/circuits.py](scoreinfra/circuits.py) | Register contract (`register_layout`), `.kmb`/`.kmx` reading, `submission_sha256` and `initial_seed`, `recover_words_from_circuits` (kickmix simulation and checks), `circuit_costs` |
| [scoreinfra/reference.py](scoreinfra/reference.py) | The FeMoCo76o113e constants, the packaged FCIDUMP and its checksum, FCIDUMP reader, `.npz` factorization loader |
| [scoreinfra/dfthc_math.py](scoreinfra/dfthc_math.py) | DF-THC metrics (`error_1`, `error_2`, `Lambda`, `E_SOS`, `lambda_eff`) in numpy |
| [scoreinfra/costs_prepare.py](scoreinfra/costs_prepare.py) | `SpinFreeData_V1` cost model of the outer and inner PREPARE (state preparations) and the Givens rotations: Toffolis and qubits |
| [FeMoCo76o113e.fcidump](FeMoCo76o113e.fcidump) | The reference integrals (FCIDUMP) |
| [../../sample_submission/dfthcsos/](../../sample_submission/dfthcsos/) | A complete example submission, the dfthc-sos starter kit's run on the provided baseline factorization: `angle_k_0.kmb` ... `angle_k_9.kmb` (the circuits) and `submission.npz` (the factorization and `tree_edges`). One extra the verifier does not read: the 12-bit `angle_words` in `submission.npz` |
| [example_submission/angle_k_reference_circuit.py](example_submission/angle_k_reference_circuit.py) | Writes the `ANGLE_k` circuits `angle_k_0.kmx`, `angle_k_1.kmx`, ... (or `.kmb` with `--format kmb`) for the `angle_words` of a `submission.npz` (one ordinary QROM per batch); for the example it rewrites the shipped circuits ([Worked example](#worked-example-the-baseline)) |

## Setup

The verifier runs in any environment with numpy, scipy and the `kickmix`
simulator, such as a Kaggle notebook with the competition data's `kickmix/` folder on `sys.path`.
Run everything from the `verifiers/` folder. Nothing else has to be installed:
the reference FCIDUMP ships in this directory as `FeMoCo76o113e.fcidump`.
The verifier always scores against it (there is no option to use another
file): it checks the file's SHA-256 and then reads it directly (about 10 s per
call).

## Submission files

A submission is one directory with `K + 1` files. The verifier reads nothing
else:

```text
RUN/
  angle_k_0.kmx ... angle_k_<K-1>.kmx   the ANGLE_k circuits (.kmx or .kmb), applied in order (K = ceil(75 / J))
  submission.npz                         a numpy.savez archive of six arrays:
    U           (R, B, 76)   \
    W           (R, B, C)     |  the factorization; only the shape of U is
    H2_I        (R, C)        |  used (the vectors are decoded from the
    H1_I        ()            |  circuits); H1_I and Hsym_lower are ignored
    Hsym_lower  (2926,)      /   (the verifier uses the baseline's shift)
    tree_edges  (75, 2)          the Givens tree the circuits' words are decoded on
```

The circuits load, for every address `a < 76 + R*B`, the 75 integer angle
words of row `a` (`brot` bits each; [What a submission must do](#what-a-submission-must-do)).
The verifier decodes each row on `tree_edges`, a list of `(parent, child)`
orbital pairs, into a unit vector:

```text
v = e_0
for t, (p, c) in enumerate(tree_edges):        # theta_t = pi * word_t / 2**(brot - 1)
    v[p], v[c] = cos(theta_t) v[p] - sin(theta_t) v[c],  sin(theta_t) v[p] + cos(theta_t) v[c]
```

Use a spanning tree rooted at orbital 0 that lists every parent before its
children, such as the dfthc-sos starter kit's path or log-depth tree (the
verifier checks only the shape). Rows `0 .. 75` are the one-body vectors and
the rest the two-body vectors `u_b^(rho)`, in `(rho, b)` order. With the weights of the
factorization, these vectors rebuild the one- and two-body integrals that
`error_1` and `error_2` compare with the reference FCIDUMP, and they give
`Lambda`, `E_SOS` and `lambda_eff` (see [Scoring](#scoring)).

Other `.npz` entries and other files are ignored: the example also stores the
`angle_words` its circuits load, but a submission does not need them.

## Running the verification

```bash
# A run directory with angle_k_0.kmx, angle_k_1.kmx, ... (or .kmb) and a
# submission.npz that holds the factorization and tree_edges:
python dfthcsos/verify.py RUN/                       # prints a JSON summary
python dfthcsos/verify.py RUN/submission.npz RUN/    # the same, factorization given explicitly

# Or the circuit files in order, with the factorization and the tree given separately:
python dfthcsos/verify.py factorization.npz angle_k_0.kmx angle_k_1.kmx ... \
    --tree-edges edges.npy
```

Options: `--salt STR` (merged into the simulator seed, see below), `--seed N`
(an explicit seed), `--shots-per-address N` (default 64) and `--format
kmb|kmx` (default: auto-detect from `angle_k_0`).

```python
from dfthcsos.verify import verify

verify("RUN/")                                                      # directory with submission.npz
verify("RUN/", "RUN/submission.npz")                                # directory, factorization given
verify(["a.kmx", "b.kmx"], "factorization.npz", tree_edges=edges)  # files, in order
```

Inputs:

- **Circuits:** a directory with `angle_k_0.kmx`, `angle_k_1.kmx`, ... (or
  `.kmb`) or an ordered list of circuit files (or `kickmix.Circuit` objects in
  Python). They must follow the register contract below; `brot` and `J` are
  read from the circuits, they are not inputs.
- **Factorization:** the five factorization arrays of
  [Submission files](#submission-files) as an `.npz`, normally
  `RUN/submission.npz` (in Python also a mapping of those arrays). It can be
  omitted when the circuits are a directory containing `submission.npz`. The
  circuits only load angle words; the weights `w, W` come from the
  factorization and `S, beta_1` are the provided baseline's
  (`FeMoCo76o113e.fixed_shifts.npz`, SHA-256 checked; the submitted `H1_I`
  and `Hsym_lower` are ignored). **Pickles are not accepted** (unpickling a submitted file can
  run arbitrary code). All factorization file inputs must have the `.npz`
  extension and load with `allow_pickle=False`; renaming a pickle does not
  make it acceptable. The starter trainer writes NPZ directly, and
  `build_circuits.py` writes a complete `submission.npz`. Its eight research
  examples also ship as NPZ in the starter kit dataset's `starter_kit/baselines/`. Training diagnostics use
  numeric `values__<name>` arrays and optional metadata uses a JSON string;
  neither affects scoring. No legacy pickle reader or conversion helper is
  shipped; the examples have already been converted to NPZ.
- **`tree_edges`:** the `(75, 2)` Givens tree (see
  [Submission files](#submission-files)), as an array or a `.npy`/`.npz` file.
  It can be omitted when the circuits are a directory containing
  `submission.npz` with a `tree_edges` entry.

Steps: check the register contract; simulate the family in `kickmix.Simulator`
on every address and recover the words; decode them on the tree and compute
the DF-THC metrics; cost the circuits and the heuristic part; apply the
formula. `verify` returns a JSON-serializable summary (`status`, `score`,
`lambda_eff`, `toffoli_count`, `num_qubits`, `verified_shots`,
`submission_sha256`, the `resources` and `metrics` breakdowns, ...), which the
command line prints. Rejections raise `InvalidCircuits` or `AssertionError`
with the reason; usage errors (missing files, a factorization of the wrong
size or format, missing `tree_edges`) raise too, as does a packaged FCIDUMP
that fails its checksum.

The simulator's measurement outcomes are seeded with
`initial_seed(submission_sha256(...), salt)`: `submission_sha256` is the
SHA-256 of the whole submission, computable from its files with

```bash
{ printf '%s\n' angle_k_*.kmb | sort -t_ -k3,3n | xargs cat
  for k in U W H2_I H1_I Hsym_lower tree_edges; do unzip -p submission.npz "$k.npy"; done
} | sha256sum
```

(the canonical `.kmb` bytes of the circuits in order, then the `.npy` entries
of `submission.npz`, each of which must be exactly one array), so it does not
depend on `.kmx` comments or `.npz` packaging. The optional `--salt` defaults
to an empty string, which gives publicly reproducible samples. To prevent
participants from anticipating grading samples before committing their
submission, the grader must supply a private, unpredictable salt and keep
it secret until submissions are fixed. `verify` reports `submission_sha256`
(never the salt).

To see the numbers behind a score, use the pieces `verify` is made of:

```python
from dfthcsos.verify import evaluate_circuits, evaluate_words, load_inputs

inputs = load_inputs("factorization.npz")              # factorization + reference integrals
evaluate_words(inputs, angle_words, tree_edges, brot)  # error_1, error_2, Lambda, E_SOS, E_gap, lambda_eff
evaluate_circuits(inputs, "RUN/", tree_edges)          # angle_words, brot, metrics, resources, score, submission_sha256
```

`angle_words` is the `(76 + R*B, 75)` integer table (one-body rows first),
each word in `[0, 2**brot)` meaning `theta / pi = word / 2**(brot - 1)`.

### Worked example: the baseline

[../../sample_submission/dfthcsos/](../../sample_submission/dfthcsos/) is a complete submission:
the dfthc-sos starter kit's run on the provided baseline factorization
(log-depth tree, `brot = 12`, `J = 8`; the circuits are ordinary QROMs). From
the `verifiers/` folder:

```bash
EX=../sample_submission/dfthcsos
python dfthcsos/verify.py $EX     # about 25 s; prints a JSON summary with "score": 3355599588.3155365
```

The 12-bit words give `lambda_eff = 49.301369` (the unrounded factorization
would give `49.254686`). The 10 circuits have 119 qubits and 3974 Toffolis
each (79,480 Toffolis across the forward and reverse passes); the heuristic
part adds 846 + 9461 + 3450 = 13,757 Toffolis, and the shared-workspace qubit
count combines 186 persistent qubits with 544 shared temporary qubits (see
[Scoring](#scoring)), so `T_total = 93237`, `Q_total = 730` and the score is
`49.301369 * 93237 * 730 = 3.356e9`.

The threshold correction leaves the baseline metrics and score unchanged:

| Quantity | Acceptance requirement | Baseline |
| --- | --- | ---: |
| Raw LCU normalization `Lambda` | `> 49.0` | 308.4559397330944 |
| SOS gap `E_gap` (Ha) | `> 3.914898` | 3.965477244291833 |
| Effective normalization `lambda_eff` | Derived score multiplier; no separate floor | 49.30136925057438 |
| Score | All checks pass | 3355599588.3155365 |

[example_submission/angle_k_reference_circuit.py](example_submission/angle_k_reference_circuit.py)
rebuilds the circuits from the `angle_words` in `submission.npz` with kickmix
alone (about 4 s). It writes the same gates as the shipped files (`.kmx`, or
`.kmb` with `--format kmb`), so the score is the same; only the comment lines
at the top of each `.kmx` file differ:

```bash
python dfthcsos/example_submission/angle_k_reference_circuit.py $EX/submission.npz OUT_DIR --brot 12 --batch-size 8
python dfthcsos/verify.py $EX/submission.npz OUT_DIR --tree-edges $EX/submission.npz
```

## What a submission must do

Split the `75` words of every row into `K = ceil(75 / J)` batches of `J`
words (zero padded). Circuit `k` (file `angle_k_<k>.kmx`, applied in order)
is the reversible XOR oracle

```text
ANGLE_k: |a>|z> -> |a>|z XOR delta[k, a]>
delta[0, a] = batch[0, a],   delta[k, a] = batch[k, a] XOR batch[k-1, a]
```

where `a` is the vector address (one-body rows `0 .. 75`, then the `R*B`
two-body rows; `3976` rows for the baseline). Applied in order to `z = 0` the
family streams the batches of row `a` through the word registers; applied in
reverse it clears them.

**Register contract** ([scoreinfra/circuits.py](scoreinfra/circuits.py); named kickmix registers,
little endian):

- `"selection"` holds the address: exactly `ceil(log2(76 + R*B))` qubits.
  Extra selection bits are rejected so workspace cannot be hidden in this register.
- `"word_0"`, ..., `"word_{J-1}"` hold the `J` words of the batch, one
  register per word. **Each word register has `brot` qubits: this is how the
  circuits state their precision.**
- All other qubits are workspace: they start and end in `|0>`, and
  measurement-based uncomputation (`HMR` plus conditioned `CZ`/`CCZ`/`NEG`)
  must leave no phase. Every circuit of the family uses the same public
  registers.
- No `Z_POW` instructions (conditioned or not): every phase must be a
  multiple of pi. The phase check only tells a half turn from no turn, and
  rotations are not counted as Toffolis.

**What the verifier simulates.** Every address is written into `selection`
and the family is run forward (reading the words after each circuit) and then
in reverse. After every circuit the phase must be unflipped, the selection
unchanged and the workspace clean; the padding words beyond `75` must be
zero and the reverse traversal must clear the word registers. kickmix draws
every `HMR` outcome from the seeded simulator, so each address is simulated
`SHOTS_PER_ADDRESS = 64` times with independent outcomes in one batch.
Any observed phase, selection, workspace, padding or reverse-traversal
violation rejects the submission, as does disagreement between repeated
angle-word samples. Any construction is allowed as long as
the simulated circuits load the submitted words;
[example_submission/angle_k_reference_circuit.py](example_submission/angle_k_reference_circuit.py)
builds the baseline one, an ordinary QROM (unary iteration over `selection`)
per batch.

### Statistical interpretation

Passing these checks is evidence from sampled measurement branches, not a
proof of exact correctness on every branch or every target-register input.
At a fixed address and fixed incoming word state, suppose a fixed check
(such as the phase or clean-workspace check) fails with probability `p` on
each independently sampled measurement record. The probability that `s`
shots all miss that failure is `(1 - p)**s`.

For example, a single missing HMR phase correction on a qubit in `|1>` has
`p = 1/2` when its execution is guaranteed, giving `2**-64` for 64 shots.
If there are two separately checked, independent opportunities per shot,
each with failure probability `1/2`, the miss probability is `2**-128`. These are
conditional examples, not universal bounds: a fault enabled only on a rare
measurement branch can have arbitrarily smaller `p`.

The verifier also learns the angle-word table from these samples and uses
each recovered batch as input to the next circuit. Agreement does not prove
that the word is independent of measurement outcomes. For a fixed input
whose word-output probabilities are `q_y`, all `s` samples agree with
probability `sum_y q_y**s`, including the possibility that they all select a
rare output. Consequently, pooling the entire run into a single binomial
confidence bound requires additional justification; the verifier does not
report such a bound. Confidence in a bound on a failure rate is also
different from a bound on the physical circuit error itself.

The probability statements assume fresh independent measurement outcomes
for a fixed candidate and check. Repeating verification with the same
submission and salt repeats the same pseudorandom samples and adds no
independent evidence. A private, unpredictable grader salt kept secret until
submissions are fixed mitigates seed grinding; an empty or public salt does
not. Any overall claim covering many attempted submissions must account for
those attempts.

Every address receives equal sampling effort. Translating these tests into
an error guarantee for a coherent block encoding additionally requires its
actual input weights, the norm-preservation assumptions of the paper's
coherent-error argument, and an error budget across repeated oracle calls.
The verifier does not certify that end-to-end algorithmic error.

## Scoring

```text
score = lambda_eff * T_total * Q_total                      (lower is better)

lambda_eff = sqrt(E_gap * (2 Lambda - E_gap))               of the words the circuits load
T_total    = ANGLES Toffolis                                Toffoli-like gates run per shot in kickmix (U_T and U_T^dagger)
           + outer_state_prep() + inner_state_prep()        heuristic: SpinFreeData_V1 (incl. _dag)
           + 2 * (N - 1) * (2 * brot - 1)                   heuristic: Givens rotations (U_T and U_T^dagger)
Q_total    = outer_persistent + inner_persistent            persistent state-prep qubits (SpinFreeData_V1)
           + J * brot                                       persistent angle-word registers
           + max(outer_temp, inner_temp, angles_temp)       shared temporary workspace
```

- **Rejection.** `verify` raises (`score_from_metrics` returns `numpy.inf`)
  if any `ANGLE_k` circuit uses more
  than 128 qubits (`QUBIT_CAP`); if `error_1` or `error_2` of the recovered
  (quantized) words exceeds 20 mHa; if the SOS gap fails
  `0 < E_gap < 2 * Lambda`; or if raw `Lambda <= 49.0` (`LAMBDA_FLOOR`) or
  `E_gap <= 3.914898` Ha (`E_GAP_FLOOR`). Both thresholds are strict, and the
  measured values are not clamped to them. There is no separate `lambda_eff`
  floor. The 128-qubit limit applies to the ANGLES circuits only
  (`max_k ANGLE_k.num_qubits <= 128`); the state-preparation qubits are not
  limited.
- **Metrics** (defined in the `evaluate_words` docstring in [verify.py](verify.py)):
  `error_1` is the one-body reconstruction residual, `error_2` the two-body
  Frobenius residual against the FCIDUMP integrals, `Lambda` the LCU
  one-norm, `E_SOS` the SOS energy; `E_gap = E_upper - E_SOS` with
  `E_upper = -22140.27335` Ha. Only `E_upper` is fixed: `E_SOS`, `E_gap`,
  `Lambda`, and `lambda_eff` are recomputed for each submission.
- **ANGLES** is the submitted family. The circuits run once forward in `U_T`
  and once in reverse in `U_T^dagger`; their Toffolis are counted by the
  simulator: the mean over all shots of the Toffoli-like gates (`CCX`, `CCZ`,
  `CSWAP`) executed in both passes, where a gate conditioned on a measured bit
  counts only on the shots whose bit is set (for the example's QROMs this is
  `2 * sum_k operation_statistics().num_toffoli_like`, the static bound). In each circuit, `"selection"` is the address register from the state
  preparations, the `J` word registers (`J * brot` qubits) stay live across
  the Givens rotations, and the remaining workspace qubits return to `|0>`
  after each circuit (`angles_temp`).
- **Heuristic** is the rest of one block-encoding pass `O_x` (outer and inner
  state preparations plus the `N - 1` Givens rotations), costed by
  `SpinFreeData_V1` in [scoreinfra/costs_prepare.py](scoreinfra/costs_prepare.py)
  from `R, B, C` (the shape of `w`), `N = 76`, `beta = brot` (the word register
  width) and the fixed `chi = 10` (keep-value bits). Because the outer state
  prep, inner state prep and `ANGLE_k` circuits run sequentially, temporary
  workspace is shared across them (`max` rather than `sum`). For the baseline
  shape this is 846 + 9461 + 3450 = 13,757 Toffolis, 90 persistent qubits and
  544 temporary qubits at `brot = 12` (the example); 846 + 9461 + 4650 = 14,957
  Toffolis, 90 persistent qubits and 1,087 temporary qubits at `brot = 16`.

The raw normalization threshold applies to `Lambda`, not the spectrum-amplified
normalization `lambda_eff` used in the score. At the threshold pair,
`sqrt(3.914898 * (2 * 49.0 - 3.914898)) = 19.19201859236271`.
This is not an independent gate or a global lower bound on `lambda_eff`:
the formula decreases toward zero as `E_gap` approaches `2 * Lambda`.
It would be a lower bound on the additional restricted domain `E_gap <= Lambda`,
but the verifier does not impose that restriction. The Frobenius checks remain
coefficient-error checks; these thresholds do not certify a 20 mHa many-electron
energy error.

Two details of the metric are deliberate and must be kept when editing: the
FCIDUMP two-electron integrals are stored as **float32** before use, and `S`
is rounded to float32 (`scoreinfra/reference.py`, `scoreinfra/dfthc_math.py`); both match the
training code the scores were defined with.
