# Pinned sources

| Component | Revision |
|---|---|
| Dream-RSI | `8ec35bd2538220517ce1bfca4282db21b8c518db` |
| GIFT-Eval | `3c7be6deffb0046e1c08f9103db8bc84b3cf7ebd` |
| GIFT data | `30841734ac5cfddbd0c3bad6d09d2b6b32becbb0` |
| TSB-AD | `303dffbfc11612995b17b06633f8c9d0ea0e38e5` |
| RCAEval | `2fca61b9730a69c21ef72411844735634dbb010f` |
| RCAEval RE1 data | `afeacb11bcc94dadfd1c8f483ee4377b2b8b614e` |
| LibraryTS / sktime | `904bb75717d5f83e9d8177affae2113c9ee3f6b3` |
| Toto source | `9213d2c86f716c43010a0a3b2b6a0e3f440e6743` |
| Timestral source | `a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff` |
| granite-tsfm source | `dfe846e6c1f1b0086b4a7b0831249ac8aeb7dcd7` |

The worker dependency lock and intentional overrides are provided under the forecasting task. Docker base tags and unpinned transitive dependencies can change; retain locally generated image IDs, source download checksums, model revisions and environment snapshots with a campaign if exact reproducibility is needed. Most checkpoint entries currently identify repositories rather than immutable model revisions: setup downloads the available revision and should be recorded before running comparative experiments.
