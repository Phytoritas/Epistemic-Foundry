import assert from "node:assert/strict";
import {
  copyFileSync,
  cpSync,
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  truncateSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
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
  validateArtifactSnapshot,
} from "./recovery-fixtures.mjs";

const temporaryDirectory = (t, prefix) => {
  const directory = mkdtempSync(path.join(tmpdir(), prefix));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  return directory;
};

test("backup_restore_test: live SQLite WAL backup restores one verified snapshot", async (t) => {
  const directory = temporaryDirectory(t, "ef-d04-sqlite-backup-");
  const sourcePath = path.join(directory, "source.db");
  const backupPath = path.join(directory, "snapshot.db");
  const restoredPath = path.join(directory, "restored.db");
  const source = openSQLiteStateStore(sourcePath);
  source.createRevisionedRecord({
    recordType: "run",
    recordId: "in-snapshot",
    value: { state: "SNAPSHOT" },
  });
  assert.equal(existsSync(`${sourcePath}-wal`), true);

  const backupConnection = new DatabaseSync(sourcePath, { readOnly: true });
  try {
    const pages = await backup(backupConnection, backupPath);
    assert.ok(pages > 0);
  } finally {
    backupConnection.close();
  }
  const backupHash = sha256File(backupPath);
  source.createRevisionedRecord({
    recordType: "run",
    recordId: "after-snapshot",
    value: { state: "MUST_NOT_APPEAR" },
  });
  source.close();

  const corruptedSource = readFileSync(sourcePath);
  Buffer.from("NOT-SQLITE-D04!!", "ascii").copy(corruptedSource, 0);
  writeFileSync(sourcePath, corruptedSource);
  const corruptedHash = sha256File(sourcePath);
  const denied = openSQLiteStateStore(sourcePath);
  assert.equal(denied.mode, SQLITE_STORE_MODE.SAFE_MODE);
  assert.equal(sha256File(sourcePath), corruptedHash, "source corruption was hidden by reset");

  restoreSQLiteBackup(backupPath, restoredPath, backupHash);
  const restored = openSQLiteStateStore(restoredPath);
  try {
    assert.equal(restored.mode, SQLITE_STORE_MODE.ACTIVE);
    assert.deepEqual(restored.readRevisionedRecord("run", "in-snapshot"), {
      recordType: "run",
      recordId: "in-snapshot",
      revision: 0,
      value: { state: "SNAPSHOT" },
    });
    assert.equal(restored.readRevisionedRecord("run", "after-snapshot"), null);
    assert.equal(restored.checkIntegrity().ok, true);
  } finally {
    restored.close();
  }
  assert.equal(sha256File(backupPath), backupHash);
  assert.equal(sha256File(sourcePath), corruptedHash);

  const damagedBackup = path.join(directory, "damaged.db");
  const rejectedTarget = path.join(directory, "must-not-exist.db");
  copyFileSync(backupPath, damagedBackup);
  truncateSync(damagedBackup, Math.max(1, readFileSync(damagedBackup).length - 17));
  assert.throws(
    () => restoreSQLiteBackup(damagedBackup, rejectedTarget, backupHash),
    /SQLite backup hash mismatch/u,
  );
  assert.equal(existsSync(rejectedTarget), false);

  const racedTarget = path.join(directory, "raced-restore.db");
  let quarantinedSQLiteStage = null;
  assert.throws(
    () =>
      restoreSQLiteBackup(backupPath, racedTarget, backupHash, {
        afterCopy(stagePath) {
          quarantinedSQLiteStage = stagePath;
          writeFileSync(stagePath, "changed between validation and publish");
        },
      }),
    /SQLite staged restore hash mismatch/u,
  );
  assert.equal(existsSync(racedTarget), false);
  assert.equal(existsSync(quarantinedSQLiteStage), true);
  assert.equal(sha256File(backupPath), backupHash);
});

test("backup_restore_test: artifact snapshot excludes crash residue and restores exact graph", (t) => {
  const directory = temporaryDirectory(t, "ef-d04-artifact-backup-");
  const sourceRoot = path.join(directory, "source");
  const snapshotRoot = path.join(directory, "snapshot");
  const restoredRoot = path.join(directory, "restored");
  const source = openContentAddressedArtifactStore(sourceRoot);
  const bytes = Buffer.from("immutable artifact snapshot\u0000with exact bytes", "utf8");
  const result = source.putArtifact(bytes, artifactMetadata());

  const residue = path.join(
    sourceRoot,
    ".staging",
    ".stage-12345678-1234-4123-8123-123456789abc",
  );
  mkdirSync(residue);
  writeFileSync(path.join(residue, "uncommitted.bin"), "never back up");
  mkdirSync(path.join(sourceRoot, ".staging", ".mutation-lock"));
  assert.equal(source.checkIntegrity().ok, true);

  const manifest = createArtifactSnapshot(sourceRoot, snapshotRoot);
  assert.equal(manifest.files.some((entry) => entry.path.includes(".staging")), false);
  assert.deepEqual(validateArtifactSnapshot(snapshotRoot), manifest);
  source.close();

  const digestHex = result.manifest.content_hash.slice("sha256:".length);
  const sourceContent = path.join(
    sourceRoot,
    "sha256",
    digestHex.slice(0, 2),
    digestHex.slice(2),
    "content.bin",
  );
  writeFileSync(sourceContent, "corrupted primary bytes");
  const corruptedSourceHash = sha256File(sourceContent);
  const denied = openContentAddressedArtifactStore(sourceRoot);
  assert.equal(denied.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
  assert.equal(sha256File(sourceContent), corruptedSourceHash, "primary corruption was reset");

  restoreArtifactSnapshot(snapshotRoot, restoredRoot);
  const restored = openContentAddressedArtifactStore(restoredRoot);
  try {
    assert.equal(restored.mode, ARTIFACT_STORE_MODE.ACTIVE);
    const resolved = restored.resolveReceipt("AR-D04-backup-fixture");
    assert.deepEqual(resolved.bytes, bytes);
    assert.equal(resolved.manifest.artifact_id, "ART-D04-backup-fixture");
    assert.equal(restored.checkIntegrity().ok, true);
  } finally {
    restored.close();
  }
  assert.equal(existsSync(path.join(restoredRoot, ".staging", ".mutation-lock")), false);
  assert.equal(sha256File(sourceContent), corruptedSourceHash);

  const damagedSnapshot = path.join(directory, "damaged-snapshot");
  const rejectedTarget = path.join(directory, "must-not-exist");
  cpSync(snapshotRoot, damagedSnapshot, { recursive: true, errorOnExist: true });
  const backedUpContent = path.join(
    damagedSnapshot,
    "sha256",
    digestHex.slice(0, 2),
    digestHex.slice(2),
    "content.bin",
  );
  writeFileSync(backedUpContent, "damaged snapshot bytes");
  assert.throws(
    () => restoreArtifactSnapshot(damagedSnapshot, rejectedTarget),
    /snapshot file inventory mismatch/u,
  );
  assert.equal(existsSync(rejectedTarget), false);

  const racedTarget = path.join(directory, "raced-target");
  let quarantinedArtifactStage = null;
  assert.throws(
    () =>
      restoreArtifactSnapshot(snapshotRoot, racedTarget, {
        afterCopy(stageRoot) {
          quarantinedArtifactStage = stageRoot;
          writeFileSync(
            path.join(
              stageRoot,
              "sha256",
              digestHex.slice(0, 2),
              digestHex.slice(2),
              "content.bin",
            ),
            "changed between validation and publish",
          );
        },
      }),
    /staged restore file inventory mismatch/u,
  );
  assert.equal(existsSync(racedTarget), false);
  assert.equal(existsSync(quarantinedArtifactStage), true);
  assert.deepEqual(validateArtifactSnapshot(snapshotRoot), manifest);
});
