/**
 * OpenTelemetry-style trace and span emission (Y02).
 *
 * A span here is well-formed by construction: a 16-byte trace id, an 8-byte
 * span id, an optional parent span id sharing the trace, a monotonic
 * start/end time in Unix nanoseconds, a canonical span kind and status, and a
 * W3C `traceparent` string. Attributes are redacted through
 * `log-redaction.mjs` before they are stored, so a span can never carry a
 * secret or PII into the trace pipeline.
 *
 * Two honesty rules are enforced:
 *   - Status truthfulness: a span that recorded an `exception` event cannot
 *     also claim status `OK`, and a span claiming `ERROR` must show a cause.
 *   - Receipt correlation: a span may reference exactly one effect receipt by
 *     id and hash, and `correlateReceipt` refuses any mismatch — so a trace id
 *     is tied to real, hashed evidence (exit criterion: trace IDs and receipts
 *     correlated).
 */

import {
  assertNoResidualSecrets,
  redactRecord,
} from "./log-redaction.mjs";
import {
  cloneCanonical,
  deepFreeze,
  fail,
  requireEnum,
  requireHash,
  requireNullableSpanId,
  requirePlainRecord,
  requireSafeInteger,
  requireString,
  requireTraceId,
  requireSpanId,
  sha256ObservabilityJson,
} from "./observability-primitives.mjs";

/** OpenTelemetry span kinds. */
export const SPAN_KINDS = new Set(["INTERNAL", "SERVER", "CLIENT", "PRODUCER", "CONSUMER"]);

/** OpenTelemetry status codes. */
export const SPAN_STATUS_CODES = new Set(["UNSET", "OK", "ERROR"]);

const TRACE_FLAG_SAMPLED = "01";
const TRACE_FLAG_NOT_SAMPLED = "00";
const TRACEPARENT_VERSION = "00";
const EXCEPTION_EVENT_NAME = "exception";

const requireStatus = (value) => {
  const status = requirePlainRecord(value, "status", {
    allowedKeys: ["code", "message"],
    requiredKeys: ["code"],
    code: "SPAN_STATUS_INVALID",
  });
  const code = requireEnum(status.code, SPAN_STATUS_CODES, "status.code", "SPAN_STATUS_INVALID");
  const message =
    status.message === undefined
      ? null
      : requireString(status.message, "status.message", { code: "SPAN_STATUS_INVALID" });
  return { code, message };
};

const requireEvents = (value) => {
  if (value === undefined) return [];
  if (!Array.isArray(value)) fail("SPAN_EVENTS_INVALID", "events must be an array");
  return value.map((raw, index) => {
    const event = requirePlainRecord(raw, `events[${index}]`, {
      allowedKeys: ["name", "time_unix_nano", "attributes"],
      requiredKeys: ["name", "time_unix_nano"],
      code: "SPAN_EVENTS_INVALID",
    });
    return {
      name: requireString(event.name, `events[${index}].name`, { code: "SPAN_EVENTS_INVALID" }),
      time_unix_nano: requireSafeInteger(event.time_unix_nano, `events[${index}].time_unix_nano`, {
        code: "SPAN_EVENTS_INVALID",
      }),
      attributes: event.attributes === undefined ? {} : event.attributes,
    };
  });
};

const requireReceiptRef = (value) => {
  if (value === undefined || value === null) return null;
  const ref = requirePlainRecord(value, "receipt_ref", {
    allowedKeys: ["receipt_id", "receipt_hash"],
    requiredKeys: ["receipt_id", "receipt_hash"],
    code: "SPAN_RECEIPT_INVALID",
  });
  return {
    receipt_id: requireString(ref.receipt_id, "receipt_ref.receipt_id", {
      code: "SPAN_RECEIPT_INVALID",
    }),
    receipt_hash: requireHash(ref.receipt_hash, "receipt_ref.receipt_hash", "SPAN_RECEIPT_INVALID"),
  };
};

/**
 * Build a well-formed, privacy-safe span.
 *
 * Attributes (span-level and per-event) are redacted before storage; the stored
 * span is re-scanned so no secret or PII can survive. Status is checked for
 * honesty against the recorded events.
 */
export const emitSpan = (input) => {
  const span = requirePlainRecord(input, "span", {
    allowedKeys: [
      "trace_id",
      "span_id",
      "parent_span_id",
      "name",
      "kind",
      "start_unix_nano",
      "end_unix_nano",
      "sampled",
      "attributes",
      "status",
      "events",
      "receipt_ref",
    ],
    requiredKeys: ["trace_id", "span_id", "name", "start_unix_nano", "end_unix_nano"],
    code: "SPAN_INVALID",
  });

  const traceId = requireTraceId(span.trace_id, "trace_id", "SPAN_INVALID");
  const spanId = requireSpanId(span.span_id, "span_id", "SPAN_INVALID");
  const parentSpanId = requireNullableSpanId(
    span.parent_span_id === undefined ? null : span.parent_span_id,
    "parent_span_id",
    "SPAN_INVALID",
  );
  if (parentSpanId === spanId) {
    fail("SPAN_INVALID", "a span cannot be its own parent", { span_id: spanId });
  }
  const name = requireString(span.name, "name", { code: "SPAN_INVALID" });
  const kind = span.kind === undefined ? "INTERNAL" : requireEnum(span.kind, SPAN_KINDS, "kind", "SPAN_INVALID");
  const startNano = requireSafeInteger(span.start_unix_nano, "start_unix_nano", { code: "SPAN_INVALID" });
  const endNano = requireSafeInteger(span.end_unix_nano, "end_unix_nano", { code: "SPAN_INVALID" });
  if (endNano < startNano) {
    fail("SPAN_INVALID", "end_unix_nano must not precede start_unix_nano", {
      start_unix_nano: startNano,
      end_unix_nano: endNano,
    });
  }
  const sampled = span.sampled === undefined ? true : span.sampled;
  if (typeof sampled !== "boolean") fail("SPAN_INVALID", "sampled must be a boolean");

  const status = span.status === undefined ? { code: "UNSET", message: null } : requireStatus(span.status);
  const events = requireEvents(span.events);

  // Honesty: a recorded exception forbids an OK claim and demands a cause.
  const hasException = events.some((event) => event.name === EXCEPTION_EVENT_NAME);
  if (hasException && status.code === "OK") {
    fail("DISHONEST_SPAN_STATUS", "a span with an exception event cannot report status OK", {
      span_id: spanId,
    });
  }
  if (status.code === "ERROR" && !hasException && status.message === null) {
    fail("DISHONEST_SPAN_STATUS", "an ERROR span must record an exception event or a status message", {
      span_id: spanId,
    });
  }

  // Privacy: redact span and event attributes, then prove nothing leaked.
  const rawAttributes = span.attributes === undefined ? {} : span.attributes;
  const attributeRedaction = redactRecord(rawAttributes);
  const redactedAttributes = attributeRedaction.redacted;
  assertNoResidualSecrets(redactedAttributes, "span.attributes");

  const redactedEvents = events.map((event) => {
    const eventRedaction = redactRecord(event.attributes);
    assertNoResidualSecrets(eventRedaction.redacted, "event.attributes");
    return {
      name: event.name,
      time_unix_nano: event.time_unix_nano,
      attributes: eventRedaction.redacted,
    };
  });

  const receiptRef = requireReceiptRef(span.receipt_ref);

  const result = {
    trace_id: traceId,
    span_id: spanId,
    parent_span_id: parentSpanId,
    name,
    kind,
    start_unix_nano: startNano,
    end_unix_nano: endNano,
    duration_unix_nano: endNano - startNano,
    sampled,
    status,
    attributes: redactedAttributes,
    events: redactedEvents,
    receipt_ref: receiptRef,
    redaction_count: attributeRedaction.redaction_count,
    traceparent: `${TRACEPARENT_VERSION}-${traceId}-${spanId}-${
      sampled ? TRACE_FLAG_SAMPLED : TRACE_FLAG_NOT_SAMPLED
    }`,
  };
  result.span_hash = sha256ObservabilityJson(result);
  return deepFreeze(result);
};

/**
 * Derive a child span sharing the parent's trace id and linking to it, without
 * mutating the parent. `overrides` supplies the child-specific fields
 * (`span_id`, `name`, timing, ...).
 */
export const startChildSpan = (parent, overrides) => {
  const parentSpan = requirePlainRecord(parent, "parent span", { code: "SPAN_INVALID" });
  const child = requirePlainRecord(overrides, "child overrides", { code: "SPAN_INVALID" });
  if (Object.hasOwn(child, "trace_id") && child.trace_id !== parentSpan.trace_id) {
    fail("SPAN_INVALID", "a child span cannot change the trace id", {
      parent_trace_id: parentSpan.trace_id,
    });
  }
  return emitSpan({
    ...cloneCanonical(child),
    trace_id: parentSpan.trace_id,
    parent_span_id: parentSpan.span_id,
  });
};

/**
 * Correlate a span with an effect receipt, tying a trace id to hashed evidence.
 *
 * The span must carry a `receipt_ref` whose id and hash exactly match the
 * supplied receipt; any mismatch, or a span without a receipt reference, fails
 * closed. Returns a frozen correlation record.
 */
export const correlateReceipt = (span, receipt) => {
  const spanRecord = requirePlainRecord(span, "span", { code: "RECEIPT_CORRELATION_INVALID" });
  const ref = spanRecord.receipt_ref;
  if (ref === null || ref === undefined) {
    fail("RECEIPT_CORRELATION_MISSING", "span does not reference an effect receipt", {
      span_id: spanRecord.span_id,
    });
  }
  const receiptRecord = requirePlainRecord(receipt, "receipt", {
    allowedKeys: ["receipt_id", "receipt_hash"],
    requiredKeys: ["receipt_id", "receipt_hash"],
    code: "RECEIPT_CORRELATION_INVALID",
  });
  const receiptId = requireString(receiptRecord.receipt_id, "receipt.receipt_id", {
    code: "RECEIPT_CORRELATION_INVALID",
  });
  const receiptHash = requireHash(receiptRecord.receipt_hash, "receipt.receipt_hash", "RECEIPT_CORRELATION_INVALID");
  if (ref.receipt_id !== receiptId) {
    fail("RECEIPT_CORRELATION_MISMATCH", "receipt id does not match the span reference", {
      span_receipt_id: ref.receipt_id,
      receipt_id: receiptId,
    });
  }
  if (ref.receipt_hash !== receiptHash) {
    fail("RECEIPT_CORRELATION_MISMATCH", "receipt hash does not match the span reference", {
      span_id: spanRecord.span_id,
    });
  }
  return deepFreeze({
    trace_id: requireTraceId(spanRecord.trace_id, "span.trace_id", "RECEIPT_CORRELATION_INVALID"),
    span_id: requireSpanId(spanRecord.span_id, "span.span_id", "RECEIPT_CORRELATION_INVALID"),
    receipt_id: receiptId,
    receipt_hash: receiptHash,
  });
};

/** Parse and validate a W3C `traceparent`, returning its components. */
export const parseTraceparent = (value) => {
  const text = requireString(value, "traceparent", { code: "TRACEPARENT_INVALID" });
  const parts = text.split("-");
  if (parts.length !== 4) fail("TRACEPARENT_INVALID", "traceparent must have four fields");
  const [version, traceId, spanId, flags] = parts;
  if (version !== TRACEPARENT_VERSION) fail("TRACEPARENT_INVALID", "unsupported traceparent version");
  if (![TRACE_FLAG_SAMPLED, TRACE_FLAG_NOT_SAMPLED].includes(flags)) {
    fail("TRACEPARENT_INVALID", "unsupported trace flags", { flags });
  }
  return deepFreeze({
    version,
    trace_id: requireTraceId(traceId, "traceparent.trace_id", "TRACEPARENT_INVALID"),
    span_id: requireSpanId(spanId, "traceparent.span_id", "TRACEPARENT_INVALID"),
    sampled: flags === TRACE_FLAG_SAMPLED,
  });
};
