# Migration plan — Epistemic Foundry v2 / v3 to v4

## 0. Status and honesty boundary

This document is a **fail-closed reference blueprint**, not an executable
runtime migrator. It describes the *declared* upgrade, downgrade, migration and
rollback matrix that work package **Z03** proves as deterministic lifecycle
proofs over declared version states and record fixtures. Nothing here claims
that a real cross-version runtime migration executes, or that the v4 plugin is
installable, validated, or production-ready. The authority for cross-version
compatibility semantics is `migrations/contracts/compatibility-matrix.json`
(composed here by citation, never restated); the v2→v3 leg is described in
`docs/migration_v2_to_v3.md`.

Guarding invariants: **EF4-I31** (breaking schema/plugin changes require
compatibility, dry-run, backup, rollback and hook re-trust) and **EF4-I35**
(fresh install, PATH-less execution, upgrade, downgrade, uninstall and
cross-platform paths are product acceptance tests).

## 1. Compatibility position

- **Write window:** v4 only. The v4 runtime never writes v3 payloads and never
  infers or defaults `resolved_refs` on the normal write path.
- **Read window:** v3 persisted artifacts are readable **only** through
  artifact-specific, explicit v3→v4 migration entry points that supply immutable
  resolution evidence.
- **Silent fallback:** forbidden. An unresolvable legacy record fails closed
  (`LEGACY_RUN_SPEC_RESOLUTION_REQUIRED`) rather than degrading silently.
- **Forward compatibility:** not claimed. A v3 runtime reading a v4 payload is
  `UNSUPPORTED`, so every declared downgrade path (v4→v3, v4→v2) is refused
  fail-closed.

## 2. Upgrade matrix

| Path | Steps | Declared terminal |
|---|---|---|
| v2 → v4 | v2→v3, then v3→v4 | `MIGRATED_EXPLICITLY` |
| v3 → v4 | v3→v4 | `MIGRATED_EXPLICITLY` |
| v4 → v3 (downgrade) | refused | `UNSUPPORTED` |
| v4 → v2 (downgrade) | refused | `UNSUPPORTED` |

An upgrade step reconciles to `MIGRATED_EXPLICITLY` only when it presents every
required lifecycle evidence item — compatibility declaration, verified backup,
migration dry-run, rollback snapshot, and hook re-trust record — **and**
re-establishes hook trust. The Z03 harness recomputes each path terminal from
its per-step outcomes and refuses any path whose declared terminal does not
match the recomputed terminal exactly (`EF_Z03_TERMINAL_RECONCILIATION_MISMATCH`).

## 3. Hook re-trust

A breaking upgrade that changes hook definitions **must** re-establish host trust
for the changed hooks. An upgraded host can never silently inherit its prior
trust decision; a step that changed hooks without a re-trust record is refused
(`EF_Z03_HOOK_TRUST_NOT_REESTABLISHED`). Declined hooks yield a DEGRADED state,
never assumed-trusted execution.

## 4. Store / artifact migration order

1. freeze writes and pause mutating jobs;
2. create and verify a backup snapshot;
3. verify the candidate package (manifest, bundle hash, signature, SBOM);
4. diff hooks, skills, MCP tools, permissions and host requirements;
5. compile the schema/store/artifact migration plan with backfill and rollback;
6. dry-run migrations against a verified clone and compare replay/Passport
   samples (a dry-run is required before any write);
7. obtain human/policy approval for permissions, downtime and migration;
8. apply the exact approved package and migration plan with effect receipts;
9. re-approve changed hooks (re-establish trust);
10. run post-upgrade health, golden FORGE, state integrity and replay checks;
11. on a non-waivable gate failure, roll back (Section 5);
12. commit the upgrade record, retaining the rollback snapshot.

## 5. Rollback

A **FAILED** migration rolls back to the **exact prior state**. Per the composed
contract's `rollback` block, rollback:

- retains the v3 source (`v3_source_retained`);
- requires the exact source hash to match (`exact_source_hash_required`) — the
  restored source payload must hash to the recorded prior source hash;
- retains all migration records (`migration_records_retained`);
- never rewrites promotion or effect history
  (`promotion_or_effect_history_rewritten = false`) — history is append-only.

Any plan that discards the source, restores an inexact payload, drops migration
records, rewrites history, or leaves unresolved records is refused fail-closed
with a typed code whose human-readable reason exceeds fifty characters.

## 6. Backfill

Batch backfill honours the composed contract's `backfill` block: a dry-run must
precede any write (`dry_run_before_write`), an unresolved record fails the whole
batch closed (`unresolved_records_fail_closed`), and a partial success is never
reported as batch success (`partial_success_is_not_batch_success`). Receipts and
migration records are required per artifact.

## 7. Determinism

Every Z03 lifecycle proof is deterministic: no clock, no randomness,
caller-supplied timestamps, and canonical JSON hashing. Re-running any report
builder with the same declared inputs and timestamp yields a byte-identical
record and hash.
