# AUTHORIZED

The bounded T02 repair is authorized **as a T02-local lifecycle-port and handler correction**. It directly repairs the current false inference that “no bound intent means no effect started,” while preserving E02’s authoritative distinction:

* intent without Attempt → `NOT_STARTED`, retry permitted;
* Attempt without a resolving receipt → `RECONCILING`, retry forbidden. 

T02’s manifest expressly owns mutating tools with intents and receipts and requires effects to reconcile; the stated HumanDecision extends that ownership to the named Python and test paths.  The change must nevertheless remain a **consumer-side lifecycle contract**: current T02 ports explicitly say that they do not themselves reach a live store and that kernel binding comes later. 

## Required CAS contract

`Reservation` may add:

```python
revision: int
stored_intent_id: str | None
stored_attempt_id: str | None
stored_receipt_id: str | None
```

The lifecycle authority must expose monotonic, linearizable operations equivalent to:

```python
reserve(
    *,
    idempotency_key: str,
    fingerprint: str,
) -> Reservation

bind_intent(
    *,
    idempotency_key: str,
    expected_revision: int,
    intent_id: str,
) -> Reservation

begin_attempt(
    *,
    idempotency_key: str,
    expected_revision: int,
    intent_id: str,
    attempt_id: str,
    started_at: str,
    dry_run: bool,
) -> AttemptTransition

bind_receipt(
    *,
    idempotency_key: str,
    expected_revision: int,
    attempt_id: str,
    receipt_id: str,
) -> Reservation
```

`AttemptTransition` must return the durable Attempt projection, the new reservation revision, and `execute_permitted`.

The following rules are mandatory:

1. `revision` starts at a fixed value and increases exactly once per successful transition.
2. Every transition compares the expected revision and fingerprint atomically.
3. Repeating the same transition with the same identifier is idempotent.
4. A populated field may never be cleared or changed to another identifier.
5. `begin_attempt` must create the full Attempt and bind `stored_attempt_id` in **one transaction**. A separate `persist_attempt()` followed by `bind_attempt()` would recreate a crash window.
6. Only the transaction that first creates the Attempt returns `execute_permitted=True`. An existing Attempt always returns `False`, including when the supplied deterministic Attempt ID is identical.

This mirrors E02’s current transactional `beginAttempt`: existing attempts return `execute_permitted:false`, while only a freshly committed Attempt permits execution.  

## Stable identity requirements

A stable identifier alone is not an execution fence, but it is necessary for recovering from crashes between store operations.

* The ActionIntent store must use create-or-existing semantics keyed by deterministic `intent_id`.
* Existing content under that ID must be byte-equivalent; otherwise fail with an integrity or ID-conflict error.
* `intent_id` must derive from the canonical semantic request binding, including the idempotency key or fingerprint, tool/operation, workspace, target, principal binding, dry-run mode, and argument hash.
* `attempt_id` must derive from the exact persisted Intent identity/hash and the fixed first-attempt number. It must not include the current retry timestamp.
* A changed request under the same idempotency key remains `IDEMPOTENCY_CONFLICT`.

This closes the crash between intent persistence and reservation binding without treating mere intent existence as proof that execution started.

## Exact execution order

All checks capable of ordinary pre-execution refusal must occur **before** the Attempt barrier:

```text
reserve/load reservation
→ validate fingerprint
→ create-or-load deterministic Intent
→ CAS-bind Intent
→ revalidate lease
→ check expected revision
→ perform any other pure pre-execution checks
```

For a live mutation:

```text
CAS begin_attempt
→ require execute_permitted=True
→ executor.execute exactly once
→ validate EffectOutcome
→ persist the receipt against that exact Attempt
→ CAS-bind the receipt
→ return the existing mutation result
```

No retry, policy lookup, approval lookup, revision check, lease check, or other fallible authority operation may be inserted between successful `begin_attempt` and `executor.execute()`. Otherwise a routine pre-execution refusal would unnecessarily leave a durable unresolved Attempt.

For dry-run:

```text
read-only preview
→ CAS begin_attempt
→ only the winner persists deterministic NOT_EXECUTED
→ CAS-bind receipt
```

This ordering is valid only because `preview()` is contractually non-mutating. A crash before the dry-run Attempt may repeat the preview, but it cannot duplicate an external effect. If `preview()` is not guaranteed read-only, it must move behind its own effect authority rather than being treated as preview.

## Required replay correction

The proposed rule—

```text
Attempt exists + no receipt
→ immediately create UNKNOWN receipt
```

—must **not** run in an ordinary concurrent replay.

A second request can observe the Attempt while the first caller is still inside `executor.execute()`. If the second caller creates an `UNKNOWN` execution receipt first, the original terminal outcome may be rejected or hidden by the create-or-existing receipt index. E02 deliberately represents an Attempt with no receipt as `RECONCILING` without fabricating a receipt. 

The replay order must instead be:

```text
1. Validate the reservation and fingerprint.

2. If an Attempt exists:
   a. obtain the receipt-store tail for that Attempt;
   b. if a receipt exists, validate its Intent/Attempt/idempotency binding,
      CAS-adopt its receipt ID, and return it;
   c. if no receipt exists, return/fail closed as RECONCILING with
      execute_permitted=False;
   d. never invoke executor.execute.

3. If no Attempt exists:
   a. create-or-load the deterministic Intent;
   b. CAS-bind it if needed;
   c. compete through begin_attempt;
   d. execute only if that call returns execute_permitted=True.
```

A reservation `stored_receipt_id` and `find_for_attempt()` result must be cross-checked, not treated as two unrelated sources. If they disagree, accept the receipt-store tail only when the store proves that the reservation’s receipt is its predecessor; otherwise raise an integrity failure.

## UNKNOWN and late terminal outcomes

An `UNKNOWN` receipt may be appended only by an explicit recovery/reconciliation path, not merely because another request arrived while execution could still be active.

If T02 retains automatic recovery after a separately established abandoned-execution transition, then all of the following are required:

* UNKNOWN receipt identity is deterministic for the Attempt.
* Its `started_at` equals the Attempt’s `started_at`.
* `external_operation_id` is `null` unless a real provider operation ID was observed. A synthetic non-null identifier must not block a later real operation identity.
* A late terminal observation is appended as a **reconciliation receipt**, never used to overwrite UNKNOWN.
* The receipt store distinguishes the one execution receipt from later reconciliation receipts and returns the current tail.

That matches E02’s existing rule: an execution receipt cannot follow an existing UNKNOWN execution receipt, but a reconciliation receipt can resolve UNKNOWN; receipt-to-Attempt, chronology, and external-operation identity are checked transactionally.  

## Receipt-store requirements

`find_for_attempt()` and create-or-existing persistence must guarantee:

```text
one current Attempt identity
at most one EXECUTION receipt for that Attempt
zero or more append-only RECONCILIATION receipts
deterministic tail selection
no overwrite
exact Intent, Attempt, idempotency-key, and timestamp binding
conflict on same ID with different canonical content
```

A crash after receipt persistence but before reservation binding is then repaired by locating and adopting the receipt. No new effect may occur.

## Guarantee boundary

With those corrections, the T02 handler establishes:

> For one semantic request and idempotency reservation, a correct durable linearizable lifecycle port grants at most one call to `executor.execute()`.

It does **not** by itself establish external semantic exactly-once behavior. A provider may still duplicate internally, lose a response after committing, or require provider-side idempotency/read-back. In that case the durable Attempt correctly fences redispatch and leaves the operation in reconciliation rather than claiming failure.

The repair also does not establish a live Python-to-E02 binding or make T02 complete. T02 may define and consume the stricter injected port under the stated HumanDecision, but it must not implement a second canonical lifecycle store: canonical lifecycle state remains revisioned and receipt-bound under the Kernel authority. 
