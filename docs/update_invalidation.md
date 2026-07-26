# Update, correction, retraction, and invalidation

## Triggers

- new paper version,
- correction or retraction,
- metadata resolution change,
- SourceIntegrityReport change,
- Claim grounding revision,
- dependency-cluster merge/split,
- DomainPack, ontology, policy, prompt, schema, or model-routing change,
- external ValidationTarget version change.

## Impact computation

UpdateImpactReport records the changed root, graph traversal, affected artifacts, unaffected artifacts, severity, and required reassessment.

## Reassessment policy

Reprocess the smallest valid set. Unchanged artifacts are reused by hash. Child workflow runs are linked to the reassessment plan. Partial child failure blocks current projection release.

## Notifications

Material changes notify owners and downstream subscribers. Notification is an event with redaction and delivery status. A changed verdict must show the exact evidence, gate, or policy delta that caused it.
