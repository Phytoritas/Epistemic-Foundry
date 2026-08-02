import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

import {
  CLASSIFIER_VERSION,
  CLASS_PROJECTIONS,
  sha256ClassificationJson as sha256CanonicalJson,
  validateHumanDecisionArtifact,
} from "../classifier/epistemic-work-classifier.mjs";

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

const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|([+-])(\d{2}):(\d{2}))$/u;
const PHASES = new Set(["IDLE", "I", "F", "O", "R", "G", "E"]);
const WORK_CLASSES = new Set(["E0", "E1", "E2", "E3", "E4", "E5"]);
const SESSION_STATUSES = new Set([
  "ACTIVE",
  "PAUSED",
  "BLOCKED",
  "COMPLETED",
  "ABORTED",
  "STALE",
]);
const ACTOR_TYPES = new Set(["human", "agent", "service"]);
const RECEIPT_ACTOR_TYPES = new Set(["human", "agent", "service", "tool"]);
const ARTIFACT_STATUSES = new Set(["VALID", "INVALID", "MISSING", "STALE"]);
const GATE_STATUSES = new Set(["PASS", "FAIL", "BLOCK", "WAIVE"]);
const RETENTION_CLASSES = new Set(["ephemeral", "project", "regulated", "permanent"]);
const CONFIDENTIALITY_CLASSES = new Set(["public", "internal", "restricted", "secret"]);
const EVALUATOR_TYPES = new Set([
  "deterministic",
  "human",
  "model_assisted",
  "formal_verifier",
]);

const STATE_KEYS = OBJECT_FREEZE([
  "session_id",
  "workspace_id",
  "revision",
  "phase",
  "work_class",
  "status",
  "run_spec_id",
  "hypothesis_revision_ids",
  "artifact_ids",
  "open_blockers",
  "phase_history",
  "policy_hash",
  "corpus_snapshot_hash",
  "updated_at",
  "state_hash",
]);
const STATE_HASH_KEYS = OBJECT_FREEZE(STATE_KEYS.filter((key) => key !== "state_hash"));
const REQUEST_KEYS = OBJECT_FREEZE([
  "request_id",
  "session_id",
  "expected_revision",
  "from_phase",
  "to_phase",
  "actor",
  "artifact_receipt_ids",
  "gate_result_ids",
  "human_decision_id",
  "reason",
  "idempotency_key",
  "requested_at",
]);
const ACTOR_KEYS = OBJECT_FREEZE(["actor_id", "actor_type", "role"]);
const MANIFEST_KEYS = OBJECT_FREEZE([
  "artifact_id",
  "artifact_type",
  "content_hash",
  "media_type",
  "byte_size",
  "storage_uri",
  "created_at",
  "created_by",
  "input_artifact_ids",
  "lineage_event_ids",
  "license",
  "retention_class",
  "confidentiality",
  "encryption",
  "integrity_status",
  "provenance_manifest_id",
]);
const MANIFEST_ENCRYPTION_KEYS = OBJECT_FREEZE(["at_rest", "in_transit", "key_ref"]);
const RECEIPT_KEYS = OBJECT_FREEZE([
  "receipt_id",
  "artifact_id",
  "action_intent_id",
  "media_type",
  "content_hash",
  "byte_size",
  "created_by",
  "created_at",
  "locator",
  "schema_ref",
  "validation_results",
  "receipt_hash",
]);
const RECEIPT_CREATOR_KEYS = OBJECT_FREEZE(["actor_id", "actor_type"]);
const PHASE_SET_KEYS = OBJECT_FREEZE([
  "set_id",
  "session_id",
  "phase",
  "required_artifacts",
  "optional_artifacts",
  "complete",
  "missing_kinds",
  "validated_at",
  "set_hash",
]);
const PHASE_SET_HASH_KEYS = OBJECT_FREEZE(
  PHASE_SET_KEYS.filter((key) => key !== "set_hash"),
);
const PHASE_ARTIFACT_KEYS = OBJECT_FREEZE([
  "artifact_id",
  "kind",
  "schema_ref",
  "content_hash",
  "receipt_id",
  "status",
]);
const GATE_DECISION_KEYS = OBJECT_FREEZE([
  "gate_id",
  "gate_version",
  "run_id",
  "name",
  "status",
  "reasons",
  "evidence_ids",
  "input_artifact_ids",
  "policy_bundle_hash",
  "decision",
  "blocker_ids",
  "waiver_authority",
  "waiver_reason",
  "evaluated_at",
  "created_at",
  "policy_version",
  "non_waivable",
  "evaluator_type",
  "input_hash",
  "decision_hash",
]);
const GATE_DECISION_HASH_KEYS = OBJECT_FREEZE(
  GATE_DECISION_KEYS.filter((key) => key !== "decision_hash"),
);
const RECEIPT_VALIDATION_KEYS = OBJECT_FREEZE(["check", "status", "details"]);
const CLASSIFICATION_KEYS = OBJECT_FREEZE([
  "classification_id",
  "request_id",
  "work_class",
  "reasons",
  "risk_factors",
  "required_phases",
  "default_role_count",
  "human_gate_required",
  "classified_at",
  "classifier_version",
  "classification_hash",
]);
const CLASSIFICATION_RISK_FACTORS = new Set([
  "AMBIGUOUS",
  "NOVELTY",
  "HIGH_STAKES",
  "EXPENSIVE",
  "CAUSAL",
  "VALIDATION",
  "MECHANISM",
]);
const CLASSIFICATION_REASON_PATTERN =
  /^(?:SIGNAL:(?:AMBIGUOUS|NOVELTY|HIGH_STAKES|EXPENSIVE|CAUSAL|VALIDATION|MECHANISM|SYNTHESIS|LOOKUP|TRANSFORM)|FLOOR:E[0-5]|INTERVIEW:I0[1-9]_[A-Z_]+|PROPOSAL_(?:REJECTED|AMBIGUOUS|IGNORED):[0-9]+:[A-Z_]+|OVERRIDE:sha256:[0-9a-f]{64})$/u;
const CLASSIFIED_AT_PATTERN =
  /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$/u;

const SCHEMA_REFS = OBJECT_FREEZE({
  CLASSIFICATION: OBJECT_FREEZE(
    new Set([
      "schemas/epistemic-work-classification.schema.json",
      "https://epistemic-foundry.local/schemas/epistemic-work-classification.schema.json",
    ]),
  ),
  PHASE_ARTIFACT_SET: OBJECT_FREEZE(
    new Set([
      "schemas/phase-artifact-set.schema.json",
      "https://epistemic-foundry.local/schemas/phase-artifact-set.schema.json",
    ]),
  ),
  GATE_DECISION: OBJECT_FREEZE(
    new Set([
      "schemas/gate-decision.schema.json",
      "https://epistemic-foundry.local/schemas/gate-decision.schema.json",
    ]),
  ),
  HUMAN_DECISION: OBJECT_FREEZE(
    new Set([
      "schemas/human-decision.schema.json",
      "https://epistemic-foundry.local/schemas/human-decision.schema.json",
    ]),
  ),
});

export const TRANSITION_ADMISSION_VERSION = "4.0.0-f03.2";

export class TransitionAdmissionError extends Error {
  constructor(code, message, details = undefined, options = undefined) {
    super(message, options);
    this.name = "TransitionAdmissionError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(canonicalClone(details));
  }
}

const fail = (code, message, details, options) => {
  throw new TransitionAdmissionError(code, message, details, options);
};

const readDataProperty = (value, key, label = "object", code = "INVALID_INPUT") => {
  const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
  if (descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")) {
    fail(code, `${label}.${key} must be an own data property`);
  }
  return descriptor.value;
};

const requirePlainRecord = (
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

const requireDenseArray = (value, label, code = "INVALID_INPUT") => {
  if (!ARRAY_IS_ARRAY(value) || IS_PROXY(value)) fail(code, `${label} must be an array`);
  const keys = REFLECT_OWN_KEYS(value);
  for (let index = 0; index < value.length; index += 1) {
    if (!OBJECT_HAS_OWN(value, index)) fail(code, `${label} cannot be sparse`);
    readDataProperty(value, String(index), label, code);
  }
  for (const key of keys) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(?:0|[1-9][0-9]*)$/u.test(key)) {
      fail(code, `${label} cannot contain non-index properties`);
    }
    if (Number(key) >= value.length) fail(code, `${label} contains an out-of-range index`);
  }
  return value;
};

const requireString = (
  value,
  label,
  { min = 1, max = undefined, code = "INVALID_INPUT" } = {},
) => {
  if (
    typeof value !== "string" ||
    value.length < min ||
    (max !== undefined && value.length > max)
  ) {
    fail(code, `${label} must be a string with a valid length`);
  }
  return value;
};

const requireHash = (value, label, code = "INVALID_INPUT") => {
  const candidate = requireString(value, label, { code });
  if (!SHA256_PATTERN.test(candidate)) fail(code, `${label} must be a canonical SHA-256`);
  return candidate;
};

const requireTimestamp = (value, label, code = "INVALID_INPUT") => {
  const candidate = requireString(value, label, { code });
  const match = RFC3339_PATTERN.exec(candidate);
  if (match === null || !NUMBER_IS_FINITE(Date.parse(candidate))) {
    fail(code, `${label} must be an RFC 3339 timestamp`);
  }
  const calendar = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  if (
    calendar.getUTCFullYear() !== Number(match[1]) ||
    calendar.getUTCMonth() !== Number(match[2]) - 1 ||
    calendar.getUTCDate() !== Number(match[3]) ||
    Number(match[4]) > 23 ||
    Number(match[5]) > 59 ||
    Number(match[6]) > 59 ||
    (match[8] !== undefined && Number(match[8]) > 23) ||
    (match[9] !== undefined && Number(match[9]) > 59)
  ) {
    fail(code, `${label} must be a real RFC 3339 timestamp`);
  }
  return candidate;
};

const requireSafeRevision = (value, label, code = "INVALID_INPUT") => {
  if (!NUMBER_IS_SAFE_INTEGER(value) || value < 0) {
    fail(code, `${label} must be a non-negative safe integer`);
  }
  return value;
};

const requireStringArray = (
  value,
  label,
  { min = 0, unique = false, itemMin = 1, itemMax = undefined, code = "INVALID_INPUT" } = {},
) => {
  const values = requireDenseArray(value, label, code);
  if (values.length < min) fail(code, `${label} must contain at least ${min} item(s)`);
  const seen = new Set();
  for (let index = 0; index < values.length; index += 1) {
    const item = requireString(values[index], `${label}[${index}]`, {
      min: itemMin,
      max: itemMax,
      code,
    });
    if (unique && seen.has(item)) fail(code, `${label} cannot contain duplicates`);
    seen.add(item);
  }
  return values;
};

const canonicalClone = (value) => JSON.parse(JSON.stringify(value));

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object" || IS_PROXY(value)) return value;
  for (const key of REFLECT_OWN_KEYS(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};

const selectKeys = (value, keys) =>
  Object.fromEntries(keys.map((key) => [key, canonicalClone(readDataProperty(value, key))]));

const compareCanonicalText = (left, right) => (left < right ? -1 : left > right ? 1 : 0);

const sameStringArray = (left, right) =>
  left.length === right.length && left.every((value, index) => value === right[index]);

const validateState = (candidate) => {
  const code = "INVALID_FORGE_SESSION_STATE";
  const state = requirePlainRecord(candidate, "ForgeSessionState", {
    allowedKeys: STATE_KEYS,
    requiredKeys: STATE_KEYS,
    code,
  });
  requireString(state.session_id, "session_id", { min: 3, max: 128, code });
  requireString(state.workspace_id, "workspace_id", { min: 3, max: 128, code });
  requireSafeRevision(state.revision, "revision", code);
  if (!PHASES.has(state.phase)) fail(code, "phase is not canonical");
  if (!WORK_CLASSES.has(state.work_class)) fail(code, "work_class is not canonical");
  if (!SESSION_STATUSES.has(state.status)) fail(code, "status is not canonical");
  requireString(state.run_spec_id, "run_spec_id", { min: 3, max: 128, code });
  requireStringArray(state.hypothesis_revision_ids, "hypothesis_revision_ids", {
    unique: true,
    itemMin: 3,
    itemMax: 128,
    code,
  });
  requireStringArray(state.artifact_ids, "artifact_ids", {
    unique: true,
    itemMin: 3,
    itemMax: 128,
    code,
  });
  requireStringArray(state.open_blockers, "open_blockers", { code });
  requireDenseArray(state.phase_history, "phase_history", code);
  requireHash(state.policy_hash, "policy_hash", code);
  requireHash(state.corpus_snapshot_hash, "corpus_snapshot_hash", code);
  requireTimestamp(state.updated_at, "updated_at", code);
  requireHash(state.state_hash, "state_hash", code);
  const expectedHash = sha256CanonicalJson(selectKeys(state, STATE_HASH_KEYS));
  if (state.state_hash !== expectedHash) {
    fail("FORGE_STATE_HASH_MISMATCH", "ForgeSessionState hash does not match its content", {
      expected: expectedHash,
      actual: state.state_hash,
    });
  }
  return state;
};

const validateRequest = (candidate) => {
  const code = "INVALID_TRANSITION_REQUEST";
  const request = requirePlainRecord(candidate, "ForgeTransitionRequest", {
    allowedKeys: REQUEST_KEYS,
    requiredKeys: REQUEST_KEYS,
    code,
  });
  requireString(request.request_id, "request_id", { min: 3, max: 128, code });
  requireString(request.session_id, "session_id", { min: 3, max: 128, code });
  requireSafeRevision(request.expected_revision, "expected_revision", code);
  if (!PHASES.has(request.from_phase) || !PHASES.has(request.to_phase)) {
    fail(code, "transition phases are not canonical");
  }
  const actor = requirePlainRecord(request.actor, "actor", {
    allowedKeys: ACTOR_KEYS,
    requiredKeys: ACTOR_KEYS,
    code,
  });
  requireString(actor.actor_id, "actor.actor_id", { min: 3, max: 128, code });
  if (!ACTOR_TYPES.has(actor.actor_type)) fail(code, "actor.actor_type is not canonical");
  requireString(actor.role, "actor.role", { code });
  requireStringArray(request.artifact_receipt_ids, "artifact_receipt_ids", {
    unique: true,
    itemMin: 3,
    itemMax: 128,
    code,
  });
  requireStringArray(request.gate_result_ids, "gate_result_ids", {
    unique: true,
    itemMin: 3,
    itemMax: 128,
    code,
  });
  if (request.human_decision_id !== null) {
    requireString(request.human_decision_id, "human_decision_id", { code });
  }
  requireString(request.reason, "reason", { code });
  requireString(request.idempotency_key, "idempotency_key", { min: 8, code });
  requireTimestamp(request.requested_at, "requested_at", code);
  return request;
};

const validateStateRequestBinding = (state, request) => {
  if (request.session_id !== state.session_id) {
    fail("SESSION_MISMATCH", "transition request belongs to another session");
  }
  if (request.expected_revision !== state.revision) {
    fail("STALE_REVISION", "transition request expected_revision is not current", {
      expectedRevision: request.expected_revision,
      currentRevision: state.revision,
    });
  }
  if (request.from_phase !== state.phase) {
    fail("FROM_PHASE_MISMATCH", "transition request from_phase is not current", {
      requestedFrom: request.from_phase,
      currentPhase: state.phase,
    });
  }
};

const validateResolvedReceipt = (resolved, requestedReceiptId) => {
  const code = "ARTIFACT_RECEIPT_INVALID";
  const resolvedRecord = requirePlainRecord(resolved, "resolved ArtifactReceipt", {
    requiredKeys: ["manifest", "receipt", "bytes"],
    code,
  });
  const manifest = requirePlainRecord(
    readDataProperty(resolvedRecord, "manifest", "resolved ArtifactReceipt", code),
    "ArtifactManifest",
    { allowedKeys: MANIFEST_KEYS, requiredKeys: MANIFEST_KEYS, code: "ARTIFACT_MANIFEST_INVALID" },
  );
  const receipt = requirePlainRecord(
    readDataProperty(resolvedRecord, "receipt", "resolved ArtifactReceipt", code),
    "ArtifactReceipt",
    { allowedKeys: RECEIPT_KEYS, requiredKeys: RECEIPT_KEYS, code },
  );
  requireString(manifest.artifact_id, "manifest.artifact_id", {
    min: 3,
    max: 128,
    code: "ARTIFACT_MANIFEST_INVALID",
  });
  requireString(manifest.artifact_type, "manifest.artifact_type", {
    code: "ARTIFACT_MANIFEST_INVALID",
  });
  requireHash(manifest.content_hash, "manifest.content_hash", "ARTIFACT_MANIFEST_INVALID");
  requireString(manifest.media_type, "manifest.media_type", {
    code: "ARTIFACT_MANIFEST_INVALID",
  });
  requireSafeRevision(manifest.byte_size, "manifest.byte_size", "ARTIFACT_MANIFEST_INVALID");
  requireString(manifest.storage_uri, "manifest.storage_uri", {
    code: "ARTIFACT_MANIFEST_INVALID",
  });
  requireTimestamp(manifest.created_at, "manifest.created_at", "ARTIFACT_MANIFEST_INVALID");
  requireString(manifest.created_by, "manifest.created_by", {
    code: "ARTIFACT_MANIFEST_INVALID",
  });
  requireStringArray(manifest.input_artifact_ids, "manifest.input_artifact_ids", {
    code: "ARTIFACT_MANIFEST_INVALID",
  });
  requireStringArray(manifest.lineage_event_ids, "manifest.lineage_event_ids", {
    code: "ARTIFACT_MANIFEST_INVALID",
  });
  if (!(manifest.license === null || typeof manifest.license === "string")) {
    fail("ARTIFACT_MANIFEST_INVALID", "manifest.license must be a string or null");
  }
  if (!RETENTION_CLASSES.has(manifest.retention_class)) {
    fail("ARTIFACT_MANIFEST_INVALID", "manifest.retention_class is not canonical");
  }
  if (!CONFIDENTIALITY_CLASSES.has(manifest.confidentiality)) {
    fail("ARTIFACT_MANIFEST_INVALID", "manifest.confidentiality is not canonical");
  }
  const encryption = requirePlainRecord(manifest.encryption, "manifest.encryption", {
    allowedKeys: MANIFEST_ENCRYPTION_KEYS,
    requiredKeys: MANIFEST_ENCRYPTION_KEYS,
    code: "ARTIFACT_MANIFEST_INVALID",
  });
  if (
    typeof encryption.at_rest !== "boolean" ||
    typeof encryption.in_transit !== "boolean" ||
    !(encryption.key_ref === null || typeof encryption.key_ref === "string")
  ) {
    fail("ARTIFACT_MANIFEST_INVALID", "manifest.encryption is invalid");
  }
  if (manifest.integrity_status !== "verified") {
    fail("ARTIFACT_MANIFEST_INVALID", "manifest is not verified");
  }
  requireString(manifest.provenance_manifest_id, "manifest.provenance_manifest_id", {
    code: "ARTIFACT_MANIFEST_INVALID",
  });

  requireString(receipt.receipt_id, "receipt.receipt_id", { min: 3, max: 128, code });
  requireString(receipt.artifact_id, "receipt.artifact_id", { min: 3, max: 128, code });
  if (!(receipt.action_intent_id === null || typeof receipt.action_intent_id === "string")) {
    fail(code, "receipt.action_intent_id must be a string or null");
  }
  requireString(receipt.media_type, "receipt.media_type", { code });
  requireHash(receipt.content_hash, "receipt.content_hash", code);
  requireSafeRevision(receipt.byte_size, "receipt.byte_size", code);
  const creator = requirePlainRecord(receipt.created_by, "receipt.created_by", {
    allowedKeys: RECEIPT_CREATOR_KEYS,
    requiredKeys: RECEIPT_CREATOR_KEYS,
    code,
  });
  requireString(creator.actor_id, "receipt.created_by.actor_id", { min: 3, max: 128, code });
  if (!RECEIPT_ACTOR_TYPES.has(creator.actor_type)) {
    fail(code, "receipt.created_by.actor_type is not canonical");
  }
  requireTimestamp(receipt.created_at, "receipt.created_at", code);
  requireString(receipt.locator, "receipt.locator", { code });
  if (!(receipt.schema_ref === null || typeof receipt.schema_ref === "string")) {
    fail(code, "receipt.schema_ref must be a string or null");
  }
  if (
    receipt.receipt_id !== requestedReceiptId ||
    receipt.artifact_id !== manifest.artifact_id ||
    receipt.content_hash !== manifest.content_hash ||
    receipt.byte_size !== manifest.byte_size ||
    receipt.media_type !== manifest.media_type ||
    receipt.locator !== manifest.storage_uri ||
    manifest.integrity_status !== "verified"
  ) {
    fail(code, "ArtifactReceipt does not bind the resolved verified manifest", {
      requestedReceiptId,
    });
  }
  requireHash(receipt.receipt_hash, "receipt.receipt_hash", code);
  const withoutHash = canonicalClone(receipt);
  delete withoutHash.receipt_hash;
  const expectedReceiptHash = sha256CanonicalJson(withoutHash);
  if (receipt.receipt_hash !== expectedReceiptHash) {
    fail(code, "ArtifactReceipt hash does not match its canonical preimage", {
      requestedReceiptId,
      expected: expectedReceiptHash,
      actual: receipt.receipt_hash,
    });
  }
  const validations = requireDenseArray(receipt.validation_results, "validation_results", code);
  if (validations.length === 0) {
    fail("ARTIFACT_RECEIPT_VALIDATION_FAILED", "ArtifactReceipt contains a non-passing check", {
      requestedReceiptId,
    });
  }
  for (let index = 0; index < validations.length; index += 1) {
    const row = requirePlainRecord(validations[index], `validation_results[${index}]`, {
      allowedKeys: RECEIPT_VALIDATION_KEYS,
      requiredKeys: RECEIPT_VALIDATION_KEYS,
      code,
    });
    requireString(row.check, `validation_results[${index}].check`, { code });
    requireString(row.details, `validation_results[${index}].details`, { min: 0, code });
    if (row.status !== "PASS") {
      fail(
        "ARTIFACT_RECEIPT_VALIDATION_FAILED",
        "ArtifactReceipt contains a non-passing check",
        { requestedReceiptId, check: row.check, status: row.status },
      );
    }
  }
  const resolvedBytes = readDataProperty(resolvedRecord, "bytes", "resolved ArtifactReceipt", code);
  if (!Buffer.isBuffer(resolvedBytes) && !(resolvedBytes instanceof Uint8Array)) {
    fail(code, "resolved artifact bytes are unavailable", { requestedReceiptId });
  }
  const bytes = Buffer.from(resolvedBytes);
  const actualContentHash = `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
  if (
    bytes.length !== manifest.byte_size ||
    bytes.length !== receipt.byte_size
  ) {
    fail(
      "ARTIFACT_CONTENT_SIZE_MISMATCH",
      "resolved artifact bytes do not match the sealed byte size",
      {
        requestedReceiptId,
        actualByteSize: bytes.length,
        expectedByteSize: manifest.byte_size,
      },
    );
  }
  if (
    actualContentHash !== manifest.content_hash ||
    actualContentHash !== receipt.content_hash
  ) {
    fail(
      "ARTIFACT_CONTENT_HASH_MISMATCH",
      "resolved artifact bytes do not match the sealed content hash",
      {
        requestedReceiptId,
        actualContentHash,
        expectedContentHash: manifest.content_hash,
      },
    );
  }
  const expectedManifestHash = sha256CanonicalJson(manifest);
  const contentChecks = validations.filter(({ check }) => check === "content_sha256");
  const manifestChecks = validations.filter(
    ({ check }) => check === "artifact_manifest_sha256",
  );
  if (
    contentChecks.length !== 1 ||
    contentChecks[0].details !== actualContentHash ||
    manifestChecks.length !== 1 ||
    manifestChecks[0].details !== expectedManifestHash
  ) {
    fail(
      "ARTIFACT_RECEIPT_INTEGRITY_EVIDENCE_MISMATCH",
      "ArtifactReceipt does not contain exact integrity evidence for its bytes and manifest",
      { requestedReceiptId },
    );
  }
  return resolvedRecord;
};

const resolveReceipts = (artifactStore, receiptIds) => {
  if (artifactStore === null || typeof artifactStore?.resolveReceipt !== "function") {
    fail("INVALID_ARTIFACT_STORE", "artifact_store must expose resolveReceipt(receiptId)");
  }
  if (receiptIds.length === 0) {
    fail(
      "TRANSITION_RECEIPT_REQUIRED",
      "a FORGE phase transition requires at least one resolving ArtifactReceipt",
    );
  }
  const resolved = [];
  const artifactIds = new Set();
  for (const receiptId of receiptIds) {
    let entry;
    try {
      entry = artifactStore.resolveReceipt(receiptId);
    } catch (error) {
      fail(
        "ARTIFACT_RECEIPT_UNRESOLVED",
        "transition ArtifactReceipt could not be resolved",
        { receiptId, causeCode: error instanceof Error ? error.code ?? error.name : "unknown" },
        { cause: error },
      );
    }
    validateResolvedReceipt(entry, receiptId);
    if (artifactIds.has(entry.manifest.artifact_id)) {
      fail(
        "DUPLICATE_ARTIFACT_RECEIPT",
        "one transition cannot present multiple receipts for the same artifact",
        { artifactId: entry.manifest.artifact_id },
      );
    }
    artifactIds.add(entry.manifest.artifact_id);
    resolved.push(entry);
  }
  return resolved;
};

const parseJsonArtifact = (resolved, label, code) => {
  if (resolved.manifest.media_type !== "application/json") {
    fail(code, `${label} must be a JSON artifact`);
  }
  const bytes = Buffer.from(resolved.bytes);
  const text = bytes.toString("utf8");
  if (!Buffer.from(text, "utf8").equals(bytes)) fail(code, `${label} is not valid UTF-8`);
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    fail(code, `${label} is not valid JSON`, undefined, { cause: error });
  }
  return parsed;
};

const isSchemaRef = (resolved, kind) => SCHEMA_REFS[kind].has(resolved.receipt.schema_ref);

const validatePhaseArtifact = (candidate, label) => {
  const code = "INVALID_PHASE_ARTIFACT_SET";
  const artifact = requirePlainRecord(candidate, label, {
    allowedKeys: PHASE_ARTIFACT_KEYS,
    requiredKeys: PHASE_ARTIFACT_KEYS,
    code,
  });
  requireString(artifact.artifact_id, `${label}.artifact_id`, { min: 3, max: 128, code });
  requireString(artifact.kind, `${label}.kind`, { code });
  requireString(artifact.schema_ref, `${label}.schema_ref`, { code });
  requireHash(artifact.content_hash, `${label}.content_hash`, code);
  requireString(artifact.receipt_id, `${label}.receipt_id`, { min: 3, max: 128, code });
  if (!ARTIFACT_STATUSES.has(artifact.status)) fail(code, `${label}.status is not canonical`);
  return artifact;
};

const validatePhaseArtifactSet = (candidate, resolved, state, request, receiptById) => {
  const code = "INVALID_PHASE_ARTIFACT_SET";
  const phaseSet = requirePlainRecord(candidate, "PhaseArtifactSet", {
    allowedKeys: PHASE_SET_KEYS,
    requiredKeys: PHASE_SET_KEYS,
    code,
  });
  requireString(phaseSet.set_id, "set_id", { min: 3, max: 128, code });
  requireString(phaseSet.session_id, "session_id", { min: 3, max: 128, code });
  if (!PHASES.has(phaseSet.phase)) fail(code, "phase is not canonical");
  const required = requireDenseArray(phaseSet.required_artifacts, "required_artifacts", code);
  const optional = requireDenseArray(phaseSet.optional_artifacts, "optional_artifacts", code);
  if (required.length === 0) fail(code, "required_artifacts must not be empty");
  const seenArtifactIds = new Set();
  const seenReceiptIds = new Set();
  for (const [label, artifacts] of [
    ["required_artifacts", required],
    ["optional_artifacts", optional],
  ]) {
    artifacts.forEach((artifact, index) => {
      const entry = validatePhaseArtifact(artifact, `${label}[${index}]`);
      if (seenArtifactIds.has(entry.artifact_id) || seenReceiptIds.has(entry.receipt_id)) {
        fail(code, "phase artifact and receipt IDs must be unique within the set");
      }
      seenArtifactIds.add(entry.artifact_id);
      seenReceiptIds.add(entry.receipt_id);
    });
  }
  if (typeof phaseSet.complete !== "boolean") fail(code, "complete must be boolean");
  requireStringArray(phaseSet.missing_kinds, "missing_kinds", { unique: true, code });
  requireTimestamp(phaseSet.validated_at, "validated_at", code);
  requireHash(phaseSet.set_hash, "set_hash", code);
  const expectedHash = sha256CanonicalJson(selectKeys(phaseSet, PHASE_SET_HASH_KEYS));
  if (phaseSet.set_hash !== expectedHash) {
    fail("PHASE_ARTIFACT_SET_HASH_MISMATCH", "PhaseArtifactSet hash does not match its content", {
      expected: expectedHash,
      actual: phaseSet.set_hash,
    });
  }
  if (
    phaseSet.set_id !== resolved.manifest.artifact_id ||
    phaseSet.session_id !== state.session_id ||
    phaseSet.phase !== request.from_phase
  ) {
    fail("PHASE_ARTIFACT_SET_SCOPE_MISMATCH", "PhaseArtifactSet does not bind the current phase", {
      setId: phaseSet.set_id,
      sessionId: phaseSet.session_id,
      phase: phaseSet.phase,
    });
  }
  if (phaseSet.complete !== true || phaseSet.missing_kinds.length !== 0) {
    fail("PHASE_ARTIFACT_SET_INCOMPLETE", "current phase artifacts are not complete", {
      setId: phaseSet.set_id,
      missingKinds: phaseSet.missing_kinds,
    });
  }
  const retainedArtifacts = new Set(state.artifact_ids);
  const assertReceiptBinding = (entry) => {
    const evidence = receiptById.get(entry.receipt_id);
    if (
      evidence === undefined ||
      evidence.manifest.artifact_id !== entry.artifact_id ||
      evidence.manifest.content_hash !== entry.content_hash ||
      evidence.receipt.schema_ref !== entry.schema_ref
    ) {
      fail(
        "PHASE_ARTIFACT_RECEIPT_MISMATCH",
        "PhaseArtifactSet entry does not match a resolving transition receipt",
        { setId: phaseSet.set_id, artifactId: entry.artifact_id, receiptId: entry.receipt_id },
      );
    }
    if (!retainedArtifacts.has(entry.artifact_id)) {
      fail(
        "PHASE_ARTIFACT_NOT_IN_STATE",
        "phase artifact is not retained by the current ForgeSessionState",
        { setId: phaseSet.set_id, artifactId: entry.artifact_id },
      );
    }
  };
  for (const entry of required) {
    if (entry.status !== "VALID") {
      fail("PHASE_ARTIFACT_NOT_VALID", "every required phase artifact must be VALID", {
        setId: phaseSet.set_id,
        artifactId: entry.artifact_id,
        status: entry.status,
      });
    }
    assertReceiptBinding(entry);
  }
  for (const entry of optional) {
    if (entry.status === "VALID") assertReceiptBinding(entry);
  }
  return deepFreeze(canonicalClone(phaseSet));
};

const resolvePhaseArtifactSet = (resolvedReceipts, state, request, receiptById) => {
  const candidates = resolvedReceipts.filter((resolved) =>
    isSchemaRef(resolved, "PHASE_ARTIFACT_SET"),
  );
  if (request.from_phase === "IDLE") {
    if (candidates.length !== 0) {
      fail(
        "UNEXPECTED_PHASE_ARTIFACT_SET",
        "IDLE has no completed current-phase PhaseArtifactSet",
      );
    }
    return null;
  }
  if (candidates.length !== 1) {
    fail(
      "PHASE_ARTIFACT_SET_REQUIRED",
      "a non-IDLE transition requires exactly one current PhaseArtifactSet receipt",
      { receiptCount: candidates.length },
    );
  }
  const parsed = parseJsonArtifact(candidates[0], "PhaseArtifactSet", "INVALID_PHASE_ARTIFACT_SET");
  return validatePhaseArtifactSet(parsed, candidates[0], state, request, receiptById);
};

const validateIdleClassificationReceipt = (resolvedReceipts, state, request) => {
  if (request.from_phase !== "IDLE") return null;
  const candidates = resolvedReceipts.filter((resolved) => isSchemaRef(resolved, "CLASSIFICATION"));
  if (candidates.length !== 1) {
    fail(
      "CLASSIFICATION_RECEIPT_REQUIRED",
      "an IDLE transition requires exactly one F01 EpistemicWorkClassification receipt",
      { receiptCount: candidates.length },
    );
  }
  const classification = parseJsonArtifact(
    candidates[0],
    "EpistemicWorkClassification",
    "INVALID_CLASSIFICATION_ARTIFACT",
  );
  const code = "INVALID_CLASSIFICATION_ARTIFACT";
  const value = requirePlainRecord(classification, "EpistemicWorkClassification", {
    allowedKeys: CLASSIFICATION_KEYS,
    requiredKeys: CLASSIFICATION_KEYS,
    code,
  });
  requireString(value.classification_id, "classification_id", { code });
  requireString(value.request_id, "request_id", { min: 3, max: 128, code });
  requireHash(value.classification_hash, "classification_hash", code);
  if (
    !/^EWC-[0-9a-f]{64}$/u.test(value.classification_id) ||
    value.classification_id !== `EWC-${value.classification_hash.slice("sha256:".length)}` ||
    value.classification_id !== candidates[0].manifest.artifact_id
  ) {
    fail(
      code,
      "IDLE classification receipt does not resolve a hash-bound F01 artifact identity",
    );
  }
  if (!WORK_CLASSES.has(value.work_class) || value.work_class !== state.work_class) {
    fail("CLASSIFICATION_STATE_MISMATCH", "IDLE classification work_class does not match state", {
      classificationWorkClass: value.work_class,
      stateWorkClass: state.work_class,
    });
  }
  const reasons = requireStringArray(value.reasons, "reasons", { min: 2, unique: true, code });
  if (reasons.some((reason) => !CLASSIFICATION_REASON_PATTERN.test(reason))) {
    fail(code, "classification reasons are outside the canonical F01 rule vocabulary");
  }
  const riskFactors = requireStringArray(value.risk_factors, "risk_factors", {
    unique: true,
    code,
  });
  if (riskFactors.length > 7 || riskFactors.some((risk) => !CLASSIFICATION_RISK_FACTORS.has(risk))) {
    fail(code, "classification risk_factors are outside the canonical F01 vocabulary");
  }
  const phases = requireStringArray(value.required_phases, "required_phases", {
    unique: true,
    code,
  });
  const baseProjection = CLASS_PROJECTIONS[value.work_class];
  const exactProjections = [baseProjection.phases];
  if (["E4", "E5"].includes(value.work_class)) {
    exactProjections.push(["I", ...baseProjection.phases]);
  }
  if (!exactProjections.some((projection) => sameStringArray(phases, projection))) {
    fail(code, "classification required_phases do not match the exact F01 projection");
  }
  if (
    !NUMBER_IS_SAFE_INTEGER(value.default_role_count) ||
    value.default_role_count !== baseProjection.roleCount ||
    typeof value.human_gate_required !== "boolean" ||
    value.human_gate_required !== baseProjection.humanGate
  ) {
    fail(code, "classification protection projection does not match work_class");
  }
  requireTimestamp(value.classified_at, "classified_at", code);
  if (!CLASSIFIED_AT_PATTERN.test(value.classified_at)) {
    fail(code, "classified_at must use UTC millisecond precision");
  }
  if (value.classifier_version !== CLASSIFIER_VERSION) {
    fail(code, "classification was not produced by the active canonical classifier version");
  }
  const schemaChecks = candidates[0].receipt.validation_results.filter(
    (row) => row.check === "canonical_schema_validation",
  );
  if (
    schemaChecks.length !== 1 ||
    schemaChecks[0].details !== candidates[0].receipt.schema_ref
  ) {
    fail(
      "CLASSIFICATION_SCHEMA_RECEIPT_REQUIRED",
      "IDLE classification requires an exact canonical schema-validation receipt",
    );
  }
  return deepFreeze({
    classification_id: value.classification_id,
    classification_hash: value.classification_hash,
  });
};

const validateGateDecision = (candidate, resolved, state) => {
  const code = "INVALID_GATE_DECISION";
  const decision = requirePlainRecord(candidate, "GateDecision", {
    allowedKeys: GATE_DECISION_KEYS,
    requiredKeys: GATE_DECISION_KEYS,
    code,
  });
  requireString(decision.gate_id, "gate_id", { code });
  requireString(decision.gate_version, "gate_version", { code });
  requireString(decision.run_id, "run_id", { code });
  requireString(decision.name, "name", { code });
  if (!GATE_STATUSES.has(decision.status)) fail(code, "status is not canonical");
  requireStringArray(decision.reasons, "reasons", { code });
  requireStringArray(decision.evidence_ids, "evidence_ids", { code });
  requireStringArray(decision.input_artifact_ids, "input_artifact_ids", {
    min: 1,
    unique: true,
    code,
  });
  requireHash(decision.policy_bundle_hash, "policy_bundle_hash", code);
  requireString(decision.decision, "decision", { code });
  if (GATE_STATUSES.has(decision.decision) && decision.decision !== decision.status) {
    fail(
      "GATE_DECISION_STATUS_MISMATCH",
      "a status-valued GateDecision decision must equal its canonical status",
      { gateId: decision.gate_id, decision: decision.decision, status: decision.status },
    );
  }
  if (decision.decision === "NOT_REQUIRED" && decision.status !== "PASS") {
    fail(
      "GATE_DECISION_STATUS_MISMATCH",
      "a policy-evidenced NOT_REQUIRED GateDecision must have status PASS",
      { gateId: decision.gate_id, decision: decision.decision, status: decision.status },
    );
  }
  requireStringArray(decision.blocker_ids, "blocker_ids", { unique: true, code });
  requireTimestamp(decision.evaluated_at, "evaluated_at", code);
  requireTimestamp(decision.created_at, "created_at", code);
  requireString(decision.policy_version, "policy_version", { code });
  if (typeof decision.non_waivable !== "boolean") fail(code, "non_waivable must be boolean");
  if (!EVALUATOR_TYPES.has(decision.evaluator_type)) fail(code, "evaluator_type is not canonical");
  requireHash(decision.input_hash, "input_hash", code);
  requireHash(decision.decision_hash, "decision_hash", code);
  if (decision.status === "WAIVE") {
    if (decision.non_waivable === true) {
      fail("NON_WAIVABLE_GATE_OVERRIDE", "a non-waivable gate cannot be WAIVE", {
        gateId: decision.gate_id,
      });
    }
    requireString(decision.waiver_authority, "waiver_authority", { code });
    requireString(decision.waiver_reason, "waiver_reason", { code });
  } else if (decision.waiver_authority !== null || decision.waiver_reason !== null) {
    fail(code, "non-WAIVE GateDecision cannot contain waiver authority or reason");
  }
  const expectedHash = sha256CanonicalJson(selectKeys(decision, GATE_DECISION_HASH_KEYS));
  if (decision.decision_hash !== expectedHash) {
    fail("GATE_DECISION_HASH_MISMATCH", "GateDecision hash does not match its content", {
      gateId: decision.gate_id,
      expected: expectedHash,
      actual: decision.decision_hash,
    });
  }
  if (decision.gate_id !== resolved.manifest.artifact_id) {
    fail("GATE_DECISION_ID_MISMATCH", "GateDecision gate_id is not its artifact identity", {
      gateId: decision.gate_id,
      artifactId: resolved.manifest.artifact_id,
    });
  }
  if (decision.run_id !== state.run_spec_id) {
    fail("GATE_DECISION_RUN_MISMATCH", "GateDecision belongs to another run", {
      gateId: decision.gate_id,
      expectedRunId: state.run_spec_id,
      actualRunId: decision.run_id,
    });
  }
  if (decision.policy_bundle_hash !== state.policy_hash) {
    fail(
      "GATE_DECISION_POLICY_MISMATCH",
      "GateDecision policy_bundle_hash is not the active session policy",
      {
        gateId: decision.gate_id,
        expectedPolicyBundleHash: state.policy_hash,
        actualPolicyBundleHash: decision.policy_bundle_hash,
      },
    );
  }
  return deepFreeze(canonicalClone(decision));
};

const resolveGateDecisions = (resolvedReceipts, state, request) => {
  const candidates = resolvedReceipts.filter((resolved) => isSchemaRef(resolved, "GATE_DECISION"));
  const decisions = candidates.map((resolved) =>
    validateGateDecision(
      parseJsonArtifact(resolved, "GateDecision", "INVALID_GATE_DECISION"),
      resolved,
      state,
    ),
  );
  const byId = new Map();
  for (const decision of decisions) {
    if (byId.has(decision.gate_id)) {
      fail("DUPLICATE_GATE_DECISION", "gate decision IDs must be unique", {
        gateId: decision.gate_id,
      });
    }
    byId.set(decision.gate_id, decision);
  }
  const requested = new Set(request.gate_result_ids);
  const extra = decisions.filter((decision) => !requested.has(decision.gate_id));
  const missing = request.gate_result_ids.filter((gateId) => !byId.has(gateId));
  if (extra.length !== 0 || missing.length !== 0) {
    fail(
      "GATE_RESULT_RESOLUTION_MISMATCH",
      "gate_result_ids must exactly identify the supplied GateDecision artifacts",
      {
        extraGateIds: extra.map((decision) => decision.gate_id).sort(compareCanonicalText),
        missingGateIds: missing.sort(compareCanonicalText),
      },
    );
  }
  if (request.to_phase === "E" && request.gate_result_ids.length === 0) {
    fail("GATE_DECISION_REQUIRED", "entering E requires resolving GateDecision artifacts");
  }
  const resolvedArtifactIds = new Set(
    resolvedReceipts.map((resolved) => resolved.manifest.artifact_id),
  );
  for (const decision of decisions) {
    const unresolvedEvidenceIds = decision.evidence_ids.filter(
      (artifactId) => !resolvedArtifactIds.has(artifactId),
    );
    if (unresolvedEvidenceIds.length !== 0) {
      fail(
        "GATE_EVIDENCE_UNRESOLVED",
        "GateDecision evidence_ids must resolve through transition ArtifactReceipts",
        {
          gateId: decision.gate_id,
          unresolvedEvidenceIds: unresolvedEvidenceIds.sort(compareCanonicalText),
        },
      );
    }
    const unresolvedInputArtifactIds = decision.input_artifact_ids.filter(
      (artifactId) => !resolvedArtifactIds.has(artifactId),
    );
    if (unresolvedInputArtifactIds.length !== 0) {
      fail(
        "GATE_INPUT_ARTIFACT_UNRESOLVED",
        "GateDecision input_artifact_ids must resolve through transition ArtifactReceipts",
        {
          gateId: decision.gate_id,
          unresolvedInputArtifactIds: unresolvedInputArtifactIds.sort(compareCanonicalText),
        },
      );
    }
  }
  const unsatisfied = decisions.filter((decision) => ["FAIL", "BLOCK"].includes(decision.status));
  if (unsatisfied.length !== 0) {
    fail("UNSATISFIED_GATE", "FAIL and BLOCK gate results cannot admit a transition", {
      gateIds: unsatisfied.map((decision) => decision.gate_id).sort(compareCanonicalText),
    });
  }
  return decisions.sort((left, right) => compareCanonicalText(left.gate_id, right.gate_id));
};

const validateHumanAuthorityReceipt = (resolved, decision) => {
  const code = "HUMAN_DECISION_AUTHORITY_MISMATCH";
  if (
    resolved.manifest.artifact_id !== decision.decision_id ||
    resolved.manifest.created_by !== decision.authority_id ||
    resolved.manifest.created_at !== decision.created_at ||
    resolved.receipt.created_by?.actor_type !== "human" ||
    resolved.receipt.created_by?.actor_id !== decision.authority_id ||
    resolved.receipt.created_at !== decision.created_at
  ) {
    fail(code, "HumanDecision manifest and receipt do not prove its declared human authority", {
      decisionId: decision.decision_id,
    });
  }
};

const resolveHumanDecision = (resolvedReceipts, state, request) => {
  const candidates = resolvedReceipts.filter((resolved) => isSchemaRef(resolved, "HUMAN_DECISION"));
  if (request.human_decision_id === null) {
    if (candidates.length !== 0) {
      fail(
        "HUMAN_DECISION_NOT_DECLARED",
        "a HumanDecision receipt must be named by human_decision_id",
      );
    }
    return null;
  }
  if (candidates.length !== 1) {
    fail(
      "HUMAN_DECISION_ARTIFACT_REQUIRED",
      "human_decision_id requires exactly one resolving HumanDecision receipt",
      { receiptCount: candidates.length },
    );
  }
  const parsed = parseJsonArtifact(
    candidates[0],
    "HumanDecision",
    "HUMAN_DECISION_ARTIFACT_INVALID",
  );
  let decision;
  try {
    decision = validateHumanDecisionArtifact(parsed);
  } catch (error) {
    fail(
      error instanceof Error ? error.code ?? "HUMAN_DECISION_ARTIFACT_INVALID" : "HUMAN_DECISION_ARTIFACT_INVALID",
      "HumanDecision artifact failed canonical validation",
      { decisionId: request.human_decision_id },
      { cause: error },
    );
  }
  if (decision.decision_id !== request.human_decision_id) {
    fail("HUMAN_DECISION_ID_MISMATCH", "human_decision_id does not match the artifact", {
      requested: request.human_decision_id,
      actual: decision.decision_id,
    });
  }
  if (decision.run_id !== state.run_spec_id) {
    fail("HUMAN_DECISION_SCOPE_MISMATCH", "HumanDecision belongs to another run", {
      expectedRunId: state.run_spec_id,
      actualRunId: decision.run_id,
    });
  }
  validateHumanAuthorityReceipt(candidates[0], decision);
  return decision;
};

const validateWaiverProvenance = (gateDecisions, humanDecision) => {
  const waived = gateDecisions.filter((decision) => decision.status === "WAIVE");
  if (waived.length === 0) {
    if (humanDecision?.decision_type === "override_waivable_gate") {
      fail(
        "HUMAN_DECISION_SCOPE_MISMATCH",
        "override_waivable_gate cannot be presented without a WAIVE GateDecision",
      );
    }
    return;
  }
  if (humanDecision === null) {
    fail(
      "HUMAN_DECISION_REQUIRED",
      "WAIVE requires an explicit resolving HumanDecision artifact and receipt",
    );
  }
  if (humanDecision.decision_type !== "override_waivable_gate") {
    fail(
      "HUMAN_DECISION_TYPE_MISMATCH",
      "WAIVE requires decision_type override_waivable_gate",
    );
  }
  for (const gate of waived) {
    if (gate.waiver_authority !== humanDecision.authority_id) {
      fail(
        "HUMAN_DECISION_AUTHORITY_MISMATCH",
        "GateDecision waiver authority differs from the HumanDecision authority",
        { gateId: gate.gate_id },
      );
    }
    if (
      gate.gate_id !== humanDecision.subject_id &&
      !humanDecision.affected_artifact_ids.includes(gate.gate_id)
    ) {
      fail(
        "HUMAN_DECISION_SCOPE_MISMATCH",
        "HumanDecision does not affect the waived gate artifact",
        { gateId: gate.gate_id, decisionId: humanDecision.decision_id },
      );
    }
  }
};

const receiptBindings = (resolvedReceipts) =>
  resolvedReceipts
    .map((resolved) => ({
      receipt_id: resolved.receipt.receipt_id,
      receipt_hash: resolved.receipt.receipt_hash,
      artifact_id: resolved.manifest.artifact_id,
      content_hash: resolved.manifest.content_hash,
      schema_ref: resolved.receipt.schema_ref,
    }))
    .sort((left, right) => compareCanonicalText(left.receipt_id, right.receipt_id));

const buildAdmission = ({
  state,
  request,
  resolvedReceipts,
  idleClassification,
  phaseSet,
  gateDecisions,
  humanDecision,
}) => {
  const semantic = {
    admission_version: TRANSITION_ADMISSION_VERSION,
    decision: "ADMIT",
    session_id: state.session_id,
    request_id: request.request_id,
    request_hash: sha256CanonicalJson(request),
    idempotency_key: request.idempotency_key,
    expected_revision: request.expected_revision,
    from_phase: request.from_phase,
    to_phase: request.to_phase,
    prior_state_hash: state.state_hash,
    idle_classification_id: idleClassification?.classification_id ?? null,
    idle_classification_hash: idleClassification?.classification_hash ?? null,
    phase_artifact_set_id: phaseSet?.set_id ?? null,
    phase_artifact_set_hash: phaseSet?.set_hash ?? null,
    receipt_bindings: receiptBindings(resolvedReceipts),
    gate_decisions: gateDecisions.map((decision) => ({
      gate_id: decision.gate_id,
      decision_hash: decision.decision_hash,
      status: decision.status,
    })),
    human_decision_id: humanDecision?.decision_id ?? null,
    human_decision_hash: humanDecision?.decision_hash ?? null,
  };
  const admissionHash = sha256CanonicalJson(semantic);
  return deepFreeze({
    ...semantic,
    admission_id: `FTA-${admissionHash.slice("sha256:".length)}`,
    admission_hash: admissionHash,
  });
};

export const admitForgeTransition = ({
  current_state,
  transition_request,
  artifact_store,
}) => {
  const state = validateState(current_state);
  const request = validateRequest(transition_request);
  validateStateRequestBinding(state, request);
  const resolvedReceipts = resolveReceipts(artifact_store, request.artifact_receipt_ids);
  const receiptById = new Map(
    resolvedReceipts.map((resolved) => [resolved.receipt.receipt_id, resolved]),
  );
  const phaseArtifactSet = resolvePhaseArtifactSet(
    resolvedReceipts,
    state,
    request,
    receiptById,
  );
  const idleClassification = validateIdleClassificationReceipt(resolvedReceipts, state, request);
  const gateDecisions = resolveGateDecisions(resolvedReceipts, state, request);
  const humanDecision = resolveHumanDecision(resolvedReceipts, state, request);
  validateWaiverProvenance(gateDecisions, humanDecision);
  const admission = buildAdmission({
    state,
    request,
    resolvedReceipts,
    idleClassification,
    phaseSet: phaseArtifactSet,
    gateDecisions,
    humanDecision,
  });
  return deepFreeze({
    admission,
    idle_classification: idleClassification,
    phase_artifact_set: phaseArtifactSet,
    gate_decisions: gateDecisions,
    human_decision: humanDecision,
  });
};

export const sha256TransitionJson = (value) => sha256CanonicalJson(value);
