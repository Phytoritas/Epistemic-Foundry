import { createHash, randomUUID } from "node:crypto";
import {
  constants as fsConstants,
  copyFileSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

export const sha256Bytes = (bytes) =>
  createHash("sha256").update(bytes).digest("hex");

export const sha256File = (filePath) => sha256Bytes(readFileSync(filePath));

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

const assertDirectory = (candidate, label) => {
  const stat = lstatSync(candidate);
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error(`${label} must be a real directory`);
  }
};

const collectFiles = (root) => {
  assertDirectory(root, "snapshot tree");
  const result = [];
  const visit = (current, prefix) => {
    for (const name of readdirSync(current).sort()) {
      const absolute = path.join(current, name);
      const relative = prefix === "" ? name : `${prefix}/${name}`;
      const stat = lstatSync(absolute);
      if (stat.isSymbolicLink()) {
        throw new Error(`snapshot tree contains a symbolic link: ${relative}`);
      }
      if (stat.isDirectory()) {
        visit(absolute, relative);
        continue;
      }
      if (!stat.isFile() || stat.nlink !== 1) {
        throw new Error(`snapshot tree contains an unsupported file: ${relative}`);
      }
      result.push({
        byte_size: stat.size,
        path: relative,
        sha256: sha256File(absolute),
      });
    }
  };
  visit(root, "");
  return result;
};

const copyManifestFiles = (sourceRoot, destinationRoot, entries) => {
  for (const entry of entries) {
    const source = path.join(sourceRoot, ...entry.path.split("/"));
    const destination = path.join(destinationRoot, ...entry.path.split("/"));
    mkdirSync(path.dirname(destination), { recursive: true, mode: 0o700 });
    copyFileSync(source, destination);
  }
};

const validateManifestEntries = (entries) => {
  for (const entry of entries) {
    if (
      typeof entry !== "object" ||
      entry === null ||
      typeof entry.path !== "string" ||
      !entry.path.startsWith("sha256/") ||
      entry.path.includes("..") ||
      entry.path.includes("\\") ||
      !Number.isSafeInteger(entry.byte_size) ||
      entry.byte_size < 0 ||
      !/^[0-9a-f]{64}$/u.test(entry.sha256)
    ) {
      throw new Error("snapshot manifest entry is invalid");
    }
  }
};

const validateArtifactPayload = (payloadRoot, entries, label) => {
  validateManifestEntries(entries);
  const actualFiles = collectFiles(path.join(payloadRoot, "sha256")).map((entry) => ({
    ...entry,
    path: `sha256/${entry.path}`,
  }));
  if (canonicalJson(actualFiles) !== canonicalJson(entries)) {
    throw new Error(`${label} file inventory mismatch`);
  }
};

export const artifactMetadata = ({
  artifactId = "ART-D04-backup-fixture",
  receiptId = "AR-D04-backup-fixture",
} = {}) => ({
  artifact: {
    artifactId,
    artifactType: "recovery_fixture",
    confidentiality: "internal",
    createdAt: "2026-07-28T00:00:00Z",
    createdBy: "ACT-D04-recovery-test",
    encryption: { atRest: true, inTransit: true, keyRef: "local://d04-test-key" },
    inputArtifactIds: [],
    license: null,
    lineageEventIds: ["EVT-D04-recovery-test"],
    mediaType: "application/octet-stream",
    provenanceManifestId: "PROV-D04-recovery-test",
    retentionClass: "project",
  },
  receipt: {
    actionIntentId: null,
    createdAt: "2026-07-28T00:00:01Z",
    createdBy: { actorId: "ACT-D04-backup-service", actorType: "service" },
    receiptId,
    schemaRef: "d04-recovery-fixture.schema.json",
    validationResults: [
      { check: "d04_recovery_fixture", details: "fixture sealed", status: "PASS" },
    ],
  },
});

export const createArtifactSnapshot = (sourceRoot, snapshotRoot) => {
  if (existsSync(snapshotRoot)) throw new Error("snapshot destination already exists");
  const canonicalSource = path.join(sourceRoot, "sha256");
  const sourceEntries = collectFiles(canonicalSource);
  if (sourceEntries.length === 0) throw new Error("artifact snapshot cannot be empty");

  const files = sourceEntries.map((entry) => ({
    ...entry,
    path: `sha256/${entry.path}`,
  }));
  const core = {
    files,
    schema: "epistemic-foundry-artifact-snapshot/v1",
  };
  const manifest = {
    ...core,
    source_bundle_hash: `sha256:${sha256Bytes(Buffer.from(canonicalJson(core), "utf8"))}`,
  };

  mkdirSync(snapshotRoot, { recursive: false, mode: 0o700 });
  copyManifestFiles(sourceRoot, snapshotRoot, files);
  writeFileSync(
    path.join(snapshotRoot, "snapshot-manifest.json"),
    `${canonicalJson(manifest)}\n`,
    { encoding: "utf8", flag: "wx", mode: 0o600 },
  );
  validateArtifactSnapshot(snapshotRoot);
  return manifest;
};

export const validateArtifactSnapshot = (snapshotRoot) => {
  assertDirectory(snapshotRoot, "snapshot root");
  const manifestPath = path.join(snapshotRoot, "snapshot-manifest.json");
  const manifestStat = lstatSync(manifestPath);
  if (manifestStat.isSymbolicLink() || !manifestStat.isFile() || manifestStat.nlink !== 1) {
    throw new Error("snapshot manifest must be one regular file");
  }
  const manifestText = readFileSync(manifestPath, "utf8");
  const manifest = JSON.parse(manifestText);
  if (`${canonicalJson(manifest)}\n` !== manifestText) {
    throw new Error("snapshot manifest is not canonical JSON");
  }
  if (
    manifest.schema !== "epistemic-foundry-artifact-snapshot/v1" ||
    !Array.isArray(manifest.files) ||
    manifest.files.length === 0
  ) {
    throw new Error("snapshot manifest shape is invalid");
  }
  const core = { files: manifest.files, schema: manifest.schema };
  const expectedBundleHash = `sha256:${sha256Bytes(
    Buffer.from(canonicalJson(core), "utf8"),
  )}`;
  if (manifest.source_bundle_hash !== expectedBundleHash) {
    throw new Error("snapshot manifest bundle hash mismatch");
  }
  validateArtifactPayload(snapshotRoot, manifest.files, "snapshot");
  return manifest;
};

export const restoreArtifactSnapshot = (snapshotRoot, targetRoot, options = {}) => {
  const manifest = validateArtifactSnapshot(snapshotRoot);
  if (existsSync(targetRoot)) throw new Error("restore target already exists");
  const stageRoot = `${targetRoot}.restore-${randomUUID()}`;
  mkdirSync(stageRoot, { recursive: false, mode: 0o700 });
  mkdirSync(path.join(stageRoot, ".staging"), { recursive: false, mode: 0o700 });
  mkdirSync(path.join(stageRoot, "sha256"), { recursive: false, mode: 0o700 });
  copyManifestFiles(snapshotRoot, stageRoot, manifest.files);
  options.afterCopy?.(stageRoot);
  validateArtifactPayload(stageRoot, manifest.files, "staged restore");
  if (existsSync(targetRoot)) throw new Error("restore target appeared during staging");
  renameSync(stageRoot, targetRoot);
  return manifest;
};

export const restoreSQLiteBackup = (
  backupPath,
  targetPath,
  expectedSha256,
  options = {},
) => {
  if (!/^[0-9a-f]{64}$/u.test(expectedSha256)) {
    throw new Error("expected SQLite backup hash is invalid");
  }
  if (sha256File(backupPath) !== expectedSha256) {
    throw new Error("SQLite backup hash mismatch");
  }
  if (existsSync(targetPath)) throw new Error("SQLite restore target already exists");
  const stagePath = `${targetPath}.restore-${randomUUID()}`;
  copyFileSync(backupPath, stagePath, fsConstants.COPYFILE_EXCL);
  options.afterCopy?.(stagePath);
  if (sha256File(stagePath) !== expectedSha256) {
    throw new Error("SQLite staged restore hash mismatch");
  }
  const database = new DatabaseSync(stagePath, { readOnly: true });
  try {
    const rows = database.prepare("PRAGMA integrity_check").all();
    if (rows.length !== 1 || rows[0]?.integrity_check !== "ok") {
      throw new Error("SQLite staged restore integrity check failed");
    }
  } finally {
    database.close();
  }
  if (existsSync(targetPath)) throw new Error("SQLite restore target appeared during staging");
  renameSync(stagePath, targetPath);
};
