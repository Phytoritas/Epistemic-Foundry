import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";

import {
  SQLITE_STORE_MODE,
  SQLiteStateStoreError,
  openSQLiteStateStore,
} from "./sqlite-state-store.mjs";

const expectCode = (code) => (error) =>
  error instanceof SQLiteStateStoreError && error.code === code;

const withDatabasePath = (prefix, callback) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  const databasePath = path.join(directory, "foundry.db");
  try {
    return callback(databasePath);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
};

const createRawDatabase = (databasePath, revisionedRecordsSql) => {
  const database = new DatabaseSync(databasePath);
  try {
    database.exec("PRAGMA journal_mode = WAL");
    database.exec(`
      CREATE TABLE ef_store_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      ) STRICT;
      ${revisionedRecordsSql};
      INSERT INTO ef_store_metadata (key, value) VALUES ('schema_version', '1');
    `);
  } finally {
    database.close();
  }
};

const canonicalRevisionedRecordsSql = `
  CREATE TABLE revisioned_records (
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 0 AND revision <= 9007199254740991),
    value_json TEXT NOT NULL CHECK (json_valid(value_json)),
    PRIMARY KEY (record_type, record_id)
  ) STRICT
`;

test("integrity failure enters SAFE_MODE and denies every mutation path", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "foundry-d01-integrity-"));
  const databasePath = path.join(directory, "foundry.db");
  let store;

  try {
    store = openSQLiteStateStore(databasePath);
    store.createRevisionedRecord({
      recordType: "session",
      recordId: "before-corruption",
      value: { state: "READY" },
    });
    store.close();
    store = undefined;

    const descriptor = fs.openSync(databasePath, "r+");
    try {
      fs.writeSync(descriptor, Buffer.from("CORRUPT!"), 0, 8, 0);
    } finally {
      fs.closeSync(descriptor);
    }

    store = openSQLiteStateStore(databasePath);
    assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);
    assert.equal(store.health().mode, SQLITE_STORE_MODE.SAFE_MODE);
    assert.equal(store.safeModeReason.code, "SQLITE_INTEGRITY_FAILED");

    assert.throws(
      () =>
        store.createRevisionedRecord({
          recordType: "session",
          recordId: "denied",
          value: { state: "MUST_NOT_WRITE" },
        }),
      expectCode("STORE_SAFE_MODE"),
    );
    assert.throws(
      () =>
        store.compareAndSwapRevision({
          recordType: "session",
          recordId: "before-corruption",
          expectedRevision: 0,
          value: { state: "MUST_NOT_WRITE" },
        }),
      expectCode("STORE_SAFE_MODE"),
    );
    assert.throws(
      () => store.transaction(() => undefined),
      expectCode("STORE_SAFE_MODE"),
    );
  } finally {
    if (store !== undefined) {
      store.close();
    }
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

const malformedSchemas = [
  {
    name: "missing composite primary key with duplicate rows",
    sql: `CREATE TABLE revisioned_records (
      record_type TEXT NOT NULL,
      record_id TEXT NOT NULL,
      revision INTEGER NOT NULL CHECK (revision >= 0),
      value_json TEXT NOT NULL CHECK (json_valid(value_json))
    ) STRICT`,
    seed: `INSERT INTO revisioned_records VALUES
      ('candidate', 'duplicate', 0, '{}'),
      ('candidate', 'duplicate', 0, '{}')`,
  },
  {
    name: "non-STRICT table",
    sql: canonicalRevisionedRecordsSql.replace(/\) STRICT\s*$/, ")"),
  },
  {
    name: "wrong revision type",
    sql: canonicalRevisionedRecordsSql.replace("revision INTEGER", "revision TEXT"),
  },
  {
    name: "nullable record identifier",
    sql: canonicalRevisionedRecordsSql.replace("record_id TEXT NOT NULL", "record_id TEXT"),
  },
  {
    name: "reversed primary-key order",
    sql: canonicalRevisionedRecordsSql.replace(
      "PRIMARY KEY (record_type, record_id)",
      "PRIMARY KEY (record_id, record_type)",
    ),
  },
  {
    name: "missing non-negative revision check",
    sql: canonicalRevisionedRecordsSql.replace(
      " CHECK (revision >= 0 AND revision <= 9007199254740991)",
      "",
    ),
  },
  {
    name: "missing safe-integer revision ceiling",
    sql: canonicalRevisionedRecordsSql.replace(
      "revision >= 0 AND revision <= 9007199254740991",
      "revision >= 0",
    ),
  },
  {
    name: "missing JSON validity check",
    sql: canonicalRevisionedRecordsSql.replace(" CHECK (json_valid(value_json))", ""),
  },
];

for (const malformed of malformedSchemas) {
  test(`schema drift enters SAFE_MODE: ${malformed.name}`, () =>
    withDatabasePath("foundry-d01-schema-", (databasePath) => {
      createRawDatabase(databasePath, malformed.sql);
      if (malformed.seed !== undefined) {
        const database = new DatabaseSync(databasePath);
        try {
          database.exec(malformed.seed);
          const integrityRows = database.prepare("PRAGMA integrity_check").all();
          assert.equal(integrityRows.length, 1);
          assert.equal(integrityRows[0].integrity_check, "ok");
        } finally {
          database.close();
        }
      }

      const store = openSQLiteStateStore(databasePath);
      try {
        assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);
        assert.equal(store.safeModeReason.code, "SQLITE_SCHEMA_FINGERPRINT_MISMATCH");
        assert.throws(
          () =>
            store.compareAndSwapRevision({
              recordType: "candidate",
              recordId: "duplicate",
              expectedRevision: 0,
              value: { state: "MUST_NOT_WRITE" },
            }),
          expectCode("STORE_SAFE_MODE"),
        );
      } finally {
        store.close();
      }
    }));
}

test("invalid persisted JSON enters SAFE_MODE during reopen", () =>
  withDatabasePath("foundry-d01-json-reopen-", (databasePath) => {
    let store = openSQLiteStateStore(databasePath);
    store.createRevisionedRecord({
      recordType: "candidate",
      recordId: "invalid-on-reopen",
      value: { valid: true },
    });
    store.close();

    const database = new DatabaseSync(databasePath);
    try {
      const update = database
        .prepare(
          `UPDATE revisioned_records
              SET value_json = '1e400'
            WHERE record_type = 'candidate' AND record_id = 'invalid-on-reopen'`,
        )
        .run();
      assert.equal(Number(update.changes), 1);
      assert.equal(
        Number(
          database
            .prepare(
              `SELECT json_valid(value_json) AS valid
                 FROM revisioned_records
                WHERE record_type = 'candidate' AND record_id = 'invalid-on-reopen'`,
            )
            .get().valid,
        ),
        1,
      );
    } finally {
      database.close();
    }

    store = openSQLiteStateStore(databasePath);
    try {
      assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);
      assert.equal(store.safeModeReason.code, "SQLITE_PERSISTED_JSON_INVALID");
      assert.throws(
        () =>
          store.createRevisionedRecord({
            recordType: "candidate",
            recordId: "denied",
            value: { state: "MUST_NOT_WRITE" },
          }),
        expectCode("STORE_SAFE_MODE"),
      );
    } finally {
      store.close();
    }
  }));

test("checkIntegrity detects runtime JSON corruption and enters SAFE_MODE", () =>
  withDatabasePath("foundry-d01-json-check-", (databasePath) => {
    const store = openSQLiteStateStore(databasePath);
    try {
      store.createRevisionedRecord({
        recordType: "candidate",
        recordId: "invalid-at-check",
        value: { valid: true },
      });

      const corrupter = new DatabaseSync(databasePath);
      try {
        corrupter.exec("PRAGMA ignore_check_constraints = ON");
        const update = corrupter
          .prepare(
            `UPDATE revisioned_records
                SET value_json = '{'
              WHERE record_type = 'candidate' AND record_id = 'invalid-at-check'`,
          )
          .run();
        assert.equal(Number(update.changes), 1);
      } finally {
        corrupter.close();
      }

      const integrity = store.checkIntegrity();
      assert.equal(integrity.ok, false);
      assert.equal(integrity.mode, SQLITE_STORE_MODE.SAFE_MODE);
      assert.equal(store.safeModeReason.code, "SQLITE_PERSISTED_JSON_INVALID");
      assert.throws(
        () => store.readRevisionedRecord("candidate", "invalid-at-check"),
        expectCode("STORE_SAFE_MODE"),
      );
    } finally {
      store.close();
    }
  }));

test("runtime JSON corruption fails the read and immediately enters SAFE_MODE", () =>
  withDatabasePath("foundry-d01-json-runtime-", (databasePath) => {
    const store = openSQLiteStateStore(databasePath);
    try {
      store.createRevisionedRecord({
        recordType: "candidate",
        recordId: "invalid-at-runtime",
        value: { valid: true },
      });

      const corrupter = new DatabaseSync(databasePath);
      try {
        corrupter.exec("PRAGMA ignore_check_constraints = ON");
        corrupter
          .prepare(
            `UPDATE revisioned_records
                SET value_json = '{'
              WHERE record_type = 'candidate' AND record_id = 'invalid-at-runtime'`,
          )
          .run();
      } finally {
        corrupter.close();
      }

      assert.throws(
        () => store.readRevisionedRecord("candidate", "invalid-at-runtime"),
        expectCode("SQLITE_PERSISTED_JSON_INVALID"),
      );
      assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);
      assert.equal(store.safeModeReason.code, "SQLITE_PERSISTED_JSON_INVALID");
      assert.throws(
        () =>
          store.compareAndSwapRevision({
            recordType: "candidate",
            recordId: "invalid-at-runtime",
            expectedRevision: 0,
            value: { valid: false },
          }),
        expectCode("STORE_SAFE_MODE"),
      );
    } finally {
      store.close();
    }
  }));

test("runtime revision corruption is detected on read and enters SAFE_MODE", () =>
  withDatabasePath("foundry-d01-revision-runtime-", (databasePath) => {
    const store = openSQLiteStateStore(databasePath);
    try {
      store.createRevisionedRecord({
        recordType: "candidate",
        recordId: "invalid-revision",
        value: { valid: true },
      });

      const corrupter = new DatabaseSync(databasePath);
      try {
        corrupter.exec("PRAGMA ignore_check_constraints = ON");
        const update = corrupter
          .prepare(
            `UPDATE revisioned_records
                SET revision = 9007199254740992
              WHERE record_type = 'candidate' AND record_id = 'invalid-revision'`,
          )
          .run();
        assert.equal(Number(update.changes), 1);
      } finally {
        corrupter.close();
      }

      assert.throws(
        () => store.readRevisionedRecord("candidate", "invalid-revision"),
        expectCode("SQLITE_PERSISTED_REVISION_INVALID"),
      );
      assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);
      assert.equal(store.safeModeReason.code, "SQLITE_PERSISTED_REVISION_INVALID");
    } finally {
      store.close();
    }
  }));

const runtimeSchemaVersionDriftCases = [
  {
    name: "read",
    invoke: (store) => store.readRevisionedRecord("candidate", "version-drift"),
    assertInitialResult: (operation) =>
      assert.throws(operation, expectCode("SQLITE_SCHEMA_VERSION_MISMATCH")),
  },
  {
    name: "integrity check",
    invoke: (store) => store.checkIntegrity(),
    assertInitialResult(operation) {
      const result = operation();
      assert.equal(result.ok, false);
      assert.equal(result.mode, SQLITE_STORE_MODE.SAFE_MODE);
    },
  },
  {
    name: "mutation",
    invoke: (store) =>
      store.createRevisionedRecord({
        recordType: "candidate",
        recordId: "must-not-write-after-version-drift",
        value: { valid: false },
      }),
    assertInitialResult: (operation) =>
      assert.throws(operation, expectCode("SQLITE_SCHEMA_VERSION_MISMATCH")),
  },
];

for (const driftCase of runtimeSchemaVersionDriftCases) {
  test(`runtime schema-version drift enters SAFE_MODE before ${driftCase.name}`, () =>
    withDatabasePath("foundry-d01-version-runtime-", (databasePath) => {
      const store = openSQLiteStateStore(databasePath);
      try {
        store.createRevisionedRecord({
          recordType: "candidate",
          recordId: "version-drift",
          value: { valid: true },
        });

        const corrupter = new DatabaseSync(databasePath);
        try {
          const update = corrupter
            .prepare(
              `UPDATE ef_store_metadata
                  SET value = '999'
                WHERE key = 'schema_version'`,
            )
            .run();
          assert.equal(Number(update.changes), 1);
        } finally {
          corrupter.close();
        }

        driftCase.assertInitialResult(() => driftCase.invoke(store));
        assert.equal(store.mode, SQLITE_STORE_MODE.SAFE_MODE);
        assert.equal(store.safeModeReason.code, "SQLITE_SCHEMA_VERSION_MISMATCH");
        assert.deepEqual(store.safeModeReason.details, { expected: "1", actual: "999" });
        assert.throws(
          () =>
            store.createRevisionedRecord({
              recordType: "candidate",
              recordId: "denied-after-version-drift",
              value: { valid: false },
            }),
          expectCode("STORE_SAFE_MODE"),
        );
      } finally {
        store.close();
      }
    }));
}
