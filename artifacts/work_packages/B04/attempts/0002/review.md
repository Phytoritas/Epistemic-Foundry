# B04 canonical registry packaging review

Status: `PASS`

Review mode: `ACTOR_SEPARATED_SHARED_WORKSPACE_TECHNICAL_REVIEW`

Reviewer identity: a read-only reviewer context separated from the B04
implementation work. The reviewer inspected the latest shared worktree and
independently reran the formal packaging verifier, the complete Python suite,
the packaging-focused suite, and the Git whitespace gate. The review used the
same Codex model family and shared workspace as the implementation, so it is
not external actor-independent certification. No external certification is
claimed.

## Authority and evidence reviewed

- `MASTER_SPEC.md`, `manifests/development_manifest.yaml`, the canonical
  packaging requirements in the product-owner shared-contract decisions, and
  the sealed B02, B03, and C04 PASS dependencies;
- the historical B04 root `SPEC_GAP` report, smoke result, reconciliation,
  command ledger, and review, whose bytes remain unchanged;
- `pyproject.toml`, `src/epistemic_foundry/_canonical/**`,
  `src/epistemic_foundry/contracts/registry.py`,
  `scripts/build/canonical_registry/**`, and `tests/packaging/**`;
- `b04-packaging-verification.json`, the wheel and sdist bytes, both
  `ArtifactReceipt` documents, and the preserved first failed reproducibility
  run;
- the installed-wheel isolation, source-tree fallback, mutation isolation,
  materialization safety, deterministic rebuild, source/dist convergence,
  and package-boundary evidence.

The formal packaging verifier is
`sha256:d1a4fc94edcc21275d84bbc540d09db78d1298c4a194e4392e47118d0457bd3f`.
Its deterministic evidence is
`sha256:6f07659db311b9689e45b9bd3643dc5a0c148a152ce1d1ef6e43002df02e2739`.
The full-suite JUnit artifact is
`sha256:6000a3ce26bff3ed54daa5defab3f1f4950f9ddc1b039242b8150dee073c33ac`.

## Resolved review findings

1. **B04-RF001 — in-memory mutation isolation.** Earlier registry objects
   could expose shared mutable state. Independent probes mutated a returned
   schema document, a nested manifest object, a validator schema, and a
   registry mapping. Later calls retained the original values in every case.
   `document()`, `manifest`, `validator()`, and `registry()` now return fresh or
   defensively copied state.
2. **B04-RF002 — materialization destination and link safety.** The
   materializer now rejects symlink and junction traversal, fails closed when
   a destination contains unrelated files, removes only stale canonical files
   whose ownership is verified, and preserves user-created empty directories.
   A Windows Junction probe raised `CanonicalMaterializationError` without
   changing the target.
3. **B04-RF003 — exact build backend and sdist self-containment.** The build
   backend remains `setuptools.build_meta` and is pinned exactly to
   `setuptools==82.0.1`. The constraint file is included in the sdist, is
   byte-equal to the source constraint, and the sdist-derived wheel is built
   with the extracted sdist's own constraint file.
4. **B04-RF004 — real installed-wheel no-fallback proof.** A fresh installed
   wheel had one packaged resource removed while a complete decoy source tree
   containing all 124 schemas and the OpenAPI document was placed under the
   process working directory. The fresh process returned
   `CANONICAL_REGISTRY_MISSING`; fallback attempts were one and fallback
   successes were zero.

## Findings

1. **Dependency and authority boundary — PASS.** B02, B03, and C04 are
   hash-bound PASS dependencies. The bounded B04 correction uses the existing
   runtime registry path and does not create a second authority or modify root
   `schemas/**` or `openapi/**`.
2. **Canonical source/projection convergence — PASS.** All eight comparisons
   across source, clean staging trees, wheel, sdist, second build, and the
   sdist-derived wheel report 125 resources with zero missing files, zero
   extras, and zero hash mismatches. There are 124 schemas and one OpenAPI
   document, with zero duplicate document IDs.
3. **Installed-wheel-only operation — PASS.** A clean virtual environment can
   enumerate all schemas, validate a representative schema, and load OpenAPI
   from the installed package while the repository is outside the import path
   and the current directory is an arbitrary empty directory.
4. **Integrity and fail-closed behavior — PASS.** A missing packaged resource
   produces `CANONICAL_REGISTRY_MISSING`; a one-byte mutation produces
   `CANONICAL_REGISTRY_HASH_MISMATCH`; duplicate IDs are rejected. No missing
   resource is silently replaced from the repository or current directory.
5. **Deterministic build — PASS after preserved failed attempt.** The first
   sdist reproducibility failure is retained under `verification-runs/0001-*`.
   The corrected two clean builds produce byte-equal wheels and sdists, and a
   wheel built from the unpacked sdist is byte-equal to the source-built
   wheel.
6. **Distribution receipts — PASS.** The wheel is 301,117 bytes with SHA-256
   `ac6fc720b2df29ef8ebb73c429e6ef484e7dd844ed863e55e1d744a691a73756`;
   the sdist is 246,149 bytes with SHA-256
   `dc5a40c8e9a92f58219e3b031038b745a00c30ce381cf43478f591d3041464d1`.
   Both have schema-valid, content-bound `ArtifactReceipt` documents.
7. **Regression and package boundary — PASS.** The fresh full suite records
   912 passed, zero failures, zero errors, and zero skipped tests. The focused
   packaging suite records 14 passed. Repository structure, package-boundary,
   lock, and `git diff --check` gates pass.
8. **Historical preservation — PASS.** The prior B04 `SPEC_GAP` artifacts and
   the initial failed resolving verification remain immutable evidence. No
   reset, clean, stash, history rewrite, commit, or push occurred.

## Non-blocking residual risk

A malformed ownership marker whose top-level JSON value is not an object can
currently raise a raw `TypeError` before the materializer converts the failure
to its JSON-formatted domain error. The failure happens before any destination
mutation, so it does not weaken materialization safety or the B04 acceptance
result. Error normalization should be handled by a later authorized package or
future maintenance change; it is not silently treated as successful input.

## Decision

B04-0002 passes. The wheel and sdist are deterministic, content-addressed
runtime snapshots of the single root canonical authority; installed-only
loading and fail-closed integrity behavior are verified; all blocking findings
are resolved. **blocking findings: 0**. The overall Foundry goal is not
complete, and `completion_ready` must remain false while the recomputed
development DAG continues.
