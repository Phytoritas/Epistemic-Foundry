# O01 primary-session separate contract review

Status: `SPEC_GAP (O01-SG001)`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Assurance limitation: this was a procedurally separate primary-session review,
not actor-independent certification. The active execution contract forbids Fleet
and subagents, so the manifest's independent-review gate has not been waived or
misrepresented as independently satisfied.

## Verdict

I04, K04, and M04 are evidence-sealed `PASS`, so O01 is dependency-ready. The
authority chain nevertheless lacks the product semantics needed to implement a
class-aware `QueryPlan` or objectively reconcile `SearchLaneReceipt` artifacts.
The correct result is fail-closed `SPEC_GAP`, before product implementation.

## Blocking findings

1. The manifest requires mandatory lanes to be class-aware, but no `E0`–`E5`
   lane matrix exists. Neither `QueryPlan` nor the retrieval workflow binds lane
   selection to an immutable `EpistemicWorkClassification` revision or hash.
2. Lane vocabulary is inconsistent. The receipt schema uses
   `counterevidence` and `external_novelty`; policy/workflow use `counter` and
   `novelty`; the completeness example also uses `support`, which is not a
   receipt lane. No alias, migration, or role-to-lane mapping has authority.
3. `QueryPlan.required_lanes` and all completeness-certificate lane arrays are
   unconstrained strings. An implementation cannot close those fields without
   first deciding the vocabulary and compatibility policy outside O01's scope.
4. The workflow says all eleven lanes reconcile, while the manifest says lanes
   are class-aware. No typed applicability decision, waiver artifact, authority,
   non-waivable minimum, or evidence rule explains when a lane is selected.
5. `SearchLaneReceipt` requires executed-query fields even for `UNSEARCHED`.
   There is no truthful representation for intentionally unselected,
   inapplicable, or waived lanes, nor a decision on whether they require a
   receipt at all.
6. `provider_failure`, `policy_blocked`, budget/time exhaustion, and manual stop
   lack an authoritative mapping to lane states, completeness states, or run
   terminal states. This prevents deterministic reconciliation and ceiling
   calculation.
7. `query_plan_test` and `receipt_completeness_test` are named only as checks;
   no objective fixtures or thresholds resolve the conflicts above. Allowing
   O01 to invent them would let the package author its own acceptance oracle.

## Classification

This is not `FAIL`: no product implementation was attempted against an invented
oracle. It is not `BLOCKED`: no tool, credential, licensed source, backend, or
host capability is unavailable. The O01 stop condition explicitly requires
`SPEC_GAP` when a shared contract, authority boundary, or threshold is
ambiguous.

## Required product decision

A product-owner HumanDecision must freeze the exact class-to-lane matrix,
typed applicability and waiver authority, one lane vocabulary and compatibility
mapping, receipt semantics for every selected/unselected/failure state,
classification revision/hash binding, completeness and run-failure mapping,
and exact resolving implementation/test/schema/workflow/config/example scopes
with objective fixtures and thresholds.

O01-0001 must remain immutable `SPEC_GAP` history. Do not weaken schemas,
silently alias conflicting lane names, fabricate `UNSEARCHED` query receipts,
or begin O02/O03 while O01 remains unresolved.
