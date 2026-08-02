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
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const CLASSIFICATION_ID_PATTERN = /^EWC-[0-9a-f]{64}$/u;
const EVENT_SCHEMA_VERSION = "4.0.0";
const ACTOR_ID = "ACT-F01-classification-committer";
const OUTBOX_INDEX_ID = "global";

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
  }

  classify(candidate, options = {}) {
    validateClassifierCapabilities(options.capabilities ?? ["artifact_read", "artifact_write"]);
    const initial = evaluateEpistemicWork(candidate);
    const idempotencyKey = classificationIdempotencyKey(initial);
    const transactionResult = this.#stateStore.transaction((store) => {
      const bindingRecord = store.readRevisionedRecord(
        CLASSIFICATION_RECORD_TYPES.IDEMPOTENCY,
        idempotencyKey,
      );
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
        return { state: loadClassification(store, binding.classification_id), status: "EXISTING" };
      }

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
      const state = commitNewState({
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
      return { state, status: "CREATED" };
    });
    this.#publish(transactionResult.state.outbox_id);
    return resultFromState(transactionResult.state, this.#artifactStore, transactionResult.status);
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
