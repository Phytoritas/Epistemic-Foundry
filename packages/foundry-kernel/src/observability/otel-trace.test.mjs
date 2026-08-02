import assert from "node:assert/strict";
import test from "node:test";

import {
  ObservabilityError,
  ResultState,
  correlateReceipt,
  emitSpan,
  evaluateSlo,
  parseTraceparent,
  startChildSpan,
} from "./index.mjs";

const TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736";
const SPAN_ID = "00f067aa0ba902b7";
const PARENT_ID = "b7ad6b7169203331";
const RECEIPT_HASH = `sha256:${"a".repeat(64)}`;

const errorCode = (code) => (error) =>
  error instanceof ObservabilityError && error.code === code;

const baseSpan = (overrides = {}) => ({
  trace_id: TRACE_ID,
  span_id: SPAN_ID,
  name: "forge.evaluate",
  start_unix_nano: 1_000,
  end_unix_nano: 2_500,
  ...overrides,
});

test("otel_trace_test: a span is well-formed with W3C trace context and a traceparent", () => {
  const span = emitSpan(baseSpan({ kind: "SERVER" }));
  assert.match(span.trace_id, /^[0-9a-f]{32}$/u);
  assert.match(span.span_id, /^[0-9a-f]{16}$/u);
  assert.equal(span.parent_span_id, null);
  assert.equal(span.kind, "SERVER");
  assert.equal(span.duration_unix_nano, 1_500);
  assert.equal(span.status.code, "UNSET");
  assert.equal(span.traceparent, `00-${TRACE_ID}-${SPAN_ID}-01`);
  assert.match(span.span_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.ok(Object.isFrozen(span));
  const parsed = parseTraceparent(span.traceparent);
  assert.deepEqual(parsed, { version: "00", trace_id: TRACE_ID, span_id: SPAN_ID, sampled: true });
});

test("otel_trace_test: an unsampled span sets the not-sampled trace flag", () => {
  const span = emitSpan(baseSpan({ sampled: false }));
  assert.equal(span.traceparent, `00-${TRACE_ID}-${SPAN_ID}-00`);
  assert.equal(parseTraceparent(span.traceparent).sampled, false);
});

test("otel_trace_test: malformed trace/span identifiers fail closed", () => {
  assert.throws(() => emitSpan(baseSpan({ trace_id: "0".repeat(32) })), errorCode("SPAN_INVALID"));
  assert.throws(() => emitSpan(baseSpan({ span_id: "0".repeat(16) })), errorCode("SPAN_INVALID"));
  assert.throws(() => emitSpan(baseSpan({ trace_id: "XYZ" })), errorCode("SPAN_INVALID"));
  assert.throws(() => emitSpan(baseSpan({ span_id: TRACE_ID })), errorCode("SPAN_INVALID"));
});

test("otel_trace_test: end time may not precede start time", () => {
  assert.throws(
    () => emitSpan(baseSpan({ start_unix_nano: 5_000, end_unix_nano: 4_000 })),
    errorCode("SPAN_INVALID"),
  );
});

test("otel_trace_test: a span cannot be its own parent and rejects unknown fields", () => {
  assert.throws(() => emitSpan(baseSpan({ parent_span_id: SPAN_ID })), errorCode("SPAN_INVALID"));
  assert.throws(() => emitSpan(baseSpan({ extra: true })), errorCode("SPAN_INVALID"));
});

test("otel_trace_test: a child span inherits the trace and links to its parent", () => {
  const parent = emitSpan(baseSpan());
  const child = startChildSpan(parent, {
    span_id: PARENT_ID,
    name: "forge.evaluate.child",
    start_unix_nano: 1_200,
    end_unix_nano: 1_800,
  });
  assert.equal(child.trace_id, parent.trace_id);
  assert.equal(child.parent_span_id, parent.span_id);
  assert.throws(
    () => startChildSpan(parent, { span_id: PARENT_ID, trace_id: "0".repeat(31) + "1", name: "x", start_unix_nano: 1, end_unix_nano: 2 }),
    errorCode("SPAN_INVALID"),
  );
});

test("otel_trace_test: secret and PII attributes are redacted before storage", () => {
  const span = emitSpan(
    baseSpan({
      attributes: {
        api_key: "sk-should-not-appear",
        note: "ping ops@example.com now",
        password: "hunter2",
      },
    }),
  );
  const serialized = JSON.stringify(span);
  assert.ok(!serialized.includes("hunter2"));
  assert.ok(!serialized.includes("sk-should-not-appear"));
  assert.ok(!serialized.includes("ops@example.com"));
  assert.equal(span.attributes.api_key, "[REDACTED]");
  assert.equal(span.attributes.password, "[REDACTED]");
  assert.equal(span.attributes.note, "ping [REDACTED] now");
  assert.ok(span.redaction_count >= 3);
});

test("otel_trace_test: span status cannot dishonestly claim OK over an exception", () => {
  assert.throws(
    () =>
      emitSpan(
        baseSpan({
          status: { code: "OK" },
          events: [{ name: "exception", time_unix_nano: 1_400 }],
        }),
      ),
    errorCode("DISHONEST_SPAN_STATUS"),
  );
  const honest = emitSpan(
    baseSpan({
      status: { code: "ERROR", message: "evaluator timeout" },
      events: [{ name: "exception", time_unix_nano: 1_400, attributes: { detail: "timeout" } }],
    }),
  );
  assert.equal(honest.status.code, "ERROR");
  assert.equal(honest.events[0].name, "exception");
});

test("otel_trace_test: an ERROR span without cause or message is refused", () => {
  assert.throws(() => emitSpan(baseSpan({ status: { code: "ERROR" } })), errorCode("DISHONEST_SPAN_STATUS"));
});

test("otel_trace_test: a span correlates to an effect receipt by id and hash", () => {
  const span = emitSpan(
    baseSpan({ receipt_ref: { receipt_id: "EFF-Y02-1", receipt_hash: RECEIPT_HASH } }),
  );
  const correlation = correlateReceipt(span, {
    receipt_id: "EFF-Y02-1",
    receipt_hash: RECEIPT_HASH,
  });
  assert.deepEqual(correlation, {
    trace_id: TRACE_ID,
    span_id: SPAN_ID,
    receipt_id: "EFF-Y02-1",
    receipt_hash: RECEIPT_HASH,
  });
  assert.ok(Object.isFrozen(correlation));
});

test("otel_trace_test: receipt correlation fails closed on mismatch or absence", () => {
  const withRef = emitSpan(
    baseSpan({ receipt_ref: { receipt_id: "EFF-Y02-1", receipt_hash: RECEIPT_HASH } }),
  );
  assert.throws(
    () => correlateReceipt(withRef, { receipt_id: "EFF-OTHER", receipt_hash: RECEIPT_HASH }),
    errorCode("RECEIPT_CORRELATION_MISMATCH"),
  );
  assert.throws(
    () => correlateReceipt(withRef, { receipt_id: "EFF-Y02-1", receipt_hash: `sha256:${"b".repeat(64)}` }),
    errorCode("RECEIPT_CORRELATION_MISMATCH"),
  );
  const noRef = emitSpan(baseSpan());
  assert.throws(
    () => correlateReceipt(noRef, { receipt_id: "EFF-Y02-1", receipt_hash: RECEIPT_HASH }),
    errorCode("RECEIPT_CORRELATION_MISSING"),
  );
});

test("otel_trace_test: an SLO with no samples reports UNKNOWN, never fabricated health", () => {
  const empty = evaluateSlo({ sample_count: 0, good_count: 0, objective: 0.99 });
  assert.equal(empty.state, ResultState.UNKNOWN);
  assert.equal(empty.observed_ratio, null);
});

test("otel_trace_test: honest SLO states track real measurements", () => {
  assert.equal(evaluateSlo({ sample_count: 100, good_count: 100, objective: 0.99 }).state, ResultState.OK);
  assert.equal(evaluateSlo({ sample_count: 100, good_count: 50, objective: 0.99 }).state, ResultState.DEGRADED);
  assert.equal(evaluateSlo({ sample_count: 100, good_count: 0, objective: 0.99 }).state, ResultState.UNAVAILABLE);
  assert.throws(
    () => evaluateSlo({ sample_count: 1, good_count: 2, objective: 0.99 }),
    errorCode("SLO_INPUT_INVALID"),
  );
});
