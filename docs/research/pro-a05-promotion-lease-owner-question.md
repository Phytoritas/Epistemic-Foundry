We are continuing the Epistemic Foundry v4 implementation against MASTER_SPEC.md in the same fresh ChatGPT conversation.

Adjudicate one shared-contract decision only. Do not approve A05 as a whole and do not invent implementation evidence.

Verified current state:

- MASTER_SPEC and workflows/evolution_promotion.workflow.yaml require a 23-node, receipt-bound promotion chain with one short-lived `promotion:commit` lease and an atomic G14 compare-and-swap.
- The workflow currently targets `epistemic_foundry.governance.evolution_authority.nodes:acquire_promotion_commit_lease` and `:commit_promotion_atomically`.
- Those Python functions validate a supplied lease shape/action type but do not bind a persisted Kernel lease, expiry/revocation, current fencing token, principal/scope, or Kernel `commitWithLease()` transaction.
- The commit path does not accept the lease and uses an in-memory `PromotionCommitter` that cannot atomically persist PromotionDecision, Passport revision, lease-use, and receipts.
- A05's manifest depends only on A04. Its declared write scope includes `evolution_authority/gate_runner.py`, `promotion.py`, `cas.py`, and `reconciliation.py`, but not the current `nodes.py`, the shared `governance/promotion.py`, or Foundry Kernel capability authority. The first three integration modules are absent and the canonical workflow does not target them.
- E03/E04 already own capability leases, fencing, approval policy, and strict replay.

The unresolved authority choice is:

1. A05 owns the runtime integration: add E03/E04 dependencies and exact owned adapter/executor paths, retarget the workflow to an A05-owned provider-neutral composition that invokes the Kernel lease-protected transaction; or
2. Keep A05 charter-only and create a separately named integration package that depends on A05+E04 and owns Python-to-Kernel lease/CAS/reconciliation plus workflow binding.

Question: Which option is more faithful to the existing higher authority and minimizes long-term contract duplication? If neither is safely selected by current authority, say SPEC_GAP and name the single user/product decision required. State the exact manifest/workflow/schema surfaces that must change before implementation, and the minimum provider-neutral invocation/result contract. Keep the answer concise and decision-grade.
