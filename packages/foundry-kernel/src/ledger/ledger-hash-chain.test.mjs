import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { Worker } from "node:worker_threads";

import { openContentAddressedArtifactStore } from "../artifacts/content-addressed-artifact-store.mjs";
import { openSQLiteStateStore } from "../state/sqlite/sqlite-state-store.mjs";
import {
  NOETIC_LEDGER_RECORD_TYPES,
  NoeticLedgerError,
  computeEventHash,
  createNoeticLedger,
  verifyEventChain,
} from "./noetic-ledger.mjs";
import {
  createLedgerFixture,
  eventInput,
  fixedTimestamp,
  payloadMetadata,
  putJsonPayload,
} from "./ledger-test-support.mjs";

const ledgerModuleUrl = new URL("./noetic-ledger.mjs", import.meta.url).href;
const stateStoreModuleUrl = new URL("../state/sqlite/sqlite-state-store.mjs", import.meta.url).href;
const artifactStoreModuleUrl = new URL(
  "../artifacts/content-addressed-artifact-store.mjs",
  import.meta.url,
).href;

const expectCode = (code) => (error) =>
  error instanceof NoeticLedgerError && error.code === code;

test("ledger_hash_chain_test: append owns sequence, payload digest, and per-run hash links", (t) => {
  const { artifactStore, ledger } = createLedgerFixture(t);
  const firstBytes = putJsonPayload(artifactStore, "ART-E01-first", { delta: 1 });
  const secondBytes = putJsonPayload(artifactStore, "ART-E01-second", { delta: 2 });
  const first = ledger.append(
    eventInput({
      eventId: "EVT-E01-first",
      eventType: "session.created",
      occurredAt: fixedTimestamp(1),
      payloadArtifactId: "ART-E01-first",
    }),
  );
  const second = ledger.append(
    eventInput({
      eventId: "EVT-E01-second",
      occurredAt: fixedTimestamp(2),
      payloadArtifactId: "ART-E01-second",
    }),
  );

  assert.equal(first.status, "APPENDED");
  assert.equal(first.event.sequence, 1);
  assert.equal(first.event.previous_event_hash, null);
  assert.equal(
    first.event.payload_hash,
    `sha256:${createHash("sha256").update(firstBytes).digest("hex")}`,
  );
  assert.equal(second.status, "APPENDED");
  assert.equal(second.event.sequence, 2);
  assert.equal(second.event.previous_event_hash, first.event.event_hash);
  assert.notEqual(second.event.payload_hash, first.event.payload_hash);
  assert.equal(secondBytes.length > 0, true);

  const events = ledger.readEvents("RUN-E01-test");
  assert.equal(Object.isFrozen(events), true);
  assert.equal(Object.isFrozen(events[0]), true);
  assert.deepEqual(events, [first.event, second.event]);
  assert.deepEqual(ledger.verifyRun("RUN-E01-test"), {
    event_count: 2,
    payload_hashes_verified: 2,
    run_id: "RUN-E01-test",
    tail_event_hash: second.event.event_hash,
  });
});

test("ledger_hash_chain_test: emitted records validate against canonical EventRecord schema", (t) => {
  const { artifactStore, ledger, root } = createLedgerFixture(t);
  putJsonPayload(artifactStore, "ART-E01-schema", { accepted: true });
  const { event } = ledger.append(
    eventInput({
      eventId: "EVT-E01-schema",
      payloadArtifactId: "ART-E01-schema",
    }),
  );
  const instancePath = path.join(root, "event.json");
  fs.writeFileSync(instancePath, JSON.stringify(event), "utf8");
  const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
  const script = `
import json
import pathlib
import sys
from jsonschema import Draft202012Validator, FormatChecker

schema = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
instance = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
Draft202012Validator.check_schema(schema)
errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance))
if errors:
    raise SystemExit("; ".join(error.message for error in errors))
print("EventRecord valid")
`;
  const result = spawnSync(
    "uv",
    [
      "run",
      "--locked",
      "python",
      "-",
      path.join(repositoryRoot, "schemas", "event-record.schema.json"),
      instancePath,
    ],
    { cwd: repositoryRoot, encoding: "utf8", input: script },
  );
  assert.equal(
    result.status,
    0,
    `schema validation failed\nstdout: ${result.stdout}\nstderr: ${result.stderr}`,
  );
  assert.equal(result.stdout.trim(), "EventRecord valid");
});

test("ledger_hash_chain_test: exact event retry is idempotent and conflicting reuse is denied", (t) => {
  const { artifactStore, ledger } = createLedgerFixture(t);
  putJsonPayload(artifactStore, "ART-E01-retry", { n: 1 });
  const input = eventInput({ eventId: "EVT-E01-retry", payloadArtifactId: "ART-E01-retry" });
  const first = ledger.append(input);
  const retry = ledger.append({ ...input });

  assert.equal(first.status, "APPENDED");
  assert.equal(retry.status, "EXISTING");
  assert.deepEqual(retry.event, first.event);
  assert.throws(
    () => ledger.append({ ...input, actor_id: "ACT-E01-conflicting-writer" }),
    expectCode("EVENT_ID_CONFLICT"),
  );
  assert.equal(ledger.readEvents(input.run_id).length, 1);
});

test("ledger_hash_chain_test: missing payload and invalid event input leave no partial ledger state", (t) => {
  const { ledger, stateStore } = createLedgerFixture(t);
  assert.throws(
    () =>
      ledger.append(
        eventInput({ eventId: "EVT-E01-missing", payloadArtifactId: "ART-E01-missing" }),
      ),
    expectCode("PAYLOAD_RESOLUTION_FAILED"),
  );
  assert.deepEqual(ledger.readEvents("RUN-E01-test"), []);
  assert.equal(
    stateStore.readRevisionedRecord(NOETIC_LEDGER_RECORD_TYPES.EVENT, "EVT-E01-missing"),
    null,
  );
  assert.throws(
    () =>
      ledger.append({
        ...eventInput({ eventId: "EVT-E01-extra", payloadArtifactId: "ART-E01-missing" }),
        sequence: 99,
      }),
    expectCode("INVALID_INPUT"),
  );
});

test("ledger_hash_chain_test: gaps, reordering, hash tamper, and mixed runs fail closed", (t) => {
  const { artifactStore, ledger } = createLedgerFixture(t);
  for (let index = 1; index <= 3; index += 1) {
    putJsonPayload(artifactStore, `ART-E01-chain-${index}`, { index });
    ledger.append(
      eventInput({
        eventId: `EVT-E01-chain-${index}`,
        occurredAt: fixedTimestamp(index),
        payloadArtifactId: `ART-E01-chain-${index}`,
      }),
    );
  }
  const events = ledger.readEvents("RUN-E01-test");
  assert.throws(() => verifyEventChain([events[0], events[2]]), expectCode("EVENT_SEQUENCE_MISMATCH"));
  assert.throws(() => verifyEventChain([events[1], events[0]]), expectCode("EVENT_SEQUENCE_MISMATCH"));
  assert.throws(
    () => verifyEventChain([{ ...events[0], event_type: "tampered" }]),
    expectCode("EVENT_HASH_MISMATCH"),
  );
  assert.throws(
    () => verifyEventChain([{ ...events[0], run_id: "RUN-other" }]),
    expectCode("EVENT_HASH_MISMATCH"),
  );
  const crossRunSecondWithoutHash = {
    ...events[1],
    run_id: "RUN-other",
  };
  delete crossRunSecondWithoutHash.event_hash;
  const crossRunSecond = {
    ...crossRunSecondWithoutHash,
    event_hash: computeEventHash(crossRunSecondWithoutHash),
  };
  assert.throws(
    () => verifyEventChain([events[0], crossRunSecond]),
    expectCode("EVENT_RUN_MISMATCH"),
  );
});

test("ledger_hash_chain_test: hash validation never executes coercion hooks", (t) => {
  const { artifactStore, ledger } = createLedgerFixture(t);
  putJsonPayload(artifactStore, "ART-E01-coercion", { value: 1 });
  const { event } = ledger.append(
    eventInput({ eventId: "EVT-E01-coercion", payloadArtifactId: "ART-E01-coercion" }),
  );
  let coercionCalls = 0;
  const hostileHash = {
    toString() {
      coercionCalls += 1;
      return event.payload_hash;
    },
  };
  assert.throws(
    () => verifyEventChain([{ ...event, payload_hash: hostileHash }]),
    expectCode("EVENT_RECORD_INVALID"),
  );
  assert.equal(coercionCalls, 0);
});

test("ledger_hash_chain_test: direct mutation of an immutable stored event is detected", (t) => {
  const { artifactStore, ledger, stateStore } = createLedgerFixture(t);
  putJsonPayload(artifactStore, "ART-E01-mutation", { n: 1 });
  const appended = ledger.append(
    eventInput({ eventId: "EVT-E01-mutation", payloadArtifactId: "ART-E01-mutation" }),
  );
  const update = stateStore.compareAndSwapRevision({
    recordType: NOETIC_LEDGER_RECORD_TYPES.EVENT,
    recordId: appended.event.event_id,
    expectedRevision: 0,
    value: { ...appended.event },
  });
  assert.equal(update.ok, true);
  assert.throws(() => ledger.readEvents(appended.event.run_id), expectCode("EVENT_RECORD_MUTATED"));
});

test("ledger_hash_chain_test: a coherently revised stream that references no event fails closed", (t) => {
  const { artifactStore, ledger, stateStore } = createLedgerFixture(t);
  putJsonPayload(artifactStore, "ART-E01-stream", { n: 1 });
  const appended = ledger.append(
    eventInput({ eventId: "EVT-E01-stream", payloadArtifactId: "ART-E01-stream" }),
  );
  const current = stateStore.readRevisionedRecord(
    NOETIC_LEDGER_RECORD_TYPES.RUN_STREAM,
    appended.event.run_id,
  );
  const forgedTailHash = `sha256:${"f".repeat(64)}`;
  const update = stateStore.compareAndSwapRevision({
    recordType: NOETIC_LEDGER_RECORD_TYPES.RUN_STREAM,
    recordId: appended.event.run_id,
    expectedRevision: current.revision,
    value: {
      ...current.value,
      event_count: 2,
      event_ids: [...current.value.event_ids, "EVT-E01-missing-tail"],
      tail_event_hash: forgedTailHash,
      tail_event_id: "EVT-E01-missing-tail",
    },
  });
  assert.equal(update.ok, true);
  assert.throws(() => ledger.readEvents(appended.event.run_id), expectCode("EVENT_RECORD_MISSING"));
});

test("ledger_hash_chain_test: sealed payload hash catches a provider-neutral adapter byte change", (t) => {
  const { stateStore } = createLedgerFixture(t);
  const first = Buffer.from('{"value":1}', "utf8");
  const changed = Buffer.from('{"value":2}', "utf8");
  let reads = 0;
  const artifactStore = {
    readArtifact(artifactId) {
      assert.equal(artifactId, "ART-E01-changing-adapter");
      reads += 1;
      return reads === 1 ? Buffer.from(first) : Buffer.from(changed);
    },
  };
  const ledger = createNoeticLedger({ artifactStore, stateStore });
  ledger.append(
    eventInput({
      eventId: "EVT-E01-changing-adapter",
      payloadArtifactId: "ART-E01-changing-adapter",
    }),
  );
  assert.throws(() => ledger.verifyRun("RUN-E01-test"), expectCode("PAYLOAD_HASH_MISMATCH"));
  assert.equal(reads, 2);
});

test("ledger_hash_chain_test: stream commit failure rolls back the new immutable event", (t) => {
  const { artifactStore, ledger, stateStore } = createLedgerFixture(t);
  putJsonPayload(artifactStore, "ART-E01-atomic-first", { n: 1 });
  putJsonPayload(artifactStore, "ART-E01-atomic-second", { n: 2 });
  const first = ledger.append(
    eventInput({
      eventId: "EVT-E01-atomic-first",
      payloadArtifactId: "ART-E01-atomic-first",
    }),
  );
  const failingStateStore = {
    transaction(callback) {
      return stateStore.transaction((transactionStore) =>
        callback({
          compareAndSwapRevision() {
            return { ok: false, status: "INJECTED_STREAM_COMMIT_FAILURE" };
          },
          createRevisionedRecord: transactionStore.createRevisionedRecord.bind(transactionStore),
          readRevisionedRecord: transactionStore.readRevisionedRecord.bind(transactionStore),
        }),
      );
    },
    createRevisionedRecord: stateStore.createRevisionedRecord.bind(stateStore),
    readRevisionedRecord: stateStore.readRevisionedRecord.bind(stateStore),
    compareAndSwapRevision: stateStore.compareAndSwapRevision.bind(stateStore),
  };
  const failingLedger = createNoeticLedger({ artifactStore, stateStore: failingStateStore });

  assert.throws(
    () =>
      failingLedger.append(
        eventInput({
          eventId: "EVT-E01-atomic-second",
          occurredAt: fixedTimestamp(2),
          payloadArtifactId: "ART-E01-atomic-second",
        }),
      ),
    expectCode("LEDGER_APPEND_COMMIT_FAILED"),
  );
  assert.equal(
    stateStore.readRevisionedRecord(
      NOETIC_LEDGER_RECORD_TYPES.EVENT,
      "EVT-E01-atomic-second",
    ),
    null,
  );
  assert.deepEqual(ledger.readEvents(first.event.run_id), [first.event]);
  assert.equal(ledger.tail(first.event.run_id).event_id, first.event.event_id);
});

const workerSource = `
  import { parentPort, workerData } from "node:worker_threads";
  const { openSQLiteStateStore } = await import(workerData.stateStoreModuleUrl);
  const { openContentAddressedArtifactStore } = await import(workerData.artifactStoreModuleUrl);
  const { createNoeticLedger } = await import(workerData.ledgerModuleUrl);
  const stateStore = openSQLiteStateStore(workerData.databasePath);
  const artifactStore = openContentAddressedArtifactStore(workerData.artifactRoot);
  const ledger = createNoeticLedger({ artifactStore, stateStore });
  const barrier = new Int32Array(workerData.barrier);
  parentPort.postMessage({ type: "READY" });
  parentPort.once("message", (message) => {
    if (message?.type !== "RUN") throw new Error("unexpected command");
    try {
      const arrival = Atomics.add(barrier, 0, 1);
      if (arrival === 0) Atomics.wait(barrier, 0, 1);
      else Atomics.notify(barrier, 0);
      const result = ledger.append(workerData.event);
      parentPort.postMessage({ type: "RESULT", result });
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
      reject(new Error(`ledger worker exited before replying with code ${code}`));
    };
    worker.once("message", onMessage);
    worker.once("error", onError);
    worker.once("exit", onExit);
  });

const createAppendWorker = (workerData) =>
  new Worker(new URL(`data:text/javascript,${encodeURIComponent(workerSource)}`), {
    type: "module",
    workerData: {
      ...workerData,
      artifactStoreModuleUrl,
      ledgerModuleUrl,
      stateStoreModuleUrl,
    },
  });

test("ledger_hash_chain_test: simultaneous writers serialize into one contiguous run chain", async (t) => {
  const { artifactRoot, artifactStore, databasePath, stateStore } = createLedgerFixture(t);
  artifactStore.putArtifact(
    Buffer.from('{"writer":"A"}', "utf8"),
    payloadMetadata({ artifactId: "ART-E01-worker-A", receiptId: "AR-E01-worker-A" }),
  );
  artifactStore.putArtifact(
    Buffer.from('{"writer":"B"}', "utf8"),
    payloadMetadata({ artifactId: "ART-E01-worker-B", receiptId: "AR-E01-worker-B" }),
  );
  stateStore.close();
  const barrier = new SharedArrayBuffer(Int32Array.BYTES_PER_ELEMENT);
  const workerA = createAppendWorker({
    artifactRoot,
    barrier,
    databasePath,
    event: eventInput({
      eventId: "EVT-E01-worker-A",
      occurredAt: fixedTimestamp(1),
      payloadArtifactId: "ART-E01-worker-A",
    }),
  });
  const workerB = createAppendWorker({
    artifactRoot,
    barrier,
    databasePath,
    event: eventInput({
      eventId: "EVT-E01-worker-B",
      occurredAt: fixedTimestamp(2),
      payloadArtifactId: "ART-E01-worker-B",
    }),
  });
  t.after(async () => {
    await Promise.allSettled([workerA.terminate(), workerB.terminate()]);
  });
  assert.deepEqual(await Promise.all([nextWorkerMessage(workerA), nextWorkerMessage(workerB)]), [
    { type: "READY" },
    { type: "READY" },
  ]);
  const pending = [nextWorkerMessage(workerA), nextWorkerMessage(workerB)];
  workerA.postMessage({ type: "RUN" });
  workerB.postMessage({ type: "RUN" });
  const results = await Promise.all(pending);
  assert.equal(results.every((message) => message.type === "RESULT"), true);
  assert.deepEqual(
    results.map((message) => message.result.event.sequence).sort(),
    [1, 2],
  );

  const observerState = openSQLiteStateStore(databasePath);
  const observerArtifacts = openContentAddressedArtifactStore(artifactRoot);
  try {
    const observer = createNoeticLedger({
      artifactStore: observerArtifacts,
      stateStore: observerState,
    });
    const events = observer.readEvents("RUN-E01-test");
    assert.equal(events.length, 2);
    assert.equal(events[1].previous_event_hash, events[0].event_hash);
    assert.equal(observer.verifyRun("RUN-E01-test").payload_hashes_verified, 2);
  } finally {
    observerState.close();
    observerArtifacts.close();
  }
});

test("ledger_hash_chain_test: independent runs each start at sequence one", (t) => {
  const { artifactStore, ledger } = createLedgerFixture(t);
  putJsonPayload(artifactStore, "ART-E01-run-A", { run: "A" });
  putJsonPayload(artifactStore, "ART-E01-run-B", { run: "B" });
  const left = ledger.append(
    eventInput({ eventId: "EVT-E01-run-A", payloadArtifactId: "ART-E01-run-A", runId: "RUN-A" }),
  );
  const right = ledger.append(
    eventInput({ eventId: "EVT-E01-run-B", payloadArtifactId: "ART-E01-run-B", runId: "RUN-B" }),
  );
  assert.equal(left.event.sequence, 1);
  assert.equal(right.event.sequence, 1);
  assert.equal(left.event.previous_event_hash, null);
  assert.equal(right.event.previous_event_hash, null);
});
