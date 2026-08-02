import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

// Compose the canonical model-tier vocabulary from the sealed contracts layer
// (X01) instead of redeclaring it here. Routing may only reason over tiers that
// the RoleSpec authority already recognizes.
import { MODEL_TIERS } from "../contracts/index.mjs";

export const ROUTE_TABLE_VERSION = "4.0.0-x03.1";
export const ROUTE_TABLE_ID_PREFIX = "RT-";
export const ROUTING_RECEIPT_ID_PREFIX = "MRR-";
export const ROUTING_DECISION_ID_PREFIX = "RTD-";
export const FALLBACK_DECISION_ID_PREFIX = "RFB-";

// These enums mirror schemas/model-routing-receipt.schema.json exactly. The
// accompanying test asserts byte-for-byte agreement with the schema so the two
// declarations cannot silently drift; the schema remains the authority.
export const ROUTING_POLICIES = Object.freeze([
  "fixed",
  "ucb",
  "thompson",
  "safe_bandit",
  "manual",
]);

export const REWARD_BASES = Object.freeze([
  "immediate_proxy",
  "validated_improvement",
  "delayed_holdout",
  "replication",
  "none",
]);

// Model routing must never acquire authority over the evaluator, the hidden
// holdout, or promotion. A task class whose leading segment names one of these
// protected authorities is refused outright, so the mutable routing surface can
// never be pointed at an immutable-authority decision.
export const PROTECTED_ROUTING_AUTHORITIES = Object.freeze([
  "evaluator",
  "holdout",
  "promotion",
]);

const ROUTING_POLICY_SET = new Set(ROUTING_POLICIES);
const REWARD_BASIS_SET = new Set(REWARD_BASES);
const MODEL_TIER_SET = new Set(MODEL_TIERS);
const PROTECTED_AUTHORITY_SET = new Set(PROTECTED_ROUTING_AUTHORITIES);

const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const IDENTIFIER_PATTERN = /^[a-z][a-z0-9_]{1,127}$/u;
const EXACT_TOKEN_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,255}$/u;
const FLOATING_TOKEN_PATTERN =
  /(?:^|[._:/+-])(?:auto|current|default|head|latest|main|master|stable|tip)(?:$|[._:/+-])/iu;
const VERSION_RANGE_PATTERN = /(?:\*|\^|~|[<>]=?|\.\.|\bx\b|\bX\b)/u;

const ROUTE_TABLE_PREIMAGE_FIELDS = Object.freeze(["route_table_version", "task_classes"]);
const ROUTE_TABLE_FIELDS = Object.freeze([
  "route_table_id",
  ...ROUTE_TABLE_PREIMAGE_FIELDS,
  "route_table_hash",
]);

const ROUTE_ENTRY_FIELDS = Object.freeze([
  "policy",
  "reward_basis",
  "exploration_probability",
  "safety_constraints",
  "route_order",
]);

const ROUTE_CANDIDATE_FIELDS = Object.freeze([
  "model_id",
  "provider_id",
  "model_tier",
  "estimated_cost",
  "estimated_latency_ms",
  "safe_default",
]);

const ROUTING_REQUEST_FIELDS = Object.freeze(["task_class", "unavailable_model_ids"]);

const RECEIPT_PREIMAGE_FIELDS = Object.freeze([
  "task_class",
  "eligible_model_ids",
  "selected_model_id",
  "policy",
  "reward_basis",
  "estimated_cost",
  "estimated_latency_ms",
  "exploration_probability",
  "safety_constraints",
]);

const RECEIPT_FIELDS = Object.freeze([
  "receipt_id",
  ...RECEIPT_PREIMAGE_FIELDS,
  "receipt_hash",
]);

const DECISION_PREIMAGE_FIELDS = Object.freeze([
  "route_table_id",
  "route_table_hash",
  "task_class",
  "policy",
  "reward_basis",
  "eligible_model_ids",
  "requested_unavailable_model_ids",
  "selected_model_id",
  "selected_model_tier",
  "selected_provider_id",
  "selected_route_index",
  "fallback_used",
  "fallback_chain",
  "safe_default_model_id",
  "fallback_policy_decision_id",
  "receipt",
]);

const DECISION_FIELDS = Object.freeze([
  "routing_decision_id",
  ...DECISION_PREIMAGE_FIELDS,
  "routing_decision_hash",
]);

const FALLBACK_STEP_FIELDS = Object.freeze(["model_id", "model_tier", "reason"]);

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;

export class RoutePolicyError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "RoutePolicyError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(canonicalClone(details));
  }
}

const fail = (code, message, details = undefined) => {
  throw new RoutePolicyError(code, message, details);
};

const compareUtf8 = (left, right) =>
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

const requireText = (
  value,
  label,
  { minLength = 1, maxLength = 4_096, code = "INVALID_INPUT" } = {},
) => {
  const length = typeof value === "string" ? [...value].length : -1;
  if (
    typeof value !== "string" ||
    !hasOnlyUnicodeScalars(value) ||
    value.normalize("NFC") !== value ||
    /\p{Cc}/u.test(value) ||
    length < minLength ||
    length > maxLength ||
    (minLength > 0 && value.trim().length === 0)
  ) {
    fail(code, `${label} must be a bounded non-blank NFC Unicode scalar string`);
  }
  return value;
};

const requirePlainDataObject = (value, label, fields, { code = "INVALID_INPUT" } = {}) => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    (OBJECT_GET_PROTOTYPE_OF(value) !== Object.prototype &&
      OBJECT_GET_PROTOTYPE_OF(value) !== null)
  ) {
    fail(code, `${label} must be a non-proxy plain data object`);
  }
  const allowed = fields === undefined ? null : new Set(fields);
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (typeof key !== "string" || (allowed !== null && !allowed.has(key))) {
      fail("UNEXPECTED_FIELD", `${label} contains an unsupported field`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail("ACCESSOR_FIELD_DENIED", `${label}.${String(key)} must be an enumerable data property`);
    }
  }
  if (fields !== undefined) {
    for (const field of fields) {
      if (!OBJECT_HAS_OWN(value, field)) {
        fail("MISSING_FIELD", `${label}.${field} is required`);
      }
    }
  }
  return value;
};

const readDataProperty = (record, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(record, key).value;

const readDenseArray = (value, label, code = "INVALID_INPUT") => {
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
      fail(code, `${label} contains a non-canonical array index`);
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
      fail(code, `${label} contains a sparse or accessor-backed element`);
    }
    output[index] = descriptor.value;
  }
  return output;
};

const requireEnum = (value, label, values, code) => {
  if (typeof value !== "string" || !values.has(value)) {
    fail(code, `${label} is outside the canonical vocabulary`);
  }
  return value;
};

const requireSafeInteger = (value, label, { minimum, maximum, code = "INVALID_INTEGER" }) => {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || Object.is(value, -0)) {
    fail(code, `${label} must be a safe non-negative integer`);
  }
  if (value < minimum || value > maximum) {
    fail(code, `${label} must be within [${minimum}, ${maximum}]`);
  }
  return value;
};

const requireFiniteNumber = (value, label, { minimum, maximum, code = "INVALID_NUMBER" }) => {
  if (typeof value !== "number" || !Number.isFinite(value) || Object.is(value, -0)) {
    fail(code, `${label} must be a finite number`);
  }
  if (value < minimum || value > maximum) {
    fail(code, `${label} must be within [${minimum}, ${maximum}]`);
  }
  return value;
};

const requireBoolean = (value, label, code = "INVALID_INPUT") => {
  if (typeof value !== "boolean") {
    fail(code, `${label} must be a boolean`);
  }
  return value;
};

const requireIdentifier = (value, label, code = "INVALID_IDENTIFIER") => {
  const candidate = requireText(value, label, { minLength: 2, maxLength: 128, code });
  if (!IDENTIFIER_PATTERN.test(candidate)) {
    fail(code, `${label} must use canonical lowercase snake_case`);
  }
  return candidate;
};

const requireExactModelId = (value, label) => {
  const candidate = requireText(value, label, { minLength: 1, maxLength: 256 });
  if (
    !EXACT_TOKEN_PATTERN.test(candidate) ||
    FLOATING_TOKEN_PATTERN.test(candidate) ||
    VERSION_RANGE_PATTERN.test(candidate)
  ) {
    fail("FLOATING_MODEL_REFERENCE", `${label} must be an exact non-floating model identifier`);
  }
  return candidate;
};

const requireStringArray = (value, label, { code = "INVALID_INPUT", sort = false } = {}) => {
  const entries = readDenseArray(value, label, code).map((entry, index) =>
    requireText(entry, `${label}[${index}]`, { maxLength: 1_024, code }),
  );
  if (new Set(entries).size !== entries.length) {
    fail(code, `${label} must contain unique values`);
  }
  if (sort) {
    const sorted = [...entries].sort(compareUtf8);
    if (entries.some((entry, index) => entry !== sorted[index])) {
      fail("NON_CANONICAL_ORDER", `${label} must use ascending UTF-8 byte order`);
    }
    return sorted;
  }
  return entries;
};

function deepFreeze(value) {
  if (value === null || typeof value !== "object") return value;
  for (const key of REFLECT_OWN_KEYS(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
}

// Canonical JSON for routing artifacts. Unlike the integer-only RoleSpec
// canonicalizer, routing receipts legitimately carry bounded decimals
// (exploration_probability, cost), so finite numbers are permitted. Number
// serialization is ECMAScript-deterministic, keeping receipts re-derivable.
const canonicalRoutingValue = (value, ancestors) => {
  if (value === null) return "null";
  if (typeof value === "string") {
    if (!hasOnlyUnicodeScalars(value) || value.normalize("NFC") !== value) {
      fail("NON_CANONICAL_JSON", "canonical JSON string must be NFC Unicode scalar text");
    }
    return JSON.stringify(value);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value) || Object.is(value, -0)) {
      fail("NON_CANONICAL_JSON", "canonical JSON only accepts finite non-negative-zero numbers");
    }
    return JSON.stringify(value);
  }
  if (ARRAY_IS_ARRAY(value)) {
    if (ancestors.has(value)) fail("NON_CANONICAL_JSON", "canonical JSON cannot contain a cycle");
    const entries = readDenseArray(value, "canonical JSON array");
    ancestors.add(value);
    try {
      return `[${entries.map((entry) => canonicalRoutingValue(entry, ancestors)).join(",")}]`;
    } finally {
      ancestors.delete(value);
    }
  }
  if (
    value === undefined ||
    typeof value !== "object" ||
    IS_PROXY(value) ||
    (OBJECT_GET_PROTOTYPE_OF(value) !== Object.prototype &&
      OBJECT_GET_PROTOTYPE_OF(value) !== null)
  ) {
    fail("NON_CANONICAL_JSON", "canonical JSON contains an unsupported value");
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
        return `${JSON.stringify(key)}:${canonicalRoutingValue(descriptor.value, ancestors)}`;
      })
      .join(",")}}`;
  } finally {
    ancestors.delete(value);
  }
};

export const canonicalizeRoutingJson = (value) => canonicalRoutingValue(value, new Set());

const canonicalClone = (value) => JSON.parse(canonicalizeRoutingJson(value));

const sha256RoutingJson = (value) =>
  `sha256:${createHash("sha256").update(canonicalizeRoutingJson(value), "utf8").digest("hex")}`;

const requireHash = (value, label, code = "INVALID_HASH") => {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) {
    fail(code, `${label} must be sha256:<64 lowercase hex>`);
  }
  return value;
};

const assertNotProtectedAuthority = (taskClass) => {
  const head = taskClass.split("_")[0];
  if (PROTECTED_AUTHORITY_SET.has(head)) {
    fail(
      "ROUTE_AUTHORITY_FORBIDDEN",
      "a routing task class cannot name the evaluator, holdout, or promotion authority",
      { task_class: taskClass, protected: [...PROTECTED_ROUTING_AUTHORITIES] },
    );
  }
  return taskClass;
};

const normalizeRouteCandidate = (candidate, label) => {
  const record = requirePlainDataObject(candidate, label, ROUTE_CANDIDATE_FIELDS, {
    code: "ROUTE_TABLE_INVALID",
  });
  return {
    model_id: requireExactModelId(readDataProperty(record, "model_id"), `${label}.model_id`),
    provider_id: requireIdentifier(
      readDataProperty(record, "provider_id"),
      `${label}.provider_id`,
      "ROUTE_TABLE_INVALID",
    ),
    model_tier: requireEnum(
      readDataProperty(record, "model_tier"),
      `${label}.model_tier`,
      MODEL_TIER_SET,
      "UNKNOWN_MODEL_TIER",
    ),
    estimated_cost: requireFiniteNumber(readDataProperty(record, "estimated_cost"), `${label}.estimated_cost`, {
      minimum: 0,
      maximum: 1_000_000_000,
      code: "ROUTE_TABLE_INVALID",
    }),
    estimated_latency_ms: requireSafeInteger(
      readDataProperty(record, "estimated_latency_ms"),
      `${label}.estimated_latency_ms`,
      { minimum: 0, maximum: 86_400_000, code: "ROUTE_TABLE_INVALID" },
    ),
    safe_default: requireBoolean(
      readDataProperty(record, "safe_default"),
      `${label}.safe_default`,
      "ROUTE_TABLE_INVALID",
    ),
  };
};

const normalizeRouteEntry = (candidate, label) => {
  const record = requirePlainDataObject(candidate, label, ROUTE_ENTRY_FIELDS, {
    code: "ROUTE_TABLE_INVALID",
  });
  const routeOrder = readDenseArray(
    readDataProperty(record, "route_order"),
    `${label}.route_order`,
    "ROUTE_TABLE_INVALID",
  ).map((entry, index) => normalizeRouteCandidate(entry, `${label}.route_order[${index}]`));
  if (routeOrder.length === 0) {
    fail("ROUTE_TABLE_INVALID", `${label}.route_order must declare at least one candidate`);
  }
  const modelIds = routeOrder.map((entry) => entry.model_id);
  if (new Set(modelIds).size !== modelIds.length) {
    fail("ROUTE_TABLE_INVALID", `${label}.route_order must not repeat a model_id`);
  }
  // Deterministic fallback ordering must terminate in exactly one safe default:
  // only the final candidate may carry safe_default = true.
  routeOrder.forEach((entry, index) => {
    const isLast = index === routeOrder.length - 1;
    if (entry.safe_default !== isLast) {
      fail(
        "SAFE_DEFAULT_POSITION_INVALID",
        `${label}.route_order must mark only the final candidate as the safe default`,
      );
    }
  });
  return {
    policy: requireEnum(
      readDataProperty(record, "policy"),
      `${label}.policy`,
      ROUTING_POLICY_SET,
      "UNKNOWN_ROUTING_POLICY",
    ),
    reward_basis: requireEnum(
      readDataProperty(record, "reward_basis"),
      `${label}.reward_basis`,
      REWARD_BASIS_SET,
      "UNKNOWN_REWARD_BASIS",
    ),
    exploration_probability: requireFiniteNumber(
      readDataProperty(record, "exploration_probability"),
      `${label}.exploration_probability`,
      { minimum: 0, maximum: 1, code: "ROUTE_TABLE_INVALID" },
    ),
    safety_constraints: requireStringArray(
      readDataProperty(record, "safety_constraints"),
      `${label}.safety_constraints`,
      { code: "ROUTE_TABLE_INVALID", sort: true },
    ),
    route_order: routeOrder,
  };
};

const normalizeRouteTablePreimage = (candidate) => {
  const record = requirePlainDataObject(candidate, "RouteTable preimage", ROUTE_TABLE_PREIMAGE_FIELDS, {
    code: "ROUTE_TABLE_INVALID",
  });
  const version = readDataProperty(record, "route_table_version");
  if (version !== ROUTE_TABLE_VERSION) {
    fail("ROUTE_TABLE_VERSION_UNSUPPORTED", `route_table_version must be ${ROUTE_TABLE_VERSION}`);
  }
  const rawTaskClasses = requirePlainDataObject(
    readDataProperty(record, "task_classes"),
    "RouteTable.task_classes",
    undefined,
    { code: "ROUTE_TABLE_INVALID" },
  );
  const keys = REFLECT_OWN_KEYS(rawTaskClasses);
  if (keys.length === 0 || keys.some((key) => typeof key !== "string")) {
    fail("ROUTE_TABLE_INVALID", "RouteTable.task_classes must declare at least one task class");
  }
  const taskClasses = {};
  for (const name of [...keys].sort(compareUtf8)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(rawTaskClasses, name);
    if (descriptor === undefined || !descriptor.enumerable || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail("ROUTE_TABLE_INVALID", `RouteTable.task_classes.${name} must be a data property`);
    }
    requireIdentifier(name, `RouteTable.task_classes key ${name}`, "ROUTE_TABLE_INVALID");
    assertNotProtectedAuthority(name);
    taskClasses[name] = normalizeRouteEntry(descriptor.value, `RouteTable.task_classes.${name}`);
  }
  return {
    route_table_version: version,
    task_classes: taskClasses,
  };
};

/** Build a deterministic, immutable, content-addressed route table. */
export const createRouteTable = (preimageCandidate) => {
  const preimage = normalizeRouteTablePreimage(preimageCandidate);
  const hash = sha256RoutingJson(preimage);
  return deepFreeze({
    route_table_id: `${ROUTE_TABLE_ID_PREFIX}${hash.slice("sha256:".length)}`,
    ...canonicalClone(preimage),
    route_table_hash: hash,
  });
};

/** Verify a persisted route table's canonical identity and content integrity. */
export const verifyRouteTableIntegrity = (candidate) => {
  const record = requirePlainDataObject(candidate, "RouteTable", ROUTE_TABLE_FIELDS, {
    code: "ROUTE_TABLE_INVALID",
  });
  const preimageCandidate = {};
  for (const field of ROUTE_TABLE_PREIMAGE_FIELDS) {
    preimageCandidate[field] = readDataProperty(record, field);
  }
  const preimage = normalizeRouteTablePreimage(preimageCandidate);
  const expectedHash = sha256RoutingJson(preimage);
  const observedHash = requireHash(
    readDataProperty(record, "route_table_hash"),
    "route_table_hash",
    "ROUTE_TABLE_INVALID",
  );
  if (observedHash !== expectedHash) {
    fail("ROUTE_TABLE_HASH_MISMATCH", "route_table_hash does not bind the canonical route table", {
      expected: expectedHash,
      observed: observedHash,
    });
  }
  const observedId = readDataProperty(record, "route_table_id");
  const expectedId = `${ROUTE_TABLE_ID_PREFIX}${expectedHash.slice("sha256:".length)}`;
  if (observedId !== expectedId) {
    fail("ROUTE_TABLE_ID_MISMATCH", "route_table_id does not derive from route_table_hash", {
      expected: expectedId,
      observed: observedId,
    });
  }
  return deepFreeze({
    route_table_id: expectedId,
    ...canonicalClone(preimage),
    route_table_hash: expectedHash,
  });
};

const buildRoutingReceipt = (preimage) => {
  const receiptPreimage = {};
  for (const field of RECEIPT_PREIMAGE_FIELDS) receiptPreimage[field] = preimage[field];
  const receiptHash = sha256RoutingJson(receiptPreimage);
  return {
    receipt_id: `${ROUTING_RECEIPT_ID_PREFIX}${receiptHash.slice("sha256:".length)}`,
    ...canonicalClone(receiptPreimage),
    receipt_hash: receiptHash,
  };
};

/** Re-derive and verify a persisted ModelRoutingReceipt without a route table. */
export const verifyModelRoutingReceipt = (candidate) => {
  const record = requirePlainDataObject(candidate, "ModelRoutingReceipt", RECEIPT_FIELDS, {
    code: "ROUTING_RECEIPT_INVALID",
  });
  const preimage = {
    task_class: assertNotProtectedAuthority(
      requireIdentifier(readDataProperty(record, "task_class"), "task_class", "ROUTING_RECEIPT_INVALID"),
    ),
    eligible_model_ids: readDenseArray(
      readDataProperty(record, "eligible_model_ids"),
      "eligible_model_ids",
      "ROUTING_RECEIPT_INVALID",
    ).map((entry, index) => requireExactModelId(entry, `eligible_model_ids[${index}]`)),
    selected_model_id: requireExactModelId(
      readDataProperty(record, "selected_model_id"),
      "selected_model_id",
    ),
    policy: requireEnum(
      readDataProperty(record, "policy"),
      "policy",
      ROUTING_POLICY_SET,
      "UNKNOWN_ROUTING_POLICY",
    ),
    reward_basis: requireEnum(
      readDataProperty(record, "reward_basis"),
      "reward_basis",
      REWARD_BASIS_SET,
      "UNKNOWN_REWARD_BASIS",
    ),
    estimated_cost: requireFiniteNumber(readDataProperty(record, "estimated_cost"), "estimated_cost", {
      minimum: 0,
      maximum: 1_000_000_000,
      code: "ROUTING_RECEIPT_INVALID",
    }),
    estimated_latency_ms: requireSafeInteger(
      readDataProperty(record, "estimated_latency_ms"),
      "estimated_latency_ms",
      { minimum: 0, maximum: 86_400_000, code: "ROUTING_RECEIPT_INVALID" },
    ),
    exploration_probability: requireFiniteNumber(
      readDataProperty(record, "exploration_probability"),
      "exploration_probability",
      { minimum: 0, maximum: 1, code: "ROUTING_RECEIPT_INVALID" },
    ),
    safety_constraints: requireStringArray(
      readDataProperty(record, "safety_constraints"),
      "safety_constraints",
      { code: "ROUTING_RECEIPT_INVALID", sort: true },
    ),
  };
  if (new Set(preimage.eligible_model_ids).size !== preimage.eligible_model_ids.length) {
    fail("ROUTING_RECEIPT_INVALID", "eligible_model_ids must be unique");
  }
  if (!preimage.eligible_model_ids.includes(preimage.selected_model_id)) {
    fail("ROUTING_RECEIPT_INVALID", "selected_model_id must be one of the eligible models");
  }
  const expected = buildRoutingReceipt(preimage);
  const observedHash = requireHash(
    readDataProperty(record, "receipt_hash"),
    "receipt_hash",
    "ROUTING_RECEIPT_INVALID",
  );
  if (observedHash !== expected.receipt_hash) {
    fail("ROUTING_RECEIPT_HASH_MISMATCH", "receipt_hash does not bind the routing receipt", {
      expected: expected.receipt_hash,
      observed: observedHash,
    });
  }
  const observedId = readDataProperty(record, "receipt_id");
  if (observedId !== expected.receipt_id) {
    fail("ROUTING_RECEIPT_ID_MISMATCH", "receipt_id does not derive from receipt_hash", {
      expected: expected.receipt_id,
      observed: observedId,
    });
  }
  return deepFreeze(expected);
};

const normalizeRoutingRequest = (candidate) => {
  const record = requirePlainDataObject(candidate, "routing request", ROUTING_REQUEST_FIELDS, {
    code: "ROUTING_REQUEST_INVALID",
  });
  return {
    task_class: requireIdentifier(
      readDataProperty(record, "task_class"),
      "task_class",
      "ROUTING_REQUEST_INVALID",
    ),
    unavailable_model_ids: readDenseArray(
      readDataProperty(record, "unavailable_model_ids"),
      "unavailable_model_ids",
      "ROUTING_REQUEST_INVALID",
    ).map((entry, index) => requireExactModelId(entry, `unavailable_model_ids[${index}]`)),
  };
};

/**
 * Derive a routing decision by executing the declared, policy-approved route
 * table. Selection walks the declared fallback order, skipping unavailable
 * candidates and terminating at the safe default. Nothing about the ordering is
 * invented at call time; the route table already encodes the cost- and
 * eval-basis-driven policy.
 */
export const deriveModelRouting = (routeTableCandidate, requestCandidate) => {
  const routeTable = verifyRouteTableIntegrity(routeTableCandidate);
  const request = normalizeRoutingRequest(requestCandidate);

  if (!OBJECT_HAS_OWN(routeTable.task_classes, request.task_class)) {
    fail("UNDECLARED_TASK_CLASS", "routing input names a task class the route table does not declare", {
      task_class: request.task_class,
    });
  }
  const entry = routeTable.task_classes[request.task_class];
  const routeOrder = entry.route_order;
  const eligibleModelIds = routeOrder.map((candidate) => candidate.model_id);
  const eligibleSet = new Set(eligibleModelIds);

  const unavailableSet = new Set();
  for (const modelId of request.unavailable_model_ids) {
    if (!eligibleSet.has(modelId)) {
      fail(
        "UNKNOWN_ROUTE_CANDIDATE",
        "routing input marks a model unavailable that the task class does not route",
        { model_id: modelId, task_class: request.task_class },
      );
    }
    unavailableSet.add(modelId);
  }

  const safeDefault = routeOrder[routeOrder.length - 1];
  if (unavailableSet.has(safeDefault.model_id)) {
    fail(
      "SAFE_DEFAULT_UNAVAILABLE",
      "the terminal safe default may never be marked unavailable; routing must always terminate",
      { safe_default_model_id: safeDefault.model_id },
    );
  }

  let selectedIndex = -1;
  const fallbackChain = [];
  for (let index = 0; index < routeOrder.length; index += 1) {
    const candidate = routeOrder[index];
    if (unavailableSet.has(candidate.model_id)) {
      fallbackChain.push({
        model_id: candidate.model_id,
        model_tier: candidate.model_tier,
        reason: "UNAVAILABLE",
      });
      continue;
    }
    selectedIndex = index;
    break;
  }

  const selected = routeOrder[selectedIndex];
  const fallbackUsed = selectedIndex > 0;
  const fallbackPolicyDecisionId = fallbackUsed
    ? `${FALLBACK_DECISION_ID_PREFIX}${sha256RoutingJson({
        route_table_hash: routeTable.route_table_hash,
        task_class: request.task_class,
        selected_model_id: selected.model_id,
        skipped_model_ids: fallbackChain.map((step) => step.model_id),
      }).slice("sha256:".length)}`
    : null;

  const receipt = buildRoutingReceipt({
    task_class: request.task_class,
    eligible_model_ids: eligibleModelIds,
    selected_model_id: selected.model_id,
    policy: entry.policy,
    reward_basis: entry.reward_basis,
    estimated_cost: selected.estimated_cost,
    estimated_latency_ms: selected.estimated_latency_ms,
    exploration_probability: entry.exploration_probability,
    safety_constraints: entry.safety_constraints,
  });

  const decisionPreimage = {
    route_table_id: routeTable.route_table_id,
    route_table_hash: routeTable.route_table_hash,
    task_class: request.task_class,
    policy: entry.policy,
    reward_basis: entry.reward_basis,
    eligible_model_ids: eligibleModelIds,
    requested_unavailable_model_ids: [...request.unavailable_model_ids].sort(compareUtf8),
    selected_model_id: selected.model_id,
    selected_model_tier: selected.model_tier,
    selected_provider_id: selected.provider_id,
    selected_route_index: selectedIndex,
    fallback_used: fallbackUsed,
    fallback_chain: fallbackChain,
    safe_default_model_id: safeDefault.model_id,
    fallback_policy_decision_id: fallbackPolicyDecisionId,
    receipt,
  };
  const decisionHash = sha256RoutingJson(decisionPreimage);
  return deepFreeze({
    routing_decision_id: `${ROUTING_DECISION_ID_PREFIX}${decisionHash.slice("sha256:".length)}`,
    ...canonicalClone(decisionPreimage),
    routing_decision_hash: decisionHash,
  });
};

export const ROUTE_TABLE_REQUIRED_FIELDS = ROUTE_TABLE_FIELDS;
export const MODEL_ROUTING_RECEIPT_FIELDS = RECEIPT_FIELDS;
export const ROUTING_DECISION_REQUIRED_FIELDS = DECISION_FIELDS;
export const FALLBACK_STEP_REQUIRED_FIELDS = FALLBACK_STEP_FIELDS;
