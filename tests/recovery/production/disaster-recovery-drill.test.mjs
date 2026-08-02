// disaster_recovery_drill: an honest, end-to-end production disaster recovery
// drill over the two canonical stores (SQLite state store + content-addressed
// artifact store). It executes the documented RB-Y03-DR-RESTORE runbook:
// backup -> continue writing -> disaster (corruption) -> hash-checked restore
// -> verify. It measures RPO/RTO and enforces the runbook's documented budgets.
//
// Nothing is faked or silently reset: post-backup writes are asserted LOST
// (bounded expected loss within RPO), the corrupt primary is asserted PRESERVED
// as evidence, and a tampered backup is asserted to REFUSE restore. The drill
// runs fully in-process on the real kernel stores; it needs no external service.

import assert from "node:assert/strict";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { performance } from "node:perf_hooks";
import test from "node:test";
import { backup, DatabaseSync } from "node:sqlite";

import {
  SQLITE_STORE_MODE,
  openSQLiteStateStore,
} from "../../../packages/foundry-kernel/src/state/sqlite/sqlite-state-store.mjs";
import {
  ARTIFACT_STORE_MODE,
  openContentAddressedArtifactStore,
} from "../../../packages/foundry-kernel/src/artifacts/content-addressed-artifact-store.mjs";
import {
  artifactMetadata,
  createArtifactSnapshot,
  restoreArtifactSnapshot,
  restoreSQLiteBackup,
  sha256File,
} from "../state/recovery-fixtures.mjs";
import { lintRunbookDirectory, parseDurationToMs } from "./runbook-lint.mjs";

const repositoryRoot = path.resolve(import.meta.dirname, "../../..");
const runbookDirectory = path.join(repositoryRoot, "ops", "runbooks");

const temporaryDirectory = (t, prefix) => {
  const directory = mkdtempSync(path.join(tmpdir(), prefix));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  return directory;
};

// Return the on-disk path of the first artifact payload under a store root, so
// the drill can corrupt a real primary payload directly on disk.
const firstArtifactPayload = (root) => {
  const shaRoot = path.join(root, "sha256");
  for (const prefix of readdirSync(shaRoot).sort()) {
    const prefixDir = path.join(shaRoot, prefix);
    if (!statSync(prefixDir).isDirectory()) continue;
    for (const rest of readdirSync(prefixDir).sort()) {
      const contentPath = path.join(prefixDir, rest, "content.bin");
      if (existsSync(contentPath)) return contentPath;
    }
  }
  throw new Error("no artifact payload found under primary store");
};

// Production-representative pre-backup state: records that MUST survive a
// disaster, plus artifacts that MUST restore byte-exact.
const PRE_BACKUP_RECORDS = [
  { recordType: "run", recordId: "run-alpha", value: { state: "SEALED" } },
  { recordType: "run", recordId: "run-beta", value: { state: "SEALED" } },
  { recordType: "ledger", recordId: "ledger-1", value: { revision: 7 } },
];
const PRE_BACKUP_ARTIFACTS = [
  { artifactId: "ART-Y03-dr-1", receiptId: "AR-Y03-dr-1", bytes: Buffer.from("dr artifact one exact", "utf8") },
  { artifactId: "ART-Y03-dr-2", receiptId: "AR-Y03-dr-2", bytes: Buffer.from("dr artifact two payload", "utf8") },
];

test("disaster_recovery_drill: coordinated backup recovers both stores with no hidden loss", async (t) => {
  // Documented objectives from the runbook are the budgets the drill enforces.
  const runbooks = lintRunbookDirectory(runbookDirectory);
  const drRunbook = runbooks.get("disaster-recovery.md");
  assert.ok(drRunbook, "RB-Y03-DR-RESTORE runbook must be present and lint-clean");
  const rpoBudgetMs = parseDurationToMs(drRunbook.metadata.rpo);
  const rtoBudgetMs = parseDurationToMs(drRunbook.metadata.rto);
  assert.ok(rpoBudgetMs > 0 && rtoBudgetMs > 0);

  const directory = temporaryDirectory(t, "ef-y03-dr-drill-");
  const primaryDbPath = path.join(directory, "primary-state.db");
  const primaryArtifactRoot = path.join(directory, "primary-artifacts");
  const backupDbPath = path.join(directory, "backup", "state.db");
  const snapshotRoot = path.join(directory, "backup", "artifact-snapshot");
  const recoveredDbPath = path.join(directory, "recovery", "state.db");
  const recoveredArtifactRoot = path.join(directory, "recovery", "artifacts");
  mkdirSync(path.join(directory, "backup"), { recursive: true });
  mkdirSync(path.join(directory, "recovery"), { recursive: true });

  // --- Seed production-representative primary state. ------------------------
  const primaryState = openSQLiteStateStore(primaryDbPath);
  for (const record of PRE_BACKUP_RECORDS) primaryState.createRevisionedRecord(record);
  const primaryArtifacts = openContentAddressedArtifactStore(primaryArtifactRoot);
  for (const item of PRE_BACKUP_ARTIFACTS) {
    primaryArtifacts.putArtifact(
      item.bytes,
      artifactMetadata({ artifactId: item.artifactId, receiptId: item.receiptId }),
    );
  }
  assert.equal(primaryState.checkIntegrity().ok, true);
  assert.equal(primaryArtifacts.checkIntegrity().ok, true);

  // --- Backup cycle (RB-Y03-BACKUP): this defines the recovery point. -------
  const backupConnection = new DatabaseSync(primaryDbPath, { readOnly: true });
  try {
    const pages = await backup(backupConnection, backupDbPath);
    assert.ok(pages > 0, "SQLite online backup produced pages");
  } finally {
    backupConnection.close();
  }
  const backupDigest = sha256File(backupDbPath);
  primaryArtifacts.close();
  createArtifactSnapshot(primaryArtifactRoot, snapshotRoot);
  const backupCompletedAt = Date.now();

  // --- Post-backup writes: acceptable loss bounded by RPO (NOT hidden). -----
  primaryState.createRevisionedRecord({
    recordType: "run",
    recordId: "run-post-backup",
    value: { state: "AFTER_BACKUP" },
  });
  primaryState.close();
  const reopened = openContentAddressedArtifactStore(primaryArtifactRoot);
  reopened.putArtifact(
    Buffer.from("artifact created after the backup", "utf8"),
    artifactMetadata({ artifactId: "ART-Y03-dr-post", receiptId: "AR-Y03-dr-post" }),
  );
  reopened.close();

  // --- Disaster: corrupt both primaries. -----------------------------------
  const disasterAt = Date.now();
  const corruptedDb = readFileSync(primaryDbPath);
  Buffer.from("NOT-SQLITE-Y03!!", "ascii").copy(corruptedDb, 0);
  writeFileSync(primaryDbPath, corruptedDb);
  const corruptDbDigest = sha256File(primaryDbPath);

  const artifactPayloadPath = firstArtifactPayload(primaryArtifactRoot);
  writeFileSync(artifactPayloadPath, "corrupted primary artifact bytes");
  const corruptArtifactDigest = sha256File(artifactPayloadPath);

  // The corrupt primaries must open in SAFE_MODE, preserving evidence.
  const deniedState = openSQLiteStateStore(primaryDbPath);
  assert.equal(deniedState.mode, SQLITE_STORE_MODE.SAFE_MODE, "disaster must be detected, not reset");
  const deniedArtifacts = openContentAddressedArtifactStore(primaryArtifactRoot);
  assert.equal(deniedArtifacts.mode, ARTIFACT_STORE_MODE.SAFE_MODE, "artifact disaster detected");
  assert.equal(sha256File(primaryDbPath), corruptDbDigest, "corrupt state preserved as evidence");
  assert.equal(sha256File(artifactPayloadPath), corruptArtifactDigest, "corrupt artifact preserved");

  // --- Restore (RB-Y03-DR-RESTORE): measure RTO across restore + verify. ---
  const rtoStart = performance.now();
  restoreSQLiteBackup(backupDbPath, recoveredDbPath, backupDigest);
  restoreArtifactSnapshot(snapshotRoot, recoveredArtifactRoot);

  const recoveredState = openSQLiteStateStore(recoveredDbPath);
  const recoveredArtifacts = openContentAddressedArtifactStore(recoveredArtifactRoot);
  try {
    // Recovered stores are healthy.
    assert.equal(recoveredState.mode, SQLITE_STORE_MODE.ACTIVE);
    assert.equal(recoveredArtifacts.mode, ARTIFACT_STORE_MODE.ACTIVE);
    assert.equal(recoveredState.checkIntegrity().ok, true);
    assert.equal(recoveredArtifacts.checkIntegrity().ok, true);

    // Every pre-backup record survives byte-exact.
    for (const record of PRE_BACKUP_RECORDS) {
      assert.deepEqual(recoveredState.readRevisionedRecord(record.recordType, record.recordId), {
        recordType: record.recordType,
        recordId: record.recordId,
        revision: 0,
        value: record.value,
      });
    }
    // Every pre-backup artifact restores byte-exact.
    for (const item of PRE_BACKUP_ARTIFACTS) {
      const resolved = recoveredArtifacts.resolveReceipt(item.receiptId);
      assert.deepEqual(resolved.bytes, item.bytes);
      assert.equal(resolved.manifest.artifact_id, item.artifactId);
    }

    // Honest loss accounting: post-backup writes are ABSENT (bounded by RPO).
    assert.equal(recoveredState.readRevisionedRecord("run", "run-post-backup"), null);
    const recoveredIds = recoveredArtifacts
      .enumerateArtifacts()
      .map((entry) => entry.artifact_id)
      .sort();
    assert.deepEqual(recoveredIds, ["ART-Y03-dr-1", "ART-Y03-dr-2"]);
  } finally {
    recoveredState.close();
    recoveredArtifacts.close();
  }
  const rtoMs = performance.now() - rtoStart;

  // --- Measured objectives are within the documented budgets. --------------
  const rpoWindowMs = disasterAt - backupCompletedAt; // max data-loss window
  assert.ok(rpoWindowMs >= 0);
  assert.ok(
    rpoWindowMs <= rpoBudgetMs,
    `measured RPO window ${rpoWindowMs}ms exceeds documented budget ${rpoBudgetMs}ms`,
  );
  assert.ok(
    rtoMs <= rtoBudgetMs,
    `measured RTO ${rtoMs.toFixed(3)}ms exceeds documented budget ${rtoBudgetMs}ms`,
  );

  // Corrupt primaries remain preserved after a successful recovery.
  assert.equal(sha256File(primaryDbPath), corruptDbDigest);
  assert.equal(sha256File(artifactPayloadPath), corruptArtifactDigest);
});

test("disaster_recovery_drill: a tampered backup refuses restore and publishes nothing", async (t) => {
  const directory = temporaryDirectory(t, "ef-y03-dr-tamper-");
  const primaryDbPath = path.join(directory, "primary.db");
  const backupDbPath = path.join(directory, "backup.db");
  const rejectedTarget = path.join(directory, "must-not-exist.db");

  const primary = openSQLiteStateStore(primaryDbPath);
  primary.createRevisionedRecord({ recordType: "run", recordId: "seed", value: { state: "SEALED" } });
  const connection = new DatabaseSync(primaryDbPath, { readOnly: true });
  try {
    await backup(connection, backupDbPath);
  } finally {
    connection.close();
  }
  primary.close();
  const trueDigest = sha256File(backupDbPath);

  // Tamper the backup after the digest was recorded.
  const tampered = readFileSync(backupDbPath);
  tampered[tampered.length - 1] ^= 0xff;
  writeFileSync(backupDbPath, tampered);

  assert.throws(
    () => restoreSQLiteBackup(backupDbPath, rejectedTarget, trueDigest),
    /SQLite backup hash mismatch/u,
    "a tampered backup must not restore",
  );
  assert.equal(existsSync(rejectedTarget), false, "no unverified restore is published");
});
