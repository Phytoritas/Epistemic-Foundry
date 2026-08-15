# A05 G14 ordering circularity — authority decision needed

## Context

Epistemic Foundry v4. Authority order is `MASTER_SPEC.md` > `manifests/development_manifest.yaml` > `manifests/acceptance_matrix.yaml` > `manifests/product_invariants.yaml` > applicable `schemas/*.schema.json` and `workflows/*.workflow.yaml` > `manifests/role_registry.yaml` > `AGENTS.md` > work-package-local notes. A lower source may never be used to justify contradicting a higher one, and a missing shared contract must never be invented locally.

A05 owns the evolution authority and promotion charter. It recently gained a provider-neutral promotion-commit port so that the Foundry Kernel (via an E05-owned adapter) performs the lease-protected compare-and-swap, while A05 keeps sequencing, evidence requirements, expected revisions, request identity, and G14 eligibility.

I have found what looks like a genuine ordering circularity and I want your judgement on the smallest correct authority decision, not a code workaround.

## The contradiction

**Higher authority says G14 completes AFTER the commit.**

`docs/v4_a05/evolution_authority_and_promotion_charter.md:214` defines the gate as the commit itself:

> `G14_ATOMIC_PROMOTION_COMMIT` — Use expected-revision compare-and-swap and atomically bind both ActionIntents, the short CapabilityLease, new PromotionDecision and Passport revisions, EventRecord, EffectReceipt, and ArtifactReceipt.

The receipt-bound workflow (charter section 8, `:355-374`) fixes 18 ordered steps ending:

> 14. Compare-and-swap the expected candidate and Passport revisions.
> 15. Record a new immutable `PromotionDecision` and `HypothesisPassport` revision.
> 16. Append the corresponding Noetic Ledger `EventRecord`.
> 17. Record the resolving `EffectReceipt` and `ArtifactReceipt`.
> 18. Complete G14 only after the atomic commit and all resolving receipts reconcile.

The ratified product-owner decision `artifacts/authority_decisions/EF4-A05-C01-B04-SHARED-CONTRACT.md` repeats this as R46 and R60, and R91 states that the *pre-commit* authorization is the short-lived `promotion:commit` CapabilityLease issued after G00–G13 pass — not a G14 decision.

The canonical workflow agrees: `workflows/evolution_promotion.workflow.yaml` runs `reconcile_commit_receipts` after `commit_promotion_atomically`, and its acceptance checks say the G14 GateDecision is emitted there, after EventRecord/EffectReceipt/ArtifactReceipt reconcile.

**But the shared promotion authority requires G14 BEFORE the commit.**

`src/epistemic_foundry/governance/promotion.py` (owned by C03) computes the verdict via `decide_promotion(request)`. Its validator requires:

- `gate_decision_ids` exactly equal to the canonical ordered 15-element set G00..G14 (`:456`), and
- exactly 15 structured `GateDecision` records, one per canonical gate, each schema-valid, self-hash-consistent, with non-empty evidence IDs and reasons (`:367-372`), and
- a resolving `effect_receipt_id` on the request.

The canonical schema `schemas/promotion-decision.schema.json` reinforces this: `gate_decision_ids` is `minItems: 15, maxItems: 15` with `prefixItems` pinning all fifteen gate names including `G14_ATOMIC_PROMOTION_COMMIT`, and both `effect_receipt_id` and `artifact_receipt_ids` are required.

`schemas/gate-decision.schema.json` `status` enum is exactly `["PASS", "FAIL", "BLOCK", "WAIVE"]`. There is no `PENDING`, `NOT_YET_EVALUATED`, or equivalent non-terminal value.

**Consequence.** The commit node must derive its verdict before dispatching the effect (deriving it afterwards would leave the Kernel holding a transaction the gates had already rejected). On an honest run, at that moment neither the G14 GateDecision nor the resolving EffectReceipt exists yet. To satisfy `decide_promotion`, a caller would have to supply a G14 decision asserting `PASS` for a commit that has not happened, plus an EffectReceipt for an effect not yet attempted. Both are exactly what the charter forbids ("never synthesize a receipt"; "absence of an EffectReceipt means success is not proven").

## What I believe, and what I want checked

My reading is that this is a shared-contract SPEC_GAP, not an A05 bug:

- A05 cannot fix it by writing `derive_promotion_decision` differently, because using `decide_promotion` at all drags in the pre-commit G14 + receipt requirement.
- A05 also cannot bypass `decide_promotion`, because then A05 would be inventing an undeclared authorization object beside the canonical `PromotionDecision` — precisely the "never invent a missing shared contract" prohibition.
- Therefore the repair needs C01 (canonical schema shape) and C03 (constructor/validator split in `governance/promotion.py`).

## Questions

1. Do you agree this is a real circularity, or is there a consistent reading of the charter under which a pre-commit `G14 PASS` is legitimate (for example, G14 meaning "the atomic commit is authorized and will be performed under this lease", later confirmed by reconciliation)? If such a reading exists, say exactly which charter text supports it and how the "complete G14 only after ... reconcile" sentence survives.

2. Assuming it is a real gap, which of these is the smallest correct decision, and why? Please pick one and justify against the authority order, not convenience.

   a. **Two typed records.** Introduce a distinct pre-commit authorization record (derived from G00–G13 + granted-level computation) that authorizes the CAS, and keep `PromotionDecision` as the post-commit immutable record that carries the commit, ledger event, receipts, and G14. This adds a canonical schema — but the canonical inventory is frozen at 127/127 and every count change so far required an explicit product-owner decision.

   b. **One record, two lifecycle states.** Keep a single `PromotionDecision` but make its gate/receipt requirements conditional on a lifecycle field, so a pre-commit instance legitimately omits G14 and the resolving receipts, and a post-commit revision requires all fifteen gates and both receipts. This changes `schemas/promotion-decision.schema.json` and its validator without changing the schema count.

   c. **Relax the pre-commit requirement only.** Make `decide_promotion` require exactly G00–G13 and treat G14 plus the resolving receipts as post-commit obligations verified during reconciliation, with `PromotionDecision` still finalized once after reconciliation. This changes C03's validator and possibly the schema's `minItems/prefixItems`.

   d. Something else you consider strictly smaller or safer.

3. Whichever you choose: what exactly must be true so that this does NOT weaken any gate? Specifically, how do we guarantee that (i) a candidate cannot reach CAS without all of G00–G13 genuinely passing, (ii) the final immutable record still proves the commit, the ledger event, and both receipts, and (iii) an interrupted dispatch stays honestly unresolved rather than becoming either a silent success or a silent rollback?

4. Separately and more narrowly: the charter fixes (R47) that every gate emits a GateDecision with `input_hash`, `decision_hash`, `policy_version`, and evidence IDs — but nothing fixes *which* evidence IDs G14 must cite. Today a schema-valid, self-hash-valid, PASSing G14 that cites entirely unrelated evidence would be structurally acceptable at completion. Should G14's `evidence_ids` be required to cover the exact effect receipt, artifact receipt, promotion decision, and ledger event of the transaction it completes? If yes, who owns that constraint — is it a canonical schema constraint (C01), a charter requirement A05 can enforce in code, or a policy-bundle matter?

Please be concrete and decisive. If my framing is wrong somewhere, correct it directly. Ground every claim in the authority order above.
