# L02-0001 memory indexing and scoped retrieval review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial pass over the fixed L02
source hashes and verification receipts, not actor-independent certification.

## Findings

1. L02 invokes L01 policy admission before opening an index. Each selected
   record is then re-evaluated with its actual creation timestamp before its
   search text can contribute to ranking. Denied, expired, future-dated, or
   scope-mismatched records never become hits.
2. Only `SESSION`, `WORKSPACE`, `USER`, and `EVIDENCE` are retrievable in the
   active memory workflow. `EPHEMERAL` and `REGULATED` fail closed before index
   access even if a custom L01 policy lists them as allowed. Searched and
   excluded classes still partition all six canonical classes.
3. Same-workspace filtering is exact. Cross-workspace retrieval remains
   default-deny and is limited to `USER` memory after every L01 policy,
   explicit-opt-in, consent, purpose, data-class, and scope gate passes.
4. Ranking is deterministic Unicode NFKC token overlap with an exact result
   cap and stable score, memory-ID, and source-hash ordering. Index, store,
   plan, execution, receipt identity, and result hashes fail closed on tamper.
5. A `SEARCHED_NONE` execution remains distinguishable from a search that was
   never run. Receipts retain query, scope partition, consent, ContextCapsule,
   source hashes, timestamp, scores, and redaction accounting without leaking
   raw memory text.
6. L03 ownership remains intact. L02 does not implement redaction policy,
   deduplication, deletion, forget, or legal-hold behavior; the receipt API only
   permits a later L03 stage to bind a deterministic selected/redacted subset.
7. Required checks pass 41/41: 22 `memory_scope_test` cases and 19
   `retrieval_receipt_test` cases. `memory-index.mjs` coverage is
   91.49% lines, 75.97%
   branches, and 97.73% functions. The sealed
   runtime receipt validates against canonical Draft 2020-12 with zero errors.
8. L01 predecessor tests pass
   27/27.
   Full Node passes 544/544
   and full Python passes 1064/1064.
   Codegen remains 126 schemas / 126 examples; structure, package boundaries,
   and diff checks pass without skipped, xfailed, todo, or cancelled cases.
9. All five product files remain within the exact L02 manifest scope. The
   generated Python cache was removed by exact resolved path; historical
   attempts, RAH generations, and unrelated dirty-worktree changes remain
   untouched.

## Assurance boundary

This gate establishes deterministic in-memory indexing, scoped retrieval, and
receipt semantics. It does not claim a production database or vector service,
L03 lifecycle behavior, cross-device synchronization, overall product
completion, release readiness, or `completion_ready=true`. Global
`implementation_gate=fail` and `completion_ready=false` remain required.
