/**
 * Fail-closed validation and deterministic hashing primitives for the typed
 * budget and adaptive fleet controls (Y01).
 *
 * These are generic structural guards and canonical hashing only. The budget
 * vocabulary itself (enforcement labels, breach policies, limit dimensions) is
 * NOT declared here — it is composed from the sealed contract registry in
 * `budget-vocabulary.mjs`, whose source of truth is
 * `schemas/budget-envelope.schema.json`.
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

/** A budget or fleet control input is malformed, mislabeled, or over budget. */
export class BudgetControlError extends Error {
  constructor(code, message, details = undefined, options = undefined) {
    super(message, options);
    this.name = "BudgetControlError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(cloneCanonical(details));
  }
}

export const fail = (code, message, details, options) => {
  throw new BudgetControlError(code, message, details, options);
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

const readDataProperty = (value, key, label = "object", code = "INVALID_INPUT") => {
  const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
  if (descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")) {
    fail(code, `${label}.${key} must be an own data property`);
  }
  return descriptor.value;
};

export const requirePlainRecord = (
  value,
  label,
  { allowedKeys = undefined, requiredKeys = undefined, code = "INVALID_INPUT" } = {},
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
  { min = 1, max = 4096, pattern = undefined, code = "INVALID_INPUT" } = {},
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

export const requireNullableString = (value, label, code = "INVALID_INPUT") =>
  value === null ? null : requireString(value, label, { code });

export const requireHash = (value, label, code = "INVALID_INPUT") =>
  requireString(value, label, { pattern: SHA256_PATTERN, code });

export const requireTimestamp = (value, label, code = "INVALID_INPUT") => {
  const candidate = requireString(value, label, { code });
  if (!RFC3339_PATTERN.test(candidate) || !NUMBER_IS_FINITE(Date.parse(candidate))) {
    fail(code, `${label} must be an RFC 3339 timestamp`);
  }
  return candidate;
};

export const requireSafeInteger = (
  value,
  label,
  { minimum = 0, maximum = Number.MAX_SAFE_INTEGER, code = "INVALID_INPUT" } = {},
) => {
  if (!NUMBER_IS_SAFE_INTEGER(value) || value < minimum || value > maximum) {
    fail(code, `${label} must be a safe integer in [${minimum}, ${maximum}]`);
  }
  return value;
};

export const requireFiniteNumber = (
  value,
  label,
  { minimum = 0, maximum = Number.MAX_VALUE, code = "INVALID_INPUT" } = {},
) => {
  if (typeof value !== "number" || !NUMBER_IS_FINITE(value) || value < minimum || value > maximum) {
    fail(code, `${label} must be a finite number in range`);
  }
  return value;
};

export const requireEnum = (value, values, label, code = "INVALID_INPUT") => {
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

export const canonicalizeBudgetJson = (value) => {
  assertCanonicalJsonValue(value);
  if (value === null) return "null";
  if (["string", "number", "boolean"].includes(typeof value)) return JSON.stringify(value);
  if (ARRAY_IS_ARRAY(value)) {
    return `[${value.map((entry) => canonicalizeBudgetJson(entry)).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort(compareText)
    .map((key) => `${JSON.stringify(key)}:${canonicalizeBudgetJson(readDataProperty(value, key))}`)
    .join(",")}}`;
};

export const sha256BudgetJson = (value) =>
  `sha256:${createHash("sha256").update(canonicalizeBudgetJson(value), "utf8").digest("hex")}`;

export const cloneCanonical = (value) => JSON.parse(canonicalizeBudgetJson(value));

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
