# C02 contract code-generation review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_REVIEW`

Review procedure: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

Reviewer identity: primary-session contract review. The product-owner shared
contract fixes this sequence to the primary session and forbids Fleet and
subagents while explicitly approving direct independent-review artifacts. This
review was performed after implementation and deterministic replay. It is
procedurally separate from authoring, but it is not actor-independent assurance
and no external certification is claimed.

## Authority and evidence reviewed

- `MASTER_SPEC.md`, `manifests/development_manifest.yaml`,
  `manifests/acceptance_matrix.yaml`, `manifests/product_invariants.yaml`, and
  `HD-EF4-C01-SG003-20260728-001`;
- the immutable C01-0004 report, review, commands, dependency calculation,
  contract verification, and runtime-migration impact boundary;
- `packages/contracts/codegen/generate.py`, `verify.py`, and
  `cross_language_fixture.mjs`;
- all nine generated TypeScript, Python, and UI projection artifacts;
- `c02-contract-codegen-verification.json` and the full-suite JUnit artifact;
- the package export, TypeScript typecheck, workspace structure, boundary,
  write-scope, protected-file, and Git whitespace checks.

The deterministic C02 verification artifact is
`sha256:df55f11d6c3650868c67f73a1d67b0d586598bba10c4740888815255fbb516bf`.
The full-suite JUnit artifact is
`sha256:13ca652d4efad7ff290781a42834d9b61a0cb82a8f81fece852c356beea6f5bc`.
The C01 migration authority remains
`sha256:3c35cc5cfe003055f2e039a4837e74527a843c4ed6795eee1d28b56954d36877`.

## Findings

1. **Dependency and ownership boundary — PASS.** C01-0004 is hash-bound PASS,
   C02 depends only on C01, and every authored file is within
   `packages/contracts/**`, `python/epistemic_foundry/contracts/**`,
   `web/src/generated/**`, or the declared C02 evidence-artifact scope. C02 did
   not modify the five C03-owned handwritten runtime/test paths.
2. **Single semantic authority — PASS.** `schemas/*.schema.json` is the only
   semantic source. The generator emits transport types, UI descriptors, and a
   content-addressed manifest; it explicitly does not translate Draft 2020-12
   conditional semantics into a competing validator.
3. **Canonical inventory — PASS.** The generator requires a one-to-one mapping
   of 124 schemas to 124 canonical examples, reusing the six historical C01
   filename aliases. Missing, multiply mapped, or unmapped examples fail
   closed. Duplicate schema `$id` or title also fails closed.
4. **Generated-name safety — PASS.** Root and `$defs` model names are checked as
   one namespace before rendering. A collision terminates generation rather
   than overwriting a TypeScript or Python declaration.
5. **No manually duplicated enums — PASS.** TypeScript union literals, Python
   `Literal` members, UI enum descriptors, const entries, required fields, and
   references derive by walking each canonical schema. The generator contains
   no handwritten canonical promotion vocabulary. Active generated artifacts
   contain zero `PILOT` or `HYPOTHESIS_PASSPORT_ONLY` values.
6. **Determinism and clean-diff — PASS.** Two independent temporary-tree
   generations are byte-identical to each other and to the nine checked-in
   outputs. Missing, stale, or extra generated files fail the clean-diff gate.
7. **Cross-language binding — PASS.** The three manifest copies are
   byte-identical and bind 124 contracts to schema bundle
   `sha256:be7158b4642bb1df4f5b56ad769c84cf4e36c5f8756a5b60b853531e9abb145c`
   and example bundle
   `sha256:24804ea2212948fc6a4b547006a459c6db7af8e854488c4272f20c0afe4e3428`.
   All 124 Python models import, and Node parses the same 124 fixture values.
8. **Real package-export exercise — PASS.** The Node verifier imports
   `@epistemic-foundry/contracts` through its workspace package export, then
   compares the exported runtime registry with the TypeScript, Python, and UI
   manifests. It does not bypass the package by importing the generated module
   through a repository-relative path.
9. **Language and workspace validation — PASS.** TypeScript 5.9.3 accepts the
   generated TypeScript and UI surfaces under strict NodeNext checking. The
   repository structure check and public-package-API boundary check both pass.
   No production dependency or lockfile mutation was introduced; the preserved
   `package-lock.json` hash is
   `32d30423475de0cadc8d5fe04802b0833f396d9bb36f78ee156d5a4306f2616a`.
10. **Full Python regression — accurately pending C03.** The required suite
    collects 855 tests: 831 pass and exactly 24 fail, with zero errors and zero
    skips. Every node ID and raw failure message matches C01-0004's authorized
    migration boundary. There are no new or changed failures, and the result is
    `EXPECTED_FAILURES_PENDING_C03`, never a full-suite PASS.
11. **Protected history and runtime — PASS.** The two handwritten runtime
    modules, three C03 migration-test files, and five C01 closeout files retain
    their exact protected SHA-256 values. Prior SPEC_GAP history and all RAH
    generations remain immutable.
12. **Typed outcome — PASS for C02 only.** C02 satisfies
    `codegen_clean_diff`, `cross_language_fixture_check`, single-source
    derivation, and the no-manual-enum rule. C03 is the next package and owns
    resolution of the 24 runtime migration failures. C04 and B04 remain
    dependency-blocked, and `completion_ready` remains false.

## Decision

C02 passes its generated-contract package gate. The nine generated projections
are deterministic, content-addressed derivations of the canonical schemas and
preserve cross-language fixture parity. This decision does not claim runtime
contract conformance, repository-wide zero failures, B04 packaging readiness,
or overall completion. Proceed only to C03.
