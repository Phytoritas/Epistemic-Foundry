# M04-0001 map UI and ranking-claim gate review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed M04
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. The view accepts exactly the M01 inventory/extraction, M02 baseline
   centrality, and M03 query/risk-impact artifacts and invokes every owning
   validator. No score or identity is silently trusted or recomputed by the UI.
2. The claim vocabulary is closed to baseline structural centrality, query
   lexical relevance, intrinsic risk, and change impact. Generic importance,
   combined scores, confidence, verdict, and semantic rank have no authority.
3. Every displayed label is bound to the sealed algorithm name, implementation
   version, artifact hash, order, score field, and unresolved-edge exclusions.
   Missing, duplicate, reordered, relabelled, stale, or tampered claims fail.
4. Coverage and exclusions are the first visible section. Indexed entities,
   unreadable paths, resolved/unresolved edges, reasons, and per-dimension
   exclusions remain visible; unresolved edges affect no ranking or impact.
5. Baseline centrality, query lexical relevance, intrinsic risk, and change
   impact remain four independent node dimensions. Risk is not inferred from
   blast radius and blast radius is not presented as a scalar risk score.
6. Query absence remains `null / NOT_PERSONALIZED`; semantic scoring remains
   `null / NOT_COMPUTED`. No unavailable value is fabricated or collapsed.
7. UI HTML escapes untrusted labels, queries, paths, and unresolved hints.
   Proxies, accessors, sparse arrays, custom fields, upstream tampering, and
   claim laundering fail closed without executing attacker-controlled getters.
8. View and claim derivation are deterministic, input-preserving, and deeply
   frozen. Input permutation produces identical projections and audit results.
9. Required checks pass 26/26: 12
   `map_ui_test` and 14 `ranking_claim_audit` cases. M01 through M04 combined
   passes 106/106.
   Full Node passes 719/719
   across 71 files; full Python passes
   1064/1064.
   Codegen remains 126/126; structure, boundaries, syntax, and diff checks pass.
10. The preserved initial 25/26 diagnostic was a test-fixture defect: the test
    attempted to mutate an already frozen artifact and raised before invoking
    the validator. Only the fixture was changed to `structuredClone`; production
    validation was not weakened. The final targeted suite is 26/26.
11. All six product files are BOM-less UTF-8 and remain inside exact
    `web/src/features/map/**` scope. Existing dirty worktree changes and every
    historical report/evidence/generation are preserved.

## Assurance boundary

This gate establishes the M04 read model, visible coverage/exclusions, truthful
algorithm labels, and ranking-claim audit for validated M01-M03 artifacts. It
does not establish actor-independent certification, production browser styling,
production-scale performance, overall product completion, release readiness,
or `completion_ready=true`. Global `implementation_gate=fail` and
`completion_ready=false` remain required.
