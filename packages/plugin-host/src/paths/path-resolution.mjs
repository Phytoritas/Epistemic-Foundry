import fs from "node:fs";
import path from "node:path";
import { types as utilTypes } from "node:util";

export const PATH_BOUNDARY = Object.freeze({
  PLUGIN_ROOT: "plugin_root",
  PLUGIN_DATA: "plugin_data",
  WORKSPACE_ROOT: "workspace_root",
  WORKSPACE_STATE: "workspace_state",
});

export const PATH_TARGET_MODE = Object.freeze({
  EXISTING: "existing",
  CREATE: "create",
});

export const ROOT_IDENTITY_VERSION = "G03_ROOT_IDENTITY_V1";

const PATH_BOUNDARIES = new Set(Object.values(PATH_BOUNDARY));
const PATH_TARGET_MODES = new Set(Object.values(PATH_TARGET_MODE));
const ROOT_IDENTITY_FIELDS = new Set([
  "identity_version",
  "volume_id",
  "file_id",
  "birthtime_ns",
]);
const VOLUME_ID_PATTERN = /^[0-9]{1,20}$/u;
const FILE_ID_PATTERN = /^[1-9][0-9]{0,19}$/u;
const BIRTHTIME_NS_PATTERN = /^[1-9][0-9]*$/u;
const RESOLUTION_RECORDS = new WeakMap();
const MAX_PATH_LENGTH = 4_096;
const WINDOWS_RESERVED_BASENAME =
  /^(?:CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])$/iu;

export class PluginPathResolutionError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "PluginPathResolutionError";
    this.code = code;
  }
}

const fail = (code, message) => {
  throw new PluginPathResolutionError(code, message);
};

const requirePlainRecord = (value, label) => {
  if (value === null || typeof value !== "object") {
    fail("INVALID_INPUT", `${label} must be a plain object`);
  }
  if (utilTypes.isProxy(value)) {
    fail("PROXY_INPUT_DENIED", `${label} must not be a Proxy`);
  }
  if (Array.isArray(value)) {
    fail("INVALID_INPUT", `${label} must be a plain object`);
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    fail("INVALID_INPUT", `${label} must not have a custom prototype`);
  }
  return value;
};

const readDataProperty = (record, key) => {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  if (descriptor === undefined) {
    fail("MISSING_FIELD", `missing required field: ${key}`);
  }
  if (!("value" in descriptor)) {
    fail("ACCESSOR_FIELD_DENIED", `${key} must be a data property`);
  }
  return descriptor.value;
};

const rejectUnknownFields = (record, allowed, label) => {
  for (const key of Reflect.ownKeys(record)) {
    if (typeof key !== "string" || !allowed.has(key)) {
      fail("UNEXPECTED_FIELD", `${label} contains an unexpected field`);
    }
  }
};

const validateRootIdentity = (value, label) => {
  const identity = requirePlainRecord(value, label);
  rejectUnknownFields(identity, ROOT_IDENTITY_FIELDS, label);

  const identityVersion = readDataProperty(identity, "identity_version");
  const volumeId = readDataProperty(identity, "volume_id");
  const fileId = readDataProperty(identity, "file_id");
  const birthtimeNs = readDataProperty(identity, "birthtime_ns");

  if (identityVersion !== ROOT_IDENTITY_VERSION) {
    fail("INVALID_INPUT", `${label}.identity_version is not canonical`);
  }
  if (
    typeof volumeId !== "string" ||
    !VOLUME_ID_PATTERN.test(volumeId) ||
    (volumeId.length > 1 && volumeId.startsWith("0"))
  ) {
    fail("INVALID_INPUT", `${label}.volume_id is not canonical`);
  }
  if (typeof fileId !== "string" || !FILE_ID_PATTERN.test(fileId)) {
    fail("INVALID_INPUT", `${label}.file_id is not canonical`);
  }
  if (
    birthtimeNs !== null &&
    (typeof birthtimeNs !== "string" || !BIRTHTIME_NS_PATTERN.test(birthtimeNs))
  ) {
    fail("INVALID_INPUT", `${label}.birthtime_ns is not canonical`);
  }

  return { identityVersion, volumeId, fileId, birthtimeNs };
};

const freezeRootIdentity = (identityVersion, volumeId, fileId, birthtimeNs) =>
  Object.freeze({
    identity_version: identityVersion,
    volume_id: volumeId,
    file_id: fileId,
    birthtime_ns: birthtimeNs,
  });

const detachedRootIdentity = (identity) =>
  freezeRootIdentity(
    identity.identity_version,
    identity.volume_id,
    identity.file_id,
    identity.birthtime_ns,
  );

const unsupportedRootIdentity = (label) =>
  fail(
    "ROOT_IDENTITY_UNSUPPORTED",
    `${label} does not expose a supported injective directory identity`,
  );

const canonicalVolumeId = (value, label) => {
  if (typeof value !== "bigint" || value < 0n) {
    unsupportedRootIdentity(label);
  }
  const canonical = value.toString(10);
  if (!VOLUME_ID_PATTERN.test(canonical)) {
    unsupportedRootIdentity(label);
  }
  return canonical;
};

const captureRootIdentity = (stats, label) => {
  const volumeId = canonicalVolumeId(stats.dev, label);
  if (typeof stats.ino !== "bigint" || stats.ino <= 0n) {
    unsupportedRootIdentity(label);
  }
  const fileId = stats.ino.toString(10);
  if (!FILE_ID_PATTERN.test(fileId)) {
    unsupportedRootIdentity(label);
  }
  if (typeof stats.birthtimeNs !== "bigint" || stats.birthtimeNs < 0n) {
    unsupportedRootIdentity(label);
  }
  const birthtimeNs = stats.birthtimeNs === 0n ? null : stats.birthtimeNs.toString(10);
  if (birthtimeNs !== null && !BIRTHTIME_NS_PATTERN.test(birthtimeNs)) {
    unsupportedRootIdentity(label);
  }
  return freezeRootIdentity(
    ROOT_IDENTITY_VERSION,
    volumeId,
    fileId,
    birthtimeNs,
  );
};

export const serializeRootIdentity = (identity) => {
  const validated = validateRootIdentity(identity, "rootIdentity");
  return JSON.stringify({
    birthtime_ns: validated.birthtimeNs,
    file_id: validated.fileId,
    identity_version: validated.identityVersion,
    volume_id: validated.volumeId,
  });
};

export const rootIdentitiesEqual = (left, right) => {
  const validatedLeft = validateRootIdentity(left, "leftRootIdentity");
  const validatedRight = validateRootIdentity(right, "rightRootIdentity");
  return (
    validatedLeft.identityVersion === validatedRight.identityVersion &&
    validatedLeft.volumeId === validatedRight.volumeId &&
    validatedLeft.fileId === validatedRight.fileId &&
    validatedLeft.birthtimeNs === validatedRight.birthtimeNs
  );
};

const requirePathString = (value, label) => {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.length > MAX_PATH_LENGTH ||
    /\p{Cc}/u.test(value)
  ) {
    fail("INVALID_PATH", `${label} is outside the accepted path contract`);
  }
  return value;
};

const comparisonPath = (value) => {
  const resolved = path.resolve(value);
  return process.platform === "win32" ? resolved.toLowerCase() : resolved;
};

const pathsEqual = (left, right) => comparisonPath(left) === comparisonPath(right);

const isWithin = (parent, candidate) => {
  const relative = path.relative(parent, candidate);
  return (
    relative === "" ||
    (relative !== ".." &&
      !relative.startsWith(`..${path.sep}`) &&
      !path.isAbsolute(relative))
  );
};

const rejectLexicalRootTraversal = (value, label) => {
  const parsed = path.parse(value);
  const remainder = value.slice(parsed.root.length);
  if (remainder.split(/[\\/]/u).some((segment) => segment === "." || segment === "..")) {
    fail("ROOT_TRAVERSAL_DENIED", `${label} must not contain traversal components`);
  }
};

const inspectExistingDirectory = (value, label, unavailableCode = "ROOT_UNAVAILABLE") => {
  const supplied = requirePathString(value, label);
  if (!path.isAbsolute(supplied)) {
    fail("ROOT_NOT_ABSOLUTE", `${label} must be an explicit absolute path`);
  }
  rejectLexicalRootTraversal(supplied, label);

  const resolved = path.resolve(supplied);
  let stats;
  let canonicalPath;
  try {
    stats = fs.lstatSync(resolved);
    canonicalPath = fs.realpathSync.native(resolved);
  } catch {
    fail(unavailableCode, `${label} is not an inspectable directory`);
  }

  if (!stats.isDirectory() || stats.isSymbolicLink()) {
    fail("ROOT_UNSAFE", `${label} must be a real directory`);
  }
  if (!pathsEqual(resolved, canonicalPath)) {
    fail("ROOT_UNSAFE", `${label} crosses a link, reparse point, or path alias`);
  }

  let identityStats;
  try {
    identityStats = fs.lstatSync(canonicalPath, { bigint: true });
  } catch {
    fail(unavailableCode, `${label} is not an inspectable directory`);
  }

  return Object.freeze({
    canonicalPath,
    identity: captureRootIdentity(identityStats, label),
  });
};

const inspectOptionalWorkspaceState = (workspaceRoot) => {
  const candidate = path.join(workspaceRoot.canonicalPath, ".epistemic-foundry");
  try {
    fs.lstatSync(candidate);
  } catch (error) {
    if (error !== null && typeof error === "object" && error.code === "ENOENT") {
      return Object.freeze({ canonicalPath: candidate, identity: null, exists: false });
    }
    fail("ROOT_UNAVAILABLE", "workspace state root could not be inspected");
  }

  const inspected = inspectExistingDirectory(candidate, "workspaceStateRoot");
  return Object.freeze({ ...inspected, exists: true });
};

const sameDirectoryIdentity = (left, right) =>
  left.identity !== null &&
  right.identity !== null &&
  rootIdentitiesEqual(left.identity, right.identity);

const assertDisjoint = (left, right, leftLabel, rightLabel) => {
  if (
    sameDirectoryIdentity(left, right) ||
    isWithin(left.canonicalPath, right.canonicalPath) ||
    isWithin(right.canonicalPath, left.canonicalPath)
  ) {
    fail(
      "PATH_BOUNDARY_OVERLAP",
      `${leftLabel} and ${rightLabel} must not overlap`,
    );
  }
};

const assertRootIdentity = (root, label) => {
  if (root.identity === null) {
    fail("BOUNDARY_ROOT_UNAVAILABLE", `${label} does not exist yet`);
  }
  const current = inspectExistingDirectory(
    root.canonicalPath,
    label,
    "BOUNDARY_ROOT_CHANGED",
  );
  if (!rootIdentitiesEqual(current.identity, root.identity)) {
    fail("BOUNDARY_ROOT_CHANGED", `${label} changed after path resolution`);
  }
};

const parsePortableRelativePath = (value) => {
  const relativePath = requirePathString(value, "relativePath");
  if (
    relativePath.includes("\\") ||
    relativePath.includes(":") ||
    relativePath.startsWith("/") ||
    relativePath.endsWith("/") ||
    relativePath.includes("//") ||
    path.posix.isAbsolute(relativePath)
  ) {
    fail("PATH_ESCAPE_DENIED", "relativePath must use canonical portable syntax");
  }

  const segments = relativePath.split("/");
  for (const segment of segments) {
    const windowsBaseName = segment.split(".", 1)[0].trimEnd();
    if (
      segment.length === 0 ||
      /[<>"|?*]/u.test(segment) ||
      segment === "." ||
      segment === ".." ||
      segment.endsWith(".") ||
      segment.endsWith(" ") ||
      WINDOWS_RESERVED_BASENAME.test(windowsBaseName)
    ) {
      fail("PATH_ESCAPE_DENIED", "relativePath contains an unsafe component");
    }
  }
  return Object.freeze({ relativePath, segments: Object.freeze(segments) });
};

const inspectChildPathNoFollow = (root, segments) => {
  let current = root.canonicalPath;
  for (let index = 0; index < segments.length; index += 1) {
    current = path.join(current, segments[index]);
    let stats;
    try {
      stats = fs.lstatSync(current, { bigint: true });
    } catch (error) {
      if (error !== null && typeof error === "object" && error.code === "ENOENT") {
        if (index < segments.length - 1) {
          fail("PATH_PARENT_MISSING", "relativePath has an unverified missing parent");
        }
        return false;
      }
      fail("PATH_INSPECTION_FAILED", "relativePath could not be inspected safely");
    }

    if (stats.isSymbolicLink()) {
      fail("PATH_LINK_DENIED", "relativePath crosses a symbolic link or reparse point");
    }
    if (canonicalVolumeId(stats.dev, "relativePath") !== root.identity.volume_id) {
      fail("PATH_MOUNT_DENIED", "relativePath crosses a filesystem boundary");
    }
    if (index < segments.length - 1 && !stats.isDirectory()) {
      fail("PATH_NOT_TRAVERSABLE", "relativePath crosses a non-directory component");
    }

    let canonicalPath;
    try {
      canonicalPath = fs.realpathSync.native(current);
    } catch {
      fail("PATH_INSPECTION_FAILED", "relativePath could not be canonicalized safely");
    }
    if (!pathsEqual(current, canonicalPath)) {
      fail("PATH_LINK_DENIED", "relativePath crosses a link or path alias");
    }
  }
  return true;
};

/**
 * Resolve the three caller-selected roots. This function never consults cwd,
 * HOME, environment variables, a repository checkout, or a PATH fallback.
 */
export const resolvePluginPaths = (input) => {
  const request = requirePlainRecord(input, "pluginPathRequest");
  rejectUnknownFields(
    request,
    new Set(["pluginRoot", "pluginData", "workspaceRoot"]),
    "pluginPathRequest",
  );

  const pluginRoot = inspectExistingDirectory(
    readDataProperty(request, "pluginRoot"),
    "pluginRoot",
  );
  const pluginData = inspectExistingDirectory(
    readDataProperty(request, "pluginData"),
    "pluginData",
  );
  const workspaceRoot = inspectExistingDirectory(
    readDataProperty(request, "workspaceRoot"),
    "workspaceRoot",
  );
  const workspaceState = inspectOptionalWorkspaceState(workspaceRoot);

  assertDisjoint(
    pluginRoot,
    pluginData,
    "pluginRoot",
    "pluginData",
  );
  assertDisjoint(
    pluginRoot,
    workspaceRoot,
    "pluginRoot",
    "workspaceRoot",
  );
  assertDisjoint(
    pluginData,
    workspaceRoot,
    "pluginData",
    "workspaceRoot",
  );

  const resolution = Object.freeze({
    schemaVersion: 1,
    pluginRoot: pluginRoot.canonicalPath,
    pluginData: pluginData.canonicalPath,
    workspaceRoot: workspaceRoot.canonicalPath,
    workspaceStateRoot: workspaceState.canonicalPath,
    workspaceStateExists: workspaceState.exists,
    explicitInputs: true,
    noFollowChecked: true,
  });

  RESOLUTION_RECORDS.set(
    resolution,
    Object.freeze({
      [PATH_BOUNDARY.PLUGIN_ROOT]: pluginRoot,
      [PATH_BOUNDARY.PLUGIN_DATA]: pluginData,
      [PATH_BOUNDARY.WORKSPACE_ROOT]: workspaceRoot,
      [PATH_BOUNDARY.WORKSPACE_STATE]: workspaceState,
    }),
  );
  return resolution;
};

export const readRootIdentity = (resolution, boundary) => {
  const roots = RESOLUTION_RECORDS.get(resolution);
  if (roots === undefined) {
    fail("UNRECOGNIZED_PATH_RESOLUTION", "a resolver-issued path resolution is required");
  }
  if (typeof boundary !== "string" || !PATH_BOUNDARIES.has(boundary)) {
    fail("UNKNOWN_PATH_BOUNDARY", "boundary is not canonical");
  }

  const root = roots[boundary];
  assertRootIdentity(root, boundary);
  return detachedRootIdentity(root.identity);
};

/**
 * Resolve an existing child or a missing final create target without following
 * links. The returned path is a checked location, not a durable capability;
 * effect code must resolve again immediately before use.
 */
export const resolveBoundaryPath = (resolution, input) => {
  const roots = RESOLUTION_RECORDS.get(resolution);
  if (roots === undefined) {
    fail("UNRECOGNIZED_PATH_RESOLUTION", "a resolver-issued path resolution is required");
  }

  const request = requirePlainRecord(input, "boundaryPathRequest");
  rejectUnknownFields(
    request,
    new Set(["boundary", "relativePath", "targetMode"]),
    "boundaryPathRequest",
  );
  const boundary = readDataProperty(request, "boundary");
  const targetMode = readDataProperty(request, "targetMode");
  if (typeof boundary !== "string" || !PATH_BOUNDARIES.has(boundary)) {
    fail("UNKNOWN_PATH_BOUNDARY", "boundary is not canonical");
  }
  if (typeof targetMode !== "string" || !PATH_TARGET_MODES.has(targetMode)) {
    fail("UNKNOWN_TARGET_MODE", "targetMode is not canonical");
  }
  if (
    targetMode === PATH_TARGET_MODE.CREATE &&
    (boundary === PATH_BOUNDARY.PLUGIN_ROOT || boundary === PATH_BOUNDARY.WORKSPACE_ROOT)
  ) {
    fail("BOUNDARY_WRITE_DENIED", "writes are limited to explicit state boundaries");
  }

  const root = roots[boundary];
  assertRootIdentity(root, boundary);
  const parsed = parsePortableRelativePath(readDataProperty(request, "relativePath"));
  const candidate = path.resolve(root.canonicalPath, ...parsed.segments);
  if (!isWithin(root.canonicalPath, candidate) || pathsEqual(root.canonicalPath, candidate)) {
    fail("PATH_ESCAPE_DENIED", "relativePath escapes its selected boundary");
  }

  const targetExists = inspectChildPathNoFollow(root, parsed.segments);
  if (targetMode === PATH_TARGET_MODE.EXISTING && !targetExists) {
    fail("PATH_TARGET_MISSING", "existing target does not exist");
  }
  if (targetMode === PATH_TARGET_MODE.CREATE && targetExists) {
    fail("PATH_TARGET_EXISTS", "create target already exists");
  }

  return Object.freeze({
    boundary,
    relativePath: parsed.relativePath,
    canonicalPath: candidate,
    targetMode,
    targetExists,
    noFollowChecked: true,
  });
};
