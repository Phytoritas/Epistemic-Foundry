import { ArtifactStoreError } from "../../artifacts/content-addressed-artifact-store.mjs";
import {
  NoeticLedgerError,
  computeEventHash,
} from "../../ledger/noetic-ledger.mjs";
import { SQLiteStateStoreError } from "../../state/sqlite/sqlite-state-store.mjs";
import {
  ClassificationCommitterError,
  assertClassificationArtifactIntegrity,
} from "../classifier/index.mjs";
import {
  FORGE_PHASES,
  ForgeFsmError,
  assertForgeSessionStateIntegrity,
  reduceAdmittedForgeTransition,
  sealForgeSessionState,
} from "../fsm/index.mjs";
import {
  TransitionAdmissionError,
  admitDurableForgeTransition,
} from "../gates/index.mjs";

import {
  ARRAY_IS_ARRAY,
  DurableForgeSessionError,
  IS_PROXY,
  NUMBER_IS_SAFE_INTEGER,
  OBJECT_FREEZE,
  canonicalJson,
  detached,
  exactKeys,
  fail,
  hashBytes,
  hashJson,
  readDataProperty,
  requireDenseArray,
  requireHash,
  requirePlainRecord,
  requireString,
  requireTimestamp,
  sameCanonical,
  withoutKey,
} from "./canonical-json.mjs";
import {
  DURABLE_FORGE_SESSION_RECORD_TYPES,
  OPERATION_BINDING_RECORD_VERSION,
  OUTBOX_INDEX_ID,
  OUTBOX_INDEX_RECORD_VERSION,
  OUTBOX_RECORD_VERSION,
  SESSION_RECORD_VERSION,
  makeBinding,
  makeIndexRecord,
  makeOutboxRecord,
  makeSessionRecord,
  validateBindingRecord,
  validateIndexRecord,
  validateOutboxEnvelope,
  validateSessionRecord,
} from "./session-records.mjs";
import {
  bindDurableForgeSessionWorkerAuthority,
} from "./session-worker-authority.mjs";

export { DurableForgeSessionError, DURABLE_FORGE_SESSION_RECORD_TYPES };

const CONTRACT = "DURABLE_FORGE_V1";
const EVENT_SCHEMA_VERSION = "4.0.0";
const EVENT_AGGREGATE_TYPE = "forge_session";
const EVENT_TYPES = OBJECT_FREEZE({
  OPEN: "forge.session.opened",
  TRANSITION: "forge.session.transitioned",
});
const dependencyMethod = (dependency, method, label) => {
  if (
    dependency === null ||
    !["object", "function"].includes(typeof dependency) ||
    IS_PROXY(dependency) ||
    typeof dependency[method] !== "function"
  ) {
    fail("FORGE_INVALID_DEPENDENCY", `${label}.${method} is required`);
  }
};

const normalizeDependencies = (options) => {
  const value = requirePlainRecord(options, "durable forge session options", {
    allowedKeys: ["stateStore", "artifactStore", "ledger", "classificationPort", "clock"],
    requiredKeys: ["stateStore", "artifactStore", "ledger", "classificationPort", "clock"],
    code: "FORGE_INVALID_DEPENDENCY",
  });
  const stateStore = readDataProperty(value, "stateStore", "options", "FORGE_INVALID_DEPENDENCY");
  const artifactStore = readDataProperty(
    value,
    "artifactStore",
    "options",
    "FORGE_INVALID_DEPENDENCY",
  );
  const ledger = readDataProperty(value, "ledger", "options", "FORGE_INVALID_DEPENDENCY");
  const classificationPort = readDataProperty(
    value,
    "classificationPort",
    "options",
    "FORGE_INVALID_DEPENDENCY",
  );
  const clock = readDataProperty(value, "clock", "options", "FORGE_INVALID_DEPENDENCY");

  for (const method of [
    "transaction",
    "readRevisionedRecord",
    "createRevisionedRecord",
    "compareAndSwapRevision",
  ]) {
    dependencyMethod(stateStore, method, "stateStore");
  }
  for (const method of ["putArtifact", "resolveReceipt"]) {
    dependencyMethod(artifactStore, method, "artifactStore");
  }
  for (const method of ["appendConditional", "readEvents", "verifyRun"]) {
    dependencyMethod(ledger, method, "ledger");
  }
  dependencyMethod(
    classificationPort,
    "readClassificationReplayProjection",
    "classificationPort",
  );
  if (typeof clock !== "function" || IS_PROXY(clock)) {
    fail("FORGE_INVALID_DEPENDENCY", "clock must be a non-proxy function");
  }
  return { stateStore, artifactStore, ledger, classificationPort, clock };
};

const timestampFromClock = (clock) => {
  let candidate;
  try {
    candidate = clock();
  } catch {
    fail("FORGE_CLOCK_INVALID", "clock could not provide a timestamp");
  }
  const value = candidate instanceof Date ? candidate.toISOString() : candidate;
  requireTimestamp(value, "clock result", "FORGE_CLOCK_INVALID");
  const canonical = new Date(value).toISOString();
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/u.test(canonical)) {
    fail("FORGE_CLOCK_INVALID", "clock result is outside the canonical range");
  }
  return canonical;
};

const compareTimes = (left, right) => new Date(left).valueOf() - new Date(right).valueOf();

const normalizeActor = (candidate, label = "actor") => {
  const actor = exactKeys(
    candidate,
    ["actor_id", "actor_type", "role"],
    label,
    "FORGE_INPUT_INVALID",
  );
  const actorId = requireString(readDataProperty(actor, "actor_id"), `${label}.actor_id`, {
    min: 3,
    max: 128,
  });
  const actorType = readDataProperty(actor, "actor_type");
  if (!new Set(["human", "agent", "service"]).has(actorType)) {
    fail("FORGE_INPUT_INVALID", `${label}.actor_type is not canonical`);
  }
  return detached({
    actor_id: actorId,
    actor_type: actorType,
    role: requireString(readDataProperty(actor, "role"), `${label}.role`),
  });
};

const normalizeExpectedHead = (candidate) => {
  const value = exactKeys(
    candidate,
    ["event_count", "tail_event_id", "tail_event_hash"],
    "expected_ledger_head",
    "FORGE_INPUT_INVALID",
  );
  const eventCount = readDataProperty(value, "event_count");
  const tailEventId = readDataProperty(value, "tail_event_id");
  const tailEventHash = readDataProperty(value, "tail_event_hash");
  if (!NUMBER_IS_SAFE_INTEGER(eventCount) || eventCount < 0) {
    fail("FORGE_INPUT_INVALID", "expected_ledger_head.event_count is invalid");
  }
  if (eventCount === 0) {
    if (tailEventId !== null || tailEventHash !== null) {
      fail("FORGE_INPUT_INVALID", "an empty expected_ledger_head requires null tail fields");
    }
  } else {
    requireString(tailEventId, "expected_ledger_head.tail_event_id");
    requireHash(tailEventHash, "expected_ledger_head.tail_event_hash");
  }
  return detached({ event_count: eventCount, tail_event_id: tailEventId, tail_event_hash: tailEventHash });
};

const normalizeOpenInput = (candidate) => {
  const keys = [
    "request_id",
    "session_id",
    "workspace_id",
    "run_spec_id",
    "classification_id",
    "policy_hash",
    "corpus_snapshot_hash",
    "actor",
    "idempotency_key",
    "requested_at",
    "expected_ledger_head",
  ];
  const value = exactKeys(candidate, keys, "open session input", "FORGE_INPUT_INVALID");
  const request = {
    request_id: requireString(readDataProperty(value, "request_id"), "request_id", {
      min: 3,
      max: 128,
    }),
    session_id: requireString(readDataProperty(value, "session_id"), "session_id", {
      min: 3,
      max: 128,
    }),
    workspace_id: requireString(readDataProperty(value, "workspace_id"), "workspace_id", {
      min: 3,
      max: 128,
    }),
    run_spec_id: requireString(readDataProperty(value, "run_spec_id"), "run_spec_id", {
      min: 3,
      max: 128,
    }),
    classification_id: requireString(
      readDataProperty(value, "classification_id"),
      "classification_id",
      { min: 3, max: 128 },
    ),
    policy_hash: requireHash(readDataProperty(value, "policy_hash"), "policy_hash"),
    corpus_snapshot_hash: requireHash(
      readDataProperty(value, "corpus_snapshot_hash"),
      "corpus_snapshot_hash",
    ),
    actor: normalizeActor(readDataProperty(value, "actor")),
    idempotency_key: requireString(
      readDataProperty(value, "idempotency_key"),
      "idempotency_key",
      { min: 8 },
    ),
    requested_at: requireTimestamp(readDataProperty(value, "requested_at"), "requested_at"),
  };
  return {
    request: detached(request),
    expectedHead: normalizeExpectedHead(readDataProperty(value, "expected_ledger_head")),
  };
};

const normalizeOpenOperationInput = (candidate, { includeProjection = false } = {}) => {
  const allowedKeys = includeProjection
    ? ["open_request", "expected_ledger_head", "classification_projection"]
    : ["open_request", "expected_ledger_head"];
  const value = exactKeys(
    candidate,
    allowedKeys,
    "open session operation input",
    "FORGE_INPUT_INVALID",
  );
  const openRequest = detached(
    readDataProperty(value, "open_request", "open session operation input", "FORGE_INPUT_INVALID"),
  );
  const normalized = normalizeOpenInput({
    ...openRequest,
    expected_ledger_head: readDataProperty(
      value,
      "expected_ledger_head",
      "open session operation input",
      "FORGE_INPUT_INVALID",
    ),
  });
  return includeProjection
    ? {
        ...normalized,
        projection: validateClassificationProjection(
          readDataProperty(
            value,
            "classification_projection",
            "open session operation input",
            "FORGE_INPUT_INVALID",
          ),
        ),
      }
    : normalized;
};

const normalizeTransitionInput = (candidate) => {
  const value = exactKeys(
    candidate,
    ["transition_request", "expected_ledger_head"],
    "transition session input",
    "FORGE_INPUT_INVALID",
  );
  const request = detached(readDataProperty(value, "transition_request"));
  const requestRecord = requirePlainRecord(request, "transition_request", {
    code: "FORGE_INPUT_INVALID",
  });
  const requestId = requireString(readDataProperty(requestRecord, "request_id"), "request_id", {
    min: 3,
    max: 128,
  });
  const sessionId = requireString(readDataProperty(requestRecord, "session_id"), "session_id", {
    min: 3,
    max: 128,
  });
  const idempotencyKey = requireString(
    readDataProperty(requestRecord, "idempotency_key"),
    "idempotency_key",
    { min: 8 },
  );
  requireTimestamp(readDataProperty(requestRecord, "requested_at"), "requested_at");
  return {
    request,
    requestId,
    sessionId,
    idempotencyKey,
    expectedHead: normalizeExpectedHead(readDataProperty(value, "expected_ledger_head")),
  };
};

const requestHashFor = (kind, request, expectedHead) =>
  hashJson({
    contract: CONTRACT,
    kind,
    request,
    expected_ledger_head: expectedHead,
  });

const suffixForOperation = (kind, sessionId, requestHash) =>
  hashJson({ contract: CONTRACT, kind, session_id: sessionId, request_hash: requestHash }).slice(
    "sha256:".length,
  );

const operationIdentity = (kind, sessionId, requestHash) => {
  const suffix = suffixForOperation(kind, sessionId, requestHash);
  return OBJECT_FREEZE({
    operationId: `FOP-F04-${suffix}`,
    eventId: `EVT-F04-${suffix}`,
    payloadArtifactId: `FSP-F04-${suffix}`,
    payloadReceiptId: `AR-F04-${suffix}`,
    outboxId: `OUTBOX-F04-${suffix}`,
  });
};

const bindingIdentity = (kind, sessionId, key) => {
  const keyHash = hashJson({
    contract: CONTRACT,
    binding_kind: kind,
    session_id: sessionId,
    key,
  });
  const prefix = kind === "REQUEST" ? "REQ-F04" : "IDEM-F04";
  return OBJECT_FREEZE({ id: `${prefix}-${keyHash.slice("sha256:".length)}`, keyHash });
};

const validateClassificationProjection = (candidate) => {
  const code = "FORGE_CLASSIFICATION_INTEGRITY_FAILED";
  const keys = [
    "projection_version",
    "classification",
    "identity_context",
    "artifact_binding",
    "ledger_binding",
    "projection_hash",
    "projection_id",
  ];
  const value = exactKeys(candidate, keys, "classification replay projection", code);
  if (readDataProperty(value, "projection_version") !== CONTRACT) {
    fail(code, "classification replay projection version is incompatible");
  }
  const semantic = Object.fromEntries(
    keys
      .filter((key) => !["projection_hash", "projection_id"].includes(key))
      .map((key) => [key, readDataProperty(value, key)]),
  );
  const expectedHash = hashJson(semantic);
  const actualHash = requireHash(readDataProperty(value, "projection_hash"), "projection_hash", code);
  const projectionId = requireString(readDataProperty(value, "projection_id"), "projection_id", {
    code,
  });
  if (actualHash !== expectedHash || projectionId !== `F01RP-${expectedHash.slice("sha256:".length)}`) {
    fail(code, "classification replay projection identity is invalid");
  }
  const classification = exactKeys(
    readDataProperty(value, "classification"),
    [
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
    ],
    "classification",
    code,
  );
  const classificationId = requireString(
    readDataProperty(classification, "classification_id", "classification", code),
    "classification.classification_id",
    { code },
  );
  const classificationHash = requireHash(
    readDataProperty(classification, "classification_hash", "classification", code),
    "classification.classification_hash",
    code,
  );
  if (classificationId !== `EWC-${classificationHash.slice("sha256:".length)}`) {
    fail(code, "classification identity is not hash-bound");
  }
  const identityContext = exactKeys(
    readDataProperty(value, "identity_context"),
    [
      "request_input_hash",
      "policy_bundle_hash",
      "accepted_signals",
      "supersedes_classification_hash",
      "human_decision_hash",
    ],
    "identity_context",
    code,
  );
  requireHash(
    readDataProperty(identityContext, "policy_bundle_hash", "identity_context", code),
    "identity_context.policy_bundle_hash",
    code,
  );
  const artifactBinding = exactKeys(
    readDataProperty(value, "artifact_binding"),
    [
      "artifact_id",
      "content_hash",
      "artifact_manifest_hash",
      "receipt_id",
      "receipt_hash",
      "schema_ref",
    ],
    "artifact_binding",
    code,
  );
  if (artifactBinding.artifact_id !== classificationId) {
    fail(code, "classification artifact binding has the wrong identity");
  }
  requireString(artifactBinding.receipt_id, "artifact_binding.receipt_id", { code });
  requireString(artifactBinding.schema_ref, "artifact_binding.schema_ref", { code });
  for (const key of ["content_hash", "artifact_manifest_hash", "receipt_hash"]) {
    requireHash(artifactBinding[key], `artifact_binding.${key}`, code);
  }
  const ledgerBinding = exactKeys(
    readDataProperty(value, "ledger_binding"),
    ["run_id", "event_id", "sequence", "event_hash", "payload_hash"],
    "ledger_binding",
    code,
  );
  requireString(readDataProperty(ledgerBinding, "run_id", "ledger_binding", code), "run_id", {
    code,
  });
  if (!NUMBER_IS_SAFE_INTEGER(ledgerBinding.sequence) || ledgerBinding.sequence < 1) {
    fail(code, "classification ledger sequence is invalid");
  }
  requireHash(ledgerBinding.event_hash, "ledger_binding.event_hash", code);
  requireHash(ledgerBinding.payload_hash, "ledger_binding.payload_hash", code);
  try {
    assertClassificationArtifactIntegrity(classification, identityContext);
  } catch {
    fail(code, "classification replay projection contains an invalid F01 artifact");
  }
  return detached(value);
};

const bindOpenToClassification = (request, projection) => {
  const code = "FORGE_CLASSIFICATION_BINDING_MISMATCH";
  if (
    projection.classification.classification_id !== request.classification_id ||
    projection.classification.request_id !== request.request_id ||
    projection.identity_context.policy_bundle_hash !== request.policy_hash ||
    projection.ledger_binding.run_id !== request.run_spec_id ||
    projection.artifact_binding.artifact_id !== request.classification_id
  ) {
    fail(code, "OPEN input does not match the sealed F01 replay projection");
  }
};

const readClassificationProjection = (classificationPort, classificationId) => {
  let projection;
  try {
    projection = classificationPort.readClassificationReplayProjection(classificationId);
  } catch (error) {
    if (error instanceof ClassificationCommitterError) {
      fail("FORGE_CLASSIFICATION_REPLAY_REQUIRED", "F01 replay projection is unavailable");
    }
    fail("FORGE_CLASSIFICATION_REPLAY_REQUIRED", "F01 replay projection is unavailable");
  }
  return validateClassificationProjection(projection);
};

const buildPublishedProjection = ({
  state,
  phaseArtifactSets,
  supersededPhaseArtifactSets,
  event,
  classificationProjection,
}) => {
  try {
    assertForgeSessionStateIntegrity(state);
  } catch {
    fail("FORGE_SESSION_STATE_INTEGRITY_FAILED", "candidate ForgeSessionState is invalid");
  }
  const semantic = {
    state: detached(state),
    phase_artifact_sets: detached(phaseArtifactSets),
    superseded_phase_artifact_sets: detached(supersededPhaseArtifactSets),
    last_session_event_id: event.event_id,
    last_session_event_hash: event.event_hash,
    classification_projection_id: classificationProjection.projection_id,
    classification_projection_hash: classificationProjection.projection_hash,
  };
  return detached({ ...semantic, projection_hash: hashJson(semantic) });
};

const validateOutboxRecord = (record) => {
  const code = "FORGE_OUTBOX_INTEGRITY_FAILED";
  const envelope = validateOutboxEnvelope(record);
  if (envelope === null) return null;
  const value = envelope.value;
  const intentKeys = [
    "intent_version",
    "kind",
    "operation_id",
    "outbox_id",
    "session_id",
    "request_hash",
    "request",
    "expected_ledger_head",
    "event_input",
    "payload_artifact_id",
    "payload_receipt_id",
    "payload_bytes",
    "payload_content_hash",
    "artifact_metadata",
    "classification_projection",
    "admission",
    "candidate_state",
    "candidate_transition",
    "phase_artifact_sets",
    "superseded_phase_artifact_sets",
    "base_projection_hash",
    "intent_hash",
  ];
  const intent = exactKeys(value.intent, intentKeys, "outbox intent", code);
  if (
    intent.intent_version !== CONTRACT ||
    !new Set(["OPEN", "TRANSITION"]).has(intent.kind) ||
    intent.operation_id !== value.operation_id ||
    intent.outbox_id !== value.outbox_id ||
    intent.session_id !== value.session_id ||
    intent.request_hash !== value.request_hash ||
    intent.intent_hash !== hashJson(withoutKey(intent, "intent_hash"))
  ) {
    fail(code, "session outbox intent binding is invalid");
  }
  const eventInput = exactKeys(
    intent.event_input,
    [
      "event_id",
      "run_id",
      "event_type",
      "aggregate_type",
      "aggregate_id",
      "actor_id",
      "payload_artifact_id",
      "occurred_at",
      "schema_version",
    ],
    "intent.event_input",
    code,
  );
  requireString(eventInput.event_id, "intent.event_input.event_id", { code });
  requireString(eventInput.run_id, "intent.event_input.run_id", { code });
  requireTimestamp(eventInput.occurred_at, "intent.event_input.occurred_at", code);
  requireString(intent.payload_bytes, "intent.payload_bytes", { code });
  requireHash(intent.payload_content_hash, "intent.payload_content_hash", code);
  try {
    assertForgeSessionStateIntegrity(intent.candidate_state);
  } catch {
    fail(code, "session outbox candidate state is invalid");
  }
  const intentRequest = requirePlainRecord(intent.request, "intent.request", { code });
  let expectedHead;
  try {
    expectedHead = normalizeExpectedHead(intent.expected_ledger_head);
  } catch {
    fail(code, "session outbox expected ledger head is invalid");
  }
  const expectedRequestHash = requestHashFor(intent.kind, intentRequest, expectedHead);
  const expectedIdentity = operationIdentity(intent.kind, intent.session_id, expectedRequestHash);
  if (
    expectedRequestHash !== intent.request_hash ||
    expectedIdentity.operationId !== intent.operation_id ||
    expectedIdentity.outboxId !== intent.outbox_id ||
    expectedIdentity.eventId !== eventInput.event_id ||
    expectedIdentity.payloadArtifactId !== intent.payload_artifact_id ||
    expectedIdentity.payloadReceiptId !== intent.payload_receipt_id ||
    eventInput.aggregate_type !== EVENT_AGGREGATE_TYPE ||
    eventInput.aggregate_id !== intent.session_id ||
    eventInput.event_type !== EVENT_TYPES[intent.kind] ||
    eventInput.payload_artifact_id !== intent.payload_artifact_id ||
    eventInput.run_id !== intent.candidate_state.run_spec_id ||
    eventInput.schema_version !== EVENT_SCHEMA_VERSION ||
    intentRequest.session_id !== intent.session_id ||
    intent.candidate_state.session_id !== intent.session_id ||
    eventInput.actor_id !== intentRequest.actor?.actor_id ||
    intent.payload_content_hash !== hashBytes(Buffer.from(intent.payload_bytes, "utf8"))
  ) {
    fail(code, "session outbox deterministic identity is invalid");
  }
  validateClassificationProjection(intent.classification_projection);
  try {
    const expectedMetadata = artifactMetadataFor({
      identity: expectedIdentity,
      event: eventInput,
      actor: intentRequest.actor,
      classificationProjection: intent.classification_projection,
      admission: intent.admission,
      candidateState: intent.candidate_state,
    });
    if (!sameCanonical(expectedMetadata, intent.artifact_metadata)) {
      fail(code, "session outbox D03 metadata is not canonical");
    }
  } catch {
    fail(code, "session outbox D03 metadata is not canonical");
  }
  requireDenseArray(intent.phase_artifact_sets, "intent.phase_artifact_sets", code);
  requireDenseArray(
    intent.superseded_phase_artifact_sets,
    "intent.superseded_phase_artifact_sets",
    code,
  );
  if (intent.kind === "OPEN") {
    if (
      intent.admission !== null ||
      intent.candidate_transition !== null ||
      intent.base_projection_hash !== null
    ) {
      fail(code, "OPEN outbox contains transition-only state");
    }
  } else {
    requirePlainRecord(intent.admission, "intent.admission", { code });
    requirePlainRecord(intent.candidate_transition, "intent.candidate_transition", { code });
    requireHash(intent.base_projection_hash, "intent.base_projection_hash", code);
  }
  try {
    const payload = strictPayload(Buffer.from(intent.payload_bytes, "utf8"));
    validatePayloadIntent(payload, intent);
  } catch {
    fail(code, "session outbox payload does not bind its candidate projections");
  }
  if (value.state === "PUBLISHED") {
    const resolution = exactKeys(
      value.resolution,
      ["status", "artifact", "ledger", "projection_hash"],
      "published outbox resolution",
      code,
    );
    if (resolution.status !== "PUBLISHED") fail(code, "published resolution status is invalid");
    const artifact = exactKeys(
      resolution.artifact,
      ["artifact_id", "content_hash", "manifest_hash", "receipt_id", "receipt_hash"],
      "published artifact resolution",
      code,
    );
    for (const key of ["content_hash", "manifest_hash", "receipt_hash"]) {
      requireHash(artifact[key], `resolution.artifact.${key}`, code);
    }
    const ledger = exactKeys(
      resolution.ledger,
      ["append_status", "event", "head"],
      "published ledger resolution",
      code,
    );
    if (!new Set(["APPENDED", "EXISTING"]).has(ledger.append_status)) {
      fail(code, "published ledger resolution status is invalid");
    }
    const resolvedEvent = validateEventRecord(ledger.event);
    let head;
    try {
      head = normalizeExpectedHead(ledger.head);
    } catch {
      fail(code, "published ledger head is invalid");
    }
    if (
      artifact.artifact_id !== intent.payload_artifact_id ||
      artifact.receipt_id !== intent.payload_receipt_id ||
      artifact.content_hash !== intent.payload_content_hash ||
      resolvedEvent.event_id !== eventInput.event_id ||
      !sameHead(head, eventHead(resolvedEvent))
    ) {
      fail(code, "published resolution does not bind its intent");
    }
    requireHash(resolution.projection_hash, "resolution.projection_hash", code);
  } else if (value.state === "CONFLICTED") {
    const resolution = exactKeys(
      value.resolution,
      ["status", "code", "artifact", "ledger"],
      "conflicted outbox resolution",
      code,
    );
    if (resolution.status !== "CONFLICTED" || resolution.code !== "STALE_LEDGER_HEAD") {
      fail(code, "conflicted resolution status is invalid");
    }
    const artifact = exactKeys(
      resolution.artifact,
      ["artifact_id", "content_hash", "manifest_hash", "receipt_id", "receipt_hash"],
      "conflicted artifact resolution",
      code,
    );
    for (const key of ["content_hash", "manifest_hash", "receipt_hash"]) {
      requireHash(artifact[key], `resolution.artifact.${key}`, code);
    }
    const ledger = exactKeys(
      resolution.ledger,
      ["expected_head", "actual_head"],
      "conflicted ledger resolution",
      code,
    );
    let expectedHeadResolution;
    try {
      expectedHeadResolution = normalizeExpectedHead(ledger.expected_head);
      normalizeExpectedHead(ledger.actual_head);
    } catch {
      fail(code, "conflicted ledger head is invalid");
    }
    if (
      artifact.artifact_id !== intent.payload_artifact_id ||
      artifact.receipt_id !== intent.payload_receipt_id ||
      artifact.content_hash !== intent.payload_content_hash ||
      !sameHead(expectedHeadResolution, expectedHead)
    ) {
      fail(code, "conflicted resolution does not bind its intent");
    }
  }
  return envelope;
};

const requestBindingsFor = ({ sessionId, requestId, idempotencyKey }) => ({
  request: bindingIdentity("REQUEST", sessionId, requestId),
  idempotency: bindingIdentity("IDEMPOTENCY", sessionId, idempotencyKey),
});

const readExistingOperation = (store, bindings, identity, requestHash) => {
  const requestRecord = validateBindingRecord(
    store.readRevisionedRecord(OPERATION_BINDING_RECORD_VERSION, bindings.request.id),
    bindings.request.id,
  );
  const idempotencyRecord = validateBindingRecord(
    store.readRevisionedRecord(OPERATION_BINDING_RECORD_VERSION, bindings.idempotency.id),
    bindings.idempotency.id,
  );
  if (requestRecord === null && idempotencyRecord === null) return null;
  if (requestRecord !== null && idempotencyRecord === null) {
    fail("FORGE_REQUEST_CONFLICT", "request_id is already bound to another intent");
  }
  if (requestRecord === null && idempotencyRecord !== null) {
    fail("FORGE_IDEMPOTENCY_CONFLICT", "idempotency_key is already bound to another intent");
  }
  if (
    requestRecord.binding_kind !== "REQUEST" ||
    requestRecord.key_hash !== bindings.request.keyHash ||
    requestRecord.request_hash !== requestHash
  ) {
    fail("FORGE_REQUEST_CONFLICT", "request_id is already bound to another intent");
  }
  if (
    idempotencyRecord.binding_kind !== "IDEMPOTENCY" ||
    idempotencyRecord.key_hash !== bindings.idempotency.keyHash ||
    idempotencyRecord.request_hash !== requestHash
  ) {
    fail("FORGE_IDEMPOTENCY_CONFLICT", "idempotency_key is already bound to another intent");
  }
  if (
    requestRecord.operation_id !== identity.operationId ||
    idempotencyRecord.operation_id !== identity.operationId ||
    requestRecord.outbox_id !== identity.outboxId ||
    idempotencyRecord.outbox_id !== identity.outboxId
  ) {
    fail("FORGE_OPERATION_BINDING_INTEGRITY_FAILED", "operation bindings disagree");
  }
  return identity.outboxId;
};

const appendIndex = (store, outboxId) => {
  const record = validateIndexRecord(
    store.readRevisionedRecord(OUTBOX_INDEX_RECORD_VERSION, OUTBOX_INDEX_ID),
  );
  if (record === null) {
    store.createRevisionedRecord({
      recordType: OUTBOX_INDEX_RECORD_VERSION,
      recordId: OUTBOX_INDEX_ID,
      value: makeIndexRecord([outboxId]),
    });
    return;
  }
  if (record.value.outbox_ids.includes(outboxId)) {
    fail("FORGE_OUTBOX_INDEX_INTEGRITY_FAILED", "new outbox already appears in the global index");
  }
  const update = store.compareAndSwapRevision({
    recordType: OUTBOX_INDEX_RECORD_VERSION,
    recordId: OUTBOX_INDEX_ID,
    expectedRevision: record.revision,
    value: makeIndexRecord([...record.value.outbox_ids, outboxId]),
  });
  if (!update.ok) fail("FORGE_STATE_COMMIT_FAILED", "global outbox index CAS failed");
};

const storedOpenProjection = (store, sessionId) => {
  const index = validateIndexRecord(
    store.readRevisionedRecord(OUTBOX_INDEX_RECORD_VERSION, OUTBOX_INDEX_ID),
  );
  if (index === null) fail("FORGE_CLASSIFICATION_REPLAY_REQUIRED", "OPEN outbox is unavailable");
  const matches = [];
  for (const outboxId of index.value.outbox_ids) {
    const outbox = validateOutboxRecord(
      store.readRevisionedRecord(OUTBOX_RECORD_VERSION, outboxId),
    );
    if (
      outbox !== null &&
      outbox.value.session_id === sessionId &&
      outbox.value.state === "PUBLISHED" &&
      outbox.value.intent.kind === "OPEN"
    ) {
      matches.push(outbox.value.intent.classification_projection);
    }
  }
  if (matches.length !== 1) {
    fail("FORGE_CLASSIFICATION_REPLAY_REQUIRED", "session requires exactly one published OPEN projection");
  }
  return validateClassificationProjection(matches[0]);
};

const artifactMetadataFor = ({
  identity,
  event,
  actor,
  classificationProjection,
  admission,
  candidateState,
}) => {
  const inputArtifactIds = new Set([classificationProjection.artifact_binding.artifact_id]);
  if (admission !== null) {
    for (const artifactId of admission.artifact_retention) inputArtifactIds.add(artifactId);
  }
  return detached({
    artifact: {
      artifactId: identity.payloadArtifactId,
      artifactType: "forge_session_event_payload",
      confidentiality: "internal",
      createdAt: event.occurred_at,
      createdBy: actor.actor_id,
      encryption: { atRest: true, inTransit: true, keyRef: null },
      inputArtifactIds: [...inputArtifactIds].sort(),
      license: null,
      lineageEventIds: [],
      mediaType: "application/json",
      provenanceManifestId: `PROV-${identity.payloadArtifactId}`,
      retentionClass: "permanent",
    },
    receipt: {
      actionIntentId: identity.operationId,
      createdAt: event.occurred_at,
      createdBy: { actorId: actor.actor_id, actorType: actor.actor_type },
      receiptId: identity.payloadReceiptId,
      schemaRef: null,
      validationResults: [
        {
          check: "durable_forge_session_payload",
          status: "PASS",
          details: candidateState.state_hash,
        },
      ],
    },
  });
};

const makePayload = ({
  kind,
  identity,
  sessionId,
  requestHash,
  request,
  expectedHead,
  classificationProjection,
  admission,
  candidateState,
  candidateTransition,
  phaseArtifactSets,
  supersededPhaseArtifactSets,
}) => detached({
  payload_version: CONTRACT,
  kind,
  operation_id: identity.operationId,
  outbox_id: identity.outboxId,
  session_id: sessionId,
  request_hash: requestHash,
  request,
  expected_ledger_head: expectedHead,
  classification_projection: classificationProjection,
  admission,
  candidate_state: candidateState,
  candidate_transition: candidateTransition,
  phase_artifact_sets: phaseArtifactSets,
  superseded_phase_artifact_sets: supersededPhaseArtifactSets,
});

const makeIntent = ({
  kind,
  identity,
  sessionId,
  requestHash,
  request,
  expectedHead,
  event,
  payload,
  metadata,
  classificationProjection,
  admission,
  candidateState,
  candidateTransition,
  phaseArtifactSets,
  supersededPhaseArtifactSets,
  baseProjectionHash,
}) => {
  const payloadBytes = `${canonicalJson(payload)}\n`;
  const semantic = {
    intent_version: CONTRACT,
    kind,
    operation_id: identity.operationId,
    outbox_id: identity.outboxId,
    session_id: sessionId,
    request_hash: requestHash,
    request,
    expected_ledger_head: expectedHead,
    event_input: event,
    payload_artifact_id: identity.payloadArtifactId,
    payload_receipt_id: identity.payloadReceiptId,
    payload_bytes: payloadBytes,
    payload_content_hash: hashBytes(Buffer.from(payloadBytes, "utf8")),
    artifact_metadata: metadata,
    classification_projection: classificationProjection,
    admission,
    candidate_state: candidateState,
    candidate_transition: candidateTransition,
    phase_artifact_sets: phaseArtifactSets,
    superseded_phase_artifact_sets: supersededPhaseArtifactSets,
    base_projection_hash: baseProjectionHash,
  };
  return detached({ ...semantic, intent_hash: hashJson(semantic) });
};

const eventInputFor = ({ kind, identity, sessionId, runId, actorId, occurredAt }) => detached({
  event_id: identity.eventId,
  run_id: runId,
  event_type: EVENT_TYPES[kind],
  aggregate_type: EVENT_AGGREGATE_TYPE,
  aggregate_id: sessionId,
  actor_id: actorId,
  payload_artifact_id: identity.payloadArtifactId,
  occurred_at: occurredAt,
  schema_version: EVENT_SCHEMA_VERSION,
});

const translateKernelError = (error, fallbackCode, fallbackMessage) => {
  if (error instanceof DurableForgeSessionError) throw error;
  if (
    error instanceof ForgeFsmError ||
    error instanceof TransitionAdmissionError
  ) {
    fail(error.code, fallbackMessage);
  }
  if (error instanceof SQLiteStateStoreError) {
    fail("FORGE_STATE_STORE_FAILED", "D01 state operation failed");
  }
  fail(fallbackCode, fallbackMessage);
};

const stateTransaction = (stateStore, callback) => {
  try {
    return stateStore.transaction(callback);
  } catch (error) {
    translateKernelError(error, "FORGE_STATE_COMMIT_FAILED", "durable session state transaction failed");
  }
};

const readStateRecord = (stateStore, recordType, recordId) => {
  try {
    return stateStore.readRevisionedRecord(recordType, recordId);
  } catch (error) {
    if (error instanceof SQLiteStateStoreError) {
      fail("FORGE_STATE_STORE_FAILED", "D01 state read failed");
    }
    if (error instanceof DurableForgeSessionError) throw error;
    fail("FORGE_STATE_STORE_FAILED", "D01 state read failed");
  }
};

const validateD03ArtifactBinding = ({
  manifest: candidateManifest,
  receipt: candidateReceipt,
  bytes,
  metadata,
  expectedContentHash,
  code,
}) => {
  const manifest = exactKeys(
    candidateManifest,
    [
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
    ],
    "D03 manifest",
    code,
  );
  const receipt = exactKeys(
    candidateReceipt,
    [
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
    ],
    "D03 receipt",
    code,
  );
  const artifactMetadata = requirePlainRecord(metadata.artifact, "D03 artifact metadata", { code });
  const receiptMetadata = requirePlainRecord(metadata.receipt, "D03 receipt metadata", { code });
  const content = Buffer.from(bytes);
  const encryption = exactKeys(
    manifest.encryption,
    ["at_rest", "in_transit", "key_ref"],
    "D03 manifest encryption",
    code,
  );
  const creator = exactKeys(
    receipt.created_by,
    ["actor_id", "actor_type"],
    "D03 receipt creator",
    code,
  );
  if (
    manifest.artifact_id !== artifactMetadata.artifactId ||
    manifest.artifact_type !== artifactMetadata.artifactType ||
    manifest.byte_size !== content.length ||
    manifest.confidentiality !== artifactMetadata.confidentiality ||
    manifest.content_hash !== expectedContentHash ||
    manifest.created_at !== artifactMetadata.createdAt ||
    manifest.created_by !== artifactMetadata.createdBy ||
    encryption.at_rest !== artifactMetadata.encryption.atRest ||
    encryption.in_transit !== artifactMetadata.encryption.inTransit ||
    encryption.key_ref !== artifactMetadata.encryption.keyRef ||
    !sameCanonical(manifest.input_artifact_ids, artifactMetadata.inputArtifactIds) ||
    manifest.integrity_status !== "verified" ||
    manifest.license !== artifactMetadata.license ||
    !sameCanonical(manifest.lineage_event_ids, artifactMetadata.lineageEventIds) ||
    manifest.media_type !== artifactMetadata.mediaType ||
    manifest.provenance_manifest_id !== artifactMetadata.provenanceManifestId ||
    manifest.retention_class !== artifactMetadata.retentionClass
  ) {
    fail(code, "D03 manifest differs from the immutable artifact intent");
  }
  if (
    receipt.action_intent_id !== receiptMetadata.actionIntentId ||
    receipt.artifact_id !== manifest.artifact_id ||
    receipt.byte_size !== manifest.byte_size ||
    receipt.content_hash !== manifest.content_hash ||
    receipt.created_at !== receiptMetadata.createdAt ||
    creator.actor_id !== receiptMetadata.createdBy.actorId ||
    creator.actor_type !== receiptMetadata.createdBy.actorType ||
    receipt.locator !== manifest.storage_uri ||
    receipt.media_type !== manifest.media_type ||
    receipt.receipt_id !== receiptMetadata.receiptId ||
    receipt.schema_ref !== receiptMetadata.schemaRef
  ) {
    fail(code, "D03 receipt differs from the immutable receipt intent");
  }
  const validationRows = requireDenseArray(
    receipt.validation_results,
    "D03 receipt.validation_results",
    code,
  );
  if (validationRows.length !== receiptMetadata.validationResults.length + 2) {
    fail(code, "D03 receipt validation rows differ from the immutable receipt intent");
  }
  const contentRow = exactKeys(
    validationRows[0],
    ["check", "status", "details"],
    "D03 content validation row",
    code,
  );
  const manifestRow = exactKeys(
    validationRows[1],
    ["check", "status", "details"],
    "D03 manifest validation row",
    code,
  );
  if (
    contentRow.check !== "content_sha256" ||
    contentRow.status !== "PASS" ||
    contentRow.details !== expectedContentHash ||
    manifestRow.check !== "artifact_manifest_sha256" ||
    manifestRow.status !== "PASS" ||
    !sameCanonical(validationRows.slice(2), receiptMetadata.validationResults)
  ) {
    fail(code, "D03 reserved or caller validation rows are inconsistent");
  }
  const manifestHash = requireHash(
    manifestRow.details,
    "D03 artifact_manifest_sha256 details",
    code,
  );
  const receiptHash = requireHash(receipt.receipt_hash, "D03 receipt_hash", code);
  return detached({
    artifact_id: manifest.artifact_id,
    content_hash: manifest.content_hash,
    manifest_hash: manifestHash,
    receipt_id: receipt.receipt_id,
    receipt_hash: receiptHash,
  });
};

const sameHead = (left, right) =>
  left.event_count === right.event_count &&
  left.tail_event_id === right.tail_event_id &&
  left.tail_event_hash === right.tail_event_hash;

const eventHead = (event) => detached({
  event_count: event.sequence,
  tail_event_id: event.event_id,
  tail_event_hash: event.event_hash,
});

const assertAppendEvent = (event, intent, contentHash) => {
  if (event === null || typeof event !== "object" || ARRAY_IS_ARRAY(event) || IS_PROXY(event)) {
    fail("FORGE_RECONCILIATION_REQUIRED", "E01 returned a malformed immutable event");
  }
  const input = intent.event_input;
  for (const key of Object.keys(input)) {
    if (event[key] !== input[key]) {
      fail("FORGE_RECONCILIATION_REQUIRED", "E01 returned a different immutable event");
    }
  }
  let computedEventHash;
  try {
    computedEventHash = computeEventHash(event);
  } catch {
    fail("FORGE_RECONCILIATION_REQUIRED", "E01 returned a malformed immutable event");
  }
  if (
    event.payload_hash !== contentHash ||
    event.sequence !== intent.expected_ledger_head.event_count + 1 ||
    event.previous_event_hash !== intent.expected_ledger_head.tail_event_hash ||
    event.event_hash !== computedEventHash
  ) {
    fail("FORGE_RECONCILIATION_REQUIRED", "E01 event binding is inconsistent");
  }
};

const sameTerminalResolution = (left, right, terminalState) => {
  if (sameCanonical(left, right)) return true;
  if (terminalState === "CONFLICTED") {
    return (
      left.status === "CONFLICTED" &&
      right.status === "CONFLICTED" &&
      left.code === right.code &&
      sameCanonical(left.artifact, right.artifact) &&
      sameCanonical(left.ledger.expected_head, right.ledger.expected_head)
    );
  }
  if (terminalState !== "PUBLISHED") return false;
  return (
    left.status === "PUBLISHED" &&
    right.status === "PUBLISHED" &&
    sameCanonical(left.artifact, right.artifact) &&
    sameCanonical(left.ledger.event, right.ledger.event) &&
    sameCanonical(left.ledger.head, right.ledger.head) &&
    left.projection_hash === right.projection_hash
  );
};

const attachTerminal = (stateStore, outboxId, terminalState, resolution) =>
  stateTransaction(stateStore, (store) => {
    const outbox = validateOutboxRecord(
      store.readRevisionedRecord(OUTBOX_RECORD_VERSION, outboxId),
    );
    if (outbox === null) fail("FORGE_OUTBOX_INTEGRITY_FAILED", "session outbox is missing");
    if (outbox.value.state !== "PENDING") {
      if (
        outbox.value.state !== terminalState ||
        !sameTerminalResolution(outbox.value.resolution, resolution, terminalState)
      ) {
        fail("FORGE_OUTBOX_TERMINAL_CONFLICT", "terminal outbox state cannot change");
      }
      return outbox.value;
    }
    const intent = outbox.value.intent;
    const session = validateSessionRecord(
      store.readRevisionedRecord(SESSION_RECORD_VERSION, intent.session_id),
    );
    if (
      session === null ||
      session.value.pending === null ||
      session.value.pending.operation_id !== intent.operation_id ||
      session.value.pending.outbox_id !== intent.outbox_id ||
      session.value.pending.candidate_state_hash !== intent.candidate_state.state_hash
    ) {
      fail("FORGE_SESSION_STATE_INTEGRITY_FAILED", "session pending pointer is inconsistent");
    }
    const currentProjectionHash = session.value.published?.projection_hash ?? null;
    if (currentProjectionHash !== intent.base_projection_hash) {
      fail("FORGE_SESSION_STATE_INTEGRITY_FAILED", "published session changed under pending intent");
    }
    let published = session.value.published;
    if (terminalState === "PUBLISHED") {
      published = buildPublishedProjection({
        state: intent.candidate_state,
        phaseArtifactSets: intent.phase_artifact_sets,
        supersededPhaseArtifactSets: intent.superseded_phase_artifact_sets,
        event: resolution.ledger.event,
        classificationProjection: intent.classification_projection,
      });
      if (published.projection_hash !== resolution.projection_hash) {
        fail("FORGE_SESSION_STATE_INTEGRITY_FAILED", "published projection resolution is inconsistent");
      }
    }
    const sessionUpdate = store.compareAndSwapRevision({
      recordType: SESSION_RECORD_VERSION,
      recordId: intent.session_id,
      expectedRevision: session.revision,
      value: makeSessionRecord(intent.session_id, published, null),
    });
    if (!sessionUpdate.ok) fail("FORGE_STATE_COMMIT_FAILED", "session publish CAS failed");
    const outboxUpdate = store.compareAndSwapRevision({
      recordType: OUTBOX_RECORD_VERSION,
      recordId: outboxId,
      expectedRevision: outbox.revision,
      value: makeOutboxRecord({
        operationId: intent.operation_id,
        outboxId,
        sessionId: intent.session_id,
        requestHash: intent.request_hash,
        state: terminalState,
        intent,
        resolution,
      }),
    });
    if (!outboxUpdate.ok) fail("FORGE_STATE_COMMIT_FAILED", "outbox terminal CAS failed");
    return validateOutboxRecord(outboxUpdate.record).value;
  });

const publishOutbox = ({ stateStore, artifactStore, ledger }, outboxId) => {
  const snapshot = validateOutboxRecord(
    readStateRecord(stateStore, OUTBOX_RECORD_VERSION, outboxId),
  );
  if (snapshot === null) fail("FORGE_OUTBOX_INTEGRITY_FAILED", "session outbox is missing");
  if (snapshot.value.state !== "PENDING") {
    return detached({ status: snapshot.value.state, outbox: snapshot.value });
  }
  const intent = snapshot.value.intent;
  let registration;
  try {
    registration = artifactStore.putArtifact(
      Buffer.from(intent.payload_bytes, "utf8"),
      intent.artifact_metadata,
    );
  } catch (error) {
    if (error instanceof ArtifactStoreError) {
      fail("FORGE_RECONCILIATION_REQUIRED", "D03 payload publication requires reconciliation");
    }
    fail("FORGE_RECONCILIATION_REQUIRED", "D03 payload publication requires reconciliation");
  }
  let artifact;
  try {
    const returned = exactKeys(
      registration,
      ["artifactStatus", "manifest", "objectStatus", "receipt", "receiptStatus", "status"],
      "D03 registration",
      "FORGE_RECONCILIATION_REQUIRED",
    );
    artifact = validateD03ArtifactBinding({
      manifest: returned.manifest,
      receipt: returned.receipt,
      bytes: Buffer.from(intent.payload_bytes, "utf8"),
      metadata: intent.artifact_metadata,
      expectedContentHash: intent.payload_content_hash,
      code: "FORGE_RECONCILIATION_REQUIRED",
    });
    if (
      artifact.artifact_id !== intent.payload_artifact_id ||
      artifact.receipt_id !== intent.payload_receipt_id
    ) {
      fail("FORGE_RECONCILIATION_REQUIRED", "D03 returned a different immutable payload binding");
    }
  } catch (error) {
    if (error instanceof DurableForgeSessionError) throw error;
    fail("FORGE_RECONCILIATION_REQUIRED", "D03 returned a malformed payload binding");
  }
  let append;
  try {
    append = ledger.appendConditional(intent.event_input, {
      expectedHead: intent.expected_ledger_head,
    });
  } catch (error) {
    if (error instanceof NoeticLedgerError) {
      fail("FORGE_RECONCILIATION_REQUIRED", "E01 event publication requires reconciliation");
    }
    fail("FORGE_RECONCILIATION_REQUIRED", "E01 event publication requires reconciliation");
  }
  if (append?.status === "STALE_LEDGER_HEAD") {
    let actualHead;
    try {
      actualHead = normalizeExpectedHead(append.actual_head);
    } catch {
      fail("FORGE_RECONCILIATION_REQUIRED", "E01 returned a malformed stale-head result");
    }
    const resolution = detached({
      status: "CONFLICTED",
      code: "STALE_LEDGER_HEAD",
      artifact,
      ledger: {
        expected_head: intent.expected_ledger_head,
        actual_head: actualHead,
      },
    });
    const terminal = attachTerminal(stateStore, outboxId, "CONFLICTED", resolution);
    return detached({ status: "CONFLICTED", outbox: terminal });
  }
  if (
    !new Set(["APPENDED", "EXISTING"]).has(append?.status) ||
    append.event === null ||
    typeof append.event !== "object"
  ) {
    fail("FORGE_RECONCILIATION_REQUIRED", "E01 returned an unknown publication result");
  }
  assertAppendEvent(append.event, intent, artifact.content_hash);
  const projection = buildPublishedProjection({
    state: intent.candidate_state,
    phaseArtifactSets: intent.phase_artifact_sets,
    supersededPhaseArtifactSets: intent.superseded_phase_artifact_sets,
    event: append.event,
    classificationProjection: intent.classification_projection,
  });
  const resolution = detached({
    status: "PUBLISHED",
    artifact,
    ledger: {
      append_status: append.status,
      event: append.event,
      head: eventHead(append.event),
    },
    projection_hash: projection.projection_hash,
  });
  const terminal = attachTerminal(stateStore, outboxId, "PUBLISHED", resolution);
  return detached({ status: "PUBLISHED", outbox: terminal });
};

const publishedAfterOperation = (dependencies, outboxId, { exactOperation = false } = {}) => {
  const before = validateOutboxRecord(
    readStateRecord(dependencies.stateStore, OUTBOX_RECORD_VERSION, outboxId),
  );
  if (before === null) fail("FORGE_OUTBOX_INTEGRITY_FAILED", "session outbox is missing");
  if (before.value.state === "CONFLICTED") {
    fail("FORGE_OPERATION_CONFLICTED", "a conflicted intent cannot be reused", {
      session_id: before.value.session_id,
      outbox_id: before.value.outbox_id,
    });
  }
  const publication = publishOutbox(dependencies, outboxId);
  if (publication.status === "CONFLICTED") {
    fail("STALE_LEDGER_HEAD", "expected ledger head is stale", {
      session_id: publication.outbox.session_id,
      outbox_id: publication.outbox.outbox_id,
    });
  }
  const outbox = publication.outbox;
  if (outbox.state !== "PUBLISHED" || outbox.resolution?.status !== "PUBLISHED") {
    fail("FORGE_OUTBOX_INTEGRITY_FAILED", "operation did not resolve to a published outbox");
  }
  if (!exactOperation) {
    const session = validateSessionRecord(
      readStateRecord(dependencies.stateStore, SESSION_RECORD_VERSION, outbox.session_id),
    );
    if (session === null || session.value.published === null) {
      fail("FORGE_SESSION_STATE_INTEGRITY_FAILED", "published session projection is missing");
    }
    return detached(session.value.published);
  }
  const projection = buildPublishedProjection({
    state: outbox.intent.candidate_state,
    phaseArtifactSets: outbox.intent.phase_artifact_sets,
    supersededPhaseArtifactSets: outbox.intent.superseded_phase_artifact_sets,
    event: outbox.resolution.ledger.event,
    classificationProjection: outbox.intent.classification_projection,
  });
  if (projection.projection_hash !== outbox.resolution.projection_hash) {
    fail("FORGE_SESSION_STATE_INTEGRITY_FAILED", "operation projection resolution changed");
  }
  return detached(projection);
};

const transitionPreparationResult = (outbox, status) => {
  const value = validateOutboxRecord(outbox);
  if (value === null || value.value.intent.kind !== "TRANSITION") {
    fail("FORGE_OUTBOX_INTEGRITY_FAILED", "transition preparation outbox is unavailable");
  }
  const intent = value.value.intent;
  return detached({
    status,
    operation_id: intent.operation_id,
    outbox_id: intent.outbox_id,
    session_id: intent.session_id,
    request_hash: intent.request_hash,
    payload_artifact_id: intent.payload_artifact_id,
    candidate_state_hash: intent.candidate_state.state_hash,
    expected_ledger_head: intent.expected_ledger_head,
    expected_revision: intent.request.expected_revision,
    new_revision: intent.candidate_state.revision,
  });
};

const openPreparationResult = (outbox, status) => {
  const value = validateOutboxRecord(outbox);
  if (value === null || value.value.intent.kind !== "OPEN") {
    fail("FORGE_OUTBOX_INTEGRITY_FAILED", "OPEN preparation outbox is unavailable");
  }
  const intent = value.value.intent;
  return detached({
    status,
    operation_id: intent.operation_id,
    outbox_id: intent.outbox_id,
    session_id: intent.session_id,
    request_hash: intent.request_hash,
    payload_artifact_id: intent.payload_artifact_id,
    candidate_state_hash: intent.candidate_state.state_hash,
    expected_ledger_head: intent.expected_ledger_head,
    expected_revision: null,
    new_revision: intent.candidate_state.revision,
  });
};

const createOperationRecords = ({
  store,
  bindings,
  identity,
  sessionId,
  requestHash,
  intent,
  existingSession,
}) => {
  const requestBinding = makeBinding({
    bindingKind: "REQUEST",
    bindingId: bindings.request.id,
    sessionId,
    keyHash: bindings.request.keyHash,
    operationId: identity.operationId,
    requestHash,
    outboxId: identity.outboxId,
  });
  const idempotencyBinding = makeBinding({
    bindingKind: "IDEMPOTENCY",
    bindingId: bindings.idempotency.id,
    sessionId,
    keyHash: bindings.idempotency.keyHash,
    operationId: identity.operationId,
    requestHash,
    outboxId: identity.outboxId,
  });
  store.createRevisionedRecord({
    recordType: OPERATION_BINDING_RECORD_VERSION,
    recordId: bindings.request.id,
    value: requestBinding,
  });
  store.createRevisionedRecord({
    recordType: OPERATION_BINDING_RECORD_VERSION,
    recordId: bindings.idempotency.id,
    value: idempotencyBinding,
  });
  store.createRevisionedRecord({
    recordType: OUTBOX_RECORD_VERSION,
    recordId: identity.outboxId,
    value: makeOutboxRecord({
      operationId: identity.operationId,
      outboxId: identity.outboxId,
      sessionId,
      requestHash,
      state: "PENDING",
      intent,
      resolution: null,
    }),
  });
  appendIndex(store, identity.outboxId);
  const pending = {
    operation_id: identity.operationId,
    outbox_id: identity.outboxId,
    candidate_state_hash: intent.candidate_state.state_hash,
  };
  if (existingSession === null) {
    store.createRevisionedRecord({
      recordType: SESSION_RECORD_VERSION,
      recordId: sessionId,
      value: makeSessionRecord(sessionId, null, pending),
    });
  } else {
    const update = store.compareAndSwapRevision({
      recordType: SESSION_RECORD_VERSION,
      recordId: sessionId,
      expectedRevision: existingSession.revision,
      value: makeSessionRecord(sessionId, existingSession.value.published, pending),
    });
    if (!update.ok) fail("FORGE_STATE_COMMIT_FAILED", "session pending CAS failed");
  }
};

const createOpenIntent = ({ request, expectedHead, requestHash, identity, projection, occurredAt }) => {
  const state = sealForgeSessionState({
    session_id: request.session_id,
    workspace_id: request.workspace_id,
    revision: 0,
    phase: "IDLE",
    work_class: projection.classification.work_class,
    status: "ACTIVE",
    run_spec_id: request.run_spec_id,
    hypothesis_revision_ids: [],
    artifact_ids: [],
    open_blockers: [],
    phase_history: [],
    policy_hash: request.policy_hash,
    corpus_snapshot_hash: request.corpus_snapshot_hash,
    updated_at: request.requested_at,
  });
  const event = eventInputFor({
    kind: "OPEN",
    identity,
    sessionId: request.session_id,
    runId: request.run_spec_id,
    actorId: request.actor.actor_id,
    occurredAt,
  });
  const payload = makePayload({
    kind: "OPEN",
    identity,
    sessionId: request.session_id,
    requestHash,
    request,
    expectedHead,
    classificationProjection: projection,
    admission: null,
    candidateState: state,
    candidateTransition: null,
    phaseArtifactSets: [],
    supersededPhaseArtifactSets: [],
  });
  const metadata = artifactMetadataFor({
    identity,
    event,
    actor: request.actor,
    classificationProjection: projection,
    admission: null,
    candidateState: state,
  });
  return makeIntent({
    kind: "OPEN",
    identity,
    sessionId: request.session_id,
    requestHash,
    request,
    expectedHead,
    event,
    payload,
    metadata,
    classificationProjection: projection,
    admission: null,
    candidateState: state,
    candidateTransition: null,
    phaseArtifactSets: [],
    supersededPhaseArtifactSets: [],
    baseProjectionHash: null,
  });
};

const compareCanonicalText = (left, right) => (left < right ? -1 : left > right ? 1 : 0);

const phaseArtifactSetSort = (left, right) => {
  const phaseDelta = FORGE_PHASES.indexOf(left.phase) - FORGE_PHASES.indexOf(right.phase);
  if (phaseDelta !== 0) return phaseDelta;
  return compareCanonicalText(left.set_id, right.set_id);
};

const appendAdmittedPhaseArtifactSet = (existingPhaseSets, admittedPhaseSet, admission) => {
  const code = "FORGE_PHASE_ARTIFACT_SET_IDENTITY_MISMATCH";
  const existing = requireDenseArray(existingPhaseSets, "phase_artifact_sets", code);
  const byId = new Map();
  const byHash = new Map();
  for (let index = 0; index < existing.length; index += 1) {
    const phaseSet = requirePlainRecord(existing[index], `phase_artifact_sets[${index}]`, { code });
    const setId = requireString(phaseSet.set_id, `phase_artifact_sets[${index}].set_id`, { code });
    const setHash = requireHash(phaseSet.set_hash, `phase_artifact_sets[${index}].set_hash`, code);
    if (
      byId.has(setId) ||
      byHash.has(setHash) ||
      !FORGE_PHASES.includes(phaseSet.phase)
    ) {
      fail(code, "phase artifact set projection contains a duplicate or invalid identity");
    }
    byId.set(setId, phaseSet);
    byHash.set(setHash, phaseSet);
  }

  if (admittedPhaseSet === null) {
    if (admission.phase_artifact_set_id !== null || admission.phase_artifact_set_hash !== null) {
      fail(code, "F03 admission contains an unreturned phase artifact set binding");
    }
    return detached([...existing].sort(phaseArtifactSetSort));
  }

  const admitted = requirePlainRecord(admittedPhaseSet, "F03 phase_artifact_set", { code });
  const admittedId = requireString(admitted.set_id, "F03 phase_artifact_set.set_id", { code });
  const admittedHash = requireHash(admitted.set_hash, "F03 phase_artifact_set.set_hash", code);
  if (
    admission.phase_artifact_set_id !== admittedId ||
    admission.phase_artifact_set_hash !== admittedHash ||
    !FORGE_PHASES.includes(admitted.phase)
  ) {
    fail(code, "F03 phase artifact set does not match its admission binding");
  }
  const sameId = byId.get(admittedId);
  const sameHash = byHash.get(admittedHash);
  if (sameId !== undefined || sameHash !== undefined) {
    if (sameId !== sameHash || !sameCanonical(sameId, admitted)) {
      fail(code, "phase artifact set identity or hash was reused with different content");
    }
    return detached([...existing].sort(phaseArtifactSetSort));
  }
  return detached([...existing, admitted].sort(phaseArtifactSetSort));
};

const bindAdmissionClassification = ({ admitted, admission, request, projection }) => {
  const code = "FORGE_CLASSIFICATION_BINDING_MISMATCH";
  if (request.from_phase !== "IDLE") {
    if (
      admitted.idle_classification !== null ||
      admission.idle_classification_id !== null ||
      admission.idle_classification_hash !== null
    ) {
      fail(code, "non-IDLE transition cannot carry an idle classification");
    }
    return;
  }

  const expectedClassification = projection.classification;
  const expectedArtifact = projection.artifact_binding;
  const idleClassification = requirePlainRecord(
    admitted.idle_classification,
    "F03 idle_classification",
    { code },
  );
  const idleClassificationId = requireString(
    readDataProperty(idleClassification, "classification_id", "F03 idle_classification", code),
    "F03 idle_classification.classification_id",
    { code },
  );
  const idleClassificationHash = requireHash(
    readDataProperty(idleClassification, "classification_hash", "F03 idle_classification", code),
    "F03 idle_classification.classification_hash",
    code,
  );
  if (
    idleClassificationId !== expectedClassification.classification_id ||
    idleClassificationHash !== expectedClassification.classification_hash ||
    admission.idle_classification_id !== expectedClassification.classification_id ||
    admission.idle_classification_hash !== expectedClassification.classification_hash
  ) {
    fail(code, "IDLE transition classification differs from the stored OPEN projection");
  }

  const receiptBindings = requireDenseArray(
    admission.receipt_bindings,
    "admission.receipt_bindings",
    code,
  );
  const classificationBindings = receiptBindings.filter(
    (binding) => binding?.schema_ref === expectedArtifact.schema_ref,
  );
  if (classificationBindings.length !== 1) {
    fail(code, "IDLE transition requires the exact stored classification receipt binding");
  }
  const binding = exactKeys(
    classificationBindings[0],
    ["receipt_id", "receipt_hash", "artifact_id", "content_hash", "schema_ref"],
    "classification receipt binding",
    code,
  );
  if (
    binding.artifact_id !== expectedArtifact.artifact_id ||
    binding.content_hash !== expectedArtifact.content_hash ||
    binding.receipt_id !== expectedArtifact.receipt_id ||
    binding.receipt_hash !== expectedArtifact.receipt_hash ||
    binding.schema_ref !== expectedArtifact.schema_ref
  ) {
    fail(code, "IDLE transition classification receipt differs from the stored OPEN projection");
  }
};

const admitAndReduceTransition = ({
  currentState,
  transitionRequest,
  artifactStore,
  projection,
  phaseArtifactSets,
  event,
}) => {
  const admitted = admitDurableForgeTransition({
    current_state: currentState,
    transition_request: transitionRequest,
    artifact_store: artifactStore,
  });
  const admission = requirePlainRecord(admitted.admission, "F03 admission");
  bindAdmissionClassification({ admitted, admission, request: transitionRequest, projection });
  const admittedPhaseSets = appendAdmittedPhaseArtifactSet(
    phaseArtifactSets,
    admitted.phase_artifact_set,
    admission,
  );
  const reduced = reduceAdmittedForgeTransition({
    current_state: currentState,
    transition_request: transitionRequest,
    classification: projection.classification,
    classification_identity_context: projection.identity_context,
    phase_artifact_sets: admittedPhaseSets,
    event,
    admission,
  });
  return detached({ admitted, reduced });
};

const createTransitionIntent = ({
  request,
  expectedHead,
  requestHash,
  identity,
  published,
  projection,
  artifactStore,
  occurredAt,
}) => {
  const event = eventInputFor({
    kind: "TRANSITION",
    identity,
    sessionId: request.session_id,
    runId: published.state.run_spec_id,
    actorId: request.actor.actor_id,
    occurredAt,
  });
  let transitionResult;
  try {
    transitionResult = admitAndReduceTransition({
      currentState: published.state,
      transitionRequest: request,
      artifactStore,
      projection,
      phaseArtifactSets: published.phase_artifact_sets,
      event: { event_id: event.event_id, occurred_at: event.occurred_at },
    });
  } catch (error) {
    translateKernelError(
      error,
      "FORGE_TRANSITION_REDUCTION_FAILED",
      "durable transition admission or reduction failed",
    );
  }
  const { admitted, reduced } = transitionResult;
  const cumulativeSuperseded = [
    ...published.superseded_phase_artifact_sets,
    ...reduced.superseded_phase_artifact_sets,
  ];
  const payload = makePayload({
    kind: "TRANSITION",
    identity,
    sessionId: request.session_id,
    requestHash,
    request,
    expectedHead,
    classificationProjection: projection,
    admission: admitted.admission,
    candidateState: reduced.state,
    candidateTransition: reduced.transition,
    phaseArtifactSets: reduced.phase_artifact_sets,
    supersededPhaseArtifactSets: cumulativeSuperseded,
  });
  const metadata = artifactMetadataFor({
    identity,
    event,
    actor: request.actor,
    classificationProjection: projection,
    admission: admitted.admission,
    candidateState: reduced.state,
  });
  return makeIntent({
    kind: "TRANSITION",
    identity,
    sessionId: request.session_id,
    requestHash,
    request,
    expectedHead,
    event,
    payload,
    metadata,
    classificationProjection: projection,
    admission: admitted.admission,
    candidateState: reduced.state,
    candidateTransition: reduced.transition,
    phaseArtifactSets: reduced.phase_artifact_sets,
    supersededPhaseArtifactSets: cumulativeSuperseded,
    baseProjectionHash: published.projection_hash,
  });
};

const strictPayload = (bytes) => {
  if (!Buffer.isBuffer(bytes) && !(bytes instanceof Uint8Array)) {
    fail("FORGE_REPLAY_INTEGRITY_FAILED", "D03 payload bytes are unavailable");
  }
  const content = Buffer.from(bytes);
  const text = content.toString("utf8");
  if (!Buffer.from(text, "utf8").equals(content) || !text.endsWith("\n")) {
    fail("FORGE_REPLAY_INTEGRITY_FAILED", "D03 payload is not canonical UTF-8 JSON");
  }
  let payload;
  try {
    payload = JSON.parse(text.slice(0, -1));
  } catch {
    fail("FORGE_REPLAY_INTEGRITY_FAILED", "D03 payload is malformed JSON");
  }
  if (`${canonicalJson(payload)}\n` !== text) {
    fail("FORGE_REPLAY_INTEGRITY_FAILED", "D03 payload is not compact canonical JSON");
  }
  return detached(payload);
};

const validateReplayArtifact = (artifactStore, outbox, event) => {
  const intent = outbox.intent;
  let resolved;
  try {
    resolved = artifactStore.resolveReceipt(intent.payload_receipt_id);
  } catch {
    fail("FORGE_REPLAY_INTEGRITY_FAILED", "D03 replay evidence is unavailable");
  }
  let evidence;
  let artifact;
  try {
    evidence = exactKeys(
      resolved,
      ["artifactId", "bytes", "contentHash", "createdBy", "manifest", "receipt", "schemaRef"],
      "D03 resolved receipt",
      "FORGE_REPLAY_INTEGRITY_FAILED",
    );
    artifact = validateD03ArtifactBinding({
      manifest: evidence.manifest,
      receipt: evidence.receipt,
      bytes: evidence.bytes,
      metadata: intent.artifact_metadata,
      expectedContentHash: intent.payload_content_hash,
      code: "FORGE_REPLAY_INTEGRITY_FAILED",
    });
  } catch (error) {
    if (error instanceof DurableForgeSessionError) throw error;
    fail("FORGE_REPLAY_INTEGRITY_FAILED", "D03 resolved receipt is malformed");
  }
  const payload = strictPayload(evidence.bytes);
  if (
    !Buffer.from(evidence.bytes).equals(Buffer.from(intent.payload_bytes, "utf8")) ||
    evidence.artifactId !== artifact.artifact_id ||
    evidence.contentHash !== artifact.content_hash ||
    !sameCanonical(evidence.createdBy, evidence.receipt.created_by) ||
    evidence.schemaRef !== evidence.receipt.schema_ref ||
    artifact.artifact_id !== intent.payload_artifact_id ||
    artifact.receipt_id !== intent.payload_receipt_id ||
    event.payload_hash !== artifact.content_hash ||
    !sameCanonical(outbox.resolution.artifact, artifact)
  ) {
    fail("FORGE_REPLAY_INTEGRITY_FAILED", "D03 payload provenance does not match the outbox");
  }
  return payload;
};

const validateEventRecord = (event) => {
  const code = "FORGE_REPLAY_INTEGRITY_FAILED";
  const keys = [
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
    "occurred_at",
    "schema_version",
    "event_hash",
  ];
  const value = exactKeys(event, keys, "E01 EventRecord", code);
  if (!NUMBER_IS_SAFE_INTEGER(value.sequence) || value.sequence < 1) {
    fail(code, "E01 sequence is invalid");
  }
  requireHash(value.payload_hash, "event.payload_hash", code);
  if (value.previous_event_hash !== null) requireHash(value.previous_event_hash, "previous_event_hash", code);
  requireHash(value.event_hash, "event.event_hash", code);
  let expectedEventHash;
  try {
    expectedEventHash = computeEventHash(value);
  } catch {
    fail(code, "E01 event hash input is malformed");
  }
  if (value.event_hash !== expectedEventHash) fail(code, "E01 event hash is invalid");
  return detached(value);
};

const findEventOutbox = (stateStore, index, event) => {
  const matches = [];
  for (const outboxId of index.value.outbox_ids) {
    const record = validateOutboxRecord(
      readStateRecord(stateStore, OUTBOX_RECORD_VERSION, outboxId),
    );
    if (record?.value.intent.event_input.event_id === event.event_id) matches.push(record.value);
  }
  if (matches.length !== 1 || matches[0].state !== "PUBLISHED") {
    fail("FORGE_REPLAY_INTEGRITY_FAILED", "E01 event requires exactly one published outbox");
  }
  return matches[0];
};

const validateReplayEventBinding = (event, outbox, allEvents) => {
  const intent = outbox.intent;
  for (const key of Object.keys(intent.event_input)) {
    if (event[key] !== intent.event_input[key]) {
      fail("FORGE_REPLAY_INTEGRITY_FAILED", "E01 event differs from its immutable intent");
    }
  }
  const predecessor = event.sequence === 1 ? null : allEvents[event.sequence - 2];
  const predecessorHead = {
    event_count: event.sequence - 1,
    tail_event_id: predecessor?.event_id ?? null,
    tail_event_hash: predecessor?.event_hash ?? null,
  };
  if (
    !sameHead(predecessorHead, intent.expected_ledger_head) ||
    !sameCanonical(outbox.resolution.ledger.event, event) ||
    !sameHead(outbox.resolution.ledger.head, eventHead(event))
  ) {
    fail("FORGE_REPLAY_INTEGRITY_FAILED", "E01 predecessor or resolution binding is invalid");
  }
};

const validatePayloadIntent = (payload, intent) => {
  const expected = makePayload({
    kind: intent.kind,
    identity: {
      operationId: intent.operation_id,
      outboxId: intent.outbox_id,
    },
    sessionId: intent.session_id,
    requestHash: intent.request_hash,
    request: intent.request,
    expectedHead: intent.expected_ledger_head,
    classificationProjection: intent.classification_projection,
    admission: intent.admission,
    candidateState: intent.candidate_state,
    candidateTransition: intent.candidate_transition,
    phaseArtifactSets: intent.phase_artifact_sets,
    supersededPhaseArtifactSets: intent.superseded_phase_artifact_sets,
  });
  if (!sameCanonical(payload, expected)) {
    fail("FORGE_REPLAY_INTEGRITY_FAILED", "D03 payload differs from its immutable intent");
  }
};

const reconstructOpenState = (request, projection) => sealForgeSessionState({
  session_id: request.session_id,
  workspace_id: request.workspace_id,
  revision: 0,
  phase: "IDLE",
  work_class: projection.classification.work_class,
  status: "ACTIVE",
  run_spec_id: request.run_spec_id,
  hypothesis_revision_ids: [],
  artifact_ids: [],
  open_blockers: [],
  phase_history: [],
  policy_hash: request.policy_hash,
  corpus_snapshot_hash: request.corpus_snapshot_hash,
  updated_at: request.requested_at,
});

const makePort = (dependencies) => {
  const { stateStore, artifactStore, ledger, classificationPort, clock } = dependencies;

  const probeExisting = ({ bindings, identity, requestHash }) =>
    stateTransaction(stateStore, (store) =>
      readExistingOperation(store, bindings, identity, requestHash));

  const inspectOpen = (candidate) => {
    const { request, expectedHead } = normalizeOpenOperationInput(candidate);
    const requestHash = requestHashFor("OPEN", request, expectedHead);
    const identity = operationIdentity("OPEN", request.session_id, requestHash);
    const bindings = requestBindingsFor({
      sessionId: request.session_id,
      requestId: request.request_id,
      idempotencyKey: request.idempotency_key,
    });
    return stateTransaction(stateStore, (store) => {
      const existing = readExistingOperation(store, bindings, identity, requestHash);
      if (existing === null) {
        return detached({
          status: "ABSENT",
          preparation: null,
          projection: null,
          ledger_event: null,
          artifact: null,
        });
      }
      const record = validateOutboxRecord(
        store.readRevisionedRecord(OUTBOX_RECORD_VERSION, existing),
      );
      if (record === null) {
        fail("FORGE_OUTBOX_INTEGRITY_FAILED", "bound OPEN outbox is missing");
      }
      const preparation = openPreparationResult(record, "EXISTING");
      if (record.value.state !== "PUBLISHED") {
        return detached({
          status: record.value.state,
          preparation,
          projection: null,
          ledger_event: null,
          artifact: null,
        });
      }
      const projection = buildPublishedProjection({
        state: record.value.intent.candidate_state,
        phaseArtifactSets: record.value.intent.phase_artifact_sets,
        supersededPhaseArtifactSets: record.value.intent.superseded_phase_artifact_sets,
        event: record.value.resolution.ledger.event,
        classificationProjection: record.value.intent.classification_projection,
      });
      if (projection.projection_hash !== record.value.resolution.projection_hash) {
        fail("FORGE_SESSION_STATE_INTEGRITY_FAILED", "operation projection resolution changed");
      }
      const session = validateSessionRecord(
        store.readRevisionedRecord(SESSION_RECORD_VERSION, request.session_id),
      );
      if (session === null || session.value.published === null) {
        fail("FORGE_SESSION_STATE_INTEGRITY_FAILED", "published session projection is missing");
      }
      const current = session.value.published;
      if (
        current.state.revision < projection.state.revision ||
        (current.state.revision === projection.state.revision &&
          current.projection_hash !== projection.projection_hash)
      ) {
        fail(
          "FORGE_SESSION_STATE_INTEGRITY_FAILED",
          "published session does not contain the inspected OPEN operation",
        );
      }
      return detached({
        status: "PUBLISHED",
        preparation,
        projection,
        ledger_event: record.value.resolution.ledger.event,
        artifact: record.value.resolution.artifact,
      });
    });
  };

  const prepareOpen = (transactionStore, candidate) => {
    for (const method of [
      "readRevisionedRecord",
      "createRevisionedRecord",
      "compareAndSwapRevision",
    ]) {
      dependencyMethod(transactionStore, method, "transactionStore");
    }
    const { request, expectedHead, projection } = normalizeOpenOperationInput(candidate, {
      includeProjection: true,
    });
    bindOpenToClassification(request, projection);
    const requestHash = requestHashFor("OPEN", request, expectedHead);
    const identity = operationIdentity("OPEN", request.session_id, requestHash);
    const bindings = requestBindingsFor({
      sessionId: request.session_id,
      requestId: request.request_id,
      idempotencyKey: request.idempotency_key,
    });
    const existing = readExistingOperation(
      transactionStore,
      bindings,
      identity,
      requestHash,
    );
    if (existing !== null) {
      return openPreparationResult(
        transactionStore.readRevisionedRecord(OUTBOX_RECORD_VERSION, existing),
        "EXISTING",
      );
    }

    const existingSession = validateSessionRecord(
      transactionStore.readRevisionedRecord(SESSION_RECORD_VERSION, request.session_id),
    );
    if (existingSession !== null && existingSession.value.pending !== null) {
      fail("FORGE_SESSION_PENDING", "session already has an unpublished operation");
    }
    if (existingSession !== null && existingSession.value.published !== null) {
      fail("FORGE_SESSION_ALREADY_OPEN", "session already has a published OPEN event");
    }
    const occurredAt = timestampFromClock(clock);
    if (compareTimes(occurredAt, request.requested_at) < 0) {
      fail("FORGE_CLOCK_INVALID", "OPEN event cannot precede requested_at");
    }
    const intent = createOpenIntent({
      request,
      expectedHead,
      requestHash,
      identity,
      projection,
      occurredAt,
    });
    createOperationRecords({
      store: transactionStore,
      bindings,
      identity,
      sessionId: request.session_id,
      requestHash,
      intent,
      existingSession,
    });
    return openPreparationResult(
      transactionStore.readRevisionedRecord(OUTBOX_RECORD_VERSION, identity.outboxId),
      "PREPARED",
    );
  };

  const inspectTransition = (candidate) => {
    const { request, requestId, sessionId, idempotencyKey, expectedHead } =
      normalizeTransitionInput(candidate);
    const requestHash = requestHashFor("TRANSITION", request, expectedHead);
    const identity = operationIdentity("TRANSITION", sessionId, requestHash);
    const bindings = requestBindingsFor({ sessionId, requestId, idempotencyKey });
    return stateTransaction(stateStore, (store) => {
      const existing = readExistingOperation(store, bindings, identity, requestHash);
      if (existing === null) {
        return detached({
          status: "ABSENT",
          preparation: null,
          projection: null,
          ledger_event: null,
          artifact: null,
        });
      }
      const record = validateOutboxRecord(
        store.readRevisionedRecord(OUTBOX_RECORD_VERSION, existing),
      );
      if (record === null) {
        fail("FORGE_OUTBOX_INTEGRITY_FAILED", "bound transition outbox is missing");
      }
      const preparation = transitionPreparationResult(record, "EXISTING");
      if (record.value.state !== "PUBLISHED") {
        return detached({
          status: record.value.state,
          preparation,
          projection: null,
          ledger_event: null,
          artifact: null,
        });
      }
      const projection = buildPublishedProjection({
        state: record.value.intent.candidate_state,
        phaseArtifactSets: record.value.intent.phase_artifact_sets,
        supersededPhaseArtifactSets: record.value.intent.superseded_phase_artifact_sets,
        event: record.value.resolution.ledger.event,
        classificationProjection: record.value.intent.classification_projection,
      });
      if (projection.projection_hash !== record.value.resolution.projection_hash) {
        fail("FORGE_SESSION_STATE_INTEGRITY_FAILED", "operation projection resolution changed");
      }
      const session = validateSessionRecord(
        store.readRevisionedRecord(SESSION_RECORD_VERSION, sessionId),
      );
      if (session === null || session.value.published === null) {
        fail("FORGE_SESSION_STATE_INTEGRITY_FAILED", "published session projection is missing");
      }
      const current = session.value.published;
      if (
        current.state.revision < projection.state.revision ||
        (current.state.revision === projection.state.revision &&
          current.projection_hash !== projection.projection_hash)
      ) {
        fail(
          "FORGE_SESSION_STATE_INTEGRITY_FAILED",
          "published session does not contain the inspected transition",
        );
      }
      return detached({
        status: "PUBLISHED",
        preparation,
        projection,
        ledger_event: record.value.resolution.ledger.event,
        artifact: record.value.resolution.artifact,
      });
    });
  };

  const prepareTransition = (transactionStore, candidate) => {
    for (const method of [
      "readRevisionedRecord",
      "createRevisionedRecord",
      "compareAndSwapRevision",
    ]) {
      dependencyMethod(transactionStore, method, "transactionStore");
    }
    const { request, requestId, sessionId, idempotencyKey, expectedHead } =
      normalizeTransitionInput(candidate);
    const requestHash = requestHashFor("TRANSITION", request, expectedHead);
    const identity = operationIdentity("TRANSITION", sessionId, requestHash);
    const bindings = requestBindingsFor({ sessionId, requestId, idempotencyKey });
    const existing = readExistingOperation(
      transactionStore,
      bindings,
      identity,
      requestHash,
    );
    if (existing !== null) {
      return transitionPreparationResult(
        transactionStore.readRevisionedRecord(OUTBOX_RECORD_VERSION, existing),
        "EXISTING",
      );
    }

    const session = validateSessionRecord(
      transactionStore.readRevisionedRecord(SESSION_RECORD_VERSION, sessionId),
    );
    if (session === null || session.value.published === null) {
      fail("FORGE_SESSION_NOT_FOUND", "published session does not exist");
    }
    if (session.value.pending !== null) {
      fail("FORGE_SESSION_PENDING", "session already has an unpublished operation");
    }
    const occurredAt = timestampFromClock(clock);
    if (
      compareTimes(occurredAt, request.requested_at) < 0 ||
      compareTimes(occurredAt, session.value.published.state.updated_at) <= 0
    ) {
      fail("FORGE_CLOCK_INVALID", "transition event time is not after the published state");
    }
    const projection = storedOpenProjection(transactionStore, sessionId);
    if (
      session.value.published.classification_projection_id !== projection.projection_id ||
      session.value.published.classification_projection_hash !== projection.projection_hash
    ) {
      fail("FORGE_CLASSIFICATION_INTEGRITY_FAILED", "published classification binding changed");
    }
    const intent = createTransitionIntent({
      request,
      expectedHead,
      requestHash,
      identity,
      published: session.value.published,
      projection,
      artifactStore,
      occurredAt,
    });
    createOperationRecords({
      store: transactionStore,
      bindings,
      identity,
      sessionId,
      requestHash,
      intent,
      existingSession: session,
    });
    return transitionPreparationResult(
      transactionStore.readRevisionedRecord(OUTBOX_RECORD_VERSION, identity.outboxId),
      "PREPARED",
    );
  };

  const openSession = (candidate) => {
    const { request, expectedHead } = normalizeOpenInput(candidate);
    const requestHash = requestHashFor("OPEN", request, expectedHead);
    const identity = operationIdentity("OPEN", request.session_id, requestHash);
    const bindings = requestBindingsFor({
      sessionId: request.session_id,
      requestId: request.request_id,
      idempotencyKey: request.idempotency_key,
    });
    const existing = probeExisting({ bindings, identity, requestHash });
    if (existing !== null) return publishedAfterOperation(dependencies, existing);

    const projection = readClassificationProjection(classificationPort, request.classification_id);
    bindOpenToClassification(request, projection);
    const prepared = stateTransaction(stateStore, (store) => prepareOpen(store, {
      open_request: request,
      expected_ledger_head: expectedHead,
      classification_projection: projection,
    }));
    return publishedAfterOperation(dependencies, prepared.outbox_id);
  };

  const transitionSession = (candidate) => {
    const prepared = stateTransaction(stateStore, (store) =>
      prepareTransition(store, candidate));
    return publishedAfterOperation(dependencies, prepared.outbox_id, { exactOperation: true });
  };

  const readSession = (sessionId) => {
    const id = requireString(sessionId, "session_id", { min: 3, max: 128 });
    const record = validateSessionRecord(
      readStateRecord(stateStore, SESSION_RECORD_VERSION, id),
    );
    return record === null || record.value.published === null
      ? null
      : detached(record.value.published);
  };

  const reconcilePending = () => {
    const index = validateIndexRecord(
      readStateRecord(stateStore, OUTBOX_INDEX_RECORD_VERSION, OUTBOX_INDEX_ID),
    );
    if (index === null) {
      return detached({ total: 0, pending: 0, published: 0, conflicted: 0 });
    }
    let pending = 0;
    let published = 0;
    let conflicted = 0;
    for (const outboxId of index.value.outbox_ids) {
      const before = validateOutboxRecord(
        readStateRecord(stateStore, OUTBOX_RECORD_VERSION, outboxId),
      );
      if (before === null) fail("FORGE_OUTBOX_INDEX_INTEGRITY_FAILED", "indexed outbox is missing");
      if (before.value.state === "PENDING") {
        const result = publishOutbox(dependencies, outboxId);
        if (result.status === "PUBLISHED") published += 1;
        else if (result.status === "CONFLICTED") conflicted += 1;
        else pending += 1;
      } else if (before.value.state === "PUBLISHED") {
        published += 1;
      } else {
        conflicted += 1;
      }
    }
    return detached({
      total: index.value.outbox_ids.length,
      pending,
      published,
      conflicted,
    });
  };

  const restoreSession = (sessionId) => {
    const id = requireString(sessionId, "session_id", { min: 3, max: 128 });
    reconcilePending();
    const stored = validateSessionRecord(
      readStateRecord(stateStore, SESSION_RECORD_VERSION, id),
    );
    if (stored === null || stored.value.published === null) {
      fail("FORGE_SESSION_NOT_FOUND", "published session does not exist");
    }
    const runId = stored.value.published.state.run_spec_id;
    let events;
    try {
      ledger.verifyRun(runId);
      events = ledger.readEvents(runId).map(validateEventRecord);
    } catch (error) {
      if (error instanceof DurableForgeSessionError) throw error;
      fail("FORGE_REPLAY_INTEGRITY_FAILED", "E01 run stream verification failed");
    }
    const sessionEvents = events.filter(
      (event) => event.aggregate_type === EVENT_AGGREGATE_TYPE && event.aggregate_id === id,
    );
    const openEvents = sessionEvents.filter((event) => event.event_type === EVENT_TYPES.OPEN);
    if (
      sessionEvents.length === 0 ||
      openEvents.length !== 1 ||
      sessionEvents[0].event_id !== openEvents[0].event_id ||
      sessionEvents.some(
        (event) => !new Set(Object.values(EVENT_TYPES)).has(event.event_type),
      )
    ) {
      fail("FORGE_REPLAY_INTEGRITY_FAILED", "session stream requires exactly one first OPEN event");
    }
    const index = validateIndexRecord(
      readStateRecord(stateStore, OUTBOX_INDEX_RECORD_VERSION, OUTBOX_INDEX_ID),
    );
    if (index === null) fail("FORGE_REPLAY_INTEGRITY_FAILED", "session outbox index is missing");

    let projection = null;
    let state = null;
    let phaseArtifactSets = [];
    let supersededPhaseArtifactSets = [];
    let replayedPublished = null;
    const publishedOutboxIds = [];

    for (let indexPosition = 0; indexPosition < sessionEvents.length; indexPosition += 1) {
      const event = sessionEvents[indexPosition];
      const outbox = findEventOutbox(stateStore, index, event);
      publishedOutboxIds.push(outbox.outbox_id);
      validateReplayEventBinding(event, outbox, events);
      const payload = validateReplayArtifact(artifactStore, outbox, event);
      validatePayloadIntent(payload, outbox.intent);

      if (indexPosition === 0) {
        if (
          outbox.intent.kind !== "OPEN" ||
          outbox.intent.admission !== null ||
          outbox.intent.candidate_transition !== null ||
          outbox.intent.phase_artifact_sets.length !== 0 ||
          outbox.intent.superseded_phase_artifact_sets.length !== 0
        ) {
          fail("FORGE_REPLAY_INTEGRITY_FAILED", "OPEN payload is malformed");
        }
        try {
          projection = readClassificationProjection(
            classificationPort,
            outbox.intent.request.classification_id,
          );
          bindOpenToClassification(outbox.intent.request, projection);
        } catch {
          fail("FORGE_REPLAY_INTEGRITY_FAILED", "F01 replay provenance could not be resolved");
        }
        if (!sameCanonical(projection, outbox.intent.classification_projection)) {
          fail("FORGE_REPLAY_INTEGRITY_FAILED", "F01 replay projection changed");
        }
        const reconstructed = reconstructOpenState(outbox.intent.request, projection);
        if (!sameCanonical(reconstructed, outbox.intent.candidate_state)) {
          fail("FORGE_REPLAY_STATE_MISMATCH", "OPEN state does not replay exactly");
        }
        state = reconstructed;
      } else {
        if (
          outbox.intent.kind !== "TRANSITION" ||
          !sameCanonical(projection, outbox.intent.classification_projection)
        ) {
          fail("FORGE_REPLAY_INTEGRITY_FAILED", "transition classification provenance changed");
        }
        let transitionResult;
        try {
          transitionResult = admitAndReduceTransition({
            currentState: state,
            transitionRequest: outbox.intent.request,
            artifactStore,
            projection,
            phaseArtifactSets,
            event: { event_id: event.event_id, occurred_at: event.occurred_at },
          });
        } catch {
          fail(
            "FORGE_REPLAY_INTEGRITY_FAILED",
            "F03 admission or F02 reduction could not replay",
          );
        }
        const { admitted, reduced } = transitionResult;
        if (!sameCanonical(admitted.admission, outbox.intent.admission)) {
          fail("FORGE_REPLAY_STATE_MISMATCH", "recorded F03 admission changed on replay");
        }
        const cumulativeSuperseded = [
          ...supersededPhaseArtifactSets,
          ...reduced.superseded_phase_artifact_sets,
        ];
        if (
          !sameCanonical(reduced.state, outbox.intent.candidate_state) ||
          !sameCanonical(reduced.transition, outbox.intent.candidate_transition) ||
          !sameCanonical(reduced.phase_artifact_sets, outbox.intent.phase_artifact_sets) ||
          !sameCanonical(cumulativeSuperseded, outbox.intent.superseded_phase_artifact_sets)
        ) {
          fail("FORGE_REPLAY_STATE_MISMATCH", "recorded transition or phase projection changed");
        }
        state = reduced.state;
        phaseArtifactSets = reduced.phase_artifact_sets;
        supersededPhaseArtifactSets = cumulativeSuperseded;
      }
      replayedPublished = buildPublishedProjection({
        state,
        phaseArtifactSets,
        supersededPhaseArtifactSets,
        event,
        classificationProjection: projection,
      });
      if (outbox.resolution.projection_hash !== replayedPublished.projection_hash) {
        fail("FORGE_REPLAY_STATE_MISMATCH", "recorded published projection hash changed");
      }
    }

    const sessionPublishedOutboxes = index.value.outbox_ids.filter((outboxId) => {
      const outbox = validateOutboxRecord(
        readStateRecord(stateStore, OUTBOX_RECORD_VERSION, outboxId),
      );
      return outbox?.value.session_id === id && outbox.value.state === "PUBLISHED";
    });
    const canonicalSessionPublishedOutboxes = [...sessionPublishedOutboxes].sort(
      compareCanonicalText,
    );
    const canonicalReplayedOutboxes = [...new Set(publishedOutboxIds)].sort(
      compareCanonicalText,
    );
    if (
      canonicalReplayedOutboxes.length !== publishedOutboxIds.length ||
      !sameCanonical(canonicalSessionPublishedOutboxes, canonicalReplayedOutboxes)
    ) {
      fail("FORGE_REPLAY_INTEGRITY_FAILED", "published outbox and E01 event counts do not reconcile");
    }
    if (!sameCanonical(replayedPublished, stored.value.published)) {
      fail("FORGE_REPLAY_STATE_MISMATCH", "final canonical session projection does not replay");
    }
    return detached(replayedPublished);
  };

  const port = OBJECT_FREEZE({
    openSession,
    transitionSession,
    readSession,
    reconcilePending,
    restoreSession,
  });
  bindDurableForgeSessionWorkerAuthority(port, {
    artifactStore,
    classificationPort,
    ledger,
    stateStore,
    clock,
    inspectOpen,
    prepareOpen,
    inspectTransition,
    prepareTransition,
  });
  return port;
};

export const createDurableForgeSessionPort = (options) => {
  const dependencies = normalizeDependencies(options);
  return makePort(dependencies);
};
