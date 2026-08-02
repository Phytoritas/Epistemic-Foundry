/**
 * Deterministic L03 memory redaction, deduplication, forget, and legal hold.
 *
 * L01 remains the consent/retention authority and L02 remains the retrieval
 * authority. This module consumes explicit source-bound redaction directives
 * and governed lifecycle inputs. It never infers a redaction profile, mutates
 * source bytes, treats an index/cache eviction as canonical deletion, or
 * silently bypasses an active legal hold.
 */

import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

import {
  MEMORY_CLASSES,
  canonicalMemoryPolicyJson,
} from "../policy/index.mjs";
import {
  sealActionIntent,
  sealEffectReceipt,
} from "../../effects/effect-coordinator.mjs";
import { computeEventHash } from "../../ledger/noetic-ledger.mjs";

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
const MEMORY_CLASS_SET = new Set(MEMORY_CLASSES);
const MEMORY_CLASS_RANK = new Map(MEMORY_CLASSES.map((value, index) => [value, index]));

export const MEMORY_LIFECYCLE_VERSION = "4.0.0-l03.1";
export const MEMORY_LIFECYCLE_ACTIONS = OBJECT_FREEZE([
  "FORGET_MEMORY",
  "DELETE_MEMORY",
]);
export const MEMORY_LIFECYCLE_DECISIONS = OBJECT_FREEZE([
  "APPLIED",
  "BLOCKED_LEGAL_HOLD",
]);
export const MEMORY_LIFECYCLE_STATUSES = OBJECT_FREEZE([
  "ACTIVE",
  "FORGOTTEN",
  "DELETED",
]);
export const TOMBSTONE_HASH_RETENTION = OBJECT_FREEZE([
  "PROHIBITED",
  "PERMITTED_BY_POLICY_AND_LAW",
]);

const ACTION_SET = new Set(MEMORY_LIFECYCLE_ACTIONS);
const DECISION_SET = new Set(MEMORY_LIFECYCLE_DECISIONS);
const STATUS_SET = new Set(MEMORY_LIFECYCLE_STATUSES);
const TOMBSTONE_SET = new Set(TOMBSTONE_HASH_RETENTION);

const HIT_FIELDS = OBJECT_FREEZE([
  "memory_id",
  "class",
  "score",
  "source_hash",
  "redacted",
]);
const SOURCE_FIELDS = OBJECT_FREEZE(["source_hash", "content"]);
const DIRECTIVE_FIELDS = OBJECT_FREEZE([
  "directive_id",
  "source_hash",
  "start_byte",
  "end_byte",
  "replacement",
]);
const REDACTION_INPUT_FIELDS = OBJECT_FREEZE([
  "hits",
  "source_artifacts",
  "redaction_directives",
  "required_redaction_profile",
]);
const REDACTED_ARTIFACT_FIELDS = OBJECT_FREEZE([
  "artifact_id",
  "original_source_hash",
  "redacted_content_hash",
  "content",
  "directive_ids",
]);
const DUPLICATE_FIELDS = OBJECT_FREEZE([
  "duplicate_memory_id",
  "representative_memory_id",
  "source_hash",
  "reason",
]);
const SELECTION_FIELDS = OBJECT_FREEZE([
  "selected_hits",
  "redacted_artifacts",
  "duplicate_exclusions",
  "redaction_count",
  "selection_hash",
]);

const STATE_INPUT_FIELDS = OBJECT_FREEZE([
  "memory_id",
  "class",
  "workspace_id",
  "revision",
  "status",
  "canonical_artifact_id",
  "source_hash",
  "content",
  "updated_at",
]);
const STATE_FIELDS = OBJECT_FREEZE([...STATE_INPUT_FIELDS, "state_hash"]);
const POLICY_INPUT_FIELDS = OBJECT_FREEZE([
  "policy_id",
  "workspace_id",
  "permitted_actions",
  "tombstone_hash_retention",
  "tombstone_authority_record_id",
  "effective_at",
]);
const POLICY_FIELDS = OBJECT_FREEZE([...POLICY_INPUT_FIELDS, "policy_hash"]);
const HOLD_SCOPE_FIELDS = OBJECT_FREEZE([
  "workspace_id",
  "memory_ids",
  "memory_classes",
]);
const HOLD_INPUT_FIELDS = OBJECT_FREEZE([
  "hold_id",
  "scope",
  "authority_record_id",
  "reason",
  "starts_at",
  "expires_at",
]);
const HOLD_FIELDS = OBJECT_FREEZE([...HOLD_INPUT_FIELDS, "hold_hash"]);
const REQUEST_INPUT_FIELDS = OBJECT_FREEZE([
  "request_id",
  "run_id",
  "memory_id",
  "workspace_id",
  "action_type",
  "target_kind",
  "expected_revision",
  "actor_id",
  "reason",
  "approval_record_ids",
  "requested_at",
  "idempotency_key",
  "event_sequence",
  "previous_event_hash",
]);
const REQUEST_FIELDS = OBJECT_FREEZE([...REQUEST_INPUT_FIELDS, "request_hash"]);
const PAYLOAD_FIELDS = OBJECT_FREEZE([
  "request_id",
  "request_hash",
  "policy_id",
  "policy_hash",
  "memory_id",
  "action_type",
  "decision",
  "previous_revision",
  "new_revision",
  "previous_state_hash",
  "new_state_hash",
  "blocking_hold_ids",
  "retained_tombstone_hash",
  "occurred_at",
]);
const ACTION_INTENT_FIELDS = OBJECT_FREEZE([
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
const EVENT_FIELDS = OBJECT_FREEZE([
  "event_id",
  "run_id",
  "sequence",
  "event_type",
  "aggregate_type",
  "aggregate_id",
  "actor_id",
  "payload_artifact_id",
  "payload_hash",
  "previous_event_hash",
  "event_hash",
  "occurred_at",
  "schema_version",
]);
const EFFECT_FIELDS = OBJECT_FREEZE([
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
const OUTCOME_FIELDS = OBJECT_FREEZE([
  "outcome_id",
  "idempotency_key",
  "request_hash",
  "decision",
  "state_changed",
  "blocking_hold_ids",
  "previous_state_hash",
  "new_state",
  "payload",
  "payload_hash",
  "action_intent",
  "event_record",
  "effect_receipt",
  "outcome_hash",
]);
const APPLICATION_FIELDS = OBJECT_FREEZE([
  "request",
  "state",
  "policy",
  "legal_holds",
  "prior_outcomes",
]);

export class MemoryLifecycleError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "MemoryLifecycleError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze({ ...details });
  }
}

const fail = (code, message, details) => {
  throw new MemoryLifecycleError(code, message, details);
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

const requirePlainDataObject = (value, label, fields, code = "MEMORY_LIFECYCLE_INPUT_INVALID") => {
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
      fail(code, `${label} contains an unsupported field`, { field: String(key) });
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

const readDenseArray = (value, label, code = "MEMORY_LIFECYCLE_INPUT_INVALID") => {
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
  { minLength = 1, maxLength = Number.MAX_SAFE_INTEGER, code = "MEMORY_LIFECYCLE_INPUT_INVALID" } = {},
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

const requireIdentifier = (value, label, code = "MEMORY_LIFECYCLE_INPUT_INVALID") =>
  requireString(value, label, { minLength: 3, maxLength: 128, code });

const requireNullableIdentifier = (value, label, code) =>
  value === null ? null : requireIdentifier(value, label, code);

const requireNonNegativeInteger = (value, label, code = "MEMORY_LIFECYCLE_INPUT_INVALID") => {
  if (!Number.isSafeInteger(value) || value < 0) fail(code, `${label} must be a non-negative safe integer`);
  return value;
};

const requirePositiveInteger = (value, label, code = "MEMORY_LIFECYCLE_INPUT_INVALID") => {
  if (!Number.isSafeInteger(value) || value < 1) fail(code, `${label} must be a positive safe integer`);
  return value;
};

const requireBoolean = (value, label, code = "MEMORY_LIFECYCLE_INPUT_INVALID") => {
  if (typeof value !== "boolean") fail(code, `${label} must be boolean`);
  return value;
};

const requireSha256 = (value, label, code = "MEMORY_LIFECYCLE_INPUT_INVALID") => {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) {
    fail(code, `${label} must be sha256:<64 lowercase hex>`);
  }
  return value;
};

const requireNullableSha256 = (value, label, code) =>
  value === null ? null : requireSha256(value, label, code);

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

const requireTimestamp = (value, label, code = "MEMORY_LIFECYCLE_INPUT_INVALID") => {
  if (!isRfc3339(value)) fail(code, `${label} must be a real RFC 3339 date-time`);
  return value;
};

const requireMemoryClass = (value, label, code = "MEMORY_LIFECYCLE_INPUT_INVALID") => {
  if (typeof value !== "string" || !MEMORY_CLASS_SET.has(value)) {
    fail(code, `${label} is not a canonical memory class`, { value });
  }
  return value;
};

const compareStrings = (left, right) => (left < right ? -1 : left > right ? 1 : 0);

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of REFLECT_OWN_KEYS(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) deepFreeze(descriptor.value);
  }
  return OBJECT_FREEZE(value);
};

const canonicalClone = (value) => deepFreeze(JSON.parse(canonicalMemoryPolicyJson(value)));

export const canonicalMemoryLifecycleJson = (value) => canonicalMemoryPolicyJson(value);

const sha256CanonicalJson = (value) =>
  `sha256:${createHash("sha256").update(canonicalMemoryLifecycleJson(value), "utf8").digest("hex")}`;

const sha256Text = (value) =>
  `sha256:${createHash("sha256").update(value, "utf8").digest("hex")}`;

const without = (value, key) => {
  const clone = { ...value };
  delete clone[key];
  return clone;
};

const requireSortedUniqueStrings = (
  value,
  label,
  { minItems = 0, code = "MEMORY_LIFECYCLE_INPUT_INVALID" } = {},
) => {
  const entries = readDenseArray(value, label, code).map((entry, index) =>
    requireIdentifier(entry, `${label}[${index}]`, code),
  );
  if (entries.length < minItems) fail(code, `${label} must contain at least ${minItems} item(s)`);
  if (new Set(entries).size !== entries.length) fail(code, `${label} contains duplicate values`);
  return OBJECT_FREEZE([...entries].sort(compareStrings));
};

const normalizeHit = (
  candidate,
  label = "MemoryRetrievalHit",
  { allowRedacted = false } = {},
) => {
  const code = "MEMORY_REDACTION_INPUT_INVALID";
  const hit = requirePlainDataObject(candidate, label, HIT_FIELDS, code);
  const score = readDataProperty(hit, "score");
  if (typeof score !== "number" || !Number.isFinite(score) || score < 0 || score > 1 || Object.is(score, -0)) {
    fail(code, `${label}.score must be a finite number from 0 through 1`);
  }
  const redacted = readDataProperty(hit, "redacted");
  if (typeof redacted !== "boolean") fail(code, `${label}.redacted must be boolean`);
  if (redacted && !allowRedacted) {
    fail("REDACTION_STAGE_ALREADY_APPLIED", "L03 accepts only unredacted L02 hits");
  }
  return canonicalClone({
    memory_id: requireIdentifier(readDataProperty(hit, "memory_id"), `${label}.memory_id`, code),
    class: requireMemoryClass(readDataProperty(hit, "class"), `${label}.class`, code),
    score,
    source_hash: requireSha256(readDataProperty(hit, "source_hash"), `${label}.source_hash`, code),
    redacted,
  });
};

const normalizeSource = (candidate, index) => {
  const code = "MEMORY_REDACTION_INPUT_INVALID";
  const source = requirePlainDataObject(candidate, `source_artifacts[${index}]`, SOURCE_FIELDS, code);
  const content = requireString(readDataProperty(source, "content"), `source_artifacts[${index}].content`, {
    minLength: 0,
    maxLength: 1_000_000,
    code,
  });
  const sourceHash = requireSha256(
    readDataProperty(source, "source_hash"),
    `source_artifacts[${index}].source_hash`,
    code,
  );
  const observed = sha256Text(content);
  if (sourceHash !== observed) {
    fail("REDACTION_SOURCE_HASH_MISMATCH", "source content does not match source_hash", {
      actual: observed,
      expected: sourceHash,
    });
  }
  return canonicalClone({ source_hash: sourceHash, content });
};

const normalizeDirective = (candidate, index) => {
  const code = "REDACTION_DIRECTIVE_INVALID";
  const directive = requirePlainDataObject(candidate, `redaction_directives[${index}]`, DIRECTIVE_FIELDS, code);
  const startByte = requireNonNegativeInteger(
    readDataProperty(directive, "start_byte"),
    `redaction_directives[${index}].start_byte`,
    code,
  );
  const endByte = requireNonNegativeInteger(
    readDataProperty(directive, "end_byte"),
    `redaction_directives[${index}].end_byte`,
    code,
  );
  if (endByte <= startByte) fail(code, "redaction directive must cover a non-empty byte span");
  return canonicalClone({
    directive_id: requireIdentifier(
      readDataProperty(directive, "directive_id"),
      `redaction_directives[${index}].directive_id`,
      code,
    ),
    source_hash: requireSha256(
      readDataProperty(directive, "source_hash"),
      `redaction_directives[${index}].source_hash`,
      code,
    ),
    start_byte: startByte,
    end_byte: endByte,
    replacement: requireString(
      readDataProperty(directive, "replacement"),
      `redaction_directives[${index}].replacement`,
      { minLength: 0, maxLength: 256, code },
    ),
  });
};

const isUtf8Boundary = (buffer, index) =>
  index === 0 || index === buffer.length || (buffer[index] & 0xc0) !== 0x80;

const applyDirectives = (source, directives) => {
  const bytes = Buffer.from(source.content, "utf8");
  const ordered = [...directives].sort(
    (left, right) =>
      left.start_byte - right.start_byte ||
      left.end_byte - right.end_byte ||
      compareStrings(left.directive_id, right.directive_id),
  );
  let previousEnd = 0;
  const chunks = [];
  for (const directive of ordered) {
    if (directive.end_byte > bytes.length) {
      fail("REDACTION_SPAN_OUT_OF_RANGE", "redaction directive exceeds source bytes", {
        directive_id: directive.directive_id,
      });
    }
    if (!isUtf8Boundary(bytes, directive.start_byte) || !isUtf8Boundary(bytes, directive.end_byte)) {
      fail("REDACTION_SPAN_SPLITS_UTF8", "redaction directive splits a UTF-8 code point", {
        directive_id: directive.directive_id,
      });
    }
    if (directive.start_byte < previousEnd) {
      fail("REDACTION_SPAN_OVERLAP", "redaction directives overlap", {
        directive_id: directive.directive_id,
      });
    }
    const original = bytes.subarray(directive.start_byte, directive.end_byte).toString("utf8");
    if (original === directive.replacement) {
      fail("REDACTION_NO_OP", "redaction directive does not change source content", {
        directive_id: directive.directive_id,
      });
    }
    chunks.push(bytes.subarray(previousEnd, directive.start_byte));
    chunks.push(Buffer.from(directive.replacement, "utf8"));
    previousEnd = directive.end_byte;
  }
  chunks.push(bytes.subarray(previousEnd));
  const content = Buffer.concat(chunks).toString("utf8");
  const redactedContentHash = sha256Text(content);
  return canonicalClone({
    artifact_id: `MRA-${redactedContentHash.slice("sha256:".length)}`,
    original_source_hash: source.source_hash,
    redacted_content_hash: redactedContentHash,
    content,
    directive_ids: ordered
      .map((directive) => directive.directive_id)
      .sort(compareStrings),
  });
};

const hitOrder = (left, right) =>
  right.score - left.score ||
  compareStrings(left.memory_id, right.memory_id) ||
  compareStrings(left.source_hash, right.source_hash);

const duplicateOrder = (left, right) =>
  compareStrings(left.representative_memory_id, right.representative_memory_id) ||
  compareStrings(left.duplicate_memory_id, right.duplicate_memory_id) ||
  compareStrings(left.source_hash, right.source_hash);

const selectionPreimage = (value) => without(value, "selection_hash");

export const redactAndDeduplicateMemory = (candidate) => {
  const code = "MEMORY_REDACTION_INPUT_INVALID";
  const input = requirePlainDataObject(candidate, "MemoryRedactionInput", REDACTION_INPUT_FIELDS, code);
  const requiredProfile = readDataProperty(input, "required_redaction_profile");
  if (requiredProfile !== null) {
    requireIdentifier(requiredProfile, "required_redaction_profile", code);
    fail(
      "REDACTION_PROFILE_UNRESOLVED",
      "a redaction profile identifier has no authoritative rule set; explicit directives are required",
      { redaction_profile: requiredProfile },
    );
  }
  const hits = readDenseArray(readDataProperty(input, "hits"), "hits", code).map((hit, index) =>
    normalizeHit(hit, `hits[${index}]`),
  );
  if (new Set(hits.map((hit) => hit.memory_id)).size !== hits.length) {
    fail("DUPLICATE_MEMORY_ID", "redaction input contains duplicate memory IDs");
  }
  const sources = readDenseArray(readDataProperty(input, "source_artifacts"), "source_artifacts", code)
    .map(normalizeSource);
  const sourceByHash = new Map();
  for (const source of sources) {
    if (sourceByHash.has(source.source_hash)) {
      fail("DUPLICATE_SOURCE_ARTIFACT", "source_artifacts contains a duplicate source hash");
    }
    sourceByHash.set(source.source_hash, source);
  }
  const hitSourceHashes = new Set(hits.map((hit) => hit.source_hash));
  for (const sourceHash of hitSourceHashes) {
    if (!sourceByHash.has(sourceHash)) {
      fail("REDACTION_SOURCE_MISSING", "a hit has no source artifact", { source_hash: sourceHash });
    }
  }
  for (const sourceHash of sourceByHash.keys()) {
    if (!hitSourceHashes.has(sourceHash)) {
      fail("REDACTION_SOURCE_UNUSED", "a source artifact is not referenced by any hit", {
        source_hash: sourceHash,
      });
    }
  }

  const directives = readDenseArray(
    readDataProperty(input, "redaction_directives"),
    "redaction_directives",
    code,
  ).map(normalizeDirective);
  if (new Set(directives.map((directive) => directive.directive_id)).size !== directives.length) {
    fail("DUPLICATE_REDACTION_DIRECTIVE", "redaction directive IDs must be unique");
  }
  const directivesBySource = new Map();
  for (const directive of directives) {
    if (!hitSourceHashes.has(directive.source_hash)) {
      fail("REDACTION_DIRECTIVE_UNUSED", "redaction directive does not bind a selected source", {
        directive_id: directive.directive_id,
      });
    }
    const group = directivesBySource.get(directive.source_hash) ?? [];
    group.push(directive);
    directivesBySource.set(directive.source_hash, group);
  }

  const redactedBySource = new Map();
  for (const [sourceHash, group] of directivesBySource.entries()) {
    redactedBySource.set(sourceHash, applyDirectives(sourceByHash.get(sourceHash), group));
  }

  const orderedHits = [...hits].sort(hitOrder);
  const representativeBySource = new Map();
  const selectedHits = [];
  const duplicateExclusions = [];
  for (const hit of orderedHits) {
    const representative = representativeBySource.get(hit.source_hash);
    if (representative === undefined) {
      representativeBySource.set(hit.source_hash, hit);
      selectedHits.push(canonicalClone({ ...hit, redacted: redactedBySource.has(hit.source_hash) }));
    } else {
      duplicateExclusions.push(canonicalClone({
        duplicate_memory_id: hit.memory_id,
        representative_memory_id: representative.memory_id,
        source_hash: hit.source_hash,
        reason: "DUPLICATE_SOURCE_HASH",
      }));
    }
  }
  duplicateExclusions.sort(duplicateOrder);
  const redactedArtifacts = [...redactedBySource.values()].sort((left, right) =>
    compareStrings(left.original_source_hash, right.original_source_hash),
  );
  const base = {
    selected_hits: selectedHits,
    redacted_artifacts: redactedArtifacts,
    duplicate_exclusions: duplicateExclusions,
    redaction_count: directives.length,
  };
  return canonicalClone({ ...base, selection_hash: sha256CanonicalJson(base) });
};

const normalizeRedactedArtifact = (candidate, index) => {
  const code = "MEMORY_SELECTION_INVALID";
  const artifact = requirePlainDataObject(candidate, `redacted_artifacts[${index}]`, REDACTED_ARTIFACT_FIELDS, code);
  const content = requireString(readDataProperty(artifact, "content"), `redacted_artifacts[${index}].content`, {
    minLength: 0,
    maxLength: 1_000_000,
    code,
  });
  const contentHash = requireSha256(
    readDataProperty(artifact, "redacted_content_hash"),
    `redacted_artifacts[${index}].redacted_content_hash`,
    code,
  );
  if (sha256Text(content) !== contentHash) fail("REDACTED_ARTIFACT_HASH_MISMATCH", "redacted content hash mismatch");
  const artifactId = requireIdentifier(
    readDataProperty(artifact, "artifact_id"),
    `redacted_artifacts[${index}].artifact_id`,
    code,
  );
  if (artifactId !== `MRA-${contentHash.slice("sha256:".length)}`) {
    fail("REDACTED_ARTIFACT_ID_MISMATCH", "redacted artifact ID does not match content hash");
  }
  return canonicalClone({
    artifact_id: artifactId,
    original_source_hash: requireSha256(
      readDataProperty(artifact, "original_source_hash"),
      `redacted_artifacts[${index}].original_source_hash`,
      code,
    ),
    redacted_content_hash: contentHash,
    content,
    directive_ids: requireSortedUniqueStrings(
      readDataProperty(artifact, "directive_ids"),
      `redacted_artifacts[${index}].directive_ids`,
      { minItems: 1, code },
    ),
  });
};

export const validateMemorySelection = (candidate) => {
  const code = "MEMORY_SELECTION_INVALID";
  const selection = requirePlainDataObject(candidate, "MemorySelection", SELECTION_FIELDS, code);
  const selectedHits = readDenseArray(readDataProperty(selection, "selected_hits"), "selected_hits", code)
    .map((hit, index) => normalizeHit(
      hit,
      `selected_hits[${index}]`,
      { allowRedacted: true },
    ));
  if (new Set(selectedHits.map((hit) => hit.memory_id)).size !== selectedHits.length) {
    fail(code, "selected hits contain duplicate memory IDs");
  }
  if (new Set(selectedHits.map((hit) => hit.source_hash)).size !== selectedHits.length) {
    fail(code, "selected hits contain duplicate source hashes");
  }
  const canonicalHits = [...selectedHits].sort(hitOrder);
  if (selectedHits.some((hit, index) => canonicalMemoryLifecycleJson(hit) !== canonicalMemoryLifecycleJson(canonicalHits[index]))) {
    fail("MEMORY_SELECTION_ORDER_INVALID", "selected hits are not in deterministic order");
  }
  const artifacts = readDenseArray(
    readDataProperty(selection, "redacted_artifacts"),
    "redacted_artifacts",
    code,
  ).map(normalizeRedactedArtifact);
  const artifactHashes = artifacts.map((artifact) => artifact.original_source_hash);
  if (new Set(artifactHashes).size !== artifactHashes.length) fail(code, "redacted artifacts contain duplicate sources");
  if (artifacts.some((artifact, index) => artifact.original_source_hash !== [...artifacts].sort(
    (left, right) => compareStrings(left.original_source_hash, right.original_source_hash),
  )[index].original_source_hash)) {
    fail("MEMORY_SELECTION_ORDER_INVALID", "redacted artifacts are not in deterministic order");
  }
  const redactedSources = new Set(selectedHits.filter((hit) => hit.redacted).map((hit) => hit.source_hash));
  if (
    redactedSources.size !== artifacts.length ||
    artifacts.some((artifact) => !redactedSources.has(artifact.original_source_hash))
  ) {
    fail(code, "redacted hit flags and redacted artifacts disagree");
  }
  const duplicateExclusions = readDenseArray(
    readDataProperty(selection, "duplicate_exclusions"),
    "duplicate_exclusions",
    code,
  ).map((entry, index) => {
    const value = requirePlainDataObject(entry, `duplicate_exclusions[${index}]`, DUPLICATE_FIELDS, code);
    if (readDataProperty(value, "reason") !== "DUPLICATE_SOURCE_HASH") {
      fail(code, "duplicate exclusion reason is not canonical");
    }
    return canonicalClone({
      duplicate_memory_id: requireIdentifier(readDataProperty(value, "duplicate_memory_id"), `duplicate_exclusions[${index}].duplicate_memory_id`, code),
      representative_memory_id: requireIdentifier(readDataProperty(value, "representative_memory_id"), `duplicate_exclusions[${index}].representative_memory_id`, code),
      source_hash: requireSha256(readDataProperty(value, "source_hash"), `duplicate_exclusions[${index}].source_hash`, code),
      reason: "DUPLICATE_SOURCE_HASH",
    });
  });
  const selectedByMemoryId = new Map(selectedHits.map((hit) => [hit.memory_id, hit]));
  const duplicateMemoryIds = new Set();
  for (const exclusion of duplicateExclusions) {
    if (exclusion.duplicate_memory_id === exclusion.representative_memory_id) {
      fail(code, "a duplicate exclusion cannot refer to itself");
    }
    if (selectedByMemoryId.has(exclusion.duplicate_memory_id)) {
      fail(code, "a selected hit cannot also be excluded as a duplicate");
    }
    if (duplicateMemoryIds.has(exclusion.duplicate_memory_id)) {
      fail(code, "a duplicate memory ID cannot be excluded more than once");
    }
    duplicateMemoryIds.add(exclusion.duplicate_memory_id);
    const representative = selectedByMemoryId.get(exclusion.representative_memory_id);
    if (representative === undefined || representative.source_hash !== exclusion.source_hash) {
      fail(code, "duplicate exclusion is not bound to its selected source representative");
    }
  }
  const canonicalDuplicateExclusions = [...duplicateExclusions].sort(duplicateOrder);
  if (duplicateExclusions.some(
    (entry, index) =>
      canonicalMemoryLifecycleJson(entry) !==
      canonicalMemoryLifecycleJson(canonicalDuplicateExclusions[index]),
  )) {
    fail("MEMORY_SELECTION_ORDER_INVALID", "duplicate exclusions are not in deterministic order");
  }
  const redactionCount = requireNonNegativeInteger(
    readDataProperty(selection, "redaction_count"),
    "redaction_count",
    code,
  );
  const minimumDirectiveCount = artifacts.reduce((total, artifact) => total + artifact.directive_ids.length, 0);
  if (redactionCount !== minimumDirectiveCount) fail(code, "redaction_count does not equal applied directives");
  const normalized = {
    selected_hits: selectedHits,
    redacted_artifacts: artifacts,
    duplicate_exclusions: duplicateExclusions,
    redaction_count: redactionCount,
  };
  const selectionHash = requireSha256(readDataProperty(selection, "selection_hash"), "selection_hash", code);
  if (selectionHash !== sha256CanonicalJson(normalized)) {
    fail("MEMORY_SELECTION_HASH_MISMATCH", "selection_hash does not match selection content");
  }
  return canonicalClone({ ...normalized, selection_hash: selectionHash });
};

const normalizeState = (candidate, { sealed = true } = {}) => {
  const code = "MEMORY_LIFECYCLE_STATE_INVALID";
  const state = requirePlainDataObject(candidate, "MemoryLifecycleState", sealed ? STATE_FIELDS : STATE_INPUT_FIELDS, code);
  const status = readDataProperty(state, "status");
  if (!STATUS_SET.has(status)) fail(code, "state.status is not canonical");
  const canonicalArtifactId = requireNullableIdentifier(
    readDataProperty(state, "canonical_artifact_id"),
    "state.canonical_artifact_id",
    code,
  );
  const sourceHash = requireNullableSha256(readDataProperty(state, "source_hash"), "state.source_hash", code);
  const rawContent = readDataProperty(state, "content");
  const content = rawContent === null
    ? null
    : requireString(rawContent, "state.content", { minLength: 0, maxLength: 1_000_000, code });
  if (status === "ACTIVE") {
    if (canonicalArtifactId === null || sourceHash === null || content === null) {
      fail(code, "ACTIVE state requires canonical artifact, source hash, and content");
    }
    if (sha256Text(content) !== sourceHash) fail("MEMORY_STATE_SOURCE_HASH_MISMATCH", "ACTIVE content does not match source_hash");
  } else if (canonicalArtifactId !== null || content !== null) {
    fail(code, "terminal lifecycle state cannot retain canonical artifact content");
  }
  const normalized = {
    memory_id: requireIdentifier(readDataProperty(state, "memory_id"), "state.memory_id", code),
    class: requireMemoryClass(readDataProperty(state, "class"), "state.class", code),
    workspace_id: requireIdentifier(readDataProperty(state, "workspace_id"), "state.workspace_id", code),
    revision: requireNonNegativeInteger(readDataProperty(state, "revision"), "state.revision", code),
    status,
    canonical_artifact_id: canonicalArtifactId,
    source_hash: sourceHash,
    content,
    updated_at: requireTimestamp(readDataProperty(state, "updated_at"), "state.updated_at", code),
  };
  if (!sealed) return canonicalClone(normalized);
  const stateHash = requireSha256(readDataProperty(state, "state_hash"), "state.state_hash", code);
  if (stateHash !== sha256CanonicalJson(normalized)) fail("MEMORY_STATE_HASH_MISMATCH", "state_hash mismatch");
  return canonicalClone({ ...normalized, state_hash: stateHash });
};

export const sealMemoryLifecycleState = (candidate) => {
  const normalized = normalizeState(candidate, { sealed: false });
  return canonicalClone({ ...normalized, state_hash: sha256CanonicalJson(normalized) });
};

export const validateMemoryLifecycleState = (candidate) => normalizeState(candidate);

const normalizePolicy = (candidate, { sealed = true } = {}) => {
  const code = "MEMORY_LIFECYCLE_POLICY_INVALID";
  const policy = requirePlainDataObject(candidate, "MemoryLifecyclePolicy", sealed ? POLICY_FIELDS : POLICY_INPUT_FIELDS, code);
  const actions = readDenseArray(readDataProperty(policy, "permitted_actions"), "policy.permitted_actions", code)
    .map((action) => {
      if (!ACTION_SET.has(action)) fail(code, "policy contains an unknown lifecycle action", { action });
      return action;
    })
    .sort((left, right) => MEMORY_LIFECYCLE_ACTIONS.indexOf(left) - MEMORY_LIFECYCLE_ACTIONS.indexOf(right));
  if (actions.length === 0 || new Set(actions).size !== actions.length) {
    fail(code, "policy.permitted_actions must be a non-empty unique set");
  }
  const retention = readDataProperty(policy, "tombstone_hash_retention");
  if (!TOMBSTONE_SET.has(retention)) fail(code, "tombstone hash retention is not canonical");
  const authority = requireNullableIdentifier(
    readDataProperty(policy, "tombstone_authority_record_id"),
    "policy.tombstone_authority_record_id",
    code,
  );
  if ((retention === "PERMITTED_BY_POLICY_AND_LAW") !== (authority !== null)) {
    fail(code, "tombstone retention permission and authority record must agree");
  }
  const normalized = {
    policy_id: requireIdentifier(readDataProperty(policy, "policy_id"), "policy.policy_id", code),
    workspace_id: requireIdentifier(readDataProperty(policy, "workspace_id"), "policy.workspace_id", code),
    permitted_actions: actions,
    tombstone_hash_retention: retention,
    tombstone_authority_record_id: authority,
    effective_at: requireTimestamp(readDataProperty(policy, "effective_at"), "policy.effective_at", code),
  };
  if (!sealed) return canonicalClone(normalized);
  const policyHash = requireSha256(readDataProperty(policy, "policy_hash"), "policy.policy_hash", code);
  if (policyHash !== sha256CanonicalJson(normalized)) fail("MEMORY_LIFECYCLE_POLICY_HASH_MISMATCH", "policy_hash mismatch");
  return canonicalClone({ ...normalized, policy_hash: policyHash });
};

export const sealMemoryLifecyclePolicy = (candidate) => {
  const normalized = normalizePolicy(candidate, { sealed: false });
  return canonicalClone({ ...normalized, policy_hash: sha256CanonicalJson(normalized) });
};

export const validateMemoryLifecyclePolicy = (candidate) => normalizePolicy(candidate);

const normalizeHoldScope = (candidate) => {
  const code = "LEGAL_HOLD_INVALID";
  const scope = requirePlainDataObject(candidate, "legal_hold.scope", HOLD_SCOPE_FIELDS, code);
  const memoryIds = requireSortedUniqueStrings(readDataProperty(scope, "memory_ids"), "legal_hold.scope.memory_ids", { code });
  const classes = readDenseArray(readDataProperty(scope, "memory_classes"), "legal_hold.scope.memory_classes", code)
    .map((value, index) => requireMemoryClass(value, `legal_hold.scope.memory_classes[${index}]`, code));
  if (new Set(classes).size !== classes.length) fail(code, "legal hold memory_classes contains duplicates");
  classes.sort((left, right) => MEMORY_CLASS_RANK.get(left) - MEMORY_CLASS_RANK.get(right));
  return canonicalClone({
    workspace_id: requireIdentifier(readDataProperty(scope, "workspace_id"), "legal_hold.scope.workspace_id", code),
    memory_ids: memoryIds,
    memory_classes: classes,
  });
};

const normalizeHold = (candidate, { sealed = true } = {}) => {
  const code = "LEGAL_HOLD_INVALID";
  const hold = requirePlainDataObject(candidate, "LegalHold", sealed ? HOLD_FIELDS : HOLD_INPUT_FIELDS, code);
  const startsAt = requireTimestamp(readDataProperty(hold, "starts_at"), "legal_hold.starts_at", code);
  const expiresAt = requireTimestamp(readDataProperty(hold, "expires_at"), "legal_hold.expires_at", code);
  if (Date.parse(expiresAt) <= Date.parse(startsAt)) {
    fail("LEGAL_HOLD_NOT_TIME_BOUNDED", "legal hold must have a finite expiry after its start");
  }
  const normalized = {
    hold_id: requireIdentifier(readDataProperty(hold, "hold_id"), "legal_hold.hold_id", code),
    scope: normalizeHoldScope(readDataProperty(hold, "scope")),
    authority_record_id: requireIdentifier(readDataProperty(hold, "authority_record_id"), "legal_hold.authority_record_id", code),
    reason: requireString(readDataProperty(hold, "reason"), "legal_hold.reason", { maxLength: 2048, code }),
    starts_at: startsAt,
    expires_at: expiresAt,
  };
  if (!sealed) return canonicalClone(normalized);
  const holdHash = requireSha256(readDataProperty(hold, "hold_hash"), "legal_hold.hold_hash", code);
  if (holdHash !== sha256CanonicalJson(normalized)) fail("LEGAL_HOLD_HASH_MISMATCH", "hold_hash mismatch");
  return canonicalClone({ ...normalized, hold_hash: holdHash });
};

export const sealLegalHold = (candidate) => {
  const normalized = normalizeHold(candidate, { sealed: false });
  return canonicalClone({ ...normalized, hold_hash: sha256CanonicalJson(normalized) });
};

export const validateLegalHold = (candidate) => normalizeHold(candidate);

const normalizeRequest = (candidate, { sealed = true } = {}) => {
  const code = "MEMORY_LIFECYCLE_REQUEST_INVALID";
  const request = requirePlainDataObject(candidate, "MemoryLifecycleRequest", sealed ? REQUEST_FIELDS : REQUEST_INPUT_FIELDS, code);
  const action = readDataProperty(request, "action_type");
  if (!ACTION_SET.has(action)) fail(code, "request.action_type is not canonical");
  const targetKind = readDataProperty(request, "target_kind");
  if (targetKind !== "CANONICAL_MEMORY") {
    fail(
      "DERIVED_CACHE_NOT_CANONICAL_MEMORY",
      "index/cache eviction is not canonical memory deletion",
      { target_kind: targetKind },
    );
  }
  const previousEventHash = requireNullableSha256(
    readDataProperty(request, "previous_event_hash"),
    "request.previous_event_hash",
    code,
  );
  const normalized = {
    request_id: requireIdentifier(readDataProperty(request, "request_id"), "request.request_id", code),
    run_id: requireIdentifier(readDataProperty(request, "run_id"), "request.run_id", code),
    memory_id: requireIdentifier(readDataProperty(request, "memory_id"), "request.memory_id", code),
    workspace_id: requireIdentifier(readDataProperty(request, "workspace_id"), "request.workspace_id", code),
    action_type: action,
    target_kind: "CANONICAL_MEMORY",
    expected_revision: requireNonNegativeInteger(readDataProperty(request, "expected_revision"), "request.expected_revision", code),
    actor_id: requireIdentifier(readDataProperty(request, "actor_id"), "request.actor_id", code),
    reason: requireString(readDataProperty(request, "reason"), "request.reason", { maxLength: 2048, code }),
    approval_record_ids: requireSortedUniqueStrings(
      readDataProperty(request, "approval_record_ids"),
      "request.approval_record_ids",
      { code },
    ),
    requested_at: requireTimestamp(readDataProperty(request, "requested_at"), "request.requested_at", code),
    idempotency_key: requireIdentifier(readDataProperty(request, "idempotency_key"), "request.idempotency_key", code),
    event_sequence: requirePositiveInteger(readDataProperty(request, "event_sequence"), "request.event_sequence", code),
    previous_event_hash: previousEventHash,
  };
  if ((normalized.event_sequence === 1) !== (previousEventHash === null)) {
    fail(code, "event sequence 1 requires no previous hash and later events require one");
  }
  if (!sealed) return canonicalClone(normalized);
  const requestHash = requireSha256(readDataProperty(request, "request_hash"), "request.request_hash", code);
  if (requestHash !== sha256CanonicalJson(normalized)) fail("MEMORY_LIFECYCLE_REQUEST_HASH_MISMATCH", "request_hash mismatch");
  return canonicalClone({ ...normalized, request_hash: requestHash });
};

export const sealMemoryLifecycleRequest = (candidate) => {
  const normalized = normalizeRequest(candidate, { sealed: false });
  return canonicalClone({ ...normalized, request_hash: sha256CanonicalJson(normalized) });
};

export const validateMemoryLifecycleRequest = (candidate) => normalizeRequest(candidate);

const holdMatches = (hold, state, requestedAt) => {
  const time = Date.parse(requestedAt);
  if (!(Date.parse(hold.starts_at) <= time && time < Date.parse(hold.expires_at))) return false;
  if (hold.scope.workspace_id !== state.workspace_id) return false;
  if (hold.scope.memory_ids.length > 0 && !hold.scope.memory_ids.includes(state.memory_id)) return false;
  if (hold.scope.memory_classes.length > 0 && !hold.scope.memory_classes.includes(state.class)) return false;
  return true;
};

const makeActionIntent = (request) => {
  const base = {
    intent_id: `MLI-${request.request_hash.slice("sha256:".length)}`,
    run_id: request.run_id,
    node_id: "govern_memory_lifecycle",
    action_type: request.action_type === "FORGET_MEMORY" ? "forget_memory" : "delete_memory",
    target_ref: request.memory_id,
    arguments_artifact_id: `MLREQ-${request.request_hash.slice("sha256:".length)}`,
    arguments_hash: request.request_hash,
    idempotency_key: request.idempotency_key,
    required_capabilities: ["database_write"],
    approval_record_ids: request.approval_record_ids,
    risk_class: "controlled_effect",
    created_at: request.requested_at,
  };
  return sealActionIntent(base);
};

const makeEvent = (request, state, decision, payloadId, payloadHash) => {
  const base = {
    event_id: `MLE-${payloadHash.slice("sha256:".length)}`,
    run_id: request.run_id,
    sequence: request.event_sequence,
    event_type: decision === "APPLIED" ? "memory.lifecycle.applied" : "memory.lifecycle.blocked_by_legal_hold",
    aggregate_type: "memory",
    aggregate_id: state.memory_id,
    actor_id: request.actor_id,
    payload_artifact_id: payloadId,
    payload_hash: payloadHash,
    previous_event_hash: request.previous_event_hash,
    occurred_at: request.requested_at,
    schema_version: "4.0.0",
  };
  return canonicalClone({ ...base, event_hash: computeEventHash(base) });
};

const makeEffectReceipt = (request, intent, decision, payloadId, observedStateHash) => {
  const applied = decision === "APPLIED";
  const identity = sha256CanonicalJson({ request_hash: request.request_hash, decision });
  const base = {
    receipt_id: `MLER-${identity.slice("sha256:".length)}`,
    intent_id: intent.intent_id,
    run_id: request.run_id,
    external_operation_id: null,
    status: applied ? "SUCCEEDED" : "NOT_EXECUTED",
    result_artifact_ids: applied ? [payloadId] : [],
    error_artifact_ids: applied ? [] : [payloadId],
    observed_state_hash: observedStateHash,
    idempotency_key: request.idempotency_key,
    started_at: request.requested_at,
    finished_at: request.requested_at,
    reconciliation_required: false,
  };
  return sealEffectReceipt(base);
};

const normalizePayload = (candidate) => {
  const code = "MEMORY_LIFECYCLE_OUTCOME_INVALID";
  const payload = requirePlainDataObject(candidate, "outcome.payload", PAYLOAD_FIELDS, code);
  const actionType = readDataProperty(payload, "action_type");
  if (!ACTION_SET.has(actionType)) fail(code, "payload.action_type is not canonical");
  const decision = readDataProperty(payload, "decision");
  if (!DECISION_SET.has(decision)) fail(code, "payload.decision is not canonical");
  return canonicalClone({
    request_id: requireIdentifier(readDataProperty(payload, "request_id"), "payload.request_id", code),
    request_hash: requireSha256(readDataProperty(payload, "request_hash"), "payload.request_hash", code),
    policy_id: requireIdentifier(readDataProperty(payload, "policy_id"), "payload.policy_id", code),
    policy_hash: requireSha256(readDataProperty(payload, "policy_hash"), "payload.policy_hash", code),
    memory_id: requireIdentifier(readDataProperty(payload, "memory_id"), "payload.memory_id", code),
    action_type: actionType,
    decision,
    previous_revision: requireNonNegativeInteger(
      readDataProperty(payload, "previous_revision"),
      "payload.previous_revision",
      code,
    ),
    new_revision: requireNonNegativeInteger(
      readDataProperty(payload, "new_revision"),
      "payload.new_revision",
      code,
    ),
    previous_state_hash: requireSha256(
      readDataProperty(payload, "previous_state_hash"),
      "payload.previous_state_hash",
      code,
    ),
    new_state_hash: requireSha256(
      readDataProperty(payload, "new_state_hash"),
      "payload.new_state_hash",
      code,
    ),
    blocking_hold_ids: requireSortedUniqueStrings(
      readDataProperty(payload, "blocking_hold_ids"),
      "payload.blocking_hold_ids",
      { code },
    ),
    retained_tombstone_hash: requireNullableSha256(
      readDataProperty(payload, "retained_tombstone_hash"),
      "payload.retained_tombstone_hash",
      code,
    ),
    occurred_at: requireTimestamp(readDataProperty(payload, "occurred_at"), "payload.occurred_at", code),
  });
};

const dependencyErrorCode = (error) =>
  error !== null && typeof error === "object" && typeof error.code === "string"
    ? error.code
    : error instanceof Error
      ? error.name
      : "unknown";

const validateCanonicalActionIntent = (candidate) => {
  const code = "MEMORY_LIFECYCLE_OUTCOME_INVALID";
  const value = requirePlainDataObject(candidate, "outcome.action_intent", ACTION_INTENT_FIELDS, code);
  let sealed;
  try {
    sealed = sealActionIntent(without(value, "intent_hash"));
  } catch (error) {
    fail(code, "action intent does not satisfy the canonical effect contract", {
      cause_code: dependencyErrorCode(error),
    });
  }
  if (canonicalMemoryLifecycleJson(sealed) !== canonicalMemoryLifecycleJson(value)) {
    fail(code, "action intent hash or canonical fields do not match");
  }
  return canonicalClone(sealed);
};

const validateCanonicalEffectReceipt = (candidate) => {
  const code = "MEMORY_LIFECYCLE_OUTCOME_INVALID";
  const value = requirePlainDataObject(candidate, "outcome.effect_receipt", EFFECT_FIELDS, code);
  let sealed;
  try {
    sealed = sealEffectReceipt(without(value, "receipt_hash"));
  } catch (error) {
    fail(code, "effect receipt does not satisfy the canonical effect contract", {
      cause_code: dependencyErrorCode(error),
    });
  }
  if (canonicalMemoryLifecycleJson(sealed) !== canonicalMemoryLifecycleJson(value)) {
    fail(code, "effect receipt hash or canonical fields do not match");
  }
  return canonicalClone(sealed);
};

const validateCanonicalEventRecord = (candidate) => {
  const code = "MEMORY_LIFECYCLE_OUTCOME_INVALID";
  const value = requirePlainDataObject(candidate, "outcome.event_record", EVENT_FIELDS, code);
  const previousEventHash = requireNullableSha256(
    readDataProperty(value, "previous_event_hash"),
    "event.previous_event_hash",
    code,
  );
  const sequence = requirePositiveInteger(readDataProperty(value, "sequence"), "event.sequence", code);
  if ((sequence === 1) !== (previousEventHash === null)) {
    fail(code, "event sequence 1 requires no previous hash and later events require one");
  }
  const schemaVersion = requireString(readDataProperty(value, "schema_version"), "event.schema_version", {
    code,
  });
  if (schemaVersion !== "4.0.0") fail(code, "event.schema_version is not canonical for L03");
  const base = canonicalClone({
    event_id: requireIdentifier(readDataProperty(value, "event_id"), "event.event_id", code),
    run_id: requireIdentifier(readDataProperty(value, "run_id"), "event.run_id", code),
    sequence,
    event_type: requireString(readDataProperty(value, "event_type"), "event.event_type", { code }),
    aggregate_type: requireString(readDataProperty(value, "aggregate_type"), "event.aggregate_type", { code }),
    aggregate_id: requireIdentifier(readDataProperty(value, "aggregate_id"), "event.aggregate_id", code),
    actor_id: requireIdentifier(readDataProperty(value, "actor_id"), "event.actor_id", code),
    payload_artifact_id: requireIdentifier(
      readDataProperty(value, "payload_artifact_id"),
      "event.payload_artifact_id",
      code,
    ),
    payload_hash: requireSha256(readDataProperty(value, "payload_hash"), "event.payload_hash", code),
    previous_event_hash: previousEventHash,
    occurred_at: requireTimestamp(readDataProperty(value, "occurred_at"), "event.occurred_at", code),
    schema_version: schemaVersion,
  });
  const eventHash = requireSha256(readDataProperty(value, "event_hash"), "event.event_hash", code);
  let expected;
  try {
    expected = computeEventHash(base);
  } catch (error) {
    fail(code, "event record does not satisfy the canonical ledger hash contract", {
      cause_code: dependencyErrorCode(error),
    });
  }
  if (eventHash !== expected) fail(code, "event.event_hash mismatch");
  return canonicalClone({ ...base, event_hash: eventHash });
};

export const validateMemoryLifecycleOutcome = (candidate) => {
  const code = "MEMORY_LIFECYCLE_OUTCOME_INVALID";
  const outcome = requirePlainDataObject(candidate, "MemoryLifecycleOutcome", OUTCOME_FIELDS, code);
  const decision = readDataProperty(outcome, "decision");
  if (!DECISION_SET.has(decision)) fail(code, "outcome.decision is not canonical");
  const stateChanged = requireBoolean(readDataProperty(outcome, "state_changed"), "outcome.state_changed", code);
  if (stateChanged !== (decision === "APPLIED")) fail(code, "state_changed does not match decision");
  const blockingHoldIds = requireSortedUniqueStrings(
    readDataProperty(outcome, "blocking_hold_ids"),
    "outcome.blocking_hold_ids",
    { code },
  );
  if ((blockingHoldIds.length > 0) !== (decision === "BLOCKED_LEGAL_HOLD")) {
    fail(code, "blocking hold IDs do not match decision");
  }
  const newState = validateMemoryLifecycleState(readDataProperty(outcome, "new_state"));
  const previousStateHash = requireSha256(readDataProperty(outcome, "previous_state_hash"), "outcome.previous_state_hash", code);
  const normalizedPayload = normalizePayload(readDataProperty(outcome, "payload"));
  const payloadHash = requireSha256(readDataProperty(outcome, "payload_hash"), "outcome.payload_hash", code);
  if (payloadHash !== sha256CanonicalJson(normalizedPayload)) fail(code, "payload_hash mismatch");
  if (
    normalizedPayload.decision !== decision ||
    normalizedPayload.previous_state_hash !== previousStateHash ||
    normalizedPayload.new_state_hash !== newState.state_hash ||
    normalizedPayload.memory_id !== newState.memory_id ||
    normalizedPayload.new_revision !== newState.revision ||
    canonicalMemoryLifecycleJson(normalizedPayload.blocking_hold_ids) !== canonicalMemoryLifecycleJson(blockingHoldIds)
  ) {
    fail(code, "payload bindings disagree with outcome");
  }
  if (decision === "APPLIED") {
    if (
      normalizedPayload.new_revision !== normalizedPayload.previous_revision + 1 ||
      normalizedPayload.occurred_at !== newState.updated_at ||
      previousStateHash === newState.state_hash ||
      !["FORGOTTEN", "DELETED"].includes(newState.status) ||
      (normalizedPayload.action_type === "FORGET_MEMORY") !== (newState.status === "FORGOTTEN") ||
      newState.canonical_artifact_id !== null ||
      newState.content !== null ||
      normalizedPayload.retained_tombstone_hash !== newState.source_hash
    ) {
      fail(code, "applied lifecycle payload does not describe one canonical terminal transition");
    }
  } else if (
    normalizedPayload.new_revision !== normalizedPayload.previous_revision ||
    previousStateHash !== newState.state_hash ||
    newState.status !== "ACTIVE" ||
    normalizedPayload.retained_tombstone_hash !== null
  ) {
    fail(code, "blocked lifecycle payload must preserve the active revision without a tombstone effect");
  }
  const intent = validateCanonicalActionIntent(readDataProperty(outcome, "action_intent"));
  const event = validateCanonicalEventRecord(readDataProperty(outcome, "event_record"));
  const receipt = validateCanonicalEffectReceipt(readDataProperty(outcome, "effect_receipt"));
  const requestHash = requireSha256(readDataProperty(outcome, "request_hash"), "outcome.request_hash", code);
  const idempotencyKey = requireIdentifier(readDataProperty(outcome, "idempotency_key"), "outcome.idempotency_key", code);
  const payloadId = `MLP-${payloadHash.slice("sha256:".length)}`;
  const expectedIntentAction = normalizedPayload.action_type === "FORGET_MEMORY"
    ? "forget_memory"
    : "delete_memory";
  const expectedEventType = decision === "APPLIED"
    ? "memory.lifecycle.applied"
    : "memory.lifecycle.blocked_by_legal_hold";
  const expectedReceiptStatus = decision === "APPLIED" ? "SUCCEEDED" : "NOT_EXECUTED";
  const expectedReceiptIdentity = sha256CanonicalJson({ request_hash: requestHash, decision });
  if (
    normalizedPayload.request_hash !== requestHash ||
    intent.intent_id !== `MLI-${requestHash.slice("sha256:".length)}` ||
    intent.run_id !== event.run_id ||
    intent.run_id !== receipt.run_id ||
    intent.node_id !== "govern_memory_lifecycle" ||
    intent.action_type !== expectedIntentAction ||
    intent.target_ref !== normalizedPayload.memory_id ||
    intent.arguments_artifact_id !== `MLREQ-${requestHash.slice("sha256:".length)}` ||
    intent.arguments_hash !== requestHash ||
    intent.idempotency_key !== idempotencyKey ||
    canonicalMemoryLifecycleJson(intent.required_capabilities) !== '["database_write"]' ||
    intent.risk_class !== "controlled_effect" ||
    intent.created_at !== normalizedPayload.occurred_at ||
    event.event_id !== `MLE-${payloadHash.slice("sha256:".length)}` ||
    event.event_type !== expectedEventType ||
    event.aggregate_type !== "memory" ||
    event.aggregate_id !== normalizedPayload.memory_id ||
    event.payload_artifact_id !== payloadId ||
    event.payload_hash !== payloadHash ||
    event.occurred_at !== normalizedPayload.occurred_at ||
    receipt.receipt_id !== `MLER-${expectedReceiptIdentity.slice("sha256:".length)}` ||
    receipt.intent_id !== intent.intent_id ||
    receipt.idempotency_key !== idempotencyKey ||
    receipt.external_operation_id !== null ||
    receipt.status !== expectedReceiptStatus ||
    receipt.observed_state_hash !== newState.state_hash ||
    receipt.started_at !== normalizedPayload.occurred_at ||
    receipt.finished_at !== normalizedPayload.occurred_at ||
    receipt.reconciliation_required !== false ||
    canonicalMemoryLifecycleJson(receipt.result_artifact_ids) !==
      canonicalMemoryLifecycleJson(decision === "APPLIED" ? [payloadId] : []) ||
    canonicalMemoryLifecycleJson(receipt.error_artifact_ids) !==
      canonicalMemoryLifecycleJson(decision === "APPLIED" ? [] : [payloadId])
  ) {
    fail(code, "intent, event, receipt, and state bindings disagree");
  }
  const outcomeId = requireIdentifier(readDataProperty(outcome, "outcome_id"), "outcome.outcome_id", code);
  const identityHash = sha256CanonicalJson({
    request_hash: requestHash,
    payload_hash: payloadHash,
    event_hash: event.event_hash,
    receipt_hash: receipt.receipt_hash,
  });
  if (outcomeId !== `MLO-${identityHash.slice("sha256:".length)}`) fail(code, "outcome_id mismatch");
  const normalized = {
    outcome_id: outcomeId,
    idempotency_key: idempotencyKey,
    request_hash: requestHash,
    decision,
    state_changed: stateChanged,
    blocking_hold_ids: blockingHoldIds,
    previous_state_hash: previousStateHash,
    new_state: newState,
    payload: normalizedPayload,
    payload_hash: payloadHash,
    action_intent: intent,
    event_record: event,
    effect_receipt: receipt,
  };
  const outcomeHash = requireSha256(readDataProperty(outcome, "outcome_hash"), "outcome.outcome_hash", code);
  if (outcomeHash !== sha256CanonicalJson(normalized)) fail("MEMORY_LIFECYCLE_OUTCOME_HASH_MISMATCH", "outcome_hash mismatch");
  return canonicalClone({ ...normalized, outcome_hash: outcomeHash });
};

const assertReplayBindings = (outcome, request, state, policy) => {
  const sameApprovalRecords =
    canonicalMemoryLifecycleJson(outcome.action_intent.approval_record_ids) ===
    canonicalMemoryLifecycleJson(request.approval_record_ids);
  const stateMatchesLineage =
    state.state_hash === outcome.previous_state_hash ||
    state.state_hash === outcome.new_state.state_hash;
  if (
    outcome.payload.request_id !== request.request_id ||
    outcome.payload.request_hash !== request.request_hash ||
    outcome.payload.policy_id !== policy.policy_id ||
    outcome.payload.policy_hash !== policy.policy_hash ||
    outcome.payload.memory_id !== request.memory_id ||
    outcome.payload.action_type !== request.action_type ||
    outcome.payload.occurred_at !== request.requested_at ||
    outcome.action_intent.run_id !== request.run_id ||
    outcome.action_intent.created_at !== request.requested_at ||
    !sameApprovalRecords ||
    outcome.event_record.run_id !== request.run_id ||
    outcome.event_record.sequence !== request.event_sequence ||
    outcome.event_record.previous_event_hash !== request.previous_event_hash ||
    outcome.event_record.actor_id !== request.actor_id ||
    outcome.event_record.occurred_at !== request.requested_at ||
    !stateMatchesLineage
  ) {
    fail(
      "MEMORY_LIFECYCLE_REPLAY_DIVERGENCE",
      "stored outcome does not match the current sealed request, policy, and memory lineage",
    );
  }
};

export const applyMemoryLifecycleRequest = (candidate) => {
  const code = "MEMORY_LIFECYCLE_INPUT_INVALID";
  const input = requirePlainDataObject(candidate, "MemoryLifecycleApplication", APPLICATION_FIELDS, code);
  const request = validateMemoryLifecycleRequest(readDataProperty(input, "request"));
  const state = validateMemoryLifecycleState(readDataProperty(input, "state"));
  const policy = validateMemoryLifecyclePolicy(readDataProperty(input, "policy"));
  const holds = readDenseArray(readDataProperty(input, "legal_holds"), "legal_holds", code)
    .map(validateLegalHold);
  if (new Set(holds.map((hold) => hold.hold_id)).size !== holds.length) {
    fail("DUPLICATE_LEGAL_HOLD", "legal hold IDs must be unique");
  }
  const priorOutcomes = readDenseArray(readDataProperty(input, "prior_outcomes"), "prior_outcomes", code)
    .map(validateMemoryLifecycleOutcome);
  if (new Set(priorOutcomes.map((outcome) => outcome.idempotency_key)).size !== priorOutcomes.length) {
    fail("DUPLICATE_LIFECYCLE_IDEMPOTENCY_KEY", "prior outcomes contain duplicate idempotency keys");
  }
  if (request.memory_id !== state.memory_id || request.workspace_id !== state.workspace_id) {
    fail("MEMORY_LIFECYCLE_TARGET_MISMATCH", "request target does not match memory state");
  }
  if (policy.workspace_id !== state.workspace_id) {
    fail("MEMORY_LIFECYCLE_POLICY_SCOPE_MISMATCH", "lifecycle policy does not govern this workspace");
  }
  const replay = priorOutcomes.find((outcome) => outcome.idempotency_key === request.idempotency_key);
  if (replay !== undefined) {
    if (replay.request_hash !== request.request_hash) {
      fail("MEMORY_LIFECYCLE_IDEMPOTENCY_CONFLICT", "idempotency key is bound to another request");
    }
    assertReplayBindings(replay, request, state, policy);
    return replay;
  }

  if (Date.parse(policy.effective_at) > Date.parse(request.requested_at)) {
    fail("MEMORY_LIFECYCLE_POLICY_NOT_EFFECTIVE", "lifecycle policy is not yet effective");
  }
  if (!policy.permitted_actions.includes(request.action_type)) {
    fail("MEMORY_LIFECYCLE_ACTION_DENIED", "lifecycle policy does not permit the requested action");
  }
  if (state.status !== "ACTIVE") {
    fail("MEMORY_LIFECYCLE_STATE_NOT_ACTIVE", "a new request cannot rewrite a terminal memory revision");
  }
  if (request.expected_revision !== state.revision) {
    fail("MEMORY_LIFECYCLE_REVISION_CONFLICT", "expected revision does not match memory state");
  }

  const blockingHolds = holds
    .filter((hold) => holdMatches(hold, state, request.requested_at))
    .sort((left, right) => compareStrings(left.hold_id, right.hold_id));
  const decision = blockingHolds.length > 0 ? "BLOCKED_LEGAL_HOLD" : "APPLIED";
  const retainedTombstoneHash =
    decision === "APPLIED" && policy.tombstone_hash_retention === "PERMITTED_BY_POLICY_AND_LAW"
      ? state.source_hash
      : null;
  const newState = decision === "BLOCKED_LEGAL_HOLD"
    ? state
    : sealMemoryLifecycleState({
      memory_id: state.memory_id,
      class: state.class,
      workspace_id: state.workspace_id,
      revision: state.revision + 1,
      status: request.action_type === "FORGET_MEMORY" ? "FORGOTTEN" : "DELETED",
      canonical_artifact_id: null,
      source_hash: retainedTombstoneHash,
      content: null,
      updated_at: request.requested_at,
    });
  const payload = canonicalClone({
    request_id: request.request_id,
    request_hash: request.request_hash,
    policy_id: policy.policy_id,
    policy_hash: policy.policy_hash,
    memory_id: state.memory_id,
    action_type: request.action_type,
    decision,
    previous_revision: state.revision,
    new_revision: newState.revision,
    previous_state_hash: state.state_hash,
    new_state_hash: newState.state_hash,
    blocking_hold_ids: blockingHolds.map((hold) => hold.hold_id),
    retained_tombstone_hash: retainedTombstoneHash,
    occurred_at: request.requested_at,
  });
  const payloadHash = sha256CanonicalJson(payload);
  const payloadId = `MLP-${payloadHash.slice("sha256:".length)}`;
  const intent = makeActionIntent(request);
  const event = makeEvent(request, state, decision, payloadId, payloadHash);
  const receipt = makeEffectReceipt(request, intent, decision, payloadId, newState.state_hash);
  const identityHash = sha256CanonicalJson({
    request_hash: request.request_hash,
    payload_hash: payloadHash,
    event_hash: event.event_hash,
    receipt_hash: receipt.receipt_hash,
  });
  const base = {
    outcome_id: `MLO-${identityHash.slice("sha256:".length)}`,
    idempotency_key: request.idempotency_key,
    request_hash: request.request_hash,
    decision,
    state_changed: decision === "APPLIED",
    blocking_hold_ids: blockingHolds.map((hold) => hold.hold_id),
    previous_state_hash: state.state_hash,
    new_state: newState,
    payload,
    payload_hash: payloadHash,
    action_intent: intent,
    event_record: event,
    effect_receipt: receipt,
  };
  return validateMemoryLifecycleOutcome({ ...base, outcome_hash: sha256CanonicalJson(base) });
};
