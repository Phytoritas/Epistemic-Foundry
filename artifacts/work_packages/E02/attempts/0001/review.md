# E02-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  packages/foundry-kernel/src/effects. Reviewer: this seal-prep session, a
  distinct actor that did not author the effect coordinator. The author
  never approves its own work, so actor_independence HOLDS for this review;
  external actor-independent certification does NOT, and no such claim is
  made. E02 governs external side effects, so ActionIntent, Attempt,
  EffectReceipt, idempotency, and reconciliation were attacked on their
  contracts rather than skimmed.
- Receipts are immutable and re-derivable. ActionIntent and EffectReceipt
  are sealed as canonical JSON whose intent_hash and receipt_hash are the
  sha256 of their canonical bytes, each excluding only its own hash field.
  A stored EffectReceipt that is force-rewritten fails closed with
  EFFECT_RECORD_MUTATED; a tampered intent is caught by
  ACTION_INTENT_HASH_MISMATCH; a hostile getter is never invoked and is
  rejected with NON_CANONICAL_JSON; a Proxy is rejected with
  ACTION_INTENT_INVALID. Emitted ActionIntent and EffectReceipt documents
  validate against the canonical Draft 2020-12 schemas/action-intent and
  schemas/effect-receipt schemas, and cross-intent binding is refused.
- Idempotent retry never double-applies. The same idempotency key with the
  same canonical intent replays one logical registration (EXISTING, not a
  second write and not a second ledger event); the same key with a different
  canonical request fails with IDEMPOTENCY_KEY_REUSED; rebinding an intent id
  to different bytes fails with INTENT_ID_CONFLICT. beginAttempt grants
  execute_permitted exactly once: a replay returns EXISTING_ATTEMPT with
  execute_permitted=false, an attempt id reused across intents fails with
  ATTEMPT_ID_CONFLICT, a receipt id reused across intents fails with
  RECEIPT_ID_CONFLICT, and two worker-thread callers racing a shared barrier
  on the same attempt see exactly one execution grant while both observe the
  single durable Attempt. Older attempt and receipt replays remain idempotent
  after later attempts.
- Reconciliation is exact, never narrated. An UNKNOWN receipt leaves the
  operation RECONCILING (completion_proven=false, retry_permitted=false) and
  a blind retry is denied with EFFECT_RECONCILIATION_REQUIRED until an
  observed reconciliation with a verified result artifact or observed state
  hash resolves it. A crash before any receipt is inspected as RECONCILING /
  UNKNOWN, not a narrated success or failure. An unsealed 'the executor says
  it completed' receipt is rejected (EFFECT_RECEIPT_INVALID) and a resolving
  receipt without observation evidence fails
  EFFECT_RECEIPT_RESOLUTION_EVIDENCE_REQUIRED, so executor narration cannot
  replace an evidence-bound EffectReceipt. Reconciliation may not change the
  observed external operation identity
  (EFFECT_RECONCILIATION_OPERATION_MISMATCH). A durable record whose ledger
  event or publication checkpoint did not confirm stays
  PENDING_EVENT_RECONCILIATION or PENDING_EVENT_CONFIRMATION, blocks verify
  with EFFECT_EVENT_RECONCILIATION_REQUIRED / EFFECT_EVENT_CONFIRMATION_REQUIRED,
  and is repaired only by exact replay without granting a second execution.
- Dependencies and checks: the coordinator builds on the sealed E01
  append-only Noetic Ledger (E01-0001 PASS) over the sealed D04 SQLite state
  store and C04 content-addressed artifact store, and adds no new production
  dependency. Ruff lint and format, the two required checks
  (effect_reconciliation_test 10/10, idempotency_test 9/9), targeted 19/19,
  full Python 1261/1261, full Node 1253/1253 across 111 files, and git diff --check all pass with
  zero failures.
- Residual limitations: E02 proves local E01/D03/D04 reconciliation and
  idempotent coordination, not the truth of arbitrary external-service
  outcomes beyond supplied resolving evidence, and local serialization is
  not a universal distributed exactly-once guarantee. Attempt and the
  publication checkpoint remain private runtime projections and create no
  new canonical schema authority. Capability leases and approval policy
  (E03) and the wider replay surface remain later packages. Verdict: PASS on
  the exact E02 package contract.
