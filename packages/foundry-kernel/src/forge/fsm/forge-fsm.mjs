import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

import { assertClassificationArtifactIntegrity } from "../classifier/epistemic-work-classifier.mjs";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const NUMBER_IS_FINITE = Number.isFinite;
const NUMBER_IS_SAFE_INTEGER = Number.isSafeInteger;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;

const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const CLASSIFICATION_ID_PATTERN = /^EWC-[0-9a-f]{64}$/u;
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:[Zz]|([+-])(\d{2}):(\d{2}))$/u;

export const FORGE_PHASES = OBJECT_FREEZE(["IDLE", "I", "F", "O", "R", "G", "E"]);
export const FORGE_EXECUTION_PHASES = OBJECT_FREEZE(["I", "F", "O", "R", "G", "E"]);
export const FORGE_TRANSITION_KINDS = OBJECT_FREEZE(["FORWARD", "RETURN", "CLOSE"]);

const PHASES = new Set(FORGE_PHASES);
const EXECUTION_PHASE_INDEX = new Map(
  FORGE_EXECUTION_PHASES.map((phase, index) => [phase, index]),
);
const WORK_CLASSES = new Set(["E0", "E1", "E2", "E3", "E4", "E5"]);
const SESSION_STATUSES = new Set([
  "ACTIVE",
  "PAUSED",
  "BLOCKED",
  "COMPLETED",
  "ABORTED",
  "STALE",
]);
const TRANSITIONABLE_STATUSES = new Set(["ACTIVE", "STALE"]);
const ACTOR_TYPES = new Set(["human", "agent", "service"]);
const ARTIFACT_STATUSES = new Set(["VALID", "INVALID", "MISSING", "STALE"]);

const CLASSIFICATION_KEYS = OBJECT_FREEZE([
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
const STATE_KEYS = OBJECT_FREEZE([
  "session_id",
  "workspace_id",
  "revision",
  "phase",
  "work_class",
  "status",
  "run_spec_id",
  "hypothesis_revision_ids",
  "artifact_ids",
  "open_blockers",
  "phase_history",
  "policy_hash",
  "corpus_snapshot_hash",
  "updated_at",
  "state_hash",
]);
const STATE_HASH_KEYS = OBJECT_FREEZE(STATE_KEYS.filter((key) => key !== "state_hash"));
const TRANSITION_REQUEST_KEYS = OBJECT_FREEZE([
  "request_id",
  "session_id",
  "expected_revision",
  "from_phase",
  "to_phase",
  "actor",
  "artifact_receipt_ids",
  "gate_result_ids",
  "human_decision_id",
  "reason",
  "idempotency_key",
  "requested_at",
]);
const PHASE_SET_KEYS = OBJECT_FREEZE([
  "set_id",
  "session_id",
  "phase",
  "required_artifacts",
  "optional_artifacts",
  "complete",
  "missing_kinds",
  "validated_at",
  "set_hash",
]);
const PHASE_SET_HASH_KEYS = OBJECT_FREEZE(PHASE_SET_KEYS.filter((key) => key !== "set_hash"));
const PHASE_ARTIFACT_KEYS = OBJECT_FREEZE([
  "artifact_id",
  "kind",
  "schema_ref",
  "content_hash",
  "receipt_id",
  "status",
]);
const PHASE_HISTORY_KEYS = OBJECT_FREEZE(["from", "to", "event_id", "at"]);
const ACTOR_KEYS = OBJECT_FREEZE(["actor_id", "actor_type", "role"]);
const EVENT_KEYS = OBJECT_FREEZE(["event_id", "occurred_at"]);
const DURABLE_TRANSITION_ADMISSION_VERSION = "4.0.0-f03.3";
const DURABLE_ADMISSION_KEYS = OBJECT_FREEZE([
  "admission_version",
  "decision",
  "session_id",
  "request_id",
  "request_hash",
  "idempotency_key",
  "expected_revision",
  "from_phase",
  "to_phase",
  "prior_state_hash",
  "idle_classification_id",
  "idle_classification_hash",
  "phase_artifact_set_id",
  "phase_artifact_set_hash",
  "receipt_bindings",
  "gate_decisions",
  "human_decision_id",
  "human_decision_hash",
  "artifact_retention",
  "admission_id",
  "admission_hash",
]);
const DURABLE_ADMISSION_SEMANTIC_KEYS = OBJECT_FREEZE(
  DURABLE_ADMISSION_KEYS.filter(
    (key) => key !== "admission_id" && key !== "admission_hash",
  ),
);
const ADMISSION_RECEIPT_BINDING_KEYS = OBJECT_FREEZE([
  "receipt_id",
  "receipt_hash",
  "artifact_id",
  "content_hash",
  "schema_ref",
]);
const ADMISSION_GATE_DECISION_KEYS = OBJECT_FREEZE([
  "gate_id",
  "decision_hash",
  "status",
]);
const ADMITTED_GATE_STATUSES = new Set(["PASS", "WAIVE"]);

const EXPECTED_PROJECTIONS = OBJECT_FREEZE({
  E0: OBJECT_FREEZE([OBJECT_FREEZE([])]),
  E1: OBJECT_FREEZE([OBJECT_FREEZE(["F", "O", "E"])]),
  E2: OBJECT_FREEZE([OBJECT_FREEZE(["F", "O", "R", "G", "E"])]),
  E3: OBJECT_FREEZE([OBJECT_FREEZE(["F", "O", "R", "G", "E"])]),
  E4: OBJECT_FREEZE([
    OBJECT_FREEZE(["F", "O", "R", "G", "E"]),
    OBJECT_FREEZE(["I", "F", "O", "R", "G", "E"]),
  ]),
  E5: OBJECT_FREEZE([
    OBJECT_FREEZE(["F", "O", "R", "G", "E"]),
    OBJECT_FREEZE(["I", "F", "O", "R", "G", "E"]),
  ]),
});

const RETURN_EDGE_ROWS = OBJECT_FREEZE([
  OBJECT_FREEZE({ from: "F", to: "I" }),
  OBJECT_FREEZE({ from: "O", to: "I" }),
  OBJECT_FREEZE({ from: "R", to: "I" }),
  OBJECT_FREEZE({ from: "G", to: "I" }),
  OBJECT_FREEZE({ from: "R", to: "O" }),
  OBJECT_FREEZE({ from: "G", to: "O" }),
  OBJECT_FREEZE({ from: "G", to: "R" }),
  OBJECT_FREEZE({ from: "E", to: "F" }),
]);

export class ForgeFsmError extends Error {
  constructor(code, message, details = undefined, options = undefined) {
    super(message, options);
    this.name = "ForgeFsmError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(cloneCanonical(details));
  }
}

const fail = (code, message, details, options) => {
  throw new ForgeFsmError(code, message, details, options);
};

const readDataProperty = (value, key, label = "object", code = "INVALID_INPUT") => {
  const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
  if (descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")) {
    fail(code, `${label}.${key} must be an own data property`);
  }
  return descriptor.value;
};

const requirePlainRecord = (
  value,
  label,
  { allowedKeys = undefined, requiredKeys = undefined, code = "INVALID_INPUT" } = {},
) => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    ![PLAIN_OBJECT_PROTOTYPE, null].includes(OBJECT_GET_PROTOTYPE_OF(value))
  ) {
    fail(code, `${label} must be a plain data object`);
  }
  const keys = REFLECT_OWN_KEYS(value);
  if (keys.some((key) => typeof key !== "string")) {
    fail(code, `${label} cannot contain symbol keys`);
  }
  for (const key of keys) readDataProperty(value, key, label, code);
  if (allowedKeys !== undefined) {
    const allowed = new Set(allowedKeys);
    for (const key of keys) {
      if (!allowed.has(key)) fail(code, `${label}.${key} is not allowed`);
    }
  }
  if (requiredKeys !== undefined) {
    for (const key of requiredKeys) {
      if (!OBJECT_HAS_OWN(value, key)) fail(code, `${label}.${key} is required`);
    }
  }
  return value;
};

const requireDenseArray = (value, label, code = "INVALID_INPUT") => {
  if (!ARRAY_IS_ARRAY(value) || IS_PROXY(value)) fail(code, `${label} must be an array`);
  const keys = REFLECT_OWN_KEYS(value);
  for (let index = 0; index < value.length; index += 1) {
    if (!OBJECT_HAS_OWN(value, index)) fail(code, `${label} cannot be sparse`);
    readDataProperty(value, String(index), label, code);
  }
  for (const key of keys) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(?:0|[1-9][0-9]*)$/u.test(key)) {
      fail(code, `${label} cannot contain non-index properties`);
    }
    if (Number(key) >= value.length) fail(code, `${label} contains an out-of-range index`);
  }
  return value;
};

const requireString = (value, label, { min = 1, max = undefined, code = "INVALID_INPUT" } = {}) => {
  if (
    typeof value !== "string" ||
    value.length < min ||
    (max !== undefined && value.length > max)
  ) {
    fail(code, `${label} must be a string with a valid length`);
  }
  return value;
};

const requireHash = (value, label, code = "INVALID_INPUT") => {
  const candidate = requireString(value, label, { code });
  if (!SHA256_PATTERN.test(candidate)) fail(code, `${label} must be a canonical SHA-256`);
  return candidate;
};

const isLeapYear = (year) => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

const daysInMonth = (year, month) => {
  if (month === 2) return isLeapYear(year) ? 29 : 28;
  return month === 4 || month === 6 || month === 9 || month === 11 ? 30 : 31;
};

const parseRfc3339 = (value) => {
  if (typeof value !== "string") return null;
  const match = RFC3339_PATTERN.exec(value);
  if (match === null || match[0].length !== value.length) return null;

  let year = Number(match[1]);
  const month = Number(match[2]);
  let day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const fraction = match[7] ?? "";
  const offsetHour = match[9] === undefined ? 0 : Number(match[9]);
  const offsetMinute = match[10] === undefined ? 0 : Number(match[10]);
  if (
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > daysInMonth(year, month) ||
    hour > 23 ||
    minute > 59 ||
    second > 60 ||
    offsetHour > 23 ||
    offsetMinute > 59
  ) {
    return null;
  }

  let utcMonth = month;
  let utcMinuteOfDay = hour * 60 + minute;
  if (match[8] === "+") {
    utcMinuteOfDay -= offsetHour * 60 + offsetMinute;
  } else if (match[8] === "-") {
    utcMinuteOfDay += offsetHour * 60 + offsetMinute;
  }
  if (utcMinuteOfDay < 0) {
    utcMinuteOfDay += 24 * 60;
    day -= 1;
    if (day === 0) {
      utcMonth -= 1;
      if (utcMonth === 0) {
        year -= 1;
        utcMonth = 12;
      }
      day = daysInMonth(year, utcMonth);
    }
  } else if (utcMinuteOfDay >= 24 * 60) {
    utcMinuteOfDay -= 24 * 60;
    day += 1;
    if (day > daysInMonth(year, utcMonth)) {
      day = 1;
      utcMonth += 1;
      if (utcMonth === 13) {
        year += 1;
        utcMonth = 1;
      }
    }
  }

  const utcMinute = utcMinuteOfDay % 60;
  const utcHour = (utcMinuteOfDay - utcMinute) / 60;
  if (
    second === 60 &&
    (utcHour !== 23 || utcMinute !== 59 || day !== daysInMonth(year, utcMonth))
  ) {
    return null;
  }
  return OBJECT_FREEZE([year, utcMonth, day, utcHour, utcMinute, second, fraction]);
};

const compareRfc3339 = (left, right, code = "INVALID_INPUT") => {
  const leftTuple = parseRfc3339(left);
  const rightTuple = parseRfc3339(right);
  if (leftTuple === null || rightTuple === null) {
    fail(code, "RFC 3339 chronology comparison requires valid timestamps");
  }
  for (let index = 0; index < 6; index += 1) {
    if (leftTuple[index] < rightTuple[index]) return -1;
    if (leftTuple[index] > rightTuple[index]) return 1;
  }
  const leftFraction = leftTuple[6];
  const rightFraction = rightTuple[6];
  const length = leftFraction.length > rightFraction.length
    ? leftFraction.length
    : rightFraction.length;
  for (let index = 0; index < length; index += 1) {
    const leftDigit = index < leftFraction.length ? leftFraction.charCodeAt(index) : 48;
    const rightDigit = index < rightFraction.length ? rightFraction.charCodeAt(index) : 48;
    if (leftDigit < rightDigit) return -1;
    if (leftDigit > rightDigit) return 1;
  }
  return 0;
};

const requireTimestamp = (value, label, code = "INVALID_INPUT") => {
  const candidate = requireString(value, label, { code });
  if (parseRfc3339(candidate) === null) {
    fail(code, `${label} must be an RFC 3339 timestamp`);
  }
  return candidate;
};

const requirePhase = (value, label, code = "INVALID_INPUT") => {
  if (!PHASES.has(value)) fail(code, `${label} must be a canonical FORGE phase`);
  return value;
};

const requireSafeRevision = (value, label, code = "INVALID_INPUT") => {
  if (!NUMBER_IS_SAFE_INTEGER(value) || value < 0) {
    fail(code, `${label} must be a non-negative safe integer`);
  }
  return value;
};

const requireStringArray = (
  value,
  label,
  { min = 0, unique = false, itemMin = 1, itemMax = undefined, code = "INVALID_INPUT" } = {},
) => {
  const array = requireDenseArray(value, label, code);
  if (array.length < min) fail(code, `${label} must contain at least ${min} item(s)`);
  const seen = new Set();
  for (let index = 0; index < array.length; index += 1) {
    const item = requireString(array[index], `${label}[${index}]`, {
      min: itemMin,
      max: itemMax,
      code,
    });
    if (unique && seen.has(item)) fail(code, `${label} cannot contain duplicates`);
    seen.add(item);
  }
  return array;
};

const assertCanonicalJsonValue = (value, label = "value", ancestors = new Set()) => {
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!NUMBER_IS_FINITE(value)) fail("NON_CANONICAL_JSON", `${label} must be finite`);
    return;
  }
  if (typeof value !== "object" || IS_PROXY(value)) {
    fail("NON_CANONICAL_JSON", `${label} is not canonical JSON data`);
  }
  if (ancestors.has(value)) fail("NON_CANONICAL_JSON", `${label} cannot be cyclic`);
  ancestors.add(value);
  try {
    if (ARRAY_IS_ARRAY(value)) {
      const array = requireDenseArray(value, label, "NON_CANONICAL_JSON");
      for (let index = 0; index < array.length; index += 1) {
        assertCanonicalJsonValue(array[index], `${label}[${index}]`, ancestors);
      }
      return;
    }
    const record = requirePlainRecord(value, label, { code: "NON_CANONICAL_JSON" });
    for (const key of Object.keys(record)) {
      assertCanonicalJsonValue(
        readDataProperty(record, key, label, "NON_CANONICAL_JSON"),
        `${label}.${key}`,
        ancestors,
      );
    }
  } finally {
    ancestors.delete(value);
  }
};

export const canonicalizeForgeJson = (value) => {
  assertCanonicalJsonValue(value);
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (ARRAY_IS_ARRAY(value)) {
    return `[${value.map((entry) => canonicalizeForgeJson(entry)).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort()
    .map(
      (key) =>
        `${JSON.stringify(key)}:${canonicalizeForgeJson(readDataProperty(value, key))}`,
    )
    .join(",")}}`;
};

export const sha256ForgeJson = (value) =>
  `sha256:${createHash("sha256").update(canonicalizeForgeJson(value), "utf8").digest("hex")}`;

const cloneCanonical = (value) => JSON.parse(canonicalizeForgeJson(value));

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

const sameStringArray = (left, right) =>
  left.length === right.length && left.every((value, index) => value === right[index]);

const edgeKey = (from, to) => `${from}->${to}`;

const compareCanonicalText = (left, right) => (left < right ? -1 : left > right ? 1 : 0);

const sortEdges = (edges) =>
  [...edges].sort((left, right) => {
    const fromDelta = FORGE_PHASES.indexOf(left.from) - FORGE_PHASES.indexOf(right.from);
    if (fromDelta !== 0) return fromDelta;
    return FORGE_PHASES.indexOf(left.to) - FORGE_PHASES.indexOf(right.to);
  });

const validateClassificationProjection = (classification) => {
  const code = "INVALID_CLASSIFICATION_PROJECTION";
  const value = requirePlainRecord(classification, "classification", {
    allowedKeys: CLASSIFICATION_KEYS,
    requiredKeys: CLASSIFICATION_KEYS,
    code,
  });
  const classificationId = requireString(readDataProperty(value, "classification_id"), "classification_id", {
    code,
  });
  const classificationHash = requireHash(
    readDataProperty(value, "classification_hash"),
    "classification_hash",
    code,
  );
  if (
    !CLASSIFICATION_ID_PATTERN.test(classificationId) ||
    classificationId !== `EWC-${classificationHash.slice("sha256:".length)}`
  ) {
    fail(code, "classification identity is not hash-bound");
  }
  const workClass = readDataProperty(value, "work_class");
  if (!WORK_CLASSES.has(workClass)) fail(code, "classification work_class is invalid");
  const requiredPhases = requireDenseArray(
    readDataProperty(value, "required_phases"),
    "classification.required_phases",
    code,
  );
  for (let index = 0; index < requiredPhases.length; index += 1) {
    requirePhase(requiredPhases[index], `classification.required_phases[${index}]`, code);
  }
  const allowedProjections = EXPECTED_PROJECTIONS[workClass];
  if (!allowedProjections.some((expected) => sameStringArray(requiredPhases, expected))) {
    fail(code, "classification required_phases do not match the exact F01 projection", {
      workClass,
      requiredPhases,
    });
  }
  return value;
};

export const compileForgePlan = ({ classification, classification_identity_context }) => {
  const value = validateClassificationProjection(classification);
  try {
    assertClassificationArtifactIntegrity(value, classification_identity_context);
  } catch (error) {
    fail(
      "CLASSIFICATION_INTEGRITY_FAILED",
      "F02 requires a hash-valid F01 classification artifact",
      { causeCode: error?.code ?? error?.name ?? "unknown" },
      { cause: error },
    );
  }

  const requiredPhases = [...readDataProperty(value, "required_phases")];
  const reachablePhases = new Set(["IDLE"]);
  for (const phase of requiredPhases) reachablePhases.add(phase);
  if (requiredPhases.length > 0) reachablePhases.add("I");

  const forwardEdges = [];
  if (requiredPhases.length > 0) {
    forwardEdges.push({ from: "IDLE", to: requiredPhases[0] });
    for (let index = 0; index < requiredPhases.length - 1; index += 1) {
      forwardEdges.push({ from: requiredPhases[index], to: requiredPhases[index + 1] });
    }
    if (!forwardEdges.some((edge) => edge.from === "I" && edge.to === "F")) {
      forwardEdges.push({ from: "I", to: "F" });
    }
  }

  const closeEdges = requiredPhases.includes("E") ? [{ from: "E", to: "IDLE" }] : [];
  const returnEdges = RETURN_EDGE_ROWS.filter(
    (edge) => reachablePhases.has(edge.from) && reachablePhases.has(edge.to),
  ).map((edge) => ({ ...edge }));

  const deduplicate = (edges) => {
    const seen = new Set();
    return sortEdges(
      edges.filter((edge) => {
        const key = edgeKey(edge.from, edge.to);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }),
    );
  };

  const semantic = {
    classification_id: readDataProperty(value, "classification_id"),
    classification_hash: readDataProperty(value, "classification_hash"),
    work_class: readDataProperty(value, "work_class"),
    required_phases: requiredPhases,
    reachable_phases: FORGE_PHASES.filter((phase) => reachablePhases.has(phase)),
    forward_edges: deduplicate(forwardEdges),
    return_edges: deduplicate(returnEdges),
    close_edges: deduplicate(closeEdges),
    stale_projection_rule: "RETURN_TARGET_INCLUSIVE",
  };
  return deepFreeze({ ...semantic, plan_hash: sha256ForgeJson(semantic) });
};

const planEdgeMap = (plan) => {
  const edges = new Map();
  for (const edge of plan.forward_edges) edges.set(edgeKey(edge.from, edge.to), "FORWARD");
  for (const edge of plan.return_edges) edges.set(edgeKey(edge.from, edge.to), "RETURN");
  for (const edge of plan.close_edges) edges.set(edgeKey(edge.from, edge.to), "CLOSE");
  return edges;
};

export const describeForgeTransition = (plan, fromPhase, toPhase) => {
  const from = requirePhase(fromPhase, "from_phase", "INVALID_TRANSITION_QUERY");
  const to = requirePhase(toPhase, "to_phase", "INVALID_TRANSITION_QUERY");
  const reachable = new Set(plan.reachable_phases);
  if (!reachable.has(from) || !reachable.has(to)) {
    return deepFreeze({
      legal: false,
      kind: null,
      from_phase: from,
      to_phase: to,
      code: "PHASE_NOT_REACHABLE_FOR_CLASSIFICATION",
    });
  }
  const kind = planEdgeMap(plan).get(edgeKey(from, to)) ?? null;
  return deepFreeze({
    legal: kind !== null,
    kind,
    from_phase: from,
    to_phase: to,
    code: kind === null ? "ILLEGAL_FORGE_TRANSITION" : null,
  });
};

export const isLegalForgeTransition = (plan, fromPhase, toPhase) =>
  describeForgeTransition(plan, fromPhase, toPhase).legal;

const validateHistoryEntry = (entry, index, code) => {
  const value = requirePlainRecord(entry, `phase_history[${index}]`, {
    allowedKeys: PHASE_HISTORY_KEYS,
    requiredKeys: PHASE_HISTORY_KEYS,
    code,
  });
  requirePhase(readDataProperty(value, "from"), `phase_history[${index}].from`, code);
  requirePhase(readDataProperty(value, "to"), `phase_history[${index}].to`, code);
  requireString(readDataProperty(value, "event_id"), `phase_history[${index}].event_id`, {
    min: 3,
    max: 128,
    code,
  });
  requireTimestamp(readDataProperty(value, "at"), `phase_history[${index}].at`, code);
  return value;
};

const validateStateShape = (state, { requireStateHash = true } = {}) => {
  const code = "INVALID_FORGE_STATE";
  const requiredKeys = requireStateHash ? STATE_KEYS : STATE_HASH_KEYS;
  const allowedKeys = requireStateHash ? STATE_KEYS : [...STATE_KEYS];
  const value = requirePlainRecord(state, "ForgeSessionState", {
    allowedKeys,
    requiredKeys,
    code,
  });
  requireString(readDataProperty(value, "session_id"), "session_id", { min: 3, max: 128, code });
  requireString(readDataProperty(value, "workspace_id"), "workspace_id", {
    min: 3,
    max: 128,
    code,
  });
  const revision = requireSafeRevision(readDataProperty(value, "revision"), "revision", code);
  const phase = requirePhase(readDataProperty(value, "phase"), "phase", code);
  const workClass = readDataProperty(value, "work_class");
  if (!WORK_CLASSES.has(workClass)) fail(code, "work_class is invalid");
  const status = readDataProperty(value, "status");
  if (!SESSION_STATUSES.has(status)) fail(code, "status is invalid");
  requireString(readDataProperty(value, "run_spec_id"), "run_spec_id", {
    min: 3,
    max: 128,
    code,
  });
  requireStringArray(readDataProperty(value, "hypothesis_revision_ids"), "hypothesis_revision_ids", {
    unique: true,
    itemMin: 3,
    itemMax: 128,
    code,
  });
  requireStringArray(readDataProperty(value, "artifact_ids"), "artifact_ids", {
    unique: true,
    itemMin: 3,
    itemMax: 128,
    code,
  });
  requireStringArray(readDataProperty(value, "open_blockers"), "open_blockers", { code });
  const history = requireDenseArray(readDataProperty(value, "phase_history"), "phase_history", code);
  history.forEach((entry, index) => validateHistoryEntry(entry, index, code));
  if (history.length > revision) fail(code, "phase_history cannot be longer than revision");
  if (history.length > 0 && readDataProperty(history.at(-1), "to") !== phase) {
    fail(code, "the last phase_history target must equal the current phase");
  }
  requireHash(readDataProperty(value, "policy_hash"), "policy_hash", code);
  requireHash(readDataProperty(value, "corpus_snapshot_hash"), "corpus_snapshot_hash", code);
  requireTimestamp(readDataProperty(value, "updated_at"), "updated_at", code);
  if (requireStateHash) requireHash(readDataProperty(value, "state_hash"), "state_hash", code);
  return value;
};

const selectKeys = (value, keys) =>
  Object.fromEntries(keys.map((key) => [key, cloneCanonical(readDataProperty(value, key))]));

export const computeForgeSessionStateHash = (state) => {
  const value = validateStateShape(state, { requireStateHash: false });
  return sha256ForgeJson(selectKeys(value, STATE_HASH_KEYS));
};

export const sealForgeSessionState = (state) => {
  const value = validateStateShape(state, { requireStateHash: false });
  const semantic = selectKeys(value, STATE_HASH_KEYS);
  return deepFreeze({ ...semantic, state_hash: sha256ForgeJson(semantic) });
};

export const assertForgeSessionStateIntegrity = (state) => {
  const value = validateStateShape(state);
  const expectedHash = sha256ForgeJson(selectKeys(value, STATE_HASH_KEYS));
  if (readDataProperty(value, "state_hash") !== expectedHash) {
    fail("FORGE_STATE_HASH_MISMATCH", "ForgeSessionState hash does not match its content", {
      expected: expectedHash,
      actual: readDataProperty(value, "state_hash"),
    });
  }
  return true;
};

const validateTransitionRequest = (request) => {
  const code = "INVALID_TRANSITION_REQUEST";
  const value = requirePlainRecord(request, "ForgeTransitionRequest", {
    allowedKeys: TRANSITION_REQUEST_KEYS,
    requiredKeys: TRANSITION_REQUEST_KEYS,
    code,
  });
  requireString(readDataProperty(value, "request_id"), "request_id", { min: 3, max: 128, code });
  requireString(readDataProperty(value, "session_id"), "session_id", { min: 3, max: 128, code });
  requireSafeRevision(readDataProperty(value, "expected_revision"), "expected_revision", code);
  requirePhase(readDataProperty(value, "from_phase"), "from_phase", code);
  requirePhase(readDataProperty(value, "to_phase"), "to_phase", code);
  const actor = requirePlainRecord(readDataProperty(value, "actor"), "actor", {
    allowedKeys: ACTOR_KEYS,
    requiredKeys: ACTOR_KEYS,
    code,
  });
  requireString(readDataProperty(actor, "actor_id"), "actor.actor_id", {
    min: 3,
    max: 128,
    code,
  });
  if (!ACTOR_TYPES.has(readDataProperty(actor, "actor_type"))) fail(code, "actor_type is invalid");
  requireString(readDataProperty(actor, "role"), "actor.role", { code });
  requireStringArray(readDataProperty(value, "artifact_receipt_ids"), "artifact_receipt_ids", {
    unique: true,
    itemMin: 3,
    itemMax: 128,
    code,
  });
  requireStringArray(readDataProperty(value, "gate_result_ids"), "gate_result_ids", {
    unique: true,
    itemMin: 3,
    itemMax: 128,
    code,
  });
  const humanDecisionId = readDataProperty(value, "human_decision_id");
  if (humanDecisionId !== null) {
    requireString(humanDecisionId, "human_decision_id", { min: 1, code });
  }
  requireString(readDataProperty(value, "reason"), "reason", { min: 1, code });
  requireString(readDataProperty(value, "idempotency_key"), "idempotency_key", { min: 8, code });
  requireTimestamp(readDataProperty(value, "requested_at"), "requested_at", code);
  return value;
};

const validateEvent = (event) => {
  const code = "INVALID_TRANSITION_EVENT";
  const value = requirePlainRecord(event, "transition event", {
    allowedKeys: EVENT_KEYS,
    requiredKeys: EVENT_KEYS,
    code,
  });
  requireString(readDataProperty(value, "event_id"), "event_id", { min: 3, max: 128, code });
  requireTimestamp(readDataProperty(value, "occurred_at"), "occurred_at", code);
  return value;
};

const requireNullableAdmissionIdentity = (value, idKey, hashKey, code) => {
  const id = readDataProperty(value, idKey, "durable transition admission", code);
  const hash = readDataProperty(value, hashKey, "durable transition admission", code);
  if (id === null || hash === null) {
    if (id !== null || hash !== null) {
      fail(code, `${idKey} and ${hashKey} must both be null or both be populated`);
    }
    return;
  }
  requireString(id, idKey, { min: 1, code });
  requireHash(hash, hashKey, code);
};

const requireCanonicalTextOrder = (values, label, code) => {
  for (let index = 1; index < values.length; index += 1) {
    if (compareCanonicalText(values[index - 1], values[index]) >= 0) {
      fail(code, `${label} must be unique and canonical-text-sorted`);
    }
  }
};

const validateDurableTransitionAdmission = (candidate, state, request) => {
  const code = "INVALID_TRANSITION_ADMISSION";
  const admission = requirePlainRecord(candidate, "durable transition admission", {
    allowedKeys: DURABLE_ADMISSION_KEYS,
    requiredKeys: DURABLE_ADMISSION_KEYS,
    code,
  });
  if (readDataProperty(admission, "admission_version") !== DURABLE_TRANSITION_ADMISSION_VERSION) {
    fail(code, "durable transition admission version is not supported");
  }
  if (readDataProperty(admission, "decision") !== "ADMIT") {
    fail(code, "durable transition admission decision must be ADMIT");
  }
  requireString(readDataProperty(admission, "session_id"), "admission.session_id", {
    min: 3,
    max: 128,
    code,
  });
  requireString(readDataProperty(admission, "request_id"), "admission.request_id", {
    min: 3,
    max: 128,
    code,
  });
  requireHash(readDataProperty(admission, "request_hash"), "admission.request_hash", code);
  requireString(
    readDataProperty(admission, "idempotency_key"),
    "admission.idempotency_key",
    { min: 8, code },
  );
  requireSafeRevision(
    readDataProperty(admission, "expected_revision"),
    "admission.expected_revision",
    code,
  );
  requirePhase(readDataProperty(admission, "from_phase"), "admission.from_phase", code);
  requirePhase(readDataProperty(admission, "to_phase"), "admission.to_phase", code);
  requireHash(
    readDataProperty(admission, "prior_state_hash"),
    "admission.prior_state_hash",
    code,
  );
  requireNullableAdmissionIdentity(
    admission,
    "idle_classification_id",
    "idle_classification_hash",
    code,
  );
  requireNullableAdmissionIdentity(
    admission,
    "phase_artifact_set_id",
    "phase_artifact_set_hash",
    code,
  );
  requireNullableAdmissionIdentity(
    admission,
    "human_decision_id",
    "human_decision_hash",
    code,
  );

  const idleClassificationId = readDataProperty(admission, "idle_classification_id");
  const idleClassificationHash = readDataProperty(admission, "idle_classification_hash");
  if (
    idleClassificationId !== null &&
    (!CLASSIFICATION_ID_PATTERN.test(idleClassificationId) ||
      idleClassificationId !==
        `EWC-${idleClassificationHash.slice("sha256:".length)}`)
  ) {
    fail(code, "idle classification identity is not hash-bound");
  }

  const receiptBindings = requireDenseArray(
    readDataProperty(admission, "receipt_bindings"),
    "admission.receipt_bindings",
    code,
  );
  if (receiptBindings.length === 0) {
    fail(code, "durable transition admission must contain receipt bindings");
  }
  const receiptIds = new Set();
  const receiptArtifactIds = new Set();
  const orderedReceiptIds = [];
  for (let index = 0; index < receiptBindings.length; index += 1) {
    const binding = requirePlainRecord(
      receiptBindings[index],
      `admission.receipt_bindings[${index}]`,
      {
        allowedKeys: ADMISSION_RECEIPT_BINDING_KEYS,
        requiredKeys: ADMISSION_RECEIPT_BINDING_KEYS,
        code,
      },
    );
    const receiptId = requireString(
      readDataProperty(binding, "receipt_id"),
      `admission.receipt_bindings[${index}].receipt_id`,
      { min: 3, max: 128, code },
    );
    const artifactId = requireString(
      readDataProperty(binding, "artifact_id"),
      `admission.receipt_bindings[${index}].artifact_id`,
      { min: 3, max: 128, code },
    );
    requireHash(
      readDataProperty(binding, "receipt_hash"),
      `admission.receipt_bindings[${index}].receipt_hash`,
      code,
    );
    requireHash(
      readDataProperty(binding, "content_hash"),
      `admission.receipt_bindings[${index}].content_hash`,
      code,
    );
    const schemaRef = readDataProperty(binding, "schema_ref");
    if (!(schemaRef === null || typeof schemaRef === "string")) {
      fail(code, `admission.receipt_bindings[${index}].schema_ref must be a string or null`);
    }
    if (receiptIds.has(receiptId) || receiptArtifactIds.has(artifactId)) {
      fail(code, "admission receipt and artifact bindings must be unique");
    }
    receiptIds.add(receiptId);
    receiptArtifactIds.add(artifactId);
    orderedReceiptIds.push(receiptId);
  }
  requireCanonicalTextOrder(orderedReceiptIds, "admission.receipt_bindings", code);

  const gateDecisions = requireDenseArray(
    readDataProperty(admission, "gate_decisions"),
    "admission.gate_decisions",
    code,
  );
  const gateIds = new Set();
  const orderedGateIds = [];
  for (let index = 0; index < gateDecisions.length; index += 1) {
    const decision = requirePlainRecord(
      gateDecisions[index],
      `admission.gate_decisions[${index}]`,
      {
        allowedKeys: ADMISSION_GATE_DECISION_KEYS,
        requiredKeys: ADMISSION_GATE_DECISION_KEYS,
        code,
      },
    );
    const gateId = requireString(
      readDataProperty(decision, "gate_id"),
      `admission.gate_decisions[${index}].gate_id`,
      { code },
    );
    requireHash(
      readDataProperty(decision, "decision_hash"),
      `admission.gate_decisions[${index}].decision_hash`,
      code,
    );
    if (!ADMITTED_GATE_STATUSES.has(readDataProperty(decision, "status"))) {
      fail(code, `admission.gate_decisions[${index}].status is not admitted`);
    }
    if (gateIds.has(gateId)) fail(code, "admission gate decision IDs must be unique");
    gateIds.add(gateId);
    orderedGateIds.push(gateId);
  }
  requireCanonicalTextOrder(orderedGateIds, "admission.gate_decisions", code);

  const artifactRetention = requireStringArray(
    readDataProperty(admission, "artifact_retention"),
    "admission.artifact_retention",
    { min: 1, unique: true, itemMin: 3, itemMax: 128, code },
  );
  requireCanonicalTextOrder(artifactRetention, "admission.artifact_retention", code);
  requireString(readDataProperty(admission, "admission_id"), "admission.admission_id", {
    min: 1,
    code,
  });
  requireHash(readDataProperty(admission, "admission_hash"), "admission.admission_hash", code);

  const semantic = selectKeys(admission, DURABLE_ADMISSION_SEMANTIC_KEYS);
  const expectedAdmissionHash = sha256ForgeJson(semantic);
  if (readDataProperty(admission, "admission_hash") !== expectedAdmissionHash) {
    fail("TRANSITION_ADMISSION_HASH_MISMATCH", "transition admission hash is invalid");
  }
  if (
    readDataProperty(admission, "admission_id") !==
    `FTA-${expectedAdmissionHash.slice("sha256:".length)}`
  ) {
    fail("TRANSITION_ADMISSION_ID_MISMATCH", "transition admission identity is not hash-bound");
  }

  const expectedRequestHash = sha256ForgeJson(request);
  if (
    readDataProperty(admission, "session_id") !== state.session_id ||
    readDataProperty(admission, "request_id") !== request.request_id ||
    readDataProperty(admission, "request_hash") !== expectedRequestHash ||
    readDataProperty(admission, "idempotency_key") !== request.idempotency_key ||
    readDataProperty(admission, "expected_revision") !== request.expected_revision ||
    readDataProperty(admission, "from_phase") !== request.from_phase ||
    readDataProperty(admission, "to_phase") !== request.to_phase ||
    readDataProperty(admission, "prior_state_hash") !== state.state_hash
  ) {
    fail(
      "TRANSITION_ADMISSION_BINDING_MISMATCH",
      "transition admission does not bind the original state and request",
    );
  }

  const expectedReceiptIds = [...request.artifact_receipt_ids].sort(compareCanonicalText);
  const expectedGateIds = [...request.gate_result_ids].sort(compareCanonicalText);
  const expectedRetention = [...receiptArtifactIds].sort(compareCanonicalText);
  const phaseArtifactSetId = readDataProperty(admission, "phase_artifact_set_id");
  const humanDecisionId = readDataProperty(admission, "human_decision_id");
  if (
    !sameStringArray(orderedReceiptIds, expectedReceiptIds) ||
    !sameStringArray(orderedGateIds, expectedGateIds) ||
    !sameStringArray(artifactRetention, expectedRetention) ||
    humanDecisionId !== request.human_decision_id ||
    (request.from_phase === "IDLE" &&
      (idleClassificationId === null || phaseArtifactSetId !== null)) ||
    (request.from_phase !== "IDLE" &&
      (idleClassificationId !== null || phaseArtifactSetId === null))
  ) {
    fail(
      "TRANSITION_ADMISSION_BINDING_MISMATCH",
      "transition admission closure does not match the original request",
    );
  }

  const retainedByState = new Set(state.artifact_ids);
  const artifactRetentionDelta = artifactRetention
    .filter((artifactId) => !retainedByState.has(artifactId))
    .sort(compareCanonicalText);
  return deepFreeze({
    admission_id: readDataProperty(admission, "admission_id"),
    admission_hash: readDataProperty(admission, "admission_hash"),
    artifact_retention_delta: artifactRetentionDelta,
  });
};

const validatePhaseArtifact = (artifact, label, code) => {
  const value = requirePlainRecord(artifact, label, {
    allowedKeys: PHASE_ARTIFACT_KEYS,
    requiredKeys: PHASE_ARTIFACT_KEYS,
    code,
  });
  requireString(readDataProperty(value, "artifact_id"), `${label}.artifact_id`, {
    min: 3,
    max: 128,
    code,
  });
  requireString(readDataProperty(value, "kind"), `${label}.kind`, { code });
  requireString(readDataProperty(value, "schema_ref"), `${label}.schema_ref`, { code });
  requireHash(readDataProperty(value, "content_hash"), `${label}.content_hash`, code);
  requireString(readDataProperty(value, "receipt_id"), `${label}.receipt_id`, {
    min: 3,
    max: 128,
    code,
  });
  if (!ARTIFACT_STATUSES.has(readDataProperty(value, "status"))) {
    fail(code, `${label}.status is invalid`);
  }
  return value;
};

const validatePhaseArtifactSet = (phaseSet, { requireSetHash = true } = {}) => {
  const code = "INVALID_PHASE_ARTIFACT_SET";
  const requiredKeys = requireSetHash ? PHASE_SET_KEYS : PHASE_SET_HASH_KEYS;
  const value = requirePlainRecord(phaseSet, "PhaseArtifactSet", {
    allowedKeys: PHASE_SET_KEYS,
    requiredKeys,
    code,
  });
  requireString(readDataProperty(value, "set_id"), "set_id", { min: 3, max: 128, code });
  requireString(readDataProperty(value, "session_id"), "session_id", { min: 3, max: 128, code });
  requirePhase(readDataProperty(value, "phase"), "phase", code);
  const required = requireDenseArray(
    readDataProperty(value, "required_artifacts"),
    "required_artifacts",
    code,
  );
  if (required.length === 0) fail(code, "required_artifacts must not be empty");
  const optional = requireDenseArray(
    readDataProperty(value, "optional_artifacts"),
    "optional_artifacts",
    code,
  );
  const artifactIds = new Set();
  for (const [label, artifacts] of [
    ["required_artifacts", required],
    ["optional_artifacts", optional],
  ]) {
    artifacts.forEach((artifact, index) => {
      const valid = validatePhaseArtifact(artifact, `${label}[${index}]`, code);
      const artifactId = readDataProperty(valid, "artifact_id");
      if (artifactIds.has(artifactId)) fail(code, "artifact IDs must be unique within a phase set");
      artifactIds.add(artifactId);
    });
  }
  if (typeof readDataProperty(value, "complete") !== "boolean") {
    fail(code, "complete must be boolean");
  }
  requireStringArray(readDataProperty(value, "missing_kinds"), "missing_kinds", {
    unique: true,
    code,
  });
  requireTimestamp(readDataProperty(value, "validated_at"), "validated_at", code);
  if (requireSetHash) requireHash(readDataProperty(value, "set_hash"), "set_hash", code);
  return value;
};

export const computePhaseArtifactSetHash = (phaseSet) => {
  const value = validatePhaseArtifactSet(phaseSet, { requireSetHash: false });
  return sha256ForgeJson(selectKeys(value, PHASE_SET_HASH_KEYS));
};

export const sealPhaseArtifactSet = (phaseSet) => {
  const value = validatePhaseArtifactSet(phaseSet, { requireSetHash: false });
  const semantic = selectKeys(value, PHASE_SET_HASH_KEYS);
  return deepFreeze({ ...semantic, set_hash: sha256ForgeJson(semantic) });
};

const phaseSetSort = (left, right) => {
  const phaseDelta = FORGE_PHASES.indexOf(left.phase) - FORGE_PHASES.indexOf(right.phase);
  if (phaseDelta !== 0) return phaseDelta;
  return compareCanonicalText(left.set_id, right.set_id);
};

const assertPhaseReachableForPlan = (phase, plan, subject, details = {}) => {
  if (!plan.reachable_phases.includes(phase)) {
    fail(
      "PHASE_NOT_REACHABLE_FOR_CLASSIFICATION",
      `${subject} is not reachable for the sealed classification`,
      {
        ...details,
        phase,
        classificationId: plan.classification_id,
        workClass: plan.work_class,
      },
    );
  }
};

const validatePhaseArtifactSets = (
  phaseSets,
  state,
  plan,
  { additionalRetainedArtifactIds = [] } = {},
) => {
  const code = "INVALID_PHASE_ARTIFACT_SET";
  const values = requireDenseArray(phaseSets, "phase_artifact_sets", code);
  const setIds = new Set();
  const stateArtifactIds = new Set([...state.artifact_ids, ...additionalRetainedArtifactIds]);
  const normalized = values.map((phaseSet) => {
    const value = validatePhaseArtifactSet(phaseSet);
    const expectedSetHash = sha256ForgeJson(selectKeys(value, PHASE_SET_HASH_KEYS));
    if (value.set_hash !== expectedSetHash) {
      fail("PHASE_ARTIFACT_SET_HASH_MISMATCH", "PhaseArtifactSet hash does not match its content", {
        setId: value.set_id,
        expected: expectedSetHash,
        actual: value.set_hash,
      });
    }
    if (value.session_id !== state.session_id) {
      fail("PHASE_ARTIFACT_SESSION_MISMATCH", "phase artifact set belongs to another session", {
        setId: value.set_id,
        expectedSessionId: state.session_id,
        actualSessionId: value.session_id,
      });
    }
    assertPhaseReachableForPlan(value.phase, plan, "PhaseArtifactSet.phase", {
      setId: value.set_id,
    });
    if (setIds.has(value.set_id)) fail(code, "phase set IDs must be unique");
    setIds.add(value.set_id);
    for (const artifact of [...value.required_artifacts, ...value.optional_artifacts]) {
      if (!stateArtifactIds.has(artifact.artifact_id)) {
        fail(
          "PHASE_ARTIFACT_NOT_IN_STATE",
          "phase artifact must be retained in ForgeSessionState.artifact_ids",
          { setId: value.set_id, artifactId: artifact.artifact_id },
        );
      }
    }
    return cloneCanonical(value);
  });
  return normalized.sort(phaseSetSort);
};

const stalePhasesFrom = (targetPhase, plan) => {
  const index = EXECUTION_PHASE_INDEX.get(targetPhase);
  if (index === undefined) fail("INVALID_RETURN_TARGET", "return target must be an execution phase");
  const reachable = new Set(plan.reachable_phases);
  return FORGE_EXECUTION_PHASES.slice(index).filter((phase) => reachable.has(phase));
};

const makeStaleProjection = ({ source, event, fromPhase, toPhase }) => {
  const identity = {
    event_id: event.event_id,
    source_set_id: source.set_id,
    source_set_hash: source.set_hash,
    transition_from: fromPhase,
    transition_to: toPhase,
  };
  const projectionDigest = sha256ForgeJson(identity).slice("sha256:".length);
  const staleArtifact = (artifact) => ({ ...cloneCanonical(artifact), status: "STALE" });
  const semantic = {
    set_id: `PAS-STALE-${projectionDigest}`,
    session_id: source.session_id,
    phase: source.phase,
    required_artifacts: source.required_artifacts.map(staleArtifact),
    optional_artifacts: source.optional_artifacts.map(staleArtifact),
    complete: false,
    missing_kinds: [...source.missing_kinds],
    validated_at: event.occurred_at,
  };
  const projected = { ...semantic, set_hash: sha256ForgeJson(semantic) };
  return {
    projected,
    supersession: {
      phase: source.phase,
      source_set_id: source.set_id,
      source_set_hash: source.set_hash,
      projection_set_id: projected.set_id,
      projection_set_hash: projected.set_hash,
    },
  };
};

const projectReturnStaleness = ({ phaseSets, event, fromPhase, toPhase, plan }) => {
  const stalePhases = stalePhasesFrom(toPhase, plan);
  const stalePhaseSet = new Set(stalePhases);
  const current = [];
  const superseded = [];
  const staleArtifactIds = new Set();
  for (const phaseSet of phaseSets) {
    if (!stalePhaseSet.has(phaseSet.phase)) {
      current.push(cloneCanonical(phaseSet));
      continue;
    }
    const projection = makeStaleProjection({
      source: phaseSet,
      event,
      fromPhase,
      toPhase,
    });
    current.push(projection.projected);
    superseded.push(projection.supersession);
    for (const artifact of [
      ...projection.projected.required_artifacts,
      ...projection.projected.optional_artifacts,
    ]) {
      staleArtifactIds.add(artifact.artifact_id);
    }
  }
  return {
    phase_artifact_sets: current.sort(phaseSetSort),
    superseded_phase_artifact_sets: superseded.sort((left, right) => {
      const phaseDelta = FORGE_PHASES.indexOf(left.phase) - FORGE_PHASES.indexOf(right.phase);
      if (phaseDelta !== 0) return phaseDelta;
      return compareCanonicalText(left.source_set_id, right.source_set_id);
    }),
    stale_artifact_ids: [...staleArtifactIds].sort(compareCanonicalText),
    stale_phases: stalePhases,
  };
};

const unchangedStaleness = (phaseSets) => ({
  phase_artifact_sets: phaseSets.map(cloneCanonical),
  superseded_phase_artifact_sets: [],
  stale_artifact_ids: [],
  stale_phases: [],
});

const reduceForgeTransitionInternal = (
  {
    current_state,
    transition_request,
    classification,
    classification_identity_context,
    phase_artifact_sets = [],
    event,
  },
  admission = undefined,
) => {
  assertForgeSessionStateIntegrity(current_state);
  const state = cloneCanonical(current_state);
  const request = validateTransitionRequest(transition_request);
  const acceptedEvent = validateEvent(event);
  const admittedTransition =
    admission === undefined
      ? null
      : validateDurableTransitionAdmission(admission, state, request);
  if (
    compareRfc3339(acceptedEvent.occurred_at, state.updated_at, "INVALID_TRANSITION_EVENT") <= 0
  ) {
    fail(
      "INVALID_TRANSITION_EVENT",
      "transition event occurred_at must be strictly later than state.updated_at",
      { occurredAt: acceptedEvent.occurred_at, updatedAt: state.updated_at },
    );
  }
  const plan = compileForgePlan({ classification, classification_identity_context });

  if (!TRANSITIONABLE_STATUSES.has(state.status)) {
    fail("FORGE_SESSION_NOT_TRANSITIONABLE", "session status does not permit a phase transition", {
      status: state.status,
    });
  }
  if (state.work_class !== plan.work_class) {
    fail("CLASSIFICATION_STATE_MISMATCH", "session work_class does not match classification", {
      stateWorkClass: state.work_class,
      classificationWorkClass: plan.work_class,
    });
  }
  assertPhaseReachableForPlan(state.phase, plan, "ForgeSessionState.phase", {
    sessionId: state.session_id,
  });
  if (request.session_id !== state.session_id) {
    fail("SESSION_MISMATCH", "transition request belongs to another session");
  }
  if (request.expected_revision !== state.revision) {
    fail("STALE_REVISION", "transition request expected_revision is not current", {
      expectedRevision: request.expected_revision,
      currentRevision: state.revision,
    });
  }
  if (request.from_phase !== state.phase) {
    fail("FROM_PHASE_MISMATCH", "transition request from_phase is not current", {
      requestedFrom: request.from_phase,
      currentPhase: state.phase,
    });
  }
  if (state.revision === Number.MAX_SAFE_INTEGER) {
    fail("REVISION_EXHAUSTED", "ForgeSessionState revision cannot be incremented");
  }

  const transition = describeForgeTransition(plan, request.from_phase, request.to_phase);
  if (!transition.legal) {
    fail(transition.code, "requested FORGE phase edge is not legal", {
      fromPhase: request.from_phase,
      toPhase: request.to_phase,
      workClass: state.work_class,
    });
  }

  const phaseSets =
    admittedTransition === null
      ? validatePhaseArtifactSets(phase_artifact_sets, state, plan)
      : validatePhaseArtifactSets(phase_artifact_sets, state, plan, {
          additionalRetainedArtifactIds: admittedTransition.artifact_retention_delta,
        });
  const staleness =
    transition.kind === "RETURN"
      ? projectReturnStaleness({
          phaseSets,
          event: acceptedEvent,
          fromPhase: request.from_phase,
          toPhase: request.to_phase,
          plan,
        })
      : unchangedStaleness(phaseSets);

  const nextStateSemantic = {
    ...selectKeys(state, STATE_HASH_KEYS),
    revision: state.revision + 1,
    phase: request.to_phase,
    status: transition.kind === "CLOSE" ? "COMPLETED" : "ACTIVE",
    phase_history: [
      ...state.phase_history.map(cloneCanonical),
      {
        from: request.from_phase,
        to: request.to_phase,
        event_id: acceptedEvent.event_id,
        at: acceptedEvent.occurred_at,
      },
    ],
    updated_at: acceptedEvent.occurred_at,
  };
  if (admittedTransition !== null) {
    nextStateSemantic.artifact_ids = [
      ...state.artifact_ids,
      ...admittedTransition.artifact_retention_delta,
    ];
  }
  const nextState = {
    ...nextStateSemantic,
    state_hash: sha256ForgeJson(nextStateSemantic),
  };
  validateStateShape(nextState);

  const transitionSemantic = {
    request_id: request.request_id,
    request_hash: sha256ForgeJson(request),
    event_id: acceptedEvent.event_id,
    session_id: state.session_id,
    from_phase: request.from_phase,
    to_phase: request.to_phase,
    kind: transition.kind,
    prior_revision: state.revision,
    current_revision: nextState.revision,
    prior_state_hash: state.state_hash,
    current_state_hash: nextState.state_hash,
    plan_hash: plan.plan_hash,
    current_phase_set_hashes: staleness.phase_artifact_sets.map((phaseSet) => phaseSet.set_hash),
    stale_projection_rule:
      transition.kind === "RETURN" ? "RETURN_TARGET_INCLUSIVE" : "NOT_APPLICABLE",
    stale_phases: staleness.stale_phases,
    stale_artifact_ids: staleness.stale_artifact_ids,
  };
  if (admittedTransition !== null) {
    transitionSemantic.admission_id = admittedTransition.admission_id;
    transitionSemantic.admission_hash = admittedTransition.admission_hash;
    transitionSemantic.artifact_retention_delta =
      admittedTransition.artifact_retention_delta.map((artifactId) => artifactId);
  }
  const transitionRecord = {
    ...transitionSemantic,
    transition_hash: sha256ForgeJson(transitionSemantic),
  };

  return deepFreeze({
    state: nextState,
    transition: transitionRecord,
    phase_artifact_sets: staleness.phase_artifact_sets,
    superseded_phase_artifact_sets: staleness.superseded_phase_artifact_sets,
  });
};

export const reduceForgeTransition = (input) => reduceForgeTransitionInternal(input);

export const reduceAdmittedForgeTransition = (candidate) => {
  const code = "INVALID_ADMITTED_TRANSITION_INPUT";
  const input = requirePlainRecord(candidate, "admitted transition input", {
    allowedKeys: [
      "current_state",
      "transition_request",
      "classification",
      "classification_identity_context",
      "phase_artifact_sets",
      "event",
      "admission",
    ],
    requiredKeys: [
      "current_state",
      "transition_request",
      "classification",
      "event",
      "admission",
    ],
    code,
  });
  return reduceForgeTransitionInternal(
    {
      current_state: readDataProperty(input, "current_state", "admitted transition input", code),
      transition_request: readDataProperty(
        input,
        "transition_request",
        "admitted transition input",
        code,
      ),
      classification: readDataProperty(
        input,
        "classification",
        "admitted transition input",
        code,
      ),
      classification_identity_context: OBJECT_HAS_OWN(input, "classification_identity_context")
        ? readDataProperty(
            input,
            "classification_identity_context",
            "admitted transition input",
            code,
          )
        : undefined,
      phase_artifact_sets: OBJECT_HAS_OWN(input, "phase_artifact_sets")
        ? readDataProperty(input, "phase_artifact_sets", "admitted transition input", code)
        : [],
      event: readDataProperty(input, "event", "admitted transition input", code),
    },
    readDataProperty(input, "admission", "admitted transition input", code),
  );
};

export const replayForgeTransitionEvents = ({
  initial_state,
  transitions,
  classification,
  classification_identity_context,
  phase_artifact_sets = [],
}) => {
  assertForgeSessionStateIntegrity(initial_state);
  const initialState = cloneCanonical(initial_state);
  const plan = compileForgePlan({ classification, classification_identity_context });
  if (initialState.work_class !== plan.work_class) {
    fail("CLASSIFICATION_STATE_MISMATCH", "session work_class does not match classification", {
      stateWorkClass: initialState.work_class,
      classificationWorkClass: plan.work_class,
    });
  }
  assertPhaseReachableForPlan(initialState.phase, plan, "ForgeSessionState.phase", {
    sessionId: initialState.session_id,
  });
  const entries = requireDenseArray(transitions, "transitions", "INVALID_REPLAY_INPUT");
  let state = initialState;
  let phaseSets = validatePhaseArtifactSets(phase_artifact_sets, initialState, plan);
  const records = [];
  const superseded = [];
  for (let index = 0; index < entries.length; index += 1) {
    const entry = requirePlainRecord(entries[index], `transitions[${index}]`, {
      allowedKeys: ["transition_request", "event"],
      requiredKeys: ["transition_request", "event"],
      code: "INVALID_REPLAY_INPUT",
    });
    const result = reduceForgeTransition({
      current_state: state,
      transition_request: readDataProperty(entry, "transition_request"),
      classification,
      classification_identity_context,
      phase_artifact_sets: phaseSets,
      event: readDataProperty(entry, "event"),
    });
    state = result.state;
    phaseSets = result.phase_artifact_sets;
    records.push(result.transition);
    superseded.push(...result.superseded_phase_artifact_sets);
  }
  return deepFreeze({
    state,
    phase_artifact_sets: phaseSets,
    transitions: records,
    superseded_phase_artifact_sets: superseded,
    replay_hash: sha256ForgeJson({
      plan_hash: plan.plan_hash,
      state_hash: state.state_hash,
      phase_set_hashes: phaseSets.map((phaseSet) => phaseSet.set_hash),
      transition_hashes: records.map((record) => record.transition_hash),
    }),
  });
};

export const replayAdmittedForgeTransitionEvents = (candidate) => {
  const input = requirePlainRecord(candidate, "admitted replay input", {
    allowedKeys: [
      "initial_state",
      "transitions",
      "classification",
      "classification_identity_context",
      "phase_artifact_sets",
    ],
    requiredKeys: ["initial_state", "transitions", "classification"],
    code: "INVALID_REPLAY_INPUT",
  });
  const initial_state = readDataProperty(
    input,
    "initial_state",
    "admitted replay input",
    "INVALID_REPLAY_INPUT",
  );
  const transitions = readDataProperty(
    input,
    "transitions",
    "admitted replay input",
    "INVALID_REPLAY_INPUT",
  );
  const classification = readDataProperty(
    input,
    "classification",
    "admitted replay input",
    "INVALID_REPLAY_INPUT",
  );
  const classification_identity_context = OBJECT_HAS_OWN(
    input,
    "classification_identity_context",
  )
    ? readDataProperty(
        input,
        "classification_identity_context",
        "admitted replay input",
        "INVALID_REPLAY_INPUT",
      )
    : undefined;
  const phase_artifact_sets = OBJECT_HAS_OWN(input, "phase_artifact_sets")
    ? readDataProperty(
        input,
        "phase_artifact_sets",
        "admitted replay input",
        "INVALID_REPLAY_INPUT",
      )
    : [];
  assertForgeSessionStateIntegrity(initial_state);
  const initialState = cloneCanonical(initial_state);
  const plan = compileForgePlan({ classification, classification_identity_context });
  if (initialState.work_class !== plan.work_class) {
    fail("CLASSIFICATION_STATE_MISMATCH", "session work_class does not match classification", {
      stateWorkClass: initialState.work_class,
      classificationWorkClass: plan.work_class,
    });
  }
  assertPhaseReachableForPlan(initialState.phase, plan, "ForgeSessionState.phase", {
    sessionId: initialState.session_id,
  });
  const entries = requireDenseArray(transitions, "transitions", "INVALID_REPLAY_INPUT");
  let state = initialState;
  let phaseSets =
    entries.length === 0
      ? validatePhaseArtifactSets(phase_artifact_sets, initialState, plan)
      : phase_artifact_sets;
  const records = [];
  const superseded = [];
  for (let index = 0; index < entries.length; index += 1) {
    const entry = requirePlainRecord(entries[index], `transitions[${index}]`, {
      allowedKeys: ["transition_request", "admission", "event"],
      requiredKeys: ["transition_request", "admission", "event"],
      code: "INVALID_REPLAY_INPUT",
    });
    const result = reduceAdmittedForgeTransition({
      current_state: state,
      transition_request: readDataProperty(entry, "transition_request"),
      classification,
      classification_identity_context,
      phase_artifact_sets: phaseSets,
      event: readDataProperty(entry, "event"),
      admission: readDataProperty(entry, "admission"),
    });
    state = result.state;
    phaseSets = result.phase_artifact_sets;
    records.push(result.transition);
    superseded.push(...result.superseded_phase_artifact_sets);
  }
  return deepFreeze({
    state,
    phase_artifact_sets: phaseSets,
    transitions: records,
    superseded_phase_artifact_sets: superseded,
    replay_hash: sha256ForgeJson({
      plan_hash: plan.plan_hash,
      state_hash: state.state_hash,
      phase_set_hashes: phaseSets.map((phaseSet) => phaseSet.set_hash),
      transition_hashes: records.map((record) => record.transition_hash),
    }),
  });
};
