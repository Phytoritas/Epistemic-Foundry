import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { types as utilTypes } from "node:util";
import { fileURLToPath } from "node:url";

import { openContentAddressedArtifactStore } from "../../../packages/foundry-kernel/src/artifacts/content-addressed-artifact-store.mjs";
import {
  createCapabilityAuthority,
  sealCapabilityPolicy,
} from "../../../packages/foundry-kernel/src/capabilities/capability-authority.mjs";
import {
  E03_IDS,
  defaultPolicyInput,
  leaseSubject,
} from "../../../packages/foundry-kernel/src/capabilities/capability-test-support.mjs";
import { createEffectCoordinator } from "../../../packages/foundry-kernel/src/effects/effect-coordinator.mjs";
import {
  createIntentFixture,
  createReceiptFixture,
  fixedEffectTimestamp,
  putEffectArtifact,
} from "../../../packages/foundry-kernel/src/effects/effect-test-support.mjs";
import {
  createNoeticLedger,
  decodeJsonPayload,
} from "../../../packages/foundry-kernel/src/ledger/noetic-ledger.mjs";
import { openSQLiteStateStore } from "../../../packages/foundry-kernel/src/state/sqlite/sqlite-state-store.mjs";

export const E04_IDS = Object.freeze({
  APPROVAL: "APR-E04-replay",
  INTENT: "INTENT-E04-replay",
  ATTEMPT: "ATTEMPT-E04-replay",
  RECEIPT: "EFF-E04-replay",
  RESULT_ARTIFACT: "ART-E04-result",
  LEASE: "LEASE-E04-replay",
  OPERATION: "OP-E04-replay",
  RUN: "RUN-E04-replay",
});

export const REPLAY_PIN_KEYS = Object.freeze([
  "adapter_model",
  "context",
  "corpus",
  "policy",
  "prompts",
  "receipts",
  "run_spec",
  "tools",
]);

const DRIFT_CLASS_BY_PIN = Object.freeze({
  adapter_model: "MODEL",
  corpus: "CORPUS",
  policy: "POLICY",
  prompts: "PROMPT",
  run_spec: "WORKFLOW",
});

const EFFECT_EVENT_TYPES = new Set([
  "effect.action-intent.recorded",
  "effect.attempt.started",
  "effect.receipt.recorded",
]);

const CAPABILITY_EVENT_TYPES = new Set([
  "capability.approval.recorded",
  "capability.lease.issued",
  "capability.lease-use.committed",
  "capability.lease.revoked",
]);

const HASH_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const NUMBER_IS_FINITE = Number.isFinite;
const NUMBER_IS_SAFE_INTEGER = Number.isSafeInteger;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);

const fail = (code, message, details = undefined) => {
  const error = new Error(message);
  error.code = code;
  if (details !== undefined) error.details = details;
  throw error;
};

const assertPlainObject = (value, label) => {
  if (
    value === null ||
    typeof value !== "object" ||
    IS_PROXY(value) ||
    ARRAY_IS_ARRAY(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== PLAIN_OBJECT_PROTOTYPE
  ) {
    fail("E04_NON_CANONICAL_JSON", `${label} must be a plain JSON object`);
  }
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (typeof key !== "string") {
      fail("E04_NON_CANONICAL_JSON", `${label} contains a symbol key`);
    }
    assertUnicodeScalarString(key, `${label} key`);
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (
      descriptor === undefined ||
      descriptor.enumerable !== true ||
      !("value" in descriptor)
    ) {
      fail("E04_NON_CANONICAL_JSON", `${label}.${key} must be an enumerable data property`);
    }
  }
  return value;
};

const assertUnicodeScalarString = (value, label) => {
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        fail("E04_NON_CANONICAL_JSON", `${label} contains an unpaired high surrogate`);
      }
      index += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      fail("E04_NON_CANONICAL_JSON", `${label} contains an unpaired low surrogate`);
    }
  }
};

const canonicalJsonInternal = (value, label) => {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") {
    assertUnicodeScalarString(value, label);
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!NUMBER_IS_FINITE(value)) {
      fail("E04_NON_CANONICAL_JSON", `${label} contains a non-finite number`);
    }
    return JSON.stringify(value);
  }
  if (typeof value !== "object" || IS_PROXY(value)) {
    fail("E04_NON_CANONICAL_JSON", `${label} is not canonical JSON data`);
  }
  if (ARRAY_IS_ARRAY(value)) {
    const keys = REFLECT_OWN_KEYS(value);
    if (keys.some((key) => typeof key !== "string")) {
      fail("E04_NON_CANONICAL_JSON", `${label} contains a symbol key`);
    }
    const lengthDescriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, "length");
    if (
      lengthDescriptor === undefined ||
      !("value" in lengthDescriptor) ||
      lengthDescriptor.value !== value.length ||
      keys.length !== value.length + 1
    ) {
      fail("E04_NON_CANONICAL_JSON", `${label} contains a sparse or decorated array`);
    }
    const entries = [];
    for (let index = 0; index < value.length; index += 1) {
      const key = String(index);
      const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
      if (
        descriptor === undefined ||
        descriptor.enumerable !== true ||
        !("value" in descriptor)
      ) {
        fail("E04_NON_CANONICAL_JSON", `${label} contains a sparse or accessor array entry`);
      }
      entries.push(canonicalJsonInternal(descriptor.value, `${label}[${index}]`));
    }
    return `[${entries.join(",")}]`;
  }
  assertPlainObject(value, label);
  const keys = REFLECT_OWN_KEYS(value).sort();
  return `{${keys
    .map((key) => {
      const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
      return `${JSON.stringify(key)}:${canonicalJsonInternal(descriptor.value, `${label}.${key}`)}`;
    })
    .join(",")}}`;
};

const assertCanonicalJsonValue = (value, label = "value") => {
  canonicalJsonInternal(value, label);
};

export const canonicalJson = (value) => canonicalJsonInternal(value, "value");

export const sha256Canonical = (value) =>
  `sha256:${createHash("sha256").update(canonicalJson(value), "utf8").digest("hex")}`;

const deepFreeze = (value) => {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const entry of Object.values(value)) deepFreeze(entry);
  }
  return value;
};

const cloneCanonical = (value) => JSON.parse(canonicalJson(value));

export const emptyEPhaseReplayState = () => ({
  approvals: {},
  effects: {},
  event_order: [],
  lease_uses: {},
  leases: {},
});

const requirePayloadObject = (payload, eventType) =>
  assertPlainObject(payload, `${eventType} payload`);

const requireNonEmptyString = (value, label) => {
  if (typeof value !== "string" || value.length === 0) {
    fail("E04_REPLAY_SEQUENCE_INVALID", `${label} must be a non-empty string`);
  }
  return value;
};

const requireEventBinding = (event, { aggregateType, aggregateId, runId = undefined }) => {
  if (
    event.aggregate_type !== aggregateType ||
    event.aggregate_id !== aggregateId ||
    (runId !== undefined && event.run_id !== runId)
  ) {
    fail("E04_REPLAY_EVENT_BINDING_INVALID", "event envelope differs from its replay payload", {
      event_id: event.event_id,
      event_type: event.event_type,
    });
  }
};

const requireExistingEffect = (state, intentId, eventType) => {
  const effect = state.effects[intentId];
  if (effect === undefined) {
    fail(
      "E04_REPLAY_SEQUENCE_INVALID",
      `${eventType} precedes its ActionIntent`,
      { intent_id: intentId },
    );
  }
  return effect;
};

export const reduceEPhaseEvent = (state, { event, payloadBytes }) => {
  const payload = requirePayloadObject(decodeJsonPayload(payloadBytes), event.event_type);
  const next = {
    approvals: { ...state.approvals },
    effects: { ...state.effects },
    event_order: [
      ...state.event_order,
      {
        event_id: event.event_id,
        event_type: event.event_type,
        sequence: event.sequence,
      },
    ],
    lease_uses: { ...state.lease_uses },
    leases: { ...state.leases },
  };

  if (event.event_type === "effect.action-intent.recorded") {
    const intentId = requireNonEmptyString(payload.intent_id, "ActionIntent.intent_id");
    requireNonEmptyString(payload.run_id, "ActionIntent.run_id");
    requireEventBinding(event, {
      aggregateType: "effect",
      aggregateId: intentId,
      runId: payload.run_id,
    });
    if (next.effects[intentId] !== undefined) {
      fail("E04_REPLAY_SEQUENCE_INVALID", "ActionIntent replay identity is missing or duplicated");
    }
    next.effects[intentId] = {
      attempts: [],
      intent: cloneCanonical(payload),
      receipts: [],
    };
    return next;
  }

  if (event.event_type === "effect.attempt.started") {
    const intentId = requireNonEmptyString(payload.intent_id, "Attempt.intent_id");
    const attemptId = requireNonEmptyString(payload.attempt_id, "Attempt.attempt_id");
    const effect = requireExistingEffect(next, intentId, event.event_type);
    requireEventBinding(event, {
      aggregateType: "effect",
      aggregateId: intentId,
      runId: effect.intent.run_id,
    });
    if (
      payload.run_id !== effect.intent.run_id ||
      payload.intent_hash !== effect.intent.intent_hash ||
      payload.idempotency_key !== effect.intent.idempotency_key ||
      payload.attempt_number !== effect.attempts.length + 1 ||
      effect.attempts.some((attempt) => attempt.attempt_id === attemptId)
    ) {
      fail("E04_REPLAY_SEQUENCE_INVALID", "Attempt replay identity is duplicated");
    }
    next.effects[intentId] = {
      ...effect,
      attempts: [...effect.attempts, cloneCanonical(payload)],
    };
    return next;
  }

  if (event.event_type === "effect.receipt.recorded") {
    const intentId = requireNonEmptyString(payload.intent_id, "EffectReceipt.intent_id");
    const receiptId = requireNonEmptyString(payload.receipt_id, "EffectReceipt.receipt_id");
    const effect = requireExistingEffect(next, intentId, event.event_type);
    requireEventBinding(event, {
      aggregateType: "effect",
      aggregateId: intentId,
      runId: effect.intent.run_id,
    });
    const tailAttempt = effect.attempts.at(-1);
    if (
      tailAttempt === undefined ||
      tailAttempt.started_at !== payload.started_at ||
      payload.run_id !== effect.intent.run_id ||
      payload.idempotency_key !== effect.intent.idempotency_key
    ) {
      fail("E04_REPLAY_SEQUENCE_INVALID", "EffectReceipt does not resolve the replayed tail Attempt");
    }
    if (effect.receipts.some((receipt) => receipt.receipt_id === receiptId)) {
      fail("E04_REPLAY_SEQUENCE_INVALID", "EffectReceipt replay identity is duplicated");
    }
    next.effects[intentId] = {
      ...effect,
      receipts: [...effect.receipts, cloneCanonical(payload)],
    };
    return next;
  }

  if (event.event_type === "capability.approval.recorded") {
    const approval = assertPlainObject(payload.approval, "approval");
    const approvalId = requireNonEmptyString(approval.approval_id, "ApprovalRecord.approval_id");
    requireEventBinding(event, {
      aggregateType: "approval",
      aggregateId: approvalId,
      runId: approval.run_id,
    });
    if (next.approvals[approvalId] !== undefined) {
      fail("E04_REPLAY_SEQUENCE_INVALID", "ApprovalRecord replay identity is duplicated");
    }
    next.approvals[approvalId] = cloneCanonical(approval);
    return next;
  }

  if (event.event_type === "capability.lease.issued") {
    const lease = assertPlainObject(payload.lease, "issued lease");
    const leaseId = requireNonEmptyString(lease.lease_id, "CapabilityLease.lease_id");
    requireEventBinding(event, {
      aggregateType: "capability_lease",
      aggregateId: leaseId,
    });
    if (next.leases[leaseId] !== undefined || lease.revoked !== false) {
      fail("E04_REPLAY_SEQUENCE_INVALID", "CapabilityLease issuance is duplicated or revoked");
    }
    next.leases[leaseId] = cloneCanonical(lease);
    return next;
  }

  if (event.event_type === "capability.lease-use.committed") {
    const use = assertPlainObject(payload.use, "lease use");
    const operationId = requireNonEmptyString(use.operation_id, "lease use.operation_id");
    const leaseId = requireNonEmptyString(use.lease_id, "lease use.lease_id");
    requireEventBinding(event, {
      aggregateType: "capability_lease",
      aggregateId: leaseId,
    });
    const lease = next.leases[leaseId];
    if (
      lease === undefined ||
      lease.revoked ||
      lease.fencing_token !== use.fencing_token ||
      next.lease_uses[operationId] !== undefined
    ) {
      fail("E04_REPLAY_SEQUENCE_INVALID", "lease use does not resolve the active replayed lease");
    }
    next.lease_uses[operationId] = cloneCanonical(use);
    return next;
  }

  if (event.event_type === "capability.lease.revoked") {
    const lease = assertPlainObject(payload.lease, "revoked lease");
    const leaseId = requireNonEmptyString(lease.lease_id, "revoked CapabilityLease.lease_id");
    requireEventBinding(event, {
      aggregateType: "capability_lease",
      aggregateId: leaseId,
    });
    const issued = next.leases[leaseId];
    if (
      issued === undefined ||
      issued.revoked ||
      lease.revoked !== true ||
      lease.fencing_token !== issued.fencing_token ||
      lease.policy_hash !== issued.policy_hash
    ) {
      fail("E04_REPLAY_SEQUENCE_INVALID", "lease revocation does not resolve an issued lease");
    }
    next.leases[leaseId] = cloneCanonical(lease);
    return next;
  }

  if (EFFECT_EVENT_TYPES.has(event.event_type) || CAPABILITY_EVENT_TYPES.has(event.event_type)) {
    fail("E04_REPLAY_EVENT_UNHANDLED", `known E-phase event is not handled: ${event.event_type}`);
  }
  fail("E04_REPLAY_EVENT_UNSUPPORTED", `event is outside the E-phase replay contract: ${event.event_type}`);
};

export const liveEPhaseProjection = ({ authority, coordinator }) => ({
  approvals: {
    [E04_IDS.APPROVAL]: authority.readApproval(E04_IDS.APPROVAL),
  },
  effects: {
    [E04_IDS.INTENT]: {
      attempts: coordinator.readAttempts(E04_IDS.INTENT),
      intent: coordinator.readIntent(E04_IDS.INTENT),
      receipts: coordinator.readReceipts(E04_IDS.INTENT),
    },
  },
  leases: {
    [E04_IDS.LEASE]: authority.readLease(E04_IDS.LEASE),
  },
});

export const pinHash = (label) => sha256Canonical({ e04_pin: label });

export const replayPins = (overrides = {}) => {
  const pins = Object.fromEntries(
    REPLAY_PIN_KEYS.map((key) => [key, pinHash(`${key}:v1`)]),
  );
  for (const [key, value] of Object.entries(overrides)) {
    if (!REPLAY_PIN_KEYS.includes(key)) {
      fail("E04_UNKNOWN_PIN", `unknown replay pin: ${key}`);
    }
    if (value === undefined) delete pins[key];
    else pins[key] = value;
  }
  return pins;
};

const validatePins = (pins, label) => {
  assertPlainObject(pins, label);
  for (const [key, value] of Object.entries(pins)) {
    if (!REPLAY_PIN_KEYS.includes(key)) fail("E04_UNKNOWN_PIN", `unknown replay pin: ${key}`);
    if (typeof value !== "string" || !HASH_PATTERN.test(value)) {
      fail("E04_PIN_INVALID", `${label}.${key} must be an exact sha256 pin`);
    }
  }
};

const valueLabel = (value) => (value === undefined ? "<missing>" : canonicalJson(value));

const mapDifferences = (source = {}, replay = {}) => {
  assertPlainObject(source, "source decision map");
  assertPlainObject(replay, "replay decision map");
  const keys = [...new Set([...Object.keys(source), ...Object.keys(replay)])].sort();
  return keys
    .filter((key) => {
      if (source[key] === undefined || replay[key] === undefined) {
        return source[key] !== replay[key];
      }
      return canonicalJson(source[key]) !== canonicalJson(replay[key]);
    })
    .map((key) => `${key}:${valueLabel(source[key])}->${valueLabel(replay[key])}`);
};

const classifyDrift = (changedPins) => {
  if (changedPins.length === 0) return "NONE";
  if (changedPins.length > 1) return "MULTIPLE";
  return DRIFT_CLASS_BY_PIN[changedPins[0]] ?? "UNKNOWN";
};

const normalizeComparisonSide = (side, label) => {
  const candidate = assertPlainObject(side, label);
  validatePins(candidate.pins, `${label}.pins`);
  assertCanonicalJsonValue(candidate.semantic_projection, `${label}.semantic_projection`);
  assertCanonicalJsonValue(candidate.strict_identity, `${label}.strict_identity`);
  return {
    gates: candidate.gates ?? {},
    pins: candidate.pins,
    semantic_projection: candidate.semantic_projection,
    strict_identity: candidate.strict_identity,
    verdicts: candidate.verdicts ?? {},
  };
};

const validateStrictIdentity = (identity, semanticProjection, label) => {
  const candidate = assertPlainObject(identity, label);
  const keys = REFLECT_OWN_KEYS(candidate).sort();
  const expectedKeys = ["event_count", "state_hash", "tail_event_hash"];
  if (canonicalJson(keys) !== canonicalJson(expectedKeys)) {
    fail(
      "E04_STRICT_IDENTITY_INVALID",
      `${label} must contain event_count, state_hash, and tail_event_hash only`,
    );
  }
  const eventCount = candidate.event_count;
  const stateHash = candidate.state_hash;
  const tailEventHash = candidate.tail_event_hash;
  if (!NUMBER_IS_SAFE_INTEGER(eventCount) || eventCount < 0) {
    fail("E04_STRICT_IDENTITY_INVALID", `${label}.event_count is invalid`);
  }
  if (typeof stateHash !== "string" || !HASH_PATTERN.test(stateHash)) {
    fail("E04_STRICT_IDENTITY_INVALID", `${label}.state_hash is invalid`);
  }
  if (
    (eventCount === 0 && tailEventHash !== null) ||
    (eventCount > 0 && (typeof tailEventHash !== "string" || !HASH_PATTERN.test(tailEventHash))
    )
  ) {
    fail("E04_STRICT_IDENTITY_INVALID", `${label}.tail_event_hash is inconsistent`);
  }
  if (stateHash !== sha256Canonical(semanticProjection)) {
    fail("E04_STRICT_IDENTITY_INVALID", `${label}.state_hash does not bind semantic_projection`);
  }
};

export const compareReplay = ({ mode, sourceRunId, replayRunId, source, replay }) => {
  if (mode !== "strict" && mode !== "semantic") {
    fail("E04_REPLAY_MODE_INVALID", "replay mode must be strict or semantic");
  }
  requireNonEmptyString(sourceRunId, "source_run_id");
  requireNonEmptyString(replayRunId, "replay_run_id");
  const left = normalizeComparisonSide(source, "source");
  const right = normalizeComparisonSide(replay, "replay");
  if (mode === "strict") {
    validateStrictIdentity(left.strict_identity, left.semantic_projection, "source.strict_identity");
    validateStrictIdentity(right.strict_identity, right.semantic_projection, "replay.strict_identity");
  }
  const unavailablePins = REPLAY_PIN_KEYS.flatMap((key) => {
    const missing = [];
    if (left.pins[key] === undefined) missing.push(`source:${key}`);
    if (right.pins[key] === undefined) missing.push(`replay:${key}`);
    return missing;
  });
  const availablePins = REPLAY_PIN_KEYS.filter(
    (key) => left.pins[key] !== undefined && right.pins[key] !== undefined,
  );
  const changedPins = availablePins.filter((key) => left.pins[key] !== right.pins[key]);
  const gateDifferences = mapDifferences(left.gates, right.gates);
  const verdictDifferences = mapDifferences(left.verdicts, right.verdicts);
  const semanticStateMatches =
    canonicalJson(left.semantic_projection) === canonicalJson(right.semantic_projection);
  const strictIdentityMatches =
    sourceRunId === replayRunId &&
    canonicalJson(left.strict_identity) === canonicalJson(right.strict_identity);

  let eventEquivalence;
  if (unavailablePins.length > 0) eventEquivalence = "NOT_COMPARABLE";
  else if (mode === "strict") {
    eventEquivalence =
      changedPins.length === 0 &&
      gateDifferences.length === 0 &&
      verdictDifferences.length === 0 &&
      semanticStateMatches &&
      strictIdentityMatches
        ? "EXACT"
        : "DRIFT";
  } else {
    eventEquivalence =
      gateDifferences.length === 0 && verdictDifferences.length === 0 && semanticStateMatches
        ? "SEMANTICALLY_EQUIVALENT"
        : "DRIFT";
  }

  return {
    artifact_hash_matches: availablePins.length - changedPins.length,
    artifact_hash_mismatches: changedPins.length,
    drift_classification:
      unavailablePins.length > 0 && changedPins.length === 0
        ? "UNKNOWN"
        : classifyDrift(changedPins),
    event_equivalence: eventEquivalence,
    gate_differences: gateDifferences,
    pinned_artifacts: REPLAY_PIN_KEYS.flatMap((key) => {
      const pins = [];
      if (left.pins[key] !== undefined) pins.push(`source:${key}=${left.pins[key]}`);
      if (right.pins[key] !== undefined) pins.push(`replay:${key}=${right.pins[key]}`);
      return pins;
    }),
    unavailable_pins: unavailablePins,
    verdict_differences: verdictDifferences,
  };
};

export const sealReplayReport = ({
  replayId,
  sourceRunId,
  replayRunId,
  mode,
  source,
  replay,
  createdAt = "2026-07-29T00:00:00Z",
}) => {
  const comparison = compareReplay({ mode, replayRunId, source, sourceRunId, replay });
  const reportWithoutHash = {
    replay_id: replayId,
    source_run_id: sourceRunId,
    replay_run_id: replayRunId,
    mode,
    pinned_artifacts: comparison.pinned_artifacts,
    unavailable_pins: comparison.unavailable_pins,
    event_equivalence: comparison.event_equivalence,
    artifact_hash_matches: comparison.artifact_hash_matches,
    artifact_hash_mismatches: comparison.artifact_hash_mismatches,
    gate_differences: comparison.gate_differences,
    verdict_differences: comparison.verdict_differences,
    drift_classification: comparison.drift_classification,
    created_at: createdAt,
  };
  return deepFreeze({
    ...reportWithoutHash,
    report_hash: sha256Canonical(reportWithoutHash),
  });
};

export const assertReplayReportIntegrity = (candidate) => {
  const report = assertPlainObject(candidate, "ReplayReport");
  if (!HASH_PATTERN.test(report.report_hash ?? "")) {
    fail("E04_REPLAY_REPORT_HASH_INVALID", "ReplayReport hash format is invalid");
  }
  const { report_hash: actual, ...withoutHash } = report;
  const expected = sha256Canonical(withoutHash);
  if (actual !== expected) {
    fail("E04_REPLAY_REPORT_HASH_MISMATCH", "ReplayReport hash does not bind its content", {
      actual,
      expected,
    });
  }
  return true;
};

export const validateReplayReportSchema = (report) => {
  const script = String.raw`
import json, pathlib, sys
from jsonschema import Draft202012Validator, FormatChecker
schema = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
instance = json.loads(sys.argv[2])
Draft202012Validator.check_schema(schema)
errors = sorted(
    Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance),
    key=lambda error: list(error.absolute_path),
)
if errors:
    raise SystemExit("; ".join(error.message for error in errors))
print("ReplayReport valid")
`;
  const result = spawnSync(
    "uv",
    [
      "run",
      "--locked",
      "python",
      "-",
      path.join(repositoryRoot, "schemas", "replay-report.schema.json"),
      canonicalJson(report),
    ],
    {
      cwd: repositoryRoot,
      encoding: "utf8",
      input: script,
    },
  );
  if (result.status !== 0) {
    fail(
      "E04_REPLAY_REPORT_SCHEMA_INVALID",
      `ReplayReport schema validation failed\n${result.stdout}\n${result.stderr}`,
    );
  }
  return result.stdout.trim();
};

export const payloadContentPath = (artifactStore, artifactRoot, artifactId) => {
  const manifest = artifactStore.readManifest(artifactId);
  const hex = manifest.content_hash.slice("sha256:".length);
  return path.join(artifactRoot, "sha256", hex.slice(0, 2), hex.slice(2), "content.bin");
};

export const createEPhaseReplayFixture = (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "ef-e04-replay-"));
  const databasePath = path.join(root, "foundry.db");
  const artifactRoot = path.join(root, "artifacts");
  const policy = sealCapabilityPolicy(
    defaultPolicyInput({
      subjects: [
        leaseSubject({
          runId: E04_IDS.RUN,
          subjectId: E04_IDS.LEASE,
        }),
      ],
    }),
  );
  let currentTime = "2026-07-28T05:00:00Z";
  let closed = false;
  const fixture = {
    artifactRoot,
    databasePath,
    policy,
    root,
    setTime(value) {
      currentTime = value;
    },
  };

  const open = () => {
    fixture.stateStore = openSQLiteStateStore(databasePath);
    fixture.artifactStore = openContentAddressedArtifactStore(artifactRoot);
    fixture.ledger = createNoeticLedger({
      artifactStore: fixture.artifactStore,
      stateStore: fixture.stateStore,
    });
    fixture.coordinator = createEffectCoordinator({
      artifactStore: fixture.artifactStore,
      ledger: fixture.ledger,
      stateStore: fixture.stateStore,
    });
    fixture.authority = createCapabilityAuthority({
      artifactStore: fixture.artifactStore,
      clock: () => currentTime,
      ledger: fixture.ledger,
      policy,
      stateStore: fixture.stateStore,
    });
    closed = false;
  };

  fixture.closeStores = () => {
    if (closed) return;
    fixture.stateStore.close();
    fixture.artifactStore.close();
    closed = true;
  };
  fixture.reopen = () => {
    fixture.closeStores();
    open();
    return fixture;
  };
  t.after(() => {
    fixture.closeStores();
    fs.rmSync(root, { force: true, recursive: true });
  });
  open();
  return fixture;
};

export const executeEPhaseScenario = (fixture) => {
  const intent = createIntentFixture(fixture.artifactStore, {
    idempotencyKey: `${E04_IDS.RUN}:replay:1`,
    intentId: E04_IDS.INTENT,
    runId: E04_IDS.RUN,
  });
  fixture.coordinator.registerIntent(intent);
  const attemptResult = fixture.coordinator.beginAttempt({
    attempt_id: E04_IDS.ATTEMPT,
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(1),
  });
  putEffectArtifact(fixture.artifactStore, {
    actionIntentId: intent.intent_id,
    artifactId: E04_IDS.RESULT_ARTIFACT,
    bytes: Buffer.from(JSON.stringify({ replay_gate: "confirmed" }), "utf8"),
    receiptId: `AR-${E04_IDS.RESULT_ARTIFACT}`,
    timestamp: fixedEffectTimestamp(2),
  });
  const receipt = createReceiptFixture({
    attempt: attemptResult.attempt,
    finishedAt: fixedEffectTimestamp(2),
    intent,
    receiptId: E04_IDS.RECEIPT,
    resultArtifactIds: [E04_IDS.RESULT_ARTIFACT],
    status: "SUCCEEDED",
  });
  fixture.coordinator.recordReceipt({
    attempt_id: attemptResult.attempt.attempt_id,
    receipt,
  });

  const approvalCommand = {
    approval_id: E04_IDS.APPROVAL,
    run_id: E04_IDS.RUN,
    subject_id: E04_IDS.LEASE,
    approval_type: "capability",
    decision: "APPROVE",
    reason: "Independent replay gate authorizes only the declared bounded lease.",
    evidence_artifact_ids: [E04_IDS.RESULT_ARTIFACT],
    conditions: ["strict replay state remains exact"],
    expires_at: "2026-07-28T06:00:00Z",
  };
  const approval = fixture.authority.issueApproval(E03_IDS.APPROVER, approvalCommand);
  const leaseCommand = {
    lease_id: E04_IDS.LEASE,
    run_id: E04_IDS.RUN,
    principal_id: E03_IDS.WORKER,
    capabilities: ["artifact:write", "sandbox:execute"],
    resource_scopes: ["workspace/e03", "artifact/e03"],
    expires_at: "2026-07-28T06:00:00Z",
    approval_ids: [],
  };
  const lease = fixture.authority.issueLease(E03_IDS.AUTHORITY, leaseCommand);
  const useCommand = {
    operation_id: E04_IDS.OPERATION,
    run_id: E04_IDS.RUN,
    lease,
    principal_id: E03_IDS.WORKER,
    capability: "artifact:write",
    resource_scopes: ["artifact/e03"],
  };
  const committed = fixture.authority.commitWithLease(useCommand, () => ({
    replay_checkpoint: "E04",
    result_artifact_id: E04_IDS.RESULT_ARTIFACT,
  }));
  fixture.setTime("2026-07-28T05:10:00Z");
  const revokeCommand = {
    lease_id: E04_IDS.LEASE,
    run_id: E04_IDS.RUN,
    reason: "bounded E04 replay fixture completed",
  };
  const revoked = fixture.authority.revokeLease(E03_IDS.AUTHORITY, revokeCommand);

  return {
    approval,
    approvalCommand,
    attempt: attemptResult.attempt,
    committed,
    intent,
    lease,
    leaseCommand,
    receipt,
    revokeCommand,
    revoked,
    useCommand,
  };
};
