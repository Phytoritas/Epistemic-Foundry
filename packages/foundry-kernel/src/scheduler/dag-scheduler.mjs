/**
 * Deterministic DAG scheduling, execution leases, retries, and bounded loops.
 *
 * Scheduler leases coordinate node/resource ownership only. They never mint or
 * replace E03 CapabilityLease authority. A caller must present the result of
 * capability/policy/approval checks as admission evidence, and the scheduler
 * binds those evidence IDs into its execution lease.
 */

import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

const ARRAY_IS_ARRAY = Array.isArray;
const ARRAY_PROTOTYPE = Array.prototype;
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
const NODE_ID_PATTERN = /^[a-z][a-z0-9_]*$/u;
const RESOURCE_PATTERN = /^(?:exclusive|quota):[a-zA-Z0-9][a-zA-Z0-9_.:-]*$/u;
const RFC3339_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:[Zz]|([+-])(\d{2}):(\d{2}))$/u;

const NODE_KEYS = OBJECT_FREEZE([
  "node_id",
  "purpose",
  "executor_type",
  "executor_ref",
  "input_schema_ref",
  "output_schema_ref",
  "depends_on",
  "read_scope",
  "write_scope",
  "capabilities",
  "model_tier",
  "timeout_seconds",
  "max_attempts",
  "failure_policy",
  "acceptance_checks",
  "resource_dependencies",
  "determinism_class",
  "idempotency_key_fields",
  "loop_contract_ref",
  "expected_effects",
  "required_policy_checks",
]);
const LOOP_KEYS = OBJECT_FREEZE([
  "loop_id",
  "workflow_id",
  "entry_node_id",
  "exit_node_id",
  "state_artifact_id",
  "convergence_metric",
  "convergence_predicate",
  "max_iterations",
  "max_cost_units",
  "max_wall_seconds",
  "dry_rounds_required",
  "dedupe_key",
  "seen_set_scope",
  "on_nonconvergence",
  "contract_hash",
]);
const LOOP_HASH_KEYS = OBJECT_FREEZE(LOOP_KEYS.filter((key) => key !== "contract_hash"));
const BUDGET_KEYS = OBJECT_FREEZE([
  "budget_id",
  "enforcement",
  "hard_limits",
  "soft_cost_currency",
  "soft_cost_amount",
  "metering_authority",
  "breach_policy",
  "created_at",
  "budget_hash",
]);
const BUDGET_HASH_KEYS = OBJECT_FREEZE(BUDGET_KEYS.filter((key) => key !== "budget_hash"));
const HARD_LIMIT_KEYS = OBJECT_FREEZE([
  "tokens",
  "calls",
  "wall_seconds",
  "concurrency",
  "storage_bytes",
  "network_bytes",
]);
const RESERVATION_KEYS = OBJECT_FREEZE([
  "tokens",
  "calls",
  "wall_seconds",
  "storage_bytes",
  "network_bytes",
]);
const ADMISSION_KEYS = OBJECT_FREEZE([
  "input_artifacts_resolved",
  "capability_authorized",
  "approval_authorized",
  "policy_checks_passed",
  "blocking_gate_ids",
  "capability_lease_ids",
]);
const LEASE_KEYS = OBJECT_FREEZE([
  "lease_id",
  "run_id",
  "node_id",
  "attempt",
  "owner_id",
  "issued_at",
  "expires_at",
  "fencing_token",
  "resource_claims",
  "capability_lease_ids",
  "idempotency_hash",
  "acquisition_request_hash",
  "input_hash",
  "lease_hash",
]);
const LEASE_HASH_KEYS = OBJECT_FREEZE(LEASE_KEYS.filter((key) => key !== "lease_hash"));

const EXECUTOR_TYPES = new Set([
  "deterministic",
  "llm",
  "parser",
  "retrieval",
  "sandbox",
  "subworkflow",
  "policy",
  "human_gate",
]);
const MODEL_TIERS = new Set(["deterministic", "economy", "balanced", "frontier"]);
const FAILURE_POLICIES = new Set([
  "fail_run",
  "mark_partial",
  "skip_downstream",
  "escalate",
]);
const DETERMINISM_CLASSES = new Set([
  "deterministic",
  "seeded_nondeterministic",
  "provider_nondeterministic",
]);
const BUDGET_ENFORCEMENTS = new Set([
  "HARD_METERED",
  "HARD_PREALLOCATED",
  "SOFT_ESTIMATE",
  "UNMETERED",
]);
const BUDGET_BREACH_POLICIES = new Set([
  "CANCEL",
  "PAUSE_AND_ESCALATE",
  "MARK_PARTIAL",
  "WARN",
]);
const LOOP_SCOPES = new Set(["run", "workflow", "project"]);
const LOOP_NONCONVERGENCE = new Set(["BLOCK", "PARTIAL", "ESCALATE", "FAIL"]);

export const SCHEDULER_ATTEMPT_STATES = OBJECT_FREEZE([
  "PENDING",
  "LEASED",
  "RUNNING",
  "RECONCILING",
  "SUCCEEDED",
  "FAILED_RETRYABLE",
  "FAILED_FINAL",
  "BLOCKED",
  "SPEC_GAP",
  "CANCELLED",
]);
const TERMINAL_ATTEMPT_STATES = new Set([
  "SUCCEEDED",
  "FAILED_RETRYABLE",
  "FAILED_FINAL",
  "BLOCKED",
  "SPEC_GAP",
  "CANCELLED",
]);
const ACTIVE_ATTEMPT_STATES = new Set(["LEASED", "RUNNING"]);

export const RETRYABLE_FAILURE_CODES = OBJECT_FREEZE([
  "NETWORK_INTERRUPTION_BEFORE_RECEIPT",
  "PROVIDER_TIMEOUT",
  "TEMPORARY_PARSER_UNAVAILABLE",
  "TEMPORARY_SERVICE_UNAVAILABLE",
  "TRANSIENT_RATE_LIMIT",
]);
const RETRYABLE_FAILURE_SET = new Set(RETRYABLE_FAILURE_CODES);
const SPEC_GAP_FAILURE_CODES = new Set(["SPEC_GAP"]);

export class SchedulerError extends Error {
  constructor(code, message, details = undefined, options = undefined) {
    super(message, options);
    this.name = "SchedulerError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(cloneCanonical(details));
  }
}

const fail = (code, message, details, options) => {
  throw new SchedulerError(code, message, details, options);
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

const readDataProperty = (value, key, label = "object", code = "INVALID_INPUT") => {
  const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
  if (
    descriptor === undefined ||
    !descriptor.enumerable ||
    !OBJECT_HAS_OWN(descriptor, "value")
  ) {
    fail(code, `${label}.${key} must be an enumerable own data property`);
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
  if (
    !ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== ARRAY_PROTOTYPE
  ) {
    fail(code, `${label} must be a plain array`);
  }
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

const requireString = (
  value,
  label,
  { min = 1, max = 4096, pattern = undefined, code = "INVALID_INPUT" } = {},
) => {
  if (
    typeof value !== "string" ||
    value.length < min ||
    value.length > max ||
    !hasOnlyUnicodeScalars(value) ||
    (pattern !== undefined && !pattern.test(value))
  ) {
    fail(code, `${label} must be a valid bounded string`);
  }
  return value;
};

const requireNullableString = (value, label, code = "INVALID_INPUT") =>
  value === null ? null : requireString(value, label, { code });

const requireHash = (value, label, code = "INVALID_INPUT") =>
  requireString(value, label, { pattern: SHA256_PATTERN, code });

const isLeapYear = (year) => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

const daysInMonth = (year, month) => {
  if (month === 2) return isLeapYear(year) ? 29 : 28;
  return month === 4 || month === 6 || month === 9 || month === 11 ? 30 : 31;
};

const daysBeforeYear = (year) =>
  365 * year +
  Math.floor((year + 3) / 4) -
  Math.floor((year + 99) / 100) +
  Math.floor((year + 399) / 400);

const daysBeforeMonth = (year, month) => {
  const cumulative = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  return cumulative[month - 1] + (month > 2 && isLeapYear(year) ? 1 : 0);
};

const parseRfc3339 = (value) => {
  if (typeof value !== "string") return null;
  const match = RFC3339_PATTERN.exec(value);
  if (match === null || match[0].length !== value.length) return null;

  let year = Number(match[1]);
  let month = Number(match[2]);
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

  let utcMinuteOfDay = hour * 60 + minute;
  if (match[8] === "+") {
    utcMinuteOfDay -= offsetHour * 60 + offsetMinute;
  } else if (match[8] === "-") {
    utcMinuteOfDay += offsetHour * 60 + offsetMinute;
  }
  if (utcMinuteOfDay < 0) {
    utcMinuteOfDay += 1_440;
    day -= 1;
    if (day === 0) {
      month -= 1;
      if (month === 0) {
        year -= 1;
        month = 12;
      }
      day = daysInMonth(year, month);
    }
  } else if (utcMinuteOfDay >= 1_440) {
    utcMinuteOfDay -= 1_440;
    day += 1;
    if (day > daysInMonth(year, month)) {
      day = 1;
      month += 1;
      if (month === 13) {
        year += 1;
        month = 1;
      }
    }
  }

  const utcMinute = utcMinuteOfDay % 60;
  const utcHour = (utcMinuteOfDay - utcMinute) / 60;
  if (
    second === 60 &&
    (utcHour !== 23 || utcMinute !== 59 || day !== daysInMonth(year, month))
  ) {
    return null;
  }
  const ordinalDay = daysBeforeYear(year) + daysBeforeMonth(year, month) + day - 1;
  const wholeSecond =
    BigInt(ordinalDay) * 86_400n + BigInt(utcHour * 3_600 + utcMinute * 60 + second);
  return OBJECT_FREEZE({
    tuple: OBJECT_FREEZE([year, month, day, utcHour, utcMinute, second]),
    wholeSecond,
    fraction,
  });
};

const compareFractions = (left, right) => {
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const leftDigit = index < left.length ? left.charCodeAt(index) : 48;
    const rightDigit = index < right.length ? right.charCodeAt(index) : 48;
    if (leftDigit < rightDigit) return -1;
    if (leftDigit > rightDigit) return 1;
  }
  return 0;
};

const compareParsedTimestamps = (left, right) => {
  for (let index = 0; index < left.tuple.length; index += 1) {
    if (left.tuple[index] < right.tuple[index]) return -1;
    if (left.tuple[index] > right.tuple[index]) return 1;
  }
  return compareFractions(left.fraction, right.fraction);
};

const parsedTimestamp = (value, label, code = "INVALID_INPUT") => {
  const candidate = requireString(value, label, { code });
  const parsed = parseRfc3339(candidate);
  if (parsed === null) fail(code, `${label} must be an RFC 3339 timestamp`);
  return parsed;
};

const requireTimestamp = (value, label, code = "INVALID_INPUT") => {
  const candidate = requireString(value, label, { code });
  if (parseRfc3339(candidate) === null) fail(code, `${label} must be an RFC 3339 timestamp`);
  return candidate;
};

const compareTimestamps = (left, right, code = "INVALID_INPUT") =>
  compareParsedTimestamps(
    parsedTimestamp(left, "left timestamp", code),
    parsedTimestamp(right, "right timestamp", code),
  );

const timestampSpanExceedsSeconds = (later, earlier, maximumSeconds, code) => {
  const parsedLater = parsedTimestamp(later, "later timestamp", code);
  const parsedEarlier = parsedTimestamp(earlier, "earlier timestamp", code);
  const sameWholeTuple = parsedLater.tuple.every(
    (entry, index) => entry === parsedEarlier.tuple[index],
  );
  let wholeDifference = parsedLater.wholeSecond - parsedEarlier.wholeSecond;
  if (parsedEarlier.tuple[5] === 60 && !sameWholeTuple) wholeDifference += 1n;
  const maximum = BigInt(maximumSeconds);
  if (wholeDifference > maximum) return true;
  if (wholeDifference < maximum) return false;
  return compareFractions(parsedLater.fraction, parsedEarlier.fraction) > 0;
};

const requireBoolean = (value, label, code = "INVALID_INPUT") => {
  if (typeof value !== "boolean") fail(code, `${label} must be boolean`);
  return value;
};

const requireSafeInteger = (
  value,
  label,
  { minimum = 0, maximum = Number.MAX_SAFE_INTEGER, code = "INVALID_INPUT" } = {},
) => {
  if (
    !NUMBER_IS_SAFE_INTEGER(value) ||
    Object.is(value, -0) ||
    value < minimum ||
    value > maximum
  ) {
    fail(code, `${label} must be a safe integer in range`);
  }
  return value;
};

const requireFiniteNumber = (
  value,
  label,
  { minimum = 0, maximum = Number.MAX_VALUE, code = "INVALID_INPUT" } = {},
) => {
  if (
    typeof value !== "number" ||
    !NUMBER_IS_FINITE(value) ||
    Object.is(value, -0) ||
    value < minimum ||
    value > maximum
  ) {
    fail(code, `${label} must be a finite number in range`);
  }
  return value;
};

const requireEnum = (value, values, label, code = "INVALID_INPUT") => {
  if (!values.has(value)) fail(code, `${label} is not a canonical value`);
  return value;
};

const requireStringArray = (
  value,
  label,
  { min = 0, unique = true, pattern = undefined, sort = false, code = "INVALID_INPUT" } = {},
) => {
  const array = requireDenseArray(value, label, code);
  if (array.length < min) fail(code, `${label} must contain at least ${min} item(s)`);
  const seen = new Set();
  const normalized = array.map((item, index) => {
    const text = requireString(item, `${label}[${index}]`, { pattern, code });
    if (unique && seen.has(text)) fail(code, `${label} cannot contain duplicates`);
    seen.add(text);
    return text;
  });
  return sort ? normalized.sort(compareText) : normalized;
};

const assertCanonicalJsonValue = (value, label = "value", ancestors = new Set()) => {
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!NUMBER_IS_FINITE(value) || Object.is(value, -0)) {
      fail("NON_CANONICAL_JSON", `${label} must be finite and must not be negative zero`);
    }
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
      array.forEach((entry, index) =>
        assertCanonicalJsonValue(entry, `${label}[${index}]`, ancestors),
      );
      return;
    }
    const record = requirePlainRecord(value, label, { code: "NON_CANONICAL_JSON" });
    for (const key of Object.keys(record)) {
      assertCanonicalJsonValue(readDataProperty(record, key, label), `${label}.${key}`, ancestors);
    }
  } finally {
    ancestors.delete(value);
  }
};

export const canonicalizeSchedulerJson = (value) => {
  assertCanonicalJsonValue(value);
  if (value === null) return "null";
  if (["string", "number", "boolean"].includes(typeof value)) return JSON.stringify(value);
  if (ARRAY_IS_ARRAY(value)) {
    return `[${value.map((entry) => canonicalizeSchedulerJson(entry)).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort(compareText)
    .map(
      (key) =>
        `${JSON.stringify(key)}:${canonicalizeSchedulerJson(readDataProperty(value, key))}`,
    )
    .join(",")}}`;
};

export const sha256SchedulerJson = (value) =>
  `sha256:${createHash("sha256").update(canonicalizeSchedulerJson(value), "utf8").digest("hex")}`;

const cloneCanonical = (value) => JSON.parse(canonicalizeSchedulerJson(value));

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

const compareText = (left, right) => (left < right ? -1 : left > right ? 1 : 0);
const selectKeys = (value, keys) =>
  Object.fromEntries(keys.map((key) => [key, cloneCanonical(readDataProperty(value, key))]));

const normalizeNode = (candidate, index) => {
  const code = "NODE_CONTRACT_INVALID";
  const node = requirePlainRecord(candidate, `nodes[${index}]`, {
    allowedKeys: NODE_KEYS,
    requiredKeys: NODE_KEYS,
    code,
  });
  const nodeId = requireString(readDataProperty(node, "node_id"), `nodes[${index}].node_id`, {
    pattern: NODE_ID_PATTERN,
    code,
  });
  const timeoutSeconds = requireSafeInteger(
    readDataProperty(node, "timeout_seconds"),
    `${nodeId}.timeout_seconds`,
    { minimum: 1, code },
  );
  const maxAttempts = requireSafeInteger(
    readDataProperty(node, "max_attempts"),
    `${nodeId}.max_attempts`,
    { minimum: 1, maximum: 10, code },
  );
  const loopRef = readDataProperty(node, "loop_contract_ref");
  if (loopRef !== null) requireString(loopRef, `${nodeId}.loop_contract_ref`, { code });
  return {
    node_id: nodeId,
    purpose: requireString(readDataProperty(node, "purpose"), `${nodeId}.purpose`, { code }),
    executor_type: requireEnum(
      readDataProperty(node, "executor_type"),
      EXECUTOR_TYPES,
      `${nodeId}.executor_type`,
      code,
    ),
    executor_ref: requireString(readDataProperty(node, "executor_ref"), `${nodeId}.executor_ref`, {
      code,
    }),
    input_schema_ref: requireString(
      readDataProperty(node, "input_schema_ref"),
      `${nodeId}.input_schema_ref`,
      { code },
    ),
    output_schema_ref: requireString(
      readDataProperty(node, "output_schema_ref"),
      `${nodeId}.output_schema_ref`,
      { code },
    ),
    depends_on: requireStringArray(readDataProperty(node, "depends_on"), `${nodeId}.depends_on`, {
      pattern: NODE_ID_PATTERN,
      sort: true,
      code,
    }),
    read_scope: requireStringArray(readDataProperty(node, "read_scope"), `${nodeId}.read_scope`, {
      sort: true,
      code,
    }),
    write_scope: requireStringArray(readDataProperty(node, "write_scope"), `${nodeId}.write_scope`, {
      sort: true,
      code,
    }),
    capabilities: requireStringArray(
      readDataProperty(node, "capabilities"),
      `${nodeId}.capabilities`,
      { sort: true, code },
    ),
    model_tier: requireEnum(
      readDataProperty(node, "model_tier"),
      MODEL_TIERS,
      `${nodeId}.model_tier`,
      code,
    ),
    timeout_seconds: timeoutSeconds,
    max_attempts: maxAttempts,
    failure_policy: requireEnum(
      readDataProperty(node, "failure_policy"),
      FAILURE_POLICIES,
      `${nodeId}.failure_policy`,
      code,
    ),
    acceptance_checks: requireStringArray(
      readDataProperty(node, "acceptance_checks"),
      `${nodeId}.acceptance_checks`,
      { min: 1, sort: true, code },
    ),
    resource_dependencies: requireStringArray(
      readDataProperty(node, "resource_dependencies"),
      `${nodeId}.resource_dependencies`,
      { pattern: RESOURCE_PATTERN, sort: true, code },
    ),
    determinism_class: requireEnum(
      readDataProperty(node, "determinism_class"),
      DETERMINISM_CLASSES,
      `${nodeId}.determinism_class`,
      code,
    ),
    idempotency_key_fields: requireStringArray(
      readDataProperty(node, "idempotency_key_fields"),
      `${nodeId}.idempotency_key_fields`,
      { sort: true, code },
    ),
    loop_contract_ref: loopRef,
    expected_effects: requireStringArray(
      readDataProperty(node, "expected_effects"),
      `${nodeId}.expected_effects`,
      { sort: true, code },
    ),
    required_policy_checks: requireStringArray(
      readDataProperty(node, "required_policy_checks"),
      `${nodeId}.required_policy_checks`,
      { sort: true, code },
    ),
  };
};

const normalizeLoopContract = (candidate, index, { requireHash: withHash = true } = {}) => {
  const code = "LOOP_CONTRACT_INVALID";
  const requiredKeys = withHash ? LOOP_KEYS : LOOP_HASH_KEYS;
  const loop = requirePlainRecord(candidate, `loop_contracts[${index}]`, {
    allowedKeys: LOOP_KEYS,
    requiredKeys,
    code,
  });
  const normalized = {
    loop_id: requireString(readDataProperty(loop, "loop_id"), `loop_contracts[${index}].loop_id`, {
      code,
    }),
    workflow_id: requireString(
      readDataProperty(loop, "workflow_id"),
      `loop_contracts[${index}].workflow_id`,
      { code },
    ),
    entry_node_id: requireString(
      readDataProperty(loop, "entry_node_id"),
      `loop_contracts[${index}].entry_node_id`,
      { pattern: NODE_ID_PATTERN, code },
    ),
    exit_node_id: requireString(
      readDataProperty(loop, "exit_node_id"),
      `loop_contracts[${index}].exit_node_id`,
      { pattern: NODE_ID_PATTERN, code },
    ),
    state_artifact_id: requireString(
      readDataProperty(loop, "state_artifact_id"),
      `loop_contracts[${index}].state_artifact_id`,
      { code },
    ),
    convergence_metric: requireString(
      readDataProperty(loop, "convergence_metric"),
      `loop_contracts[${index}].convergence_metric`,
      { code },
    ),
    convergence_predicate: requireString(
      readDataProperty(loop, "convergence_predicate"),
      `loop_contracts[${index}].convergence_predicate`,
      { code },
    ),
    max_iterations: requireSafeInteger(
      readDataProperty(loop, "max_iterations"),
      `loop_contracts[${index}].max_iterations`,
      { minimum: 1, code },
    ),
    max_cost_units: requireFiniteNumber(
      readDataProperty(loop, "max_cost_units"),
      `loop_contracts[${index}].max_cost_units`,
      { code },
    ),
    max_wall_seconds: requireSafeInteger(
      readDataProperty(loop, "max_wall_seconds"),
      `loop_contracts[${index}].max_wall_seconds`,
      { minimum: 1, code },
    ),
    dry_rounds_required: requireSafeInteger(
      readDataProperty(loop, "dry_rounds_required"),
      `loop_contracts[${index}].dry_rounds_required`,
      { minimum: 1, code },
    ),
    dedupe_key: requireString(
      readDataProperty(loop, "dedupe_key"),
      `loop_contracts[${index}].dedupe_key`,
      { code },
    ),
    seen_set_scope: requireEnum(
      readDataProperty(loop, "seen_set_scope"),
      LOOP_SCOPES,
      `loop_contracts[${index}].seen_set_scope`,
      code,
    ),
    on_nonconvergence: requireEnum(
      readDataProperty(loop, "on_nonconvergence"),
      LOOP_NONCONVERGENCE,
      `loop_contracts[${index}].on_nonconvergence`,
      code,
    ),
  };
  if (withHash) {
    const actual = requireHash(
      readDataProperty(loop, "contract_hash"),
      `loop_contracts[${index}].contract_hash`,
      code,
    );
    const expected = sha256SchedulerJson(normalized);
    if (actual !== expected) {
      fail("LOOP_CONTRACT_HASH_MISMATCH", "LoopContract hash does not match canonical fields", {
        actual,
        expected,
        loop_id: normalized.loop_id,
      });
    }
    return { ...normalized, contract_hash: actual };
  }
  return normalized;
};

export const sealLoopContract = (candidate) => {
  const normalized = normalizeLoopContract(candidate, 0, { requireHash: false });
  return deepFreeze({ ...normalized, contract_hash: sha256SchedulerJson(normalized) });
};

const normalizeResourceCapacities = (candidate, nodes) => {
  const code = "RESOURCE_CAPACITY_INVALID";
  const capacities = requirePlainRecord(candidate, "resource_capacities", { code });
  const normalized = {};
  for (const key of Object.keys(capacities).sort(compareText)) {
    requireString(key, `resource_capacities.${key}`, { pattern: RESOURCE_PATTERN, code });
    const capacity = requireSafeInteger(
      readDataProperty(capacities, key, "resource_capacities", code),
      `resource_capacities.${key}`,
      { minimum: 1, code },
    );
    if (key.startsWith("exclusive:") && capacity !== 1) {
      fail(code, "exclusive resources must have capacity exactly one", { resource: key });
    }
    normalized[key] = capacity;
  }
  const used = new Set(nodes.flatMap((node) => node.resource_dependencies));
  for (const resource of used) {
    if (resource.startsWith("quota:") && !OBJECT_HAS_OWN(normalized, resource)) {
      fail("RESOURCE_CAPACITY_MISSING", "quota resources require an explicit bounded capacity", {
        resource,
      });
    }
    if (resource.startsWith("exclusive:") && !OBJECT_HAS_OWN(normalized, resource)) {
      normalized[resource] = 1;
    }
  }
  for (const resource of Object.keys(normalized)) {
    if (!used.has(resource)) {
      fail(code, "resource capacity is declared but no node uses it", { resource });
    }
  }
  return Object.fromEntries(Object.entries(normalized).sort(([left], [right]) => compareText(left, right)));
};

const stronglyConnectedComponents = (nodes) => {
  const byId = new Map(nodes.map((node) => [node.node_id, node]));
  let index = 0;
  const indices = new Map();
  const lowLinks = new Map();
  const stack = [];
  const onStack = new Set();
  const components = [];

  const visit = (nodeId) => {
    indices.set(nodeId, index);
    lowLinks.set(nodeId, index);
    index += 1;
    stack.push(nodeId);
    onStack.add(nodeId);
    for (const dependency of byId.get(nodeId).depends_on) {
      if (!indices.has(dependency)) {
        visit(dependency);
        lowLinks.set(nodeId, Math.min(lowLinks.get(nodeId), lowLinks.get(dependency)));
      } else if (onStack.has(dependency)) {
        lowLinks.set(nodeId, Math.min(lowLinks.get(nodeId), indices.get(dependency)));
      }
    }
    if (lowLinks.get(nodeId) === indices.get(nodeId)) {
      const component = [];
      while (stack.length > 0) {
        const member = stack.pop();
        onStack.delete(member);
        component.push(member);
        if (member === nodeId) break;
      }
      components.push(component.sort(compareText));
    }
  };
  for (const nodeId of [...byId.keys()].sort(compareText)) {
    if (!indices.has(nodeId)) visit(nodeId);
  }
  return components;
};

const validateLoopsAndOrder = (workflowId, nodes, loops) => {
  const byId = new Map(nodes.map((node) => [node.node_id, node]));
  const loopsById = new Map();
  for (const loop of loops) {
    if (loopsById.has(loop.loop_id)) fail("DUPLICATE_LOOP_ID", "loop_id must be unique", { loop_id: loop.loop_id });
    if (loop.workflow_id !== workflowId) {
      fail("LOOP_WORKFLOW_MISMATCH", "LoopContract workflow does not match the compiled workflow", {
        loop_id: loop.loop_id,
      });
    }
    loopsById.set(loop.loop_id, loop);
  }

  const components = stronglyConnectedComponents(nodes);
  const componentByNode = new Map();
  components.forEach((component, componentIndex) =>
    component.forEach((nodeId) => componentByNode.set(nodeId, componentIndex)),
  );
  const usedLoops = new Set();
  const loopGroups = [];
  for (const component of components) {
    if (component.length <= 1) continue;
    const refs = new Set(component.map((nodeId) => byId.get(nodeId).loop_contract_ref));
    if (refs.size !== 1 || refs.has(null)) {
      fail("DAG_CYCLE_WITHOUT_LOOP_CONTRACT", "every node in a cycle must reference one LoopContract", {
        nodes: component,
      });
    }
    const loopId = [...refs][0];
    const loop = loopsById.get(loopId);
    if (loop === undefined) {
      fail("LOOP_CONTRACT_NOT_FOUND", "cycle references an unavailable LoopContract", {
        loop_id: loopId,
        nodes: component,
      });
    }
    if (!component.includes(loop.entry_node_id) || !component.includes(loop.exit_node_id)) {
      fail("LOOP_BOUNDARY_MISMATCH", "LoopContract entry and exit must belong to its cycle", {
        loop_id: loopId,
        nodes: component,
      });
    }
    if (!byId.get(loop.entry_node_id).depends_on.includes(loop.exit_node_id)) {
      fail("LOOP_BACKEDGE_MISSING", "loop entry must declare its exit as the bounded back-edge", {
        loop_id: loopId,
      });
    }
    usedLoops.add(loopId);
    const members = new Set(component);
    const adjacency = new Map(component.map((nodeId) => [nodeId, new Set()]));
    const indegree = new Map(component.map((nodeId) => [nodeId, 0]));
    for (const nodeId of component) {
      for (const dependency of byId.get(nodeId).depends_on) {
        if (!members.has(dependency)) continue;
        if (nodeId === loop.entry_node_id && dependency === loop.exit_node_id) continue;
        if (!adjacency.get(dependency).has(nodeId)) {
          adjacency.get(dependency).add(nodeId);
          indegree.set(nodeId, indegree.get(nodeId) + 1);
        }
      }
    }
    const internalQueue = [...indegree.entries()]
      .filter(([, count]) => count === 0)
      .map(([nodeId]) => nodeId)
      .sort(compareText);
    const orderedMembers = [];
    while (internalQueue.length > 0) {
      const current = internalQueue.shift();
      orderedMembers.push(current);
      for (const target of [...adjacency.get(current)].sort(compareText)) {
        indegree.set(target, indegree.get(target) - 1);
        if (indegree.get(target) === 0) {
          internalQueue.push(target);
          internalQueue.sort(compareText);
        }
      }
    }
    if (
      orderedMembers.length !== component.length ||
      orderedMembers[0] !== loop.entry_node_id ||
      orderedMembers.at(-1) !== loop.exit_node_id
    ) {
      fail(
        "LOOP_CONTRACT_INCOMPLETE",
        "removing the declared back-edge must yield an entry-to-exit DAG",
        { loop_id: loopId, nodes: component },
      );
    }
    loopGroups.push({
      loop_id: loopId,
      entry_node_id: loop.entry_node_id,
      exit_node_id: loop.exit_node_id,
      node_ids: orderedMembers,
      contract_hash: loop.contract_hash,
    });
  }
  for (const loop of loops) {
    if (!usedLoops.has(loop.loop_id)) {
      fail("LOOP_CONTRACT_UNUSED", "LoopContract must resolve exactly one real cycle", {
        loop_id: loop.loop_id,
      });
    }
  }
  for (const node of nodes) {
    if (node.loop_contract_ref !== null && !usedLoops.has(node.loop_contract_ref)) {
      fail("LOOP_CONTRACT_NOT_CYCLIC", "node references a LoopContract outside a cycle", {
        node_id: node.node_id,
        loop_id: node.loop_contract_ref,
      });
    }
  }

  const componentEdges = new Map(components.map((_, index) => [index, new Set()]));
  const indegree = new Map(components.map((_, index) => [index, 0]));
  for (const node of nodes) {
    const consumer = componentByNode.get(node.node_id);
    for (const dependency of node.depends_on) {
      const producer = componentByNode.get(dependency);
      if (producer !== consumer && !componentEdges.get(producer).has(consumer)) {
        componentEdges.get(producer).add(consumer);
        indegree.set(consumer, indegree.get(consumer) + 1);
      }
    }
  }
  const componentKey = (componentIndex) => components[componentIndex][0];
  const queue = [...indegree.entries()]
    .filter(([, count]) => count === 0)
    .map(([componentIndex]) => componentIndex)
    .sort((left, right) => compareText(componentKey(left), componentKey(right)));
  const componentOrder = [];
  while (queue.length > 0) {
    const current = queue.shift();
    componentOrder.push(current);
    for (const target of [...componentEdges.get(current)].sort((left, right) =>
      compareText(componentKey(left), componentKey(right)),
    )) {
      indegree.set(target, indegree.get(target) - 1);
      if (indegree.get(target) === 0) {
        queue.push(target);
        queue.sort((left, right) => compareText(componentKey(left), componentKey(right)));
      }
    }
  }
  if (componentOrder.length !== components.length) {
    fail("DAG_CONDENSATION_FAILED", "condensed workflow graph is not acyclic");
  }
  const groupByMember = new Map();
  for (const group of loopGroups) group.node_ids.forEach((nodeId) => groupByMember.set(nodeId, group));
  const topologicalOrder = componentOrder.flatMap((componentIndex) => {
    const component = components[componentIndex];
    return component.length > 1 ? groupByMember.get(component[0]).node_ids : component;
  });
  return {
    loop_groups: loopGroups.sort((left, right) => compareText(left.loop_id, right.loop_id)),
    topological_order: topologicalOrder,
  };
};

export const compileSchedulerPlan = (candidate) => {
  const code = "SCHEDULER_PLAN_INVALID";
  const input = requirePlainRecord(candidate, "scheduler plan input", {
    allowedKeys: ["workflow_id", "nodes", "loop_contracts", "resource_capacities"],
    requiredKeys: ["workflow_id", "nodes", "loop_contracts", "resource_capacities"],
    code,
  });
  const workflowId = requireString(readDataProperty(input, "workflow_id"), "workflow_id", { code });
  const nodeInputs = requireDenseArray(readDataProperty(input, "nodes"), "nodes", code);
  if (nodeInputs.length === 0) fail(code, "workflow must contain at least one node");
  const nodes = nodeInputs.map((node, index) => normalizeNode(node, index)).sort((left, right) =>
    compareText(left.node_id, right.node_id),
  );
  const byId = new Map();
  for (const node of nodes) {
    if (byId.has(node.node_id)) fail("DUPLICATE_NODE_ID", "node_id must be unique", { node_id: node.node_id });
    byId.set(node.node_id, node);
  }
  for (const node of nodes) {
    for (const dependency of node.depends_on) {
      if (dependency === node.node_id) {
        fail("SELF_DEPENDENCY", "a node cannot depend on itself", { node_id: node.node_id });
      }
      if (!byId.has(dependency)) {
        fail("UNKNOWN_DEPENDENCY", "node dependency does not resolve", {
          node_id: node.node_id,
          dependency,
        });
      }
    }
  }
  const loopInputs = requireDenseArray(readDataProperty(input, "loop_contracts"), "loop_contracts", code);
  const loops = loopInputs
    .map((loop, index) => normalizeLoopContract(loop, index))
    .sort((left, right) => compareText(left.loop_id, right.loop_id));
  const capacities = normalizeResourceCapacities(
    readDataProperty(input, "resource_capacities"),
    nodes,
  );
  const topology = validateLoopsAndOrder(workflowId, nodes, loops);
  const semantic = {
    workflow_id: workflowId,
    nodes,
    loop_contracts: loops,
    resource_capacities: capacities,
    topological_order: topology.topological_order,
    loop_groups: topology.loop_groups,
  };
  return deepFreeze({ ...semantic, plan_hash: sha256SchedulerJson(semantic) });
};

export const assertSchedulerPlanIntegrity = (candidate) => {
  const plan = requirePlainRecord(candidate, "SchedulerPlan", {
    allowedKeys: [
      "workflow_id",
      "nodes",
      "loop_contracts",
      "resource_capacities",
      "topological_order",
      "loop_groups",
      "plan_hash",
    ],
    requiredKeys: [
      "workflow_id",
      "nodes",
      "loop_contracts",
      "resource_capacities",
      "topological_order",
      "loop_groups",
      "plan_hash",
    ],
    code: "SCHEDULER_PLAN_INTEGRITY_FAILED",
  });
  const rebuilt = compileSchedulerPlan({
    workflow_id: readDataProperty(plan, "workflow_id"),
    nodes: readDataProperty(plan, "nodes"),
    loop_contracts: readDataProperty(plan, "loop_contracts"),
    resource_capacities: readDataProperty(plan, "resource_capacities"),
  });
  if (canonicalizeSchedulerJson(plan) !== canonicalizeSchedulerJson(rebuilt)) {
    fail("SCHEDULER_PLAN_INTEGRITY_FAILED", "SchedulerPlan does not match canonical compilation");
  }
  return plan;
};

const normalizeHardLimits = (candidate, code) => {
  const limits = requirePlainRecord(candidate, "hard_limits", {
    allowedKeys: HARD_LIMIT_KEYS,
    requiredKeys: HARD_LIMIT_KEYS,
    code,
  });
  return Object.fromEntries(
    HARD_LIMIT_KEYS.map((key) => {
      const value = readDataProperty(limits, key, "hard_limits", code);
      return [
        key,
        value === null
          ? null
          : requireSafeInteger(value, `hard_limits.${key}`, { minimum: 0, code }),
      ];
    }),
  );
};

const normalizeBudgetEnvelope = (candidate, { requireHash: withHash = true } = {}) => {
  const code = "BUDGET_ENVELOPE_INVALID";
  const budget = requirePlainRecord(candidate, "BudgetEnvelope", {
    allowedKeys: BUDGET_KEYS,
    requiredKeys: withHash ? BUDGET_KEYS : BUDGET_HASH_KEYS,
    code,
  });
  const enforcement = requireEnum(
    readDataProperty(budget, "enforcement"),
    BUDGET_ENFORCEMENTS,
    "enforcement",
    code,
  );
  const normalized = {
    budget_id: requireString(readDataProperty(budget, "budget_id"), "budget_id", {
      min: 3,
      max: 128,
      code,
    }),
    enforcement,
    hard_limits: normalizeHardLimits(readDataProperty(budget, "hard_limits"), code),
    soft_cost_currency: requireNullableString(
      readDataProperty(budget, "soft_cost_currency"),
      "soft_cost_currency",
      code,
    ),
    soft_cost_amount:
      readDataProperty(budget, "soft_cost_amount") === null
        ? null
        : requireFiniteNumber(readDataProperty(budget, "soft_cost_amount"), "soft_cost_amount", {
            code,
          }),
    metering_authority: requireNullableString(
      readDataProperty(budget, "metering_authority"),
      "metering_authority",
      code,
    ),
    breach_policy: requireEnum(
      readDataProperty(budget, "breach_policy"),
      BUDGET_BREACH_POLICIES,
      "breach_policy",
      code,
    ),
    created_at: requireTimestamp(readDataProperty(budget, "created_at"), "created_at", code),
  };
  if (["HARD_METERED", "HARD_PREALLOCATED"].includes(enforcement)) {
    if (normalized.metering_authority === null) {
      fail(code, "hard budget enforcement requires a metering authority");
    }
    if (HARD_LIMIT_KEYS.every((key) => normalized.hard_limits[key] === null)) {
      fail(code, "hard budget enforcement requires at least one hard limit");
    }
  }
  if (enforcement === "UNMETERED" && HARD_LIMIT_KEYS.some((key) => normalized.hard_limits[key] !== null)) {
    fail(code, "UNMETERED budgets cannot imply hard limits");
  }
  if (withHash) {
    const actual = requireHash(readDataProperty(budget, "budget_hash"), "budget_hash", code);
    const expected = sha256SchedulerJson(normalized);
    if (actual !== expected) {
      fail("BUDGET_HASH_MISMATCH", "BudgetEnvelope hash does not match canonical fields", {
        actual,
        expected,
      });
    }
    return { ...normalized, budget_hash: actual };
  }
  return normalized;
};

export const sealBudgetEnvelope = (candidate) => {
  const normalized = normalizeBudgetEnvelope(candidate, { requireHash: false });
  return deepFreeze({ ...normalized, budget_hash: sha256SchedulerJson(normalized) });
};

const normalizeReservation = (candidate) => {
  const code = "BUDGET_RESERVATION_INVALID";
  const reservation = requirePlainRecord(candidate, "budget_reservation", {
    allowedKeys: RESERVATION_KEYS,
    requiredKeys: RESERVATION_KEYS,
    code,
  });
  return Object.fromEntries(
    RESERVATION_KEYS.map((key) => [
      key,
      requireSafeInteger(readDataProperty(reservation, key), `budget_reservation.${key}`, {
        minimum: 0,
        code,
      }),
    ]),
  );
};

const normalizeAdmission = (candidate, node) => {
  const code = "ADMISSION_EVIDENCE_INVALID";
  const admission = requirePlainRecord(candidate, "admission", {
    allowedKeys: ADMISSION_KEYS,
    requiredKeys: ADMISSION_KEYS,
    code,
  });
  const normalized = {
    input_artifacts_resolved: requireBoolean(
      readDataProperty(admission, "input_artifacts_resolved"),
      "admission.input_artifacts_resolved",
      code,
    ),
    capability_authorized: requireBoolean(
      readDataProperty(admission, "capability_authorized"),
      "admission.capability_authorized",
      code,
    ),
    approval_authorized: requireBoolean(
      readDataProperty(admission, "approval_authorized"),
      "admission.approval_authorized",
      code,
    ),
    policy_checks_passed: requireBoolean(
      readDataProperty(admission, "policy_checks_passed"),
      "admission.policy_checks_passed",
      code,
    ),
    blocking_gate_ids: requireStringArray(
      readDataProperty(admission, "blocking_gate_ids"),
      "admission.blocking_gate_ids",
      { sort: true, code },
    ),
    capability_lease_ids: requireStringArray(
      readDataProperty(admission, "capability_lease_ids"),
      "admission.capability_lease_ids",
      { sort: true, code },
    ),
  };
  if (!normalized.input_artifacts_resolved) fail("INPUT_ARTIFACTS_UNRESOLVED", "node inputs do not resolve");
  if (!normalized.capability_authorized) fail("CAPABILITY_NOT_AUTHORIZED", "capability policy denied node execution");
  if (!normalized.approval_authorized) fail("APPROVAL_NOT_AUTHORIZED", "approval policy denied node execution");
  if (!normalized.policy_checks_passed) fail("POLICY_CHECK_FAILED", "required policy checks did not pass");
  if (normalized.blocking_gate_ids.length > 0) {
    fail("BLOCKING_GATE_PRESENT", "a non-waivable gate blocks node execution", {
      gate_ids: normalized.blocking_gate_ids,
    });
  }
  if (node.capabilities.length > 0 && normalized.capability_lease_ids.length === 0) {
    fail("CAPABILITY_LEASE_EVIDENCE_MISSING", "capability-bearing node requires external lease evidence");
  }
  return normalized;
};

const normalizeIdempotencyValues = (candidate, node) => {
  const code = "IDEMPOTENCY_BINDING_INVALID";
  const values = requirePlainRecord(candidate, "idempotency_values", {
    allowedKeys: node.idempotency_key_fields,
    requiredKeys: node.idempotency_key_fields,
    code,
  });
  const normalized = {};
  for (const key of node.idempotency_key_fields) {
    const value = readDataProperty(values, key, "idempotency_values", code);
    assertCanonicalJsonValue(value, `idempotency_values.${key}`);
    normalized[key] = cloneCanonical(value);
  }
  return normalized;
};

const normalizeLease = (candidate) => {
  const code = "SCHEDULER_LEASE_INVALID";
  const lease = requirePlainRecord(candidate, "SchedulerLease", {
    allowedKeys: LEASE_KEYS,
    requiredKeys: LEASE_KEYS,
    code,
  });
  const normalized = {
    lease_id: requireString(readDataProperty(lease, "lease_id"), "lease_id", { code }),
    run_id: requireString(readDataProperty(lease, "run_id"), "run_id", { code }),
    node_id: requireString(readDataProperty(lease, "node_id"), "node_id", {
      pattern: NODE_ID_PATTERN,
      code,
    }),
    attempt: requireSafeInteger(readDataProperty(lease, "attempt"), "attempt", {
      minimum: 1,
      maximum: 10,
      code,
    }),
    owner_id: requireString(readDataProperty(lease, "owner_id"), "owner_id", { code }),
    issued_at: requireTimestamp(readDataProperty(lease, "issued_at"), "issued_at", code),
    expires_at: requireTimestamp(readDataProperty(lease, "expires_at"), "expires_at", code),
    fencing_token: requireSafeInteger(readDataProperty(lease, "fencing_token"), "fencing_token", {
      minimum: 1,
      code,
    }),
    resource_claims: requireStringArray(
      readDataProperty(lease, "resource_claims"),
      "resource_claims",
      { pattern: /^(?:node:[a-z][a-z0-9_]*|(?:exclusive|quota):[a-zA-Z0-9][a-zA-Z0-9_.:-]*)$/u, sort: true, code },
    ),
    capability_lease_ids: requireStringArray(
      readDataProperty(lease, "capability_lease_ids"),
      "capability_lease_ids",
      { sort: true, code },
    ),
    idempotency_hash: requireHash(readDataProperty(lease, "idempotency_hash"), "idempotency_hash", code),
    acquisition_request_hash: requireHash(
      readDataProperty(lease, "acquisition_request_hash"),
      "acquisition_request_hash",
      code,
    ),
    input_hash: requireHash(readDataProperty(lease, "input_hash"), "input_hash", code),
  };
  if (compareTimestamps(normalized.expires_at, normalized.issued_at, code) <= 0) {
    fail(code, "scheduler lease must expire after issuance");
  }
  const actual = requireHash(readDataProperty(lease, "lease_hash"), "lease_hash", code);
  const expected = sha256SchedulerJson(normalized);
  if (actual !== expected) {
    fail("SCHEDULER_LEASE_HASH_MISMATCH", "scheduler lease hash does not match canonical fields", {
      actual,
      expected,
    });
  }
  return { ...normalized, lease_hash: actual };
};

const sealLease = (semantic) => deepFreeze({ ...semantic, lease_hash: sha256SchedulerJson(semantic) });

const makeEmptyUsage = () => Object.fromEntries(RESERVATION_KEYS.map((key) => [key, 0]));

const attemptSnapshot = (attempt) => deepFreeze(cloneCanonical(attempt));

class DagScheduler {
  #runId;
  #plan;
  #nodes;
  #budget;
  #usage = makeEmptyUsage();
  #attempts = new Map();
  #activeLeases = new Map();
  #resourceOwners = new Map();
  #resourceHeads = new Map();
  #nodeHeads = new Map();
  #fencingCounter = 0;
  #idempotencyBindings = new Map();
  #loopStates = new Map();
  #commands = [];

  constructor({ run_id: runId, plan, budget_envelope: budget }) {
    this.#runId = requireString(runId, "run_id", { code: "SCHEDULER_CREATE_INVALID" });
    assertSchedulerPlanIntegrity(plan);
    this.#plan = deepFreeze(cloneCanonical(plan));
    this.#nodes = new Map(this.#plan.nodes.map((node) => [node.node_id, node]));
    this.#budget = deepFreeze(normalizeBudgetEnvelope(budget));
    for (const nodeId of this.#nodes.keys()) this.#attempts.set(nodeId, []);
    for (const loop of this.#plan.loop_contracts) {
      this.#loopStates.set(loop.loop_id, {
        loop_id: loop.loop_id,
        status: "PENDING",
        iterations: 0,
        total_cost_units: 0,
        started_at: null,
        last_round_at: null,
        dry_rounds: 0,
        seen_item_keys: [],
        nonconvergence_action: null,
      });
    }
  }

  #node(nodeId) {
    const id = requireString(nodeId, "node_id", {
      pattern: NODE_ID_PATTERN,
      code: "NODE_QUERY_INVALID",
    });
    const node = this.#nodes.get(id);
    if (node === undefined) fail("NODE_NOT_FOUND", "node is not part of the compiled plan", { node_id: id });
    return node;
  }

  #history(nodeId) {
    return this.#attempts.get(nodeId);
  }

  #lastAttempt(nodeId) {
    return this.#history(nodeId).at(-1) ?? null;
  }

  #appendCommand(operation, input) {
    this.#commands.push(deepFreeze({ operation, input: cloneCanonical(input) }));
  }

  #replaceAttempt(nodeId, next) {
    const history = this.#history(nodeId);
    history[history.length - 1] = attemptSnapshot(next);
    return history.at(-1);
  }

  #assertMonotonicAttemptTime(at, attempt, code = "ATTEMPT_CLOCK_REGRESSION") {
    const priorCandidates = [
      attempt.leased_at,
      attempt.transition_history.at(-1)?.at,
      attempt.last_heartbeat_at,
    ].filter((candidate) => candidate !== null && candidate !== undefined);
    const prior = priorCandidates.reduce((latest, candidate) =>
      compareTimestamps(candidate, latest, code) > 0
        ? candidate
        : latest,
    );
    if (compareTimestamps(at, prior, code) < 0) {
      fail(code, "attempt transition time cannot move backwards", {
        at,
        prior_activity_at: prior,
        node_id: attempt.node_id,
        attempt: attempt.attempt,
      });
    }
  }

  #activeCount() {
    return this.#activeLeases.size;
  }

  #hardEnforced() {
    return ["HARD_METERED", "HARD_PREALLOCATED"].includes(this.#budget.enforcement);
  }

  #assertBudget(reservation) {
    if (!this.#hardEnforced()) return;
    for (const key of RESERVATION_KEYS) {
      const limit = this.#budget.hard_limits[key];
      if (limit !== null && this.#usage[key] + reservation[key] > limit) {
        fail("BUDGET_LIMIT_EXCEEDED", "hard budget admission limit would be exceeded", {
          dimension: key,
          current: this.#usage[key],
          requested: reservation[key],
          limit,
          breach_policy: this.#budget.breach_policy,
        });
      }
    }
    const concurrency = this.#budget.hard_limits.concurrency;
    if (concurrency !== null && this.#activeCount() + 1 > concurrency) {
      fail("CONCURRENCY_LIMIT_EXCEEDED", "hard concurrency admission limit would be exceeded", {
        active: this.#activeCount(),
        limit: concurrency,
      });
    }
  }

  #structuralBlockers(node) {
    const blockers = [];
    const last = this.#lastAttempt(node.node_id);
    if (last !== null) {
      if (["LEASED", "RUNNING", "RECONCILING"].includes(last.status)) {
        blockers.push({ code: `NODE_${last.status}`, node_id: node.node_id });
      } else if (["SUCCEEDED", "FAILED_FINAL", "BLOCKED", "SPEC_GAP", "CANCELLED"].includes(last.status)) {
        blockers.push({ code: "NODE_TERMINAL", node_id: node.node_id, status: last.status });
      } else if (last.status === "FAILED_RETRYABLE" && last.attempt >= node.max_attempts) {
        blockers.push({ code: "RETRY_EXHAUSTED", node_id: node.node_id });
      }
    }
    const loopRef = node.loop_contract_ref;
    const loop = loopRef === null ? null : this.#loopStates.get(loopRef);
    for (const dependencyId of node.depends_on) {
      if (
        loop !== null &&
        node.node_id === this.#plan.loop_contracts.find((entry) => entry.loop_id === loopRef).entry_node_id &&
        dependencyId === this.#plan.loop_contracts.find((entry) => entry.loop_id === loopRef).exit_node_id &&
        loop.iterations === 0
      ) {
        continue;
      }
      const dependency = this.#node(dependencyId);
      const prior = this.#lastAttempt(dependencyId);
      if (prior === null || prior.status !== "SUCCEEDED") {
        if (prior !== null && prior.status === "FAILED_FINAL") {
          const codeByPolicy = {
            fail_run: "PREDECESSOR_FAILED_RUN",
            mark_partial: "PARTIAL_PREDECESSOR_NOT_AUTHORIZED",
            skip_downstream: "PREDECESSOR_SKIPS_DOWNSTREAM",
            escalate: "PREDECESSOR_ESCALATION_REQUIRED",
          };
          blockers.push({
            code: codeByPolicy[dependency.failure_policy],
            dependency: dependencyId,
            status: prior.status,
          });
        } else {
          blockers.push({
            code: "PREDECESSOR_NOT_SUCCEEDED",
            dependency: dependencyId,
            status: prior?.status ?? "MISSING",
          });
        }
      } else if (prior.terminal_receipt_id === null) {
        blockers.push({ code: "PREDECESSOR_RECEIPT_MISSING", dependency: dependencyId });
      }
    }
    return blockers.sort((left, right) =>
      compareText(`${left.code}:${left.dependency ?? left.node_id ?? ""}`, `${right.code}:${right.dependency ?? right.node_id ?? ""}`),
    );
  }

  inspectNode(nodeId) {
    const node = this.#node(nodeId);
    const blockers = this.#structuralBlockers(node);
    return deepFreeze({
      node_id: node.node_id,
      ready: blockers.length === 0,
      blockers,
      attempts: this.#history(node.node_id).map((attempt) => cloneCanonical(attempt)),
    });
  }

  readyNodes() {
    return deepFreeze(
      this.#plan.topological_order.filter((nodeId) => this.#structuralBlockers(this.#node(nodeId)).length === 0),
    );
  }

  #resourceClaims(node) {
    return [`node:${node.node_id}`, ...node.resource_dependencies].sort(compareText);
  }

  #resourceCapacity(resource) {
    if (resource.startsWith("node:") || resource.startsWith("exclusive:")) return 1;
    return this.#plan.resource_capacities[resource];
  }

  #assertResourcesAvailable(claims) {
    for (const resource of claims) {
      const owners = this.#resourceOwners.get(resource) ?? new Set();
      const capacity = this.#resourceCapacity(resource);
      if (owners.size >= capacity) {
        fail("RESOURCE_CONFLICT", "scheduler resource capacity is exhausted", {
          resource,
          capacity,
          active_lease_ids: [...owners].sort(compareText),
        });
      }
    }
  }

  #claimResources(lease) {
    for (const resource of lease.resource_claims) {
      const owners = this.#resourceOwners.get(resource) ?? new Set();
      owners.add(lease.lease_id);
      this.#resourceOwners.set(resource, owners);
      this.#resourceHeads.set(resource, lease.fencing_token);
    }
    this.#nodeHeads.set(lease.node_id, lease.fencing_token);
    this.#activeLeases.set(lease.lease_id, lease);
  }

  #releaseResources(lease) {
    for (const resource of lease.resource_claims) {
      const owners = this.#resourceOwners.get(resource);
      if (owners === undefined) continue;
      owners.delete(lease.lease_id);
      if (owners.size === 0) this.#resourceOwners.delete(resource);
    }
    this.#activeLeases.delete(lease.lease_id);
  }

  acquireLease(candidate) {
    const code = "LEASE_ACQUISITION_INVALID";
    const command = requirePlainRecord(candidate, "lease acquisition", {
      allowedKeys: [
        "node_id",
        "owner_id",
        "at",
        "expires_at",
        "input_hash",
        "idempotency_values",
        "admission",
        "budget_reservation",
      ],
      requiredKeys: [
        "node_id",
        "owner_id",
        "at",
        "expires_at",
        "input_hash",
        "idempotency_values",
        "admission",
        "budget_reservation",
      ],
      code,
    });
    const node = this.#node(readDataProperty(command, "node_id"));
    const ownerId = requireString(readDataProperty(command, "owner_id"), "owner_id", { code });
    const at = requireTimestamp(readDataProperty(command, "at"), "at", code);
    const expiresAt = requireTimestamp(readDataProperty(command, "expires_at"), "expires_at", code);
    if (compareTimestamps(expiresAt, at, code) <= 0) {
      fail(code, "scheduler lease must expire after issuance");
    }
    if (timestampSpanExceedsSeconds(expiresAt, at, node.timeout_seconds, code)) {
      fail("LEASE_EXCEEDS_NODE_TIMEOUT", "scheduler lease exceeds NodeContract timeout", {
        node_id: node.node_id,
      });
    }
    const inputHash = requireHash(readDataProperty(command, "input_hash"), "input_hash", code);
    const idempotencyValues = normalizeIdempotencyValues(
      readDataProperty(command, "idempotency_values"),
      node,
    );
    const idempotencyHash = sha256SchedulerJson({
      run_id: this.#runId,
      node_id: node.node_id,
      input_hash: inputHash,
      idempotency_values: idempotencyValues,
    });
    const acquisitionRequestHash = sha256SchedulerJson({
      run_id: this.#runId,
      node_id: node.node_id,
      owner_id: ownerId,
      at,
      expires_at: expiresAt,
      input_hash: inputHash,
      idempotency_values: idempotencyValues,
      admission: readDataProperty(command, "admission"),
      budget_reservation: readDataProperty(command, "budget_reservation"),
    });
    const existingBinding = this.#idempotencyBindings.get(node.node_id);
    if (existingBinding !== undefined && existingBinding !== idempotencyHash) {
      fail("IDEMPOTENCY_CONFLICT", "node retry changed its canonical idempotency binding", {
        node_id: node.node_id,
      });
    }
    const last = this.#lastAttempt(node.node_id);
    if (last !== null && ACTIVE_ATTEMPT_STATES.has(last.status)) {
      const active = this.#activeLeases.get(last.lease_id);
      if (
        active !== undefined &&
        active.owner_id === ownerId &&
        active.idempotency_hash === idempotencyHash &&
        active.input_hash === inputHash &&
        active.expires_at === expiresAt &&
        active.acquisition_request_hash === acquisitionRequestHash
      ) {
        return deepFreeze(cloneCanonical(active));
      }
      if (active !== undefined && active.idempotency_hash === idempotencyHash) {
        fail("IDEMPOTENCY_CONFLICT", "active lease retry changed its canonical acquisition request", {
          node_id: node.node_id,
        });
      }
      fail("NODE_ALREADY_LEASED", "node already has an active execution lease", {
        node_id: node.node_id,
      });
    }
    const blockers = this.#structuralBlockers(node);
    if (blockers.length > 0) {
      fail("NODE_NOT_READY", "node has unresolved structural blockers", {
        node_id: node.node_id,
        blockers,
      });
    }
    const admission = normalizeAdmission(readDataProperty(command, "admission"), node);
    const reservation = normalizeReservation(readDataProperty(command, "budget_reservation"));
    this.#assertBudget(reservation);
    const claims = this.#resourceClaims(node);
    this.#assertResourcesAvailable(claims);

    const attemptNumber = last === null ? 1 : last.attempt + 1;
    if (attemptNumber > node.max_attempts) {
      fail("RETRY_EXHAUSTED", "NodeContract max_attempts has been exhausted", {
        node_id: node.node_id,
      });
    }
    if (last !== null) {
      const priorAt = last.transition_history.at(-1)?.at ?? last.leased_at;
      if (compareTimestamps(at, priorAt, code) < 0) {
        fail("ATTEMPT_CLOCK_REGRESSION", "retry lease predates the prior attempt transition", {
          node_id: node.node_id,
          at,
          prior_attempt_at: priorAt,
        });
      }
    }
    const token = this.#fencingCounter + 1;
    const leaseId = `SLEASE-${sha256SchedulerJson({
      run_id: this.#runId,
      node_id: node.node_id,
      attempt: attemptNumber,
      owner_id: ownerId,
      fencing_token: token,
      idempotency_hash: idempotencyHash,
      acquisition_request_hash: acquisitionRequestHash,
    }).slice("sha256:".length)}`;
    const lease = sealLease({
      lease_id: leaseId,
      run_id: this.#runId,
      node_id: node.node_id,
      attempt: attemptNumber,
      owner_id: ownerId,
      issued_at: at,
      expires_at: expiresAt,
      fencing_token: token,
      resource_claims: claims,
      capability_lease_ids: admission.capability_lease_ids,
      idempotency_hash: idempotencyHash,
      acquisition_request_hash: acquisitionRequestHash,
      input_hash: inputHash,
    });
    const attempt = attemptSnapshot({
      run_id: this.#runId,
      node_id: node.node_id,
      attempt: attemptNumber,
      status: "LEASED",
      lease_id: lease.lease_id,
      fencing_token: token,
      owner_id: ownerId,
      idempotency_hash: idempotencyHash,
      input_hash: inputHash,
      leased_at: at,
      started_at: null,
      last_heartbeat_at: null,
      finished_at: null,
      terminal_receipt_id: null,
      effect_receipt_ids: [],
      failure_code: null,
      reconciliation_receipt_id: null,
      pending_failure_code: null,
      transition_history: [
        { from: "PENDING", to: "LEASED", at, fencing_token: token },
      ],
    });
    this.#fencingCounter = token;
    this.#idempotencyBindings.set(node.node_id, idempotencyHash);
    this.#attempts.get(node.node_id).push(attempt);
    this.#claimResources(lease);
    for (const key of RESERVATION_KEYS) this.#usage[key] += reservation[key];
    this.#appendCommand("acquireLease", cloneCanonical(command));
    return lease;
  }

  #assertActiveLease(candidate, at, allowedStates) {
    const lease = normalizeLease(candidate);
    if (lease.run_id !== this.#runId) fail("LEASE_RUN_MISMATCH", "scheduler lease belongs to another run");
    const node = this.#node(lease.node_id);
    const last = this.#lastAttempt(node.node_id);
    const nodeHead = this.#nodeHeads.get(node.node_id) ?? 0;
    if (lease.fencing_token < nodeHead) {
      fail("STALE_FENCING_TOKEN", "a newer scheduler lease fences this worker", {
        supplied: lease.fencing_token,
        current: nodeHead,
      });
    }
    for (const resource of lease.resource_claims) {
      const resourceHead = this.#resourceHeads.get(resource) ?? 0;
      if (!resource.startsWith("quota:") && lease.fencing_token < resourceHead) {
        fail("STALE_FENCING_TOKEN", "a newer exclusive resource lease fences this worker", {
          resource,
          supplied: lease.fencing_token,
          current: resourceHead,
        });
      }
    }
    if (
      last === null ||
      last.attempt !== lease.attempt ||
      last.lease_id !== lease.lease_id ||
      last.fencing_token !== lease.fencing_token
    ) {
      fail("LEASE_ATTEMPT_MISMATCH", "scheduler lease does not resolve the current node attempt");
    }
    if (!allowedStates.has(last.status)) {
      fail("ATTEMPT_STATE_INVALID", "node attempt is not in a state allowed by this operation", {
        status: last.status,
      });
    }
    const active = this.#activeLeases.get(lease.lease_id);
    if (active === undefined || canonicalizeSchedulerJson(active) !== canonicalizeSchedulerJson(lease)) {
      fail("LEASE_NOT_ACTIVE", "scheduler lease is not the active canonical lease");
    }
    for (const resource of lease.resource_claims) {
      const owners = this.#resourceOwners.get(resource);
      if (owners === undefined || !owners.has(lease.lease_id)) {
        fail("LEASE_NOT_ACTIVE", "scheduler lease no longer owns every declared resource", {
          resource,
        });
      }
      if (
        !resource.startsWith("quota:") &&
        this.#resourceHeads.get(resource) !== lease.fencing_token
      ) {
        fail("STALE_FENCING_TOKEN", "exclusive resource fencing head differs from scheduler lease", {
          resource,
        });
      }
    }
    if (compareTimestamps(at, lease.issued_at, "LEASE_OPERATION_INVALID") < 0) {
      fail("LEASE_NOT_YET_VALID", "scheduler operation predates lease issuance");
    }
    if (compareTimestamps(at, lease.expires_at, "LEASE_OPERATION_INVALID") >= 0) {
      fail("LEASE_EXPIRED", "scheduler lease has expired");
    }
    return { lease, node, attempt: last };
  }

  startAttempt(candidate) {
    const code = "START_ATTEMPT_INVALID";
    const command = requirePlainRecord(candidate, "start attempt", {
      allowedKeys: ["lease", "at"],
      requiredKeys: ["lease", "at"],
      code,
    });
    const at = requireTimestamp(readDataProperty(command, "at"), "at", code);
    const { lease, attempt } = this.#assertActiveLease(
      readDataProperty(command, "lease"),
      at,
      new Set(["LEASED"]),
    );
    this.#assertMonotonicAttemptTime(at, attempt);
    const next = this.#replaceAttempt(lease.node_id, {
      ...attempt,
      status: "RUNNING",
      started_at: at,
      last_heartbeat_at: at,
      transition_history: [
        ...attempt.transition_history,
        { from: "LEASED", to: "RUNNING", at, fencing_token: lease.fencing_token },
      ],
    });
    this.#appendCommand("startAttempt", cloneCanonical(command));
    return next;
  }

  heartbeat(candidate) {
    const code = "HEARTBEAT_INVALID";
    const command = requirePlainRecord(candidate, "heartbeat", {
      allowedKeys: ["lease", "at"],
      requiredKeys: ["lease", "at"],
      code,
    });
    const at = requireTimestamp(readDataProperty(command, "at"), "at", code);
    const { lease, attempt } = this.#assertActiveLease(
      readDataProperty(command, "lease"),
      at,
      new Set(["RUNNING"]),
    );
    this.#assertMonotonicAttemptTime(at, attempt, "HEARTBEAT_CLOCK_REGRESSION");
    const next = this.#replaceAttempt(lease.node_id, { ...attempt, last_heartbeat_at: at });
    this.#appendCommand("heartbeat", cloneCanonical(command));
    return next;
  }

  recordSuccess(candidate) {
    const code = "SUCCESS_RECORD_INVALID";
    const command = requirePlainRecord(candidate, "success record", {
      allowedKeys: ["lease", "at", "terminal_receipt_id", "effect_receipt_ids"],
      requiredKeys: ["lease", "at", "terminal_receipt_id", "effect_receipt_ids"],
      code,
    });
    const at = requireTimestamp(readDataProperty(command, "at"), "at", code);
    const { lease, node, attempt } = this.#assertActiveLease(
      readDataProperty(command, "lease"),
      at,
      new Set(["RUNNING"]),
    );
    this.#assertMonotonicAttemptTime(at, attempt);
    const terminalReceiptId = requireString(
      readDataProperty(command, "terminal_receipt_id"),
      "terminal_receipt_id",
      { code },
    );
    const effectReceiptIds = requireStringArray(
      readDataProperty(command, "effect_receipt_ids"),
      "effect_receipt_ids",
      { sort: true, code },
    );
    if (node.expected_effects.length > 0 && effectReceiptIds.length === 0) {
      fail("EFFECT_RECEIPT_MISSING", "effectful node cannot succeed without an EffectReceipt");
    }
    const next = this.#replaceAttempt(node.node_id, {
      ...attempt,
      status: "SUCCEEDED",
      finished_at: at,
      terminal_receipt_id: terminalReceiptId,
      effect_receipt_ids: effectReceiptIds,
      transition_history: [
        ...attempt.transition_history,
        { from: "RUNNING", to: "SUCCEEDED", at, fencing_token: lease.fencing_token },
      ],
    });
    this.#releaseResources(lease);
    this.#appendCommand("recordSuccess", cloneCanonical(command));
    return next;
  }

  #failureTarget(node, attempt, failureCode) {
    if (SPEC_GAP_FAILURE_CODES.has(failureCode)) return "SPEC_GAP";
    if (!RETRYABLE_FAILURE_SET.has(failureCode)) return "FAILED_FINAL";
    return attempt.attempt < node.max_attempts ? "FAILED_RETRYABLE" : "FAILED_FINAL";
  }

  recordFailure(candidate) {
    const code = "FAILURE_RECORD_INVALID";
    const command = requirePlainRecord(candidate, "failure record", {
      allowedKeys: ["lease", "at", "failure_code", "terminal_receipt_id", "effect_state"],
      requiredKeys: ["lease", "at", "failure_code", "terminal_receipt_id", "effect_state"],
      code,
    });
    const at = requireTimestamp(readDataProperty(command, "at"), "at", code);
    const { lease, node, attempt } = this.#assertActiveLease(
      readDataProperty(command, "lease"),
      at,
      new Set(["LEASED", "RUNNING"]),
    );
    this.#assertMonotonicAttemptTime(at, attempt);
    const failureCode = requireString(readDataProperty(command, "failure_code"), "failure_code", {
      code,
    });
    const terminalReceiptId = requireString(
      readDataProperty(command, "terminal_receipt_id"),
      "terminal_receipt_id",
      { code },
    );
    const effectState = readDataProperty(command, "effect_state");
    if (!new Set(["KNOWN_NO_EFFECT", "RECEIPT_PRESENT", "UNKNOWN"]).has(effectState)) {
      fail(code, "effect_state is not canonical");
    }
    const target = effectState === "UNKNOWN" ? "RECONCILING" : this.#failureTarget(node, attempt, failureCode);
    const next = this.#replaceAttempt(node.node_id, {
      ...attempt,
      status: target,
      finished_at: target === "RECONCILING" ? null : at,
      terminal_receipt_id: terminalReceiptId,
      failure_code: target === "RECONCILING" ? null : failureCode,
      pending_failure_code: target === "RECONCILING" ? failureCode : null,
      transition_history: [
        ...attempt.transition_history,
        { from: attempt.status, to: target, at, fencing_token: lease.fencing_token },
      ],
    });
    this.#releaseResources(lease);
    this.#appendCommand("recordFailure", cloneCanonical(command));
    return next;
  }

  reconcileExpired(candidate) {
    const code = "EXPIRY_RECONCILIATION_INVALID";
    const command = requirePlainRecord(candidate, "expiry reconciliation", {
      allowedKeys: ["at"],
      requiredKeys: ["at"],
      code,
    });
    const at = requireTimestamp(readDataProperty(command, "at"), "at", code);
    const orphaned = [];
    for (const nodeId of this.#plan.topological_order) {
      const attempt = this.#lastAttempt(nodeId);
      if (attempt === null || !ACTIVE_ATTEMPT_STATES.has(attempt.status)) continue;
      const lease = this.#activeLeases.get(attempt.lease_id);
      if (lease === undefined || compareTimestamps(at, lease.expires_at, code) < 0) continue;
      const next = this.#replaceAttempt(nodeId, {
        ...attempt,
        status: "RECONCILING",
        pending_failure_code: "TEMPORARY_SERVICE_UNAVAILABLE",
        transition_history: [
          ...attempt.transition_history,
          { from: attempt.status, to: "RECONCILING", at, fencing_token: lease.fencing_token },
        ],
      });
      this.#releaseResources(lease);
      orphaned.push({ node_id: nodeId, attempt: next.attempt, lease_id: lease.lease_id });
    }
    this.#appendCommand("reconcileExpired", cloneCanonical(command));
    return deepFreeze(orphaned);
  }

  resolveReconciliation(candidate) {
    const code = "RECONCILIATION_RESOLUTION_INVALID";
    const command = requirePlainRecord(candidate, "reconciliation resolution", {
      allowedKeys: [
        "node_id",
        "attempt",
        "at",
        "outcome",
        "reconciliation_receipt_id",
        "terminal_receipt_id",
        "effect_receipt_ids",
      ],
      requiredKeys: [
        "node_id",
        "attempt",
        "at",
        "outcome",
        "reconciliation_receipt_id",
        "terminal_receipt_id",
        "effect_receipt_ids",
      ],
      code,
    });
    const node = this.#node(readDataProperty(command, "node_id"));
    const attemptNumber = requireSafeInteger(readDataProperty(command, "attempt"), "attempt", {
      minimum: 1,
      maximum: 10,
      code,
    });
    const at = requireTimestamp(readDataProperty(command, "at"), "at", code);
    const outcome = readDataProperty(command, "outcome");
    if (!new Set(["NO_EFFECT", "EFFECT_SUCCEEDED", "FAILED_FINAL"]).has(outcome)) {
      fail(code, "outcome is not canonical");
    }
    const receiptId = requireString(
      readDataProperty(command, "reconciliation_receipt_id"),
      "reconciliation_receipt_id",
      { code },
    );
    const terminalReceiptId = requireString(
      readDataProperty(command, "terminal_receipt_id"),
      "terminal_receipt_id",
      { code },
    );
    const effectReceiptIds = requireStringArray(
      readDataProperty(command, "effect_receipt_ids"),
      "effect_receipt_ids",
      { sort: true, code },
    );
    const attempt = this.#lastAttempt(node.node_id);
    if (attempt === null || attempt.attempt !== attemptNumber || attempt.status !== "RECONCILING") {
      fail("RECONCILIATION_NOT_REQUIRED", "node attempt is not awaiting reconciliation");
    }
    this.#assertMonotonicAttemptTime(at, attempt, "RECONCILIATION_CLOCK_REGRESSION");
    let target;
    let failureCode = attempt.pending_failure_code;
    if (outcome === "EFFECT_SUCCEEDED") {
      if (effectReceiptIds.length === 0) {
        fail("EFFECT_RECEIPT_MISSING", "successful reconciliation requires an EffectReceipt");
      }
      target = "SUCCEEDED";
      failureCode = null;
    } else if (outcome === "FAILED_FINAL") {
      target = "FAILED_FINAL";
    } else {
      target = this.#failureTarget(node, attempt, attempt.pending_failure_code);
    }
    const next = this.#replaceAttempt(node.node_id, {
      ...attempt,
      status: target,
      finished_at: at,
      terminal_receipt_id: terminalReceiptId,
      effect_receipt_ids: effectReceiptIds,
      failure_code: failureCode,
      reconciliation_receipt_id: receiptId,
      pending_failure_code: null,
      transition_history: [
        ...attempt.transition_history,
        { from: "RECONCILING", to: target, at, fencing_token: attempt.fencing_token },
      ],
    });
    this.#appendCommand("resolveReconciliation", cloneCanonical(command));
    return next;
  }

  recordLoopRound(candidate) {
    const code = "LOOP_ROUND_INVALID";
    const command = requirePlainRecord(candidate, "loop round", {
      allowedKeys: ["loop_id", "at", "observed_item_keys", "cost_units", "convergence_met"],
      requiredKeys: ["loop_id", "at", "observed_item_keys", "cost_units", "convergence_met"],
      code,
    });
    const loopId = requireString(readDataProperty(command, "loop_id"), "loop_id", { code });
    const contract = this.#plan.loop_contracts.find((loop) => loop.loop_id === loopId);
    if (contract === undefined) fail("LOOP_NOT_FOUND", "loop is not part of the compiled plan", { loop_id: loopId });
    const at = requireTimestamp(readDataProperty(command, "at"), "at", code);
    const items = requireStringArray(
      readDataProperty(command, "observed_item_keys"),
      "observed_item_keys",
      { sort: true, code },
    );
    const cost = requireFiniteNumber(readDataProperty(command, "cost_units"), "cost_units", {
      code,
    });
    const convergenceMet = requireBoolean(
      readDataProperty(command, "convergence_met"),
      "convergence_met",
      code,
    );
    const current = this.#loopStates.get(loopId);
    if (!["PENDING", "RUNNING"].includes(current.status)) {
      fail("LOOP_TERMINAL", "bounded loop has already terminated", { status: current.status });
    }
    if (
      current.last_round_at !== null &&
      compareTimestamps(at, current.last_round_at, code) < 0
    ) {
      fail("LOOP_CLOCK_REGRESSION", "loop round time cannot move backwards");
    }
    if (current.iterations >= contract.max_iterations) {
      fail("LOOP_ITERATION_LIMIT_REACHED", "bounded loop has no remaining iterations");
    }
    if (current.total_cost_units + cost > contract.max_cost_units) {
      fail("LOOP_COST_LIMIT_EXCEEDED", "bounded loop cost admission would exceed its contract");
    }
    const startedAt = current.started_at ?? at;
    if (compareTimestamps(at, startedAt, code) < 0) {
      fail("LOOP_CLOCK_REGRESSION", "loop round predates its first round");
    }
    if (timestampSpanExceedsSeconds(at, startedAt, contract.max_wall_seconds, code)) {
      fail("LOOP_WALL_LIMIT_EXCEEDED", "bounded loop wall-time admission exceeds its contract");
    }
    const seen = new Set(current.seen_item_keys);
    let newItems = 0;
    for (const item of items) {
      if (!seen.has(item)) newItems += 1;
      seen.add(item);
    }
    const dryRounds = newItems === 0 ? current.dry_rounds + 1 : 0;
    const iterations = current.iterations + 1;
    let status = "RUNNING";
    let action = null;
    if (convergenceMet && dryRounds >= contract.dry_rounds_required) {
      status = "CONVERGED";
    } else if (iterations >= contract.max_iterations) {
      status = "NONCONVERGED";
      action = contract.on_nonconvergence;
    }
    const next = deepFreeze({
      loop_id: loopId,
      status,
      iterations,
      total_cost_units: current.total_cost_units + cost,
      started_at: startedAt,
      last_round_at: at,
      dry_rounds: dryRounds,
      seen_item_keys: [...seen].sort(compareText),
      nonconvergence_action: action,
    });
    this.#loopStates.set(loopId, next);
    this.#appendCommand("recordLoopRound", cloneCanonical(command));
    return next;
  }

  snapshot() {
    const semantic = {
      run_id: this.#runId,
      plan_hash: this.#plan.plan_hash,
      budget_hash: this.#budget.budget_hash,
      budget_enforcement: this.#budget.enforcement,
      budget_usage: cloneCanonical(this.#usage),
      fencing_counter: this.#fencingCounter,
      active_lease_ids: [...this.#activeLeases.keys()].sort(compareText),
      active_leases: [...this.#activeLeases.values()]
        .sort((left, right) => compareText(left.lease_id, right.lease_id))
        .map((lease) => cloneCanonical(lease)),
      idempotency_bindings: Object.fromEntries(
        [...this.#idempotencyBindings.entries()].sort(([left], [right]) => compareText(left, right)),
      ),
      resource_owners: Object.fromEntries(
        [...this.#resourceOwners.entries()]
          .sort(([left], [right]) => compareText(left, right))
          .map(([resource, owners]) => [resource, [...owners].sort(compareText)]),
      ),
      resource_fencing_heads: Object.fromEntries(
        [...this.#resourceHeads.entries()].sort(([left], [right]) => compareText(left, right)),
      ),
      node_fencing_heads: Object.fromEntries(
        [...this.#nodeHeads.entries()].sort(([left], [right]) => compareText(left, right)),
      ),
      node_attempts: Object.fromEntries(
        [...this.#attempts.entries()]
          .sort(([left], [right]) => compareText(left, right))
          .map(([nodeId, attempts]) => [nodeId, attempts.map((attempt) => cloneCanonical(attempt))]),
      ),
      loop_states: Object.fromEntries(
        [...this.#loopStates.entries()]
          .sort(([left], [right]) => compareText(left, right))
          .map(([loopId, state]) => [loopId, cloneCanonical(state)]),
      ),
      ready_node_ids: [...this.readyNodes()],
    };
    return deepFreeze({ ...semantic, state_hash: sha256SchedulerJson(semantic) });
  }

  commandLog() {
    return deepFreeze(this.#commands.map((command) => cloneCanonical(command)));
  }
}

export const createDagScheduler = (candidate) => {
  const input = requirePlainRecord(candidate, "scheduler creation", {
    allowedKeys: ["run_id", "plan", "budget_envelope"],
    requiredKeys: ["run_id", "plan", "budget_envelope"],
    code: "SCHEDULER_CREATE_INVALID",
  });
  return new DagScheduler({
    run_id: readDataProperty(input, "run_id"),
    plan: readDataProperty(input, "plan"),
    budget_envelope: readDataProperty(input, "budget_envelope"),
  });
};

export const replaySchedulerCommands = (candidate) => {
  const code = "SCHEDULER_REPLAY_INVALID";
  const input = requirePlainRecord(candidate, "scheduler replay", {
    allowedKeys: ["run_id", "plan", "budget_envelope", "commands"],
    requiredKeys: ["run_id", "plan", "budget_envelope", "commands"],
    code,
  });
  const runId = readDataProperty(input, "run_id", "scheduler replay", code);
  const plan = readDataProperty(input, "plan", "scheduler replay", code);
  const budgetEnvelope = readDataProperty(
    input,
    "budget_envelope",
    "scheduler replay",
    code,
  );
  const entries = requireDenseArray(
    readDataProperty(input, "commands", "scheduler replay", code),
    "commands",
    code,
  );
  const scheduler = createDagScheduler({
    run_id: runId,
    plan,
    budget_envelope: budgetEnvelope,
  });
  const operations = new Set([
    "acquireLease",
    "startAttempt",
    "heartbeat",
    "recordSuccess",
    "recordFailure",
    "reconcileExpired",
    "resolveReconciliation",
    "recordLoopRound",
  ]);
  for (let index = 0; index < entries.length; index += 1) {
    const entry = requirePlainRecord(entries[index], `commands[${index}]`, {
      allowedKeys: ["operation", "input"],
      requiredKeys: ["operation", "input"],
      code: "SCHEDULER_REPLAY_INVALID",
    });
    const operation = requireString(readDataProperty(entry, "operation"), `commands[${index}].operation`, {
      code: "SCHEDULER_REPLAY_INVALID",
    });
    if (!operations.has(operation)) {
      fail("SCHEDULER_REPLAY_INVALID", "command operation is not replayable", { operation });
    }
    scheduler[operation](readDataProperty(entry, "input"));
  }
  return deepFreeze({ snapshot: scheduler.snapshot(), commands: scheduler.commandLog() });
};
