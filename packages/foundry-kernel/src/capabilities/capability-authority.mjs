/**
 * Capability leases, fencing, and immutable approval records.
 *
 * Public commands deliberately cannot assert authority roles, principal types,
 * issue times, policy hashes, fencing tokens, or record hashes. Those values are
 * derived from a sealed policy projection, the authority clock, and D01 state.
 * Lease-protected mutations and their event outbox entry commit in one D01
 * transaction. E01 publication is idempotent and explicitly reconcilable.
 */

import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const NUMBER_IS_FINITE = Number.isFinite;
const NUMBER_IS_SAFE_INTEGER = Number.isSafeInteger;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const OBJECT_IS = Object.is;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;

const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|([+-])(\d{2}):(\d{2}))$/u;
const EVENT_SCHEMA_VERSION = "4.0.0";
const EVENT_ACTOR_ID = "ACT-E03-capability-authority";
const COUNTER_ID = "global";
const OUTBOX_INDEX_ID = "global";

const LEASE_KEYS = OBJECT_FREEZE([
  "lease_id",
  "principal_id",
  "principal_type",
  "capabilities",
  "resource_scopes",
  "issued_at",
  "expires_at",
  "fencing_token",
  "policy_hash",
  "approval_ids",
  "revoked",
  "revocation_reason",
  "lease_hash",
]);
const LEASE_HASH_KEYS = OBJECT_FREEZE(LEASE_KEYS.filter((key) => key !== "lease_hash"));
const APPROVAL_KEYS = OBJECT_FREEZE([
  "approval_id",
  "run_id",
  "subject_id",
  "approval_type",
  "decision",
  "authority_id",
  "authority_role",
  "reason",
  "evidence_artifact_ids",
  "conditions",
  "issued_at",
  "expires_at",
  "record_hash",
]);
const APPROVAL_HASH_KEYS = OBJECT_FREEZE(
  APPROVAL_KEYS.filter((key) => key !== "record_hash"),
);
const POLICY_KEYS = OBJECT_FREEZE([
  "policy_hash",
  "principals",
  "subjects",
  "approval_rules",
  "capability_rules",
]);
const POLICY_PROJECTION_KEYS = OBJECT_FREEZE([
  "policy_hash",
  "principals",
  "subjects",
  "approval_rules",
  "capability_rules",
]);
const PRINCIPAL_KEYS = OBJECT_FREEZE([
  "principal_id",
  "principal_type",
  "identity_class",
  "capabilities",
  "resource_scopes",
  "authority_role",
  "approval_types",
]);
const SUBJECT_KEYS = OBJECT_FREEZE([
  "subject_id",
  "run_id",
  "maker_principal_ids",
  "capabilities",
  "resource_scopes",
]);
const APPROVAL_RULE_KEYS = OBJECT_FREEZE([
  "approval_type",
  "authority_roles",
  "evidence_required",
]);
const CAPABILITY_RULE_KEYS = OBJECT_FREEZE(["capability", "required_approval_type"]);
const LEASE_COMMAND_KEYS = OBJECT_FREEZE([
  "lease_id",
  "run_id",
  "principal_id",
  "capabilities",
  "resource_scopes",
  "expires_at",
  "approval_ids",
]);
const APPROVAL_COMMAND_KEYS = OBJECT_FREEZE([
  "approval_id",
  "run_id",
  "subject_id",
  "approval_type",
  "decision",
  "reason",
  "evidence_artifact_ids",
  "conditions",
  "expires_at",
]);
const REVOKE_COMMAND_KEYS = OBJECT_FREEZE(["lease_id", "run_id", "reason"]);
const USE_COMMAND_KEYS = OBJECT_FREEZE([
  "operation_id",
  "run_id",
  "lease",
  "principal_id",
  "capability",
  "resource_scopes",
]);

const PRINCIPAL_TYPES = new Set(["human", "agent", "service", "tool"]);
const IDENTITY_CLASSES = new Set([
  "human",
  "agent",
  "service",
  "tool",
  "candidate",
  "model",
  "prompt",
  "backend",
]);
const UNTRUSTED_AUTHORITY_CLASSES = new Set(["candidate", "model", "prompt", "backend"]);
const APPROVAL_TYPES = new Set([
  "capability",
  "external_effect",
  "high_risk_validation",
  "human_override",
  "release",
  "data_access",
]);
const APPROVAL_DECISIONS = new Set(["APPROVE", "DENY", "EXPIRE", "REVOKE"]);

export const PRIVILEGED_CAPABILITIES = OBJECT_FREEZE([
  "holdout:read",
  "evaluator:write",
  "policy:write",
  "promotion:approve",
  "promotion:commit",
  "approval:issue",
  "ledger:rewrite",
  "capability:issue",
  "capability:revoke",
]);
const PRIVILEGED_CAPABILITY_SET = new Set(PRIVILEGED_CAPABILITIES);

export const CAPABILITY_RECORD_TYPES = OBJECT_FREEZE({
  APPROVAL: "foundry.capabilities.approval.v1",
  APPROVAL_BINDING: "foundry.capabilities.approval-binding.v1",
  APPROVAL_HEAD: "foundry.capabilities.approval-head.v1",
  FENCING_COUNTER: "foundry.capabilities.fencing-counter.v1",
  LEASE: "foundry.capabilities.lease.v1",
  LEASE_BINDING: "foundry.capabilities.lease-binding.v1",
  LEASE_USE: "foundry.capabilities.lease-use.v1",
  OUTBOX: "foundry.capabilities.outbox.v1",
  OUTBOX_INDEX: "foundry.capabilities.outbox-index.v1",
  SCOPE_HEAD: "foundry.capabilities.scope-head.v1",
});
const CAPABILITY_RECORD_TYPE_SET = new Set(Object.values(CAPABILITY_RECORD_TYPES));

export const CAPABILITY_EVENT_TYPES = OBJECT_FREEZE({
  APPROVAL_RECORDED: "capability.approval.recorded",
  LEASE_ISSUED: "capability.lease.issued",
  LEASE_REVOKED: "capability.lease.revoked",
  LEASE_USE_COMMITTED: "capability.lease-use.committed",
});

export class CapabilityAuthorityError extends Error {
  constructor(code, message, details = undefined, options = undefined) {
    super(message, options);
    this.name = "CapabilityAuthorityError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze({ ...details });
  }
}

const fail = (code, message, details, options) => {
  throw new CapabilityAuthorityError(code, message, details, options);
};

const dependencyCauseCode = (error) =>
  error !== null && typeof error === "object" && typeof error.code === "string"
    ? error.code
    : error instanceof Error
      ? error.name
      : "unknown";

const hasOnlyUnicodeScalars = (value) => {
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      return false;
    }
  }
  return true;
};

const requireNonEmptyString = (value, label, code = "INVALID_INPUT") => {
  if (typeof value !== "string" || value.length === 0 || !hasOnlyUnicodeScalars(value)) {
    fail(code, `${label} must be a non-empty Unicode scalar string`);
  }
  return value;
};

const requireBoundedString = (
  value,
  label,
  { minLength = 1, maxLength = Number.MAX_SAFE_INTEGER, code = "INVALID_INPUT" } = {},
) => {
  const normalized = requireNonEmptyString(value, label, code);
  if (normalized.length < minLength || normalized.length > maxLength) {
    fail(code, `${label} must contain between ${minLength} and ${maxLength} characters`);
  }
  return normalized;
};

const requireNullableString = (value, label, code = "INVALID_INPUT") => {
  if (value === null) return null;
  return requireNonEmptyString(value, label, code);
};

const requirePlainDataObject = (
  value,
  label,
  { allowedKeys, requiredKeys = allowedKeys, code = "INVALID_INPUT" },
) => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    (OBJECT_GET_PROTOTYPE_OF(value) !== PLAIN_OBJECT_PROTOTYPE &&
      OBJECT_GET_PROTOTYPE_OF(value) !== null)
  ) {
    fail(code, `${label} must be a plain data object`);
  }
  const allowed = new Set(allowedKeys);
  const keys = REFLECT_OWN_KEYS(value);
  for (let index = 0; index < keys.length; index += 1) {
    const key = keys[index];
    if (typeof key !== "string" || !allowed.has(key)) {
      fail(code, `${label} contains an unsupported field`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail(code, `${label}.${key} must be an enumerable data property`);
    }
  }
  for (let index = 0; index < requiredKeys.length; index += 1) {
    if (!OBJECT_HAS_OWN(value, requiredKeys[index])) {
      fail(code, `${label}.${requiredKeys[index]} is required`);
    }
  }
  return value;
};

const readDataProperty = (object, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(object, key).value;

const isCanonicalArrayIndex = (key, length) => {
  if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) return false;
  const index = Number(key);
  return NUMBER_IS_SAFE_INTEGER(index) && index >= 0 && index < length && String(index) === key;
};

const readDenseArray = (value, label, code = "INVALID_INPUT") => {
  if (!ARRAY_IS_ARRAY(value) || IS_PROXY(value)) fail(code, `${label} must be a dense array`);
  const keys = REFLECT_OWN_KEYS(value);
  for (let index = 0; index < keys.length; index += 1) {
    const key = keys[index];
    if (key === "length") continue;
    if (!isCanonicalArrayIndex(key, value.length)) {
      fail(code, `${label} contains a non-element property`);
    }
  }
  const result = new Array(value.length);
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail(code, `${label} contains a sparse or accessor element`);
    }
    result[index] = descriptor.value;
  }
  return result;
};

const requireStringArray = (
  value,
  label,
  { minItems = 0, unique = false, sort = false, code = "INVALID_INPUT" } = {},
) => {
  const entries = readDenseArray(value, label, code).map((entry, index) =>
    requireNonEmptyString(entry, `${label}[${index}]`, code),
  );
  if (entries.length < minItems) fail(code, `${label} must contain at least ${minItems} item(s)`);
  if (unique && new Set(entries).size !== entries.length) {
    fail(code, `${label} must not contain duplicate values`);
  }
  if (sort) entries.sort();
  return OBJECT_FREEZE(entries);
};

const isLeapYear = (year) => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

const isRfc3339 = (value) => {
  if (typeof value !== "string" || !hasOnlyUnicodeScalars(value)) return false;
  const match = RFC3339_PATTERN.exec(value);
  if (match === null) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const offsetHour = match[8] === undefined ? 0 : Number(match[8]);
  const offsetMinute = match[9] === undefined ? 0 : Number(match[9]);
  const monthLengths = [31, isLeapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return (
    year >= 1 &&
    month >= 1 &&
    month <= 12 &&
    day >= 1 &&
    day <= monthLengths[month - 1] &&
    hour <= 23 &&
    minute <= 59 &&
    second <= 59 &&
    offsetHour <= 23 &&
    offsetMinute <= 59 &&
    NUMBER_IS_FINITE(Date.parse(value))
  );
};

const requireTimestamp = (value, label, code = "INVALID_INPUT") => {
  if (!isRfc3339(value)) fail(code, `${label} must be a real RFC 3339 date-time`);
  return value;
};

const assertCanonicalJsonValue = (value, label = "value", ancestors = new WeakSet()) => {
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") {
    if (!hasOnlyUnicodeScalars(value)) fail("NON_CANONICAL_JSON", `${label} has invalid Unicode`);
    return;
  }
  if (typeof value === "number") {
    if (!NUMBER_IS_FINITE(value) || OBJECT_IS(value, -0)) {
      fail("NON_CANONICAL_JSON", `${label} contains a non-canonical number`);
    }
    return;
  }
  if (typeof value !== "object" || IS_PROXY(value)) {
    fail("NON_CANONICAL_JSON", `${label} contains a non-JSON value`);
  }
  if (ancestors.has(value)) fail("NON_CANONICAL_JSON", `${label} contains a cycle`);
  ancestors.add(value);
  try {
    if (ARRAY_IS_ARRAY(value)) {
      const entries = readDenseArray(value, label, "NON_CANONICAL_JSON");
      for (let index = 0; index < entries.length; index += 1) {
        assertCanonicalJsonValue(entries[index], `${label}[${index}]`, ancestors);
      }
      return;
    }
    const prototype = OBJECT_GET_PROTOTYPE_OF(value);
    if (prototype !== PLAIN_OBJECT_PROTOTYPE && prototype !== null) {
      fail("NON_CANONICAL_JSON", `${label} must contain only plain JSON objects`);
    }
    const keys = REFLECT_OWN_KEYS(value);
    for (let index = 0; index < keys.length; index += 1) {
      const key = keys[index];
      if (typeof key !== "string" || !hasOnlyUnicodeScalars(key)) {
        fail("NON_CANONICAL_JSON", `${label} has a non-canonical property name`);
      }
      const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
      if (
        descriptor === undefined ||
        !descriptor.enumerable ||
        !OBJECT_HAS_OWN(descriptor, "value")
      ) {
        fail("NON_CANONICAL_JSON", `${label}.${key} must be a data property`);
      }
      assertCanonicalJsonValue(descriptor.value, `${label}.${key}`, ancestors);
    }
  } finally {
    ancestors.delete(value);
  }
};

const renderCanonicalJson = (value) => {
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "number") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (ARRAY_IS_ARRAY(value)) {
    let rendered = "[";
    for (let index = 0; index < value.length; index += 1) {
      if (index !== 0) rendered += ",";
      rendered += renderCanonicalJson(readDataProperty(value, String(index)));
    }
    return `${rendered}]`;
  }
  const keys = Object.keys(value).sort();
  let rendered = "{";
  for (let index = 0; index < keys.length; index += 1) {
    if (index !== 0) rendered += ",";
    const key = keys[index];
    rendered += `${JSON.stringify(key)}:${renderCanonicalJson(readDataProperty(value, key))}`;
  }
  return `${rendered}}`;
};

export const canonicalCapabilityJson = (value) => {
  assertCanonicalJsonValue(value);
  return renderCanonicalJson(value);
};

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of REFLECT_OWN_KEYS(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};

const canonicalClone = (value) => deepFreeze(JSON.parse(canonicalCapabilityJson(value)));
const sha256Text = (value) =>
  `sha256:${createHash("sha256").update(value, "utf8").digest("hex")}`;
const sha256CanonicalJson = (value) => sha256Text(canonicalCapabilityJson(value));

const selectHashFields = (candidate, keys, label, code) => {
  const result = {};
  for (let index = 0; index < keys.length; index += 1) {
    const key = keys[index];
    if (!OBJECT_HAS_OWN(candidate, key)) fail(code, `${label}.${key} is required for hashing`);
    result[key] = readDataProperty(candidate, key);
  }
  return result;
};

export const computeCapabilityLeaseHash = (lease) =>
  sha256CanonicalJson(selectHashFields(lease, LEASE_HASH_KEYS, "CapabilityLease", "LEASE_INVALID"));

export const computeApprovalRecordHash = (approval) =>
  sha256CanonicalJson(
    selectHashFields(approval, APPROVAL_HASH_KEYS, "ApprovalRecord", "APPROVAL_INVALID"),
  );

const sameCanonical = (left, right) => canonicalCapabilityJson(left) === canonicalCapabilityJson(right);

const normalizeLease = (candidate, { sealed = true } = {}) => {
  const lease = requirePlainDataObject(candidate, "CapabilityLease", {
    allowedKeys: sealed ? LEASE_KEYS : LEASE_HASH_KEYS,
    code: "LEASE_INVALID",
  });
  const principalType = readDataProperty(lease, "principal_type");
  if (!PRINCIPAL_TYPES.has(principalType)) fail("LEASE_INVALID", "principal_type is not canonical");
  const issuedAt = requireTimestamp(readDataProperty(lease, "issued_at"), "issued_at", "LEASE_INVALID");
  const expiresAt = requireTimestamp(readDataProperty(lease, "expires_at"), "expires_at", "LEASE_INVALID");
  if (Date.parse(issuedAt) >= Date.parse(expiresAt)) {
    fail("LEASE_INVALID", "CapabilityLease must expire strictly after it is issued");
  }
  const fencingToken = readDataProperty(lease, "fencing_token");
  if (!NUMBER_IS_SAFE_INTEGER(fencingToken) || fencingToken < 1) {
    fail("LEASE_INVALID", "fencing_token must be a positive safe integer");
  }
  const policyHash = readDataProperty(lease, "policy_hash");
  if (typeof policyHash !== "string" || !SHA256_PATTERN.test(policyHash)) {
    fail("LEASE_INVALID", "policy_hash must be a canonical SHA-256 digest");
  }
  const revoked = readDataProperty(lease, "revoked");
  if (typeof revoked !== "boolean") fail("LEASE_INVALID", "revoked must be boolean");
  const revocationReason = requireNullableString(
    readDataProperty(lease, "revocation_reason"),
    "revocation_reason",
    "LEASE_INVALID",
  );
  if ((revoked && revocationReason === null) || (!revoked && revocationReason !== null)) {
    fail("LEASE_INVALID", "revocation_reason must exist exactly when revoked is true");
  }
  const normalized = {
    lease_id: requireBoundedString(readDataProperty(lease, "lease_id"), "lease_id", {
      minLength: 3,
      maxLength: 128,
      code: "LEASE_INVALID",
    }),
    principal_id: requireBoundedString(
      readDataProperty(lease, "principal_id"),
      "principal_id",
      { minLength: 3, maxLength: 128, code: "LEASE_INVALID" },
    ),
    principal_type: principalType,
    capabilities: requireStringArray(readDataProperty(lease, "capabilities"), "capabilities", {
      minItems: 1,
      unique: true,
      sort: true,
      code: "LEASE_INVALID",
    }),
    resource_scopes: requireStringArray(
      readDataProperty(lease, "resource_scopes"),
      "resource_scopes",
      { minItems: 1, unique: true, sort: true, code: "LEASE_INVALID" },
    ),
    issued_at: issuedAt,
    expires_at: expiresAt,
    fencing_token: fencingToken,
    policy_hash: policyHash,
    approval_ids: requireStringArray(readDataProperty(lease, "approval_ids"), "approval_ids", {
      unique: true,
      sort: true,
      code: "LEASE_INVALID",
    }),
    revoked,
    revocation_reason: revocationReason,
  };
  for (let index = 0; index < normalized.approval_ids.length; index += 1) {
    requireBoundedString(normalized.approval_ids[index], `approval_ids[${index}]`, {
      minLength: 3,
      maxLength: 128,
      code: "LEASE_INVALID",
    });
  }
  if (!sealed) return canonicalClone(normalized);
  const leaseHash = readDataProperty(lease, "lease_hash");
  if (typeof leaseHash !== "string" || !SHA256_PATTERN.test(leaseHash)) {
    fail("LEASE_INVALID", "lease_hash must be a canonical SHA-256 digest");
  }
  const complete = { ...normalized, lease_hash: leaseHash };
  const expected = computeCapabilityLeaseHash(complete);
  if (leaseHash !== expected) {
    fail("LEASE_HASH_MISMATCH", "lease_hash does not match canonical fields", {
      actual: leaseHash,
      expected,
      leaseId: normalized.lease_id,
    });
  }
  return canonicalClone(complete);
};

const sealLease = (candidate) => {
  const normalized = normalizeLease(candidate, { sealed: false });
  return canonicalClone({ ...normalized, lease_hash: computeCapabilityLeaseHash(normalized) });
};

const normalizeApproval = (candidate, { sealed = true } = {}) => {
  const approval = requirePlainDataObject(candidate, "ApprovalRecord", {
    allowedKeys: sealed ? APPROVAL_KEYS : APPROVAL_HASH_KEYS,
    code: "APPROVAL_INVALID",
  });
  const approvalType = readDataProperty(approval, "approval_type");
  if (!APPROVAL_TYPES.has(approvalType)) fail("APPROVAL_INVALID", "approval_type is not canonical");
  const decision = readDataProperty(approval, "decision");
  if (!APPROVAL_DECISIONS.has(decision)) fail("APPROVAL_INVALID", "decision is not canonical");
  const issuedAt = requireTimestamp(
    readDataProperty(approval, "issued_at"),
    "issued_at",
    "APPROVAL_INVALID",
  );
  const rawExpiresAt = readDataProperty(approval, "expires_at");
  const expiresAt =
    rawExpiresAt === null
      ? null
      : requireTimestamp(rawExpiresAt, "expires_at", "APPROVAL_INVALID");
  if (expiresAt !== null && Date.parse(expiresAt) <= Date.parse(issuedAt)) {
    fail("APPROVAL_INVALID", "expires_at must be later than issued_at");
  }
  const normalized = {
    approval_id: requireNonEmptyString(
      readDataProperty(approval, "approval_id"),
      "approval_id",
      "APPROVAL_INVALID",
    ),
    run_id: requireNonEmptyString(readDataProperty(approval, "run_id"), "run_id", "APPROVAL_INVALID"),
    subject_id: requireNonEmptyString(
      readDataProperty(approval, "subject_id"),
      "subject_id",
      "APPROVAL_INVALID",
    ),
    approval_type: approvalType,
    decision,
    authority_id: requireNonEmptyString(
      readDataProperty(approval, "authority_id"),
      "authority_id",
      "APPROVAL_INVALID",
    ),
    authority_role: requireNonEmptyString(
      readDataProperty(approval, "authority_role"),
      "authority_role",
      "APPROVAL_INVALID",
    ),
    reason: requireNonEmptyString(readDataProperty(approval, "reason"), "reason", "APPROVAL_INVALID"),
    evidence_artifact_ids: requireStringArray(
      readDataProperty(approval, "evidence_artifact_ids"),
      "evidence_artifact_ids",
      { unique: true, sort: true, code: "APPROVAL_INVALID" },
    ),
    conditions: requireStringArray(readDataProperty(approval, "conditions"), "conditions", {
      unique: true,
      sort: true,
      code: "APPROVAL_INVALID",
    }),
    issued_at: issuedAt,
    expires_at: expiresAt,
  };
  if (!sealed) return canonicalClone(normalized);
  const recordHash = readDataProperty(approval, "record_hash");
  if (typeof recordHash !== "string" || !SHA256_PATTERN.test(recordHash)) {
    fail("APPROVAL_INVALID", "record_hash must be a canonical SHA-256 digest");
  }
  const complete = { ...normalized, record_hash: recordHash };
  const expected = computeApprovalRecordHash(complete);
  if (recordHash !== expected) {
    fail("APPROVAL_HASH_MISMATCH", "record_hash does not match canonical fields", {
      actual: recordHash,
      approvalId: normalized.approval_id,
      expected,
    });
  }
  return canonicalClone(complete);
};

const sealApproval = (candidate) => {
  const normalized = normalizeApproval(candidate, { sealed: false });
  return canonicalClone({ ...normalized, record_hash: computeApprovalRecordHash(normalized) });
};

const SEALED_POLICIES = new WeakSet();

const uniqueBy = (entries, key, label) => {
  const seen = new Set();
  for (let index = 0; index < entries.length; index += 1) {
    const value = entries[index][key];
    if (seen.has(value)) fail("POLICY_INVALID", `${label} contains duplicate ${key}: ${value}`);
    seen.add(value);
  }
};

export const sealCapabilityPolicy = (candidate) => {
  const policy = requirePlainDataObject(candidate, "capability policy", {
    allowedKeys: POLICY_KEYS,
    code: "POLICY_INVALID",
  });
  const policyHash = readDataProperty(policy, "policy_hash");
  if (typeof policyHash !== "string" || !SHA256_PATTERN.test(policyHash)) {
    fail("POLICY_INVALID", "policy_hash must identify an exact sealed PolicyBundle");
  }
  const principals = readDenseArray(readDataProperty(policy, "principals"), "principals", "POLICY_INVALID").map(
    (entry, index) => {
      const principal = requirePlainDataObject(entry, `principals[${index}]`, {
        allowedKeys: PRINCIPAL_KEYS,
        code: "POLICY_INVALID",
      });
      const principalType = readDataProperty(principal, "principal_type");
      const identityClass = readDataProperty(principal, "identity_class");
      if (!PRINCIPAL_TYPES.has(principalType)) fail("POLICY_INVALID", "principal_type is invalid");
      if (!IDENTITY_CLASSES.has(identityClass)) fail("POLICY_INVALID", "identity_class is invalid");
      const authorityRole = requireNullableString(
        readDataProperty(principal, "authority_role"),
        `principals[${index}].authority_role`,
        "POLICY_INVALID",
      );
      const capabilities = requireStringArray(
        readDataProperty(principal, "capabilities"),
        `principals[${index}].capabilities`,
        { unique: true, sort: true, code: "POLICY_INVALID" },
      );
      const approvalTypes = requireStringArray(
        readDataProperty(principal, "approval_types"),
        `principals[${index}].approval_types`,
        { unique: true, sort: true, code: "POLICY_INVALID" },
      );
      for (const approvalType of approvalTypes) {
        if (!APPROVAL_TYPES.has(approvalType)) fail("POLICY_INVALID", "approval_types is invalid");
      }
      if (UNTRUSTED_AUTHORITY_CLASSES.has(identityClass)) {
        if (approvalTypes.length > 0 || capabilities.some((item) => PRIVILEGED_CAPABILITY_SET.has(item))) {
          fail(
            "UNTRUSTED_AUTHORITY_GRANT_DENIED",
            `${identityClass} identities cannot receive approval or privileged capabilities`,
          );
        }
      }
      return {
        principal_id: requireNonEmptyString(
          readDataProperty(principal, "principal_id"),
          `principals[${index}].principal_id`,
          "POLICY_INVALID",
        ),
        principal_type: principalType,
        identity_class: identityClass,
        capabilities,
        resource_scopes: requireStringArray(
          readDataProperty(principal, "resource_scopes"),
          `principals[${index}].resource_scopes`,
          { unique: true, sort: true, code: "POLICY_INVALID" },
        ),
        authority_role: authorityRole,
        approval_types: approvalTypes,
      };
    },
  );
  const subjects = readDenseArray(readDataProperty(policy, "subjects"), "subjects", "POLICY_INVALID").map(
    (entry, index) => {
      const subject = requirePlainDataObject(entry, `subjects[${index}]`, {
        allowedKeys: SUBJECT_KEYS,
        code: "POLICY_INVALID",
      });
      return {
        subject_id: requireNonEmptyString(
          readDataProperty(subject, "subject_id"),
          `subjects[${index}].subject_id`,
          "POLICY_INVALID",
        ),
        run_id: requireNonEmptyString(
          readDataProperty(subject, "run_id"),
          `subjects[${index}].run_id`,
          "POLICY_INVALID",
        ),
        maker_principal_ids: requireStringArray(
          readDataProperty(subject, "maker_principal_ids"),
          `subjects[${index}].maker_principal_ids`,
          { minItems: 1, unique: true, sort: true, code: "POLICY_INVALID" },
        ),
        capabilities: requireStringArray(
          readDataProperty(subject, "capabilities"),
          `subjects[${index}].capabilities`,
          { unique: true, sort: true, code: "POLICY_INVALID" },
        ),
        resource_scopes: requireStringArray(
          readDataProperty(subject, "resource_scopes"),
          `subjects[${index}].resource_scopes`,
          { unique: true, sort: true, code: "POLICY_INVALID" },
        ),
      };
    },
  );
  const approvalRules = readDenseArray(
    readDataProperty(policy, "approval_rules"),
    "approval_rules",
    "POLICY_INVALID",
  ).map((entry, index) => {
    const rule = requirePlainDataObject(entry, `approval_rules[${index}]`, {
      allowedKeys: APPROVAL_RULE_KEYS,
      code: "POLICY_INVALID",
    });
    const approvalType = readDataProperty(rule, "approval_type");
    if (!APPROVAL_TYPES.has(approvalType)) fail("POLICY_INVALID", "approval rule type is invalid");
    const evidenceRequired = readDataProperty(rule, "evidence_required");
    if (typeof evidenceRequired !== "boolean") fail("POLICY_INVALID", "evidence_required must be boolean");
    return {
      approval_type: approvalType,
      authority_roles: requireStringArray(
        readDataProperty(rule, "authority_roles"),
        `approval_rules[${index}].authority_roles`,
        { minItems: 1, unique: true, sort: true, code: "POLICY_INVALID" },
      ),
      evidence_required: evidenceRequired,
    };
  });
  const capabilityRules = readDenseArray(
    readDataProperty(policy, "capability_rules"),
    "capability_rules",
    "POLICY_INVALID",
  ).map((entry, index) => {
    const rule = requirePlainDataObject(entry, `capability_rules[${index}]`, {
      allowedKeys: CAPABILITY_RULE_KEYS,
      code: "POLICY_INVALID",
    });
    const requiredApprovalType = requireNullableString(
      readDataProperty(rule, "required_approval_type"),
      `capability_rules[${index}].required_approval_type`,
      "POLICY_INVALID",
    );
    if (requiredApprovalType !== null && !APPROVAL_TYPES.has(requiredApprovalType)) {
      fail("POLICY_INVALID", "required_approval_type is invalid");
    }
    return {
      capability: requireNonEmptyString(
        readDataProperty(rule, "capability"),
        `capability_rules[${index}].capability`,
        "POLICY_INVALID",
      ),
      required_approval_type: requiredApprovalType,
    };
  });
  uniqueBy(principals, "principal_id", "principals");
  uniqueBy(subjects, "subject_id", "subjects");
  uniqueBy(approvalRules, "approval_type", "approval_rules");
  uniqueBy(capabilityRules, "capability", "capability_rules");
  const ruleCapabilities = new Set(capabilityRules.map((rule) => rule.capability));
  for (const principal of principals) {
    for (const capability of principal.capabilities) {
      if (!ruleCapabilities.has(capability)) {
        fail("POLICY_INVALID", `capability ${capability} has no explicit policy rule`);
      }
    }
  }
  const approvalRuleTypes = new Set(approvalRules.map((rule) => rule.approval_type));
  for (const rule of capabilityRules) {
    if (rule.required_approval_type !== null && !approvalRuleTypes.has(rule.required_approval_type)) {
      fail("POLICY_INVALID", `capability ${rule.capability} refers to a missing approval rule`);
    }
  }
  const projection = {
    policy_hash: policyHash,
    principals,
    subjects,
    approval_rules: approvalRules,
    capability_rules: capabilityRules,
  };
  const sealed = canonicalClone({
    ...projection,
    projection_hash: sha256CanonicalJson(
      selectHashFields(
        projection,
        POLICY_PROJECTION_KEYS,
        "capability policy projection",
        "POLICY_INVALID",
      ),
    ),
  });
  SEALED_POLICIES.add(sealed);
  return sealed;
};

const normalizeLeaseCommand = (candidate) => {
  const command = requirePlainDataObject(candidate, "lease command", {
    allowedKeys: LEASE_COMMAND_KEYS,
  });
  return canonicalClone({
    lease_id: requireNonEmptyString(readDataProperty(command, "lease_id"), "lease_id"),
    run_id: requireNonEmptyString(readDataProperty(command, "run_id"), "run_id"),
    principal_id: requireNonEmptyString(readDataProperty(command, "principal_id"), "principal_id"),
    capabilities: requireStringArray(readDataProperty(command, "capabilities"), "capabilities", {
      minItems: 1,
      unique: true,
      sort: true,
    }),
    resource_scopes: requireStringArray(
      readDataProperty(command, "resource_scopes"),
      "resource_scopes",
      { minItems: 1, unique: true, sort: true },
    ),
    expires_at: requireTimestamp(readDataProperty(command, "expires_at"), "expires_at"),
    approval_ids: requireStringArray(readDataProperty(command, "approval_ids"), "approval_ids", {
      unique: true,
      sort: true,
    }),
  });
};

const normalizeApprovalCommand = (candidate) => {
  const command = requirePlainDataObject(candidate, "approval command", {
    allowedKeys: APPROVAL_COMMAND_KEYS,
  });
  const approvalType = readDataProperty(command, "approval_type");
  if (!APPROVAL_TYPES.has(approvalType)) fail("INVALID_INPUT", "approval_type is not canonical");
  const decision = readDataProperty(command, "decision");
  if (!APPROVAL_DECISIONS.has(decision)) fail("INVALID_INPUT", "decision is not canonical");
  const rawExpiresAt = readDataProperty(command, "expires_at");
  return canonicalClone({
    approval_id: requireNonEmptyString(readDataProperty(command, "approval_id"), "approval_id"),
    run_id: requireNonEmptyString(readDataProperty(command, "run_id"), "run_id"),
    subject_id: requireNonEmptyString(readDataProperty(command, "subject_id"), "subject_id"),
    approval_type: approvalType,
    decision,
    reason: requireNonEmptyString(readDataProperty(command, "reason"), "reason"),
    evidence_artifact_ids: requireStringArray(
      readDataProperty(command, "evidence_artifact_ids"),
      "evidence_artifact_ids",
      { unique: true, sort: true },
    ),
    conditions: requireStringArray(readDataProperty(command, "conditions"), "conditions", {
      unique: true,
      sort: true,
    }),
    expires_at: rawExpiresAt === null ? null : requireTimestamp(rawExpiresAt, "expires_at"),
  });
};

const scopeRecordId = (scope) => sha256Text(`capability-scope\u0000${scope}`);
const approvalHeadRecordId = (subjectId, approvalType) =>
  sha256Text(`approval-head\u0000${subjectId}\u0000${approvalType}`);
const operationRecordId = (operationId) => sha256Text(`capability-use\u0000${operationId}`);
const outboxIdentity = (kind, id) => {
  const hex = sha256Text(`capability-event\u0000${kind}\u0000${id}`).slice("sha256:".length);
  return OBJECT_FREEZE({
    artifactId: `ART-E03-${hex}`,
    eventId: `EVT-E03-${hex}`,
    outboxId: `OUT-E03-${hex}`,
  });
};

const requireImmutableRecord = (record, label, expectedType, expectedId) => {
  if (record === null) fail("CAPABILITY_STATE_MISSING", `${label} is missing`);
  if (record.recordType !== expectedType || record.recordId !== expectedId || record.revision !== 0) {
    fail("CAPABILITY_STATE_INTEGRITY_FAILED", `${label} is not immutable`, {
      expectedId,
      expectedType,
      revision: record.revision,
    });
  }
  return record.value;
};

const updateRecord = (store, record, value, label) => {
  const update = store.compareAndSwapRevision({
    recordType: record.recordType,
    recordId: record.recordId,
    expectedRevision: record.revision,
    value,
  });
  if (!update.ok) fail("CAPABILITY_STATE_COMMIT_FAILED", `${label} CAS failed`, { status: update.status });
  return update.record;
};

const validateCounter = (record) => {
  if (record === null) return 0;
  const value = requirePlainDataObject(record.value, "fencing counter", {
    allowedKeys: ["last_fencing_token"],
    code: "CAPABILITY_STATE_INTEGRITY_FAILED",
  });
  const token = readDataProperty(value, "last_fencing_token");
  if (!NUMBER_IS_SAFE_INTEGER(token) || token < 1) {
    fail("CAPABILITY_STATE_INTEGRITY_FAILED", "fencing counter is invalid");
  }
  return token;
};

const allocateFencingToken = (store) => {
  const record = store.readRevisionedRecord(CAPABILITY_RECORD_TYPES.FENCING_COUNTER, COUNTER_ID);
  const previous = validateCounter(record);
  if (previous === Number.MAX_SAFE_INTEGER) fail("FENCING_TOKEN_EXHAUSTED", "fencing counter is exhausted");
  const next = previous + 1;
  const value = { last_fencing_token: next };
  if (record === null) {
    store.createRevisionedRecord({
      recordType: CAPABILITY_RECORD_TYPES.FENCING_COUNTER,
      recordId: COUNTER_ID,
      value,
    });
  } else {
    updateRecord(store, record, value, "fencing counter");
  }
  return next;
};

const validateScopeHead = (record, scope) => {
  if (record === null) return null;
  const head = requirePlainDataObject(record.value, "scope head", {
    allowedKeys: ["scope", "lease_id", "lease_hash", "fencing_token"],
    code: "CAPABILITY_STATE_INTEGRITY_FAILED",
  });
  const fencingToken = readDataProperty(head, "fencing_token");
  const leaseHash = readDataProperty(head, "lease_hash");
  if (
    readDataProperty(head, "scope") !== scope ||
    !NUMBER_IS_SAFE_INTEGER(fencingToken) ||
    fencingToken < 1 ||
    typeof leaseHash !== "string" ||
    !SHA256_PATTERN.test(leaseHash)
  ) {
    fail("CAPABILITY_STATE_INTEGRITY_FAILED", "scope head is invalid", { scope });
  }
  return head;
};

const setScopeHead = (store, scope, lease) => {
  const recordId = scopeRecordId(scope);
  const record = store.readRevisionedRecord(CAPABILITY_RECORD_TYPES.SCOPE_HEAD, recordId);
  validateScopeHead(record, scope);
  const value = {
    scope,
    lease_id: lease.lease_id,
    lease_hash: lease.lease_hash,
    fencing_token: lease.fencing_token,
  };
  if (record === null) {
    store.createRevisionedRecord({
      recordType: CAPABILITY_RECORD_TYPES.SCOPE_HEAD,
      recordId,
      value,
    });
  } else {
    updateRecord(store, record, value, `scope head ${scope}`);
  }
};

const validateOutboxIndex = (record) => {
  if (record === null) return OBJECT_FREEZE([]);
  const index = requirePlainDataObject(record.value, "outbox index", {
    allowedKeys: ["outbox_ids"],
    code: "CAPABILITY_STATE_INTEGRITY_FAILED",
  });
  return requireStringArray(readDataProperty(index, "outbox_ids"), "outbox_ids", {
    unique: true,
    code: "CAPABILITY_STATE_INTEGRITY_FAILED",
  });
};

const computeOutboxHash = (outbox) =>
  sha256CanonicalJson(
    selectHashFields(
      outbox,
      [
        "outbox_id",
        "event_id",
        "run_id",
        "event_type",
        "aggregate_type",
        "aggregate_id",
        "actor_id",
        "occurred_at",
        "payload_artifact_id",
        "payload_hash",
        "payload",
      ],
      "outbox",
      "CAPABILITY_STATE_INTEGRITY_FAILED",
    ),
  );

const validateOutbox = (candidate) => {
  const outbox = requirePlainDataObject(candidate, "outbox", {
    allowedKeys: [
      "outbox_id",
      "event_id",
      "run_id",
      "event_type",
      "aggregate_type",
      "aggregate_id",
      "actor_id",
      "occurred_at",
      "payload_artifact_id",
      "payload_hash",
      "payload",
      "outbox_hash",
      "published",
      "event_hash",
    ],
    code: "CAPABILITY_STATE_INTEGRITY_FAILED",
  });
  const payload = canonicalClone(readDataProperty(outbox, "payload"));
  const payloadHash = readDataProperty(outbox, "payload_hash");
  const outboxHash = readDataProperty(outbox, "outbox_hash");
  const published = readDataProperty(outbox, "published");
  const eventHash = readDataProperty(outbox, "event_hash");
  if (payloadHash !== sha256CanonicalJson(payload)) {
    fail("CAPABILITY_STATE_INTEGRITY_FAILED", "outbox payload hash mismatch");
  }
  if (typeof published !== "boolean") fail("CAPABILITY_STATE_INTEGRITY_FAILED", "published is invalid");
  if (!(eventHash === null || (typeof eventHash === "string" && SHA256_PATTERN.test(eventHash)))) {
    fail("CAPABILITY_STATE_INTEGRITY_FAILED", "event_hash is invalid");
  }
  if (published !== (eventHash !== null)) {
    fail("CAPABILITY_STATE_INTEGRITY_FAILED", "outbox publication state is inconsistent");
  }
  if (outboxHash !== computeOutboxHash(outbox)) {
    fail("CAPABILITY_STATE_INTEGRITY_FAILED", "outbox hash mismatch");
  }
  for (const key of [
    "outbox_id",
    "event_id",
    "run_id",
    "event_type",
    "aggregate_type",
    "aggregate_id",
    "actor_id",
    "payload_artifact_id",
  ]) {
    requireNonEmptyString(readDataProperty(outbox, key), `outbox.${key}`, "CAPABILITY_STATE_INTEGRITY_FAILED");
  }
  requireTimestamp(readDataProperty(outbox, "occurred_at"), "outbox.occurred_at", "CAPABILITY_STATE_INTEGRITY_FAILED");
  return canonicalClone(outbox);
};

const queueOutbox = (store, descriptor) => {
  const payload = canonicalClone(descriptor.payload);
  const base = {
    outbox_id: descriptor.outboxId,
    event_id: descriptor.eventId,
    run_id: descriptor.runId,
    event_type: descriptor.eventType,
    aggregate_type: descriptor.aggregateType,
    aggregate_id: descriptor.aggregateId,
    actor_id: descriptor.actorId,
    occurred_at: descriptor.occurredAt,
    payload_artifact_id: descriptor.artifactId,
    payload_hash: sha256CanonicalJson(payload),
    payload,
  };
  const outbox = validateOutbox({
    ...base,
    outbox_hash: computeOutboxHash(base),
    published: false,
    event_hash: null,
  });
  store.createRevisionedRecord({
    recordType: CAPABILITY_RECORD_TYPES.OUTBOX,
    recordId: descriptor.outboxId,
    value: outbox,
  });
  const indexRecord = store.readRevisionedRecord(
    CAPABILITY_RECORD_TYPES.OUTBOX_INDEX,
    OUTBOX_INDEX_ID,
  );
  const outboxIds = validateOutboxIndex(indexRecord);
  const next = { outbox_ids: [...outboxIds, descriptor.outboxId] };
  if (indexRecord === null) {
    store.createRevisionedRecord({
      recordType: CAPABILITY_RECORD_TYPES.OUTBOX_INDEX,
      recordId: OUTBOX_INDEX_ID,
      value: next,
    });
  } else {
    updateRecord(store, indexRecord, next, "outbox index");
  }
  return outbox;
};

const normalizeDependencies = (options) => {
  const object = requirePlainDataObject(options, "authority options", {
    allowedKeys: ["artifactStore", "ledger", "stateStore", "policy", "clock"],
  });
  const artifactStore = readDataProperty(object, "artifactStore");
  const ledger = readDataProperty(object, "ledger");
  const stateStore = readDataProperty(object, "stateStore");
  const policy = readDataProperty(object, "policy");
  const clock = readDataProperty(object, "clock");
  if (!SEALED_POLICIES.has(policy)) fail("UNSEALED_POLICY", "policy must come from sealCapabilityPolicy()");
  if (
    artifactStore === null ||
    (typeof artifactStore !== "object" && typeof artifactStore !== "function") ||
    typeof artifactStore.putArtifact !== "function"
  ) {
    fail("INVALID_INPUT", "artifactStore must expose putArtifact()");
  }
  if (
    ledger === null ||
    (typeof ledger !== "object" && typeof ledger !== "function") ||
    typeof ledger.append !== "function"
  ) {
    fail("INVALID_INPUT", "ledger must expose E01 append()");
  }
  if (
    stateStore === null ||
    (typeof stateStore !== "object" && typeof stateStore !== "function") ||
    typeof stateStore.transaction !== "function" ||
    typeof stateStore.readRevisionedRecord !== "function" ||
    typeof stateStore.createRevisionedRecord !== "function" ||
    typeof stateStore.compareAndSwapRevision !== "function"
  ) {
    fail("INVALID_INPUT", "stateStore must expose the D01 transactional revision API");
  }
  if (typeof clock !== "function") fail("INVALID_INPUT", "clock must be a trusted synchronous function");
  return OBJECT_FREEZE({ artifactStore, ledger, stateStore, policy, clock });
};

const artifactMetadata = (outbox) => ({
  artifact: {
    artifactId: outbox.payload_artifact_id,
    artifactType: "capability_event_payload",
    confidentiality: "internal",
    createdAt: outbox.occurred_at,
    createdBy: EVENT_ACTOR_ID,
    encryption: { atRest: true, inTransit: true, keyRef: "local://e03-capability-events" },
    inputArtifactIds: [],
    license: null,
    lineageEventIds: [],
    mediaType: "application/json",
    provenanceManifestId: "PROV-E03-capability-authority",
    retentionClass: "project",
  },
  receipt: {
    actionIntentId: null,
    createdAt: outbox.occurred_at,
    createdBy: { actorId: EVENT_ACTOR_ID, actorType: "service" },
    receiptId: `AR-${outbox.payload_artifact_id}`,
    schemaRef: null,
    validationResults: [
      {
        check: "capability_event_outbox",
        status: "PASS",
        details: outbox.outbox_hash,
      },
    ],
  },
});

const isThenable = (value) =>
  value !== null &&
  (typeof value === "object" || typeof value === "function") &&
  typeof value.then === "function";

const assertExternalRecordType = (recordType) => {
  const type = requireNonEmptyString(recordType, "recordType");
  if (CAPABILITY_RECORD_TYPE_SET.has(type)) {
    fail(
      "CAPABILITY_STATE_ACCESS_DENIED",
      "lease callback cannot access Capability Authority private records",
      { recordType: type },
    );
  }
  return type;
};

const normalizeExternalRecordTypeAllowlist = (candidate) => {
  const recordTypes = requireStringArray(candidate, "allowedRecordTypes", {
    minItems: 1,
    unique: true,
    sort: true,
  });
  for (const recordType of recordTypes) assertExternalRecordType(recordType);
  return new Set(recordTypes);
};

const assertAllowedExternalRecordType = (recordType, allowedRecordTypes) => {
  const type = assertExternalRecordType(recordType);
  if (allowedRecordTypes !== null && !allowedRecordTypes.has(type)) {
    fail(
      "CAPABILITY_STATE_ACCESS_DENIED",
      "lease callback record type is outside its explicit allowlist",
      { recordType: type },
    );
  }
  return type;
};

const createLeaseCommitStore = (store, allowedRecordTypes = null) =>
  OBJECT_FREEZE({
    readRevisionedRecord(recordType, recordId) {
      return store.readRevisionedRecord(
        assertAllowedExternalRecordType(recordType, allowedRecordTypes),
        recordId,
      );
    },
    createRevisionedRecord(candidate) {
      const command = requirePlainDataObject(candidate, "create record command", {
        allowedKeys: ["recordType", "recordId", "value"],
      });
      assertAllowedExternalRecordType(
        readDataProperty(command, "recordType"),
        allowedRecordTypes,
      );
      return store.createRevisionedRecord(command);
    },
    compareAndSwapRevision(candidate) {
      const command = requirePlainDataObject(candidate, "compare-and-swap command", {
        allowedKeys: ["recordType", "recordId", "expectedRevision", "value"],
      });
      assertAllowedExternalRecordType(
        readDataProperty(command, "recordType"),
        allowedRecordTypes,
      );
      return store.compareAndSwapRevision(command);
    },
  });

const readLeaseUseRecord = (store, operationId) => {
  const recordId = operationRecordId(operationId);
  const record = store.readRevisionedRecord(CAPABILITY_RECORD_TYPES.LEASE_USE, recordId);
  if (record === null) return null;
  const use = requirePlainDataObject(
    requireImmutableRecord(
      record,
      "lease use",
      CAPABILITY_RECORD_TYPES.LEASE_USE,
      recordId,
    ),
    "lease use",
    {
      allowedKeys: [
        "operation_id",
        "request_hash",
        "lease_id",
        "fencing_token",
        "committed_at",
        "result",
        "outbox_id",
      ],
      code: "CAPABILITY_STATE_INTEGRITY_FAILED",
    },
  );
  if (
    readDataProperty(use, "operation_id") !== operationId ||
    !SHA256_PATTERN.test(readDataProperty(use, "request_hash")) ||
    !NUMBER_IS_SAFE_INTEGER(readDataProperty(use, "fencing_token")) ||
    readDataProperty(use, "fencing_token") < 1
  ) {
    fail("CAPABILITY_STATE_INTEGRITY_FAILED", "lease use identity is invalid", {
      operationId,
    });
  }
  requireNonEmptyString(
    readDataProperty(use, "lease_id"),
    "lease use.lease_id",
    "CAPABILITY_STATE_INTEGRITY_FAILED",
  );
  requireTimestamp(
    readDataProperty(use, "committed_at"),
    "lease use.committed_at",
    "CAPABILITY_STATE_INTEGRITY_FAILED",
  );
  requireNonEmptyString(
    readDataProperty(use, "outbox_id"),
    "lease use.outbox_id",
    "CAPABILITY_STATE_INTEGRITY_FAILED",
  );
  return OBJECT_FREEZE({ recordId, use: canonicalClone(use) });
};

const CONSTRUCTOR_TOKEN = Symbol("CapabilityAuthority");
const CAPABILITY_AUTHORITY_DEPENDENCY_IDENTITIES = new WeakMap();

export class CapabilityAuthority {
  #artifactStore;
  #ledger;
  #stateStore;
  #policy;
  #clock;
  #principals;
  #subjects;
  #approvalRules;
  #capabilityRules;

  constructor(token, dependencies) {
    if (token !== CONSTRUCTOR_TOKEN) fail("DIRECT_CONSTRUCTION_DENIED", "use createCapabilityAuthority()");
    this.#artifactStore = dependencies.artifactStore;
    this.#ledger = dependencies.ledger;
    this.#stateStore = dependencies.stateStore;
    this.#policy = dependencies.policy;
    this.#clock = dependencies.clock;
    this.#principals = new Map(this.#policy.principals.map((entry) => [entry.principal_id, entry]));
    this.#subjects = new Map(this.#policy.subjects.map((entry) => [entry.subject_id, entry]));
    this.#approvalRules = new Map(
      this.#policy.approval_rules.map((entry) => [entry.approval_type, entry]),
    );
    this.#capabilityRules = new Map(
      this.#policy.capability_rules.map((entry) => [entry.capability, entry]),
    );
    CAPABILITY_AUTHORITY_DEPENDENCY_IDENTITIES.set(
      this,
      OBJECT_FREEZE({
        artifactStore: dependencies.artifactStore,
        ledger: dependencies.ledger,
        stateStore: dependencies.stateStore,
        clock: dependencies.clock,
      }),
    );
  }

  #now() {
    let value;
    try {
      value = this.#clock();
    } catch (error) {
      fail("CLOCK_FAILED", "authority clock failed", { causeCode: dependencyCauseCode(error) }, { cause: error });
    }
    if (isThenable(value)) {
      if (typeof value.catch === "function") value.catch(() => undefined);
      fail("ASYNC_CLOCK_DENIED", "authority clock must be synchronous");
    }
    return requireTimestamp(value, "clock result", "CLOCK_INVALID");
  }

  #principal(principalId) {
    const id = requireNonEmptyString(principalId, "authenticated principal ID");
    const principal = this.#principals.get(id);
    if (principal === undefined) fail("PRINCIPAL_NOT_AUTHORIZED", "principal is absent from sealed policy", { principalId: id });
    return principal;
  }

  #assertDirectCapability(principal, capability) {
    if (!principal.capabilities.includes(capability)) {
      fail("CAPABILITY_NOT_AUTHORIZED", "sealed policy does not grant the authority capability", {
        capability,
        principalId: principal.principal_id,
      });
    }
  }

  #assertLeaseGrant(principal, command) {
    for (const capability of command.capabilities) {
      if (!principal.capabilities.includes(capability)) {
        fail("CAPABILITY_NOT_AUTHORIZED", "principal is not eligible for requested capability", {
          capability,
          principalId: principal.principal_id,
        });
      }
      if (!this.#capabilityRules.has(capability)) {
        fail("CAPABILITY_POLICY_MISSING", "requested capability has no explicit policy rule", { capability });
      }
      if (
        UNTRUSTED_AUTHORITY_CLASSES.has(principal.identity_class) &&
        PRIVILEGED_CAPABILITY_SET.has(capability)
      ) {
        fail("UNTRUSTED_AUTHORITY_GRANT_DENIED", "untrusted identity cannot receive capability", {
          capability,
          identityClass: principal.identity_class,
        });
      }
    }
    for (const scope of command.resource_scopes) {
      if (!principal.resource_scopes.includes(scope)) {
        fail("RESOURCE_SCOPE_NOT_AUTHORIZED", "principal is not eligible for requested resource scope", {
          principalId: principal.principal_id,
          scope,
        });
      }
    }
    const requiresApproval = command.capabilities.some(
      (capability) =>
        this.#capabilityRules.get(capability).required_approval_type !== null,
    );
    if (!requiresApproval) return;
    const subject = this.#subjects.get(command.lease_id);
    if (subject === undefined) {
      fail("LEASE_SUBJECT_UNKNOWN", "lease is absent from the sealed subject registry", {
        leaseId: command.lease_id,
      });
    }
    if (subject.run_id !== command.run_id) {
      fail("LEASE_RUN_SCOPE_MISMATCH", "lease command run does not match sealed subject scope", {
        leaseId: command.lease_id,
        runId: command.run_id,
      });
    }
    if (!sameCanonical(subject.capabilities, command.capabilities)) {
      fail("LEASE_SUBJECT_SCOPE_MISMATCH", "lease capabilities differ from sealed subject scope", {
        leaseId: command.lease_id,
      });
    }
    if (!sameCanonical(subject.resource_scopes, command.resource_scopes)) {
      fail("LEASE_SUBJECT_SCOPE_MISMATCH", "lease resources differ from sealed subject scope", {
        leaseId: command.lease_id,
      });
    }
  }

  #readApprovalHead(store, subjectId, approvalType) {
    const recordId = approvalHeadRecordId(subjectId, approvalType);
    const record = store.readRevisionedRecord(CAPABILITY_RECORD_TYPES.APPROVAL_HEAD, recordId);
    if (record === null) return OBJECT_FREEZE({ head: null, record: null, recordId });
    const head = requirePlainDataObject(record.value, "approval head", {
      allowedKeys: [
        "subject_id",
        "approval_type",
        "approval_id",
        "record_hash",
        "decision",
        "issued_at",
      ],
      code: "CAPABILITY_STATE_INTEGRITY_FAILED",
    });
    if (
      readDataProperty(head, "subject_id") !== subjectId ||
      readDataProperty(head, "approval_type") !== approvalType ||
      !APPROVAL_DECISIONS.has(readDataProperty(head, "decision")) ||
      typeof readDataProperty(head, "record_hash") !== "string" ||
      !SHA256_PATTERN.test(readDataProperty(head, "record_hash")) ||
      !isRfc3339(readDataProperty(head, "issued_at"))
    ) {
      fail("CAPABILITY_STATE_INTEGRITY_FAILED", "approval head is invalid", {
        approvalType,
        subjectId,
      });
    }
    return OBJECT_FREEZE({ head: canonicalClone(head), record, recordId });
  }

  #setApprovalHead(store, approval) {
    const snapshot = this.#readApprovalHead(store, approval.subject_id, approval.approval_type);
    const value = {
      subject_id: approval.subject_id,
      approval_type: approval.approval_type,
      approval_id: approval.approval_id,
      record_hash: approval.record_hash,
      decision: approval.decision,
      issued_at: approval.issued_at,
    };
    if (snapshot.record === null) {
      store.createRevisionedRecord({
        recordType: CAPABILITY_RECORD_TYPES.APPROVAL_HEAD,
        recordId: snapshot.recordId,
        value,
      });
    } else {
      const previousInstant = Date.parse(snapshot.head.issued_at);
      const nextInstant = Date.parse(approval.issued_at);
      if (nextInstant < previousInstant) {
        fail(
          "APPROVAL_CLOCK_REGRESSION",
          "approval authority time moved behind the current subject decision",
          {
            approvalType: approval.approval_type,
            currentApprovalId: snapshot.head.approval_id,
            currentIssuedAt: snapshot.head.issued_at,
            proposedApprovalId: approval.approval_id,
            proposedIssuedAt: approval.issued_at,
            subjectId: approval.subject_id,
          },
        );
      }
      if (nextInstant === previousInstant) {
        fail(
          "APPROVAL_TIMESTAMP_CONFLICT",
          "distinct approval decisions for one subject require strictly ordered authority time",
          {
            approvalType: approval.approval_type,
            currentApprovalId: snapshot.head.approval_id,
            currentIssuedAt: snapshot.head.issued_at,
            proposedApprovalId: approval.approval_id,
            proposedIssuedAt: approval.issued_at,
            subjectId: approval.subject_id,
          },
        );
      }
      updateRecord(store, snapshot.record, value, "approval head");
    }
  }

  #readApproval(store, approvalId) {
    const record = store.readRevisionedRecord(CAPABILITY_RECORD_TYPES.APPROVAL, approvalId);
    return normalizeApproval(
      requireImmutableRecord(record, "ApprovalRecord", CAPABILITY_RECORD_TYPES.APPROVAL, approvalId),
    );
  }

  #readApprovalBinding(store, approval) {
    const record = store.readRevisionedRecord(
      CAPABILITY_RECORD_TYPES.APPROVAL_BINDING,
      approval.approval_id,
    );
    const binding = requirePlainDataObject(
      requireImmutableRecord(
        record,
        "approval binding",
        CAPABILITY_RECORD_TYPES.APPROVAL_BINDING,
        approval.approval_id,
      ),
      "approval binding",
      {
        allowedKeys: ["request_hash", "outbox_id", "policy_hash", "policy_projection_hash"],
        code: "CAPABILITY_STATE_INTEGRITY_FAILED",
      },
    );
    const policyHash = readDataProperty(binding, "policy_hash");
    if (typeof policyHash !== "string" || !SHA256_PATTERN.test(policyHash)) {
      fail("CAPABILITY_STATE_INTEGRITY_FAILED", "approval binding policy_hash is invalid");
    }
    if (policyHash !== this.#policy.policy_hash) {
      fail("APPROVAL_POLICY_MISMATCH", "approval was issued under a different sealed policy", {
        approvalId: approval.approval_id,
      });
    }
    if (readDataProperty(binding, "policy_projection_hash") !== this.#policy.projection_hash) {
      fail(
        "APPROVAL_POLICY_PROJECTION_MISMATCH",
        "approval capability projection differs from the sealed policy projection",
        { approvalId: approval.approval_id },
      );
    }
    const command = {
      approval_id: approval.approval_id,
      run_id: approval.run_id,
      subject_id: approval.subject_id,
      approval_type: approval.approval_type,
      decision: approval.decision,
      reason: approval.reason,
      evidence_artifact_ids: approval.evidence_artifact_ids,
      conditions: approval.conditions,
      expires_at: approval.expires_at,
    };
    const expectedRequestHash = sha256CanonicalJson({
      authenticated_principal_id: approval.authority_id,
      command,
      policy_hash: policyHash,
    });
    if (readDataProperty(binding, "request_hash") !== expectedRequestHash) {
      fail("CAPABILITY_STATE_INTEGRITY_FAILED", "approval binding request hash mismatch", {
        approvalId: approval.approval_id,
      });
    }
    return binding;
  }

  #assertApprovals(store, leaseLike, atTime) {
    const required = new Set();
    for (const capability of leaseLike.capabilities) {
      const rule = this.#capabilityRules.get(capability);
      if (rule === undefined) fail("CAPABILITY_POLICY_MISSING", "lease capability has no policy rule", { capability });
      if (rule.required_approval_type !== null) required.add(rule.required_approval_type);
    }
    if (required.size === 0) return;
    const matched = new Set();
    const subject = this.#subjects.get(leaseLike.lease_id);
    if (subject === undefined) {
      fail("APPROVAL_SUBJECT_UNKNOWN", "lease approval subject is absent from sealed authority registry", {
        leaseId: leaseLike.lease_id,
      });
    }
    for (const approvalId of leaseLike.approval_ids) {
      const approval = this.#readApproval(store, approvalId);
      this.#readApprovalBinding(store, approval);
      if (approval.subject_id !== leaseLike.lease_id || approval.decision !== "APPROVE") continue;
      const approvalHead = this.#readApprovalHead(
        store,
        approval.subject_id,
        approval.approval_type,
      ).head;
      if (
        approvalHead === null ||
        approvalHead.approval_id !== approval.approval_id ||
        approvalHead.record_hash !== approval.record_hash ||
        approvalHead.decision !== "APPROVE"
      ) {
        continue;
      }
      if (Date.parse(approval.issued_at) > Date.parse(atTime)) continue;
      if (approval.expires_at !== null && Date.parse(approval.expires_at) < Date.parse(leaseLike.expires_at ?? atTime)) {
        continue;
      }
      if (subject.maker_principal_ids.includes(approval.authority_id)) {
        fail("SELF_APPROVAL_DENIED", "maker approval cannot authorize its own subject", {
          approvalId,
          authorityId: approval.authority_id,
        });
      }
      const rule = this.#approvalRules.get(approval.approval_type);
      if (rule === undefined || !rule.authority_roles.includes(approval.authority_role)) continue;
      const authority = this.#principals.get(approval.authority_id);
      if (
        authority === undefined ||
        authority.authority_role !== approval.authority_role ||
        !authority.approval_types.includes(approval.approval_type)
      ) {
        fail("APPROVAL_AUTHORITY_STALE", "approval authority is no longer valid under sealed policy", {
          approvalId,
          authorityId: approval.authority_id,
        });
      }
      if (approval.conditions.length > 0) {
        fail(
          "APPROVAL_CONDITIONS_UNASSESSED",
          "conditional approval cannot authorize a lease without assessed condition results",
          { approvalId },
        );
      }
      matched.add(approval.approval_type);
    }
    for (const approvalType of required) {
      if (!matched.has(approvalType)) {
        fail("REQUIRED_APPROVAL_MISSING", "lease lacks a valid approval required by sealed policy", {
          approvalType,
          leaseId: leaseLike.lease_id,
        });
      }
    }
  }

  #readLease(store, leaseId) {
    const record = store.readRevisionedRecord(CAPABILITY_RECORD_TYPES.LEASE, leaseId);
    if (record === null) fail("LEASE_NOT_FOUND", "CapabilityLease does not exist", { leaseId });
    return OBJECT_FREEZE({ lease: normalizeLease(record.value), record });
  }

  #assertCurrentLease(store, suppliedLease, request, now) {
    const { lease: persisted } = this.#readLease(store, suppliedLease.lease_id);
    const bindingRecord = store.readRevisionedRecord(
      CAPABILITY_RECORD_TYPES.LEASE_BINDING,
      persisted.lease_id,
    );
    const binding = requirePlainDataObject(
      requireImmutableRecord(
        bindingRecord,
        "lease binding",
        CAPABILITY_RECORD_TYPES.LEASE_BINDING,
        persisted.lease_id,
      ),
      "lease binding",
      {
        allowedKeys: [
          "request_hash",
          "outbox_id",
          "run_id",
          "policy_hash",
          "policy_projection_hash",
        ],
        code: "CAPABILITY_STATE_INTEGRITY_FAILED",
      },
    );
    if (readDataProperty(binding, "run_id") !== request.run_id) {
      fail("LEASE_RUN_SCOPE_MISMATCH", "lease cannot be used in another run", {
        leaseId: persisted.lease_id,
        runId: request.run_id,
      });
    }
    if (readDataProperty(binding, "policy_hash") !== this.#policy.policy_hash) {
      fail("LEASE_POLICY_MISMATCH", "lease binding belongs to another sealed policy");
    }
    if (readDataProperty(binding, "policy_projection_hash") !== this.#policy.projection_hash) {
      fail(
        "LEASE_POLICY_PROJECTION_MISMATCH",
        "lease capability projection differs from the sealed policy projection",
      );
    }
    if (!sameCanonical(persisted, suppliedLease)) {
      fail("LEASE_STATE_MISMATCH", "supplied lease is not the current canonical lease revision", {
        leaseId: suppliedLease.lease_id,
      });
    }
    if (persisted.policy_hash !== this.#policy.policy_hash) {
      fail("LEASE_POLICY_MISMATCH", "lease was issued under a different sealed policy", {
        leaseId: persisted.lease_id,
      });
    }
    if (persisted.revoked) fail("LEASE_REVOKED", "lease has been revoked", { leaseId: persisted.lease_id });
    if (Date.parse(now) < Date.parse(persisted.issued_at)) {
      fail("LEASE_NOT_YET_VALID", "lease has not reached its issued_at boundary");
    }
    if (Date.parse(now) >= Date.parse(persisted.expires_at)) {
      fail("LEASE_EXPIRED", "lease is expired; the attempt is orphaned and requires reconciliation", {
        leaseId: persisted.lease_id,
      });
    }
    if (request.principal_id !== persisted.principal_id) {
      fail("LEASE_PRINCIPAL_MISMATCH", "lease belongs to another principal");
    }
    const principal = this.#principal(request.principal_id);
    if (principal.principal_type !== persisted.principal_type) {
      fail("LEASE_PRINCIPAL_MISMATCH", "lease principal type differs from sealed policy");
    }
    if (!persisted.capabilities.includes(request.capability)) {
      fail("LEASE_CAPABILITY_MISSING", "lease does not contain the requested capability", {
        capability: request.capability,
      });
    }
    for (const scope of request.resource_scopes) {
      if (!persisted.resource_scopes.includes(scope)) {
        fail("LEASE_SCOPE_MISSING", "lease does not contain the requested resource scope", { scope });
      }
    }
    this.#assertApprovals(store, persisted, now);
    for (const scope of persisted.resource_scopes) {
      const record = store.readRevisionedRecord(
        CAPABILITY_RECORD_TYPES.SCOPE_HEAD,
        scopeRecordId(scope),
      );
      const head = validateScopeHead(record, scope);
      if (
        head === null ||
        head.fencing_token !== persisted.fencing_token ||
        head.lease_id !== persisted.lease_id ||
        head.lease_hash !== persisted.lease_hash
      ) {
        fail("STALE_FENCING_TOKEN", "lease fencing token is no longer current for every scope", {
          leaseId: persisted.lease_id,
          scope,
          token: persisted.fencing_token,
        });
      }
    }
    return persisted;
  }

  #publish(outboxId) {
    const snapshot = this.#stateStore.transaction((store) => {
      const record = store.readRevisionedRecord(CAPABILITY_RECORD_TYPES.OUTBOX, outboxId);
      if (record === null) fail("CAPABILITY_STATE_MISSING", "event outbox is missing", { outboxId });
      return OBJECT_FREEZE({ outbox: validateOutbox(record.value), revision: record.revision });
    });
    if (snapshot.outbox.published) return snapshot.outbox;
    const bytes = Buffer.from(canonicalCapabilityJson(snapshot.outbox.payload), "utf8");
    try {
      this.#artifactStore.putArtifact(bytes, artifactMetadata(snapshot.outbox));
      const append = this.#ledger.append({
        event_id: snapshot.outbox.event_id,
        run_id: snapshot.outbox.run_id,
        event_type: snapshot.outbox.event_type,
        aggregate_type: snapshot.outbox.aggregate_type,
        aggregate_id: snapshot.outbox.aggregate_id,
        actor_id: snapshot.outbox.actor_id,
        payload_artifact_id: snapshot.outbox.payload_artifact_id,
        occurred_at: snapshot.outbox.occurred_at,
        schema_version: EVENT_SCHEMA_VERSION,
      });
      return this.#stateStore.transaction((store) => {
        const current = store.readRevisionedRecord(CAPABILITY_RECORD_TYPES.OUTBOX, outboxId);
        if (current === null) fail("CAPABILITY_STATE_MISSING", "event outbox vanished", { outboxId });
        const outbox = validateOutbox(current.value);
        if (outbox.published) {
          if (outbox.event_hash !== append.event.event_hash) {
            fail("CAPABILITY_STATE_INTEGRITY_FAILED", "published outbox event hash changed");
          }
          return outbox;
        }
        const updated = validateOutbox({
          ...outbox,
          published: true,
          event_hash: append.event.event_hash,
        });
        return validateOutbox(updateRecord(store, current, updated, "event outbox").value);
      });
    } catch (error) {
      if (error instanceof CapabilityAuthorityError && error.code !== "CAPABILITY_EVENT_RECONCILIATION_REQUIRED") {
        throw error;
      }
      fail(
        "CAPABILITY_EVENT_RECONCILIATION_REQUIRED",
        "canonical state committed but E01 event publication requires reconciliation",
        { causeCode: dependencyCauseCode(error), outboxId },
        { cause: error },
      );
    }
  }

  issueApproval(authenticatedPrincipalId, candidate) {
    const authority = this.#principal(authenticatedPrincipalId);
    this.#assertDirectCapability(authority, "approval:issue");
    const command = normalizeApprovalCommand(candidate);
    if (authority.authority_role === null || !authority.approval_types.includes(command.approval_type)) {
      fail("APPROVAL_AUTHORITY_DENIED", "principal is not an authority for this approval type", {
        approvalType: command.approval_type,
        principalId: authority.principal_id,
      });
    }
    const rule = this.#approvalRules.get(command.approval_type);
    if (rule === undefined || !rule.authority_roles.includes(authority.authority_role)) {
      fail("APPROVAL_AUTHORITY_DENIED", "authority role is not allowed by sealed policy");
    }
    const subject = this.#subjects.get(command.subject_id);
    if (subject === undefined) fail("APPROVAL_SUBJECT_UNKNOWN", "approval subject is absent from sealed registry");
    if (subject.run_id !== command.run_id) {
      fail("APPROVAL_RUN_SCOPE_MISMATCH", "approval command run does not match sealed subject scope", {
        runId: command.run_id,
        subjectId: command.subject_id,
      });
    }
    if (command.decision === "APPROVE" && subject.maker_principal_ids.includes(authority.principal_id)) {
      fail("SELF_APPROVAL_DENIED", "a maker cannot approve its own subject", {
        authorityId: authority.principal_id,
        subjectId: command.subject_id,
      });
    }
    if (rule.evidence_required && command.evidence_artifact_ids.length === 0) {
      fail("APPROVAL_EVIDENCE_REQUIRED", "approval policy requires evidence artifacts");
    }
    const requestHash = sha256CanonicalJson({
      authenticated_principal_id: authority.principal_id,
      command,
      policy_hash: this.#policy.policy_hash,
    });
    const result = this.#stateStore.transaction((store) => {
      const bindingRecord = store.readRevisionedRecord(
        CAPABILITY_RECORD_TYPES.APPROVAL_BINDING,
        command.approval_id,
      );
      const approvalRecord = store.readRevisionedRecord(
        CAPABILITY_RECORD_TYPES.APPROVAL,
        command.approval_id,
      );
      if (bindingRecord !== null || approvalRecord !== null) {
        const binding = requirePlainDataObject(
          requireImmutableRecord(
            bindingRecord,
            "approval binding",
            CAPABILITY_RECORD_TYPES.APPROVAL_BINDING,
            command.approval_id,
          ),
          "approval binding",
          {
            allowedKeys: [
              "request_hash",
              "outbox_id",
              "policy_hash",
              "policy_projection_hash",
            ],
            code: "CAPABILITY_STATE_INTEGRITY_FAILED",
          },
        );
        if (readDataProperty(binding, "policy_hash") !== this.#policy.policy_hash) {
          fail("APPROVAL_POLICY_MISMATCH", "approval belongs to another sealed policy");
        }
        if (readDataProperty(binding, "policy_projection_hash") !== this.#policy.projection_hash) {
          fail(
            "APPROVAL_POLICY_PROJECTION_MISMATCH",
            "approval capability projection differs from the sealed policy projection",
          );
        }
        if (readDataProperty(binding, "request_hash") !== requestHash) {
          fail("APPROVAL_ID_CONFLICT", "approval ID is bound to another canonical command");
        }
        const approval = normalizeApproval(
          requireImmutableRecord(
            approvalRecord,
            "ApprovalRecord",
            CAPABILITY_RECORD_TYPES.APPROVAL,
            command.approval_id,
          ),
        );
        return OBJECT_FREEZE({ approval, outboxId: readDataProperty(binding, "outbox_id") });
      }
      const issuedAt = this.#now();
      if (command.expires_at !== null && Date.parse(command.expires_at) <= Date.parse(issuedAt)) {
        fail("APPROVAL_ALREADY_EXPIRED", "approval expiry must be after authority time");
      }
      const approval = sealApproval({
        ...command,
        authority_id: authority.principal_id,
        authority_role: authority.authority_role,
        issued_at: issuedAt,
      });
      store.createRevisionedRecord({
        recordType: CAPABILITY_RECORD_TYPES.APPROVAL,
        recordId: approval.approval_id,
        value: approval,
      });
      this.#setApprovalHead(store, approval);
      const identity = outboxIdentity("approval", approval.approval_id);
      queueOutbox(store, {
        ...identity,
        runId: approval.run_id,
        eventType: CAPABILITY_EVENT_TYPES.APPROVAL_RECORDED,
        aggregateType: "approval",
        aggregateId: approval.approval_id,
        actorId: authority.principal_id,
        occurredAt: approval.issued_at,
        payload: { approval },
      });
      store.createRevisionedRecord({
        recordType: CAPABILITY_RECORD_TYPES.APPROVAL_BINDING,
        recordId: approval.approval_id,
        value: {
          request_hash: requestHash,
          outbox_id: identity.outboxId,
          policy_hash: this.#policy.policy_hash,
          policy_projection_hash: this.#policy.projection_hash,
        },
      });
      return OBJECT_FREEZE({ approval, outboxId: identity.outboxId });
    });
    this.#publish(result.outboxId);
    return result.approval;
  }

  issueLease(authenticatedPrincipalId, candidate) {
    const issuer = this.#principal(authenticatedPrincipalId);
    this.#assertDirectCapability(issuer, "capability:issue");
    const command = normalizeLeaseCommand(candidate);
    const principal = this.#principal(command.principal_id);
    this.#assertLeaseGrant(principal, command);
    const requestHash = sha256CanonicalJson({
      authenticated_principal_id: issuer.principal_id,
      command,
      policy_hash: this.#policy.policy_hash,
    });
    const result = this.#stateStore.transaction((store) => {
      const bindingRecord = store.readRevisionedRecord(
        CAPABILITY_RECORD_TYPES.LEASE_BINDING,
        command.lease_id,
      );
      const leaseRecord = store.readRevisionedRecord(CAPABILITY_RECORD_TYPES.LEASE, command.lease_id);
      if (bindingRecord !== null || leaseRecord !== null) {
        const binding = requirePlainDataObject(
          requireImmutableRecord(
            bindingRecord,
            "lease binding",
            CAPABILITY_RECORD_TYPES.LEASE_BINDING,
            command.lease_id,
          ),
          "lease binding",
          {
            allowedKeys: [
              "request_hash",
              "outbox_id",
              "run_id",
              "policy_hash",
              "policy_projection_hash",
            ],
            code: "CAPABILITY_STATE_INTEGRITY_FAILED",
          },
        );
        if (readDataProperty(binding, "policy_hash") !== this.#policy.policy_hash) {
          fail("LEASE_POLICY_MISMATCH", "existing lease binding belongs to another sealed policy");
        }
        if (readDataProperty(binding, "policy_projection_hash") !== this.#policy.projection_hash) {
          fail(
            "LEASE_POLICY_PROJECTION_MISMATCH",
            "existing lease capability projection differs from sealed policy",
          );
        }
        if (readDataProperty(binding, "request_hash") !== requestHash) {
          fail("LEASE_ID_CONFLICT", "lease ID is bound to another canonical command");
        }
        if (leaseRecord === null) {
          fail("CAPABILITY_STATE_MISSING", "lease binding exists without its CapabilityLease");
        }
        const lease = normalizeLease(leaseRecord.value);
        if (lease.policy_hash !== this.#policy.policy_hash) {
          fail("LEASE_POLICY_MISMATCH", "existing lease belongs to another sealed policy");
        }
        return OBJECT_FREEZE({ lease, outboxId: readDataProperty(binding, "outbox_id") });
      }
      const issuedAt = this.#now();
      if (Date.parse(command.expires_at) <= Date.parse(issuedAt)) {
        fail("LEASE_ALREADY_EXPIRED", "lease expiry must be after authority time");
      }
      this.#assertApprovals(store, { ...command, issued_at: issuedAt }, issuedAt);
      const token = allocateFencingToken(store);
      const lease = sealLease({
        lease_id: command.lease_id,
        principal_id: principal.principal_id,
        principal_type: principal.principal_type,
        capabilities: command.capabilities,
        resource_scopes: command.resource_scopes,
        issued_at: issuedAt,
        expires_at: command.expires_at,
        fencing_token: token,
        policy_hash: this.#policy.policy_hash,
        approval_ids: command.approval_ids,
        revoked: false,
        revocation_reason: null,
      });
      store.createRevisionedRecord({
        recordType: CAPABILITY_RECORD_TYPES.LEASE,
        recordId: lease.lease_id,
        value: lease,
      });
      for (const scope of lease.resource_scopes) setScopeHead(store, scope, lease);
      const identity = outboxIdentity("lease-issued", lease.lease_id);
      queueOutbox(store, {
        ...identity,
        runId: command.run_id,
        eventType: CAPABILITY_EVENT_TYPES.LEASE_ISSUED,
        aggregateType: "capability_lease",
        aggregateId: lease.lease_id,
        actorId: issuer.principal_id,
        occurredAt: lease.issued_at,
        payload: { lease },
      });
      store.createRevisionedRecord({
        recordType: CAPABILITY_RECORD_TYPES.LEASE_BINDING,
        recordId: lease.lease_id,
        value: {
          request_hash: requestHash,
          outbox_id: identity.outboxId,
          run_id: command.run_id,
          policy_hash: this.#policy.policy_hash,
          policy_projection_hash: this.#policy.projection_hash,
        },
      });
      return OBJECT_FREEZE({ lease, outboxId: identity.outboxId });
    });
    this.#publish(result.outboxId);
    return result.lease;
  }

  #commitWithLeaseCore(candidate, callback, allowedRecordTypes) {
    if (typeof callback !== "function") fail("INVALID_INPUT", "lease commit callback must be a function");
    const command = requirePlainDataObject(candidate, "lease use command", {
      allowedKeys: USE_COMMAND_KEYS,
    });
    const normalized = canonicalClone({
      operation_id: requireNonEmptyString(readDataProperty(command, "operation_id"), "operation_id"),
      run_id: requireNonEmptyString(readDataProperty(command, "run_id"), "run_id"),
      lease: normalizeLease(readDataProperty(command, "lease")),
      principal_id: requireNonEmptyString(readDataProperty(command, "principal_id"), "principal_id"),
      capability: requireNonEmptyString(readDataProperty(command, "capability"), "capability"),
      resource_scopes: requireStringArray(
        readDataProperty(command, "resource_scopes"),
        "resource_scopes",
        { minItems: 1, unique: true, sort: true },
      ),
    });
    const requestHash = sha256CanonicalJson({
      operation_id: normalized.operation_id,
      run_id: normalized.run_id,
      lease_hash: normalized.lease.lease_hash,
      fencing_token: normalized.lease.fencing_token,
      principal_id: normalized.principal_id,
      capability: normalized.capability,
      resource_scopes: normalized.resource_scopes,
    });
    const recordId = operationRecordId(normalized.operation_id);
    const transactionResult = this.#stateStore.transaction((store) => {
      const existing = readLeaseUseRecord(store, normalized.operation_id);
      if (existing !== null) {
        const { use } = existing;
        if (readDataProperty(use, "request_hash") !== requestHash) {
          fail("LEASE_OPERATION_CONFLICT", "operation ID is bound to another lease request");
        }
        return OBJECT_FREEZE({ status: "EXISTING", use });
      }
      const startedAt = this.#now();
      const lease = this.#assertCurrentLease(store, normalized.lease, normalized, startedAt);
      let callbackResult;
      try {
        callbackResult = callback(
          createLeaseCommitStore(store, allowedRecordTypes),
          lease,
        );
      } catch (error) {
        if (error instanceof CapabilityAuthorityError) throw error;
        fail(
          "LEASE_COMMIT_CALLBACK_FAILED",
          "lease-protected mutation failed and was rolled back",
          { causeCode: dependencyCauseCode(error), operationId: normalized.operation_id },
          { cause: error },
        );
      }
      if (isThenable(callbackResult)) {
        if (typeof callbackResult.catch === "function") callbackResult.catch(() => undefined);
        fail("ASYNC_LEASE_COMMIT_DENIED", "lease commit callback must be synchronous");
      }
      let result;
      try {
        result = canonicalClone(callbackResult);
      } catch (error) {
        if (error instanceof CapabilityAuthorityError) {
          fail("LEASE_COMMIT_RESULT_INVALID", "lease commit result must be canonical JSON", {
            causeCode: error.code,
          });
        }
        throw error;
      }
      const committedAt = this.#now();
      if (Date.parse(committedAt) < Date.parse(startedAt)) {
        fail("CLOCK_REGRESSION", "authority clock moved backwards during lease-protected commit", {
          committedAt,
          startedAt,
        });
      }
      this.#assertCurrentLease(store, lease, normalized, committedAt);
      const identity = outboxIdentity("lease-use", normalized.operation_id);
      const use = canonicalClone({
        operation_id: normalized.operation_id,
        request_hash: requestHash,
        lease_id: lease.lease_id,
        fencing_token: lease.fencing_token,
        committed_at: committedAt,
        result,
        outbox_id: identity.outboxId,
      });
      store.createRevisionedRecord({
        recordType: CAPABILITY_RECORD_TYPES.LEASE_USE,
        recordId,
        value: use,
      });
      queueOutbox(store, {
        ...identity,
        runId: normalized.run_id,
        eventType: CAPABILITY_EVENT_TYPES.LEASE_USE_COMMITTED,
        aggregateType: "capability_lease",
        aggregateId: lease.lease_id,
        actorId: normalized.principal_id,
        occurredAt: committedAt,
        payload: { use },
      });
      return OBJECT_FREEZE({ status: "COMMITTED", use });
    });
    return OBJECT_FREEZE({ recordId, transactionResult });
  }

  commitWithLease(candidate, callback) {
    const { recordId, transactionResult } = this.#commitWithLeaseCore(
      candidate,
      callback,
      null,
    );
    const published = this.#publish(transactionResult.use.outbox_id);
    return OBJECT_FREEZE({
      status: transactionResult.status,
      operation_id: transactionResult.use.operation_id,
      lease_id: transactionResult.use.lease_id,
      fencing_token: transactionResult.use.fencing_token,
      result: transactionResult.use.result,
      lease_use_id: recordId,
      lease_use_hash: sha256CanonicalJson(transactionResult.use),
      event_record_id: published.event_id,
      event_record_hash: published.event_hash,
    });
  }

  commitWithLeaseDeferredEvent(candidate, callback, allowedRecordTypes) {
    const allowlist = normalizeExternalRecordTypeAllowlist(allowedRecordTypes);
    const { recordId, transactionResult } = this.#commitWithLeaseCore(
      candidate,
      callback,
      allowlist,
    );
    return OBJECT_FREEZE({
      status: transactionResult.status,
      operation_id: transactionResult.use.operation_id,
      lease_id: transactionResult.use.lease_id,
      fencing_token: transactionResult.use.fencing_token,
      result: transactionResult.use.result,
      lease_use_id: recordId,
      lease_use_hash: sha256CanonicalJson(transactionResult.use),
      event_outbox_id: transactionResult.use.outbox_id,
      event_publication_status: "DEFERRED",
    });
  }

  revokeLease(authenticatedPrincipalId, candidate) {
    const authority = this.#principal(authenticatedPrincipalId);
    this.#assertDirectCapability(authority, "capability:revoke");
    const commandObject = requirePlainDataObject(candidate, "revoke command", {
      allowedKeys: REVOKE_COMMAND_KEYS,
    });
    const command = canonicalClone({
      lease_id: requireNonEmptyString(readDataProperty(commandObject, "lease_id"), "lease_id"),
      run_id: requireNonEmptyString(readDataProperty(commandObject, "run_id"), "run_id"),
      reason: requireNonEmptyString(readDataProperty(commandObject, "reason"), "reason"),
    });
    const revokedAt = this.#now();
    const result = this.#stateStore.transaction((store) => {
      const { lease, record } = this.#readLease(store, command.lease_id);
      const binding = requirePlainDataObject(
        requireImmutableRecord(
          store.readRevisionedRecord(CAPABILITY_RECORD_TYPES.LEASE_BINDING, lease.lease_id),
          "lease binding",
          CAPABILITY_RECORD_TYPES.LEASE_BINDING,
          lease.lease_id,
        ),
        "lease binding",
        {
          allowedKeys: [
            "request_hash",
            "outbox_id",
            "run_id",
            "policy_hash",
            "policy_projection_hash",
          ],
          code: "CAPABILITY_STATE_INTEGRITY_FAILED",
        },
      );
      if (readDataProperty(binding, "run_id") !== command.run_id) {
        fail("LEASE_RUN_SCOPE_MISMATCH", "lease cannot be revoked from another run");
      }
      if (lease.revoked) {
        if (lease.revocation_reason !== command.reason) {
          fail("LEASE_REVOCATION_CONFLICT", "lease is already revoked for another reason");
        }
        const identity = outboxIdentity("lease-revoked", lease.lease_id);
        return OBJECT_FREEZE({ lease, outboxId: identity.outboxId });
      }
      const { lease_hash: _previousLeaseHash, ...leaseWithoutHash } = lease;
      const revoked = sealLease({
        ...leaseWithoutHash,
        revoked: true,
        revocation_reason: command.reason,
      });
      updateRecord(store, record, revoked, "CapabilityLease revocation");
      for (const scope of revoked.resource_scopes) {
        const headRecord = store.readRevisionedRecord(
          CAPABILITY_RECORD_TYPES.SCOPE_HEAD,
          scopeRecordId(scope),
        );
        const head = validateScopeHead(headRecord, scope);
        if (
          head !== null &&
          head.lease_id === revoked.lease_id &&
          head.fencing_token === revoked.fencing_token
        ) {
          updateRecord(
            store,
            headRecord,
            { ...head, lease_hash: revoked.lease_hash },
            `revoked scope head ${scope}`,
          );
        }
      }
      const identity = outboxIdentity("lease-revoked", revoked.lease_id);
      queueOutbox(store, {
        ...identity,
        runId: command.run_id,
        eventType: CAPABILITY_EVENT_TYPES.LEASE_REVOKED,
        aggregateType: "capability_lease",
        aggregateId: revoked.lease_id,
        actorId: authority.principal_id,
        occurredAt: revokedAt,
        payload: { lease: revoked, revoked_at: revokedAt },
      });
      return OBJECT_FREEZE({ lease: revoked, outboxId: identity.outboxId });
    });
    this.#publish(result.outboxId);
    return result.lease;
  }

  inspectLeaseUse(operationId) {
    const id = requireNonEmptyString(operationId, "operationId");
    return this.#stateStore.transaction((store) => {
      const record = readLeaseUseRecord(store, id);
      if (record === null) return null;
      const { recordId, use } = record;
      const identity = outboxIdentity("lease-use", id);
      const outboxRecord = store.readRevisionedRecord(
        CAPABILITY_RECORD_TYPES.OUTBOX,
        identity.outboxId,
      );
      if (
        outboxRecord === null ||
        outboxRecord.recordType !== CAPABILITY_RECORD_TYPES.OUTBOX ||
        outboxRecord.recordId !== identity.outboxId
      ) {
        fail("CAPABILITY_STATE_INTEGRITY_FAILED", "lease use event outbox is missing", {
          operationId: id,
        });
      }
      const outbox = validateOutbox(outboxRecord.value);
      if (
        outboxRecord.revision !== (outbox.published ? 1 : 0) ||
        use.outbox_id !== identity.outboxId ||
        outbox.outbox_id !== identity.outboxId ||
        outbox.event_id !== identity.eventId ||
        outbox.payload_artifact_id !== identity.artifactId ||
        outbox.event_type !== CAPABILITY_EVENT_TYPES.LEASE_USE_COMMITTED ||
        outbox.aggregate_type !== "capability_lease" ||
        outbox.aggregate_id !== use.lease_id ||
        !sameCanonical(outbox.payload, { use })
      ) {
        fail("CAPABILITY_STATE_INTEGRITY_FAILED", "lease use event binding is invalid", {
          operationId: id,
        });
      }
      return OBJECT_FREEZE({
        status: "COMMITTED",
        operation_id: use.operation_id,
        request_hash: use.request_hash,
        lease_id: use.lease_id,
        fencing_token: use.fencing_token,
        result: use.result,
        lease_use_id: recordId,
        lease_use_hash: sha256CanonicalJson(use),
        event_outbox_id: outbox.outbox_id,
        event_publication_status: outbox.published
          ? "PUBLISHED"
          : "PENDING_EVENT_RECONCILIATION",
        event: OBJECT_FREEZE({
          event_id: outbox.event_id,
          run_id: outbox.run_id,
          event_type: outbox.event_type,
          aggregate_type: outbox.aggregate_type,
          aggregate_id: outbox.aggregate_id,
          actor_id: outbox.actor_id,
          payload_artifact_id: outbox.payload_artifact_id,
          occurred_at: outbox.occurred_at,
          schema_version: EVENT_SCHEMA_VERSION,
          event_hash: outbox.event_hash,
        }),
      });
    });
  }

  reconcileLeaseUseEvent(operationId) {
    const id = requireNonEmptyString(operationId, "operationId");
    const before = this.inspectLeaseUse(id);
    if (before === null) {
      fail("CAPABILITY_STATE_MISSING", "lease use does not exist", { operationId: id });
    }
    this.#publish(before.event_outbox_id);
    const after = this.inspectLeaseUse(id);
    if (after === null || after.event_publication_status !== "PUBLISHED") {
      fail(
        "CAPABILITY_EVENT_RECONCILIATION_REQUIRED",
        "lease use event publication remains unresolved",
        { operationId: id },
      );
    }
    return after;
  }

  readLease(leaseId) {
    const id = requireNonEmptyString(leaseId, "leaseId");
    return this.#stateStore.transaction((store) => this.#readLease(store, id).lease);
  }

  readApproval(approvalId) {
    const id = requireNonEmptyString(approvalId, "approvalId");
    return this.#stateStore.transaction((store) => this.#readApproval(store, id));
  }

  reconcileEvents() {
    const outboxIds = this.#stateStore.transaction((store) =>
      validateOutboxIndex(
        store.readRevisionedRecord(CAPABILITY_RECORD_TYPES.OUTBOX_INDEX, OUTBOX_INDEX_ID),
      ),
    );
    let published = 0;
    let existing = 0;
    for (const outboxId of outboxIds) {
      const before = this.#stateStore.transaction((store) => {
        const record = store.readRevisionedRecord(CAPABILITY_RECORD_TYPES.OUTBOX, outboxId);
        if (record === null) fail("CAPABILITY_STATE_MISSING", "indexed outbox is missing", { outboxId });
        return validateOutbox(record.value).published;
      });
      this.#publish(outboxId);
      if (before) existing += 1;
      else published += 1;
    }
    return OBJECT_FREEZE({ existing, published, total: outboxIds.length });
  }
}

export const getCapabilityAuthorityDependencyIdentity = (authority) => {
  const identity = CAPABILITY_AUTHORITY_DEPENDENCY_IDENTITIES.get(authority);
  if (identity === undefined) {
    fail("INVALID_INPUT", "authority must come from createCapabilityAuthority()");
  }
  return identity;
};

export const createCapabilityAuthority = (options) =>
  new CapabilityAuthority(CONSTRUCTOR_TOKEN, normalizeDependencies(options));
