# A05 evolution authority contract gap

## Status

`SPEC_GAP`

A05 cannot satisfy its non-waivable evolution-authority and scientific-
promotion criteria without changes to canonical schemas and workflow files
outside its declared write scope. This record fails closed. It does not claim
that the Evolution Chamber, verifier firewall, Evidence Parliament, or
promotion pipeline is implemented or qualified.

### Later update — runtime ownership resolved, contracts still pending

`docs/v4_a05/promotion_runtime_ownership_decision.md` ratifies who may execute
the commit chain: A05 owns orchestration and a provider-neutral port, E05 owns
the concrete Foundry Kernel adapter. That resolves the ownership half of
`A05-SG002` and removes the dependency cycle that blocked every earlier option.

The schema half of both gaps remains open. `A05-SG001` and the conditional
promotion-validity constraint in `A05-SG002` still require C01 schema work, and
the promotion-commit transport contract is staged unregistered at
`docs/v4_a05/proposed_contracts/` pending a product-owner decision to raise the
frozen 127/127 canonical inventory.

## Authority and scope

The controlling package contract is `manifests/development_manifest.yaml`.
A05 may write only:

- `docs/v4_a05/**`
- `artifacts/work_packages/A05/**`

`MASTER_EXECUTION_PROMPT.md` requires every evolution run to pin thirteen
classes of search, evaluator, validation, statistics, archive, budget, and
authority state. It also requires promotion to be constrained by deterministic
gates, independent Parliament and attestation, replication where required, and
policy, safety, ethics, and human approval gates.

The deterministic probe at
`artifacts/work_packages/A05/authority_contract_probe.py` binds the examined
authority files by SHA-256 and reproduces both gaps below. Its checked output
is `artifacts/work_packages/A05/authority-contract-probe.json`.

## A05-SG001 — incomplete EvolutionRunSpec pin contract

`schemas/evolution-run-spec.schema.json` is closed with
`additionalProperties: false`, but it does not represent most of the mandatory
per-run pins. Of the thirteen higher-authority requirement groups, only the
research objective and operator registry are fully bound. Eleven groups are
partial, missing, or ambiguous.

The absent or unresolved semantics include:

- forbidden authority fields and initial lineage binding;
- semantic-island and migration rules;
- explicit parent-selection and model-routing policies;
- evaluator qualification-report binding;
- public, hidden, OOD, adversarial, and replication stage plans;
- novelty and prior-art boundaries;
- fitness and hard-gate policies;
- adaptive-search statistical policy;
- archive and negative-knowledge retention policy;
- concurrency and a canonical `EvolutionRunSpec`-to-`RunSpec` resolution
  contract.

The referenced base `RunSpec` has no declared resolution rule for these
indirect values, and its `run_type` vocabulary has no `evolve` value. Because
the evolution schema rejects undeclared fields, an implementation cannot add
the missing pins locally without changing shared canonical contracts.

Required authority decision: define the canonical per-run fields or immutable
references, their resolution and hash rules, compatibility/migration behavior,
and the relationship between `EvolutionRunSpec` and `RunSpec`. Assign those
schema and workflow changes to an authorized package before rerunning A05.

## A05-SG002 — unsafe promotion remains schema/workflow valid

`schemas/promotion-decision.schema.json` accepts all three adversarial fixtures
used by the probe:

- `PROMOTE` with `hard_gate_status: FAIL`;
- `PROMOTE` with `hard_gate_status: PARTIAL`;
- `PROMOTE` with empty replication and approval arrays, including when the
  hard-gate label is `PASS`.

The schema has no conditional constraint connecting `decision: PROMOTE` to
passing hard gates or non-empty authority artifacts.

In `workflows/evolution_chamber_cycle.workflow.yaml`, the node
`run_evidence_parliament_promotion` is a provider-nondeterministic LLM node
whose output is the permissive `PromotionDecision`. Its output directly
unlocks `issue_hypothesis_passport_revisions`. The workflow has no separate
Parliament adjudication node, independent-attestation node, human-authority
node, or produced adjudication/attestation/approval artifact, and it does not
reference a post-LLM deterministic promotion gate.

`src/epistemic_foundry/governance/promotion.py` does reject failed gates and
missing evidence. That is useful local behavior, but it does not close the
canonical contract gap: the canonical workflow neither binds that helper as
the promotion executor nor invokes it as a mandatory downstream gate.

Required authority decision: define conditional promotion validity in the
canonical schema and bind the canonical workflow to distinct deterministic
gate, Parliament adjudication, independent attestation, replication-ceiling,
and explicit policy/human-approval artifacts. Specify which authority owns the
final state transition and how every prerequisite resolves to immutable
receipts.

## Package effect

A05 is not integrated. A06 depends on A05 and is therefore not
dependency-ready. No canonical schema or workflow was changed, no gate was
weakened, and no runtime or scientific-promotion claim is made. Resolution
requires a higher-authority scope and contract decision followed by new
negative, adversarial, crash/resume, provenance, and independent-review
evidence.

## A05-SG003 — G14 cannot be evidence for the commit that produces it

The charter defines `G14_ATOMIC_PROMOTION_COMMIT` as the atomic commit itself,
not as prior authorization: it binds both ActionIntents, the short
`CapabilityLease`, the new `PromotionDecision` and Passport revisions, the
`EventRecord`, the `EffectReceipt`, and the `ArtifactReceipt`
(`evolution_authority_and_promotion_charter.md:214`). Step 18 of the
receipt-bound workflow states it plainly: complete G14 only after the atomic
commit and all resolving receipts reconcile (`:374`). The shared-contract
decision repeats this as `R46` and `R60`, and `R91` makes clear that the
*pre*-commit authorization is the short `promotion:commit` lease issued after
G00-G13 pass, not a G14 decision.

The shared promotion authority requires the opposite ordering. Its request
validator demands `gate_decision_ids` equal to the canonical ordered G00-G14
set and exactly fifteen structured `GateDecision` records including G14, plus a
resolving `EffectReceipt` reference, before a verdict can be computed
(`src/epistemic_foundry/governance/promotion.py:367`, `:456`). The commit node
must derive its verdict before dispatching the effect, so on an honest run
neither the G14 decision nor the resolving receipt exists yet.

This cannot be closed inside A05. Continuing to use the shared
`decide_promotion` cannot avoid the pre-commit G14 requirement, and abandoning
it would mean A05 inventing an undeclared authorization object beside the
canonical `PromotionDecision`, which is exactly what the authority order
forbids.

Recommended authority decision, still pending C01/C03 ratification: use a
14+1 proof split without inventing a new authorization record. G00-G13 are the
exact eligibility dependencies bound by
the existing commit `ActionIntent` and short `promotion:commit` lease. The
Kernel transaction records the immutable `PromotionDecision`, Passport
revision, ledger event, and resolving receipts. Only then does reconciliation
emit the one G14 `GateDecision`; the new level is ineffective until that
matching G14 PASS exists.

That requires C01 to version the existing schemas so
`PromotionDecision.gate_decision_ids` means exactly ordered G00-G13 and the
G14 decision has a typed, role-complete transaction-evidence carrier. C03 must
split pre-commit eligibility derivation, committed-decision construction, and
G14 completion validation. Historical records remain immutable under their
recorded compatibility epoch. Until those shared changes are ratified, A05's
commit entrypoints stop with `SPEC_GAP` before any commit-port dispatch.

G14's minimum evidence closure is not a policy option. It must bind both
ActionIntents, the CapabilityLease and authoritative lease-use/fencing record,
the PromotionDecision, Passport revision, EventRecord, EffectReceipt, and the
complete operation-owned ArtifactReceipt set by exact IDs and hashes. A05 owns
that semantic requirement; C01 owns its canonical carrier; A05 reconciliation,
using shared C03 validators, owns the cross-record same-transaction checks.
