// W02 checkpoint, pause, resume, and cancellation runtime.
//
// The runtime never asserts recoverability: a checkpoint is sealed only after
// the recorded command log is actually replayed into a fresh scheduler and the
// rebuilt state hash matches, and resume re-proves that replay before handing
// back a scheduler.  Cancellation is complete only when every pending effect is
// reconciled to a terminal receipt; an unresolved effect keeps the run in an
// explicit unresolved state instead of a clean stop (EF4-I13/I26).

import {
  canonicalizeSchedulerJson,
  createDagScheduler,
  replaySchedulerCommands,
  sha256SchedulerJson,
} from "../../scheduler/dag-scheduler.mjs";

export const RUN_LIFECYCLE_STATES = Object.freeze([
  "RUNNING",
  "PAUSED",
  "CANCELLING",
  "CANCELLED",
  "CANCELLED_WITH_UNRESOLVED_EFFECTS",
]);
export const CANCELLATION_OUTCOMES = Object.freeze([
  "CANCELLED",
  "CANCELLED_WITH_UNRESOLVED_EFFECTS",
]);
const UNRESOLVED_ATTEMPT_STATES = Object.freeze([
  "LEASED",
  "RUNNING",
  "RECONCILING",
]);
const FINAL_TERMINAL_NODE_STATUSES = Object.freeze([
  "SUCCEEDED",
  "FAILED_FINAL",
  "BLOCKED",
  "SPEC_GAP",
  "CANCELLED",
]);
const REVIEW_DECISIONS = Object.freeze(["APPROVE", "REJECT"]);
const RFC3339 =
  /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.[0-9]+)?(?:[Zz]|([+-])(\d{2}):(\d{2}))$/;
const SHA256 = /^sha256:[0-9a-f]{64}$/;

export class CheckpointRuntimeError extends Error {
  constructor(code, message, details = null) {
    super(message);
    this.name = "CheckpointRuntimeError";
    this.code = code;
    this.details = details === null ? null : structuredClone(details);
    Object.freeze(this);
  }
}

const fail = (code, message, details = null) => {
  throw new CheckpointRuntimeError(code, message, details);
};

const isPlainObject = (value) =>
  typeof value === "object" &&
  value !== null &&
  !Array.isArray(value) &&
  Object.getPrototypeOf(value) === Object.prototype;

const requireObject = (value, label) => {
  if (!isPlainObject(value)) fail("CHECKPOINT_INPUT_INVALID", `${label} must be an object`);
  return value;
};

/** A scheduler is identified by its sealed snapshot/commandLog surface. */
const requireScheduler = (value, label) => {
  if (
    typeof value !== "object" ||
    value === null ||
    typeof value.snapshot !== "function" ||
    typeof value.commandLog !== "function"
  ) {
    fail("CHECKPOINT_INPUT_INVALID", `${label} must expose snapshot() and commandLog()`);
  }
  return value;
};

const requireText = (value, label) => {
  if (typeof value !== "string" || value.trim() === "") {
    fail("CHECKPOINT_INPUT_INVALID", `${label} must be a non-empty string`);
  }
  return value;
};

const isLeapYear = (year) => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

const daysInMonth = (year, month) =>
  [31, isLeapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][
    month - 1
  ];

const requireTimestamp = (value, label) => {
  if (typeof value !== "string") {
    fail("CHECKPOINT_INPUT_INVALID", `${label} must be a real RFC 3339 timestamp`);
  }
  const match = RFC3339.exec(value);
  if (match === null) {
    fail("CHECKPOINT_INPUT_INVALID", `${label} must be a real RFC 3339 timestamp`);
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const offsetHour = match[8] === undefined ? 0 : Number(match[8]);
  const offsetMinute = match[9] === undefined ? 0 : Number(match[9]);
  const offsetSign = match[7] === "-" ? -1 : 1;
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
    fail("CHECKPOINT_INPUT_INVALID", `${label} must be a real RFC 3339 timestamp`);
  }
  const signedOffsetMinutes =
    match[7] === undefined ? 0 : offsetSign * (offsetHour * 60 + offsetMinute);
  const utcMinuteOfDay =
    ((hour * 60 + minute - signedOffsetMinutes) % 1_440 + 1_440) % 1_440;
  if (second === 60) {
    const utcMinutes = hour * 60 + minute - signedOffsetMinutes;
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
    if (
      utcMinuteOfDay !== 23 * 60 + 59 ||
      utcDay !== daysInMonth(utcYear, utcMonth)
    ) {
      fail(
        "CHECKPOINT_INPUT_INVALID",
        `${label} has a leap second outside UTC month-end 23:59`,
      );
    }
  }
  return value;
};

const requireSchemaString = (value, label, { minLength = 0 } = {}) => {
  if (typeof value !== "string" || value.length < minLength) {
    fail("CHECKPOINT_INPUT_INVALID", `${label} must be a schema-valid string`);
  }
  return value;
};

const requireSchemaStringArray = (value, label) => {
  if (!Array.isArray(value)) {
    fail("CHECKPOINT_INPUT_INVALID", `${label} must be an array`);
  }
  const entries = [];
  for (let index = 0; index < value.length; index += 1) {
    if (!Object.hasOwn(value, index)) {
      fail("CHECKPOINT_INPUT_INVALID", `${label} must not be sparse`);
    }
    entries.push(requireSchemaString(value[index], `${label}[${index}]`));
  }
  return entries;
};

const requireSchemaNonNegativeInteger = (value, label) => {
  if (!Number.isInteger(value) || value < 0) {
    fail("CHECKPOINT_INPUT_INVALID", `${label} must be a non-negative integer`);
  }
  return value;
};

const requireStringArray = (value, label) => {
  if (!Array.isArray(value)) fail("CHECKPOINT_INPUT_INVALID", `${label} must be an array`);
  const values = value.map((entry, index) => requireText(entry, `${label}[${index}]`));
  if (new Set(values).size !== values.length) {
    fail("CHECKPOINT_INPUT_INVALID", `${label} must not contain duplicates`);
  }
  return [...values].sort();
};

const requireNonNegativeInteger = (value, label) => {
  if (!Number.isSafeInteger(value) || value < 0) {
    fail("CHECKPOINT_INPUT_INVALID", `${label} must be a non-negative integer`);
  }
  return value;
};

const freezeCheckpointManifest = (manifest) => {
  Object.freeze(manifest.artifact_ids);
  Object.freeze(manifest.expected_node_ids);
  Object.freeze(manifest.gate_decision_ids);
  Object.freeze(manifest.pending_effect_ids);
  Object.freeze(manifest.terminal_node_ids);
  return Object.freeze(manifest);
};

/** Every attempt whose effect is not yet resolved to a terminal receipt. */
export function pendingEffects(snapshot) {
  requireObject(snapshot, "snapshot");
  const pending = [];
  for (const [nodeId, attempts] of Object.entries(snapshot.node_attempts ?? {})) {
    for (const attempt of attempts) {
      if (UNRESOLVED_ATTEMPT_STATES.includes(attempt.status)) {
        pending.push({
          attempt: attempt.attempt,
          node_id: nodeId,
          status: attempt.status,
        });
      }
    }
  }
  return pending.sort((left, right) =>
    left.node_id === right.node_id
      ? left.attempt - right.attempt
      : left.node_id.localeCompare(right.node_id),
  );
}

const deriveCheckpointProjections = ({ snapshot, plan }) => {
  const terminal = [];
  const expected = [];
  for (const [nodeId, attempts] of Object.entries(snapshot.node_attempts ?? {})) {
    expected.push(nodeId);
    const latestAttempt = attempts.at(-1) ?? null;
    if (
      latestAttempt !== null &&
      FINAL_TERMINAL_NODE_STATUSES.includes(latestAttempt.status)
    ) {
      terminal.push(nodeId);
    }
  }
  for (const nodeId of plan.nodes.map((node) => node.node_id)) {
    if (!expected.includes(nodeId)) expected.push(nodeId);
  }

  return {
    expected_node_ids: [...expected].sort(),
    pending_effect_ids: pendingEffects(snapshot).map(
      (entry) => `${entry.node_id}#${entry.attempt}`,
    ),
    terminal_node_ids: [...terminal].sort(),
  };
};

const equalStringArrays = (left, right) =>
  left.length === right.length && left.every((entry, index) => entry === right[index]);

function replayEvidence({ run_id, plan, budget_envelope, commands }) {
  const rebuilt = replaySchedulerCommands({ run_id, plan, budget_envelope, commands });
  return {
    command_count: commands.length,
    rebuilt_state_hash: rebuilt.snapshot.state_hash,
    snapshot: rebuilt.snapshot,
  };
}

/**
 * Seal a checkpoint manifest for the current scheduler state.
 *
 * `replay_verified` is computed, never supplied: the command log is replayed
 * into a fresh scheduler and its state hash must equal the live snapshot's.
 */
export function sealCheckpoint({
  scheduler,
  run_id: runId,
  plan,
  budget_envelope: budget,
  checkpoint_id: checkpointId,
  layer_index: layerIndex,
  artifact_ids: artifactIds = [],
  gate_decision_ids: gateDecisionIds = [],
  created_at: createdAt,
}) {
  requireScheduler(scheduler, "scheduler");
  requireText(runId, "run_id");
  requireObject(plan, "plan");
  requireObject(budget, "budget_envelope");
  requireText(checkpointId, "checkpoint_id");
  requireNonNegativeInteger(layerIndex, "layer_index");
  requireTimestamp(createdAt, "created_at");

  const snapshot = scheduler.snapshot();
  if (snapshot.run_id !== runId) {
    fail("CHECKPOINT_RUN_MISMATCH", "scheduler snapshot belongs to a different run");
  }
  if (snapshot.plan_hash !== plan.plan_hash) {
    fail("CHECKPOINT_PLAN_MISMATCH", "scheduler snapshot does not bind this plan");
  }
  const commands = scheduler.commandLog();
  const replay = replayEvidence({
    run_id: runId,
    plan,
    budget_envelope: budget,
    commands,
  });
  const replayVerified = replay.rebuilt_state_hash === snapshot.state_hash;
  if (!replayVerified) {
    fail(
      "CHECKPOINT_REPLAY_DIVERGED",
      "replaying the command log did not reproduce the live scheduler state",
      { live_state_hash: snapshot.state_hash, rebuilt_state_hash: replay.rebuilt_state_hash },
    );
  }

  const projections = deriveCheckpointProjections({ snapshot, plan });
  const pending = pendingEffects(snapshot);
  const semantic = {
    artifact_ids: requireStringArray(artifactIds, "artifact_ids"),
    checkpoint_id: checkpointId,
    created_at: createdAt,
    event_sequence: replay.command_count,
    expected_node_ids: projections.expected_node_ids,
    gate_decision_ids: requireStringArray(gateDecisionIds, "gate_decision_ids"),
    layer_index: layerIndex,
    pending_effect_ids: projections.pending_effect_ids,
    replay_verified: replayVerified,
    run_id: runId,
    state_hash: snapshot.state_hash,
    terminal_node_ids: projections.terminal_node_ids,
  };
  const manifest = {
    ...semantic,
    checkpoint_hash: sha256SchedulerJson(canonicalizeSchedulerJson(semantic)),
  };
  return Object.freeze({
    commands,
    manifest: freezeCheckpointManifest(manifest),
    pending_effects: Object.freeze(pending),
  });
}

/** Validate a stored checkpoint manifest's shape and self-hash. */
export function validateCheckpointManifest(manifest) {
  requireObject(manifest, "checkpoint manifest");
  const expectedKeys = [
    "artifact_ids",
    "checkpoint_hash",
    "checkpoint_id",
    "created_at",
    "event_sequence",
    "expected_node_ids",
    "gate_decision_ids",
    "layer_index",
    "pending_effect_ids",
    "replay_verified",
    "run_id",
    "state_hash",
    "terminal_node_ids",
  ];
  const keys = Object.keys(manifest).sort();
  if (keys.join(" ") !== expectedKeys.join(" ")) {
    fail("CHECKPOINT_FIELD_SET_INVALID", "checkpoint manifest field set is not canonical", {
      missing: expectedKeys.filter((key) => !keys.includes(key)),
      unknown: keys.filter((key) => !expectedKeys.includes(key)),
    });
  }
  const stateHash = requireSchemaString(manifest.state_hash, "state_hash", { minLength: 1 });
  const asserted = requireSchemaString(manifest.checkpoint_hash, "checkpoint_hash", {
    minLength: 1,
  });
  if (!SHA256.test(stateHash) || !SHA256.test(asserted)) {
    fail("CHECKPOINT_FIELD_SET_INVALID", "state_hash and checkpoint_hash must be sha256 ids");
  }
  if (typeof manifest.replay_verified !== "boolean") {
    fail("CHECKPOINT_FIELD_SET_INVALID", "replay_verified must be a boolean");
  }
  const semantic = {
    artifact_ids: requireSchemaStringArray(manifest.artifact_ids, "artifact_ids"),
    checkpoint_id: requireSchemaString(manifest.checkpoint_id, "checkpoint_id", {
      minLength: 1,
    }),
    created_at: requireTimestamp(manifest.created_at, "created_at"),
    event_sequence: requireSchemaNonNegativeInteger(manifest.event_sequence, "event_sequence"),
    expected_node_ids: requireSchemaStringArray(
      manifest.expected_node_ids,
      "expected_node_ids",
    ),
    gate_decision_ids: requireSchemaStringArray(
      manifest.gate_decision_ids,
      "gate_decision_ids",
    ),
    layer_index: requireSchemaNonNegativeInteger(manifest.layer_index, "layer_index"),
    pending_effect_ids: requireSchemaStringArray(
      manifest.pending_effect_ids,
      "pending_effect_ids",
    ),
    replay_verified: manifest.replay_verified,
    run_id: requireSchemaString(manifest.run_id, "run_id", { minLength: 1 }),
    state_hash: stateHash,
    terminal_node_ids: requireSchemaStringArray(
      manifest.terminal_node_ids,
      "terminal_node_ids",
    ),
  };
  const recomputed = sha256SchedulerJson(canonicalizeSchedulerJson(semantic));
  if (asserted !== recomputed) {
    fail("CHECKPOINT_HASH_MISMATCH", "checkpoint_hash does not match canonical content");
  }
  return freezeCheckpointManifest({ ...semantic, checkpoint_hash: asserted });
}

/** Pause a run: admission stops, in-flight attempts and effects are preserved. */
export function pauseRun({ scheduler, run_id: runId, plan, budget_envelope: budget, checkpoint_id: checkpointId, layer_index: layerIndex, created_at: createdAt, reason }) {
  requireText(reason, "reason");
  const sealed = sealCheckpoint({
    scheduler,
    run_id: runId,
    plan,
    budget_envelope: budget,
    checkpoint_id: checkpointId,
    layer_index: layerIndex,
    created_at: createdAt,
  });
  return Object.freeze({
    ...sealed,
    admission_open: false,
    in_flight_attempts: sealed.pending_effects,
    reason,
    state: "PAUSED",
  });
}

/**
 * Resume from a reviewed checkpoint.
 *
 * A checkpoint may resume only when an independent review APPROVED it, the
 * reviewer is not the author, the stored manifest self-hash holds, and the
 * command log replays to the exact recorded state hash and projections.
 */
export function resumeFromCheckpoint({
  manifest,
  commands,
  plan,
  budget_envelope: budget,
  review,
}) {
  const sealed = validateCheckpointManifest(manifest);
  if (!Array.isArray(commands)) {
    fail("CHECKPOINT_INPUT_INVALID", "commands must be an array");
  }
  requireObject(review, "review");
  const decision = requireText(review.decision, "review.decision");
  if (!REVIEW_DECISIONS.includes(decision)) {
    fail("CHECKPOINT_REVIEW_INVALID", "review decision is outside the canonical vocabulary");
  }
  if (decision !== "APPROVE") {
    fail("CHECKPOINT_REVIEW_REJECTED", "resume requires an approved checkpoint review");
  }
  const reviewer = requireText(review.reviewer_id, "review.reviewer_id");
  const author = requireText(review.author_id, "review.author_id");
  if (reviewer === author) {
    fail("CHECKPOINT_REVIEW_NOT_INDEPENDENT", "a checkpoint author cannot approve its own resume");
  }
  if (requireText(review.checkpoint_hash, "review.checkpoint_hash") !== sealed.checkpoint_hash) {
    fail("CHECKPOINT_REVIEW_BINDING_INVALID", "the review does not bind this checkpoint hash");
  }
  if (sealed.replay_verified !== true) {
    fail("CHECKPOINT_NOT_REPLAY_VERIFIED", "an unverified checkpoint cannot resume");
  }
  if (commands.length !== sealed.event_sequence) {
    fail("CHECKPOINT_COMMAND_COUNT_MISMATCH", "command log length differs from the sealed sequence", {
      recorded: sealed.event_sequence,
      supplied: commands.length,
    });
  }

  const replay = replayEvidence({
    run_id: sealed.run_id,
    plan,
    budget_envelope: budget,
    commands,
  });
  if (replay.rebuilt_state_hash !== sealed.state_hash) {
    fail("CHECKPOINT_REPLAY_DIVERGED", "resume replay did not reproduce the sealed state", {
      rebuilt_state_hash: replay.rebuilt_state_hash,
      sealed_state_hash: sealed.state_hash,
    });
  }
  const manifestProjections = {
    expected_node_ids: sealed.expected_node_ids,
    pending_effect_ids: sealed.pending_effect_ids,
    terminal_node_ids: sealed.terminal_node_ids,
  };
  const derivedProjections = deriveCheckpointProjections({
    snapshot: replay.snapshot,
    plan,
  });
  const mismatchedFields = Object.keys(manifestProjections).filter(
    (field) => !equalStringArrays(manifestProjections[field], derivedProjections[field]),
  );
  if (mismatchedFields.length > 0) {
    fail(
      "CHECKPOINT_PROJECTION_MISMATCH",
      "checkpoint projections do not match the replay-derived scheduler state",
      {
        derived: derivedProjections,
        manifest: manifestProjections,
        mismatched_fields: mismatchedFields,
      },
    );
  }

  const scheduler = createDagScheduler({
    run_id: sealed.run_id,
    plan,
    budget_envelope: budget,
  });
  for (const command of commands) {
    scheduler[command.operation](command.input);
  }
  if (scheduler.snapshot().state_hash !== sealed.state_hash) {
    fail("CHECKPOINT_REPLAY_DIVERGED", "rebuilt scheduler state does not match the checkpoint");
  }
  return Object.freeze({
    manifest: sealed,
    resumed_state_hash: sealed.state_hash,
    scheduler,
    state: "RUNNING",
  });
}

/**
 * Cancel a run and reconcile its effects.
 *
 * Every pending effect must resolve to a terminal EffectReceipt status.  A
 * receipt-less or UNKNOWN effect leaves the run in
 * CANCELLED_WITH_UNRESOLVED_EFFECTS: cancellation never claims a clean stop
 * over an effect whose outcome is unknown.
 */
export function cancelRun({
  scheduler,
  run_id: runId,
  plan,
  budget_envelope: budget,
  checkpoint_id: checkpointId,
  layer_index: layerIndex,
  created_at: createdAt,
  reason,
  effect_receipts: effectReceipts = [],
}) {
  requireText(reason, "reason");
  if (!Array.isArray(effectReceipts)) {
    fail("CHECKPOINT_INPUT_INVALID", "effect_receipts must be an array");
  }
  const sealed = sealCheckpoint({
    scheduler,
    run_id: runId,
    plan,
    budget_envelope: budget,
    checkpoint_id: checkpointId,
    layer_index: layerIndex,
    created_at: createdAt,
  });

  const receiptsByEffect = new Map();
  for (const [index, receipt] of effectReceipts.entries()) {
    requireObject(receipt, `effect_receipts[${index}]`);
    const effectId = requireText(receipt.effect_id, `effect_receipts[${index}].effect_id`);
    const status = requireText(receipt.status, `effect_receipts[${index}].status`);
    if (!["SUCCEEDED", "FAILED", "ROLLED_BACK", "NOT_EXECUTED", "UNKNOWN"].includes(status)) {
      fail("EFFECT_RECEIPT_INVALID", `effect_receipts[${index}].status is not canonical`);
    }
    const reconciliationRequired = receipt.reconciliation_required;
    if (typeof reconciliationRequired !== "boolean") {
      fail(
        "EFFECT_RECEIPT_INVALID",
        `effect_receipts[${index}].reconciliation_required must be boolean`,
      );
    }
    const receiptId = requireText(receipt.receipt_id, `effect_receipts[${index}].receipt_id`);
    if (receiptsByEffect.has(effectId)) {
      fail("EFFECT_RECEIPT_INVALID", `duplicate receipt for effect ${effectId}`);
    }
    receiptsByEffect.set(effectId, {
      receipt_id: receiptId,
      reconciliation_required: reconciliationRequired,
      status,
    });
  }
  for (const effectId of receiptsByEffect.keys()) {
    if (!sealed.manifest.pending_effect_ids.includes(effectId)) {
      fail("EFFECT_RECEIPT_UNKNOWN_EFFECT", `receipt targets an effect outside this run: ${effectId}`);
    }
  }
  const receiptIds = new Set();
  for (const { receipt_id: receiptId } of receiptsByEffect.values()) {
    if (receiptIds.has(receiptId)) {
      fail("EFFECT_RECEIPT_INVALID", `duplicate receipt id ${receiptId}`);
    }
    receiptIds.add(receiptId);
  }

  const reconciled = [];
  const unresolved = [];
  for (const effectId of sealed.manifest.pending_effect_ids) {
    const receipt = receiptsByEffect.get(effectId);
    if (receipt === undefined) {
      unresolved.push({ effect_id: effectId, reason: "NO_RESOLVING_RECEIPT" });
    } else if (receipt.status === "UNKNOWN") {
      unresolved.push({ effect_id: effectId, reason: "RECEIPT_STATUS_UNKNOWN" });
    } else if (receipt.reconciliation_required === true) {
      unresolved.push({ effect_id: effectId, reason: "RECEIPT_RECONCILIATION_REQUIRED" });
    } else {
      reconciled.push({ effect_id: effectId, receipt_id: receipt.receipt_id, status: receipt.status });
    }
  }

  const outcome = unresolved.length === 0 ? "CANCELLED" : "CANCELLED_WITH_UNRESOLVED_EFFECTS";
  return Object.freeze({
    manifest: sealed.manifest,
    outcome,
    pending_effect_ids: sealed.manifest.pending_effect_ids,
    reason,
    reconciled_effects: Object.freeze(reconciled),
    state: outcome,
    unresolved_effects: Object.freeze(unresolved),
  });
}
