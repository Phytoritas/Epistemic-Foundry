# Status, receipts, and revisions

- Use `PASS`, `FAIL`, `BLOCKED`, and `SPEC_GAP` truthfully: implementation failure is not a contract gap, and missing infrastructure is not failure.
- Every effect starts from an `ActionIntent` and resolves through an `EffectReceipt`; every artifact claim has an `ArtifactReceipt`.
- Canonical records are immutable revisions. Corrections, promotions, invalidations, and replays append new records rather than overwriting history.
- Retries bind an idempotency key and canonical request hash. Same key plus different input is a conflict.
- A crash without a resolving receipt is not success. Reconcile external state and ledger state before retrying or reporting completion.
