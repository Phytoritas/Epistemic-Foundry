import assert from "node:assert/strict";
import test from "node:test";

import {
  MEMORY_CLASSES,
} from "../policy/index.mjs";

import {
  MEMORY_INDEX_VERSION,
  MEMORY_QUERY_ALGORITHM,
  MEMORY_SEARCH_STATUSES,
  RETRIEVABLE_MEMORY_CLASSES,
  MemoryIndexError,
  buildMemoryIndex,
  compileMemoryQuery,
  executeMemorySearch,
  retrievePermittedMemory,
  validateMemoryIndex,
} from "./index.mjs";
import {
  EVALUATED_AT,
  HASH_A,
  makeConsent,
  makeIndex,
  makePolicy,
  makeRecords,
  makeRequest,
  memoryRecord,
} from "./memory-index-test-support.mjs";


const errorCode = (code) => (error) =>
  error instanceof MemoryIndexError && error.code === code;

test("memory_scope_test: index partitions all six canonical stores and seals identity", () => {
  const index = makeIndex();
  assert.equal(index.index_version, MEMORY_INDEX_VERSION);
  assert.deepEqual(Object.keys(index.stores).toSorted(), [...MEMORY_CLASSES].toSorted());
  assert.equal(index.stores.WORKSPACE.record_count, 2);
  assert.equal(index.stores.EPHEMERAL.record_count, 0);
  assert.match(index.index_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(index.index_id, `MIDX-${index.index_hash.slice(7)}`);
  assert.deepEqual(validateMemoryIndex(index), index);
  assert.ok(Object.isFrozen(index));
  assert.ok(Object.isFrozen(index.stores.WORKSPACE.records));
});

test("memory_scope_test: duplicate memory IDs fail closed across stores", () => {
  const records = makeRecords();
  records.push(memoryRecord({ class: "SESSION", search_text: "duplicate" }));
  assert.throws(() => buildMemoryIndex(records), errorCode("DUPLICATE_MEMORY_ID"));
});

test("memory_scope_test: an unknown memory class cannot create an implicit store", () => {
  assert.throws(
    () => buildMemoryIndex([memoryRecord({ class: "PROFILE" })]),
    errorCode("UNKNOWN_MEMORY_CLASS"),
  );
});

test("memory_scope_test: malformed record shape and accessors are rejected", () => {
  const record = memoryRecord();
  Object.defineProperty(record, "search_text", { enumerable: true, get: () => "secret" });
  assert.throws(() => buildMemoryIndex([record]), errorCode("MEMORY_RECORD_INVALID"));
  assert.throws(
    () => buildMemoryIndex([{ ...memoryRecord(), unexpected: true }]),
    errorCode("MEMORY_RECORD_INVALID"),
  );
});

test("memory_scope_test: store or index tamper is detected", () => {
  const index = structuredClone(makeIndex());
  index.stores.WORKSPACE.records[0].search_text = "tampered";
  assert.throws(() => validateMemoryIndex(index), errorCode("MEMORY_STORE_HASH_MISMATCH"));

  const indexHashTamper = structuredClone(makeIndex());
  indexHashTamper.index_hash = HASH_A;
  assert.throws(
    () => validateMemoryIndex(indexHashTamper),
    errorCode("MEMORY_INDEX_HASH_MISMATCH"),
  );
});

test("memory_scope_test: query plan partitions searched and excluded classes", () => {
  const plan = compileMemoryQuery(makeRequest({ requested_classes: ["SESSION", "WORKSPACE"] }));
  assert.equal(plan.algorithm, MEMORY_QUERY_ALGORITHM);
  assert.deepEqual(plan.searched_classes, ["SESSION", "WORKSPACE"]);
  assert.deepEqual(plan.excluded_classes, ["EPHEMERAL", "USER", "EVIDENCE", "REGULATED"]);
  assert.match(plan.query_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.match(plan.plan_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(plan.consent_id, "CONS-L02-001");
});

test("memory_scope_test: L01 denial occurs before the index is opened", () => {
  let touched = false;
  const inaccessibleIndex = new Proxy({}, {
    get() {
      touched = true;
      throw new Error("index must not be opened");
    },
  });
  const request = makeRequest({ requested_classes: ["REGULATED"], consent_record: null });
  assert.throws(
    () => executeMemorySearch({ index: inaccessibleIndex, request }),
    errorCode("MEMORY_SCOPE_DENIED"),
  );
  assert.equal(touched, false);
});

test("memory_scope_test: the workflow rejects allowed but non-retrievable stores before index access", () => {
  assert.deepEqual(RETRIEVABLE_MEMORY_CLASSES, ["SESSION", "WORKSPACE", "USER", "EVIDENCE"]);
  const policy = makePolicy({
    allowed_classes: [...MEMORY_CLASSES],
  });
  for (const memoryClass of ["EPHEMERAL", "REGULATED"]) {
    let touched = false;
    const inaccessibleIndex = new Proxy({}, {
      get() {
        touched = true;
        throw new Error("index must not be opened");
      },
    });
    assert.throws(
      () => executeMemorySearch({
        index: inaccessibleIndex,
        request: makeRequest({
          policy,
          requested_classes: [memoryClass],
          consent_record: null,
        }),
      }),
      errorCode("MEMORY_STORE_NOT_RETRIEVABLE"),
    );
    assert.equal(touched, false);
  }
});

test("memory_scope_test: only requested stores contribute hits", () => {
  const execution = executeMemorySearch({
    index: makeIndex(),
    request: makeRequest({ requested_classes: ["WORKSPACE"] }),
  });
  assert.equal(execution.status, MEMORY_SEARCH_STATUSES.SEARCHED_WITH_HITS);
  assert.deepEqual(execution.hits.map((hit) => hit.memory_id), ["MEM-L02-001", "MEM-L02-002"]);
  assert.ok(execution.hits.every((hit) => hit.class === "WORKSPACE"));
  assert.ok(execution.plan.excluded_classes.includes("REGULATED"));
  assert.ok(!execution.hits.some((hit) => hit.memory_id === "MEM-L02-005"));
});

test("memory_scope_test: target workspace is an exact store filter", () => {
  const index = makeIndex([
    memoryRecord(),
    memoryRecord({ memory_id: "MEM-L02-OTHER", workspace_id: "WS-L02-OTHER" }),
  ]);
  const execution = executeMemorySearch({ index, request: makeRequest() });
  assert.deepEqual(execution.hits.map((hit) => hit.memory_id), ["MEM-L02-001"]);
});

test("memory_scope_test: each record is rechecked for retention before text scoring", () => {
  const index = makeIndex([
    memoryRecord({ memory_id: "MEM-L02-CURRENT", created_at: "2026-07-01T00:00:00.000Z" }),
    memoryRecord({ memory_id: "MEM-L02-EXPIRED", created_at: "2025-01-01T00:00:00.000Z" }),
  ]);
  const execution = executeMemorySearch({ index, request: makeRequest() });
  assert.deepEqual(execution.hits.map((hit) => hit.memory_id), ["MEM-L02-CURRENT"]);
  assert.deepEqual(execution.policy_excluded_memory_ids, ["MEM-L02-EXPIRED"]);
});

test("memory_scope_test: future-dated records are policy exclusions", () => {
  const index = makeIndex([
    memoryRecord({ memory_id: "MEM-L02-FUTURE", created_at: "2026-08-01T00:00:00.000Z" }),
  ]);
  const execution = executeMemorySearch({ index, request: makeRequest() });
  assert.equal(execution.status, MEMORY_SEARCH_STATUSES.SEARCHED_NONE);
  assert.deepEqual(execution.policy_excluded_memory_ids, ["MEM-L02-FUTURE"]);
});

test("memory_scope_test: cross-workspace retrieval remains denied by default", () => {
  assert.throws(
    () => compileMemoryQuery(makeRequest({ target_workspace_id: "WS-L02-OTHER" })),
    errorCode("MEMORY_SCOPE_DENIED"),
  );
});

test("memory_scope_test: explicit USER cross-workspace retrieval requires all L01 gates", () => {
  const policy = makePolicy({ cross_workspace_retrieval: "EXPLICIT_ONLY" });
  const request = makeRequest({
    policy,
    consent_record: makeConsent(policy),
    requested_classes: ["USER"],
    target_workspace_id: "WS-L02-OTHER",
    cross_workspace_opt_in: true,
  });
  const execution = executeMemorySearch({ index: makeIndex(), request });
  assert.equal(execution.plan.cross_workspace, true);
  assert.deepEqual(execution.hits.map((hit) => hit.memory_id), ["MEM-L02-004"]);
});

test("memory_scope_test: cross-workspace opt-in cannot authorize a non-USER store", () => {
  const policy = makePolicy({ cross_workspace_retrieval: "ALLOW_BY_POLICY" });
  assert.throws(
    () => compileMemoryQuery(makeRequest({
      policy,
      consent_record: makeConsent(policy),
      requested_classes: ["WORKSPACE"],
      target_workspace_id: "WS-L02-OTHER",
      cross_workspace_opt_in: true,
    })),
    errorCode("MEMORY_SCOPE_DENIED"),
  );
});

test("memory_scope_test: missing, revoked, or scope-mismatched consent is denied", () => {
  assert.throws(
    () => compileMemoryQuery(makeRequest({ consent_record: null })),
    errorCode("MEMORY_SCOPE_DENIED"),
  );
  const policy = makePolicy();
  assert.throws(
    () => compileMemoryQuery(makeRequest({
      policy,
      consent_record: makeConsent(policy, {
        decision: "REVOKED",
        revoked_at: "2026-07-01T00:00:00.000Z",
      }),
    })),
    errorCode("MEMORY_SCOPE_DENIED"),
  );
  assert.throws(
    () => compileMemoryQuery(makeRequest({
      policy,
      consent_record: makeConsent(policy, { scopes: ["USER"] }),
    })),
    errorCode("MEMORY_SCOPE_DENIED"),
  );
});

test("memory_scope_test: deterministic score, cap, and tie-break are stable", () => {
  const index = makeIndex([
    memoryRecord({ memory_id: "MEM-L02-Z", search_text: "prior scope decision" }),
    memoryRecord({ memory_id: "MEM-L02-A", search_text: "prior scope decision" }),
    memoryRecord({ memory_id: "MEM-L02-M", search_text: "prior scope" }),
  ]);
  const execution = executeMemorySearch({
    index,
    request: makeRequest({ limit: 2 }),
  });
  assert.deepEqual(execution.hits.map((hit) => hit.memory_id), ["MEM-L02-A", "MEM-L02-Z"]);
  assert.deepEqual(execution.hits.map((hit) => hit.score), [1, 1]);
  assert.equal(execution.uncapped_match_count, 3);
});

test("memory_scope_test: Unicode NFKC token matching is deterministic", () => {
  const index = makeIndex([
    memoryRecord({ search_text: "ＰＲＩＯＲ scope decision" }),
  ]);
  const execution = executeMemorySearch({ index, request: makeRequest() });
  assert.equal(execution.hits[0].score, 1);
});

test("memory_scope_test: punctuation-only queries and invalid caps fail closed", () => {
  assert.throws(
    () => compileMemoryQuery(makeRequest({ query: "---" })),
    errorCode("MEMORY_QUERY_EMPTY"),
  );
  assert.throws(
    () => compileMemoryQuery(makeRequest({ limit: 201 })),
    errorCode("MEMORY_RESULT_CAP_INVALID"),
  );
});

test("memory_scope_test: request wrappers cannot use getters, Proxies, or extra fields", () => {
  const request = makeRequest();
  Object.defineProperty(request, "query", { enumerable: true, get: () => "prior" });
  assert.throws(() => compileMemoryQuery(request), errorCode("MEMORY_QUERY_REQUEST_INVALID"));
  assert.throws(
    () => executeMemorySearch(new Proxy({ index: makeIndex(), request: makeRequest() }, {})),
    errorCode("MEMORY_SEARCH_INPUT_INVALID"),
  );
  assert.throws(
    () => compileMemoryQuery({ ...makeRequest(), unbounded: true }),
    errorCode("MEMORY_QUERY_REQUEST_INVALID"),
  );
});

test("memory_scope_test: same inputs replay to byte-identical execution", () => {
  const index = makeIndex();
  const request = makeRequest({ evaluated_at: EVALUATED_AT });
  const first = executeMemorySearch({ index, request });
  const second = executeMemorySearch({ index, request });
  assert.deepEqual(second, first);
  assert.equal(second.execution_hash, first.execution_hash);
});

test("memory_scope_test: end-to-end retrieval emits no raw search text", () => {
  const result = retrievePermittedMemory({ index: makeIndex(), request: makeRequest() });
  assert.equal(result.search_execution.hits.length, 2);
  assert.equal(result.receipt.hits.length, 2);
  assert.ok(!JSON.stringify(result).includes("strawberry spacing"));
  assert.ok(Object.isFrozen(result));
});
