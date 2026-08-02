# C03-0002 runtime migration review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_REVIEW`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

The product-owner execution contract requires serial execution in the primary
session and forbids Fleet and subagents. This review was performed after the
implementation and validation as a separate adversarial pass. It is not
actor-independent assurance; `actor_independence=false` and no external
certification is claimed.

## Authority and evidence reviewed

- `MASTER_SPEC.md`, `manifests/development_manifest.yaml`, and
  `HD-EF4-C01-SG004-20260730-001`;
- immutable C01-0006 and C02-0002 reports, verification artifacts, regression
  receipts, and RAH closeouts;
- the C03 exact write scope and the preserved C03-0001 history;
- `migrations/contracts/document_registration_migration.py`, its descriptor,
  compatibility matrix, migration-record schema, and fixtures;
- `docs/schema_evolution.md` and the three authorized runtime test surfaces;
- targeted and full-suite JUnit receipts plus the machine-readable C03
  verification, regression, and dependency artifacts.

## Findings

1. **Dependency and authority — PASS.** C01-0006 and C02-0002 are hash-frozen
   PASS dependencies. The active contract is exactly 126 Draft 2020-12 schemas
   and 126 one-to-one examples with 126 unique schema IDs. C03 neither redefines
   canonical schemas nor mutates the B04-owned package snapshot.
2. **Exact write scope — PASS.** C03 changes are confined to the approved
   `migrations/contracts/**`, `docs/schema_evolution.md`, two handwritten
   runtime modules, three named test files, and C03 attempt evidence. The
   unauthorized `migrations/__init__.py` path is absent.
3. **Legacy document-registration boundary — PASS.** A final legacy
   `DocumentManifest` is insufficient to reconstruct registration provenance.
   Migration requires a canonical `DocumentRegistrationRequest` and immutable
   source, receipt, principal, timestamp, and lineage evidence. Missing or
   inconsistent evidence fails closed with
   `LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED`.
4. **Canonical output and rollback — PASS.** Sufficient evidence produces the
   canonical request, registration, manifest, and a hash-bound
   `DocumentRegistrationMigrationRecord`. All outputs validate against their
   schemas. Rollback returns the exact legacy payload only when the recorded
   source hash matches.
5. **No inferred authority — PASS.** The migration performs no environment,
   repository-root, network, or package-snapshot discovery. It does not invent
   pins, registration history, receipts, actors, or timestamps.
6. **Nested request adversarial validation — PASS.** Rehashed payloads with a
   file URI, extra origin field, asserted verified external identifier,
   traversal filename, invalid media type, or noncanonical confidentiality are
   rejected. The migration independently enforces closed fields and canonical
   vocabularies rather than trusting a recomputed hash alone.
7. **Immutable evidence adversarial validation — PASS.** Empty identifiers,
   malformed SHA-256 values, non-UTC timestamps, receipt-list drift, source
   identity drift, and an unbound effect receipt are rejected deterministically.
8. **Evolution and promotion compatibility — PASS.** The handwritten runtime
   retains strict `resolved_refs` semantics, canonical promotion levels,
   conditional partial grants, null non-grants, receipt-bound atomic commit,
   replay identity, and fail-closed legacy handling. Active contract surfaces
   contain neither `PILOT` nor `HYPOTHESIS_PASSPORT_ONLY`.
9. **Targeted regression — PASS.** The targeted C03 suite collects 105 cases;
   all 105 pass with zero failure, error, skip, or xfail masking.
10. **Full regression — accurately bounded.** The full suite collects 983
    cases: 964 pass, 19 fail, zero error, zero skip. Relative to C02's 970-case
    baseline, the exact 13 new document-registration migration cases pass.
    Every residual failure retains the same node ID, raw-message hash, and
    normalized fingerprint as the prior authority: 18 belong to the authorized
    B04-0006 stale-projection reconciliation and one is the pre-existing J02
    exact-tokenizer lock debt. C03-created failures are zero, and the full suite
    is explicitly not reported green.
11. **History and gate discipline — PASS.** C03-0001's nine evidence artifacts
    retain their frozen hashes. No report, RAH evidence, generation, or dirty
    worktree content was reset, cleaned, stashed, or overwritten.
12. **Package decision — PASS.** C03 satisfies its runtime migration package
    gate. The pre-C04 B04-0006 projection correction is dependency-ready. C04,
    final B04 packaging, release readiness, and overall completion remain
    unclaimed.

## Decision

C03-0002 passes its bounded runtime migration package gate. Proceed only to the
pre-C04 B04-0006 deterministic projection and receipt. Keep the global
implementation gate failed and `completion_ready=false`.
