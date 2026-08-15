# T02 durable Attempt implementation review

Review the implemented T02-local repair described below against your prior `AUTHORIZED` design answer and repository authority. Return `NO_BLOCKER` or only material correctness, authority, compatibility, or concurrency blockers. Ignore style and do not ask to run tests.

Changed production paths are limited to the authorized T02 package, its local error-details schema, and adopted architecture document:

- `src/epistemic_foundry/application/mcp_mutating/{ports.py,handler_factory.py,reconciliation.py,service.py,__init__.py}`
- `contracts/mcp/t02/schemas/mutation-error-details.schema.json`
- `docs/t02_mutating_tool_architecture.md`
- T02 test harness/source only

Implemented lifecycle contract:

1. `Reservation` now carries monotonic `revision`, `stored_intent_id`, `stored_attempt_id`, and `stored_receipt_id`.
2. `IdempotencyReservationPort` now exposes fingerprint-bound CAS transitions `bind_intent`, `begin_attempt`, and `bind_receipt`. `begin_attempt` atomically creates/binds the full E02 Attempt and returns `AttemptTransition(attempt, reservation, execute_permitted)`. Only a fresh transition may execute.
3. Handler derives deterministic `intent_id` from the full semantic fingerprint. The immutable Intent store is create-or-existing under that ID. Existing approval candidate-ID derivation was preserved for compatibility.
4. Handler accepts a canonical store-provided `intent_hash` only when re-derivable; otherwise it derives a stable hash from the persisted Intent. `attempt_id` derives only from intent ID/hash plus fixed attempt number 1, never retry time.
5. Before trusting the Attempt transition, handler requires the exact eight E02 Attempt fields, re-derives `attempt_hash`, validates ID/Intent/hash/idempotency/number/start bindings, and checks the reservation revision transition.
6. All ordinary refusals remain before the Attempt barrier: lifecycle reserve/Intent bind, lease revalidation, expected revision, and dry-run preview. A live winner calls `executor.execute()` immediately after the successful Attempt transition. No authority operation is inserted between them.
7. Execution receipts include the Attempt start and current finish timestamps and are persisted create-or-existing against the exact Attempt. Returned receipt identity, Intent, key, status/reconciliation projection, and start time are checked before CAS binding.
8. Receipt storage exposes `find_for_attempt()` and predecessor proof. Replay prefers the current Attempt tail, cross-checks any reservation receipt, adopts a receipt persisted before a crash, and never executes when an Attempt already exists.
9. Attempt-without-receipt ordinary replay does not fabricate UNKNOWN. It returns the retryable T02-local `EFFECT_RECONCILING` mutation subcode through the unchanged sealed T01 `INTERNAL` envelope, with `reconciliation_required=true`. This subcode was added only to the T02-owned error-details enum/mapping; the shared T01 envelope and mutation-result schema are unchanged.
10. `UNKNOWN` remains an actual receipt state. Reconciliation appends a terminal successor, receipt-tail replay accepts it only with predecessor proof, and `outstanding_receipts()` stops reporting a resolved predecessor while retaining it append-only.
11. `reconciliation_report()` now requires explicit Attempt inputs. Intent without Attempt is `NOT_STARTED` and carries no receipt obligation; Attempt without receipt is missing/reconciling.

The strict in-memory T02 harness models revision 0→Intent→Attempt→receipt, deterministic full Attempt hashes, create-or-existing receipts per Attempt, reconciliation tails, and predecessor proofs. Added regression source covers: Attempt/no receipt fences without UNKNOWN or execution; receipt persisted before reservation bind is adopted; reservation/no Intent and Intent/no Attempt safely continue; one committed call produces exactly one Attempt and revision 3; and replay after reconciliation returns the terminal tail without a second effect.

No E02/kernel source, shared schemas, manifests, T01 files, catalogs, or generated descriptors were changed. The port remains an injected consumer contract; it does not claim a live Python-to-E02 binding or a second lifecycle store.
