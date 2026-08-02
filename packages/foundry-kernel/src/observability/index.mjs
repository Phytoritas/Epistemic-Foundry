/**
 * Observability, SLOs and privacy-safe telemetry (Y02).
 *
 * Public surface for the observability subsystem:
 *  - OpenTelemetry-style spans and W3C trace context, correlated to effect
 *    receipts by id and hash (`otel-trace.mjs`);
 *  - privacy-safe log/telemetry redaction that fails closed (`log-redaction.mjs`);
 *  - honest result states that never fabricate a healthy metric
 *    (`result-state.mjs`).
 */

export {
  SPAN_KINDS,
  SPAN_STATUS_CODES,
  emitSpan,
  startChildSpan,
  correlateReceipt,
  parseTraceparent,
} from "./otel-trace.mjs";
export {
  REDACTION_PLACEHOLDER,
  redactRecord,
  assertNoResidualSecrets,
} from "./log-redaction.mjs";
export { ResultState, isResultState, evaluateSlo } from "./result-state.mjs";
export { ObservabilityError } from "./observability-primitives.mjs";
