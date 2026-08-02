# E02 ActionIntent, Attempt and EffectReceipt review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Final verdict: `PASS`

blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

The product owner requires serial primary-session execution without Fleet or
subagents and explicitly authorizes the independent-review artifacts. This is a
procedurally separate adversarial review of the final E02 bytes. It is not
external actor-independent certification.

## Authority and reviewed boundary

- `MASTER_SPEC.md`, `MASTER_EXECUTION_PROMPT.md`, `AGENTS.md`, and E02 in
  `manifests/development_manifest.yaml`;
- invariant `EF4-I13` (receipt-bound completion);
- canonical `schemas/action-intent.schema.json` —
  `sha256:acaf9861436d3217c579f7eed518f2f138261a4a8cc1cb750c97a52ad908b0b1`;
- canonical `schemas/effect-receipt.schema.json` —
  `sha256:2fc5f33eaea8dd86ebbdb59c2c9d6075d4b2d7c9f03bab304c550dfd80d1a4cc`;
- E01 dependency report —
  `sha256:beddc2a3019fcf680435ea6d5f907b5e7b50b0fa8a384673917c6198f49f32e1`;
- unchanged dependency implementations: D01 SQLite store
  (`sha256:6619dccb72f40e92fdaae3d023a2d6591f8d63bdfe789ba5c36b53ce7dbe1380`),
  D03 artifact store
  (`sha256:75e69756d30ab5b5112fd908f3fec312660f30e603fe1201566db2ad263c8c8e`),
  and E01 Noetic Ledger
  (`sha256:58ea9dc0d52d9c20720b33970ee3b8d8d05703ba7dd0fb4f51a483d9f505f1ed`);
- final E02 files:
  - `packages/foundry-kernel/src/effects/effect-coordinator.mjs` —
    `sha256:a4d2b9b851f9055869db842d10702e6017a61c18fcc637521fdec398b5abc1f2`;
  - `packages/foundry-kernel/src/effects/effect-test-support.mjs` —
    `sha256:df45bdec72a2ed2ffda922189e21f1102cc1cdcf2c50d661f9ac1e98051c0a4a`;
  - `packages/foundry-kernel/src/effects/effect-reconciliation.test.mjs` —
    `sha256:998a962b3e193e3b497aa60078f5f3d650332d88f973d81d3b167be025a13402`;
  - `packages/foundry-kernel/src/effects/idempotency.test.mjs` —
    `sha256:0d386c1eb2ded877423979838d604e1270ec4112b82f162d2d2222924fda5dec`.

E02 owns only `packages/foundry-kernel/src/effects/**` and
`artifacts/work_packages/E02/**`. No canonical schema, E01 ledger, D01 state
store, D03 artifact store, manifest, or other package implementation was
changed to make E02 pass.

## Adversarial findings

1. **Canonical intent and receipt integrity — PASS.** ActionIntent and
   EffectReceipt accept only plain canonical JSON data, bind all schema fields
   except their own hash, validate exact `sha256:` forms, and validate against
   the unchanged Draft 2020-12 authorities. Accessors, Proxies, hostile
   coercion, sparse arrays, hidden properties, invalid timestamps, and mutated
   sealed records fail before authority-bearing work occurs.
2. **Attempt authority and persistence — PASS.** Attempt is an E02-private
   runtime projection rather than an invented public schema. Intent, Attempt,
   EffectReceipt, the operation journal, idempotency binding, and publication
   checkpoint are persisted through D01. Immutable record IDs cannot be rebound
   and journal revision, attempt number, chronology, lineage, and receipt order
   reconcile on every read.
3. **Idempotency and concurrency — PASS.** The same key and canonical request
   resolve one logical intent; the same key with a changed request fails with
   `IDEMPOTENCY_KEY_REUSED`. Exact retries return immutable prior results.
   Concurrent callers for the same attempt serialize so exactly one receives
   `execute_permitted=true`. Replaying an older immutable attempt or receipt
   remains idempotent after later attempts exist.
4. **Unknown-effect reconciliation — PASS.** A started attempt without a
   resolving receipt and an `UNKNOWN` receipt both block retry. Reconciliation
   must supply verified result/error artifact evidence or an
   `observed_state_hash`, retain any non-null external operation identity, and
   complete before a later attempt may begin. `external_operation_id` alone is
   never treated as observation evidence.
5. **No narrative completion — PASS.** Executor narration and unsealed objects
   have no completion authority. A `SUCCEEDED` receipt must bind a verified
   result artifact or observed-state hash. `FAILED`, `NOT_EXECUTED`, and
   `ROLLED_BACK` likewise require resolving evidence; otherwise retry remains
   closed. Exact argument bytes and all receipt-linked artifacts are re-read
   through D03 before verification.
6. **Ledger/outbox crash recovery — PASS.** D01 first commits the immutable
   operation record. D03/E01 publication is then verified, followed by a D01
   publication checkpoint. A crash before the receipt, after the ledger append,
   or before checkpoint confirmation does not produce completion. Exact replay
   repairs missing publication or confirmation without duplicating execution,
   and event order, payload hash, identity, and ledger chain are revalidated.
7. **Authority separation — PASS.** E02 coordinates already-authorized effects;
   it does not issue capabilities, approvals, promotion decisions, or policy.
   It never calls an external executor itself. E03 retains capability and
   approval authority, while downstream packages retain domain-specific effect
   execution and promotion authority.
8. **Regression and repeatability — PASS for E02.** The final targeted gate is
   19/19, five prior repeats are 95/95, and coverage of the coordinator is
   86.31% lines, 74.17% branches, and 97.94% functions. Python is 913/913.
   Structure, boundaries, toolchain/lock, CI matrix/cache, ten CI policy tests,
   syntax, strict UTF-8, and `git diff --check` pass. Final repository-wide Node
   discovery is 189 passed with only the existing out-of-scope `S04-TM004`
   stale manifest-hash binding.

## Preserved failed and residual observations

- An earlier repository-wide Node run recorded 188 passed and 2 failed. In
  addition to `S04-TM004`, one D03 reader observed Windows `EPERM` while the
  artifact-store mutation lock was handed off and entered
  `ARTIFACT_STORE_STRUCTURE_INVALID`. The exact D03 test then passed alone
  (1/1, about 49.8 seconds), and the subsequent full Node run passed that same
  test while producing 189/190 overall. This first failure is retained as an
  intermittent Windows concurrency observation owned by D03; it is not hidden
  or converted into proof that the platform race cannot recur.
- `scripts/build/double_build.py` still fails while building its staged source
  because the staged tree omits the existing `scripts/` build-hook package.
  E02 has no B02/B04 packaging write authority, so the failure is preserved as
  an out-of-scope integration residual.

## Assurance limitations

- The coordinator proves durable local D01/D03/E01 reconciliation. It does not
  prove that an arbitrary external service performed an operation correctly;
  that claim remains limited to the supplied resolving artifacts or observed
  state and the later domain-specific qualification gates.
- Local SQLite transactions serialize E02 tests, but this package does not
  claim distributed exactly-once execution, remote consensus, or cross-region
  availability. Idempotency plus reconciliation gives at-most-one execution
  permission within the qualified store boundary, not a universal exactly-once
  theorem.
- ActionIntent and EffectReceipt are canonical public artifacts. Attempt and
  the publication checkpoint are private E02 runtime projections and do not
  create additional canonical schema authority.
- The separate review is user-authorized and procedurally independent within
  the primary session; it is not external actor-independent certification.

## Decision

E02 satisfies its exact package contract. Side effects cannot complete by
narration, unresolved or unknown effects reconcile before retry, and the
idempotency, ledger publication, crash, and evidence boundaries fail closed.
The overall Foundry objective remains active and `completion_ready=false`.
