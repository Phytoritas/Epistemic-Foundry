/**
 * Receipt-bound external-effect coordination.
 *
 * ActionIntent and EffectReceipt follow their canonical JSON Schemas. Attempt,
 * operation journal, idempotency index, and publication checkpoint records are
 * private Foundry Kernel storage projections; they do not introduce public
 * artifact schemas or extend the canonical schema bundle.
 */

import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

const ARRAY_IS_ARRAY = Array.isArray;
const BUFFER_IS_BUFFER = Buffer.isBuffer;
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
  /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:[Zz]|([+-])(\d{2}):(\d{2}))$/u;
const OPERATION_SCHEMA_VERSION = "1.0.0";
const EVENT_SCHEMA_VERSION = "4.0.0";
const EVENT_ACTOR_ID = "ACT-E02-effect-coordinator";

const ACTION_INTENT_KEYS = OBJECT_FREEZE([
  "intent_id",
  "run_id",
  "node_id",
  "action_type",
  "target_ref",
  "arguments_artifact_id",
  "arguments_hash",
  "idempotency_key",
  "required_capabilities",
  "approval_record_ids",
  "risk_class",
  "created_at",
  "intent_hash",
]);
const ACTION_INTENT_HASH_KEYS = OBJECT_FREEZE(
  ACTION_INTENT_KEYS.filter((key) => key !== "intent_hash"),
);
const ACTION_INTENT_INPUT_KEYS = ACTION_INTENT_HASH_KEYS;
const EFFECT_RECEIPT_KEYS = OBJECT_FREEZE([
  "receipt_id",
  "intent_id",
  "run_id",
  "external_operation_id",
  "status",
  "result_artifact_ids",
  "error_artifact_ids",
  "observed_state_hash",
  "idempotency_key",
  "started_at",
  "finished_at",
  "reconciliation_required",
  "receipt_hash",
]);
const EFFECT_RECEIPT_HASH_KEYS = OBJECT_FREEZE(
  EFFECT_RECEIPT_KEYS.filter((key) => key !== "receipt_hash"),
);
const EFFECT_RECEIPT_INPUT_KEYS = EFFECT_RECEIPT_HASH_KEYS;
const ATTEMPT_KEYS = OBJECT_FREEZE([
  "attempt_id",
  "attempt_number",
  "intent_id",
  "intent_hash",
  "run_id",
  "idempotency_key",
  "started_at",
  "attempt_hash",
]);
const ATTEMPT_HASH_KEYS = OBJECT_FREEZE(
  ATTEMPT_KEYS.filter((key) => key !== "attempt_hash"),
);
const ATTEMPT_INPUT_KEYS = OBJECT_FREEZE(["attempt_id", "intent_id", "started_at"]);
const IDEMPOTENCY_KEYS = OBJECT_FREEZE([
  "idempotency_key",
  "intent_id",
  "intent_hash",
]);
const OPERATION_KEYS = OBJECT_FREEZE([
  "schema_version",
  "intent_id",
  "intent_hash",
  "run_id",
  "idempotency_key",
  "journal",
]);
const PUBLICATION_KEYS = OBJECT_FREEZE([
  "schema_version",
  "intent_id",
  "intent_hash",
  "run_id",
  "published_event_count",
]);
const ATTEMPT_ENTRY_KEYS = OBJECT_FREEZE(["kind", "attempt_id"]);
const RECEIPT_ENTRY_KEYS = OBJECT_FREEZE([
  "kind",
  "attempt_id",
  "receipt_id",
  "mode",
]);

const RISK_CLASSES = new Set([
  "read_only",
  "bounded_compute",
  "controlled_effect",
  "high_risk",
]);
const EFFECT_STATUSES = new Set([
  "SUCCEEDED",
  "FAILED",
  "UNKNOWN",
  "ROLLED_BACK",
  "NOT_EXECUTED",
]);
const RESOLVING_STATUSES = new Set([
  "SUCCEEDED",
  "FAILED",
  "ROLLED_BACK",
  "NOT_EXECUTED",
]);
const RECEIPT_MODES = new Set(["EXECUTION", "RECONCILIATION"]);

export const EFFECT_RECORD_TYPES = OBJECT_FREEZE({
  ACTION_INTENT: "foundry.effects.action-intent.v1",
  ATTEMPT: "foundry.effects.attempt.v1",
  EFFECT_RECEIPT: "foundry.effects.effect-receipt.v1",
  IDEMPOTENCY: "foundry.effects.idempotency.v1",
  OPERATION: "foundry.effects.operation.v1",
  PUBLICATION: "foundry.effects.publication.v1",
});

export const EFFECT_EVENT_TYPES = OBJECT_FREEZE({
  ACTION_INTENT: "effect.action-intent.recorded",
  ATTEMPT: "effect.attempt.started",
  EFFECT_RECEIPT: "effect.receipt.recorded",
});

export class EffectCoordinatorError extends Error {
  constructor(code, message, details = undefined, options = undefined) {
    super(message, options);
    this.name = "EffectCoordinatorError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze({ ...details });
  }
}

const fail = (code, message, details, options) => {
  throw new EffectCoordinatorError(code, message, details, options);
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

const requireNullableString = (value, label, code) => {
  if (value === null) return null;
  if (typeof value !== "string" || value.length === 0 || !hasOnlyUnicodeScalars(value)) {
    fail(code, `${label} must be a non-empty Unicode scalar string or null`);
  }
  return value;
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
  if (!ARRAY_IS_ARRAY(value) || IS_PROXY(value)) {
    fail(code, `${label} must be a dense array`);
  }
  const keys = REFLECT_OWN_KEYS(value);
  for (let index = 0; index < keys.length; index += 1) {
    const key = keys[index];
    if (key === "length") continue;
    if (!isCanonicalArrayIndex(key, value.length)) {
      fail(code, `${label} contains a non-element property`);
    }
  }
  const output = new Array(value.length);
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail(code, `${label} contains a sparse or accessor element`);
    }
    output[index] = descriptor.value;
  }
  return output;
};

const requireStringArray = (
  value,
  label,
  { minItems = 0, code = "INVALID_INPUT" } = {},
) => {
  const entries = readDenseArray(value, label, code);
  if (entries.length < minItems) {
    fail(code, `${label} must contain at least ${minItems} item(s)`);
  }
  return OBJECT_FREEZE(
    entries.map((entry, index) =>
      requireNonEmptyString(entry, `${label}[${index}]`, code),
    ),
  );
};

const isLeapYear = (year) => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

const daysInMonth = (year, month) => {
  if (month === 2) return isLeapYear(year) ? 29 : 28;
  return month === 4 || month === 6 || month === 9 || month === 11 ? 30 : 31;
};

const parseRfc3339 = (value) => {
  if (typeof value !== "string" || !hasOnlyUnicodeScalars(value)) return null;
  const match = RFC3339_PATTERN.exec(value);
  if (match === null) return null;
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
    utcMinuteOfDay += 24 * 60;
    day -= 1;
    if (day === 0) {
      utcMonth -= 1;
      if (utcMonth === 0) {
        year -= 1;
        utcMonth = 12;
      }
      day = daysInMonth(year, utcMonth);
    }
  } else if (utcMinuteOfDay >= 24 * 60) {
    utcMinuteOfDay -= 24 * 60;
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
  return OBJECT_FREEZE([year, utcMonth, day, utcHour, utcMinute, second, fraction]);
};

const compareRfc3339 = (left, right) => {
  const leftTuple = parseRfc3339(left);
  const rightTuple = parseRfc3339(right);
  if (leftTuple === null || rightTuple === null) {
    fail("INVALID_INPUT", "RFC 3339 chronology comparison requires valid timestamps");
  }
  for (let index = 0; index < 6; index += 1) {
    if (leftTuple[index] < rightTuple[index]) return -1;
    if (leftTuple[index] > rightTuple[index]) return 1;
  }
  const leftFraction = leftTuple[6];
  const rightFraction = rightTuple[6];
  const length = leftFraction.length > rightFraction.length
    ? leftFraction.length
    : rightFraction.length;
  for (let index = 0; index < length; index += 1) {
    const leftDigit = index < leftFraction.length ? leftFraction.charCodeAt(index) : 48;
    const rightDigit = index < rightFraction.length ? rightFraction.charCodeAt(index) : 48;
    if (leftDigit < rightDigit) return -1;
    if (leftDigit > rightDigit) return 1;
  }
  return 0;
};

const requireTimestamp = (value, label, code = "INVALID_INPUT") => {
  if (parseRfc3339(value) === null) {
    fail(code, `${label} must be a real RFC 3339 date-time`);
  }
  return value;
};

const assertCanonicalJsonValue = (value, label = "value", ancestors = new WeakSet()) => {
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") {
    if (!hasOnlyUnicodeScalars(value)) {
      fail("NON_CANONICAL_JSON", `${label} contains an unpaired Unicode surrogate`);
    }
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
        fail("NON_CANONICAL_JSON", `${label} contains a non-canonical property name`);
      }
      const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
      if (
        descriptor === undefined ||
        !descriptor.enumerable ||
        !OBJECT_HAS_OWN(descriptor, "value")
      ) {
        fail("NON_CANONICAL_JSON", `${label}.${key} must be an enumerable data property`);
      }
      assertCanonicalJsonValue(descriptor.value, `${label}.${key}`, ancestors);
    }
  } finally {
    ancestors.delete(value);
  }
};

const renderCanonicalJson = (value) => {
  if (value === null) return "null";
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return JSON.stringify(value);
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

export const canonicalEffectJson = (value) => {
  assertCanonicalJsonValue(value);
  return renderCanonicalJson(value);
};

const sha256Bytes = (bytes) =>
  `sha256:${createHash("sha256").update(bytes).digest("hex")}`;

const sha256Text = (value) => sha256Bytes(Buffer.from(value, "utf8"));

const sha256CanonicalJson = (value) => sha256Text(canonicalEffectJson(value));

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  const keys = REFLECT_OWN_KEYS(value);
  for (let index = 0; index < keys.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, keys[index]);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};

const canonicalClone = (value) => deepFreeze(JSON.parse(canonicalEffectJson(value)));

const selectHashFields = (candidate, keys, label, code) => {
  const selected = {};
  for (let index = 0; index < keys.length; index += 1) {
    const key = keys[index];
    if (!OBJECT_HAS_OWN(candidate, key)) fail(code, `${label}.${key} is required for hashing`);
    selected[key] = readDataProperty(candidate, key);
  }
  return selected;
};

export const computeActionIntentHash = (intent) =>
  sha256CanonicalJson(
    selectHashFields(
      intent,
      ACTION_INTENT_HASH_KEYS,
      "ActionIntent",
      "ACTION_INTENT_INVALID",
    ),
  );

export const computeEffectReceiptHash = (receipt) =>
  sha256CanonicalJson(
    selectHashFields(
      receipt,
      EFFECT_RECEIPT_HASH_KEYS,
      "EffectReceipt",
      "EFFECT_RECEIPT_INVALID",
    ),
  );

const computeAttemptHash = (attempt) =>
  sha256CanonicalJson(
    selectHashFields(attempt, ATTEMPT_HASH_KEYS, "Attempt", "ATTEMPT_RECORD_INVALID"),
  );

const normalizeActionIntent = (candidate, { sealed = true } = {}) => {
  const keys = sealed ? ACTION_INTENT_KEYS : ACTION_INTENT_INPUT_KEYS;
  const intent = requirePlainDataObject(candidate, "ActionIntent", {
    allowedKeys: keys,
    code: "ACTION_INTENT_INVALID",
  });
  const riskClass = readDataProperty(intent, "risk_class");
  if (!RISK_CLASSES.has(riskClass)) {
    fail("ACTION_INTENT_INVALID", "ActionIntent.risk_class is not canonical");
  }
  const argumentsHash = readDataProperty(intent, "arguments_hash");
  if (typeof argumentsHash !== "string" || !SHA256_PATTERN.test(argumentsHash)) {
    fail("ACTION_INTENT_INVALID", "ActionIntent.arguments_hash is not canonical");
  }
  const normalized = {
    intent_id: requireNonEmptyString(
      readDataProperty(intent, "intent_id"),
      "ActionIntent.intent_id",
      "ACTION_INTENT_INVALID",
    ),
    run_id: requireNonEmptyString(
      readDataProperty(intent, "run_id"),
      "ActionIntent.run_id",
      "ACTION_INTENT_INVALID",
    ),
    node_id: requireNonEmptyString(
      readDataProperty(intent, "node_id"),
      "ActionIntent.node_id",
      "ACTION_INTENT_INVALID",
    ),
    action_type: requireNonEmptyString(
      readDataProperty(intent, "action_type"),
      "ActionIntent.action_type",
      "ACTION_INTENT_INVALID",
    ),
    target_ref: requireNonEmptyString(
      readDataProperty(intent, "target_ref"),
      "ActionIntent.target_ref",
      "ACTION_INTENT_INVALID",
    ),
    arguments_artifact_id: requireNonEmptyString(
      readDataProperty(intent, "arguments_artifact_id"),
      "ActionIntent.arguments_artifact_id",
      "ACTION_INTENT_INVALID",
    ),
    arguments_hash: argumentsHash,
    idempotency_key: requireNonEmptyString(
      readDataProperty(intent, "idempotency_key"),
      "ActionIntent.idempotency_key",
      "ACTION_INTENT_INVALID",
    ),
    required_capabilities: requireStringArray(
      readDataProperty(intent, "required_capabilities"),
      "ActionIntent.required_capabilities",
      { minItems: 1, code: "ACTION_INTENT_INVALID" },
    ),
    approval_record_ids: requireStringArray(
      readDataProperty(intent, "approval_record_ids"),
      "ActionIntent.approval_record_ids",
      { code: "ACTION_INTENT_INVALID" },
    ),
    risk_class: riskClass,
    created_at: requireTimestamp(
      readDataProperty(intent, "created_at"),
      "ActionIntent.created_at",
      "ACTION_INTENT_INVALID",
    ),
  };
  if (!sealed) return canonicalClone(normalized);
  const intentHash = readDataProperty(intent, "intent_hash");
  if (typeof intentHash !== "string" || !SHA256_PATTERN.test(intentHash)) {
    fail("ACTION_INTENT_INVALID", "ActionIntent.intent_hash is not canonical");
  }
  const complete = { ...normalized, intent_hash: intentHash };
  const expected = computeActionIntentHash(complete);
  if (intentHash !== expected) {
    fail("ACTION_INTENT_HASH_MISMATCH", "ActionIntent.intent_hash does not match canonical fields", {
      actual: intentHash,
      expected,
      intentId: normalized.intent_id,
    });
  }
  return canonicalClone(complete);
};

export const sealActionIntent = (input) => {
  const normalized = normalizeActionIntent(input, { sealed: false });
  return canonicalClone({ ...normalized, intent_hash: computeActionIntentHash(normalized) });
};

const normalizeEffectReceipt = (candidate, { sealed = true } = {}) => {
  const keys = sealed ? EFFECT_RECEIPT_KEYS : EFFECT_RECEIPT_INPUT_KEYS;
  const receipt = requirePlainDataObject(candidate, "EffectReceipt", {
    allowedKeys: keys,
    code: "EFFECT_RECEIPT_INVALID",
  });
  const status = readDataProperty(receipt, "status");
  if (!EFFECT_STATUSES.has(status)) {
    fail("EFFECT_RECEIPT_INVALID", "EffectReceipt.status is not canonical");
  }
  const observedStateHash = readDataProperty(receipt, "observed_state_hash");
  if (
    !(
      observedStateHash === null ||
      (typeof observedStateHash === "string" && SHA256_PATTERN.test(observedStateHash))
    )
  ) {
    fail(
      "EFFECT_RECEIPT_INVALID",
      "EffectReceipt.observed_state_hash must be a canonical SHA-256 digest or null",
    );
  }
  const reconciliationRequired = readDataProperty(receipt, "reconciliation_required");
  if (typeof reconciliationRequired !== "boolean") {
    fail("EFFECT_RECEIPT_INVALID", "EffectReceipt.reconciliation_required must be boolean");
  }
  if (reconciliationRequired !== (status === "UNKNOWN")) {
    fail(
      "EFFECT_RECEIPT_RECONCILIATION_MISMATCH",
      "EffectReceipt.reconciliation_required must be true exactly for UNKNOWN",
    );
  }
  const startedAt = requireTimestamp(
    readDataProperty(receipt, "started_at"),
    "EffectReceipt.started_at",
    "EFFECT_RECEIPT_INVALID",
  );
  const finishedAt = requireTimestamp(
    readDataProperty(receipt, "finished_at"),
    "EffectReceipt.finished_at",
    "EFFECT_RECEIPT_INVALID",
  );
  if (compareRfc3339(finishedAt, startedAt) < 0) {
    fail("EFFECT_RECEIPT_INVALID", "EffectReceipt.finished_at precedes started_at");
  }
  const normalized = {
    receipt_id: requireNonEmptyString(
      readDataProperty(receipt, "receipt_id"),
      "EffectReceipt.receipt_id",
      "EFFECT_RECEIPT_INVALID",
    ),
    intent_id: requireNonEmptyString(
      readDataProperty(receipt, "intent_id"),
      "EffectReceipt.intent_id",
      "EFFECT_RECEIPT_INVALID",
    ),
    run_id: requireNonEmptyString(
      readDataProperty(receipt, "run_id"),
      "EffectReceipt.run_id",
      "EFFECT_RECEIPT_INVALID",
    ),
    external_operation_id: requireNullableString(
      readDataProperty(receipt, "external_operation_id"),
      "EffectReceipt.external_operation_id",
      "EFFECT_RECEIPT_INVALID",
    ),
    status,
    result_artifact_ids: requireStringArray(
      readDataProperty(receipt, "result_artifact_ids"),
      "EffectReceipt.result_artifact_ids",
      { code: "EFFECT_RECEIPT_INVALID" },
    ),
    error_artifact_ids: requireStringArray(
      readDataProperty(receipt, "error_artifact_ids"),
      "EffectReceipt.error_artifact_ids",
      { code: "EFFECT_RECEIPT_INVALID" },
    ),
    observed_state_hash: observedStateHash,
    idempotency_key: requireNonEmptyString(
      readDataProperty(receipt, "idempotency_key"),
      "EffectReceipt.idempotency_key",
      "EFFECT_RECEIPT_INVALID",
    ),
    started_at: startedAt,
    finished_at: finishedAt,
    reconciliation_required: reconciliationRequired,
  };
  const hasObservedEvidence =
    normalized.observed_state_hash !== null ||
    normalized.result_artifact_ids.length > 0 ||
    normalized.error_artifact_ids.length > 0;
  if (RESOLVING_STATUSES.has(status) && !hasObservedEvidence) {
    fail(
      "EFFECT_RECEIPT_RESOLUTION_EVIDENCE_REQUIRED",
      "a resolving EffectReceipt must bind an artifact or observed state hash",
    );
  }
  if (
    status === "SUCCEEDED" &&
    normalized.observed_state_hash === null &&
    normalized.result_artifact_ids.length === 0
  ) {
    fail(
      "EFFECT_RECEIPT_SUCCESS_EVIDENCE_REQUIRED",
      "SUCCEEDED must bind a result artifact or observed state hash",
    );
  }
  if (!sealed) return canonicalClone(normalized);
  const receiptHash = readDataProperty(receipt, "receipt_hash");
  if (typeof receiptHash !== "string" || !SHA256_PATTERN.test(receiptHash)) {
    fail("EFFECT_RECEIPT_INVALID", "EffectReceipt.receipt_hash is not canonical");
  }
  const complete = { ...normalized, receipt_hash: receiptHash };
  const expected = computeEffectReceiptHash(complete);
  if (receiptHash !== expected) {
    fail(
      "EFFECT_RECEIPT_HASH_MISMATCH",
      "EffectReceipt.receipt_hash does not match canonical fields",
      { actual: receiptHash, expected, receiptId: normalized.receipt_id },
    );
  }
  return canonicalClone(complete);
};

export const sealEffectReceipt = (input) => {
  const normalized = normalizeEffectReceipt(input, { sealed: false });
  return canonicalClone({ ...normalized, receipt_hash: computeEffectReceiptHash(normalized) });
};

const normalizeAttemptInput = (candidate) => {
  const attempt = requirePlainDataObject(candidate, "attempt", {
    allowedKeys: ATTEMPT_INPUT_KEYS,
  });
  return OBJECT_FREEZE({
    attempt_id: requireNonEmptyString(readDataProperty(attempt, "attempt_id"), "attempt.attempt_id"),
    intent_id: requireNonEmptyString(readDataProperty(attempt, "intent_id"), "attempt.intent_id"),
    started_at: requireTimestamp(readDataProperty(attempt, "started_at"), "attempt.started_at"),
  });
};

const validateAttemptRecord = (candidate) => {
  const attempt = requirePlainDataObject(candidate, "Attempt", {
    allowedKeys: ATTEMPT_KEYS,
    code: "ATTEMPT_RECORD_INVALID",
  });
  const number = readDataProperty(attempt, "attempt_number");
  if (!NUMBER_IS_SAFE_INTEGER(number) || number < 1) {
    fail("ATTEMPT_RECORD_INVALID", "Attempt.attempt_number must be a positive safe integer");
  }
  const intentHash = readDataProperty(attempt, "intent_hash");
  const attemptHash = readDataProperty(attempt, "attempt_hash");
  if (typeof intentHash !== "string" || !SHA256_PATTERN.test(intentHash)) {
    fail("ATTEMPT_RECORD_INVALID", "Attempt.intent_hash is not canonical");
  }
  if (typeof attemptHash !== "string" || !SHA256_PATTERN.test(attemptHash)) {
    fail("ATTEMPT_RECORD_INVALID", "Attempt.attempt_hash is not canonical");
  }
  const normalized = {
    attempt_id: requireNonEmptyString(
      readDataProperty(attempt, "attempt_id"),
      "Attempt.attempt_id",
      "ATTEMPT_RECORD_INVALID",
    ),
    attempt_number: number,
    intent_id: requireNonEmptyString(
      readDataProperty(attempt, "intent_id"),
      "Attempt.intent_id",
      "ATTEMPT_RECORD_INVALID",
    ),
    intent_hash: intentHash,
    run_id: requireNonEmptyString(
      readDataProperty(attempt, "run_id"),
      "Attempt.run_id",
      "ATTEMPT_RECORD_INVALID",
    ),
    idempotency_key: requireNonEmptyString(
      readDataProperty(attempt, "idempotency_key"),
      "Attempt.idempotency_key",
      "ATTEMPT_RECORD_INVALID",
    ),
    started_at: requireTimestamp(
      readDataProperty(attempt, "started_at"),
      "Attempt.started_at",
      "ATTEMPT_RECORD_INVALID",
    ),
    attempt_hash: attemptHash,
  };
  const expected = computeAttemptHash(normalized);
  if (attemptHash !== expected) {
    fail("ATTEMPT_HASH_MISMATCH", "Attempt.attempt_hash does not match canonical fields", {
      actual: attemptHash,
      attemptId: normalized.attempt_id,
      expected,
    });
  }
  return canonicalClone(normalized);
};

const buildAttempt = (intent, input, number) => {
  const withoutHash = {
    attempt_id: input.attempt_id,
    attempt_number: number,
    intent_id: intent.intent_id,
    intent_hash: intent.intent_hash,
    run_id: intent.run_id,
    idempotency_key: intent.idempotency_key,
    started_at: input.started_at,
  };
  return validateAttemptRecord({ ...withoutHash, attempt_hash: computeAttemptHash(withoutHash) });
};

const idempotencyRecordId = (key) => sha256Text(`effect-idempotency\u0000${key}`);

const validateIdempotencyRecord = (candidate) => {
  const record = requirePlainDataObject(candidate, "idempotency record", {
    allowedKeys: IDEMPOTENCY_KEYS,
    code: "EFFECT_RECORD_INTEGRITY_FAILED",
  });
  const intentHash = readDataProperty(record, "intent_hash");
  if (typeof intentHash !== "string" || !SHA256_PATTERN.test(intentHash)) {
    fail("EFFECT_RECORD_INTEGRITY_FAILED", "idempotency record intent_hash is invalid");
  }
  return OBJECT_FREEZE({
    idempotency_key: requireNonEmptyString(
      readDataProperty(record, "idempotency_key"),
      "idempotency record.idempotency_key",
      "EFFECT_RECORD_INTEGRITY_FAILED",
    ),
    intent_id: requireNonEmptyString(
      readDataProperty(record, "intent_id"),
      "idempotency record.intent_id",
      "EFFECT_RECORD_INTEGRITY_FAILED",
    ),
    intent_hash: intentHash,
  });
};

const validateJournalEntry = (candidate, index) => {
  const provisional = requirePlainDataObject(candidate, `operation.journal[${index}]`, {
    allowedKeys: [...ATTEMPT_ENTRY_KEYS, ...RECEIPT_ENTRY_KEYS],
    requiredKeys: ["kind"],
    code: "EFFECT_RECORD_INTEGRITY_FAILED",
  });
  const kind = readDataProperty(provisional, "kind");
  if (kind === "ATTEMPT") {
    const entry = requirePlainDataObject(candidate, `operation.journal[${index}]`, {
      allowedKeys: ATTEMPT_ENTRY_KEYS,
      code: "EFFECT_RECORD_INTEGRITY_FAILED",
    });
    return OBJECT_FREEZE({
      kind,
      attempt_id: requireNonEmptyString(
        readDataProperty(entry, "attempt_id"),
        `operation.journal[${index}].attempt_id`,
        "EFFECT_RECORD_INTEGRITY_FAILED",
      ),
    });
  }
  if (kind === "RECEIPT") {
    const entry = requirePlainDataObject(candidate, `operation.journal[${index}]`, {
      allowedKeys: RECEIPT_ENTRY_KEYS,
      code: "EFFECT_RECORD_INTEGRITY_FAILED",
    });
    const mode = readDataProperty(entry, "mode");
    if (!RECEIPT_MODES.has(mode)) {
      fail("EFFECT_RECORD_INTEGRITY_FAILED", "operation receipt mode is invalid");
    }
    return OBJECT_FREEZE({
      kind,
      attempt_id: requireNonEmptyString(
        readDataProperty(entry, "attempt_id"),
        `operation.journal[${index}].attempt_id`,
        "EFFECT_RECORD_INTEGRITY_FAILED",
      ),
      receipt_id: requireNonEmptyString(
        readDataProperty(entry, "receipt_id"),
        `operation.journal[${index}].receipt_id`,
        "EFFECT_RECORD_INTEGRITY_FAILED",
      ),
      mode,
    });
  }
  fail("EFFECT_RECORD_INTEGRITY_FAILED", "operation journal kind is invalid");
};

const validateOperationRecord = (candidate) => {
  const operation = requirePlainDataObject(candidate, "operation", {
    allowedKeys: OPERATION_KEYS,
    code: "EFFECT_RECORD_INTEGRITY_FAILED",
  });
  if (readDataProperty(operation, "schema_version") !== OPERATION_SCHEMA_VERSION) {
    fail("EFFECT_RECORD_INTEGRITY_FAILED", "operation schema version is unsupported");
  }
  const intentHash = readDataProperty(operation, "intent_hash");
  if (typeof intentHash !== "string" || !SHA256_PATTERN.test(intentHash)) {
    fail("EFFECT_RECORD_INTEGRITY_FAILED", "operation intent_hash is invalid");
  }
  const journal = readDenseArray(
    readDataProperty(operation, "journal"),
    "operation.journal",
    "EFFECT_RECORD_INTEGRITY_FAILED",
  ).map(validateJournalEntry);
  return canonicalClone({
    schema_version: OPERATION_SCHEMA_VERSION,
    intent_id: requireNonEmptyString(
      readDataProperty(operation, "intent_id"),
      "operation.intent_id",
      "EFFECT_RECORD_INTEGRITY_FAILED",
    ),
    intent_hash: intentHash,
    run_id: requireNonEmptyString(
      readDataProperty(operation, "run_id"),
      "operation.run_id",
      "EFFECT_RECORD_INTEGRITY_FAILED",
    ),
    idempotency_key: requireNonEmptyString(
      readDataProperty(operation, "idempotency_key"),
      "operation.idempotency_key",
      "EFFECT_RECORD_INTEGRITY_FAILED",
    ),
    journal,
  });
};

const validatePublicationRecord = (candidate, revision) => {
  const publication = requirePlainDataObject(candidate, "publication checkpoint", {
    allowedKeys: PUBLICATION_KEYS,
    code: "EFFECT_RECORD_INTEGRITY_FAILED",
  });
  if (readDataProperty(publication, "schema_version") !== OPERATION_SCHEMA_VERSION) {
    fail("EFFECT_RECORD_INTEGRITY_FAILED", "publication schema version is unsupported");
  }
  const intentHash = readDataProperty(publication, "intent_hash");
  if (typeof intentHash !== "string" || !SHA256_PATTERN.test(intentHash)) {
    fail("EFFECT_RECORD_INTEGRITY_FAILED", "publication intent_hash is invalid");
  }
  const count = readDataProperty(publication, "published_event_count");
  if (!NUMBER_IS_SAFE_INTEGER(count) || count < 0 || count !== revision) {
    fail(
      "EFFECT_RECORD_INTEGRITY_FAILED",
      "publication count must be a non-negative safe integer equal to its revision",
      { count, revision },
    );
  }
  return OBJECT_FREEZE({
    schema_version: OPERATION_SCHEMA_VERSION,
    intent_id: requireNonEmptyString(
      readDataProperty(publication, "intent_id"),
      "publication.intent_id",
      "EFFECT_RECORD_INTEGRITY_FAILED",
    ),
    intent_hash: intentHash,
    run_id: requireNonEmptyString(
      readDataProperty(publication, "run_id"),
      "publication.run_id",
      "EFFECT_RECORD_INTEGRITY_FAILED",
    ),
    published_event_count: count,
  });
};

const assertImmutableRecord = (record, type, id, label) => {
  if (record === null) fail("EFFECT_RECORD_MISSING", `${label} is missing`, { id, type });
  if (record.recordType !== type || record.recordId !== id) {
    fail("EFFECT_RECORD_INTEGRITY_FAILED", `${label} storage identity is inconsistent`, {
      id,
      type,
    });
  }
  if (record.revision !== 0) {
    fail("EFFECT_RECORD_MUTATED", `${label} must remain at immutable revision zero`, {
      id,
      revision: record.revision,
      type,
    });
  }
  return record.value;
};

const sameCanonicalRecord = (left, right) => canonicalEffectJson(left) === canonicalEffectJson(right);

const assertIntentBinding = (record, intent, label) => {
  if (
    record.intent_id !== intent.intent_id ||
    record.run_id !== intent.run_id ||
    record.idempotency_key !== intent.idempotency_key
  ) {
    fail("EFFECT_RECORD_INTEGRITY_FAILED", `${label} is bound to a different intent`);
  }
};

const loadSnapshot = (store, intentId) => {
  const intentRecord = store.readRevisionedRecord(EFFECT_RECORD_TYPES.ACTION_INTENT, intentId);
  const intent = normalizeActionIntent(
    assertImmutableRecord(
      intentRecord,
      EFFECT_RECORD_TYPES.ACTION_INTENT,
      intentId,
      "ActionIntent",
    ),
  );
  const operationRecord = store.readRevisionedRecord(EFFECT_RECORD_TYPES.OPERATION, intentId);
  if (operationRecord === null) {
    fail("EFFECT_RECORD_MISSING", "operation record is missing", { intentId });
  }
  if (
    operationRecord.recordType !== EFFECT_RECORD_TYPES.OPERATION ||
    operationRecord.recordId !== intentId
  ) {
    fail("EFFECT_RECORD_INTEGRITY_FAILED", "operation storage identity is inconsistent");
  }
  const operation = validateOperationRecord(operationRecord.value);
  if (operationRecord.revision !== operation.journal.length) {
    fail(
      "EFFECT_RECORD_INTEGRITY_FAILED",
      "operation revision does not reconcile with its append-only journal",
      { intentId, journalLength: operation.journal.length, revision: operationRecord.revision },
    );
  }
  if (
    operation.intent_id !== intent.intent_id ||
    operation.intent_hash !== intent.intent_hash ||
    operation.run_id !== intent.run_id ||
    operation.idempotency_key !== intent.idempotency_key
  ) {
    fail("EFFECT_RECORD_INTEGRITY_FAILED", "operation is not bound to its ActionIntent");
  }
  const publicationRecord = store.readRevisionedRecord(
    EFFECT_RECORD_TYPES.PUBLICATION,
    intentId,
  );
  if (publicationRecord === null) {
    fail("EFFECT_RECORD_MISSING", "publication checkpoint is missing", { intentId });
  }
  if (
    publicationRecord.recordType !== EFFECT_RECORD_TYPES.PUBLICATION ||
    publicationRecord.recordId !== intentId
  ) {
    fail("EFFECT_RECORD_INTEGRITY_FAILED", "publication storage identity is inconsistent");
  }
  const publication = validatePublicationRecord(
    publicationRecord.value,
    publicationRecord.revision,
  );
  if (
    publication.intent_id !== intent.intent_id ||
    publication.intent_hash !== intent.intent_hash ||
    publication.run_id !== intent.run_id
  ) {
    fail("EFFECT_RECORD_INTEGRITY_FAILED", "publication checkpoint is not bound to ActionIntent");
  }
  const idempotencyId = idempotencyRecordId(intent.idempotency_key);
  const idempotencyRecord = store.readRevisionedRecord(
    EFFECT_RECORD_TYPES.IDEMPOTENCY,
    idempotencyId,
  );
  const idempotency = validateIdempotencyRecord(
    assertImmutableRecord(
      idempotencyRecord,
      EFFECT_RECORD_TYPES.IDEMPOTENCY,
      idempotencyId,
      "idempotency record",
    ),
  );
  if (
    idempotency.idempotency_key !== intent.idempotency_key ||
    idempotency.intent_id !== intent.intent_id ||
    idempotency.intent_hash !== intent.intent_hash
  ) {
    fail("EFFECT_RECORD_INTEGRITY_FAILED", "idempotency record does not resolve ActionIntent");
  }

  const attempts = [];
  const receipts = [];
  const receiptEntries = [];
  const attemptIds = new Set();
  const receiptIds = new Set();
  let currentAttempt = null;
  let currentReceipts = [];
  let lastFinishedAt = null;

  for (let index = 0; index < operation.journal.length; index += 1) {
    const entry = operation.journal[index];
    if (entry.kind === "ATTEMPT") {
      if (attemptIds.has(entry.attempt_id)) {
        fail("EFFECT_RECORD_INTEGRITY_FAILED", "operation contains a duplicate attempt ID");
      }
      if (currentAttempt !== null) {
        const latest = currentReceipts[currentReceipts.length - 1];
        if (latest === undefined || latest.status === "UNKNOWN") {
          fail(
            "EFFECT_RECORD_INTEGRITY_FAILED",
            "operation starts a retry before the prior attempt is reconciled",
          );
        }
        if (latest.status === "SUCCEEDED") {
          fail("EFFECT_RECORD_INTEGRITY_FAILED", "operation retries after a successful effect");
        }
      }
      const stored = store.readRevisionedRecord(EFFECT_RECORD_TYPES.ATTEMPT, entry.attempt_id);
      const attempt = validateAttemptRecord(
        assertImmutableRecord(
          stored,
          EFFECT_RECORD_TYPES.ATTEMPT,
          entry.attempt_id,
          "Attempt",
        ),
      );
      assertIntentBinding(attempt, intent, "Attempt");
      if (
        attempt.intent_hash !== intent.intent_hash ||
        attempt.attempt_number !== attempts.length + 1
      ) {
        fail("EFFECT_RECORD_INTEGRITY_FAILED", "Attempt lineage does not reconcile");
      }
      const earliestStart =
        currentAttempt === null
          ? intent.created_at
          : currentReceipts[currentReceipts.length - 1].finished_at;
      if (compareRfc3339(attempt.started_at, earliestStart) < 0) {
        fail(
          "EFFECT_RECORD_INTEGRITY_FAILED",
          "Attempt chronology precedes its intent or the prior resolved receipt",
        );
      }
      attempts.push(attempt);
      attemptIds.add(attempt.attempt_id);
      currentAttempt = attempt;
      currentReceipts = [];
      lastFinishedAt = null;
      continue;
    }

    if (currentAttempt === null || entry.attempt_id !== currentAttempt.attempt_id) {
      fail("EFFECT_RECORD_INTEGRITY_FAILED", "receipt is not bound to the current Attempt");
    }
    if (receiptIds.has(entry.receipt_id)) {
      fail("EFFECT_RECORD_INTEGRITY_FAILED", "operation contains a duplicate receipt ID");
    }
    if (currentReceipts.length === 0) {
      if (!RECEIPT_MODES.has(entry.mode)) {
        fail("EFFECT_RECORD_INTEGRITY_FAILED", "first receipt has an invalid mode");
      }
    } else {
      const prior = currentReceipts[currentReceipts.length - 1];
      if (prior.status !== "UNKNOWN" || entry.mode !== "RECONCILIATION") {
        fail(
          "EFFECT_RECORD_INTEGRITY_FAILED",
          "only an UNKNOWN receipt may be followed by a reconciliation receipt",
        );
      }
    }
    const stored = store.readRevisionedRecord(
      EFFECT_RECORD_TYPES.EFFECT_RECEIPT,
      entry.receipt_id,
    );
    const receipt = normalizeEffectReceipt(
      assertImmutableRecord(
        stored,
        EFFECT_RECORD_TYPES.EFFECT_RECEIPT,
        entry.receipt_id,
        "EffectReceipt",
      ),
    );
    assertIntentBinding(receipt, intent, "EffectReceipt");
    if (receipt.started_at !== currentAttempt.started_at) {
      fail("EFFECT_RECORD_INTEGRITY_FAILED", "EffectReceipt.started_at differs from Attempt");
    }
    if (lastFinishedAt !== null && compareRfc3339(receipt.finished_at, lastFinishedAt) < 0) {
      fail("EFFECT_RECORD_INTEGRITY_FAILED", "receipt chronology moves backwards");
    }
    const priorReceipt = currentReceipts[currentReceipts.length - 1];
    if (
      priorReceipt?.external_operation_id !== null &&
      priorReceipt?.external_operation_id !== undefined &&
      receipt.external_operation_id !== priorReceipt.external_operation_id
    ) {
      fail(
        "EFFECT_RECORD_INTEGRITY_FAILED",
        "reconciliation changed the observed external operation identity",
      );
    }
    receipts.push(receipt);
    receiptEntries.push(entry);
    receiptIds.add(receipt.receipt_id);
    currentReceipts.push(receipt);
    lastFinishedAt = receipt.finished_at;
  }

  return OBJECT_FREEZE({
    attempts: OBJECT_FREEZE(attempts),
    idempotency,
    intent,
    operation,
    operationRecord,
    publication,
    publicationRecord,
    receiptEntries: OBJECT_FREEZE(receiptEntries),
    receipts: OBJECT_FREEZE(receipts),
  });
};

const operationTail = (snapshot) => {
  const attempt = snapshot.attempts.at(-1) ?? null;
  if (attempt === null) return OBJECT_FREEZE({ attempt: null, receipt: null });
  let receipt = null;
  for (let index = snapshot.operation.journal.length - 1; index >= 0; index -= 1) {
    const entry = snapshot.operation.journal[index];
    if (entry.kind === "RECEIPT" && entry.attempt_id === attempt.attempt_id) {
      receipt = snapshot.receipts.find((candidate) => candidate.receipt_id === entry.receipt_id);
      break;
    }
  }
  return OBJECT_FREEZE({ attempt, receipt: receipt ?? null });
};

const appendJournalEntry = (store, snapshot, entry) => {
  const requiredPublishedCount = snapshot.operation.journal.length + 1;
  if (snapshot.publication.published_event_count !== requiredPublishedCount) {
    fail(
      "EFFECT_EVENT_RECONCILIATION_REQUIRED",
      "all prior effect records must have confirmed ledger events before another mutation",
      {
        confirmed: snapshot.publication.published_event_count,
        intentId: snapshot.intent.intent_id,
        required: requiredPublishedCount,
      },
    );
  }
  const next = {
    ...snapshot.operation,
    journal: [...snapshot.operation.journal, entry],
  };
  const update = store.compareAndSwapRevision({
    recordType: EFFECT_RECORD_TYPES.OPERATION,
    recordId: snapshot.intent.intent_id,
    expectedRevision: snapshot.operationRecord.revision,
    value: next,
  });
  if (!update.ok) {
    fail("EFFECT_OPERATION_COMMIT_FAILED", "operation journal CAS did not commit", {
      intentId: snapshot.intent.intent_id,
      status: update.status,
    });
  }
};

const recordIdentity = (kind, id) =>
  createHash("sha256").update(`${kind}\u0000${id}`, "utf8").digest("hex");

const publicationDescriptor = (kind, record) => {
  let recordId;
  let eventType;
  let occurredAt;
  if (kind === "ACTION_INTENT") {
    recordId = record.intent_id;
    eventType = EFFECT_EVENT_TYPES.ACTION_INTENT;
    occurredAt = record.created_at;
  } else if (kind === "ATTEMPT") {
    recordId = record.attempt_id;
    eventType = EFFECT_EVENT_TYPES.ATTEMPT;
    occurredAt = record.started_at;
  } else if (kind === "EFFECT_RECEIPT") {
    recordId = record.receipt_id;
    eventType = EFFECT_EVENT_TYPES.EFFECT_RECEIPT;
    occurredAt = record.finished_at;
  } else {
    fail("EFFECT_RECORD_INTEGRITY_FAILED", "unknown publication kind");
  }
  const token = recordIdentity(kind, recordId).slice(0, 40);
  return OBJECT_FREEZE({
    artifactId: `ART-E02-${token}`,
    artifactReceiptId: `AR-E02-${token}`,
    eventId: `EVT-E02-${token}`,
    eventType,
    occurredAt,
    recordId,
  });
};

const artifactMetadata = (descriptor, intentId) => ({
  artifact: {
    artifactId: descriptor.artifactId,
    artifactType: "event_payload",
    confidentiality: "internal",
    createdAt: descriptor.occurredAt,
    createdBy: EVENT_ACTOR_ID,
    encryption: { atRest: true, inTransit: true, keyRef: "local://e02-effect-ledger" },
    inputArtifactIds: [],
    license: null,
    lineageEventIds: [],
    mediaType: "application/json",
    provenanceManifestId: "PROV-E02-effect-coordinator",
    retentionClass: "project",
  },
  receipt: {
    actionIntentId: intentId,
    createdAt: descriptor.occurredAt,
    createdBy: { actorId: EVENT_ACTOR_ID, actorType: "service" },
    receiptId: descriptor.artifactReceiptId,
    schemaRef: null,
    validationResults: [
      {
        check: "effect_event_payload",
        status: "PASS",
        details: "deterministic E02 canonical event payload",
      },
    ],
  },
});

const publishRecord = (dependencies, kind, record) => {
  const descriptor = publicationDescriptor(kind, record);
  const bytes = Buffer.from(canonicalEffectJson(record), "utf8");
  try {
    dependencies.artifactStore.putArtifact(
      bytes,
      artifactMetadata(descriptor, record.intent_id),
    );
    const result = dependencies.ledger.append({
      event_id: descriptor.eventId,
      run_id: record.run_id,
      event_type: descriptor.eventType,
      aggregate_type: "effect",
      aggregate_id: record.intent_id,
      actor_id: EVENT_ACTOR_ID,
      payload_artifact_id: descriptor.artifactId,
      occurred_at: descriptor.occurredAt,
      schema_version: EVENT_SCHEMA_VERSION,
    });
    return OBJECT_FREEZE({ descriptor, event: result.event, status: result.status });
  } catch (error) {
    fail(
      "EFFECT_EVENT_PUBLICATION_FAILED",
      "effect record is durable but its resolving ledger event is not confirmed",
      {
        causeCode: dependencyCauseCode(error),
        eventId: descriptor.eventId,
        kind,
        recordId: descriptor.recordId,
      },
      { cause: error },
    );
  }
};

const expectedPublications = (snapshot) => {
  const expected = [
    OBJECT_FREEZE({
      descriptor: publicationDescriptor("ACTION_INTENT", snapshot.intent),
      kind: "ACTION_INTENT",
      record: snapshot.intent,
    }),
  ];
  const attempts = new Map(snapshot.attempts.map((attempt) => [attempt.attempt_id, attempt]));
  const receipts = new Map(snapshot.receipts.map((receipt) => [receipt.receipt_id, receipt]));
  for (let index = 0; index < snapshot.operation.journal.length; index += 1) {
    const entry = snapshot.operation.journal[index];
    const kind = entry.kind === "ATTEMPT" ? "ATTEMPT" : "EFFECT_RECEIPT";
    const record = entry.kind === "ATTEMPT"
      ? attempts.get(entry.attempt_id)
      : receipts.get(entry.receipt_id);
    expected.push(
      OBJECT_FREEZE({ descriptor: publicationDescriptor(kind, record), kind, record }),
    );
  }
  return OBJECT_FREEZE(expected);
};

const confirmPublication = (dependencies, kind, record) =>
  dependencies.stateStore.transaction((store) => {
    const snapshot = loadSnapshot(store, record.intent_id);
    const expected = expectedPublications(snapshot);
    const descriptor = publicationDescriptor(kind, record);
    const index = expected.findIndex(
      (entry) => entry.descriptor.eventId === descriptor.eventId,
    );
    if (index < 0 || !sameCanonicalRecord(expected[index].record, record)) {
      fail(
        "EFFECT_EVENT_RECONCILIATION_FAILED",
        "published record is not present at its canonical operation position",
        { kind, recordId: descriptor.recordId },
      );
    }
    const targetCount = index + 1;
    const current = snapshot.publication.published_event_count;
    if (current >= targetCount) return OBJECT_FREEZE({ status: "EXISTING", targetCount });
    if (current !== targetCount - 1) {
      fail(
        "EFFECT_EVENT_RECONCILIATION_FAILED",
        "publication confirmation cannot skip or reorder effect events",
        { current, intentId: record.intent_id, targetCount },
      );
    }
    const update = store.compareAndSwapRevision({
      recordType: EFFECT_RECORD_TYPES.PUBLICATION,
      recordId: record.intent_id,
      expectedRevision: snapshot.publicationRecord.revision,
      value: {
        ...snapshot.publication,
        published_event_count: targetCount,
      },
    });
    if (!update.ok) {
      fail("EFFECT_EVENT_CONFIRMATION_FAILED", "publication checkpoint CAS did not commit", {
        intentId: record.intent_id,
        status: update.status,
      });
    }
    return OBJECT_FREEZE({ status: "CONFIRMED", targetCount });
  });

const publishAndConfirmRecord = (dependencies, kind, record) => {
  const publication = publishRecord(dependencies, kind, record);
  let confirmation;
  try {
    confirmation = confirmPublication(dependencies, kind, record);
  } catch (error) {
    if (error instanceof EffectCoordinatorError) throw error;
    fail(
      "EFFECT_EVENT_CONFIRMATION_FAILED",
      "ledger event exists but its durable publication checkpoint is not confirmed",
      {
        causeCode: dependencyCauseCode(error),
        eventId: publication.descriptor.eventId,
        kind,
        recordId: publication.descriptor.recordId,
      },
      { cause: error },
    );
  }
  return OBJECT_FREEZE({ publication, confirmation });
};

const inspectPublications = (dependencies, snapshot) => {
  dependencies.ledger.verifyRun(snapshot.intent.run_id);
  const events = dependencies.ledger.readEvents(snapshot.intent.run_id);
  const knownTypes = new Set(Object.values(EFFECT_EVENT_TYPES));
  const relevant = events.filter(
    (event) =>
      event.aggregate_type === "effect" &&
      event.aggregate_id === snapshot.intent.intent_id &&
      knownTypes.has(event.event_type),
  );
  const expected = expectedPublications(snapshot);
  if (snapshot.publication.published_event_count > expected.length) {
    fail(
      "EFFECT_RECORD_INTEGRITY_FAILED",
      "publication checkpoint exceeds the durable effect journal",
      {
        confirmed: snapshot.publication.published_event_count,
        expected: expected.length,
        intentId: snapshot.intent.intent_id,
      },
    );
  }
  const expectedIds = new Set(expected.map((entry) => entry.descriptor.eventId));
  const unexpected = relevant.filter((event) => !expectedIds.has(event.event_id));
  if (unexpected.length !== 0) {
    fail("EFFECT_EVENT_RECONCILIATION_FAILED", "ledger contains an unexpected effect event", {
      eventIds: unexpected.map((event) => event.event_id),
      intentId: snapshot.intent.intent_id,
    });
  }
  const relevantById = new Map(relevant.map((event) => [event.event_id, event]));
  const missing = [];
  let previousSequence = 0;
  for (let index = 0; index < expected.length; index += 1) {
    const item = expected[index];
    const descriptor = item.descriptor;
    const event = relevantById.get(descriptor.eventId);
    if (event === undefined) {
      missing.push(descriptor.eventId);
      continue;
    }
    if (
      event.run_id !== snapshot.intent.run_id ||
      event.event_type !== descriptor.eventType ||
      event.actor_id !== EVENT_ACTOR_ID ||
      event.payload_artifact_id !== descriptor.artifactId ||
      event.occurred_at !== descriptor.occurredAt ||
      event.sequence <= previousSequence
    ) {
      fail("EFFECT_EVENT_RECONCILIATION_FAILED", "effect event differs from its durable record", {
        eventId: event.event_id,
        intentId: snapshot.intent.intent_id,
      });
    }
    previousSequence = event.sequence;
    let payload;
    try {
      payload = dependencies.artifactStore.readArtifact(descriptor.artifactId);
    } catch (error) {
      fail(
        "EFFECT_EVENT_RECONCILIATION_FAILED",
        "effect event payload cannot be integrity-verified",
        { causeCode: dependencyCauseCode(error), eventId: event.event_id },
        { cause: error },
      );
    }
    const expectedBytes = Buffer.from(canonicalEffectJson(item.record), "utf8");
    if (!BUFFER_IS_BUFFER(payload) && !(payload instanceof Uint8Array)) {
      fail("EFFECT_EVENT_RECONCILIATION_FAILED", "effect event payload is not bytes");
    }
    if (!Buffer.from(payload).equals(expectedBytes)) {
      fail("EFFECT_EVENT_RECONCILIATION_FAILED", "effect event payload differs from durable record", {
        eventId: event.event_id,
      });
    }
  }
  for (let index = 0; index < snapshot.publication.published_event_count; index += 1) {
    const confirmedId = expected[index].descriptor.eventId;
    if (!relevantById.has(confirmedId)) {
      fail(
        "EFFECT_EVENT_RECONCILIATION_FAILED",
        "publication checkpoint claims a ledger event that is not present",
        { eventId: confirmedId, intentId: snapshot.intent.intent_id },
      );
    }
  }
  const orderedRelevantIds = relevant.map((event) => event.event_id);
  const presentExpectedIds = expected
    .map((entry) => entry.descriptor.eventId)
    .filter((eventId) => relevantById.has(eventId));
  if (canonicalEffectJson(orderedRelevantIds) !== canonicalEffectJson(presentExpectedIds)) {
    fail("EFFECT_EVENT_RECONCILIATION_FAILED", "effect ledger event order is inconsistent");
  }
  return OBJECT_FREEZE({
    event_count: relevant.length,
    expected_event_count: expected.length,
    missing_event_ids: OBJECT_FREEZE(missing),
    publication_confirmation_required:
      snapshot.publication.published_event_count !== expected.length,
    reconciled: missing.length === 0,
  });
};

const verifyArguments = (artifactStore, intent) => {
  let bytes;
  try {
    bytes = artifactStore.readArtifact(intent.arguments_artifact_id);
  } catch (error) {
    fail(
      "ACTION_ARGUMENTS_RESOLUTION_FAILED",
      "ActionIntent arguments artifact cannot be resolved",
      {
        artifactId: intent.arguments_artifact_id,
        causeCode: dependencyCauseCode(error),
      },
      { cause: error },
    );
  }
  if (IS_PROXY(bytes) || !(BUFFER_IS_BUFFER(bytes) || bytes instanceof Uint8Array)) {
    fail("ACTION_ARGUMENTS_RESOLUTION_FAILED", "arguments artifact did not resolve to bytes");
  }
  const actual = sha256Bytes(Buffer.from(bytes));
  if (actual !== intent.arguments_hash) {
    fail("ACTION_ARGUMENTS_HASH_MISMATCH", "arguments artifact differs from ActionIntent", {
      actual,
      artifactId: intent.arguments_artifact_id,
      expected: intent.arguments_hash,
    });
  }
};

const verifyReceiptArtifacts = (artifactStore, receipt) => {
  const ids = [...receipt.result_artifact_ids, ...receipt.error_artifact_ids];
  for (let index = 0; index < ids.length; index += 1) {
    try {
      const bytes = artifactStore.readArtifact(ids[index]);
      if (IS_PROXY(bytes) || !(BUFFER_IS_BUFFER(bytes) || bytes instanceof Uint8Array)) {
        fail("EFFECT_ARTIFACT_RESOLUTION_FAILED", "receipt artifact did not resolve to bytes", {
          artifactId: ids[index],
        });
      }
    } catch (error) {
      if (error instanceof EffectCoordinatorError) throw error;
      fail(
        "EFFECT_ARTIFACT_RESOLUTION_FAILED",
        "EffectReceipt references an unavailable or corrupt artifact",
        { artifactId: ids[index], causeCode: dependencyCauseCode(error) },
        { cause: error },
      );
    }
  }
};

const validateDependencies = (options) => {
  const object = requirePlainDataObject(options, "effect coordinator options", {
    allowedKeys: ["artifactStore", "ledger", "stateStore"],
  });
  const artifactStore = readDataProperty(object, "artifactStore");
  const ledger = readDataProperty(object, "ledger");
  const stateStore = readDataProperty(object, "stateStore");
  if (
    artifactStore === null ||
    (typeof artifactStore !== "object" && typeof artifactStore !== "function") ||
    typeof artifactStore.putArtifact !== "function" ||
    typeof artifactStore.readArtifact !== "function"
  ) {
    fail("INVALID_INPUT", "artifactStore must expose putArtifact() and readArtifact()");
  }
  if (
    ledger === null ||
    (typeof ledger !== "object" && typeof ledger !== "function") ||
    typeof ledger.append !== "function" ||
    typeof ledger.readEvents !== "function" ||
    typeof ledger.verifyRun !== "function"
  ) {
    fail("INVALID_INPUT", "ledger must expose the E01 append/read/verify API");
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
  return OBJECT_FREEZE({ artifactStore, ledger, stateStore });
};

const outcomeFromSnapshot = (snapshot, publication) => {
  const tail = operationTail(snapshot);
  if (!publication.reconciled) {
    return OBJECT_FREEZE({
      attempt: tail.attempt,
      completion_proven: false,
      effect_status: tail.receipt?.status ?? null,
      event_reconciliation_required: true,
      missing_event_ids: publication.missing_event_ids,
      outcome_resolved: false,
      receipt: tail.receipt,
      reconciliation_required: true,
      retry_permitted: false,
      status: "PENDING_EVENT_RECONCILIATION",
    });
  }
  if (publication.publication_confirmation_required) {
    return OBJECT_FREEZE({
      attempt: tail.attempt,
      completion_proven: false,
      effect_status: tail.receipt?.status ?? null,
      event_reconciliation_required: false,
      missing_event_ids: OBJECT_FREEZE([]),
      outcome_resolved: false,
      publication_confirmation_required: true,
      receipt: tail.receipt,
      reconciliation_required: true,
      retry_permitted: false,
      status: "PENDING_EVENT_CONFIRMATION",
    });
  }
  if (tail.attempt === null) {
    return OBJECT_FREEZE({
      attempt: null,
      completion_proven: false,
      effect_status: null,
      event_reconciliation_required: false,
      missing_event_ids: OBJECT_FREEZE([]),
      outcome_resolved: false,
      publication_confirmation_required: false,
      receipt: null,
      reconciliation_required: false,
      retry_permitted: true,
      status: "NOT_STARTED",
    });
  }
  if (tail.receipt === null || tail.receipt.status === "UNKNOWN") {
    return OBJECT_FREEZE({
      attempt: tail.attempt,
      completion_proven: false,
      effect_status: "UNKNOWN",
      event_reconciliation_required: false,
      missing_event_ids: OBJECT_FREEZE([]),
      outcome_resolved: false,
      publication_confirmation_required: false,
      receipt: tail.receipt,
      reconciliation_required: true,
      retry_permitted: false,
      status: "RECONCILING",
    });
  }
  return OBJECT_FREEZE({
    attempt: tail.attempt,
    completion_proven: tail.receipt.status === "SUCCEEDED",
    effect_status: tail.receipt.status,
    event_reconciliation_required: false,
    missing_event_ids: OBJECT_FREEZE([]),
    outcome_resolved: true,
    publication_confirmation_required: false,
    receipt: tail.receipt,
    reconciliation_required: false,
    retry_permitted: tail.receipt.status !== "SUCCEEDED",
    status: tail.receipt.status,
  });
};

const CONSTRUCTOR_TOKEN = Symbol("EffectCoordinator");

export class EffectCoordinator {
  #artifactStore;
  #ledger;
  #stateStore;

  constructor(token, dependencies) {
    if (token !== CONSTRUCTOR_TOKEN) fail("DIRECT_CONSTRUCTION_DENIED", "use createEffectCoordinator()");
    this.#artifactStore = dependencies.artifactStore;
    this.#ledger = dependencies.ledger;
    this.#stateStore = dependencies.stateStore;
  }

  registerIntent(candidate) {
    const intent = normalizeActionIntent(candidate);
    verifyArguments(this.#artifactStore, intent);
    const result = this.#stateStore.transaction((store) => {
      const indexId = idempotencyRecordId(intent.idempotency_key);
      const indexRecord = store.readRevisionedRecord(EFFECT_RECORD_TYPES.IDEMPOTENCY, indexId);
      const intentRecord = store.readRevisionedRecord(
        EFFECT_RECORD_TYPES.ACTION_INTENT,
        intent.intent_id,
      );
      const operationRecord = store.readRevisionedRecord(
        EFFECT_RECORD_TYPES.OPERATION,
        intent.intent_id,
      );

      if (indexRecord !== null) {
        const index = validateIdempotencyRecord(
          assertImmutableRecord(
            indexRecord,
            EFFECT_RECORD_TYPES.IDEMPOTENCY,
            indexId,
            "idempotency record",
          ),
        );
        if (index.idempotency_key !== intent.idempotency_key) {
          fail("EFFECT_RECORD_INTEGRITY_FAILED", "idempotency index hash collision detected");
        }
        if (index.intent_hash !== intent.intent_hash || index.intent_id !== intent.intent_id) {
          fail(
            "IDEMPOTENCY_KEY_REUSED",
            "idempotency key is already bound to a different canonical ActionIntent",
            { existingIntentId: index.intent_id, requestedIntentId: intent.intent_id },
          );
        }
        const existing = normalizeActionIntent(
          assertImmutableRecord(
            intentRecord,
            EFFECT_RECORD_TYPES.ACTION_INTENT,
            intent.intent_id,
            "ActionIntent",
          ),
        );
        if (!sameCanonicalRecord(existing, intent) || operationRecord === null) {
          fail("EFFECT_RECORD_INTEGRITY_FAILED", "idempotency index has incomplete durable state");
        }
        loadSnapshot(store, intent.intent_id);
        return OBJECT_FREEZE({ intent: existing, status: "EXISTING" });
      }

      if (intentRecord !== null || operationRecord !== null) {
        fail("INTENT_ID_CONFLICT", "intent ID already exists without the requested idempotency binding", {
          intentId: intent.intent_id,
        });
      }
      store.createRevisionedRecord({
        recordType: EFFECT_RECORD_TYPES.IDEMPOTENCY,
        recordId: indexId,
        value: {
          idempotency_key: intent.idempotency_key,
          intent_id: intent.intent_id,
          intent_hash: intent.intent_hash,
        },
      });
      store.createRevisionedRecord({
        recordType: EFFECT_RECORD_TYPES.ACTION_INTENT,
        recordId: intent.intent_id,
        value: intent,
      });
      store.createRevisionedRecord({
        recordType: EFFECT_RECORD_TYPES.OPERATION,
        recordId: intent.intent_id,
        value: {
          schema_version: OPERATION_SCHEMA_VERSION,
          intent_id: intent.intent_id,
          intent_hash: intent.intent_hash,
          run_id: intent.run_id,
          idempotency_key: intent.idempotency_key,
          journal: [],
        },
      });
      store.createRevisionedRecord({
        recordType: EFFECT_RECORD_TYPES.PUBLICATION,
        recordId: intent.intent_id,
        value: {
          schema_version: OPERATION_SCHEMA_VERSION,
          intent_id: intent.intent_id,
          intent_hash: intent.intent_hash,
          run_id: intent.run_id,
          published_event_count: 0,
        },
      });
      return OBJECT_FREEZE({ intent, status: "REGISTERED" });
    });
    const publication = publishAndConfirmRecord(
      {
        artifactStore: this.#artifactStore,
        ledger: this.#ledger,
        stateStore: this.#stateStore,
      },
      "ACTION_INTENT",
      result.intent,
    );
    return OBJECT_FREEZE({ ...result, event_status: publication.publication.status });
  }

  beginAttempt(candidate) {
    const input = normalizeAttemptInput(candidate);
    const transactionResult = this.#stateStore.transaction((store) => {
      const snapshot = loadSnapshot(store, input.intent_id);
      verifyArguments(this.#artifactStore, snapshot.intent);
      const existingAttemptRecord = store.readRevisionedRecord(
        EFFECT_RECORD_TYPES.ATTEMPT,
        input.attempt_id,
      );
      if (existingAttemptRecord !== null) {
        const existing = validateAttemptRecord(
          assertImmutableRecord(
            existingAttemptRecord,
            EFFECT_RECORD_TYPES.ATTEMPT,
            input.attempt_id,
            "Attempt",
          ),
        );
        if (
          existing.intent_id !== input.intent_id ||
          existing.started_at !== input.started_at ||
          !snapshot.attempts.some((attempt) => attempt.attempt_id === existing.attempt_id)
        ) {
          fail("ATTEMPT_ID_CONFLICT", "attempt ID is already bound to a different attempt");
        }
        return OBJECT_FREEZE({ attempt: existing, created: false, snapshot });
      }
      const tail = operationTail(snapshot);
      if (tail.attempt !== null && (tail.receipt === null || tail.receipt.status === "UNKNOWN")) {
        fail(
          "EFFECT_RECONCILIATION_REQUIRED",
          "an unresolved effect must be reconciled before retry",
          { attemptId: tail.attempt.attempt_id, intentId: input.intent_id },
        );
      }
      if (tail.receipt?.status === "SUCCEEDED") {
        return OBJECT_FREEZE({ attempt: tail.attempt, created: false, snapshot });
      }
      const earliestStart = tail.receipt?.finished_at ?? snapshot.intent.created_at;
      if (compareRfc3339(input.started_at, earliestStart) < 0) {
        fail(
          "ATTEMPT_CHRONOLOGY_INVALID",
          "Attempt.started_at must not precede the intent or prior resolved receipt",
          { earliestStart, intentId: input.intent_id, startedAt: input.started_at },
        );
      }
      const attempt = buildAttempt(snapshot.intent, input, snapshot.attempts.length + 1);
      store.createRevisionedRecord({
        recordType: EFFECT_RECORD_TYPES.ATTEMPT,
        recordId: attempt.attempt_id,
        value: attempt,
      });
      appendJournalEntry(store, snapshot, { kind: "ATTEMPT", attempt_id: attempt.attempt_id });
      return OBJECT_FREEZE({ attempt, created: true, snapshot: null });
    });

    if (!transactionResult.created) {
      const publication = publishAndConfirmRecord(
        {
          artifactStore: this.#artifactStore,
          ledger: this.#ledger,
          stateStore: this.#stateStore,
        },
        "ATTEMPT",
        transactionResult.attempt,
      );
      const current = this.inspect(input.intent_id);
      return OBJECT_FREEZE({
        attempt: transactionResult.attempt,
        event_status: publication.publication.status,
        execute_permitted: false,
        outcome: current,
        status:
          current.status === "SUCCEEDED" ? "EXISTING_RESULT" : "EXISTING_ATTEMPT",
      });
    }
    const publication = publishAndConfirmRecord(
      {
        artifactStore: this.#artifactStore,
        ledger: this.#ledger,
        stateStore: this.#stateStore,
      },
      "ATTEMPT",
      transactionResult.attempt,
    );
    return OBJECT_FREEZE({
      attempt: transactionResult.attempt,
      event_status: publication.publication.status,
      execute_permitted: true,
      status: "STARTED",
    });
  }

  #recordReceipt(candidate, mode) {
    const request = requirePlainDataObject(candidate, "receipt request", {
      allowedKeys: ["attempt_id", "receipt"],
    });
    const attemptId = requireNonEmptyString(
      readDataProperty(request, "attempt_id"),
      "receipt request.attempt_id",
    );
    const receipt = normalizeEffectReceipt(readDataProperty(request, "receipt"));
    verifyReceiptArtifacts(this.#artifactStore, receipt);
    const result = this.#stateStore.transaction((store) => {
      const snapshot = loadSnapshot(store, receipt.intent_id);
      const attempt = snapshot.attempts.find((entry) => entry.attempt_id === attemptId);
      if (attempt === undefined) {
        fail("ATTEMPT_NOT_FOUND", "EffectReceipt does not resolve a durable Attempt", { attemptId });
      }
      const tail = operationTail(snapshot);
      const existingReceiptRecord = store.readRevisionedRecord(
        EFFECT_RECORD_TYPES.EFFECT_RECEIPT,
        receipt.receipt_id,
      );
      if (existingReceiptRecord !== null) {
        const existing = normalizeEffectReceipt(
          assertImmutableRecord(
            existingReceiptRecord,
            EFFECT_RECORD_TYPES.EFFECT_RECEIPT,
            receipt.receipt_id,
            "EffectReceipt",
          ),
        );
        const binding = snapshot.operation.journal.find(
          (entry) => entry.kind === "RECEIPT" && entry.receipt_id === existing.receipt_id,
        );
        if (
          !sameCanonicalRecord(existing, receipt) ||
          binding === undefined ||
          binding.attempt_id !== attemptId ||
          binding.mode !== mode
        ) {
          fail("RECEIPT_ID_CONFLICT", "receipt ID is already bound to a different receipt");
        }
        return OBJECT_FREEZE({ receipt: existing, status: "EXISTING" });
      }
      if (tail.attempt?.attempt_id !== attemptId) {
        fail("RECEIPT_ATTEMPT_MISMATCH", "receipt may resolve only the current Attempt");
      }
      assertIntentBinding(receipt, snapshot.intent, "EffectReceipt");
      if (receipt.started_at !== attempt.started_at) {
        fail("RECEIPT_ATTEMPT_MISMATCH", "EffectReceipt.started_at differs from Attempt");
      }
      if (mode === "EXECUTION") {
        if (tail.receipt !== null) {
          fail(
            tail.receipt.status === "UNKNOWN"
              ? "EFFECT_RECONCILIATION_REQUIRED"
              : "EFFECT_ALREADY_RESOLVED",
            "an existing receipt prevents a second execution receipt",
          );
        }
      } else if (tail.receipt !== null && tail.receipt.status !== "UNKNOWN") {
        fail("EFFECT_ALREADY_RESOLVED", "a resolved effect cannot be reconciled again");
      }
      if (
        tail.receipt !== null &&
        compareRfc3339(receipt.finished_at, tail.receipt.finished_at) < 0
      ) {
        fail("EFFECT_RECEIPT_INVALID", "reconciliation receipt chronology moves backwards");
      }
      if (
        mode === "RECONCILIATION" &&
        tail.receipt?.external_operation_id !== null &&
        tail.receipt?.external_operation_id !== undefined &&
        receipt.external_operation_id !== tail.receipt.external_operation_id
      ) {
        fail(
          "EFFECT_RECONCILIATION_OPERATION_MISMATCH",
          "reconciliation must retain the observed external operation identity",
        );
      }
      store.createRevisionedRecord({
        recordType: EFFECT_RECORD_TYPES.EFFECT_RECEIPT,
        recordId: receipt.receipt_id,
        value: receipt,
      });
      appendJournalEntry(store, snapshot, {
        kind: "RECEIPT",
        attempt_id: attemptId,
        receipt_id: receipt.receipt_id,
        mode,
      });
      return OBJECT_FREEZE({ receipt, status: "RECORDED" });
    });
    const publication = publishAndConfirmRecord(
      {
        artifactStore: this.#artifactStore,
        ledger: this.#ledger,
        stateStore: this.#stateStore,
      },
      "EFFECT_RECEIPT",
      result.receipt,
    );
    const outcome = this.inspect(result.receipt.intent_id);
    return OBJECT_FREEZE({
      ...result,
      event_status: publication.publication.status,
      outcome,
    });
  }

  recordReceipt(candidate) {
    return this.#recordReceipt(candidate, "EXECUTION");
  }

  reconcile(candidate) {
    return this.#recordReceipt(candidate, "RECONCILIATION");
  }

  inspect(intentId) {
    const id = requireNonEmptyString(intentId, "intentId");
    const snapshot = this.#stateStore.transaction((store) => loadSnapshot(store, id));
    verifyArguments(this.#artifactStore, snapshot.intent);
    for (let index = 0; index < snapshot.receipts.length; index += 1) {
      verifyReceiptArtifacts(this.#artifactStore, snapshot.receipts[index]);
    }
    const publication = inspectPublications(
      { artifactStore: this.#artifactStore, ledger: this.#ledger },
      snapshot,
    );
    const outcome = outcomeFromSnapshot(snapshot, publication);
    return OBJECT_FREEZE({
      ...outcome,
      attempt_count: snapshot.attempts.length,
      intent: snapshot.intent,
      ledger_event_count: publication.event_count,
      receipt_count: snapshot.receipts.length,
    });
  }

  verify(intentId) {
    const outcome = this.inspect(intentId);
    if (outcome.event_reconciliation_required) {
      fail(
        "EFFECT_EVENT_RECONCILIATION_REQUIRED",
        "durable effect records are missing resolving ledger events",
        { intentId, missingEventIds: outcome.missing_event_ids },
      );
    }
    if (outcome.publication_confirmation_required) {
      fail(
        "EFFECT_EVENT_CONFIRMATION_REQUIRED",
        "ledger events exist but their durable publication checkpoint is unresolved",
        { intentId },
      );
    }
    return OBJECT_FREEZE({
      attempt_count: outcome.attempt_count,
      completion_proven: outcome.completion_proven,
      effect_status: outcome.effect_status,
      intent_hash_verified: true,
      ledger_event_count: outcome.ledger_event_count,
      outcome_resolved: outcome.outcome_resolved,
      receipt_count: outcome.receipt_count,
      receipt_hashes_verified: outcome.receipt_count,
      reconciliation_required: outcome.reconciliation_required,
      run_id: outcome.intent.run_id,
    });
  }

  readIntent(intentId) {
    const id = requireNonEmptyString(intentId, "intentId");
    return this.#stateStore.transaction((store) => loadSnapshot(store, id).intent);
  }

  readAttempts(intentId) {
    const id = requireNonEmptyString(intentId, "intentId");
    return this.#stateStore.transaction((store) => loadSnapshot(store, id).attempts);
  }

  readReceipts(intentId) {
    const id = requireNonEmptyString(intentId, "intentId");
    return this.#stateStore.transaction((store) => loadSnapshot(store, id).receipts);
  }
}

export const createEffectCoordinator = (options) =>
  new EffectCoordinator(CONSTRUCTOR_TOKEN, validateDependencies(options));

export const isResolvingEffectStatus = (status) => RESOLVING_STATUSES.has(status);
