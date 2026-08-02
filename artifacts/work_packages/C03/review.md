# C03 runtime migration contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_REVIEW`

Review procedure: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

Reviewer identity: primary-session contract review. The product-owner shared
contract fixes this sequence to the primary session and forbids Fleet and
subagents while explicitly authorizing direct independent-review artifacts.
This review was performed after implementation, targeted testing, full-suite
testing, and deterministic evidence replay. It is procedurally separate from
authoring, but it is not actor-independent assurance and no external
certification is claimed.

## Authority and evidence reviewed

- `MASTER_SPEC.md`, `manifests/development_manifest.yaml`,
  `manifests/acceptance_matrix.yaml`, `manifests/product_invariants.yaml`, and
  `HD-EF4-C01-SG003-20260728-001`;
- immutable C01-0004 migration-debt evidence and the C02 generated-contract
  checkpoint;
- the two C03-owned handwritten runtime modules, three authorized regression
  test files, `docs/schema_evolution.md`, and `migrations/contracts/**`;
- `targeted-runtime-migration.junit.xml`, `full-python-regression.junit.xml`,
  and `c03-runtime-migration-verification.json`;
- migration fixtures, compatibility/rollback/backfill contracts, active legacy
  value scans, skip/xfail scans, source hashes, dependency hashes, and Git
  whitespace checks.

The deterministic C03 verification artifact is
`sha256:51c22895ee9f0b8ae8ab44b61af13a1ab9600f5f1a8751efd890c1caacbfd4ff`.
The targeted JUnit artifact is
`sha256:d768d1268aa29c56f6dceb2e765b5b45ffda0d5aa154f220b50faf72415a972e`.
The full-suite JUnit artifact is
`sha256:b30c079f4b65c92f23974cf6597d5e2ccbb1516b9e45bb4150ad7deccd4114d8`.

## Findings

1. **Dependency and ownership boundary — PASS.** C01-0004 and C02-0001 are
   immutable, hash-bound PASS dependencies. Authored runtime, test, migration,
   documentation, and evidence files stay within C03's exact bounded scope.
   C03 does not modify canonical schemas, examples, OpenAPI, generated models,
   C04 evidence, or B04 packaging paths.
2. **Strict EvolutionRunSpec write path — PASS.** A v4 write requires the full,
   non-empty `resolved_refs` mapping with exact versions/revisions, lowercase
   SHA-256 pins, resolver identity/version, artifact locator, timestamp,
   authority class, and reproducibility class. Missing/default/empty pins,
   floating revisions, version ranges, unversioned provider aliases, and
   mismatched top-level authority bindings fail closed.
3. **Legacy EvolutionRunSpec migration — PASS.** Persisted v3 input is accepted
   only through an explicit migration entry point supplied with immutable
   resolution evidence and a distinct target run ID. Unresolvable input raises
   `LEGACY_RUN_SPEC_RESOLUTION_REQUIRED`; no environment discovery or fabricated
   reference is used. Rollback verifies the exact source hash and returns the
   preserved source payload without deleting migration history.
4. **Canonical promotion semantics — PASS.** The runtime recognizes only the
   six ordered levels. `PROMOTE` requires requested equals granted;
   `CONDITIONAL` requires `current < granted < requested`; `REJECT`,
   `UNDERDETERMINED`, and `BLOCKED` require `granted_level: null`. A non-grant
   receipt causes no candidate-level mutation, and demotion/invalidation is
   routed to a separate reassessment boundary.
5. **Legacy promotion records — PASS.** `PILOT` and
   `HYPOTHESIS_PASSPORT_ONLY` are not active aliases or fallback values. A
   historical value needs a record-specific, approved, hash-bound migration
   record; otherwise the runtime raises
   `LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED`.
6. **Gate identity and order — PASS after correction.** An adversarial review
   found that canonical generated `GateDecision` artifacts use an opaque
   `gate_id` (`GD-*`) and carry the semantic G00-G14 identity in `name`. The
   corrected runtime validates the canonical semantic order through `name`,
   requires 15 unique non-empty artifact IDs, validates decision hashes,
   evidence, policy version, applicability, and status, and preserves semantic
   gate names in `PromotionDecision.gate_decision_ids`. A regression test passes
   actual canonical `gate_decision()` output into promotion evaluation.
7. **Receipt, CAS, crash, and replay behavior — PASS.** Promotion commit checks
   the canonical idempotency composition, expected revision, CapabilityLease,
   resolving EffectReceipt, and decision/request hashes. A crash before the
   EffectReceipt cannot promote. Identical replay returns the original result;
   conflicting replay fails; non-grant replay preserves null semantics and
   candidate state.
8. **Compatibility, backfill, and rollback — PASS.** The machine-readable
   matrix exposes a v4-only write window and an explicit v3 migration read
   window. Silent fallback and partial-success batch claims are forbidden.
   Dry-run, immutable source retention, per-artifact MigrationRecord, resolving
   receipts, and exact source-hash rollback are required.
9. **Migration fixture execution — PASS.** Both MigrationRecord classes pass
   Draft 2020-12 validation. The EvolutionRunSpec fixture reproduces source,
   target, and migration hashes and exact rollback. The promotion fixture is a
   record-specific reviewed conversion, not a global mapping.
10. **Targeted runtime tests — PASS.** The targeted C03 suite records 92 passed,
    zero failures, zero errors, and zero skips. All 14 required migration and
    promotion nodes are present.
11. **C01 migration-debt continuity — PASS after correction.** An adversarial
    review found that one of C01's 24 recorded pytest node IDs had been renamed.
    The original node ID was restored. The current full-suite JUnit contains all
    24/24 authority node IDs as passing tests, so no debt item disappears by
    rename.
12. **Full Python regression — PASS for C03 implementation.** The required
    suite records 898 passed, zero failed, zero errors, and zero skipped. The 24
    C01/C02 migration failures are resolved, no xfail/skip suppression was
    added, and active canonical/runtime artifacts contain zero legacy promotion
    values.
13. **Typed outcome — PASS for C03 only.** C03 satisfies its runtime migration,
    compatibility-matrix, fixture, rollback/backfill, and full-suite migration
    obligations. Repository-wide final contract conformance remains owned by
    C04. B04 remains dependency-blocked, and `completion_ready` remains false.

## Decision

C03 passes its bounded runtime migration package gate. The handwritten runtime
now conforms to the C01 contract and the C02 projections, the exact 24 recorded
migration failures are resolved, and both targeted and full Python suites are
zero-failure and zero-skip. Proceed only to the artifact-only C04 conformance
gate; do not begin B04 before C04 PASS.
