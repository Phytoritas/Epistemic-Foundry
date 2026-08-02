import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { Worker } from "node:worker_threads";

import { openSQLiteStateStore } from "./sqlite-state-store.mjs";

const storeModuleUrl = new URL("./sqlite-state-store.mjs", import.meta.url).href;

const workerSource = `
  import { parentPort, workerData } from "node:worker_threads";

  const { openSQLiteStateStore } = await import(workerData.storeModuleUrl);
  const store = openSQLiteStateStore(workerData.databasePath);
  const barrier = new Int32Array(workerData.barrier);
  parentPort.postMessage({ type: "READY" });
  parentPort.once("message", (message) => {
    if (message?.type !== "RUN") {
      store.close();
      throw new Error("unexpected worker command");
    }
    try {
      const previousArrivalCount = Atomics.add(barrier, 0, 1);
      if (previousArrivalCount === 0) {
        Atomics.wait(barrier, 0, 1);
      } else {
        Atomics.notify(barrier, 0);
      }
      const result = store.compareAndSwapRevision({
        recordType: "candidate",
        recordId: "candidate-1",
        expectedRevision: 0,
        value: { winner: workerData.writerId },
      });
      parentPort.postMessage({ type: "RESULT", result });
    } finally {
      store.close();
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
      reject(new Error(`CAS worker exited before replying with code ${code}`));
    };
    worker.once("message", onMessage);
    worker.once("error", onError);
    worker.once("exit", onExit);
  });

const createCasWorker = (databasePath, writerId, barrier) =>
  new Worker(new URL(`data:text/javascript,${encodeURIComponent(workerSource)}`), {
    type: "module",
    workerData: { databasePath, storeModuleUrl, writerId, barrier },
  });

const openWorkerSource = `
  import { parentPort, workerData } from "node:worker_threads";

  const { openSQLiteStateStore } = await import(workerData.storeModuleUrl);
  const barrier = new Int32Array(workerData.barrier);
  const previousArrivalCount = Atomics.add(barrier, 0, 1);
  if (previousArrivalCount === 0) {
    Atomics.wait(barrier, 0, 1);
  } else {
    Atomics.notify(barrier, 0);
  }
  const store = openSQLiteStateStore(workerData.databasePath);
  try {
    parentPort.postMessage({ type: "OPENED", mode: store.mode, journalMode: store.journalMode });
  } finally {
    store.close();
  }
`;

const createOpenWorker = (databasePath, barrier) =>
  new Worker(new URL(`data:text/javascript,${encodeURIComponent(openWorkerSource)}`), {
    type: "module",
    workerData: { databasePath, storeModuleUrl, barrier },
  });

test("two writers with the same expected revision produce one update and one stale no-op", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "foundry-d01-cas-"));
  const databasePath = path.join(directory, "foundry.db");
  const workers = [];

  try {
    const seed = openSQLiteStateStore(databasePath);
    try {
      seed.createRevisionedRecord({
        recordType: "candidate",
        recordId: "candidate-1",
        value: { winner: null },
      });
      assert.equal(seed.readRevisionedRecord("candidate", "candidate-1").revision, 0);
    } finally {
      seed.close();
    }

    const barrier = new SharedArrayBuffer(Int32Array.BYTES_PER_ELEMENT);
    const workerA = createCasWorker(databasePath, "A", barrier);
    const workerB = createCasWorker(databasePath, "B", barrier);
    workers.push(workerA, workerB);
    const ready = await Promise.all([nextWorkerMessage(workerA), nextWorkerMessage(workerB)]);
    assert.deepEqual(ready, [{ type: "READY" }, { type: "READY" }]);

    const resultMessages = [nextWorkerMessage(workerA), nextWorkerMessage(workerB)];
    workerA.postMessage({ type: "RUN" });
    workerB.postMessage({ type: "RUN" });
    const [messageA, messageB] = await Promise.all(resultMessages);
    assert.equal(Atomics.load(new Int32Array(barrier), 0), 2);
    assert.equal(messageA.type, "RESULT");
    assert.equal(messageB.type, "RESULT");
    const [resultA, resultB] = [messageA.result, messageB.result];

    const succeeded = [resultA, resultB].filter((result) => result.ok);
    const stale = [resultA, resultB].filter((result) => !result.ok);
    assert.equal(succeeded.length, 1);
    assert.equal(stale.length, 1);
    assert.equal(succeeded[0].status, "UPDATED");
    assert.equal(succeeded[0].previousRevision, 0);
    assert.equal(succeeded[0].currentRevision, 1);
    assert.equal(stale[0].status, "STALE_REVISION");
    assert.equal(stale[0].code, "STALE_REVISION");
    assert.equal(stale[0].expectedRevision, 0);
    assert.equal(stale[0].currentRevision, 1);

    const winner = resultA.ok ? "A" : "B";
    const observer = openSQLiteStateStore(databasePath);
    try {
      const current = observer.readRevisionedRecord("candidate", "candidate-1");
      assert.equal(current.revision, 1);
      assert.deepEqual(current.value, { winner });
      assert.deepEqual(stale[0].record, current);
    } finally {
      observer.close();
    }
  } finally {
    await Promise.allSettled(workers.map((worker) => worker.terminate()));
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test("concurrent first opens initialize one canonical WAL schema", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "foundry-d01-open-"));
  const databasePath = path.join(directory, "foundry.db");
  const workers = [];

  try {
    const barrier = new SharedArrayBuffer(Int32Array.BYTES_PER_ELEMENT);
    const workerA = createOpenWorker(databasePath, barrier);
    const workerB = createOpenWorker(databasePath, barrier);
    workers.push(workerA, workerB);
    const [messageA, messageB] = await Promise.all([
      nextWorkerMessage(workerA),
      nextWorkerMessage(workerB),
    ]);
    assert.equal(Atomics.load(new Int32Array(barrier), 0), 2);
    assert.deepEqual(messageA, { type: "OPENED", mode: "ACTIVE", journalMode: "wal" });
    assert.deepEqual(messageB, { type: "OPENED", mode: "ACTIVE", journalMode: "wal" });

    const observer = openSQLiteStateStore(databasePath);
    try {
      const created = observer.createRevisionedRecord({
        recordType: "session",
        recordId: "after-concurrent-open",
        value: { state: "READY" },
      });
      assert.equal(created.revision, 0);
    } finally {
      observer.close();
    }
  } finally {
    await Promise.allSettled(workers.map((worker) => worker.terminate()));
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
