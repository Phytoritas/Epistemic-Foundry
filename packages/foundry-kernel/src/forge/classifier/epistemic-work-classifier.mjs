import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const NUMBER_IS_FINITE = Number.isFinite;
const NUMBER_IS_SAFE_INTEGER = Number.isSafeInteger;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const OBJECT_IS = Object.is;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;

export const CLASSIFIER_VERSION = "4.0.1-f01.1";
export const CLASSIFICATION_SCHEMA_ID =
  "https://epistemic-foundry.local/schemas/epistemic-work-classification.schema.json";
export const HUMAN_DECISION_SCHEMA_ID =
  "https://epistemic-foundry.local/schemas/human-decision.schema.json";

export const CLASSIFICATION_SIGNALS = OBJECT_FREEZE([
  "TRANSFORM",
  "LOOKUP",
  "SYNTHESIS",
  "MECHANISM",
  "CAUSAL",
  "VALIDATION",
  "HIGH_STAKES",
  "EXPENSIVE",
  "NOVELTY",
  "AMBIGUOUS",
]);

export const SIGNAL_PRIORITY = OBJECT_FREEZE([
  "AMBIGUOUS",
  "NOVELTY",
  "HIGH_STAKES",
  "EXPENSIVE",
  "CAUSAL",
  "VALIDATION",
  "MECHANISM",
  "SYNTHESIS",
  "LOOKUP",
  "TRANSFORM",
]);

export const INTERVIEW_RULES = OBJECT_FREEZE([
  "I01_AMBIGUOUS_SIGNAL",
  "I02_CONFLICTING_REQUIREMENTS",
  "I03_MISSING_GOAL_OR_DECISION",
  "I04_MISSING_SCOPE",
  "I05_MISSING_FALSIFIER",
  "I06_MISSING_AUTHORITY",
  "I07_MISSING_HIGH_RISK_CONTRACT",
  "I08_MISSING_NOVELTY_BOUNDARY",
  "I09_UNBOUNDED_COST",
]);

export const WORK_CLASSES = OBJECT_FREEZE(["E0", "E1", "E2", "E3", "E4", "E5"]);

export const SIGNAL_FLOORS = OBJECT_FREEZE({
  TRANSFORM: "E0",
  LOOKUP: "E1",
  SYNTHESIS: "E2",
  MECHANISM: "E3",
  CAUSAL: "E4",
  VALIDATION: "E4",
  HIGH_STAKES: "E4",
  EXPENSIVE: "E4",
  NOVELTY: "E5",
  AMBIGUOUS: "E5",
});

export const CLASS_PROJECTIONS = OBJECT_FREEZE({
  E0: OBJECT_FREEZE({ phases: OBJECT_FREEZE([]), roleCount: 0, humanGate: false }),
  E1: OBJECT_FREEZE({
    phases: OBJECT_FREEZE(["F", "O", "E"]),
    roleCount: 1,
    humanGate: false,
  }),
  E2: OBJECT_FREEZE({
    phases: OBJECT_FREEZE(["F", "O", "R", "G", "E"]),
    roleCount: 3,
    humanGate: false,
  }),
  E3: OBJECT_FREEZE({
    phases: OBJECT_FREEZE(["F", "O", "R", "G", "E"]),
    roleCount: 6,
    humanGate: false,
  }),
  E4: OBJECT_FREEZE({
    phases: OBJECT_FREEZE(["F", "O", "R", "G", "E"]),
    roleCount: 10,
    humanGate: true,
  }),
  E5: OBJECT_FREEZE({
    phases: OBJECT_FREEZE(["F", "O", "R", "G", "E"]),
    roleCount: 12,
    humanGate: true,
  }),
});

const SIGNAL_SET = new Set(CLASSIFICATION_SIGNALS);
const INTERVIEW_RULE_SET = new Set(INTERVIEW_RULES);
const WORK_CLASS_SET = new Set(WORK_CLASSES);
const SIGNAL_PRIORITY_INDEX = new Map(
  SIGNAL_PRIORITY.map((signal, index) => [signal, index]),
);
const WORK_CLASS_INDEX = new Map(WORK_CLASSES.map((workClass, index) => [workClass, index]));
const RISK_SIGNALS = new Set([
  "MECHANISM",
  "CAUSAL",
  "VALIDATION",
  "HIGH_STAKES",
  "EXPENSIVE",
  "NOVELTY",
  "AMBIGUOUS",
]);
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const CLASSIFICATION_ID_PATTERN = /^EWC-[0-9a-f]{64}$/u;
const CLASSIFIED_AT_PATTERN =
  /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$/u;
const RFC3339_PATTERN =
  /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$/u;
const BASE_PHASES = OBJECT_FREEZE(["F", "O", "R", "G", "E"]);
const DIRECT_LLM_OUTPUT_FIELDS = new Set([
  "work_class",
  "required_phases",
  "default_role_count",
  "human_gate_required",
  "classification_id",
  "classified_at",
  "classification_hash",
]);
const PROPOSAL_FIELDS = new Set([
  "signal",
  "request_span_start",
  "request_span_end",
  "exact_excerpt",
  "confidence",
  "short_rationale",
]);
const BUSINESS_ARTIFACT_KEYS = OBJECT_FREEZE([
  "classification_id",
  "request_id",
  "work_class",
  "reasons",
  "risk_factors",
  "required_phases",
  "default_role_count",
  "human_gate_required",
  "classified_at",
  "classifier_version",
  "classification_hash",
]);
const HUMAN_DECISION_KEYS = OBJECT_FREEZE([
  "decision_id",
  "run_id",
  "subject_id",
  "decision_type",
  "decision",
  "authority_id",
  "authority_role",
  "rationale",
  "evidence_artifact_ids",
  "affected_artifact_ids",
  "supersedes_decision_id",
  "non_mutation_acknowledgement",
  "created_at",
  "decision_hash",
]);
const HUMAN_DECISION_TYPE_SET = new Set([
  "accept",
  "reject",
  "correct",
  "narrow_scope",
  "override_waivable_gate",
  "withdraw",
  "appeal",
  "release",
  "hold",
]);

export class EpistemicWorkClassifierError extends Error {
  constructor(code, message, details = undefined, options = undefined) {
    super(message, options);
    this.name = "EpistemicWorkClassifierError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(canonicalClone(details));
  }
}

const fail = (code, message, details, options) => {
  throw new EpistemicWorkClassifierError(code, message, details, options);
};

const hasOnlyUnicodeScalars = (value) => {
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      return false;
    }
  }
  return true;
};

const requireString = (value, label, { allowEmpty = false, code = "INVALID_INPUT" } = {}) => {
  if (
    typeof value !== "string" ||
    (!allowEmpty && value.length === 0) ||
    !hasOnlyUnicodeScalars(value)
  ) {
    fail(code, `${label} must be a${allowEmpty ? "" : " non-empty"} Unicode scalar string`);
  }
  return value;
};

const requireHash = (value, label, { code = "INVALID_INPUT" } = {}) => {
  const candidate = requireString(value, label, { code });
  if (!SHA256_PATTERN.test(candidate)) fail(code, `${label} must be a canonical SHA-256`);
  return candidate;
};

const requireNullableHash = (value, label) =>
  value === null ? null : requireHash(value, label);

const requirePlainDataObject = (
  value,
  label,
  { allowedKeys = undefined, requiredKeys = undefined, code = "INVALID_INPUT" } = {},
) => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    (OBJECT_GET_PROTOTYPE_OF(value) !== PLAIN_OBJECT_PROTOTYPE &&
      OBJECT_GET_PROTOTYPE_OF(value) !== null)
  ) {
    fail(code, `${label} must be a plain data object`);
  }
  const allowed = allowedKeys === undefined ? null : new Set(allowedKeys);
  const keys = REFLECT_OWN_KEYS(value);
  for (let index = 0; index < keys.length; index += 1) {
    const key = keys[index];
    if (typeof key !== "string" || (allowed !== null && !allowed.has(key))) {
      fail(code, `${label} contains an unsupported field`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail(code, `${label}.${String(key)} must be an enumerable data property`);
    }
  }
  if (requiredKeys !== undefined) {
    for (let index = 0; index < requiredKeys.length; index += 1) {
      if (!OBJECT_HAS_OWN(value, requiredKeys[index])) {
        fail(code, `${label}.${requiredKeys[index]} is required`);
      }
    }
  }
  return value;
};

const readDataProperty = (object, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(object, key).value;

const readDenseArray = (value, label, code = "INVALID_INPUT") => {
  if (!ARRAY_IS_ARRAY(value) || IS_PROXY(value)) fail(code, `${label} must be a dense array`);
  const keys = REFLECT_OWN_KEYS(value);
  for (let index = 0; index < keys.length; index += 1) {
    const key = keys[index];
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
      fail(code, `${label} contains a non-element property`);
    }
    const numeric = Number(key);
    if (!NUMBER_IS_SAFE_INTEGER(numeric) || numeric < 0 || numeric >= value.length) {
      fail(code, `${label} contains a non-canonical array index`);
    }
  }
  const result = new Array(value.length);
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail(code, `${label} must not be sparse or accessor-backed`);
    }
    result[index] = descriptor.value;
  }
  return result;
};

const requireStringArray = (value, label, code) => {
  const entries = readDenseArray(value, label, code);
  return entries.map((entry, index) =>
    requireString(entry, `${label}[${index}]`, { allowEmpty: true, code }),
  );
};

const requireClassifierVersion = (value, code = "CLASSIFIER_VERSION_MISMATCH") => {
  const candidate = requireString(value, "classifier_version", { code });
  if (candidate !== CLASSIFIER_VERSION) {
    fail(code, `classifier_version must be exactly ${CLASSIFIER_VERSION}`, {
      expected: CLASSIFIER_VERSION,
      actual: candidate,
    });
  }
  return candidate;
};

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object" || IS_PROXY(value)) return value;
  const keys = REFLECT_OWN_KEYS(value);
  for (let index = 0; index < keys.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, keys[index]);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};

const assertCanonicalJsonValue = (value, label = "value", ancestors = new WeakSet()) => {
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") {
    if (!hasOnlyUnicodeScalars(value)) fail("NON_CANONICAL_JSON", `${label} has invalid Unicode`);
    return;
  }
  if (typeof value === "number") {
    if (!NUMBER_IS_FINITE(value) || OBJECT_IS(value, -0)) {
      fail("NON_CANONICAL_JSON", `${label} has a non-canonical number`);
    }
    return;
  }
  if (typeof value !== "object" || IS_PROXY(value)) {
    fail("NON_CANONICAL_JSON", `${label} has a non-JSON value`);
  }
  if (ancestors.has(value)) fail("NON_CANONICAL_JSON", `${label} has a cycle`);
  ancestors.add(value);
  try {
    if (ARRAY_IS_ARRAY(value)) {
      const elements = readDenseArray(value, label, "NON_CANONICAL_JSON");
      for (let index = 0; index < elements.length; index += 1) {
        assertCanonicalJsonValue(elements[index], `${label}[${index}]`, ancestors);
      }
      return;
    }
    requirePlainDataObject(value, label, { code: "NON_CANONICAL_JSON" });
    const keys = Object.keys(value);
    for (let index = 0; index < keys.length; index += 1) {
      assertCanonicalJsonValue(readDataProperty(value, keys[index]), `${label}.${keys[index]}`, ancestors);
    }
  } finally {
    ancestors.delete(value);
  }
};

const canonicalClone = (value) => {
  assertCanonicalJsonValue(value);
  return JSON.parse(JSON.stringify(value));
};

export const canonicalizeClassificationJson = (value) => {
  assertCanonicalJsonValue(value);
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (ARRAY_IS_ARRAY(value)) {
    return `[${value.map((entry) => canonicalizeClassificationJson(entry)).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort()
    .map(
      (key) =>
        `${JSON.stringify(key)}:${canonicalizeClassificationJson(readDataProperty(value, key))}`,
    )
    .join(",")}}`;
};

export const sha256ClassificationJson = (value) =>
  `sha256:${createHash("sha256")
    .update(canonicalizeClassificationJson(value), "utf8")
    .digest("hex")}`;

export const validateHumanDecisionArtifact = (candidate, baseDecision = undefined) => {
  const code = "HUMAN_DECISION_ARTIFACT_INVALID";
  const value = requirePlainDataObject(candidate, "HumanDecision artifact", {
    allowedKeys: HUMAN_DECISION_KEYS,
    requiredKeys: HUMAN_DECISION_KEYS,
    code,
  });
  const decisionType = requireString(
    readDataProperty(value, "decision_type"),
    "HumanDecision.decision_type",
    { code },
  );
  if (!HUMAN_DECISION_TYPE_SET.has(decisionType)) {
    fail(code, "HumanDecision.decision_type is outside the canonical vocabulary");
  }
  const runIdValue = readDataProperty(value, "run_id");
  const supersedesValue = readDataProperty(value, "supersedes_decision_id");
  const createdAt = requireString(
    readDataProperty(value, "created_at"),
    "HumanDecision.created_at",
    { code },
  );
  if (!RFC3339_PATTERN.test(createdAt) || !NUMBER_IS_FINITE(Date.parse(createdAt))) {
    fail(code, "HumanDecision.created_at must be an RFC 3339 date-time");
  }
  if (readDataProperty(value, "non_mutation_acknowledgement") !== true) {
    fail(code, "HumanDecision must acknowledge immutable-history non-mutation");
  }
  const preimage = {
    decision_id: requireString(
      readDataProperty(value, "decision_id"),
      "HumanDecision.decision_id",
      { code },
    ),
    run_id:
      runIdValue === null
        ? null
        : requireString(runIdValue, "HumanDecision.run_id", { allowEmpty: true, code }),
    subject_id: requireString(
      readDataProperty(value, "subject_id"),
      "HumanDecision.subject_id",
      { code },
    ),
    decision_type: decisionType,
    decision: requireString(
      readDataProperty(value, "decision"),
      "HumanDecision.decision",
      { code },
    ),
    authority_id: requireString(
      readDataProperty(value, "authority_id"),
      "HumanDecision.authority_id",
      { code },
    ),
    authority_role: requireString(
      readDataProperty(value, "authority_role"),
      "HumanDecision.authority_role",
      { code },
    ),
    rationale: requireString(
      readDataProperty(value, "rationale"),
      "HumanDecision.rationale",
      { code },
    ),
    evidence_artifact_ids: requireStringArray(
      readDataProperty(value, "evidence_artifact_ids"),
      "HumanDecision.evidence_artifact_ids",
      code,
    ),
    affected_artifact_ids: requireStringArray(
      readDataProperty(value, "affected_artifact_ids"),
      "HumanDecision.affected_artifact_ids",
      code,
    ),
    supersedes_decision_id:
      supersedesValue === null
        ? null
        : requireString(supersedesValue, "HumanDecision.supersedes_decision_id", {
            allowEmpty: true,
            code,
          }),
    non_mutation_acknowledgement: true,
    created_at: createdAt,
  };
  const decisionHash = requireHash(
    readDataProperty(value, "decision_hash"),
    "HumanDecision.decision_hash",
    { code: "HUMAN_DECISION_INTEGRITY_FAILED" },
  );
  const expectedHash = sha256ClassificationJson(preimage);
  if (decisionHash !== expectedHash) {
    fail(
      "HUMAN_DECISION_INTEGRITY_FAILED",
      "HumanDecision.decision_hash does not match its canonical preimage",
      { expected: expectedHash, actual: decisionHash },
    );
  }
  const decision = deepFreeze({ ...preimage, decision_hash: decisionHash });
  if (baseDecision !== undefined) {
    if (decision.decision_type !== "correct") {
      fail(
        "HUMAN_DECISION_AUTHORITY_MISMATCH",
        "classification override requires a corrective HumanDecision",
        { expected_decision_type: "correct", actual_decision_type: decision.decision_type },
      );
    }
    if (
      decision.run_id !== baseDecision.run_id ||
      decision.subject_id !== baseDecision.classification_id ||
      !decision.affected_artifact_ids.includes(baseDecision.classification_id)
    ) {
      fail(
        "HUMAN_DECISION_SCOPE_MISMATCH",
        "HumanDecision does not bind the exact run and base classification revision",
        {
          expected_run_id: baseDecision.run_id,
          expected_subject_id: baseDecision.classification_id,
        },
      );
    }
  }
  return decision;
};

const signalSort = (left, right) =>
  SIGNAL_PRIORITY_INDEX.get(left) - SIGNAL_PRIORITY_INDEX.get(right);

const normalizeTrustedSignals = (value, label) => {
  const entries = readDenseArray(value, label);
  const signals = new Set();
  for (let index = 0; index < entries.length; index += 1) {
    const signal = requireString(entries[index], `${label}[${index}]`);
    if (!SIGNAL_SET.has(signal)) {
      fail(
        "CLASSIFIER_INPUT_VALIDATION_FAILED",
        `${label}[${index}] is outside the closed signal vocabulary`,
        { signal },
      );
    }
    signals.add(signal);
  }
  return [...signals].sort(signalSort);
};

const normalizeMissingContractFlags = (value) => {
  const entries = readDenseArray(value, "missing_contract_flags");
  const flags = new Set();
  for (let index = 0; index < entries.length; index += 1) {
    const flag = requireString(entries[index], `missing_contract_flags[${index}]`);
    if (!INTERVIEW_RULE_SET.has(flag)) {
      fail("CLASSIFIER_INPUT_VALIDATION_FAILED", "unknown Interview rule", { flag });
    }
    flags.add(flag);
  }
  return INTERVIEW_RULES.filter((flag) => flags.has(flag));
};

const proposalField = (proposal, key) => {
  const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(proposal, key);
  return descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")
    ? undefined
    : descriptor.value;
};

const inspectLlmProposal = (proposal, index, requestBytes) => {
  const rejection = (reason, ignoredFields = []) => ({
    index,
    status: "REJECTED",
    reason,
    signal: null,
    start: null,
    end: null,
    ignored_fields: ignoredFields,
  });
  if (
    proposal === null ||
    typeof proposal !== "object" ||
    ARRAY_IS_ARRAY(proposal) ||
    IS_PROXY(proposal) ||
    (OBJECT_GET_PROTOTYPE_OF(proposal) !== PLAIN_OBJECT_PROTOTYPE &&
      OBJECT_GET_PROTOTYPE_OF(proposal) !== null)
  ) {
    return rejection("MALFORMED_PROPOSAL");
  }
  const keys = REFLECT_OWN_KEYS(proposal);
  const ignoredFields = [];
  for (let keyIndex = 0; keyIndex < keys.length; keyIndex += 1) {
    const key = keys[keyIndex];
    if (typeof key !== "string") return rejection("MALFORMED_PROPOSAL");
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(proposal, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      return rejection("MALFORMED_PROPOSAL");
    }
    if (DIRECT_LLM_OUTPUT_FIELDS.has(key)) ignoredFields.push(key);
    else if (!PROPOSAL_FIELDS.has(key)) return rejection("UNSUPPORTED_PROPOSAL_FIELD");
  }
  for (const key of PROPOSAL_FIELDS) {
    if (!OBJECT_HAS_OWN(proposal, key)) return rejection("MISSING_REQUIRED_FIELD", ignoredFields);
  }

  const signal = proposalField(proposal, "signal");
  if (typeof signal !== "string" || !SIGNAL_SET.has(signal)) {
    return rejection("UNKNOWN_SIGNAL", ignoredFields);
  }
  const start = proposalField(proposal, "request_span_start");
  const end = proposalField(proposal, "request_span_end");
  if (
    !NUMBER_IS_SAFE_INTEGER(start) ||
    !NUMBER_IS_SAFE_INTEGER(end) ||
    start < 0 ||
    end <= start ||
    end > requestBytes.length
  ) {
    return rejection("INVALID_SOURCE_SPAN", ignoredFields);
  }
  const exactExcerpt = proposalField(proposal, "exact_excerpt");
  if (typeof exactExcerpt !== "string" || !hasOnlyUnicodeScalars(exactExcerpt)) {
    return rejection("INVALID_EXCERPT", ignoredFields);
  }
  const excerptBytes = Buffer.from(exactExcerpt, "utf8");
  const selectedBytes = requestBytes.subarray(start, end);
  if (
    excerptBytes.length !== selectedBytes.length ||
    !excerptBytes.equals(selectedBytes) ||
    Buffer.from(selectedBytes.toString("utf8"), "utf8").compare(selectedBytes) !== 0
  ) {
    return rejection("SOURCE_SPAN_MISMATCH", ignoredFields);
  }
  const confidence = proposalField(proposal, "confidence");
  if (typeof confidence !== "number" || !NUMBER_IS_FINITE(confidence) || confidence < 0 || confidence > 1) {
    return rejection("INVALID_CONFIDENCE", ignoredFields);
  }
  const rationale = proposalField(proposal, "short_rationale");
  if (typeof rationale !== "string" || rationale.length === 0 || !hasOnlyUnicodeScalars(rationale)) {
    return rejection("INVALID_RATIONALE", ignoredFields);
  }
  if (confidence < 0.5) return rejection("LOW_CONFIDENCE", ignoredFields);
  return {
    index,
    status: confidence < 0.75 ? "AMBIGUOUS" : "ACCEPTED",
    reason: confidence < 0.75 ? "BELOW_ACCEPTANCE_THRESHOLD" : "SUPPORTED",
    signal,
    start,
    end,
    ignored_fields: ignoredFields.sort(),
  };
};

const normalizeLlmProposals = (value, requestText) => {
  const proposals = readDenseArray(value, "llm_signal_proposals");
  const requestBytes = Buffer.from(requestText, "utf8");
  const trace = new Array(proposals.length);
  const accepted = new Set();
  let injectAmbiguous = false;
  const acceptedBySpan = new Map();

  for (let index = 0; index < proposals.length; index += 1) {
    const result = inspectLlmProposal(proposals[index], index, requestBytes);
    trace[index] = result;
    if (result.status === "AMBIGUOUS") injectAmbiguous = true;
    if (result.status !== "ACCEPTED") continue;
    accepted.add(result.signal);
    const spanKey = `${result.start}:${result.end}`;
    const spanSignals = acceptedBySpan.get(spanKey) ?? new Set();
    spanSignals.add(result.signal);
    acceptedBySpan.set(spanKey, spanSignals);
  }
  for (const spanSignals of acceptedBySpan.values()) {
    if (spanSignals.size > 1) injectAmbiguous = true;
  }
  return {
    accepted: [...accepted].sort(signalSort),
    injectAmbiguous,
    trace,
  };
};

const normalizeClassificationInput = (candidate) => {
  const input = requirePlainDataObject(candidate, "classification input", {
    allowedKeys: [
      "run_id",
      "request_id",
      "request_text",
      "request_input_hash",
      "classifier_version",
      "policy_bundle_hash",
      "policy_bundle_signals",
      "typed_request_metadata",
      "deterministic_detector_signals",
      "llm_signal_proposals",
      "missing_contract_flags",
    ],
    requiredKeys: [
      "run_id",
      "request_id",
      "request_text",
      "request_input_hash",
      "policy_bundle_hash",
      "policy_bundle_signals",
      "typed_request_metadata",
      "deterministic_detector_signals",
      "llm_signal_proposals",
      "missing_contract_flags",
    ],
  });
  const requestText = requireString(readDataProperty(input, "request_text"), "request_text", {
    allowEmpty: true,
  });
  const typedMetadata = requirePlainDataObject(
    readDataProperty(input, "typed_request_metadata"),
    "typed_request_metadata",
    { allowedKeys: ["signals"], requiredKeys: ["signals"] },
  );
  const classifierVersion = OBJECT_HAS_OWN(input, "classifier_version")
    ? requireClassifierVersion(readDataProperty(input, "classifier_version"))
    : CLASSIFIER_VERSION;
  const requestInputHash = requireHash(
    readDataProperty(input, "request_input_hash"),
    "request_input_hash",
  );
  const expectedRequestInputHash = classificationInputHash(requestText);
  if (requestInputHash !== expectedRequestInputHash) {
    fail(
      "REQUEST_INPUT_HASH_MISMATCH",
      "request_input_hash does not cryptographically bind request_text",
      { expected: expectedRequestInputHash, actual: requestInputHash },
    );
  }
  return deepFreeze({
    run_id: requireString(readDataProperty(input, "run_id"), "run_id"),
    request_id: requireString(readDataProperty(input, "request_id"), "request_id"),
    request_text: requestText,
    request_input_hash: requestInputHash,
    classifier_version: classifierVersion,
    policy_bundle_hash: requireHash(
      readDataProperty(input, "policy_bundle_hash"),
      "policy_bundle_hash",
    ),
    policy_bundle_signals: normalizeTrustedSignals(
      readDataProperty(input, "policy_bundle_signals"),
      "policy_bundle_signals",
    ),
    request_signals: normalizeTrustedSignals(
      readDataProperty(typedMetadata, "signals"),
      "typed_request_metadata.signals",
    ),
    detector_signals: normalizeTrustedSignals(
      readDataProperty(input, "deterministic_detector_signals"),
      "deterministic_detector_signals",
    ),
    llm: normalizeLlmProposals(readDataProperty(input, "llm_signal_proposals"), requestText),
    missing_contract_flags: normalizeMissingContractFlags(
      readDataProperty(input, "missing_contract_flags"),
    ),
  });
};

const normalizePriorClassification = (candidate, requestId) => {
  if (candidate === undefined || candidate === null) return null;
  const prior = requirePlainDataObject(candidate, "prior classification context", {
    allowedKeys: ["request_id", "accepted_signals"],
    requiredKeys: ["request_id", "accepted_signals"],
  });
  const priorRequestId = requireString(readDataProperty(prior, "request_id"), "prior.request_id");
  if (priorRequestId !== requestId) return null;
  return {
    request_id: priorRequestId,
    accepted_signals: normalizeTrustedSignals(
      readDataProperty(prior, "accepted_signals"),
      "prior.accepted_signals",
    ),
  };
};

const maximumFloor = (signals) => {
  let maximum = 0;
  for (let index = 0; index < signals.length; index += 1) {
    maximum = Math.max(maximum, WORK_CLASS_INDEX.get(SIGNAL_FLOORS[signals[index]]));
  }
  return WORK_CLASSES[maximum];
};

const projectionFor = (workClass, interviewRequired) => {
  const projection = CLASS_PROJECTIONS[workClass];
  if (interviewRequired && WORK_CLASS_INDEX.get(workClass) < WORK_CLASS_INDEX.get("E4")) {
    fail(
      "UNDERPROCESSING_MONOTONICITY_VIOLATION",
      "Interview cannot be projected onto E0-E3; AMBIGUOUS must raise the class to E5",
    );
  }
  return {
    required_phases: interviewRequired ? ["I", ...BASE_PHASES] : [...projection.phases],
    default_role_count: projection.roleCount,
    human_gate_required: projection.humanGate,
  };
};

const orderedReasons = ({ acceptedSignals, floorWorkClass, interviewRules, overrideHash = null }) => {
  const reasons = acceptedSignals.map((signal) => `SIGNAL:${signal}`);
  reasons.push(`FLOOR:${floorWorkClass}`);
  for (let index = 0; index < interviewRules.length; index += 1) {
    reasons.push(`INTERVIEW:${interviewRules[index]}`);
  }
  if (overrideHash !== null) reasons.push(`OVERRIDE:${overrideHash}`);
  return reasons;
};

export const buildClassificationPreimage = (candidate) => {
  const value = requirePlainDataObject(candidate, "classification preimage input", {
    allowedKeys: [
      "request_id",
      "request_input_hash",
      "classifier_version",
      "policy_bundle_hash",
      "accepted_signals",
      "reasons",
      "risk_factors",
      "work_class",
      "required_phases",
      "default_role_count",
      "human_gate_required",
      "supersedes_classification_hash",
      "human_decision_hash",
    ],
    requiredKeys: [
      "request_id",
      "request_input_hash",
      "classifier_version",
      "policy_bundle_hash",
      "accepted_signals",
      "reasons",
      "risk_factors",
      "work_class",
      "required_phases",
      "default_role_count",
      "human_gate_required",
      "supersedes_classification_hash",
      "human_decision_hash",
    ],
  });
  return deepFreeze({
    schema_id: CLASSIFICATION_SCHEMA_ID,
    request_id: requireString(readDataProperty(value, "request_id"), "request_id"),
    request_input_hash: requireHash(
      readDataProperty(value, "request_input_hash"),
      "request_input_hash",
    ),
    classifier_version: requireClassifierVersion(readDataProperty(value, "classifier_version")),
    policy_bundle_hash: requireHash(
      readDataProperty(value, "policy_bundle_hash"),
      "policy_bundle_hash",
    ),
    accepted_signals: canonicalClone(readDataProperty(value, "accepted_signals")),
    reasons: canonicalClone(readDataProperty(value, "reasons")),
    risk_factors: canonicalClone(readDataProperty(value, "risk_factors")),
    work_class: requireString(readDataProperty(value, "work_class"), "work_class"),
    required_phases: canonicalClone(readDataProperty(value, "required_phases")),
    default_role_count: readDataProperty(value, "default_role_count"),
    human_gate_required: readDataProperty(value, "human_gate_required"),
    supersedes_classification_hash: requireNullableHash(
      readDataProperty(value, "supersedes_classification_hash"),
      "supersedes_classification_hash",
    ),
    human_decision_hash: requireNullableHash(
      readDataProperty(value, "human_decision_hash"),
      "human_decision_hash",
    ),
  });
};

const sealDecision = (semantic) => {
  const preimage = buildClassificationPreimage(semantic);
  const classificationHash = sha256ClassificationJson(preimage);
  const digestHex = classificationHash.slice("sha256:".length);
  return deepFreeze({
    ...canonicalClone(semantic),
    preimage,
    classification_hash: classificationHash,
    classification_id: `EWC-${digestHex}`,
  });
};

export const sealClassificationSupersession = (decision, previousClassificationHash) => {
  const supersedes = requireHash(
    previousClassificationHash,
    "supersedes_classification_hash",
  );
  if (decision.classification_hash === supersedes) {
    fail("CLASSIFICATION_SUPERSESSION_CYCLE", "classification cannot supersede itself");
  }
  const semantic = {
    request_id: decision.request_id,
    request_input_hash: decision.request_input_hash,
    classifier_version: decision.classifier_version,
    policy_bundle_hash: decision.policy_bundle_hash,
    accepted_signals: [...decision.accepted_signals],
    reasons: [...decision.reasons],
    risk_factors: [...decision.risk_factors],
    work_class: decision.work_class,
    required_phases: [...decision.required_phases],
    default_role_count: decision.default_role_count,
    human_gate_required: decision.human_gate_required,
    supersedes_classification_hash: supersedes,
    human_decision_hash: null,
  };
  return deepFreeze({
    ...sealDecision(semantic),
    run_id: decision.run_id,
    floor_work_class: decision.floor_work_class,
    interview_rules: [...decision.interview_rules],
    classifier_trace: {
      ...canonicalClone(decision.classifier_trace),
      semantic_reclassification: {
        supersedes_classification_hash: supersedes,
      },
    },
  });
};

export const evaluateEpistemicWork = (candidate, context = undefined) => {
  const input = normalizeClassificationInput(candidate);
  const prior = normalizePriorClassification(context?.prior_classification, input.request_id);
  const accepted = new Set([
    ...input.policy_bundle_signals,
    ...input.request_signals,
    ...input.detector_signals,
    ...input.llm.accepted,
  ]);
  const stickyAmbiguous = prior?.accepted_signals.includes("AMBIGUOUS") ?? false;
  if (
    accepted.size === 0 ||
    input.llm.injectAmbiguous ||
    input.missing_contract_flags.includes("I01_AMBIGUOUS_SIGNAL") ||
    stickyAmbiguous
  ) {
    accepted.add("AMBIGUOUS");
  }
  const initialSignals = [...accepted].sort(signalSort);
  if (
    input.missing_contract_flags.length > 0 &&
    WORK_CLASS_INDEX.get(maximumFloor(initialSignals)) < WORK_CLASS_INDEX.get("E4")
  ) {
    accepted.add("AMBIGUOUS");
  }
  const acceptedSignals = [...accepted].sort(signalSort);
  const floorWorkClass = maximumFloor(acceptedSignals);
  const interviewRuleSet = new Set(input.missing_contract_flags);
  if (accepted.has("AMBIGUOUS")) interviewRuleSet.add("I01_AMBIGUOUS_SIGNAL");
  const interviewRules = INTERVIEW_RULES.filter((rule) => interviewRuleSet.has(rule));
  const projection = projectionFor(floorWorkClass, interviewRules.length > 0);
  const reasons = orderedReasons({
    acceptedSignals,
    floorWorkClass,
    interviewRules,
  });
  const riskFactors = acceptedSignals.filter((signal) => RISK_SIGNALS.has(signal));
  const semantic = {
    request_id: input.request_id,
    request_input_hash: input.request_input_hash,
    classifier_version: input.classifier_version,
    policy_bundle_hash: input.policy_bundle_hash,
    accepted_signals: acceptedSignals,
    reasons,
    risk_factors: riskFactors,
    work_class: floorWorkClass,
    required_phases: projection.required_phases,
    default_role_count: projection.default_role_count,
    human_gate_required: projection.human_gate_required,
    supersedes_classification_hash: null,
    human_decision_hash: null,
  };
  const decision = sealDecision(semantic);
  return deepFreeze({
    ...decision,
    run_id: input.run_id,
    floor_work_class: floorWorkClass,
    interview_rules: interviewRules,
    classifier_trace: {
      source_precedence: [
        "POLICY_BUNDLE",
        "TYPED_REQUEST_METADATA",
        "DETERMINISTIC_DETECTOR",
        "LLM_SIGNAL_PROPOSAL",
      ],
      policy_bundle_signals: input.policy_bundle_signals,
      request_signals: input.request_signals,
      detector_signals: input.detector_signals,
      llm_proposals: input.llm.trace,
      empty_signal_ambiguity_injected:
        input.policy_bundle_signals.length === 0 &&
        input.request_signals.length === 0 &&
        input.detector_signals.length === 0 &&
        input.llm.accepted.length === 0,
      sticky_ambiguity_applied: stickyAmbiguous,
    },
  });
};

const hasInterview = (decision) => decision.required_phases[0] === "I";

const phaseSet = (decision) => new Set(decision.required_phases);

export const assertMonotonicProtection = (previous, next) => {
  const previousClass = WORK_CLASS_INDEX.get(previous.work_class);
  const nextClass = WORK_CLASS_INDEX.get(next.work_class);
  if (previousClass === undefined || nextClass === undefined) {
    fail("INVALID_INPUT", "monotonic comparison requires canonical work classes");
  }
  const regressions = [];
  if (nextClass < previousClass) regressions.push("work_class");
  if (previous.human_gate_required && !next.human_gate_required) regressions.push("human_gate");
  if (hasInterview(previous) && !hasInterview(next)) regressions.push("interview");
  if (next.default_role_count < previous.default_role_count) regressions.push("role_count");
  const nextPhases = phaseSet(next);
  for (const phase of phaseSet(previous)) {
    if (!nextPhases.has(phase)) regressions.push(`phase:${phase}`);
  }
  if (regressions.length > 0) {
    fail(
      "UNDERPROCESSING_MONOTONICITY_VIOLATION",
      "classification protection decreased",
      { regressions },
    );
  }
  return true;
};

export const applyHumanClassificationOverride = (baseDecision, candidate) => {
  const override = requirePlainDataObject(candidate, "classification override", {
    allowedKeys: [
      "target_work_class",
      "add_interview",
      "interview_rule",
      "human_decision",
      "human_decision_hash",
    ],
    requiredKeys: ["target_work_class", "add_interview", "interview_rule"],
  });
  const targetWorkClass = requireString(
    readDataProperty(override, "target_work_class"),
    "target_work_class",
  );
  if (!WORK_CLASS_SET.has(targetWorkClass)) fail("INVALID_INPUT", "target_work_class is invalid");
  const addInterview = readDataProperty(override, "add_interview");
  if (typeof addInterview !== "boolean") fail("INVALID_INPUT", "add_interview must be boolean");
  const interviewRuleValue = readDataProperty(override, "interview_rule");
  const interviewRule =
    interviewRuleValue === null
      ? null
      : requireString(interviewRuleValue, "interview_rule");
  if (interviewRule !== null && !INTERVIEW_RULE_SET.has(interviewRule)) {
    fail("INVALID_INPUT", "interview_rule is invalid");
  }
  if (addInterview !== (interviewRule !== null)) {
    fail("INVALID_INPUT", "an added Interview requires exactly one canonical interview_rule");
  }
  if (!OBJECT_HAS_OWN(override, "human_decision")) {
    fail(
      "HUMAN_DECISION_ARTIFACT_REQUIRED",
      "human override requires a resolved canonical HumanDecision artifact",
    );
  }
  const humanDecision = validateHumanDecisionArtifact(
    readDataProperty(override, "human_decision"),
    baseDecision,
  );
  const humanDecisionHash = humanDecision.decision_hash;
  if (OBJECT_HAS_OWN(override, "human_decision_hash")) {
    const assertedHash = requireHash(
      readDataProperty(override, "human_decision_hash"),
      "human_decision_hash",
      { code: "HUMAN_DECISION_INTEGRITY_FAILED" },
    );
    if (assertedHash !== humanDecisionHash) {
      fail(
        "HUMAN_DECISION_INTEGRITY_FAILED",
        "human_decision_hash does not match the resolved HumanDecision artifact",
        { expected: humanDecisionHash, actual: assertedHash },
      );
    }
  }
  if (!WORK_CLASS_SET.has(baseDecision.work_class)) {
    fail("INVALID_INPUT", "base classification has an invalid work class");
  }
  const currentRank = WORK_CLASS_INDEX.get(baseDecision.work_class);
  const targetRank = WORK_CLASS_INDEX.get(targetWorkClass);
  if (targetRank < currentRank) {
    fail("HUMAN_OVERRIDE_LOWERING_DENIED", "same-revision HumanDecision cannot lower class");
  }
  const existingInterview = hasInterview(baseDecision);
  if (addInterview && targetRank < WORK_CLASS_INDEX.get("E4")) {
    fail("HUMAN_OVERRIDE_INVALID", "Interview can only use an E4 or E5 exact projection");
  }
  if (targetRank === currentRank && (!addInterview || existingInterview)) {
    fail("HUMAN_OVERRIDE_NO_OP", "override must add protection without mutating history");
  }
  const interviewRuleSet = new Set(baseDecision.interview_rules ?? []);
  if (interviewRule !== null) interviewRuleSet.add(interviewRule);
  const interviewRules = INTERVIEW_RULES.filter((rule) => interviewRuleSet.has(rule));
  const projection = projectionFor(targetWorkClass, existingInterview || addInterview);
  const semantic = {
    request_id: baseDecision.request_id,
    request_input_hash: baseDecision.request_input_hash,
    classifier_version: baseDecision.classifier_version,
    policy_bundle_hash: baseDecision.policy_bundle_hash,
    accepted_signals: [...baseDecision.accepted_signals],
    reasons: orderedReasons({
      acceptedSignals: baseDecision.accepted_signals,
      floorWorkClass: baseDecision.floor_work_class,
      interviewRules,
      overrideHash: humanDecisionHash,
    }),
    risk_factors: [...baseDecision.risk_factors],
    work_class: targetWorkClass,
    required_phases: projection.required_phases,
    default_role_count: projection.default_role_count,
    human_gate_required: projection.human_gate_required,
    supersedes_classification_hash: baseDecision.classification_hash,
    human_decision_hash: humanDecisionHash,
  };
  const decision = {
    ...sealDecision(semantic),
    run_id: baseDecision.run_id,
    floor_work_class: baseDecision.floor_work_class,
    interview_rules: interviewRules,
    classifier_trace: {
      ...(baseDecision.classifier_trace ?? {}),
      human_override: {
        human_decision_hash: humanDecisionHash,
        supersedes_classification_hash: baseDecision.classification_hash,
      },
    },
  };
  assertMonotonicProtection(baseDecision, decision);
  return deepFreeze(decision);
};

export const materializeClassificationArtifact = (decision, classifiedAt) => {
  const timestamp = requireString(classifiedAt, "classified_at");
  if (!CLASSIFIED_AT_PATTERN.test(timestamp) || !NUMBER_IS_FINITE(Date.parse(timestamp))) {
    fail("INVALID_INPUT", "classified_at must be a real UTC RFC 3339 millisecond timestamp");
  }
  return deepFreeze({
    classification_id: decision.classification_id,
    request_id: decision.request_id,
    work_class: decision.work_class,
    reasons: [...decision.reasons],
    risk_factors: [...decision.risk_factors],
    required_phases: [...decision.required_phases],
    default_role_count: decision.default_role_count,
    human_gate_required: decision.human_gate_required,
    classified_at: timestamp,
    classifier_version: decision.classifier_version,
    classification_hash: decision.classification_hash,
  });
};

export const assertClassificationArtifactIntegrity = (artifact, identityContext) => {
  const value = requirePlainDataObject(artifact, "classification artifact", {
    allowedKeys: BUSINESS_ARTIFACT_KEYS,
    requiredKeys: BUSINESS_ARTIFACT_KEYS,
    code: "CLASSIFICATION_INTEGRITY_FAILED",
  });
  const classificationId = requireString(
    readDataProperty(value, "classification_id"),
    "classification_id",
    { code: "CLASSIFICATION_INTEGRITY_FAILED" },
  );
  const classificationHash = requireString(
    readDataProperty(value, "classification_hash"),
    "classification_hash",
    { code: "CLASSIFICATION_INTEGRITY_FAILED" },
  );
  if (!CLASSIFICATION_ID_PATTERN.test(classificationId) || !SHA256_PATTERN.test(classificationHash)) {
    fail("CLASSIFICATION_INTEGRITY_FAILED", "classification identity format is invalid");
  }
  if (classificationId !== `EWC-${classificationHash.slice("sha256:".length)}`) {
    fail("CLASSIFICATION_INTEGRITY_FAILED", "classification ID does not bind its hash");
  }
  const timestamp = readDataProperty(value, "classified_at");
  if (
    typeof timestamp !== "string" ||
    !CLASSIFIED_AT_PATTERN.test(timestamp) ||
    !NUMBER_IS_FINITE(Date.parse(timestamp))
  ) {
    fail("CLASSIFICATION_INTEGRITY_FAILED", "classified_at is invalid");
  }
  const context = requirePlainDataObject(identityContext, "classification identity context", {
    allowedKeys: [
      "request_input_hash",
      "policy_bundle_hash",
      "accepted_signals",
      "supersedes_classification_hash",
      "human_decision_hash",
    ],
    requiredKeys: [
      "request_input_hash",
      "policy_bundle_hash",
      "accepted_signals",
      "supersedes_classification_hash",
      "human_decision_hash",
    ],
    code: "CLASSIFICATION_INTEGRITY_FAILED",
  });
  const preimage = buildClassificationPreimage({
    request_id: readDataProperty(value, "request_id"),
    request_input_hash: readDataProperty(context, "request_input_hash"),
    classifier_version: readDataProperty(value, "classifier_version"),
    policy_bundle_hash: readDataProperty(context, "policy_bundle_hash"),
    accepted_signals: readDataProperty(context, "accepted_signals"),
    reasons: readDataProperty(value, "reasons"),
    risk_factors: readDataProperty(value, "risk_factors"),
    work_class: readDataProperty(value, "work_class"),
    required_phases: readDataProperty(value, "required_phases"),
    default_role_count: readDataProperty(value, "default_role_count"),
    human_gate_required: readDataProperty(value, "human_gate_required"),
    supersedes_classification_hash: readDataProperty(
      context,
      "supersedes_classification_hash",
    ),
    human_decision_hash: readDataProperty(context, "human_decision_hash"),
  });
  const expectedHash = sha256ClassificationJson(preimage);
  if (classificationHash !== expectedHash) {
    fail("CLASSIFICATION_INTEGRITY_FAILED", "classification hash does not match preimage", {
      expected: expectedHash,
      actual: classificationHash,
    });
  }
  return true;
};

export const assertStrictClassificationReplay = (recorded, replayed) => {
  const recordedJson = canonicalizeClassificationJson(recorded);
  const replayedJson = canonicalizeClassificationJson(replayed);
  if (recordedJson !== replayedJson) {
    fail("REPLAY_DIVERGENCE", "strict replay changed classification semantics or identity");
  }
  return true;
};

export const validateClassifierCapabilities = (candidate) => {
  const values = readDenseArray(candidate, "classifier capabilities");
  const capabilities = new Set();
  for (let index = 0; index < values.length; index += 1) {
    const capability = requireString(values[index], `classifier capabilities[${index}]`);
    if (capability === "artifact.read" || capability === "artifact.write" || capability.includes(":")) {
      fail("CAPABILITY_VOCABULARY_MISMATCH", "classifier capability alias is forbidden", {
        capability,
      });
    }
    if (capability !== "artifact_read" && capability !== "artifact_write") {
      fail("CAPABILITY_VOCABULARY_MISMATCH", "classifier capability is outside its bounded vocabulary", {
        capability,
      });
    }
    capabilities.add(capability);
  }
  if (!capabilities.has("artifact_read") || !capabilities.has("artifact_write")) {
    fail("CLASSIFIER_CAPABILITY_MISSING", "classifier requires artifact_read and artifact_write");
  }
  return OBJECT_FREEZE(["artifact_read", "artifact_write"]);
};

export const validateClassificationResultEnvelope = (envelope, classification = null) => {
  const value = requirePlainDataObject(envelope, "ResultEnvelope", {
    allowedKeys: [
      "run_id",
      "node_id",
      "attempt",
      "status",
      "output_artifact_ids",
      "evidence_ids",
      "errors",
      "metrics",
      "input_hash",
      "output_hash",
      "started_at",
      "finished_at",
      "completeness",
      "effect_receipt_ids",
      "policy_decision_ids",
      "schema_validation_report_id",
      "terminal_reason",
    ],
    requiredKeys: ["status", "output_artifact_ids"],
  });
  const status = requireString(readDataProperty(value, "status"), "ResultEnvelope.status");
  const outputIds = readDenseArray(
    readDataProperty(value, "output_artifact_ids"),
    "ResultEnvelope.output_artifact_ids",
  );
  if (status === "success" && classification === null) {
    fail(
      "CLASSIFICATION_ARTIFACT_MISSING",
      "ResultEnvelope success cannot replace the classification business artifact",
    );
  }
  if (classification !== null && !outputIds.includes(classification.classification_id)) {
    fail(
      "CLASSIFICATION_ARTIFACT_MISSING",
      "ResultEnvelope does not bind the classification artifact ID",
    );
  }
  return true;
};

export const classificationIdempotencyKey = ({
  request_id,
  request_input_hash,
  classifier_version,
  policy_bundle_hash,
  human_decision_hash = null,
}) => {
  const base = {
    request_id: requireString(request_id, "request_id"),
    request_input_hash: requireHash(request_input_hash, "request_input_hash"),
    classifier_version: requireClassifierVersion(classifier_version),
    policy_bundle_hash: requireHash(policy_bundle_hash, "policy_bundle_hash"),
    human_decision_hash: requireNullableHash(human_decision_hash, "human_decision_hash"),
  };
  return `classification:${sha256ClassificationJson(base)}`;
};

export const classificationInputHash = (requestText) =>
  `sha256:${createHash("sha256")
    .update(requireString(requestText, "request_text", { allowEmpty: true }), "utf8")
    .digest("hex")}`;
