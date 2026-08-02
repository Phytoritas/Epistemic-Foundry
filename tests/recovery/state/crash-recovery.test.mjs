import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import {
  SQLITE_STORE_MODE,
  openSQLiteStateStore,
} from "../../../packages/foundry-kernel/src/state/sqlite/sqlite-state-store.mjs";
import {
  ARTIFACT_STORE_MODE,
  openContentAddressedArtifactStore,
} from "../../../packages/foundry-kernel/src/artifacts/content-addressed-artifact-store.mjs";

const repositoryRoot = path.resolve(import.meta.dirname, "../../..");
const sqliteModuleUrl = pathToFileURL(
  path.join(
    repositoryRoot,
    "packages/foundry-kernel/src/state/sqlite/sqlite-state-store.mjs",
  ),
).href;
const artifactModuleUrl = pathToFileURL(
  path.join(
    repositoryRoot,
    "packages/foundry-kernel/src/artifacts/content-addressed-artifact-store.mjs",
  ),
).href;

const temporaryDirectory = (t, prefix) => {
  const directory = mkdtempSync(path.join(tmpdir(), prefix));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  return directory;
};

const runCrashingChild = (script, environment) => {
  const result = spawnSync(process.execPath, ["--input-type=module", "-e", script], {
    encoding: "utf8",
    env: { ...process.env, ...environment },
    timeout: 15_000,
    windowsHide: true,
  });
  assert.equal(result.error, undefined, result.error?.message);
  assert.match(result.stdout, /CRASH_POINT_REACHED/u);
  assert.notEqual(result.status, 0, "crash fixture exited cleanly instead of being terminated");
  return result;
};

test("crash_recovery_test: SQLite replays committed WAL after abrupt process death", (t) => {
  const directory = temporaryDirectory(t, "ef-d04-sqlite-committed-");
  const databasePath = path.join(directory, "state.db");
  const script = `
    import fs from "node:fs";
    import { openSQLiteStateStore } from ${JSON.stringify(sqliteModuleUrl)};
    const store = openSQLiteStateStore(process.env.EF_D04_DATABASE);
    store.createRevisionedRecord({
      recordType: "run",
      recordId: "committed-before-crash",
      value: { state: "SEALED" },
    });
    fs.writeSync(1, "CRASH_POINT_REACHED\\n");
    process.kill(process.pid, "SIGKILL");
  `;
  runCrashingChild(script, { EF_D04_DATABASE: databasePath });

  const recovered = openSQLiteStateStore(databasePath);
  try {
    assert.equal(recovered.mode, SQLITE_STORE_MODE.ACTIVE);
    assert.deepEqual(recovered.readRevisionedRecord("run", "committed-before-crash"), {
      recordType: "run",
      recordId: "committed-before-crash",
      revision: 0,
      value: { state: "SEALED" },
    });
    assert.deepEqual(recovered.checkIntegrity(), {
      details: ["ok"],
      mode: SQLITE_STORE_MODE.ACTIVE,
      ok: true,
    });
  } finally {
    recovered.close();
  }
});

test("crash_recovery_test: SQLite rolls back an interrupted transaction without reset", (t) => {
  const directory = temporaryDirectory(t, "ef-d04-sqlite-rollback-");
  const databasePath = path.join(directory, "state.db");
  const baseline = openSQLiteStateStore(databasePath);
  baseline.createRevisionedRecord({
    recordType: "run",
    recordId: "baseline",
    value: { state: "PRESERVE" },
  });
  baseline.close();

  const script = `
    import fs from "node:fs";
    import { openSQLiteStateStore } from ${JSON.stringify(sqliteModuleUrl)};
    const store = openSQLiteStateStore(process.env.EF_D04_DATABASE);
    store.transaction((tx) => {
      tx.compareAndSwapRevision({
        recordType: "run",
        recordId: "baseline",
        expectedRevision: 0,
        value: { state: "MUST_ROLL_BACK" },
      });
      tx.createRevisionedRecord({
        recordType: "run",
        recordId: "partial",
        value: { state: "MUST_NOT_EXIST" },
      });
      fs.writeSync(1, "CRASH_POINT_REACHED\\n");
      process.kill(process.pid, "SIGKILL");
    });
  `;
  runCrashingChild(script, { EF_D04_DATABASE: databasePath });

  const recovered = openSQLiteStateStore(databasePath);
  try {
    assert.deepEqual(recovered.readRevisionedRecord("run", "baseline"), {
      recordType: "run",
      recordId: "baseline",
      revision: 0,
      value: { state: "PRESERVE" },
    });
    assert.equal(recovered.readRevisionedRecord("run", "partial"), null);
    assert.equal(recovered.checkIntegrity().ok, true);
  } finally {
    recovered.close();
  }
});

test("crash_recovery_test: corrupted SQLite remains preserved and enters SAFE_MODE", (t) => {
  const directory = temporaryDirectory(t, "ef-d04-sqlite-corrupt-");
  const databasePath = path.join(directory, "state.db");
  const store = openSQLiteStateStore(databasePath);
  store.createRevisionedRecord({
    recordType: "run",
    recordId: "must-not-be-reset",
    value: { state: "PRESERVE_EVIDENCE" },
  });
  store.close();

  const corrupted = readFileSync(databasePath);
  Buffer.from("NOT-SQLITE-D04!!", "ascii").copy(corrupted, 0);
  writeFileSync(databasePath, corrupted);
  const before = createHash("sha256").update(corrupted).digest("hex");

  const denied = openSQLiteStateStore(databasePath);
  assert.equal(denied.mode, SQLITE_STORE_MODE.SAFE_MODE);
  assert.equal(denied.isClosed, true);
  assert.match(denied.safeModeReason.code, /^SQLITE_/u);
  assert.equal(createHash("sha256").update(readFileSync(databasePath)).digest("hex"), before);
});

test("crash_recovery_test: artifact crash residue stays quarantined from canonical state", (t) => {
  const directory = temporaryDirectory(t, "ef-d04-artifact-crash-");
  const artifactRoot = path.join(directory, "artifact-store");
  const script = `
    import fs from "node:fs";
    import path from "node:path";
    import { openContentAddressedArtifactStore } from ${JSON.stringify(artifactModuleUrl)};
    const store = openContentAddressedArtifactStore(process.env.EF_D04_ARTIFACT_ROOT);
    store.putArtifact(Buffer.from("committed artifact before crash"), {
      artifact: {
        artifactId: "ART-D04-crash",
        artifactType: "recovery_fixture",
        confidentiality: "internal",
        createdAt: "2026-07-28T00:00:00Z",
        createdBy: "ACT-D04-crash-child",
        encryption: { atRest: true, inTransit: true, keyRef: "local://d04" },
        inputArtifactIds: [], license: null, lineageEventIds: ["EVT-D04-crash"],
        mediaType: "application/octet-stream", provenanceManifestId: "PROV-D04-crash",
        retentionClass: "project",
      },
      receipt: {
        actionIntentId: null, createdAt: "2026-07-28T00:00:01Z",
        createdBy: { actorId: "ACT-D04-crash-child", actorType: "service" },
        receiptId: "AR-D04-crash", schemaRef: "d04.schema.json",
        validationResults: [{ check: "crash_fixture", details: "sealed", status: "PASS" }],
      },
    });
    const residue = path.join(
      process.env.EF_D04_ARTIFACT_ROOT,
      ".staging",
      ".stage-12345678-1234-4123-8123-123456789abc",
    );
    fs.mkdirSync(residue);
    fs.writeFileSync(path.join(residue, "uncommitted.bin"), "never canonical");
    fs.writeSync(1, "CRASH_POINT_REACHED\\n");
    process.kill(process.pid, "SIGKILL");
  `;
  runCrashingChild(script, { EF_D04_ARTIFACT_ROOT: artifactRoot });

  const residue = path.join(
    artifactRoot,
    ".staging",
    ".stage-12345678-1234-4123-8123-123456789abc",
  );
  assert.equal(existsSync(residue), true, "the recovery gate must not hide residue by reset");
  const recovered = openContentAddressedArtifactStore(artifactRoot);
  try {
    assert.equal(recovered.mode, ARTIFACT_STORE_MODE.ACTIVE);
    assert.deepEqual(recovered.readArtifact("ART-D04-crash"), Buffer.from("committed artifact before crash"));
    assert.deepEqual(recovered.enumerateArtifacts().map((item) => item.artifact_id), [
      "ART-D04-crash",
    ]);
    assert.equal(recovered.checkIntegrity().ok, true);
  } finally {
    recovered.close();
  }
});
