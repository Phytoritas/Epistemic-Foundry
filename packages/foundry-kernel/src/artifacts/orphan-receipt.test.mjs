import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  cpSync,
  linkSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  renameSync,
  rmSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { Worker } from "node:worker_threads";

import {
  ARTIFACT_STORE_MODE,
  ArtifactStoreError,
  openContentAddressedArtifactStore,
} from "./content-addressed-artifact-store.mjs";

const digestHex = (bytes) => createHash("sha256").update(bytes).digest("hex");
const indexKey = (kind, id) =>
  createHash("sha256").update(`${kind}-id\u0000${id}`, "utf8").digest("hex");

const metadata = ({
  artifact = {},
  artifactId = "ART-D03-receipt-fixture",
  receipt = {},
  receiptId = "AR-D03-receipt-fixture",
} = {}) => ({
  artifact: {
    artifactId,
    artifactType: "receipt_fixture",
    confidentiality: "restricted",
    createdAt: "2026-07-28T01:00:00Z",
    createdBy: "ACT-D03-artifact-author",
    encryption: { atRest: true, inTransit: true, keyRef: "local://receipt-key" },
    inputArtifactIds: ["ART-input-0001"],
    license: "fixture-only",
    lineageEventIds: ["EVT-D03-receipt"],
    mediaType: "application/json",
    provenanceManifestId: "PROV-D03-receipt",
    retentionClass: "regulated",
    ...artifact,
  },
  receipt: {
    actionIntentId: "INT-D03-test",
    createdAt: "2026-07-28T01:00:01Z",
    createdBy: { actorId: "ACT-D03-receipt", actorType: "service" },
    receiptId,
    schemaRef: "receipt-fixture.schema.json",
    validationResults: [
      { check: "json_schema", status: "PASS", details: "fixture schema pass" },
    ],
    ...receipt,
  },
});

const temporaryRoot = (t) => {
  const root = mkdtempSync(path.join(tmpdir(), "ef-d03-orphan-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return root;
};

const recordPath = (root, bytes) => {
  const hex = digestHex(bytes);
  return path.join(root, "sha256", hex.slice(0, 2), hex.slice(2));
};

const registrationPath = (root, bytes, artifactId) =>
  path.join(recordPath(root, bytes), "artifacts", indexKey("artifact", artifactId));

const manifestPath = (root, bytes, artifactId) =>
  path.join(registrationPath(root, bytes, artifactId), "artifact-manifest.json");

const receiptsPath = (root, bytes, artifactId) =>
  path.join(registrationPath(root, bytes, artifactId), "receipts");

const receiptPath = (root, bytes, artifactId, receiptId) =>
  path.join(receiptsPath(root, bytes, artifactId), `${indexKey("receipt", receiptId)}.json`);

const expectCode = (code) => (error) =>
  error instanceof ArtifactStoreError && error.code === code;

const prepareArtifact = (t, bytes = Buffer.from("orphan target", "utf8"), ids = {}) => {
  const root = temporaryRoot(t);
  const store = openContentAddressedArtifactStore(root);
  assert.equal(store.mode, ARTIFACT_STORE_MODE.ACTIVE);
  const artifactId = ids.artifactId ?? "ART-D03-receipt-fixture";
  const receiptId = ids.receiptId ?? "AR-D03-receipt-fixture";
  const result = store.putArtifact(bytes, metadata({ artifactId, receiptId }));
  return {
    artifactId,
    bytes,
    receiptId,
    result,
    root,
    store,
    record: recordPath(root, bytes),
    registration: registrationPath(root, bytes, artifactId),
  };
};

test("orphan_receipt_test: registrations without content fail closed", (t) => {
  const fixture = prepareArtifact(t);
  unlinkSync(path.join(fixture.record, "content.bin"));
  assert.throws(
    () => fixture.store.resolveReceipt(fixture.receiptId),
    expectCode("ARTIFACT_ORPHAN_RECEIPT"),
  );
  assert.equal(fixture.store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
});

test("orphan_receipt_test: receipts without manifest fail closed", (t) => {
  const fixture = prepareArtifact(t);
  unlinkSync(path.join(fixture.registration, "artifact-manifest.json"));
  const integrity = fixture.store.checkIntegrity();
  assert.equal(integrity.ok, false);
  assert.equal(integrity.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
  assert.equal(fixture.store.safeModeReason.code, "ARTIFACT_ORPHAN_RECEIPT");
});

test("orphan_receipt_test: bytes and manifest without receipt are incomplete", (t) => {
  const fixture = prepareArtifact(t);
  unlinkSync(receiptPath(fixture.root, fixture.bytes, fixture.artifactId, fixture.receiptId));
  assert.throws(
    () => fixture.store.readArtifact(fixture.artifactId),
    expectCode("ARTIFACT_RECORD_INCOMPLETE"),
  );
  assert.equal(fixture.store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
});

test("orphan_receipt_test: receipt pointing at another artifact cannot resolve", (t) => {
  const root = temporaryRoot(t);
  const store = openContentAddressedArtifactStore(root);
  const leftBytes = Buffer.from("left receipt bytes");
  const rightBytes = Buffer.from("right receipt bytes");
  const leftIds = { artifactId: "ART-left-receipt", receiptId: "AR-left-receipt" };
  const rightIds = { artifactId: "ART-right-receipt", receiptId: "AR-right-receipt" };
  store.putArtifact(leftBytes, metadata(leftIds));
  store.putArtifact(rightBytes, metadata(rightIds));
  writeFileSync(
    receiptPath(root, leftBytes, leftIds.artifactId, leftIds.receiptId),
    readFileSync(receiptPath(root, rightBytes, rightIds.artifactId, rightIds.receiptId)),
  );

  assert.throws(
    () => store.resolveReceipt(leftIds.receiptId),
    expectCode("ARTIFACT_RECEIPT_KEY_MISMATCH"),
  );
  assert.equal(store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
});

test("orphan_receipt_test: copied manifest cannot relabel addressed bytes", (t) => {
  const root = temporaryRoot(t);
  const store = openContentAddressedArtifactStore(root);
  const leftBytes = Buffer.from("left manifest bytes");
  const rightBytes = Buffer.from("right manifest bytes");
  const leftIds = { artifactId: "ART-left-manifest", receiptId: "AR-left-manifest" };
  const rightIds = { artifactId: "ART-right-manifest", receiptId: "AR-right-manifest" };
  store.putArtifact(leftBytes, metadata(leftIds));
  store.putArtifact(rightBytes, metadata(rightIds));
  writeFileSync(
    manifestPath(root, leftBytes, leftIds.artifactId),
    readFileSync(manifestPath(root, rightBytes, rightIds.artifactId)),
  );

  assert.throws(
    () => store.readManifest(leftIds.artifactId),
    expectCode("ARTIFACT_MANIFEST_KEY_MISMATCH"),
  );
  assert.equal(store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
});

test("orphan_receipt_test: uncommitted staging material is never canonical", (t) => {
  const root = temporaryRoot(t);
  const store = openContentAddressedArtifactStore(root);
  const stage = path.join(root, ".staging", ".stage-12345678-1234-4123-8123-123456789abc");
  mkdirSync(stage);
  writeFileSync(path.join(stage, "content.bin"), Buffer.from("uncommitted"));
  assert.deepEqual(store.enumerateArtifacts(), []);
  assert.deepEqual(store.checkIntegrity(), {
    artifactCount: 0,
    details: null,
    objectCount: 0,
    mode: ARTIFACT_STORE_MODE.ACTIVE,
    ok: true,
    receiptCount: 0,
  });
  assert.throws(
    () => store.readObject(`sha256:${"a".repeat(64)}`),
    expectCode("ARTIFACT_NOT_FOUND"),
  );
  assert.equal(store.mode, ARTIFACT_STORE_MODE.ACTIVE);
});

test("orphan_receipt_test: malformed or linked staging entry blocks open", (t) => {
  const firstRoot = temporaryRoot(t);
  let store = openContentAddressedArtifactStore(firstRoot);
  assert.equal(store.mode, ARTIFACT_STORE_MODE.ACTIVE);
  store.close();
  writeFileSync(path.join(firstRoot, ".staging", "unexpected"), "x", "utf8");
  store = openContentAddressedArtifactStore(firstRoot);
  assert.equal(store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
  assert.equal(store.safeModeReason.code, "ARTIFACT_STORE_STRUCTURE_INVALID");

  const secondRoot = temporaryRoot(t);
  store = openContentAddressedArtifactStore(secondRoot);
  store.close();
  const external = path.join(secondRoot, "external-stage");
  mkdirSync(external);
  const link = path.join(
    secondRoot,
    ".staging",
    ".stage-12345678-1234-4123-8123-123456789abc",
  );
  try {
    symlinkSync(external, link, process.platform === "win32" ? "junction" : "dir");
  } catch (error) {
    if (error instanceof Error && ["EPERM", "EACCES", "ENOTSUP"].includes(error.code)) {
      return;
    }
    throw error;
  }
  store = openContentAddressedArtifactStore(secondRoot);
  assert.equal(store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
  assert.equal(store.safeModeReason.code, "ARTIFACT_STORE_STRUCTURE_INVALID");
});

test("orphan_receipt_test: mutation scans unrelated corruption before publishing", (t) => {
  const fixture = prepareArtifact(t, Buffer.from("existing artifact"));
  unlinkSync(path.join(fixture.record, "content.bin"));
  assert.throws(
    () =>
      fixture.store.putArtifact(
        Buffer.from("new artifact"),
        metadata({ artifactId: "ART-new-after-orphan", receiptId: "AR-new-after-orphan" }),
      ),
    expectCode("ARTIFACT_ORPHAN_RECEIPT"),
  );
  assert.equal(fixture.store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
});

test("orphan_receipt_test: reopening a corrupt tree fails closed before read", (t) => {
  const fixture = prepareArtifact(t, Buffer.from("reopen orphan"));
  fixture.store.close();
  unlinkSync(path.join(fixture.record, "content.bin"));
  const reopened = openContentAddressedArtifactStore(fixture.root);
  assert.equal(reopened.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
  assert.equal(reopened.safeModeReason.code, "ARTIFACT_ORPHAN_RECEIPT");
  assert.throws(() => reopened.resolveReceipt(fixture.receiptId), expectCode("STORE_SAFE_MODE"));
});

test("orphan_receipt_test: unknown files at every canonical layer are rejected", (t) => {
  const objectFixture = prepareArtifact(t, Buffer.from("extra object entry"));
  writeFileSync(path.join(objectFixture.record, "shadow.bin"), "x", "utf8");
  assert.throws(
    () => objectFixture.store.readReceipt(objectFixture.receiptId),
    expectCode("ARTIFACT_RECORD_INCOMPLETE"),
  );

  const registrationFixture = prepareArtifact(t, Buffer.from("extra registration entry"));
  writeFileSync(path.join(registrationFixture.registration, "shadow.json"), "{}\n", "utf8");
  assert.throws(
    () => registrationFixture.store.readReceipt(registrationFixture.receiptId),
    expectCode("ARTIFACT_RECORD_INCOMPLETE"),
  );

  const receiptFixture = prepareArtifact(t, Buffer.from("extra receipt entry"));
  writeFileSync(
    path.join(receiptsPath(receiptFixture.root, receiptFixture.bytes, receiptFixture.artifactId), "shadow.json"),
    "{}\n",
    "utf8",
  );
  assert.throws(
    () => receiptFixture.store.readReceipt(receiptFixture.receiptId),
    expectCode("ARTIFACT_REGISTRATION_STRUCTURE_INVALID"),
  );
});

test("orphan_receipt_test: moved record cannot remain addressable under old digest", (t) => {
  const fixture = prepareArtifact(t, Buffer.from("moved record"));
  const destination = path.join(path.dirname(fixture.record), `${"f".repeat(62)}`);
  renameSync(fixture.record, destination);
  assert.throws(
    () => fixture.store.resolveReceipt(fixture.receiptId),
    expectCode("ARTIFACT_HASH_MISMATCH"),
  );
  assert.equal(fixture.store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
});

const runWorker = ({ bytes, metadataValue, moduleUrl, root }) =>
  new Promise((resolve, reject) => {
    const workerSource = `
      import { parentPort, workerData } from "node:worker_threads";
      import { openContentAddressedArtifactStore } from ${JSON.stringify(moduleUrl)};
      const store = openContentAddressedArtifactStore(workerData.root);
      try {
        const result = store.putArtifact(Buffer.from(workerData.bytes, "base64"), workerData.metadataValue);
        parentPort.postMessage({
          ok: true,
          status: result.status,
          objectStatus: result.objectStatus,
          artifactStatus: result.artifactStatus,
          receiptStatus: result.receiptStatus,
          artifactId: result.manifest.artifact_id,
          receiptId: result.receipt.receipt_id,
        });
      } catch (error) {
        parentPort.postMessage({ ok: false, code: error?.code, message: error?.message });
      }
    `;
    const worker = new Worker(workerSource, {
      eval: true,
      type: "module",
      workerData: {
        bytes: bytes.toString("base64"),
        metadataValue,
        root,
      },
    });
    worker.once("message", resolve);
    worker.once("error", reject);
    worker.once("exit", (code) => {
      if (code !== 0) reject(new Error(`worker exited ${code}`));
    });
  });

test("orphan_receipt_test: concurrent identical publishers converge", async (t) => {
  const root = temporaryRoot(t);
  const bytes = Buffer.from("concurrent identical artifact", "utf8");
  const moduleUrl = new URL("./content-addressed-artifact-store.mjs", import.meta.url).href;
  const fixture = metadata({ artifactId: "ART-concurrent", receiptId: "AR-concurrent" });
  const results = await Promise.all([
    runWorker({ bytes, metadataValue: fixture, moduleUrl, root }),
    runWorker({ bytes, metadataValue: fixture, moduleUrl, root }),
  ]);
  assert.equal(results.every((result) => result.ok), true, JSON.stringify(results));
  assert.deepEqual(
    results.map((result) => result.status).sort(),
    ["CREATED", "EXISTING"],
  );
  assert.equal(new Set(results.map((result) => result.artifactId)).size, 1);
  assert.equal(new Set(results.map((result) => result.receiptId)).size, 1);

  const store = openContentAddressedArtifactStore(root);
  assert.equal(store.mode, ARTIFACT_STORE_MODE.ACTIVE);
  assert.deepEqual(store.readArtifact("ART-concurrent"), bytes);
  assert.equal(store.checkIntegrity().artifactCount, 1);
  assert.equal(store.checkIntegrity().receiptCount, 1);
});

test("orphan_receipt_test: concurrent distinct registrations share one object", async (t) => {
  const root = temporaryRoot(t);
  const bytes = Buffer.from("concurrent shared content", "utf8");
  const moduleUrl = new URL("./content-addressed-artifact-store.mjs", import.meta.url).href;
  const results = await Promise.all([
    runWorker({
      bytes,
      metadataValue: metadata({ artifactId: "ART-concurrent-A", receiptId: "AR-concurrent-A" }),
      moduleUrl,
      root,
    }),
    runWorker({
      bytes,
      metadataValue: metadata({
        artifact: { createdBy: "ACT-concurrent-B", provenanceManifestId: "PROV-concurrent-B" },
        artifactId: "ART-concurrent-B",
        receiptId: "AR-concurrent-B",
      }),
      moduleUrl,
      root,
    }),
  ]);
  assert.equal(results.every((result) => result.ok), true, JSON.stringify(results));
  assert.equal(results.filter((result) => result.objectStatus === "CREATED").length, 1);
  assert.equal(results.filter((result) => result.objectStatus === "EXISTING").length, 1);
  assert.equal(results.every((result) => result.artifactStatus === "CREATED"), true);

  const store = openContentAddressedArtifactStore(root);
  assert.deepEqual(store.checkIntegrity(), {
    artifactCount: 2,
    details: null,
    objectCount: 1,
    mode: ARTIFACT_STORE_MODE.ACTIVE,
    ok: true,
    receiptCount: 2,
  });
});

test("orphan_receipt_test: concurrent readers tolerate transient staging and lock handoff", async (t) => {
  const root = temporaryRoot(t);
  const bytes = Buffer.from("reader writer overlap", "utf8");
  const moduleUrl = new URL("./content-addressed-artifact-store.mjs", import.meta.url).href;
  const initialStore = openContentAddressedArtifactStore(root);
  initialStore.putArtifact(
    bytes,
    metadata({ artifactId: "ART-reader-anchor", receiptId: "AR-reader-anchor" }),
  );
  initialStore.close();

  const writerSource = `
    import { parentPort, workerData } from "node:worker_threads";
    import { openContentAddressedArtifactStore } from ${JSON.stringify(moduleUrl)};
    const store = openContentAddressedArtifactStore(workerData.root);
    try {
      for (let index = 0; index < 20; index += 1) {
        const value = structuredClone(workerData.metadataValue);
        value.artifact.artifactId = \`ART-overlap-\${String(index).padStart(2, "0")}\`;
        value.artifact.provenanceManifestId = \`PROV-overlap-\${index}\`;
        value.receipt.receiptId = \`AR-overlap-\${String(index).padStart(2, "0")}\`;
        store.putArtifact(Buffer.from(workerData.bytes, "base64"), value);
      }
      parentPort.postMessage({ ok: true });
    } catch (error) {
      parentPort.postMessage({ ok: false, code: error?.code, message: error?.message });
    }
  `;
  const readerSource = `
    import { parentPort, workerData } from "node:worker_threads";
    import { openContentAddressedArtifactStore } from ${JSON.stringify(moduleUrl)};
    const store = openContentAddressedArtifactStore(workerData.root);
    try {
      for (let index = 0; index < 200; index += 1) {
        const integrity = store.checkIntegrity();
        if (!integrity.ok) throw new Error(\`integrity failed: \${JSON.stringify(integrity)}\`);
        const bytes = store.readArtifact("ART-reader-anchor");
        if (bytes.toString("base64") !== workerData.bytes) throw new Error("anchor bytes changed");
      }
      parentPort.postMessage({ ok: true });
    } catch (error) {
      parentPort.postMessage({
        ok: false,
        code: error?.code,
        message: error?.message,
        reason: store.safeModeReason,
      });
    }
  `;
  const run = (source, workerData) =>
    new Promise((resolve, reject) => {
      const worker = new Worker(source, { eval: true, type: "module", workerData });
      worker.once("message", resolve);
      worker.once("error", reject);
      worker.once("exit", (code) => {
        if (code !== 0) reject(new Error(`worker exited ${code}`));
      });
    });
  const encoded = bytes.toString("base64");
  const results = await Promise.all([
    run(writerSource, { bytes: encoded, metadataValue: metadata(), root }),
    run(readerSource, { bytes: encoded, root }),
  ]);
  assert.equal(results.every((result) => result.ok), true, JSON.stringify(results));

  const reopened = openContentAddressedArtifactStore(root);
  assert.equal(reopened.mode, ARTIFACT_STORE_MODE.ACTIVE);
  assert.deepEqual(reopened.checkIntegrity(), {
    artifactCount: 21,
    details: null,
    objectCount: 1,
    mode: ARTIFACT_STORE_MODE.ACTIVE,
    ok: true,
    receiptCount: 21,
  });
});

test(
  "orphan_receipt_test: disappearing Windows mutation lock EPERM is a bounded handoff",
  { skip: process.platform !== "win32" },
  async (t) => {
    const root = temporaryRoot(t);
    const store = openContentAddressedArtifactStore(root);
    store.close();
    mkdirSync(path.join(root, ".staging", ".mutation-lock"));
    const moduleUrl = new URL("./content-addressed-artifact-store.mjs", import.meta.url).href;
    const workerSource = `
      import fs from "node:fs";
      import { syncBuiltinESMExports } from "node:module";
      import path from "node:path";
      import { parentPort, workerData } from "node:worker_threads";
      const original = fs.readdirSync;
      let injected = 0;
      fs.readdirSync = (candidate, ...args) => {
        if (path.basename(String(candidate)) === ".mutation-lock" && injected === 0) {
          injected += 1;
          fs.rmdirSync(candidate);
          const error = new Error("injected Windows handoff");
          error.code = "EPERM";
          throw error;
        }
        return original(candidate, ...args);
      };
      syncBuiltinESMExports();
      const { openContentAddressedArtifactStore } = await import(workerData.moduleUrl);
      const opened = openContentAddressedArtifactStore(workerData.root);
      parentPort.postMessage({ injected, mode: opened.mode, reason: opened.safeModeReason });
    `;
    const result = await new Promise((resolve, reject) => {
      const worker = new Worker(workerSource, {
        eval: true,
        type: "module",
        workerData: { moduleUrl, root },
      });
      worker.once("message", resolve);
      worker.once("error", reject);
      worker.once("exit", (code) => {
        if (code !== 0) reject(new Error(`worker exited ${code}`));
      });
    });
    assert.deepEqual(result, { injected: 1, mode: ARTIFACT_STORE_MODE.ACTIVE, reason: null });
  },
);

test(
  "orphan_receipt_test: persistent Windows mutation lock EPERM fails closed",
  { skip: process.platform !== "win32" },
  async (t) => {
    const root = temporaryRoot(t);
    const store = openContentAddressedArtifactStore(root);
    store.close();
    mkdirSync(path.join(root, ".staging", ".mutation-lock"));
    const moduleUrl = new URL("./content-addressed-artifact-store.mjs", import.meta.url).href;
    const workerSource = `
      import fs from "node:fs";
      import { syncBuiltinESMExports } from "node:module";
      import path from "node:path";
      import { parentPort, workerData } from "node:worker_threads";
      const original = fs.readdirSync;
      let injected = 0;
      fs.readdirSync = (candidate, ...args) => {
        if (path.basename(String(candidate)) === ".mutation-lock") {
          injected += 1;
          const error = new Error("injected persistent Windows denial");
          error.code = "EPERM";
          throw error;
        }
        return original(candidate, ...args);
      };
      syncBuiltinESMExports();
      const { openContentAddressedArtifactStore } = await import(workerData.moduleUrl);
      const opened = openContentAddressedArtifactStore(workerData.root);
      parentPort.postMessage({ injected, mode: opened.mode, reason: opened.safeModeReason });
    `;
    const result = await new Promise((resolve, reject) => {
      const worker = new Worker(workerSource, {
        eval: true,
        type: "module",
        workerData: { moduleUrl, root },
      });
      worker.once("message", resolve);
      worker.once("error", reject);
      worker.once("exit", (code) => {
        if (code !== 0) reject(new Error(`worker exited ${code}`));
      });
    });
    assert.equal(result.injected, 9);
    assert.equal(result.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
    assert.deepEqual(result.reason, {
      code: "ARTIFACT_STORE_STRUCTURE_INVALID",
      details: { cause: "EPERM" },
    });
  },
);

test("orphan_receipt_test: complete record copied under wrong address is rejected", (t) => {
  const fixture = prepareArtifact(t, Buffer.from("copy target"));
  const wrongHex = `00${"b".repeat(62)}`;
  const wrong = path.join(fixture.root, "sha256", wrongHex.slice(0, 2), wrongHex.slice(2));
  mkdirSync(path.dirname(wrong), { recursive: true });
  cpSync(fixture.record, wrong, { recursive: true });
  const integrity = fixture.store.checkIntegrity();
  assert.equal(integrity.ok, false);
  assert.equal(integrity.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
  assert.equal(fixture.store.safeModeReason.code, "ARTIFACT_HASH_MISMATCH");
});

test("orphan_receipt_test: hard-linked manifest and receipt are rejected", (t) => {
  const manifestFixture = prepareArtifact(t, Buffer.from("manifest hardlink"));
  const manifest = manifestPath(
    manifestFixture.root,
    manifestFixture.bytes,
    manifestFixture.artifactId,
  );
  const externalManifest = `${manifestFixture.root}-external-manifest.json`;
  t.after(() => rmSync(externalManifest, { force: true }));
  renameSync(manifest, externalManifest);
  linkSync(externalManifest, manifest);
  assert.throws(
    () => manifestFixture.store.readManifest(manifestFixture.artifactId),
    expectCode("ARTIFACT_FILE_IDENTITY_INVALID"),
  );

  const receiptFixture = prepareArtifact(t, Buffer.from("receipt hardlink"));
  const receipt = receiptPath(
    receiptFixture.root,
    receiptFixture.bytes,
    receiptFixture.artifactId,
    receiptFixture.receiptId,
  );
  const externalReceipt = `${receiptFixture.root}-external-receipt.json`;
  t.after(() => rmSync(externalReceipt, { force: true }));
  renameSync(receipt, externalReceipt);
  linkSync(externalReceipt, receipt);
  assert.throws(
    () => receiptFixture.store.readReceipt(receiptFixture.receiptId),
    expectCode("ARTIFACT_FILE_IDENTITY_INVALID"),
  );
});

test("orphan_receipt_test: same artifact may retain multiple resolving receipts", (t) => {
  const fixture = prepareArtifact(t, Buffer.from("multiple receipt persistence"), {
    artifactId: "ART-multi-receipt",
    receiptId: "AR-multi-receipt-1",
  });
  const firstManifest = fixture.result.manifest;
  const second = fixture.store.putArtifact(
    fixture.bytes,
    metadata({
      artifact: {
        artifactId: firstManifest.artifact_id,
        artifactType: firstManifest.artifact_type,
        confidentiality: firstManifest.confidentiality,
        createdAt: firstManifest.created_at,
        createdBy: firstManifest.created_by,
        encryption: {
          atRest: firstManifest.encryption.at_rest,
          inTransit: firstManifest.encryption.in_transit,
          keyRef: firstManifest.encryption.key_ref,
        },
        inputArtifactIds: firstManifest.input_artifact_ids,
        license: firstManifest.license,
        lineageEventIds: firstManifest.lineage_event_ids,
        mediaType: firstManifest.media_type,
        provenanceManifestId: firstManifest.provenance_manifest_id,
        retentionClass: firstManifest.retention_class,
      },
      artifactId: "ART-multi-receipt",
      receipt: {
        createdAt: "2026-07-28T02:00:00Z",
        createdBy: { actorId: "ACT-independent-receipt", actorType: "agent" },
      },
      receiptId: "AR-multi-receipt-2",
    }),
  );
  assert.equal(second.artifactStatus, "EXISTING");
  assert.equal(second.receiptStatus, "CREATED");
  fixture.store.close();

  const reopened = openContentAddressedArtifactStore(fixture.root);
  assert.equal(reopened.mode, ARTIFACT_STORE_MODE.ACTIVE);
  assert.deepEqual(
    reopened.enumerateReceipts().map((entry) => entry.receipt_id),
    ["AR-multi-receipt-1", "AR-multi-receipt-2"],
  );
  assert.deepEqual(reopened.resolveReceipt("AR-multi-receipt-1").bytes, fixture.bytes);
  assert.deepEqual(reopened.resolveReceipt("AR-multi-receipt-2").bytes, fixture.bytes);
});
