// Build the installable plugin payload.
//
// Checks require an existing generated pair to match its closed inventories.
// Normal builds require replaceable ordinary final roots, then prepare and
// verify the complete closed dist + runtime pair in one marked private
// generation. This lets a build recover from a stale or incomplete generated
// root without trusting or executing it. Only after the staged pair verifies
// does the builder replace both final roots by directory renames, retaining the
// previous pair until both replacements have committed.
//
// Usage:
//   node plugins/epistemic-foundry/scripts/build.mjs
//   node plugins/epistemic-foundry/scripts/build.mjs --check
//   node plugins/epistemic-foundry/scripts/build.mjs --release
//   node plugins/epistemic-foundry/scripts/build.mjs --check --release

import { spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import {
  closeSync,
  fsyncSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  rmdirSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PLUGIN_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const REPOSITORY_ROOT = dirname(dirname(PLUGIN_ROOT));
const SOURCE_DIR = join(PLUGIN_ROOT, "src");
const DIST_DIR = join(PLUGIN_ROOT, "dist");
const RUNTIME_DIR = join(PLUGIN_ROOT, "runtime");
const WORKSPACE_MAP_WORKER = join(
  REPOSITORY_ROOT,
  "packages",
  "plugin-host",
  "src",
  "cli",
  "bundle-map-worker.mjs",
);
const PRIVATE_STAGE_ENV = "EFOUNDRY_PRIVATE_STAGING_ROOT";
const PRIVATE_STAGE_PREFIX = ".efoundry-build-";
const PRIVATE_STAGE_MARKER = ".epistemic-foundry-private-stage";
const PRIVATE_STAGE_MARKER_TEXT = "epistemic-foundry-private-stage-v1\n";
const PREVIOUS_DIST_NAME = "previous-dist";
const PREVIOUS_RUNTIME_NAME = "previous-runtime";
const FOUNDRY_KERNEL_SOURCE = "packages/foundry-kernel/src";
const FOUNDRY_KERNEL_OUTPUT = "foundry-kernel";
const PLUGIN_HOST_SOURCE = "packages/plugin-host/src";
const PLUGIN_HOST_OUTPUT = "plugin-host";

/** Exact Foundry Kernel ESM closure copied into the plugin payload. */
const FOUNDRY_KERNEL_FILES = Object.freeze([
  "artifacts/content-addressed-artifact-store.mjs",
  "capabilities/capability-authority.mjs",
  "effects/effect-coordinator.mjs",
  "ledger/noetic-ledger.mjs",
  "state/sqlite/sqlite-state-store.mjs",
  "forge/classifier/index.mjs",
  "forge/classifier/epistemic-work-classifier.mjs",
  "forge/classifier/classification-committer.mjs",
  "forge/fsm/index.mjs",
  "forge/fsm/forge-fsm.mjs",
  "forge/gates/index.mjs",
  "forge/gates/transition-admission-gate.mjs",
  "forge/session/index.mjs",
  "forge/session/installed-forge-runtime.mjs",
  "forge/session/durable-forge-session.mjs",
  "forge/session/session-transition-worker.mjs",
  "forge/session/session-records.mjs",
  "forge/session/canonical-json.mjs",
]);

/** Exact Plugin Host ESM/data closure copied into the plugin payload. */
const PLUGIN_HOST_FILES = Object.freeze([
  "mcp/read/mcp-server.mjs",
  "mcp/read/local-stdio-handler.mjs",
  "mcp/read/local-stdio-binding.mjs",
  "mcp/generated/tool-descriptors.json",
  "paths/path-resolution.mjs",
]);

/** Exact repository inputs that may affect the generated plugin payload. */
const RELEASE_INPUTS = Object.freeze([
  "plugins/epistemic-foundry/src",
  "plugins/epistemic-foundry/scripts",
  ...FOUNDRY_KERNEL_FILES.map(
    (relative) => `${FOUNDRY_KERNEL_SOURCE}/${relative}`,
  ),
  ...PLUGIN_HOST_FILES.map(
    (relative) => `${PLUGIN_HOST_SOURCE}/${relative}`,
  ),
  "src/epistemic_foundry",
  "packages/plugin-host/src/cli/bundle-map-worker.mjs",
  "packages/workspace-map/src",
]);

/** Source files copied verbatim into the payload. */
const COPIED = Object.freeze([
  "cli.mjs",
  "python-runtime.mjs",
  "runtime-observation.mjs",
  "installed-forge-runtime.mjs",
  "store-read-model.mjs",
  "mcp-server.mjs",
  "hook-runner.mjs",
]);
/** Release-only closure duplicated from bundle-map-worker.mjs. */
const RELEASE_WORKSPACE_MAP_FILES = Object.freeze([
  "inventory/workspace-inventory.mjs",
  "inventory/index.mjs",
  "ranking/baseline/baseline-centrality.mjs",
  "ranking/baseline/index.mjs",
  "ranking/query/query-ranking-common.mjs",
  "ranking/query/query-personalization.mjs",
  "ranking/query/risk-change-impact.mjs",
  "ranking/query/index.mjs",
  "snapshot/repository-scan.mjs",
  "snapshot/workspace-map-snapshot.mjs",
  "snapshot/index.mjs",
]);
const RELEASE_WORKSPACE_MAP_SOURCE = "packages/workspace-map/src";
const RELEASE_PYTHON_SOURCE = "src/epistemic_foundry";
const RELEASE_PYTHON_BOOTSTRAP =
  "plugins/epistemic-foundry/src/python-bootstrap.py";
const RELEASE_PYTHON_EXCLUDED_SUFFIXES = Object.freeze([".pyc", ".pyo"]);
const RELEASE_PYTHON_EXCLUDED_NAME = "conftest.py";
const GIT_MAX_BUFFER = 64 * 1024 * 1024;
const DIST_FILES = new Set([
  ...COPIED,
  "tool-descriptors.json",
  "payload-manifest.json",
]);
const DIST_DIRECTORIES = new Set([
  FOUNDRY_KERNEL_OUTPUT,
  PLUGIN_HOST_OUTPUT,
  "workspace-map",
]);

const sha256Bytes = (bytes) => createHash("sha256").update(bytes).digest("hex");

class BuildRefusedError extends Error {}

function lstatIfPresent(path) {
  try {
    return lstatSync(path);
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

function entryKind(entry) {
  if (entry.isSymbolicLink()) return "symlink";
  if (entry.isFile()) return "file";
  if (entry.isDirectory()) return "directory";
  return "special entry";
}

function inspectDistInventory(distRoot = DIST_DIR) {
  let rootMetadata;
  try {
    rootMetadata = lstatIfPresent(distRoot);
  } catch (error) {
    return {
      absent: false,
      missingMembers: [],
      structuralErrors: [`dist: could not inspect output root: ${error.message}`],
    };
  }
  if (rootMetadata === null) {
    return { absent: true, missingMembers: [], structuralErrors: [] };
  }
  if (rootMetadata.isSymbolicLink()) {
    return {
      absent: false,
      missingMembers: [],
      structuralErrors: ["dist: output root is a symlink"],
    };
  }
  if (!rootMetadata.isDirectory()) {
    return {
      absent: false,
      missingMembers: [],
      structuralErrors: ["dist: output root is not a directory"],
    };
  }

  let existing;
  try {
    existing = readdirSync(distRoot, { withFileTypes: true }).sort((left, right) =>
      left.name.localeCompare(right.name),
    );
  } catch (error) {
    return {
      absent: false,
      missingMembers: [],
      structuralErrors: [
        `dist: could not enumerate output root: ${error.message}`,
      ],
    };
  }

  const missingMembers = [];
  const structuralErrors = [];
  const observed = new Set();
  for (const entry of existing) {
    observed.add(entry.name);
    if (entry.isSymbolicLink()) {
      structuralErrors.push(`${entry.name}: symlink is not allowed`);
    } else if (DIST_FILES.has(entry.name)) {
      if (!entry.isFile()) {
        structuralErrors.push(
          `${entry.name}: expected file, found ${entryKind(entry)}`,
        );
      }
    } else if (DIST_DIRECTORIES.has(entry.name)) {
      if (!entry.isDirectory()) {
        structuralErrors.push(
          `${entry.name}: expected directory, found ${entryKind(entry)}`,
        );
      }
    } else {
      structuralErrors.push(`${entry.name}: unexpected ${entryKind(entry)}`);
    }
  }
  for (const expected of [...DIST_FILES, ...DIST_DIRECTORIES].sort()) {
    if (!observed.has(expected)) {
      missingMembers.push(`${expected}: missing from dist`);
    }
  }
  return { absent: false, missingMembers, structuralErrors };
}

function processResult(result) {
  const output = [result.stdout, result.stderr, result.error?.message]
    .filter((part) => part)
    .join("")
    .trim();
  return {
    ok: !result.error && result.status === 0,
    output: output || `process exited with status ${result.status}`,
  };
}

function childEnvironment(privateStageRoot = null) {
  const environment = { ...process.env };
  delete environment[PRIVATE_STAGE_ENV];
  if (privateStageRoot !== null) {
    environment[PRIVATE_STAGE_ENV] = privateStageRoot;
  }
  return environment;
}

function releaseSourceStatus() {
  const result = spawnSync(
    "git",
    ["status", "--porcelain", "--untracked-files=all", "--", ...RELEASE_INPUTS],
    {
      cwd: REPOSITORY_ROOT,
      encoding: "utf8",
      windowsHide: true,
    },
  );
  const processed = processResult(result);
  if (!processed.ok) {
    return {
      ok: false,
      output: `could not inspect release inputs with git status --porcelain: ${processed.output}`,
    };
  }
  const dirty = (result.stdout ?? "")
    .split(/\r?\n/u)
    .filter((line) => line.length > 0);
  if (dirty.length > 0) {
    return {
      ok: false,
      output: [
        "release build requires every declared input to match Git HEAD; dirty or untracked inputs:",
        ...dirty.map((line) => `  ${line}`),
      ].join("\n"),
    };
  }
  return { ok: true, output: "release inputs match Git HEAD" };
}

function gitText(args, label) {
  const result = spawnSync("git", args, {
    cwd: REPOSITORY_ROOT,
    encoding: "utf8",
    maxBuffer: GIT_MAX_BUFFER,
    windowsHide: true,
  });
  if (result.error || result.status !== 0) {
    throw new BuildRefusedError(`${label}: Git input could not be read`);
  }
  return result.stdout ?? "";
}

function gitBytes(args, label) {
  const result = spawnSync("git", args, {
    cwd: REPOSITORY_ROOT,
    encoding: null,
    maxBuffer: GIT_MAX_BUFFER,
    windowsHide: true,
  });
  if (result.error || result.status !== 0 || !Buffer.isBuffer(result.stdout)) {
    throw new BuildRefusedError(`${label}: Git blob could not be read`);
  }
  return result.stdout;
}

function readHeadOid() {
  const oid = gitText(
    ["rev-parse", "--verify", "HEAD^{commit}"],
    "release HEAD",
  ).trim();
  if (!/^[0-9a-f]{40,64}$/u.test(oid)) {
    throw new BuildRefusedError("release HEAD: Git returned an invalid commit OID");
  }
  return oid;
}

function releaseTreeEntries(headOid) {
  const requested = [
    ...COPIED.map((relative) => `plugins/epistemic-foundry/src/${relative}`),
    ...FOUNDRY_KERNEL_FILES.map(
      (relative) => `${FOUNDRY_KERNEL_SOURCE}/${relative}`,
    ),
    ...PLUGIN_HOST_FILES.map(
      (relative) => `${PLUGIN_HOST_SOURCE}/${relative}`,
    ),
    ...RELEASE_WORKSPACE_MAP_FILES.map(
      (relative) => `${RELEASE_WORKSPACE_MAP_SOURCE}/${relative}`,
    ),
    RELEASE_PYTHON_SOURCE,
    RELEASE_PYTHON_BOOTSTRAP,
  ];
  const listed = gitText(
    ["ls-tree", "-r", "-z", "--full-tree", headOid, "--", ...requested],
    "release closure",
  );
  const entries = new Map();
  for (const record of listed.split("\0")) {
    if (!record) continue;
    const separator = record.indexOf("\t");
    const header = separator >= 0 ? record.slice(0, separator).split(" ") : [];
    const path = separator >= 0 ? record.slice(separator + 1) : "";
    if (
      header.length !== 3 ||
      (header[0] !== "100644" && header[0] !== "100755") ||
      header[1] !== "blob" ||
      !/^[0-9a-f]{40,64}$/u.test(header[2]) ||
      !path
    ) {
      throw new BuildRefusedError("release closure: Git returned an invalid tree entry");
    }
    if (entries.has(path)) {
      throw new BuildRefusedError("release closure: Git returned a duplicate tree path");
    }
    entries.set(path, Object.freeze({ mode: header[0], oid: header[2] }));
  }
  return entries;
}

function immutableExpectedFile(relative, bytes) {
  const parts = relative.split("/");
  if (
    !relative ||
    relative.startsWith("/") ||
    relative.includes("\\") ||
    parts.some((part) => !part || part === "." || part === "..")
  ) {
    throw new BuildRefusedError("release closure: unsafe generated relative path");
  }
  return Object.freeze({
    contentBase64: bytes.toString("base64"),
    relative,
    sha256: sha256Bytes(bytes),
  });
}

function expectedFileBytes(file) {
  return Buffer.from(file.contentBase64, "base64");
}

function requiredExpectedFile(files, relative, label) {
  const matches = files.filter((file) => file.relative === relative);
  if (matches.length !== 1) {
    throw new BuildRefusedError(
      `${label}: expected exactly one ${relative} entry`,
    );
  }
  return matches[0];
}

function pinnedFile(entries, blobCache, source, relative = source) {
  const entry = entries.get(source);
  if (!entry) {
    throw new BuildRefusedError(`release closure: ${source} is missing from pinned HEAD`);
  }
  let contentBase64 = blobCache.get(entry.oid);
  if (contentBase64 === undefined) {
    contentBase64 = gitBytes(
      ["cat-file", "blob", entry.oid],
      `release closure ${source}`,
    ).toString("base64");
    blobCache.set(entry.oid, contentBase64);
  }
  return immutableExpectedFile(relative, Buffer.from(contentBase64, "base64"));
}

function pythonSourceExcluded(path) {
  const name = path.slice(path.lastIndexOf("/") + 1);
  return (
    name === RELEASE_PYTHON_EXCLUDED_NAME ||
    RELEASE_PYTHON_EXCLUDED_SUFFIXES.some((suffix) => path.endsWith(suffix))
  );
}

function captureReleaseClosure(headOid) {
  const entries = releaseTreeEntries(headOid);
  const blobCache = new Map();
  const copied = COPIED.map((relative) =>
    pinnedFile(
      entries,
      blobCache,
      `plugins/epistemic-foundry/src/${relative}`,
      relative,
    ),
  );
  const foundryKernelFiles = FOUNDRY_KERNEL_FILES.map((relative) =>
    pinnedFile(
      entries,
      blobCache,
      `${FOUNDRY_KERNEL_SOURCE}/${relative}`,
      relative,
    ),
  );
  const pluginHostFiles = PLUGIN_HOST_FILES.map((relative) =>
    pinnedFile(
      entries,
      blobCache,
      `${PLUGIN_HOST_SOURCE}/${relative}`,
      relative,
    ),
  );
  const distPayload = prepareDistPayloadFromBytes(
    copied,
    foundryKernelFiles,
    pluginHostFiles,
  );

  const workspaceFiles = RELEASE_WORKSPACE_MAP_FILES.map((relative) =>
    pinnedFile(
      entries,
      blobCache,
      `${RELEASE_WORKSPACE_MAP_SOURCE}/${relative}`,
      relative,
    ),
  );
  const workspaceManifestFiles = {};
  for (const file of workspaceFiles) {
    workspaceManifestFiles[file.relative] = `sha256:${file.sha256}`;
  }
  const workspaceManifest = immutableExpectedFile(
    "bundle-manifest.json",
    Buffer.from(
      `${JSON.stringify(
        {
          source: RELEASE_WORKSPACE_MAP_SOURCE,
          files: workspaceManifestFiles,
        },
        null,
        2,
      )}\n`,
      "utf8",
    ),
  );

  const pythonPrefix = `${RELEASE_PYTHON_SOURCE}/`;
  const pythonSources = [...entries.keys()]
    .filter((path) => path.startsWith(pythonPrefix) && !pythonSourceExcluded(path))
    .sort();
  if (pythonSources.length === 0) {
    throw new BuildRefusedError(
      `release closure: no tracked files found under ${RELEASE_PYTHON_SOURCE}`,
    );
  }
  const pythonFiles = [];
  const pythonManifestEntries = [];
  for (const source of pythonSources) {
    const packageRelative = source.slice(pythonPrefix.length);
    const output = `python/epistemic_foundry/${packageRelative}`;
    const file = pinnedFile(entries, blobCache, source, output);
    pythonFiles.push(file);
    pythonManifestEntries.push(Object.freeze({
      path: output,
      sha256: file.sha256,
      source,
    }));
  }
  const bootstrap = pinnedFile(
    entries,
    blobCache,
    RELEASE_PYTHON_BOOTSTRAP,
    "bootstrap.py",
  );
  pythonFiles.push(bootstrap);
  pythonManifestEntries.push(Object.freeze({
    path: bootstrap.relative,
    sha256: bootstrap.sha256,
    source: RELEASE_PYTHON_BOOTSTRAP,
  }));
  const runtimeManifest = Object.freeze({
    contentBase64: null,
    relative: "runtime-manifest.json",
    sha256: null,
  });

  return Object.freeze({
    distPayload,
    headOid,
    pythonManifestEntries: Object.freeze(pythonManifestEntries),
    runtimeFiles: Object.freeze([...pythonFiles, runtimeManifest]),
    workspaceFiles: Object.freeze([...workspaceFiles, workspaceManifest]),
  });
}

function assertPinnedHead(headOid) {
  if (readHeadOid() !== headOid) {
    throw new BuildRefusedError(
      "release HEAD changed after the input closure was pinned",
    );
  }
}

function configuredPythonExecutable() {
  const executable = process.env.EFOUNDRY_BUILD_PYTHON;
  if (!executable) {
    return {
      ok: false,
      output:
        "EFOUNDRY_BUILD_PYTHON is required and must be an absolute path to an existing regular Python executable file",
    };
  }
  if (!isAbsolute(executable)) {
    return {
      ok: false,
      output: `EFOUNDRY_BUILD_PYTHON must be absolute; received ${JSON.stringify(executable)}`,
    };
  }
  let metadata;
  try {
    metadata = statSync(executable);
  } catch (error) {
    return {
      ok: false,
      output: `EFOUNDRY_BUILD_PYTHON does not name an existing file: ${JSON.stringify(executable)} (${error.message})`,
    };
  }
  if (!metadata.isFile()) {
    return {
      ok: false,
      output: `EFOUNDRY_BUILD_PYTHON must name a regular file; received ${JSON.stringify(executable)}`,
    };
  }
  return { ok: true, executable };
}

function buildWorkspaceMap(mode, privateStageRoot = null) {
  const args = [WORKSPACE_MAP_WORKER];
  if (mode === "check") args.push("--check");
  if (mode === "preflight") args.push("--preflight");
  return processResult(
    spawnSync(process.execPath, args, {
      cwd: REPOSITORY_ROOT,
      encoding: "utf8",
      env: childEnvironment(privateStageRoot),
      windowsHide: true,
    }),
  );
}

function buildPythonRuntime(mode, releaseMode, executable, privateStageRoot = null) {
  const script = join(PLUGIN_ROOT, "scripts", "build-python-runtime.py");
  const args = [script];
  if (mode === "check") args.push("--check");
  if (mode === "preflight") args.push("--preflight");
  if (mode === "build" && releaseMode) args.push("--require-clean");
  return processResult(
    spawnSync(executable, args, {
      cwd: REPOSITORY_ROOT,
      encoding: "utf8",
      env: childEnvironment(privateStageRoot),
      windowsHide: true,
    }),
  );
}

function atomicWriteText(path, text) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = join(
    dirname(path),
    `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`,
  );
  let descriptor = null;
  try {
    descriptor = openSync(temporary, "wx");
    writeFileSync(descriptor, text, "utf8");
    fsyncSync(descriptor);
    closeSync(descriptor);
    descriptor = null;
    renameSync(temporary, path);
  } catch (error) {
    if (descriptor !== null) {
      try {
        closeSync(descriptor);
      } catch {
        // The original write failure remains authoritative.
      }
    }
    try {
      unlinkSync(temporary);
    } catch (cleanupError) {
      if (cleanupError.code !== "ENOENT") {
        error.message = `${error.message}; temporary cleanup also failed: ${cleanupError.message}`;
      }
    }
    throw error;
  }
}

function createPrivateStage() {
  const stageRoot = mkdtempSync(join(PLUGIN_ROOT, PRIVATE_STAGE_PREFIX));
  try {
    atomicWriteText(join(stageRoot, PRIVATE_STAGE_MARKER), PRIVATE_STAGE_MARKER_TEXT);
  } catch (error) {
    try {
      rmdirSync(stageRoot);
    } catch (cleanupError) {
      error.message = `${error.message}; empty private stage retained at ${stageRoot}: ${cleanupError.message}`;
    }
    throw error;
  }
  return stageRoot;
}

function assertOwnedPrivateStage(stageRoot) {
  if (!isAbsolute(stageRoot)) {
    throw new Error("refusing to use a non-absolute private staging path");
  }
  const resolved = resolve(stageRoot);
  if (
    dirname(resolved) !== resolve(PLUGIN_ROOT) ||
    !basename(resolved).startsWith(PRIVATE_STAGE_PREFIX)
  ) {
    throw new Error("refusing to clean an unrecognized private staging path");
  }
  const metadata = lstatIfPresent(resolved);
  if (metadata === null) return resolved;
  if (metadata.isSymbolicLink() || !metadata.isDirectory()) {
    throw new Error("refusing to clean a non-directory private staging path");
  }
  const marker = join(resolved, PRIVATE_STAGE_MARKER);
  const markerMetadata = lstatIfPresent(marker);
  if (
    markerMetadata === null ||
    markerMetadata.isSymbolicLink() ||
    !markerMetadata.isFile() ||
    readFileSync(marker, "utf8") !== PRIVATE_STAGE_MARKER_TEXT
  ) {
    throw new Error("refusing to clean a private stage without its ownership marker");
  }
  return resolved;
}

function assertPrivateStageContents(stageRoot, expectedPayloadNames) {
  const owned = assertOwnedPrivateStage(stageRoot);
  const expected = new Set([PRIVATE_STAGE_MARKER, ...expectedPayloadNames]);
  const entries = readdirSync(owned, { withFileTypes: true }).sort((left, right) =>
    left.name.localeCompare(right.name),
  );
  const observed = new Set(entries.map((entry) => entry.name));
  const differences = [];
  for (const entry of entries) {
    if (!expected.has(entry.name)) {
      differences.push(`${entry.name}: unexpected ${entryKind(entry)}`);
      continue;
    }
    if (entry.name === PRIVATE_STAGE_MARKER) {
      if (entry.isSymbolicLink() || !entry.isFile()) {
        differences.push(`${entry.name}: ownership marker is not a regular file`);
      }
    } else if (entry.isSymbolicLink() || !entry.isDirectory()) {
      differences.push(`${entry.name}: expected non-symlink directory`);
    }
  }
  for (const name of [...expected].sort()) {
    if (!observed.has(name)) differences.push(`${name}: missing from private stage`);
  }
  if (differences.length > 0) {
    throw new Error(
      `private stage contents are not the owned generation inventory: ${differences.join("; ")}`,
    );
  }
  return owned;
}

function sameFileIdentity(left, right) {
  return (
    left.dev === right.dev &&
    left.ino === right.ino &&
    left.size === right.size &&
    left.mtimeMs === right.mtimeMs
  );
}

function captureTreeSnapshot(root, label) {
  const rootMetadata = lstatIfPresent(root);
  if (rootMetadata === null) {
    return Object.freeze({ absent: true, digest: null, entryCount: 0 });
  }
  if (rootMetadata.isSymbolicLink() || !rootMetadata.isDirectory()) {
    throw new Error(`${label} is not a snapshot-safe non-symlink directory`);
  }

  const digest = createHash("sha256");
  let entryCount = 0;
  const visit = (directory, prefix) => {
    const before = readdirSync(directory, { withFileTypes: true }).sort((left, right) =>
      left.name.localeCompare(right.name),
    );
    for (const entry of before) {
      const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
      const path = join(directory, entry.name);
      const metadata = lstatSync(path);
      if (metadata.isSymbolicLink()) {
        throw new Error(`${label}/${relative} is a symlink or junction`);
      }
      if (metadata.isDirectory()) {
        digest.update("directory\0", "utf8");
        digest.update(relative, "utf8");
        digest.update("\0", "utf8");
        entryCount += 1;
        visit(path, relative);
      } else if (metadata.isFile()) {
        const bytes = readFileSync(path);
        const afterRead = lstatSync(path);
        if (!afterRead.isFile() || !sameFileIdentity(metadata, afterRead)) {
          throw new Error(`${label}/${relative} changed while it was being snapshotted`);
        }
        digest.update("file\0", "utf8");
        digest.update(relative, "utf8");
        digest.update("\0", "utf8");
        digest.update(sha256Bytes(bytes), "utf8");
        digest.update("\0", "utf8");
        entryCount += 1;
      } else {
        throw new Error(`${label}/${relative} is a special entry`);
      }
    }
    const after = readdirSync(directory).sort((left, right) =>
      left.localeCompare(right),
    );
    const beforeNames = before.map((entry) => entry.name);
    if (JSON.stringify(beforeNames) !== JSON.stringify(after)) {
      throw new Error(`${label}/${prefix || "."} changed while it was being snapshotted`);
    }
  };
  visit(root, "");
  const rootAfter = lstatSync(root);
  if (!rootAfter.isDirectory() || !sameFileIdentity(rootMetadata, rootAfter)) {
    throw new Error(`${label} changed while it was being snapshotted`);
  }
  return Object.freeze({
    absent: false,
    digest: digest.digest("hex"),
    entryCount,
  });
}

function snapshotsEqual(left, right) {
  return (
    left.absent === right.absent &&
    left.digest === right.digest &&
    left.entryCount === right.entryCount
  );
}

function captureGenerationSnapshots(distRoot, runtimeRoot, label) {
  return Object.freeze({
    dist: captureTreeSnapshot(distRoot, `${label} dist`),
    runtime: captureTreeSnapshot(runtimeRoot, `${label} runtime`),
  });
}

function generationSnapshotDrift(before, after, label) {
  const drift = [];
  if (!snapshotsEqual(before.dist, after.dist)) {
    drift.push(`${label} dist changed during verification`);
  }
  if (!snapshotsEqual(before.runtime, after.runtime)) {
    drift.push(`${label} runtime changed during verification`);
  }
  return drift;
}

function assertTreeSnapshot(root, expected, label) {
  const observed = captureTreeSnapshot(root, label);
  if (!snapshotsEqual(observed, expected)) {
    throw new Error(`${label} changed after its validated snapshot`);
  }
  return observed;
}

function cleanupPrivateStage(stageRoot) {
  const owned = assertOwnedPrivateStage(stageRoot);
  if (lstatIfPresent(owned) === null) return;
  const entries = readdirSync(owned).sort();
  if (entries.length !== 1 || entries[0] !== PRIVATE_STAGE_MARKER) {
    throw new Error(
      `private stage still contains generated payload and was retained at ${owned}`,
    );
  }
  unlinkSync(join(owned, PRIVATE_STAGE_MARKER));
  rmdirSync(owned);
}

function prepareDistPayloadFromBytes(
  copied,
  foundryKernelFiles,
  pluginHostFiles,
) {
  const closedFoundryKernelFiles = Object.freeze([...foundryKernelFiles]);
  const closedPluginHostFiles = Object.freeze([...pluginHostFiles]);
  const payloadKernelFiles = closedFoundryKernelFiles.map((file) =>
    immutableExpectedFile(
      `${FOUNDRY_KERNEL_OUTPUT}/${file.relative}`,
      expectedFileBytes(file),
    ),
  );
  const payloadPluginHostFiles = closedPluginHostFiles.map((file) =>
    immutableExpectedFile(
      `${PLUGIN_HOST_OUTPUT}/${file.relative}`,
      expectedFileBytes(file),
    ),
  );
  const files = [...copied, ...payloadKernelFiles, ...payloadPluginHostFiles];
  const manifestFiles = {};
  for (const file of files) {
    manifestFiles[file.relative] = `sha256:${file.sha256}`;
  }

  const descriptorSource = requiredExpectedFile(
    closedPluginHostFiles,
    "mcp/generated/tool-descriptors.json",
    "plugin-host closure",
  );
  const canonicalDescriptorBytes = expectedFileBytes(descriptorSource);
  const canonical = JSON.parse(canonicalDescriptorBytes.toString("utf8"));
  const { generated_from: _provenance, ...packaged } = canonical;
  const descriptor = immutableExpectedFile(
    "tool-descriptors.json",
    Buffer.from(`${JSON.stringify(packaged, null, 2)}\n`, "utf8"),
  );
  files.push(descriptor);
  manifestFiles[descriptor.relative] = `sha256:${descriptor.sha256}`;

  return Object.freeze({
    files: Object.freeze(files),
    foundryKernelFiles: closedFoundryKernelFiles,
    manifestFiles: Object.freeze(manifestFiles),
    pluginHostFiles: closedPluginHostFiles,
  });
}

function prepareDistPayload() {
  const copied = COPIED.map((relative) =>
    immutableExpectedFile(relative, readFileSync(join(SOURCE_DIR, relative))),
  );
  const foundryKernelFiles = FOUNDRY_KERNEL_FILES.map((relative) =>
    immutableExpectedFile(
      relative,
      readStableFileBytes(
        join(REPOSITORY_ROOT, FOUNDRY_KERNEL_SOURCE, relative),
        `${FOUNDRY_KERNEL_SOURCE}/${relative}`,
      ),
    ),
  );
  const pluginHostFiles = PLUGIN_HOST_FILES.map((relative) =>
    immutableExpectedFile(
      relative,
      readStableFileBytes(
        join(REPOSITORY_ROOT, PLUGIN_HOST_SOURCE, relative),
        `${PLUGIN_HOST_SOURCE}/${relative}`,
      ),
    ),
  );
  return prepareDistPayloadFromBytes(
    copied,
    foundryKernelFiles,
    pluginHostFiles,
  );
}

function readStableFileBytes(path, label) {
  const before = lstatSync(path);
  if (before.isSymbolicLink() || !before.isFile()) {
    throw new Error(`${label} is not a regular file`);
  }
  const bytes = readFileSync(path);
  const after = lstatSync(path);
  if (!after.isFile() || !sameFileIdentity(before, after)) {
    throw new Error(`${label} changed while it was being read`);
  }
  return bytes;
}

function expectedTreeDirectories(expectedFiles) {
  const directories = new Set();
  for (const file of expectedFiles) {
    const parts = file.relative.split("/");
    for (let depth = 1; depth < parts.length; depth += 1) {
      directories.add(parts.slice(0, depth).join("/"));
    }
  }
  return directories;
}

function verifyClosedFileTree(
  root,
  expectedFiles,
  label,
  expectedSource = "pinned HEAD",
) {
  const drift = [];
  const expectedByPath = new Map();
  for (const file of expectedFiles) {
    if (expectedByPath.has(file.relative)) {
      throw new BuildRefusedError(`${label}: duplicate expected file path`);
    }
    expectedByPath.set(file.relative, file);
  }
  const expectedDirectories = expectedTreeDirectories(expectedFiles);
  let rootMetadata;
  try {
    rootMetadata = lstatIfPresent(root);
  } catch {
    return [`${label}: output root could not be inspected`];
  }
  if (rootMetadata === null) return [`${label}: output root is missing`];
  if (rootMetadata.isSymbolicLink() || !rootMetadata.isDirectory()) {
    return [`${label}: output root is not a non-symlink directory`];
  }

  const observedFiles = new Set();
  const observedDirectories = new Set();
  const pending = [[root, ""]];
  while (pending.length > 0) {
    const [directory, prefix] = pending.pop();
    let entries;
    try {
      entries = readdirSync(directory, { withFileTypes: true }).sort((left, right) =>
        left.name.localeCompare(right.name),
      );
    } catch {
      drift.push(`${label}/${prefix || "."}: directory could not be enumerated`);
      continue;
    }
    for (const entry of entries) {
      const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
      const path = join(directory, entry.name);
      let metadata;
      try {
        metadata = lstatSync(path);
      } catch {
        drift.push(`${label}/${relative}: entry could not be inspected`);
        continue;
      }
      if (metadata.isSymbolicLink()) {
        drift.push(`${label}/${relative}: symlink or junction is not allowed`);
      } else if (metadata.isDirectory()) {
        if (!expectedDirectories.has(relative)) {
          drift.push(`${label}/${relative}: unexpected directory`);
        } else {
          observedDirectories.add(relative);
          pending.push([path, relative]);
        }
      } else if (metadata.isFile()) {
        const expected = expectedByPath.get(relative);
        if (!expected) {
          drift.push(`${label}/${relative}: unexpected file`);
          continue;
        }
        observedFiles.add(relative);
        if (expected.contentBase64 === null) continue;
        let actual;
        try {
          actual = readStableFileBytes(path, `${label}/${relative}`);
        } catch {
          drift.push(`${label}/${relative}: file could not be read stably`);
          continue;
        }
        if (!actual.equals(expectedFileBytes(expected))) {
          drift.push(`${label}/${relative}: bytes differ from ${expectedSource}`);
        }
      } else {
        drift.push(`${label}/${relative}: special entry is not allowed`);
      }
    }
  }

  for (const relative of [...expectedDirectories].sort()) {
    if (!observedDirectories.has(relative)) {
      drift.push(`${label}/${relative}: required directory is missing`);
    }
  }
  for (const relative of [...expectedByPath.keys()].sort()) {
    if (!observedFiles.has(relative)) {
      drift.push(`${label}/${relative}: required file is missing`);
    }
  }
  return drift;
}

function pythonRequirementAtLeast312(value) {
  if (typeof value !== "string") return false;
  const match = /^>=\s*(\d+)\.(\d+)(?:\.(\d+))?$/u.exec(value);
  if (!match) return false;
  const major = Number(match[1]);
  const minor = Number(match[2]);
  return major > 3 || (major === 3 && minor >= 12);
}

function verifyRuntimeManifest(manifestBytes, releaseClosure) {
  const drift = [];
  const manifestText = manifestBytes.toString("utf8");
  if (!Buffer.from(manifestText, "utf8").equals(manifestBytes)) {
    return ["release python runtime/runtime-manifest.json: invalid UTF-8"];
  }
  let manifest;
  try {
    manifest = JSON.parse(manifestText);
  } catch {
    return ["release python runtime/runtime-manifest.json: invalid JSON"];
  }
  if (manifest === null || typeof manifest !== "object" || Array.isArray(manifest)) {
    return ["release python runtime/runtime-manifest.json: expected an object"];
  }

  const expectedEntries = releaseClosure.pythonManifestEntries
    .map((entry) => JSON.stringify([entry.source, entry.path, entry.sha256]))
    .sort();
  const actualEntries = [];
  let validEntries = Array.isArray(manifest.files);
  if (validEntries) {
    for (const entry of manifest.files) {
      if (
        entry === null ||
        typeof entry !== "object" ||
        Array.isArray(entry) ||
        typeof entry.source !== "string" ||
        typeof entry.path !== "string" ||
        typeof entry.sha256 !== "string"
      ) {
        validEntries = false;
        break;
      }
      actualEntries.push(JSON.stringify([entry.source, entry.path, entry.sha256]));
    }
  }
  actualEntries.sort();
  if (
    !validEntries ||
    actualEntries.length !== new Set(actualEntries).size ||
    JSON.stringify(actualEntries) !== JSON.stringify(expectedEntries)
  ) {
    drift.push(
      "release python runtime/runtime-manifest.json: source paths and hashes do not match pinned HEAD",
    );
  }
  if (manifest.source_commit !== releaseClosure.headOid) {
    drift.push(
      "release python runtime/runtime-manifest.json: source_commit does not match pinned HEAD",
    );
  }
  if (!Array.isArray(manifest.dirty_inputs) || manifest.dirty_inputs.length !== 0) {
    drift.push(
      "release python runtime/runtime-manifest.json: dirty_inputs must be empty",
    );
  }
  if (!pythonRequirementAtLeast312(manifest.python_requirement)) {
    drift.push(
      "release python runtime/runtime-manifest.json: python_requirement must be >=3.12",
    );
  }
  return drift;
}

function verifyReleaseGeneratedClosure(distRoot, runtimeRoot, releaseClosure) {
  const drift = [
    ...verifyClosedFileTree(
      join(distRoot, FOUNDRY_KERNEL_OUTPUT),
      releaseClosure.distPayload.foundryKernelFiles,
      "release foundry-kernel",
    ),
    ...verifyClosedFileTree(
      join(distRoot, PLUGIN_HOST_OUTPUT),
      releaseClosure.distPayload.pluginHostFiles,
      "release plugin-host",
    ),
    ...verifyClosedFileTree(
      join(distRoot, "workspace-map"),
      releaseClosure.workspaceFiles,
      "release workspace-map",
    ),
    ...verifyClosedFileTree(
      runtimeRoot,
      releaseClosure.runtimeFiles,
      "release python runtime",
    ),
  ];
  try {
    const manifestBytes = readStableFileBytes(
      join(runtimeRoot, "runtime-manifest.json"),
      "release python runtime/runtime-manifest.json",
    );
    drift.push(...verifyRuntimeManifest(manifestBytes, releaseClosure));
  } catch {
    drift.push(
      "release python runtime/runtime-manifest.json: file could not be read stably",
    );
  }
  return drift;
}

function bindRuntimeManifest(prepared, runtimeManifestBytes) {
  const runtimeManifestSha256 = `sha256:${sha256Bytes(runtimeManifestBytes)}`;

  const manifestText = `${JSON.stringify(
    {
      descriptor_source: "contracts/mcp/t01/tool-catalog.yaml",
      files: prepared.manifestFiles,
      runtime_manifest_sha256: runtimeManifestSha256,
      source:
        "plugins/epistemic-foundry/src + packages/foundry-kernel/src + packages/plugin-host/src",
    },
    null,
    2,
  )}\n`;
  return Object.freeze({
    ...prepared,
    manifestText,
    runtimeManifestSha256,
  });
}

function compareDistPayload(prepared, targetDist = DIST_DIR) {
  const drift = [];
  for (const file of prepared.files) {
    if (
      file.relative.startsWith(`${FOUNDRY_KERNEL_OUTPUT}/`) ||
      file.relative.startsWith(`${PLUGIN_HOST_OUTPUT}/`)
    ) {
      continue;
    }
    let bundled = null;
    try {
      bundled = readFileSync(join(targetDist, file.relative));
    } catch {
      drift.push(`${file.relative}: missing from payload`);
      continue;
    }
    if (!bundled.equals(expectedFileBytes(file))) {
      drift.push(`${file.relative}: payload differs from source`);
    }
  }
  let bundledManifest = null;
  try {
    bundledManifest = readFileSync(join(targetDist, "payload-manifest.json"));
  } catch {
    drift.push("payload-manifest.json: missing from payload");
  }
  if (
    bundledManifest !== null &&
    !bundledManifest.equals(Buffer.from(prepared.manifestText, "utf8"))
  ) {
    drift.push("payload-manifest.json: payload differs from source");
  }
  drift.push(
    ...verifyClosedFileTree(
      join(targetDist, FOUNDRY_KERNEL_OUTPUT),
      prepared.foundryKernelFiles,
      FOUNDRY_KERNEL_OUTPUT,
      "prepared source closure",
    ),
    ...verifyClosedFileTree(
      join(targetDist, PLUGIN_HOST_OUTPUT),
      prepared.pluginHostFiles,
      PLUGIN_HOST_OUTPUT,
      "prepared source closure",
    ),
  );
  return drift;
}

function writeDistBody(prepared, targetDist) {
  for (const file of prepared.files) {
    atomicWriteText(join(targetDist, file.relative), expectedFileBytes(file));
  }
}

function generationRoots(stageRoot, previousSnapshots, stagedSnapshots) {
  return [
    {
      backupRoot: join(stageRoot, PREVIOUS_DIST_NAME),
      finalRoot: DIST_DIR,
      label: "dist",
      previousSnapshot: previousSnapshots.dist,
      stagedRoot: join(stageRoot, "dist"),
      stagedSnapshot: stagedSnapshots.dist,
    },
    {
      backupRoot: join(stageRoot, PREVIOUS_RUNTIME_NAME),
      finalRoot: RUNTIME_DIR,
      label: "runtime",
      previousSnapshot: previousSnapshots.runtime,
      stagedRoot: join(stageRoot, "runtime"),
      stagedSnapshot: stagedSnapshots.runtime,
    },
  ];
}

function stagedGenerationSnapshots(
  stageRoot,
  prepared,
  releaseMode,
  executable,
  releaseClosure,
) {
  const targetDist = join(stageRoot, "dist");
  const targetRuntime = join(stageRoot, "runtime");
  const Failure = releaseClosure !== null ? BuildRefusedError : Error;
  let snapshotsBefore;
  try {
    snapshotsBefore = captureGenerationSnapshots(
      targetDist,
      targetRuntime,
      "staged generation before verification",
    );
  } catch (error) {
    throw new Failure(
      `staged generation snapshot A failed: ${error.message}`,
    );
  }

  const drift = [];
  try {
    assertPrivateStageContents(stageRoot, ["dist", "runtime"]);
  } catch (error) {
    drift.push(`private stage inventory: ${error.message}`);
  }
  const inventory = inspectDistInventory(targetDist);
  if (inventory.absent) drift.push("dist inventory: staged dist root is missing");
  drift.push(
    ...inventory.structuralErrors.map((error) => `dist inventory: ${error}`),
    ...inventory.missingMembers.map((error) => `dist inventory: ${error}`),
  );
  drift.push(...compareDistPayload(prepared, targetDist));
  const workspaceMap = buildWorkspaceMap("check", stageRoot);
  if (!workspaceMap.ok) drift.push(`workspace map: ${workspaceMap.output}`);
  const runtime = buildPythonRuntime(
    "check",
    releaseMode,
    executable,
    stageRoot,
  );
  if (!runtime.ok) drift.push(`python runtime: ${runtime.output}`);
  if (releaseClosure !== null) {
    drift.push(
      ...verifyReleaseGeneratedClosure(targetDist, targetRuntime, releaseClosure),
    );
  }
  let snapshotsAfter;
  try {
    snapshotsAfter = captureGenerationSnapshots(
      targetDist,
      targetRuntime,
      "staged generation after verification",
    );
  } catch (error) {
    throw new Failure(
      `staged generation snapshot B failed: ${error.message}`,
    );
  }
  drift.push(
    ...generationSnapshotDrift(
      snapshotsBefore,
      snapshotsAfter,
      "staged generation",
    ),
  );
  if (drift.length > 0) {
    const message = `staged generation verification failed: ${drift.join("; ")}`;
    throw new Failure(message);
  }
  return snapshotsAfter;
}

function rollbackGeneration(stageRoot, roots) {
  const errors = [];
  for (const root of [...roots].reverse()) {
    try {
      const staged = captureTreeSnapshot(root.stagedRoot, `rollback staged ${root.label}`);
      const final = captureTreeSnapshot(root.finalRoot, `rollback final ${root.label}`);
      if (!staged.absent) {
        if (!snapshotsEqual(staged, root.stagedSnapshot)) {
          throw new Error(`staged ${root.label} no longer matches the new generation`);
        }
        if (
          !final.absent &&
          !(
            !root.previousSnapshot.absent &&
            snapshotsEqual(final, root.previousSnapshot) &&
            lstatIfPresent(root.backupRoot) === null
          )
        ) {
          throw new Error(`final ${root.label} is occupied by an unrecognized tree`);
        }
      } else if (snapshotsEqual(final, root.stagedSnapshot)) {
        renameSync(root.finalRoot, root.stagedRoot);
        assertTreeSnapshot(
          root.stagedRoot,
          root.stagedSnapshot,
          `retained new ${root.label}`,
        );
        assertTreeSnapshot(
          root.finalRoot,
          { absent: true, digest: null, entryCount: 0 },
          `vacated final ${root.label}`,
        );
      } else {
        throw new Error(`new ${root.label} generation cannot be located for rollback`);
      }
    } catch (error) {
      errors.push(`${root.label} new-generation retention: ${error.message}`);
    }
  }

  for (const root of roots) {
    try {
      const final = captureTreeSnapshot(root.finalRoot, `rollback final ${root.label}`);
      const backup = captureTreeSnapshot(root.backupRoot, `rollback previous ${root.label}`);
      if (root.previousSnapshot.absent) {
        if (!final.absent || !backup.absent) {
          throw new Error(`previous ${root.label} was absent but a rollback path is occupied`);
        }
        continue;
      }
      if (snapshotsEqual(final, root.previousSnapshot) && backup.absent) continue;
      if (!final.absent || !snapshotsEqual(backup, root.previousSnapshot)) {
        throw new Error(`validated previous ${root.label} is not restorable without overwrite`);
      }
      renameSync(root.backupRoot, root.finalRoot);
      assertTreeSnapshot(
        root.finalRoot,
        root.previousSnapshot,
        `restored final ${root.label}`,
      );
      assertTreeSnapshot(
        root.backupRoot,
        { absent: true, digest: null, entryCount: 0 },
        `vacated previous ${root.label}`,
      );
    } catch (error) {
      errors.push(`${root.label} previous-generation restore: ${error.message}`);
    }
  }

  if (errors.length === 0) {
    try {
      assertPrivateStageContents(stageRoot, ["dist", "runtime"]);
      for (const root of roots) {
        assertTreeSnapshot(
          root.stagedRoot,
          root.stagedSnapshot,
          `retained new ${root.label}`,
        );
        assertTreeSnapshot(
          root.finalRoot,
          root.previousSnapshot,
          `restored final ${root.label}`,
        );
      }
    } catch (error) {
      errors.push(`rollback reconciliation: ${error.message}`);
    }
  }
  return errors;
}

function publishGeneration(
  stageRoot,
  previousSnapshots,
  stagedSnapshots,
  pinnedHeadOid = null,
) {
  const roots = generationRoots(stageRoot, previousSnapshots, stagedSnapshots);
  try {
    assertPrivateStageContents(stageRoot, ["dist", "runtime"]);
    for (const root of roots) {
      assertTreeSnapshot(
        root.finalRoot,
        root.previousSnapshot,
        `final ${root.label} before publication`,
      );
      assertTreeSnapshot(
        root.stagedRoot,
        root.stagedSnapshot,
        `staged ${root.label} before publication`,
      );
      if (lstatIfPresent(root.backupRoot) !== null) {
        throw new Error(`previous ${root.label} backup path is already occupied`);
      }
    }
    if (pinnedHeadOid !== null) assertPinnedHead(pinnedHeadOid);

    for (const root of roots) {
      if (root.previousSnapshot.absent) continue;
      renameSync(root.finalRoot, root.backupRoot);
      assertTreeSnapshot(
        root.backupRoot,
        root.previousSnapshot,
        `retained previous ${root.label}`,
      );
      assertTreeSnapshot(
        root.finalRoot,
        { absent: true, digest: null, entryCount: 0 },
        `vacated final ${root.label}`,
      );
    }

    // A release ref that moves while the old roots are being retained must
    // roll back before any pinned generation becomes active.
    if (pinnedHeadOid !== null) assertPinnedHead(pinnedHeadOid);
    for (const root of roots) {
      renameSync(root.stagedRoot, root.finalRoot);
      assertTreeSnapshot(
        root.finalRoot,
        root.stagedSnapshot,
        `published final ${root.label}`,
      );
      assertTreeSnapshot(
        root.stagedRoot,
        { absent: true, digest: null, entryCount: 0 },
        `vacated staged ${root.label}`,
      );
    }
    return roots;
  } catch (error) {
    const rollbackErrors = rollbackGeneration(stageRoot, roots);
    const rollback = rollbackErrors.length > 0
      ? `; rollback incomplete: ${rollbackErrors.join("; ")}`
      : "; both previous roots restored and the new generation was retained";
    const Failure = error instanceof BuildRefusedError ? BuildRefusedError : Error;
    throw new Failure(
      `generation publication failed: ${error.message}${rollback}; retained stage: ${stageRoot}`,
    );
  }
}

function cleanupPublishedGeneration(stageRoot, roots) {
  const remaining = new Set(
    roots
      .filter((root) => !root.previousSnapshot.absent)
      .map((root) => basename(root.backupRoot)),
  );
  assertPrivateStageContents(stageRoot, [...remaining]);
  for (const root of [...roots].reverse()) {
    if (root.previousSnapshot.absent) continue;
    assertPrivateStageContents(stageRoot, [...remaining]);
    assertTreeSnapshot(
      root.backupRoot,
      root.previousSnapshot,
      `cleanup previous ${root.label}`,
    );
    rmSync(root.backupRoot, { recursive: true, force: false });
    remaining.delete(basename(root.backupRoot));
  }
  assertPrivateStageContents(stageRoot, []);
  cleanupPrivateStage(stageRoot);
}

function printFailure(status, drift) {
  console.error(JSON.stringify({ drift, status }, null, 2));
  process.exitCode = 1;
}

function main() {
  const checkOnly = process.argv.includes("--check");
  const releaseMode = process.argv.includes("--release");
  const knownArguments = new Set(["--check", "--release"]);
  const unknownArguments = process.argv.slice(2).filter((argument) => !knownArguments.has(argument));
  if (unknownArguments.length > 0) {
    printFailure("BUILD_REFUSED", [`unknown arguments: ${unknownArguments.join(", ")}`]);
    return;
  }

  let releaseClosure = null;
  if (releaseMode) {
    const sourceStatus = releaseSourceStatus();
    if (!sourceStatus.ok) {
      printFailure("BUILD_REFUSED", [sourceStatus.output]);
      return;
    }
    try {
      const pinnedHeadOid = readHeadOid();
      releaseClosure = captureReleaseClosure(pinnedHeadOid);
    } catch (error) {
      printFailure("BUILD_REFUSED", [
        error instanceof BuildRefusedError
          ? error.message
          : "release closure: pinned inputs could not be prepared",
      ]);
      return;
    }
  }

  const python = configuredPythonExecutable();
  if (!python.ok) {
    console.error(`build failed: ${python.output}`);
    process.exitCode = 1;
    return;
  }

  let prepared;
  try {
    // Freeze every top-level dist byte before destination preflight or writes.
    prepared = releaseClosure === null
      ? prepareDistPayload()
      : releaseClosure.distPayload;
  } catch (error) {
    printFailure("BUILD_REFUSED", [`dist inputs: ${error.message}`]);
    return;
  }

  let finalSnapshotsBefore;
  try {
    finalSnapshotsBefore = captureGenerationSnapshots(
      DIST_DIR,
      RUNTIME_DIR,
      "final generation before verification",
    );
  } catch (error) {
    printFailure(checkOnly ? "DRIFTED" : "BUILD_REFUSED", [
      `final generation snapshot A failed: ${error.message}`,
    ]);
    return;
  }

  // All four destination preflights are read-only and finish before any
  // payload write: dist root, workspace-map, runtime root, runtime/python.
  const distInspection = inspectDistInventory();
  const workspacePreflight = buildWorkspaceMap("preflight");
  const runtimePreflight = buildPythonRuntime(
    "preflight",
    releaseMode,
    python.executable,
  );
  let runtimeAbsent = false;
  let runtimePresenceError = null;
  try {
    runtimeAbsent = lstatIfPresent(RUNTIME_DIR) === null;
  } catch (error) {
    runtimePresenceError = error.message;
  }

  const verificationErrors = distInspection.structuralErrors.map(
    (error) => `dist inventory: ${error}`,
  );
  if (checkOnly) {
    verificationErrors.push(
      ...distInspection.missingMembers.map(
        (error) => `dist inventory: ${error}`,
      ),
    );
  }
  if (!workspacePreflight.ok) {
    verificationErrors.push(
      `workspace-map preflight: ${workspacePreflight.output}`,
    );
  }
  if (!runtimePreflight.ok) {
    verificationErrors.push(
      `runtime/runtime-python preflight: ${runtimePreflight.output}`,
    );
  }
  if (runtimePresenceError !== null) {
    verificationErrors.push(`runtime root: ${runtimePresenceError}`);
  }
  if (checkOnly && distInspection.absent) {
    verificationErrors.push("dist inventory: dist output root is missing");
  }
  if (checkOnly && runtimeAbsent) {
    verificationErrors.push("runtime inventory: runtime output root is missing");
  }

  let checkedPrepared = null;
  if (checkOnly) {
    const workspaceMap = buildWorkspaceMap("check");
    if (!workspaceMap.ok) {
      verificationErrors.push(`workspace map: ${workspaceMap.output}`);
    }
    const runtime = buildPythonRuntime("check", releaseMode, python.executable);
    if (!runtime.ok) {
      verificationErrors.push(`python runtime: ${runtime.output}`);
    }
    try {
      checkedPrepared = bindRuntimeManifest(
        prepared,
        readStableFileBytes(
          join(RUNTIME_DIR, "runtime-manifest.json"),
          "runtime/runtime-manifest.json",
        ),
      );
      verificationErrors.push(...compareDistPayload(checkedPrepared));
      if (releaseClosure !== null) {
        verificationErrors.push(
          ...verifyReleaseGeneratedClosure(DIST_DIR, RUNTIME_DIR, releaseClosure),
        );
      }
    } catch (error) {
      verificationErrors.push(`runtime manifest binding: ${error.message}`);
    }
  }

  let finalSnapshotsAfter = null;
  try {
    finalSnapshotsAfter = captureGenerationSnapshots(
      DIST_DIR,
      RUNTIME_DIR,
      "final generation after verification",
    );
  } catch (error) {
    verificationErrors.push(
      `final generation snapshot B failed: ${error.message}`,
    );
  }
  if (finalSnapshotsAfter !== null) {
    verificationErrors.push(
      ...generationSnapshotDrift(
        finalSnapshotsBefore,
        finalSnapshotsAfter,
        "final generation",
      ),
    );
  }
  if (verificationErrors.length > 0) {
    printFailure(
      checkOnly ? "DRIFTED" : "BUILD_REFUSED",
      verificationErrors,
    );
    return;
  }
  if (checkOnly) {
    console.log(JSON.stringify({
      file_count: Object.keys(checkedPrepared.manifestFiles).length,
      status: "CURRENT",
    }));
    return;
  }

  const previousSnapshots = finalSnapshotsAfter;

  let privateStageRoot = null;
  let publicationAttempted = false;
  try {
    privateStageRoot = createPrivateStage();
    const targetDist = join(privateStageRoot, "dist");
    writeDistBody(prepared, targetDist);
    const workspaceMap = buildWorkspaceMap("build", privateStageRoot);
    if (!workspaceMap.ok) {
      throw new Error(`workspace map: ${workspaceMap.output}`);
    }
    const runtime = buildPythonRuntime(
      "build",
      releaseMode,
      python.executable,
      privateStageRoot,
    );
    if (!runtime.ok) throw new Error(`python runtime: ${runtime.output}`);

    const boundPrepared = bindRuntimeManifest(
      prepared,
      readStableFileBytes(
        join(privateStageRoot, "runtime", "runtime-manifest.json"),
        "staged runtime/runtime-manifest.json",
      ),
    );

    // This is the dist commit marker. It is written only after workspace-map
    // and runtime succeeded, and it is the final write in the dist subtree.
    atomicWriteText(
      join(targetDist, "payload-manifest.json"),
      boundPrepared.manifestText,
    );
    const stagedSnapshots = stagedGenerationSnapshots(
      privateStageRoot,
      boundPrepared,
      releaseMode,
      python.executable,
      releaseClosure,
    );

    if (releaseClosure !== null) assertPinnedHead(releaseClosure.headOid);
    publicationAttempted = true;
    const publishedRoots = publishGeneration(
      privateStageRoot,
      previousSnapshots,
      stagedSnapshots,
      releaseClosure?.headOid ?? null,
    );
    let stagingCleanup = null;
    try {
      cleanupPublishedGeneration(privateStageRoot, publishedRoots);
      privateStageRoot = null;
    } catch (error) {
      stagingCleanup = error.message;
    }
    if (stagingCleanup !== null) {
      console.error(JSON.stringify({
        final_generation: "PUBLISHED",
        retained_stage: privateStageRoot,
        staging_cleanup: stagingCleanup,
        status: "BUILD_CLEANUP_FAILED_AFTER_PUBLISH",
      }, null, 2));
      process.exitCode = 1;
      return;
    }
    console.log(JSON.stringify({
      file_count: Object.keys(boundPrepared.manifestFiles).length,
      runtime: runtime.output,
      status: "BUILT",
    }));
  } catch (error) {
    const drift = [error.message];
    if (privateStageRoot !== null && !publicationAttempted) {
      try {
        cleanupPrivateStage(privateStageRoot);
        privateStageRoot = null;
      } catch (cleanupError) {
        drift.push(`private staging: ${cleanupError.message}`);
      }
    }
    printFailure(
      error instanceof BuildRefusedError ? "BUILD_REFUSED" : "BUILD_FAILED",
      drift,
    );
  }
}

main();
