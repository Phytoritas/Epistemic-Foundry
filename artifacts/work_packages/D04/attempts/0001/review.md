# D04-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  tests/recovery/state (crash-recovery.test.mjs, backup-restore.test.mjs,
  recovery-fixtures.mjs, test_postgres_backup_restore.py). Reviewer: this
  seal-prep session, a distinct actor that did not author the fixtures. The
  author never approves its own work, so actor_independence HOLDS for this
  review; external actor-independent certification does NOT, and no such
  claim is made. D04 is risk_class=critical, so the gate was attacked on
  crash recovery, corruption preservation, and non-destructive restore
  rather than skimmed.
- Crash and corruption fixtures recover safely. A committed record is
  written and the child process is SIGKILLed; on reopen the SQLite store is
  ACTIVE, replays the committed WAL, reads back the sealed record, and its
  integrity check is ok. An interrupted transaction (a compare-and-swap plus
  an insert killed mid-flight) rolls back completely: the baseline record
  keeps its original value and the partial record does not exist. A SQLite
  header overwritten with non-SQLite bytes opens read-only SAFE_MODE with a
  SQLITE_* reason and the handle closed. Artifact crash residue under
  .staging survives a SIGKILL; on reopen the artifact store is ACTIVE,
  resolves the committed artifact, enumerates exactly it, and integrity is
  ok.
- No data loss hidden by reset. The corrupted SQLite file's sha256 is
  captured before open and asserted identical after SAFE_MODE entry, so the
  gate cannot mask corruption by silently re-initialising the file. The
  crash residue is asserted still present after recovery precisely so the
  recovery path cannot hide loss behind a reset. Restore never mutates its
  source: after a corrupt source enters SAFE_MODE, the backup and the
  corrupt source both keep their captured hashes. A restore is staged into a
  fresh sibling, its copied hash or full canonical inventory and (for
  SQLite) PRAGMA integrity_check are revalidated, and only then is the stage
  atomically renamed onto an absent target. A damaged backup (truncated, or
  a snapshot content file overwritten) fails closed with a hash or inventory
  mismatch and the target never exists; a validation-to-publication race
  injected through afterCopy fails closed with the target absent and the
  quarantined stage preserved.
- Backup and restore round-trip faithfully. The live node:sqlite WAL backup
  is bound to its SHA-256 and restores a point-in-time snapshot: the record
  present at snapshot time is read back and a record written after the
  snapshot is absent. The artifact snapshot is a sorted canonical sha256
  graph inventory with a source bundle hash; it excludes .staging and
  .mutation-lock residue, and the restored store resolves the receipt to the
  exact original bytes. The restored artifact tree does not contain the
  .mutation-lock directory.
- PostgreSQL fixture. A custom-format pg_dump is validated by a pg_restore
  TOC preflight and restored single-transaction into a fresh staging
  database in a disposable pinned container, with schema, function, owner,
  forced-RLS, data, and runtime-principal verification before the database
  is renamed; a corrupt archive is rejected before restore. It requires a
  local Docker daemon and runs under the full Python suite.
- Dependencies and checks: the gate only reads the sealed D02 SQLite state
  store (D02-0001 PASS) and D03 content-addressed artifact store (D03-0001
  PASS) and modifies none of them; it adds no new production dependency. The
  two required checks (crash_recovery_test 4/4, backup_restore_test 2/2),
  targeted 6/6, full Python 1261/1261, full Node 1253/1253 across 111 files,
  ruff lint and format, and git diff --check all pass with zero failures.
- Preserved limitations: Windows abrupt termination proves process-death
  recovery, not storage-device power-loss durability beyond host and SQLite
  guarantees; the helpers are acceptance fixtures, not a shipped backup CLI
  or production recovery service; and the PostgreSQL test qualifies a
  logical custom dump in one disposable container, not physical backup,
  PITR, cross-region recovery, or production RPO/RTO. Verdict: PASS on the
  exact D04 package contract.
