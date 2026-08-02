import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  EFFECT_EVENT_TYPES,
  EFFECT_RECORD_TYPES,
  EffectCoordinatorError,
  createEffectCoordinator,
  sealEffectReceipt,
} from "./effect-coordinator.mjs";
import {
  createEffectFixture,
  createIntentFixture,
  createReceiptFixture,
  digestBytes,
  fixedEffectTimestamp,
  putEffectArtifact,
} from "./effect-test-support.mjs";

const expectCode = (code) => (error) =>
  error instanceof EffectCoordinatorError && error.code === code;

test("effect_reconciliation_test: UNKNOWN blocks retry until an observed reconciliation resolves it", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore);
  assert.equal(fixture.coordinator.registerIntent(intent).status, "REGISTERED");

  const started = fixture.coordinator.beginAttempt({
    attempt_id: "ATTEMPT-E02-0001",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(1),
  });
  assert.equal(started.status, "STARTED");
  assert.equal(started.execute_permitted, true);

  const unknown = createReceiptFixture({
    attempt: started.attempt,
    finishedAt: fixedEffectTimestamp(2),
    intent,
    receiptId: "EFF-E02-UNKNOWN-0001",
    status: "UNKNOWN",
  });
  const recorded = fixture.coordinator.recordReceipt({
    attempt_id: started.attempt.attempt_id,
    receipt: unknown,
  });
  assert.equal(recorded.outcome.status, "RECONCILING");
  assert.equal(recorded.outcome.completion_proven, false);
  assert.equal(recorded.outcome.retry_permitted, false);
  assert.throws(
    () =>
      fixture.coordinator.beginAttempt({
        attempt_id: "ATTEMPT-E02-BLIND-RETRY",
        intent_id: intent.intent_id,
        started_at: fixedEffectTimestamp(3),
      }),
    expectCode("EFFECT_RECONCILIATION_REQUIRED"),
  );

  const resultId = "ART-E02-RESULT-0001";
  putEffectArtifact(fixture.artifactStore, {
    actionIntentId: intent.intent_id,
    artifactId: resultId,
    bytes: Buffer.from(JSON.stringify({ effect: "confirmed" }), "utf8"),
    receiptId: "AR-E02-RESULT-0001",
    timestamp: fixedEffectTimestamp(3),
  });
  const resolved = createReceiptFixture({
    attempt: started.attempt,
    externalOperationId: "external-operation-0001",
    finishedAt: fixedEffectTimestamp(4),
    intent,
    receiptId: "EFF-E02-RESOLVED-0001",
    resultArtifactIds: [resultId],
    status: "SUCCEEDED",
  });
  const reconciliation = fixture.coordinator.reconcile({
    attempt_id: started.attempt.attempt_id,
    receipt: resolved,
  });
  assert.equal(reconciliation.outcome.status, "SUCCEEDED");
  assert.equal(reconciliation.outcome.completion_proven, true);
  assert.equal(reconciliation.outcome.retry_permitted, false);
  assert.deepEqual(fixture.coordinator.verify(intent.intent_id), {
    attempt_count: 1,
    completion_proven: true,
    effect_status: "SUCCEEDED",
    intent_hash_verified: true,
    ledger_event_count: 4,
    outcome_resolved: true,
    receipt_count: 2,
    receipt_hashes_verified: 2,
    reconciliation_required: false,
    run_id: intent.run_id,
  });
});

test("effect_reconciliation_test: crash before receipt is unresolved, not narrated failure or success", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-CRASH",
    idempotencyKey: "RUN-E02-0001:crash:1",
  });
  fixture.coordinator.registerIntent(intent);
  const first = fixture.coordinator.beginAttempt({
    attempt_id: "ATTEMPT-E02-CRASH-1",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(5),
  });

  const interrupted = fixture.coordinator.inspect(intent.intent_id);
  assert.equal(interrupted.status, "RECONCILING");
  assert.equal(interrupted.effect_status, "UNKNOWN");
  assert.equal(interrupted.receipt, null);
  assert.equal(interrupted.completion_proven, false);
  assert.equal(interrupted.retry_permitted, false);

  const noEffect = createReceiptFixture({
    attempt: first.attempt,
    finishedAt: fixedEffectTimestamp(6),
    intent,
    observedStateHash: digestBytes(Buffer.from("external-state:no-effect", "utf8")),
    receiptId: "EFF-E02-NOT-EXECUTED",
    status: "NOT_EXECUTED",
  });
  const reconciled = fixture.coordinator.reconcile({
    attempt_id: first.attempt.attempt_id,
    receipt: noEffect,
  });
  assert.equal(reconciled.outcome.status, "NOT_EXECUTED");
  assert.equal(reconciled.outcome.retry_permitted, true);

  const second = fixture.coordinator.beginAttempt({
    attempt_id: "ATTEMPT-E02-CRASH-2",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(7),
  });
  assert.equal(second.attempt.attempt_number, 2);
  assert.equal(second.execute_permitted, true);
  assert.deepEqual(
    fixture.coordinator.readAttempts(intent.intent_id).map((attempt) => attempt.attempt_id),
    ["ATTEMPT-E02-CRASH-1", "ATTEMPT-E02-CRASH-2"],
  );
});

test("effect_reconciliation_test: executor narration cannot replace an evidence-bound EffectReceipt", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-NARRATION",
    idempotencyKey: "RUN-E02-0001:narration:1",
  });
  fixture.coordinator.registerIntent(intent);
  const started = fixture.coordinator.beginAttempt({
    attempt_id: "ATTEMPT-E02-NARRATION",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(8),
  });
  const narratedResult = {
    status: "SUCCEEDED",
    message: "the executor says the effect completed",
  };
  assert.equal(narratedResult.status, "SUCCEEDED");
  assert.equal(fixture.coordinator.inspect(intent.intent_id).completion_proven, false);

  const unsealedReceipt = {
    receipt_id: "EFF-E02-NARRATION",
    intent_id: intent.intent_id,
    run_id: intent.run_id,
    external_operation_id: null,
    status: "SUCCEEDED",
    result_artifact_ids: [],
    error_artifact_ids: [],
    observed_state_hash: null,
    idempotency_key: intent.idempotency_key,
    started_at: started.attempt.started_at,
    finished_at: fixedEffectTimestamp(9),
    reconciliation_required: false,
  };
  assert.throws(
    () =>
      fixture.coordinator.recordReceipt({
        attempt_id: started.attempt.attempt_id,
        receipt: unsealedReceipt,
      }),
    expectCode("EFFECT_RECEIPT_INVALID"),
  );
  assert.throws(
    () => sealEffectReceipt(unsealedReceipt),
    expectCode("EFFECT_RECEIPT_RESOLUTION_EVIDENCE_REQUIRED"),
  );
  assert.equal(fixture.coordinator.readReceipts(intent.intent_id).length, 0);
  assert.equal(fixture.coordinator.inspect(intent.intent_id).completion_proven, false);
});

test("effect_reconciliation_test: a durable receipt missing its ledger event is not completion", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-EVENT-CRASH",
    idempotencyKey: "RUN-E02-0001:event-crash:1",
  });
  fixture.coordinator.registerIntent(intent);
  const started = fixture.coordinator.beginAttempt({
    attempt_id: "ATTEMPT-E02-EVENT-CRASH",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(10),
  });
  const resultId = "ART-E02-EVENT-CRASH-RESULT";
  putEffectArtifact(fixture.artifactStore, {
    actionIntentId: intent.intent_id,
    artifactId: resultId,
    receiptId: "AR-E02-EVENT-CRASH-RESULT",
    timestamp: fixedEffectTimestamp(11),
  });
  const receipt = createReceiptFixture({
    attempt: started.attempt,
    finishedAt: fixedEffectTimestamp(12),
    intent,
    receiptId: "EFF-E02-EVENT-CRASH",
    resultArtifactIds: [resultId],
    status: "SUCCEEDED",
  });

  const interruptedLedger = {
    append(input) {
      if (input.event_type === EFFECT_EVENT_TYPES.EFFECT_RECEIPT) {
        const error = new Error("synthetic crash before ledger publication");
        error.code = "SYNTHETIC_LEDGER_INTERRUPTION";
        throw error;
      }
      return fixture.ledger.append(input);
    },
    readEvents: fixture.ledger.readEvents.bind(fixture.ledger),
    verifyRun: fixture.ledger.verifyRun.bind(fixture.ledger),
  };
  const interruptedCoordinator = createEffectCoordinator({
    artifactStore: fixture.artifactStore,
    ledger: interruptedLedger,
    stateStore: fixture.stateStore,
  });
  assert.throws(
    () =>
      interruptedCoordinator.recordReceipt({
        attempt_id: started.attempt.attempt_id,
        receipt,
      }),
    expectCode("EFFECT_EVENT_PUBLICATION_FAILED"),
  );

  const pending = fixture.coordinator.inspect(intent.intent_id);
  assert.equal(pending.status, "PENDING_EVENT_RECONCILIATION");
  assert.equal(pending.completion_proven, false);
  assert.equal(pending.event_reconciliation_required, true);
  assert.throws(
    () => fixture.coordinator.verify(intent.intent_id),
    expectCode("EFFECT_EVENT_RECONCILIATION_REQUIRED"),
  );

  const replay = fixture.coordinator.recordReceipt({
    attempt_id: started.attempt.attempt_id,
    receipt,
  });
  assert.equal(replay.status, "EXISTING");
  assert.equal(replay.outcome.completion_proven, true);
  assert.equal(fixture.coordinator.verify(intent.intent_id).ledger_event_count, 3);
});

test("effect_reconciliation_test: receipt mutation and cross-intent binding fail closed", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-TAMPER",
    idempotencyKey: "RUN-E02-0001:tamper:1",
  });
  fixture.coordinator.registerIntent(intent);
  const started = fixture.coordinator.beginAttempt({
    attempt_id: "ATTEMPT-E02-TAMPER",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(13),
  });
  const failed = createReceiptFixture({
    attempt: started.attempt,
    errorArtifactIds: [],
    externalOperationId: "external-operation-tamper",
    finishedAt: fixedEffectTimestamp(14),
    intent,
    observedStateHash: digestBytes(Buffer.from("external-state:failed", "utf8")),
    receiptId: "EFF-E02-TAMPER",
    status: "FAILED",
  });
  fixture.coordinator.recordReceipt({ attempt_id: started.attempt.attempt_id, receipt: failed });
  const mutation = fixture.stateStore.compareAndSwapRevision({
    recordType: EFFECT_RECORD_TYPES.EFFECT_RECEIPT,
    recordId: failed.receipt_id,
    expectedRevision: 0,
    value: failed,
  });
  assert.equal(mutation.ok, true);
  assert.throws(
    () => fixture.coordinator.inspect(intent.intent_id),
    expectCode("EFFECT_RECORD_MUTATED"),
  );
});

test("effect_reconciliation_test: attempt chronology cannot precede intent or prior reconciliation", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    createdAt: fixedEffectTimestamp(33),
    intentId: "INTENT-E02-CHRONOLOGY",
    idempotencyKey: "RUN-E02-0001:chronology:1",
  });
  fixture.coordinator.registerIntent(intent);
  assert.throws(
    () =>
      fixture.coordinator.beginAttempt({
        attempt_id: "ATTEMPT-E02-BEFORE-INTENT",
        intent_id: intent.intent_id,
        started_at: fixedEffectTimestamp(32),
      }),
    expectCode("ATTEMPT_CHRONOLOGY_INVALID"),
  );

  const first = fixture.coordinator.beginAttempt({
    attempt_id: "ATTEMPT-E02-CHRONOLOGY-1",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(34),
  });
  const failed = createReceiptFixture({
    attempt: first.attempt,
    externalOperationId: "external-operation-chronology",
    finishedAt: fixedEffectTimestamp(36),
    intent,
    observedStateHash: digestBytes(Buffer.from("external-state:chronology-failed", "utf8")),
    receiptId: "EFF-E02-CHRONOLOGY-1",
    status: "FAILED",
  });
  fixture.coordinator.recordReceipt({ attempt_id: first.attempt.attempt_id, receipt: failed });
  assert.throws(
    () =>
      fixture.coordinator.beginAttempt({
        attempt_id: "ATTEMPT-E02-BEFORE-RECEIPT",
        intent_id: intent.intent_id,
        started_at: fixedEffectTimestamp(35),
      }),
    expectCode("ATTEMPT_CHRONOLOGY_INVALID"),
  );
  assert.equal(fixture.coordinator.readAttempts(intent.intent_id).length, 1);
});

test("effect_reconciliation_test: an attempt event crash blocks receipt creation until exact replay repairs it", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-ATTEMPT-EVENT-CRASH",
    idempotencyKey: "RUN-E02-0001:attempt-event-crash:1",
  });
  fixture.coordinator.registerIntent(intent);
  const request = {
    attempt_id: "ATTEMPT-E02-EVENT-CRASH",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(23),
  };
  const interruptedLedger = {
    append(input) {
      if (input.event_type === EFFECT_EVENT_TYPES.ATTEMPT) {
        const error = new Error("synthetic attempt-event interruption");
        error.code = "SYNTHETIC_ATTEMPT_EVENT_INTERRUPTION";
        throw error;
      }
      return fixture.ledger.append(input);
    },
    readEvents: fixture.ledger.readEvents.bind(fixture.ledger),
    verifyRun: fixture.ledger.verifyRun.bind(fixture.ledger),
  };
  const interrupted = createEffectCoordinator({
    artifactStore: fixture.artifactStore,
    ledger: interruptedLedger,
    stateStore: fixture.stateStore,
  });
  assert.throws(
    () => interrupted.beginAttempt(request),
    expectCode("EFFECT_EVENT_PUBLICATION_FAILED"),
  );
  const durableAttempt = fixture.coordinator.readAttempts(intent.intent_id)[0];
  assert.equal(durableAttempt.attempt_id, request.attempt_id);
  assert.equal(fixture.coordinator.inspect(intent.intent_id).status, "PENDING_EVENT_RECONCILIATION");

  const premature = createReceiptFixture({
    attempt: durableAttempt,
    externalOperationId: "external-operation-premature",
    finishedAt: fixedEffectTimestamp(24),
    intent,
    observedStateHash: digestBytes(Buffer.from("external-state:premature-failed", "utf8")),
    receiptId: "EFF-E02-PREMATURE",
    status: "FAILED",
  });
  assert.throws(
    () =>
      fixture.coordinator.recordReceipt({
        attempt_id: durableAttempt.attempt_id,
        receipt: premature,
      }),
    expectCode("EFFECT_EVENT_RECONCILIATION_REQUIRED"),
  );
  assert.equal(fixture.coordinator.readReceipts(intent.intent_id).length, 0);

  const repaired = fixture.coordinator.beginAttempt(request);
  assert.equal(repaired.status, "EXISTING_ATTEMPT");
  assert.equal(repaired.execute_permitted, false);
  assert.equal(fixture.coordinator.inspect(intent.intent_id).status, "RECONCILING");
  assert.equal(fixture.ledger.readEvents(intent.run_id).length, 2);
});

test("effect_reconciliation_test: reconciliation retains external operation identity", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-OPERATION-BINDING",
    idempotencyKey: "RUN-E02-0001:operation-binding:1",
  });
  fixture.coordinator.registerIntent(intent);
  const started = fixture.coordinator.beginAttempt({
    attempt_id: "ATTEMPT-E02-OPERATION-BINDING",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(37),
  });
  const unknown = createReceiptFixture({
    attempt: started.attempt,
    externalOperationId: "external-operation-original",
    finishedAt: fixedEffectTimestamp(38),
    intent,
    receiptId: "EFF-E02-OPERATION-UNKNOWN",
    status: "UNKNOWN",
  });
  fixture.coordinator.recordReceipt({ attempt_id: started.attempt.attempt_id, receipt: unknown });
  const mismatched = createReceiptFixture({
    attempt: started.attempt,
    externalOperationId: "external-operation-substituted",
    finishedAt: fixedEffectTimestamp(39),
    intent,
    observedStateHash: digestBytes(Buffer.from("external-state:mismatched", "utf8")),
    receiptId: "EFF-E02-OPERATION-MISMATCH",
    status: "FAILED",
  });
  assert.throws(
    () =>
      fixture.coordinator.reconcile({
        attempt_id: started.attempt.attempt_id,
        receipt: mismatched,
      }),
    expectCode("EFFECT_RECONCILIATION_OPERATION_MISMATCH"),
  );
  assert.equal(fixture.coordinator.readReceipts(intent.intent_id).length, 1);
  assert.equal(fixture.coordinator.inspect(intent.intent_id).status, "RECONCILING");
});

test("effect_reconciliation_test: crash after ledger append requires durable confirmation replay", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-CONFIRM-CRASH",
    idempotencyKey: "RUN-E02-0001:confirm-crash:1",
  });
  fixture.coordinator.registerIntent(intent);
  let failConfirmation = false;
  const ledger = {
    append(input) {
      const result = fixture.ledger.append(input);
      if (input.event_type === EFFECT_EVENT_TYPES.ATTEMPT) failConfirmation = true;
      return result;
    },
    readEvents: fixture.ledger.readEvents.bind(fixture.ledger),
    verifyRun: fixture.ledger.verifyRun.bind(fixture.ledger),
  };
  const stateStore = {
    compareAndSwapRevision: fixture.stateStore.compareAndSwapRevision.bind(fixture.stateStore),
    createRevisionedRecord: fixture.stateStore.createRevisionedRecord.bind(fixture.stateStore),
    readRevisionedRecord: fixture.stateStore.readRevisionedRecord.bind(fixture.stateStore),
    transaction(callback) {
      if (failConfirmation) {
        failConfirmation = false;
        const error = new Error("synthetic publication checkpoint interruption");
        error.code = "SYNTHETIC_CONFIRMATION_INTERRUPTION";
        throw error;
      }
      return fixture.stateStore.transaction((store) => callback(store));
    },
  };
  const interrupted = createEffectCoordinator({
    artifactStore: fixture.artifactStore,
    ledger,
    stateStore,
  });
  const request = {
    attempt_id: "ATTEMPT-E02-CONFIRM-CRASH",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(25),
  };
  assert.throws(
    () => interrupted.beginAttempt(request),
    expectCode("EFFECT_EVENT_CONFIRMATION_FAILED"),
  );
  const pending = fixture.coordinator.inspect(intent.intent_id);
  assert.equal(pending.status, "PENDING_EVENT_CONFIRMATION");
  assert.equal(pending.completion_proven, false);
  assert.equal(pending.publication_confirmation_required, true);
  assert.throws(
    () => fixture.coordinator.verify(intent.intent_id),
    expectCode("EFFECT_EVENT_CONFIRMATION_REQUIRED"),
  );

  const replay = fixture.coordinator.beginAttempt(request);
  assert.equal(replay.status, "EXISTING_ATTEMPT");
  assert.equal(replay.execute_permitted, false);
  assert.equal(fixture.coordinator.inspect(intent.intent_id).status, "RECONCILING");
});

test("effect_reconciliation_test: emitted ActionIntent and EffectReceipt pass canonical schemas", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-SCHEMA",
    idempotencyKey: "RUN-E02-0001:schema:1",
  });
  fixture.coordinator.registerIntent(intent);
  const started = fixture.coordinator.beginAttempt({
    attempt_id: "ATTEMPT-E02-SCHEMA",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(26),
  });
  const receipt = createReceiptFixture({
    attempt: started.attempt,
    finishedAt: fixedEffectTimestamp(27),
    intent,
    receiptId: "EFF-E02-SCHEMA",
    status: "UNKNOWN",
  });
  fixture.coordinator.recordReceipt({ attempt_id: started.attempt.attempt_id, receipt });

  const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
  const payload = JSON.stringify({ "action-intent": intent, "effect-receipt": receipt });
  const script = String.raw`
import json, pathlib, sys
from jsonschema import Draft202012Validator, FormatChecker
root = pathlib.Path(sys.argv[1]); instances = json.loads(sys.argv[2])
for name, instance in instances.items():
    schema = json.loads((root / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance))
    if errors: raise SystemExit("; ".join(error.message for error in errors))
print("2 canonical E02 documents validated")
`;
  const actual = spawnSync(
    "uv",
    ["run", "--locked", "python", "-", repositoryRoot, payload],
    { cwd: repositoryRoot, encoding: "utf8", input: script },
  );
  assert.equal(
    actual.status,
    0,
    `schema validation failed\nstdout: ${actual.stdout}\nstderr: ${actual.stderr}`,
  );
  assert.equal(actual.stdout.trim(), "2 canonical E02 documents validated");
});
