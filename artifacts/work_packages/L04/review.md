# L04-0001 recall quality and privacy review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed L04
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. The evaluation traverses the actual L01 policy, L02 scoped-search and receipt,
   and L03 redaction/deduplication authorities. It does not replace the product
   path with a scoring-only fixture implementation.
2. Precision is an exact fixture oracle: required memory-ID sets must match,
   distractors cannot enter bounded top-k, expired records are excluded before
   ranking, exact-source duplicates do not amplify, and `SEARCHED_NONE` remains
   distinct from an unsearched class.
3. Receipt identity is bound to the post-L03 selected subset. Input permutation
   preserves selection hash, receipt ID, and result hash; selected records retain
   provenance without returning raw search/source text.
4. Privacy is fail-closed. Cross-workspace access is denied by default; the only
   permitted case is an exact USER target with policy permission, explicit opt-in,
   active matching consent, and target-workspace binding. WORKSPACE cross-access,
   missing/revoked consent, malformed policy, other classes, and other workspaces
   are rejected.
5. Prompt-injection-shaped memory text remains untrusted data and acquires no
   authority. Private/cross-workspace forbidden IDs and raw forbidden bytes have
   zero occurrences in selected output and canonical receipts.
6. Required checks pass 25/25: 10
   `recall_precision_test` and 15 `cross_workspace_leak_test` cases, with no
   skipped, todo, cancelled, xfailed, or suppressed case.
7. L01 passes 27/27, L02 passes
   41/41, and L03 passes
   44/44. Full Node passes
   613/613 across
   63 files; full Python passes
   1064/1064.
   Codegen remains 126 schemas / 126 examples; repository structure, package
   boundaries, and diff checks pass.
8. All three product/evaluation files are BOM-less UTF-8 and remain inside the
   exact `tests/evals/recall/**` scope. Existing dirty-worktree changes, historical
   reports, and RAH generations remain untouched.

## Assurance boundary

This gate establishes deterministic local fixture quality and privacy for the
current L01-L03 memory path. It does not claim production corpus recall metrics,
production persistence/vector infrastructure, actor-independent review, overall
product completion, release readiness, or `completion_ready=true`. Global
`implementation_gate=fail` and `completion_ready=false` remain required.
