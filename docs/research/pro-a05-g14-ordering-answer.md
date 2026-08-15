# SPEC_GAP — select option **d: a 14+1 proof split using existing record types**

Your diagnosis is correct. The present schema/runtime contract creates a real causal cycle, and A05 cannot repair it locally. `MASTER_SPEC.md` requires `SPEC_GAP` when shared semantics conflict, while EF4-I13 independently requires receipt-bound completion. 

## 1. A pre-commit G14 PASS is not a valid reading

There is no charter text supporting “G14 PASS means authorization to attempt the commit.”

The charter defines G14 by the **actual CAS and its resulting record set**, not by permission to attempt it. Its fixed sequence places the commit intent and short `promotion:commit` lease before CAS, then places `PromotionDecision`, Passport revision, EventRecord, receipts, and finally G14 after reconciliation.  

The local canonical registry confirms the same interpretation by mapping G14 to `reconcile_commit_receipts` and stating that it completes only after the atomic commit. 

A pre-commit G14 PASS would therefore create one of three unauthorized outcomes:

* it falsely attests that an unperformed commit occurred;
* it must later be mutated, violating GateDecision immutability;
* or a second G14 must be issued, contradicting the one-gate/one-decision sequence.

The absence of `PENDING` from `GateDecision.status` does not justify premature PASS. Before reconciliation, G14 simply has **not executed to completion**; the operation is represented by the attempt/reconciliation lifecycle, not by a synthetic GateDecision.

## 2. Smallest correct authority decision: option d, not a–c

The correct split is:

```text
G00–G13 deterministic eligibility
→ commit ActionIntent
→ short promotion:commit CapabilityLease
→ Kernel CAS and atomic commit set
→ reconciliation
→ G14 completion decision
→ effective promotion
```

### Pre-commit

A pure deterministic derivation validates exactly G00–G13 and computes:

* the decision disposition;
* the grantable level;
* every applicable ceiling;
* unresolved limitations;
* the exact promotion request and expected revisions.

That derivation is **not a new authority artifact**. Its canonical inputs and result are bound through the existing `commit_promotion` ActionIntent. The ActionIntent plus the persisted CapabilityLease remains the sole pre-CAS authorization.

### Commit transaction

The Kernel revalidates the same G00–G13-bound request, lease, fencing token, request hash, idempotency identity, and expected revisions inside `commitWithLease()`.

The transaction then stages and atomically publishes the closed commit set:

```text
PromotionDecision
HypothesisPassport revision
EventRecord
EffectReceipt
ArtifactReceipt set
lease-use / fencing evidence
```

`PromotionDecision.gate_decision_ids` must therefore contain **exactly G00 through G13**. G14 is downstream evidence about that committed decision and cannot be one of its causal inputs.

The existing `effect_receipt_id` and `artifact_receipt_ids` may remain required in the final `PromotionDecision`, but their semantics must be frozen as follows:

> They are transaction-produced references to records staged after the effect outcome is known and resolved before atomic publication. They are not caller-supplied pre-effect evidence and are not inputs to the pre-commit eligibility derivation.

No dangling receipt reference may commit. Nothing in the staged set becomes authoritative independently of the atomic transaction.

### Post-commit

`reconcile_commit_receipts` validates the committed set and emits the one immutable G14 GateDecision. Only the matching G14 PASS makes the new level effective.

Thus:

```text
PromotionDecision present ≠ completed promotion
Passport revision present ≠ completed promotion
matching G14 PASS = completed and effective promotion
```

This preserves the charter’s placement of `PromotionDecision` before G14 and allows G14 to cite that exact immutable decision.

### Why the other options are inferior

**a** adds an unnecessary authorization type beside the already-defined ActionIntent and CapabilityLease, and changes the frozen 127/127 inventory.

**b** creates an authority-looking provisional `PromotionDecision`, overloads one type with two meanings, and risks treating the pre-commit revision as effective.

**c**, as written, finalizes `PromotionDecision` only after reconciliation. That contradicts the charter’s step 15 and makes it impossible for G14 to cite the already-immutable PromotionDecision it is completing.

Option d changes existing contracts but adds no schema. The inventory remains 127 schemas and 127 matching examples, consistent with C01’s current cardinality authority. 

## Required authority surfaces

No A05 implementation should proceed until these shared changes are ratified.

### C01

In `schemas/promotion-decision.schema.json`:

* change `gate_decision_ids` to exactly fourteen ordered entries, G00–G13;
* define those as the decision’s **eligibility-gate dependencies**, not the complete workflow gate census;
* retain receipt fields only with the transaction-produced semantics above;
* version the changed write contract without rewriting historical records.

In `schemas/gate-decision.schema.json`:

* preserve the existing terminal status vocabulary;
* add a G14-specific typed evidence carrier sufficient to identify mandatory evidence roles, IDs, and hashes;
* retain exactly fifteen gates globally.

This is C01 work because C01 owns both canonical schemas and the fail-closed G00–G14, lease, CAS, and receipt surface. 

### C03

In `src/epistemic_foundry/governance/promotion.py`, separate:

```text
derive_promotion_verdict(...)
    G00–G13 only
    no G14
    no pre-existing commit EffectReceipt

construct_or_validate_committed_promotion_decision(...)
    transaction-produced record references
    immutable decision and revision identity

validate_g14_completion(...)
    exact post-commit evidence closure
```

C03 owns that shared runtime projection and compatibility handling. Historical 15-ID PromotionDecisions remain immutable and readable only under their recorded schema/compatibility epoch; they are not silently rewritten to the new meaning. 

### A05 workflow and runtime

The workflow remains exactly 23 nodes and keeps its current ordering. No gate is removed or reordered.

A05 must ensure:

* `commit_promotion_atomically` consumes the G00–G13-bound request and lease;
* it returns the authoritative commit-set identity rather than a fabricated completed G14 result;
* `reconcile_commit_receipts` alone emits G14;
* the effective-level reducer requires a matching G14 PASS.

A05’s manifest already requires exact ordered, receipt-bound G00–G14 behavior and mandates `SPEC_GAP` rather than fabrication when promotion semantics are ambiguous. 

## 3. Conditions that prevent gate weakening

### CAS admission

A candidate may reach CAS only when all of the following hold:

* exactly fourteen GateDecisions exist in canonical G00–G13 order;
* every decision is schema-valid and self-hash-valid;
* each decision binds the same run, candidate revision, requested level, sealed promotion pack, policy version, and applicable input hash;
* no required gate is missing;
* no FAIL or BLOCK is concealed;
* no non-waivable gate is WAIVEd;
* every `NOT_REQUIRED` determination is backed by the exact sealed policy rule;
* the grantable level is the minimum of all applicable ceilings;
* the commit ActionIntent binds that exact gate set, request hash, expected revisions, policy hash, and idempotency identity;
* the Kernel independently revalidates the persisted lease, scope, principal, capability, fencing token, and revision heads before and after its callback.

A caller-supplied summary that merely says “all gates passed” is insufficient.

### Final proof

G14 PASS requires the exact same transaction identity across:

```text
request-promotion ActionIntent
commit-promotion ActionIntent
CapabilityLease
lease-use and fencing record
PromotionDecision
HypothesisPassport revision
EventRecord
EffectReceipt
complete ArtifactReceipt set
expected and committed revisions
canonical request hash
```

The final proof is the G14 GateDecision plus this closed evidence set. This is stronger than making `PromotionDecision` alone carry a premature G14 assertion.

### Interrupted dispatch

When dispatch may have occurred but the outcome is unknown:

* no G14 PASS is emitted;
* the new level is not projected as effective;
* no receipt is synthesized;
* absence of a response is not interpreted as rollback;
* the operation is not blindly repeated;
* the same idempotency key and request hash are used to inspect canonical state, lease-use, outbox, ledger, and receipts;
* a confirmed existing commit is reconciled as the same operation;
* contradictory evidence becomes an integrity failure;
* unresolved evidence remains explicitly unresolved.

The charter already requires unknown CAS outcomes to remain unknown until canonical state, ledger state, and receipts reconcile, and forbids treating absence of an EffectReceipt as proof of success. 

## 4. G14 evidence must be transaction-specific

Yes. A non-empty but unrelated `evidence_ids` array must never support G14 PASS.

At minimum, G14 must cite the exact IDs—and, through typed bindings, the exact content hashes—of:

* both ActionIntents;
* the CapabilityLease and authoritative lease-use/fencing record;
* the PromotionDecision;
* the Passport revision;
* the EventRecord;
* the resolving EffectReceipt;
* the complete operation-owned ArtifactReceipt set.

All must agree on operation identity, canonical request hash, candidate and Passport identities, expected and committed revisions, and fencing token.

Ownership is layered:

* **A05 owns the semantic rule** defining what G14 proves and when it may PASS.
* **C01 owns the canonical structural carrier** for typed G14 evidence roles, IDs, and hashes.
* **A05 reconciliation, using shared C03 validators, owns cross-artifact resolution and same-transaction equality checks.** JSON Schema alone cannot prove that separately stored records describe the same transaction.
* **The PolicyBundle does not own this minimum evidence closure.** Policy may supply `policy_version` and applicability evidence, but it cannot omit, substitute, or waive the G14 transaction records.

Until that decision and the C01/C03 projections are frozen, the current repository remains `SPEC_GAP`; bypassing `decide_promotion`, pre-issuing G14, or fabricating a receipt is not authorized.
