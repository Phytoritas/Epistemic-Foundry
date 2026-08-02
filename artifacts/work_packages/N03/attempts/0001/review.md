# N03-0001 DAG scheduler, leases, retries and concurrency review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed N03
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. DAG compilation is deterministic across node permutations. Duplicate,
   unknown, self, hostile, and cyclic dependencies fail closed; every real
   cycle requires exactly one matching, hash-valid `LoopContract` whose
   back-edge removal yields an entry-to-exit executable order.
2. Readiness is bound to real predecessor status and terminal receipts. Failure
   policy remains typed and visible; a downstream node cannot infer success
   from an absent receipt or an unresolved predecessor.
3. Admission requires resolved inputs, policy/approval evidence, and external
   E03 capability-lease IDs. The scheduler records this evidence but does not
   mint, replace, or broaden capability authority.
4. Budget and resource admission is checked before token, usage, lease, or
   ownership mutation. Exclusive resources, bounded quotas, and multi-resource
   acquisition are atomic; rejected admission leaves no partial reservation.
5. Node and exclusive-resource fencing prevents stale workers from committing.
   Exact acquisition retry reuses one lease, while changed idempotency,
   admission, or reservation bindings conflict instead of silently forking.
6. Attempts are immutable. Retry is allowed only for the closed transient
   failure taxonomy, timestamps cannot regress, and expired/unknown-effect
   work enters reconciliation before reassignment. Success after reconciliation
   requires terminal, reconciliation, and effect receipts.
7. Hard call/concurrency budgets and bounded loop iteration, cost, wall-time,
   dry-round, and dedupe rules are enforced without inventing unavailable
   meters. Command replay reproduces exact state and rejects tamper.
8. Plans, leases, attempts, command logs, and snapshots are deeply immutable;
   snapshots bind active leases, budget usage, fencing heads, resource owners,
   and idempotency bindings.
9. Required N03 checks pass 24/24: 15
   `scheduler_property_test` and 9 `resource_conflict_test` cases. N01 passes
   21/21, E02 passes 19/19, and E03 passes 30/30. The official serial full Node
   gate passes 793/793
   across 77 files; full Python passes
   1064/1064.
   Codegen remains 126/126; structure, boundaries, syntax, and diff checks pass.
10. Before formal serial collection, a diagnostic run observed 792/793 with one
    unrelated artifact-store concurrency failure; the isolated surface passed
    1/1 and a complete rerun passed 793/793. The original failing test identifier
    was not retained, so this review records that evidence limitation without
    inventing a name. The independently captured official serial JUnit is clean.
11. All five product files are BOM-less UTF-8 and remain inside exact
    `packages/foundry-kernel/src/scheduler/**` scope. Existing dirty worktree
    changes and every historical report/evidence/generation are preserved.

## Assurance boundary

This gate establishes an in-memory deterministic scheduler contract and its
failure, replay, resource, receipt, and fencing semantics. It does not prove
distributed consensus, persistence across process restart outside command-log
replay, remote provider availability, N04 fan-in/reviewer independence,
actor-independent certification, overall product completion, release or
production readiness, or `completion_ready=true`. Global
`implementation_gate=fail` remains required.
