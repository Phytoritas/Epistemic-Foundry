import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

export const ARRAY_IS_ARRAY = Array.isArray;
export const IS_PROXY = utilTypes.isProxy;
export const NUMBER_IS_FINITE = Number.isFinite;
export const NUMBER_IS_SAFE_INTEGER = Number.isSafeInteger;
export const OBJECT_FREEZE = Object.freeze;

const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;
const HASH_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:Z|([+-])(\d{2}):(\d{2}))$/u;

export class DurableForgeSessionError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "DurableForgeSessionError";
    this.code = code;
    if (details !== undefined) this.details = detached(details);
  }
}

export const fail = (code, message, details = undefined) => {
  throw new DurableForgeSessionError(code, message, details);
};

export const readDataProperty = (
  value,
  key,
  label = "object",
  code = "FORGE_INPUT_INVALID",
) => {
  const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
  if (
    descriptor === undefined ||
    !descriptor.enumerable ||
    !OBJECT_HAS_OWN(descriptor, "value")
  ) {
    fail(code, `${label}.${key} must be an enumerable own data property`);
  }
  return descriptor.value;
};

export const requirePlainRecord = (
  value,
  label,
  { allowedKeys = undefined, requiredKeys = undefined, code = "FORGE_INPUT_INVALID" } = {},
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
      if (!allowed.has(key)) fail(code, `${label}.${key} is not allowed`);
    }
  }
  if (requiredKeys !== undefined) {
    for (const key of requiredKeys) {
      if (!OBJECT_HAS_OWN(value, key)) fail(code, `${label}.${key} is required`);
    }
  }
  return value;
};

export const requireDenseArray = (value, label, code = "FORGE_INPUT_INVALID") => {
  if (!ARRAY_IS_ARRAY(value) || IS_PROXY(value)) fail(code, `${label} must be an array`);
  const keys = REFLECT_OWN_KEYS(value);
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail(code, `${label} must be dense and contain only data elements`);
    }
  }
  for (const key of keys) {
    if (key === "length") continue;
    if (
      typeof key !== "string" ||
      !/^(?:0|[1-9][0-9]*)$/u.test(key) ||
      Number(key) >= value.length
    ) {
      fail(code, `${label} cannot contain non-element properties`);
    }
  }
  return value;
};

export const requireString = (
  value,
  label,
  { min = 1, max = undefined, code = "FORGE_INPUT_INVALID" } = {},
) => {
  if (
    typeof value !== "string" ||
    value.length < min ||
    (max !== undefined && value.length > max)
  ) {
    fail(code, `${label} must be a bounded non-empty string`);
  }
  return value;
};

export const requireHash = (value, label, code = "FORGE_INPUT_INVALID") => {
  if (typeof value !== "string" || !HASH_PATTERN.test(value)) {
    fail(code, `${label} must be a canonical SHA-256`);
  }
  return value;
};

export const requireTimestamp = (value, label, code = "FORGE_INPUT_INVALID") => {
  if (typeof value !== "string" || !RFC3339_PATTERN.test(value)) {
    fail(code, `${label} must be an RFC 3339 date-time`);
  }
  const parsed = new Date(value);
  if (!NUMBER_IS_FINITE(parsed.valueOf())) {
    fail(code, `${label} must be a real RFC 3339 date-time`);
  }
  return value;
};

const assertCanonicalJson = (value, label = "value", ancestors = new Set()) => {
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!NUMBER_IS_FINITE(value) || !NUMBER_IS_SAFE_INTEGER(value) || Object.is(value, -0)) {
      fail("FORGE_NON_CANONICAL_JSON", `${label} must be a finite safe integer`);
    }
    return;
  }
  if (typeof value !== "object" || IS_PROXY(value)) {
    fail("FORGE_NON_CANONICAL_JSON", `${label} is not canonical JSON data`);
  }
  if (ancestors.has(value)) fail("FORGE_NON_CANONICAL_JSON", `${label} cannot be cyclic`);
  ancestors.add(value);
  try {
    if (ARRAY_IS_ARRAY(value)) {
      const entries = requireDenseArray(value, label, "FORGE_NON_CANONICAL_JSON");
      for (let index = 0; index < entries.length; index += 1) {
        assertCanonicalJson(entries[index], `${label}[${index}]`, ancestors);
      }
      return;
    }
    const record = requirePlainRecord(value, label, { code: "FORGE_NON_CANONICAL_JSON" });
    for (const key of Object.keys(record)) {
      assertCanonicalJson(
        readDataProperty(record, key, label, "FORGE_NON_CANONICAL_JSON"),
        `${label}.${key}`,
        ancestors,
      );
    }
  } finally {
    ancestors.delete(value);
  }
};

export const canonicalJson = (value) => {
  assertCanonicalJson(value);
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "boolean" || typeof value === "number") {
    return JSON.stringify(value);
  }
  if (ARRAY_IS_ARRAY(value)) {
    return `[${value.map((entry) => canonicalJson(entry)).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(readDataProperty(value, key))}`)
    .join(",")}}`;
};

export const hashBytes = (bytes) =>
  `sha256:${createHash("sha256").update(bytes).digest("hex")}`;

export const hashJson = (value) =>
  hashBytes(Buffer.from(canonicalJson(value), "utf8"));

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

export const detached = (value) => deepFreeze(JSON.parse(canonicalJson(value)));

export const sameCanonical = (left, right) => canonicalJson(left) === canonicalJson(right);

export const withoutKey = (record, omittedKey) =>
  Object.fromEntries(
    Object.keys(record)
      .filter((key) => key !== omittedKey)
      .map((key) => [key, readDataProperty(record, key)]),
  );

export const hashSealedRecord = (record) => hashJson(withoutKey(record, "record_hash"));

export const sealRecord = (semantic) => detached({
  ...semantic,
  record_hash: hashJson(semantic),
});

export const exactKeys = (value, expectedKeys, label, code) =>
  requirePlainRecord(value, label, {
    allowedKeys: expectedKeys,
    requiredKeys: expectedKeys,
    code,
  });
