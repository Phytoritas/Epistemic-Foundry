import { createHash } from "node:crypto";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { types as utilTypes } from "node:util";

const STRING_CHAR_CODE_AT = Function.prototype.call.bind(String.prototype.charCodeAt);
const STRING_TO_LOWER_CASE = Function.prototype.call.bind(String.prototype.toLowerCase);
const STRING_INCLUDES = Function.prototype.call.bind(String.prototype.includes);
const STRING_STARTS_WITH = Function.prototype.call.bind(String.prototype.startsWith);
const NUMBER_TO_STRING = Function.prototype.call.bind(Number.prototype.toString);
const PROMISE_THEN = Function.prototype.call.bind(Promise.prototype.then);
const ARRAY_SORT = Function.prototype.call.bind(Array.prototype.sort);
const WEAK_SET_HAS = Function.prototype.call.bind(WeakSet.prototype.has);
const WEAK_SET_ADD = Function.prototype.call.bind(WeakSet.prototype.add);
const WEAK_SET_DELETE = Function.prototype.call.bind(WeakSet.prototype.delete);
const ARRAY_IS_ARRAY = Array.isArray;
const ARRAY_CONSTRUCTOR = Array;
const OBJECT_IS = Object.is;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_DEFINE_PROPERTY = Object.defineProperty;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_DELETE_PROPERTY = Reflect.deleteProperty;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const NUMBER_IS_FINITE = Number.isFinite;
const NUMBER_IS_SAFE_INTEGER = Number.isSafeInteger;
const TO_NUMBER = Number;
const JSON_PARSE = JSON.parse;
const PROMISE_CONSTRUCTOR = Promise;
const PROMISE_SPECIES = Symbol.species;
const PROMISE_SPECIES_DESCRIPTOR = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(
  PROMISE_CONSTRUCTOR,
  PROMISE_SPECIES,
);
const PROMISE_OBSERVER_CONSTRUCTOR = OBJECT_FREEZE({
  [PROMISE_SPECIES]: PROMISE_CONSTRUCTOR,
});
const WEAK_SET_CONSTRUCTOR = WeakSet;
const DATE_NOW = Date.now;
const ATOMICS_WAIT = Atomics.wait;
const MATH_MIN = Math.min;
const IS_PROXY = utilTypes.isProxy;
const IS_PROMISE = utilTypes.isPromise;
const SCHEMA_VERSION = 1;
const SCHEMA_VERSION_TEXT = "1";
const MAX_REVISION = Number.MAX_SAFE_INTEGER;
const DEFAULT_BUSY_TIMEOUT_MS = 5_000;
const MAX_BUSY_TIMEOUT_MS = 60_000;
const BUSY_RETRY_INTERVAL_MS = 10;
const BUSY_RETRY_CELL = new Int32Array(new SharedArrayBuffer(Int32Array.BYTES_PER_ELEMENT));
const CANONICAL_TABLE_SQL = OBJECT_FREEZE({
  ef_store_metadata: `CREATE TABLE ef_store_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
  ) STRICT`,
  revisioned_records: `CREATE TABLE revisioned_records (
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 0 AND revision <= ${MAX_REVISION}),
    value_json TEXT NOT NULL CHECK (json_valid(value_json)),
    PRIMARY KEY (record_type, record_id)
  ) STRICT`,
});
const CANONICAL_TABLE_NAMES = OBJECT_FREEZE(["ef_store_metadata", "revisioned_records"]);
const CANONICAL_COLUMNS = OBJECT_FREEZE({
  ef_store_metadata: OBJECT_FREEZE([
    OBJECT_FREEZE({
      cid: 0,
      name: "key",
      type: "TEXT",
      notnull: 1,
      dfltValue: null,
      pk: 1,
      hidden: 0,
    }),
    OBJECT_FREEZE({
      cid: 1,
      name: "value",
      type: "TEXT",
      notnull: 1,
      dfltValue: null,
      pk: 0,
      hidden: 0,
    }),
  ]),
  revisioned_records: OBJECT_FREEZE([
    OBJECT_FREEZE({
      cid: 0,
      name: "record_type",
      type: "TEXT",
      notnull: 1,
      dfltValue: null,
      pk: 1,
      hidden: 0,
    }),
    OBJECT_FREEZE({
      cid: 1,
      name: "record_id",
      type: "TEXT",
      notnull: 1,
      dfltValue: null,
      pk: 2,
      hidden: 0,
    }),
    OBJECT_FREEZE({
      cid: 2,
      name: "revision",
      type: "INTEGER",
      notnull: 1,
      dfltValue: null,
      pk: 0,
      hidden: 0,
    }),
    OBJECT_FREEZE({
      cid: 3,
      name: "value_json",
      type: "TEXT",
      notnull: 1,
      dfltValue: null,
      pk: 0,
      hidden: 0,
    }),
  ]),
});
const CANONICAL_PRIMARY_KEYS = OBJECT_FREEZE({
  ef_store_metadata: OBJECT_FREEZE(["key"]),
  revisioned_records: OBJECT_FREEZE(["record_type", "record_id"]),
});

export const SQLITE_STORE_MODE = OBJECT_FREEZE({
  ACTIVE: "ACTIVE",
  SAFE_MODE: "SAFE_MODE",
});

export class SQLiteStateStoreError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "SQLiteStateStoreError";
    this.code = code;
    if (details !== undefined) this.details = OBJECT_FREEZE({ ...details });
  }
}

const fail = (code, message, details) => {
  throw new SQLiteStateStoreError(code, message, details);
};

const requireNonEmptyString = (value, label) => {
  if (typeof value !== "string" || value.length === 0) {
    fail("INVALID_INPUT", `${label} must be a non-empty string`);
  }
  return value;
};

const requireRevision = (value, label = "revision") => {
  if (!NUMBER_IS_SAFE_INTEGER(value) || value < 0) {
    fail("INVALID_REVISION", `${label} must be a non-negative safe integer`);
  }
  return value;
};

const isCanonicalArrayIndex = (key, length) => {
  if (typeof key !== "string" || key.length === 0) return false;
  const first = STRING_CHAR_CODE_AT(key, 0);
  if (first === 0x30) return key.length === 1 && length > 0;
  if (first < 0x31 || first > 0x39) return false;

  let index = first - 0x30;
  for (let offset = 1; offset < key.length; offset += 1) {
    const codeUnit = STRING_CHAR_CODE_AT(key, offset);
    if (codeUnit < 0x30 || codeUnit > 0x39) return false;
    const digit = codeUnit - 0x30;
    if (index > (MAX_REVISION - digit) / 10) return false;
    index = index * 10 + digit;
  }
  return index < length;
};

const assertJsonValue = (
  value,
  pathLabel = "value",
  ancestors = new WEAK_SET_CONSTRUCTOR(),
) => {
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!NUMBER_IS_FINITE(value) || OBJECT_IS(value, -0)) {
      fail("INVALID_RECORD_VALUE", `${pathLabel} contains a non-finite number`);
    }
    return;
  }
  if (typeof value !== "object") {
    fail("INVALID_RECORD_VALUE", `${pathLabel} contains a non-JSON value`);
  }
  if (IS_PROXY(value)) {
    fail("INVALID_RECORD_VALUE", `${pathLabel} contains a Proxy`);
  }
  if (WEAK_SET_HAS(ancestors, value)) {
    fail("INVALID_RECORD_VALUE", `${pathLabel} contains a cyclic reference`);
  }

    WEAK_SET_ADD(ancestors, value);
  try {
    if (ARRAY_IS_ARRAY(value)) {
      const keys = REFLECT_OWN_KEYS(value);
      for (let keyIndex = 0; keyIndex < keys.length; keyIndex += 1) {
        const key = keys[keyIndex];
        if (key === "length") continue;
        if (!isCanonicalArrayIndex(key, value.length)) {
          fail("INVALID_RECORD_VALUE", `${pathLabel} contains a non-element property`);
        }
      }
      for (let index = 0; index < value.length; index += 1) {
        const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, NUMBER_TO_STRING(index));
        if (descriptor === undefined) {
          fail("INVALID_RECORD_VALUE", `${pathLabel} contains a sparse array`);
        }
        if (!OBJECT_HAS_OWN(descriptor, "value")) {
          fail("INVALID_RECORD_VALUE", `${pathLabel}[${index}] is not a plain JSON element`);
        }
        assertJsonValue(descriptor.value, `${pathLabel}[${index}]`, ancestors);
      }
      return;
    }

    const prototype = OBJECT_GET_PROTOTYPE_OF(value);
    if (prototype !== PLAIN_OBJECT_PROTOTYPE && prototype !== null) {
      fail("INVALID_RECORD_VALUE", `${pathLabel} must contain only plain JSON objects`);
    }
    const keys = REFLECT_OWN_KEYS(value);
    for (let keyIndex = 0; keyIndex < keys.length; keyIndex += 1) {
      const key = keys[keyIndex];
      if (typeof key !== "string") {
        fail("INVALID_RECORD_VALUE", `${pathLabel} contains a symbol-keyed property`);
      }
      const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
      if (!descriptor.enumerable || !OBJECT_HAS_OWN(descriptor, "value")) {
        fail("INVALID_RECORD_VALUE", `${pathLabel}.${key} is not a plain JSON property`);
      }
      assertJsonValue(descriptor.value, `${pathLabel}.${key}`, ancestors);
    }
  } finally {
    WEAK_SET_DELETE(ancestors, value);
  }
};

const encodeJsonString = (value) => {
  let encoded = '"';
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = STRING_CHAR_CODE_AT(value, index);
    if (codeUnit === 0x22) {
      encoded += '\\"';
    } else if (codeUnit === 0x5c) {
      encoded += "\\\\";
    } else if (codeUnit === 0x08) {
      encoded += "\\b";
    } else if (codeUnit === 0x0c) {
      encoded += "\\f";
    } else if (codeUnit === 0x0a) {
      encoded += "\\n";
    } else if (codeUnit === 0x0d) {
      encoded += "\\r";
    } else if (codeUnit === 0x09) {
      encoded += "\\t";
    } else if (codeUnit <= 0x1f) {
      const hexadecimal = NUMBER_TO_STRING(codeUnit, 16);
      const padding = hexadecimal.length === 1 ? "000" : "00";
      encoded += `\\u${padding}${hexadecimal}`;
    } else if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const nextCodeUnit = STRING_CHAR_CODE_AT(value, index + 1);
      if (nextCodeUnit >= 0xdc00 && nextCodeUnit <= 0xdfff) {
        encoded += value[index] + value[index + 1];
        index += 1;
      } else {
        encoded += `\\u${NUMBER_TO_STRING(codeUnit, 16)}`;
      }
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      encoded += `\\u${NUMBER_TO_STRING(codeUnit, 16)}`;
    } else {
      encoded += value[index];
    }
  }
  return `${encoded}"`;
};

const encodeValidatedJsonValue = (value) => {
  if (value === null) return "null";
  if (typeof value === "string") return encodeJsonString(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return NUMBER_TO_STRING(value);
  if (ARRAY_IS_ARRAY(value)) {
    let encoded = "[";
    for (let index = 0; index < value.length; index += 1) {
      const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, NUMBER_TO_STRING(index));
      if (index !== 0) encoded += ",";
      encoded += encodeValidatedJsonValue(descriptor.value);
    }
    return `${encoded}]`;
  }

  let encoded = "{";
  const keys = REFLECT_OWN_KEYS(value);
  for (let index = 0; index < keys.length; index += 1) {
    const key = keys[index];
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (index !== 0) encoded += ",";
    encoded += `${encodeJsonString(key)}:${encodeValidatedJsonValue(descriptor.value)}`;
  }
  return `${encoded}}`;
};

const encodeJson = (value) => {
  assertJsonValue(value);
  return encodeValidatedJsonValue(value);
};

const decodeCanonicalJson = (encoded, pathLabel) => {
  const value = JSON_PARSE(encoded);
  assertJsonValue(value, pathLabel);
  if (encoded !== encodeValidatedJsonValue(value)) {
    fail("INVALID_RECORD_VALUE", `${pathLabel} is not canonically encoded`);
  }
  return value;
};

const isThenable = (value) => {
  if (
    value === null ||
    (typeof value !== "object" && typeof value !== "function")
  ) {
    return false;
  }
  if (IS_PROXY(value) || IS_PROMISE(value)) return true;

  let current = value;
  while (current !== null) {
    if (IS_PROXY(current)) return true;
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(current, "then");
    if (descriptor !== undefined) {
      if (!OBJECT_HAS_OWN(descriptor, "value")) return true;
      return typeof descriptor.value === "function";
    }
    current = OBJECT_GET_PROTOTYPE_OF(current);
  }
  return false;
};

const sameAccessorDescriptor = (actual, expected) =>
  actual !== undefined &&
  expected !== undefined &&
  !OBJECT_HAS_OWN(actual, "value") &&
  !OBJECT_HAS_OWN(expected, "value") &&
  actual.get === expected.get &&
  actual.set === expected.set &&
  actual.enumerable === expected.enumerable &&
  actual.configurable === expected.configurable;

const hasTrustedLocalPromiseConstructor = (value) => {
  let current = value;
  for (let depth = 0; depth < 2 && current !== null; depth += 1) {
    if (IS_PROXY(current)) return false;
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(current, "constructor");
    if (descriptor !== undefined) {
      return (
        OBJECT_HAS_OWN(descriptor, "value") &&
        descriptor.value === PROMISE_CONSTRUCTOR &&
        sameAccessorDescriptor(
          OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(PROMISE_CONSTRUCTOR, PROMISE_SPECIES),
          PROMISE_SPECIES_DESCRIPTOR,
        )
      );
    }
    current = OBJECT_GET_PROTOTYPE_OF(current);
  }
  return false;
};

const observeNativePromiseRejectionWithoutUserCode = (value) => {
  if (!IS_PROMISE(value) || IS_PROXY(value)) return false;
  if (hasTrustedLocalPromiseConstructor(value)) {
    PROMISE_THEN(value, undefined, () => undefined);
    return true;
  }

  let shadowOwner = value;
  let originalConstructorDescriptor;
  let constructorShadowed = false;
  for (let depth = 0; depth < 2 && shadowOwner !== null; depth += 1) {
    if (IS_PROXY(shadowOwner)) return false;
    originalConstructorDescriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(
      shadowOwner,
      "constructor",
    );
    if (originalConstructorDescriptor === undefined) {
      try {
        OBJECT_DEFINE_PROPERTY(shadowOwner, "constructor", {
          configurable: true,
          enumerable: false,
          value: PROMISE_OBSERVER_CONSTRUCTOR,
          writable: true,
        });
        originalConstructorDescriptor = undefined;
        constructorShadowed = true;
        break;
      } catch {
        shadowOwner = OBJECT_GET_PROTOTYPE_OF(shadowOwner);
        continue;
      }
    }
    if (!originalConstructorDescriptor.configurable) return false;
    OBJECT_DEFINE_PROPERTY(shadowOwner, "constructor", {
      configurable: true,
      enumerable: false,
      value: PROMISE_OBSERVER_CONSTRUCTOR,
      writable: true,
    });
    constructorShadowed = true;
    break;
  }
  if (!constructorShadowed) return false;

  try {
    PROMISE_THEN(value, undefined, () => undefined);
    return true;
  } catch {
    return false;
  } finally {
    if (originalConstructorDescriptor === undefined) {
      REFLECT_DELETE_PROPERTY(shadowOwner, "constructor");
    } else {
      OBJECT_DEFINE_PROPERTY(shadowOwner, "constructor", originalConstructorDescriptor);
    }
  }
};

const isIntegrityError = (error) => {
  if (!(error instanceof Error)) return false;
  if (error.errcode === 11 || error.errcode === 26) return true;
  const message = STRING_TO_LOWER_CASE(error.message);
  return (
    STRING_INCLUDES(message, "database disk image is malformed") ||
    STRING_INCLUDES(message, "file is not a database") ||
    STRING_INCLUDES(message, "database corruption") ||
    STRING_INCLUDES(message, "database malformed")
  );
};

const isSQLiteBusyError = (error) => error instanceof Error && error.errcode === 5;

const configureWalJournal = (database, busyTimeoutMs) => {
  const deadline = DATE_NOW() + busyTimeoutMs;
  while (true) {
    try {
      return database.prepare("PRAGMA journal_mode = WAL").get();
    } catch (error) {
      const remainingMs = deadline - DATE_NOW();
      if (!isSQLiteBusyError(error) || remainingMs <= 0) throw error;
      ATOMICS_WAIT(BUSY_RETRY_CELL, 0, 0, MATH_MIN(BUSY_RETRY_INTERVAL_MS, remainingMs));
    }
  }
};

const isSqlWhitespace = (codeUnit) =>
  codeUnit === 0x20 || (codeUnit >= 0x09 && codeUnit <= 0x0d);

const normalizeSchemaSql = (sql) => {
  const source = typeof sql === "string" ? sql : "";
  let start = 0;
  let end = source.length;
  while (start < end && isSqlWhitespace(STRING_CHAR_CODE_AT(source, start))) start += 1;
  while (end > start && isSqlWhitespace(STRING_CHAR_CODE_AT(source, end - 1))) end -= 1;
  if (end > start && STRING_CHAR_CODE_AT(source, end - 1) === 0x3b) end -= 1;

  let normalized = "";
  let pendingSpace = false;
  for (let index = start; index < end; index += 1) {
    if (isSqlWhitespace(STRING_CHAR_CODE_AT(source, index))) {
      pendingSpace = true;
    } else {
      if (pendingSpace && normalized.length !== 0) normalized += " ";
      normalized += source[index];
      pendingSpace = false;
    }
  }
  if (pendingSpace && normalized.length !== 0) normalized += " ";
  return STRING_TO_LOWER_CASE(normalized);
};

const fingerprintSchema = (rows) => {
  const entries = new ARRAY_CONSTRUCTOR(rows.length);
  for (let index = 0; index < rows.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(rows, NUMBER_TO_STRING(index));
    const row = descriptor.value;
    entries[index] = `${row.name}:${normalizeSchemaSql(row.sql)}`;
  }
  ARRAY_SORT(entries);
  let material = "";
  for (let index = 0; index < entries.length; index += 1) {
    if (index !== 0) material += "\n";
    material += entries[index];
  }
  return `sha256:${createHash("sha256").update(material, "utf8").digest("hex")}`;
};

const CANONICAL_SCHEMA_ROWS = OBJECT_FREEZE([
  OBJECT_FREEZE({
    name: "ef_store_metadata",
    sql: CANONICAL_TABLE_SQL.ef_store_metadata,
  }),
  OBJECT_FREEZE({
    name: "revisioned_records",
    sql: CANONICAL_TABLE_SQL.revisioned_records,
  }),
]);
const CANONICAL_SCHEMA_FINGERPRINT = fingerprintSchema(CANONICAL_SCHEMA_ROWS);

const sameJsonShape = (actual, expected) => encodeJson(actual) === encodeJson(expected);

const readOwnArrayElement = (values, index) => {
  const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(values, NUMBER_TO_STRING(index));
  if (descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")) {
    fail("SQLITE_RESULT_SHAPE_INVALID", "SQLite returned a sparse or accessor-bearing row set");
  }
  return descriptor.value;
};

const normalizeOptions = (options) => {
  if (options === undefined) return OBJECT_FREEZE({ busyTimeoutMs: DEFAULT_BUSY_TIMEOUT_MS });
  if (
    options === null ||
    typeof options !== "object" ||
    ARRAY_IS_ARRAY(options) ||
    IS_PROXY(options) ||
    OBJECT_GET_PROTOTYPE_OF(options) !== PLAIN_OBJECT_PROTOTYPE
  ) {
    fail("INVALID_INPUT", "options must be a plain object");
  }
  const keys = REFLECT_OWN_KEYS(options);
  let busyTimeoutMs = DEFAULT_BUSY_TIMEOUT_MS;
  for (let index = 0; index < keys.length; index += 1) {
    const key = keys[index];
    if (key !== "busyTimeoutMs") {
      fail("INVALID_INPUT", "options contains an unsupported field");
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(options, key);
    if (!descriptor.enumerable || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail("INVALID_INPUT", "options must contain only plain data properties");
    }
    busyTimeoutMs = descriptor.value;
  }
  if (
    !NUMBER_IS_SAFE_INTEGER(busyTimeoutMs) ||
    busyTimeoutMs < 0 ||
    busyTimeoutMs > MAX_BUSY_TIMEOUT_MS
  ) {
    fail("INVALID_INPUT", `busyTimeoutMs must be between 0 and ${MAX_BUSY_TIMEOUT_MS}`);
  }
  return OBJECT_FREEZE({ busyTimeoutMs });
};

const normalizeDatabasePath = (databasePath) => {
  const candidate = requireNonEmptyString(databasePath, "databasePath");
  if (candidate === ":memory:" || STRING_STARTS_WITH(candidate, "file:")) {
    fail("FILE_DATABASE_REQUIRED", "D01 requires a filesystem-backed SQLite database");
  }
  return path.resolve(candidate);
};

export class SQLiteStateStore {
  #database;
  #databasePath;
  #mode;
  #journalMode;
  #safeModeReason;
  #closed;
  #transactionActive;

  constructor(token, fields) {
    if (token !== CONSTRUCTOR_TOKEN) {
      fail("DIRECT_CONSTRUCTION_DENIED", "use SQLiteStateStore.open()");
    }
    this.#database = fields.database;
    this.#databasePath = fields.databasePath;
    this.#mode = fields.mode;
    this.#journalMode = fields.journalMode;
    this.#safeModeReason = fields.safeModeReason;
    this.#closed = fields.closed ?? false;
    this.#transactionActive = false;
  }

  static open(databasePath, options = undefined) {
    const resolvedPath = normalizeDatabasePath(databasePath);
    const normalizedOptions = normalizeOptions(options);
    let database;

    try {
      database = new DatabaseSync(resolvedPath);
      database.exec(`PRAGMA busy_timeout = ${normalizedOptions.busyTimeoutMs}`);
      database.exec("PRAGMA foreign_keys = ON");

      const journalRow = configureWalJournal(database, normalizedOptions.busyTimeoutMs);
      const journalMode =
        typeof journalRow?.journal_mode === "string"
          ? STRING_TO_LOWER_CASE(journalRow.journal_mode)
          : "";
      if (journalMode !== "wal") {
        return SQLiteStateStore.#safe(database, resolvedPath, "SQLITE_WAL_REQUIRED", journalMode);
      }

      SQLiteStateStore.#initializeEmptyDatabase(database);

      const schema = SQLiteStateStore.#validateSchema(database);
      if (!schema.ok) {
        return SQLiteStateStore.#safe(database, resolvedPath, schema.code, schema.details);
      }

      const schemaVersion = SQLiteStateStore.#validateSchemaVersion(database);
      if (!schemaVersion.ok) {
        return SQLiteStateStore.#safe(
          database,
          resolvedPath,
          schemaVersion.code,
          schemaVersion.details,
        );
      }

      const persistedJson = SQLiteStateStore.#validatePersistedJson(database);
      if (!persistedJson.ok) {
        return SQLiteStateStore.#safe(
          database,
          resolvedPath,
          persistedJson.code,
          persistedJson.details,
        );
      }

      const integrity = SQLiteStateStore.#runIntegrityCheck(database);
      if (!integrity.ok) {
        return SQLiteStateStore.#safe(
          database,
          resolvedPath,
          "SQLITE_INTEGRITY_FAILED",
          integrity.details,
        );
      }

      return new SQLiteStateStore(CONSTRUCTOR_TOKEN, {
        database,
        databasePath: resolvedPath,
        mode: SQLITE_STORE_MODE.ACTIVE,
        journalMode,
        safeModeReason: null,
      });
    } catch (error) {
      if (
        error instanceof SQLiteStateStoreError &&
        error.code === "SQLITE_SCHEMA_INITIALIZATION_OUTCOME_UNCERTAIN"
      ) {
        return SQLiteStateStore.#safe(database ?? null, resolvedPath, error.code, error.details);
      }
      if (isIntegrityError(error)) {
        return SQLiteStateStore.#safe(
          database ?? null,
          resolvedPath,
          "SQLITE_INTEGRITY_FAILED",
          OBJECT_FREEZE(["sqlite reported corrupt or non-database content"]),
        );
      }
      try {
        database?.close();
      } catch {
        // The original open/configuration failure remains authoritative.
      }
      throw new SQLiteStateStoreError(
        "SQLITE_OPEN_FAILED",
        "SQLite state store could not be opened or initialized",
        { cause: error instanceof Error ? error.name : "unknown" },
      );
    }
  }

  static #safe(database, databasePath, code, details) {
    try {
      database?.close();
    } catch {
      // SAFE_MODE does not depend on retaining a readable database handle.
    }
    return new SQLiteStateStore(CONSTRUCTOR_TOKEN, {
      database: null,
      databasePath,
      mode: SQLITE_STORE_MODE.SAFE_MODE,
      journalMode: null,
      safeModeReason: OBJECT_FREEZE({ code, details }),
      closed: true,
    });
  }

  static #initializeEmptyDatabase(database) {
    const applicationObjects = SQLiteStateStore.#listApplicationObjects(database);
    if (applicationObjects.length !== 0) return;

    database.exec("BEGIN IMMEDIATE");
    try {
      if (SQLiteStateStore.#listApplicationObjects(database).length === 0) {
        database.exec(`${CANONICAL_TABLE_SQL.ef_store_metadata};`);
        database.exec(`${CANONICAL_TABLE_SQL.revisioned_records};`);
        database
          .prepare("INSERT INTO ef_store_metadata (key, value) VALUES ('schema_version', ?)")
          .run(SCHEMA_VERSION_TEXT);
      }
      database.exec("COMMIT");
    } catch (error) {
      try {
        database.exec("ROLLBACK");
      } catch (rollbackError) {
        throw new SQLiteStateStoreError(
          "SQLITE_SCHEMA_INITIALIZATION_OUTCOME_UNCERTAIN",
          "schema initialization failed and rollback could not be confirmed",
          {
            cause: error instanceof Error ? error.name : "unknown",
            rollbackCause: rollbackError instanceof Error ? rollbackError.name : "unknown",
          },
        );
      }
      throw error;
    }
  }

  static #listApplicationObjects(database) {
    return database
      .prepare(
        `SELECT type, name
           FROM sqlite_schema
          WHERE name NOT LIKE 'sqlite_%'
          ORDER BY type, name`,
      )
      .all();
  }

  static #validateSchema(database) {
    const objects = database
      .prepare(
        `SELECT type, name, tbl_name AS tableName, sql
           FROM sqlite_schema
          WHERE name NOT LIKE 'sqlite_%'
          ORDER BY type, name`,
      )
      .all();
    const actualRows = [];
    const objectShape = new ARRAY_CONSTRUCTOR(objects.length);
    for (let index = 0; index < objects.length; index += 1) {
      const object = readOwnArrayElement(objects, index);
      if (object.type === "table") {
        actualRows[actualRows.length] = { name: object.name, sql: object.sql };
      }
      objectShape[index] = {
        type: object.type,
        name: object.name,
        tableName: object.tableName,
      };
    }
    const actualFingerprint = fingerprintSchema(actualRows);
    const expectedObjectShape = new ARRAY_CONSTRUCTOR(CANONICAL_TABLE_NAMES.length);
    for (let index = 0; index < CANONICAL_TABLE_NAMES.length; index += 1) {
      const name = readOwnArrayElement(CANONICAL_TABLE_NAMES, index);
      expectedObjectShape[index] = { type: "table", name, tableName: name };
    }

    if (
      !sameJsonShape(objectShape, expectedObjectShape) ||
      actualFingerprint !== CANONICAL_SCHEMA_FINGERPRINT
    ) {
      return OBJECT_FREEZE({
        ok: false,
        code: "SQLITE_SCHEMA_FINGERPRINT_MISMATCH",
        details: OBJECT_FREEZE({
          expectedFingerprint: CANONICAL_SCHEMA_FINGERPRINT,
          actualFingerprint,
          expectedObjects: OBJECT_FREEZE(expectedObjectShape),
          actualObjects: OBJECT_FREEZE(objectShape),
        }),
      });
    }

    const rawTableList = database
      .prepare(
        `SELECT name, type, ncol, wr, strict
           FROM pragma_table_list
          WHERE schema = 'main' AND name IN ('ef_store_metadata', 'revisioned_records')
          ORDER BY name`,
      )
      .all();
    const tableList = new ARRAY_CONSTRUCTOR(rawTableList.length);
    for (let index = 0; index < rawTableList.length; index += 1) {
      const row = readOwnArrayElement(rawTableList, index);
      tableList[index] = {
        name: row.name,
        type: row.type,
        ncol: TO_NUMBER(row.ncol),
        wr: TO_NUMBER(row.wr),
        strict: TO_NUMBER(row.strict),
      };
    }
    const expectedTableList = new ARRAY_CONSTRUCTOR(CANONICAL_TABLE_NAMES.length);
    for (let index = 0; index < CANONICAL_TABLE_NAMES.length; index += 1) {
      const name = readOwnArrayElement(CANONICAL_TABLE_NAMES, index);
      expectedTableList[index] = {
        name,
        type: "table",
        ncol: CANONICAL_COLUMNS[name].length,
        wr: 0,
        strict: 1,
      };
    }
    if (!sameJsonShape(tableList, expectedTableList)) {
      return OBJECT_FREEZE({
        ok: false,
        code: "SQLITE_SCHEMA_STRUCTURE_MISMATCH",
        details: OBJECT_FREEZE({ component: "table_list" }),
      });
    }

    for (let tableIndex = 0; tableIndex < CANONICAL_TABLE_NAMES.length; tableIndex += 1) {
      const tableName = readOwnArrayElement(CANONICAL_TABLE_NAMES, tableIndex);
      const rawColumns = database
        .prepare(
          `SELECT cid, name, type, "notnull" AS isNotNull, dflt_value AS dfltValue, pk, hidden
             FROM pragma_table_xinfo(?)
            ORDER BY cid`,
        )
        .all(tableName);
      const columns = new ARRAY_CONSTRUCTOR(rawColumns.length);
      for (let index = 0; index < rawColumns.length; index += 1) {
        const row = readOwnArrayElement(rawColumns, index);
        columns[index] = {
          cid: TO_NUMBER(row.cid),
          name: row.name,
          type: row.type,
          notnull: TO_NUMBER(row.isNotNull),
          dfltValue: row.dfltValue,
          pk: TO_NUMBER(row.pk),
          hidden: TO_NUMBER(row.hidden),
        };
      }
      if (!sameJsonShape(columns, CANONICAL_COLUMNS[tableName])) {
        return OBJECT_FREEZE({
          ok: false,
          code: "SQLITE_SCHEMA_STRUCTURE_MISMATCH",
          details: OBJECT_FREEZE({ component: "columns", tableName }),
        });
      }

      const indexes = database
        .prepare(
          `SELECT name, "unique" AS isUnique, origin, partial
             FROM pragma_index_list(?)
            ORDER BY name`,
        )
        .all(tableName);
      if (
        indexes.length !== 1 ||
        TO_NUMBER(readOwnArrayElement(indexes, 0).isUnique) !== 1 ||
        readOwnArrayElement(indexes, 0).origin !== "pk" ||
        TO_NUMBER(readOwnArrayElement(indexes, 0).partial) !== 0
      ) {
        return OBJECT_FREEZE({
          ok: false,
          code: "SQLITE_SCHEMA_STRUCTURE_MISMATCH",
          details: OBJECT_FREEZE({ component: "primary_key_index", tableName }),
        });
      }
      const index = readOwnArrayElement(indexes, 0);
      const primaryKeyRows = database
        .prepare("SELECT name FROM pragma_index_info(?) ORDER BY seqno")
        .all(index.name);
      const primaryKeyColumns = new ARRAY_CONSTRUCTOR(primaryKeyRows.length);
      for (let columnIndex = 0; columnIndex < primaryKeyRows.length; columnIndex += 1) {
        primaryKeyColumns[columnIndex] = readOwnArrayElement(primaryKeyRows, columnIndex).name;
      }
      if (!sameJsonShape(primaryKeyColumns, CANONICAL_PRIMARY_KEYS[tableName])) {
        return OBJECT_FREEZE({
          ok: false,
          code: "SQLITE_SCHEMA_STRUCTURE_MISMATCH",
          details: OBJECT_FREEZE({ component: "primary_key_columns", tableName }),
        });
      }
    }

    return OBJECT_FREEZE({ ok: true });
  }

  static #validateSchemaVersion(database) {
    const row = database
      .prepare("SELECT value FROM ef_store_metadata WHERE key = 'schema_version'")
      .get();
    const actual = row === undefined ? null : row.value;
    const details = OBJECT_FREEZE({ expected: SCHEMA_VERSION_TEXT, actual });
    if (actual !== SCHEMA_VERSION_TEXT) {
      return OBJECT_FREEZE({
        ok: false,
        code: "SQLITE_SCHEMA_VERSION_MISMATCH",
        details,
      });
    }
    return OBJECT_FREEZE({ ok: true, details });
  }

  static #validateTransactionState(database) {
    const schema = SQLiteStateStore.#validateSchema(database);
    if (!schema.ok) return schema;
    const schemaVersion = SQLiteStateStore.#validateSchemaVersion(database);
    if (!schemaVersion.ok) return schemaVersion;
    return SQLiteStateStore.#validatePersistedJson(database);
  }

  static #isPersistentStateValidationError(error) {
    return (
      error instanceof SQLiteStateStoreError &&
      (error.code === "SQLITE_SCHEMA_FINGERPRINT_MISMATCH" ||
        error.code === "SQLITE_SCHEMA_STRUCTURE_MISMATCH" ||
        error.code === "SQLITE_SCHEMA_VERSION_MISMATCH" ||
        error.code === "SQLITE_PERSISTED_REVISION_INVALID" ||
        error.code === "SQLITE_PERSISTED_JSON_INVALID")
    );
  }

  static #validatePersistedJson(database) {
    const invalidRevisionRow = database
      .prepare(
        `SELECT record_type AS recordType,
                record_id AS recordId,
                CAST(revision AS TEXT) AS revisionText,
                typeof(revision) AS revisionType
           FROM revisioned_records
          WHERE typeof(revision) <> 'integer'
             OR revision < 0
             OR revision > ?
          ORDER BY record_type, record_id
          LIMIT 1`,
      )
      .get(MAX_REVISION);
    if (invalidRevisionRow !== undefined) {
      return OBJECT_FREEZE({
        ok: false,
        code: "SQLITE_PERSISTED_REVISION_INVALID",
        details: OBJECT_FREEZE({
          recordType: invalidRevisionRow.recordType,
          recordId: invalidRevisionRow.recordId,
          revision: invalidRevisionRow.revisionText,
          revisionType: invalidRevisionRow.revisionType,
        }),
      });
    }

    const invalidRow = database
      .prepare(
        `SELECT record_type AS recordType,
                record_id AS recordId,
                revision
           FROM revisioned_records
          WHERE json_valid(value_json) <> 1
          ORDER BY record_type, record_id
          LIMIT 1`,
      )
      .get();
    if (invalidRow !== undefined) {
      return OBJECT_FREEZE({
        ok: false,
        code: "SQLITE_PERSISTED_JSON_INVALID",
        details: OBJECT_FREEZE({
          recordType: invalidRow.recordType,
          recordId: invalidRow.recordId,
          revision: TO_NUMBER(invalidRow.revision),
        }),
      });
    }

    const rows = database
      .prepare(
        `SELECT record_type AS recordType,
                record_id AS recordId,
                CAST(revision AS TEXT) AS revisionText,
                typeof(revision) AS revisionType,
                value_json AS valueJson
           FROM revisioned_records
          ORDER BY record_type, record_id`,
      )
      .all();
    for (let index = 0; index < rows.length; index += 1) {
      const row = readOwnArrayElement(rows, index);
      try {
        decodeCanonicalJson(row.valueJson, "persisted value");
      } catch {
        return OBJECT_FREEZE({
          ok: false,
          code: "SQLITE_PERSISTED_JSON_INVALID",
          details: OBJECT_FREEZE({
            recordType: row.recordType,
            recordId: row.recordId,
            revision: TO_NUMBER(row.revisionText),
          }),
        });
      }
    }
    return OBJECT_FREEZE({ ok: true, details: OBJECT_FREEZE([]) });
  }

  static #runIntegrityCheck(database) {
    const rows = database.prepare("PRAGMA integrity_check").all();
    const details = new ARRAY_CONSTRUCTOR(rows.length);
    for (let index = 0; index < rows.length; index += 1) {
      const result = readOwnArrayElement(rows, index).integrity_check;
      details[index] = typeof result === "string" ? result : "unknown integrity result";
    }
    return OBJECT_FREEZE({
      ok:
        details.length === 1 &&
        STRING_TO_LOWER_CASE(readOwnArrayElement(details, 0)) === "ok",
      details: OBJECT_FREEZE(details),
    });
  }

  get databasePath() {
    return this.#databasePath;
  }

  get mode() {
    return this.#mode;
  }

  get journalMode() {
    return this.#journalMode;
  }

  get schemaVersion() {
    return SCHEMA_VERSION;
  }

  get safeModeReason() {
    return this.#safeModeReason;
  }

  get isClosed() {
    return this.#closed;
  }

  health() {
    return OBJECT_FREEZE({
      mode: this.#mode,
      journalMode: this.#journalMode,
      schemaVersion: SCHEMA_VERSION,
      safeModeReason: this.#safeModeReason,
      closed: this.#closed,
    });
  }

  transaction(callback) {
    this.#assertMutable();
    if (typeof callback !== "function") {
      fail("INVALID_INPUT", "transaction callback must be a function");
    }
    if (this.#transactionActive) {
      fail("NESTED_TRANSACTION_DENIED", "nested transactions are not supported");
    }

    let transactionStarted = false;
    try {
      this.#database.exec("BEGIN IMMEDIATE");
      transactionStarted = true;
      const transactionState = SQLiteStateStore.#validateTransactionState(this.#database);
      if (!transactionState.ok) {
        throw new SQLiteStateStoreError(
          transactionState.code,
          "SQLite state store changed before the transaction write lock was acquired",
          transactionState.details,
        );
      }
      this.#transactionActive = true;
      const result = callback(this);
      if (isThenable(result)) {
        observeNativePromiseRejectionWithoutUserCode(result);
        fail("ASYNC_TRANSACTION_DENIED", "transaction callbacks must be synchronous");
      }
      this.#database.exec("COMMIT");
      transactionStarted = false;
      return result;
    } catch (error) {
      if (transactionStarted) {
        try {
          this.#database.exec("ROLLBACK");
          transactionStarted = false;
        } catch (rollbackError) {
          const details = OBJECT_FREEZE({
            cause: error instanceof Error ? error.name : "unknown",
            rollbackCause: rollbackError instanceof Error ? rollbackError.name : "unknown",
          });
          this.#enterSafeMode("SQLITE_TRANSACTION_OUTCOME_UNCERTAIN", details);
          throw new SQLiteStateStoreError(
            "SQLITE_TRANSACTION_OUTCOME_UNCERTAIN",
            "transaction failed and rollback could not be confirmed",
            details,
          );
        }
      }
      if (
        error instanceof SQLiteStateStoreError &&
        error.code === "ASYNC_TRANSACTION_DENIED"
      ) {
        this.#enterSafeMode(
          "ASYNC_TRANSACTION_DENIED",
          OBJECT_FREEZE({ rollback: "confirmed", escapedContinuationDenied: true }),
        );
      }
      if (SQLiteStateStore.#isPersistentStateValidationError(error)) {
        this.#enterSafeMode(error.code, error.details);
      }
      if (isIntegrityError(error)) {
        const details = this.#sqliteFailureDetails(error);
        this.#enterSafeMode("SQLITE_INTEGRITY_FAILED", details);
        throw new SQLiteStateStoreError(
          "SQLITE_INTEGRITY_FAILED",
          "SQLite integrity failure occurred during a transaction",
          details,
        );
      }
      throw error;
    } finally {
      this.#transactionActive = false;
    }
  }

  createRevisionedRecord({ recordType, recordId, value }) {
    this.#assertMutable();
    const type = requireNonEmptyString(recordType, "recordType");
    const id = requireNonEmptyString(recordId, "recordId");
    const valueJson = encodeJson(value);

    return this.#mutateAtomically(() => {
      try {
        this.#database
          .prepare(
            `INSERT INTO revisioned_records
              (record_type, record_id, revision, value_json)
             VALUES (?, ?, 0, ?)`,
          )
          .run(type, id, valueJson);
      } catch (error) {
        if (
          error instanceof Error &&
          STRING_INCLUDES(STRING_TO_LOWER_CASE(error.message), "unique")
        ) {
          fail("RECORD_ALREADY_EXISTS", "revisioned record already exists", {
            recordType: type,
            recordId: id,
          });
        }
        throw error;
      }
      return this.#read(type, id);
    });
  }

  readRevisionedRecord(recordType, recordId) {
    this.#assertReadable();
    const type = requireNonEmptyString(recordType, "recordType");
    const id = requireNonEmptyString(recordId, "recordId");
    return this.#read(type, id);
  }

  compareAndSwapRevision({ recordType, recordId, expectedRevision, value }) {
    this.#assertMutable();
    const type = requireNonEmptyString(recordType, "recordType");
    const id = requireNonEmptyString(recordId, "recordId");
    const expected = requireRevision(expectedRevision, "expectedRevision");
    const valueJson = encodeJson(value);

    return this.#mutateAtomically(() => {
      const result = this.#database
        .prepare(
          `UPDATE revisioned_records
             SET revision = revision + 1, value_json = ?
           WHERE record_type = ? AND record_id = ? AND revision = ? AND revision < ?`,
        )
        .run(valueJson, type, id, expected, MAX_REVISION);

      const record = this.#read(type, id);
      if (TO_NUMBER(result.changes) === 1) {
        return OBJECT_FREEZE({
          ok: true,
          status: "UPDATED",
          previousRevision: expected,
          currentRevision: record.revision,
          record,
        });
      }
      if (record === null) {
        return OBJECT_FREEZE({
          ok: false,
          status: "RECORD_NOT_FOUND",
          code: "RECORD_NOT_FOUND",
          expectedRevision: expected,
          currentRevision: null,
          record: null,
        });
      }
      if (record.revision === expected && expected === MAX_REVISION) {
        fail("REVISION_EXHAUSTED", "revision cannot be incremented beyond the safe integer limit", {
          recordType: type,
          recordId: id,
          revision: expected,
        });
      }
      return OBJECT_FREEZE({
        ok: false,
        status: "STALE_REVISION",
        code: "STALE_REVISION",
        expectedRevision: expected,
        currentRevision: record.revision,
        record,
      });
    });
  }

  checkIntegrity() {
    this.#assertAvailable();
    let result;
    try {
      result = SQLiteStateStore.#validateSchema(this.#database);
      if (result.ok) {
        result = SQLiteStateStore.#validateSchemaVersion(this.#database);
        if (result.ok) {
          const persistedJson = SQLiteStateStore.#validatePersistedJson(this.#database);
          result = persistedJson.ok
            ? SQLiteStateStore.#runIntegrityCheck(this.#database)
            : OBJECT_FREEZE({
                ok: false,
                code: persistedJson.code,
                details: persistedJson.details,
              });
        }
      }
    } catch (error) {
      if (!isIntegrityError(error)) throw error;
      result = OBJECT_FREEZE({
        ok: false,
        code: "SQLITE_INTEGRITY_FAILED",
        details: OBJECT_FREEZE(["sqlite reported corrupt or non-database content"]),
      });
    }
    if (!result.ok) {
      this.#enterSafeMode(result.code ?? "SQLITE_INTEGRITY_FAILED", result.details);
    }
    return OBJECT_FREEZE({
      ok: result.ok,
      mode: this.#mode,
      details: result.details,
    });
  }

  close() {
    if (this.#closed) return;
    try {
      this.#database?.close();
    } finally {
      this.#database = null;
      this.#closed = true;
      this.#transactionActive = false;
    }
  }

  #read(recordType, recordId) {
    let row;
    try {
      row = this.#database
        .prepare(
          `SELECT record_type AS recordType,
                  record_id AS recordId,
                  CAST(revision AS TEXT) AS revisionText,
                  typeof(revision) AS revisionType,
                  value_json AS valueJson
             FROM revisioned_records
            WHERE record_type = ? AND record_id = ?`,
        )
        .get(recordType, recordId);
    } catch (error) {
      if (!isIntegrityError(error)) throw error;
      const details = this.#sqliteFailureDetails(error);
      this.#enterSafeMode("SQLITE_INTEGRITY_FAILED", details);
      throw new SQLiteStateStoreError(
        "SQLITE_INTEGRITY_FAILED",
        "SQLite integrity failure occurred while reading a record",
        details,
      );
    }
    if (row === undefined) return null;
    const revision = TO_NUMBER(row.revisionText);
    if (
      row.revisionType !== "integer" ||
      !NUMBER_IS_SAFE_INTEGER(revision) ||
      revision < 0 ||
      revision > MAX_REVISION
    ) {
      const details = OBJECT_FREEZE({
        recordType: row.recordType,
        recordId: row.recordId,
        revision: row.revisionText,
        revisionType: row.revisionType,
      });
      this.#enterSafeMode("SQLITE_PERSISTED_REVISION_INVALID", details);
      throw new SQLiteStateStoreError(
        "SQLITE_PERSISTED_REVISION_INVALID",
        "persisted record revision is outside the canonical safe integer range",
        details,
      );
    }
    let value;
    try {
      value = decodeCanonicalJson(row.valueJson, "persisted value");
    } catch (error) {
      const details = OBJECT_FREEZE({
        recordType: row.recordType,
        recordId: row.recordId,
        revision,
      });
      this.#enterSafeMode("SQLITE_PERSISTED_JSON_INVALID", details);
      throw new SQLiteStateStoreError(
        "SQLITE_PERSISTED_JSON_INVALID",
        "persisted record value is not valid JSON",
        {
          ...details,
          cause: error instanceof Error ? error.name : "unknown",
        },
      );
    }
    return OBJECT_FREEZE({
      recordType: row.recordType,
      recordId: row.recordId,
      revision,
      value,
    });
  }

  #mutateAtomically(operation) {
    if (this.#transactionActive) return operation();
    return this.transaction(operation);
  }

  #sqliteFailureDetails(error) {
    return OBJECT_FREEZE({
      cause: error instanceof Error ? error.name : "unknown",
      sqliteErrcode:
        error instanceof Error && NUMBER_IS_SAFE_INTEGER(error.errcode) ? error.errcode : null,
      sqliteErrorName:
        error instanceof Error && typeof error.errstr === "string" ? error.errstr : null,
    });
  }

  #enterSafeMode(code, details) {
    this.#mode = SQLITE_STORE_MODE.SAFE_MODE;
    this.#journalMode = null;
    this.#safeModeReason = OBJECT_FREEZE({ code, details });
    try {
      this.#database?.close();
    } catch {
      // Dropping the handle reference remains fail-closed even if SQLite cannot confirm close.
    } finally {
      this.#database = null;
      this.#closed = true;
      this.#transactionActive = false;
    }
  }

  #assertAvailable() {
    if (this.#mode === SQLITE_STORE_MODE.SAFE_MODE) {
      fail("STORE_SAFE_MODE", "SQLite state store is in SAFE_MODE", {
        reason: this.#safeModeReason?.code ?? "unknown",
      });
    }
    if (this.#closed || this.#database === null) {
      fail("STORE_CLOSED", "SQLite state store is closed");
    }
  }

  #assertReadable() {
    this.#assertAvailable();
    let schema;
    let schemaVersion;
    try {
      schema = SQLiteStateStore.#validateSchema(this.#database);
      if (schema.ok) {
        schemaVersion = SQLiteStateStore.#validateSchemaVersion(this.#database);
      }
    } catch (error) {
      if (!isIntegrityError(error)) throw error;
      const details = OBJECT_FREEZE(["sqlite reported corrupt or non-database content"]);
      this.#enterSafeMode("SQLITE_INTEGRITY_FAILED", details);
      throw new SQLiteStateStoreError(
        "SQLITE_INTEGRITY_FAILED",
        "SQLite integrity failure was detected while reading",
        { details },
      );
    }
    if (!schema.ok) {
      this.#enterSafeMode(schema.code, schema.details);
      throw new SQLiteStateStoreError(
        schema.code,
        "SQLite state store schema no longer matches the canonical fingerprint",
        schema.details,
      );
    }
    if (!schemaVersion.ok) {
      this.#enterSafeMode(schemaVersion.code, schemaVersion.details);
      throw new SQLiteStateStoreError(
        schemaVersion.code,
        "SQLite state store schema version no longer matches the canonical version",
        schemaVersion.details,
      );
    }
  }

  #assertMutable() {
    this.#assertReadable();
    let persistedJson;
    try {
      persistedJson = SQLiteStateStore.#validatePersistedJson(this.#database);
    } catch (error) {
      if (!isIntegrityError(error)) throw error;
      const details = OBJECT_FREEZE(["sqlite reported corrupt or non-database content"]);
      this.#enterSafeMode("SQLITE_INTEGRITY_FAILED", details);
      throw new SQLiteStateStoreError(
        "SQLITE_INTEGRITY_FAILED",
        "SQLite integrity failure was detected before mutation",
        { details },
      );
    }
    if (!persistedJson.ok) {
      this.#enterSafeMode(persistedJson.code, persistedJson.details);
      throw new SQLiteStateStoreError(
        persistedJson.code,
        persistedJson.code === "SQLITE_PERSISTED_REVISION_INVALID"
          ? "persisted record revision is outside the canonical safe integer range"
          : "persisted record value is not valid JSON",
        persistedJson.details,
      );
    }
  }
}

const CONSTRUCTOR_TOKEN = Symbol("SQLiteStateStore");

export const openSQLiteStateStore = (databasePath, options = undefined) =>
  SQLiteStateStore.open(databasePath, options);
