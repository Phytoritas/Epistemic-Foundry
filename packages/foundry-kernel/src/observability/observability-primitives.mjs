/**
 * Fail-closed validation and deterministic hashing primitives for
 * observability, SLOs and privacy-safe telemetry (Y02).
 *
 * These are generic structural guards, canonical hashing, and W3C trace-context
 * identifier validators only. The higher-level semantics — how a span is shaped,
 * which log keys/values are sensitive, and how an SLO honestly reports its state
 * — live in `otel-trace.mjs`, `log-redaction.mjs`, and `result-state.mjs`.
 *
 * Nothing here fabricates a healthy signal: every validator refuses malformed,
 * proxied, or out-of-range input rather than coercing it into a plausible value,
 * so a telemetry record can never look well-formed when it is not.
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
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;

export const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
export const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|([+-])(\d{2}):(\d{2}))$/u;

/** W3C trace-context: a 16-byte trace id and an 8-byte span id, lowercase hex. */
export const TRACE_ID_PATTERN = /^[0-9a-f]{32}$/u;
export const SPAN_ID_PATTERN = /^[0-9a-f]{16}$/u;
const TRACE_ID_ZERO = "0".repeat(32);
const SPAN_ID_ZERO = "0".repeat(16);

/** An observability or telemetry input is malformed, mislabeled, or dishonest. */
export class ObservabilityError extends Error {
  constructor(code, message, details = undefined, options = undefined) {
    super(message, options);
    this.name = "ObservabilityError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(cloneCanonical(details));
  }
}

export const fail = (code, message, details, options) => {
  throw new ObservabilityError(code, message, details, options);
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

const readDataProperty = (value, key, label = "object", code = "OBSERVABILITY_INVALID") => {
  const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
  if (descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")) {
    fail(code, `${label}.${key} must be an own data property`);
  }
  return descriptor.value;
};

export const requirePlainRecord = (
  value,
  label,
  { allowedKeys = undefined, requiredKeys = undefined, code = "OBSERVABILITY_INVALID" } = {},
) => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    ![PLAIN_OBJECT_PROTOTYPE, null].includes(OBJECT_GET_PROTOTYPE_OF(value))
  ) {
    fail(code, `${label} must be a plain data object`);
  }
  const keys = REFLECT_OWN_KEYS(value);
  if (keys.some((key) => typeof key !== "string")) {
    fail(code, `${label} cannot contain symbol keys`);
  }
  for (const key of keys) readDataProperty(value, key, label, code);
  if (allowedKeys !== undefined) {
    const allowed = new Set(allowedKeys);
    for (const key of keys) {
      if (!allowed.has(key)) fail(code, `${label}.${key} is not an allowed field`, { field: key });
    }
  }
  if (requiredKeys !== undefined) {
    for (const key of requiredKeys) {
      if (!OBJECT_HAS_OWN(value, key)) fail(code, `${label}.${key} is required`, { field: key });
    }
  }
  return value;
};

export const requireString = (
  value,
  label,
  { min = 1, max = 4096, pattern = undefined, code = "OBSERVABILITY_INVALID" } = {},
) => {
  if (
    typeof value !== "string" ||
    value.length < min ||
    value.length > max ||
    !hasOnlyUnicodeScalars(value) ||
    (pattern !== undefined && !pattern.test(value))
  ) {
    fail(code, `${label} must be a valid bounded string`);
  }
  return value;
};

export const requireNullableString = (value, label, code = "OBSERVABILITY_INVALID") =>
  value === null ? null : requireString(value, label, { code });

export const requireHash = (value, label, code = "OBSERVABILITY_INVALID") =>
  requireString(value, label, { pattern: SHA256_PATTERN, code });

/** A 16-byte, non-zero W3C trace id in lowercase hex. */
export const requireTraceId = (value, label, code = "OBSERVABILITY_INVALID") => {
  const candidate = requireString(value, label, { pattern: TRACE_ID_PATTERN, code });
  if (candidate === TRACE_ID_ZERO) fail(code, `${label} must not be the all-zero trace id`);
  return candidate;
};

/** An 8-byte, non-zero W3C span id in lowercase hex. */
export const requireSpanId = (value, label, code = "OBSERVABILITY_INVALID") => {
  const candidate = requireString(value, label, { pattern: SPAN_ID_PATTERN, code });
  if (candidate === SPAN_ID_ZERO) fail(code, `${label} must not be the all-zero span id`);
  return candidate;
};

export const requireNullableSpanId = (value, label, code = "OBSERVABILITY_INVALID") =>
  value === null ? null : requireSpanId(value, label, code);

export const requireTimestamp = (value, label, code = "OBSERVABILITY_INVALID") => {
  const candidate = requireString(value, label, { code });
  if (!RFC3339_PATTERN.test(candidate) || !NUMBER_IS_FINITE(Date.parse(candidate))) {
    fail(code, `${label} must be an RFC 3339 timestamp`);
  }
  return candidate;
};

export const requireSafeInteger = (
  value,
  label,
  { minimum = 0, maximum = Number.MAX_SAFE_INTEGER, code = "OBSERVABILITY_INVALID" } = {},
) => {
  if (!NUMBER_IS_SAFE_INTEGER(value) || value < minimum || value > maximum) {
    fail(code, `${label} must be a safe integer in [${minimum}, ${maximum}]`);
  }
  return value;
};

export const requireFiniteNumber = (
  value,
  label,
  { minimum = 0, maximum = Number.MAX_VALUE, code = "OBSERVABILITY_INVALID" } = {},
) => {
  if (typeof value !== "number" || !NUMBER_IS_FINITE(value) || value < minimum || value > maximum) {
    fail(code, `${label} must be a finite number in range`);
  }
  return value;
};

export const requireEnum = (value, values, label, code = "OBSERVABILITY_INVALID") => {
  if (!values.has(value)) {
    fail(code, `${label} is not a canonical value`, { value, canonical: [...values] });
  }
  return value;
};

const assertCanonicalJsonValue = (value, label = "value", ancestors = new Set()) => {
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!NUMBER_IS_FINITE(value)) fail("NON_CANONICAL_JSON", `${label} must be finite`);
    return;
  }
  if (typeof value !== "object" || IS_PROXY(value)) {
    fail("NON_CANONICAL_JSON", `${label} is not canonical JSON data`);
  }
  if (ancestors.has(value)) fail("NON_CANONICAL_JSON", `${label} cannot be cyclic`);
  ancestors.add(value);
  try {
    if (ARRAY_IS_ARRAY(value)) {
      value.forEach((entry, index) =>
        assertCanonicalJsonValue(entry, `${label}[${index}]`, ancestors),
      );
      return;
    }
    const record = requirePlainRecord(value, label, { code: "NON_CANONICAL_JSON" });
    for (const key of Object.keys(record)) {
      assertCanonicalJsonValue(readDataProperty(record, key, label), `${label}.${key}`, ancestors);
    }
  } finally {
    ancestors.delete(value);
  }
};

export const canonicalizeObservabilityJson = (value) => {
  assertCanonicalJsonValue(value);
  if (value === null) return "null";
  if (["string", "number", "boolean"].includes(typeof value)) return JSON.stringify(value);
  if (ARRAY_IS_ARRAY(value)) {
    return `[${value.map((entry) => canonicalizeObservabilityJson(entry)).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort(compareText)
    .map((key) => `${JSON.stringify(key)}:${canonicalizeObservabilityJson(readDataProperty(value, key))}`)
    .join(",")}}`;
};

export const sha256ObservabilityJson = (value) =>
  `sha256:${createHash("sha256").update(canonicalizeObservabilityJson(value), "utf8").digest("hex")}`;

export const cloneCanonical = (value) => JSON.parse(canonicalizeObservabilityJson(value));

export const compareText = (left, right) => (left < right ? -1 : left > right ? 1 : 0);

export const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of REFLECT_OWN_KEYS(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};
