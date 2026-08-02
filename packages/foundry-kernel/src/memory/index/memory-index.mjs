/**
 * Deterministic L02 memory index, scoped search, and retrieval receipt.
 *
 * L01 remains the policy authority. A query class is prospectively admitted
 * before its store is opened, and every candidate record is evaluated again
 * with its real creation time before its search text is inspected. L02 does
 * not redact, deduplicate, delete, forget, or implement legal hold; L03 owns
 * those transformations. The receipt builder accepts only a ranked subset of
 * the raw L02 hits so L03 can later finalize the same canonical contract.
 */

import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

import {
  MEMORY_CLASSES,
  MemoryPolicyError,
  canonicalMemoryPolicyJson,
  evaluateMemoryAccess,
  validateConsentRecord,
  validateMemoryPolicy,
} from "../policy/index.mjs";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;

const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|([+-])(\d{2}):(\d{2}))$/u;
const TOKEN_PATTERN = /[\p{L}\p{N}]+/gu;
const MEMORY_CLASS_SET = new Set(MEMORY_CLASSES);
const MEMORY_CLASS_RANK = new Map(MEMORY_CLASSES.map((value, index) => [value, index]));

export const MEMORY_INDEX_VERSION = "4.0.0-l02.1";
export const MEMORY_QUERY_ALGORITHM = "unicode_nfkc_token_overlap_v1";
export const MAX_MEMORY_RESULTS = 200;
export const RETRIEVABLE_MEMORY_CLASSES = OBJECT_FREEZE([
  "SESSION",
  "WORKSPACE",
  "USER",
  "EVIDENCE",
]);
const RETRIEVABLE_MEMORY_CLASS_SET = new Set(RETRIEVABLE_MEMORY_CLASSES);

export const MEMORY_SEARCH_STATUSES = OBJECT_FREEZE({
  SEARCHED_NONE: "SEARCHED_NONE",
  SEARCHED_WITH_HITS: "SEARCHED_WITH_HITS",
});
const MEMORY_SEARCH_STATUS_SET = new Set(Object.values(MEMORY_SEARCH_STATUSES));

const RECORD_FIELDS = OBJECT_FREEZE([
  "memory_id",
  "class",
  "workspace_id",
  "search_text",
  "source_hash",
  "created_at",
]);
const STORE_FIELDS = OBJECT_FREEZE(["class", "record_count", "records", "store_hash"]);
const INDEX_FIELDS = OBJECT_FREEZE([
  "index_id",
  "index_version",
  "stores",
  "index_hash",
]);
const REQUEST_FIELDS = OBJECT_FREEZE([
  "query",
  "workspace_id",
  "target_workspace_id",
  "purpose",
  "data_class",
  "requested_classes",
  "policy",
  "consent_record",
  "evaluated_at",
  "cross_workspace_opt_in",
  "limit",
  "context_capsule_id",
]);
const PLAN_FIELDS = OBJECT_FREEZE([
  "algorithm",
  "query",
  "query_hash",
  "workspace_id",
  "target_workspace_id",
  "purpose",
  "data_class",
  "searched_classes",
  "excluded_classes",
  "policy_hash",
  "consent_id",
  "evaluated_at",
  "cross_workspace",
  "limit",
  "context_capsule_id",
  "plan_hash",
]);
const HIT_FIELDS = OBJECT_FREEZE([
  "memory_id",
  "class",
  "score",
  "source_hash",
  "redacted",
]);
const EXECUTION_FIELDS = OBJECT_FREEZE([
  "status",
  "plan",
  "hits",
  "policy_excluded_memory_ids",
  "uncapped_match_count",
  "execution_hash",
]);
const RECEIPT_INPUT_FIELDS = OBJECT_FREEZE([
  "search_execution",
  "selected_hits",
  "redaction_count",
  "retrieved_at",
]);
const SEARCH_INPUT_FIELDS = OBJECT_FREEZE(["index", "request"]);
const RECEIPT_FIELDS = OBJECT_FREEZE([
  "receipt_id",
  "query",
  "workspace_id",
  "purpose",
  "searched_classes",
  "excluded_classes",
  "hits",
  "redaction_count",
  "consent_id",
  "context_capsule_id",
  "retrieved_at",
  "result_hash",
]);

export class MemoryIndexError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "MemoryIndexError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze({ ...details });
  }
}

const fail = (code, message, details) => {
  throw new MemoryIndexError(code, message, details);
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

const requireNullableIdentifier = (value, label, code = "INVALID_INPUT") =>
  value === null ? null : requireIdentifier(value, label, code);

const requireNonNegativeInteger = (value, label, code = "INVALID_INPUT") => {
  if (!Number.isSafeInteger(value) || value < 0) {
    fail(code, `${label} must be a non-negative safe integer`);
  }
  return value;
};

const requireSha256 = (value, label, code = "INVALID_INPUT") => {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) {
    fail(code, `${label} must be sha256:<64 lowercase hex>`);
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

const requireMemoryClass = (value, label, code = "UNKNOWN_MEMORY_CLASS") => {
  if (typeof value !== "string" || !MEMORY_CLASS_SET.has(value)) {
    fail(code, `${label} is not a canonical memory class`, { value });
  }
  return value;
};

const requireCanonicalClassSet = (value, label, { minItems = 1 } = {}) => {
  const result = readDenseArray(value, label).map((entry, index) =>
    requireMemoryClass(entry, `${label}[${index}]`),
  );
  if (result.length < minItems) fail("MEMORY_SCOPE_EMPTY", `${label} must not be empty`);
  if (new Set(result).size !== result.length) fail("MEMORY_SCOPE_DUPLICATE", `${label} has duplicates`);
  result.sort((left, right) => MEMORY_CLASS_RANK.get(left) - MEMORY_CLASS_RANK.get(right));
  return OBJECT_FREEZE(result);
};

const compareStrings = (left, right) => (left < right ? -1 : left > right ? 1 : 0);

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

export const canonicalMemoryIndexJson = (value) => canonicalMemoryPolicyJson(value);

const sha256CanonicalJson = (value) =>
  `sha256:${createHash("sha256").update(canonicalMemoryIndexJson(value), "utf8").digest("hex")}`;

const normalizeRecord = (candidate, label = "MemoryRecord") => {
  const code = "MEMORY_RECORD_INVALID";
  const record = requirePlainDataObject(candidate, label, RECORD_FIELDS, code);
  return canonicalClone({
    memory_id: requireIdentifier(readDataProperty(record, "memory_id"), `${label}.memory_id`, code),
    class: requireMemoryClass(readDataProperty(record, "class"), `${label}.class`),
    workspace_id: requireIdentifier(
      readDataProperty(record, "workspace_id"),
      `${label}.workspace_id`,
      code,
    ),
    search_text: requireString(readDataProperty(record, "search_text"), `${label}.search_text`, {
      maxLength: 1_000_000,
      code,
    }),
    source_hash: requireSha256(readDataProperty(record, "source_hash"), `${label}.source_hash`, code),
    created_at: requireTimestamp(readDataProperty(record, "created_at"), `${label}.created_at`, code),
  });
};

const storePreimage = (memoryClass, records) => ({ class: memoryClass, records });

const buildStore = (memoryClass, records) => {
  const normalized = records
    .map((record, index) => normalizeRecord(record, `${memoryClass}.records[${index}]`))
    .sort((left, right) =>
      compareStrings(left.workspace_id, right.workspace_id) ||
      compareStrings(left.memory_id, right.memory_id) ||
      compareStrings(left.source_hash, right.source_hash),
    );
  return canonicalClone({
    class: memoryClass,
    record_count: normalized.length,
    records: normalized,
    store_hash: sha256CanonicalJson(storePreimage(memoryClass, normalized)),
  });
};

const indexPreimage = (stores) => ({
  index_version: MEMORY_INDEX_VERSION,
  stores: MEMORY_CLASSES.map((memoryClass) => ({
    class: memoryClass,
    record_count: stores[memoryClass].record_count,
    store_hash: stores[memoryClass].store_hash,
  })),
});

export const buildMemoryIndex = (candidateRecords) => {
  const records = readDenseArray(candidateRecords, "records", "MEMORY_INDEX_INVALID");
  const normalized = records.map((record, index) => normalizeRecord(record, `records[${index}]`));
  const memoryIds = normalized.map((record) => record.memory_id);
  if (new Set(memoryIds).size !== memoryIds.length) {
    fail("DUPLICATE_MEMORY_ID", "memory_id must be globally unique in one index");
  }
  const stores = {};
  for (const memoryClass of MEMORY_CLASSES) {
    stores[memoryClass] = buildStore(
      memoryClass,
      normalized.filter((record) => record.class === memoryClass),
    );
  }
  const preimage = indexPreimage(stores);
  const indexHash = sha256CanonicalJson(preimage);
  return canonicalClone({
    index_id: `MIDX-${indexHash.slice("sha256:".length)}`,
    index_version: MEMORY_INDEX_VERSION,
    stores,
    index_hash: indexHash,
  });
};

const validateStoreEnvelope = (candidate, memoryClass) => {
  const code = "MEMORY_INDEX_INVALID";
  const store = requirePlainDataObject(candidate, `stores.${memoryClass}`, STORE_FIELDS, code);
  const declaredClass = requireMemoryClass(readDataProperty(store, "class"), `stores.${memoryClass}.class`, code);
  if (declaredClass !== memoryClass) fail(code, `stores.${memoryClass}.class does not match its key`);
  const records = readDataProperty(store, "records");
  if (!ARRAY_IS_ARRAY(records) || IS_PROXY(records) || OBJECT_GET_PROTOTYPE_OF(records) !== Array.prototype) {
    fail(code, `stores.${memoryClass}.records must be a plain array`);
  }
  const recordCount = requireNonNegativeInteger(
    readDataProperty(store, "record_count"),
    `stores.${memoryClass}.record_count`,
    code,
  );
  if (records.length !== recordCount) fail(code, `stores.${memoryClass}.record_count mismatch`);
  return {
    class: memoryClass,
    record_count: recordCount,
    records,
    store_hash: requireSha256(
      readDataProperty(store, "store_hash"),
      `stores.${memoryClass}.store_hash`,
      code,
    ),
  };
};

const validateIndexEnvelope = (candidate) => {
  const code = "MEMORY_INDEX_INVALID";
  const index = requirePlainDataObject(candidate, "MemoryIndex", INDEX_FIELDS, code);
  const indexVersion = readDataProperty(index, "index_version");
  if (indexVersion !== MEMORY_INDEX_VERSION) fail(code, "unsupported memory index version");
  const storesCandidate = readDataProperty(index, "stores");
  const stores = requirePlainDataObject(storesCandidate, "stores", MEMORY_CLASSES, code);
  const storeEnvelopes = {};
  for (const memoryClass of MEMORY_CLASSES) {
    storeEnvelopes[memoryClass] = validateStoreEnvelope(
      readDataProperty(stores, memoryClass),
      memoryClass,
    );
  }
  const indexHash = requireSha256(readDataProperty(index, "index_hash"), "index_hash", code);
  const expectedIndexHash = sha256CanonicalJson(indexPreimage(storeEnvelopes));
  if (indexHash !== expectedIndexHash) {
    fail("MEMORY_INDEX_HASH_MISMATCH", "index_hash does not match store inventory", {
      actual: indexHash,
      expected: expectedIndexHash,
    });
  }
  const indexId = requireIdentifier(readDataProperty(index, "index_id"), "index_id", code);
  if (indexId !== `MIDX-${indexHash.slice("sha256:".length)}`) {
    fail("MEMORY_INDEX_ID_MISMATCH", "index_id does not match index_hash");
  }
  return { index_id: indexId, index_version: indexVersion, stores: storeEnvelopes, index_hash: indexHash };
};

const validateSelectedStore = (store) => {
  const records = readDenseArray(store.records, `stores.${store.class}.records`, "MEMORY_INDEX_INVALID")
    .map((record, index) => normalizeRecord(record, `stores.${store.class}.records[${index}]`));
  if (records.some((record) => record.class !== store.class)) {
    fail("MEMORY_STORE_CLASS_MISMATCH", "a store contains a record from another class");
  }
  const canonicalOrder = [...records].sort((left, right) =>
    compareStrings(left.workspace_id, right.workspace_id) ||
    compareStrings(left.memory_id, right.memory_id) ||
    compareStrings(left.source_hash, right.source_hash),
  );
  if (records.some((record, index) => record !== canonicalOrder[index])) {
    fail("MEMORY_STORE_ORDER_INVALID", "memory store records are not in canonical order");
  }
  const expected = sha256CanonicalJson(storePreimage(store.class, records));
  if (store.store_hash !== expected) {
    fail("MEMORY_STORE_HASH_MISMATCH", "selected memory store hash mismatch", {
      memory_class: store.class,
      actual: store.store_hash,
      expected,
    });
  }
  return OBJECT_FREEZE(records);
};

export const validateMemoryIndex = (candidate) => {
  const envelope = validateIndexEnvelope(candidate);
  const records = [];
  for (const memoryClass of MEMORY_CLASSES) {
    records.push(...validateSelectedStore(envelope.stores[memoryClass]));
  }
  const memoryIds = records.map((record) => record.memory_id);
  if (new Set(memoryIds).size !== memoryIds.length) {
    fail("DUPLICATE_MEMORY_ID", "memory_id must be globally unique in one index");
  }
  const rebuilt = buildMemoryIndex(records);
  if (rebuilt.index_hash !== envelope.index_hash || rebuilt.index_id !== envelope.index_id) {
    fail("MEMORY_INDEX_REBUILD_MISMATCH", "memory index differs from its canonical rebuild");
  }
  return rebuilt;
};

const normalizeRequest = (candidate) => {
  const code = "MEMORY_QUERY_REQUEST_INVALID";
  const request = requirePlainDataObject(candidate, "MemoryQueryRequest", REQUEST_FIELDS, code);
  const crossWorkspaceOptIn = readDataProperty(request, "cross_workspace_opt_in");
  if (typeof crossWorkspaceOptIn !== "boolean") {
    fail(code, "cross_workspace_opt_in must be boolean");
  }
  const limit = readDataProperty(request, "limit");
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_MEMORY_RESULTS) {
    fail("MEMORY_RESULT_CAP_INVALID", `limit must be an integer from 1 through ${MAX_MEMORY_RESULTS}`);
  }
  const policy = validateMemoryPolicy(readDataProperty(request, "policy"));
  const consentCandidate = readDataProperty(request, "consent_record");
  const consent = consentCandidate === null ? null : validateConsentRecord(consentCandidate);
  return {
    query: requireString(readDataProperty(request, "query"), "query", { maxLength: 4096, code }),
    workspace_id: requireIdentifier(readDataProperty(request, "workspace_id"), "workspace_id", code),
    target_workspace_id: requireIdentifier(
      readDataProperty(request, "target_workspace_id"),
      "target_workspace_id",
      code,
    ),
    purpose: requireString(readDataProperty(request, "purpose"), "purpose", { maxLength: 512, code }),
    data_class: requireString(readDataProperty(request, "data_class"), "data_class", {
      maxLength: 256,
      code,
    }),
    requested_classes: requireCanonicalClassSet(
      readDataProperty(request, "requested_classes"),
      "requested_classes",
    ),
    policy,
    consent_record: consent,
    evaluated_at: requireTimestamp(readDataProperty(request, "evaluated_at"), "evaluated_at", code),
    cross_workspace_opt_in: crossWorkspaceOptIn,
    limit,
    context_capsule_id: requireNullableIdentifier(
      readDataProperty(request, "context_capsule_id"),
      "context_capsule_id",
      code,
    ),
  };
};

const policyEvaluation = (request, memoryClass, memoryCreatedAt) => ({
  policy: request.policy,
  request: {
    workspace_id: request.workspace_id,
    target_workspace_id: request.target_workspace_id,
    memory_class: memoryClass,
    purpose: request.purpose,
    data_class: request.data_class,
    scope: memoryClass,
    memory_created_at: memoryCreatedAt,
    evaluated_at: request.evaluated_at,
    cross_workspace_opt_in: request.cross_workspace_opt_in,
  },
  consent_record: request.consent_record,
});

const prospectiveDecision = (request, memoryClass) => {
  let decision;
  try {
    decision = evaluateMemoryAccess(policyEvaluation(request, memoryClass, request.evaluated_at));
  } catch (error) {
    if (error instanceof MemoryPolicyError) {
      fail("MEMORY_POLICY_INVALID", "L01 rejected the memory policy or consent artifact", {
        cause_code: error.code,
      });
    }
    throw error;
  }
  if (decision.decision !== "ALLOW") {
    fail("MEMORY_SCOPE_DENIED", "L01 denied the requested memory class before store search", {
      memory_class: memoryClass,
      reason_code: decision.reason_code,
    });
  }
  return decision;
};

const planPreimage = (value) => {
  const { plan_hash: _ignored, ...preimage } = value;
  return preimage;
};

export const compileMemoryQuery = (candidate) => {
  const request = normalizeRequest(candidate);
  const queryTokens = tokenize(request.query);
  if (queryTokens.length === 0) {
    fail("MEMORY_QUERY_EMPTY", "query must contain at least one Unicode letter or number");
  }
  const decisions = request.requested_classes.map((memoryClass) =>
    prospectiveDecision(request, memoryClass),
  );
  const nonRetrievableClass = request.requested_classes.find(
    (memoryClass) => !RETRIEVABLE_MEMORY_CLASS_SET.has(memoryClass),
  );
  if (nonRetrievableClass !== undefined) {
    fail(
      "MEMORY_STORE_NOT_RETRIEVABLE",
      "the memory recall workflow may search only session, workspace, user, or evidence stores",
      { memory_class: nonRetrievableClass },
    );
  }
  const consentIds = [...new Set(decisions.map((decision) => decision.consent_id).filter(Boolean))];
  if (consentIds.length > 1) {
    fail("MEMORY_RECEIPT_CONSENT_AMBIGUOUS", "one retrieval receipt cannot bind multiple consent IDs");
  }
  const excludedClasses = MEMORY_CLASSES.filter(
    (memoryClass) => !request.requested_classes.includes(memoryClass),
  );
  const base = {
    algorithm: MEMORY_QUERY_ALGORITHM,
    query: request.query,
    query_hash: sha256CanonicalJson({ query: request.query }),
    workspace_id: request.workspace_id,
    target_workspace_id: request.target_workspace_id,
    purpose: request.purpose,
    data_class: request.data_class,
    searched_classes: request.requested_classes,
    excluded_classes: excludedClasses,
    policy_hash: request.policy.policy_hash,
    consent_id: consentIds[0] ?? null,
    evaluated_at: request.evaluated_at,
    cross_workspace: request.workspace_id !== request.target_workspace_id,
    limit: request.limit,
    context_capsule_id: request.context_capsule_id,
  };
  return canonicalClone({ ...base, plan_hash: sha256CanonicalJson(base) });
};

const validatePlan = (candidate) => {
  const code = "MEMORY_QUERY_PLAN_INVALID";
  const plan = requirePlainDataObject(candidate, "MemoryQueryPlan", PLAN_FIELDS, code);
  if (readDataProperty(plan, "algorithm") !== MEMORY_QUERY_ALGORITHM) {
    fail(code, "memory query algorithm is not canonical");
  }
  const normalized = {
    algorithm: MEMORY_QUERY_ALGORITHM,
    query: requireString(readDataProperty(plan, "query"), "plan.query", { maxLength: 4096, code }),
    query_hash: requireSha256(readDataProperty(plan, "query_hash"), "plan.query_hash", code),
    workspace_id: requireIdentifier(readDataProperty(plan, "workspace_id"), "plan.workspace_id", code),
    target_workspace_id: requireIdentifier(
      readDataProperty(plan, "target_workspace_id"),
      "plan.target_workspace_id",
      code,
    ),
    purpose: requireString(readDataProperty(plan, "purpose"), "plan.purpose", { maxLength: 512, code }),
    data_class: requireString(readDataProperty(plan, "data_class"), "plan.data_class", {
      maxLength: 256,
      code,
    }),
    searched_classes: requireCanonicalClassSet(
      readDataProperty(plan, "searched_classes"),
      "plan.searched_classes",
    ),
    excluded_classes: requireCanonicalClassSet(
      readDataProperty(plan, "excluded_classes"),
      "plan.excluded_classes",
      { minItems: 0 },
    ),
    policy_hash: requireSha256(readDataProperty(plan, "policy_hash"), "plan.policy_hash", code),
    consent_id: requireNullableIdentifier(readDataProperty(plan, "consent_id"), "plan.consent_id", code),
    evaluated_at: requireTimestamp(readDataProperty(plan, "evaluated_at"), "plan.evaluated_at", code),
    cross_workspace: readDataProperty(plan, "cross_workspace"),
    limit: readDataProperty(plan, "limit"),
    context_capsule_id: requireNullableIdentifier(
      readDataProperty(plan, "context_capsule_id"),
      "plan.context_capsule_id",
      code,
    ),
  };
  if (typeof normalized.cross_workspace !== "boolean") fail(code, "plan.cross_workspace must be boolean");
  if (!Number.isSafeInteger(normalized.limit) || normalized.limit < 1 || normalized.limit > MAX_MEMORY_RESULTS) {
    fail(code, "plan.limit is outside the canonical result cap");
  }
  if (normalized.cross_workspace !== (normalized.workspace_id !== normalized.target_workspace_id)) {
    fail(code, "plan.cross_workspace does not match workspace identities");
  }
  const partition = [...normalized.searched_classes, ...normalized.excluded_classes];
  if (
    partition.length !== MEMORY_CLASSES.length ||
    new Set(partition).size !== MEMORY_CLASSES.length ||
    MEMORY_CLASSES.some((memoryClass) => !partition.includes(memoryClass))
  ) {
    fail("MEMORY_SCOPE_PARTITION_INVALID", "searched and excluded classes must partition the vocabulary");
  }
  if (normalized.searched_classes.some((memoryClass) => !RETRIEVABLE_MEMORY_CLASS_SET.has(memoryClass))) {
    fail(
      "MEMORY_STORE_NOT_RETRIEVABLE",
      "query plan searched_classes contains a non-retrievable memory store",
    );
  }
  const expectedQueryHash = sha256CanonicalJson({ query: normalized.query });
  if (normalized.query_hash !== expectedQueryHash) fail("MEMORY_QUERY_HASH_MISMATCH", "query_hash mismatch");
  const planHash = requireSha256(readDataProperty(plan, "plan_hash"), "plan.plan_hash", code);
  const expectedPlanHash = sha256CanonicalJson(normalized);
  if (planHash !== expectedPlanHash) fail("MEMORY_QUERY_PLAN_HASH_MISMATCH", "plan_hash mismatch");
  return canonicalClone({ ...normalized, plan_hash: planHash });
};

const tokenize = (value) => {
  const normalized = value.normalize("NFKC").toLowerCase();
  const matches = normalized.match(TOKEN_PATTERN) ?? [];
  return [...new Set(matches)].sort(compareStrings);
};

const scoreRecord = (queryTokens, searchText) => {
  const candidate = new Set(tokenize(searchText));
  let matched = 0;
  for (const token of queryTokens) if (candidate.has(token)) matched += 1;
  if (matched === 0) return 0;
  return Number((matched / queryTokens.length).toFixed(12));
};

const normalizeHit = (candidate, label = "MemoryRetrievalHit") => {
  const code = "MEMORY_RETRIEVAL_HIT_INVALID";
  const hit = requirePlainDataObject(candidate, label, HIT_FIELDS, code);
  const score = readDataProperty(hit, "score");
  if (typeof score !== "number" || !Number.isFinite(score) || score < 0 || score > 1 || Object.is(score, -0)) {
    fail(code, `${label}.score must be a finite number from 0 through 1`);
  }
  const redacted = readDataProperty(hit, "redacted");
  if (typeof redacted !== "boolean") fail(code, `${label}.redacted must be boolean`);
  return canonicalClone({
    memory_id: requireIdentifier(readDataProperty(hit, "memory_id"), `${label}.memory_id`, code),
    class: requireMemoryClass(readDataProperty(hit, "class"), `${label}.class`, code),
    score,
    source_hash: requireSha256(readDataProperty(hit, "source_hash"), `${label}.source_hash`, code),
    redacted,
  });
};

const executionPreimage = (value) => {
  const { execution_hash: _ignored, ...preimage } = value;
  return preimage;
};

const validateExecution = (candidate) => {
  const code = "MEMORY_SEARCH_EXECUTION_INVALID";
  const execution = requirePlainDataObject(candidate, "MemorySearchExecution", EXECUTION_FIELDS, code);
  const status = readDataProperty(execution, "status");
  if (!MEMORY_SEARCH_STATUS_SET.has(status)) fail(code, "search execution status is not canonical");
  const plan = validatePlan(readDataProperty(execution, "plan"));
  const hits = readDenseArray(readDataProperty(execution, "hits"), "execution.hits", code).map(
    (hit, index) => normalizeHit(hit, `execution.hits[${index}]`),
  );
  if (new Set(hits.map((hit) => hit.memory_id)).size !== hits.length) {
    fail(code, "execution hits contain duplicate memory IDs");
  }
  if (hits.some((hit) => !plan.searched_classes.includes(hit.class))) {
    fail("MEMORY_HIT_OUTSIDE_SCOPE", "execution contains a hit from an excluded class");
  }
  const canonicalHits = [...hits].sort(
    (left, right) =>
      right.score - left.score ||
      compareStrings(left.memory_id, right.memory_id) ||
      compareStrings(left.source_hash, right.source_hash),
  );
  if (hits.some((hit, index) => hit !== canonicalHits[index])) {
    fail("MEMORY_HIT_ORDER_INVALID", "execution hits are not in deterministic rank order");
  }
  const policyExcluded = readDenseArray(
    readDataProperty(execution, "policy_excluded_memory_ids"),
    "execution.policy_excluded_memory_ids",
    code,
  ).map((value, index) => requireIdentifier(value, `policy_excluded_memory_ids[${index}]`, code));
  if (new Set(policyExcluded).size !== policyExcluded.length) fail(code, "policy exclusions contain duplicates");
  if (policyExcluded.some((value, index) => value !== [...policyExcluded].sort(compareStrings)[index])) {
    fail(code, "policy exclusions are not in canonical order");
  }
  const uncappedMatchCount = requireNonNegativeInteger(
    readDataProperty(execution, "uncapped_match_count"),
    "execution.uncapped_match_count",
    code,
  );
  if (hits.length > plan.limit || hits.length > uncappedMatchCount) fail(code, "execution result count is inconsistent");
  if (
    (status === MEMORY_SEARCH_STATUSES.SEARCHED_NONE) !== (hits.length === 0) ||
    (status === MEMORY_SEARCH_STATUSES.SEARCHED_WITH_HITS) !== (hits.length > 0)
  ) {
    fail(code, "search status does not match hit count");
  }
  const normalized = {
    status,
    plan,
    hits,
    policy_excluded_memory_ids: [...policyExcluded].sort(compareStrings),
    uncapped_match_count: uncappedMatchCount,
  };
  const executionHash = requireSha256(
    readDataProperty(execution, "execution_hash"),
    "execution.execution_hash",
    code,
  );
  if (executionHash !== sha256CanonicalJson(normalized)) {
    fail("MEMORY_SEARCH_EXECUTION_HASH_MISMATCH", "execution_hash mismatch");
  }
  return canonicalClone({ ...normalized, execution_hash: executionHash });
};

export const executeMemorySearch = (candidate) => {
  const input = requirePlainDataObject(
    candidate,
    "MemorySearchInput",
    SEARCH_INPUT_FIELDS,
    "MEMORY_SEARCH_INPUT_INVALID",
  );
  const indexCandidate = readDataProperty(input, "index");
  const requestCandidate = readDataProperty(input, "request");
  const request = normalizeRequest(requestCandidate);
  const plan = compileMemoryQuery(requestCandidate);
  const index = validateIndexEnvelope(indexCandidate);
  const queryTokens = tokenize(plan.query);
  const matches = [];
  const policyExcluded = [];
  const seenIds = new Set();

  for (const memoryClass of plan.searched_classes) {
    const records = validateSelectedStore(index.stores[memoryClass]);
    for (const record of records) {
      if (record.workspace_id !== plan.target_workspace_id) continue;
      if (seenIds.has(record.memory_id)) {
        fail("DUPLICATE_MEMORY_ID", "selected stores contain duplicate memory IDs");
      }
      seenIds.add(record.memory_id);
      const access = evaluateMemoryAccess(policyEvaluation(request, memoryClass, record.created_at));
      if (access.decision !== "ALLOW") {
        policyExcluded.push(record.memory_id);
        continue;
      }
      const score = scoreRecord(queryTokens, record.search_text);
      if (score === 0) continue;
      matches.push({
        memory_id: record.memory_id,
        class: record.class,
        score,
        source_hash: record.source_hash,
        redacted: false,
      });
    }
  }

  matches.sort(
    (left, right) =>
      right.score - left.score ||
      compareStrings(left.memory_id, right.memory_id) ||
      compareStrings(left.source_hash, right.source_hash),
  );
  const uncappedMatchCount = matches.length;
  const hits = matches.slice(0, plan.limit);
  const status =
    hits.length === 0
      ? MEMORY_SEARCH_STATUSES.SEARCHED_NONE
      : MEMORY_SEARCH_STATUSES.SEARCHED_WITH_HITS;
  const base = {
    status,
    plan,
    hits,
    policy_excluded_memory_ids: [...policyExcluded].sort(compareStrings),
    uncapped_match_count: uncappedMatchCount,
  };
  return canonicalClone({ ...base, execution_hash: sha256CanonicalJson(base) });
};

const selectedHitKey = (hit) =>
  `${hit.memory_id}\u0000${hit.class}\u0000${String(hit.score)}\u0000${hit.source_hash}`;

const receiptIdentityPreimage = (base) => ({
  query: base.query,
  workspace_id: base.workspace_id,
  purpose: base.purpose,
  searched_classes: base.searched_classes,
  excluded_classes: base.excluded_classes,
  hits: base.hits,
  redaction_count: base.redaction_count,
  consent_id: base.consent_id,
  context_capsule_id: base.context_capsule_id,
  retrieved_at: base.retrieved_at,
});

export const emitMemoryRetrievalReceipt = (candidate) => {
  const code = "MEMORY_RETRIEVAL_RECEIPT_INPUT_INVALID";
  const input = requirePlainDataObject(candidate, "MemoryRetrievalReceiptInput", RECEIPT_INPUT_FIELDS, code);
  const execution = validateExecution(readDataProperty(input, "search_execution"));
  const selectedHits = readDenseArray(
    readDataProperty(input, "selected_hits"),
    "selected_hits",
    code,
  ).map((hit, index) => normalizeHit(hit, `selected_hits[${index}]`));
  if (new Set(selectedHits.map((hit) => hit.memory_id)).size !== selectedHits.length) {
    fail(code, "selected_hits contain duplicate memory IDs");
  }
  const available = new Map(execution.hits.map((hit) => [selectedHitKey(hit), hit]));
  let previousIndex = -1;
  for (const hit of selectedHits) {
    const key = selectedHitKey({ ...hit, redacted: false });
    if (!available.has(key)) {
      fail("MEMORY_RECEIPT_HIT_NOT_SEARCHED", "receipt hit was not produced by the scoped search", {
        memory_id: hit.memory_id,
      });
    }
    const index = execution.hits.findIndex((raw) => selectedHitKey(raw) === key);
    if (index <= previousIndex) {
      fail("MEMORY_RECEIPT_HIT_ORDER_INVALID", "selected hits must preserve deterministic search order");
    }
    previousIndex = index;
  }
  const redactionCount = requireNonNegativeInteger(
    readDataProperty(input, "redaction_count"),
    "redaction_count",
    code,
  );
  if (redactionCount < selectedHits.filter((hit) => hit.redacted).length) {
    fail(code, "redaction_count cannot be lower than the number of redacted hits");
  }
  const retrievedAt = requireTimestamp(readDataProperty(input, "retrieved_at"), "retrieved_at", code);
  if (retrievedAt !== execution.plan.evaluated_at) {
    fail("MEMORY_RETRIEVAL_TIME_MISMATCH", "retrieved_at must equal the policy evaluation time");
  }
  const base = receiptIdentityPreimage({
    query: execution.plan.query,
    workspace_id: execution.plan.workspace_id,
    purpose: execution.plan.purpose,
    searched_classes: execution.plan.searched_classes,
    excluded_classes: execution.plan.excluded_classes,
    hits: selectedHits,
    redaction_count: redactionCount,
    consent_id: execution.plan.consent_id,
    context_capsule_id: execution.plan.context_capsule_id,
    retrieved_at: retrievedAt,
  });
  const identityHash = sha256CanonicalJson(base);
  const withId = { receipt_id: `MRR-${identityHash.slice("sha256:".length)}`, ...base };
  return canonicalClone({ ...withId, result_hash: sha256CanonicalJson(withId) });
};

export const validateMemoryRetrievalReceipt = (candidate) => {
  const code = "MEMORY_RETRIEVAL_RECEIPT_INVALID";
  const receipt = requirePlainDataObject(candidate, "MemoryRetrievalReceipt", RECEIPT_FIELDS, code);
  const normalized = {
    receipt_id: requireIdentifier(readDataProperty(receipt, "receipt_id"), "receipt_id", code),
    query: requireString(readDataProperty(receipt, "query"), "query", { maxLength: 4096, code }),
    workspace_id: requireIdentifier(readDataProperty(receipt, "workspace_id"), "workspace_id", code),
    purpose: requireString(readDataProperty(receipt, "purpose"), "purpose", { maxLength: 512, code }),
    searched_classes: requireCanonicalClassSet(
      readDataProperty(receipt, "searched_classes"),
      "searched_classes",
    ),
    excluded_classes: requireCanonicalClassSet(
      readDataProperty(receipt, "excluded_classes"),
      "excluded_classes",
      { minItems: 0 },
    ),
    hits: readDenseArray(readDataProperty(receipt, "hits"), "hits", code).map((hit, index) =>
      normalizeHit(hit, `hits[${index}]`),
    ),
    redaction_count: requireNonNegativeInteger(
      readDataProperty(receipt, "redaction_count"),
      "redaction_count",
      code,
    ),
    consent_id: requireNullableIdentifier(readDataProperty(receipt, "consent_id"), "consent_id", code),
    context_capsule_id: requireNullableIdentifier(
      readDataProperty(receipt, "context_capsule_id"),
      "context_capsule_id",
      code,
    ),
    retrieved_at: requireTimestamp(readDataProperty(receipt, "retrieved_at"), "retrieved_at", code),
  };
  const partition = [...normalized.searched_classes, ...normalized.excluded_classes];
  if (
    partition.length !== MEMORY_CLASSES.length ||
    new Set(partition).size !== MEMORY_CLASSES.length ||
    MEMORY_CLASSES.some((memoryClass) => !partition.includes(memoryClass))
  ) {
    fail("MEMORY_SCOPE_PARTITION_INVALID", "receipt searched/excluded classes must partition vocabulary");
  }
  if (normalized.searched_classes.some((memoryClass) => !RETRIEVABLE_MEMORY_CLASS_SET.has(memoryClass))) {
    fail(
      "MEMORY_STORE_NOT_RETRIEVABLE",
      "receipt searched_classes contains a non-retrievable memory store",
    );
  }
  if (normalized.hits.some((hit) => !normalized.searched_classes.includes(hit.class))) {
    fail("MEMORY_HIT_OUTSIDE_SCOPE", "receipt contains a hit from an excluded class");
  }
  if (new Set(normalized.hits.map((hit) => hit.memory_id)).size !== normalized.hits.length) {
    fail(code, "receipt hits contain duplicate memory IDs");
  }
  const canonicalHits = [...normalized.hits].sort(
    (left, right) =>
      right.score - left.score ||
      compareStrings(left.memory_id, right.memory_id) ||
      compareStrings(left.source_hash, right.source_hash),
  );
  if (normalized.hits.some((hit, index) => hit !== canonicalHits[index])) {
    fail("MEMORY_HIT_ORDER_INVALID", "receipt hits are not in deterministic rank order");
  }
  if (normalized.redaction_count < normalized.hits.filter((hit) => hit.redacted).length) {
    fail(code, "redaction_count is lower than the number of redacted hits");
  }
  const identityBase = receiptIdentityPreimage(normalized);
  const expectedReceiptId = `MRR-${sha256CanonicalJson(identityBase).slice("sha256:".length)}`;
  if (normalized.receipt_id !== expectedReceiptId) {
    fail("MEMORY_RETRIEVAL_RECEIPT_ID_MISMATCH", "receipt_id does not match receipt identity");
  }
  const resultHash = requireSha256(readDataProperty(receipt, "result_hash"), "result_hash", code);
  if (resultHash !== sha256CanonicalJson(normalized)) {
    fail("MEMORY_RETRIEVAL_RECEIPT_HASH_MISMATCH", "result_hash does not match receipt content");
  }
  return canonicalClone({ ...normalized, result_hash: resultHash });
};

export const retrievePermittedMemory = (candidate) => {
  const input = requirePlainDataObject(
    candidate,
    "MemoryRetrievalInput",
    SEARCH_INPUT_FIELDS,
    "MEMORY_RETRIEVAL_INPUT_INVALID",
  );
  const index = readDataProperty(input, "index");
  const request = readDataProperty(input, "request");
  const searchExecution = executeMemorySearch({ index, request });
  const receipt = emitMemoryRetrievalReceipt({
    search_execution: searchExecution,
    selected_hits: searchExecution.hits,
    redaction_count: 0,
    retrieved_at: searchExecution.plan.evaluated_at,
  });
  return canonicalClone({ search_execution: searchExecution, receipt });
};
