import assert from "node:assert/strict";
import test from "node:test";

import {
  MemoryIndexError,
  emitMemoryRetrievalReceipt,
  executeMemorySearch,
  retrievePermittedMemory,
  validateMemoryRetrievalReceipt,
} from "./index.mjs";
import {
  EVALUATED_AT,
  HASH_A,
  makeIndex,
  makeRequest,
  memoryRecord,
} from "./memory-index-test-support.mjs";


const errorCode = (code) => (error) =>
  error instanceof MemoryIndexError && error.code === code;

const execution = (requestOverrides = {}, records = undefined) =>
  executeMemorySearch({
    index: records === undefined ? makeIndex() : makeIndex(records),
    request: makeRequest(requestOverrides),
  });

const receipt = (searchExecution = execution(), overrides = {}) =>
  emitMemoryRetrievalReceipt({
    search_execution: searchExecution,
    selected_hits: searchExecution.hits,
    redaction_count: 0,
    retrieved_at: searchExecution.plan.evaluated_at,
    ...overrides,
  });

test("retrieval_receipt_test: receipt has the exact canonical fields and a valid seal", () => {
  const value = receipt();
  assert.deepEqual(Object.keys(value), [
    "consent_id",
    "context_capsule_id",
    "excluded_classes",
    "hits",
    "purpose",
    "query",
    "receipt_id",
    "redaction_count",
    "result_hash",
    "retrieved_at",
    "searched_classes",
    "workspace_id",
  ]);
  assert.match(value.receipt_id, /^MRR-[0-9a-f]{64}$/u);
  assert.match(value.result_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.deepEqual(validateMemoryRetrievalReceipt(value), value);
  assert.ok(Object.isFrozen(value));
});

test("retrieval_receipt_test: zero hits are SEARCHED_NONE, not unsearched", () => {
  const searched = execution({ query: "no matching phrase" });
  assert.equal(searched.status, "SEARCHED_NONE");
  assert.deepEqual(searched.hits, []);
  const value = receipt(searched);
  assert.deepEqual(value.hits, []);
  assert.deepEqual(value.searched_classes, ["WORKSPACE"]);
  assert.equal(value.query, "no matching phrase");
  assert.deepEqual(validateMemoryRetrievalReceipt(value), value);
});

test("retrieval_receipt_test: searched and excluded classes form a complete partition", () => {
  const value = receipt(execution({ requested_classes: ["SESSION", "WORKSPACE"] }));
  assert.deepEqual(value.searched_classes, ["SESSION", "WORKSPACE"]);
  assert.deepEqual(value.excluded_classes, ["EPHEMERAL", "USER", "EVIDENCE", "REGULATED"]);
  assert.equal(new Set([...value.searched_classes, ...value.excluded_classes]).size, 6);
});

test("retrieval_receipt_test: hit provenance is retained without raw memory text", () => {
  const value = receipt();
  assert.deepEqual(Object.keys(value.hits[0]), [
    "class",
    "memory_id",
    "redacted",
    "score",
    "source_hash",
  ]);
  assert.match(value.hits[0].source_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(Object.hasOwn(value.hits[0], "search_text"), false);
});

test("retrieval_receipt_test: same execution replays to the same ID, hash, and timestamp", () => {
  const searched = execution();
  const first = receipt(searched);
  const second = receipt(searched);
  assert.deepEqual(second, first);
  assert.equal(second.receipt_id, first.receipt_id);
  assert.equal(second.result_hash, first.result_hash);
  assert.equal(second.retrieved_at, first.retrieved_at);
});

test("retrieval_receipt_test: query mutation is an integrity failure", () => {
  const tampered = structuredClone(receipt());
  tampered.query = "different query";
  assert.throws(
    () => validateMemoryRetrievalReceipt(tampered),
    errorCode("MEMORY_RETRIEVAL_RECEIPT_ID_MISMATCH"),
  );
});

test("retrieval_receipt_test: result hash and receipt ID tamper fail closed", () => {
  const hashTamper = structuredClone(receipt());
  hashTamper.result_hash = HASH_A;
  assert.throws(
    () => validateMemoryRetrievalReceipt(hashTamper),
    errorCode("MEMORY_RETRIEVAL_RECEIPT_HASH_MISMATCH"),
  );
  const idTamper = structuredClone(receipt());
  idTamper.receipt_id = `MRR-${"f".repeat(64)}`;
  assert.throws(
    () => validateMemoryRetrievalReceipt(idTamper),
    errorCode("MEMORY_RETRIEVAL_RECEIPT_ID_MISMATCH"),
  );
});

test("retrieval_receipt_test: an excluded-class hit cannot be inserted", () => {
  const tampered = structuredClone(receipt());
  tampered.hits = [{
    memory_id: "MEM-L02-REG",
    class: "REGULATED",
    score: 1,
    source_hash: HASH_A,
    redacted: false,
  }];
  assert.throws(
    () => validateMemoryRetrievalReceipt(tampered),
    errorCode("MEMORY_HIT_OUTSIDE_SCOPE"),
  );
});

test("retrieval_receipt_test: receipt emission rejects a hit not produced by search", () => {
  const searched = execution();
  const forged = [{ ...searched.hits[0], memory_id: "MEM-L02-FORGED" }];
  assert.throws(
    () => receipt(searched, { selected_hits: forged }),
    errorCode("MEMORY_RECEIPT_HIT_NOT_SEARCHED"),
  );
});

test("retrieval_receipt_test: selected hits must preserve deterministic search order", () => {
  const searched = execution();
  assert.equal(searched.hits.length, 2);
  assert.throws(
    () => receipt(searched, { selected_hits: [...searched.hits].reverse() }),
    errorCode("MEMORY_RECEIPT_HIT_ORDER_INVALID"),
  );
});

test("retrieval_receipt_test: L03 may redact or select a deterministic subset", () => {
  const searched = execution();
  const selected = [{ ...searched.hits[1], redacted: true }];
  const value = receipt(searched, { selected_hits: selected, redaction_count: 1 });
  assert.equal(value.hits.length, 1);
  assert.equal(value.hits[0].redacted, true);
  assert.equal(value.redaction_count, 1);
  assert.deepEqual(validateMemoryRetrievalReceipt(value), value);
});

test("retrieval_receipt_test: redaction count cannot under-report redacted hits", () => {
  const searched = execution();
  const selected = [{ ...searched.hits[0], redacted: true }];
  assert.throws(
    () => receipt(searched, { selected_hits: selected, redaction_count: 0 }),
    errorCode("MEMORY_RETRIEVAL_RECEIPT_INPUT_INVALID"),
  );
});

test("retrieval_receipt_test: policy evaluation time and retrieval time are one sealed boundary", () => {
  const searched = execution();
  assert.throws(
    () => receipt(searched, { retrieved_at: "2026-07-31T00:00:00.001Z" }),
    errorCode("MEMORY_RETRIEVAL_TIME_MISMATCH"),
  );
  assert.equal(receipt(searched).retrieved_at, EVALUATED_AT);
});

test("retrieval_receipt_test: consent and ContextCapsule bindings remain explicit", () => {
  const value = receipt();
  assert.equal(value.consent_id, "CONS-L02-001");
  assert.equal(value.context_capsule_id, "CC-L02-001");

  const noConsent = receipt(execution({
    requested_classes: ["SESSION"],
    consent_record: null,
    context_capsule_id: null,
  }));
  assert.equal(noConsent.consent_id, null);
  assert.equal(noConsent.context_capsule_id, null);
});

test("retrieval_receipt_test: extra fields, accessors, and Proxy wrappers fail closed", () => {
  assert.throws(
    () => validateMemoryRetrievalReceipt({ ...receipt(), hidden: true }),
    errorCode("MEMORY_RETRIEVAL_RECEIPT_INVALID"),
  );
  const accessor = structuredClone(receipt());
  Object.defineProperty(accessor, "query", { enumerable: true, get: () => "prior" });
  assert.throws(
    () => validateMemoryRetrievalReceipt(accessor),
    errorCode("MEMORY_RETRIEVAL_RECEIPT_INVALID"),
  );
  assert.throws(
    () => emitMemoryRetrievalReceipt(new Proxy({
      search_execution: execution(),
      selected_hits: [],
      redaction_count: 0,
      retrieved_at: EVALUATED_AT,
    }, {})),
    errorCode("MEMORY_RETRIEVAL_RECEIPT_INPUT_INVALID"),
  );
});

test("retrieval_receipt_test: non-canonical hit order is rejected during validation", () => {
  const tampered = structuredClone(receipt());
  tampered.hits.reverse();
  assert.throws(
    () => validateMemoryRetrievalReceipt(tampered),
    errorCode("MEMORY_HIT_ORDER_INVALID"),
  );
});

test("retrieval_receipt_test: end-to-end helper returns execution and matching receipt", () => {
  const result = retrievePermittedMemory({ index: makeIndex(), request: makeRequest() });
  assert.deepEqual(result.receipt.hits, result.search_execution.hits);
  assert.equal(result.receipt.query, result.search_execution.plan.query);
  assert.equal(result.receipt.retrieved_at, result.search_execution.plan.evaluated_at);
  assert.deepEqual(validateMemoryRetrievalReceipt(result.receipt), result.receipt);
});

test("retrieval_receipt_test: score or provenance mutation is detected", () => {
  const scoreTamper = structuredClone(receipt());
  scoreTamper.hits[0].score = 0.25;
  assert.throws(
    () => validateMemoryRetrievalReceipt(scoreTamper),
    errorCode("MEMORY_HIT_ORDER_INVALID"),
  );

  const provenanceTamper = structuredClone(receipt());
  provenanceTamper.hits[0].source_hash = HASH_A;
  if (receipt().hits[0].source_hash === HASH_A) {
    provenanceTamper.hits[0].source_hash = `sha256:${"d".repeat(64)}`;
  }
  assert.throws(
    () => validateMemoryRetrievalReceipt(provenanceTamper),
    errorCode("MEMORY_RETRIEVAL_RECEIPT_ID_MISMATCH"),
  );
});

test("retrieval_receipt_test: a record outside retention is absent and accounted as policy exclusion", () => {
  const searched = execution({}, [
    memoryRecord({ memory_id: "MEM-L02-OLD", created_at: "2025-01-01T00:00:00.000Z" }),
  ]);
  assert.deepEqual(searched.hits, []);
  assert.deepEqual(searched.policy_excluded_memory_ids, ["MEM-L02-OLD"]);
  const value = receipt(searched);
  assert.deepEqual(value.hits, []);
  assert.equal(value.query, searched.plan.query);
});
