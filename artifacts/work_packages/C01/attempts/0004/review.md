# C01 attempt 0004 contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_REVIEW`

Review procedure: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

Reviewer identity: primary-session contract review. The product owner prohibited
Fleet and subagents for this fixed serial sequence and explicitly approved
direct review. This review was performed after implementation and deterministic
replay. It is procedurally separate from authoring, but it is not
actor-independent assurance and no external certification is claimed.

## Authority and evidence reviewed

- `HD-EF4-C01-SG003-20260728-001`, including the C01-local gate, C03 migration
  ownership, C04 full-suite ownership, and B04-after-C04 rule;
- preserved `C01-0001`, `C01-0002`, and `C01-0003` reports, reviews, commands,
  verification artifacts, and the unresolved history of `C01-SG003` before the
  product-owner decision;
- the corrected C01/C02/C03/C04/B04 entries in
  `manifests/development_manifest.yaml`;
- all canonical schemas, canonical examples, OpenAPI 3.1.1, API documentation,
  and C01 contract tests;
- baseline and residual full-suite JUnit artifacts and every normalized
  migration-failure fingerprint;
- deterministic evidence at
  `artifacts/work_packages/C01/attempts/0004/c01-contract-verification.json`.

The C01-0004 verification artifact is
`sha256:c60a154ff342a802de5f8333b3cbad8bdfdc4c15a4f6c735a51c47e0ef7abc64`.
The migration-impact artifact is
`sha256:3c35cc5cfe003055f2e039a4837e74527a843c4ed6795eee1d28b56954d36877`.
The prior C01-0003 report remains
`sha256:d3f14a0f227bc7fa4743b7d2fbb266cb1999cd2524f4a93a9770b19910a130e5`.

## Findings

1. **C01-SG003 resolution — confirmed.** The canonical HumanDecision is
   recorded, its content hash and canonical decision hash remain valid, and
   C01-0003 remains immutable `SPEC_GAP` history. The new decision is
   prospective; it does not relabel any prior result.
2. **Package ownership and gate order — PASS.** C01 owns canonical contracts
   only. C02 depends on C01; C03 depends on C01 and C02 and owns exactly the
   five authorized runtime/test migration paths; C04 depends on C02 and C03
   and owns the repository-wide zero-failure gate; B04 depends on C04 in
   addition to B02 and B03.
3. **EvolutionRunSpec authority — PASS.** `resolved_refs` remains required,
   contains all twenty A05 pin classes, and requires the canonical resolution
   tuple. Floating aliases and version ranges remain rejected. The fixture
   contains no inferred/default pin and recomputes to
   `sha256:580392a2d791515a6523472372fa3139321807a9fa3a2a0f183e93b4686948df`.
4. **PromotionDecision null semantics — PASS.** `granted_level` remains a
   required field. `PROMOTE` requires a non-null grant exactly equal to the
   request. `CONDITIONAL` requires a non-null level strictly below the request;
   the runtime will additionally enforce current-level ordering in C03.
   `REJECT`, `UNDERDETERMINED`, and `BLOCKED` require `null` and do not change
   prior candidate or Passport state. Demotion remains a separate reassessment
   workflow.
5. **No schema weakening or legacy escape hatch — PASS.** `PILOT` and
   `HYPOTHESIS_PASSPORT_ONLY` have zero active canonical literal hits. Neither
   alias, unconstrained string fallback, inferred `resolved_refs`, nor an
   empty/default pin path was introduced.
6. **Canonical schema and examples — PASS.** All 124 Draft 2020-12 schemas
   meta-validate, all 124 `$id` values are unique, all 124 canonical examples
   validate one-to-one, and schema/example cardinality remains unchanged.
7. **REST v1 contract — PASS.** The document is OpenAPI 3.1.1 with Draft
   2020-12 dialect, `/api/v1`, 33 unique operations, 22 canonical external
   scientific schema references, explicit operation security/capabilities,
   and idempotency on all twelve mutations. `openapi-spec-validator==0.7.2`
   returns `OK`. OpenAPI Generator 7.14.0 completes a Python client dry-run
   using the repository-relative input and writes no generated client into the
   repository.
8. **Targeted contract regression — PASS.** The C01 suite passes 71 tests with
   zero failures and zero skips, exceeding the prior 64-test floor.
9. **Full Python regression — accurately pending C03.** The residual suite
   collects 855 tests: 831 pass and 24 fail. The same 24 node IDs were present
   in the 848-test baseline, grouped as two EvolutionRunSpec, fourteen
   governance, and eight FORGE-cycle failures. All 24 normalized fingerprints
   match. Twenty-two raw messages have smaller `(+N more)` suffixes because the
   authorized decision-specific schema branches remove or reclassify secondary
   errors; both raw messages and that explanation are preserved per failure.
   No new failure is hidden.
10. **C01 runtime boundary — PASS.** The two handwritten runtime files and
    three migration-test files retain their exact pre-attempt SHA-256 values.
    C01 made no runtime migration, added no skip/xfail, and did not start C03,
    C04, or B04.
11. **Whole-bundle diagnostic — separated.** `validate_spec_bundle.py
    --no-audit` still reports fourteen `PACKAGE_MANIFEST` hash/inventory
    diagnostics from the preserved dirty worktree. These are not used as C01
    PASS evidence, are not erased, and do not become a claim that the full
    repository suite or package manifest passes.
12. **Typed outcome — PASS for C01 only.** Under the explicit product-owner
    decision, C01's package status is `PASS` and contract status is
    `CONFORMANT`; runtime migration is `PENDING_C03`, full-suite status is
    `EXPECTED_FAILURES_PENDING_C03`, and `completion_ready` remains false.

## Decision

C01 attempt 0004 passes its canonical-contract-local gate. C02 is now the only
next package in the fixed sequence. The 24 runtime failures remain visible,
owned by C03, and must reach zero before C04 can pass. B04 remains forbidden
until C04 PASS, and no repository-wide conformance or overall completion is
claimed.
