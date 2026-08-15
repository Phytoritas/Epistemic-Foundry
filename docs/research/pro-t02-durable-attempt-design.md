# T02 durable Attempt and crash-idempotency design review

Advise on the smallest authorized T02-local repair for this confirmed crash-order defect. Repository authority wins; do not propose evidence packets or broad refactors.

Authority and scope:

- `MASTER_SPEC.md` defines E02 as `ActionIntent, Attempt and EffectReceipt`, with unknown effects reconciled before retry.
- E02's current `effect-coordinator.mjs` persists a canonical Attempt transactionally before execution. Intent with no Attempt is `NOT_STARTED` and retryable; Attempt with no receipt is `UNKNOWN/RECONCILING` and not retryable.
- T02 is `MCP mutating tools with intents and receipts`, depends on T01, and `HD-EF4-T02-SCOPE-20260801-002` authorizes `src/epistemic_foundry/application/mcp_mutating/**` and `tests/mcp/t02/**` in addition to the manifest path.
- No shared schema or E02 source change is proposed.

Current T02 defect:

1. `reserve()` records only fingerprint plus optional intent/receipt IDs.
2. Handler persists the intent.
3. It executes the external effect.
4. It persists the receipt.
5. Only then does `idempotency.bind(intent_id, receipt_id)`.

A crash after external execution but before receipt/bind leaves the reservation with no intent ID. Replay treats that state as effect-not-started and may execute the same effect again. The current test also wrongly treats every `intent_id + no receipt` state as unknown, although E02 requires an actual durable Attempt to distinguish it from `NOT_STARTED`.

Proposed bounded repair:

- Extend the T02 reservation projection with a monotonic CAS revision and `stored_attempt_id`.
- Add idempotent/CAS reservation transitions: bind the deterministic persisted intent; atomically create and bind one durable Attempt immediately before any live effect; bind a receipt after it is stored.
- Make the Attempt transition return `execute_permitted`; a pre-existing Attempt never grants execution again.
- Extend the receipt-store port with create-or-existing persistence keyed by Attempt plus `find_for_attempt()`. This closes a crash after receipt persistence but before the reservation receipt-ID bind: replay adopts the already stored receipt instead of minting a false UNKNOWN or executing again.
- Replay precedence: current receipt for Attempt -> stored receipt ID -> if Attempt exists but no receipt, create one UNKNOWN receipt and fence execution -> if no Attempt, continue safely (reusing a persisted deterministic intent when present).
- Generate stable intent and Attempt IDs from the already deterministic candidate/request binding, so a crash between intent persistence and reservation binding cannot create distinct logical intents.
- For dry-run, perform the read-only preview first, then persist the Attempt, then record `NOT_EXECUTED`; for a live call, persist the Attempt immediately before `executor.execute()`.
- Keep `EffectReceipt` public shape and mutation-result schema unchanged; Attempt identity remains internal to the lifecycle port, matching E02's journal binding.
- Update only T02 production ports/handler/reconciliation helpers and T02 test harness/source. Do not change E02, shared schemas, catalogs, manifests, or T01.

Question: Is this package-local composition authorized and sufficient? Return either `AUTHORIZED` with any exact must-have CAS/ordering corrections, or `SPEC_GAP` naming the missing shared decision. Focus on at-most-once effect safety, crash states, concurrent replay, and E02 semantic alignment. Do not ask to run tests.
