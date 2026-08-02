import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

const ARRAY_IS_ARRAY = Array.isArray;
const BUFFER_IS_BUFFER = Buffer.isBuffer;
const IS_PROMISE = utilTypes.isPromise;
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
const SEMVER_PATTERN = /^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$/u;
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|([+-])(\d{2}):(\d{2}))$/u;
const STREAM_SCHEMA_VERSION = "1.0.0";
const DEFAULT_EVENT_SCHEMA_VERSION = "4.0.0";
const EVENT_RECORD_TYPE = "noetic-ledger.event.v1";
const RUN_STREAM_RECORD_TYPE = "noetic-ledger.run-stream.v1";

const EVENT_INPUT_REQUIRED_KEYS = OBJECT_FREEZE([
  "event_id",
  "run_id",
  "event_type",
  "aggregate_type",
  "aggregate_id",
  "actor_id",
  "payload_artifact_id",
  "occurred_at",
]);
const EVENT_INPUT_ALLOWED_KEYS = OBJECT_FREEZE([
  ...EVENT_INPUT_REQUIRED_KEYS,
  "schema_version",
]);
const EVENT_RECORD_KEYS = OBJECT_FREEZE([
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
const EVENT_HASH_INPUT_KEYS = OBJECT_FREEZE(
  EVENT_RECORD_KEYS.filter((key) => key !== "event_hash"),
);
const STREAM_KEYS = OBJECT_FREEZE([
  "event_count",
  "event_ids",
  "run_id",
  "schema_version",
  "tail_event_hash",
  "tail_event_id",
]);
const APPEND_INTENT_KEYS = OBJECT_FREEZE([
  "event_id",
  "run_id",
  "event_type",
  "aggregate_type",
  "aggregate_id",
  "actor_id",
  "payload_artifact_id",
  "payload_hash",
  "occurred_at",
  "schema_version",
]);

export const NOETIC_LEDGER_RECORD_TYPES = OBJECT_FREEZE({
  EVENT: EVENT_RECORD_TYPE,
  RUN_STREAM: RUN_STREAM_RECORD_TYPE,
});

export class NoeticLedgerError extends Error {
  constructor(code, message, details = undefined, options = undefined) {
    super(message, options);
    this.name = "NoeticLedgerError";
    this.code = code;
    if (details !== undefined) this.details = OBJECT_FREEZE({ ...details });
  }
}

const fail = (code, message, details, options) => {
  throw new NoeticLedgerError(code, message, details, options);
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

const requireNonEmptyString = (value, label, code = "INVALID_INPUT") => {
  if (typeof value !== "string" || value.length === 0 || !hasOnlyUnicodeScalars(value)) {
    fail(code, `${label} must be a non-empty Unicode scalar string`);
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

const isLeapYear = (year) => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

const isCanonicalArrayIndex = (key, length) => {
  if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) return false;
  const index = Number(key);
  return NUMBER_IS_SAFE_INTEGER(index) && index >= 0 && index < length && String(index) === key;
};

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
    NUMBER_IS_FINITE(Date.parse(value))
  );
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
  if (ancestors.has(value)) {
    fail("NON_CANONICAL_JSON", `${label} contains a cyclic reference`);
  }

  ancestors.add(value);
  try {
    if (ARRAY_IS_ARRAY(value)) {
      const keys = REFLECT_OWN_KEYS(value);
      for (let keyIndex = 0; keyIndex < keys.length; keyIndex += 1) {
        const key = keys[keyIndex];
        if (key === "length") continue;
        if (!isCanonicalArrayIndex(key, value.length)) {
          fail("NON_CANONICAL_JSON", `${label} contains a non-element array property`);
        }
      }
      for (let index = 0; index < value.length; index += 1) {
        const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
        if (
          descriptor === undefined ||
          !descriptor.enumerable ||
          !OBJECT_HAS_OWN(descriptor, "value")
        ) {
          fail("NON_CANONICAL_JSON", `${label} contains a sparse or accessor array element`);
        }
        assertCanonicalJsonValue(descriptor.value, `${label}[${index}]`, ancestors);
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

const canonicalJson = (value) => {
  assertCanonicalJsonValue(value);
  return renderCanonicalJson(value);
};

const sha256Bytes = (bytes) =>
  `sha256:${createHash("sha256").update(bytes).digest("hex")}`;

const sha256CanonicalJson = (value) =>
  sha256Bytes(Buffer.from(canonicalJson(value), "utf8"));

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

const canonicalClone = (value) => deepFreeze(JSON.parse(canonicalJson(value)));

const normalizeEventInput = (input) => {
  const object = requirePlainDataObject(input, "event", {
    allowedKeys: EVENT_INPUT_ALLOWED_KEYS,
    requiredKeys: EVENT_INPUT_REQUIRED_KEYS,
  });
  const occurredAt = requireNonEmptyString(readDataProperty(object, "occurred_at"), "event.occurred_at");
  if (!isRfc3339(occurredAt)) {
    fail("INVALID_INPUT", "event.occurred_at must be a real RFC 3339 date-time");
  }
  const schemaVersion = OBJECT_HAS_OWN(object, "schema_version")
    ? requireNonEmptyString(readDataProperty(object, "schema_version"), "event.schema_version")
    : DEFAULT_EVENT_SCHEMA_VERSION;
  if (!SEMVER_PATTERN.test(schemaVersion)) {
    fail("INVALID_INPUT", "event.schema_version must satisfy the EventRecord schema");
  }
  return OBJECT_FREEZE({
    event_id: requireNonEmptyString(readDataProperty(object, "event_id"), "event.event_id"),
    run_id: requireNonEmptyString(readDataProperty(object, "run_id"), "event.run_id"),
    event_type: requireNonEmptyString(readDataProperty(object, "event_type"), "event.event_type"),
    aggregate_type: requireNonEmptyString(
      readDataProperty(object, "aggregate_type"),
      "event.aggregate_type",
    ),
    aggregate_id: requireNonEmptyString(
      readDataProperty(object, "aggregate_id"),
      "event.aggregate_id",
    ),
    actor_id: requireNonEmptyString(readDataProperty(object, "actor_id"), "event.actor_id"),
    payload_artifact_id: requireNonEmptyString(
      readDataProperty(object, "payload_artifact_id"),
      "event.payload_artifact_id",
    ),
    occurred_at: occurredAt,
    schema_version: schemaVersion,
  });
};

const eventHashInput = (event) => {
  const input = {};
  for (let index = 0; index < EVENT_HASH_INPUT_KEYS.length; index += 1) {
    const key = EVENT_HASH_INPUT_KEYS[index];
    if (!OBJECT_HAS_OWN(event, key)) {
      fail("EVENT_RECORD_INVALID", `EventRecord.${key} is required for hashing`);
    }
    input[key] = readDataProperty(event, key);
  }
  return input;
};

export const computeEventHash = (event) => sha256CanonicalJson(eventHashInput(event));

const validateEventRecord = (candidate) => {
  const event = requirePlainDataObject(candidate, "EventRecord", {
    allowedKeys: EVENT_RECORD_KEYS,
    code: "EVENT_RECORD_INVALID",
  });
  const strings = [
    "event_id",
    "run_id",
    "event_type",
    "aggregate_type",
    "aggregate_id",
    "actor_id",
    "payload_artifact_id",
  ];
  for (let index = 0; index < strings.length; index += 1) {
    const key = strings[index];
    requireNonEmptyString(readDataProperty(event, key), `EventRecord.${key}`, "EVENT_RECORD_INVALID");
  }
  const sequence = readDataProperty(event, "sequence");
  if (!NUMBER_IS_SAFE_INTEGER(sequence) || sequence < 1) {
    fail("EVENT_RECORD_INVALID", "EventRecord.sequence must be a positive safe integer");
  }
  const payloadHash = readDataProperty(event, "payload_hash");
  const previousEventHash = readDataProperty(event, "previous_event_hash");
  const eventHash = readDataProperty(event, "event_hash");
  if (typeof payloadHash !== "string" || !SHA256_PATTERN.test(payloadHash)) {
    fail("EVENT_RECORD_INVALID", "EventRecord.payload_hash is not canonical");
  }
  if (
    !(
      previousEventHash === null ||
      (typeof previousEventHash === "string" && SHA256_PATTERN.test(previousEventHash))
    )
  ) {
    fail("EVENT_RECORD_INVALID", "EventRecord.previous_event_hash is not canonical");
  }
  if (typeof eventHash !== "string" || !SHA256_PATTERN.test(eventHash)) {
    fail("EVENT_RECORD_INVALID", "EventRecord.event_hash is not canonical");
  }
  const occurredAt = readDataProperty(event, "occurred_at");
  if (!isRfc3339(occurredAt)) {
    fail("EVENT_RECORD_INVALID", "EventRecord.occurred_at is not a real RFC 3339 date-time");
  }
  const schemaVersion = readDataProperty(event, "schema_version");
  if (typeof schemaVersion !== "string" || !SEMVER_PATTERN.test(schemaVersion)) {
    fail("EVENT_RECORD_INVALID", "EventRecord.schema_version is not canonical");
  }
  const recomputed = computeEventHash(event);
  if (eventHash !== recomputed) {
    fail("EVENT_HASH_MISMATCH", "EventRecord.event_hash does not match its canonical fields", {
      eventId: readDataProperty(event, "event_id"),
      expected: recomputed,
      actual: eventHash,
    });
  }
  return canonicalClone(event);
};

const verifyAndCloneEventChain = (candidates) => {
  if (!ARRAY_IS_ARRAY(candidates) || IS_PROXY(candidates)) {
    fail("EVENT_CHAIN_INVALID", "events must be a plain dense array");
  }
  const events = new Array(candidates.length);
  const eventIds = new Set();
  let runId = null;
  let previousHash = null;
  for (let index = 0; index < candidates.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(candidates, String(index));
    if (descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail("EVENT_CHAIN_INVALID", "events must not be sparse or accessor-backed");
    }
    const event = validateEventRecord(descriptor.value);
    if (event.sequence !== index + 1) {
      fail("EVENT_SEQUENCE_MISMATCH", "event sequence is not contiguous", {
        eventId: event.event_id,
        expected: index + 1,
        actual: event.sequence,
      });
    }
    if (event.previous_event_hash !== previousHash) {
      fail("EVENT_CHAIN_MISMATCH", "event previous hash does not match the verified tail", {
        eventId: event.event_id,
        expected: previousHash,
        actual: event.previous_event_hash,
      });
    }
    if (runId === null) runId = event.run_id;
    if (event.run_id !== runId) {
      fail("EVENT_RUN_MISMATCH", "one event chain cannot contain multiple run IDs", {
        eventId: event.event_id,
        expected: runId,
        actual: event.run_id,
      });
    }
    if (eventIds.has(event.event_id)) {
      fail("EVENT_ID_DUPLICATE", "event ID appears more than once in one run", {
        eventId: event.event_id,
      });
    }
    eventIds.add(event.event_id);
    events[index] = event;
    previousHash = event.event_hash;
  }
  return OBJECT_FREEZE({
    eventCount: events.length,
    events: OBJECT_FREEZE(events),
    runId,
    tailEventHash: previousHash,
  });
};

export const verifyEventChain = (events) => {
  const result = verifyAndCloneEventChain(events);
  return OBJECT_FREEZE({
    event_count: result.eventCount,
    run_id: result.runId,
    tail_event_hash: result.tailEventHash,
  });
};

const validateRunStream = (record, expectedRunId) => {
  if (record.recordType !== RUN_STREAM_RECORD_TYPE || record.recordId !== expectedRunId) {
    fail("RUN_STREAM_INVALID", "run stream storage identity is inconsistent", {
      runId: expectedRunId,
    });
  }
  const stream = requirePlainDataObject(record.value, "run stream", {
    allowedKeys: STREAM_KEYS,
    code: "RUN_STREAM_INVALID",
  });
  const runId = requireNonEmptyString(
    readDataProperty(stream, "run_id"),
    "run stream.run_id",
    "RUN_STREAM_INVALID",
  );
  const eventCount = readDataProperty(stream, "event_count");
  const eventIds = readDataProperty(stream, "event_ids");
  if (runId !== expectedRunId) {
    fail("RUN_STREAM_INVALID", "run stream is bound to a different run ID", {
      expected: expectedRunId,
      actual: runId,
    });
  }
  if (readDataProperty(stream, "schema_version") !== STREAM_SCHEMA_VERSION) {
    fail("RUN_STREAM_INVALID", "run stream schema version is not supported", { runId });
  }
  if (!NUMBER_IS_SAFE_INTEGER(eventCount) || eventCount < 1) {
    fail("RUN_STREAM_INVALID", "run stream event_count must be positive", { runId });
  }
  if (!ARRAY_IS_ARRAY(eventIds) || IS_PROXY(eventIds) || eventIds.length !== eventCount) {
    fail("RUN_STREAM_INVALID", "run stream event_ids do not reconcile with event_count", {
      runId,
    });
  }
  if (record.revision !== eventCount - 1) {
    fail("RUN_STREAM_REVISION_MISMATCH", "run stream revision does not reconcile with event_count", {
      runId,
      revision: record.revision,
      eventCount,
    });
  }
  const normalizedIds = new Array(eventCount);
  const seen = new Set();
  for (let index = 0; index < eventCount; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(eventIds, String(index));
    if (descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail("RUN_STREAM_INVALID", "run stream event_ids are sparse or accessor-backed", { runId });
    }
    const eventId = requireNonEmptyString(
      descriptor.value,
      `run stream.event_ids[${index}]`,
      "RUN_STREAM_INVALID",
    );
    if (seen.has(eventId)) {
      fail("RUN_STREAM_INVALID", "run stream contains a duplicate event ID", { runId, eventId });
    }
    seen.add(eventId);
    normalizedIds[index] = eventId;
  }
  const tailEventId = requireNonEmptyString(
    readDataProperty(stream, "tail_event_id"),
    "run stream.tail_event_id",
    "RUN_STREAM_INVALID",
  );
  const tailEventHash = readDataProperty(stream, "tail_event_hash");
  if (
    typeof tailEventHash !== "string" ||
    !SHA256_PATTERN.test(tailEventHash) ||
    tailEventId !== normalizedIds[eventCount - 1]
  ) {
    fail("RUN_STREAM_INVALID", "run stream tail does not match its ordered event IDs", { runId });
  }
  return OBJECT_FREEZE({
    eventCount,
    eventIds: OBJECT_FREEZE(normalizedIds),
    runId,
    tailEventHash,
    tailEventId,
  });
};

const loadRunSnapshot = (store, runId) => {
  const streamRecord = store.readRevisionedRecord(RUN_STREAM_RECORD_TYPE, runId);
  if (streamRecord === null) {
    return OBJECT_FREEZE({
      events: OBJECT_FREEZE([]),
      streamRecord: null,
      tailEventHash: null,
    });
  }
  const stream = validateRunStream(streamRecord, runId);
  const candidates = new Array(stream.eventCount);
  for (let index = 0; index < stream.eventCount; index += 1) {
    const eventId = stream.eventIds[index];
    const eventRecord = store.readRevisionedRecord(EVENT_RECORD_TYPE, eventId);
    if (eventRecord === null) {
      fail("EVENT_RECORD_MISSING", "run stream references a missing immutable event", {
        runId,
        eventId,
      });
    }
    if (eventRecord.revision !== 0) {
      fail("EVENT_RECORD_MUTATED", "an immutable event record has a non-zero revision", {
        runId,
        eventId,
        revision: eventRecord.revision,
      });
    }
    if (eventRecord.recordType !== EVENT_RECORD_TYPE || eventRecord.recordId !== eventId) {
      fail("EVENT_RECORD_INVALID", "event storage identity is inconsistent", { runId, eventId });
    }
    candidates[index] = eventRecord.value;
  }
  const chain = verifyAndCloneEventChain(candidates);
  if (chain.runId !== runId) {
    fail("EVENT_RUN_MISMATCH", "run stream contains an event from another run", {
      expected: runId,
      actual: chain.runId,
    });
  }
  for (let index = 0; index < chain.events.length; index += 1) {
    if (chain.events[index].event_id !== stream.eventIds[index]) {
      fail("RUN_STREAM_ORDER_MISMATCH", "run stream order differs from immutable event identity", {
        runId,
        sequence: index + 1,
      });
    }
  }
  if (
    chain.tailEventHash !== stream.tailEventHash ||
    chain.events[chain.events.length - 1].event_id !== stream.tailEventId
  ) {
    fail("RUN_STREAM_TAIL_MISMATCH", "run stream tail differs from the verified event chain", {
      runId,
    });
  }
  return OBJECT_FREEZE({
    events: chain.events,
    streamRecord,
    tailEventHash: chain.tailEventHash,
  });
};

const buildRunStream = (runId, events) => {
  const tail = events[events.length - 1];
  return {
    event_count: events.length,
    event_ids: events.map((event) => event.event_id),
    run_id: runId,
    schema_version: STREAM_SCHEMA_VERSION,
    tail_event_hash: tail.event_hash,
    tail_event_id: tail.event_id,
  };
};

const sameAppendIntent = (event, intent) => {
  for (let index = 0; index < APPEND_INTENT_KEYS.length; index += 1) {
    const key = APPEND_INTENT_KEYS[index];
    if (event[key] !== intent[key]) return false;
  }
  return true;
};

const normalizePayloadBytes = (value, artifactId) => {
  if (IS_PROXY(value) || !(BUFFER_IS_BUFFER(value) || value instanceof Uint8Array)) {
    fail("PAYLOAD_RESOLUTION_FAILED", "artifact store returned non-byte payload content", {
      artifactId,
    });
  }
  return Buffer.from(value);
};

const resolvePayload = (artifactStore, artifactId) => {
  let value;
  try {
    value = artifactStore.readArtifact(artifactId);
  } catch (error) {
    fail(
      "PAYLOAD_RESOLUTION_FAILED",
      "payload artifact could not be resolved and integrity-verified",
      {
        artifactId,
        causeCode:
          error !== null && typeof error === "object" && typeof error.code === "string"
            ? error.code
            : error instanceof Error
              ? error.name
              : "unknown",
      },
      { cause: error },
    );
  }
  const bytes = normalizePayloadBytes(value, artifactId);
  return OBJECT_FREEZE({ bytes, payloadHash: sha256Bytes(bytes) });
};

const parsePayloadBytes = (value) => {
  const bytes = normalizePayloadBytes(value, "inline-payload");
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    fail("PAYLOAD_JSON_INVALID", "JSON payload must not contain a UTF-8 BOM");
  }
  let text;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch (error) {
    fail("PAYLOAD_JSON_INVALID", "payload bytes are not valid UTF-8", undefined, {
      cause: error,
    });
  }
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    fail("PAYLOAD_JSON_INVALID", "payload bytes are not valid JSON", undefined, {
      cause: error,
    });
  }
  try {
    return canonicalClone(parsed);
  } catch (error) {
    if (error instanceof NoeticLedgerError) {
      fail("PAYLOAD_JSON_INVALID", "payload JSON is outside the canonical JSON value domain", {
        causeCode: error.code,
      });
    }
    throw error;
  }
};

export const decodeJsonPayload = (bytes) => parsePayloadBytes(bytes);

const validateDependencies = (options) => {
  const object = requirePlainDataObject(options, "ledger options", {
    allowedKeys: ["artifactStore", "stateStore"],
  });
  const artifactStore = readDataProperty(object, "artifactStore");
  const stateStore = readDataProperty(object, "stateStore");
  if (
    artifactStore === null ||
    (typeof artifactStore !== "object" && typeof artifactStore !== "function") ||
    typeof artifactStore.readArtifact !== "function"
  ) {
    fail("INVALID_INPUT", "artifactStore must expose readArtifact(artifactId)");
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
  return OBJECT_FREEZE({ artifactStore, stateStore });
};

const normalizeRebuildOptions = (options) => {
  const object = requirePlainDataObject(options, "rebuild options", {
    allowedKeys: ["initialState", "reducer"],
  });
  const reducer = readDataProperty(object, "reducer");
  if (typeof reducer !== "function") {
    fail("INVALID_INPUT", "rebuild options.reducer must be a synchronous function");
  }
  let initialState;
  try {
    initialState = canonicalClone(readDataProperty(object, "initialState"));
  } catch (error) {
    if (error instanceof NoeticLedgerError) {
      fail("INVALID_INPUT", "rebuild options.initialState must be canonical JSON", {
        causeCode: error.code,
      });
    }
    throw error;
  }
  return OBJECT_FREEZE({ initialState, reducer });
};

const runReducerPass = (events, payloads, initialState, reducer, pass) => {
  let state = canonicalClone(initialState);
  const trace = new Array(events.length);
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    const context = OBJECT_FREEZE({
      event,
      payloadBytes: Buffer.from(payloads[index]),
    });
    let nextState;
    try {
      nextState = reducer(state, context);
    } catch (error) {
      fail(
        "REDUCER_FAILED",
        "reducer threw while rebuilding canonical state",
        { eventId: event.event_id, pass, sequence: event.sequence },
        { cause: error },
      );
    }
    if (IS_PROMISE(nextState)) {
      nextState.catch(() => undefined);
      fail("ASYNC_REDUCER_DENIED", "reducers must be synchronous and side-effect free", {
        eventId: event.event_id,
        pass,
        sequence: event.sequence,
      });
    }
    let rendered;
    try {
      rendered = canonicalJson(nextState);
    } catch (error) {
      if (error instanceof NoeticLedgerError) {
        fail("REDUCER_OUTPUT_INVALID", "reducer output is not canonical JSON", {
          causeCode: error.code,
          eventId: event.event_id,
          pass,
          sequence: event.sequence,
        });
      }
      throw error;
    }
    state = deepFreeze(JSON.parse(rendered));
    trace[index] = rendered;
  }
  return OBJECT_FREEZE({ state, trace: OBJECT_FREEZE(trace) });
};

const assertDeterministicTrace = (left, right, events) => {
  for (let index = 0; index < left.trace.length; index += 1) {
    if (left.trace[index] !== right.trace[index]) {
      fail("REDUCER_NON_DETERMINISTIC", "two isolated reducer passes produced different state", {
        eventId: events[index].event_id,
        sequence: events[index].sequence,
      });
    }
  }
};

const CONSTRUCTOR_TOKEN = Symbol("NoeticLedger");

export class NoeticLedger {
  #artifactStore;
  #stateStore;

  constructor(token, dependencies) {
    if (token !== CONSTRUCTOR_TOKEN) {
      fail("DIRECT_CONSTRUCTION_DENIED", "use createNoeticLedger()");
    }
    this.#artifactStore = dependencies.artifactStore;
    this.#stateStore = dependencies.stateStore;
  }

  append(input) {
    const normalized = normalizeEventInput(input);
    const payload = resolvePayload(this.#artifactStore, normalized.payload_artifact_id);
    const intent = OBJECT_FREEZE({ ...normalized, payload_hash: payload.payloadHash });

    return this.#stateStore.transaction((store) => {
      const existingRecord = store.readRevisionedRecord(EVENT_RECORD_TYPE, normalized.event_id);
      if (existingRecord !== null) {
        if (existingRecord.revision !== 0) {
          fail("EVENT_RECORD_MUTATED", "an immutable event record has a non-zero revision", {
            eventId: normalized.event_id,
            revision: existingRecord.revision,
          });
        }
        const existing = validateEventRecord(existingRecord.value);
        if (!sameAppendIntent(existing, intent)) {
          fail("EVENT_ID_CONFLICT", "event ID is already bound to a different immutable event", {
            eventId: normalized.event_id,
          });
        }
        const snapshot = loadRunSnapshot(store, normalized.run_id);
        if (
          existing.sequence > snapshot.events.length ||
          snapshot.events[existing.sequence - 1]?.event_id !== existing.event_id
        ) {
          fail("EVENT_RECORD_ORPHANED", "existing event is not reconciled with its run stream", {
            eventId: existing.event_id,
            runId: existing.run_id,
          });
        }
        return OBJECT_FREEZE({ event: existing, status: "EXISTING" });
      }

      const snapshot = loadRunSnapshot(store, normalized.run_id);
      const previousEventHash = snapshot.tailEventHash;
      const eventWithoutHash = {
        event_id: normalized.event_id,
        run_id: normalized.run_id,
        sequence: snapshot.events.length + 1,
        event_type: normalized.event_type,
        aggregate_type: normalized.aggregate_type,
        aggregate_id: normalized.aggregate_id,
        actor_id: normalized.actor_id,
        payload_artifact_id: normalized.payload_artifact_id,
        payload_hash: payload.payloadHash,
        previous_event_hash: previousEventHash,
        occurred_at: normalized.occurred_at,
        schema_version: normalized.schema_version,
      };
      const event = validateEventRecord({
        ...eventWithoutHash,
        event_hash: computeEventHash(eventWithoutHash),
      });
      store.createRevisionedRecord({
        recordType: EVENT_RECORD_TYPE,
        recordId: event.event_id,
        value: event,
      });
      const nextEvents = [...snapshot.events, event];
      const streamValue = buildRunStream(normalized.run_id, nextEvents);
      if (snapshot.streamRecord === null) {
        store.createRevisionedRecord({
          recordType: RUN_STREAM_RECORD_TYPE,
          recordId: normalized.run_id,
          value: streamValue,
        });
      } else {
        const update = store.compareAndSwapRevision({
          recordType: RUN_STREAM_RECORD_TYPE,
          recordId: normalized.run_id,
          expectedRevision: snapshot.streamRecord.revision,
          value: streamValue,
        });
        if (!update.ok) {
          fail("LEDGER_APPEND_COMMIT_FAILED", "run stream CAS did not commit under write lock", {
            runId: normalized.run_id,
            status: update.status,
          });
        }
      }
      const committed = loadRunSnapshot(store, normalized.run_id);
      const committedTail = committed.events[committed.events.length - 1];
      if (committedTail.event_id !== event.event_id || committedTail.event_hash !== event.event_hash) {
        fail("LEDGER_APPEND_RECONCILIATION_FAILED", "appended event is not the committed run tail", {
          eventId: event.event_id,
          runId: event.run_id,
        });
      }
      return OBJECT_FREEZE({ event, status: "APPENDED" });
    });
  }

  readEvents(runId) {
    const id = requireNonEmptyString(runId, "runId");
    return this.#stateStore.transaction((store) => loadRunSnapshot(store, id).events);
  }

  tail(runId) {
    const events = this.readEvents(runId);
    return events.length === 0 ? null : events[events.length - 1];
  }

  verifyRun(runId) {
    const id = requireNonEmptyString(runId, "runId");
    const events = this.readEvents(id);
    for (let index = 0; index < events.length; index += 1) {
      const event = events[index];
      const payload = resolvePayload(this.#artifactStore, event.payload_artifact_id);
      if (payload.payloadHash !== event.payload_hash) {
        fail("PAYLOAD_HASH_MISMATCH", "payload artifact hash differs from the sealed event", {
          eventId: event.event_id,
          expected: event.payload_hash,
          actual: payload.payloadHash,
        });
      }
    }
    return OBJECT_FREEZE({
      event_count: events.length,
      payload_hashes_verified: events.length,
      run_id: id,
      tail_event_hash: events.length === 0 ? null : events[events.length - 1].event_hash,
    });
  }

  rebuild(runId, options) {
    const id = requireNonEmptyString(runId, "runId");
    const normalized = normalizeRebuildOptions(options);
    const events = this.readEvents(id);
    const payloads = new Array(events.length);
    for (let index = 0; index < events.length; index += 1) {
      const event = events[index];
      const payload = resolvePayload(this.#artifactStore, event.payload_artifact_id);
      if (payload.payloadHash !== event.payload_hash) {
        fail("PAYLOAD_HASH_MISMATCH", "payload artifact hash differs from the sealed event", {
          eventId: event.event_id,
          expected: event.payload_hash,
          actual: payload.payloadHash,
        });
      }
      payloads[index] = payload.bytes;
    }
    const first = runReducerPass(
      events,
      payloads,
      normalized.initialState,
      normalized.reducer,
      1,
    );
    const second = runReducerPass(
      events,
      payloads,
      normalized.initialState,
      normalized.reducer,
      2,
    );
    assertDeterministicTrace(first, second, events);
    return OBJECT_FREEZE({
      event_count: events.length,
      run_id: id,
      state: first.state,
      state_hash: sha256CanonicalJson(first.state),
      tail_event_hash: events.length === 0 ? null : events[events.length - 1].event_hash,
    });
  }
}

export const createNoeticLedger = (options) =>
  new NoeticLedger(CONSTRUCTOR_TOKEN, validateDependencies(options));
