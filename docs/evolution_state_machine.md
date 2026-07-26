# EVOLVE State Machine

## States

```text
DRAFT
→ FRAMED
→ EVALUATOR_SEALED
→ POPULATION_READY
→ GENERATING
→ CONTRACT_SCREEN
→ EVALUATING
→ CHALLENGING
→ SELECTING
→ REPLICATING
→ PROMOTION_REVIEW
→ CHECKPOINTED
→ PAUSED | COMPLETED | BLOCKED | FAILED | CANCELLED
```

## Transition evidence

Every transition requires:

- expected state revision;
- RunSpec and evaluator hash;
- required PhaseArtifactSet;
- candidate/effect count reconciliation;
- budget and statistical-ledger state;
- unresolved blocker list;
- policy checks;
- transition receipt.

## Illegal transitions

- generation before evaluator seal;
- holdout execution before candidate freeze;
- promotion before adaptive-search statistics;
- high promotion before required replication;
- evaluator change during run;
- archive mutation without rebalance plan;
- resume with mismatched evaluator/policy/ontology;
- completion with missing worker identities.

## Return edges

A challenge, replication failure, correction or evaluator defect may return a candidate to an earlier state through a new revision. Prior state remains immutable and downstream artifacts become stale by impact propagation.
