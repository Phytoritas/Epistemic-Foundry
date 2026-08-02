# M03-0001 query personalization, risk and change impact review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed M03
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. Query personalization is a deterministic, content-bound artifact over
   validated M01 inventory and edge-extraction identities. A missing query is
   represented by `query=null`, `personalization=null`, and zero relevance for
   every node rather than by an inferred or hidden default.
2. Non-null query relevance uses documented field-weighted Unicode token
   overlap and an exact-phrase bonus. Semantic scoring remains the separate,
   explicit `null / NOT_COMPUTED` dimension; no model confidence is invented.
3. Query output contains neither baseline centrality, intrinsic risk, nor blast
   radius. Risk/change-impact output contains neither query relevance nor
   baseline centrality. The manifest separation criterion is therefore enforced
   structurally and through negative tests.
4. Intrinsic risk is computed only from complete typed profiles for authority,
   write scope, data sensitivity, and mutable-contract status. It is not a proxy
   for relevance, centrality, or graph reachability.
5. All 19 closed M01 edge kinds have an explicit impact direction. Dependency,
   provenance and supersession targets propagate to dependants; evidence
   support/counter relations propagate from evidence to claims; contract
   ownership is bidirectional.
6. All eight shared-resource kinds materialize as deterministic pairwise,
   bidirectional effective edges. Their participants therefore contribute to
   blast radius as real typed graph structure rather than an unrecorded score
   adjustment.
7. Unresolved M01 edges remain visible and hash-bound but are excluded from
   relevance scoring and impact propagation. Empty change sets, cycles,
   multi-source traversal, equal-length canonical path witnesses, and
   permutation stability are verified.
8. Hash/ID rebuilding, deep immutability, exact risk-profile coverage, closed
   vocabularies, dense-array checks, proxies, accessors, custom prototypes, and
   tampering all fail closed without invoking attacker-controlled accessors.
9. Required checks pass 33/33: 12
   `personalization_test` and 21 `blast_radius_test` cases. M01+M02+M03 combined
   passes 80/80.
   Full Node passes 693/693
   across 69 files; full Python passes
   1064/1064.
   Codegen remains 126/126; structure, boundaries, syntax, and diff checks pass.
10. The initial 30/31 targeted diagnostic was a test-fixture defect: the test
    assigned the already-observed score `1`, so no mutation occurred. The
    fixture now uses a guaranteed different bounded score; production validation
    was not weakened. The final targeted suite is 33/33.
11. All six product files are BOM-less UTF-8 and remain inside exact
    `packages/workspace-map/src/ranking/query/**` scope. Existing dirty worktree
    changes and every historical report/evidence/generation are preserved.

## Assurance boundary

This gate establishes deterministic query relevance, intrinsic risk, and
typed graph change impact for M01-validated inputs. It does not establish M04
map-UI integration, actor-independent certification, production-scale
performance, overall product completion, release readiness, or
`completion_ready=true`. Global `implementation_gate=fail` and
`completion_ready=false` remain required.
