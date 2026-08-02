# B04-0003 canonical projection correction review

Overall package status: `FAIL`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW`

This review was performed as a separate read-only pass in the primary
session after the mechanism audit. Fleet and subagents are forbidden by the
product-owner decision. The review is therefore procedurally separated from
the audit implementation, but it is not external actor-independent
certification and does not claim that level of assurance.

## Authority and evidence reviewed

- `MASTER_SPEC.md`, `manifests/development_manifest.yaml`, and
  `HD-EF4-F01-SG002-20260729-001`;
- immutable F01-0002 and prior B04 attempt reports, commands, and reviews;
- root `schemas/**` and `openapi/**` as the sole canonical source authority;
- the existing read-only projection mechanism at
  `scripts/build/canonical_registry/materialize.py`;
- the live derived snapshot at `src/epistemic_foundry/_canonical/**`;
- `source-inventory.json`, `snapshot-inventory.json`,
  `canonical-projection-verification.json`, and
  `installed-wheel-verification.json` from B04-0003.

The audit ran only against an external temporary staging tree. It did not
modify root canonical sources or the live package snapshot. The source
inventory contains 124 schemas plus one OpenAPI 3.1.1 document with 33 unique
operations. Missing paths, extra paths, and duplicate schema IDs are all zero.
The already-known stale snapshot mismatch is exactly
`schemas/epistemic-work-classification.schema.json`.

## Blocking findings

1. **B04-MECH001 — source bundle algorithm mismatch.** The product decision
   requires SHA-256 over deterministic canonical JSON containing normalized
   path, size, file hash, and target path. The existing materializer instead
   hashes path, NUL, raw bytes, and NUL. The required hash is
   `sha256:47a8d63daadae502bc3fc91c19cebc1f8f04f885e24d6d409c444748e04fd340`;
   the existing mechanism reports
   `sha256:4c207bf3fe666f1b194e441e0cb187dcc20c8495a519960209238d65b4709367`.
2. **B04-MECH002 — projected snapshot hash missing.** The generated registry
   does not record `projected_snapshot_bundle_hash`, so it cannot bind the
   complete derived tree required by the correction contract.
3. **B04-MECH003 — distinct source and package paths missing.** Registry
   entries expose one relative path rather than separate `source_path` and
   `package_path` values.
4. **B04-MECH004 — projection tool identity missing.** The registry does not
   record the deterministic projection tool identity and version.
5. **B04-MECH005 — atomic replacement missing.** The materializer removes and
   writes individual destination files. It does not stage and atomically
   replace the complete target tree, so a crash can expose a partial snapshot.
6. **B04-MECH006 — source-change fail-closed error missing.** The mechanism
   does not revalidate the sealed source bundle and cannot emit the required
   `SOURCE_CHANGED_DURING_PROJECTION` error.

Every finding is non-waivable under the product-owner contract. These are
clear implementation defects, so the correct package classification is
`FAIL`, not `SPEC_GAP` and not `BLOCKED`.

## Deliberately unrun gates

Live projection, clean wheel/sdist builds, installed-wheel-only loading,
deterministic rebuild, and full regression suites were not run. Running the
build hook would invoke the same nonconformant materializer and could mutate
the live snapshot file by file before the required atomicity and source-change
guards exist. None of those unrun gates is represented as PASS.

## Preservation and dependency decision

- Root `schemas/**` and `openapi/**` mutations: 0.
- Live `_canonical/**` mutations: 0.
- Unrelated writes: 0.
- Reverse synchronization and source-tree fallback: 0.
- F01 classifier artifacts modified by B04-0003: 0.
- F01-0003, F02, and F03 started: no.
- Prior B04/F01 attempts and RAH generations remain retained.

The current decision makes the existing generator and packaging tests
read-only for this correction attempt. B04-0003 must therefore remain an
immutable `FAIL`. Continuing requires a new product-owner correction decision
that authorizes the exact generator and related packaging-test paths for a new
B04 attempt; it does not permit relabeling this attempt or weakening a gate.

## Decision

B04-0003 fails with six blocking findings. No projection receipt exists,
F01 remains `WAITING_ON_B04_PROJECTION`, F01-0003 is not authorized to start,
and `completion_ready` remains false.

