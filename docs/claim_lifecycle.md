# Claim, evidence, and Passport lifecycle

## Append-only rule

No canonical research object is edited in place after release. Corrections create a new revision and a lifecycle event.

## Claim states

```text
DRAFT
CANDIDATE
GROUNDED
REVIEW_REQUIRED
REVIEWED
PROMOTED
REJECTED
STALE
INVALIDATED
SUPERSEDED
```

## Transition requirements

- `CANDIDATE → GROUNDED`: exact SourceSpan resolution and grounding verification.
- `GROUNDED → PROMOTED`: evidence-layer and release-gate PASS.
- `PROMOTED → STALE`: source, schema, policy, ontology, or dependency update affects current validity.
- `STALE → SUPERSEDED`: a new approved revision replaces current use.
- `PROMOTED → INVALIDATED`: retraction, source corruption, or decisive provenance failure.
- `REJECTED`: remains queryable for audit and dedupe.

## Cascade graph

```text
DocumentVersion
→ SourceSpan
→ ClaimCard
→ EvidenceNode
→ EvidencePack
→ CoverageSnapshot
→ Adjudication
→ HypothesisPassport
→ ValidationPlan / ExperimentTicket
```

UpdateImpactReport traverses this graph. The system marks current projections stale before rerunning affected workflows.

## Human decisions

A human may approve, reject, narrow scope, or request more evidence. The underlying machine artifacts remain unchanged. The HumanDecision links to the exact subject revision and may itself be superseded.
