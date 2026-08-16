import { createHash, timingSafeEqual } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { types as utilTypes } from "node:util";

import {
  PATH_BOUNDARY,
  PATH_TARGET_MODE,
  readRootIdentity,
  resolveBoundaryPath,
  rootIdentitiesEqual,
  serializeRootIdentity,
} from "../../paths/path-resolution.mjs";

export const LOCAL_STDIO_BINDING_VERSION = "LOCAL_STDIO_READ_V1";
export const LOCAL_STDIO_BINDING_FILENAME = "local-stdio-binding.json";

const PROTOCOL_VERSION = "2026-07-28";
const MAX_BINDING_BYTES = 64 * 1024;
const BINDING_FIELDS = new Set([
  "binding_version",
  "protocol_version",
  "principal_id",
  "principal_type",
  "workspace_id",
  "workspace_root",
  "workspace_root_identity",
  "plugin_data_root_identity",
  "capabilities",
  "issued_at",
  "expires_at",
  "grant_hash",
]);
const PRINCIPAL_TYPES = new Set(["human", "agent", "service", "tool"]);
const CAPABILITY_PATTERN = /^mcp\.read\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$/u;
const HASH_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:[Zz]|([+-])(\d{2}):(\d{2}))$/u;

export class LocalStdioBindingError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "LocalStdioBindingError";
    this.code = code;
  }
}

const fail = (code, message) => {
  throw new LocalStdioBindingError(code, message);
};

const requirePlainRecord = (value, label) => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail("BINDING_INVALID", `${label} must be a plain object`);
  }
  if (utilTypes.isProxy(value)) {
    fail("BINDING_INVALID", `${label} must not be a Proxy`);
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    fail("BINDING_INVALID", `${label} must not have a custom prototype`);
  }
  return value;
};

const readDataProperty = (record, key) => {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  if (descriptor === undefined) {
    fail("BINDING_INVALID", `missing required field: ${key}`);
  }
  if (!("value" in descriptor)) {
    fail("BINDING_INVALID", `${key} must be a data property`);
  }
  return descriptor.value;
};

const rejectUnknownFields = (record) => {
  for (const key of Reflect.ownKeys(record)) {
    if (typeof key !== "string" || !BINDING_FIELDS.has(key)) {
      fail("BINDING_INVALID", "binding contains an unexpected field");
    }
  }
};

const requireText = (value, label, minimum = 1, maximum = 128) => {
  if (
    typeof value !== "string" ||
    value.length < minimum ||
    value.length > maximum ||
    /\p{Cc}/u.test(value)
  ) {
    fail("BINDING_INVALID", `${label} is not canonical`);
  }
  return value;
};

const isLeapYear = (year) =>
  year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

const daysInMonth = (year, month) => {
  if (month === 2) return isLeapYear(year) ? 29 : 28;
  return month === 4 || month === 6 || month === 9 || month === 11 ? 30 : 31;
};

const parseRfc3339 = (value) => {
  if (typeof value !== "string") return null;
  const match = RFC3339_PATTERN.exec(value);
  if (match === null || match[0].length !== value.length) return null;

  let year = Number(match[1]);
  const month = Number(match[2]);
  let day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const fraction = match[7] ?? "";
  const offsetHour = match[9] === undefined ? 0 : Number(match[9]);
  const offsetMinute = match[10] === undefined ? 0 : Number(match[10]);
  if (
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > daysInMonth(year, month) ||
    hour > 23 ||
    minute > 59 ||
    second > 60 ||
    offsetHour > 23 ||
    offsetMinute > 59
  ) {
    return null;
  }

  let utcMonth = month;
  let utcMinuteOfDay = hour * 60 + minute;
  if (match[8] === "+") {
    utcMinuteOfDay -= offsetHour * 60 + offsetMinute;
  } else if (match[8] === "-") {
    utcMinuteOfDay += offsetHour * 60 + offsetMinute;
  }
  if (utcMinuteOfDay < 0) {
    utcMinuteOfDay += 1_440;
    day -= 1;
    if (day === 0) {
      utcMonth -= 1;
      if (utcMonth === 0) {
        year -= 1;
        utcMonth = 12;
      }
      day = daysInMonth(year, utcMonth);
    }
  } else if (utcMinuteOfDay >= 1_440) {
    utcMinuteOfDay -= 1_440;
    day += 1;
    if (day > daysInMonth(year, utcMonth)) {
      day = 1;
      utcMonth += 1;
      if (utcMonth === 13) {
        year += 1;
        utcMonth = 1;
      }
    }
  }

  const utcMinute = utcMinuteOfDay % 60;
  const utcHour = (utcMinuteOfDay - utcMinute) / 60;
  if (
    second === 60 &&
    (utcHour !== 23 ||
      utcMinute !== 59 ||
      day !== daysInMonth(year, utcMonth))
  ) {
    return null;
  }
  return Object.freeze([year, utcMonth, day, utcHour, utcMinute, second, fraction]);
};

const compareRfc3339 = (left, right) => {
  const leftTuple = parseRfc3339(left);
  const rightTuple = parseRfc3339(right);
  if (leftTuple === null || rightTuple === null) {
    fail("BINDING_INVALID", "RFC 3339 comparison requires valid timestamps");
  }
  for (let index = 0; index < 6; index += 1) {
    if (leftTuple[index] < rightTuple[index]) return -1;
    if (leftTuple[index] > rightTuple[index]) return 1;
  }
  const leftFraction = leftTuple[6];
  const rightFraction = rightTuple[6];
  const length = Math.max(leftFraction.length, rightFraction.length);
  for (let index = 0; index < length; index += 1) {
    const leftDigit = index < leftFraction.length ? leftFraction.charCodeAt(index) : 48;
    const rightDigit = index < rightFraction.length ? rightFraction.charCodeAt(index) : 48;
    if (leftDigit < rightDigit) return -1;
    if (leftDigit > rightDigit) return 1;
  }
  return 0;
};

const requireTimestamp = (value, label) => {
  if (parseRfc3339(value) === null) {
    fail("BINDING_INVALID", `${label} is not a real RFC 3339 date-time`);
  }
  return value;
};

const requireCanonicalWorkspaceRoot = (value) => {
  const candidate = requireText(value, "workspace_root", 1, 4096);
  if (
    !path.isAbsolute(candidate) ||
    path.resolve(candidate) !== candidate ||
    path.normalize(candidate) !== candidate
  ) {
    fail("BINDING_INVALID", "workspace_root is not a canonical absolute path");
  }
  return candidate;
};

const canonicalRootIdentity = (value, label) => {
  try {
    return Object.freeze(JSON.parse(serializeRootIdentity(value)));
  } catch {
    fail("BINDING_INVALID", `${label} is not a canonical G03 root identity`);
  }
};

const requireCapabilities = (value) => {
  if (!Array.isArray(value) || utilTypes.isProxy(value)) {
    fail("BINDING_INVALID", "capabilities must be an array");
  }
  if (Object.getPrototypeOf(value) !== Array.prototype || value.length === 0) {
    fail("BINDING_INVALID", "capabilities must be a non-empty canonical array");
  }
  const capabilities = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (descriptor === undefined || !("value" in descriptor)) {
      fail("BINDING_INVALID", "capabilities must contain data properties only");
    }
    const capability = descriptor.value;
    if (typeof capability !== "string" || !CAPABILITY_PATTERN.test(capability)) {
      fail("BINDING_INVALID", "capabilities contains a noncanonical value");
    }
    capabilities.push(capability);
  }
  const allowedKeys = new Set(["length", ...capabilities.map((_value, index) => String(index))]);
  for (const key of Reflect.ownKeys(value)) {
    if (typeof key !== "string" || !allowedKeys.has(key)) {
      fail("BINDING_INVALID", "capabilities contains an unexpected field");
    }
  }
  const canonical = [...capabilities].sort();
  if (
    new Set(capabilities).size !== capabilities.length ||
    capabilities.some((capability, index) => capability !== canonical[index])
  ) {
    fail("BINDING_INVALID", "capabilities must be unique and sorted");
  }
  return Object.freeze(capabilities);
};

const normalizeBinding = (candidate, { requireGrantHash }) => {
  const record = requirePlainRecord(candidate, "binding");
  rejectUnknownFields(record);

  const bindingVersion = readDataProperty(record, "binding_version");
  const protocolVersion = readDataProperty(record, "protocol_version");
  if (bindingVersion !== LOCAL_STDIO_BINDING_VERSION) {
    fail("BINDING_VERSION_MISMATCH", "binding_version is not supported");
  }
  if (protocolVersion !== PROTOCOL_VERSION) {
    fail("PROTOCOL_VERSION_MISMATCH", "protocol_version is not supported");
  }

  const principalId = requireText(readDataProperty(record, "principal_id"), "principal_id", 3);
  const principalType = readDataProperty(record, "principal_type");
  if (!PRINCIPAL_TYPES.has(principalType)) {
    fail("BINDING_INVALID", "principal_type is not canonical");
  }
  const workspaceId = requireText(readDataProperty(record, "workspace_id"), "workspace_id", 3);
  const workspaceRoot = requireCanonicalWorkspaceRoot(
    readDataProperty(record, "workspace_root"),
  );
  const workspaceRootIdentity = canonicalRootIdentity(
    readDataProperty(record, "workspace_root_identity"),
    "workspace_root_identity",
  );
  const pluginDataRootIdentity = canonicalRootIdentity(
    readDataProperty(record, "plugin_data_root_identity"),
    "plugin_data_root_identity",
  );
  const capabilities = requireCapabilities(readDataProperty(record, "capabilities"));
  const issuedAt = requireTimestamp(readDataProperty(record, "issued_at"), "issued_at");
  const expiresAt = requireTimestamp(readDataProperty(record, "expires_at"), "expires_at");
  if (compareRfc3339(expiresAt, issuedAt) <= 0) {
    fail("BINDING_INVALID", "expires_at must be later than issued_at");
  }

  const grantDescriptor = Object.getOwnPropertyDescriptor(record, "grant_hash");
  if (requireGrantHash && grantDescriptor === undefined) {
    fail("BINDING_INVALID", "missing required field: grant_hash");
  }
  if (grantDescriptor !== undefined && !("value" in grantDescriptor)) {
    fail("BINDING_INVALID", "grant_hash must be a data property");
  }
  const grantHash = grantDescriptor?.value ?? null;
  if (grantHash !== null && (typeof grantHash !== "string" || !HASH_PATTERN.test(grantHash))) {
    fail("BINDING_INVALID", "grant_hash is not canonical");
  }

  return Object.freeze({
    binding_version: bindingVersion,
    protocol_version: protocolVersion,
    principal_id: principalId,
    principal_type: principalType,
    workspace_id: workspaceId,
    workspace_root: workspaceRoot,
    workspace_root_identity: workspaceRootIdentity,
    plugin_data_root_identity: pluginDataRootIdentity,
    capabilities,
    issued_at: issuedAt,
    expires_at: expiresAt,
    grant_hash: grantHash,
  });
};

const grantPreimage = (binding) =>
  JSON.stringify({
    binding_version: binding.binding_version,
    capabilities: binding.capabilities,
    expires_at: binding.expires_at,
    issued_at: binding.issued_at,
    plugin_data_root_identity: binding.plugin_data_root_identity,
    principal_id: binding.principal_id,
    principal_type: binding.principal_type,
    protocol_version: binding.protocol_version,
    workspace_id: binding.workspace_id,
    workspace_root: binding.workspace_root,
    workspace_root_identity: binding.workspace_root_identity,
  });

const deriveNormalizedGrantHash = (binding) =>
  `sha256:${createHash("sha256").update(grantPreimage(binding), "utf8").digest("hex")}`;

/** Derive the only LOCAL_STDIO_READ_V1 grant preimage and digest. */
export const deriveLocalStdioBindingGrantHash = (candidate) =>
  deriveNormalizedGrantHash(normalizeBinding(candidate, { requireGrantHash: false }));

const hashesEqual = (left, right) => {
  const leftBytes = Buffer.from(left, "ascii");
  const rightBytes = Buffer.from(right, "ascii");
  return leftBytes.length === rightBytes.length && timingSafeEqual(leftBytes, rightBytes);
};

const readBindingDocument = (canonicalPath) => {
  let descriptor;
  try {
    const noFollowFlag =
      process.platform === "win32" ? 0 : (fs.constants.O_NOFOLLOW ?? 0);
    descriptor = fs.openSync(
      canonicalPath,
      fs.constants.O_RDONLY | noFollowFlag,
    );
    const stats = fs.fstatSync(descriptor);
    if (!stats.isFile() || stats.size <= 0 || stats.size > MAX_BINDING_BYTES) {
      fail("BINDING_INVALID", "binding file is outside the accepted size contract");
    }
    return fs.readFileSync(descriptor, "utf8");
  } catch (error) {
    if (error instanceof LocalStdioBindingError) throw error;
    fail("BINDING_UNAVAILABLE", "binding file could not be opened");
  } finally {
    if (descriptor !== undefined) {
      try {
        fs.closeSync(descriptor);
      } catch {
        // The public authentication result remains redacted.
      }
    }
  }
};

/** Recheck one authenticated binding against the resolver-issued roots. */
export const assertLocalStdioBindingRoots = (binding, resolution) => {
  const workspaceIdentity = readRootIdentity(resolution, PATH_BOUNDARY.WORKSPACE_ROOT);
  const pluginDataIdentity = readRootIdentity(resolution, PATH_BOUNDARY.PLUGIN_DATA);
  if (
    binding.workspace_root !== resolution.workspaceRoot ||
    !rootIdentitiesEqual(binding.workspace_root_identity, workspaceIdentity) ||
    !rootIdentitiesEqual(binding.plugin_data_root_identity, pluginDataIdentity)
  ) {
    fail("BINDING_ROOT_MISMATCH", "binding roots do not match the resolved roots");
  }
};

/** Load, authenticate, and freeze the binding at the G03 PLUGIN_DATA boundary. */
export const loadLocalStdioBinding = ({ resolution, now }) => {
  const evaluatedAt = requireTimestamp(now, "now");
  const bindingPath = resolveBoundaryPath(resolution, {
    boundary: PATH_BOUNDARY.PLUGIN_DATA,
    relativePath: LOCAL_STDIO_BINDING_FILENAME,
    targetMode: PATH_TARGET_MODE.EXISTING,
  });
  let parsed;
  try {
    parsed = JSON.parse(readBindingDocument(bindingPath.canonicalPath));
  } catch (error) {
    if (error instanceof LocalStdioBindingError) throw error;
    fail("BINDING_INVALID", "binding file is not valid JSON");
  }

  const binding = normalizeBinding(parsed, { requireGrantHash: true });
  const derived = deriveNormalizedGrantHash(binding);
  if (!hashesEqual(binding.grant_hash, derived)) {
    fail("BINDING_DIGEST_MISMATCH", "binding grant_hash does not match its projection");
  }
  if (
    compareRfc3339(evaluatedAt, binding.issued_at) < 0 ||
    compareRfc3339(evaluatedAt, binding.expires_at) >= 0
  ) {
    fail("BINDING_INACTIVE", "binding is not active at the evaluated time");
  }
  assertLocalStdioBindingRoots(binding, resolution);
  return binding;
};
