import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import { createContext, runInContext } from "node:vm";

import {
  SQLITE_STORE_MODE,
  SQLiteStateStoreError,
  openSQLiteStateStore,
} from "./sqlite-state-store.mjs";

const withStorePath = (callback) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "foundry-d01-wal-"));
  const databasePath = path.join(directory, "foundry.db");
  try {
    return callback(databasePath);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
};

const readJournalMode = (databasePath) => {
  const database = new DatabaseSync(databasePath, { readOnly: true });
  try {
    return database.prepare("PRAGMA journal_mode").get().journal_mode;
  } finally {
    database.close();
  }
};

test("SQLite store uses WAL and committed state survives reopen", () =>
  withStorePath((databasePath) => {
    let store = openSQLiteStateStore(databasePath);
    try {
      assert.equal(store.journalMode, "wal");
      assert.equal(readJournalMode(databasePath), "wal");

      store.transaction((transactionStore) => {
        transactionStore.createRevisionedRecord({
          recordType: "session",
          recordId: "committed",
          value: { state: "RUNNING" },
        });
        const updated = transactionStore.compareAndSwapRevision({
          recordType: "session",
          recordId: "committed",
          expectedRevision: 0,
          value: { state: "PAUSED" },
        });
        assert.equal(updated.ok, true);
        assert.equal(updated.currentRevision, 1);
      });
    } finally {
      store.close();
    }

    store = openSQLiteStateStore(databasePath);
    try {
      assert.deepEqual(store.readRevisionedRecord("session", "committed"), {
        recordType: "session",
        recordId: "committed",
        revision: 1,
        value: { state: "PAUSED" },
      });
      assert.equal(readJournalMode(databasePath), "wal");
    } finally {
      store.close();
    }
  }));

test("transaction rollback leaves no partial records or revisions", () =>
  withStorePath((databasePath) => {
    const store = openSQLiteStateStore(databasePath);
    try {
      store.createRevisionedRecord({
        recordType: "session",
        recordId: "existing",
        value: { state: "READY" },
      });

      assert.throws(
        () =>
          store.transaction((transactionStore) => {
            transactionStore.compareAndSwapRevision({
              recordType: "session",
              recordId: "existing",
              expectedRevision: 0,
              value: { state: "MUST_ROLL_BACK" },
            });
            transactionStore.createRevisionedRecord({
              recordType: "session",
              recordId: "partial",
              value: { state: "MUST_NOT_EXIST" },
            });
            throw new Error("synthetic transaction failure");
          }),
        /synthetic transaction failure/,
      );

      assert.deepEqual(store.readRevisionedRecord("session", "existing"), {
        recordType: "session",
        recordId: "existing",
        revision: 0,
        value: { state: "READY" },
      });
      assert.equal(store.readRevisionedRecord("session", "partial"), null);
    } finally {
      store.close();
    }

    const reopened = openSQLiteStateStore(databasePath);
    try {
      assert.equal(reopened.readRevisionedRecord("session", "existing").revision, 0);
      assert.equal(reopened.readRevisionedRecord("session", "partial"), null);
    } finally {
      reopened.close();
    }
  }));

test("transaction rejects then accessors without executing them and revokes the handle", () =>
  withStorePath((databasePath) => {
    const store = openSQLiteStateStore(databasePath);
    let thenGetterCalls = 0;
    const callbackResult = {};
    Object.defineProperty(callbackResult, "then", {
      configurable: true,
      get() {
        thenGetterCalls += 1;
        throw new Error("then accessor must not execute");
      },
    });

    try {
      assert.throws(
        () =>
          store.transaction((transactionStore) => {
            transactionStore.createRevisionedRecord({
              recordType: "session",
              recordId: "then-accessor",
              value: { state: "MUST_ROLL_BACK" },
            });
            return callbackResult;
          }),
        (error) =>
          error instanceof SQLiteStateStoreError && error.code === "ASYNC_TRANSACTION_DENIED",
      );
      assert.equal(thenGetterCalls, 0);
      assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);
      assert.equal(store.safeModeReason.code, "ASYNC_TRANSACTION_DENIED");
      assert.throws(
        () => store.readRevisionedRecord("session", "then-accessor"),
        (error) => error instanceof SQLiteStateStoreError && error.code === "STORE_SAFE_MODE",
      );

      const observer = openSQLiteStateStore(databasePath);
      try {
        assert.equal(observer.readRevisionedRecord("session", "then-accessor"), null);
      } finally {
        observer.close();
      }
    } finally {
      store.close();
    }
  }));

test("rejected async transaction cannot write before or after its await boundary", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "foundry-d01-async-"));
  const databasePath = path.join(directory, "foundry.db");
  const store = openSQLiteStateStore(databasePath);
  let continuationError;
  let completeContinuation;
  const continuationComplete = new Promise((resolve) => {
    completeContinuation = resolve;
  });

  try {
    assert.throws(
      () =>
        store.transaction(async (transactionStore) => {
          transactionStore.createRevisionedRecord({
            recordType: "session",
            recordId: "before-await",
            value: { state: "MUST_ROLL_BACK" },
          });
          await Promise.resolve();
          try {
            transactionStore.createRevisionedRecord({
              recordType: "session",
              recordId: "after-await",
              value: { state: "MUST_BE_DENIED" },
            });
          } catch (error) {
            continuationError = error;
          } finally {
            completeContinuation();
          }
        }),
      (error) =>
        error instanceof SQLiteStateStoreError && error.code === "ASYNC_TRANSACTION_DENIED",
    );

    await continuationComplete;
    assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);
    assert.equal(store.safeModeReason.code, "ASYNC_TRANSACTION_DENIED");
    assert.equal(continuationError?.code, "STORE_SAFE_MODE");

    const observer = openSQLiteStateStore(databasePath);
    try {
      assert.equal(observer.readRevisionedRecord("session", "before-await"), null);
      assert.equal(observer.readRevisionedRecord("session", "after-await"), null);
    } finally {
      observer.close();
    }
  } finally {
    store.close();
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test("rejected async transaction is observed while its continuation remains revoked", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "foundry-d01-async-reject-"));
  const databasePath = path.join(directory, "foundry.db");
  const store = openSQLiteStateStore(databasePath);
  let signalContinuation;
  const continuationReached = new Promise((resolve) => {
    signalContinuation = resolve;
  });

  try {
    assert.throws(
      () =>
        store.transaction(async (transactionStore) => {
          transactionStore.createRevisionedRecord({
            recordType: "session",
            recordId: "before-rejected-await",
            value: { state: "MUST_ROLL_BACK" },
          });
          await Promise.resolve();
          signalContinuation();
          throw new Error("synthetic rejected continuation");
        }),
      (error) =>
        error instanceof SQLiteStateStoreError && error.code === "ASYNC_TRANSACTION_DENIED",
    );

    await continuationReached;
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);
    assert.equal(store.safeModeReason.code, "ASYNC_TRANSACTION_DENIED");

    const observer = openSQLiteStateStore(databasePath);
    try {
      assert.equal(observer.readRevisionedRecord("session", "before-rejected-await"), null);
    } finally {
      observer.close();
    }
  } finally {
    store.close();
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test("cross-realm async rejection is observed without running constructor or species hooks", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "foundry-d01-cross-realm-"));
  const databasePath = path.join(directory, "foundry.db");
  const store = openSQLiteStateStore(databasePath);
  const hooks = { constructor: 0, species: 0, then: 0 };
  const unhandled = [];
  let continuationError;
  let completeContinuation;
  const continuationComplete = new Promise((resolve) => {
    completeContinuation = resolve;
  });
  const onUnhandledRejection = (reason, promise) => {
    unhandled.push({ reason, promise });
  };
  const context = createContext({
    afterRecord: {
      recordType: "session",
      recordId: "cross-realm-after-await",
      value: { state: "MUST_BE_DENIED" },
    },
    beforeRecord: {
      recordType: "session",
      recordId: "cross-realm-before-await",
      value: { state: "MUST_ROLL_BACK" },
    },
    hooks,
    signalContinuation(errorCode) {
      continuationError = errorCode;
      completeContinuation();
    },
  });
  const crossRealmCallback = runInContext(
    `(() => {
      Object.defineProperty(Promise.prototype, "constructor", {
        configurable: true,
        get() {
          hooks.constructor += 1;
          throw new Error("cross-realm Promise constructor hook must not execute");
        },
      });
      Object.defineProperty(Promise, Symbol.species, {
        configurable: true,
        get() {
          hooks.species += 1;
          throw new Error("cross-realm Promise species hook must not execute");
        },
      });
      Object.defineProperty(Promise.prototype, "then", {
        configurable: true,
        get() {
          hooks.then += 1;
          throw new Error("cross-realm Promise then hook must not execute");
        },
      });
      return async (transactionStore) => {
        transactionStore.createRevisionedRecord(beforeRecord);
        await 0;
        try {
          transactionStore.createRevisionedRecord(afterRecord);
        } catch (error) {
          signalContinuation(error && error.code);
        }
        throw new Error("synthetic cross-realm rejection");
      };
    })()`,
    context,
  );

  process.on("unhandledRejection", onUnhandledRejection);
  try {
    assert.throws(
      () => store.transaction(crossRealmCallback),
      (error) =>
        error instanceof SQLiteStateStoreError && error.code === "ASYNC_TRANSACTION_DENIED",
    );

    await continuationComplete;
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(continuationError, "STORE_SAFE_MODE");
    assert.deepEqual(hooks, { constructor: 0, species: 0, then: 0 });
    assert.deepEqual(unhandled, []);
    assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);

    const observer = openSQLiteStateStore(databasePath);
    try {
      assert.equal(observer.readRevisionedRecord("session", "cross-realm-before-await"), null);
      assert.equal(observer.readRevisionedRecord("session", "cross-realm-after-await"), null);
    } finally {
      observer.close();
    }
  } finally {
    process.off("unhandledRejection", onUnhandledRejection);
    store.close();
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test("rejected Promise subclass is observed without running inherited hooks", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "foundry-d01-promise-subclass-"));
  const databasePath = path.join(directory, "foundry.db");
  const store = openSQLiteStateStore(databasePath);
  const hooks = { constructor: 0, species: 0, then: 0 };
  const unhandled = [];
  const onUnhandledRejection = (reason, promise) => {
    unhandled.push({ reason, promise });
  };

  class DerivedPromise extends Promise {}
  Object.defineProperty(DerivedPromise.prototype, "constructor", {
    configurable: true,
    get() {
      hooks.constructor += 1;
      throw new Error("Promise subclass constructor hook must not execute");
    },
  });
  Object.defineProperty(DerivedPromise, Symbol.species, {
    configurable: true,
    get() {
      hooks.species += 1;
      throw new Error("Promise subclass species hook must not execute");
    },
  });
  Object.defineProperty(DerivedPromise.prototype, "then", {
    configurable: true,
    get() {
      hooks.then += 1;
      throw new Error("Promise subclass then hook must not execute");
    },
  });
  const rejected = new DerivedPromise((resolve, reject) => {
    reject(new Error("synthetic Promise subclass rejection"));
  });

  process.on("unhandledRejection", onUnhandledRejection);
  try {
    assert.throws(
      () =>
        store.transaction((transactionStore) => {
          transactionStore.createRevisionedRecord({
            recordType: "session",
            recordId: "promise-subclass",
            value: { state: "MUST_ROLL_BACK" },
          });
          return rejected;
        }),
      (error) =>
        error instanceof SQLiteStateStoreError && error.code === "ASYNC_TRANSACTION_DENIED",
    );

    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(hooks, { constructor: 0, species: 0, then: 0 });
    assert.deepEqual(unhandled, []);
    assert.equal(Object.getOwnPropertyDescriptor(rejected, "constructor"), undefined);
    assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);

    const observer = openSQLiteStateStore(databasePath);
    try {
      assert.equal(observer.readRevisionedRecord("session", "promise-subclass"), null);
    } finally {
      observer.close();
    }
  } finally {
    process.off("unhandledRejection", onUnhandledRejection);
    store.close();
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

for (const restrictPromise of [
  Object.preventExtensions,
  Object.seal,
  Object.freeze,
]) {
  test(`rejected ${restrictPromise.name} Promise is observed without becoming extensible`, async () => {
    const directory = fs.mkdtempSync(
      path.join(os.tmpdir(), `foundry-d01-${restrictPromise.name}-`),
    );
    const databasePath = path.join(directory, "foundry.db");
    const store = openSQLiteStateStore(databasePath);
    const rejected = Promise.reject(new Error(`synthetic ${restrictPromise.name} rejection`));
    restrictPromise(rejected);
    const unhandled = [];
    const onUnhandledRejection = (reason, promise) => {
      unhandled.push({ reason, promise });
    };

    process.on("unhandledRejection", onUnhandledRejection);
    try {
      assert.throws(
        () =>
          store.transaction((transactionStore) => {
            transactionStore.createRevisionedRecord({
              recordType: "session",
              recordId: restrictPromise.name,
              value: { state: "MUST_ROLL_BACK" },
            });
            return rejected;
          }),
        (error) =>
          error instanceof SQLiteStateStoreError && error.code === "ASYNC_TRANSACTION_DENIED",
      );

      await new Promise((resolve) => setImmediate(resolve));
      assert.deepEqual(unhandled, []);
      assert.equal(Object.isExtensible(rejected), false);
      assert.equal(Object.getOwnPropertyDescriptor(rejected, "constructor"), undefined);
      assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);

      const observer = openSQLiteStateStore(databasePath);
      try {
        assert.equal(observer.readRevisionedRecord("session", restrictPromise.name), null);
      } finally {
        observer.close();
      }
    } finally {
      process.off("unhandledRejection", onUnhandledRejection);
      store.close();
      fs.rmSync(directory, { recursive: true, force: true });
    }
  });
}

test("native Promise results remain denied after Promise then-method tampering", () =>
  withStorePath((databasePath) => {
    const originalThenDescriptor = Object.getOwnPropertyDescriptor(Promise.prototype, "then");
    const store = openSQLiteStateStore(databasePath);

    Object.defineProperty(Promise.prototype, "then", {
      configurable: true,
      writable: true,
      value: undefined,
    });
    try {
      assert.throws(
        () =>
          store.transaction((transactionStore) => {
            transactionStore.createRevisionedRecord({
              recordType: "session",
              recordId: "tampered-promise-then",
              value: { state: "MUST_ROLL_BACK" },
            });
            return Promise.resolve("must-not-commit");
          }),
        (error) =>
          error instanceof SQLiteStateStoreError && error.code === "ASYNC_TRANSACTION_DENIED",
      );
      assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);
      assert.equal(store.safeModeReason.code, "ASYNC_TRANSACTION_DENIED");
    } finally {
      Object.defineProperty(Promise.prototype, "then", originalThenDescriptor);
      store.close();
    }

    const observer = openSQLiteStateStore(databasePath);
    try {
      assert.equal(observer.readRevisionedRecord("session", "tampered-promise-then"), null);
    } finally {
      observer.close();
    }
  }));

test("an unconfirmed transaction outcome enters SAFE_MODE and denies reuse", () =>
  withStorePath((databasePath) => {
    const store = openSQLiteStateStore(databasePath);

    assert.throws(
      () =>
        store.transaction((transactionStore) => {
          transactionStore.createRevisionedRecord({
            recordType: "session",
            recordId: "uncertain",
            value: { state: "UNCONFIRMED" },
          });
          transactionStore.close();
        }),
      (error) =>
        error instanceof SQLiteStateStoreError &&
        error.code === "SQLITE_TRANSACTION_OUTCOME_UNCERTAIN",
    );

    assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);
    assert.equal(store.safeModeReason.code, "SQLITE_TRANSACTION_OUTCOME_UNCERTAIN");
    assert.throws(
      () =>
        store.createRevisionedRecord({
          recordType: "session",
          recordId: "must-not-write",
          value: { state: "DENIED" },
        }),
      (error) => error instanceof SQLiteStateStoreError && error.code === "STORE_SAFE_MODE",
    );
  }));

test("record values reject lossy or non-JSON JavaScript values", () =>
  withStorePath((databasePath) => {
    const store = openSQLiteStateStore(databasePath);
    const sparse = [];
    sparse.length = 1;
    const cyclic = {};
    cyclic.self = cyclic;
    const accessorObject = {};
    Object.defineProperty(accessorObject, "computed", {
      enumerable: true,
      get: () => "not-plain-json",
    });
    const nonEnumerableObject = {};
    Object.defineProperty(nonEnumerableObject, "hidden", {
      enumerable: false,
      value: "not-plain-json",
    });
    const arrayWithExtraProperty = [];
    arrayWithExtraProperty.extra = "not-an-array-element";
    const invalidValues = [
      Number.NaN,
      Number.POSITIVE_INFINITY,
      -0,
      { missing: undefined },
      { callable: () => undefined },
      { symbolic: Symbol("not-json") },
      sparse,
      new Date("2026-07-28T00:00:00.000Z"),
      new Proxy({ valid: true }, {}),
      cyclic,
      accessorObject,
      nonEnumerableObject,
      arrayWithExtraProperty,
    ];

    try {
      for (const [index, value] of invalidValues.entries()) {
        assert.throws(
          () =>
            store.createRevisionedRecord({
              recordType: "invalid-json",
              recordId: String(index),
              value,
            }),
          (error) => error instanceof SQLiteStateStoreError && error.code === "INVALID_RECORD_VALUE",
        );
        assert.equal(store.readRevisionedRecord("invalid-json", String(index)), null);
      }
    } finally {
      store.close();
    }
  }));

test("record encoding ignores inherited object and array toJSON hooks", () =>
  withStorePath((databasePath) => {
    const originalObjectDescriptor = Object.getOwnPropertyDescriptor(
      Object.prototype,
      "toJSON",
    );
    const originalArrayDescriptor = Object.getOwnPropertyDescriptor(Array.prototype, "toJSON");
    let objectHookCalls = 0;
    let arrayHookCalls = 0;
    let store;

    Object.defineProperty(Object.prototype, "toJSON", {
      configurable: true,
      value() {
        objectHookCalls += 1;
        return { forgedByObjectPrototype: true };
      },
    });
    Object.defineProperty(Array.prototype, "toJSON", {
      configurable: true,
      value() {
        arrayHookCalls += 1;
        return ["forged-by-array-prototype"];
      },
    });

    try {
      store = openSQLiteStateStore(databasePath);
      const created = store.createRevisionedRecord({
        recordType: "strict-json",
        recordId: "inherited-to-json",
        value: { intended: true, nested: [{ preserved: true }] },
      });
      assert.deepEqual(created.value, {
        intended: true,
        nested: [{ preserved: true }],
      });
      assert.equal(objectHookCalls, 0);
      assert.equal(arrayHookCalls, 0);
      store.close();

      store = openSQLiteStateStore(databasePath);
      assert.deepEqual(store.readRevisionedRecord("strict-json", "inherited-to-json"), {
        recordType: "strict-json",
        recordId: "inherited-to-json",
        revision: 0,
        value: { intended: true, nested: [{ preserved: true }] },
      });
      assert.equal(objectHookCalls, 0);
      assert.equal(arrayHookCalls, 0);
    } finally {
      store?.close();
      if (originalArrayDescriptor === undefined) {
        delete Array.prototype.toJSON;
      } else {
        Object.defineProperty(Array.prototype, "toJSON", originalArrayDescriptor);
      }
      if (originalObjectDescriptor === undefined) {
        delete Object.prototype.toJSON;
      } else {
        Object.defineProperty(Object.prototype, "toJSON", originalObjectDescriptor);
      }
    }
  }));

test("record encoding ignores inherited array join hooks", () =>
  withStorePath((databasePath) => {
    const originalJoinDescriptor = Object.getOwnPropertyDescriptor(Array.prototype, "join");
    const originalJoin = originalJoinDescriptor.value;
    let targetedJoinCalls = 0;
    let schemaJoinCalls = 0;
    let store;

    Object.defineProperty(Array.prototype, "join", {
      configurable: true,
      writable: true,
      value(separator) {
        if (separator === "\n") {
          schemaJoinCalls += 1;
          return "forged-schema-fingerprint";
        }
        if (separator === "," && this.length === 2 && this[0] === "1" && this[1] === "2") {
          targetedJoinCalls += 1;
          return "9,9";
        }
        return Reflect.apply(originalJoin, this, [separator]);
      },
    });

    try {
      store = openSQLiteStateStore(databasePath);
      const created = store.createRevisionedRecord({
        recordType: "strict-json",
        recordId: "inherited-array-join",
        value: { intended: true, nested: [1, 2] },
      });
      assert.deepEqual(created.value, { intended: true, nested: [1, 2] });
      assert.equal(targetedJoinCalls, 0);
      assert.equal(schemaJoinCalls, 0);
      store.close();

      store = openSQLiteStateStore(databasePath);
      assert.deepEqual(store.readRevisionedRecord("strict-json", "inherited-array-join"), {
        recordType: "strict-json",
        recordId: "inherited-array-join",
        revision: 0,
        value: { intended: true, nested: [1, 2] },
      });
      assert.equal(targetedJoinCalls, 0);
      assert.equal(schemaJoinCalls, 0);
      assert.equal(store.mode, "ACTIVE");
    } finally {
      store?.close();
      Object.defineProperty(Array.prototype, "join", originalJoinDescriptor);
    }
  }));

test("record encoding ignores inherited string and number helper hooks", () =>
  withStorePath((databasePath) => {
    const originalCharCodeAtDescriptor = Object.getOwnPropertyDescriptor(
      String.prototype,
      "charCodeAt",
    );
    const originalPadStartDescriptor = Object.getOwnPropertyDescriptor(
      String.prototype,
      "padStart",
    );
    const originalNumberToStringDescriptor = Object.getOwnPropertyDescriptor(
      Number.prototype,
      "toString",
    );
    const originalCharCodeAt = originalCharCodeAtDescriptor.value;
    const originalPadStart = originalPadStartDescriptor.value;
    const originalNumberToString = originalNumberToStringDescriptor.value;
    let charCodeAtCalls = 0;
    let padStartCalls = 0;
    let numberToStringCalls = 0;
    let store;

    Object.defineProperty(String.prototype, "charCodeAt", {
      configurable: true,
      writable: true,
      value(index) {
        charCodeAtCalls += 1;
        return Reflect.apply(originalCharCodeAt, this, [index]);
      },
    });
    Object.defineProperty(String.prototype, "padStart", {
      configurable: true,
      writable: true,
      value(targetLength, fillString) {
        padStartCalls += 1;
        return Reflect.apply(originalPadStart, this, [targetLength, fillString]);
      },
    });
    Object.defineProperty(Number.prototype, "toString", {
      configurable: true,
      writable: true,
      value(radix) {
        numberToStringCalls += 1;
        return Reflect.apply(originalNumberToString, this, [radix]);
      },
    });

    try {
      const intended = { text: "control:\u0001 astral:😀 lone:\ud800", number: 987654321 };
      store = openSQLiteStateStore(databasePath);
      const created = store.createRevisionedRecord({
        recordType: "strict-json",
        recordId: "inherited-string-number-helpers",
        value: intended,
      });
      assert.deepEqual(created.value, intended);
      assert.equal(charCodeAtCalls, 0);
      assert.equal(padStartCalls, 0);
      assert.equal(numberToStringCalls, 0);
      store.close();

      store = openSQLiteStateStore(databasePath);
      assert.deepEqual(
        store.readRevisionedRecord("strict-json", "inherited-string-number-helpers"),
        {
          recordType: "strict-json",
          recordId: "inherited-string-number-helpers",
          revision: 0,
          value: intended,
        },
      );
      assert.equal(charCodeAtCalls, 0);
      assert.equal(padStartCalls, 0);
      assert.equal(numberToStringCalls, 0);
      assert.equal(store.mode, "ACTIVE");
    } finally {
      store?.close();
      Object.defineProperty(
        Number.prototype,
        "toString",
        originalNumberToStringDescriptor,
      );
      Object.defineProperty(String.prototype, "padStart", originalPadStartDescriptor);
      Object.defineProperty(String.prototype, "charCodeAt", originalCharCodeAtDescriptor);
    }
  }));

test("record validation ignores inherited RegExp test hooks", () =>
  withStorePath((databasePath) => {
    const originalTestDescriptor = Object.getOwnPropertyDescriptor(RegExp.prototype, "test");
    const originalTest = originalTestDescriptor.value;
    let targetedCalls = 0;
    const value = [1, 2];
    value.extra = "MUST_NOT_DISAPPEAR";
    let store;

    Object.defineProperty(RegExp.prototype, "test", {
      configurable: true,
      writable: true,
      value(candidate) {
        if (candidate === "extra") {
          targetedCalls += 1;
          return true;
        }
        return Reflect.apply(originalTest, this, [candidate]);
      },
    });

    try {
      store = openSQLiteStateStore(databasePath);
      assert.throws(
        () =>
          store.createRevisionedRecord({
            recordType: "strict-json",
            recordId: "inherited-regexp-test",
            value,
          }),
        (error) =>
          error instanceof SQLiteStateStoreError && error.code === "INVALID_RECORD_VALUE",
      );
      assert.equal(targetedCalls, 0);
      assert.equal(store.readRevisionedRecord("strict-json", "inherited-regexp-test"), null);
      assert.equal(store.mode, "ACTIVE");
    } finally {
      store?.close();
      Object.defineProperty(RegExp.prototype, "test", originalTestDescriptor);
    }
  }));

test("explicit close remains distinct from SAFE_MODE", () =>
  withStorePath((databasePath) => {
    const store = openSQLiteStateStore(databasePath);
    store.close();

    assert.equal(store.isClosed, true);
    assert.equal(store.mode, SQLITE_STORE_MODE.ACTIVE);
    assert.throws(
      () => store.readRevisionedRecord("session", "closed"),
      (error) => error instanceof SQLiteStateStoreError && error.code === "STORE_CLOSED",
    );
    assert.throws(
      () =>
        store.createRevisionedRecord({
          recordType: "session",
          recordId: "closed",
          value: { state: "DENIED" },
        }),
      (error) => error instanceof SQLiteStateStoreError && error.code === "STORE_CLOSED",
    );
  }));

test("compare-and-swap reports revision exhaustion without modifying the record", () =>
  withStorePath((databasePath) => {
    let store = openSQLiteStateStore(databasePath);
    store.createRevisionedRecord({
      recordType: "session",
      recordId: "exhausted",
      value: { state: "AT_LIMIT" },
    });
    store.close();

    const database = new DatabaseSync(databasePath);
    try {
      database
        .prepare(
          `UPDATE revisioned_records
              SET revision = ?
            WHERE record_type = 'session' AND record_id = 'exhausted'`,
        )
        .run(Number.MAX_SAFE_INTEGER);
    } finally {
      database.close();
    }

    store = openSQLiteStateStore(databasePath);
    try {
      assert.throws(
        () =>
          store.compareAndSwapRevision({
            recordType: "session",
            recordId: "exhausted",
            expectedRevision: Number.MAX_SAFE_INTEGER,
            value: { state: "MUST_NOT_WRITE" },
          }),
        (error) => error instanceof SQLiteStateStoreError && error.code === "REVISION_EXHAUSTED",
      );
      assert.deepEqual(store.readRevisionedRecord("session", "exhausted"), {
        recordType: "session",
        recordId: "exhausted",
        revision: Number.MAX_SAFE_INTEGER,
        value: { state: "AT_LIMIT" },
      });
    } finally {
      store.close();
    }
  }));
