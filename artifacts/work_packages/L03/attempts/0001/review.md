# L03-0001 redaction, dedupe, forget and legal-hold review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial pass over fixed L03
source hashes and verification receipts, not actor-independent certification.

## Findings

1. Redaction accepts only explicit source-hash-bound UTF-8 byte spans. Source
   content is verified before use; out-of-range, overlapping, code-point-
   splitting, no-op, duplicate, unused, or profile-only directives fail closed.
   Source bytes are never mutated; a content-addressed derived artifact is
   emitted and replay validation rejects accessor/proxy and hash tampering.
2. Deduplication groups only exact source hashes. The representative is selected
   by score descending, memory ID ascending, then source hash ascending. A
   duplicate neither contributes another selected hit nor raises the score, and
   every exclusion is bound back to the selected representative and source.
3. Forget and delete create a new immutable terminal revision, clear canonical
   content/artifact references, and retain a non-reversible source tombstone
   only when a sealed policy carries explicit policy-and-law authority. A new
   request cannot rewrite a terminal revision.
4. Legal holds require a sealed authority record, bounded start/expiry interval,
   workspace scope and optional memory/class scope. A matching active hold
   preserves the exact source revision and records `NOT_EXECUTED`; expired,
   future, and nonmatching holds do not acquire blocking authority.
5. Canonical forget is distinct from disposable index/cache eviction. The
   lifecycle request rejects noncanonical targets, so cache deletion cannot be
   represented as fulfillment of a user forget request.
6. Requests, policies, states, holds, payloads, outcomes, and replay lineage are
   hash-bound. Same-key/same-request replay returns the prior immutable outcome;
   key reuse with another request, another policy, or unrelated state lineage
   fails closed.
7. ActionIntent and EffectReceipt use the common effect authority; EventRecord
   uses the Noetic Ledger hash authority. All three canonical Draft 2020-12
   schemas validate with zero errors and independently recomputed hashes match.
8. Required checks pass 44/44: 19 `redaction_test` and 25
   `forget_legal_hold_test` cases. `memory-lifecycle.mjs` coverage is
   94.53% lines, 79.95%
   branches, and 94.79% functions.
9. L01 predecessor tests pass
   27/27;
   adjacent L02 passes
   41/41.
   Full Node passes 588/588
   across 61 files and full Python
   passes 1064/1064.
   Codegen remains 126 schemas / 126 examples; structure, package boundaries,
   and diff checks pass without skipped, xfailed, todo, or cancelled cases.
10. All five product files remain inside the exact L03 manifest scope. Existing
    dirty-worktree changes, historical attempts, and RAH generations remain
    untouched.

## Assurance boundary

This gate establishes deterministic local in-memory lifecycle semantics. It
does not claim a production persistence backend, jurisdiction-specific legal
advice, L04 recall-quality integration, L05 evolution-memory policy, overall
product completion, release readiness, or `completion_ready=true`. Global
`implementation_gate=fail` and `completion_ready=false` remain required.
