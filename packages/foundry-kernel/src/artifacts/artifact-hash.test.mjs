import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  linkSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  ARTIFACT_STORE_MODE,
  ArtifactStoreError,
  openContentAddressedArtifactStore,
} from "./content-addressed-artifact-store.mjs";

const digestHex = (bytes) => createHash("sha256").update(bytes).digest("hex");
const digest = (bytes) => `sha256:${digestHex(bytes)}`;
const indexKey = (kind, id) =>
  createHash("sha256").update(`${kind}-id\u0000${id}`, "utf8").digest("hex");

const canonicalJson = (value) => {
  if (value === null) return "null";
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
    .join(",")}}`;
};

const metadata = ({
  artifact = {},
  artifactId = "ART-D03-fixture-0001",
  receipt = {},
  receiptId = "AR-D03-fixture-0001",
} = {}) => ({
  artifact: {
    artifactId,
    artifactType: "binary_fixture",
    confidentiality: "internal",
    createdAt: "2026-07-28T00:00:00Z",
    createdBy: "ACT-D03-artifact-author",
    encryption: { atRest: true, inTransit: true, keyRef: "local://test-key" },
    inputArtifactIds: [],
    license: null,
    lineageEventIds: ["EVT-D03-test"],
    mediaType: "application/octet-stream",
    provenanceManifestId: "PROV-D03-test",
    retentionClass: "project",
    ...artifact,
  },
  receipt: {
    actionIntentId: null,
    createdAt: "2026-07-28T00:00:01Z",
    createdBy: { actorId: "ACT-D03-receipt-writer", actorType: "service" },
    receiptId,
    schemaRef: "fixture.schema.json",
    validationResults: [
      { check: "fixture_contract", status: "PASS", details: "test fixture accepted" },
    ],
    ...receipt,
  },
});

const temporaryRoot = (t, name = "ef-d03-") => {
  const root = mkdtempSync(path.join(tmpdir(), name));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return root;
};

const activeStore = (t) => {
  const root = temporaryRoot(t);
  const store = openContentAddressedArtifactStore(root);
  assert.equal(store.mode, ARTIFACT_STORE_MODE.ACTIVE);
  assert.equal(store.isClosed, false);
  return { root, store };
};

const recordPath = (root, bytes) => {
  const hex = digestHex(bytes);
  return path.join(root, "sha256", hex.slice(0, 2), hex.slice(2));
};

const registrationPath = (root, bytes, artifactId) =>
  path.join(recordPath(root, bytes), "artifacts", indexKey("artifact", artifactId));

const manifestPath = (root, bytes, artifactId) =>
  path.join(registrationPath(root, bytes, artifactId), "artifact-manifest.json");

const receiptPath = (root, bytes, artifactId, receiptId) =>
  path.join(
    registrationPath(root, bytes, artifactId),
    "receipts",
    `${indexKey("receipt", receiptId)}.json`,
  );

const expectCode = (code) => (error) =>
  error instanceof ArtifactStoreError && error.code === code;

test("artifact_hash_test: exact bytes address an opaque artifact and resolving receipt", (t) => {
  const { root, store } = activeStore(t);
  const source = Buffer.from([0x00, 0x01, 0x7f, 0x80, 0xff, 0x0a]);
  const original = Buffer.from(source);
  const ids = { artifactId: "IC-opaque/fixture:0001", receiptId: "AR-opaque/fixture:0001" };
  const result = store.putArtifact(source, metadata(ids));
  const hex = digestHex(original);

  assert.deepEqual(
    {
      artifactStatus: result.artifactStatus,
      objectStatus: result.objectStatus,
      receiptStatus: result.receiptStatus,
      status: result.status,
    },
    {
      artifactStatus: "CREATED",
      objectStatus: "CREATED",
      receiptStatus: "CREATED",
      status: "CREATED",
    },
  );
  assert.equal(result.manifest.artifact_id, ids.artifactId);
  assert.equal(result.manifest.content_hash, `sha256:${hex}`);
  assert.equal(result.manifest.storage_uri, `artifact://sha256/${hex}`);
  assert.equal(result.manifest.byte_size, original.length);
  assert.equal(result.receipt.receipt_id, ids.receiptId);
  assert.equal(result.receipt.artifact_id, ids.artifactId);
  assert.equal(result.receipt.content_hash, result.manifest.content_hash);
  assert.equal(result.receipt.locator, result.manifest.storage_uri);
  assert.equal(result.receipt.schema_ref, "fixture.schema.json");
  assert.deepEqual(result.receipt.created_by, {
    actor_id: "ACT-D03-receipt-writer",
    actor_type: "service",
  });
  assert.equal(Object.isFrozen(result.manifest), true);
  assert.equal(Object.isFrozen(result.receipt), true);

  source.fill(0x44);
  assert.deepEqual(store.readArtifact(ids.artifactId), original);
  assert.deepEqual(store.readObject(result.manifest.content_hash), original);
  const returned = store.readObject(result.manifest.storage_uri);
  returned.fill(0x55);
  assert.deepEqual(store.readArtifact(ids.artifactId), original);

  const resolved = store.resolveReceipt(ids.receiptId);
  assert.deepEqual(resolved.bytes, original);
  assert.equal(resolved.schemaRef, "fixture.schema.json");
  assert.deepEqual(resolved.createdBy, result.receipt.created_by);
  assert.equal(resolved.manifest.artifact_id, ids.artifactId);

  const receiptWithoutHash = { ...result.receipt };
  delete receiptWithoutHash.receipt_hash;
  assert.equal(
    result.receipt.receipt_hash,
    digest(Buffer.from(canonicalJson(receiptWithoutHash), "utf8")),
  );
  const manifestHash = digest(Buffer.from(canonicalJson(result.manifest), "utf8"));
  assert.deepEqual(result.receipt.validation_results.slice(0, 2), [
    { check: "content_sha256", details: `sha256:${hex}`, status: "PASS" },
    { check: "artifact_manifest_sha256", details: manifestHash, status: "PASS" },
  ]);

  const expectedRecord = recordPath(root, original);
  assert.deepEqual(readdirSync(expectedRecord).sort(), ["artifacts", "content.bin"]);
  assert.deepEqual(readFileSync(path.join(expectedRecord, "content.bin")), original);
  assert.deepEqual(
    readdirSync(registrationPath(root, original, ids.artifactId)).sort(),
    ["artifact-manifest.json", "receipts"],
  );

  store.close();
  const reopened = openContentAddressedArtifactStore(root);
  assert.equal(reopened.mode, ARTIFACT_STORE_MODE.ACTIVE);
  assert.deepEqual(reopened.readArtifact(ids.artifactId), original);
  assert.deepEqual(reopened.readReceipt(ids.receiptId), result.receipt);
  assert.deepEqual(reopened.checkIntegrity(), {
    artifactCount: 1,
    details: null,
    objectCount: 1,
    ok: true,
    receiptCount: 1,
    mode: ARTIFACT_STORE_MODE.ACTIVE,
  });
});

test("artifact_hash_test: empty bytes have a real content address", (t) => {
  const { store } = activeStore(t);
  const result = store.putArtifact(
    Buffer.alloc(0),
    metadata({ artifactId: "ART-empty", receiptId: "AR-empty" }),
  );
  assert.equal(
    result.manifest.content_hash,
    "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  );
  assert.equal(result.manifest.byte_size, 0);
  assert.deepEqual(store.readArtifact("ART-empty"), Buffer.alloc(0));
});

test("artifact_hash_test: artifact ID satisfies the manifest/receipt schema intersection", (t) => {
  const { store } = activeStore(t);
  const minimumId = "A01";
  const maximumId = `ART-${"o".repeat(124)}`;
  store.putArtifact(
    Buffer.from("minimum artifact ID"),
    metadata({ artifactId: minimumId, receiptId: "AR-minimum-artifact-id" }),
  );
  store.putArtifact(
    Buffer.from("maximum artifact ID"),
    metadata({ artifactId: maximumId, receiptId: "AR-maximum-artifact-id" }),
  );
  assert.deepEqual(store.readArtifact(minimumId), Buffer.from("minimum artifact ID"));
  assert.deepEqual(store.readArtifact(maximumId), Buffer.from("maximum artifact ID"));
  for (const artifactId of ["A", "AB", `ART-${"o".repeat(125)}`]) {
    assert.throws(
      () =>
        store.putArtifact(
          Buffer.from(`invalid artifact ID ${artifactId.length}`),
          metadata({ artifactId, receiptId: `AR-invalid-artifact-${artifactId.length}` }),
        ),
      expectCode("INVALID_INPUT"),
    );
  }
  assert.throws(
    () =>
      store.putArtifact(
        Buffer.from("empty artifact ID"),
        metadata({ artifactId: "", receiptId: "AR-empty-artifact-id" }),
      ),
    expectCode("INVALID_INPUT"),
  );
});

test("artifact_hash_test: emitted manifest and receipt pass canonical Draft 2020-12 schemas", (t) => {
  const { root, store } = activeStore(t);
  const bytes = Buffer.from("schema validation target", "utf8");
  const ids = { artifactId: "ART-schema-validation", receiptId: "AR-schema-validation" };
  store.putArtifact(bytes, metadata(ids));
  const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
  const script = `
import json
import pathlib
import sys
from jsonschema import Draft202012Validator, FormatChecker

pairs = ((sys.argv[1], sys.argv[2]), (sys.argv[3], sys.argv[4]))
for schema_path, instance_path in pairs:
    schema = json.loads(pathlib.Path(schema_path).read_text(encoding="utf-8"))
    instance = json.loads(pathlib.Path(instance_path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        raise SystemExit("; ".join(error.message for error in errors))
print("2 canonical documents validated")
`;
  const validation = spawnSync(
    "uv",
    [
      "run",
      "--locked",
      "python",
      "-",
      path.join(repositoryRoot, "schemas", "artifact-manifest.schema.json"),
      manifestPath(root, bytes, ids.artifactId),
      path.join(repositoryRoot, "schemas", "artifact-receipt.schema.json"),
      receiptPath(root, bytes, ids.artifactId, ids.receiptId),
    ],
    { cwd: repositoryRoot, encoding: "utf8", input: script },
  );
  assert.equal(
    validation.status,
    0,
    `schema validation failed\nstdout: ${validation.stdout}\nstderr: ${validation.stderr}`,
  );
  assert.equal(validation.stdout.trim(), "2 canonical documents validated");
});

test("artifact_hash_test: identical registration and receipt replay is idempotent", (t) => {
  const { store } = activeStore(t);
  const bytes = Buffer.from("same immutable bytes", "utf8");
  const fixture = metadata({ artifactId: "ART-replay", receiptId: "AR-replay" });
  const first = store.putArtifact(bytes, fixture);
  const replay = store.putArtifact(bytes, fixture);
  assert.equal(first.status, "CREATED");
  assert.deepEqual(
    {
      artifactStatus: replay.artifactStatus,
      objectStatus: replay.objectStatus,
      receiptStatus: replay.receiptStatus,
      status: replay.status,
    },
    {
      artifactStatus: "EXISTING",
      objectStatus: "EXISTING",
      receiptStatus: "EXISTING",
      status: "EXISTING",
    },
  );
  assert.deepEqual(replay.manifest, first.manifest);
  assert.deepEqual(replay.receipt, first.receipt);
});

test("artifact_hash_test: one byte object supports multiple artifacts and receipts", (t) => {
  const { store } = activeStore(t);
  const bytes = Buffer.from("shared immutable bytes", "utf8");
  const firstMetadata = metadata({
    artifactId: "ART-shared-A",
    receiptId: "AR-shared-A-1",
  });
  const first = store.putArtifact(bytes, firstMetadata);
  const second = store.putArtifact(
    bytes,
    metadata({
      artifact: {
        artifactType: "derived_fixture",
        createdAt: "2026-07-28T00:02:00Z",
        createdBy: "ACT-second-registration",
        provenanceManifestId: "PROV-second",
      },
      artifactId: "ART-shared-B",
      receipt: { createdAt: "2026-07-28T00:02:01Z" },
      receiptId: "AR-shared-B-1",
    }),
  );
  const third = store.putArtifact(
    bytes,
    metadata({
      artifact: firstMetadata.artifact,
      artifactId: "ART-shared-A",
      receipt: {
        actionIntentId: "AI-second-validation",
        createdAt: "2026-07-28T00:03:00Z",
        createdBy: { actorId: "ACT-independent-validator", actorType: "agent" },
        validationResults: [
          { check: "independent_validation", status: "PASS", details: "second receipt" },
        ],
      },
      receiptId: "AR-shared-A-2",
    }),
  );

  assert.equal(first.objectStatus, "CREATED");
  assert.equal(second.objectStatus, "EXISTING");
  assert.equal(second.artifactStatus, "CREATED");
  assert.equal(third.objectStatus, "EXISTING");
  assert.equal(third.artifactStatus, "EXISTING");
  assert.equal(third.receiptStatus, "CREATED");
  assert.deepEqual(
    store.enumerateArtifacts().map((manifest) => manifest.artifact_id),
    ["ART-shared-A", "ART-shared-B"],
  );
  assert.deepEqual(
    store.enumerateReceipts().map((receipt) => receipt.receipt_id),
    ["AR-shared-A-1", "AR-shared-A-2", "AR-shared-B-1"],
  );
  assert.deepEqual(store.checkIntegrity(), {
    artifactCount: 2,
    details: null,
    objectCount: 1,
    ok: true,
    receiptCount: 3,
    mode: ARTIFACT_STORE_MODE.ACTIVE,
  });
  assert.deepEqual(store.resolveReceipt("AR-shared-A-2").bytes, bytes);
});

test("artifact_hash_test: artifact ID cannot be rebound to different bytes", (t) => {
  const { store } = activeStore(t);
  store.putArtifact(
    Buffer.from("first bytes"),
    metadata({ artifactId: "ART-stable-id", receiptId: "AR-first" }),
  );
  assert.throws(
    () =>
      store.putArtifact(
        Buffer.from("different bytes"),
        metadata({ artifactId: "ART-stable-id", receiptId: "AR-second" }),
      ),
    expectCode("ARTIFACT_ID_CONFLICT"),
  );
  assert.equal(store.mode, ARTIFACT_STORE_MODE.ACTIVE);
  assert.deepEqual(store.readArtifact("ART-stable-id"), Buffer.from("first bytes"));
});

test("artifact_hash_test: receipt ID cannot be rebound", (t) => {
  const { store } = activeStore(t);
  store.putArtifact(
    Buffer.from("first receipt bytes"),
    metadata({ artifactId: "ART-receipt-first", receiptId: "AR-stable-id" }),
  );
  assert.throws(
    () =>
      store.putArtifact(
        Buffer.from("second receipt bytes"),
        metadata({ artifactId: "ART-receipt-second", receiptId: "AR-stable-id" }),
      ),
    expectCode("ARTIFACT_RECEIPT_ID_CONFLICT"),
  );
  assert.equal(store.mode, ARTIFACT_STORE_MODE.ACTIVE);
});

test("artifact_hash_test: immutable artifact metadata cannot be overwritten", (t) => {
  const { store } = activeStore(t);
  const bytes = Buffer.from("metadata target", "utf8");
  store.putArtifact(
    bytes,
    metadata({ artifactId: "ART-metadata", receiptId: "AR-metadata-1" }),
  );
  assert.throws(
    () =>
      store.putArtifact(
        bytes,
        metadata({
          artifact: { mediaType: "text/plain" },
          artifactId: "ART-metadata",
          receiptId: "AR-metadata-2",
        }),
      ),
    expectCode("ARTIFACT_IMMUTABLE_CONFLICT"),
  );
  assert.equal(store.mode, ARTIFACT_STORE_MODE.ACTIVE);
});

test("artifact_hash_test: distinct byte sequences never alias", (t) => {
  const { store } = activeStore(t);
  const left = store.putArtifact(
    Buffer.from("left"),
    metadata({ artifactId: "ART-left", receiptId: "AR-left" }),
  );
  const right = store.putArtifact(
    Buffer.from("right"),
    metadata({ artifactId: "ART-right", receiptId: "AR-right" }),
  );
  assert.notEqual(left.manifest.content_hash, right.manifest.content_hash);
  assert.notEqual(left.manifest.storage_uri, right.manifest.storage_uri);
  assert.equal(store.checkIntegrity().objectCount, 2);
});

test("artifact_hash_test: hostile metadata and byte views fail before accessors run", (t) => {
  const { store } = activeStore(t);
  let getterCalls = 0;
  const accessorMetadata = metadata();
  Object.defineProperty(accessorMetadata.artifact, "createdAt", {
    enumerable: true,
    get() {
      getterCalls += 1;
      return "2026-07-28T00:00:00Z";
    },
  });
  assert.throws(
    () => store.putArtifact(Buffer.from("x"), accessorMetadata),
    expectCode("INVALID_INPUT"),
  );
  assert.equal(getterCalls, 0);
  assert.throws(
    () => store.putArtifact(Buffer.from("x"), new Proxy(metadata(), {})),
    expectCode("INVALID_INPUT"),
  );
  assert.throws(
    () => store.putArtifact(new Proxy(new Uint8Array([1]), {}), metadata()),
    expectCode("INVALID_INPUT"),
  );
  assert.throws(
    () => store.putArtifact(new DataView(new ArrayBuffer(1)), metadata()),
    expectCode("INVALID_INPUT"),
  );
  assert.equal(store.mode, ARTIFACT_STORE_MODE.ACTIVE);
  assert.equal(store.enumerateArtifacts().length, 0);
});

test("artifact_hash_test: canonical metadata validation is strict and non-mutating", (t) => {
  const { store } = activeStore(t);
  const invalid = [
    metadata({ artifact: { createdAt: "2026-02-30T00:00:00Z" } }),
    metadata({ artifactId: "x" }),
    metadata({ artifact: { retentionClass: "forever" } }),
    metadata({ artifact: { confidentiality: "classified" } }),
    metadata({ receipt: { createdBy: { actorId: "x", actorType: "service" } } }),
    metadata({ receipt: { createdBy: { actorId: "ACT-valid", actorType: "model" } } }),
    metadata({ receipt: { schemaRef: "" } }),
    metadata({
      receipt: {
        validationResults: [
          { check: "content_sha256", status: "PASS", details: "forged store check" },
        ],
      },
    }),
  ];
  const missing = metadata();
  delete missing.artifact.license;
  invalid.push(missing);
  for (const candidate of invalid) {
    assert.throws(
      () => store.putArtifact(Buffer.from("invalid"), candidate),
      expectCode("INVALID_INPUT"),
    );
  }
  const validEmptyCallerChecks = metadata({
    artifactId: "ART-empty-caller-checks",
    receipt: { validationResults: [] },
    receiptId: "AR-empty-caller-checks",
  });
  const result = store.putArtifact(Buffer.from("valid"), validEmptyCallerChecks);
  assert.equal(result.receipt.validation_results.length, 2);
  assert.equal(store.mode, ARTIFACT_STORE_MODE.ACTIVE);
});

test("artifact_hash_test: exact content tamper enters SAFE_MODE and denies reuse", (t) => {
  const { root, store } = activeStore(t);
  const bytes = Buffer.from("original bytes", "utf8");
  const result = store.putArtifact(
    bytes,
    metadata({ artifactId: "ART-tamper", receiptId: "AR-tamper" }),
  );
  writeFileSync(path.join(recordPath(root, bytes), "content.bin"), Buffer.from("changed! bytes"));

  assert.throws(() => store.readArtifact(result.manifest.artifact_id), expectCode("ARTIFACT_HASH_MISMATCH"));
  assert.equal(store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
  assert.equal(store.safeModeReason.code, "ARTIFACT_HASH_MISMATCH");
  assert.throws(() => store.readManifest(result.manifest.artifact_id), expectCode("STORE_SAFE_MODE"));
  assert.throws(
    () =>
      store.putArtifact(
        Buffer.from("new"),
        metadata({ artifactId: "ART-new", receiptId: "AR-new" }),
      ),
    expectCode("STORE_SAFE_MODE"),
  );
});

test("artifact_hash_test: noncanonical manifest and receipt tamper fail closed", (t) => {
  const first = activeStore(t);
  const firstBytes = Buffer.from("manifest target");
  const firstIds = { artifactId: "ART-manifest-target", receiptId: "AR-manifest-target" };
  first.store.putArtifact(firstBytes, metadata(firstIds));
  const firstManifestPath = manifestPath(first.root, firstBytes, firstIds.artifactId);
  writeFileSync(firstManifestPath, `${readFileSync(firstManifestPath, "utf8")} `, "utf8");
  assert.throws(
    () => first.store.readManifest(firstIds.artifactId),
    expectCode("ARTIFACT_MANIFEST_NON_CANONICAL"),
  );
  assert.equal(first.store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);

  const second = activeStore(t);
  const secondBytes = Buffer.from("receipt target");
  const secondIds = { artifactId: "ART-receipt-target", receiptId: "AR-receipt-target" };
  second.store.putArtifact(secondBytes, metadata(secondIds));
  const secondReceiptPath = receiptPath(
    second.root,
    secondBytes,
    secondIds.artifactId,
    secondIds.receiptId,
  );
  const receipt = JSON.parse(readFileSync(secondReceiptPath, "utf8"));
  receipt.schema_ref = "tampered.schema.json";
  writeFileSync(secondReceiptPath, `${canonicalJson(receipt)}\n`, "utf8");
  assert.throws(
    () => second.store.resolveReceipt(secondIds.receiptId),
    expectCode("ARTIFACT_RECEIPT_HASH_MISMATCH"),
  );
  assert.equal(second.store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
});

test("artifact_hash_test: hard-linked record file is rejected", (t) => {
  const { root, store } = activeStore(t);
  const bytes = Buffer.from("hard link target");
  const ids = { artifactId: "ART-hardlink", receiptId: "AR-hardlink" };
  store.putArtifact(bytes, metadata(ids));
  const contentPath = path.join(recordPath(root, bytes), "content.bin");
  const external = path.join(path.dirname(root), `${path.basename(root)}-external.bin`);
  t.after(() => rmSync(external, { force: true }));
  renameSync(contentPath, external);
  linkSync(external, contentPath);

  assert.throws(() => store.readArtifact(ids.artifactId), expectCode("ARTIFACT_FILE_IDENTITY_INVALID"));
  assert.equal(store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
});

test("artifact_hash_test: linked root is never accepted as canonical authority", (t) => {
  const target = temporaryRoot(t, "ef-d03-target-");
  const parent = temporaryRoot(t, "ef-d03-link-parent-");
  const link = path.join(parent, "linked-store");
  try {
    symlinkSync(target, link, process.platform === "win32" ? "junction" : "dir");
  } catch (error) {
    if (error instanceof Error && ["EPERM", "EACCES", "ENOTSUP"].includes(error.code)) {
      t.skip(`host cannot create a directory link: ${error.code}`);
      return;
    }
    throw error;
  }
  const store = openContentAddressedArtifactStore(link);
  assert.equal(store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
  assert.equal(store.safeModeReason.code, "ARTIFACT_STORE_ROOT_LINK_DENIED");
});

test("artifact_hash_test: unexpected tree entries fail integrity and mutation admission", (t) => {
  const { root, store } = activeStore(t);
  writeFileSync(path.join(root, "unmanaged.txt"), "not canonical", "utf8");
  assert.deepEqual(store.checkIntegrity(), {
    artifactCount: 0,
    details: { entries: [".staging", "sha256", "unmanaged.txt"] },
    objectCount: 0,
    mode: ARTIFACT_STORE_MODE.SAFE_MODE,
    ok: false,
    receiptCount: 0,
  });
  assert.throws(
    () =>
      store.putArtifact(
        Buffer.from("blocked"),
        metadata({ artifactId: "ART-blocked", receiptId: "AR-blocked" }),
      ),
    expectCode("STORE_SAFE_MODE"),
  );
});

test("artifact_hash_test: content references are strict while opaque IDs cannot traverse", (t) => {
  const { store } = activeStore(t);
  for (const reference of ["../secret", `SHA256:${"a".repeat(64)}`, "sha256:abc", "file:///tmp/x"]) {
    assert.throws(() => store.readObject(reference), expectCode("INVALID_CONTENT_REFERENCE"));
  }
  assert.throws(() => store.readArtifact("../secret"), expectCode("ARTIFACT_NOT_FOUND"));
  assert.throws(() => store.readReceipt("../../receipt"), expectCode("ARTIFACT_RECEIPT_NOT_FOUND"));
  assert.equal(store.mode, ARTIFACT_STORE_MODE.ACTIVE);
});

test("artifact_hash_test: replacing the root after open is detected by identity", (t) => {
  const root = temporaryRoot(t, "ef-d03-root-identity-");
  const moved = `${root}-moved`;
  t.after(() => rmSync(moved, { recursive: true, force: true }));
  const store = openContentAddressedArtifactStore(root);
  assert.equal(store.mode, ARTIFACT_STORE_MODE.ACTIVE);
  renameSync(root, moved);
  mkdirSync(root);
  assert.throws(() => store.enumerateArtifacts(), expectCode("ARTIFACT_STORE_IDENTITY_CHANGED"));
  assert.equal(store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
});

test("artifact_hash_test: public surface has no deletion or overwrite operation", (t) => {
  const { store } = activeStore(t);
  for (const name of ["deleteArtifact", "deleteObject", "overwriteArtifact", "updateManifest", "updateReceipt"]) {
    assert.equal(store[name], undefined);
  }
  store.close();
  assert.throws(() => store.enumerateArtifacts(), expectCode("STORE_CLOSED"));
});

test("artifact_hash_test: duplicate artifact IDs copied across objects fail closed", (t) => {
  const { root, store } = activeStore(t);
  const leftBytes = Buffer.from("duplicate-id-left");
  const rightBytes = Buffer.from("duplicate-id-right");
  store.putArtifact(
    leftBytes,
    metadata({ artifactId: "ART-duplicate-source", receiptId: "AR-duplicate-source" }),
  );
  store.putArtifact(
    rightBytes,
    metadata({ artifactId: "ART-duplicate-target", receiptId: "AR-duplicate-target" }),
  );
  const targetManifest = manifestPath(root, rightBytes, "ART-duplicate-target");
  const replacement = JSON.parse(
    readFileSync(manifestPath(root, leftBytes, "ART-duplicate-source"), "utf8"),
  );
  replacement.content_hash = digest(rightBytes);
  replacement.storage_uri = `artifact://sha256/${digestHex(rightBytes)}`;
  replacement.byte_size = rightBytes.length;
  writeFileSync(targetManifest, `${canonicalJson(replacement)}\n`, "utf8");
  assert.equal(store.checkIntegrity().ok, false);
  assert.equal(store.mode, ARTIFACT_STORE_MODE.SAFE_MODE);
  assert.equal(store.safeModeReason.code, "ARTIFACT_MANIFEST_KEY_MISMATCH");
});
