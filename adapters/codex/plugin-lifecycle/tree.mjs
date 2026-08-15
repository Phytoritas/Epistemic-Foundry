import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {
  FAILURE,
  LIMITS,
  STATUS,
  canonicalJson,
  compareUtf8,
  fail,
  hashJson,
  strictVersion,
} from "./core.mjs";

function pathKey(value) {
  const resolved = path.resolve(value).normalize("NFC");
  return process.platform === "win32" || process.platform === "darwin"
    ? resolved.toLowerCase()
    : resolved;
}

function ordinaryDirectory(root, label) {
  if (!path.isAbsolute(root) || path.resolve(root) !== path.normalize(root)) {
    fail(FAILURE.UNSAFE_PATH, `${label} is not a canonical absolute path`);
  }
  if (process.platform === "win32" && (/^(?:\\\\|\/\/)/u.test(root) || path.parse(root).root.startsWith("\\\\"))) {
    fail(FAILURE.UNSAFE_PATH, `${label} cannot be a UNC or network path`);
  }
  const stat = fs.lstatSync(root, { bigint: true });
  if (stat.isSymbolicLink() || !stat.isDirectory()) fail(FAILURE.UNSAFE_PATH, `${label} is not ordinary`);
  const real = fs.realpathSync.native(root);
  if (pathKey(real) !== pathKey(root)) fail(FAILURE.UNSAFE_PATH, `${label} resolves through an alias`);
  return real;
}

function signature(stat) {
  return [stat.dev, stat.ino, stat.mode, stat.nlink, stat.size, stat.mtimeNs, stat.ctimeNs].join(":");
}

function checkDeadline(deadlineMs) {
  if (Number.isFinite(deadlineMs) && Date.now() > deadlineMs) {
    fail(FAILURE.RESOURCE_LIMIT, "lifecycle operation deadline exceeded");
  }
}

function safeSegment(segment) {
  if (
    segment.length === 0 ||
    segment === "." ||
    segment === ".." ||
    segment !== segment.normalize("NFC") ||
    /[\u0000-\u001f\u007f/\\:]/u.test(segment) ||
    /[ .]$/u.test(segment)
  ) {
    fail(FAILURE.PACKAGE_INVALID, "unsafe tree path segment");
  }
}

function streamFile(source, destination, maxBytes, collectBytes = false, deadlineMs = null) {
  checkDeadline(deadlineMs);
  const before = fs.lstatSync(source, { bigint: true });
  if (before.isSymbolicLink() || !before.isFile() || before.nlink !== 1n) {
    fail(FAILURE.PACKAGE_INVALID, "linked, hardlinked, or special file");
  }
  if (before.size > BigInt(maxBytes)) fail(FAILURE.RESOURCE_LIMIT, "file exceeds the configured limit");
  const sourceFd = fs.openSync(source, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0));
  let destinationFd;
  const hash = createHash("sha256");
  const chunks = collectBytes ? [] : null;
  let total = 0;
  try {
    const openedBefore = fs.fstatSync(sourceFd, { bigint: true });
    if (openedBefore.dev !== before.dev || openedBefore.ino !== before.ino) {
      fail(FAILURE.PACKAGE_DRIFT, "file identity changed before read");
    }
    if (destination !== null) destinationFd = fs.openSync(destination, "wx", Number(before.mode & 0o777n));
    const buffer = Buffer.allocUnsafe(64 * 1024);
    for (;;) {
      checkDeadline(deadlineMs);
      const count = fs.readSync(sourceFd, buffer, 0, buffer.length, null);
      if (count === 0) break;
      total += count;
      if (total > maxBytes) fail(FAILURE.RESOURCE_LIMIT, "file exceeded its declared bound");
      const slice = buffer.subarray(0, count);
      hash.update(slice);
      if (destinationFd !== undefined) {
        let written = 0;
        while (written < slice.length) {
          const countWritten = fs.writeSync(destinationFd, slice, written, slice.length - written);
          if (countWritten === 0) fail(FAILURE.IO_FAILURE, "streaming copy made no progress");
          written += countWritten;
        }
      }
      if (chunks !== null) chunks.push(Buffer.from(slice));
    }
    if (destinationFd !== undefined) fs.fsyncSync(destinationFd);
    const openedAfter = fs.fstatSync(sourceFd, { bigint: true });
    const after = fs.lstatSync(source, { bigint: true });
    if (
      signature(before) !== signature(after) ||
      signature(openedBefore) !== signature(openedAfter) ||
      after.dev !== openedAfter.dev ||
      after.ino !== openedAfter.ino
    ) {
      fail(FAILURE.PACKAGE_DRIFT, "file changed during streaming read");
    }
    return {
      byte_size: total,
      sha256: `sha256:${hash.digest("hex")}`,
      mode: Number(after.mode & 0o777n),
      bytes: chunks === null ? null : Buffer.concat(chunks, total),
    };
  } finally {
    if (destinationFd !== undefined) fs.closeSync(destinationFd);
    fs.closeSync(sourceFd);
  }
}

function inventoryPass(root, limits) {
  const entries = [];
  const aliases = new Set();
  let files = 0;
  let entryCount = 0;
  let totalBytes = 0;
  const visit = (directory, relative, depth) => {
    checkDeadline(limits.deadlineMs);
    if (depth > limits.maxDepth) fail(FAILURE.RESOURCE_LIMIT, "tree depth exceeded");
    const before = fs.lstatSync(directory, { bigint: true });
    if (before.isSymbolicLink() || !before.isDirectory()) fail(FAILURE.PACKAGE_INVALID, "non-ordinary directory");
    const children = fs.readdirSync(directory, { withFileTypes: true });
    if (entryCount + children.length > limits.maxEntries) fail(FAILURE.RESOURCE_LIMIT, "tree entry count exceeded");
    children.sort((a, b) => compareUtf8(a.name, b.name));
    for (const child of children) {
      checkDeadline(limits.deadlineMs);
      entryCount += 1;
      if (entryCount > limits.maxEntries) fail(FAILURE.RESOURCE_LIMIT, "tree entry count exceeded");
      safeSegment(child.name);
      const childRelative = relative === "" ? child.name : `${relative}/${child.name}`;
      const alias = childRelative
        .split("/")
        .map((part) => part.normalize("NFC").toLowerCase())
        .join("/");
      if (aliases.has(alias)) fail(FAILURE.PACKAGE_INVALID, "tree contains a path alias");
      aliases.add(alias);
      const absolute = path.join(directory, child.name);
      const stat = fs.lstatSync(absolute, { bigint: true });
      if (stat.isSymbolicLink()) fail(FAILURE.PACKAGE_INVALID, "tree contains a symlink or junction");
      if (stat.isDirectory()) {
        entries.push({ path: childRelative, type: "directory", mode: Number(stat.mode & 0o777n), byte_size: null, sha256: null });
        visit(absolute, childRelative, depth + 1);
        continue;
      }
      files += 1;
      if (files > limits.maxFiles) fail(FAILURE.RESOURCE_LIMIT, "tree file count exceeded");
      const observed = streamFile(absolute, null, limits.maxFileBytes, false, limits.deadlineMs);
      totalBytes += observed.byte_size;
      if (totalBytes > limits.maxTreeBytes) fail(FAILURE.RESOURCE_LIMIT, "tree byte limit exceeded");
      entries.push({
        path: childRelative,
        type: "file",
        mode: observed.mode,
        byte_size: observed.byte_size,
        sha256: observed.sha256,
      });
    }
    const after = fs.lstatSync(directory, { bigint: true });
    if (signature(before) !== signature(after)) fail(FAILURE.PACKAGE_DRIFT, "directory changed during inventory");
  };
  visit(root, "", 0);
  entries.sort((a, b) => compareUtf8(a.path, b.path));
  const inventoryBytes = Buffer.byteLength(canonicalJson(entries), "utf8");
  if (inventoryBytes > limits.maxInventoryBytes) fail(FAILURE.RESOURCE_LIMIT, "tree inventory byte limit exceeded");
  return {
    inventory: entries,
    entry_count: entryCount,
    file_count: files,
    byte_size: totalBytes,
    inventory_bytes: inventoryBytes,
    tree_hash: hashJson("PLUGIN_LIFECYCLE_V3_TREE", entries),
  };
}

function manifestPath(raw, label) {
  if (typeof raw !== "string" || raw.length === 0 || raw.includes("\\") || path.posix.isAbsolute(raw)) {
    fail(FAILURE.PACKAGE_INVALID, `${label} is not package-relative`);
  }
  let value = raw.startsWith("./") ? raw.slice(2) : raw;
  if (value.endsWith("/")) value = value.slice(0, -1);
  const normalized = path.posix.normalize(value);
  if (normalized !== value || normalized === "." || normalized === ".." || normalized.startsWith("../")) {
    fail(FAILURE.PACKAGE_INVALID, `${label} is not canonical`);
  }
  for (const segment of normalized.split("/")) safeSegment(segment);
  return normalized;
}

export function inspectTree(root, { pluginName = null, limits = LIMITS } = {}) {
  const canonicalRoot = ordinaryDirectory(root, "tree root");
  const first = inventoryPass(canonicalRoot, limits);
  let manifest = null;
  let manifestHash = null;
  let hasHooks = false;
  if (pluginName !== null) {
    const relative = ".codex-plugin/plugin.json";
    const entry = first.inventory.find((item) => item.path === relative && item.type === "file");
    if (entry === undefined || entry.byte_size > limits.maxManifestBytes) {
      fail(FAILURE.PACKAGE_INVALID, "bounded plugin manifest is missing");
    }
    const captured = streamFile(
      path.join(canonicalRoot, ".codex-plugin", "plugin.json"),
      null,
      limits.maxManifestBytes,
      true,
      limits.deadlineMs,
    );
    if (captured.sha256 !== entry.sha256) fail(FAILURE.PACKAGE_DRIFT, "manifest changed during inspection");
    try {
      manifest = JSON.parse(captured.bytes.toString("utf8"));
    } catch {
      fail(FAILURE.PACKAGE_INVALID, "plugin manifest is not JSON");
    }
    if (manifest === null || typeof manifest !== "object" || Array.isArray(manifest) || manifest.name !== pluginName) {
      fail(FAILURE.PACKAGE_INVALID, "manifest name does not match the exact selector");
    }
    strictVersion(manifest.version);
    const inventoryPaths = new Set(first.inventory.map((item) => item.path));
    for (const [label, raw] of [
      ["skills", manifest.skills],
      ["hooks", manifest.hooks],
      ["mcpServers", manifest.mcpServers],
      ["interface.composerIcon", manifest.interface?.composerIcon],
      ["interface.logo", manifest.interface?.logo],
    ]) {
      if (raw === undefined) continue;
      const resolved = manifestPath(raw, label);
      if (!inventoryPaths.has(resolved) && !first.inventory.some((item) => item.path.startsWith(`${resolved}/`))) {
        fail(FAILURE.PACKAGE_INVALID, `${label} does not resolve inside the package`);
      }
      if (label === "hooks") hasHooks = true;
    }
    manifestHash = captured.sha256;
  }
  const second = inventoryPass(canonicalRoot, limits);
  if (first.tree_hash !== second.tree_hash || canonicalJson(first.inventory) !== canonicalJson(second.inventory)) {
    fail(FAILURE.PACKAGE_DRIFT, "tree changed during inspection");
  }
  return {
    root: canonicalRoot,
    plugin_name: pluginName,
    plugin_version: manifest?.version ?? null,
    manifest_hash: manifestHash,
    has_hooks: hasHooks,
    hook_subject_hash: hasHooks ? first.tree_hash : null,
    ...first,
  };
}

function sameTree(left, right) {
  return left.tree_hash === right.tree_hash && canonicalJson(left.inventory) === canonicalJson(right.inventory);
}

function durableFileSync(file) {
  const before = fs.lstatSync(file, { bigint: true });
  if (before.isSymbolicLink() || !before.isFile() || before.nlink !== 1n) {
    fail(FAILURE.STATE_CORRUPT, "durable publication contains a linked or special file");
  }
  let fd;
  try {
    fd = fs.openSync(file, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0));
    const opened = fs.fstatSync(fd, { bigint: true });
    if (opened.dev !== before.dev || opened.ino !== before.ino) {
      fail(FAILURE.PACKAGE_DRIFT, "published file identity changed before durable sync");
    }
    fs.fsyncSync(fd);
    const after = fs.fstatSync(fd, { bigint: true });
    if (signature(opened) !== signature(after)) {
      fail(FAILURE.PACKAGE_DRIFT, "published file changed during durable sync");
    }
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
  }
}

export function durableFsyncDirectory(directory) {
  const canonical = ordinaryDirectory(directory, "durable directory boundary");
  let fd;
  try {
    fd = fs.openSync(canonical, fs.constants.O_RDONLY | (fs.constants.O_DIRECTORY ?? 0));
    fs.fsyncSync(fd);
  } catch (cause) {
    if (cause?.code === undefined && cause?.name === "LifecycleError") throw cause;
    fail(
      FAILURE.HOST_UNSUPPORTED,
      "the host cannot durably synchronize a lifecycle directory boundary",
      STATUS.UNSUPPORTED,
    );
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
  }
}

function durableSyncParents(directory) {
  const parent = path.dirname(directory);
  durableFsyncDirectory(parent);
  const grandparent = path.dirname(parent);
  if (pathKey(grandparent) !== pathKey(parent)) durableFsyncDirectory(grandparent);
}

export function durableSyncTree(root, limits = LIMITS, syncParents = true) {
  const before = inspectTree(root, { limits });
  for (const entry of before.inventory) {
    if (entry.type !== "file") continue;
    durableFileSync(path.join(root, ...entry.path.split("/")));
  }
  const directories = before.inventory
    .filter((entry) => entry.type === "directory")
    .sort((left, right) => right.path.split("/").length - left.path.split("/").length);
  for (const entry of directories) {
    durableFsyncDirectory(path.join(root, ...entry.path.split("/")));
  }
  durableFsyncDirectory(root);
  if (syncParents) durableSyncParents(root);
  const after = inspectTree(root, { limits });
  if (!sameTree(before, after)) fail(FAILURE.PACKAGE_DRIFT, "published tree changed during durable sync");
  return after;
}

export function durablePublishDirectory(stageRoot, finalRoot, limits = LIMITS) {
  if (fs.existsSync(finalRoot)) fail(FAILURE.STATE_CORRUPT, "durable publication destination already exists");
  const staged = durableSyncTree(stageRoot, limits, false);
  const sourceParent = path.dirname(stageRoot);
  const destinationParent = path.dirname(finalRoot);
  durableFsyncDirectory(sourceParent);
  if (pathKey(destinationParent) !== pathKey(sourceParent)) durableFsyncDirectory(destinationParent);
  const commonParent = path.dirname(sourceParent);
  if (pathKey(commonParent) !== pathKey(path.dirname(destinationParent))) {
    fail(FAILURE.UNSAFE_PATH, "durable publication roots do not share one private parent");
  }
  durableFsyncDirectory(commonParent);
  fs.renameSync(stageRoot, finalRoot);
  durableFsyncDirectory(sourceParent);
  if (pathKey(destinationParent) !== pathKey(sourceParent)) durableFsyncDirectory(destinationParent);
  durableFsyncDirectory(finalRoot);
  durableFsyncDirectory(commonParent);
  const published = inspectTree(finalRoot, { limits });
  if (!sameTree(staged, published)) fail(FAILURE.PACKAGE_DRIFT, "published tree differs after atomic rename");
  return published;
}

export function durableQuarantineDirectory(sourceRoot, quarantineRoot, expectedTreeHash, limits = LIMITS) {
  if (fs.existsSync(quarantineRoot)) fail(FAILURE.RECONCILIATION_REQUIRED, "resource quarantine is already occupied", STATUS.BLOCKED);
  const sourceIdentity = durableSyncTree(sourceRoot, limits, false);
  if (sourceIdentity.tree_hash !== expectedTreeHash) {
    fail(FAILURE.RECONCILIATION_REQUIRED, "resource changed before quarantine", STATUS.BLOCKED);
  }
  const sourceParent = path.dirname(sourceRoot);
  const quarantineParent = path.dirname(quarantineRoot);
  const commonParent = path.dirname(sourceParent);
  if (pathKey(commonParent) !== pathKey(path.dirname(quarantineParent))) {
    fail(FAILURE.UNSAFE_PATH, "resource quarantine roots do not share one private parent");
  }
  durableFsyncDirectory(sourceParent);
  if (pathKey(quarantineParent) !== pathKey(sourceParent)) durableFsyncDirectory(quarantineParent);
  durableFsyncDirectory(commonParent);
  fs.renameSync(sourceRoot, quarantineRoot);
  durableFsyncDirectory(sourceParent);
  if (pathKey(quarantineParent) !== pathKey(sourceParent)) durableFsyncDirectory(quarantineParent);
  durableFsyncDirectory(quarantineRoot);
  durableFsyncDirectory(commonParent);
  const quarantined = inspectTree(quarantineRoot, { limits });
  if (!sameTree(sourceIdentity, quarantined)) {
    fail(FAILURE.RECONCILIATION_REQUIRED, "quarantined resource identity differs", STATUS.BLOCKED);
  }
  return quarantined;
}

export function durableRemoveQuarantine(quarantineRoot, expectedTreeHash, limits = LIMITS) {
  const identity = durableSyncTree(quarantineRoot, limits, false);
  if (identity.tree_hash !== expectedTreeHash) {
    fail(FAILURE.RECONCILIATION_REQUIRED, "quarantine changed before deletion", STATUS.BLOCKED);
  }
  const parent = path.dirname(quarantineRoot);
  durableFsyncDirectory(parent);
  fs.rmSync(quarantineRoot, { recursive: true, force: false });
  durableFsyncDirectory(parent);
  const grandparent = path.dirname(parent);
  if (pathKey(grandparent) !== pathKey(parent)) durableFsyncDirectory(grandparent);
}

function copyInventory(sourceRoot, destinationRoot, identity, limits) {
  checkDeadline(limits.deadlineMs);
  fs.mkdirSync(destinationRoot, { recursive: false });
  for (const entry of identity.inventory) {
    checkDeadline(limits.deadlineMs);
    const destination = path.join(destinationRoot, ...entry.path.split("/"));
    if (entry.type === "directory") {
      fs.mkdirSync(destination, { recursive: false, mode: entry.mode });
      fs.chmodSync(destination, entry.mode);
      continue;
    }
    const source = path.join(sourceRoot, ...entry.path.split("/"));
    const copied = streamFile(source, destination, limits.maxFileBytes, false, limits.deadlineMs);
    if (copied.byte_size !== entry.byte_size || copied.sha256 !== entry.sha256) {
      fail(FAILURE.PACKAGE_DRIFT, "file changed during copy");
    }
    fs.chmodSync(destination, entry.mode);
  }
}

export function copyExactTree(sourceRoot, destinationRoot, identity, limits = LIMITS) {
  if (fs.existsSync(destinationRoot)) fail(FAILURE.STATE_CORRUPT, "copy destination already exists");
  try {
    copyInventory(sourceRoot, destinationRoot, identity, limits);
    const observed = inspectTree(destinationRoot, { pluginName: identity.plugin_name, limits });
    if (!sameTree(identity, observed)) fail(FAILURE.PACKAGE_DRIFT, "copied tree identity differs");
    return observed;
  } catch (cause) {
    if (fs.existsSync(destinationRoot)) fs.rmSync(destinationRoot, { recursive: true, force: true });
    throw cause;
  }
}

export function preserveTree({ sourceRoot, identity, storeRoot, stagingRoot, operationId, kind, limits = LIMITS }) {
  const finalContainer = path.join(storeRoot, identity.tree_hash.slice(7));
  const finalRoot = path.join(finalContainer, "data");
  if (fs.existsSync(finalContainer)) {
    const observed = inspectTree(finalRoot, { pluginName: identity.plugin_name, limits });
    if (!sameTree(identity, observed)) fail(FAILURE.STATE_CORRUPT, "content-addressed tree drifted");
    durableSyncTree(finalContainer, limits);
    return finalRoot;
  }
  const stageName = `stage-${operationId}-${kind}`;
  if (!/^stage-op_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}-(?:package|snapshot|marketplace)$/u.test(stageName)) {
    fail(FAILURE.INVALID_INPUT, "owned staging name is invalid");
  }
  const stageContainer = path.join(stagingRoot, stageName);
  const stageData = path.join(stageContainer, "data");
  if (fs.existsSync(stageContainer)) fail(FAILURE.STATE_CORRUPT, "owned staging path already exists");
  fs.mkdirSync(stageContainer, { recursive: false });
  try {
    copyInventory(sourceRoot, stageData, identity, limits);
    const sourceAfter = inspectTree(sourceRoot, { pluginName: identity.plugin_name, limits });
    const copied = inspectTree(stageData, { pluginName: identity.plugin_name, limits });
    if (!sameTree(identity, sourceAfter) || !sameTree(identity, copied)) {
      fail(FAILURE.PACKAGE_DRIFT, "tree changed across the copy boundary");
    }
    durablePublishDirectory(stageContainer, finalContainer, limits);
    return finalRoot;
  } catch (cause) {
    if (fs.existsSync(stageContainer)) fs.rmSync(stageContainer, { recursive: true, force: true });
    throw cause;
  }
}

export function reconcileOwnedStaging(stagingRoot, limits = LIMITS, remove = false) {
  const entries = fs.readdirSync(stagingRoot, { withFileTypes: true });
  if (entries.length > limits.maxEntries) fail(FAILURE.RESOURCE_LIMIT, "staging entry bound exceeded");
  for (const entry of entries) {
    if (!entry.isDirectory() || !/^stage-op_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}-(?:package|snapshot|marketplace)$/u.test(entry.name)) {
      fail(FAILURE.STATE_CORRUPT, "staging contains an unknown entry");
    }
  }
  if (!remove) return;
  const selected = entries.slice(0, limits.maxCleanupItems);
  for (const entry of selected) {
    const target = path.join(stagingRoot, entry.name);
    if (path.dirname(target) !== stagingRoot) fail(FAILURE.UNSAFE_PATH, "staging cleanup escaped its root");
    if (!entry.name.endsWith("-snapshot")) inspectTree(target, { limits });
    fs.rmSync(target, { recursive: true, force: true });
  }
  if (selected.length !== entries.length) {
    fail(FAILURE.RESOURCE_LIMIT, "bounded staging orphan cleanup is incomplete");
  }
}

export function treeRecord(identity, preservedRoot) {
  return {
    package_hash: identity.tree_hash,
    plugin_name: identity.plugin_name,
    plugin_version: identity.plugin_version,
    manifest_hash: identity.manifest_hash,
    has_hooks: identity.has_hooks,
    hook_subject_hash: identity.hook_subject_hash,
    entry_count: identity.entry_count,
    file_count: identity.file_count,
    byte_size: identity.byte_size,
    inventory_bytes: identity.inventory_bytes,
    inventory_json: canonicalJson(identity.inventory),
    preserved_root: preservedRoot,
  };
}

export function identityFromRecord(record) {
  return {
    root: record.preserved_root,
    plugin_name: record.plugin_name,
    plugin_version: record.plugin_version,
    manifest_hash: record.manifest_hash,
    has_hooks: record.has_hooks === 1 || record.has_hooks === true,
    hook_subject_hash: record.hook_subject_hash,
    entry_count: record.entry_count,
    file_count: record.file_count,
    byte_size: record.byte_size,
    inventory_bytes: record.inventory_bytes,
    tree_hash: record.package_hash,
    inventory: JSON.parse(record.inventory_json),
  };
}
