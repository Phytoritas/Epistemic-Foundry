import assert from "node:assert/strict";
import test from "node:test";
import { Worker } from "node:worker_threads";

import {
  EffectCoordinatorError,
  computeActionIntentHash,
  sealActionIntent,
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

const stateStoreModuleUrl = new URL(
  "../state/sqlite/sqlite-state-store.mjs",
  import.meta.url,
).href;
const artifactStoreModuleUrl = new URL(
  "../artifacts/content-addressed-artifact-store.mjs",
  import.meta.url,
).href;
const ledgerModuleUrl = new URL("../ledger/noetic-ledger.mjs", import.meta.url).href;
const coordinatorModuleUrl = new URL("./effect-coordinator.mjs", import.meta.url).href;

const attemptWorkerSource = `
  import { parentPort, workerData } from "node:worker_threads";

  const { openSQLiteStateStore } = await import(workerData.stateStoreModuleUrl);
  const { openContentAddressedArtifactStore } = await import(workerData.artifactStoreModuleUrl);
  const { createNoeticLedger } = await import(workerData.ledgerModuleUrl);
  const { createEffectCoordinator } = await import(workerData.coordinatorModuleUrl);
  const stateStore = openSQLiteStateStore(workerData.databasePath);
  const artifactStore = openContentAddressedArtifactStore(workerData.artifactRoot);
  const ledger = createNoeticLedger({ artifactStore, stateStore });
  const coordinator = createEffectCoordinator({ artifactStore, ledger, stateStore });
  const barrier = new Int32Array(workerData.barrier);
  parentPort.postMessage({ type: "READY" });
  parentPort.once("message", (message) => {
    if (message?.type !== "RUN") throw new Error("unexpected worker command");
    try {
      const previous = Atomics.add(barrier, 0, 1);
      if (previous === 0) Atomics.wait(barrier, 0, 1);
      else Atomics.notify(barrier, 0);
      const result = coordinator.beginAttempt(workerData.request);
      parentPort.postMessage({
        type: "RESULT",
        attemptId: result.attempt.attempt_id,
        executePermitted: result.execute_permitted,
        status: result.status,
      });
    } catch (error) {
      parentPort.postMessage({
        type: "ERROR",
        code: error?.code ?? error?.name ?? "unknown",
        message: error?.message ?? String(error),
      });
    } finally {
      stateStore.close();
      artifactStore.close();
    }
  });
`;

const nextWorkerMessage = (worker) =>
  new Promise((resolve, reject) => {
    const cleanup = () => {
      worker.off("message", onMessage);
      worker.off("error", onError);
      worker.off("exit", onExit);
    };
    const onMessage = (message) => {
      cleanup();
      resolve(message);
    };
    const onError = (error) => {
      cleanup();
      reject(error);
    };
    const onExit = (code) => {
      cleanup();
      reject(new Error(`attempt worker exited before replying with code ${code}`));
    };
    worker.once("message", onMessage);
    worker.once("error", onError);
    worker.once("exit", onExit);
  });

const createAttemptWorker = (fixture, request, barrier) =>
  new Worker(new URL(`data:text/javascript,${encodeURIComponent(attemptWorkerSource)}`), {
    type: "module",
    workerData: {
      artifactRoot: fixture.artifactRoot,
      artifactStoreModuleUrl,
      barrier,
      coordinatorModuleUrl,
      databasePath: fixture.databasePath,
      ledgerModuleUrl,
      request,
      stateStoreModuleUrl,
    },
  });

test("idempotency_test: same key and same canonical intent replays one logical registration", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore);
  const first = fixture.coordinator.registerIntent(intent);
  const replay = fixture.coordinator.registerIntent(intent);
  assert.equal(first.status, "REGISTERED");
  assert.equal(replay.status, "EXISTING");
  assert.deepEqual(replay.intent, first.intent);
  assert.equal(fixture.ledger.readEvents(intent.run_id).length, 1);
});

test("idempotency_test: same key with a different canonical request is a conflict", (t) => {
  const fixture = createEffectFixture(t);
  const first = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-IDEMPOTENCY-A",
    idempotencyKey: "RUN-E02-0001:shared-key",
  });
  fixture.coordinator.registerIntent(first);
  const second = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-IDEMPOTENCY-B",
    idempotencyKey: first.idempotency_key,
    targetRef: "TARGET-E02-DIFFERENT",
  });
  assert.throws(
    () => fixture.coordinator.registerIntent(second),
    expectCode("IDEMPOTENCY_KEY_REUSED"),
  );
  assert.equal(fixture.coordinator.readIntent(first.intent_id).intent_hash, first.intent_hash);
  assert.equal(fixture.ledger.readEvents(first.run_id).length, 1);
});

test("idempotency_test: an intent ID cannot be rebound under a different key", (t) => {
  const fixture = createEffectFixture(t);
  const first = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-STABLE-ID",
    idempotencyKey: "RUN-E02-0001:stable-id:1",
  });
  fixture.coordinator.registerIntent(first);
  const rebound = createIntentFixture(fixture.artifactStore, {
    argumentsArtifactId: "ART-ARGS-INTENT-E02-STABLE-ID-SECOND",
    intentId: first.intent_id,
    idempotencyKey: "RUN-E02-0001:stable-id:2",
  });
  assert.throws(
    () => fixture.coordinator.registerIntent(rebound),
    expectCode("INTENT_ID_CONFLICT"),
  );
});

test("idempotency_test: retrying one attempt never grants a second execution", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-ATTEMPT-REPLAY",
    idempotencyKey: "RUN-E02-0001:attempt-replay:1",
  });
  fixture.coordinator.registerIntent(intent);
  const request = {
    attempt_id: "ATTEMPT-E02-REPLAY",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(15),
  };
  const first = fixture.coordinator.beginAttempt(request);
  const replay = fixture.coordinator.beginAttempt(request);
  assert.equal(first.execute_permitted, true);
  assert.equal(replay.execute_permitted, false);
  assert.equal(replay.status, "EXISTING_ATTEMPT");
  assert.deepEqual(replay.attempt, first.attempt);
  assert.equal(fixture.coordinator.readAttempts(intent.intent_id).length, 1);
  assert.equal(fixture.ledger.readEvents(intent.run_id).length, 2);
});

test("idempotency_test: retrying one receipt returns the existing logical result", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-RECEIPT-REPLAY",
    idempotencyKey: "RUN-E02-0001:receipt-replay:1",
  });
  fixture.coordinator.registerIntent(intent);
  const started = fixture.coordinator.beginAttempt({
    attempt_id: "ATTEMPT-E02-RECEIPT-REPLAY",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(16),
  });
  const resultId = "ART-E02-RECEIPT-REPLAY";
  putEffectArtifact(fixture.artifactStore, {
    actionIntentId: intent.intent_id,
    artifactId: resultId,
    receiptId: "AR-E02-RECEIPT-REPLAY",
    timestamp: fixedEffectTimestamp(17),
  });
  const receipt = createReceiptFixture({
    attempt: started.attempt,
    finishedAt: fixedEffectTimestamp(18),
    intent,
    receiptId: "EFF-E02-RECEIPT-REPLAY",
    resultArtifactIds: [resultId],
    status: "SUCCEEDED",
  });
  const first = fixture.coordinator.recordReceipt({
    attempt_id: started.attempt.attempt_id,
    receipt,
  });
  const replay = fixture.coordinator.recordReceipt({
    attempt_id: started.attempt.attempt_id,
    receipt,
  });
  assert.equal(first.status, "RECORDED");
  assert.equal(replay.status, "EXISTING");
  assert.deepEqual(replay.receipt, first.receipt);
  assert.equal(replay.outcome.completion_proven, true);
  assert.equal(fixture.coordinator.readReceipts(intent.intent_id).length, 1);
  assert.equal(fixture.ledger.readEvents(intent.run_id).length, 3);
});

test("idempotency_test: attempt and receipt IDs are immutable identities", (t) => {
  const fixture = createEffectFixture(t);
  const firstIntent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-IDENTITY-A",
    idempotencyKey: "RUN-E02-0001:identity-a:1",
  });
  const secondIntent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-IDENTITY-B",
    idempotencyKey: "RUN-E02-0001:identity-b:1",
  });
  fixture.coordinator.registerIntent(firstIntent);
  fixture.coordinator.registerIntent(secondIntent);
  const firstAttempt = fixture.coordinator.beginAttempt({
    attempt_id: "ATTEMPT-E02-IMMUTABLE-ID",
    intent_id: firstIntent.intent_id,
    started_at: fixedEffectTimestamp(19),
  });
  assert.throws(
    () =>
      fixture.coordinator.beginAttempt({
        attempt_id: firstAttempt.attempt.attempt_id,
        intent_id: secondIntent.intent_id,
        started_at: fixedEffectTimestamp(20),
      }),
    expectCode("ATTEMPT_ID_CONFLICT"),
  );

  const firstFailed = createReceiptFixture({
    attempt: firstAttempt.attempt,
    externalOperationId: "external-operation-identity-a",
    finishedAt: fixedEffectTimestamp(20),
    intent: firstIntent,
    observedStateHash: digestBytes(Buffer.from("external-state:identity-a-failed", "utf8")),
    receiptId: "EFF-E02-IMMUTABLE-ID",
    status: "FAILED",
  });
  fixture.coordinator.recordReceipt({
    attempt_id: firstAttempt.attempt.attempt_id,
    receipt: firstFailed,
  });
  const secondAttempt = fixture.coordinator.beginAttempt({
    attempt_id: "ATTEMPT-E02-IDENTITY-B",
    intent_id: secondIntent.intent_id,
    started_at: fixedEffectTimestamp(21),
  });
  const conflictingReceipt = createReceiptFixture({
    attempt: secondAttempt.attempt,
    externalOperationId: "external-operation-identity-b",
    finishedAt: fixedEffectTimestamp(22),
    intent: secondIntent,
    observedStateHash: digestBytes(Buffer.from("external-state:identity-b-failed", "utf8")),
    receiptId: firstFailed.receipt_id,
    status: "FAILED",
  });
  assert.throws(
    () =>
      fixture.coordinator.recordReceipt({
        attempt_id: secondAttempt.attempt.attempt_id,
        receipt: conflictingReceipt,
      }),
    expectCode("RECEIPT_ID_CONFLICT"),
  );
});

test("idempotency_test: hashes reject mutation, accessors, and hostile coercion", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-HASH",
    idempotencyKey: "RUN-E02-0001:hash:1",
  });
  const tampered = { ...intent, target_ref: "TARGET-E02-TAMPERED" };
  assert.throws(
    () => fixture.coordinator.registerIntent(tampered),
    expectCode("ACTION_INTENT_HASH_MISMATCH"),
  );

  let getterCalls = 0;
  const accessor = { ...intent };
  Object.defineProperty(accessor, "target_ref", {
    enumerable: true,
    get() {
      getterCalls += 1;
      return "TARGET-E02-ACCESSOR";
    },
  });
  assert.throws(
    () => computeActionIntentHash(accessor),
    expectCode("NON_CANONICAL_JSON"),
  );
  assert.equal(getterCalls, 0);
  assert.throws(
    () => sealActionIntent(new Proxy({ ...intent }, {})),
    expectCode("ACTION_INTENT_INVALID"),
  );
});

test("idempotency_test: immutable older attempt and receipt replays remain idempotent", (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-HISTORICAL-REPLAY",
    idempotencyKey: "RUN-E02-0001:historical-replay:1",
  });
  fixture.coordinator.registerIntent(intent);
  const firstRequest = {
    attempt_id: "ATTEMPT-E02-HISTORICAL-1",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(28),
  };
  const first = fixture.coordinator.beginAttempt(firstRequest);
  const firstReceipt = createReceiptFixture({
    attempt: first.attempt,
    externalOperationId: "external-operation-historical-1",
    finishedAt: fixedEffectTimestamp(29),
    intent,
    observedStateHash: digestBytes(Buffer.from("external-state:historical-1-failed", "utf8")),
    receiptId: "EFF-E02-HISTORICAL-1",
    status: "FAILED",
  });
  fixture.coordinator.recordReceipt({
    attempt_id: first.attempt.attempt_id,
    receipt: firstReceipt,
  });

  const second = fixture.coordinator.beginAttempt({
    attempt_id: "ATTEMPT-E02-HISTORICAL-2",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(30),
  });
  const secondReceipt = createReceiptFixture({
    attempt: second.attempt,
    externalOperationId: "external-operation-historical-2",
    finishedAt: fixedEffectTimestamp(31),
    intent,
    observedStateHash: digestBytes(Buffer.from("external-state:historical-2-failed", "utf8")),
    receiptId: "EFF-E02-HISTORICAL-2",
    status: "FAILED",
  });
  fixture.coordinator.recordReceipt({
    attempt_id: second.attempt.attempt_id,
    receipt: secondReceipt,
  });

  const oldAttemptReplay = fixture.coordinator.beginAttempt(firstRequest);
  assert.equal(oldAttemptReplay.status, "EXISTING_ATTEMPT");
  assert.equal(oldAttemptReplay.execute_permitted, false);
  assert.equal(oldAttemptReplay.attempt.attempt_id, first.attempt.attempt_id);
  const oldReceiptReplay = fixture.coordinator.recordReceipt({
    attempt_id: first.attempt.attempt_id,
    receipt: firstReceipt,
  });
  assert.equal(oldReceiptReplay.status, "EXISTING");
  assert.equal(oldReceiptReplay.receipt.receipt_id, firstReceipt.receipt_id);
  assert.equal(oldReceiptReplay.outcome.attempt.attempt_id, second.attempt.attempt_id);
  assert.equal(fixture.coordinator.readAttempts(intent.intent_id).length, 2);
  assert.equal(fixture.coordinator.readReceipts(intent.intent_id).length, 2);
  assert.equal(fixture.ledger.readEvents(intent.run_id).length, 5);
});

test("idempotency_test: concurrent same-attempt callers grant execution once", async (t) => {
  const fixture = createEffectFixture(t);
  const intent = createIntentFixture(fixture.artifactStore, {
    intentId: "INTENT-E02-CONCURRENT",
    idempotencyKey: "RUN-E02-0001:concurrent:1",
  });
  fixture.coordinator.registerIntent(intent);
  const request = {
    attempt_id: "ATTEMPT-E02-CONCURRENT",
    intent_id: intent.intent_id,
    started_at: fixedEffectTimestamp(32),
  };
  const barrier = new SharedArrayBuffer(Int32Array.BYTES_PER_ELEMENT);
  const workers = [
    createAttemptWorker(fixture, request, barrier),
    createAttemptWorker(fixture, request, barrier),
  ];
  t.after(async () => {
    await Promise.allSettled(workers.map((worker) => worker.terminate()));
  });
  const ready = await Promise.all(workers.map(nextWorkerMessage));
  assert.deepEqual(ready, [{ type: "READY" }, { type: "READY" }]);
  const results = workers.map(nextWorkerMessage);
  for (const worker of workers) worker.postMessage({ type: "RUN" });
  const messages = await Promise.all(results);
  assert.equal(Atomics.load(new Int32Array(barrier), 0), 2);
  assert.equal(messages.some((message) => message.type === "ERROR"), false, JSON.stringify(messages));
  assert.deepEqual(
    messages.map((message) => message.attemptId),
    [request.attempt_id, request.attempt_id],
  );
  assert.equal(messages.filter((message) => message.executePermitted).length, 1);
  assert.equal(messages.filter((message) => !message.executePermitted).length, 1);
  assert.equal(fixture.coordinator.readAttempts(intent.intent_id).length, 1);
  assert.equal(fixture.ledger.readEvents(intent.run_id).length, 2);
  assert.equal(fixture.coordinator.verify(intent.intent_id).reconciliation_required, true);
});
