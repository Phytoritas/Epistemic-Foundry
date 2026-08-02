# D04 backup, corruption, and recovery gate review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Final verdict: `PASS`

blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

The product owner requires serial primary-session execution without Fleet or
subagents and explicitly approves the independent-review artifacts. This is a
procedurally separate adversarial review of the final D04 bytes. It is not external
actor-independent certification.

## Authority and reviewed boundary

- `MASTER_SPEC.md`, `MASTER_EXECUTION_PROMPT.md`, `AGENTS.md`, and D04 in
  `manifests/development_manifest.yaml`;
- dependency reports D02
  (`sha256:b843adb04258b3e72d3a2f21591441bd94f2a16ea409b014c8b49f1200eb004b`)
  and D03
  (`sha256:10f6c29d27bbd68ace5a86fa21d019037b8a7bcec82c92c9f0922d66106eaf33`);
- unchanged dependency implementations: SQLite store
  (`sha256:6619dccb72f40e92fdaae3d023a2d6591f8d63bdfe789ba5c36b53ce7dbe1380`),
  PostgreSQL migration
  (`sha256:21f349f098a03b8e7e2f4a82cef69f5df0fe2e73d88224ab197191260e316682`),
  and artifact store
  (`sha256:75e69756d30ab5b5112fd908f3fec312660f30e603fe1201566db2ad263c8c8e`);
- final D04 files:
  - `tests/recovery/state/recovery-fixtures.mjs` —
    `sha256:a09eca4e977092e99500a8e146196831fb64a155e6b04a23e0c576f81b034b66`;
  - `tests/recovery/state/crash-recovery.test.mjs` —
    `sha256:73ec38611cd9cb8e93ea531065ff8e885c044f0c8a11a4dcb8a5500e85729cdf`;
  - `tests/recovery/state/backup-restore.test.mjs` —
    `sha256:f7e780cf3f3a4b15bfd70054bcf06c91ee9ccaa131cc4d7cadc98372a3f6ac66`;
  - `tests/recovery/state/test_postgres_backup_restore.py` —
    `sha256:877fd187e1f2360fe0afec008e2cec9bb4e85733206e4d61089386ad83ad6141`.

D04 owns only `tests/recovery/state/**` and
`artifacts/work_packages/D04/**`. No D01, D02, or D03 implementation file was
modified to make the gate pass.

## Resolved review findings

1. **D04-RF001 — PostgreSQL owner dump under forced RLS.** The first custom
   dump ran as the schema owner and PostgreSQL correctly rejected the table
   export because `revisioned_records` uses `FORCE ROW LEVEL SECURITY`. The
   fixture was corrected without weakening RLS: records are created through
   the runtime principal, transaction-local tenant/workspace context, and the
   canonical `SECURITY DEFINER` create function. The disposable backup
   operator is the container-local `postgres` superuser; the dump retains
   ownership, restore runs into a fresh staging database, and the test then
   revalidates forced RLS, owner identity, canonical functions, data, and
   runtime-principal access before database rename.
2. **D04-RF002 — validation-to-publish TOCTOU and partial target exposure.** An
   initial test harness validated a SQLite backup or artifact snapshot before
   copying directly to the final target. A mutation between validation and
   completion could leave a partial target. The final harness copies to a
   sibling restore stage, rechecks the copied SQLite hash and
   `PRAGMA integrity_check` or the full artifact inventory/hash manifest, and
   only then atomically renames the stage. Fault injection mutates each staged
   copy after initial validation. Both cases reject publication, leave the
   canonical target absent, preserve the quarantined stage for diagnosis, and
   leave the backup/snapshot unchanged.

## Final findings

1. **Abrupt SQLite process death — PASS.** A real child process is terminated
   after a committed WAL write. Reopen recovers the committed record and
   passes integrity checking. A second child dies inside an open transaction;
   reopen preserves the prior revision and contains neither the partial record
   nor the attempted update. No reset or replacement is used.
2. **SQLite corruption and restoration — PASS.** Header corruption enters
   `SAFE_MODE` and the exact corrupted bytes remain unchanged. A live
   `node:sqlite.backup()` snapshot restores only snapshot-time state. The
   restored database passes the store integrity path, while later source
   records do not appear. Invalid source hashes and staged-copy mutation are
   rejected before canonical target publication.
3. **Artifact crash residue and corruption — PASS.** A killed publisher leaves
   an intentionally constructed `.staging` residue. The residue remains
   present but is not enumerated as a canonical artifact. A committed artifact
   still resolves through its receipt. Later canonical-byte corruption enters
   `SAFE_MODE` without resetting the source.
4. **Artifact backup graph — PASS.** The snapshot contains only `sha256/**`
   canonical files, excludes `.staging` and the mutation lock, records sorted
   relative paths, byte sizes, file SHA-256 values, and a canonical source
   bundle hash. Validation rejects links, multiply-linked files, unexpected
   inventory, malformed paths, and content mutation. Restore to a fresh sibling
   stage is revalidated before atomic publication, and the installed store
   resolves the original exact bytes and receipt.
5. **PostgreSQL staging recovery — PASS.** The test uses the exact pinned
   PostgreSQL 16.13 image digest and does not touch `memento-postgres`. A
   custom-format `pg_dump` is preflighted with `pg_restore --list`. Restore is
   `--single-transaction --exit-on-error` into a new staging database. Schema,
   four canonical functions, forced RLS, owner, snapshot record, absence of a
   post-backup record, and runtime access are verified before the staging
   database is renamed. The deliberately damaged source database remains
   unchanged. A corrupt archive is rejected before a target database is
   created.
6. **No hidden data loss — PASS.** Corrupted sources, crash residue, and failed
   restore stages are retained. Only per-test operating-system temporary roots
   are removed by test teardown. No canonical source reset, clean, truncation,
   or fallback is used to manufacture recovery success.
7. **Repeatability — PASS.** The final Node recovery set passes in ten
   independent runs (60 test executions). The disposable PostgreSQL restore
   passes in three independent runs. The required final targeted gate is 7/7:
   six Node tests and one Python/PostgreSQL test.
8. **Regression — PASS for D04.** The full Python suite records 913 passed.
   Repository-wide Node discovery records 149 passed and the same single
   pre-existing `S04-TM004` stale manifest-hash failure. Structure, package
   boundaries, toolchain/lock checks, ten CI policy tests, strict UTF-8, and
   `git diff --check` pass. The existing `scripts/build/double_build.py` staged
   `scripts/` omission remains outside D04.
9. **Claim boundary — PASS.** D04 proves local SQLite and artifact fixtures and
   a disposable PostgreSQL logical backup/restore path. It does not claim
   production RPO/RTO, cross-region failover, object-store service recovery,
   continuous PITR, or disaster-recovery operations; those remain Y03 and
   later release responsibilities.

## Preserved limitations

- On Windows, `SIGKILL` is represented by an abrupt non-zero child termination;
  the tests prove process-death recovery, not storage-device power-loss
  durability beyond the host and SQLite guarantees.
- The artifact/SQLite restore helpers live in D04 test scope and are acceptance
  harnesses, not a shipped backup CLI or production recovery service.
- PostgreSQL recovery uses one disposable container and a logical custom dump;
  it does not qualify production physical backup, WAL archiving, or regional
  failover.
- The repository-wide Node residual is `S04-TM004`: expected manifest hash
  `456330ae...` versus actual `a0a0db29...`. D04 has no S04 write authority.
- `scripts/build/double_build.py` still omits `scripts/` from its staged source;
  D04 has no build integration write authority.
- Test-created `__pycache__` is ignored. Two cleanup command shapes were
  rejected before execution by the safety hook, and no destructive workaround
  was used.

## Decision

D04 satisfies its exact package contract. Crash and corruption fixtures recover
safely, verified backups restore into fresh staging targets, corrupt or raced
inputs fail closed, and no data loss is hidden by reset. The overall Foundry
objective remains active and `completion_ready=false`.
