# Epistemic state model

## Why a scalar score is insufficient

A single confidence number collapses incompatible questions: whether a source says the claim, whether studies are independent, whether the method measures the construct, whether causation is identified, and whether the claim is novel. Epistemic Foundry stores a state vector.

## Required dimensions

```text
grounding
scope_match
directness
method_validity
design_strength
statistical_precision
independence
replication
counterevidence_pressure
coverage_completeness
causal_identifiability
novelty_search_completeness
decision_stability
testability
```

Missing dimensions remain null or unknown. They are not imputed into apparent certainty.

## Categorical statuses

### Epistemic
`ENTAILED`, `SUPPORTED`, `MIXED`, `CONTRADICTED`, `UNDERDETERMINED`, `UNTESTABLE`.

### Causal
`IDENTIFIED`, `ASSUMPTION_DEPENDENT`, `NOT_IDENTIFIED`, `NOT_APPLICABLE`.

### Novelty
`PRIOR_ART_FOUND`, `NO_DIRECT_PRIOR_ART_IN_SEARCH_SCOPE`, `SEARCH_INCOMPLETE`, `NOT_ASSESSED`.

### Promotion
`INBOX`, `EVIDENCE_READY`, `COUNCIL_REVIEWED`, `CONDITIONALLY_PROMOTED`, `PROMOTED`, `REJECTED`, `STALE`, `SUPERSEDED`.

### Validation
`TARGET_NOT_CONFIGURED`, `NOT_REPRESENTABLE`, `NOT_IDENTIFIABLE`, `PLAN_READY`, `EXECUTED`, `FALSIFIED`, `TARGET_COMPATIBLE`, `INCONCLUSIVE`.

## Language policy

The Passport generator maps states to admissible language. Examples:

- Allowed: “Supported in the searched corpus under the recorded scope.”
- Allowed: “No direct prior art was found in the recorded databases through the recorded date.”
- Disallowed: “Proved true.”
- Disallowed: “No such study exists.”
- Disallowed: “Causal” when causal status is `NOT_IDENTIFIED`.

## Stability

Confidence is reported with a DecisionStabilityReport. A high evidence score with a verdict that flips when one dependency cluster is removed is fragile and must be described as such.
