import { assertForgeSessionStateIntegrity } from "../fsm/index.mjs";

import {
  NUMBER_IS_SAFE_INTEGER,
  OBJECT_FREEZE,
  detached,
  exactKeys,
  fail,
  hashSealedRecord,
  hashJson,
  readDataProperty,
  requireDenseArray,
  requireHash,
  requirePlainRecord,
  requireString,
  sealRecord,
  withoutKey,
} from "./canonical-json.mjs";

export const SESSION_RECORD_VERSION = "foundry.forge.session.v1";
export const OPERATION_BINDING_RECORD_VERSION =
  "foundry.forge.session-operation-binding.v1";
export const OUTBOX_RECORD_VERSION = "foundry.forge.session-outbox.v1";
export const OUTBOX_INDEX_RECORD_VERSION = "foundry.forge.session-outbox-index.v1";
export const OUTBOX_INDEX_ID = "global";

const OUTBOX_STATES = new Set(["PENDING", "PUBLISHED", "CONFLICTED"]);

export const DURABLE_FORGE_SESSION_RECORD_TYPES = OBJECT_FREEZE({
  SESSION: SESSION_RECORD_VERSION,
  OPERATION_BINDING: OPERATION_BINDING_RECORD_VERSION,
  OUTBOX: OUTBOX_RECORD_VERSION,
  OUTBOX_INDEX: OUTBOX_INDEX_RECORD_VERSION,
});

export const validatePublishedProjection = (candidate) => {
  const code = "FORGE_SESSION_STATE_INTEGRITY_FAILED";
  const keys = [
    "state",
    "phase_artifact_sets",
    "superseded_phase_artifact_sets",
    "last_session_event_id",
    "last_session_event_hash",
    "classification_projection_id",
    "classification_projection_hash",
    "projection_hash",
  ];
  const value = exactKeys(candidate, keys, "published projection", code);
  try {
    assertForgeSessionStateIntegrity(readDataProperty(value, "state", "published projection", code));
  } catch {
    fail(code, "published ForgeSessionState is invalid");
  }
  requireDenseArray(
    readDataProperty(value, "phase_artifact_sets", "published projection", code),
    "phase_artifact_sets",
    code,
  );
  requireDenseArray(
    readDataProperty(value, "superseded_phase_artifact_sets", "published projection", code),
    "superseded_phase_artifact_sets",
    code,
  );
  requireString(readDataProperty(value, "last_session_event_id"), "last_session_event_id", {
    code,
  });
  requireHash(readDataProperty(value, "last_session_event_hash"), "last_session_event_hash", code);
  requireString(
    readDataProperty(value, "classification_projection_id"),
    "classification_projection_id",
    { code },
  );
  requireHash(
    readDataProperty(value, "classification_projection_hash"),
    "classification_projection_hash",
    code,
  );
  const expectedHash = hashJson(withoutKey(value, "projection_hash"));
  if (readDataProperty(value, "projection_hash") !== expectedHash) {
    fail(code, "published projection hash is invalid");
  }
  return detached(value);
};

export const validateSessionRecord = (record) => {
  const code = "FORGE_SESSION_STATE_INTEGRITY_FAILED";
  if (record === null) return null;
  if (!NUMBER_IS_SAFE_INTEGER(record.revision) || record.revision < 0) {
    fail(code, "session record revision is invalid");
  }
  const keys = ["record_version", "session_id", "published", "pending", "record_hash"];
  const value = exactKeys(record.value, keys, "session record", code);
  if (value.record_version !== SESSION_RECORD_VERSION || value.session_id !== record.recordId) {
    fail(code, "session record identity is invalid");
  }
  const published = value.published === null ? null : validatePublishedProjection(value.published);
  let pending = null;
  if (value.pending !== null) {
    const accepted = exactKeys(
      value.pending,
      ["operation_id", "outbox_id", "candidate_state_hash"],
      "session pending",
      code,
    );
    pending = detached({
      operation_id: requireString(accepted.operation_id, "pending.operation_id", { code }),
      outbox_id: requireString(accepted.outbox_id, "pending.outbox_id", { code }),
      candidate_state_hash: requireHash(
        accepted.candidate_state_hash,
        "pending.candidate_state_hash",
        code,
      ),
    });
  }
  if (value.record_hash !== hashSealedRecord(value)) {
    fail(code, "session record hash is invalid");
  }
  return {
    revision: record.revision,
    value: detached({ ...value, published, pending }),
  };
};

export const validateBindingRecord = (record, expectedId = undefined) => {
  const code = "FORGE_OPERATION_BINDING_INTEGRITY_FAILED";
  if (record === null) return null;
  if (record.revision !== 0) fail(code, "operation binding must remain at revision 0");
  const keys = [
    "record_version",
    "binding_kind",
    "binding_id",
    "session_id",
    "key_hash",
    "operation_id",
    "request_hash",
    "outbox_id",
    "record_hash",
  ];
  const value = exactKeys(record.value, keys, "operation binding", code);
  if (
    value.record_version !== OPERATION_BINDING_RECORD_VERSION ||
    value.binding_id !== record.recordId ||
    (expectedId !== undefined && value.binding_id !== expectedId) ||
    !new Set(["REQUEST", "IDEMPOTENCY"]).has(value.binding_kind)
  ) {
    fail(code, "operation binding identity is invalid");
  }
  requireHash(value.key_hash, "binding.key_hash", code);
  requireHash(value.request_hash, "binding.request_hash", code);
  if (value.record_hash !== hashSealedRecord(value)) {
    fail(code, "operation binding record hash is invalid");
  }
  return detached(value);
};

export const validateOutboxEnvelope = (record) => {
  const code = "FORGE_OUTBOX_INTEGRITY_FAILED";
  if (record === null) return null;
  const keys = [
    "record_version",
    "outbox_id",
    "operation_id",
    "session_id",
    "request_hash",
    "state",
    "intent",
    "resolution",
    "record_hash",
  ];
  const value = exactKeys(record.value, keys, "session outbox", code);
  if (
    value.record_version !== OUTBOX_RECORD_VERSION ||
    value.outbox_id !== record.recordId ||
    !OUTBOX_STATES.has(value.state)
  ) {
    fail(code, "session outbox identity or state is invalid");
  }
  requireHash(value.request_hash, "outbox.request_hash", code);
  if (
    (value.state === "PENDING" && (record.revision !== 0 || value.resolution !== null)) ||
    (value.state !== "PENDING" && (record.revision !== 1 || value.resolution === null))
  ) {
    fail(code, "session outbox lifecycle is invalid");
  }
  const intent = requirePlainRecord(value.intent, "outbox intent", { code });
  if (
    intent.operation_id !== value.operation_id ||
    intent.outbox_id !== value.outbox_id ||
    intent.session_id !== value.session_id ||
    intent.request_hash !== value.request_hash ||
    intent.intent_hash !== hashJson(withoutKey(intent, "intent_hash"))
  ) {
    fail(code, "session outbox intent binding is invalid");
  }
  if (value.record_hash !== hashSealedRecord(value)) {
    fail(code, "session outbox record hash is invalid");
  }
  return { revision: record.revision, value: detached(value) };
};

export const validateIndexRecord = (record) => {
  const code = "FORGE_OUTBOX_INDEX_INTEGRITY_FAILED";
  if (record === null) return null;
  const keys = ["record_version", "outbox_ids", "record_hash"];
  const value = exactKeys(record.value, keys, "session outbox index", code);
  if (value.record_version !== OUTBOX_INDEX_RECORD_VERSION) {
    fail(code, "session outbox index version is invalid");
  }
  const ids = requireDenseArray(value.outbox_ids, "outbox_ids", code);
  const seen = new Set();
  for (const id of ids) {
    requireString(id, "outbox_id", { code });
    if (seen.has(id)) fail(code, "session outbox index contains a duplicate ID");
    seen.add(id);
  }
  if (value.record_hash !== hashSealedRecord(value)) {
    fail(code, "session outbox index hash is invalid");
  }
  return { revision: record.revision, value: detached(value) };
};

export const makeBinding = ({
  bindingKind,
  bindingId,
  sessionId,
  keyHash,
  operationId,
  requestHash,
  outboxId,
}) => sealRecord({
  record_version: OPERATION_BINDING_RECORD_VERSION,
  binding_kind: bindingKind,
  binding_id: bindingId,
  session_id: sessionId,
  key_hash: keyHash,
  operation_id: operationId,
  request_hash: requestHash,
  outbox_id: outboxId,
});

export const makeSessionRecord = (sessionId, published, pending) =>
  sealRecord({
    record_version: SESSION_RECORD_VERSION,
    session_id: sessionId,
    published: published === null ? null : detached(published),
    pending: pending === null ? null : detached(pending),
  });

export const makeIndexRecord = (outboxIds) =>
  sealRecord({
    record_version: OUTBOX_INDEX_RECORD_VERSION,
    outbox_ids: [...outboxIds],
  });

export const makeOutboxRecord = ({
  operationId,
  outboxId,
  sessionId,
  requestHash,
  state,
  intent,
  resolution,
}) => sealRecord({
  record_version: OUTBOX_RECORD_VERSION,
  outbox_id: outboxId,
  operation_id: operationId,
  session_id: sessionId,
  request_hash: requestHash,
  state,
  intent: detached(intent),
  resolution: resolution === null ? null : detached(resolution),
});
