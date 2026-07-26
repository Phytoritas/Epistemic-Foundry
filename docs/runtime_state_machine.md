# Runtime State Machine

## 1. Run states

```text
PLANNED
  → VALIDATED
  → QUEUED
  → RUNNING
  → SUCCEEDED | PARTIAL | FAILED | BLOCKED | CANCELLED
```

Additional:
- `SUPERSEDED`: a revised immutable RunSpec replaces planned work
- `RECONCILING`: receipts and canonical state disagree
- `REPLAYING`: strict/semantic replay in progress

Forbidden:
- FAILED → SUCCEEDED by field update
- SUCCEEDED → RUNNING
- BLOCKED → RUNNING without a resume event and prerequisite record

## 2. Node attempt states

```text
PENDING
→ LEASED
→ RUNNING
→ SUCCEEDED
  | FAILED_RETRYABLE
  | FAILED_FINAL
  | BLOCKED
  | SPEC_GAP
  | CANCELLED
```

A retry creates attempt N+1. It never mutates the evidence of attempt N.

## 3. Readiness

A node is READY when:
- all required predecessors have acceptable terminal receipts
- its input artifact hashes resolve
- capability policy permits it
- approval policy permits it
- write resources are leaseable
- budget/time remains
- no blocking gate applies

`mark_partial` predecessor behavior must be explicitly allowed by the downstream contract.

## 4. Lease and fencing

Lease:
- resource/node
- owner
- issued at
- expires at
- monotonically increasing fencing token

A stale worker cannot commit after a newer token is issued. Commit checks token in the same transaction as result/event persistence.

## 5. Heartbeat

Workers heartbeat only while actively owning a lease. Expiry makes the attempt orphaned; scheduler reconciles before retrying.

## 6. Retry taxonomy

Retryable:
- provider timeout
- transient rate limit
- temporary parser/service unavailability
- network interruption before receipt

Not retryable:
- schema invalid
- deterministic test failure
- unauthorized capability
- scientific gate failure
- malformed source
- SPEC_GAP
- budget exhausted without approval

Backoff and maximum attempts are NodeContract fields.

## 7. Idempotency and effects

Sequence:
```text
ActionIntent
→ policy/approval
→ effect execution with idempotency key
→ EffectReceipt
→ reconciliation
→ canonical event
```

If process crashes:
- intent without receipt: query external state or safely retry with same key
- receipt without event: verify receipt then append event
- external effect unknown: enter RECONCILING, never assume failure/success

## 8. Fan-out completeness

At dispatch:
- persist expected node IDs
- create pending attempts
- track each terminal state

At fan-in:
- compare expected IDs with terminal receipts
- failed/skipped/missing are explicit inputs
- synthesis cannot mark complete if policy requires all
- partial policy records missing nodes in ResultEnvelope

## 9. Checkpoints

Checkpoint requires:
- all nodes in layer terminal
- gates evaluated
- artifacts hashed
- state replay agrees
- pending effects reconciled
- approval complete
- checkpoint manifest committed

Resume reads checkpoint, not a narrative summary.

## 10. Cancellation

Cancellation:
- stops new dispatch
- requests cooperative worker stop
- does not delete artifacts/events
- waits/reconciles external effects
- records incomplete expected set
- preserves resumability unless explicitly terminal

## 11. Replay

### Strict replay

Pin:
- RunSpec
- corpus snapshot
- ontology/ranking/prompt/workflow versions
- model snapshot if available
- deterministic seeds
- artifacts

Compare:
- event sequence
- gate decisions
- artifact hashes
- passport fields

### Semantic replay

When exact model/provider cannot be reproduced:
- preserve canonical inputs
- rerun current approved adapter
- compare structured fields
- report drift by role/gate/verdict
- never call exact reproduction

## 12. Reducer invariants

- event sequence strictly monotonic per run
- same event log → same materialized state
- terminal result has output or typed failure
- successful effect has receipt
- promoted passport has passed gates and attestation
- missing counter/null completion blocks promotion
