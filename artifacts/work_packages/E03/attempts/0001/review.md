# E03-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  packages/foundry-kernel/src/capabilities. Reviewer: this seal-prep
  session, a distinct actor that did not author the capability authority.
  The author never approves its own work, so actor_independence HOLDS for
  this review; external actor-independent certification does NOT, and no
  such claim is made. E03 is risk_class=medium and governs bounded
  authority, so leases, fencing, and approval were attacked on their
  contracts rather than skimmed.
- Leases are scoped and expiring (fail closed). issueLease binds every
  lease to a sealed PolicyBundle subject and its declared run and resource
  scopes; a run or scope drift is denied with LEASE_RUN_SCOPE_MISMATCH or
  LEASE_SUBJECT_SCOPE_MISMATCH, and a zero or negative lifetime fails with
  LEASE_ALREADY_EXPIRED before the global fencing counter is ever created.
  commitWithLease refuses to invoke or persist the caller callback on an
  expired lease (LEASE_EXPIRED at the exact expires_at boundary), a clock
  before issued_at (LEASE_NOT_YET_VALID), a revoked lease (LEASE_REVOKED),
  or a changed policy (LEASE_POLICY_MISMATCH). An expiry or authority clock
  regression that happens after the callback has already staged a
  revisioned record rolls that record back so nothing persists
  (LEASE_EXPIRED, CLOCK_REGRESSION), and an exact lease-issuance or
  operation retry returns the first logical lease rather than minting a
  second. Issued leases are deep-frozen, schema-valid against the canonical
  Draft 2020-12 capability-lease schema, and carry a sha256 lease_hash.
- Fencing prevents split-brain (monotonic token). The global fencing token
  is monotonic: a newer overlapping lease is issued at old_token+1, and the
  stale holder's later commit fails closed with STALE_FENCING_TOKEN without
  persisting its mutation, so two holders never both act. Replacing even
  one scope of a multi-scope lease invalidates the whole prior lease. A
  forged fencing token or any other tampered lease field is caught by the
  sealed lease_hash (LEASE_HASH_MISMATCH) before the callback runs; the
  callback cannot read authority-private scope-head state
  (CAPABILITY_STATE_ACCESS_DENIED); an async callback is denied and its
  pre-await mutation rolls back (ASYNC_LEASE_COMMIT_DENIED); a thrown
  callback rolls back result, lease-use, and event outbox
  (LEASE_COMMIT_CALLBACK_FAILED); and a lease committed through a
  transient E01 outage reconciles its single event exactly once. A same
  policy_hash carrying a different capability projection is rejected
  (LEASE_POLICY_PROJECTION_MISMATCH).
- Approval is explicit, never implicit. A privileged capability
  (promotion:commit) cannot be leased without a matching approval
  (REQUIRED_APPROVAL_MISSING) and passes only with the exact prior
  approval. The approval authority_role is server-derived from the sealed
  policy: a client that asserts its own authority_role is rejected
  (INVALID_INPUT), a principal cannot approve its own subject
  (SELF_APPROVAL_DENIED), an approver role without approval:issue is denied
  (CAPABILITY_NOT_AUTHORIZED), and a candidate/model/backend principal that
  tries to hold privileged authority is refused at policy seal time
  (UNTRUSTED_AUTHORITY_GRANT_DENIED). A later REVOKE approval head
  invalidates an earlier APPROVE-bound lease, and the approval head itself
  rejects clock regression (APPROVAL_CLOCK_REGRESSION) and same-instant
  conflicting decisions (APPROVAL_TIMESTAMP_CONFLICT).
- Dependencies and checks: the capability authority builds on the sealed
  E01 append-only Noetic Ledger (E01-0001 PASS) over the sealed C04
  artifact store and D04 SQLite state store and adds no new production
  dependency; emitted leases and approvals validate against the canonical
  Draft 2020-12 capability-lease and approval-record schemas. Ruff lint and
  format, the two required checks (lease_expiry_test 11/11, fencing_test 19/19), targeted 30/30, full Python 1261/1261, full Node 1253/1253 across 111 files, and git diff --check all pass with
  zero failures.
- Residual limitations: E03 provides capability leases, fencing, and the
  approval policy only; the E-phase strict and semantic replay gate (E04)
  and the wider scheduler, effects execution, and promotion surface remain
  later packages. Verdict: PASS on the exact E03 package contract.
