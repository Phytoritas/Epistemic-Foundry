/**
 * Shared deterministic and hostile-input-safe primitives for M03.
 *
 * This module intentionally does not read the filesystem, infer missing
 * metadata, or import the M02 centrality implementation. M03 binds its own
 * artifacts to validated M01 inventory and edge-extraction identities.
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

export const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;

export class WorkspaceMapQueryRankingError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "WorkspaceMapQueryRankingError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(canonicalClone(details));
  }
}

export const fail = (code, message, details = undefined) => {
  throw new WorkspaceMapQueryRankingError(code, message, details);
};

export const compareUtf8 = (left, right) =>
  Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));

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

export const requireText = (
  value,
  label,
  { minLength = 1, maxLength = 4096, code = "INVALID_INPUT", allowControl = false } = {},
) => {
  const length = typeof value === "string" ? [...value].length : -1;
  if (
    typeof value !== "string" ||
    !hasOnlyUnicodeScalars(value) ||
    value.normalize("NFC") !== value ||
    (!allowControl && /\p{Cc}/u.test(value)) ||
    length < minLength ||
    length > maxLength
  ) {
    fail(code, `${label} must be a bounded NFC Unicode scalar string`);
  }
  return value;
};

export const requireIdentifier = (value, label, code = "INVALID_INPUT") =>
  requireText(value, label, { minLength: 3, maxLength: 128, code });

export const requireHash = (value, label, code = "INVALID_HASH") => {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) {
    fail(code, `${label} must be sha256:<64 lowercase hex>`);
  }
  return value;
};

export const requireBoolean = (value, label, code = "INVALID_INPUT") => {
  if (typeof value !== "boolean") fail(code, `${label} must be boolean`);
  return value;
};

export const requireEnum = (value, label, allowed, code = "UNKNOWN_VOCABULARY") => {
  if (typeof value !== "string" || !allowed.has(value)) {
    fail(
      code,
      `${label} is outside the canonical vocabulary`,
      typeof value === "string" ? { value } : undefined,
    );
  }
  return value;
};

export const requirePlainDataObject = (
  value,
  label,
  fields,
  code = "INVALID_INPUT",
) => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    (OBJECT_GET_PROTOTYPE_OF(value) !== PLAIN_OBJECT_PROTOTYPE &&
      OBJECT_GET_PROTOTYPE_OF(value) !== null)
  ) {
    fail(code, `${label} must be a non-proxy plain data object`);
  }
  const allowed = new Set(fields);
  const keys = REFLECT_OWN_KEYS(value);
  for (const key of keys) {
    if (typeof key !== "string" || !allowed.has(key)) {
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
  for (const field of fields) {
    if (!OBJECT_HAS_OWN(value, field)) fail(code, `${label}.${field} is required`);
  }
  return value;
};

export const readDataProperty = (object, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(object, key).value;

export const readDenseArray = (value, label, code = "INVALID_INPUT") => {
  if (
    !ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== Array.prototype
  ) {
    fail(code, `${label} must be a non-proxy plain dense array`);
  }
  for (const key of REFLECT_OWN_KEYS(value)) {
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
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail(code, `${label} contains a sparse or accessor-backed element`);
    }
    result.push(descriptor.value);
  }
  return result;
};

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

const canonicalizeValue = (value, ancestors) => {
  if (value === null) return "null";
  if (typeof value === "string") {
    requireText(value, "canonical JSON string", {
      minLength: 0,
      maxLength: 1_000_000,
      code: "NON_CANONICAL_JSON",
    });
    return JSON.stringify(value);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value) || Object.is(value, -0)) {
      fail("NON_CANONICAL_JSON", "canonical JSON accepts finite non-negative-zero numbers");
    }
    return JSON.stringify(value);
  }
  if (ARRAY_IS_ARRAY(value)) {
    if (ancestors.has(value)) fail("NON_CANONICAL_JSON", "canonical JSON cannot contain a cycle");
    const entries = readDenseArray(value, "canonical JSON array", "NON_CANONICAL_JSON");
    ancestors.add(value);
    try {
      return `[${entries.map((entry) => canonicalizeValue(entry, ancestors)).join(",")}]`;
    } finally {
      ancestors.delete(value);
    }
  }
  if (value === undefined || typeof value !== "object" || IS_PROXY(value)) {
    fail("NON_CANONICAL_JSON", "canonical JSON contains an unsupported value");
  }
  const prototype = OBJECT_GET_PROTOTYPE_OF(value);
  if (prototype !== PLAIN_OBJECT_PROTOTYPE && prototype !== null) {
    fail("NON_CANONICAL_JSON", "canonical JSON object has a custom prototype");
  }
  if (ancestors.has(value)) fail("NON_CANONICAL_JSON", "canonical JSON cannot contain a cycle");
  const keys = REFLECT_OWN_KEYS(value);
  if (keys.some((key) => typeof key !== "string")) {
    fail("NON_CANONICAL_JSON", "canonical JSON object contains a symbol key");
  }
  keys.sort(compareUtf8);
  ancestors.add(value);
  try {
    return `{${keys
      .map((key) => {
        const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
        if (
          descriptor === undefined ||
          !descriptor.enumerable ||
          !OBJECT_HAS_OWN(descriptor, "value")
        ) {
          fail("NON_CANONICAL_JSON", "canonical JSON object contains an accessor field");
        }
        return `${JSON.stringify(key)}:${canonicalizeValue(descriptor.value, ancestors)}`;
      })
      .join(",")}}`;
  } finally {
    ancestors.delete(value);
  }
};

export const canonicalizeQueryRankingJson = (value) =>
  canonicalizeValue(value, new Set());

export const canonicalClone = (value) =>
  deepFreeze(JSON.parse(canonicalizeQueryRankingJson(value)));

export const sha256CanonicalJson = (value) =>
  `sha256:${createHash("sha256")
    .update(canonicalizeQueryRankingJson(value), "utf8")
    .digest("hex")}`;

export const roundedScore = (value) => {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
    fail("INVALID_SCORE", "score must be finite and in [0, 1]");
  }
  const rounded = Number(value.toFixed(12));
  return Object.is(rounded, -0) ? 0 : rounded;
};

export const assertUniqueStrings = (values, label, code) => {
  if (new Set(values).size !== values.length) {
    fail(code, `${label} must not contain duplicates`);
  }
};
