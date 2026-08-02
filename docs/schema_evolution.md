# Schema evolution and C03 runtime migration

Canonical JSON Schemas keep stable `$id` values, strict unknown-field policy,
and content-addressed bundle hashes. C03 does not add to or weaken the 126
canonical schemas. Its package-local migration records and fixtures live under
`migrations/contracts/**`; they describe how persisted pre-v4 records cross the
already-approved C01 contract boundary.

## Compatibility window

The v4 runtime has one write format: v4. A new `EvolutionRunSpec` must carry a
complete, non-empty `resolved_refs` object before it is sealed. Runtime never
fills it with `{}`, discovers pins from the current checkout or environment,
resolves `main`/`latest`/ranges, invents a digest, or treats an unversioned model
alias as an immutable revision.

Persisted v3 records are readable only through the explicit migration entry
point. This is a bounded read window, not backward-compatible acceptance on the
normal write path. A v3 consumer is not claimed to read v4. The machine-readable
matrix is `migrations/contracts/compatibility-matrix.json`.

| Input and operation | v4 result |
| --- | --- |
| New v4 write with complete exact pins | accepted and hash-sealed |
| New write without `resolved_refs`, or with empty/floating pins | rejected |
| Persisted v3 read with complete immutable resolution evidence | explicit migration |
| Persisted v3 read with any unresolved exact version/hash | `LEGACY_RUN_SPEC_RESOLUTION_REQUIRED` |
| Legacy promotion level without reviewed record-specific evidence | `LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED` |
| Legacy promotion level with a valid hash-bound `MigrationRecord` | explicit fixture-specific migration |
| Legacy final `DocumentManifest` plus a canonical request and complete immutable registration evidence | explicit registration-lineage migration |
| Legacy final `DocumentManifest` alone, or missing source/receipt/lineage evidence | `LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED` |

## EvolutionRunSpec v3 to v4

`migrate_legacy_evolution_run_spec` takes the immutable v3 payload, a complete
resolved-reference set, resolution-evidence artifact IDs, and a distinct target
`evolution_run_id`. It invokes the same strict builder used for new v4 writes.
The result contains the v4 spec and an `EvolutionRunSpecMigrationRecord` binding
the source artifact hash, target `spec_hash`, evidence IDs, versions, timestamp,
and its own canonical hash.

No resolver runs inside this function. If any pin cannot be reconstructed from
the existing ledger, artifact manifests, and immutable sources, migration fails
closed with `LEGACY_RUN_SPEC_RESOLUTION_REQUIRED`. The caller must not substitute
a plausible value and must not make `resolved_refs` optional to absorb history.

## PromotionDecision migration and null semantics

The active promotion ladder is `INBOX < CANDIDATE < LITERATURE_GROUNDED <
VALIDATION_SCREENED < EMPIRICALLY_TESTED < REPLICATED`. `PROMOTE` grants exactly
the requested level. `CONDITIONAL` grants a non-null level strictly between the
current and requested levels. `REJECT`, `UNDERDETERMINED`, and `BLOCKED` use
`granted_level: null` and do not change candidate state.

Historical promotion strings have no repository-wide one-to-one mapping. They
are never aliases, fallbacks, or automatic conversions. A specific record may
be converted only when an approved `PromotionLevelMigrationRecord` binds its
source value and hash, reviewed canonical target and hash, review authority,
evidence artifacts, rationale, timestamp, and record hash. Otherwise the read
fails with `LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED`.

A rejected or blocked promotion request is not a demotion. Retraction,
replication failure, leakage, forged receipts, and other invalidations require a
separate reassessment/downgrade artifact and resolving effect receipt.

## GateDecision runtime migration

The v4 `GateDecision` writer accepts the evaluated outcome plus explicit
`gate_version`, `input_artifact_ids`, `policy_bundle_hash`, and `blocker_ids`.
It derives `decision` from the final status, generates `evaluated_at` and
`created_at` from one clock reading, and hashes the complete record except for
`decision_hash`. A caller that needs replay identity must also supply the
original opaque `gate_id` and timestamp; generating a new ID or time is a new
artifact, not replay.

Pre-v4 decisions missing any canonical authority binding are not accepted on
the normal read or write path. They may be reconstructed only when immutable
artifacts establish every required field. C03 does not infer an input artifact,
policy digest, blocker, version, or timestamp, and does not copy a stale hash.
If those bindings cannot be established, validation fails closed and the
legacy record remains preserved rather than being presented as canonical.

## EvaluatorBundle and HoldoutManifest runtime migration

The v4 holdout writer requires opaque hidden-partition handles, immutable
content hashes, an ACL policy hash, redaction and cache-isolation policies, and
the bound evaluator identity. Candidate, mutation-model, prompt, and backend
access are always false; unblinding approval is always required. The evaluator
writer likewise requires code, metric, environment, dependency-lock, data,
policy, qualification, and holdout bindings. Both writers seal one timestamp
and compute their self-hash over the complete record except for that hash.

Principal access is runtime policy input to `VerifierFirewall`, not a field in
the canonical `HoldoutManifest`. The firewall recomputes both recorded hashes,
checks evaluator and holdout identity, refuses mutable or candidate-readable
records, and treats hidden, OOD, and adversarial opaque handles as leakage
targets. Candidate-generating roles remain denied even if an external runtime
policy mistakenly lists their principal.

The retired dataset-list, selection-cutoff, principal-list, string access,
unblinding-policy, rotation-policy, evaluator-artifact-list, metric-list, and
environment-ID shapes have no silent compatibility adapter. Migration requires
the actual sealed bytes, digests, handles, policy artifacts, evaluator binding,
and original time/identity evidence. Missing evidence is a validation failure;
the runtime never fabricates a digest, discovers a partition from the current
environment, or weakens the canonical schemas to absorb a legacy record.

## Document registration lineage migration

The active 126-contract inventory distinguishes the staged
`DocumentRegistrationRequest`, immutable initial `DocumentRegistration`, and
later final `DocumentManifest`. A historical final manifest does not prove that
an earlier registration request, source-byte effect, receipts, principal, or
ledger events existed. Normal v4 writes therefore never synthesize these
objects and never accept the old final manifest as an initial registration.

`migrate_legacy_document_manifest` is the only C03 compatibility entry point.
It requires a canonical hash-bound request plus a closed evidence bundle that
names the immutable source blob, content hash and byte size, action intent,
effect and artifact receipts, submitting principal, registration timestamp,
registration event, and final-manifest lineage event. The source content hash,
media type, and original filename must match the frozen legacy manifest. The
function then emits a new request/registration/manifest tuple and a
`DocumentRegistrationMigrationRecord` binding every output hash to the source
manifest hash and evidence IDs.

Missing, inconsistent, or fabricated-looking evidence fails closed with
`LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED`. No current checkout,
environment, network resolver, K01 runtime, or package snapshot is consulted.
Rollback reproduces the exact source manifest only after its hash matches the
migration record; it does not delete the new lineage or rewrite history.

## Dry-run and backfill procedure

1. Freeze the source snapshot and inventory every v3 artifact without writing.
2. Resolve every required reference only from ledger evidence, immutable
   manifests, pinned sources, and—when migrating document registration—resolved
   source/effect/artifact receipts and lineage events; record unresolved items.
3. Run the transformer in dry-run mode and validate each v4 spec, source hash,
   target hash, and `MigrationRecord` against the frozen fixtures.
4. Abort the batch if any record is unresolved. Partial success is not batch
   success, and unresolved records remain unchanged and fail closed.
5. After authorized review, append one immutable target artifact and one
   `MigrationRecord` per source artifact. Preserve the source and all ledger and
   receipt history.
6. Rebuild projections and replay from the sealed target snapshot. Reconcile
   counts, receipts, hashes, and semantic checks before advancing consumers.

## Rollback

Rollback is source-preserving, not history-rewriting. The runtime verifies that
the supplied legacy payload still matches `source_artifact_hash`, then returns
that exact payload. It never reverse-engineers v3 by dropping v4 fields. The v4
artifact, migration record, events, and receipts remain immutable evidence of
the attempted rollout. Hash mismatch fails closed.

## Breaking-change sequence

1. record the proposal and affected-object inventory;
2. freeze the shared contract and authority decision;
3. publish the migration descriptor and compatibility matrix;
4. implement forward transform and exact source-preserving rollback;
5. validate golden fixtures and canonical hashes;
6. dry-run against a frozen snapshot;
7. complete the authorized contract review and approval record;
8. append migration events and receipts;
9. rebuild projections; and
10. replay and issue a semantic-equivalence report.

## Prohibitions

- changing a schema while claiming its old content hash;
- accepting missing, empty, inferred, floating, or fabricated pins;
- silently dropping unknown or unconvertible data;
- adding legacy enum aliases or unconstrained-string fallbacks;
- treating a promotion rejection as a downgrade;
- rewriting old artifacts to look native to v4;
- inferring a `DocumentRegistration` from a final `DocumentManifest` alone;
- inventing source, receipt, principal, timestamp, or lineage evidence;
- deleting migration, effect, or ledger history during rollback; or
- advancing C04 before C03 migration tests and the full Python regression pass.
