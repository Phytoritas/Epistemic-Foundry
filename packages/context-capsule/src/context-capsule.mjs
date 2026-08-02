import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

import { contractByTitle } from "@epistemic-foundry/contracts";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;

const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:Z|([+-])(\d{2}):(\d{2}))$/u;
const PHASES = OBJECT_FREEZE(["IDLE", "I", "F", "O", "R", "G", "E"]);
const PHASE_SET = new Set(PHASES);
const DISPOSITIONS = new Set(["INCLUDE", "EXCLUDE"]);

const CAPSULE_FIELDS = OBJECT_FREEZE([
  "capsule_id",
  "session_id",
  "phase",
  "purpose",
  "run_spec_hash",
  "policy_hash",
  "artifact_ids",
  "summaries",
  "open_blockers",
  "excluded_artifact_ids",
  "allowed_capabilities",
  "token_budget",
  "created_at",
  "expires_at",
  "capsule_hash",
]);
const CAPSULE_PREIMAGE_FIELDS = OBJECT_FREEZE(
  CAPSULE_FIELDS.filter((field) => field !== "capsule_hash"),
);
const SNAPSHOT_FIELDS = OBJECT_FREEZE([
  "capsule_id",
  "session_id",
  "phase",
  "purpose",
  "run_spec_hash",
  "policy_hash",
  "artifact_selections",
  "open_blockers",
  "allowed_capabilities",
  "token_budget",
  "created_at",
  "expires_at",
]);
const SELECTION_FIELDS = OBJECT_FREEZE([
  "artifact_id",
  "disposition",
  "source_hash",
  "summary",
]);
const SUMMARY_FIELDS = OBJECT_FREEZE([
  "artifact_id",
  "summary",
  "source_hash",
  "summary_hash",
]);
const FRESHNESS_FIELDS = OBJECT_FREEZE([
  "session_id",
  "phase",
  "run_spec_hash",
  "policy_hash",
  "current_artifacts",
  "now",
]);
const CURRENT_ARTIFACT_FIELDS = OBJECT_FREEZE(["artifact_id", "content_hash"]);

const compareUtf8 = (left, right) =>
  Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));

export const CONTEXT_CAPSULE_SCHEMA_ID =
  "https://epistemic-foundry.local/schemas/context-capsule.schema.json";

export class ContextCapsuleError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "ContextCapsuleError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(canonicalClone(details));
  }
}

const fail = (code, message, details = undefined) => {
  throw new ContextCapsuleError(code, message, details);
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
  { allowEmpty = false, minLength = undefined, maxLength = undefined } = {},
) => {
  const length = typeof value === "string" ? [...value].length : undefined;
  if (
    typeof value !== "string" ||
    !hasOnlyUnicodeScalars(value) ||
    (!allowEmpty && length === 0) ||
    (minLength !== undefined && length < minLength) ||
    (maxLength !== undefined && length > maxLength)
  ) {
    fail("INVALID_INPUT", `${label} must be a bounded Unicode scalar string`);
  }
  return value;
};

const requireId = (value, label) =>
  requireString(value, label, { minLength: 3, maxLength: 128 });

const requireHash = (value, label) => {
  const hash = requireString(value, label);
  if (!SHA256_PATTERN.test(hash)) {
    fail("INVALID_HASH", `${label} must be a lowercase sha256 digest`);
  }
  return hash;
};

const requirePlainDataObject = (
  value,
  label,
  { allowedFields, requiredFields = allowedFields },
) => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value)
  ) {
    fail("INVALID_INPUT", `${label} must be a non-proxy plain data object`);
  }
  const prototype = OBJECT_GET_PROTOTYPE_OF(value);
  if (prototype !== Object.prototype && prototype !== null) {
    fail("INVALID_INPUT", `${label} must not have a custom prototype`);
  }
  const allowed = new Set(allowedFields);
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (typeof key !== "string" || !allowed.has(key)) {
      fail("UNEXPECTED_FIELD", `${label} contains unsupported field ${String(key)}`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail("ACCESSOR_FIELD_DENIED", `${label}.${String(key)} must be an enumerable data field`);
    }
  }
  for (const key of requiredFields) {
    if (!OBJECT_HAS_OWN(value, key)) {
      fail("MISSING_FIELD", `${label}.${key} is required`);
    }
  }
  return value;
};

const readDataProperty = (record, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(record, key).value;

const readDenseArray = (value, label) => {
  if (!ARRAY_IS_ARRAY(value) || IS_PROXY(value)) {
    fail("INVALID_INPUT", `${label} must be a non-proxy dense array`);
  }
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
      fail("INVALID_INPUT", `${label} contains a non-element property`);
    }
    const index = Number(key);
    if (!Number.isSafeInteger(index) || index < 0 || index >= value.length) {
      fail("INVALID_INPUT", `${label} contains a non-canonical array index`);
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
      fail("INVALID_INPUT", `${label} must not be sparse or accessor-backed`);
    }
    result[index] = descriptor.value;
  }
  return result;
};

const isLeapYear = (year) => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

const requireRfc3339 = (value, label) => {
  const timestamp = requireString(value, label);
  const match = RFC3339_PATTERN.exec(timestamp);
  if (match === null) fail("INVALID_TIMESTAMP", `${label} must be RFC 3339`);
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
    second > 59 ||
    offsetHour > 23 ||
    offsetMinute > 59 ||
    !Number.isFinite(Date.parse(timestamp))
  ) {
    fail("INVALID_TIMESTAMP", `${label} must be a real RFC 3339 instant`);
  }
  return timestamp;
};

const requirePhase = (value, label) => {
  const phase = requireString(value, label);
  if (!PHASE_SET.has(phase)) fail("INVALID_PHASE", `${label} is not a canonical FORGE phase`);
  return phase;
};

const requireNonNegativeInteger = (value, label) => {
  if (!Number.isSafeInteger(value) || value < 0) {
    fail("INVALID_INPUT", `${label} must be a non-negative safe integer`);
  }
  return value;
};

const normalizeUniqueStrings = (
  value,
  label,
  { id = false, sort = true, allowEmpty = false } = {},
) => {
  const entries = readDenseArray(value, label).map((entry, index) =>
    id
      ? requireId(entry, `${label}[${index}]`)
      : requireString(entry, `${label}[${index}]`, { allowEmpty }),
  );
  const seen = new Set();
  for (const entry of entries) {
    if (seen.has(entry)) fail("DUPLICATE_VALUE", `${label} contains duplicate ${entry}`);
    seen.add(entry);
  }
  if (sort) entries.sort(compareUtf8);
  return entries;
};

const requireCanonicalOrder = (entries, label) => {
  const sorted = [...entries].sort(compareUtf8);
  if (entries.some((entry, index) => entry !== sorted[index])) {
    fail("NON_CANONICAL_ORDER", `${label} must use ascending UTF-8 byte order`);
  }
};

const assertCanonicalJsonValue = (value, label = "value", ancestors = new WeakSet()) => {
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") {
    if (!hasOnlyUnicodeScalars(value)) fail("NON_CANONICAL_JSON", `${label} contains invalid Unicode`);
    return;
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || Object.is(value, -0)) {
      fail("NON_CANONICAL_JSON", `${label} contains a non-canonical number`);
    }
    return;
  }
  if (typeof value !== "object" || IS_PROXY(value) || ancestors.has(value)) {
    fail("NON_CANONICAL_JSON", `${label} is not canonical JSON`);
  }
  ancestors.add(value);
  try {
    if (ARRAY_IS_ARRAY(value)) {
      readDenseArray(value, label).forEach((entry, index) =>
        assertCanonicalJsonValue(entry, `${label}[${index}]`, ancestors),
      );
      return;
    }
    const prototype = OBJECT_GET_PROTOTYPE_OF(value);
    if (prototype !== Object.prototype && prototype !== null) {
      fail("NON_CANONICAL_JSON", `${label} must be a plain data object`);
    }
    for (const key of REFLECT_OWN_KEYS(value)) {
      if (typeof key !== "string") fail("NON_CANONICAL_JSON", `${label} contains a symbol key`);
      const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
      if (
        descriptor === undefined ||
        !descriptor.enumerable ||
        !OBJECT_HAS_OWN(descriptor, "value")
      ) {
        fail("NON_CANONICAL_JSON", `${label}.${key} is not an enumerable data property`);
      }
      assertCanonicalJsonValue(descriptor.value, `${label}.${key}`, ancestors);
    }
  } finally {
    ancestors.delete(value);
  }
};

export const canonicalizeContextCapsuleJson = (value) => {
  assertCanonicalJsonValue(value);
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (ARRAY_IS_ARRAY(value)) {
    return `[${value.map((entry) => canonicalizeContextCapsuleJson(entry)).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort()
    .map(
      (key) =>
        `${JSON.stringify(key)}:${canonicalizeContextCapsuleJson(readDataProperty(value, key))}`,
    )
    .join(",")}}`;
};

const sha256CanonicalJson = (value) =>
  `sha256:${createHash("sha256")
    .update(canonicalizeContextCapsuleJson(value), "utf8")
    .digest("hex")}`;

const canonicalClone = (value) => JSON.parse(canonicalizeContextCapsuleJson(value));

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

const contract = contractByTitle.get("ContextCapsule");
if (
  contract === undefined ||
  contract.schema_id !== CONTEXT_CAPSULE_SCHEMA_ID ||
  canonicalizeContextCapsuleJson([...contract.required_fields].sort()) !==
    canonicalizeContextCapsuleJson([...CAPSULE_FIELDS].sort()) ||
  canonicalizeContextCapsuleJson(contract.properties.map((entry) => entry.name).sort()) !==
    canonicalizeContextCapsuleJson([...CAPSULE_FIELDS].sort())
) {
  fail(
    "CANONICAL_CONTRACT_MISMATCH",
    "the generated ContextCapsule contract no longer matches the J03 implementation boundary",
  );
}

export const CONTEXT_CAPSULE_SCHEMA_SHA256 = contract.source_sha256;

const normalizeSelection = (candidate, index) => {
  const label = `artifact_selections[${index}]`;
  const record = requirePlainDataObject(candidate, label, {
    allowedFields: SELECTION_FIELDS,
    requiredFields: ["artifact_id", "disposition"],
  });
  const artifactId = requireId(readDataProperty(record, "artifact_id"), `${label}.artifact_id`);
  const disposition = requireString(
    readDataProperty(record, "disposition"),
    `${label}.disposition`,
  );
  if (!DISPOSITIONS.has(disposition)) {
    fail("INVALID_DISPOSITION", `${label}.disposition must be INCLUDE or EXCLUDE`);
  }
  const hasSourceHash = OBJECT_HAS_OWN(record, "source_hash");
  const hasSummary = OBJECT_HAS_OWN(record, "summary");
  if (disposition === "EXCLUDE") {
    if (hasSourceHash || hasSummary) {
      fail(
        "EXCLUDED_ARTIFACT_CONTENT_DENIED",
        `${label} must not copy excluded content or its summary into the capsule input`,
      );
    }
    return { artifactId, disposition, sourceHash: null, summary: null };
  }
  if (!hasSourceHash || !hasSummary) {
    fail(
      "UNBOUND_INCLUDED_ARTIFACT",
      `${label} must bind every included artifact to both source_hash and summary`,
    );
  }
  const summary = requireString(readDataProperty(record, "summary"), `${label}.summary`);
  if (summary.trim().length === 0) {
    fail("EMPTY_SUMMARY", `${label}.summary must contain bounded canonical-state context`);
  }
  return {
    artifactId,
    disposition,
    sourceHash: requireHash(readDataProperty(record, "source_hash"), `${label}.source_hash`),
    summary,
  };
};

const normalizeSnapshot = (candidate) => {
  const record = requirePlainDataObject(candidate, "canonicalStateSnapshot", {
    allowedFields: SNAPSHOT_FIELDS,
  });
  const selections = readDenseArray(
    readDataProperty(record, "artifact_selections"),
    "artifact_selections",
  ).map(normalizeSelection);
  const byId = new Map();
  for (const selection of selections) {
    if (byId.has(selection.artifactId)) {
      fail(
        "ARTIFACT_DISPOSITION_CONFLICT",
        `artifact ${selection.artifactId} has more than one inclusion/exclusion decision`,
      );
    }
    byId.set(selection.artifactId, selection);
  }
  selections.sort((left, right) => compareUtf8(left.artifactId, right.artifactId));
  if (!selections.some((selection) => selection.disposition === "INCLUDE")) {
    fail(
      "CANONICAL_ARTIFACT_REQUIRED",
      "a ContextCapsule must include at least one hash-bound canonical artifact",
    );
  }
  const purpose = requireString(readDataProperty(record, "purpose"), "purpose");
  if (purpose.trim().length === 0) fail("EMPTY_PURPOSE", "purpose must explain the context use");
  const createdAt = requireRfc3339(readDataProperty(record, "created_at"), "created_at");
  const expiresValue = readDataProperty(record, "expires_at");
  const expiresAt = expiresValue === null ? null : requireRfc3339(expiresValue, "expires_at");
  if (expiresAt !== null && Date.parse(expiresAt) <= Date.parse(createdAt)) {
    fail("INVALID_FRESHNESS_WINDOW", "expires_at must be later than created_at");
  }
  return {
    capsuleId: requireId(readDataProperty(record, "capsule_id"), "capsule_id"),
    sessionId: requireId(readDataProperty(record, "session_id"), "session_id"),
    phase: requirePhase(readDataProperty(record, "phase"), "phase"),
    purpose,
    runSpecHash: requireHash(readDataProperty(record, "run_spec_hash"), "run_spec_hash"),
    policyHash: requireHash(readDataProperty(record, "policy_hash"), "policy_hash"),
    selections,
    openBlockers: normalizeUniqueStrings(
      readDataProperty(record, "open_blockers"),
      "open_blockers",
      { sort: false },
    ),
    allowedCapabilities: normalizeUniqueStrings(
      readDataProperty(record, "allowed_capabilities"),
      "allowed_capabilities",
    ),
    tokenBudget: requireNonNegativeInteger(
      readDataProperty(record, "token_budget"),
      "token_budget",
    ),
    createdAt,
    expiresAt,
  };
};

export const computeContextCapsuleHash = (preimageCandidate) => {
  const preimage = requirePlainDataObject(preimageCandidate, "ContextCapsuleHashPreimage", {
    allowedFields: CAPSULE_PREIMAGE_FIELDS,
  });
  return sha256CanonicalJson(preimage);
};

/**
 * Assemble a new capsule only from an explicit canonical-state snapshot.
 * There is deliberately no clock, random ID, previous-capsule or filesystem
 * fallback: replaying the same snapshot must yield the same immutable bytes.
 */
export const assembleContextCapsule = (snapshotCandidate) => {
  const snapshot = normalizeSnapshot(snapshotCandidate);
  const included = snapshot.selections.filter((entry) => entry.disposition === "INCLUDE");
  const excluded = snapshot.selections.filter((entry) => entry.disposition === "EXCLUDE");
  const preimage = {
    capsule_id: snapshot.capsuleId,
    session_id: snapshot.sessionId,
    phase: snapshot.phase,
    purpose: snapshot.purpose,
    run_spec_hash: snapshot.runSpecHash,
    policy_hash: snapshot.policyHash,
    artifact_ids: included.map((entry) => entry.artifactId),
    summaries: included.map((entry) => ({
      artifact_id: entry.artifactId,
      summary: entry.summary,
      source_hash: entry.sourceHash,
      summary_hash: sha256CanonicalJson(entry.summary),
    })),
    open_blockers: snapshot.openBlockers,
    excluded_artifact_ids: excluded.map((entry) => entry.artifactId),
    allowed_capabilities: snapshot.allowedCapabilities,
    token_budget: snapshot.tokenBudget,
    created_at: snapshot.createdAt,
    expires_at: snapshot.expiresAt,
  };
  return deepFreeze({ ...preimage, capsule_hash: computeContextCapsuleHash(preimage) });
};

const normalizeSummary = (candidate, index) => {
  const label = `summaries[${index}]`;
  const record = requirePlainDataObject(candidate, label, { allowedFields: SUMMARY_FIELDS });
  const normalized = {
    artifact_id: requireId(readDataProperty(record, "artifact_id"), `${label}.artifact_id`),
    summary: requireString(readDataProperty(record, "summary"), `${label}.summary`),
    source_hash: requireHash(readDataProperty(record, "source_hash"), `${label}.source_hash`),
    summary_hash: requireHash(readDataProperty(record, "summary_hash"), `${label}.summary_hash`),
  };
  if (normalized.summary.trim().length === 0) {
    fail("EMPTY_SUMMARY", `${label}.summary must not be blank`);
  }
  const expected = sha256CanonicalJson(normalized.summary);
  if (normalized.summary_hash !== expected) {
    fail("SUMMARY_HASH_MISMATCH", `${label}.summary_hash does not bind the summary bytes`, {
      artifact_id: normalized.artifact_id,
      expected,
      observed: normalized.summary_hash,
    });
  }
  return normalized;
};

const normalizeCapsule = (candidate, { verifyHash }) => {
  const record = requirePlainDataObject(candidate, "ContextCapsule", {
    allowedFields: CAPSULE_FIELDS,
  });
  const artifactIds = normalizeUniqueStrings(
    readDataProperty(record, "artifact_ids"),
    "artifact_ids",
    { id: true },
  );
  requireCanonicalOrder(artifactIds, "artifact_ids");
  if (artifactIds.length === 0) {
    fail("CANONICAL_ARTIFACT_REQUIRED", "artifact_ids must contain a canonical artifact");
  }
  const summaries = readDenseArray(readDataProperty(record, "summaries"), "summaries").map(
    normalizeSummary,
  );
  const summaryIds = summaries.map((summary) => summary.artifact_id);
  const summarySeen = new Set();
  for (const artifactId of summaryIds) {
    if (summarySeen.has(artifactId)) {
      fail("DUPLICATE_VALUE", `summaries contains duplicate artifact ${artifactId}`);
    }
    summarySeen.add(artifactId);
  }
  requireCanonicalOrder(summaryIds, "summaries");
  if (
    artifactIds.length !== summaryIds.length ||
    artifactIds.some((artifactId, index) => artifactId !== summaryIds[index])
  ) {
    fail(
      "UNBOUND_INCLUDED_ARTIFACT",
      "every artifact_id must have exactly one source-hash-bound summary",
    );
  }
  const excluded = normalizeUniqueStrings(
    readDataProperty(record, "excluded_artifact_ids"),
    "excluded_artifact_ids",
    { id: true },
  );
  requireCanonicalOrder(excluded, "excluded_artifact_ids");
  const overlap = artifactIds.filter((artifactId) => new Set(excluded).has(artifactId));
  if (overlap.length > 0) {
    fail(
      "ARTIFACT_DISPOSITION_CONFLICT",
      "an artifact cannot be both included and explicitly excluded",
      { artifact_ids: overlap },
    );
  }
  const capabilities = normalizeUniqueStrings(
    readDataProperty(record, "allowed_capabilities"),
    "allowed_capabilities",
  );
  requireCanonicalOrder(capabilities, "allowed_capabilities");
  const createdAt = requireRfc3339(readDataProperty(record, "created_at"), "created_at");
  const expiresValue = readDataProperty(record, "expires_at");
  const expiresAt = expiresValue === null ? null : requireRfc3339(expiresValue, "expires_at");
  if (expiresAt !== null && Date.parse(expiresAt) <= Date.parse(createdAt)) {
    fail("INVALID_FRESHNESS_WINDOW", "expires_at must be later than created_at");
  }
  const normalized = {
    capsule_id: requireId(readDataProperty(record, "capsule_id"), "capsule_id"),
    session_id: requireId(readDataProperty(record, "session_id"), "session_id"),
    phase: requirePhase(readDataProperty(record, "phase"), "phase"),
    purpose: requireString(readDataProperty(record, "purpose"), "purpose"),
    run_spec_hash: requireHash(readDataProperty(record, "run_spec_hash"), "run_spec_hash"),
    policy_hash: requireHash(readDataProperty(record, "policy_hash"), "policy_hash"),
    artifact_ids: artifactIds,
    summaries,
    open_blockers: normalizeUniqueStrings(
      readDataProperty(record, "open_blockers"),
      "open_blockers",
      { sort: false },
    ),
    excluded_artifact_ids: excluded,
    allowed_capabilities: capabilities,
    token_budget: requireNonNegativeInteger(
      readDataProperty(record, "token_budget"),
      "token_budget",
    ),
    created_at: createdAt,
    expires_at: expiresAt,
  };
  if (normalized.purpose.trim().length === 0) fail("EMPTY_PURPOSE", "purpose must not be blank");
  const observedHash = requireHash(readDataProperty(record, "capsule_hash"), "capsule_hash");
  if (verifyHash) {
    const expectedHash = computeContextCapsuleHash(normalized);
    if (observedHash !== expectedHash) {
      fail("CAPSULE_HASH_MISMATCH", "capsule_hash does not bind the canonical capsule", {
        expected: expectedHash,
        observed: observedHash,
      });
    }
  }
  return { ...normalized, capsule_hash: observedHash };
};

export const verifyContextCapsuleIntegrity = (candidate) =>
  deepFreeze(normalizeCapsule(candidate, { verifyHash: true }));

const normalizeCurrentArtifact = (candidate, index) => {
  const label = `current_artifacts[${index}]`;
  const record = requirePlainDataObject(candidate, label, {
    allowedFields: CURRENT_ARTIFACT_FIELDS,
  });
  return {
    artifactId: requireId(readDataProperty(record, "artifact_id"), `${label}.artifact_id`),
    contentHash: requireHash(readDataProperty(record, "content_hash"), `${label}.content_hash`),
  };
};

const normalizeFreshnessState = (candidate) => {
  const record = requirePlainDataObject(candidate, "freshnessState", {
    allowedFields: FRESHNESS_FIELDS,
  });
  const artifacts = readDenseArray(
    readDataProperty(record, "current_artifacts"),
    "current_artifacts",
  ).map(normalizeCurrentArtifact);
  const byId = new Map();
  for (const artifact of artifacts) {
    if (byId.has(artifact.artifactId)) {
      fail("DUPLICATE_VALUE", `current_artifacts contains duplicate ${artifact.artifactId}`);
    }
    byId.set(artifact.artifactId, artifact.contentHash);
  }
  return {
    sessionId: requireId(readDataProperty(record, "session_id"), "session_id"),
    phase: requirePhase(readDataProperty(record, "phase"), "phase"),
    runSpecHash: requireHash(readDataProperty(record, "run_spec_hash"), "run_spec_hash"),
    policyHash: requireHash(readDataProperty(record, "policy_hash"), "policy_hash"),
    currentArtifacts: byId,
    now: requireRfc3339(readDataProperty(record, "now"), "now"),
  };
};

/**
 * Fail closed unless an intact capsule still matches the current canonical
 * session, phase, policy, RunSpec and complete relevant-artifact inventory.
 */
export const requireFreshContextCapsule = (capsuleCandidate, freshnessCandidate) => {
  const capsule = verifyContextCapsuleIntegrity(capsuleCandidate);
  const current = normalizeFreshnessState(freshnessCandidate);
  if (capsule.session_id !== current.sessionId) {
    fail("CAPSULE_SESSION_DRIFT", "the capsule belongs to a different canonical session");
  }
  if (capsule.phase !== current.phase) {
    fail("CAPSULE_PHASE_DRIFT", "the canonical FORGE phase changed after capsule assembly");
  }
  if (capsule.run_spec_hash !== current.runSpecHash) {
    fail("CAPSULE_RUN_SPEC_DRIFT", "the governing RunSpec changed after capsule assembly");
  }
  if (capsule.policy_hash !== current.policyHash) {
    fail("CAPSULE_POLICY_DRIFT", "the governing policy changed after capsule assembly");
  }
  if (capsule.expires_at === null) {
    fail("CAPSULE_FRESHNESS_UNDECLARED", "a capsule without expires_at cannot be used for resume");
  }
  const now = Date.parse(current.now);
  if (now < Date.parse(capsule.created_at)) {
    fail("CAPSULE_NOT_YET_VALID", "the capsule creation instant is in the future");
  }
  if (now >= Date.parse(capsule.expires_at)) {
    fail("CAPSULE_EXPIRED", "the capsule freshness window has expired");
  }
  const included = new Set(capsule.artifact_ids);
  const excluded = new Set(capsule.excluded_artifact_ids);
  const unaccounted = [...current.currentArtifacts.keys()]
    .filter((artifactId) => !included.has(artifactId) && !excluded.has(artifactId))
    .sort(compareUtf8);
  if (unaccounted.length > 0) {
    fail(
      "CAPSULE_CANONICAL_STATE_DRIFT",
      "current canonical artifacts are neither included nor explicitly excluded",
      { artifact_ids: unaccounted },
    );
  }
  const currentSummaryHashes = new Map(
    capsule.summaries.map((summary) => [summary.artifact_id, summary.source_hash]),
  );
  const stale = capsule.artifact_ids
    .filter(
      (artifactId) => current.currentArtifacts.get(artifactId) !== currentSummaryHashes.get(artifactId),
    )
    .sort(compareUtf8);
  if (stale.length > 0) {
    fail(
      "CAPSULE_ARTIFACT_STALE",
      "included canonical artifacts changed or disappeared after capsule assembly",
      { artifact_ids: stale },
    );
  }
  return deepFreeze({
    status: "FRESH",
    capsule_id: capsule.capsule_id,
    capsule_hash: capsule.capsule_hash,
    checked_at: current.now,
    included_artifact_count: capsule.artifact_ids.length,
    excluded_artifact_count: capsule.excluded_artifact_ids.length,
  });
};

export const CONTEXT_CAPSULE_PHASES = PHASES;
