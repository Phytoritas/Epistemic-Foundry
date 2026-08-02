# C01 attempt 0002 contract review

Status: `SPEC_GAP_WITH_USER_AUTHORIZED_PRIMARY_SESSION_REVIEW`

Review procedure: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

Reviewer identity: primary session contract review. The product owner prohibited
Fleet and subagents and approved direct reviews for this serial execution. No
actor-independent assurance is claimed. The review was performed after the
read-only deterministic conflict probe and cannot waive a shared-contract gap.

## Authority and history reviewed

- `HD-EF4-A05-C01-B04-20260727-001` and requirements R68-R99;
- C01's corrected dependencies and write scope in
  `manifests/development_manifest.yaml`;
- the A05 attempt-0002 resolving report and authority charter;
- `manifests/acceptance_matrix.yaml` and
  `tools/validate_spec_bundle.py` schema/example mapping;
- `schemas/evolution-run-spec.schema.json` and its mapped example;
- `schemas/promotion-decision.schema.json` and its mapped example;
- the unchanged top-level C01 attempt-0001 report, commands, review, schema
  audit, and OpenAPI authority audit.

The deterministic conflict artifact is
`sha256:2f0d871c00af463360548e2282b4512a0028b0632179211ee0461d31eeac24c8`.
The prior C01 report remains
`sha256:14d1815150ba37ebc416d637afbb1514fbbb024f9fe6940ed7b976ce33b60d68`.

## Findings

1. **Prior gap resolution — confirmed.** The product-owner decision supplies
   the REST v1 endpoint, transport, security, pagination, error, and async
   authority missing in `C01-SG001`. Attempt 0002 does not reopen that gap.
2. **Mandatory schema delta — confirmed.** R72 requires `resolved_refs` in
   EvolutionRunSpec and the six A05 levels in PromotionDecision. Weakening
   either requirement, making `resolved_refs` optional, or retaining legacy
   promotion aliases would contradict the higher-order decision.
3. **Canonical example binding — confirmed.** The bundle validator maps one
   canonical example to every schema by schema stem, and the acceptance matrix
   requires zero schema/example validation errors across 124 schemas and 124
   examples.
4. **Evolution example conflict — reproduced.** Applying the required
   `resolved_refs` constraint in memory causes
   `examples/sample_evolution-run-spec.json` to fail with
   `'resolved_refs' is a required property`.
5. **Promotion example conflict — reproduced.** Applying the required six
   levels in memory causes `examples/sample_promotion-decision.json` to fail
   because `PILOT` and `HYPOTHESIS_PASSPORT_ONLY` are outside the enum.
6. **Write-scope conflict — confirmed.** Neither mapped example is in C01's
   write scope. Editing either file would violate package authority; leaving
   them unchanged makes the mandatory schema/example gate fail.
7. **No lawful compatibility escape — confirmed.** A legacy alias, optional
   `resolved_refs`, conditional bypass, or example exclusion would weaken the
   new contract or the acceptance gate. C01 cannot change its own write scope.
8. **Minimum correction — bounded.** Add only
   `examples/sample_evolution-run-spec.json` and
   `examples/sample_promotion-decision.json` to C01's write scope.
   `examples/**`, the Adjudication example, and the PhaseArtifactSet example
   are unnecessary and are not requested.
9. **Fail-closed preservation — PASS.** After detecting the conflict, no
   canonical schema, example, OpenAPI, API documentation, contract test, or
   runtime file was modified. Attempt-0001 history byte-matches its bound
   hashes.
10. **Dependency effect — confirmed.** A05 remains PASS; C01 is SPEC_GAP;
    B04 remains WAITING on C01. C02 and C03 are also direct C01 dependents.

## Validation reviewed

- deterministic conflict evidence regeneration: PASS, byte-for-byte;
- verifier compilation: PASS;
- required schema simulation: exactly one EvolutionRunSpec error and two
  PromotionDecision enum errors;
- full Python regression: 789 passed;
- C01 write-scope and history hash audit: PASS;
- `git diff --check -- artifacts/work_packages/C01`: PASS.

## Decision

`C01-SG002` is a real shared-contract scope conflict, not an implementation
failure and not a reopening of `C01-SG001`. C01 attempt 0002 is not integrated.
Per the product owner's stop rule, B04 and subsequent fixed-order work do not
start until a higher-order decision grants C01 authority over exactly the two
invalidated canonical examples.

