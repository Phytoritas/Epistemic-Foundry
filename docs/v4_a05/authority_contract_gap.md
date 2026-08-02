# A05 evolution authority contract gap

## Status

`SPEC_GAP`

A05 cannot satisfy its non-waivable evolution-authority and scientific-
promotion criteria without changes to canonical schemas and workflow files
outside its declared write scope. This record fails closed. It does not claim
that the Evolution Chamber, verifier firewall, Evidence Parliament, or
promotion pipeline is implemented or qualified.

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
