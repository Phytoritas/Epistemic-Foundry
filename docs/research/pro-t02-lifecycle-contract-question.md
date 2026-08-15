# Epistemic Foundry T02 → E02 lifecycle authority decision

Continue from the prior O01 review in this conversation. This is a separate, independent blocker. Use the previously attached `MASTER_SPEC.md` and development manifest together with the new T02/E02 files.

## Verified defect

The current T02 mutation handler performs approximately:

```text
reserve idempotency key
→ persist local intent-shaped mapping
→ execute external effect
→ persist local receipt-shaped mapping
→ finally bind intent/receipt to the reservation
```

A crash after the external effect but before receipt/binding leaves the reservation without an attempt signal. Replay can interpret that state as not started and execute the effect again.

E02 already distinguishes durable Intent, Attempt, Receipt, and reconciliation. T02 currently exposes separate reservation, intent-store, receipt-store, and executor ports rather than a single atomic lifecycle authority.

## Observed contract mismatches

- Canonical `ActionIntent` requires fields such as `run_id`, `node_id`, `arguments_artifact_id`, `created_at`, and `intent_hash`; the T02 common mutation request does not supply all of them.
- Canonical `EffectReceipt` requires fields such as `run_id`, `started_at`, `finished_at`, and `receipt_hash`; T02's local receipt shape does not supply all of them.
- T02 catalog risk classes are `medium` / `high` / `critical`, while canonical `ActionIntent.risk_class` uses `read_only` / `bounded_compute` / `controlled_effect` / `high_risk`.
- T02 source ownership and E02 kernel ownership are separate, and no explicit Python-to-kernel lifecycle port has been located.

## Decision question

Do the attached higher-authority sources already imply one unique provider-neutral T02→E02 integration contract that can be implemented without changing shared semantics, or is this a genuine `SPEC_GAP`?

Return exactly one top-level verdict:

- `AUTHORIZED`, only if all required field sources, risk mapping, atomic lifecycle operations, replay states, and ownership boundary are uniquely derivable; or
- `SPEC_GAP`, if any materially different choices remain compatible with authority.

If `AUTHORIZED`, provide:

1. the exact `MutationLifecyclePort` operations and atomicity boundaries;
2. the authoritative source of every canonical `ActionIntent`, Attempt, and `EffectReceipt` field;
3. the exact risk-class mapping;
4. crash/replay/reconciliation state transitions;
5. the smallest in-scope file changes and migration consequences;
6. adversarial cases for effect-after-crash, concurrent same-key requests, replay mutation, and dry-run isolation.

If `SPEC_GAP`, provide:

1. the smallest unresolved human decision;
2. every missing field/risk/lifecycle/ownership binding;
3. mutually exclusive viable integration choices;
4. the canonical owner paths that must freeze the decision;
5. which T03+ packages remain blocked.

Do not treat a local copy of E02's state machine as authority. Do not approve a two-stage `bind_intent`/`bind_receipt` patch unless it truly closes every crash window. Distinguish self-hash integrity from durable effect authority and external exactly-once guarantees.
