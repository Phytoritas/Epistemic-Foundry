# RECOMMENDED — A05 orchestration with an E05 Kernel adapter

The new evidence does **not** require reducing A05 to a charter-only package. The cycle-free design is dependency inversion:

* **A05 owns executable promotion orchestration and a provider-neutral port.**
* **E05 owns the concrete E02/E03/E04/Kernel adapter and production composition root.**
* E02, E03, the Foundry Kernel, and the Noetic Ledger retain effect, lease, fencing, transaction, and replay authority.

This preserves A05’s declared ownership of the 23-node, G00–G14 promotion chain without making A05 depend on later authority implementations. It also uses E05’s existing position as the downstream candidate action/effect and reconciliation package instead of creating a duplicate integration package.   

## Recommended DAG

Here `X -> Y` means “X depends on Y.”

```text
A05 -> A04
A06 -> A05

C01 -> A04,A05        # must first be ratified in MASTER_SPEC
C02 -> C01
C03 -> C01,C02
C04 -> C02,C03

E01 -> C04,D04
E02 -> E01
E03 -> E01
E04 -> E02,E03

E05 -> A05,A06,C05,E02,E03,E04
```

The exact dependency changes are:

1. **Do not add** `A05 -> E03` or `A05 -> E04`.
2. Add direct manifest dependencies `E05 -> A05,E02,E03`; retain its existing `A06,E04,C05` dependencies. The direct edges are warranted because the adapter will consume A05’s port and invoke E02/E03 contracts directly rather than relying on hidden transitive access through E04.
3. Amend `MASTER_SPEC.md` so C01 depends on `A04,A05`.

The third item is presently a **SPEC_GAP**. `MASTER_SPEC.md` says C01 depends only on A04, while the lower manifest adds A05. Under the declared authority order, the manifest cannot establish that edge by itself. This recommendation resolves the conflict by ratifying `C01 -> A05` in the higher authority; it does not remove the existing manifest edge. No canonical schema or transport implementation is authorized until that amendment is frozen.   

## Ownership boundary

### A05: provider-neutral orchestration

A05 should own:

* `models.py`: immutable promotion-operation request and outcome models;
* `cas.py`: the `PromotionCommitPort` protocol;
* `promotion.py`: lease acquisition and atomic-commit orchestration;
* `reconciliation.py`: unknown-outcome and receipt reconciliation.

The port should expose only three closed operations:

```text
acquire_commit_lease(request) -> lease reference
commit_promotion(request) -> COMMITTED | EXISTING | OUTCOME_UNKNOWN
reconcile_promotion(request identity) -> resolved outcome | still unknown
```

A05 determines sequencing, required gate evidence, expected revisions, request identity, idempotency, and when G14 is eligible. It does **not** decide that a supplied lease is authoritative, implement fencing, persist the transaction, fabricate receipts, or inspect an in-memory substitute for Kernel state.

The workflow should remain A05-owned and reference only A05-owned entrypoints:

```text
epistemic_foundry.governance.evolution_authority.promotion:
  acquire_promotion_commit_lease

epistemic_foundry.governance.evolution_authority.promotion:
  commit_promotion_atomically

epistemic_foundry.governance.evolution_authority.reconciliation:
  reconcile_commit_receipts
```

This replaces the current unowned `nodes.py` targets without introducing an implicit `A05 -> E05` dependency. The A05 entrypoints receive their port from a trusted runtime composition context and fail closed when no canonical E05 binding is present.

### E05: concrete adapter and composition

E05 should own the paired adapter:

```text
src/epistemic_foundry/effects/v4_e05/promotion_commit_adapter.py
packages/foundry-kernel/src/integrations/evolution-promotion/**
```

Its manifest scope and exit criteria should be expanded accordingly. E05 supplies the trusted port implementation and the production executor binding for the A05 entrypoints.

The Kernel-side handler must accept a closed promotion command and invoke `commitWithLease()` internally. It must construct the synchronous transaction callback inside the Kernel process; neither Python nor the transport may submit a callback or executable closure. That callback atomically writes the PromotionDecision, Passport revision, and other approved transaction records while `commitWithLease()` retains lease revalidation, fencing, immutable lease-use, and outbox authority.

E05 may translate and compose those authorities, but must not implement a second lease store, fencing head, CAS engine, effect ledger, or replay rule. E02 already owns the `ActionIntent -> Attempt -> effect -> EffectReceipt` lifecycle, E03 owns lease/fencing policy, and E04 owns strict and semantic replay. 

## Correct lifecycle

The commit path must be:

```text
sealed ActionIntent
→ registered/started Attempt
→ short-lived promotion:commit lease
→ Kernel commitWithLease transaction
→ COMMITTED or EXISTING result
→ EffectReceipt recording/reconciliation
→ artifact/event/lease-use reconciliation
→ G14
```

A completed EffectReceipt is therefore **not** a pre-CAS requirement. It records the already attempted effect. A transport interruption after dispatch yields `OUTCOME_UNKNOWN`; it cannot become success, no second commit may be attempted blindly, and the reconciliation node resolves the original operation by its bound identity.

## Smallest canonical transport contract

Add one C01-owned strict schema:

```text
schemas/promotion-commit-operation.schema.json
```

It should contain two reusable definitions.

### Invocation binding

The invocation definition must bind:

```text
operation_id
operation = commit_promotion
ActionIntent reference and hash
Attempt reference
CapabilityLease reference and hash
principal_id
capability = promotion:commit
workspace and target scopes
fencing_token
sealed promotion-pack reference and hash
expected PromotionDecision/Passport revisions
idempotency key
trusted port-binding ID and hash
request_hash
```

The full ActionIntent and CapabilityLease bodies should not be copied into this object; canonical ID-and-hash references avoid duplicate wire contracts.

### Kernel result binding

The result definition must bind:

```text
disposition = COMMITTED | EXISTING
operation_id
request_hash
port-binding ID and hash
lease reference and fencing token
immutable lease-use reference and hash
PromotionDecision reference and hash
Passport-revision reference and hash
ledger/outbox references and hashes
observed pre-revisions
committed post-revisions
result_hash
```

`OUTCOME_UNKNOWN` is an adapter/attempt state, not a forged Kernel disposition. It carries the original operation and request identity into reconciliation but contains no invented lease-use or commit result.

Then version:

* `node-invocation.schema.json` to carry an `authority_operation` reference to the invocation definition;
* `result-envelope.schema.json` to carry an `authority_operation_result` reference to the result definition.

The acquire node may continue emitting the existing canonical CapabilityLease as an output artifact. The commit node emits the Kernel operation result; the reconciliation node resolves the EffectReceipt and final receipt set. The workflow keeps all 23 nodes and the same G00–G14 ordering.

Because EF4-I22 prohibits duplicated transport literals, C01 must own the schema, C02 must generate the Python/TypeScript projections, and C03/C04 must version and verify compatibility. Adding the schema also requires advancing the exact canonical schema/example and packaged-resource counts wherever those counts are frozen.  

The current empty Foundry Kernel export map and absence of a Python transport do not change this ownership decision. They mean only that the E05 adapter and production consumer do not yet exist. `commitWithLease()` should remain internal; E05 should expose only the closed promotion operation through the trusted transport, not the raw callback-bearing primitive. Until that binding exists, the A05 entrypoints must fail closed rather than fall back to the in-memory committer. 
