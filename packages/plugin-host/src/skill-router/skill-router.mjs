import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

const ARRAY_IS_ARRAY = Array.isArray;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const IS_PROXY = utilTypes.isProxy;

const REQUEST_FIELDS = OBJECT_FREEZE([
  "request_id",
  "request_text",
  "explicit_skill_id",
  "candidates",
  "context_budget_tokens",
  "policy_hash",
  "decided_at",
]);
const CANDIDATE_FIELDS = OBJECT_FREEZE([
  "skill_id",
  "description",
  "content_hash",
  "source",
  "allow_implicit_invocation",
  "sensitive",
  "side_effecting",
  "trigger_phrases",
  "exclusion_phrases",
  "activation_authorization",
]);
const REQUIRED_CANDIDATE_FIELDS = OBJECT_FREEZE([
  "skill_id",
  "description",
  "content_hash",
  "source",
  "sensitive",
  "side_effecting",
  "trigger_phrases",
  "exclusion_phrases",
]);
const RUNTIME_FIELDS = OBJECT_FREEZE(["is_remote_skill_authorized"]);
const AUTHORIZATION_FIELDS = OBJECT_FREEZE([
  "decision",
  "purpose",
  "requestId",
  "skillId",
  "workspaceId",
  "lockHash",
  "contentHash",
  "policyHash",
  "permissions",
  "activationScopeId",
  "explicitApprovalLinked",
  "conformanceId",
  "rollbackAvailable",
  "effectPerformed",
]);

const AUTHORITY_NOTES = OBJECT_FREEZE([
  "FULL_SKILL_INSTRUCTIONS_NOT_LOADED",
  "REMOTE_SKILLS_REQUIRE_S03_EXPLICIT_ACTIVATION",
  "ROUTING_DECISION_HAS_NO_STATE_OR_AUTHORITY",
  "SENSITIVE_AND_SIDE_EFFECTING_SKILLS_EXPLICIT_ONLY",
]);
const SOURCE = OBJECT_FREEZE({ BUNDLED: "bundled", REMOTE: "remote" });
const SOURCE_VALUES = new Set(Object.values(SOURCE));
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const SKILL_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/u;
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:Z|([+-])(\d{2}):(\d{2}))$/u;

export const SKILL_SOURCE = SOURCE;

export class SkillRoutingError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "SkillRoutingError";
    this.code = code;
  }
}

const fail = (code, message) => {
  throw new SkillRoutingError(code, message);
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

const requireString = (
  value,
  label,
  { allowEmpty = false, minLength = undefined, maxLength = undefined } = {},
) => {
  const scalarLength = typeof value === "string" ? [...value].length : undefined;
  if (
    typeof value !== "string" ||
    !hasOnlyUnicodeScalars(value) ||
    (!allowEmpty && scalarLength === 0) ||
    (minLength !== undefined && scalarLength < minLength) ||
    (maxLength !== undefined && scalarLength > maxLength)
  ) {
    fail("INVALID_INPUT", `${label} must be a bounded Unicode scalar string`);
  }
  return value;
};

const requirePlainDataObject = (
  value,
  label,
  { allowedFields, requiredFields = [] },
) => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value)
  ) {
    fail("INVALID_INPUT", `${label} must be a non-proxy plain data object`);
  }
  const prototype = OBJECT_GET_PROTOTYPE_OF(value);
  if (prototype !== Object.prototype && prototype !== null) {
    fail("INVALID_INPUT", `${label} must not have a custom prototype`);
  }

  const allowed = new Set(allowedFields);
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (typeof key !== "string" || !allowed.has(key)) {
      fail("UNEXPECTED_FIELD", `${label} contains an unsupported field`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail("ACCESSOR_FIELD_DENIED", `${label}.${String(key)} must be an enumerable data property`);
    }
  }
  for (const key of requiredFields) {
    if (!OBJECT_HAS_OWN(value, key)) fail("MISSING_FIELD", `${label}.${key} is required`);
  }
  return value;
};

const readDataProperty = (record, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(record, key).value;

const readOptionalDataProperty = (record, key, defaultValue) => {
  const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(record, key);
  return descriptor === undefined ? defaultValue : descriptor.value;
};

const readDenseArray = (value, label) => {
  if (!ARRAY_IS_ARRAY(value) || IS_PROXY(value)) {
    fail("INVALID_INPUT", `${label} must be a non-proxy dense array`);
  }
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
      fail("INVALID_INPUT", `${label} contains a non-element property`);
    }
    const index = Number(key);
    if (!Number.isSafeInteger(index) || index < 0 || index >= value.length) {
      fail("INVALID_INPUT", `${label} contains a non-canonical array index`);
    }
  }
  const result = new Array(value.length);
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail("INVALID_INPUT", `${label} must not be sparse or accessor-backed`);
    }
    result[index] = descriptor.value;
  }
  return result;
};

const compareUtf8 = (left, right) =>
  Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));

const normalizeSearchText = (value) =>
  value
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[^\p{Letter}\p{Number}]+/gu, " ")
    .trim();

const normalizePhrases = (value, label) => {
  const entries = readDenseArray(value, label);
  const normalized = entries.map((entry, index) => {
    const phrase = requireString(entry, `${label}[${index}]`, { minLength: 2, maxLength: 256 });
    const canonical = normalizeSearchText(phrase);
    if (canonical.length === 0) fail("INVALID_INPUT", `${label}[${index}] has no searchable text`);
    return canonical;
  });
  normalized.sort(compareUtf8);
  for (let index = 1; index < normalized.length; index += 1) {
    if (normalized[index - 1] === normalized[index]) {
      fail("DUPLICATE_TRIGGER_PHRASE", `${label} contains a duplicate canonical phrase`);
    }
  }
  return OBJECT_FREEZE(normalized);
};

const requireBoolean = (value, label) => {
  if (typeof value !== "boolean") fail("INVALID_INPUT", `${label} must be boolean`);
  return value;
};

const requireHash = (value, label) => {
  const hash = requireString(value, label);
  if (!SHA256_PATTERN.test(hash)) fail("INVALID_HASH", `${label} must be canonical SHA-256`);
  return hash;
};

const requireSkillId = (value, label) => {
  const skillId = requireString(value, label, { minLength: 3, maxLength: 128 });
  if (!SKILL_ID_PATTERN.test(skillId)) {
    fail("INVALID_SKILL_ID", `${label} must use the canonical lowercase skill ID syntax`);
  }
  return skillId;
};

const isLeapYear = (year) => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

const requireRfc3339 = (value, label) => {
  const timestamp = requireString(value, label);
  const match = RFC3339_PATTERN.exec(timestamp);
  if (match === null) fail("INVALID_TIMESTAMP", `${label} must be RFC 3339`);
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const offsetHour = match[9] === undefined ? 0 : Number(match[9]);
  const offsetMinute = match[10] === undefined ? 0 : Number(match[10]);
  const days = [31, isLeapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > days[month - 1] ||
    hour > 23 ||
    minute > 59 ||
    second > 59 ||
    offsetHour > 23 ||
    offsetMinute > 59
  ) {
    fail("INVALID_TIMESTAMP", `${label} must be RFC 3339`);
  }
  return timestamp;
};

const normalizeCandidate = (candidate, index) => {
  const label = `candidates[${index}]`;
  const record = requirePlainDataObject(candidate, label, {
    allowedFields: CANDIDATE_FIELDS,
    requiredFields: REQUIRED_CANDIDATE_FIELDS,
  });
  const source = requireString(readDataProperty(record, "source"), `${label}.source`);
  if (!SOURCE_VALUES.has(source)) fail("INVALID_INPUT", `${label}.source is not canonical`);
  const activationAuthorization = readOptionalDataProperty(
    record,
    "activation_authorization",
    null,
  );
  if (source === SOURCE.BUNDLED && activationAuthorization !== null) {
    fail("INVALID_INPUT", `${label}.activation_authorization is remote-only`);
  }
  const implicitPolicy = readOptionalDataProperty(
    record,
    "allow_implicit_invocation",
    null,
  );
  if (implicitPolicy !== null) requireBoolean(implicitPolicy, `${label}.allow_implicit_invocation`);

  return OBJECT_FREEZE({
    skillId: requireSkillId(readDataProperty(record, "skill_id"), `${label}.skill_id`),
    description: requireString(readDataProperty(record, "description"), `${label}.description`, {
      minLength: 3,
      maxLength: 2_048,
    }),
    contentHash: requireHash(readDataProperty(record, "content_hash"), `${label}.content_hash`),
    source,
    implicitPolicy,
    sensitive: requireBoolean(readDataProperty(record, "sensitive"), `${label}.sensitive`),
    sideEffecting: requireBoolean(
      readDataProperty(record, "side_effecting"),
      `${label}.side_effecting`,
    ),
    triggerPhrases: normalizePhrases(readDataProperty(record, "trigger_phrases"), `${label}.trigger_phrases`),
    exclusionPhrases: normalizePhrases(
      readDataProperty(record, "exclusion_phrases"),
      `${label}.exclusion_phrases`,
    ),
    activationAuthorization,
  });
};

const normalizeRequest = (candidate) => {
  const record = requirePlainDataObject(candidate, "skillRoutingRequest", {
    allowedFields: REQUEST_FIELDS,
    requiredFields: REQUEST_FIELDS,
  });
  const candidates = readDenseArray(readDataProperty(record, "candidates"), "candidates").map(
    normalizeCandidate,
  );
  candidates.sort((left, right) => compareUtf8(left.skillId, right.skillId));
  for (let index = 1; index < candidates.length; index += 1) {
    if (candidates[index - 1].skillId === candidates[index].skillId) {
      fail("DUPLICATE_SKILL_ID", "candidates contains a duplicate skill_id");
    }
  }
  const explicitSkillValue = readDataProperty(record, "explicit_skill_id");
  const explicitSkillId =
    explicitSkillValue === null
      ? null
      : requireSkillId(explicitSkillValue, "explicit_skill_id");
  const contextBudgetTokens = readDataProperty(record, "context_budget_tokens");
  if (!Number.isSafeInteger(contextBudgetTokens) || contextBudgetTokens < 0) {
    fail("INVALID_INPUT", "context_budget_tokens must be a non-negative safe integer");
  }
  return OBJECT_FREEZE({
    requestId: requireString(readDataProperty(record, "request_id"), "request_id", {
      minLength: 3,
      maxLength: 128,
    }),
    requestText: requireString(readDataProperty(record, "request_text"), "request_text", {
      minLength: 1,
      maxLength: 100_000,
    }),
    explicitSkillId,
    candidates: OBJECT_FREEZE(candidates),
    contextBudgetTokens,
    policyHash: requireHash(readDataProperty(record, "policy_hash"), "policy_hash"),
    decidedAt: requireRfc3339(readDataProperty(record, "decided_at"), "decided_at"),
  });
};

const normalizeRuntime = (candidate) => {
  if (candidate === undefined) {
    return OBJECT_FREEZE({ isRemoteSkillAuthorized: () => false });
  }
  const record = requirePlainDataObject(candidate, "skillRoutingRuntime", {
    allowedFields: RUNTIME_FIELDS,
    requiredFields: RUNTIME_FIELDS,
  });
  const guard = readDataProperty(record, "is_remote_skill_authorized");
  if (typeof guard !== "function") {
    fail("INVALID_INPUT", "is_remote_skill_authorized must be a function");
  }
  return OBJECT_FREEZE({ isRemoteSkillAuthorized: guard });
};

const phraseMatches = (normalizedRequest, phrase) =>
  ` ${normalizedRequest} `.includes(` ${phrase} `);

const implicitPolicyAllows = (candidate) =>
  candidate.source === SOURCE.BUNDLED &&
  candidate.implicitPolicy === true &&
  !candidate.sensitive &&
  !candidate.sideEffecting;

const evaluateImplicitCandidate = (candidate, normalizedRequest) => {
  const exclusion = candidate.exclusionPhrases.find((phrase) =>
    phraseMatches(normalizedRequest, phrase),
  );
  const matches = candidate.triggerPhrases.filter((phrase) =>
    phraseMatches(normalizedRequest, phrase),
  );
  const score = exclusion === undefined && matches.length > 0 ? 1 : 0;
  const implicitAllowed = implicitPolicyAllows(candidate);
  let reason;
  if (exclusion !== undefined) reason = `EXCLUSION_MATCH:${exclusion}`;
  else if (matches.length === 0) reason = "NO_TRIGGER_MATCH";
  else if (candidate.source === SOURCE.REMOTE) reason = "REMOTE_EXPLICIT_ONLY";
  else if (candidate.sensitive) reason = "SENSITIVE_EXPLICIT_ONLY";
  else if (candidate.sideEffecting) reason = "SIDE_EFFECTING_EXPLICIT_ONLY";
  else if (candidate.implicitPolicy === null) reason = "IMPLICIT_POLICY_UNSPECIFIED";
  else if (!candidate.implicitPolicy) reason = "IMPLICIT_POLICY_DENIED";
  else reason = `BOUNDED_TRIGGER_MATCH:${matches[0]}`;
  return { candidate, score, reason, implicitAllowed, eligible: score === 1 && implicitAllowed };
};

const validateRemoteAuthorization = (candidate, request, runtime) => {
  const authorization = candidate.activationAuthorization;
  if (authorization === null) {
    fail(
      "REMOTE_ACTIVATION_AUTHORIZATION_REQUIRED",
      "an explicit remote skill route requires an S03 activation authorization",
    );
  }
  let branded = false;
  try {
    branded = runtime.isRemoteSkillAuthorized(authorization) === true;
  } catch {
    branded = false;
  }
  if (!branded) {
    fail(
      "REMOTE_ACTIVATION_AUTHORIZATION_REQUIRED",
      "the remote activation authorization is not recognized by its S03 boundary",
    );
  }
  const record = requirePlainDataObject(authorization, "activation_authorization", {
    allowedFields: AUTHORIZATION_FIELDS,
    requiredFields: AUTHORIZATION_FIELDS,
  });
  const field = (key) => readDataProperty(record, key);
  if (
    field("decision") !== "ALLOW" ||
    field("purpose") !== "explicit_skill_activation" ||
    field("skillId") !== candidate.skillId ||
    field("contentHash") !== candidate.contentHash ||
    field("policyHash") !== request.policyHash ||
    field("explicitApprovalLinked") !== true ||
    field("rollbackAvailable") !== true ||
    field("effectPerformed") !== false
  ) {
    fail(
      "REMOTE_ACTIVATION_AUTHORIZATION_MISMATCH",
      "the S03 authorization does not bind this exact explicit route",
    );
  }
};

const evaluateExplicitCandidates = (request, runtime) => {
  const selected = request.candidates.find(
    (candidate) => candidate.skillId === request.explicitSkillId,
  );
  if (selected === undefined) {
    fail("UNKNOWN_EXPLICIT_SKILL", "explicit_skill_id is absent from the bounded skill index");
  }
  if (selected.source === SOURCE.REMOTE) validateRemoteAuthorization(selected, request, runtime);
  return request.candidates.map((candidate) => ({
    candidate,
    score: candidate === selected ? 1 : 0,
    reason:
      candidate === selected
        ? selected.source === SOURCE.REMOTE
          ? "EXPLICIT_EXACT_ID_REMOTE_AUTHORIZED"
          : "EXPLICIT_EXACT_ID"
        : "EXPLICIT_NOT_REQUESTED",
    implicitAllowed: implicitPolicyAllows(candidate),
    eligible: candidate === selected,
  }));
};

const evaluatedOrder = (left, right) =>
  right.score - left.score || compareUtf8(left.candidate.skillId, right.candidate.skillId);

const canonicalCandidate = (evaluation) =>
  OBJECT_FREEZE({
    skill_id: evaluation.candidate.skillId,
    score: evaluation.score,
    reason: evaluation.reason,
    implicit_allowed: evaluation.implicitAllowed,
  });

const assertCanonicalJsonValue = (value, label = "value", ancestors = new WeakSet()) => {
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") {
    if (!hasOnlyUnicodeScalars(value)) {
      fail("NON_CANONICAL_JSON", `${label} contains invalid Unicode`);
    }
    return;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value) || Object.is(value, -0)) {
      fail("NON_CANONICAL_JSON", `${label} contains a non-canonical number`);
    }
    return;
  }
  if (typeof value !== "object" || IS_PROXY(value) || ancestors.has(value)) {
    fail("NON_CANONICAL_JSON", `${label} is not canonical JSON`);
  }
  ancestors.add(value);
  try {
    if (ARRAY_IS_ARRAY(value)) {
      const entries = readDenseArray(value, label);
      entries.forEach((entry, index) =>
        assertCanonicalJsonValue(entry, `${label}[${index}]`, ancestors),
      );
      return;
    }
    const prototype = OBJECT_GET_PROTOTYPE_OF(value);
    if (prototype !== Object.prototype && prototype !== null) {
      fail("NON_CANONICAL_JSON", `${label} must be a plain data object`);
    }
    const keys = REFLECT_OWN_KEYS(value);
    for (const key of keys) {
      if (typeof key !== "string") fail("NON_CANONICAL_JSON", `${label} contains a symbol key`);
      const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
      if (
        descriptor === undefined ||
        !descriptor.enumerable ||
        !OBJECT_HAS_OWN(descriptor, "value")
      ) {
        fail("NON_CANONICAL_JSON", `${label}.${key} is not an enumerable data property`);
      }
      assertCanonicalJsonValue(descriptor.value, `${label}.${key}`, ancestors);
    }
  } finally {
    ancestors.delete(value);
  }
};

export const canonicalizeSkillRoutingJson = (value) => {
  assertCanonicalJsonValue(value);
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (ARRAY_IS_ARRAY(value)) {
    return `[${value.map((entry) => canonicalizeSkillRoutingJson(entry)).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort(compareUtf8)
    .map(
      (key) =>
        `${JSON.stringify(key)}:${canonicalizeSkillRoutingJson(readDataProperty(value, key))}`,
    )
    .join(",")}}`;
};

export const computeSkillRoutingDecisionHash = (preimage) =>
  `sha256:${createHash("sha256")
    .update(canonicalizeSkillRoutingJson(preimage), "utf8")
    .digest("hex")}`;

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of REFLECT_OWN_KEYS(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};

/**
 * Produce one immutable SkillRoutingDecision from bounded metadata. This
 * policy function never loads skill bodies, activates a skill, or mutates
 * FORGE state. Unknown fields fail closed so instruction/reference content
 * cannot be smuggled into the always-visible routing context.
 */
export const routeSkillRequest = (requestCandidate, runtimeCandidate = undefined) => {
  const request = normalizeRequest(requestCandidate);
  const runtime = normalizeRuntime(runtimeCandidate);
  let evaluations;
  let selectedSkillIds;
  let mode;

  if (request.explicitSkillId !== null) {
    evaluations = evaluateExplicitCandidates(request, runtime);
    selectedSkillIds = [request.explicitSkillId];
    mode = "explicit";
  } else {
    const normalizedRequest = normalizeSearchText(request.requestText);
    evaluations = request.candidates.map((candidate) =>
      evaluateImplicitCandidate(candidate, normalizedRequest),
    );
    const eligible = evaluations.filter((evaluation) => evaluation.eligible);
    if (eligible.length === 1) {
      selectedSkillIds = [eligible[0].candidate.skillId];
      mode = "implicit";
    } else {
      selectedSkillIds = [];
      mode = "none";
      if (eligible.length > 1) {
        const ambiguousIds = new Set(eligible.map((evaluation) => evaluation.candidate.skillId));
        evaluations = evaluations.map((evaluation) =>
          ambiguousIds.has(evaluation.candidate.skillId)
            ? { ...evaluation, reason: "AMBIGUOUS_TRIGGER_MATCH", eligible: false }
            : evaluation,
        );
      }
    }
  }

  evaluations.sort(evaluatedOrder);
  const selectedSet = new Set(selectedSkillIds);
  const candidates = evaluations.map(canonicalCandidate);
  const rejectedSkillIds = evaluations
    .map((evaluation) => evaluation.candidate.skillId)
    .filter((skillId) => !selectedSet.has(skillId))
    .sort(compareUtf8);
  const metadataBindings = request.candidates.map(
    (candidate) =>
      `SKILL_METADATA:${candidate.skillId}:${candidate.source}:${candidate.contentHash}`,
  );
  const preimage = {
    request_id: request.requestId,
    mode,
    candidates,
    selected_skill_ids: selectedSkillIds,
    rejected_skill_ids: rejectedSkillIds,
    context_budget_tokens: selectedSkillIds.length === 0 ? 0 : request.contextBudgetTokens,
    authority_notes: [...AUTHORITY_NOTES, ...metadataBindings],
    policy_hash: request.policyHash,
    decided_at: request.decidedAt,
  };
  const decisionHash = computeSkillRoutingDecisionHash(preimage);
  return deepFreeze({
    decision_id: `SRD-${decisionHash.slice("sha256:".length)}`,
    ...preimage,
    decision_hash: decisionHash,
  });
};
