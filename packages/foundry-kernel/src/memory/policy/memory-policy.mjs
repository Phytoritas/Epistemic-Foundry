/**
 * Deterministic L01 memory-policy admission boundary.
 *
 * This module decides whether a single memory record is eligible to reach the
 * L02 retrieval layer. It does not search, redact, delete, deduplicate, or
 * implement legal hold. Invalid policy or consent artifacts fail closed;
 * ordinary access denials are returned as immutable typed decisions.
 */

import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;

const DAY_MILLISECONDS = 86_400_000;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|([+-])(\d{2}):(\d{2}))$/u;

export const MEMORY_CLASSES = OBJECT_FREEZE([
  "EPHEMERAL",
  "SESSION",
  "WORKSPACE",
  "USER",
  "EVIDENCE",
  "REGULATED",
]);
const MEMORY_CLASS_SET = new Set(MEMORY_CLASSES);
const MEMORY_CLASS_RANK = new Map(MEMORY_CLASSES.map((value, index) => [value, index]));

export const CROSS_WORKSPACE_RETRIEVAL = OBJECT_FREEZE({
  DENY: "DENY",
  EXPLICIT_ONLY: "EXPLICIT_ONLY",
  ALLOW_BY_POLICY: "ALLOW_BY_POLICY",
});
const CROSS_WORKSPACE_SET = new Set(Object.values(CROSS_WORKSPACE_RETRIEVAL));

export const CONSENT_DECISIONS = OBJECT_FREEZE([
  "GRANTED",
  "DENIED",
  "REVOKED",
  "EXPIRED",
]);
const CONSENT_DECISION_SET = new Set(CONSENT_DECISIONS);
const EXTERNAL_SYNC_SET = new Set(["DENY", "ALLOW_REDACTED", "ALLOW"]);

const POLICY_FIELDS = OBJECT_FREEZE([
  "policy_id",
  "workspace_id",
  "allowed_classes",
  "default_retention_days",
  "class_rules",
  "cross_workspace_retrieval",
  "effective_at",
]);
const SEALED_POLICY_FIELDS = OBJECT_FREEZE([...POLICY_FIELDS, "policy_hash"]);
const CLASS_RULE_FIELDS = OBJECT_FREEZE([
  "class",
  "retention_days",
  "requires_consent",
  "external_sync",
  "redaction_profile",
]);
const CONSENT_FIELDS = OBJECT_FREEZE([
  "consent_id",
  "subject_id",
  "workspace_id",
  "purposes",
  "data_classes",
  "scopes",
  "decision",
  "granted_at",
  "expires_at",
  "revoked_at",
  "recorded_by",
  "policy_hash",
]);
const SEALED_CONSENT_FIELDS = OBJECT_FREEZE([...CONSENT_FIELDS, "record_hash"]);
const ACCESS_REQUEST_FIELDS = OBJECT_FREEZE([
  "workspace_id",
  "target_workspace_id",
  "memory_class",
  "purpose",
  "data_class",
  "scope",
  "memory_created_at",
  "evaluated_at",
  "cross_workspace_opt_in",
]);
const EVALUATION_FIELDS = OBJECT_FREEZE(["policy", "request", "consent_record"]);

export class MemoryPolicyError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "MemoryPolicyError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze({ ...details });
  }
}

const fail = (code, message, details) => {
  throw new MemoryPolicyError(code, message, details);
};

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

const requirePlainDataObject = (value, label, fields, code = "INVALID_INPUT") => {
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
  const allowed = new Set(fields);
  const keys = REFLECT_OWN_KEYS(value);
  for (const key of keys) {
    if (typeof key !== "string" || !allowed.has(key)) {
      fail(code, `${label} contains an unsupported field`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor === undefined || !descriptor.enumerable || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail(code, `${label}.${String(key)} must be an enumerable data property`);
    }
  }
  for (const field of fields) {
    if (!OBJECT_HAS_OWN(value, field)) fail(code, `${label}.${field} is required`);
  }
  return value;
};

const readDataProperty = (object, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(object, key).value;

const readDenseArray = (value, label, code = "INVALID_INPUT") => {
  if (!ARRAY_IS_ARRAY(value) || IS_PROXY(value) || OBJECT_GET_PROTOTYPE_OF(value) !== Array.prototype) {
    fail(code, `${label} must be a plain dense array`);
  }
  const keys = REFLECT_OWN_KEYS(value);
  for (const key of keys) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
      fail(code, `${label} contains a non-element property`);
    }
    const index = Number(key);
    if (!Number.isSafeInteger(index) || index >= value.length || String(index) !== key) {
      fail(code, `${label} contains an invalid element index`);
    }
  }
  const result = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (descriptor === undefined || !descriptor.enumerable || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail(code, `${label} contains a sparse or accessor element`);
    }
    result.push(descriptor.value);
  }
  return result;
};

const requireString = (
  value,
  label,
  { minLength = 1, maxLength = Number.MAX_SAFE_INTEGER, code = "INVALID_INPUT" } = {},
) => {
  if (
    typeof value !== "string" ||
    !hasOnlyUnicodeScalars(value) ||
    value.length < minLength ||
    value.length > maxLength
  ) {
    fail(code, `${label} must be a Unicode string with length ${minLength}..${maxLength}`);
  }
  return value;
};

const requireIdentifier = (value, label, code = "INVALID_INPUT") =>
  requireString(value, label, { minLength: 3, maxLength: 128, code });

const requireStringSet = (value, label, { minItems = 1, code = "INVALID_INPUT" } = {}) => {
  const entries = readDenseArray(value, label, code).map((entry, index) =>
    requireString(entry, `${label}[${index}]`, { code }),
  );
  if (entries.length < minItems) fail(code, `${label} must contain at least ${minItems} item(s)`);
  if (new Set(entries).size !== entries.length) fail(code, `${label} must not contain duplicates`);
  entries.sort();
  return OBJECT_FREEZE(entries);
};

const requireNonNegativeInteger = (value, label, code = "INVALID_INPUT") => {
  if (!Number.isSafeInteger(value) || value < 0) {
    fail(code, `${label} must be a non-negative safe integer`);
  }
  return value;
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
    Number.isFinite(Date.parse(value))
  );
};

const requireTimestamp = (value, label, code = "INVALID_INPUT") => {
  if (!isRfc3339(value)) fail(code, `${label} must be a real RFC 3339 date-time`);
  return value;
};

const requireNullableTimestamp = (value, label, code) =>
  value === null ? null : requireTimestamp(value, label, code);

const assertCanonicalJsonValue = (value, label = "value", ancestors = new WeakSet()) => {
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") {
    if (!hasOnlyUnicodeScalars(value)) fail("NON_CANONICAL_JSON", `${label} has invalid Unicode`);
    return;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value) || Object.is(value, -0)) {
      fail("NON_CANONICAL_JSON", `${label} has a non-canonical number`);
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
      for (const [index, entry] of readDenseArray(value, label, "NON_CANONICAL_JSON").entries()) {
        assertCanonicalJsonValue(entry, `${label}[${index}]`, ancestors);
      }
      return;
    }
    const prototype = OBJECT_GET_PROTOTYPE_OF(value);
    if (prototype !== PLAIN_OBJECT_PROTOTYPE && prototype !== null) {
      fail("NON_CANONICAL_JSON", `${label} must contain plain JSON objects`);
    }
    for (const key of REFLECT_OWN_KEYS(value)) {
      if (typeof key !== "string" || !hasOnlyUnicodeScalars(key)) {
        fail("NON_CANONICAL_JSON", `${label} has a non-canonical property name`);
      }
      const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
      if (descriptor === undefined || !descriptor.enumerable || !OBJECT_HAS_OWN(descriptor, "value")) {
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
  if (ARRAY_IS_ARRAY(value)) return `[${value.map(renderCanonicalJson).join(",")}]`;
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${renderCanonicalJson(readDataProperty(value, key))}`)
    .join(",")}}`;
};

export const canonicalMemoryPolicyJson = (value) => {
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

const canonicalClone = (value) => deepFreeze(JSON.parse(canonicalMemoryPolicyJson(value)));
const sha256CanonicalJson = (value) =>
  `sha256:${createHash("sha256").update(canonicalMemoryPolicyJson(value), "utf8").digest("hex")}`;

const requireMemoryClass = (value, label, code = "UNKNOWN_MEMORY_CLASS") => {
  if (typeof value !== "string" || !MEMORY_CLASS_SET.has(value)) {
    fail(code, `${label} is not a canonical memory class`, { value });
  }
  return value;
};

const normalizeClassRule = (candidate, index, allowedClasses) => {
  const code = "MEMORY_POLICY_INVALID";
  const rule = requirePlainDataObject(candidate, `class_rules[${index}]`, CLASS_RULE_FIELDS, code);
  const memoryClass = requireMemoryClass(readDataProperty(rule, "class"), `class_rules[${index}].class`);
  if (!allowedClasses.has(memoryClass)) {
    fail("CLASS_RULE_NOT_ALLOWED", "a class rule cannot grant a class outside allowed_classes", {
      memory_class: memoryClass,
    });
  }
  const requiresConsent = readDataProperty(rule, "requires_consent");
  if (typeof requiresConsent !== "boolean") {
    fail(code, `class_rules[${index}].requires_consent must be boolean`);
  }
  const externalSync = readDataProperty(rule, "external_sync");
  if (!EXTERNAL_SYNC_SET.has(externalSync)) {
    fail(code, `class_rules[${index}].external_sync is not canonical`);
  }
  return {
    class: memoryClass,
    retention_days: requireNonNegativeInteger(
      readDataProperty(rule, "retention_days"),
      `class_rules[${index}].retention_days`,
      code,
    ),
    requires_consent: requiresConsent,
    external_sync: externalSync,
    redaction_profile: requireString(
      readDataProperty(rule, "redaction_profile"),
      `class_rules[${index}].redaction_profile`,
      { code },
    ),
  };
};

const normalizePolicy = (candidate, { sealed }) => {
  const code = "MEMORY_POLICY_INVALID";
  const fields = sealed ? SEALED_POLICY_FIELDS : POLICY_FIELDS;
  const policy = requirePlainDataObject(candidate, "MemoryPolicy", fields, code);
  const allowedClasses = readDenseArray(readDataProperty(policy, "allowed_classes"), "allowed_classes", code)
    .map((entry, index) => requireMemoryClass(entry, `allowed_classes[${index}]`));
  if (allowedClasses.length === 0) fail(code, "allowed_classes must not be empty");
  if (new Set(allowedClasses).size !== allowedClasses.length) {
    fail(code, "allowed_classes must not contain duplicates");
  }
  allowedClasses.sort((left, right) => MEMORY_CLASS_RANK.get(left) - MEMORY_CLASS_RANK.get(right));
  const allowedSet = new Set(allowedClasses);
  const classRules = readDenseArray(readDataProperty(policy, "class_rules"), "class_rules", code)
    .map((rule, index) => normalizeClassRule(rule, index, allowedSet));
  if (classRules.length === 0) fail("CLASS_RULE_MISSING", "class_rules must contain at least one rule");
  const ruleClasses = classRules.map((rule) => rule.class);
  if (new Set(ruleClasses).size !== ruleClasses.length) {
    fail("DUPLICATE_CLASS_RULE", "class_rules must contain at most one rule per memory class");
  }
  classRules.sort(
    (left, right) => MEMORY_CLASS_RANK.get(left.class) - MEMORY_CLASS_RANK.get(right.class),
  );
  const crossWorkspaceRetrieval = readDataProperty(policy, "cross_workspace_retrieval");
  if (!CROSS_WORKSPACE_SET.has(crossWorkspaceRetrieval)) {
    fail(code, "cross_workspace_retrieval is not canonical");
  }
  const normalized = {
    policy_id: requireIdentifier(readDataProperty(policy, "policy_id"), "policy_id", code),
    workspace_id: requireIdentifier(readDataProperty(policy, "workspace_id"), "workspace_id", code),
    allowed_classes: allowedClasses,
    default_retention_days: requireNonNegativeInteger(
      readDataProperty(policy, "default_retention_days"),
      "default_retention_days",
      code,
    ),
    class_rules: classRules,
    cross_workspace_retrieval: crossWorkspaceRetrieval,
    effective_at: requireTimestamp(readDataProperty(policy, "effective_at"), "effective_at", code),
  };
  if (!sealed) return canonicalClone(normalized);
  const policyHash = readDataProperty(policy, "policy_hash");
  if (typeof policyHash !== "string" || !SHA256_PATTERN.test(policyHash)) {
    fail(code, "policy_hash must be a canonical SHA-256 digest");
  }
  const expected = computeMemoryPolicyHash(normalized);
  if (policyHash !== expected) {
    fail("MEMORY_POLICY_HASH_MISMATCH", "policy_hash does not match the normalized policy", {
      actual: policyHash,
      expected,
    });
  }
  return canonicalClone({ ...normalized, policy_hash: policyHash });
};

export const computeMemoryPolicyHash = (candidate) => {
  const normalized = normalizePolicy(candidate, { sealed: false });
  return sha256CanonicalJson(normalized);
};

export const sealMemoryPolicy = (candidate) => {
  const normalized = normalizePolicy(candidate, { sealed: false });
  return canonicalClone({ ...normalized, policy_hash: sha256CanonicalJson(normalized) });
};

export const validateMemoryPolicy = (candidate) => normalizePolicy(candidate, { sealed: true });

const normalizeConsent = (candidate, { sealed }) => {
  const code = "CONSENT_RECORD_INVALID";
  const fields = sealed ? SEALED_CONSENT_FIELDS : CONSENT_FIELDS;
  const consent = requirePlainDataObject(candidate, "ConsentRecord", fields, code);
  const decision = readDataProperty(consent, "decision");
  if (!CONSENT_DECISION_SET.has(decision)) fail(code, "decision is not canonical");
  const grantedAt = requireNullableTimestamp(readDataProperty(consent, "granted_at"), "granted_at", code);
  const expiresAt = requireNullableTimestamp(readDataProperty(consent, "expires_at"), "expires_at", code);
  const revokedAt = requireNullableTimestamp(readDataProperty(consent, "revoked_at"), "revoked_at", code);
  if (decision === "GRANTED" && grantedAt === null) fail(code, "GRANTED consent requires granted_at");
  if (decision === "REVOKED" && revokedAt === null) fail(code, "REVOKED consent requires revoked_at");
  if (decision === "EXPIRED" && expiresAt === null) fail(code, "EXPIRED consent requires expires_at");
  if (grantedAt !== null && expiresAt !== null && Date.parse(grantedAt) >= Date.parse(expiresAt)) {
    fail(code, "expires_at must be strictly later than granted_at");
  }
  const policyHash = readDataProperty(consent, "policy_hash");
  if (typeof policyHash !== "string" || !SHA256_PATTERN.test(policyHash)) {
    fail(code, "policy_hash must be a canonical SHA-256 digest");
  }
  const normalized = {
    consent_id: requireIdentifier(readDataProperty(consent, "consent_id"), "consent_id", code),
    subject_id: requireIdentifier(readDataProperty(consent, "subject_id"), "subject_id", code),
    workspace_id: requireIdentifier(readDataProperty(consent, "workspace_id"), "workspace_id", code),
    purposes: requireStringSet(readDataProperty(consent, "purposes"), "purposes", { code }),
    data_classes: requireStringSet(readDataProperty(consent, "data_classes"), "data_classes", { code }),
    scopes: requireStringSet(readDataProperty(consent, "scopes"), "scopes", { code }),
    decision,
    granted_at: grantedAt,
    expires_at: expiresAt,
    revoked_at: revokedAt,
    recorded_by: requireIdentifier(readDataProperty(consent, "recorded_by"), "recorded_by", code),
    policy_hash: policyHash,
  };
  if (!sealed) return canonicalClone(normalized);
  const recordHash = readDataProperty(consent, "record_hash");
  if (typeof recordHash !== "string" || !SHA256_PATTERN.test(recordHash)) {
    fail(code, "record_hash must be a canonical SHA-256 digest");
  }
  const expected = computeConsentRecordHash(normalized);
  if (recordHash !== expected) {
    fail("CONSENT_RECORD_HASH_MISMATCH", "record_hash does not match the normalized consent", {
      actual: recordHash,
      expected,
    });
  }
  return canonicalClone({ ...normalized, record_hash: recordHash });
};

export const computeConsentRecordHash = (candidate) => {
  const normalized = normalizeConsent(candidate, { sealed: false });
  return sha256CanonicalJson(normalized);
};

export const sealConsentRecord = (candidate) => {
  const normalized = normalizeConsent(candidate, { sealed: false });
  return canonicalClone({ ...normalized, record_hash: sha256CanonicalJson(normalized) });
};

export const validateConsentRecord = (candidate) => normalizeConsent(candidate, { sealed: true });

const normalizeAccessRequest = (candidate) => {
  const code = "MEMORY_ACCESS_REQUEST_INVALID";
  const request = requirePlainDataObject(candidate, "MemoryAccessRequest", ACCESS_REQUEST_FIELDS, code);
  const crossWorkspaceOptIn = readDataProperty(request, "cross_workspace_opt_in");
  if (typeof crossWorkspaceOptIn !== "boolean") {
    fail(code, "cross_workspace_opt_in must be boolean");
  }
  return canonicalClone({
    workspace_id: requireIdentifier(readDataProperty(request, "workspace_id"), "workspace_id", code),
    target_workspace_id: requireIdentifier(
      readDataProperty(request, "target_workspace_id"),
      "target_workspace_id",
      code,
    ),
    memory_class: requireMemoryClass(readDataProperty(request, "memory_class"), "memory_class"),
    purpose: requireString(readDataProperty(request, "purpose"), "purpose", { code }),
    data_class: requireString(readDataProperty(request, "data_class"), "data_class", { code }),
    scope: requireString(readDataProperty(request, "scope"), "scope", { code }),
    memory_created_at: requireTimestamp(
      readDataProperty(request, "memory_created_at"),
      "memory_created_at",
      code,
    ),
    evaluated_at: requireTimestamp(readDataProperty(request, "evaluated_at"), "evaluated_at", code),
    cross_workspace_opt_in: crossWorkspaceOptIn,
  });
};

export const retentionDaysForClass = (policyCandidate, memoryClass) => {
  const policy = validateMemoryPolicy(policyCandidate);
  const normalizedClass = requireMemoryClass(memoryClass, "memory_class");
  if (!policy.allowed_classes.includes(normalizedClass)) {
    fail("MEMORY_CLASS_NOT_ALLOWED", "memory class is not allowed by policy", {
      memory_class: normalizedClass,
    });
  }
  const rule = policy.class_rules.find((entry) => entry.class === normalizedClass);
  return rule?.retention_days ?? policy.default_retention_days;
};

const decision = (value) => canonicalClone(value);

const accessDecision = ({ policy, request, rule, consentId, allowed, reasonCode }) =>
  decision({
    decision: allowed ? "ALLOW" : "DENY",
    reason_code: reasonCode,
    policy_hash: policy.policy_hash,
    workspace_id: request.workspace_id,
    target_workspace_id: request.target_workspace_id,
    memory_class: request.memory_class,
    purpose: request.purpose,
    retention_days: rule?.retention_days ?? policy.default_retention_days,
    consent_id: consentId,
    evaluated_at: request.evaluated_at,
    cross_workspace: request.workspace_id !== request.target_workspace_id,
  });

/**
 * Evaluate one candidate memory before any index or store is searched.
 */
export const evaluateMemoryAccess = (candidate) => {
  const input = requirePlainDataObject(candidate, "MemoryAccessEvaluation", EVALUATION_FIELDS);
  const policy = validateMemoryPolicy(readDataProperty(input, "policy"));
  const request = normalizeAccessRequest(readDataProperty(input, "request"));
  const consentCandidate = readDataProperty(input, "consent_record");
  const deny = (reasonCode, rule = undefined, consentId = null) =>
    accessDecision({ policy, request, rule, consentId, allowed: false, reasonCode });

  if (request.workspace_id !== policy.workspace_id) return deny("POLICY_WORKSPACE_MISMATCH");
  if (Date.parse(request.evaluated_at) < Date.parse(policy.effective_at)) {
    return deny("POLICY_NOT_YET_EFFECTIVE");
  }
  if (!policy.allowed_classes.includes(request.memory_class)) return deny("MEMORY_CLASS_NOT_ALLOWED");
  const rule = policy.class_rules.find((entry) => entry.class === request.memory_class);
  const retentionDays = rule?.retention_days ?? policy.default_retention_days;
  const createdAt = Date.parse(request.memory_created_at);
  const evaluatedAt = Date.parse(request.evaluated_at);
  if (createdAt > evaluatedAt) return deny("MEMORY_TIMESTAMP_IN_FUTURE", rule);
  if (evaluatedAt - createdAt > retentionDays * DAY_MILLISECONDS) {
    return deny("RETENTION_EXPIRED", rule);
  }

  const crossWorkspace = request.workspace_id !== request.target_workspace_id;
  if (crossWorkspace) {
    if (policy.cross_workspace_retrieval === CROSS_WORKSPACE_RETRIEVAL.DENY) {
      return deny("CROSS_WORKSPACE_DENIED", rule);
    }
    if (request.memory_class !== "USER") {
      return deny("CROSS_WORKSPACE_CLASS_DENIED", rule);
    }
    if (!request.cross_workspace_opt_in) {
      return deny("CROSS_WORKSPACE_OPT_IN_REQUIRED", rule);
    }
  }

  const consentRequired = rule?.requires_consent === true || request.memory_class === "USER" || crossWorkspace;
  if (!consentRequired) {
    if (consentCandidate !== null) {
      validateConsentRecord(consentCandidate);
    }
    return accessDecision({
      policy,
      request,
      rule,
      consentId: null,
      allowed: true,
      reasonCode: "ACCESS_ALLOWED",
    });
  }
  if (consentCandidate === null) return deny("CONSENT_REQUIRED", rule);

  const consent = validateConsentRecord(consentCandidate);
  const consentId = consent.consent_id;
  if (consent.decision === "DENIED") return deny("CONSENT_DENIED", rule, consentId);
  if (consent.decision === "REVOKED") return deny("CONSENT_REVOKED", rule, consentId);
  if (consent.decision === "EXPIRED") return deny("CONSENT_EXPIRED", rule, consentId);
  if (consent.decision !== "GRANTED") return deny("CONSENT_NOT_GRANTED", rule, consentId);
  if (consent.policy_hash !== policy.policy_hash) return deny("CONSENT_POLICY_MISMATCH", rule, consentId);
  if (consent.workspace_id !== request.workspace_id) {
    return deny("CONSENT_WORKSPACE_MISMATCH", rule, consentId);
  }
  if (!consent.purposes.includes(request.purpose)) return deny("CONSENT_PURPOSE_MISMATCH", rule, consentId);
  if (!consent.data_classes.includes(request.data_class)) {
    return deny("CONSENT_DATA_CLASS_MISMATCH", rule, consentId);
  }
  if (
    request.scope !== request.memory_class ||
    !consent.scopes.includes(request.memory_class)
  ) {
    return deny("CONSENT_SCOPE_MISMATCH", rule, consentId);
  }
  if (consent.granted_at === null || Date.parse(consent.granted_at) > evaluatedAt) {
    return deny("CONSENT_NOT_YET_VALID", rule, consentId);
  }
  if (consent.revoked_at !== null && Date.parse(consent.revoked_at) <= evaluatedAt) {
    return deny("CONSENT_REVOKED", rule, consentId);
  }
  if (consent.expires_at !== null && Date.parse(consent.expires_at) <= evaluatedAt) {
    return deny("CONSENT_EXPIRED", rule, consentId);
  }
  return accessDecision({
    policy,
    request,
    rule,
    consentId,
    allowed: true,
    reasonCode: "ACCESS_ALLOWED",
  });
};

export const requireMemoryAccess = (candidate) => {
  const result = evaluateMemoryAccess(candidate);
  if (result.decision !== "ALLOW") {
    fail(result.reason_code, "memory access denied by deterministic L01 policy", { decision: result });
  }
  return result;
};
