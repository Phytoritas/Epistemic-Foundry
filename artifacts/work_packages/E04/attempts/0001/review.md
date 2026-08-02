# E04-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  tests/replay/effects (the strict and semantic E-phase replay gate and its
  replay-test-support harness). Reviewer: this seal-prep session, a distinct
  actor that did not author the replay gate. The author never approves its
  own work, so actor_independence HOLDS for this review; external
  actor-independent certification does NOT, and no such claim is made. E04 is
  risk_class=critical and is the replay/provenance truth boundary, so strict
  byte-identity and honest semantic drift were attacked on their contracts
  rather than skimmed.
- Strict reducer equivalence is byte-identical and fails closed. The harness
  rebuilds the append-only E01 Noetic Ledger stream -- the E02 effect events
  (action-intent.recorded, attempt.started, receipt.recorded) and the E03
  capability events (approval.recorded, lease.issued, lease-use.committed,
  lease.revoked) over the sealed C04 artifact store and D04 SQLite state
  store -- and rebuilding the run twice is deepEqual with a matching sha256
  state_hash, seven events in a fixed order, and live-projection parity for
  effects, approvals, leases, and the committed lease-use result. Reopening
  both durable stores preserves stream and reducer identity; exact intent,
  attempt, receipt, approval, lease, lease-use, and revoke retries append no
  events and never re-run the guarded callback; and an EXACT report is minted
  only with event_equivalence=EXACT, drift_classification=NONE, all sixteen
  pinned artifacts matching, zero mismatches, and passing integrity and
  Draft 2020-12 schema. Fail-closed is real, not narrative: a tampered or
  missing payload throws PAYLOAD_HASH_MISMATCH / PAYLOAD_RESOLUTION_FAILED
  before equivalence, a duplicated logical payload identity throws
  E04_REPLAY_SEQUENCE_INVALID, and an event envelope that rebinds a valid
  payload to another aggregate throws E04_REPLAY_EVENT_BINDING_INVALID.
- Semantic drift is reported, never erased. Distinct run and event
  identities are classified SEMANTICALLY_EQUIVALENT and the same comparison
  under strict mode is DRIFT, never falsely EXACT. A changed adapter_model
  pin is MODEL drift and two changed pins are MULTIPLE drift, with BOTH the
  source and replay pin values retained in pinned_artifacts and counted as
  mismatches rather than erased. Gate and verdict changes surface as explicit
  gate_differences and verdict_differences under DRIFT, and a changed
  semantic projection is DRIFT even when gates and verdicts match. A missing
  required pin makes the runs NOT_COMPARABLE with drift_classification=UNKNOWN
  (fail-closed, not a silent EXACT). The report_hash excludes itself and any
  mutation or placeholder fails E04_REPLAY_REPORT_HASH_MISMATCH; a floating
  pin fails E04_PIN_INVALID; an empty or detached strict identity fails
  E04_STRICT_IDENTITY_INVALID; and canonical hashing rejects getters and
  invalid Unicode without ever invoking an accessor (E04_NON_CANONICAL_JSON).
- Dependencies and checks: the replay gate consumes the sealed E02 effect
  reconciliation (E02-0001 PASS) and E03 capability authority (E03-0001 PASS)
  over the sealed E01 ledger, C04 artifact store, and D04 state store, and
  adds no new production dependency; emitted ReplayReports validate against
  the harness's ReplayReport schema. Ruff lint and format, the two required
  checks (strict_replay_test 8/8, semantic_replay_report 10/10), targeted 18/18, full Python 1261/1261, full Node 1291/1291 across 115 files, and git diff --check all pass with
  zero failures.
- Residual limitations: E04 provides the E-phase strict and semantic replay
  gate only; the wider scheduler, effects execution, promotion, and evolution
  surface remain later packages. Verdict: PASS on the exact E04 package
  contract.
