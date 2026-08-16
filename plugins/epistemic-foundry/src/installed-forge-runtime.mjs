import { createHash } from "node:crypto";
import { lstatSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { types as utilTypes } from "node:util";

import {
  openInstalledForgeReadRuntime,
  openInstalledForgeRuntime,
} from "./foundry-kernel/forge/session/index.mjs";
import {
  PATH_BOUNDARY,
  PATH_TARGET_MODE,
  resolveBoundaryPath,
  resolvePluginPaths,
} from "./plugin-host/paths/path-resolution.mjs";

const AUTHORITY_PRINCIPAL_ID =
  "SVC-PLUGIN-ALPHA-LOCAL-SESSION-AUTHORITY";
const WORKER_PRINCIPAL_ID = "AG-PLUGIN-ALPHA-LOCAL-SESSION-WORKER";
const CLASSIFICATION_CAPABILITY = "mcp.write.classification";
const SESSION_CAPABILITY = "mcp.write.session";
const LEASE_DURATION_MILLISECONDS = 300_000;
const POLICY_HASH_PREFIX = "PLUGIN_ALPHA_LOCAL_SESSION_POLICY_V1\0";
const PLUGIN_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const OPEN_OPTION_KEYS = new Set(["env", "clock"]);
const REQUIRED_ENVIRONMENT_KEYS = Object.freeze([
  "PLUGIN_DATA",
  "EFOUNDRY_WORKSPACE_ROOT",
  "EFOUNDRY_WORKSPACE_ID",
]);
const COMMON_LEASE_CONTEXT_KEYS = Object.freeze([
  "leaseId",
  "runId",
  "workerPrincipalId",
  "approvalRecordIds",
  "workspaceId",
  "targetRef",
  "semanticFingerprint",
  "idempotencyKey",
  "requestedAt",
]);
const CLASSIFICATION_LEASE_CONTEXT_KEYS = new Set([
  ...COMMON_LEASE_CONTEXT_KEYS,
  "authPrincipalId",
  "argumentsArtifactId",
]);
const OPEN_LEASE_CONTEXT_KEYS = new Set([
  ...COMMON_LEASE_CONTEXT_KEYS,
  "openRequestArtifactId",
]);
const TRANSITION_LEASE_CONTEXT_KEYS = new Set([
  ...COMMON_LEASE_CONTEXT_KEYS,
  "transitionRequestArtifactId",
]);
const ERROR_MESSAGES = Object.freeze({
  INVALID_INPUT: "plugin Forge runtime input is invalid",
  UNAVAILABLE: "installed Forge runtime is unavailable",
});
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:Z|[+-](\d{2}):(\d{2}))$/u;
const CANONICAL_UTC_PATTERN =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/u;

export class PluginForgeRuntimeError extends Error {
  constructor(code) {
    const stableCode =
      typeof code === "string" && Object.hasOwn(ERROR_MESSAGES, code)
        ? code
        : "UNAVAILABLE";
    super(ERROR_MESSAGES[stableCode]);
    this.name = "PluginForgeRuntimeError";
    this.code = stableCode;
  }
}

const invalidInput = () => {
  throw new PluginForgeRuntimeError("INVALID_INPUT");
};

const unavailable = () => {
  throw new PluginForgeRuntimeError("UNAVAILABLE");
};

const requirePlainRecord = (candidate, { allowProcessEnvironment = false } = {}) => {
  if (
    candidate === null ||
    typeof candidate !== "object" ||
    Array.isArray(candidate) ||
    utilTypes.isProxy(candidate)
  ) {
    invalidInput();
  }
  const prototype = Object.getPrototypeOf(candidate);
  if (
    prototype !== Object.prototype &&
    prototype !== null &&
    !(allowProcessEnvironment && candidate === process.env)
  ) {
    invalidInput();
  }
  return candidate;
};

const readDataProperty = (record, key, { required = true } = {}) => {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  if (descriptor === undefined) {
    if (required) invalidInput();
    return undefined;
  }
  if (!("value" in descriptor)) invalidInput();
  return descriptor.value;
};

const rejectUnexpectedKeys = (record, allowedKeys) => {
  for (const key of Reflect.ownKeys(record)) {
    if (typeof key !== "string" || !allowedKeys.has(key)) invalidInput();
    const descriptor = Object.getOwnPropertyDescriptor(record, key);
    if (descriptor === undefined || !("value" in descriptor)) invalidInput();
  }
};

const hasOnlyUnicodeScalars = (value) => {
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (next < 0xdc00 || next > 0xdfff) return false;
      index += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      return false;
    }
  }
  return true;
};

const readEnvironment = (candidate) => {
  const env = requirePlainRecord(candidate, { allowProcessEnvironment: true });
  for (const key of Reflect.ownKeys(env)) {
    if (typeof key !== "string") invalidInput();
    const descriptor = Object.getOwnPropertyDescriptor(env, key);
    if (
      descriptor === undefined ||
      !("value" in descriptor) ||
      typeof descriptor.value !== "string"
    ) {
      invalidInput();
    }
  }

  const values = Object.fromEntries(
    REQUIRED_ENVIRONMENT_KEYS.map((key) => [key, readDataProperty(env, key)]),
  );
  if (
    values.PLUGIN_DATA.length === 0 ||
    values.EFOUNDRY_WORKSPACE_ROOT.length === 0 ||
    values.EFOUNDRY_WORKSPACE_ID.length < 3 ||
    values.EFOUNDRY_WORKSPACE_ID.length > 128 ||
    !hasOnlyUnicodeScalars(values.EFOUNDRY_WORKSPACE_ID)
  ) {
    invalidInput();
  }
  return Object.freeze({
    pluginData: values.PLUGIN_DATA,
    workspaceRoot: values.EFOUNDRY_WORKSPACE_ROOT,
    workspaceId: values.EFOUNDRY_WORKSPACE_ID,
  });
};

const defaultClock = Object.freeze(() => new Date().toISOString());

const normalizeOptions = (candidate) => {
  const options = candidate === undefined ? {} : requirePlainRecord(candidate);
  rejectUnexpectedKeys(options, OPEN_OPTION_KEYS);

  const configuredEnvironment = readDataProperty(options, "env", { required: false });
  const configuredClock = readDataProperty(options, "clock", { required: false });
  const clock = configuredClock === undefined ? defaultClock : configuredClock;
  if (typeof clock !== "function" || utilTypes.isProxy(clock)) invalidInput();

  return Object.freeze({
    environment: readEnvironment(
      configuredEnvironment === undefined ? process.env : configuredEnvironment,
    ),
    clock,
  });
};

const dependencyCodeIs = (error, expected) => {
  if (
    error === null ||
    !["object", "function"].includes(typeof error) ||
    utilTypes.isProxy(error)
  ) {
    return false;
  }
  const descriptor = Object.getOwnPropertyDescriptor(error, "code");
  return descriptor !== undefined && "value" in descriptor && descriptor.value === expected;
};

const boundaryPath = (resolution, relativePath, targetMode) =>
  resolveBoundaryPath(resolution, {
    boundary: PATH_BOUNDARY.PLUGIN_DATA,
    relativePath,
    targetMode,
  });

const requireOrdinaryDirectory = (candidate) => {
  let stats;
  try {
    stats = lstatSync(candidate);
  } catch {
    unavailable();
  }
  if (!stats.isDirectory() || stats.isSymbolicLink()) unavailable();
};

const requireOrdinaryFile = (candidate) => {
  let stats;
  try {
    stats = lstatSync(candidate);
  } catch {
    unavailable();
  }
  if (!stats.isFile() || stats.isSymbolicLink()) unavailable();
};

const ensureFinalDirectory = (resolution, relativePath) => {
  let createTarget = null;
  try {
    createTarget = boundaryPath(resolution, relativePath, PATH_TARGET_MODE.CREATE);
  } catch (error) {
    if (!dependencyCodeIs(error, "PATH_TARGET_EXISTS")) unavailable();
  }

  if (createTarget !== null) {
    try {
      mkdirSync(createTarget.canonicalPath, { recursive: false, mode: 0o700 });
    } catch (error) {
      if (!dependencyCodeIs(error, "EEXIST")) unavailable();
    }
  }

  let existing;
  try {
    existing = boundaryPath(resolution, relativePath, PATH_TARGET_MODE.EXISTING);
  } catch {
    unavailable();
  }
  requireOrdinaryDirectory(existing.canonicalPath);
  return existing;
};

const resolveRoots = (environment) => {
  try {
    return resolvePluginPaths({
      pluginRoot: PLUGIN_ROOT,
      pluginData: environment.pluginData,
      workspaceRoot: environment.workspaceRoot,
    });
  } catch {
    unavailable();
  }
};

const resolveExistingStatePaths = (resolution) => {
  let database;
  let artifacts;
  try {
    artifacts = boundaryPath(
      resolution,
      "forge/artifacts",
      PATH_TARGET_MODE.EXISTING,
    );
    database = boundaryPath(
      resolution,
      "forge/state.sqlite3",
      PATH_TARGET_MODE.EXISTING,
    );
  } catch {
    unavailable();
  }
  requireOrdinaryDirectory(artifacts.canonicalPath);
  requireOrdinaryFile(database.canonicalPath);
  return Object.freeze({
    artifactRoot: artifacts.canonicalPath,
    databasePath: database.canonicalPath,
  });
};

const resolveWritableStatePaths = (resolution) => {
  ensureFinalDirectory(resolution, "forge");
  const artifacts = ensureFinalDirectory(resolution, "forge/artifacts");

  let database;
  try {
    database = boundaryPath(
      resolution,
      "forge/state.sqlite3",
      PATH_TARGET_MODE.CREATE,
    );
  } catch (error) {
    if (!dependencyCodeIs(error, "PATH_TARGET_EXISTS")) unavailable();
    try {
      database = boundaryPath(
        resolution,
        "forge/state.sqlite3",
        PATH_TARGET_MODE.EXISTING,
      );
    } catch {
      unavailable();
    }
    requireOrdinaryFile(database.canonicalPath);
  }

  return Object.freeze({
    artifactRoot: artifacts.canonicalPath,
    databasePath: database.canonicalPath,
  });
};

const policyHash = (workspaceId) =>
  `sha256:${createHash("sha256")
    .update(`${POLICY_HASH_PREFIX}${workspaceId}`, "utf8")
    .digest("hex")}`;

const capabilityPolicy = (workspaceId) => {
  const empty = () => Object.freeze([]);
  const authorityCapabilities = Object.freeze(["capability:issue"]);
  const workerCapabilities = Object.freeze([
    CLASSIFICATION_CAPABILITY,
    SESSION_CAPABILITY,
  ]);
  const workerScopes = Object.freeze([workspaceId]);
  return Object.freeze({
    policy_hash: policyHash(workspaceId),
    principals: Object.freeze([
      Object.freeze({
        principal_id: AUTHORITY_PRINCIPAL_ID,
        principal_type: "service",
        identity_class: "service",
        capabilities: authorityCapabilities,
        resource_scopes: empty(),
        authority_role: null,
        approval_types: empty(),
      }),
      Object.freeze({
        principal_id: WORKER_PRINCIPAL_ID,
        principal_type: "agent",
        identity_class: "agent",
        capabilities: workerCapabilities,
        resource_scopes: workerScopes,
        authority_role: null,
        approval_types: empty(),
      }),
    ]),
    subjects: empty(),
    approval_rules: empty(),
    capability_rules: Object.freeze([
      Object.freeze({
        capability: "capability:issue",
        required_approval_type: null,
      }),
      Object.freeze({
        capability: CLASSIFICATION_CAPABILITY,
        required_approval_type: null,
      }),
      Object.freeze({
        capability: SESSION_CAPABILITY,
        required_approval_type: null,
      }),
    ]),
  });
};

const requireExactLeaseContext = (candidate, workspaceId, allowedKeys) => {
  const context = requirePlainRecord(candidate);
  rejectUnexpectedKeys(context, allowedKeys);
  if (Reflect.ownKeys(context).length !== allowedKeys.size) invalidInput();

  const leaseId = readDataProperty(context, "leaseId");
  const runId = readDataProperty(context, "runId");
  const workerPrincipalId = readDataProperty(context, "workerPrincipalId");
  const contextWorkspaceId = readDataProperty(context, "workspaceId");
  const requestedAt = readDataProperty(context, "requestedAt");
  const approvalRecordIds = readDataProperty(context, "approvalRecordIds");
  if (
    typeof leaseId !== "string" ||
    leaseId.length < 3 ||
    leaseId.length > 128 ||
    typeof runId !== "string" ||
    runId.length === 0 ||
    workerPrincipalId !== WORKER_PRINCIPAL_ID ||
    contextWorkspaceId !== workspaceId ||
    typeof requestedAt !== "string" ||
    !Array.isArray(approvalRecordIds) ||
    utilTypes.isProxy(approvalRecordIds)
  ) {
    invalidInput();
  }

  const approvalIds = [];
  const approvalKeys = new Set(["length"]);
  for (let index = 0; index < approvalRecordIds.length; index += 1) {
    const key = String(index);
    approvalKeys.add(key);
    const descriptor = Object.getOwnPropertyDescriptor(approvalRecordIds, key);
    if (
      descriptor === undefined ||
      !("value" in descriptor) ||
      typeof descriptor.value !== "string" ||
      descriptor.value.length === 0
    ) {
      invalidInput();
    }
    approvalIds.push(descriptor.value);
  }
  if (
    Reflect.ownKeys(approvalRecordIds).some((key) => !approvalKeys.has(key)) ||
    new Set(approvalIds).size !== approvalIds.length
  ) {
    invalidInput();
  }

  return Object.freeze({
    approvalIds: Object.freeze(approvalIds),
    leaseId,
    requestedAt,
    runId,
    workerPrincipalId,
  });
};

const leaseExpiry = (requestedAt) => {
  const match = RFC3339_PATTERN.exec(requestedAt);
  if (match === null) invalidInput();
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const fraction = match[7] ?? "";
  const offsetHour = match[8] === undefined ? 0 : Number(match[8]);
  const offsetMinute = match[9] === undefined ? 0 : Number(match[9]);
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const monthLengths = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > monthLengths[month - 1] ||
    hour > 23 ||
    minute > 59 ||
    second > 59 ||
    offsetHour > 23 ||
    offsetMinute > 59 ||
    (fraction.length > 3 && /[^0]/u.test(fraction.slice(3)))
  ) {
    invalidInput();
  }

  const requestedMilliseconds = Date.parse(requestedAt);
  if (!Number.isFinite(requestedMilliseconds)) invalidInput();
  const expiresMilliseconds = requestedMilliseconds + LEASE_DURATION_MILLISECONDS;
  let expiresAt;
  try {
    expiresAt = new Date(expiresMilliseconds).toISOString();
  } catch {
    invalidInput();
  }
  if (
    !CANONICAL_UTC_PATTERN.test(expiresAt) ||
    Number(expiresAt.slice(0, 4)) < 1 ||
    Date.parse(expiresAt) - requestedMilliseconds !== LEASE_DURATION_MILLISECONDS
  ) {
    invalidInput();
  }
  return expiresAt;
};

const mutationRuntime = (workspaceId, capability, leaseContextKeys) => {
  const leaseCommandFactory = (candidate) => {
    const context = requireExactLeaseContext(candidate, workspaceId, leaseContextKeys);
    return Object.freeze({
      lease_id: context.leaseId,
      run_id: context.runId,
      principal_id: context.workerPrincipalId,
      capabilities: Object.freeze([capability]),
      resource_scopes: Object.freeze([workspaceId]),
      expires_at: leaseExpiry(context.requestedAt),
      approval_ids: context.approvalIds,
    });
  };
  Object.freeze(leaseCommandFactory);
  return Object.freeze({
    authorityPrincipalId: AUTHORITY_PRINCIPAL_ID,
    workerPrincipalId: WORKER_PRINCIPAL_ID,
    leaseCommandFactory,
  });
};

const classificationRuntime = (workspaceId) =>
  mutationRuntime(
    workspaceId,
    CLASSIFICATION_CAPABILITY,
    CLASSIFICATION_LEASE_CONTEXT_KEYS,
  );

const openRuntime = (workspaceId) =>
  mutationRuntime(workspaceId, SESSION_CAPABILITY, OPEN_LEASE_CONTEXT_KEYS);

const transitionRuntime = (workspaceId) =>
  mutationRuntime(
    workspaceId,
    SESSION_CAPABILITY,
    TRANSITION_LEASE_CONTEXT_KEYS,
  );

const closeOnce = (runtime) => {
  let attempted = false;
  let closeError = null;
  const close = () => {
    if (attempted) {
      if (closeError !== null) throw closeError;
      return;
    }
    attempted = true;
    try {
      runtime.close();
    } catch {
      closeError = new PluginForgeRuntimeError("UNAVAILABLE");
      throw closeError;
    }
  };
  return Object.freeze(close);
};

const opened = (workspaceId, paths, runtime) =>
  Object.freeze({
    workspaceId,
    paths,
    runtime,
    close: closeOnce(runtime),
  });

export const openPluginForgeReadRuntime = (options = undefined) => {
  const normalized = normalizeOptions(options);
  const resolution = resolveRoots(normalized.environment);
  const paths = resolveExistingStatePaths(resolution);
  let runtime;
  try {
    runtime = openInstalledForgeReadRuntime({
      databasePath: paths.databasePath,
      artifactRoot: paths.artifactRoot,
      clock: normalized.clock,
    });
  } catch {
    unavailable();
  }
  return opened(normalized.environment.workspaceId, paths, runtime);
};

export const openPluginForgeRuntime = (options = undefined) => {
  const normalized = normalizeOptions(options);
  const resolution = resolveRoots(normalized.environment);
  const paths = resolveWritableStatePaths(resolution);
  const workspaceId = normalized.environment.workspaceId;
  let runtime;
  try {
    runtime = openInstalledForgeRuntime({
      databasePath: paths.databasePath,
      artifactRoot: paths.artifactRoot,
      capabilityPolicy: capabilityPolicy(workspaceId),
      clock: normalized.clock,
      classificationRuntime: classificationRuntime(workspaceId),
      openRuntime: openRuntime(workspaceId),
      transitionRuntime: transitionRuntime(workspaceId),
    });
  } catch {
    unavailable();
  }
  return opened(workspaceId, paths, runtime);
};