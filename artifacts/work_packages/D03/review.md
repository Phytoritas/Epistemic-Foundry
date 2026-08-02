# D03 content-addressed artifact store and receipts review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Final verdict: `PASS`

blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

The product owner requires serial primary-session execution without Fleet or
subagents and explicitly approves all independent reviews. This review is
therefore a procedurally separate adversarial pass in the primary session. It
does not claim external actor-independent certification.

## Authority and final reviewed bytes

- `MASTER_SPEC.md`, `MASTER_EXECUTION_PROMPT.md`, `AGENTS.md`, and D03 in
  `manifests/development_manifest.yaml`;
- D01 dependency report —
  `sha256:00d44672b4c9680589ecd85c39f617c29bdfe79afd288a2769cafb1ba59a9a91`;
- `packages/foundry-kernel/src/artifacts/content-addressed-artifact-store.mjs`
  — `sha256:75e69756d30ab5b5112fd908f3fec312660f30e603fe1201566db2ad263c8c8e`;
- `packages/foundry-kernel/src/artifacts/artifact-hash.test.mjs` —
  `sha256:587b78680a5b5175f6889273369eddd25f54f3c47cf5d618277b9a4db634484a`;
- `packages/foundry-kernel/src/artifacts/orphan-receipt.test.mjs` —
  `sha256:c22c07e3d81d7121a8cf8258538bc8299d512413ae2a302327485206e2518d68`.

## Resolved blocking findings

1. **D03-RF001 — content, registration, and receipt identity conflation.**
   The final design addresses exact byte objects by SHA-256 while keeping
   `artifact_id` and `receipt_id` opaque and independent. Identical bytes may
   have multiple registrations and receipts, but neither opaque identifier can
   be rebound to different immutable content or metadata.
2. **D03-RF002 — opened-file/path and record-identity TOCTOU.** Canonical
   paths, roots, file identities, link counts, record paths, embedded IDs, and
   content hashes are revalidated. Root replacement, cross-address copying,
   hard links, symlinks, junctions, traversal, and unexpected entries fail
   closed.
3. **D03-RF003 — post-rename commit uncertainty.** Publication stages and
   flushes records before rename, flushes canonical files, attempts directory
   flushes where supported, then verifies the committed graph. An uncertain
   or unverifiable post-rename outcome is never reported as success and enters
   `SAFE_MODE`.
4. **D03-RF004 — writer mutation-lock `ENOENT` handoff.** A disappearing lock
   during ownership handoff is treated as a bounded namespace transition only
   after the staging entry and surrounding structure remain valid. Identity
   drift or an invalid entry still fails closed.
5. **D03-RF005 — reader transient staging disappearance.** Readers tolerate a
   concurrent publisher removing its private staging entry, while malformed,
   linked, persistent, or structurally inconsistent staging material remains
   an integrity failure.
6. **D03-RF006 — Windows transient `EPERM` during mutation-lock removal.** The
   implementation performs at most eight retries after the initial attempt,
   and only for `EPERM`/`EACCES` while enumerating or inspecting `.staging` and
   its mutation lock. Canonical bytes, manifests, and receipts have no retry
   relaxation. One-shot injected `EPERM` recovers; persistent `EPERM` reaches
   exactly nine attempts and enters `SAFE_MODE`.

## Final findings

1. **Three-layer immutable identity — PASS.** Raw bytes determine the content
   digest. Opaque artifact registrations bind content, schema, creator, and
   canonical metadata. Opaque receipts bind the registration, manifest hash,
   exact byte digest and byte size, creator, and their own canonical
   self-hash. Global duplicate-ID scans prevent cross-object rebinding before
   publication.
2. **Receipt resolution — PASS.** A resolving receipt requires the exact byte
   object and canonical manifest; copied, missing, partial, orphaned, or
   cross-labeled records are rejected. One artifact may legitimately retain
   several independently identified receipts.
3. **Canonical persistence — PASS.** Records use deterministic canonical JSON
   and UTF-8. The generated `ArtifactManifest` and `ArtifactReceipt` pass the
   canonical Draft 2020-12 schemas. Noncanonical serialization, hash mismatch,
   malformed persisted data, and extra files fail closed.
4. **Crash-aware publication boundary — PASS for D03.** Staging, same-filesystem
   rename, file fsync, supported directory fsync, committed graph verification,
   and a serial mutation lock prevent narrative or partial completion. D03
   intentionally does not implement stale staging/lock recovery, backup, or
   corruption-recovery policy; those are D04 responsibilities.
5. **No permissive path fallback — PASS.** The store neither reads from the
   repository root nor depends on the current working directory. Linked roots,
   changed roots, aliases, absolute names, mixed separators, hard-linked record
   files, and unknown entries are denied.
6. **No mutation escape hatch — PASS.** The public surface contains no delete,
   overwrite, or update operation. Idempotent replay returns the existing
   immutable logical result only when the entire request binding matches.
7. **Concurrency — PASS.** Concurrent identical publishers converge and
   distinct registrations can share one object. The final repeated gate records
   25/25 runs, 50/50 targeted executions, and 100/100 worker results.
8. **Verification — PASS for D03.** The required suites record 40/40. Coverage
   on one canonical module identity is 84.83% lines, 79.62% branches, and
   92.98% functions. Python records 912/912; D03, D01, and kernel security
   record 112/112. Structure, boundaries, toolchain, CI policy, strict UTF-8,
   and whitespace checks pass.

## Preserved failures and limitations

- The repository-wide Node set records 143 passed and one existing non-D03
  failure, `S04-TM004`, because the stored
  `development_manifest.yaml` hash binding is stale. D03 does not own S04.
- `scripts/build/double_build.py` retains the existing non-D03 failure because
  staged source omits `scripts/`, which the build hook requires. D03 does not
  own build integration.
- An early cache-busting coverage run double-counted the same logical module
  and reported a misleading 26.88% line value. It is preserved in
  `commands.jsonl`; the final canonical single-module run is 84.83%.
- Three simultaneously launched overlap stress commands exceeded their
  120-second tool windows. Their six test processes exited naturally; no
  unrelated Node process was killed. The isolated overlap scenario and final
  25-run contention gate pass.
- Windows does not expose the same portable directory-fsync primitive as Unix.
  Canonical files are fsynced and directory handles are fsynced where the
  platform supports them; the implementation does not claim stronger Windows
  directory durability than the host provides.
- Without a kernel `openat`-style directory-handle API, the implementation
  materially narrows and detects path/identity replacement but does not claim
  mathematical elimination of every malicious concurrent parent-directory
  substitution.
- Stale staging/lock recovery and backup/corruption lifecycle remain expressly
  assigned to D04.

## Decision

D03 satisfies its exact package contract. Immutable byte objects are addressed
by hash, and receipts resolve exact bytes, schema, creator, and manifest under a
fail-closed publication and integrity boundary. No non-waivable D03 finding
remains. The overall Foundry objective is not complete; `completion_ready`
remains false. The recomputed READY order is D04, G01, A06, and the next
manifest-order package is D04.
