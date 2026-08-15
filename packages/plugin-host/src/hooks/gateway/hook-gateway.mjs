import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

const ARRAY_IS_ARRAY = Array.isArray;
const NUMBER_IS_FINITE = Number.isFinite;
const NUMBER_IS_SAFE_INTEGER = Number.isSafeInteger;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const OBJECT_IS = Object.is;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const IS_PROXY = utilTypes.isProxy;

const REQUEST_KEYS = OBJECT_FREEZE([
  "event_id",
  "host",
  "event_type",
  "session_id",
  "tool_name",
  "received_at",
  "raw_payload",
  "coverage",
]);
const RUNTIME_KEYS = OBJECT_FREEZE(["decide", "timeout_ms"]);
const DECISION_KEYS = OBJECT_FREEZE([
  "decision",
  "reasons",
  "action_intent_id",
  "effect_receipt_id",
]);
const ENVELOPE_KEYS = OBJECT_FREEZE([
  "event_id",
  "host",
  "event_type",
  "session_id",
  "tool_name",
  "received_at",
  "raw_payload_hash",
  "normalized_payload",
  "decision",
  "reasons",
  "action_intent_id",
  "effect_receipt_id",
  "coverage",
  "envelope_hash",
]);

export const HOOK_HOSTS = OBJECT_FREEZE(["codex", "claude", "other"]);
export const HOOK_EVENT_TYPES = OBJECT_FREEZE([
  "SessionStart",
  "UserPromptSubmit",
  "PermissionRequest",
  "PreToolUse",
  "PostToolUse",
  "SubagentStart",
  "SubagentStop",
  "Stop",
  "PreCompact",
  "PostCompact",
  "SessionEnd",
]);
export const HOOK_DECISIONS = OBJECT_FREEZE([
  "ALLOW",
  "BLOCK",
  "REWRITE",
  "ADVISORY",
  "NOT_APPLICABLE",
  "ERROR",
]);
export const HOOK_COVERAGE = OBJECT_FREEZE(["OBSERVED", "PARTIAL", "UNOBSERVED"]);

const HOST_SET = new Set(HOOK_HOSTS);
const EVENT_TYPE_SET = new Set(HOOK_EVENT_TYPES);
const DECISION_SET = new Set(HOOK_DECISIONS);
const COVERAGE_SET = new Set(HOOK_COVERAGE);
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:[Zz]|([+-])(\d{2}):(\d{2}))$/u;
const MAX_PLATFORM_TIMEOUT_MS = 2_147_483_647;

export class HookGatewayError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "HookGatewayError";
    this.code = code;
  }
}

const fail = (code, message) => {
  throw new HookGatewayError(code, message);
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

const requireString = (
  value,
  label,
  { allowEmpty = true, minLength = undefined, maxLength = undefined, code = "INVALID_INPUT" } = {},
) => {
  const scalarLength = typeof value === "string" ? [...value].length : undefined;
  if (
    typeof value !== "string" ||
    !hasOnlyUnicodeScalars(value) ||
    (!allowEmpty && scalarLength === 0) ||
    (minLength !== undefined && scalarLength < minLength) ||
    (maxLength !== undefined && scalarLength > maxLength)
  ) {
    fail(code, `${label} must be a canonical Unicode scalar string`);
  }
  return value;
};

const requireNullableString = (value, label, code = "INVALID_INPUT") =>
  value === null ? null : requireString(value, label, { code });

const requireEnum = (value, values, label, code = "INVALID_INPUT") => {
  const candidate = requireString(value, label, { allowEmpty: false, code });
  if (!values.has(candidate)) fail(code, `${label} is outside the canonical vocabulary`);
  return candidate;
};

const requirePlainDataObject = (
  value,
  label,
  { allowedKeys = undefined, requiredKeys = undefined, code = "INVALID_INPUT" } = {},
) => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value)
  ) {
    fail(code, `${label} must be a non-proxy plain data object`);
  }
  const prototype = OBJECT_GET_PROTOTYPE_OF(value);
  if (prototype !== PLAIN_OBJECT_PROTOTYPE && prototype !== null) {
    fail(code, `${label} must be a plain data object`);
  }

  const allowed = allowedKeys === undefined ? null : new Set(allowedKeys);
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (typeof key !== "string" || (allowed !== null && !allowed.has(key))) {
      fail(code, `${label} contains an unsupported field`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail(code, `${label}.${String(key)} must be an enumerable data property`);
    }
  }

  if (requiredKeys !== undefined) {
    for (const key of requiredKeys) {
      if (!OBJECT_HAS_OWN(value, key)) fail(code, `${label}.${key} is required`);
    }
  }
  return value;
};

const readDataProperty = (record, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(record, key).value;

const readDenseArray = (value, label, code = "NON_CANONICAL_JSON") => {
  if (!ARRAY_IS_ARRAY(value) || IS_PROXY(value)) {
    fail(code, `${label} must be a non-proxy dense array`);
  }
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
      fail(code, `${label} contains a non-element property`);
    }
    const index = Number(key);
    if (!NUMBER_IS_SAFE_INTEGER(index) || index < 0 || index >= value.length) {
      fail(code, `${label} contains a non-canonical array index`);
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
      fail(code, `${label} must not be sparse or accessor-backed`);
    }
    result[index] = descriptor.value;
  }
  return result;
};

const assertCanonicalJsonValue = (value, label = "value", ancestors = new WeakSet()) => {
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") {
    if (!hasOnlyUnicodeScalars(value)) fail("NON_CANONICAL_JSON", `${label} has invalid Unicode`);
    return;
  }
  if (typeof value === "number") {
    if (!NUMBER_IS_FINITE(value) || OBJECT_IS(value, -0)) {
      fail("NON_CANONICAL_JSON", `${label} has a non-canonical number`);
    }
    return;
  }
  if (typeof value !== "object" || IS_PROXY(value)) {
    fail("NON_CANONICAL_JSON", `${label} has a non-JSON value`);
  }
  if (ancestors.has(value)) fail("NON_CANONICAL_JSON", `${label} has a cycle`);
  ancestors.add(value);
  try {
    if (ARRAY_IS_ARRAY(value)) {
      const entries = readDenseArray(value, label);
      for (let index = 0; index < entries.length; index += 1) {
        assertCanonicalJsonValue(entries[index], `${label}[${index}]`, ancestors);
      }
      return;
    }
    requirePlainDataObject(value, label, { code: "NON_CANONICAL_JSON" });
    for (const key of Object.keys(value)) {
      assertCanonicalJsonValue(readDataProperty(value, key), `${label}.${key}`, ancestors);
    }
  } finally {
    ancestors.delete(value);
  }
};

export const canonicalizeHookJson = (value) => {
  assertCanonicalJsonValue(value);
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (ARRAY_IS_ARRAY(value)) {
    const entries = readDenseArray(value, "value");
    return `[${entries.map((entry) => canonicalizeHookJson(entry)).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalizeHookJson(readDataProperty(value, key))}`)
    .join(",")}}`;
};

export const sha256HookJson = (value) =>
  `sha256:${createHash("sha256").update(canonicalizeHookJson(value), "utf8").digest("hex")}`;

const canonicalClone = (value) => JSON.parse(canonicalizeHookJson(value));

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object" || IS_PROXY(value)) return value;
  for (const key of REFLECT_OWN_KEYS(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};

const isLeapYear = (year) => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

const requireRfc3339 = (value, label, code) => {
  const candidate = requireString(value, label, { allowEmpty: false, code });
  const match = RFC3339_PATTERN.exec(candidate);
  if (match === null || match[0].length !== candidate.length) {
    fail(code, `${label} must be an RFC 3339 date-time`);
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const offsetHour = match[9] === undefined ? 0 : Number(match[9]);
  const offsetMinute = match[10] === undefined ? 0 : Number(match[10]);
  const days = [31, isLeapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > days[month - 1] ||
    hour > 23 ||
    minute > 59 ||
    second > 60 ||
    offsetHour > 23 ||
    offsetMinute > 59
  ) {
    fail(code, `${label} must be an RFC 3339 date-time`);
  }
  if (second === 60) {
    const offsetSign = match[8] === "-" ? -1 : 1;
    const offsetMinutes = offsetSign * (offsetHour * 60 + offsetMinute);
    const utcMinutes = hour * 60 + minute - offsetMinutes;
    const utcDayDelta = Math.floor(utcMinutes / (24 * 60));
    const utcMinuteOfDay = ((utcMinutes % (24 * 60)) + 24 * 60) % (24 * 60);
    let utcYear = year;
    let utcMonth = month;
    let utcDay = day + utcDayDelta;
    if (utcDay < 1) {
      utcMonth -= 1;
      if (utcMonth < 1) {
        utcYear -= 1;
        utcMonth = 12;
      }
      const previousMonthDays = [
        31,
        isLeapYear(utcYear) ? 29 : 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
      ];
      utcDay = previousMonthDays[utcMonth - 1];
    } else if (utcDay > days[month - 1]) {
      utcDay = 1;
      utcMonth += 1;
      if (utcMonth > 12) {
        utcYear += 1;
        utcMonth = 1;
      }
    }
    const utcMonthDays = [
      31,
      isLeapYear(utcYear) ? 29 : 28,
      31,
      30,
      31,
      30,
      31,
      31,
      30,
      31,
      30,
      31,
    ];
    if (
      utcMinuteOfDay !== 23 * 60 + 59 ||
      utcDay !== utcMonthDays[utcMonth - 1]
    ) {
      fail(code, `${label} must be an RFC 3339 date-time`);
    }
  }
  return candidate;
};

const requireStringArray = (value, label, code) => {
  const entries = readDenseArray(value, label, code);
  return entries.map((entry, index) =>
    requireString(entry, `${label}[${index}]`, { code }),
  );
};

const normalizeDecision = (candidate) => {
  const code = "HOOK_DECISION_INVALID";
  const record = requirePlainDataObject(candidate, "hook decision", {
    allowedKeys: DECISION_KEYS,
    requiredKeys: DECISION_KEYS,
    code,
  });
  return {
    decision: requireEnum(readDataProperty(record, "decision"), DECISION_SET, "decision", code),
    reasons: requireStringArray(readDataProperty(record, "reasons"), "reasons", code),
    action_intent_id: requireNullableString(
      readDataProperty(record, "action_intent_id"),
      "action_intent_id",
      code,
    ),
    effect_receipt_id: requireNullableString(
      readDataProperty(record, "effect_receipt_id"),
      "effect_receipt_id",
      code,
    ),
  };
};

const validateEnvelopeFields = (candidate) => {
  const code = "HOOK_ENVELOPE_INVALID";
  const record = requirePlainDataObject(candidate, "HookEventEnvelope", {
    allowedKeys: ENVELOPE_KEYS,
    requiredKeys: ENVELOPE_KEYS,
    code,
  });
  const normalizedPayload = readDataProperty(record, "normalized_payload");
  requirePlainDataObject(normalizedPayload, "normalized_payload", { code });
  assertCanonicalJsonValue(normalizedPayload, "normalized_payload");
  const rawPayloadHash = requireString(readDataProperty(record, "raw_payload_hash"), "raw_payload_hash", {
    allowEmpty: false,
    code,
  });
  const envelopeHash = requireString(readDataProperty(record, "envelope_hash"), "envelope_hash", {
    allowEmpty: false,
    code,
  });
  if (!SHA256_PATTERN.test(rawPayloadHash) || !SHA256_PATTERN.test(envelopeHash)) {
    fail(code, "HookEventEnvelope hashes must be canonical SHA-256 values");
  }

  return {
    event_id: requireString(readDataProperty(record, "event_id"), "event_id", {
      minLength: 3,
      maxLength: 128,
      code,
    }),
    host: requireEnum(readDataProperty(record, "host"), HOST_SET, "host", code),
    event_type: requireEnum(
      readDataProperty(record, "event_type"),
      EVENT_TYPE_SET,
      "event_type",
      code,
    ),
    session_id: requireNullableString(readDataProperty(record, "session_id"), "session_id", code),
    tool_name: requireNullableString(readDataProperty(record, "tool_name"), "tool_name", code),
    received_at: requireRfc3339(readDataProperty(record, "received_at"), "received_at", code),
    raw_payload_hash: rawPayloadHash,
    normalized_payload: canonicalClone(normalizedPayload),
    ...normalizeDecision({
      decision: readDataProperty(record, "decision"),
      reasons: readDataProperty(record, "reasons"),
      action_intent_id: readDataProperty(record, "action_intent_id"),
      effect_receipt_id: readDataProperty(record, "effect_receipt_id"),
    }),
    coverage: requireEnum(readDataProperty(record, "coverage"), COVERAGE_SET, "coverage", code),
    envelope_hash: envelopeHash,
  };
};

export const validateHookEventEnvelope = (candidate) => {
  const normalized = validateEnvelopeFields(candidate);
  const { envelope_hash: observedHash, ...preimage } = normalized;
  const expectedHash = sha256HookJson(preimage);
  if (observedHash !== expectedHash) {
    fail("HOOK_ENVELOPE_HASH_MISMATCH", "HookEventEnvelope hash does not match its canonical preimage");
  }
  return deepFreeze(normalized);
};

const normalizeRequest = (candidate) => {
  const request = requirePlainDataObject(candidate, "hook request", {
    allowedKeys: REQUEST_KEYS,
    requiredKeys: REQUEST_KEYS,
  });
  const rawPayload = readDataProperty(request, "raw_payload");
  requirePlainDataObject(rawPayload, "raw_payload", { code: "NON_CANONICAL_JSON" });
  assertCanonicalJsonValue(rawPayload, "raw_payload");
  return {
    event_id: requireString(readDataProperty(request, "event_id"), "event_id", {
      minLength: 3,
      maxLength: 128,
    }),
    host: requireEnum(readDataProperty(request, "host"), HOST_SET, "host"),
    event_type: requireEnum(
      readDataProperty(request, "event_type"),
      EVENT_TYPE_SET,
      "event_type",
    ),
    session_id: requireNullableString(readDataProperty(request, "session_id"), "session_id"),
    tool_name: requireNullableString(readDataProperty(request, "tool_name"), "tool_name"),
    received_at: requireRfc3339(readDataProperty(request, "received_at"), "received_at", "INVALID_INPUT"),
    raw_payload_hash: sha256HookJson(rawPayload),
    normalized_payload: canonicalClone(rawPayload),
    coverage: requireEnum(readDataProperty(request, "coverage"), COVERAGE_SET, "coverage"),
  };
};

const normalizeRuntime = (candidate) => {
  const runtime = requirePlainDataObject(candidate, "hook runtime", {
    allowedKeys: RUNTIME_KEYS,
    requiredKeys: RUNTIME_KEYS,
  });
  const decide = readDataProperty(runtime, "decide");
  if (typeof decide !== "function") fail("INVALID_INPUT", "decide must be a function");
  const timeoutMs = readDataProperty(runtime, "timeout_ms");
  if (
    !NUMBER_IS_SAFE_INTEGER(timeoutMs) ||
    timeoutMs < 1 ||
    timeoutMs > MAX_PLATFORM_TIMEOUT_MS
  ) {
    fail("INVALID_INPUT", "timeout_ms must be a positive platform-bounded integer");
  }
  return { decide, timeoutMs };
};

const errorDecision = (reason) => ({
  decision: "ERROR",
  reasons: [reason],
  action_intent_id: null,
  effect_receipt_id: null,
});

const sealEnvelope = (base, decision) => {
  const preimage = { ...base, ...decision };
  return validateHookEventEnvelope({
    ...preimage,
    envelope_hash: sha256HookJson(preimage),
  });
};

/**
 * Normalize one already-observed host event, invoke a bounded decision function,
 * and return an immutable HookEventEnvelope. The gateway never treats hook
 * coverage as exhaustive and never converts a timeout or callback failure into
 * ALLOW. Host-specific response mapping belongs to H02/H03 adapters.
 */
export const dispatchHookEvent = async (requestCandidate, runtimeCandidate) => {
  const base = normalizeRequest(requestCandidate);
  const { decide, timeoutMs } = normalizeRuntime(runtimeCandidate);
  deepFreeze(base.normalized_payload);
  const decisionInput = deepFreeze(canonicalClone(base));
  const abortController = new AbortController();

  const decisionPromise = Promise.resolve()
    .then(() => decide(decisionInput, abortController.signal))
    .then(
      (candidate) => ({ kind: "decision", candidate }),
      () => ({ kind: "callback_error" }),
    );
  let timer;
  const timeoutPromise = new Promise((resolve) => {
    timer = setTimeout(() => resolve({ kind: "timeout" }), timeoutMs);
  });

  const outcome = await Promise.race([decisionPromise, timeoutPromise]);
  clearTimeout(timer);
  if (outcome.kind === "timeout") abortController.abort("HOOK_DECISION_TIMEOUT");

  let decision;
  if (outcome.kind === "timeout") {
    decision = errorDecision("HOOK_DECISION_TIMEOUT");
  } else if (outcome.kind === "callback_error") {
    decision = errorDecision("HOOK_DECISION_CALLBACK_ERROR");
  } else {
    try {
      decision = normalizeDecision(outcome.candidate);
    } catch (error) {
      if (!(error instanceof HookGatewayError)) throw error;
      decision = errorDecision("HOOK_DECISION_INVALID");
    }
  }

  return sealEnvelope(base, decision);
};
