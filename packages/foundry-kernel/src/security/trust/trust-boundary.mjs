import { types as utilTypes } from "node:util";

/**
 * Deterministic trust-zone boundary for text entering model context.
 *
 * This module deliberately has no authority-granting API. Evidence and model
 * output can be sealed for data-only use, scanned for advisory injection
 * signals, or denied when they request an authority-bearing use. A clean scan
 * and a `trusted` extraction label never make content authoritative.
 */

export const TRUST_ZONE = Object.freeze({
  EVIDENCE_DATA: "evidence_data_plane",
  MODEL_OUTPUT: "model_output_plane",
});

export const UNTRUSTED_SOURCE_KIND = Object.freeze({
  PDF_TEXT: "pdf_text",
  SUPPLEMENTARY_FILE: "supplementary_file",
  WEB_PAGE: "web_page",
  DATASET: "dataset",
  CAPTION: "caption",
  METADATA: "metadata",
  RETRIEVED_TEXT: "retrieved_text",
  SEARCH_SNIPPET: "search_snippet",
  TOOL_OUTPUT: "tool_output",
  IMPORTED_GRAPH: "imported_graph",
  EXTERNAL_SERVICE_OUTPUT: "external_service_output",
  BENCHMARK_OUTPUT: "benchmark_output",
  MODEL_OUTPUT: "model_output",
  SUBAGENT_OUTPUT: "subagent_output",
  PRIOR_AGENT_TEXT: "prior_agent_text",
  EXTERNAL_MODEL_OUTPUT: "external_model_output",
});

export const SOURCE_TRUST_LABEL = Object.freeze({
  TRUSTED: "trusted",
  UNTRUSTED: "untrusted",
  QUARANTINED: "quarantined",
});

export const DATA_ONLY_USE = Object.freeze({
  QUOTE: "quote",
  PARSE: "parse",
  EXTRACT: "extract",
  SUMMARIZE: "summarize",
  ANALYZE: "analyze",
  CLASSIFY: "classify",
  INDEX: "index",
  CITE: "cite",
});

const SOURCE_ZONE = new Map([
  [UNTRUSTED_SOURCE_KIND.PDF_TEXT, TRUST_ZONE.EVIDENCE_DATA],
  [UNTRUSTED_SOURCE_KIND.SUPPLEMENTARY_FILE, TRUST_ZONE.EVIDENCE_DATA],
  [UNTRUSTED_SOURCE_KIND.WEB_PAGE, TRUST_ZONE.EVIDENCE_DATA],
  [UNTRUSTED_SOURCE_KIND.DATASET, TRUST_ZONE.EVIDENCE_DATA],
  [UNTRUSTED_SOURCE_KIND.CAPTION, TRUST_ZONE.EVIDENCE_DATA],
  [UNTRUSTED_SOURCE_KIND.METADATA, TRUST_ZONE.EVIDENCE_DATA],
  [UNTRUSTED_SOURCE_KIND.RETRIEVED_TEXT, TRUST_ZONE.EVIDENCE_DATA],
  [UNTRUSTED_SOURCE_KIND.SEARCH_SNIPPET, TRUST_ZONE.EVIDENCE_DATA],
  [UNTRUSTED_SOURCE_KIND.TOOL_OUTPUT, TRUST_ZONE.EVIDENCE_DATA],
  [UNTRUSTED_SOURCE_KIND.IMPORTED_GRAPH, TRUST_ZONE.EVIDENCE_DATA],
  [UNTRUSTED_SOURCE_KIND.EXTERNAL_SERVICE_OUTPUT, TRUST_ZONE.EVIDENCE_DATA],
  [UNTRUSTED_SOURCE_KIND.BENCHMARK_OUTPUT, TRUST_ZONE.EVIDENCE_DATA],
  [UNTRUSTED_SOURCE_KIND.MODEL_OUTPUT, TRUST_ZONE.MODEL_OUTPUT],
  [UNTRUSTED_SOURCE_KIND.SUBAGENT_OUTPUT, TRUST_ZONE.MODEL_OUTPUT],
  [UNTRUSTED_SOURCE_KIND.PRIOR_AGENT_TEXT, TRUST_ZONE.MODEL_OUTPUT],
  [UNTRUSTED_SOURCE_KIND.EXTERNAL_MODEL_OUTPUT, TRUST_ZONE.MODEL_OUTPUT],
]);

const SOURCE_TRUST_LABELS = new Set(Object.values(SOURCE_TRUST_LABEL));
const DATA_ONLY_USES = new Set(Object.values(DATA_ONLY_USE));
const SEALED_SEGMENTS = new WeakMap();
const EMPTY_IDS = Object.freeze([]);
const MAX_SCAN_SIGNALS = 64;

const INJECTION_SIGNAL_PATTERNS = Object.freeze([
  Object.freeze({
    signalId: "role_override",
    expression:
      "\\b(?:ignore|disregard|forget|override)\\b[\\s\\S]{0,96}\\b(?:previous|prior|above|system|developer|user|safety)\\b[\\s\\S]{0,48}\\b(?:instruction|message|prompt|policy|rule)s?\\b",
  }),
  Object.freeze({
    signalId: "role_delimiter",
    expression:
      "<\\s*\\/?\\s*(?:system|developer|assistant|tool)\\b[^>]*>|\\[\\s*(?:system|developer|assistant|tool)\\s*\\]|[\"']role[\"']\\s*:\\s*[\"'](?:system|developer|assistant|tool)[\"']",
  }),
  Object.freeze({
    signalId: "authority_claim",
    expression:
      "\\b(?:approval|authorization|permission|capability)\\b[\\s\\S]{0,48}\\b(?:granted|approved|authorized|enabled)\\b|\\b(?:you|this (?:document|message|model))\\s+(?:are|is)\\s+(?:now\\s+)?authorized\\b",
  }),
  Object.freeze({
    signalId: "tool_execution_request",
    expression:
      "\\b(?:call|invoke|run|execute|launch|use)\\b[\\s\\S]{0,48}\\b(?:tool|shell|terminal|command|function|mcp)\\b",
  }),
  Object.freeze({
    signalId: "secret_exfiltration_request",
    expression:
      "\\b(?:reveal|print|send|exfiltrate|upload|return)\\b[\\s\\S]{0,80}\\b(?:secret|api[ -]?key|token|credential|system prompt)\\b",
  }),
  Object.freeze({
    signalId: "policy_rewrite_request",
    expression:
      "\\b(?:change|replace|disable|bypass|ignore|override)\\b[\\s\\S]{0,64}\\b(?:policy|guardrail|safety|schema|permission|phase)\\b",
  }),
]);

export class TrustBoundaryError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "TrustBoundaryError";
    this.code = code;
  }
}

const fail = (code, message) => {
  throw new TrustBoundaryError(code, message);
};

const requirePlainRecord = (value, label) => {
  if (value === null || typeof value !== "object") {
    fail("INVALID_INPUT", `${label} must be a plain object`);
  }
  if (utilTypes.isProxy(value)) {
    fail("PROXY_INPUT_DENIED", `${label} must not be a Proxy`);
  }
  if (Array.isArray(value)) {
    fail("INVALID_INPUT", `${label} must be a plain object`);
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    fail("INVALID_INPUT", `${label} must not have a custom prototype`);
  }
  return value;
};

const readPlainArrayValues = (value, label) => {
  if (value === null || typeof value !== "object") {
    fail("INVALID_INPUT", `${label} must be a plain array`);
  }
  if (utilTypes.isProxy(value)) {
    fail("PROXY_INPUT_DENIED", `${label} must not be a Proxy`);
  }
  if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype) {
    fail("INVALID_INPUT", `${label} must be a plain array`);
  }

  const lengthDescriptor = Object.getOwnPropertyDescriptor(value, "length");
  const length = lengthDescriptor?.value;
  if (!Number.isSafeInteger(length) || length < 0) {
    fail("INVALID_INPUT", `${label} has an invalid length`);
  }

  for (const key of Reflect.ownKeys(value)) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(?:0|[1-9][0-9]*)$/.test(key)) {
      fail("UNEXPECTED_FIELD", `${label} contains a non-index field`);
    }
    const index = Number(key);
    if (!Number.isSafeInteger(index) || index >= length || String(index) !== key) {
      fail("UNEXPECTED_FIELD", `${label} contains an invalid index`);
    }
  }

  const values = [];
  for (let index = 0; index < length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (descriptor === undefined) {
      fail("SPARSE_ARRAY_DENIED", `${label} must not be sparse`);
    }
    if (!("value" in descriptor)) {
      fail("ACCESSOR_FIELD_DENIED", `${label}[${index}] must be a data property`);
    }
    values.push(descriptor.value);
  }
  return values;
};

const readDataProperty = (record, key, { optional = false } = {}) => {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  if (descriptor === undefined) {
    if (optional) return undefined;
    fail("MISSING_FIELD", `missing required field: ${key}`);
  }
  if (!("value" in descriptor)) {
    fail("ACCESSOR_FIELD_DENIED", `${key} must be a data property`);
  }
  return descriptor.value;
};

const rejectUnknownFields = (record, allowedFields) => {
  for (const key of Reflect.ownKeys(record)) {
    if (typeof key !== "string" || !allowedFields.has(key)) {
      fail("UNEXPECTED_FIELD", `unexpected trust-boundary field: ${String(key)}`);
    }
  }
};

const requireString = (value, label, { maxLength = 512 } = {}) => {
  if (typeof value !== "string" || value.length === 0) {
    fail("INVALID_STRING", `${label} must be a non-empty string`);
  }
  if (value.length > maxLength) {
    fail("INVALID_STRING", `${label} exceeds ${maxLength} characters`);
  }
  if (/\p{Cc}/u.test(value)) {
    fail("INVALID_STRING", `${label} must not contain control characters`);
  }
  return value;
};

const requireOptionalIdentifier = (value, label) => {
  if (value === undefined || value === null) return null;
  return requireString(value, label);
};

const getSealedRecord = (segment) => {
  if (segment === null || typeof segment !== "object") {
    fail("UNSEALED_CONTENT", "untrusted content must be a sealed segment");
  }
  const record = SEALED_SEGMENTS.get(segment);
  if (record === undefined) {
    fail(
      "UNSEALED_CONTENT",
      "untrusted content must be sealed in this runtime; copied or forged objects are denied",
    );
  }
  return record;
};

/**
 * Seal text with an immutable, runtime-private provenance brand.
 *
 * Unknown fields are rejected so role, capability, approval, or policy fields
 * cannot be smuggled beside the content. Such claims may exist only inside the
 * opaque `content` string, where they remain data.
 */
export const sealUntrustedContent = (input) => {
  const record = requirePlainRecord(input, "input");
  const allowedFields = new Set([
    "sourceId",
    "sourceKind",
    "content",
    "trustLabel",
    "injectionScanReportId",
  ]);
  rejectUnknownFields(record, allowedFields);

  const sourceId = requireString(readDataProperty(record, "sourceId"), "sourceId");
  const sourceKind = requireString(
    readDataProperty(record, "sourceKind"),
    "sourceKind",
    { maxLength: 128 },
  );
  const trustZone = SOURCE_ZONE.get(sourceKind);
  if (trustZone === undefined) {
    fail("UNKNOWN_SOURCE_KIND", `unsupported untrusted source kind: ${sourceKind}`);
  }

  const content = readDataProperty(record, "content");
  if (typeof content !== "string") {
    fail("INVALID_CONTENT", "content must be a string and is never executed or parsed as authority");
  }

  const trustLabelValue = readDataProperty(record, "trustLabel", { optional: true });
  const trustLabel = trustLabelValue ?? SOURCE_TRUST_LABEL.UNTRUSTED;
  if (!SOURCE_TRUST_LABELS.has(trustLabel)) {
    fail("INVALID_TRUST_LABEL", "unsupported source trust label");
  }

  const injectionScanReportId = requireOptionalIdentifier(
    readDataProperty(record, "injectionScanReportId", { optional: true }),
    "injectionScanReportId",
  );

  const disposition = Object.freeze({
    instructionEligible: false,
    authorityEligible: false,
    executable: false,
    canGrantCapabilities: false,
    canAlterPolicy: false,
    canChangePhase: false,
    canApprove: false,
  });
  const segment = Object.freeze({
    schemaVersion: 1,
    kind: "untrusted_content",
    trustZone,
    sourceKind,
    sourceId,
    content,
    sourceTrustLabel: trustLabel,
    injectionScanReportId,
    disposition,
  });

  SEALED_SEGMENTS.set(
    segment,
    Object.freeze({ sourceId, sourceKind, trustZone, content, trustLabel, injectionScanReportId }),
  );
  return segment;
};

export const isSealedUntrustedContent = (value) =>
  value !== null && typeof value === "object" && SEALED_SEGMENTS.has(value);

/**
 * Return advisory prompt-injection signals without changing trust status.
 * Absence of a signal is not evidence of safety or authority.
 */
export const scanInstructionLikeContent = (segment) => {
  const record = getSealedRecord(segment);
  const normalizedContent = record.content.normalize("NFKC");
  const signals = [];
  let truncated = false;

  for (const pattern of INJECTION_SIGNAL_PATTERNS) {
    const expression = new RegExp(pattern.expression, "giu");
    for (const match of normalizedContent.matchAll(expression)) {
      if (signals.length === MAX_SCAN_SIGNALS) {
        truncated = true;
        break;
      }
      signals.push(
        Object.freeze({
          signalId: pattern.signalId,
          start: match.index,
          end: match.index + match[0].length,
        }),
      );
    }
    if (truncated) break;
  }

  return Object.freeze({
    schemaVersion: 1,
    kind: "prompt_injection_scan",
    sourceId: record.sourceId,
    trustZone: record.trustZone,
    status: signals.length > 0 ? "SUSPECTED" : "NO_SIGNAL",
    coordinateSpace: "NFKC",
    signals: Object.freeze(signals),
    truncated,
    resultingDisposition: "UNTRUSTED_DATA_ONLY",
    authorityEligible: false,
  });
};

/**
 * Validate a requested use. The allowlist contains data transforms only; all
 * unknown and authority-bearing uses fail closed.
 */
export const assertDataOnlyUse = (segment, requestedUse) => {
  const record = getSealedRecord(segment);
  const use = requireString(requestedUse, "requestedUse", { maxLength: 128 });
  if (!DATA_ONLY_USES.has(use)) {
    fail(
      "UNTRUSTED_USE_DENIED",
      `${record.trustZone} content cannot be used as ${use}; only data-only transforms are permitted`,
    );
  }
  return Object.freeze({
    decision: "DATA_USE_ONLY",
    requestedUse: use,
    sourceId: record.sourceId,
    trustZone: record.trustZone,
    authorityEligible: false,
    executable: false,
  });
};

/**
 * Produce a typed denial for an authority request originating from evidence or
 * model output. The content is intentionally not inspected: persuasive prose,
 * JSON-shaped approvals, and a clean scan all receive the same denial.
 */
export const denyUntrustedAuthorityRequest = (segment, requestType, subjectId = null) => {
  const record = getSealedRecord(segment);
  const normalizedRequestType = requireString(requestType, "requestType", { maxLength: 128 });
  const normalizedSubjectId = requireOptionalIdentifier(subjectId, "subjectId");

  return Object.freeze({
    decision: "DENY",
    reasonCode: "UNTRUSTED_ORIGIN",
    requestType: normalizedRequestType,
    subjectId: normalizedSubjectId,
    sourceId: record.sourceId,
    trustZone: record.trustZone,
    capabilityGrantIds: EMPTY_IDS,
    approvalRecordIds: EMPTY_IDS,
    policyDecisionIds: EMPTY_IDS,
    phaseTransitionIds: EMPTY_IDS,
    instructionIds: EMPTY_IDS,
  });
};

/**
 * Assemble only the untrusted side of a provider context. It intentionally has
 * no instruction/messages field and accepts only runtime-branded segments.
 */
export const assembleDataOnlyContext = (segments) => {
  const segmentValues = readPlainArrayValues(segments, "segments");

  const sealedSegments = [];
  const evidenceDataSourceIds = [];
  const modelOutputSourceIds = [];
  for (const segment of segmentValues) {
    const record = getSealedRecord(segment);
    sealedSegments.push(segment);
    if (record.trustZone === TRUST_ZONE.EVIDENCE_DATA) {
      evidenceDataSourceIds.push(record.sourceId);
    } else {
      modelOutputSourceIds.push(record.sourceId);
    }
  }

  return Object.freeze({
    schemaVersion: 1,
    kind: "data_only_context",
    boundaryPolicy: "UNTRUSTED_CONTENT_NEVER_INSTRUCTION",
    dataSegments: Object.freeze(sealedSegments),
    evidenceDataSourceIds: Object.freeze(evidenceDataSourceIds),
    modelOutputSourceIds: Object.freeze(modelOutputSourceIds),
    authorityEligible: false,
    executable: false,
  });
};
