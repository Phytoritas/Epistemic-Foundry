# M01-0001 typed inventory and dependency extraction review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed M01
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. M01 consumes a frozen logical snapshot and is a pure deterministic mapper;
   it does not scan or mutate the filesystem, guess missing targets, or acquire
   canonical workspace-snapshot authority owned by later M packages.
2. The closed inventory vocabulary separates CODE, RESEARCH, and ARTIFACT
   layers and keeps SOURCE, DIST, GENERATED, VENDOR, and TEST identities
   explicit. Portable paths, explicit locators, hashes, unreadable paths,
   duplicate identities, custom prototypes, accessors, proxies, sparse arrays,
   and cyclic canonical input are fail-closed.
3. Edge extraction retains typed identity namespaces, source/target direction,
   owner, source locator, and provenance. Missing research and provenance
   targets remain explicit as `TARGET_NOT_FOUND` or
   `MISSING_TARGET_LOCATOR`; no unresolved edge is silently dropped.
4. Inventory and edge IDs bind deterministic canonical hashes. Input
   permutation is byte-stable, outputs are deeply immutable, and validation
   rejects content, count, partition, hash, ID, inventory-binding, and semantic
   tampering.
5. M01 emits no ranking, centrality, personalization, or score. Those remain
   bounded to M02/M03.
6. Required checks pass 22/22: 11
   `map_inventory_test` and 11 `edge_resolution_test` cases, with no failure,
   skipped, todo, cancelled, xfailed, or suppressed case.
7. Full Node passes 635/635
   across 65 distinct files, and full
   Python passes 1064/1064.
   Codegen remains 126 schemas / 126 examples; repository structure, package
   boundaries, and diff checks pass.
8. All four product files are BOM-less UTF-8 and remain inside the exact
   `packages/workspace-map/src/inventory/**` scope. Existing dirty-worktree
   changes, historical reports, evidence, and RAH generations remain untouched.

## Assurance boundary

This gate establishes typed deterministic inventory and dependency extraction
for a caller-supplied frozen snapshot. It does not establish filesystem watcher
or parser coverage, ranking quality, centrality, personalization, production
scale, actor-independent review, overall product completion, release readiness,
or `completion_ready=true`. Global `implementation_gate=fail` and
`completion_ready=false` remain required.
