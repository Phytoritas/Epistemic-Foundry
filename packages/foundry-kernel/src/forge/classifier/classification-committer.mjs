import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

import {
  bindClassificationWorkerAuthority,
} from "./classification-worker-authority.mjs";

import {
  applyHumanClassificationOverride,
  assertClassificationArtifactIntegrity,
  assertStrictClassificationReplay,
  canonicalizeClassificationJson,
  classificationIdempotencyKey,
  evaluateEpistemicWork,
  materializeClassificationArtifact,
  sealClassificationSupersession,
  sha256ClassificationJson,
  validateHumanDecisionArtifact,
  validateClassifierCapabilities,
  EpistemicWorkClassifierError,
  CLASSIFICATION_SCHEMA_ID,
} from "./epistemic-work-classifier.mjs";

const OBJECT_FREEZE = Object.freeze;
const ARRAY_PROTOTYPE = Array.prototype;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const CLASSIFICATION_ID_PATTERN = /^EWC-[0-9a-f]{64}$/u;
const SEMVER_PATTERN = /^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$/u;
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:[Zz]|([+-])(\d{2}):(\d{2}))$/u;
const EVENT_SCHEMA_VERSION = "4.0.0";
const ACTOR_ID = "ACT-F01-classification-committer";
const OUTBOX_INDEX_ID = "global";

const D03_MANIFEST_KEYS = OBJECT_FREEZE([
  "artifact_id",
  "artifact_type",
  "byte_size",
  "confidentiality",
  "content_hash",
  "created_at",
  "created_by",
  "encryption",
  "input_artifact_ids",
  "integrity_status",
  "license",
  "lineage_event_ids",
  "media_type",
  "provenance_manifest_id",
  "retention_class",
  "storage_uri",
]);
const D03_ENCRYPTION_KEYS = OBJECT_FREEZE(["at_rest", "in_transit", "key_ref"]);
const D03_RECEIPT_KEYS = OBJECT_FREEZE([
  "action_intent_id",
  "artifact_id",
  "byte_size",
  "content_hash",
  "created_at",
  "created_by",
  "locator",
  "media_type",
  "receipt_hash",
  "receipt_id",
  "schema_ref",
  "validation_results",
]);
const D03_RECEIPT_CREATOR_KEYS = OBJECT_FREEZE(["actor_id", "actor_type"]);
const D03_VALIDATION_ROW_KEYS = OBJECT_FREEZE(["check", "details", "status"]);
const E01_EVENT_RECORD_KEYS = OBJECT_FREEZE([
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
const E01_EVENT_HASH_INPUT_KEYS = OBJECT_FREEZE(
  E01_EVENT_RECORD_KEYS.filter((key) => key !== "event_hash"),
);
const CLASSIFICATION_PREPARATION_STATES = new WeakMap();

export const CLASSIFICATION_RECORD_TYPES = OBJECT_FREEZE({
  CLASSIFICATION: "foundry.forge.classification.v1",
  IDEMPOTENCY: "foundry.forge.classification-idempotency.v1",
  HUMAN_DECISION_BINDING: "foundry.forge.classification-human-decision.v1",
  ACTIVE: "foundry.forge.classification-active.v1",
  OUTBOX: "foundry.forge.classification-outbox.v1",
  OUTBOX_INDEX: "foundry.forge.classification-outbox-index.v1",
});

export const CLASSIFICATION_EVENT_TYPES = OBJECT_FREEZE({
  CLASSIFIED: "forge.epistemic-work.classified",
  RECLASSIFIED: "forge.epistemic-work.reclassified",
  OVERRIDDEN: "forge.epistemic-work.override-recorded",
});

const CLASSIFICATION_EVENT_TYPE_SET = new Set(Object.values(CLASSIFICATION_EVENT_TYPES));

export class ClassificationCommitterError extends Error {
  constructor(code, message, details = undefined, options = undefined) {
    super(message, options);
    this.name = "ClassificationCommitterError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(cloneJson(details));
  }
}

const fail = (code, message, details, options) => {
  throw new ClassificationCommitterError(code, message, details, options);
};

const dependencyCauseCode = (error) =>
  error !== null && typeof error === "object" && typeof error.code === "string"
    ? error.code
    : error instanceof Error
      ? error.name
      : "unknown";

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of Reflect.ownKeys(value)) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (descriptor !== undefined && Object.hasOwn(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};

const cloneJson = (value) => JSON.parse(JSON.stringify(value));

const requireString = (value, label) => {
  if (typeof value !== "string" || value.length === 0) {
    fail("INVALID_INPUT", `${label} must be a non-empty string`);
  }
  return value;
};

const requireHash = (value, label) => {
  const candidate = requireString(value, label);
  if (!SHA256_PATTERN.test(candidate)) fail("INVALID_INPUT", `${label} must be a SHA-256`);
  return candidate;
};

const timestampFromClock = (clock) => {
  const value = clock();
  const timestamp = value instanceof Date ? value.toISOString() : value;
  if (typeof timestamp !== "string") fail("CLASSIFIER_CLOCK_INVALID", "clock must return a Date or string");
  const parsed = new Date(timestamp);
  if (!Number.isFinite(parsed.valueOf())) fail("CLASSIFIER_CLOCK_INVALID", "clock returned an invalid timestamp");
  const canonical = parsed.toISOString();
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/u.test(canonical)) {
    fail("CLASSIFIER_CLOCK_INVALID", "clock timestamp is outside the canonical range");
  }
  return canonical;
};

const requireDependencyMethod = (dependency, method, label) => {
  if (dependency === null || typeof dependency !== "object" || typeof dependency[method] !== "function") {
    fail("INVALID_DEPENDENCY", `${label}.${method} is required`);
  }
};

const normalizeDependencies = (options) => {
  if (options === null || typeof options !== "object" || Array.isArray(options)) {
    fail("INVALID_DEPENDENCY", "committer options must be an object");
  }
  const { artifactStore, ledger, stateStore, clock = () => new Date() } = options;
  requireDependencyMethod(artifactStore, "putArtifact", "artifactStore");
  requireDependencyMethod(artifactStore, "readArtifact", "artifactStore");
  requireDependencyMethod(artifactStore, "readManifest", "artifactStore");
  requireDependencyMethod(artifactStore, "readReceipt", "artifactStore");
  requireDependencyMethod(artifactStore, "enumerateReceipts", "artifactStore");
  requireDependencyMethod(ledger, "append", "ledger");
  requireDependencyMethod(stateStore, "transaction", "stateStore");
  requireDependencyMethod(stateStore, "readRevisionedRecord", "stateStore");
  if (typeof clock !== "function") fail("INVALID_DEPENDENCY", "clock must be a function");
  return { artifactStore, ledger, stateStore, clock };
};

const recordValue = (record, label) => {
  if (record === null) return null;
  if (!Number.isSafeInteger(record.revision) || record.revision < 0) {
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `${label} has an invalid revision`);
  }
  if (record.value === null || typeof record.value !== "object" || Array.isArray(record.value)) {
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `${label} has an invalid value`);
  }
  return record.value;
};

const classificationState = (record) => {
  const value = recordValue(record, "classification record");
  if (value === null) return null;
  const required = [
    "classification",
    "identity_context",
    "accepted_signals",
    "floor_work_class",
    "interview_rules",
    "classifier_trace",
    "run_id",
    "receipt_id",
    "event_id",
    "outbox_id",
  ];
  for (const key of required) {
    if (!Object.hasOwn(value, key)) {
      fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `classification record misses ${key}`);
    }
  }
  assertClassificationArtifactIntegrity(value.classification, value.identity_context);
  if (value.classification.classification_id !== record.recordId || record.revision !== 0) {
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", "classification record identity or immutability changed");
  }
  return deepFreeze(cloneJson(value));
};

const activeState = (record) => {
  const value = recordValue(record, "active classification pointer");
  if (value === null) return null;
  for (const key of [
    "request_id",
    "request_input_hash",
    "classification_id",
    "classification_hash",
    "classified_at",
  ]) {
    if (!Object.hasOwn(value, key)) {
      fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `active pointer misses ${key}`);
    }
  }
  if (
    value.request_id !== record.recordId ||
    !CLASSIFICATION_ID_PATTERN.test(value.classification_id) ||
    !SHA256_PATTERN.test(value.classification_hash) ||
    value.classification_id !== `EWC-${value.classification_hash.slice("sha256:".length)}`
  ) {
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", "active pointer identity is invalid");
  }
  return deepFreeze(cloneJson(value));
};

const loadClassification = (store, classificationId) => {
  const record = store.readRevisionedRecord(
    CLASSIFICATION_RECORD_TYPES.CLASSIFICATION,
    classificationId,
  );
  const value = classificationState(record);
  if (value === null) fail("CLASSIFICATION_NOT_FOUND", "classification does not exist", { classificationId });
  return value;
};

const updateRecord = (store, record, value, label) => {
  const update = store.compareAndSwapRevision({
    recordType: record.recordType,
    recordId: record.recordId,
    expectedRevision: record.revision,
    value,
  });
  if (!update.ok) {
    fail("CLASSIFICATION_COMMIT_CONFLICT", `${label} compare-and-swap failed`, {
      status: update.status,
    });
  }
  return update.record;
};

const appendOutboxIndex = (store, outboxId) => {
  const record = store.readRevisionedRecord(
    CLASSIFICATION_RECORD_TYPES.OUTBOX_INDEX,
    OUTBOX_INDEX_ID,
  );
  if (record === null) {
    store.createRevisionedRecord({
      recordType: CLASSIFICATION_RECORD_TYPES.OUTBOX_INDEX,
      recordId: OUTBOX_INDEX_ID,
      value: { outbox_ids: [outboxId] },
    });
    return;
  }
  const value = recordValue(record, "classification outbox index");
  if (!Array.isArray(value.outbox_ids) || value.outbox_ids.some((id) => typeof id !== "string")) {
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", "classification outbox index is invalid");
  }
  if (value.outbox_ids.includes(outboxId)) {
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", "classification outbox index contains a duplicate");
  }
  updateRecord(
    store,
    record,
    { outbox_ids: [...value.outbox_ids, outboxId] },
    "classification outbox index",
  );
};

const identityContextFor = (decision) => ({
  request_input_hash: decision.request_input_hash,
  policy_bundle_hash: decision.policy_bundle_hash,
  accepted_signals: [...decision.accepted_signals],
  supersedes_classification_hash: decision.supersedes_classification_hash,
  human_decision_hash: decision.human_decision_hash,
});

const priorContextFor = (state) =>
  state === null
    ? null
    : {
        request_id: state.classification.request_id,
        accepted_signals: [...state.accepted_signals],
      };

const decisionFromState = (state) => ({
  ...cloneJson(state.classification),
  request_input_hash: state.identity_context.request_input_hash,
  policy_bundle_hash: state.identity_context.policy_bundle_hash,
  accepted_signals: [...state.accepted_signals],
  supersedes_classification_hash: state.identity_context.supersedes_classification_hash,
  human_decision_hash: state.identity_context.human_decision_hash,
  run_id: state.run_id,
  floor_work_class: state.floor_work_class,
  interview_rules: [...state.interview_rules],
  classifier_trace: cloneJson(state.classifier_trace),
});

const resultFromState = (state, artifactStore, status) => {
  let receipt;
  try {
    receipt = artifactStore.readReceipt(state.receipt_id);
  } catch (error) {
    fail(
      "CLASSIFICATION_RECONCILIATION_REQUIRED",
      "classification state exists but its ArtifactReceipt is unavailable",
      { classificationId: state.classification.classification_id, causeCode: dependencyCauseCode(error) },
      { cause: error },
    );
  }
  return deepFreeze({
    status,
    classification: cloneJson(state.classification),
    artifact_receipt: cloneJson(receipt),
    accepted_signals: [...state.accepted_signals],
    floor_work_class: state.floor_work_class,
    interview_rules: [...state.interview_rules],
    classifier_trace: cloneJson(state.classifier_trace),
  });
};

const artifactMetadata = (state) => ({
  artifact: {
    artifactId: state.classification.classification_id,
    artifactType: "epistemic_work_classification",
    confidentiality: "internal",
    createdAt: state.classification.classified_at,
    createdBy: ACTOR_ID,
    encryption: { atRest: true, inTransit: true, keyRef: null },
    inputArtifactIds: [],
    license: null,
    lineageEventIds: [],
    mediaType: "application/json",
    provenanceManifestId: `PROV-${state.classification.classification_id}`,
    retentionClass: "permanent",
  },
  receipt: {
    actionIntentId: null,
    createdAt: state.classification.classified_at,
    createdBy: { actorId: ACTOR_ID, actorType: "service" },
    receiptId: state.receipt_id,
    schemaRef: CLASSIFICATION_SCHEMA_ID,
    validationResults: [
      {
        check: "epistemic_work_classification_contract",
        status: "PASS",
        details: state.classification.classification_hash,
      },
    ],
  },
});

const eventAggregateFor = (state) => {
  const supersededHash = state.identity_context.supersedes_classification_hash;
  if (supersededHash === null) {
    return {
      aggregate_type: "epistemic_work_classification",
      aggregate_id: state.classification.classification_id,
    };
  }
  return {
    aggregate_type: "epistemic_work_classification_supersession",
    aggregate_id: `EWC-${supersededHash.slice("sha256:".length)}`,
  };
};

const readDataProperty = (object, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(object, key).value;

const requireExactPlainDataObject = (
  value,
  label,
  expectedKeys,
  { allowNullPrototype = false } = {},
) => {
  if (
    value === null ||
    typeof value !== "object" ||
    IS_PROXY(value) ||
    Array.isArray(value)
  ) {
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `${label} must be a plain data object`);
  }
  const prototype = OBJECT_GET_PROTOTYPE_OF(value);
  if (
    prototype !== PLAIN_OBJECT_PROTOTYPE &&
    !(allowNullPrototype && prototype === null)
  ) {
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `${label} has a custom prototype`);
  }
  const keys = REFLECT_OWN_KEYS(value);
  if (keys.length !== expectedKeys.length) {
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `${label} has a non-canonical field set`);
  }
  const expected = new Set(expectedKeys);
  for (let index = 0; index < keys.length; index += 1) {
    const key = keys[index];
    if (typeof key !== "string" || !expected.has(key)) {
      fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `${label} has a non-canonical field set`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !Object.hasOwn(descriptor, "value")
    ) {
      fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `${label}.${key} must be a data property`);
    }
  }
  return value;
};

const isCanonicalArrayIndex = (key, length) => {
  if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) return false;
  const index = Number(key);
  return Number.isSafeInteger(index) && index >= 0 && index < length && String(index) === key;
};

const requireDenseDataArray = (value, label) => {
  if (
    value === null ||
    typeof value !== "object" ||
    IS_PROXY(value) ||
    !Array.isArray(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== ARRAY_PROTOTYPE
  ) {
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `${label} must be a plain dense array`);
  }
  const lengthDescriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, "length");
  if (
    lengthDescriptor === undefined ||
    !Object.hasOwn(lengthDescriptor, "value") ||
    !Number.isSafeInteger(lengthDescriptor.value) ||
    lengthDescriptor.value < 0
  ) {
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `${label} has an invalid length`);
  }
  const length = lengthDescriptor.value;
  const keys = REFLECT_OWN_KEYS(value);
  if (keys.length !== length + 1) {
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `${label} has non-element properties`);
  }
  for (let keyIndex = 0; keyIndex < keys.length; keyIndex += 1) {
    const key = keys[keyIndex];
    if (key !== "length" && !isCanonicalArrayIndex(key, length)) {
      fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `${label} has non-element properties`);
    }
  }
  const elements = new Array(length);
  for (let index = 0; index < length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !Object.hasOwn(descriptor, "value")
    ) {
      fail(
        "CLASSIFICATION_STATE_INTEGRITY_FAILED",
        `${label} must not be sparse or accessor-backed`,
      );
    }
    elements[index] = descriptor.value;
  }
  return elements;
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

const isLeapYear = (year) => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

const daysInMonth = (year, month) =>
  [31, isLeapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][
    month - 1
  ];

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
  if (
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > daysInMonth(year, month) ||
    hour > 23 ||
    minute > 59 ||
    second > 60 ||
    offsetHour > 23 ||
    offsetMinute > 59
  ) {
    return false;
  }
  if (second <= 59) return true;
  const offsetSign = match[7] === "-" ? -1 : 1;
  const offsetMinutes =
    match[7] === undefined ? 0 : offsetSign * (offsetHour * 60 + offsetMinute);
  const utcMinutes = hour * 60 + minute - offsetMinutes;
  const utcMinuteOfDay = ((utcMinutes % 1_440) + 1_440) % 1_440;
  if (utcMinuteOfDay !== 23 * 60 + 59) return false;
  let utcYear = year;
  let utcMonth = month;
  let utcDay = day + Math.floor(utcMinutes / 1_440);
  if (utcDay < 1) {
    utcMonth -= 1;
    if (utcMonth < 1) {
      utcYear -= 1;
      utcMonth = 12;
    }
    utcDay = daysInMonth(utcYear, utcMonth);
  } else if (utcDay > daysInMonth(utcYear, utcMonth)) {
    utcDay = 1;
    utcMonth += 1;
    if (utcMonth > 12) {
      utcYear += 1;
      utcMonth = 1;
    }
  }
  return utcDay === daysInMonth(utcYear, utcMonth);
};

const sha256Bytes = (bytes) =>
  `sha256:${createHash("sha256").update(bytes).digest("hex")}`;

const computeReplayEventHash = (event) => {
  const preimage = {};
  for (let index = 0; index < E01_EVENT_HASH_INPUT_KEYS.length; index += 1) {
    const key = E01_EVENT_HASH_INPUT_KEYS[index];
    preimage[key] = event[key];
  }
  return sha256ClassificationJson(preimage);
};

const withReplayIntegrityBoundary = (operation, message) => {
  try {
    return operation();
  } catch (error) {
    if (error instanceof ClassificationCommitterError) throw error;
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", message);
  }
};

const withReplaySnapshotBoundary = (operation) => {
  try {
    return operation();
  } catch (error) {
    if (error instanceof ClassificationCommitterError) throw error;
    if (error instanceof EpistemicWorkClassifierError) {
      fail(
        "CLASSIFICATION_STATE_INTEGRITY_FAILED",
        "classification replay snapshot failed integrity validation",
      );
    }
    fail(
      "CLASSIFICATION_RECONCILIATION_REQUIRED",
      "classification replay snapshot could not be resolved",
    );
  }
};

const assertReplaySnapshot = (state, outbox, outboxRevision) => {
  const digest = state.classification.classification_hash.slice("sha256:".length);
  if (
    typeof state.run_id !== "string" ||
    state.run_id.length === 0 ||
    state.receipt_id !== `AR-F01-${digest}` ||
    state.event_id !== `EVT-F01-${digest}` ||
    state.outbox_id !== `OUTBOX-F01-${digest}` ||
    !CLASSIFICATION_EVENT_TYPE_SET.has(state.event_type)
  ) {
    fail(
      "CLASSIFICATION_STATE_INTEGRITY_FAILED",
      "classification replay identity is inconsistent",
    );
  }
  if (!outbox.published) {
    fail(
      "CLASSIFICATION_RECONCILIATION_REQUIRED",
      "classification replay requires a published outbox",
      { classificationId: state.classification.classification_id },
    );
  }
  if (outboxRevision !== 1) {
    fail(
      "CLASSIFICATION_STATE_INTEGRITY_FAILED",
      "published classification outbox revision is invalid",
    );
  }
  if (
    outbox.outbox_id !== state.outbox_id ||
    outbox.classification_id !== state.classification.classification_id ||
    outbox.event_id !== state.event_id ||
    outbox.run_id !== state.run_id ||
    outbox.event_type !== state.event_type ||
    !SHA256_PATTERN.test(outbox.event_hash) ||
    !SHA256_PATTERN.test(outbox.receipt_hash)
  ) {
    fail(
      "CLASSIFICATION_STATE_INTEGRITY_FAILED",
      "published classification outbox does not bind replay state",
    );
  }
};

const readReplayEvidence = ({ artifactStore, ledger, state }) => {
  try {
    return {
      manifest: artifactStore.readManifest(state.classification.classification_id),
      bytes: artifactStore.readArtifact(state.classification.classification_id),
      receipt: artifactStore.readReceipt(state.receipt_id),
      events: ledger.readEvents(state.run_id),
    };
  } catch {
    fail(
      "CLASSIFICATION_RECONCILIATION_REQUIRED",
      "classification replay dependencies could not resolve D03 and E01 state",
      { classificationId: state.classification.classification_id },
    );
  }
};

const validationRowMatches = (row, check, details) =>
  row.check === check &&
  row.status === "PASS" &&
  row.details === details;

const validateReplayArtifact = ({ state, outbox, manifest, bytes, receipt }) => {
  if (
    bytes === null ||
    typeof bytes !== "object" ||
    IS_PROXY(bytes)
  ) {
    fail(
      "CLASSIFICATION_STATE_INTEGRITY_FAILED",
      "classification replay artifact evidence is malformed",
    );
  }
  const bytesPrototype = OBJECT_GET_PROTOTYPE_OF(bytes);
  if (
    !(
      (Buffer.isBuffer(bytes) && bytesPrototype === Buffer.prototype) ||
      (bytes instanceof Uint8Array && bytesPrototype === Uint8Array.prototype)
    )
  ) {
    fail(
      "CLASSIFICATION_STATE_INTEGRITY_FAILED",
      "classification replay artifact bytes are not canonical",
    );
  }

  const manifestRecord = requireExactPlainDataObject(
    manifest,
    "classification replay ArtifactManifest",
    D03_MANIFEST_KEYS,
  );
  const encryption = requireExactPlainDataObject(
    readDataProperty(manifestRecord, "encryption"),
    "classification replay ArtifactManifest.encryption",
    D03_ENCRYPTION_KEYS,
  );
  const inputArtifactIds = requireDenseDataArray(
    readDataProperty(manifestRecord, "input_artifact_ids"),
    "classification replay ArtifactManifest.input_artifact_ids",
  );
  const lineageEventIds = requireDenseDataArray(
    readDataProperty(manifestRecord, "lineage_event_ids"),
    "classification replay ArtifactManifest.lineage_event_ids",
  );
  const receiptRecord = requireExactPlainDataObject(
    receipt,
    "classification replay ArtifactReceipt",
    D03_RECEIPT_KEYS,
  );
  const receiptCreator = requireExactPlainDataObject(
    readDataProperty(receiptRecord, "created_by"),
    "classification replay ArtifactReceipt.created_by",
    D03_RECEIPT_CREATOR_KEYS,
  );
  const validations = requireDenseDataArray(
    readDataProperty(receiptRecord, "validation_results"),
    "classification replay ArtifactReceipt.validation_results",
  );
  for (let index = 0; index < validations.length; index += 1) {
    requireExactPlainDataObject(
      validations[index],
      `classification replay ArtifactReceipt.validation_results[${index}]`,
      D03_VALIDATION_ROW_KEYS,
    );
  }

  const content = Buffer.from(bytes);
  const contentHash = sha256Bytes(content);
  const manifestHash = sha256ClassificationJson(manifestRecord);
  const classificationId = state.classification.classification_id;
  const expectedStorageUri = `artifact://sha256/${contentHash.slice("sha256:".length)}`;
  if (
    manifestRecord.artifact_id !== classificationId ||
    manifestRecord.artifact_type !== "epistemic_work_classification" ||
    manifestRecord.byte_size !== content.length ||
    manifestRecord.confidentiality !== "internal" ||
    manifestRecord.content_hash !== contentHash ||
    manifestRecord.created_at !== state.classification.classified_at ||
    manifestRecord.created_by !== ACTOR_ID ||
    encryption.at_rest !== true ||
    encryption.in_transit !== true ||
    encryption.key_ref !== null ||
    inputArtifactIds.length !== 0 ||
    manifestRecord.integrity_status !== "verified" ||
    manifestRecord.license !== null ||
    lineageEventIds.length !== 0 ||
    manifestRecord.media_type !== "application/json" ||
    manifestRecord.provenance_manifest_id !== `PROV-${classificationId}` ||
    manifestRecord.retention_class !== "permanent" ||
    manifestRecord.storage_uri !== expectedStorageUri
  ) {
    fail(
      "CLASSIFICATION_STATE_INTEGRITY_FAILED",
      "classification replay manifest does not bind stored F01 state",
    );
  }

  const receiptWithoutHash = {};
  for (let index = 0; index < D03_RECEIPT_KEYS.length; index += 1) {
    const key = D03_RECEIPT_KEYS[index];
    if (key !== "receipt_hash") receiptWithoutHash[key] = readDataProperty(receiptRecord, key);
  }
  const receiptHash = sha256ClassificationJson(receiptWithoutHash);
  if (
    receiptRecord.action_intent_id !== null ||
    receiptRecord.artifact_id !== classificationId ||
    receiptRecord.byte_size !== content.length ||
    receiptRecord.content_hash !== contentHash ||
    receiptRecord.created_at !== state.classification.classified_at ||
    receiptCreator.actor_id !== ACTOR_ID ||
    receiptCreator.actor_type !== "service" ||
    receiptRecord.locator !== expectedStorageUri ||
    receiptRecord.media_type !== "application/json" ||
    receiptRecord.receipt_id !== state.receipt_id ||
    receiptRecord.receipt_hash !== receiptHash ||
    receiptRecord.receipt_hash !== outbox.receipt_hash ||
    receiptRecord.schema_ref !== CLASSIFICATION_SCHEMA_ID ||
    validations.length !== 3 ||
    !validationRowMatches(validations[0], "content_sha256", contentHash) ||
    !validationRowMatches(validations[1], "artifact_manifest_sha256", manifestHash) ||
    !validationRowMatches(
      validations[2],
      "epistemic_work_classification_contract",
      state.classification.classification_hash,
    )
  ) {
    fail(
      "CLASSIFICATION_STATE_INTEGRITY_FAILED",
      "classification replay receipt does not bind stored F01 state and outbox",
    );
  }

  const text = content.toString("utf8");
  if (!Buffer.from(text, "utf8").equals(content)) {
    fail(
      "CLASSIFICATION_STATE_INTEGRITY_FAILED",
      "classification replay artifact is not valid UTF-8",
    );
  }
  let artifact;
  try {
    artifact = JSON.parse(text);
  } catch {
    fail(
      "CLASSIFICATION_STATE_INTEGRITY_FAILED",
      "classification replay artifact is not valid JSON",
    );
  }
  assertClassificationArtifactIntegrity(artifact, state.identity_context);
  assertStrictClassificationReplay(state.classification, artifact);

  return deepFreeze({
    artifact_id: classificationId,
    content_hash: contentHash,
    artifact_manifest_hash: manifestHash,
    receipt_id: receiptRecord.receipt_id,
    receipt_hash: receiptRecord.receipt_hash,
    schema_ref: receiptRecord.schema_ref,
  });
};

const validateReplayEvent = ({ state, outbox, events, contentHash }) => {
  const candidates = requireDenseDataArray(events, "classification replay E01 event stream");
  const eventIds = new Set();
  let previousEventHash = null;
  let matchedEvent = null;
  for (let index = 0; index < candidates.length; index += 1) {
    const record = requireExactPlainDataObject(
      candidates[index],
      `classification replay EventRecord[${index}]`,
      E01_EVENT_RECORD_KEYS,
      { allowNullPrototype: true },
    );
    const event = {};
    for (let keyIndex = 0; keyIndex < E01_EVENT_RECORD_KEYS.length; keyIndex += 1) {
      const key = E01_EVENT_RECORD_KEYS[keyIndex];
      event[key] = readDataProperty(record, key);
    }
    for (const key of [
      "event_id",
      "run_id",
      "event_type",
      "aggregate_type",
      "aggregate_id",
      "actor_id",
      "payload_artifact_id",
    ]) {
      if (
        typeof event[key] !== "string" ||
        event[key].length === 0 ||
        !hasOnlyUnicodeScalars(event[key])
      ) {
        fail(
          "CLASSIFICATION_STATE_INTEGRITY_FAILED",
          "classification replay EventRecord has an invalid identifier",
        );
      }
    }
    if (
      !Number.isSafeInteger(event.sequence) ||
      event.sequence !== index + 1 ||
      typeof event.payload_hash !== "string" ||
      !SHA256_PATTERN.test(event.payload_hash) ||
      !(
        event.previous_event_hash === null ||
        (typeof event.previous_event_hash === "string" &&
          SHA256_PATTERN.test(event.previous_event_hash))
      ) ||
      typeof event.event_hash !== "string" ||
      !SHA256_PATTERN.test(event.event_hash) ||
      !isRfc3339(event.occurred_at) ||
      typeof event.schema_version !== "string" ||
      !SEMVER_PATTERN.test(event.schema_version) ||
      event.previous_event_hash !== previousEventHash ||
      event.run_id !== state.run_id ||
      eventIds.has(event.event_id) ||
      event.event_hash !== computeReplayEventHash(event)
    ) {
      fail(
        "CLASSIFICATION_STATE_INTEGRITY_FAILED",
        "classification replay E01 event stream is not canonical",
      );
    }
    eventIds.add(event.event_id);
    previousEventHash = event.event_hash;
    if (event.event_id === state.event_id) {
      if (matchedEvent !== null) {
        fail(
          "CLASSIFICATION_STATE_INTEGRITY_FAILED",
          "classification replay requires exactly one stored E01 event",
        );
      }
      matchedEvent = event;
    }
  }
  if (matchedEvent === null) {
    fail(
      "CLASSIFICATION_STATE_INTEGRITY_FAILED",
      "classification replay requires exactly one stored E01 event",
    );
  }
  const event = matchedEvent;
  const aggregate = eventAggregateFor(state);
  if (
    !Number.isSafeInteger(event.sequence) ||
    event.sequence < 1 ||
    event.run_id !== state.run_id ||
    event.event_id !== state.event_id ||
    event.event_hash !== outbox.event_hash ||
    !SHA256_PATTERN.test(event.event_hash) ||
    event.payload_artifact_id !== state.classification.classification_id ||
    event.payload_hash !== contentHash ||
    !SHA256_PATTERN.test(event.payload_hash) ||
    event.event_type !== state.event_type ||
    event.aggregate_type !== aggregate.aggregate_type ||
    event.aggregate_id !== aggregate.aggregate_id ||
    event.actor_id !== ACTOR_ID ||
    event.occurred_at !== state.classification.classified_at ||
    event.schema_version !== EVENT_SCHEMA_VERSION
  ) {
    fail(
      "CLASSIFICATION_STATE_INTEGRITY_FAILED",
      "classification replay E01 event does not bind stored F01 state and artifact",
    );
  }
  return deepFreeze({
    run_id: event.run_id,
    event_id: event.event_id,
    sequence: event.sequence,
    event_hash: event.event_hash,
    payload_hash: event.payload_hash,
  });
};

const validateOutbox = (record) => {
  const value = recordValue(record, "classification outbox");
  if (value === null) return null;
  for (const key of [
    "outbox_id",
    "classification_id",
    "event_id",
    "run_id",
    "event_type",
    "published",
    "event_hash",
    "receipt_hash",
  ]) {
    if (!Object.hasOwn(value, key)) fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", `outbox misses ${key}`);
  }
  if (
    value.outbox_id !== record.recordId ||
    typeof value.published !== "boolean" ||
    value.published !== (value.event_hash !== null && value.receipt_hash !== null)
  ) {
    fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", "classification outbox is inconsistent");
  }
  return deepFreeze(cloneJson(value));
};

const buildState = ({ decision, classification, eventType, priorContext }) => {
  const digest = decision.classification_hash.slice("sha256:".length);
  return deepFreeze({
    classification,
    identity_context: identityContextFor(decision),
    accepted_signals: [...decision.accepted_signals],
    floor_work_class: decision.floor_work_class,
    interview_rules: [...decision.interview_rules],
    classifier_trace: cloneJson(decision.classifier_trace),
    run_id: decision.run_id,
    receipt_id: `AR-F01-${digest}`,
    event_id: `EVT-F01-${digest}`,
    outbox_id: `OUTBOX-F01-${digest}`,
    event_type: eventType,
    prior_context: priorContext,
  });
};

const commitNewState = ({ store, decision, classifiedAt, eventType, idempotencyKey, priorContext, binding }) => {
  const classification = materializeClassificationArtifact(decision, classifiedAt);
  const state = buildState({ decision, classification, eventType, priorContext });
  assertClassificationArtifactIntegrity(classification, state.identity_context);
  store.createRevisionedRecord({
    recordType: CLASSIFICATION_RECORD_TYPES.CLASSIFICATION,
    recordId: classification.classification_id,
    value: state,
  });
  if (binding.type === "idempotency") {
    store.createRevisionedRecord({
      recordType: CLASSIFICATION_RECORD_TYPES.IDEMPOTENCY,
      recordId: idempotencyKey,
      value: {
        idempotency_key: idempotencyKey,
        classification_id: classification.classification_id,
        classification_hash: classification.classification_hash,
        prior_context: priorContext,
      },
    });
  } else {
    store.createRevisionedRecord({
      recordType: CLASSIFICATION_RECORD_TYPES.HUMAN_DECISION_BINDING,
      recordId: binding.humanDecisionHash,
      value: {
        human_decision_hash: binding.humanDecisionHash,
        request_hash: binding.requestHash,
        classification_id: classification.classification_id,
        classification_hash: classification.classification_hash,
      },
    });
  }
  const activeRecord = store.readRevisionedRecord(
    CLASSIFICATION_RECORD_TYPES.ACTIVE,
    classification.request_id,
  );
  const nextActive = {
    request_id: classification.request_id,
    request_input_hash: decision.request_input_hash,
    classification_id: classification.classification_id,
    classification_hash: classification.classification_hash,
    classified_at: classification.classified_at,
  };
  if (activeRecord === null) {
    store.createRevisionedRecord({
      recordType: CLASSIFICATION_RECORD_TYPES.ACTIVE,
      recordId: classification.request_id,
      value: nextActive,
    });
  } else {
    const active = activeState(activeRecord);
    if (active.request_input_hash !== decision.request_input_hash) {
      fail(
        "REQUEST_REVISION_ID_REUSED",
        "request_id cannot bind a different immutable request_input_hash",
      );
    }
    if (decision.supersedes_classification_hash !== active.classification_hash) {
      fail("STALE_CLASSIFICATION_REVISION", "classification does not supersede the active revision");
    }
    updateRecord(store, activeRecord, nextActive, "active classification pointer");
  }
  store.createRevisionedRecord({
    recordType: CLASSIFICATION_RECORD_TYPES.OUTBOX,
    recordId: state.outbox_id,
    value: {
      outbox_id: state.outbox_id,
      classification_id: classification.classification_id,
      event_id: state.event_id,
      run_id: state.run_id,
      event_type: state.event_type,
      published: false,
      event_hash: null,
      receipt_hash: null,
    },
  });
  appendOutboxIndex(store, state.outbox_id);
  return state;
};

const existingBindingState = (store, recordType, recordId, expected = undefined) => {
  const record = store.readRevisionedRecord(recordType, recordId);
  if (record === null) return null;
  if (record.revision !== 0) fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", "immutable binding was revised");
  const value = recordValue(record, "classification binding");
  if (expected !== undefined && expected(value) !== true) {
    fail("IDEMPOTENCY_CONFLICT", "immutable classification binding was reused for different input");
  }
  return loadClassification(store, value.classification_id);
};

const resolveHumanDecision = (artifactStore, candidate) => {
  if (!Object.hasOwn(candidate, "human_decision_id")) {
    fail(
      "HUMAN_DECISION_ARTIFACT_REQUIRED",
      "override command requires human_decision_id for an immutable HumanDecision artifact",
    );
  }
  const humanDecisionId = requireString(candidate.human_decision_id, "human_decision_id");
  let manifest;
  let bytes;
  try {
    manifest = artifactStore.readManifest(humanDecisionId);
    bytes = artifactStore.readArtifact(humanDecisionId);
  } catch (error) {
    fail(
      "HUMAN_DECISION_ARTIFACT_INVALID",
      "HumanDecision artifact could not be resolved",
      { humanDecisionId, causeCode: dependencyCauseCode(error) },
      { cause: error },
    );
  }
  if (
    manifest === null ||
    typeof manifest !== "object" ||
    Array.isArray(manifest) ||
    manifest.artifact_id !== humanDecisionId ||
    manifest.artifact_type !== "human_decision" ||
    manifest.media_type !== "application/json" ||
    manifest.integrity_status !== "verified"
  ) {
    fail(
      "HUMAN_DECISION_ARTIFACT_INVALID",
      "resolved HumanDecision manifest is not a canonical verified JSON authority artifact",
      { humanDecisionId },
    );
  }
  if (!Buffer.isBuffer(bytes) && !(bytes instanceof Uint8Array)) {
    fail("HUMAN_DECISION_ARTIFACT_INVALID", "HumanDecision artifact bytes are invalid");
  }
  const content = Buffer.from(bytes);
  const text = content.toString("utf8");
  if (!Buffer.from(text, "utf8").equals(content)) {
    fail("HUMAN_DECISION_ARTIFACT_INVALID", "HumanDecision artifact is not valid UTF-8");
  }
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    fail(
      "HUMAN_DECISION_ARTIFACT_INVALID",
      "HumanDecision artifact is not valid JSON",
      { humanDecisionId, causeCode: dependencyCauseCode(error) },
      { cause: error },
    );
  }
  const decision = validateHumanDecisionArtifact(parsed);
  if (decision.decision_id !== humanDecisionId) {
    fail(
      "HUMAN_DECISION_INTEGRITY_FAILED",
      "human_decision_id does not match the resolved HumanDecision decision_id",
      { expected: decision.decision_id, actual: humanDecisionId },
    );
  }
  if (Object.hasOwn(candidate, "human_decision_hash")) {
    const assertedHash = requireString(candidate.human_decision_hash, "human_decision_hash");
    if (!SHA256_PATTERN.test(assertedHash)) {
      fail(
        "HUMAN_DECISION_INTEGRITY_FAILED",
        "human_decision_hash must be a canonical SHA-256 assertion",
      );
    }
    if (assertedHash !== decision.decision_hash) {
      fail(
        "HUMAN_DECISION_INTEGRITY_FAILED",
        "human_decision_hash does not match the resolved HumanDecision artifact",
        { expected: decision.decision_hash, actual: assertedHash },
      );
    }
  }
  let receipts;
  try {
    receipts = artifactStore
      .enumerateReceipts()
      .filter((receipt) => receipt.artifact_id === humanDecisionId);
  } catch (error) {
    fail(
      "HUMAN_DECISION_ARTIFACT_INVALID",
      "HumanDecision ArtifactReceipt could not be resolved",
      { humanDecisionId, causeCode: dependencyCauseCode(error) },
      { cause: error },
    );
  }
  if (receipts.length !== 1) {
    fail(
      "HUMAN_DECISION_ARTIFACT_INVALID",
      "HumanDecision artifact requires exactly one immutable ArtifactReceipt",
      { humanDecisionId, receiptCount: receipts.length },
    );
  }
  const receipt = receipts[0];
  if (
    receipt.content_hash !== manifest.content_hash ||
    receipt.byte_size !== manifest.byte_size ||
    receipt.media_type !== manifest.media_type ||
    receipt.schema_ref !== "schemas/human-decision.schema.json" ||
    receipt.created_at !== decision.created_at ||
    receipt.created_by?.actor_type !== "human" ||
    receipt.created_by?.actor_id !== decision.authority_id ||
    manifest.created_at !== decision.created_at ||
    manifest.created_by !== decision.authority_id
  ) {
    fail(
      "HUMAN_DECISION_AUTHORITY_MISMATCH",
      "HumanDecision manifest and ArtifactReceipt do not prove the declared human authority",
      { humanDecisionId },
    );
  }
  return decision;
};

class ClassificationCommitter {
  #artifactStore;
  #ledger;
  #stateStore;
  #clock;

  constructor(options) {
    const dependencies = normalizeDependencies(options);
    this.#artifactStore = dependencies.artifactStore;
    this.#ledger = dependencies.ledger;
    this.#stateStore = dependencies.stateStore;
    this.#clock = dependencies.clock;
    bindClassificationWorkerAuthority(this, {
      artifactStore: dependencies.artifactStore,
      ledger: dependencies.ledger,
      stateStore: dependencies.stateStore,
      clock: dependencies.clock,
      prepareClassification: (store, candidate, prepareOptions = {}) =>
        this.#prepareClassification(store, candidate, prepareOptions),
    });
  }

  #prepareClassification(store, candidate, options = {}) {
    validateClassifierCapabilities(options.capabilities ?? ["artifact_read", "artifact_write"]);
    const initial = evaluateEpistemicWork(candidate);
    const idempotencyKey = classificationIdempotencyKey(initial);
    const bindingRecord = store.readRevisionedRecord(
      CLASSIFICATION_RECORD_TYPES.IDEMPOTENCY,
      idempotencyKey,
    );
    let state;
    let status;
    if (bindingRecord !== null) {
      if (bindingRecord.revision !== 0) {
        fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", "idempotency binding was revised");
      }
      const binding = recordValue(bindingRecord, "classification idempotency binding");
      const replay = evaluateEpistemicWork(candidate, {
        prior_classification: binding.prior_context,
      });
      const expected = binding.prior_context === null
        ? replay
        : (() => {
            const priorHash = binding.classification_hash === replay.classification_hash
              ? null
              : loadClassification(store, binding.classification_id)
                  .identity_context.supersedes_classification_hash;
            return priorHash === null ? replay : sealClassificationSupersession(replay, priorHash);
          })();
      if (expected.classification_hash !== binding.classification_hash) {
        fail("IDEMPOTENCY_CONFLICT", "idempotency key is bound to a different classification preimage");
      }
      state = loadClassification(store, binding.classification_id);
      status = "EXISTING";
    } else {
      const activeRecord = store.readRevisionedRecord(
        CLASSIFICATION_RECORD_TYPES.ACTIVE,
        initial.request_id,
      );
      const active = activeRecord === null ? null : activeState(activeRecord);
      let priorState = null;
      if (active !== null) {
        if (active.request_input_hash !== initial.request_input_hash) {
          fail("REQUEST_REVISION_ID_REUSED", "request_id was reused for changed request content");
        }
        priorState = loadClassification(store, active.classification_id);
      }
      const priorContext = priorContextFor(priorState);
      let decision = evaluateEpistemicWork(candidate, { prior_classification: priorContext });
      if (priorState !== null) {
        decision = sealClassificationSupersession(
          decision,
          priorState.classification.classification_hash,
        );
      }
      state = commitNewState({
        store,
        decision,
        classifiedAt: timestampFromClock(this.#clock),
        eventType:
          priorState === null
            ? CLASSIFICATION_EVENT_TYPES.CLASSIFIED
            : CLASSIFICATION_EVENT_TYPES.RECLASSIFIED,
        idempotencyKey,
        priorContext,
        binding: { type: "idempotency" },
      });
      status = "CREATED";
    }
    const preparation = deepFreeze(cloneJson({
      status,
      classification_id: state.classification.classification_id,
      classification_hash: state.classification.classification_hash,
      request_id: state.classification.request_id,
      run_id: state.run_id,
      outbox_id: state.outbox_id,
    }));
    CLASSIFICATION_PREPARATION_STATES.set(preparation, state);
    return preparation;
  }

  classify(candidate, options = {}) {
    const preparation = this.#stateStore.transaction((store) =>
      this.#prepareClassification(store, candidate, options));
    this.#publish(preparation.outbox_id);
    const state = CLASSIFICATION_PREPARATION_STATES.get(preparation);
    if (state === undefined) {
      fail(
        "CLASSIFICATION_STATE_INTEGRITY_FAILED",
        "classification preparation lost its private state binding",
      );
    }
    return resultFromState(state, this.#artifactStore, preparation.status);
  }

  override(candidate, options = {}) {
    validateClassifierCapabilities(options.capabilities ?? ["artifact_read", "artifact_write"]);
    if (candidate === null || typeof candidate !== "object" || Array.isArray(candidate)) {
      fail("INVALID_INPUT", "override command must be an object");
    }
    const requestId = requireString(candidate.request_id, "request_id");
    const baseClassificationId = requireString(
      candidate.base_classification_id,
      "base_classification_id",
    );
    const humanDecision = resolveHumanDecision(this.#artifactStore, candidate);
    const humanDecisionHash = humanDecision.decision_hash;
    const requestHash = sha256ClassificationJson({
      request_id: requestId,
      base_classification_id: baseClassificationId,
      target_work_class: candidate.target_work_class,
      add_interview: candidate.add_interview,
      interview_rule: candidate.interview_rule,
      human_decision_id: humanDecision.decision_id,
      human_decision_hash: humanDecisionHash,
    });
    const transactionResult = this.#stateStore.transaction((store) => {
      const baseState = loadClassification(store, baseClassificationId);
      const baseDecision = decisionFromState(baseState);
      validateHumanDecisionArtifact(humanDecision, baseDecision);
      const existing = existingBindingState(
        store,
        CLASSIFICATION_RECORD_TYPES.HUMAN_DECISION_BINDING,
        humanDecisionHash,
        (binding) => binding.request_hash === requestHash,
      );
      if (existing !== null) return { state: existing, status: "EXISTING" };

      const activeRecord = store.readRevisionedRecord(
        CLASSIFICATION_RECORD_TYPES.ACTIVE,
        requestId,
      );
      const active = activeRecord === null ? null : activeState(activeRecord);
      if (active === null || active.classification_id !== baseClassificationId) {
        fail("STALE_CLASSIFICATION_REVISION", "override base is not the active classification");
      }
      const decision = applyHumanClassificationOverride(baseDecision, {
        target_work_class: candidate.target_work_class,
        add_interview: candidate.add_interview,
        interview_rule: candidate.interview_rule,
        human_decision: humanDecision,
        human_decision_hash: humanDecisionHash,
      });
      const state = commitNewState({
        store,
        decision,
        classifiedAt: timestampFromClock(this.#clock),
        eventType: CLASSIFICATION_EVENT_TYPES.OVERRIDDEN,
        idempotencyKey: null,
        priorContext: priorContextFor(baseState),
        binding: { type: "human", humanDecisionHash, requestHash },
      });
      return { state, status: "CREATED" };
    });
    this.#publish(transactionResult.state.outbox_id);
    return resultFromState(transactionResult.state, this.#artifactStore, transactionResult.status);
  }

  readClassification(classificationId) {
    const id = requireString(classificationId, "classificationId");
    return this.#stateStore.transaction((store) => {
      const state = loadClassification(store, id);
      const bytes = this.#artifactStore.readArtifact(id);
      const artifact = JSON.parse(bytes.toString("utf8"));
      assertStrictClassificationReplay(state.classification, artifact);
      return resultFromState(state, this.#artifactStore, "EXISTING");
    });
  }

  readClassificationReplayProjection(classificationId) {
    const id = requireString(classificationId, "classificationId");
    try {
      requireDependencyMethod(this.#ledger, "readEvents", "ledger");
    } catch (error) {
      if (error instanceof ClassificationCommitterError) throw error;
      fail("INVALID_DEPENDENCY", "ledger.readEvents is required");
    }
    const snapshot = withReplaySnapshotBoundary(() =>
      this.#stateStore.transaction((store) => {
        const state = loadClassification(store, id);
        const outboxRecord = store.readRevisionedRecord(
          CLASSIFICATION_RECORD_TYPES.OUTBOX,
          state.outbox_id,
        );
        if (outboxRecord === null) {
          fail("CLASSIFICATION_STATE_MISSING", "classification outbox is missing");
        }
        const outbox = validateOutbox(outboxRecord);
        assertReplaySnapshot(state, outbox, outboxRecord.revision);
        return deepFreeze({
          state: deepFreeze(cloneJson(state)),
          outbox: deepFreeze(cloneJson(outbox)),
        });
      }),
    );

    const evidence = readReplayEvidence({
      artifactStore: this.#artifactStore,
      ledger: this.#ledger,
      state: snapshot.state,
    });
    const artifactBinding = withReplayIntegrityBoundary(
      () =>
        validateReplayArtifact({
          state: snapshot.state,
          outbox: snapshot.outbox,
          manifest: evidence.manifest,
          bytes: evidence.bytes,
          receipt: evidence.receipt,
        }),
      "classification replay D03 evidence is malformed",
    );
    const ledgerBinding = withReplayIntegrityBoundary(
      () =>
        validateReplayEvent({
          state: snapshot.state,
          outbox: snapshot.outbox,
          events: evidence.events,
          contentHash: artifactBinding.content_hash,
        }),
      "classification replay E01 evidence is malformed",
    );
    const semantic = {
      projection_version: "DURABLE_FORGE_V1",
      classification: snapshot.state.classification,
      identity_context: snapshot.state.identity_context,
      artifact_binding: artifactBinding,
      ledger_binding: ledgerBinding,
    };
    const projectionHash = sha256ClassificationJson(semantic);
    return deepFreeze(cloneJson({
      ...semantic,
      projection_hash: projectionHash,
      projection_id: `F01RP-${projectionHash.slice("sha256:".length)}`,
    }));
  }

  readActiveClassification(requestId) {
    const id = requireString(requestId, "requestId");
    const classificationId = this.#stateStore.transaction((store) => {
      const record = store.readRevisionedRecord(CLASSIFICATION_RECORD_TYPES.ACTIVE, id);
      const active = record === null ? null : activeState(record);
      return active?.classification_id ?? null;
    });
    return classificationId === null ? null : this.readClassification(classificationId);
  }

  strictReplay(classificationId, candidate) {
    const recorded = this.readClassification(classificationId);
    const state = this.#stateStore.transaction((store) => loadClassification(store, classificationId));
    let replay = evaluateEpistemicWork(candidate, {
      prior_classification: state.prior_context,
    });
    if (state.identity_context.human_decision_hash !== null) {
      fail("REPLAY_DIVERGENCE", "human override replay requires its immutable HumanDecision workflow");
    }
    if (state.identity_context.supersedes_classification_hash !== null) {
      replay = sealClassificationSupersession(
        replay,
        state.identity_context.supersedes_classification_hash,
      );
    }
    const replayArtifact = materializeClassificationArtifact(
      replay,
      recorded.classification.classified_at,
    );
    assertStrictClassificationReplay(recorded.classification, replayArtifact);
    return recorded;
  }

  reconcileEvents() {
    const ids = this.#stateStore.transaction((store) => {
      const record = store.readRevisionedRecord(
        CLASSIFICATION_RECORD_TYPES.OUTBOX_INDEX,
        OUTBOX_INDEX_ID,
      );
      if (record === null) return [];
      const value = recordValue(record, "classification outbox index");
      if (!Array.isArray(value.outbox_ids)) {
        fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", "classification outbox index is invalid");
      }
      return [...value.outbox_ids];
    });
    let published = 0;
    let existing = 0;
    for (const id of ids) {
      const wasPublished = this.#stateStore.transaction((store) => {
        const record = store.readRevisionedRecord(CLASSIFICATION_RECORD_TYPES.OUTBOX, id);
        if (record === null) fail("CLASSIFICATION_STATE_MISSING", "classification outbox is missing");
        return validateOutbox(record).published;
      });
      this.#publish(id);
      if (wasPublished) existing += 1;
      else published += 1;
    }
    return deepFreeze({ total: ids.length, published, existing });
  }

  #publish(outboxId) {
    const snapshot = this.#stateStore.transaction((store) => {
      const outboxRecord = store.readRevisionedRecord(
        CLASSIFICATION_RECORD_TYPES.OUTBOX,
        outboxId,
      );
      if (outboxRecord === null) fail("CLASSIFICATION_STATE_MISSING", "classification outbox is missing");
      const outbox = validateOutbox(outboxRecord);
      const state = loadClassification(store, outbox.classification_id);
      return { outbox, state };
    });
    if (snapshot.outbox.published) return snapshot.outbox;
    try {
      const bytes = Buffer.from(`${canonicalizeClassificationJson(snapshot.state.classification)}\n`, "utf8");
      const registration = this.#artifactStore.putArtifact(bytes, artifactMetadata(snapshot.state));
      const aggregate = eventAggregateFor(snapshot.state);
      const append = this.#ledger.append({
        event_id: snapshot.state.event_id,
        run_id: snapshot.state.run_id,
        event_type: snapshot.state.event_type,
        aggregate_type: aggregate.aggregate_type,
        aggregate_id: aggregate.aggregate_id,
        actor_id: ACTOR_ID,
        payload_artifact_id: snapshot.state.classification.classification_id,
        occurred_at: snapshot.state.classification.classified_at,
        schema_version: EVENT_SCHEMA_VERSION,
      });
      return this.#stateStore.transaction((store) => {
        const record = store.readRevisionedRecord(CLASSIFICATION_RECORD_TYPES.OUTBOX, outboxId);
        if (record === null) fail("CLASSIFICATION_STATE_MISSING", "classification outbox vanished");
        const current = validateOutbox(record);
        if (current.published) {
          if (
            current.event_hash !== append.event.event_hash ||
            current.receipt_hash !== registration.receipt.receipt_hash
          ) {
            fail("CLASSIFICATION_STATE_INTEGRITY_FAILED", "published outbox identity changed");
          }
          return current;
        }
        const next = {
          ...current,
          published: true,
          event_hash: append.event.event_hash,
          receipt_hash: registration.receipt.receipt_hash,
        };
        return validateOutbox(updateRecord(store, record, next, "classification outbox"));
      });
    } catch (error) {
      if (error instanceof ClassificationCommitterError) throw error;
      fail(
        "CLASSIFICATION_RECONCILIATION_REQUIRED",
        "classification committed but ArtifactReceipt or ledger publication needs reconciliation",
        { outboxId, causeCode: dependencyCauseCode(error) },
        { cause: error },
      );
    }
  }
}

export const createClassificationCommitter = (options) => new ClassificationCommitter(options);

export const classify_epistemic_work = (candidate, context = undefined) =>
  evaluateEpistemicWork(candidate, context);

export { EpistemicWorkClassifierError };
