import assert from "node:assert/strict";
import test from "node:test";

import {
  computeActionIntentHash,
  computeEffectReceiptHash,
} from "../../effects/effect-coordinator.mjs";
import { computeEventHash } from "../../ledger/noetic-ledger.mjs";

import {
  MemoryLifecycleError,
  applyMemoryLifecycleRequest,
  canonicalMemoryLifecycleJson,
  sealLegalHold,
  sealMemoryLifecyclePolicy,
  sealMemoryLifecycleRequest,
  validateLegalHold,
  validateMemoryLifecycleOutcome,
  validateMemoryLifecyclePolicy,
  validateMemoryLifecycleRequest,
} from "./index.mjs";
import {
  FIXED_AT,
  PREVIOUS_EVENT_HASH,
  legalHold,
  lifecycleApplication,
  lifecyclePolicy,
  lifecycleRequest,
  lifecycleState,
  textHash,
} from "./memory-lifecycle-test-support.mjs";

const errorCode = (code) => (error) =>
  error instanceof MemoryLifecycleError && error.code === code;

test("forget_legal_hold_test: forget creates a new immutable revision, event, and resolving receipt", () => {
  const input = lifecycleApplication();
  const before = structuredClone(input);
  const result = applyMemoryLifecycleRequest(input);
  assert.deepEqual(input, before);
  assert.equal(result.decision, "APPLIED");
  assert.equal(result.state_changed, true);
  assert.equal(result.new_state.status, "FORGOTTEN");
  assert.equal(result.new_state.revision, 5);
  assert.equal(result.new_state.canonical_artifact_id, null);
  assert.equal(result.new_state.content, null);
  assert.equal(result.new_state.source_hash, null);
  assert.equal(result.event_record.event_type, "memory.lifecycle.applied");
  assert.equal(result.event_record.previous_event_hash, PREVIOUS_EVENT_HASH);
  assert.equal(result.effect_receipt.status, "SUCCEEDED");
  assert.equal(result.effect_receipt.reconciliation_required, false);
  assert.match(result.outcome_id, /^MLO-[0-9a-f]{64}$/u);
  assert.deepEqual(validateMemoryLifecycleOutcome(result), result);
  assert.ok(Object.isFrozen(result));
});

test("forget_legal_hold_test: delete uses a distinct terminal status without retaining a forbidden tombstone hash", () => {
  const request = lifecycleRequest({ action_type: "DELETE_MEMORY", request_id: "REQ-L03-DELETE" });
  const result = applyMemoryLifecycleRequest(lifecycleApplication({ request }));
  assert.equal(result.new_state.status, "DELETED");
  assert.equal(result.payload.retained_tombstone_hash, null);
  assert.equal(result.new_state.source_hash, null);
  assert.equal(result.action_intent.action_type, "delete_memory");
});

test("forget_legal_hold_test: a non-reversible tombstone hash is retained only with explicit policy-and-law authority", () => {
  const state = lifecycleState();
  const policy = lifecyclePolicy({
    tombstone_hash_retention: "PERMITTED_BY_POLICY_AND_LAW",
    tombstone_authority_record_id: "AUTH-L03-TOMBSTONE",
  });
  const result = applyMemoryLifecycleRequest(lifecycleApplication({ state, policy }));
  assert.equal(result.payload.retained_tombstone_hash, state.source_hash);
  assert.equal(result.new_state.source_hash, state.source_hash);
  assert.equal(result.new_state.content, null);
  assert.equal(result.new_state.canonical_artifact_id, null);
});

test("forget_legal_hold_test: tombstone retention permission requires an authority record", () => {
  assert.throws(
    () => sealMemoryLifecyclePolicy({
      policy_id: "MLP-L03-BAD",
      workspace_id: "WS-L03-001",
      permitted_actions: ["FORGET_MEMORY"],
      tombstone_hash_retention: "PERMITTED_BY_POLICY_AND_LAW",
      tombstone_authority_record_id: null,
      effective_at: "2026-01-01T00:00:00.000Z",
    }),
    errorCode("MEMORY_LIFECYCLE_POLICY_INVALID"),
  );
  assert.throws(
    () => sealMemoryLifecyclePolicy({
      policy_id: "MLP-L03-BAD",
      workspace_id: "WS-L03-001",
      permitted_actions: ["FORGET_MEMORY"],
      tombstone_hash_retention: "PROHIBITED",
      tombstone_authority_record_id: "AUTH-L03-UNAUTHORIZED",
      effective_at: "2026-01-01T00:00:00.000Z",
    }),
    errorCode("MEMORY_LIFECYCLE_POLICY_INVALID"),
  );
});

test("forget_legal_hold_test: active matching legal hold blocks the effect and preserves source state", () => {
  const state = lifecycleState();
  const result = applyMemoryLifecycleRequest(lifecycleApplication({
    state,
    legal_holds: [legalHold()],
  }));
  assert.equal(result.decision, "BLOCKED_LEGAL_HOLD");
  assert.equal(result.state_changed, false);
  assert.deepEqual(result.new_state, state);
  assert.deepEqual(result.blocking_hold_ids, ["HOLD-L03-001"]);
  assert.equal(result.event_record.event_type, "memory.lifecycle.blocked_by_legal_hold");
  assert.equal(result.effect_receipt.status, "NOT_EXECUTED");
  assert.deepEqual(result.effect_receipt.result_artifact_ids, []);
  assert.equal(result.effect_receipt.error_artifact_ids.length, 1);
  assert.equal(result.effect_receipt.observed_state_hash, state.state_hash);
});

test("forget_legal_hold_test: expired, future, and nonmatching holds do not block", () => {
  const expired = legalHold({
    hold_id: "HOLD-L03-EXPIRED",
    starts_at: "2026-01-01T00:00:00.000Z",
    expires_at: "2026-07-31T00:59:59.999Z",
  });
  const future = legalHold({
    hold_id: "HOLD-L03-FUTURE",
    starts_at: "2026-08-01T00:00:00.000Z",
    expires_at: "2026-09-01T00:00:00.000Z",
  });
  const otherWorkspace = legalHold({
    hold_id: "HOLD-L03-OTHER",
    scope: { workspace_id: "WS-L03-OTHER", memory_ids: [], memory_classes: [] },
  });
  const result = applyMemoryLifecycleRequest(lifecycleApplication({
    legal_holds: [future, otherWorkspace, expired],
  }));
  assert.equal(result.decision, "APPLIED");
  assert.deepEqual(result.blocking_hold_ids, []);
});

test("forget_legal_hold_test: class-scoped and workspace-scoped holds are deterministic", () => {
  const classHold = legalHold({
    hold_id: "HOLD-L03-CLASS",
    scope: { workspace_id: "WS-L03-001", memory_ids: [], memory_classes: ["WORKSPACE"] },
  });
  const workspaceHold = legalHold({
    hold_id: "HOLD-L03-ALL",
    scope: { workspace_id: "WS-L03-001", memory_ids: [], memory_classes: [] },
  });
  const result = applyMemoryLifecycleRequest(lifecycleApplication({ legal_holds: [classHold, workspaceHold] }));
  assert.deepEqual(result.blocking_hold_ids, ["HOLD-L03-ALL", "HOLD-L03-CLASS"]);
});

test("forget_legal_hold_test: legal holds must be explicitly time-bounded and hash-sealed", () => {
  assert.throws(
    () => sealLegalHold({
      hold_id: "HOLD-L03-BAD",
      scope: { workspace_id: "WS-L03-001", memory_ids: [], memory_classes: [] },
      authority_record_id: "AUTH-L03-001",
      reason: "invalid interval",
      starts_at: "2026-08-01T00:00:00.000Z",
      expires_at: "2026-08-01T00:00:00.000Z",
    }),
    errorCode("LEGAL_HOLD_NOT_TIME_BOUNDED"),
  );
  const tampered = structuredClone(legalHold());
  tampered.reason = "tampered reason";
  assert.throws(() => validateLegalHold(tampered), errorCode("LEGAL_HOLD_HASH_MISMATCH"));
});

test("forget_legal_hold_test: same request replay returns the exact prior immutable outcome", () => {
  const input = lifecycleApplication();
  const first = applyMemoryLifecycleRequest(input);
  const replay = applyMemoryLifecycleRequest({ ...input, prior_outcomes: [first] });
  assert.deepEqual(replay, first);
  assert.equal(replay.outcome_id, first.outcome_id);
  assert.equal(replay.event_record.event_id, first.event_record.event_id);
  assert.equal(replay.effect_receipt.receipt_id, first.effect_receipt.receipt_id);
});

test("forget_legal_hold_test: idempotency key reuse with a different request fails closed", () => {
  const input = lifecycleApplication();
  const first = applyMemoryLifecycleRequest(input);
  const conflicting = lifecycleRequest({
    request_id: "REQ-L03-CONFLICT",
    action_type: "DELETE_MEMORY",
    idempotency_key: input.request.idempotency_key,
  });
  assert.throws(
    () => applyMemoryLifecycleRequest({ ...input, request: conflicting, prior_outcomes: [first] }),
    errorCode("MEMORY_LIFECYCLE_IDEMPOTENCY_CONFLICT"),
  );
});

test("forget_legal_hold_test: revision mismatch and target mismatch fail closed", () => {
  assert.throws(
    () => applyMemoryLifecycleRequest(lifecycleApplication({
      request: lifecycleRequest({ expected_revision: 3 }),
    })),
    errorCode("MEMORY_LIFECYCLE_REVISION_CONFLICT"),
  );
  assert.throws(
    () => applyMemoryLifecycleRequest(lifecycleApplication({
      request: lifecycleRequest({ memory_id: "MEM-L03-OTHER" }),
    })),
    errorCode("MEMORY_LIFECYCLE_TARGET_MISMATCH"),
  );
});

test("forget_legal_hold_test: action and workspace policy boundaries fail closed", () => {
  assert.throws(
    () => applyMemoryLifecycleRequest(lifecycleApplication({
      request: lifecycleRequest({ action_type: "DELETE_MEMORY" }),
      policy: lifecyclePolicy({ permitted_actions: ["FORGET_MEMORY"] }),
    })),
    errorCode("MEMORY_LIFECYCLE_ACTION_DENIED"),
  );
  assert.throws(
    () => applyMemoryLifecycleRequest(lifecycleApplication({
      policy: lifecyclePolicy({ workspace_id: "WS-L03-OTHER" }),
    })),
    errorCode("MEMORY_LIFECYCLE_POLICY_SCOPE_MISMATCH"),
  );
});

test("forget_legal_hold_test: a future policy is not silently applied", () => {
  assert.throws(
    () => applyMemoryLifecycleRequest(lifecycleApplication({
      policy: lifecyclePolicy({ effective_at: "2026-08-01T00:00:00.000Z" }),
    })),
    errorCode("MEMORY_LIFECYCLE_POLICY_NOT_EFFECTIVE"),
  );
});

test("forget_legal_hold_test: a new request cannot rewrite an immutable terminal revision", () => {
  const first = applyMemoryLifecycleRequest(lifecycleApplication());
  const nextRequest = lifecycleRequest({
    request_id: "REQ-L03-002",
    idempotency_key: "IDEMP-L03-002",
    expected_revision: 5,
    event_sequence: 3,
    previous_event_hash: first.event_record.event_hash,
  });
  assert.throws(
    () => applyMemoryLifecycleRequest(lifecycleApplication({
      request: nextRequest,
      state: first.new_state,
    })),
    errorCode("MEMORY_LIFECYCLE_STATE_NOT_ACTIVE"),
  );
});

test("forget_legal_hold_test: index or cache eviction cannot masquerade as canonical forgetting", () => {
  assert.throws(
    () => sealMemoryLifecycleRequest({
      request_id: "REQ-L03-CACHE",
      run_id: "RUN-L03-001",
      memory_id: "MEM-L03-001",
      workspace_id: "WS-L03-001",
      action_type: "FORGET_MEMORY",
      target_kind: "INDEX_CACHE",
      expected_revision: 4,
      actor_id: "ACT-L03-001",
      reason: "cache cleanup",
      approval_record_ids: [],
      requested_at: FIXED_AT,
      idempotency_key: "IDEMP-L03-CACHE",
      event_sequence: 2,
      previous_event_hash: PREVIOUS_EVENT_HASH,
    }),
    errorCode("DERIVED_CACHE_NOT_CANONICAL_MEMORY"),
  );
});

test("forget_legal_hold_test: first event and previous-event hash semantics are exact", () => {
  const first = lifecycleRequest({ event_sequence: 1, previous_event_hash: null });
  assert.equal(first.event_sequence, 1);
  assert.equal(first.previous_event_hash, null);
  assert.throws(
    () => sealMemoryLifecycleRequest({
      ...lifecycleRequest(),
      event_sequence: 1,
      previous_event_hash: PREVIOUS_EVENT_HASH,
      request_hash: undefined,
    }),
    errorCode("MEMORY_LIFECYCLE_REQUEST_INVALID"),
  );
});

test("forget_legal_hold_test: request, policy, and outcome hashes reject tampering", () => {
  const requestTamper = structuredClone(lifecycleRequest());
  requestTamper.reason = "different";
  assert.throws(() => validateMemoryLifecycleRequest(requestTamper), errorCode("MEMORY_LIFECYCLE_REQUEST_HASH_MISMATCH"));
  const policyTamper = structuredClone(lifecyclePolicy());
  policyTamper.workspace_id = "WS-L03-OTHER";
  assert.throws(() => validateMemoryLifecyclePolicy(policyTamper), errorCode("MEMORY_LIFECYCLE_POLICY_HASH_MISMATCH"));
  const outcomeTamper = structuredClone(applyMemoryLifecycleRequest(lifecycleApplication()));
  outcomeTamper.outcome_hash = textHash("tampered");
  assert.throws(() => validateMemoryLifecycleOutcome(outcomeTamper), errorCode("MEMORY_LIFECYCLE_OUTCOME_HASH_MISMATCH"));
});

test("forget_legal_hold_test: canonical ActionIntent, EventRecord, and EffectReceipt fields are complete", () => {
  const result = applyMemoryLifecycleRequest(lifecycleApplication());
  assert.deepEqual(Object.keys(result.action_intent), [
    "action_type", "approval_record_ids", "arguments_artifact_id", "arguments_hash",
    "created_at", "idempotency_key", "intent_hash", "intent_id", "node_id",
    "required_capabilities", "risk_class", "run_id", "target_ref",
  ]);
  assert.deepEqual(result.action_intent.required_capabilities, ["database_write"]);
  assert.deepEqual(Object.keys(result.event_record), [
    "actor_id", "aggregate_id", "aggregate_type", "event_hash", "event_id", "event_type",
    "occurred_at", "payload_artifact_id", "payload_hash", "previous_event_hash", "run_id",
    "schema_version", "sequence",
  ]);
  assert.deepEqual(Object.keys(result.effect_receipt), [
    "error_artifact_ids", "external_operation_id", "finished_at", "idempotency_key", "intent_id",
    "observed_state_hash", "receipt_hash", "receipt_id", "reconciliation_required",
    "result_artifact_ids", "run_id", "started_at", "status",
  ]);
});

test("forget_legal_hold_test: legal-hold input order does not change the outcome", () => {
  const firstHold = legalHold({ hold_id: "HOLD-L03-A" });
  const secondHold = legalHold({ hold_id: "HOLD-L03-B" });
  const left = applyMemoryLifecycleRequest(lifecycleApplication({ legal_holds: [firstHold, secondHold] }));
  const right = applyMemoryLifecycleRequest(lifecycleApplication({ legal_holds: [secondHold, firstHold] }));
  assert.deepEqual(right, left);
  assert.deepEqual(left.blocking_hold_ids, ["HOLD-L03-A", "HOLD-L03-B"]);
});

test("forget_legal_hold_test: duplicate hold IDs and duplicate prior keys fail closed", () => {
  assert.throws(
    () => applyMemoryLifecycleRequest(lifecycleApplication({ legal_holds: [legalHold(), legalHold()] })),
    errorCode("DUPLICATE_LEGAL_HOLD"),
  );
  const first = applyMemoryLifecycleRequest(lifecycleApplication());
  assert.throws(
    () => applyMemoryLifecycleRequest(lifecycleApplication({ prior_outcomes: [first, first] })),
    errorCode("DUPLICATE_LIFECYCLE_IDEMPOTENCY_KEY"),
  );
});

test("forget_legal_hold_test: proxies, accessors, and extra fields fail closed", () => {
  const input = lifecycleApplication();
  assert.throws(
    () => applyMemoryLifecycleRequest(new Proxy(input, {})),
    errorCode("MEMORY_LIFECYCLE_INPUT_INVALID"),
  );
  const request = structuredClone(lifecycleRequest());
  Object.defineProperty(request, "reason", { enumerable: true, get: () => "hidden" });
  assert.throws(() => validateMemoryLifecycleRequest(request), errorCode("MEMORY_LIFECYCLE_REQUEST_INVALID"));
  assert.throws(
    () => applyMemoryLifecycleRequest({ ...input, fallback: true }),
    errorCode("MEMORY_LIFECYCLE_INPUT_INVALID"),
  );
});

test("forget_legal_hold_test: sealed policy and hold replay canonically", () => {
  const policy = lifecyclePolicy();
  const hold = legalHold();
  assert.deepEqual(validateMemoryLifecyclePolicy(policy), policy);
  assert.deepEqual(validateLegalHold(hold), hold);
  assert.match(policy.policy_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.match(hold.hold_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("forget_legal_hold_test: emitted hashes match canonical effect and ledger authorities", () => {
  const result = applyMemoryLifecycleRequest(lifecycleApplication());
  assert.equal(result.action_intent.intent_hash, computeActionIntentHash(result.action_intent));
  assert.equal(result.event_record.event_hash, computeEventHash(result.event_record));
  assert.equal(result.effect_receipt.receipt_hash, computeEffectReceiptHash(result.effect_receipt));
});

test("forget_legal_hold_test: replay rejects a different sealed lifecycle policy", () => {
  const input = lifecycleApplication();
  const first = applyMemoryLifecycleRequest(input);
  const differentPolicy = lifecyclePolicy({
    policy_id: "MLP-L03-DIFFERENT",
    effective_at: "2026-02-01T00:00:00.000Z",
  });
  assert.throws(
    () => applyMemoryLifecycleRequest({
      ...input,
      policy: differentPolicy,
      prior_outcomes: [first],
    }),
    errorCode("MEMORY_LIFECYCLE_REPLAY_DIVERGENCE"),
  );
});

test("forget_legal_hold_test: replay rejects a different memory lineage", () => {
  const input = lifecycleApplication();
  const first = applyMemoryLifecycleRequest(input);
  const differentState = lifecycleState({ content: "different canonical memory content" });
  assert.throws(
    () => applyMemoryLifecycleRequest({
      ...input,
      state: differentState,
      prior_outcomes: [first],
    }),
    errorCode("MEMORY_LIFECYCLE_REPLAY_DIVERGENCE"),
  );
  assert.notEqual(differentState.state_hash, first.previous_state_hash);
  assert.match(canonicalMemoryLifecycleJson(first), /^\{/u);
});
