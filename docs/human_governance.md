# Human governance, approvals, and appeals

## Roles

A production deployment assigns:

- corpus/license steward,
- annotation owner and adjudicator,
- research decision owner,
- method/ethics reviewer,
- data protection or privacy authority where applicable,
- validation action approver,
- incident commander,
- release attestor,
- signing-key custodian.

One person may hold multiple roles only when the PolicyBundle permits it and the conflict is recorded.

## HumanDecision contract

Every decision records subject revision, authority, role, rationale, evidence, scope, expiry, affected artifacts, and whether it supersedes a prior decision. It never edits the machine result.

## ApprovalRecord

Consequential actions require scoped approval. Approval expires, can be revoked, and is checked immediately before ActionIntent execution.

## Appeals

Appeals create new review artifacts and may produce a new decision revision. They do not delete prior reasoning. Emergency revocation can halt execution and mark dependent outputs stale.

## Separation of duties

- maker cannot self-approve,
- judge cannot waive deterministic gates,
- operator cannot sign its own unreviewed release,
- source/license steward cannot silently expand document access,
- model output cannot grant capabilities.
