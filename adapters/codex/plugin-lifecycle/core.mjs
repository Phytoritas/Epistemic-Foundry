import { createHash } from "node:crypto";

export const STATUS = Object.freeze({
  IDLE: "IDLE",
  CAPTURED: "CAPTURED",
  PREPARED: "PREPARED",
  ACTIVE: "ACTIVE",
  VERIFIED: "VERIFIED",
  DEGRADED: "DEGRADED",
  BLOCKED: "BLOCKED",
  ROLLED_BACK: "ROLLED_BACK",
  UNINSTALLED: "UNINSTALLED",
  FAILED: "FAILED",
  UNSUPPORTED: "UNSUPPORTED",
});

export const FAILURE = Object.freeze({
  INVALID_INPUT: "INVALID_INPUT",
  UNSAFE_PATH: "UNSAFE_PATH",
  RESOURCE_LIMIT: "RESOURCE_LIMIT",
  STATE_CORRUPT: "STATE_CORRUPT",
  IO_FAILURE: "IO_FAILURE",
  CONCURRENT_OPERATION: "CONCURRENT_OPERATION",
  RECONCILIATION_REQUIRED: "RECONCILIATION_REQUIRED",
  HOST_COMMAND_FAILED: "HOST_COMMAND_FAILED",
  HOST_OUTPUT_INVALID: "HOST_OUTPUT_INVALID",
  HOST_AMBIGUOUS: "HOST_AMBIGUOUS",
  HOST_UNSUPPORTED: "HOST_UNSUPPORTED",
  PACKAGE_INVALID: "PACKAGE_INVALID",
  PACKAGE_DRIFT: "PACKAGE_DRIFT",
  IDENTITY_MISMATCH: "IDENTITY_MISMATCH",
  QUIESCENCE_REQUIRED: "QUIESCENCE_REQUIRED",
  MIGRATION_REQUIRED: "MIGRATION_REQUIRED",
  MIGRATION_FAILED: "MIGRATION_FAILED",
  MIGRATION_RECEIPT_INVALID: "MIGRATION_RECEIPT_INVALID",
  MIGRATION_ROLLBACK_FAILED: "MIGRATION_ROLLBACK_FAILED",
  TRUST_REQUIRED: "TRUST_REQUIRED",
  TRUST_DECLINED: "TRUST_DECLINED",
  TRUST_UNAVAILABLE: "TRUST_UNAVAILABLE",
  CHECK_FAILED: "CHECK_FAILED",
  ROLLBACK_FAILED: "ROLLBACK_FAILED",
  PLUGIN_DATA_CHANGED: "PLUGIN_DATA_CHANGED",
  NOT_FOUND: "NOT_FOUND",
  INVALID_TRANSITION: "INVALID_TRANSITION",
});

export const LIMITS = Object.freeze({
  maxFiles: 20_000,
  maxEntries: 40_000,
  maxDepth: 32,
  maxFileBytes: 256 * 1024 * 1024,
  maxTreeBytes: 2 * 1024 * 1024 * 1024,
  maxManifestBytes: 1024 * 1024,
  maxInventoryBytes: 16 * 1024 * 1024,
  maxRetainedEntries: 500_000,
  maxRetainedBytes: 16 * 1024 * 1024 * 1024,
  maxRetainedObjects: 4096,
  maxPreparations: 1024,
  maxHistoryOperations: 100_000,
  maxHistoryEffects: 1_000_000,
  maxHistoryEvents: 2_000_000,
  maxEffectsPerOperation: 2048,
  maxCleanupItems: 128,
  maxOperationMs: 15 * 60 * 1000,
  maxInjectedBytes: 128 * 1024,
  maxInjectedDepth: 16,
  maxInjectedNodes: 4096,
  maxInjectedString: 16 * 1024,
  maxDiagnosticBytes: 512 * 1024,
  maxDiagnosticBlobs: 4096,
  maxCommandOutputBytes: 4 * 1024 * 1024,
});

const MESSAGES = Object.freeze({
  INVALID_INPUT: "The request was rejected.",
  UNSAFE_PATH: "A filesystem boundary was rejected.",
  RESOURCE_LIMIT: "A bounded lifecycle limit was exceeded.",
  STATE_CORRUPT: "Private lifecycle state is unavailable.",
  IO_FAILURE: "The lifecycle operation could not be durably recorded.",
  CONCURRENT_OPERATION: "Another lifecycle operation is pending.",
  RECONCILIATION_REQUIRED: "A prior lifecycle operation was reconciled and requires an explicit retry.",
  HOST_COMMAND_FAILED: "The Codex host operation failed.",
  HOST_OUTPUT_INVALID: "The Codex host response was not usable.",
  HOST_AMBIGUOUS: "The Codex host did not identify one exact lifecycle object.",
  HOST_UNSUPPORTED: "The required host capability is unavailable.",
  PACKAGE_INVALID: "The plugin package was rejected.",
  PACKAGE_DRIFT: "The filesystem tree changed while it was being captured.",
  IDENTITY_MISMATCH: "The observed package does not match the prepared package.",
  QUIESCENCE_REQUIRED: "Safe quiescence and current-data ownership are required.",
  MIGRATION_REQUIRED: "A crash-idempotent migration contract is required.",
  MIGRATION_FAILED: "The requested migration failed.",
  MIGRATION_RECEIPT_INVALID: "The migration owner did not return a durable resolving receipt.",
  MIGRATION_ROLLBACK_FAILED: "The migration could not be rolled back safely.",
  TRUST_REQUIRED: "Fresh trust is required for the executable package closure.",
  TRUST_DECLINED: "Fresh trust was declined.",
  TRUST_UNAVAILABLE: "Fresh trust is unavailable.",
  CHECK_FAILED: "A non-waivable post-activation check failed.",
  ROLLBACK_FAILED: "The previous package could not be restored.",
  PLUGIN_DATA_CHANGED: "Plugin data changed outside an owned restoration boundary.",
  NOT_FOUND: "The requested lifecycle object was not found.",
  INVALID_TRANSITION: "The lifecycle transition was rejected.",
});

export class LifecycleError extends Error {
  constructor(code, internalMessage, status = STATUS.FAILED, context = {}) {
    super(internalMessage);
    this.name = "LifecycleError";
    this.code = code;
    this.status = status;
    this.context = context;
  }
}

export function fail(code, internalMessage, status = STATUS.FAILED, context = {}) {
  throw new LifecycleError(code, internalMessage, status, context);
}

export function isPlainObject(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

export function compareUtf8(left, right) {
  return Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));
}

export function canonicalJson(value) {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value) || Object.is(value, -0)) fail(FAILURE.INVALID_INPUT, "non-canonical number");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (!isPlainObject(value)) fail(FAILURE.INVALID_INPUT, "value is not closed JSON");
  const keys = Object.keys(value).sort(compareUtf8);
  return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
}

export function sha256(bytes) {
  return `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
}

export function hashJson(domain, value) {
  return sha256(Buffer.from(`${domain}\0${canonicalJson(value)}`, "utf8"));
}

export function exactFields(value, fields, label) {
  if (!isPlainObject(value)) fail(FAILURE.INVALID_INPUT, `${label} must be an object`);
  const actual = Object.keys(value).sort(compareUtf8);
  const expected = [...fields].sort(compareUtf8);
  if (canonicalJson(actual) !== canonicalJson(expected)) {
    fail(FAILURE.INVALID_INPUT, `${label} is outside its closed field contract`);
  }
  return value;
}

export function allowedFields(value, fields, label) {
  if (!isPlainObject(value)) fail(FAILURE.INVALID_INPUT, `${label} must be an object`);
  const allowed = new Set(fields);
  if (Object.keys(value).some((key) => !allowed.has(key))) {
    fail(FAILURE.INVALID_INPUT, `${label} contains unsupported fields`);
  }
  return value;
}

export function boundedJson(value, label, overrides = {}) {
  const limits = {
    bytes: overrides.bytes ?? LIMITS.maxInjectedBytes,
    depth: overrides.depth ?? LIMITS.maxInjectedDepth,
    nodes: overrides.nodes ?? LIMITS.maxInjectedNodes,
    string: overrides.string ?? LIMITS.maxInjectedString,
  };
  let nodes = 0;
  const visit = (candidate, depth) => {
    nodes += 1;
    if (nodes > limits.nodes || depth > limits.depth) fail(FAILURE.RESOURCE_LIMIT, `${label} is too complex`);
    if (typeof candidate === "string" && Buffer.byteLength(candidate, "utf8") > limits.string) {
      fail(FAILURE.RESOURCE_LIMIT, `${label} contains an oversized string`);
    }
    if (candidate === null || ["string", "boolean", "number"].includes(typeof candidate)) {
      canonicalJson(candidate);
      return;
    }
    if (Array.isArray(candidate)) {
      for (const item of candidate) visit(item, depth + 1);
      return;
    }
    if (!isPlainObject(candidate)) fail(FAILURE.INVALID_INPUT, `${label} is not JSON`);
    for (const item of Object.values(candidate)) visit(item, depth + 1);
  };
  visit(value, 0);
  const text = canonicalJson(value);
  if (Buffer.byteLength(text, "utf8") > limits.bytes) fail(FAILURE.RESOURCE_LIMIT, `${label} is too large`);
  return JSON.parse(text);
}

export function deepFreeze(value) {
  if (value === null || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const item of Object.values(value)) deepFreeze(item);
  return Object.freeze(value);
}

export function makeResult(operation, outcome, activeHash = null) {
  const code = outcome.code ?? null;
  return deepFreeze({
    ok: outcome.ok === true,
    operation,
    status: outcome.status,
    failure: code,
    message: code === null ? outcome.message : MESSAGES[code] ?? "The lifecycle operation failed.",
    prepared_id: outcome.prepared_id ?? null,
    package_hash: outcome.package_hash ?? null,
    active_hash: activeHash,
    rolled_back: outcome.rolled_back === true,
    data: outcome.data ?? null,
  });
}

export function errorOutcome(error, context = {}) {
  const known = error instanceof LifecycleError;
  return {
    ok: false,
    status: known ? error.status : STATUS.FAILED,
    code: known ? error.code : FAILURE.IO_FAILURE,
    prepared_id: known ? error.context.prepared_id ?? context.prepared_id : context.prepared_id,
    package_hash: known ? error.context.package_hash ?? context.package_hash : context.package_hash,
    rolled_back: false,
    data: null,
    internal: known ? error.message : String(error?.message ?? error),
  };
}

export function strictVersion(value) {
  if (
    typeof value !== "string" ||
    value.length > 128 ||
    !/^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/u.test(value)
  ) {
    fail(FAILURE.PACKAGE_INVALID, "manifest version is not strict SemVer");
  }
  return value;
}
