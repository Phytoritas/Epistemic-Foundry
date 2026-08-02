# E01-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  packages/foundry-kernel/src/ledger. Reviewer: this seal-prep session, a
  distinct actor that did not author the ledger. The author never approves
  its own work, so actor_independence HOLDS for this review; external
  actor-independent certification does NOT, and no such claim is made. E01
  is risk_class=critical, so the append-only ledger, its hash chain, and
  its rebuild were attacked on their contracts rather than skimmed.
- Append-only immutability. Each EventRecord is written once at revision 0
  and is never updated or deleted; the public surface exposes only append
  and read operations. A stored event whose revision was forced non-zero
  fails closed with EVENT_RECORD_MUTATED, an exact retry of the same event
  is idempotent (EXISTING, not a second write), and rebinding an event id
  to a different actor or payload is denied with EVENT_ID_CONFLICT. Reads
  return deep-frozen events, and a partial append (missing payload or an
  invalid input carrying an extra field) leaves no event and no run-stream
  state behind.
- Hash chain and ordering. append assigns the next contiguous per-run
  sequence and links previous_event_hash to the verified run tail; the
  first event of every run links to null and independent runs each restart
  at sequence one. verifyEventChain recomputes each event_hash over its
  canonical fields and fails closed on sequence gaps or reorder
  (EVENT_SEQUENCE_MISMATCH), field tamper (EVENT_HASH_MISMATCH), a cross-run
  splice (EVENT_RUN_MISMATCH), a coherently revised stream that references a
  missing immutable event (EVENT_RECORD_MISSING), and a provider-neutral
  adapter byte change caught by the sealed payload hash
  (PAYLOAD_HASH_MISMATCH). Hash validation reads data properties only and
  never triggers a toString coercion hook. Two worker-thread writers racing
  a shared barrier serialize through the run-stream compare-and-swap into
  one contiguous chain, and a rejected stream commit rolls back the new
  immutable event so the run tail is unchanged.
- State is rebuildable. rebuild re-resolves and hash-verifies every payload
  before any reducer runs, then executes the caller's synchronous reducer
  twice and asserts an identical canonical trace. Non-deterministic
  (REDUCER_NON_DETERMINISTIC), async (ASYNC_REDUCER_DENIED), input-mutating
  (REDUCER_FAILED), and non-JSON (REDUCER_OUTPUT_INVALID) reducers are
  rejected; JSON payload decoding rejects invalid UTF-8, a UTF-8 BOM, and
  malformed syntax; and canonical state hashing rejects hidden array
  properties. Reopening both the D04 SQLite state store and the C04 artifact
  store reproduces byte-identical state and state_hash, an empty run
  preserves the canonical initial state without invoking the reducer, and
  the caller supplies occurred_at so rebuild carries no hidden clock.
- Dependencies and checks: the ledger builds on the sealed C04
  content-addressed artifact store (C04-0001 PASS) and the sealed D04 SQLite
  state store (D04-0001 PASS) and adds no new production dependency; emitted
  records validate against the canonical Draft 2020-12
  schemas/event-record.schema.json. Ruff lint and format, the two required
  checks (ledger_hash_chain_test 12/12, reducer_replay_test 9/9), targeted
  21/21, full Python 1261/1261, full Node 1253/1253 across 111 files, and git diff --check all pass with
  zero failures.
- Residual limitations: E01 provides the append-only ledger, its hash
  chain, and deterministic rebuild only; ActionIntent, Attempt, and
  EffectReceipt (E02) and the wider effects, capability, and replay surface
  remain later packages. Verdict: PASS on the exact E01 package contract.
