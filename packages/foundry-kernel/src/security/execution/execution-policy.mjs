import fs from "node:fs";
import path from "node:path";
import { types as utilTypes } from "node:util";

/**
 * Fail-closed execution-boundary primitives for S02.
 *
 * The module keeps secret references and policy internals in runtime-private
 * WeakMaps. Public objects are immutable capabilities, not serializable
 * authority. It validates observable path, egress, sandbox-profile, and
 * outbound-data boundaries; it does not claim to be an OS/container sandbox.
 */

export const OUTBOUND_BOUNDARY = Object.freeze({
  PROMPT: "prompt",
  EVIDENCE_ARTIFACT: "evidence_artifact",
  LOG: "log",
  EXPORT: "export",
  NETWORK_REQUEST: "network_request",
});

export const NETWORK_POLICY = Object.freeze({
  DISABLED: "disabled",
  ALLOWLIST: "allowlist",
});

export const PATH_OPERATION = Object.freeze({
  READ: "read",
  WRITE: "write",
  CREATE: "create",
  DELETE: "delete",
  EXECUTE: "execute",
  LIST: "list",
});

const OUTBOUND_BOUNDARIES = new Set(Object.values(OUTBOUND_BOUNDARY));
const NETWORK_POLICIES = new Set(Object.values(NETWORK_POLICY));
const PATH_OPERATIONS = new Set(Object.values(PATH_OPERATION));
const ALL_SECRET_HANDLES = new WeakSet();
const MAX_PAYLOAD_DEPTH = 64;
const MAX_PAYLOAD_NODES = 10_000;
const MAX_PAYLOAD_CHARACTERS = 1_048_576;
const MAX_STRING_CHARACTERS = 262_144;
const MAX_ARRAY_ITEMS = 10_000;
const MAX_OBJECT_FIELDS = 10_000;
const MAX_FIELD_NAME_CHARACTERS = 1_024;

const SECRET_FIELD_NAMES = new Set([
  "apikey",
  "authorization",
  "clientsecret",
  "cookie",
  "credential",
  "credentials",
  "password",
  "privatekey",
  "refreshtoken",
  "secret",
  "secretkey",
  "sessioncookie",
  "token",
  "accesstoken",
]);

const SECRET_TEXT_PATTERNS = Object.freeze([
  /-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----/u,
  /\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b/u,
  /\b(?:https?|wss?):\/\/[^\s/@:]+:[^\s/@]+@/iu,
]);

const WINDOWS_RESERVED_BASENAME =
  /^(?:CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])$/iu;

export class ExecutionSecurityError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "ExecutionSecurityError";
    this.code = code;
  }
}

const fail = (code, message) => {
  throw new ExecutionSecurityError(code, message);
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

const readDataProperty = (record, key, { optional = false } = {}) => {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  if (descriptor === undefined) {
    if (optional) return undefined;
    fail("MISSING_FIELD", `missing required field: ${key}`);
  }
  if (!("value" in descriptor)) {
    fail("ACCESSOR_FIELD_DENIED", `${key} must be a data property`);
  }
  return descriptor.value;
};

const rejectUnknownFields = (record, allowedFields, label) => {
  for (const key of Reflect.ownKeys(record)) {
    if (typeof key !== "string" || !allowedFields.has(key)) {
      fail("UNEXPECTED_FIELD", `${label} contains an unexpected field`);
    }
  }
};

const readPlainArrayValues = (value, label) => {
  if (value === null || typeof value !== "object") {
    fail("INVALID_INPUT", `${label} must be a plain array`);
  }
  if (utilTypes.isProxy(value)) {
    fail("PROXY_INPUT_DENIED", `${label} must not be a Proxy`);
  }
  if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype) {
    fail("INVALID_INPUT", `${label} must be a plain array`);
  }

  const lengthDescriptor = Object.getOwnPropertyDescriptor(value, "length");
  const length = lengthDescriptor?.value;
  if (!Number.isSafeInteger(length) || length < 0 || length > MAX_ARRAY_ITEMS) {
    fail("INVALID_INPUT", `${label} has an invalid length`);
  }

  for (const key of Reflect.ownKeys(value)) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(?:0|[1-9][0-9]*)$/u.test(key)) {
      fail("UNEXPECTED_FIELD", `${label} contains a non-index field`);
    }
    const index = Number(key);
    if (!Number.isSafeInteger(index) || index >= length || String(index) !== key) {
      fail("UNEXPECTED_FIELD", `${label} contains an invalid index`);
    }
  }

  const values = [];
  for (let index = 0; index < length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (descriptor === undefined) {
      fail("SPARSE_ARRAY_DENIED", `${label} must not be sparse`);
    }
    if (!("value" in descriptor)) {
      fail("ACCESSOR_FIELD_DENIED", `${label} elements must be data properties`);
    }
    values.push(descriptor.value);
  }
  return values;
};

const requireString = (value, label, { maxLength = 512 } = {}) => {
  if (typeof value !== "string" || value.length === 0) {
    fail("INVALID_STRING", `${label} must be a non-empty string`);
  }
  if (value.length > maxLength || /\p{Cc}/u.test(value)) {
    fail("INVALID_STRING", `${label} is outside the accepted string contract`);
  }
  return value;
};

const requireIdentifier = (value, label) =>
  requireString(value, label, { maxLength: 256 });

const normalizedSecretFieldName = (value) =>
  value.normalize("NFKC").toLowerCase().replace(/[^a-z0-9]/gu, "");

const isSecretFieldName = (value) =>
  SECRET_FIELD_NAMES.has(normalizedSecretFieldName(value));

const assertStringHasNoSecretSignal = (value, boundary) => {
  if (value.length > MAX_STRING_CHARACTERS) {
    fail("PAYLOAD_LIMIT_EXCEEDED", `${boundary} contains an oversized string`);
  }
  for (const expression of SECRET_TEXT_PATTERNS) {
    if (expression.test(value)) {
      fail(
        "SECRET_PATTERN_BOUNDARY_DENIED",
        `${boundary} payload contains a secret-shaped value`,
      );
    }
  }
};

const getSecretHandleRecord = (secretHandles, handle) => {
  if (handle === null || typeof handle !== "object") {
    fail("UNRECOGNIZED_SECRET_HANDLE", "secret use requires an opaque runtime handle");
  }
  const record = secretHandles.get(handle);
  if (record === undefined) {
    fail(
      "UNRECOGNIZED_SECRET_HANDLE",
      "copied, serialized, Proxy-wrapped, or forged secret handles are denied",
    );
  }
  return record;
};

const getExecutionPolicyRecord = (executionPolicies, policy) => {
  if (policy === null || typeof policy !== "object") {
    fail("UNRECOGNIZED_POLICY", "an opaque runtime execution policy is required");
  }
  const record = executionPolicies.get(policy);
  if (record === undefined) {
    fail(
      "UNRECOGNIZED_POLICY",
      "copied, serialized, Proxy-wrapped, or forged execution policies are denied",
    );
  }
  return record;
};

const parseNetworkUrl = (value, { policyEntry = false } = {}) => {
  const input = requireString(value, policyEntry ? "allowlistedOrigin" : "url", {
    maxLength: 2_048,
  });

  let parsed;
  try {
    parsed = new URL(input);
  } catch {
    fail("INVALID_EGRESS_URL", "egress requires an absolute HTTP(S) URL");
  }

  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    fail("INVALID_EGRESS_URL", "egress is limited to explicit HTTP(S) origins");
  }
  if (parsed.hostname.length === 0 || parsed.username.length > 0 || parsed.password.length > 0) {
    fail("EGRESS_CREDENTIALS_DENIED", "URL credentials and missing hosts are denied");
  }
  if (parsed.origin === "null") {
    fail("INVALID_EGRESS_URL", "egress URL has no canonical origin");
  }

  if (policyEntry) {
    if (parsed.pathname !== "/" || parsed.search !== "" || parsed.hash !== "") {
      fail("INVALID_ALLOWLIST_ORIGIN", "allowlist entries must be origins without paths or data");
    }
  } else {
    if (parsed.hash !== "") {
      fail("EGRESS_FRAGMENT_DENIED", "network request URLs must not contain fragments");
    }
    assertStringHasNoSecretSignal(input, OUTBOUND_BOUNDARY.NETWORK_REQUEST);
    for (const key of parsed.searchParams.keys()) {
      if (isSecretFieldName(key)) {
        fail(
          "SECRET_FIELD_BOUNDARY_DENIED",
          "network URL contains a secret-bearing query field",
        );
      }
    }
  }

  return Object.freeze({ origin: parsed.origin, protocol: parsed.protocol });
};

const parseOrigins = (value, label, { secureOnly = false } = {}) => {
  const origins = new Set();
  for (const entry of readPlainArrayValues(value, label)) {
    const { origin, protocol } = parseNetworkUrl(entry, { policyEntry: true });
    if (secureOnly && protocol !== "https:") {
      fail("INSECURE_SECRET_ORIGIN", "secret handles may bind only to HTTPS origins");
    }
    if (origins.has(origin)) {
      fail("DUPLICATE_ORIGIN", `${label} contains a duplicate canonical origin`);
    }
    origins.add(origin);
  }
  return origins;
};

/**
 * Create an opaque, non-serializing secret reference. Secret material is not
 * accepted by this API; unknown fields (including value/token/password) fail.
 */
const issueOpaqueSecretHandle = (secretHandles, input) => {
  const record = requirePlainRecord(input, "secretHandleInput");
  rejectUnknownFields(
    record,
    new Set(["handleId", "vaultId", "allowedOrigins"]),
    "secretHandleInput",
  );

  const handleId = requireIdentifier(readDataProperty(record, "handleId"), "handleId");
  const vaultId = requireIdentifier(readDataProperty(record, "vaultId"), "vaultId");
  const allowedOrigins = parseOrigins(
    readDataProperty(record, "allowedOrigins"),
    "allowedOrigins",
    { secureOnly: true },
  );

  const handle = Object.freeze(Object.create(null));
  secretHandles.set(
    handle,
    Object.freeze({ handleId, vaultId, allowedOrigins }),
  );
  ALL_SECRET_HANDLES.add(handle);
  return handle;
};

/**
 * Validate JSON-like data before it crosses a prompt, artifact, log, export,
 * or network boundary. Validation uses descriptors and rejects Proxies,
 * accessors, custom prototypes, cycles, secret handles, secret-shaped fields,
 * and common raw-secret encodings without invoking attacker-controlled code.
 */
export const assertSecretFreeBoundaryPayload = (payload, boundary) => {
  const normalizedBoundary = requireString(boundary, "boundary", { maxLength: 64 });
  if (!OUTBOUND_BOUNDARIES.has(normalizedBoundary)) {
    fail("UNKNOWN_BOUNDARY", "unsupported outbound boundary");
  }

  const stack = [{ value: payload, depth: 0 }];
  const seen = new Set();
  let inspectedNodes = 0;
  let inspectedCharacters = 0;

  while (stack.length > 0) {
    const { value, depth } = stack.pop();
    inspectedNodes += 1;
    if (inspectedNodes > MAX_PAYLOAD_NODES || depth > MAX_PAYLOAD_DEPTH) {
      fail("PAYLOAD_LIMIT_EXCEEDED", `${normalizedBoundary} payload exceeds inspection limits`);
    }

    if (value === null || typeof value === "boolean") continue;
    if (typeof value === "number") {
      if (!Number.isFinite(value)) {
        fail("UNSUPPORTED_PAYLOAD_VALUE", `${normalizedBoundary} payload must be JSON-like`);
      }
      continue;
    }
    if (typeof value === "string") {
      inspectedCharacters += value.length;
      if (inspectedCharacters > MAX_PAYLOAD_CHARACTERS) {
        fail("PAYLOAD_LIMIT_EXCEEDED", `${normalizedBoundary} payload is too large`);
      }
      assertStringHasNoSecretSignal(value, normalizedBoundary);
      continue;
    }
    if (typeof value !== "object") {
      fail("UNSUPPORTED_PAYLOAD_VALUE", `${normalizedBoundary} payload must be JSON-like`);
    }
    if (ALL_SECRET_HANDLES.has(value)) {
      fail(
        "SECRET_HANDLE_BOUNDARY_DENIED",
        `opaque secret handles cannot enter ${normalizedBoundary}`,
      );
    }
    if (utilTypes.isProxy(value)) {
      fail("PROXY_INPUT_DENIED", `${normalizedBoundary} payload must not contain a Proxy`);
    }
    if (seen.has(value)) {
      fail("CYCLIC_PAYLOAD_DENIED", `${normalizedBoundary} payload must not contain cycles`);
    }
    seen.add(value);

    if (Array.isArray(value)) {
      const elements = readPlainArrayValues(value, `${normalizedBoundary} payload array`);
      for (let index = elements.length - 1; index >= 0; index -= 1) {
        stack.push({ value: elements[index], depth: depth + 1 });
      }
      continue;
    }

    const object = requirePlainRecord(value, `${normalizedBoundary} payload object`);
    const keys = Reflect.ownKeys(object);
    if (keys.length > MAX_OBJECT_FIELDS) {
      fail("PAYLOAD_LIMIT_EXCEEDED", `${normalizedBoundary} payload has too many fields`);
    }
    for (let index = keys.length - 1; index >= 0; index -= 1) {
      const key = keys[index];
      if (typeof key !== "string") {
        fail("UNSUPPORTED_PAYLOAD_VALUE", `${normalizedBoundary} payload has a symbol key`);
      }
      inspectedCharacters += key.length;
      if (
        key.length > MAX_FIELD_NAME_CHARACTERS ||
        inspectedCharacters > MAX_PAYLOAD_CHARACTERS
      ) {
        fail("PAYLOAD_LIMIT_EXCEEDED", `${normalizedBoundary} payload field names are too large`);
      }
      if (isSecretFieldName(key)) {
        fail(
          "SECRET_FIELD_BOUNDARY_DENIED",
          `${normalizedBoundary} payload contains a secret-bearing field`,
        );
      }
      const descriptor = Object.getOwnPropertyDescriptor(object, key);
      if (descriptor === undefined || !("value" in descriptor)) {
        fail("ACCESSOR_FIELD_DENIED", `${normalizedBoundary} payload must not contain accessors`);
      }
      stack.push({ value: descriptor.value, depth: depth + 1 });
    }
  }

  return Object.freeze({
    status: "PASS",
    boundary: normalizedBoundary,
    inspectedNodes,
    secretMaterialExposed: false,
    authorityEligible: false,
  });
};

const normalizePathForComparison = (value) => {
  const normalized = path.resolve(value);
  return process.platform === "win32" ? normalized.toLowerCase() : normalized;
};

const inspectResourceRoot = (rootPath, rootId, unavailableCode) => {
  const candidate = requireString(rootPath, "resourceRoot.path", { maxLength: 4_096 });
  if (!path.isAbsolute(candidate)) {
    fail("RESOURCE_ROOT_NOT_ABSOLUTE", `resource root ${rootId} must be absolute`);
  }
  const resolved = path.resolve(candidate);

  let stats;
  let canonical;
  try {
    stats = fs.lstatSync(resolved);
    canonical = fs.realpathSync.native(resolved);
  } catch {
    fail(unavailableCode, `resource root ${rootId} is not inspectable`);
  }
  if (!stats.isDirectory() || stats.isSymbolicLink()) {
    fail("RESOURCE_ROOT_UNSAFE", `resource root ${rootId} must be a real directory`);
  }
  if (normalizePathForComparison(resolved) !== normalizePathForComparison(canonical)) {
    fail("RESOURCE_ROOT_UNSAFE", `resource root ${rootId} crosses a link or alias`);
  }
  return Object.freeze({
    canonicalPath: canonical,
    identity: Object.freeze({
      device: stats.dev,
      inode: stats.ino,
      birthtimeMs: stats.birthtimeMs,
    }),
  });
};

const validateResourceRoot = (rootPath, rootId) =>
  inspectResourceRoot(rootPath, rootId, "RESOURCE_ROOT_UNAVAILABLE");

const assertResourceRootUnchanged = (root) => {
  const current = inspectResourceRoot(
    root.canonicalPath,
    root.rootId,
    "RESOURCE_ROOT_CHANGED",
  );
  if (
    current.identity.device !== root.identity.device ||
    current.identity.inode !== root.identity.inode ||
    current.identity.birthtimeMs !== root.identity.birthtimeMs
  ) {
    fail("RESOURCE_ROOT_CHANGED", `resource root ${root.rootId} changed after policy issue`);
  }
};

const parseOperations = (value, rootId) => {
  const operations = new Set();
  for (const operation of readPlainArrayValues(value, `resource root ${rootId} operations`)) {
    const normalized = requireString(operation, "pathOperation", { maxLength: 32 });
    if (!PATH_OPERATIONS.has(normalized)) {
      fail("UNKNOWN_PATH_OPERATION", `resource root ${rootId} has an unknown operation`);
    }
    if (operations.has(normalized)) {
      fail("DUPLICATE_PATH_OPERATION", `resource root ${rootId} repeats an operation`);
    }
    operations.add(normalized);
  }
  if (operations.size === 0) {
    fail("EMPTY_PATH_OPERATIONS", `resource root ${rootId} grants no operations`);
  }
  return operations;
};

const parseResourceRoots = (value) => {
  const roots = new Map();
  for (const rootValue of readPlainArrayValues(value, "resourceRoots")) {
    const root = requirePlainRecord(rootValue, "resourceRoot");
    rejectUnknownFields(root, new Set(["rootId", "path", "operations"]), "resourceRoot");
    const rootId = requireIdentifier(readDataProperty(root, "rootId"), "rootId");
    if (roots.has(rootId)) {
      fail("DUPLICATE_RESOURCE_ROOT", "resourceRoots contains a duplicate rootId");
    }
    const rootInspection = validateResourceRoot(readDataProperty(root, "path"), rootId);
    const operations = parseOperations(readDataProperty(root, "operations"), rootId);
    roots.set(
      rootId,
      Object.freeze({
        rootId,
        canonicalPath: rootInspection.canonicalPath,
        identity: rootInspection.identity,
        operations,
      }),
    );
  }
  return roots;
};

/**
 * Create a runtime-branded policy. The profile identifier is bound into every
 * authorization decision; actual sandbox isolation must be supplied and
 * separately qualified by the execution adapter.
 */
const issueExecutionPolicy = (executionPolicies, input) => {
  const record = requirePlainRecord(input, "executionPolicyInput");
  rejectUnknownFields(
    record,
    new Set([
      "policyId",
      "sandboxProfileId",
      "networkPolicy",
      "egressAllowlist",
      "resourceRoots",
    ]),
    "executionPolicyInput",
  );

  const policyId = requireIdentifier(readDataProperty(record, "policyId"), "policyId");
  const sandboxProfileId = requireIdentifier(
    readDataProperty(record, "sandboxProfileId"),
    "sandboxProfileId",
  );
  const networkPolicy = requireString(
    readDataProperty(record, "networkPolicy"),
    "networkPolicy",
    { maxLength: 64 },
  );
  if (!NETWORK_POLICIES.has(networkPolicy)) {
    fail(
      "UNSUPPORTED_NETWORK_POLICY",
      "only disabled or exact allowlist egress is implemented by this boundary",
    );
  }

  const egressAllowlist = parseOrigins(
    readDataProperty(record, "egressAllowlist"),
    "egressAllowlist",
  );
  if (networkPolicy === NETWORK_POLICY.DISABLED && egressAllowlist.size > 0) {
    fail("INCONSISTENT_NETWORK_POLICY", "disabled network policy cannot contain origins");
  }
  if (networkPolicy === NETWORK_POLICY.ALLOWLIST && egressAllowlist.size === 0) {
    fail("INCONSISTENT_NETWORK_POLICY", "allowlist network policy requires an origin");
  }

  const resourceRoots = parseResourceRoots(readDataProperty(record, "resourceRoots"));
  const policy = Object.freeze({
    schemaVersion: 1,
    kind: "execution_policy",
    policyId,
    sandboxProfileId,
  });
  executionPolicies.set(
    policy,
    Object.freeze({
      policyId,
      sandboxProfileId,
      networkPolicy,
      egressAllowlist,
      resourceRoots,
    }),
  );
  return policy;
};

const assertSandboxProfile = (executionPolicies, sealDecision, policy, observedProfileId) => {
  const record = getExecutionPolicyRecord(executionPolicies, policy);
  const observed = requireIdentifier(observedProfileId, "observedProfileId");
  if (observed !== record.sandboxProfileId) {
    fail("SANDBOX_PROFILE_MISMATCH", "observed sandbox profile does not match policy");
  }
  return sealDecision({
    decision: "ALLOW",
    policyId: record.policyId,
    sandboxProfileId: record.sandboxProfileId,
  });
};

const parsePortableRelativePath = (value) => {
  const relativePath = requireString(value, "relativePath", { maxLength: 4_096 });
  if (
    relativePath.includes("\\") ||
    relativePath.includes(":") ||
    path.posix.isAbsolute(relativePath) ||
    path.win32.isAbsolute(relativePath)
  ) {
    fail(
      "PATH_ESCAPE_DENIED",
      "resource paths must be portable forward-slash relative paths",
    );
  }

  const segments = relativePath.split("/");
  for (const segment of segments) {
    const windowsBaseName = segment.split(".", 1)[0].replace(/[ .]+$/u, "");
    if (
      segment.length === 0 ||
      segment === "." ||
      segment === ".." ||
      segment.endsWith(".") ||
      segment.endsWith(" ") ||
      WINDOWS_RESERVED_BASENAME.test(windowsBaseName)
    ) {
      fail("PATH_ESCAPE_DENIED", "resource path contains an unsafe component");
    }
  }
  return Object.freeze({ relativePath, segments: Object.freeze(segments) });
};

const assertExistingPathSegmentsNoFollow = (root, segments) => {
  let current = root.canonicalPath;
  for (let index = 0; index < segments.length; index += 1) {
    current = path.join(current, segments[index]);
    let stats;
    try {
      stats = fs.lstatSync(current);
    } catch (error) {
      if (error !== null && typeof error === "object" && error.code === "ENOENT") {
        if (index < segments.length - 1) {
          fail("PATH_PARENT_MISSING", "resource path has an unverified missing parent");
        }
        return false;
      }
      fail("PATH_INSPECTION_FAILED", "resource path could not be inspected safely");
    }

    if (stats.isSymbolicLink()) {
      fail("PATH_LINK_DENIED", "resource path crosses a symbolic link or reparse point");
    }
    if (stats.dev !== root.identity.device) {
      fail("PATH_MOUNT_DENIED", "resource path crosses a filesystem mount boundary");
    }
    if (index < segments.length - 1 && !stats.isDirectory()) {
      fail("PATH_NOT_TRAVERSABLE", "resource path crosses a non-directory component");
    }
    let canonical;
    try {
      canonical = fs.realpathSync.native(current);
    } catch {
      fail("PATH_INSPECTION_FAILED", "resource path could not be canonicalized safely");
    }
    if (normalizePathForComparison(current) !== normalizePathForComparison(canonical)) {
      fail("PATH_LINK_DENIED", "resource path crosses a link or path alias");
    }
    if (index === segments.length - 1 && !stats.isDirectory() && stats.nlink > 1) {
      fail("PATH_LINK_DENIED", "resource path targets a multiply-linked non-directory");
    }
  }
  return true;
};

const authorizePathAccess = (executionPolicies, sealDecision, policy, input) => {
  const policyRecord = getExecutionPolicyRecord(executionPolicies, policy);
  const request = requirePlainRecord(input, "pathAccessRequest");
  rejectUnknownFields(
    request,
    new Set(["rootId", "relativePath", "operation"]),
    "pathAccessRequest",
  );

  const rootId = requireIdentifier(readDataProperty(request, "rootId"), "rootId");
  const operation = requireString(readDataProperty(request, "operation"), "operation", {
    maxLength: 32,
  });
  if (!PATH_OPERATIONS.has(operation)) {
    fail("UNKNOWN_PATH_OPERATION", "path request contains an unknown operation");
  }
  const root = policyRecord.resourceRoots.get(rootId);
  if (root === undefined || !root.operations.has(operation)) {
    fail("PATH_SCOPE_DENIED", "path request is outside the granted resource scope");
  }
  assertResourceRootUnchanged(root);

  const parsed = parsePortableRelativePath(readDataProperty(request, "relativePath"));
  const candidate = path.resolve(root.canonicalPath, ...parsed.segments);
  const relative = path.relative(root.canonicalPath, candidate);
  if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    fail("PATH_ESCAPE_DENIED", "canonical resource path escapes its root");
  }
  const targetExists = assertExistingPathSegmentsNoFollow(root, parsed.segments);
  if (operation === PATH_OPERATION.CREATE && targetExists) {
    fail("PATH_TARGET_EXISTS", "create requires an absent final path component");
  }
  if (operation !== PATH_OPERATION.CREATE && !targetExists) {
    fail("PATH_TARGET_MISSING", `${operation} requires an existing target`);
  }

  return sealDecision({
    decision: "ALLOW",
    policyId: policyRecord.policyId,
    sandboxProfileId: policyRecord.sandboxProfileId,
    rootId,
    operation,
    relativePath: parsed.relativePath,
    canonicalPath: candidate,
    targetExists,
    noFollowChecked: true,
  });
};

const authorizeEgressOrigin = (policyRecord, url) => {
  if (policyRecord.networkPolicy === NETWORK_POLICY.DISABLED) {
    fail("EGRESS_DISABLED", "network egress is disabled by policy");
  }
  const { origin } = parseNetworkUrl(url);
  if (!policyRecord.egressAllowlist.has(origin)) {
    fail("EGRESS_DESTINATION_DENIED", "network destination is not exactly allowlisted");
  }
  return origin;
};

const authorizeEgress = (executionPolicies, sealDecision, policy, input) => {
  const policyRecord = getExecutionPolicyRecord(executionPolicies, policy);
  const request = requirePlainRecord(input, "egressRequest");
  rejectUnknownFields(request, new Set(["url", "payload"]), "egressRequest");
  const url = readDataProperty(request, "url");
  const origin = authorizeEgressOrigin(policyRecord, url);
  const payload = readDataProperty(request, "payload", { optional: true });
  if (payload !== undefined) {
    assertSecretFreeBoundaryPayload(payload, OUTBOUND_BOUNDARY.NETWORK_REQUEST);
  }

  return sealDecision({
    decision: "ALLOW",
    policyId: policyRecord.policyId,
    sandboxProfileId: policyRecord.sandboxProfileId,
    origin,
    redirectPolicy: "REAUTHORIZE_EACH_HOP",
    secretMaterialExposed: false,
  });
};

/**
 * Authorize last-mile use of an opaque secret reference. The decision exposes
 * neither secret bytes nor handle/vault identifiers. Resolution and injection
 * remain the responsibility of a separately trusted execution adapter.
 */
const authorizeSecretEgress = (
  secretHandles,
  executionPolicies,
  sealDecision,
  policy,
  input,
) => {
  const policyRecord = getExecutionPolicyRecord(executionPolicies, policy);
  const request = requirePlainRecord(input, "secretEgressRequest");
  rejectUnknownFields(request, new Set(["handle", "url"]), "secretEgressRequest");
  const handleRecord = getSecretHandleRecord(
    secretHandles,
    readDataProperty(request, "handle"),
  );
  const url = readDataProperty(request, "url");
  const origin = authorizeEgressOrigin(policyRecord, url);
  if (!handleRecord.allowedOrigins.has(origin)) {
    fail("SECRET_DESTINATION_DENIED", "secret handle is not bound to this destination");
  }

  return sealDecision({
    decision: "ALLOW",
    purpose: "network_authentication",
    policyId: policyRecord.policyId,
    sandboxProfileId: policyRecord.sandboxProfileId,
    origin,
    redirectPolicy: "REAUTHORIZE_EACH_HOP",
    opaqueHandleValidated: true,
    secretMaterialExposed: false,
  });
};

/**
 * Create an isolated authority compartment. The kernel bootstrap retains the
 * issuer and passes only the guard into effect paths. Objects issued by a
 * separately created boundary are foreign and fail closed, so importing this
 * module is not enough to mint authority accepted by the kernel boundary.
 */
export const createExecutionSecurityBoundary = () => {
  const secretHandles = new WeakMap();
  const executionPolicies = new WeakMap();
  const authorizationDecisions = new WeakSet();

  const sealDecision = (fields) => {
    const decision = Object.freeze(fields);
    authorizationDecisions.add(decision);
    return decision;
  };

  const issuer = Object.freeze({
    issueOpaqueSecretHandle: (input) => issueOpaqueSecretHandle(secretHandles, input),
    issueExecutionPolicy: (input) => issueExecutionPolicy(executionPolicies, input),
  });

  const guard = Object.freeze({
    isOpaqueSecretHandle: (value) =>
      value !== null && typeof value === "object" && secretHandles.has(value),
    isExecutionPolicy: (value) =>
      value !== null && typeof value === "object" && executionPolicies.has(value),
    isAuthorizationDecision: (value) =>
      value !== null && typeof value === "object" && authorizationDecisions.has(value),
    assertSecretFreeBoundaryPayload,
    assertSandboxProfile: (policy, observedProfileId) =>
      assertSandboxProfile(executionPolicies, sealDecision, policy, observedProfileId),
    authorizePathAccess: (policy, input) =>
      authorizePathAccess(executionPolicies, sealDecision, policy, input),
    authorizeEgress: (policy, input) =>
      authorizeEgress(executionPolicies, sealDecision, policy, input),
    authorizeSecretEgress: (policy, input) =>
      authorizeSecretEgress(
        secretHandles,
        executionPolicies,
        sealDecision,
        policy,
        input,
      ),
  });

  return Object.freeze({ issuer, guard });
};
