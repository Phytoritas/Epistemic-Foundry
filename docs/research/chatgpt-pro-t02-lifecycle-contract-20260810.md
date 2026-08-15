# SPEC_GAP

**Gap:** `T02-E02-DURABLE-MUTATION-LIFECYCLE-AND-EFFECT-AUTHORITY-BINDING`

The attached authority does **not** define one unique provider-neutral T02→E02 integration contract. E02 clearly owns durable `ActionIntent → Attempt → EffectReceipt` state, while T02 owns the mutating MCP surface, but the sources do not bind T02’s request context, risk vocabulary, external executor, identifiers, timestamps, or replay behavior to E02’s lifecycle through one authoritative port. The master authority requires unresolved shared semantics to return `SPEC_GAP`; it also reserves canonical state and replay to the Foundry Kernel and requires side effects to resolve through artifact/effect receipts and event-sourced lifecycle state.   

The manifest reinforces the ownership split:

* E02 owns `packages/foundry-kernel/src/effects/**` and must ensure that unknown effects reconcile before retry. 
* T02 owns `packages/plugin-host/src/mcp/write/**` and promises “no mutation without lease” and “effects reconcile,” but declares no T02→E02 lifecycle binding. 
* The T02 port module itself states that none of its ports reaches a live store and that kernel binding belongs to a later work package. 

## 1. The verified crash defect is real

The current sequence is:

```text
reserve idempotency key
→ persist local intent
→ execute or preview
→ persist local receipt
→ bind intent_id + receipt_id to reservation
```

The reservation port has only:

```text
reserve(key, fingerprint)
bind(key, intent_id, receipt_id)
```

and its durable projection has no Attempt identity or started state.  

The handler performs the external effect before the final `bind`.   Therefore all of these crashes leave the reservation with neither stored intent nor receipt:

```text
after intent persistence
after effect dispatch
after effect completion
after receipt persistence
before final bind
```

On replay, `stored_intent_id is None` causes `_replay()` to return `None`, after which the handler continues into another lifecycle. The code comment that “no persisted intent means the effect could not have started” is false under its own ordering. 

That permits duplicate external execution after the critical crash:

```text
effect committed externally
→ process crashes before final bind
→ replay sees reservation as unstarted
→ effect dispatched again
```

## 2. E02 already defines the needed safety distinction—but not the T02 binding

E02’s current coordinator has the correct internal distinction:

```text
no durable Attempt
→ NOT_STARTED
→ retry_permitted = true

durable Attempt + no receipt
or durable Attempt + UNKNOWN receipt
→ RECONCILING
→ retry_permitted = false

terminal receipt
→ resolved outcome
```



It also implements three important durable boundaries:

1. `registerIntent()` atomically creates the idempotency index, canonical ActionIntent, operation journal, and publication checkpoint. 
2. `beginAttempt()` atomically creates and journals a durable Attempt before returning `execute_permitted: true`; it refuses another attempt while a prior effect remains unresolved. 
3. `recordReceipt()` requires a durable current Attempt and atomically binds the receipt to it; execution and reconciliation receipts are distinct modes.  

But E02’s public source does not determine how T02 obtains all canonical inputs or how its Python/host-layer handler reaches this coordinator. Attempt, idempotency index, journal, and publication checkpoint are explicitly private kernel projections rather than public schemas. 

Thus E02 supplies a safe lifecycle engine, not a completed T02→E02 integration contract.

## 3. Missing canonical field bindings

### ActionIntent

T02’s common mutation input carries only:

```text
workspace_id
dry_run
expected_revision
idempotency_key
approval_record_ids
```



Canonical `ActionIntent` additionally requires:

```text
intent_id
run_id
node_id
action_type
target_ref
arguments_artifact_id
arguments_hash
required_capabilities
risk_class
created_at
intent_hash
```



The unresolved bindings are:

| Canonical field         | Current candidate source                                  | Missing authority decision                                                         |
| ----------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `intent_id`             | No canonical source                                       | Caller-supplied, deterministic E02 derivation, or trusted allocator                |
| `run_id`                | Not in common mutation input                              | MCP request, workflow run, session, or separately required invocation context      |
| `node_id`               | Not in common mutation input                              | MCP tool name, workflow node ID, or invocation ID                                  |
| `action_type`           | T02 `handler_operation`                                   | Whether this catalog field is the canonical ActionIntent action                    |
| `target_ref`            | Tool-specific input                                       | Exact projection and normalization rule                                            |
| `arguments_artifact_id` | No artifact-creation port in the shown T02 lifecycle      | Which owner persists canonical argument bytes before intent registration           |
| `arguments_hash`        | Current handler hashes an in-memory mapping               | Whether it must equal the hash of the artifact named by `arguments_artifact_id`    |
| `required_capabilities` | Policy output, while catalog also declares one capability | Exact set: catalog capability, policy set, intersection, or union                  |
| `approval_record_ids`   | Caller IDs are verified and projected                     | Whether the canonical field carries declared IDs or only successfully verified IDs |
| `risk_class`            | Catalog risk or policy risk                               | Mapping is unresolved                                                              |
| `created_at`            | Handler’s `generated_at` is a possible value              | Trusted clock owner and chronology                                                 |
| `intent_hash`           | E02 can seal it                                           | T02 must not self-declare a competing hash algorithm                               |

The current local intent mapping is not a canonical ActionIntent: it omits several required fields and adds `candidate_id`, which canonical `additionalProperties: false` rejects. The handler also passes the catalog’s `risk_class` directly. 

### Risk-class mismatch

T02’s catalog uses:

```text
medium
high
critical
```

 

Canonical ActionIntent uses:

```text
read_only
bounded_compute
controlled_effect
high_risk
```



At least three materially different mappings remain possible:

1. `medium → controlled_effect`, `high|critical → high_risk`;
2. every T02 mutating operation → `controlled_effect`, with catalog severity retained separately;
3. canonical ActionIntent risk comes from `PolicyDecision.risk_class`, while catalog risk remains only operational review severity.

Nothing in the attached higher authority selects one.

### Attempt

The current T02 lifecycle has no source for:

```text
attempt_id
started_at
```

or an operation that durably marks the Attempt before calling the executor.

E02 derives:

```text
attempt_number
intent_id
intent_hash
run_id
idempotency_key
attempt_hash
```

from the registered intent and durable journal, but requires the caller to supply `attempt_id`, `intent_id`, and `started_at`. 

The authority must therefore decide:

* who allocates `attempt_id`;
* which clock supplies `started_at`;
* whether dispatch is permitted after durable state commit alone or only after ledger-event publication confirmation;
* how T02 receives and obeys `execute_permitted`.

### EffectReceipt

Canonical EffectReceipt requires `run_id`, `started_at`, `finished_at`, and `receipt_hash`, among other fields. 

The current local receipt mapping omits those fields and adds `new_revision`, which the canonical schema does not allow. 

The local reconciliation path additionally writes `reconciles_receipt_id` and `new_revision` into its receipt-shaped mapping, while omitting canonical run/timestamp/hash fields. It is therefore a local reconciliation record, not a canonical EffectReceipt. 

The missing decisions include:

* receipt ID allocator;
* exact `started_at` binding to the durable Attempt;
* trusted `finished_at` source;
* destination for `new_revision`;
* whether reconciliation lineage is a private E02 journal relation or a new public field;
* artifact persistence and validation for result/error IDs;
* who invokes E02’s canonical receipt sealer.

## 4. Smallest unresolved human decision

The smallest sufficient decision is:

> **Select one owner and one provider-neutral integration model by which every T02 mutation is registered, started, inspected, receipted, and reconciled through E02’s durable lifecycle before T02 may report or retry an external effect; freeze the complete field-source and risk projection; and assign exact implementation and public-API paths.**

It must settle five coupled matters:

1. **Lifecycle authority:** E02 is either the sole durable lifecycle service or T02 is explicitly granted another authority. The latter would conflict with Kernel authority unless the master contract is amended.
2. **Field-source projection:** every ActionIntent, Attempt, and EffectReceipt field listed above.
3. **Risk projection:** one exact rule from T02 catalog/policy data to canonical ActionIntent risk.
4. **External-operation identity:** how an attempted effect can be found after a crash.
5. **Composition owner:** exact public package/API or transport boundary between `packages/plugin-host/src/mcp/write/**` and `packages/foundry-kernel/src/effects/**`.

A blanket “use E02” approval is insufficient because it does not answer the field, risk, ID, time, and external-effect questions.

## 5. Mutually exclusive viable integration choices

### Choice A — synchronous split authority

```text
T02:
  policy / approval / lease checks
  canonical request projection
  external adapter invocation

E02:
  registerIntent
  beginAttempt
  recordReceipt / reconcile / inspect
  durable idempotency and replay state
```

Mandatory order:

```text
seal canonical ActionIntent
→ E02 registerIntent
→ E02 inspect/beginAttempt
→ execute only when execute_permitted=true
→ seal canonical EffectReceipt
→ E02 recordReceipt
```

This is the smallest conceptual change, but it requires an authoritative T02-to-E02 public port and complete field mapping.

### Choice B — kernel-owned end-to-end effect command

T02 passes a canonical mutation command to an E02-owned service. The kernel owns lifecycle coordination and invokes a registered external executor port itself.

This minimizes the risk that T02 ignores `execute_permitted`, but requires E02 to own or compose executor dispatch, cancellation, and adapter registration.

### Choice C — durable outbox/worker model

T02 registers the canonical intent and returns an accepted/pending handle. A kernel worker later begins the Attempt, executes the effect, and records the receipt.

This gives the cleanest crash recovery boundary but changes the current synchronous MCP response model and requires worker ownership, claim/lease semantics, and polling or event delivery.

All three satisfy the higher-level requirement that effects be receipt-bound. None is uniquely selected by the attached authority.

## 6. External exactly-once remains a separate decision

A durable Attempt prevents **blind redispatch**. It does not prove that an external service executed the operation exactly once.

After:

```text
durable Attempt
→ request reaches provider
→ provider commits
→ local process crashes before response
```

E02 can correctly say:

```text
RECONCILING
retry_permitted = false
```

but cannot infer the provider outcome.

One of these external contracts must be selected per executor:

* the provider accepts and durably honors the same idempotency key;
* an external operation ID is reserved before dispatch and can be queried after a crash;
* the provider supports authoritative read-back/reconciliation by target revision;
* unknown effects are never automatically retried and require operator reconciliation.

The current synthetic `UNOBSERVED_OPERATION_ID` does not identify the actual external operation and therefore cannot itself establish exactly-once or successful reconciliation. T02’s own contract correctly says an unproven failure must remain `UNKNOWN`, but the missing lookup authority remains. 

The three guarantees must remain distinct:

```text
self-hash integrity
  = these bytes rederive their published hash

durable lifecycle authority
  = the kernel durably knows whether an Attempt started and whether it resolved

external exactly-once
  = the external system commits the semantic operation at most once
```

Neither of the first two implies the third.

## 7. Why `bind_intent` followed later by `bind_receipt` is insufficient

Adding a separate `bind_intent` before execution would prevent the exact “no intent means not started” mistake, but it would not provide truthful E02 lifecycle semantics:

1. crash after intent bind but before effect dispatch would be indistinguishable from crash after dispatch;
2. intent persistence and reservation binding would remain separate-store operations unless one owner made them atomic;
3. no durable Attempt would distinguish `NOT_STARTED` from `RECONCILING`;
4. crash after receipt persistence but before receipt binding could hide an existing terminal receipt;
5. the local intent and receipt shapes would still not satisfy canonical schemas;
6. replay could not prove whether the observed receipt belongs to the current Attempt.

E02 already refuses a receipt that does not resolve a durable Attempt and prevents another execution receipt while the current effect is unresolved.  A two-bind patch would imitate only part of that state machine and must not be accepted as equivalent authority.

## 8. Canonical owner paths that must record the decision

The decision must be bound in this order:

1. **`MASTER_SPEC.md`**
   Freeze the T02→E02 effect-authority relationship if it is intended to be a product-wide rule.

2. **`manifests/development_manifest.yaml`**
   Assign:

   * the integration/composition owner;
   * any direct dependency required between T02 and E02;
   * the exact public bridge path;
   * exact ownership for the T02 catalog/input contracts if they must change.

3. **E02 owner**

   ```text
   packages/foundry-kernel/src/effects/**
   ```

   Own:

   * canonical lifecycle state;
   * idempotency index;
   * durable Attempt;
   * receipt binding;
   * replay and reconciliation state.

4. **T02 owner**

   ```text
   packages/plugin-host/src/mcp/write/**
   ```

   Own:

   * MCP mutation projection;
   * invocation of the approved E02 public port;
   * refusal before external execution when E02 does not grant a fresh Attempt;
   * output projection without duplicating kernel state.

5. **T02 contract surfaces**

   ```text
   contracts/mcp/t02/tool-catalog.yaml
   contracts/mcp/t02/schemas/common-mutation-input.schema.json
   contracts/mcp/t02/schemas/tools/**
   ```

   These require an exact manifest owner before any change. The current T02 manifest entry lists only `packages/plugin-host/src/mcp/write/**`. 

6. **Canonical public schemas**

   ```text
   schemas/action-intent.schema.json
   schemas/effect-receipt.schema.json
   ```

   No schema change is inherently required if the existing fields can be sourced. If the chosen design adds public fields, the canonical schema authority must own that correction; T02 or E02 cannot append fields locally.

7. **Attached Python integration modules**
   Their exact repository paths must either be explicitly assigned as the T02 adapter implementation or removed from the production authority path. A standalone local copy of E02’s state machine is not an acceptable substitute for the kernel service.

## 9. Blocked packages

`T03` itself is **not dependency-blocked by T02**: its manifest dependency is only T01. It may continue implementing stable CLI parsing, JSON, and error projection, but mutating commands must remain unavailable or fail closed rather than claim a reachable lifecycle. 

The blocked chain begins at:

```text
T02
→ T04
→ T05
→ T06
```

T04 directly depends on both T02 and T03. T05 depends on T04, and T06 depends on T05.  

`U01` also directly depends on T04, so its full handler/server integration branch and downstream packages cannot claim dependency-complete runtime reachability while this gap remains. 

The correct present state is therefore:

```yaml
verdict: SPEC_GAP
gap_id: T02-E02-DURABLE-MUTATION-LIFECYCLE-AND-EFFECT-AUTHORITY-BINDING

current_t02_reservation_flow:
  duplicate_effect_safe: false
  canonical_action_intent: false
  durable_attempt_present: false
  canonical_effect_receipt: false
  external_exactly_once: not_established

e02_internal_lifecycle:
  durable_intent: implemented_in_source
  durable_attempt: implemented_in_source
  unresolved_effect_blocks_retry: implemented_in_source
  t02_binding: not_defined

two_stage_bind_patch:
  sufficient: false

T03:
  package_dependency_blocked: false
  mutating_runtime_reachability: unavailable

T04_and_descendants:
  dependency_blocked: true

product_complete: false
```


*Generated 1 image(s). Saved to: C:\Users\yhmoo\.oracle\sessions\pro-f9ebd7-eec030\artifacts\file_00000000f92c81f8bc242b239e387e0a.png*
