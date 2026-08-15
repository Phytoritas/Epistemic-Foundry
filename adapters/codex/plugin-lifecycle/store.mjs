import { randomUUID } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import fs from "node:fs";
import path from "node:path";
import {
  FAILURE,
  LIMITS,
  STATUS,
  boundedJson,
  canonicalJson,
  compareUtf8,
  exactFields,
  fail,
  hashJson,
  sha256,
} from "./core.mjs";

const COMPILED_STATE_SCHEMA_SHA256 = "sha256:cd35de2ed07b46758a8a0256497d77c11faef786f06e0b4ba43b60af1dd0415c";
const COMPILED_LOCK_SCHEMA_SHA256 = "sha256:62f5434777ec45d587f9662eb5a3315004740335ca53732913b0030162efc37a";
const OWNED_DIRECTORIES = Object.freeze(["marketplaces", "packages", "recovery", "snapshots", "staging"]);
const SQLITE_FILES = new Set([
  "lifecycle.sqlite3",
  "lifecycle.sqlite3-shm",
  "lifecycle.sqlite3-wal",
  "lifecycle.sqlite3-journal",
  "ownership.sqlite3",
  "ownership.sqlite3-shm",
  "ownership.sqlite3-wal",
  "ownership.sqlite3-journal",
]);

function pathKey(value) {
  const resolved = path.resolve(value).normalize("NFC");
  return process.platform === "win32" || process.platform === "darwin"
    ? resolved.toLowerCase()
    : resolved;
}

function rejectNetworkPath(value, label) {
  if (process.platform === "win32" && (/^(?:\\\\|\/\/)/u.test(value) || path.parse(value).root.startsWith("\\\\"))) {
    fail(FAILURE.UNSAFE_PATH, `${label} cannot be a UNC or network path`);
  }
}

function projectionHash(value) {
  return hashJson("PLUGIN_LIFECYCLE_V3_PROJECTION", {
    version: value.version,
    status: value.status,
    active_selector: value.active_selector,
    active_package_hash: value.active_package_hash,
    previous_selector: value.previous_selector,
    previous_package_hash: value.previous_package_hash,
    failure_code: value.failure_code,
  });
}

function asJson(value, label) {
  return canonicalJson(boundedJson(value, label));
}

function rowBoolean(value) {
  return value === 1 || value === true;
}

function pragmaValue(row) {
  return row === undefined ? undefined : Object.values(row)[0];
}

function isBusy(cause) {
  const code = String(cause?.code ?? "");
  const message = String(cause?.message ?? "");
  return code.includes("SQLITE_BUSY") || code.includes("SQLITE_LOCKED") || /database is (?:locked|busy)/iu.test(message);
}

function openDatabase(databasePath, timeout) {
  const db = new DatabaseSync(databasePath, {
    timeout,
    defensive: true,
    allowExtension: false,
    allowBareNamedParameters: false,
    allowUnknownNamedParameters: false,
  });
  try {
    db.exec("PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON; PRAGMA trusted_schema=OFF;");
    const journalMode = String(pragmaValue(db.prepare("PRAGMA journal_mode").get()) ?? "").toLowerCase();
    const synchronous = Number(pragmaValue(db.prepare("PRAGMA synchronous").get()));
    if (journalMode !== "wal" || synchronous !== 2) {
      fail(FAILURE.HOST_UNSUPPORTED, "SQLite WAL/FULL durability is unavailable", STATUS.UNSUPPORTED);
    }
    return db;
  } catch (cause) {
    try { db.close(); } catch { /* preserve the opening failure */ }
    throw cause;
  }
}

export function createSagaStore({ lifecycleRoot, contractPath }) {
  let contract;
  try {
    contract = JSON.parse(fs.readFileSync(contractPath, "utf8"));
  } catch {
    fail(FAILURE.STATE_CORRUPT, "private lifecycle contract is unreadable");
  }
  exactFields(
    contract,
    [
      "contract_id",
      "contract_version",
      "canonical",
      "authority",
      "not_a_shared_schema",
      "persistence",
      "status_values",
      "failure_values",
      "required_ports",
    ],
    "private lifecycle contract",
  );
  exactFields(
    contract.persistence,
    [
      "engine",
      "database_file",
      "lock_database_file",
      "journal_mode",
      "synchronous",
      "writer_serialization",
      "diagnostics",
      "composition_binding",
      "schema_sha256",
      "lock_schema_sha256",
      "lock_schema_sql",
      "schema_sql",
    ],
    "private lifecycle persistence contract",
  );
  if (
    contract.contract_id !== "PLUGIN_LIFECYCLE_V3_FENCED_SQLITE_SAGA" ||
    contract.contract_version !== 3 ||
    contract.canonical !== false ||
    contract.not_a_shared_schema !== true ||
    contract.persistence.engine !== "node:sqlite" ||
    contract.persistence.database_file !== "lifecycle.sqlite3" ||
    contract.persistence.lock_database_file !== "ownership.sqlite3" ||
    contract.persistence.journal_mode !== "WAL" ||
    contract.persistence.synchronous !== "FULL"
  ) fail(FAILURE.STATE_CORRUPT, "private lifecycle contract is incompatible");
  if (contract.persistence.composition_binding !== "immutable canonical runtime composition JSON plus domain-separated sha256") {
    fail(FAILURE.STATE_CORRUPT, "private lifecycle composition binding contract is incompatible");
  }
  if (
    contract.persistence.schema_sha256 !== COMPILED_STATE_SCHEMA_SHA256 ||
    contract.persistence.lock_schema_sha256 !== COMPILED_LOCK_SCHEMA_SHA256 ||
    sha256(Buffer.from(contract.persistence.schema_sql, "utf8")) !== COMPILED_STATE_SCHEMA_SHA256 ||
    sha256(Buffer.from(contract.persistence.lock_schema_sql, "utf8")) !== COMPILED_LOCK_SCHEMA_SHA256
  ) fail(FAILURE.STATE_CORRUPT, "compiled lifecycle schema digest differs");
  if (
    canonicalJson([...Object.values(STATUS)].sort(compareUtf8)) !==
      canonicalJson([...contract.status_values].sort(compareUtf8)) ||
    canonicalJson([...Object.values(FAILURE)].sort(compareUtf8)) !==
      canonicalJson([...contract.failure_values].sort(compareUtf8))
  ) fail(FAILURE.STATE_CORRUPT, "runtime enums drifted from the private contract");
  const requiredPorts = {
    command_when_injected: ["capability_id"],
    private_root: ["capability_id", "qualify", "revalidate"],
    data_snapshot: ["capability_id", "qualify", "capture", "compare", "restore", "reconcile", "dispose"],
    quiescence: ["capability_id", "acquire", "revalidate", "renew", "recover", "release", "reconcile"],
    verification: ["capability_id", "health", "replay", "integrity"],
    migration_when_requested: ["capability_id", "apply", "rollback", "reconcile", "verifyCompatible"],
    trust_when_package_changes: ["capability_id", "request"],
  };
  if (canonicalJson(contract.required_ports) !== canonicalJson(requiredPorts)) {
    fail(FAILURE.STATE_CORRUPT, "runtime capability hooks drifted from the private contract");
  }

  rejectNetworkPath(lifecycleRoot, "lifecycleRoot");
  if (!fs.existsSync(lifecycleRoot)) {
    fail(FAILURE.HOST_UNSUPPORTED, "protected lifecycleRoot must be provisioned before use", STATUS.UNSUPPORTED);
  }
  const rootStat = fs.lstatSync(lifecycleRoot, { bigint: true });
  if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) fail(FAILURE.UNSAFE_PATH, "lifecycleRoot is not ordinary");
  const realRoot = fs.realpathSync.native(lifecycleRoot);
  if (pathKey(realRoot) !== pathKey(lifecycleRoot)) fail(FAILURE.UNSAFE_PATH, "lifecycleRoot resolves through an alias");
  const roots = { root: realRoot };
  for (const name of OWNED_DIRECTORIES) roots[name] = path.join(realRoot, name);
  for (const entry of fs.readdirSync(realRoot, { withFileTypes: true })) {
    if (OWNED_DIRECTORIES.includes(entry.name)) {
      if (!entry.isDirectory()) fail(FAILURE.STATE_CORRUPT, "owned lifecycle entry is not a directory");
      continue;
    }
    if (!entry.isFile() || !SQLITE_FILES.has(entry.name)) fail(FAILURE.STATE_CORRUPT, "lifecycleRoot contains an unknown entry");
    const stat = fs.lstatSync(path.join(realRoot, entry.name), { bigint: true });
    if (stat.isSymbolicLink() || !stat.isFile() || stat.nlink !== 1n) {
      fail(FAILURE.STATE_CORRUPT, "lifecycle SQLite state is linked or non-ordinary");
    }
  }

  let lockDb;
  try {
    lockDb = openDatabase(path.join(realRoot, contract.persistence.lock_database_file), 1);
    lockDb.exec(contract.persistence.lock_schema_sql);
  } catch (cause) {
    if (lockDb !== undefined) {
      try { lockDb.close(); } catch { /* preserve the opening failure */ }
    }
    if (isBusy(cause)) fail(FAILURE.CONCURRENT_OPERATION, "another lifecycle process owns schema bootstrap", STATUS.BLOCKED);
    throw cause;
  }
  let db;
  try {
    lockDb.exec("BEGIN IMMEDIATE");
    db = openDatabase(path.join(realRoot, contract.persistence.database_file), 10_000);
    db.exec(contract.persistence.schema_sql);
    lockDb.exec("COMMIT");
  } catch (cause) {
    if (lockDb.isTransaction) {
      try { lockDb.exec("ROLLBACK"); } catch { /* connection close remains fail-safe */ }
    }
    if (db !== undefined) db.close();
    lockDb.close();
    if (isBusy(cause)) fail(FAILURE.CONCURRENT_OPERATION, "another lifecycle process owns schema bootstrap", STATUS.BLOCKED);
    throw cause;
  }
  for (const name of [contract.persistence.lock_database_file, contract.persistence.database_file]) {
    const databasePath = path.join(realRoot, name);
    const stat = fs.lstatSync(databasePath, { bigint: true });
    if (
      stat.isSymbolicLink() ||
      !stat.isFile() ||
      stat.nlink !== 1n ||
      pathKey(fs.realpathSync.native(databasePath)) !== pathKey(databasePath)
    ) fail(FAILURE.STATE_CORRUPT, "lifecycle SQLite database identity is not ordinary");
  }
  let activeEpoch = null;
  let closed = false;
  let databaseClosed = false;
  let lockClosed = false;

  const assertOwnership = () => {
    if (closed || databaseClosed || lockClosed) fail(FAILURE.INVALID_TRANSITION, "lifecycle store is closed");
    if (activeEpoch === null || !lockDb.isTransaction) {
      fail(FAILURE.CONCURRENT_OPERATION, "lifecycle ownership is not held", STATUS.BLOCKED);
    }
    const row = lockDb.prepare("SELECT owner_epoch FROM ownership WHERE singleton = 1").get();
    if (row === undefined || row.owner_epoch !== activeEpoch) {
      fail(FAILURE.CONCURRENT_OPERATION, "lifecycle ownership fence was lost", STATUS.BLOCKED);
    }
    return activeEpoch;
  };

  const withOwnership = (callable) => {
    if (closed || databaseClosed || lockClosed) fail(FAILURE.INVALID_TRANSITION, "lifecycle store is closed");
    if (activeEpoch !== null) fail(FAILURE.CONCURRENT_OPERATION, "lifecycle call is reentrant", STATUS.BLOCKED);
    try {
      lockDb.exec("BEGIN IMMEDIATE");
    } catch (cause) {
      if (isBusy(cause)) fail(FAILURE.CONCURRENT_OPERATION, "another lifecycle process owns the saga", STATUS.BLOCKED);
      throw cause;
    }
    activeEpoch = `epoch_${randomUUID()}`;
    let result;
    let thrown = null;
    try {
      lockDb.prepare("UPDATE ownership SET owner_epoch = ?, acquired_at = ? WHERE singleton = 1").run(
        activeEpoch,
        new Date().toISOString(),
      );
      result = callable(activeEpoch);
      if (result?.then !== undefined) {
        fail(FAILURE.HOST_UNSUPPORTED, "lifecycle ownership callback must be synchronous", STATUS.UNSUPPORTED);
      }
    } catch (cause) {
      thrown = cause;
    }
    try {
      lockDb.exec("COMMIT");
    } catch (cause) {
      if (lockDb.isTransaction) {
        try { lockDb.exec("ROLLBACK"); } catch { /* connection close remains fail-safe */ }
      }
      if (thrown === null) thrown = cause;
    } finally {
      activeEpoch = null;
    }
    if (thrown !== null) throw thrown;
    return result;
  };

  const tx = (callable) => {
    assertOwnership();
    try {
      db.exec("BEGIN IMMEDIATE");
    } catch (cause) {
      if (isBusy(cause)) fail(FAILURE.CONCURRENT_OPERATION, "lifecycle state writer is busy", STATUS.BLOCKED);
      throw cause;
    }
    try {
      assertOwnership();
      const value = callable();
      assertOwnership();
      db.exec("COMMIT");
      return value;
    } catch (cause) {
      if (db.isTransaction) db.exec("ROLLBACK");
      throw cause;
    }
  };

  const initialize = ({ binding, bindingHash }) => {
    assertOwnership();
    const bindingJson = asJson(binding, "runtime composition binding");
    if (
      typeof bindingHash !== "string" ||
      bindingHash !== hashJson("PLUGIN_LIFECYCLE_V3_COMPOSITION_BINDING", JSON.parse(bindingJson))
    ) fail(FAILURE.STATE_CORRUPT, "runtime composition binding seal is invalid");
    tx(() => {
      const existingVersion = db.prepare("SELECT value FROM meta WHERE key = ?").get("contract_version");
      if (existingVersion === undefined) {
        db.prepare("INSERT INTO meta(key, value) VALUES(?, ?)").run("contract_version", "3");
        db.prepare("INSERT INTO meta(key, value) VALUES(?, ?)").run("schema_sha256", COMPILED_STATE_SCHEMA_SHA256);
        db.prepare("INSERT INTO meta(key, value) VALUES(?, ?)").run("operation_count", "0");
        db.prepare("INSERT INTO meta(key, value) VALUES(?, ?)").run("effect_count", "0");
        db.prepare("INSERT INTO meta(key, value) VALUES(?, ?)").run("event_count", "0");
        db.prepare("INSERT INTO meta(key, value) VALUES(?, ?)").run("composition_binding_json", bindingJson);
        db.prepare("INSERT INTO meta(key, value) VALUES(?, ?)").run("composition_binding_hash", bindingHash);
        const initial = {
          version: 0,
          status: STATUS.IDLE,
          active_selector: null,
          active_package_hash: null,
          previous_selector: null,
          previous_package_hash: null,
          failure_code: null,
        };
        db.prepare(
          `INSERT INTO current_projection(
            singleton, version, status, active_selector, active_package_hash,
            previous_selector, previous_package_hash, failure_code, projection_hash
          ) VALUES(1, ?, ?, ?, ?, ?, ?, ?, ?)`,
        ).run(
          initial.version,
          initial.status,
          initial.active_selector,
          initial.active_package_hash,
          initial.previous_selector,
          initial.previous_package_hash,
          initial.failure_code,
          projectionHash(initial),
        );
      } else {
        const schemaDigest = db.prepare("SELECT value FROM meta WHERE key = ?").get("schema_sha256");
        const counters = ["operation_count", "effect_count", "event_count"].map(
          (key) => db.prepare("SELECT value FROM meta WHERE key = ?").get(key)?.value,
        );
        const storedBinding = db.prepare("SELECT value FROM meta WHERE key = ?").get("composition_binding_json")?.value;
        const storedBindingHash = db.prepare("SELECT value FROM meta WHERE key = ?").get("composition_binding_hash")?.value;
        if (
          existingVersion.value !== "3" ||
          schemaDigest?.value !== COMPILED_STATE_SCHEMA_SHA256 ||
          counters.some((value) => typeof value !== "string" || !/^(?:0|[1-9]\d*)$/u.test(value)) ||
          storedBinding !== bindingJson ||
          storedBindingHash !== bindingHash
        ) {
          fail(
            FAILURE.HOST_UNSUPPORTED,
            "lifecycle state belongs to a different immutable runtime composition",
            STATUS.UNSUPPORTED,
          );
        }
      }
    });
    const metaKeys = db.prepare("SELECT key FROM meta ORDER BY key").all().map((row) => row.key);
    const expectedMetaKeys = [
      "composition_binding_hash",
      "composition_binding_json",
      "contract_version",
      "effect_count",
      "event_count",
      "operation_count",
      "schema_sha256",
    ];
    if (canonicalJson(metaKeys) !== canonicalJson(expectedMetaKeys)) {
      fail(FAILURE.STATE_CORRUPT, "lifecycle metadata contains unknown or missing fields");
    }
    for (const name of OWNED_DIRECTORIES) {
      const target = roots[name];
      if (!fs.existsSync(target)) fs.mkdirSync(target, { recursive: false, mode: 0o700 });
      const stat = fs.lstatSync(target, { bigint: true });
      if (stat.isSymbolicLink() || !stat.isDirectory() || pathKey(fs.realpathSync.native(target)) !== pathKey(target)) {
        fail(FAILURE.STATE_CORRUPT, `owned ${name} root is invalid`);
      }
    }
  };

  const projection = () => {
    assertOwnership();
    const row = db.prepare("SELECT * FROM current_projection WHERE singleton = 1").get();
    if (row === undefined || projectionHash(row) !== row.projection_hash) {
      fail(FAILURE.STATE_CORRUPT, "current projection CAS seal is invalid");
    }
    return row;
  };

  const consumeCount = (key, maximum, label) => {
    const row = db.prepare("SELECT value FROM meta WHERE key = ?").get(key);
    if (row === undefined || !/^(?:0|[1-9]\d*)$/u.test(row.value)) {
      fail(FAILURE.STATE_CORRUPT, `${label} counter is invalid`);
    }
    const current = Number(row.value);
    if (!Number.isSafeInteger(current) || current >= maximum) {
      fail(FAILURE.RESOURCE_LIMIT, `${label} history budget is exhausted`);
    }
    db.prepare("UPDATE meta SET value = ? WHERE key = ?").run(String(current + 1), key);
  };

  const casProjection = (patch) => {
    const current = projection();
    const next = {
      version: current.version + 1,
      status: patch.status ?? current.status,
      active_selector: Object.hasOwn(patch, "active_selector") ? patch.active_selector : current.active_selector,
      active_package_hash: Object.hasOwn(patch, "active_package_hash")
        ? patch.active_package_hash
        : current.active_package_hash,
      previous_selector: Object.hasOwn(patch, "previous_selector") ? patch.previous_selector : current.previous_selector,
      previous_package_hash: Object.hasOwn(patch, "previous_package_hash")
        ? patch.previous_package_hash
        : current.previous_package_hash,
      failure_code: Object.hasOwn(patch, "failure_code") ? patch.failure_code : current.failure_code,
    };
    const nextHash = projectionHash(next);
    const changed = db.prepare(
      `UPDATE current_projection SET
        version = ?, status = ?, active_selector = ?, active_package_hash = ?,
        previous_selector = ?, previous_package_hash = ?, failure_code = ?, projection_hash = ?
       WHERE singleton = 1 AND version = ? AND projection_hash = ?`,
    ).run(
      next.version,
      next.status,
      next.active_selector,
      next.active_package_hash,
      next.previous_selector,
      next.previous_package_hash,
      next.failure_code,
      nextHash,
      current.version,
      current.projection_hash,
    );
    if (Number(changed.changes) !== 1) fail(FAILURE.CONCURRENT_OPERATION, "projection CAS failed", STATUS.BLOCKED);
    return { ...next, projection_hash: nextHash };
  };

  const addEvent = (operationId, kind, status, data) => {
    const epoch = assertOwnership();
    consumeCount("event_count", LIMITS.maxHistoryEvents, "event");
    db.prepare(
      "INSERT INTO events(operation_id, owner_epoch, kind, status, data_json, created_at) VALUES(?, ?, ?, ?, ?, ?)",
    ).run(operationId, epoch, kind, status, asJson(data, "event data"), new Date().toISOString());
  };

  const operationForUpdate = (operationId) => {
    const epoch = assertOwnership();
    const row = db.prepare("SELECT * FROM operations WHERE operation_id = ? AND resolved_at IS NULL").get(operationId);
    if (row === undefined) fail(FAILURE.STATE_CORRUPT, "pending operation is missing");
    if (row.owner_epoch !== epoch) fail(FAILURE.CONCURRENT_OPERATION, "operation fence belongs to another owner", STATUS.BLOCKED);
    return row;
  };

  const pending = () => {
    assertOwnership();
    return db.prepare("SELECT * FROM operations WHERE resolved_at IS NULL").get() ?? null;
  };

  const claimPending = (operationId) =>
    tx(() => {
      const epoch = assertOwnership();
      const row = db.prepare("SELECT * FROM operations WHERE operation_id = ? AND resolved_at IS NULL").get(operationId);
      if (row === undefined) fail(FAILURE.STATE_CORRUPT, "pending operation disappeared before fencing");
      if (row.owner_epoch !== epoch) {
        db.prepare("UPDATE operations SET owner_epoch = ?, phase = 'RECONCILING' WHERE operation_id = ?").run(epoch, operationId);
        db.prepare("UPDATE effects SET owner_epoch = ? WHERE operation_id = ? AND resolved_at IS NULL").run(
          epoch,
          operationId,
        );
        addEvent(operationId, "OPERATION_FENCED", STATUS.BLOCKED, {
          previous_owner_epoch: row.owner_epoch,
          owner_epoch: epoch,
        });
      }
      return db.prepare("SELECT * FROM operations WHERE operation_id = ?").get(operationId);
    });

  const startOperation = ({ operationId, method, selector = null, preparedId = null, intent = null }) =>
    tx(() => {
      const epoch = assertOwnership();
      if (db.prepare("SELECT operation_id FROM operations WHERE resolved_at IS NULL").get() !== undefined) {
        fail(FAILURE.CONCURRENT_OPERATION, "one global lifecycle operation is already pending", STATUS.BLOCKED);
      }
      consumeCount("operation_count", LIMITS.maxHistoryOperations, "operation");
      const now = new Date().toISOString();
      db.prepare(
        `INSERT INTO operations(
          operation_id, owner_epoch, method, selector, prepared_id, status, phase,
          intent_json, result_json, started_at, resolved_at
        ) VALUES(?, ?, ?, ?, ?, 'PENDING', 'STARTED', ?, NULL, ?, NULL)`,
      ).run(operationId, epoch, method, selector, preparedId, asJson(intent, "operation intent"), now);
      addEvent(operationId, "OPERATION_STARTED", "PENDING", { method, selector, prepared_id: preparedId });
      return db.prepare("SELECT * FROM operations WHERE operation_id = ?").get(operationId);
    });

  const updatePreparationInner = (preparedId, patch) => {
    const allowed = new Set([
      "status",
      "plugin_data_snapshot_hash",
      "plugin_data_snapshot_operation_id",
      "updated_at",
      "cancelled_at",
      "finalized_at",
    ]);
    if (Object.keys(patch).some((key) => !allowed.has(key))) fail(FAILURE.INVALID_INPUT, "preparation patch is not allowed");
    const current = db.prepare("SELECT * FROM preparations WHERE prepared_id = ?").get(preparedId);
    if (current === undefined) fail(FAILURE.NOT_FOUND, "preparation is missing");
    const next = { ...current, ...patch };
    db.prepare(
      `UPDATE preparations SET
        status = ?, plugin_data_snapshot_hash = ?, plugin_data_snapshot_operation_id = ?,
        updated_at = ?, cancelled_at = ?, finalized_at = ?
       WHERE prepared_id = ?`,
    ).run(
      next.status,
      next.plugin_data_snapshot_hash,
      next.plugin_data_snapshot_operation_id,
      next.updated_at ?? new Date().toISOString(),
      next.cancelled_at,
      next.finalized_at,
      preparedId,
    );
    return db.prepare("SELECT * FROM preparations WHERE prepared_id = ?").get(preparedId);
  };

  const finishOperation = ({ operationId, outcome, projectionPatch = {}, preparationPatch = null }) =>
    tx(() => {
      operationForUpdate(operationId);
      if (db.prepare("SELECT effect_id FROM effects WHERE operation_id = ? AND resolved_at IS NULL").get(operationId) !== undefined) {
        fail(FAILURE.STATE_CORRUPT, "operation has an unresolved effect");
      }
      const heldLease = db.prepare("SELECT lease_id FROM operation_leases WHERE operation_id = ? AND status = 'HELD'").get(operationId);
      if (heldLease !== undefined) fail(FAILURE.QUIESCENCE_REQUIRED, "operation still owns a quiescence lease", STATUS.BLOCKED);
      if (preparationPatch !== null) updatePreparationInner(preparationPatch.prepared_id, preparationPatch.patch);
      const now = new Date().toISOString();
      db.prepare(
        "UPDATE operations SET status = ?, phase = 'RESOLVED', result_json = ?, resolved_at = ? WHERE operation_id = ?",
      ).run(outcome.status, asJson(outcome, "operation result"), now, operationId);
      addEvent(operationId, "OPERATION_RESOLVED", outcome.status, {
        code: outcome.code ?? null,
        prepared_id: outcome.prepared_id ?? null,
        package_hash: outcome.package_hash ?? null,
      });
      return casProjection({
        ...projectionPatch,
        status: Object.hasOwn(projectionPatch, "status") ? projectionPatch.status : outcome.status,
        failure_code: Object.hasOwn(projectionPatch, "failure_code")
          ? projectionPatch.failure_code
          : outcome.code ?? null,
      });
    });

  const intentEffect = ({ operationId, effectId, kind, intent }) =>
    tx(() => {
      const epoch = assertOwnership();
      operationForUpdate(operationId);
      if (db.prepare("SELECT effect_id FROM effects WHERE operation_id = ? AND resolved_at IS NULL").get(operationId) !== undefined) {
        fail(FAILURE.CONCURRENT_OPERATION, "operation already has a pending effect", STATUS.BLOCKED);
      }
      const ordinal = Number(db.prepare("SELECT COUNT(*) AS count FROM effects WHERE operation_id = ?").get(operationId).count) + 1;
      if (ordinal > LIMITS.maxEffectsPerOperation) fail(FAILURE.RESOURCE_LIMIT, "operation effect budget is exhausted");
      consumeCount("effect_count", LIMITS.maxHistoryEffects, "effect");
      db.prepare(
        `INSERT INTO effects(
          effect_id, operation_id, owner_epoch, ordinal, kind, phase, intent_json,
          resolution_json, diagnostic_hash, created_at, resolved_at
        ) VALUES(?, ?, ?, ?, ?, 'INTENT_COMMITTED', ?, NULL, NULL, ?, NULL)`,
      ).run(effectId, operationId, epoch, ordinal, kind, asJson(intent, "effect intent"), new Date().toISOString());
      db.prepare("UPDATE operations SET phase = 'EFFECT_PENDING' WHERE operation_id = ?").run(operationId);
      addEvent(operationId, "EFFECT_INTENT_COMMITTED", "PENDING", { effect_id: effectId, kind, ordinal });
      return db.prepare("SELECT * FROM effects WHERE effect_id = ?").get(effectId);
    });

  const storeDiagnosticInner = (diagnostic) => {
    if (diagnostic === null) return null;
    const boundedDiagnostic = boundedJson(diagnostic, "diagnostic blob", {
      bytes: LIMITS.maxDiagnosticBytes,
      depth: 16,
      nodes: 4096,
      string: LIMITS.maxDiagnosticBytes,
    });
    const data = Buffer.from(canonicalJson(boundedDiagnostic), "utf8");
    if (data.length > LIMITS.maxDiagnosticBytes) fail(FAILURE.RESOURCE_LIMIT, "diagnostic blob exceeds bound");
    const diagnosticHash = sha256(data);
    const existing = db.prepare("SELECT * FROM diagnostic_blobs WHERE blob_hash = ?").get(diagnosticHash);
    if (existing === undefined) {
      const liveCount = Number(db.prepare("SELECT COUNT(*) AS count FROM diagnostic_blobs WHERE data IS NOT NULL").get().count);
      if (liveCount >= LIMITS.maxDiagnosticBlobs) fail(FAILURE.RESOURCE_LIMIT, "diagnostic blob store is full");
      assertRetainedCapacity(0, data.length, 1);
      db.prepare(
        "INSERT INTO diagnostic_blobs(blob_hash, byte_size, data, created_at, purged_at) VALUES(?, ?, ?, ?, NULL)",
      ).run(diagnosticHash, data.length, data, new Date().toISOString());
    } else if (existing.data === null) {
      assertRetainedCapacity(0, data.length, 1);
      db.prepare("UPDATE diagnostic_blobs SET byte_size = ?, data = ?, purged_at = NULL WHERE blob_hash = ?").run(
        data.length,
        data,
        diagnosticHash,
      );
    }
    return diagnosticHash;
  };

  const attachEffectDiagnostic = ({ effectId, diagnostic }) =>
    tx(() => {
      const effect = db.prepare("SELECT * FROM effects WHERE effect_id = ? AND resolved_at IS NULL").get(effectId);
      if (effect === undefined) fail(FAILURE.STATE_CORRUPT, "pending effect is missing");
      operationForUpdate(effect.operation_id);
      const diagnosticHash = storeDiagnosticInner(diagnostic);
      db.prepare("UPDATE effects SET diagnostic_hash = ? WHERE effect_id = ?").run(diagnosticHash, effectId);
      addEvent(effect.operation_id, "EFFECT_DIAGNOSTIC_ATTACHED", "PENDING", {
        effect_id: effectId,
        diagnostic_hash: diagnosticHash,
      });
      return diagnosticHash;
    });

  const resolveEffectInner = ({ effectId, resolution, diagnostic = null }) => {
    const effect = db.prepare("SELECT * FROM effects WHERE effect_id = ? AND resolved_at IS NULL").get(effectId);
    if (effect === undefined) fail(FAILURE.STATE_CORRUPT, "pending effect is missing");
    if (effect.owner_epoch !== assertOwnership()) {
      fail(FAILURE.CONCURRENT_OPERATION, "effect resolution fence belongs to another owner", STATUS.BLOCKED);
    }
    operationForUpdate(effect.operation_id);
    const diagnosticHash = storeDiagnosticInner(diagnostic) ?? effect.diagnostic_hash;
    const now = new Date().toISOString();
    db.prepare(
      `UPDATE effects SET phase = 'RESOLVED', resolution_json = ?, diagnostic_hash = ?, resolved_at = ?
       WHERE effect_id = ?`,
    ).run(asJson(resolution, "effect resolution"), diagnosticHash, now, effectId);
    if (resolution.status === "APPLIED" && ["HOST_MARKETPLACE_ADD", "HOST_MARKETPLACE_REMOVE"].includes(effect.kind)) {
      const intent = JSON.parse(effect.intent_json);
      const marketplace = db.prepare("SELECT * FROM marketplaces WHERE marketplace_id = ?").get(intent.marketplace_id);
      if (marketplace === undefined || marketplace.registration_name !== intent.name || marketplace.disposed_at !== null) {
        fail(FAILURE.STATE_CORRUPT, "marketplace effect does not bind a live recorded marketplace");
      }
      if (effect.kind === "HOST_MARKETPLACE_ADD") {
        db.prepare("UPDATE marketplaces SET registered = 1 WHERE marketplace_id = ?").run(intent.marketplace_id);
      } else {
        db.prepare("UPDATE marketplaces SET registered = 0 WHERE marketplace_id = ?").run(intent.marketplace_id);
      }
    }
    db.prepare("UPDATE operations SET phase = 'EFFECT_RESOLVED' WHERE operation_id = ?").run(effect.operation_id);
    addEvent(effect.operation_id, "EFFECT_RESOLVED", resolution.status ?? "UNKNOWN", {
      effect_id: effectId,
      diagnostic_hash: diagnosticHash,
    });
    return { effect, diagnosticHash };
  };

  const resolveEffect = (value) => tx(() => resolveEffectInner(value).diagnosticHash);
  const unresolvedEffect = (operationId) => {
    assertOwnership();
    return db.prepare(
      "SELECT * FROM effects WHERE operation_id = ? AND resolved_at IS NULL ORDER BY ordinal LIMIT 1",
    ).get(operationId) ?? null;
  };
  const effects = (operationId) => {
    assertOwnership();
    return db.prepare("SELECT * FROM effects WHERE operation_id = ? ORDER BY ordinal").all(operationId);
  };
  const ensureDiagnosticCapacity = (required = 1) => {
    assertOwnership();
    if (!Number.isSafeInteger(required) || required < 1 || required > 2) {
      fail(FAILURE.INVALID_INPUT, "diagnostic reservation is invalid");
    }
    const count = Number(db.prepare("SELECT COUNT(*) AS count FROM diagnostic_blobs WHERE data IS NOT NULL").get().count);
    if (count + required > LIMITS.maxDiagnosticBlobs) fail(FAILURE.RESOURCE_LIMIT, "diagnostic blob store is full");
  };

  const assertRetainedCapacity = (extraEntries, extraBytes, extraObjects = 1) => {
    assertOwnership();
    if (
      !Number.isSafeInteger(extraEntries) ||
      !Number.isSafeInteger(extraBytes) ||
      !Number.isSafeInteger(extraObjects) ||
      extraEntries < 0 ||
      extraBytes < 0 ||
      extraObjects < 0
    ) fail(FAILURE.INVALID_INPUT, "retained lifecycle capacity request is invalid");
    const totals = db.prepare(
      `SELECT
        (SELECT COALESCE(SUM(entry_count), 0) FROM packages WHERE disposed_at IS NULL) +
        (SELECT COALESCE(SUM(s.entry_count), 0)
           FROM operation_snapshots o JOIN snapshots s ON s.snapshot_hash = o.snapshot_hash
          WHERE o.status != 'DISPOSED' AND s.disposed_at IS NULL) +
        (SELECT COALESCE(SUM(p.entry_count + 5), 0)
           FROM marketplaces m JOIN packages p ON p.package_hash = m.package_hash
          WHERE m.disposed_at IS NULL) AS entries,
        (SELECT COALESCE(SUM(byte_size + inventory_bytes), 0) FROM packages WHERE disposed_at IS NULL) +
        (SELECT COALESCE(SUM(s.byte_size + s.inventory_bytes), 0)
           FROM operation_snapshots o JOIN snapshots s ON s.snapshot_hash = o.snapshot_hash
          WHERE o.status != 'DISPOSED' AND s.disposed_at IS NULL) +
        (SELECT COALESCE(SUM(p.byte_size + ${LIMITS.maxManifestBytes}), 0)
           FROM marketplaces m JOIN packages p ON p.package_hash = m.package_hash
          WHERE m.disposed_at IS NULL) +
        (SELECT COALESCE(SUM(byte_size), 0) FROM diagnostic_blobs WHERE data IS NOT NULL) AS bytes,
        (SELECT COUNT(*) FROM packages WHERE disposed_at IS NULL) +
        (SELECT COUNT(*) FROM operation_snapshots WHERE status != 'DISPOSED') +
        (SELECT COUNT(*) FROM marketplaces WHERE disposed_at IS NULL) +
        (SELECT COUNT(*) FROM diagnostic_blobs WHERE data IS NOT NULL) AS objects`,
    ).get();
    if (
      Number(totals.entries) + extraEntries > LIMITS.maxRetainedEntries ||
      Number(totals.bytes) + extraBytes > LIMITS.maxRetainedBytes ||
      Number(totals.objects) + extraObjects > LIMITS.maxRetainedObjects
    ) fail(FAILURE.RESOURCE_LIMIT, "retained lifecycle resource budget is exhausted");
  };

  const ensurePackageCapacity = (record) => {
    assertOwnership();
    const prior = db.prepare("SELECT disposed_at FROM packages WHERE package_hash = ?").get(record.package_hash);
    if (prior === undefined || prior.disposed_at !== null) {
      assertRetainedCapacity(record.entry_count, record.byte_size + record.inventory_bytes);
    }
  };

  const ensureSnapshotCapacity = (entryCount, byteSize) => {
    assertOwnership();
    assertRetainedCapacity(entryCount, byteSize + LIMITS.maxInjectedBytes);
  };

  const ensureMarketplaceCapacity = (packageHash, marketplaceId) => {
    assertOwnership();
    const prior = db.prepare("SELECT disposed_at FROM marketplaces WHERE marketplace_id = ?").get(marketplaceId);
    if (prior !== undefined && prior.disposed_at === null) return;
    const packageRow = db.prepare(
      "SELECT entry_count, byte_size FROM packages WHERE package_hash = ? AND disposed_at IS NULL",
    ).get(packageHash);
    if (packageRow === undefined) fail(FAILURE.STATE_CORRUPT, "marketplace package record is unavailable");
    assertRetainedCapacity(
      Number(packageRow.entry_count) + 5,
      Number(packageRow.byte_size) + LIMITS.maxManifestBytes,
    );
  };

  const validateInventoryRecord = (record) => {
    const bytes = Buffer.byteLength(record.inventory_json, "utf8");
    if (
      bytes !== record.inventory_bytes ||
      bytes > LIMITS.maxInventoryBytes ||
      record.entry_count > LIMITS.maxEntries ||
      record.file_count > record.entry_count
    ) fail(FAILURE.STATE_CORRUPT, "tree record exceeds or differs from its inventory bounds");
  };

  const savePackage = (record) =>
    tx(() => {
      validateInventoryRecord(record);
      const prior = db.prepare("SELECT * FROM packages WHERE package_hash = ?").get(record.package_hash);
      if (prior === undefined || prior.disposed_at !== null) {
        assertRetainedCapacity(record.entry_count, record.byte_size + record.inventory_bytes);
      }
      db.prepare(
        `INSERT INTO packages(
          package_hash, plugin_name, plugin_version, manifest_hash, has_hooks, hook_subject_hash,
          entry_count, file_count, byte_size, inventory_bytes, inventory_json, preserved_root, created_at, disposed_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(package_hash) DO UPDATE SET preserved_root = excluded.preserved_root, disposed_at = NULL`,
      ).run(
        record.package_hash,
        record.plugin_name,
        record.plugin_version,
        record.manifest_hash,
        record.has_hooks ? 1 : 0,
        record.hook_subject_hash,
        record.entry_count,
        record.file_count,
        record.byte_size,
        record.inventory_bytes,
        record.inventory_json,
        record.preserved_root,
        new Date().toISOString(),
      );
      const observed = db.prepare("SELECT * FROM packages WHERE package_hash = ?").get(record.package_hash);
      if (
        observed === undefined ||
        observed.plugin_name !== record.plugin_name ||
        observed.plugin_version !== record.plugin_version ||
        observed.manifest_hash !== record.manifest_hash ||
        rowBoolean(observed.has_hooks) !== record.has_hooks ||
        observed.hook_subject_hash !== record.hook_subject_hash ||
        observed.entry_count !== record.entry_count ||
        observed.file_count !== record.file_count ||
        observed.byte_size !== record.byte_size ||
        observed.inventory_bytes !== record.inventory_bytes ||
        observed.inventory_json !== record.inventory_json ||
        observed.preserved_root !== record.preserved_root ||
        observed.disposed_at !== null
      ) fail(FAILURE.STATE_CORRUPT, "package record collision");
      return observed;
    });

  const packageRecord = (packageHash) => {
    assertOwnership();
    return db.prepare("SELECT * FROM packages WHERE package_hash = ? AND disposed_at IS NULL").get(packageHash) ?? null;
  };
  const packageHashes = () => {
    assertOwnership();
    return db.prepare("SELECT package_hash FROM packages WHERE disposed_at IS NULL").all().map((row) => row.package_hash);
  };

  const saveSnapshot = (record) =>
    tx(() => {
      validateInventoryRecord(record);
      const prior = db.prepare("SELECT * FROM snapshots WHERE snapshot_hash = ?").get(record.snapshot_hash);
      if (prior === undefined || prior.disposed_at !== null) {
        assertRetainedCapacity(record.entry_count, record.byte_size + record.inventory_bytes);
      }
      db.prepare(
        `INSERT INTO snapshots(
          snapshot_hash, entry_count, file_count, byte_size, inventory_bytes,
          inventory_json, preserved_root, created_at, disposed_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(snapshot_hash) DO UPDATE SET preserved_root = excluded.preserved_root, disposed_at = NULL`,
      ).run(
        record.snapshot_hash,
        record.entry_count,
        record.file_count,
        record.byte_size,
        record.inventory_bytes,
        record.inventory_json,
        record.preserved_root,
        new Date().toISOString(),
      );
      const observed = db.prepare("SELECT * FROM snapshots WHERE snapshot_hash = ?").get(record.snapshot_hash);
      if (
        observed === undefined ||
        observed.entry_count !== record.entry_count ||
        observed.file_count !== record.file_count ||
        observed.byte_size !== record.byte_size ||
        observed.inventory_bytes !== record.inventory_bytes ||
        observed.inventory_json !== record.inventory_json ||
        observed.preserved_root !== record.preserved_root ||
        observed.disposed_at !== null
      ) fail(FAILURE.STATE_CORRUPT, "snapshot record collision");
      return observed;
    });

  const snapshotRecord = (hash) => {
    assertOwnership();
    return db.prepare("SELECT * FROM snapshots WHERE snapshot_hash = ? AND disposed_at IS NULL").get(hash) ?? null;
  };

  const saveMarketplace = (record) =>
    tx(() => {
      const packageRow = db.prepare(
        "SELECT entry_count, byte_size FROM packages WHERE package_hash = ? AND disposed_at IS NULL",
      ).get(record.package_hash);
      if (packageRow === undefined) fail(FAILURE.STATE_CORRUPT, "marketplace package record is unavailable");
      assertRetainedCapacity(
        Number(packageRow.entry_count) + 5,
        Number(packageRow.byte_size) + LIMITS.maxManifestBytes,
      );
      db.prepare(
        `INSERT INTO marketplaces(
          marketplace_id, registration_name, root, selector, package_hash, purpose,
          registered, created_at, disposed_at
        ) VALUES(?, ?, ?, ?, ?, ?, 0, ?, NULL)`,
      ).run(
        record.marketplace_id,
        record.registration_name,
        record.root,
        record.selector,
        record.package_hash,
        record.purpose,
        new Date().toISOString(),
      );
      return db.prepare("SELECT * FROM marketplaces WHERE marketplace_id = ?").get(record.marketplace_id);
    });

  const marketplace = (marketplaceId, includeDisposed = false) => {
    assertOwnership();
    return db.prepare(
      includeDisposed
        ? "SELECT * FROM marketplaces WHERE marketplace_id = ?"
        : "SELECT * FROM marketplaces WHERE marketplace_id = ? AND disposed_at IS NULL",
    ).get(marketplaceId) ?? null;
  };
  const allMarketplaces = () => {
    assertOwnership();
    return db.prepare("SELECT * FROM marketplaces WHERE disposed_at IS NULL ORDER BY marketplace_id").all();
  };
  const setMarketplaceRegistered = (marketplaceId, registered) =>
    tx(() => {
      const item = db.prepare("SELECT * FROM marketplaces WHERE marketplace_id = ? AND disposed_at IS NULL").get(marketplaceId);
      if (item === undefined) fail(FAILURE.STATE_CORRUPT, "marketplace record is missing");
      db.prepare("UPDATE marketplaces SET registered = ? WHERE marketplace_id = ?").run(registered ? 1 : 0, marketplaceId);
    });

  const savePreparation = (record) =>
    tx(() => {
      const count = Number(db.prepare("SELECT COUNT(*) AS count FROM preparations WHERE finalized_at IS NULL").get().count);
      if (count >= LIMITS.maxPreparations) fail(FAILURE.RESOURCE_LIMIT, "live preparation budget is exhausted");
      db.prepare(
        `INSERT INTO preparations(
          prepared_id, selector, activation_selector, rollback_selector, status,
          candidate_package_hash, previous_selector, previous_package_hash, previous_root,
          candidate_marketplace_id, rollback_marketplace_id, plugin_data_snapshot_hash,
          plugin_data_snapshot_operation_id,
          migration_plan_json, trust_nonce, created_at, updated_at, cancelled_at, finalized_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, NULL, NULL)`,
      ).run(
        record.prepared_id,
        record.selector,
        record.activation_selector,
        record.rollback_selector,
        record.status,
        record.candidate_package_hash,
        record.previous_selector,
        record.previous_package_hash,
        record.previous_root,
        record.candidate_marketplace_id,
        record.rollback_marketplace_id,
        record.migration_plan_json,
        record.trust_nonce,
        record.created_at,
        record.updated_at,
      );
      return db.prepare("SELECT * FROM preparations WHERE prepared_id = ?").get(record.prepared_id);
    });

  const preparation = (preparedId) => {
    assertOwnership();
    return db.prepare("SELECT * FROM preparations WHERE prepared_id = ?").get(preparedId) ?? null;
  };
  const updatePreparation = (preparedId, patch) => tx(() => updatePreparationInner(preparedId, patch));
  const preparationHasEffectResolution = (preparedId, kind, statuses) => {
    assertOwnership();
    if (
      typeof preparedId !== "string" ||
      typeof kind !== "string" ||
      !Array.isArray(statuses) ||
      !statuses.every((status) => typeof status === "string")
    ) fail(FAILURE.INVALID_INPUT, "preparation effect query is invalid");
    const rows = db.prepare(
      `SELECT e.resolution_json FROM operations o JOIN effects e ON e.operation_id = o.operation_id
       WHERE o.prepared_id = ? AND e.kind = ? AND e.resolution_json IS NOT NULL`,
    ).all(preparedId, kind);
    return rows.some((row) => {
      try {
        const value = boundedJson(JSON.parse(row.resolution_json), "stored effect resolution");
        return statuses.includes(value.status);
      } catch {
        fail(FAILURE.STATE_CORRUPT, "stored effect resolution is invalid");
      }
    });
  };

  const recordLeaseAcquire = ({ effectId, lease }) =>
    tx(() => {
      const effect = db.prepare("SELECT * FROM effects WHERE effect_id = ? AND resolved_at IS NULL").get(effectId);
      if (effect === undefined || effect.kind !== "QUIESCE_ACQUIRE") fail(FAILURE.STATE_CORRUPT, "lease acquire effect is invalid");
      operationForUpdate(effect.operation_id);
      const existing = db.prepare("SELECT * FROM operation_leases WHERE operation_id = ?").get(effect.operation_id);
      if (existing !== undefined && existing.status !== "RELEASED") fail(FAILURE.STATE_CORRUPT, "operation already has a held lease");
      db.prepare(
        `INSERT INTO operation_leases(operation_id, lease_id, lease_json, status, acquired_effect_id, updated_at)
         VALUES(?, ?, ?, 'HELD', ?, ?)
         ON CONFLICT(operation_id) DO UPDATE SET
           lease_id = excluded.lease_id, lease_json = excluded.lease_json,
           status = 'HELD', acquired_effect_id = excluded.acquired_effect_id, updated_at = excluded.updated_at`,
      ).run(
        effect.operation_id,
        lease.lease_id,
        asJson(lease, "quiescence lease"),
        effectId,
        new Date().toISOString(),
      );
      resolveEffectInner({ effectId, resolution: { status: "APPLIED", lease_id: lease.lease_id } });
      return db.prepare("SELECT * FROM operation_leases WHERE operation_id = ?").get(effect.operation_id);
    });

  const updateRecoveredLease = (operationId, lease) =>
    tx(() => {
      operationForUpdate(operationId);
      const current = db.prepare("SELECT * FROM operation_leases WHERE operation_id = ? AND status = 'HELD'").get(operationId);
      if (current === undefined || current.lease_id !== lease.lease_id) fail(FAILURE.STATE_CORRUPT, "recovered lease does not match durable ownership");
      db.prepare("UPDATE operation_leases SET lease_json = ?, updated_at = ? WHERE operation_id = ?").run(
        asJson(lease, "recovered quiescence lease"),
        new Date().toISOString(),
        operationId,
      );
      addEvent(operationId, "LEASE_RECOVERED", "HELD", { lease_id: lease.lease_id });
      return db.prepare("SELECT * FROM operation_leases WHERE operation_id = ?").get(operationId);
    });

  const recordLeaseRelease = ({ effectId, leaseId }) =>
    tx(() => {
      const effect = db.prepare("SELECT * FROM effects WHERE effect_id = ? AND resolved_at IS NULL").get(effectId);
      if (effect === undefined || effect.kind !== "QUIESCE_RELEASE") fail(FAILURE.STATE_CORRUPT, "lease release effect is invalid");
      operationForUpdate(effect.operation_id);
      const current = db.prepare("SELECT * FROM operation_leases WHERE operation_id = ? AND status = 'HELD'").get(effect.operation_id);
      if (current === undefined || current.lease_id !== leaseId) fail(FAILURE.STATE_CORRUPT, "released lease differs from durable ownership");
      db.prepare("UPDATE operation_leases SET status = 'RELEASED', updated_at = ? WHERE operation_id = ?").run(
        new Date().toISOString(),
        effect.operation_id,
      );
      resolveEffectInner({ effectId, resolution: { status: "APPLIED", lease_id: leaseId } });
    });

  const lease = (operationId) => {
    assertOwnership();
    return db.prepare("SELECT * FROM operation_leases WHERE operation_id = ?").get(operationId) ?? null;
  };

  const resolveSnapshotCapture = ({ effectId, snapshotLink, resolution }) =>
    tx(() => {
      const effect = db.prepare("SELECT * FROM effects WHERE effect_id = ? AND resolved_at IS NULL").get(effectId);
      if (effect === undefined || effect.kind !== "DATA_SNAPSHOT_CAPTURE") fail(FAILURE.STATE_CORRUPT, "snapshot capture effect is invalid");
      operationForUpdate(effect.operation_id);
      db.prepare(
        `INSERT INTO operation_snapshots(
          operation_id, snapshot_hash, capability_id, external_snapshot_id,
          capture_receipt_hash, restore_receipt_hash, status, updated_at
        ) VALUES(?, ?, ?, ?, ?, NULL, 'CAPTURED', ?)
        ON CONFLICT(operation_id) DO NOTHING`,
      ).run(
        effect.operation_id,
        snapshotLink.snapshot_hash,
        snapshotLink.capability_id,
        snapshotLink.external_snapshot_id,
        snapshotLink.capture_receipt_hash,
        new Date().toISOString(),
      );
      const observed = db.prepare("SELECT * FROM operation_snapshots WHERE operation_id = ?").get(effect.operation_id);
      if (
        observed === undefined ||
        observed.snapshot_hash !== snapshotLink.snapshot_hash ||
        observed.capability_id !== snapshotLink.capability_id ||
        observed.external_snapshot_id !== snapshotLink.external_snapshot_id ||
        observed.capture_receipt_hash !== snapshotLink.capture_receipt_hash
      ) fail(FAILURE.STATE_CORRUPT, "operation snapshot link collision");
      resolveEffectInner({ effectId, resolution });
      return observed;
    });

  const resolveSnapshotRestore = ({ effectId, captureOperationId, receiptHash, resolution }) =>
    tx(() => {
      const effect = db.prepare("SELECT * FROM effects WHERE effect_id = ? AND resolved_at IS NULL").get(effectId);
      if (effect === undefined || effect.kind !== "DATA_SNAPSHOT_RESTORE") fail(FAILURE.STATE_CORRUPT, "snapshot restore effect is invalid");
      operationForUpdate(effect.operation_id);
      const link = db.prepare("SELECT * FROM operation_snapshots WHERE operation_id = ?").get(captureOperationId);
      if (link === undefined || link.status === "DISPOSED") fail(FAILURE.STATE_CORRUPT, "operation snapshot link is unavailable");
      db.prepare(
        "UPDATE operation_snapshots SET restore_receipt_hash = ?, status = 'RESTORED', updated_at = ? WHERE operation_id = ?",
      ).run(receiptHash, new Date().toISOString(), captureOperationId);
      db.prepare(
        `INSERT INTO recoveries(
          operation_id, backup_root, snapshot_hash, restore_receipt_hash, created_at, disposed_at
        ) VALUES(?, NULL, ?, ?, ?, NULL)
        ON CONFLICT(operation_id) DO UPDATE SET restore_receipt_hash = excluded.restore_receipt_hash`,
      ).run(effect.operation_id, link.snapshot_hash, receiptHash, new Date().toISOString());
      resolveEffectInner({ effectId, resolution });
    });

  const resolveSnapshotDispose = ({ effectId, captureOperationId, receiptHash, resolution }) =>
    tx(() => {
      const effect = db.prepare("SELECT * FROM effects WHERE effect_id = ? AND resolved_at IS NULL").get(effectId);
      if (effect === undefined || effect.kind !== "DATA_SNAPSHOT_DISPOSE") fail(FAILURE.STATE_CORRUPT, "snapshot dispose effect is invalid");
      operationForUpdate(effect.operation_id);
      const link = db.prepare("SELECT * FROM operation_snapshots WHERE operation_id = ?").get(captureOperationId);
      if (link === undefined) fail(FAILURE.STATE_CORRUPT, "snapshot dispose link is unavailable");
      db.prepare(
        "UPDATE operation_snapshots SET status = 'DISPOSED', updated_at = ? WHERE operation_id = ?",
      ).run(new Date().toISOString(), captureOperationId);
      addEvent(effect.operation_id, "SNAPSHOT_DISPOSED", "DISPOSED", {
        capture_operation_id: captureOperationId,
        snapshot_hash: link.snapshot_hash,
        receipt_hash: receiptHash,
      });
      resolveEffectInner({ effectId, resolution });
    });

  const operationSnapshot = (operationId) => {
    assertOwnership();
    return db.prepare("SELECT * FROM operation_snapshots WHERE operation_id = ?").get(operationId) ?? null;
  };

  const cancelPreparation = (preparedId) =>
    tx(() => {
      const item = db.prepare("SELECT * FROM preparations WHERE prepared_id = ?").get(preparedId);
      if (item === undefined) fail(FAILURE.NOT_FOUND, "preparation is missing");
      if (item.plugin_data_snapshot_hash !== null || item.finalized_at !== null) {
        fail(FAILURE.INVALID_TRANSITION, "preparation crossed its pre-effect cancellation boundary");
      }
      const mutation = db.prepare(
        `SELECT e.effect_id FROM operations o JOIN effects e ON e.operation_id = o.operation_id
         WHERE o.prepared_id = ? AND e.kind IN (
           'HOST_PLUGIN_ADD', 'HOST_PLUGIN_REMOVE', 'HOST_MARKETPLACE_ADD', 'HOST_MARKETPLACE_REMOVE',
           'MIGRATION_APPLY', 'MIGRATION_ROLLBACK', 'DATA_SNAPSHOT_RESTORE'
         ) LIMIT 1`,
      ).get(preparedId);
      if (mutation !== undefined) fail(FAILURE.INVALID_TRANSITION, "preparation has lifecycle effects");
      return updatePreparationInner(preparedId, {
        status: STATUS.BLOCKED,
        cancelled_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    });

  const finalizePreparation = (preparedId, finalizingOperationId) =>
    tx(() => {
      const item = db.prepare("SELECT * FROM preparations WHERE prepared_id = ?").get(preparedId);
      if (item === undefined) fail(FAILURE.NOT_FOUND, "preparation is missing");
      if (item.finalized_at !== null) return item;
      if (
        item.cancelled_at === null &&
        ![STATUS.ROLLED_BACK, STATUS.FAILED, STATUS.BLOCKED, STATUS.UNINSTALLED, STATUS.UNSUPPORTED].includes(item.status)
      ) {
        fail(FAILURE.INVALID_TRANSITION, "preparation is not terminal for finalization");
      }
      if (
        db.prepare(
          "SELECT operation_id FROM operations WHERE prepared_id = ? AND resolved_at IS NULL AND operation_id != ?",
        ).get(preparedId, finalizingOperationId) !== undefined
      ) {
        fail(FAILURE.CONCURRENT_OPERATION, "preparation still has a pending operation", STATUS.BLOCKED);
      }
      const registered = db.prepare(
        `SELECT m.marketplace_id FROM marketplaces m
         WHERE m.marketplace_id IN (?, ?) AND m.registered = 1 LIMIT 1`,
      ).get(item.candidate_marketplace_id, item.rollback_marketplace_id);
      if (registered !== undefined) fail(FAILURE.INVALID_TRANSITION, "preparation still owns a registered marketplace");
      return updatePreparationInner(preparedId, {
        finalized_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    });

  const cleanupCandidates = ({ before, maxItems }) => {
    assertOwnership();
    const marketplaces = db.prepare(
      `SELECT m.* FROM marketplaces m
       WHERE m.created_at <= ? AND m.registered = 0 AND m.disposed_at IS NULL
         AND NOT EXISTS(
           SELECT 1 FROM preparations p
           WHERE p.finalized_at IS NULL
             AND m.marketplace_id IN (p.candidate_marketplace_id, p.rollback_marketplace_id)
         )
       ORDER BY m.created_at LIMIT ?`,
    ).all(before, maxItems);
    const recoveries = db.prepare(
      `SELECT r.* FROM recoveries r JOIN operations o ON o.operation_id = r.operation_id
       WHERE o.resolved_at IS NOT NULL AND o.resolved_at <= ? AND r.disposed_at IS NULL
       ORDER BY r.created_at LIMIT ?`,
    ).all(before, maxItems);
    const diagnostics = db.prepare(
      `SELECT d.blob_hash FROM diagnostic_blobs d
       WHERE d.data IS NOT NULL AND d.created_at <= ?
         AND NOT EXISTS(
           SELECT 1 FROM effects e JOIN operations o ON o.operation_id = e.operation_id
           WHERE e.diagnostic_hash = d.blob_hash AND o.resolved_at IS NULL
         )
       ORDER BY d.created_at LIMIT ?`,
    ).all(before, maxItems);
    const operationSnapshots = db.prepare(
      `SELECT s.* FROM operation_snapshots s JOIN operations o ON o.operation_id = s.operation_id
       LEFT JOIN preparations p ON p.prepared_id = o.prepared_id
       WHERE s.status IN ('CAPTURED', 'RESTORED') AND o.resolved_at IS NOT NULL AND o.resolved_at <= ?
         AND (
           o.method = 'uninstall' OR p.finalized_at IS NOT NULL OR
           p.plugin_data_snapshot_operation_id IS NULL OR p.plugin_data_snapshot_operation_id != s.operation_id
         )
       ORDER BY s.updated_at LIMIT ?`,
    ).all(before, maxItems);
    const packages = db.prepare(
      `SELECT p.* FROM packages p
       WHERE p.disposed_at IS NULL AND p.created_at <= ?
         AND NOT EXISTS(SELECT 1 FROM marketplaces m WHERE m.package_hash = p.package_hash AND m.disposed_at IS NULL)
         AND NOT EXISTS(
           SELECT 1 FROM preparations q
           WHERE q.finalized_at IS NULL
             AND (q.candidate_package_hash = p.package_hash OR q.previous_package_hash = p.package_hash)
         )
         AND NOT EXISTS(
           SELECT 1 FROM current_projection c
           WHERE c.singleton = 1
             AND (c.active_package_hash = p.package_hash OR c.previous_package_hash = p.package_hash)
         )
       ORDER BY p.created_at LIMIT ?`,
    ).all(before, maxItems);
    const snapshots = db.prepare(
      `SELECT s.* FROM snapshots s
       WHERE s.disposed_at IS NULL AND s.created_at <= ?
         AND NOT EXISTS(
           SELECT 1 FROM preparations p
           WHERE p.finalized_at IS NULL AND p.plugin_data_snapshot_hash = s.snapshot_hash
         )
         AND NOT EXISTS(
           SELECT 1 FROM operation_snapshots o
           WHERE o.snapshot_hash = s.snapshot_hash AND o.status != 'DISPOSED'
         )
         AND NOT EXISTS(
           SELECT 1 FROM recoveries r
           WHERE r.snapshot_hash = s.snapshot_hash AND r.disposed_at IS NULL
         )
       ORDER BY s.created_at LIMIT ?`,
    ).all(before, maxItems);
    return { marketplaces, recoveries, diagnostics, operationSnapshots, packages, snapshots };
  };

  const markMarketplaceDisposed = (marketplaceId) =>
    tx(() => {
      const row = db.prepare("SELECT * FROM marketplaces WHERE marketplace_id = ?").get(marketplaceId);
      if (row === undefined) fail(FAILURE.NOT_FOUND, "marketplace record is missing");
      if (row.disposed_at !== null) return;
      if (row.registered === 1) fail(FAILURE.INVALID_TRANSITION, "registered marketplace cannot be disposed");
      db.prepare("UPDATE marketplaces SET disposed_at = ? WHERE marketplace_id = ?").run(
        new Date().toISOString(),
        marketplaceId,
      );
    });
  const markRecoveryDisposed = (operationId) =>
    tx(() => db.prepare("UPDATE recoveries SET disposed_at = ? WHERE operation_id = ?").run(new Date().toISOString(), operationId));
  const purgeDiagnostic = (blobHash) =>
    tx(() => db.prepare("UPDATE diagnostic_blobs SET data = NULL, purged_at = ? WHERE blob_hash = ?").run(new Date().toISOString(), blobHash));
  const markPackageDisposed = (packageHash) =>
    tx(() => {
      const row = db.prepare("SELECT disposed_at FROM packages WHERE package_hash = ?").get(packageHash);
      if (row === undefined) fail(FAILURE.NOT_FOUND, "package record is missing");
      if (row.disposed_at !== null) return;
      if (cleanupCandidates({ before: new Date().toISOString(), maxItems: LIMITS.maxRetainedObjects }).packages
        .every((item) => item.package_hash !== packageHash)) {
        fail(FAILURE.INVALID_TRANSITION, "referenced package cannot be disposed");
      }
      db.prepare("UPDATE packages SET disposed_at = ? WHERE package_hash = ?").run(new Date().toISOString(), packageHash);
    });
  const markSnapshotDisposed = (snapshotHash) =>
    tx(() => {
      const row = db.prepare("SELECT disposed_at FROM snapshots WHERE snapshot_hash = ?").get(snapshotHash);
      if (row === undefined) fail(FAILURE.NOT_FOUND, "snapshot record is missing");
      if (row.disposed_at !== null) return;
      if (cleanupCandidates({ before: new Date().toISOString(), maxItems: LIMITS.maxRetainedObjects }).snapshots
        .every((item) => item.snapshot_hash !== snapshotHash)) {
        fail(FAILURE.INVALID_TRANSITION, "referenced snapshot cannot be disposed");
      }
      db.prepare("UPDATE snapshots SET disposed_at = ? WHERE snapshot_hash = ?").run(new Date().toISOString(), snapshotHash);
    });

  const resourceDisposed = (resourceType, resourceId) => {
    assertOwnership();
    let row;
    if (resourceType === "marketplace") {
      row = db.prepare("SELECT disposed_at FROM marketplaces WHERE marketplace_id = ?").get(resourceId);
    } else if (resourceType === "package") {
      row = db.prepare("SELECT disposed_at FROM packages WHERE package_hash = ?").get(resourceId);
    } else if (resourceType === "snapshot") {
      row = db.prepare("SELECT disposed_at FROM snapshots WHERE snapshot_hash = ?").get(resourceId);
    } else if (resourceType === "recovery") {
      row = db.prepare("SELECT disposed_at FROM recoveries WHERE operation_id = ?").get(resourceId);
    } else {
      fail(FAILURE.STATE_CORRUPT, "resource disposal type is unknown");
    }
    if (row === undefined) fail(FAILURE.STATE_CORRUPT, "resource disposal record is missing");
    return row.disposed_at !== null;
  };

  const close = () => {
    if (activeEpoch !== null) fail(FAILURE.INVALID_TRANSITION, "cannot close while lifecycle ownership is held");
    if (closed) return;
    if (!databaseClosed) {
      db.close();
      databaseClosed = true;
    }
    if (!lockClosed) {
      lockDb.close();
      lockClosed = true;
    }
    closed = databaseClosed && lockClosed;
  };

  return Object.freeze({
    roots,
    contract,
    withOwnership,
    initialize,
    projection,
    pending,
    claimPending,
    startOperation,
    finishOperation,
    intentEffect,
    attachEffectDiagnostic,
    resolveEffect,
    unresolvedEffect,
    effects,
    ensureDiagnosticCapacity,
    ensurePackageCapacity,
    ensureSnapshotCapacity,
    ensureMarketplaceCapacity,
    savePackage,
    packageRecord,
    packageHashes,
    saveSnapshot,
    snapshotRecord,
    saveMarketplace,
    marketplace,
    allMarketplaces,
    setMarketplaceRegistered,
    savePreparation,
    preparation,
    updatePreparation,
    preparationHasEffectResolution,
    recordLeaseAcquire,
    updateRecoveredLease,
    recordLeaseRelease,
    lease,
    resolveSnapshotCapture,
    resolveSnapshotRestore,
    resolveSnapshotDispose,
    operationSnapshot,
    cancelPreparation,
    finalizePreparation,
    cleanupCandidates,
    markMarketplaceDisposed,
    markRecoveryDisposed,
    purgeDiagnostic,
    markPackageDisposed,
    markSnapshotDisposed,
    resourceDisposed,
    close,
  });
}
