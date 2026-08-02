export const INTAKE_FRAME_KIND = "EpistemicFoundryIntakeFrame";
export const INTAKE_FRAME_VERSION = "4.0.0-i04.1";
export const INTAKE_EXPORT_FORMAT = "epistemic-foundry/intake-frame+json";

const ID_PATTERN = /^[A-Z][A-Z0-9_-]*-[A-Za-z0-9._:-]+$/;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/;
const SEMVER_PATTERN = /^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$/;
const RFC3339_PATTERN = /^(?<year>\d{4})-(?<month>\d{2})-(?<day>\d{2})[Tt](?<hour>\d{2}):(?<minute>\d{2}):(?<second>\d{2})(?:\.(?<fraction>\d+))?(?<zone>[Zz]|(?<offsetSign>[+-])(?<offsetHour>\d{2}):(?<offsetMinute>\d{2}))$/;

const INPUT_KEYS = [
  "consent_requirement",
  "council_blockers",
  "council_ready",
  "insight_card",
  "measurement_compatibilities",
  "ontology_resolutions",
  "unknown_scope",
];

const CARD_KEYS = [
  "alternative_hypotheses",
  "created_at",
  "created_by",
  "decision_context",
  "falsifiers",
  "insight_id",
  "lens_provenance",
  "mechanism_path",
  "null_model",
  "predictions",
  "registration_hash",
  "registration_status",
  "revision",
  "risk_class",
  "schema_version",
  "scope",
  "statement",
  "terms_to_define",
];

const SCOPE_KEYS = [
  "comparator",
  "conditions",
  "domain",
  "domain_extensions",
  "entity_subtype",
  "entity_type",
  "exclusion_criteria",
  "geography",
  "inclusion_criteria",
  "intervention_or_exposure",
  "jurisdiction",
  "language",
  "lifecycle_stage",
  "measurement_time",
  "population",
  "setting",
  "spatial_scale",
  "temporal_scale",
  "time_period",
  "unit_of_analysis",
];

const SCOPE_SCALAR_KEYS = [
  "domain",
  "population",
  "entity_type",
  "entity_subtype",
  "unit_of_analysis",
  "setting",
  "geography",
  "jurisdiction",
  "language",
  "lifecycle_stage",
  "spatial_scale",
  "temporal_scale",
  "time_period",
  "measurement_time",
];

const INTERVENTION_KEYS = [
  "category",
  "duration",
  "frequency",
  "max_value",
  "min_value",
  "name",
  "rate",
  "route_or_delivery",
  "unit",
];

const INTERVENTION_NULLABLE_TEXT_KEYS = [
  "category",
  "duration",
  "frequency",
  "route_or_delivery",
  "unit",
];

const CANDIDATE_KEYS = [
  "authority_ref",
  "canonical_label",
  "conflicting_dimensions",
  "construct_id",
  "entity_kind",
  "matched_dimensions",
  "missing_dimensions",
  "viable",
];

const ONTOLOGY_KEYS = [
  "abstention_reasons",
  "candidates",
  "mapping_key_hash",
  "proposed_construct_id",
  "resolver_version",
  "review_queue_items",
  "selected_construct_id",
  "status",
];

const REVIEW_ITEM_KEYS = [
  "candidate_construct_ids",
  "mapping_key_hash",
  "policy_version",
  "proposed_construct_id",
  "reasons",
  "required_authority_artifact",
  "review_item_id",
];

const MEASUREMENT_KEYS = [
  "aggregation_allowed",
  "bridge_id",
  "compatibility_status",
  "construct_equivalence",
  "left_identity_hash",
  "left_measurement_id",
  "method_threats",
  "promotion_ceiling",
  "required_transformations",
  "right_identity_hash",
  "right_measurement_id",
];

const CONSENT_REQUIREMENT_KEYS = [
  "evaluated_at",
  "records",
  "required",
  "required_data_classes",
  "required_purposes",
  "required_scopes",
];

const CONSENT_RECORD_KEYS = [
  "consent_id",
  "data_classes",
  "decision",
  "expires_at",
  "granted_at",
  "policy_hash",
  "purposes",
  "record_hash",
  "recorded_by",
  "revoked_at",
  "scopes",
  "subject_id",
  "workspace_id",
];

const REGISTRATION_STATUSES = new Set(["inbox", "eligible", "withdrawn"]);
const RISK_CLASSES = new Set(["routine", "consequential", "high_stakes"]);
const LENS_VALUES = new Set([
  "adapt",
  "borrow",
  "modify",
  "magnify",
  "minify",
  "substitute",
  "rearrange",
  "reverse",
  "combine",
  "human",
]);
const UNKNOWN_SOURCES = new Set(["ABSENT", "EXPLICIT_NULL", "BLANK_STRING"]);
const ONTOLOGY_ENTITY_KINDS = new Set([
  "CONCEPT",
  "LATENT_CONSTRUCT",
  "VARIABLE",
  "OPERATIONAL_MEASURE",
  "METHOD",
  "UNIT",
  "PROXY_RELATION",
]);
const ONTOLOGY_STATUSES = new Set([
  "RESOLVED",
  "PENDING_APPROVAL",
  "AMBIGUOUS",
  "UNKNOWN",
]);
const COMPATIBILITY_STATUSES = new Set([
  "DIRECTLY_COMPARABLE",
  "CONVERTIBLE",
  "WITHIN_METHOD_ONLY",
  "NOT_COMPARABLE",
  "UNKNOWN",
]);
const CONSTRUCT_EQUIVALENCE = new Set(["SAME", "PARTIAL", "DIFFERENT", "UNKNOWN"]);
const PROMOTION_CEILINGS = new Set([
  "NO_RESTRICTION",
  "CONDITIONAL_ONLY",
  "METHOD_BOUNDARY_ONLY",
  "BLOCK_AGGREGATION",
]);
const CONSENT_DECISIONS = new Set(["GRANTED", "DENIED", "REVOKED", "EXPIRED"]);
const UTF8_ENCODER = new TextEncoder();

export class IntakeContractError extends Error {
  constructor(code, message, details = null) {
    super(message);
    this.name = "IntakeContractError";
    this.code = code;
    this.details = details === null ? null : deepFreeze(jsonClone(details));
  }
}

const fail = (code, message, details = null) => {
  throw new IntakeContractError(code, message, details);
};

const isRecord = (value) => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
};

const requireRecord = (value, label) => {
  if (!isRecord(value)) fail("INTAKE_INPUT_INVALID", `${label} must be an object`);
  return value;
};

const exactKeys = (value, expected, label) => {
  const actual = Object.keys(requireRecord(value, label)).sort();
  const canonical = [...expected].sort();
  const missing = canonical.filter((key) => !actual.includes(key));
  const extra = actual.filter((key) => !canonical.includes(key));
  if (missing.length || extra.length) {
    fail("INTAKE_FIELD_SET_INVALID", `${label} must use its closed field set`, {
      extra,
      missing,
    });
  }
};

const requireString = (value, label, { minimum = 1, nullable = false } = {}) => {
  if (nullable && value === null) return null;
  if (typeof value !== "string" || value.includes("\0") || value.trim().length < minimum) {
    fail("INTAKE_INPUT_INVALID", `${label} must be a NUL-free string`);
  }
  return value;
};

const requireNormalizedString = (
  value,
  label,
  { minimum = 1, nullable = false } = {},
) => {
  const text = requireString(value, label, { minimum, nullable });
  if (text !== null && text !== text.trim()) {
    fail("INTAKE_INPUT_INVALID", `${label} must already be normalized`);
  }
  return text;
};

const requireBoolean = (value, label) => {
  if (typeof value !== "boolean") fail("INTAKE_INPUT_INVALID", `${label} must be boolean`);
  return value;
};

const requireEnum = (value, allowed, label) => {
  const normalized = requireString(value, label);
  if (!allowed.has(normalized)) {
    fail("INTAKE_INPUT_INVALID", `${label} uses a value outside its closed vocabulary`, {
      actual: normalized,
      allowed: [...allowed].sort(),
    });
  }
  return normalized;
};

const requireStringArray = (value, label, { minimum = 0, unique = false } = {}) => {
  if (!Array.isArray(value) || value.length < minimum) {
    fail("INTAKE_INPUT_INVALID", `${label} must be an array with at least ${minimum} item(s)`);
  }
  const result = value.map((entry, index) => requireString(entry, `${label}[${index}]`));
  if (unique && new Set(result).size !== result.length) {
    fail("INTAKE_INPUT_INVALID", `${label} must not contain duplicates`);
  }
  return result;
};

const requireNormalizedStringArray = (
  value,
  label,
  { minimum = 0, unique = false } = {},
) => {
  const result = requireStringArray(value, label, { minimum, unique });
  result.forEach((entry, index) =>
    requireNormalizedString(entry, `${label}[${index}]`),
  );
  return result;
};

const assertJsonValue = (value, path = "$", seen = new Set()) => {
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) fail("INTAKE_INPUT_INVALID", `${path} must be finite JSON`);
    return;
  }
  if (typeof value !== "object") {
    fail("INTAKE_INPUT_INVALID", `${path} must be representable as JSON`);
  }
  if (seen.has(value)) fail("INTAKE_INPUT_INVALID", `${path} contains a cycle`);
  seen.add(value);
  if (Array.isArray(value)) {
    value.forEach((entry, index) => assertJsonValue(entry, `${path}[${index}]`, seen));
  } else {
    requireRecord(value, path);
    for (const [key, entry] of Object.entries(value)) {
      if (!key || key.includes("\0") || ["__proto__", "constructor", "prototype"].includes(key)) {
        fail("INTAKE_INPUT_INVALID", `${path} contains an unsafe object key`);
      }
      assertJsonValue(entry, `${path}.${key}`, seen);
    }
  }
  seen.delete(value);
};

const canonicalJson = (value) => {
  assertJsonValue(value);
  const encode = (entry) => {
    if (entry === null || typeof entry !== "object") return JSON.stringify(entry);
    if (Array.isArray(entry)) return `[${entry.map(encode).join(",")}]`;
    return `{${Object.keys(entry)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${encode(entry[key])}`)
      .join(",")}}`;
  };
  return encode(value);
};

const jsonClone = (value) => JSON.parse(canonicalJson(value));

const deepFreeze = (value) => {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const entry of Object.values(value)) deepFreeze(entry);
    Object.freeze(value);
  }
  return value;
};

const SHA256_CONSTANTS = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

const rotateRight = (value, count) => (value >>> count) | (value << (32 - count));

const sha256Hex = (bytes) => {
  const bitLength = BigInt(bytes.length) * 8n;
  const paddedLength = Math.ceil((bytes.length + 9) / 64) * 64;
  const padded = new Uint8Array(paddedLength);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  for (let index = 0; index < 8; index += 1) {
    padded[paddedLength - 1 - index] = Number((bitLength >> BigInt(index * 8)) & 0xffn);
  }

  const state = new Uint32Array([
    0x6a09e667,
    0xbb67ae85,
    0x3c6ef372,
    0xa54ff53a,
    0x510e527f,
    0x9b05688c,
    0x1f83d9ab,
    0x5be0cd19,
  ]);
  const schedule = new Uint32Array(64);
  const view = new DataView(padded.buffer);
  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      schedule[index] = view.getUint32(offset + index * 4, false);
    }
    for (let index = 16; index < 64; index += 1) {
      const previous15 = schedule[index - 15];
      const previous2 = schedule[index - 2];
      const sigma0 =
        rotateRight(previous15, 7) ^ rotateRight(previous15, 18) ^ (previous15 >>> 3);
      const sigma1 =
        rotateRight(previous2, 17) ^ rotateRight(previous2, 19) ^ (previous2 >>> 10);
      schedule[index] =
        (schedule[index - 16] + sigma0 + schedule[index - 7] + sigma1) >>> 0;
    }

    let [a, b, c, d, e, f, g, h] = state;
    for (let index = 0; index < 64; index += 1) {
      const sum1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const choose = (e & f) ^ (~e & g);
      const temporary1 =
        (h + sum1 + choose + SHA256_CONSTANTS[index] + schedule[index]) >>> 0;
      const sum0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temporary2 = (sum0 + majority) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temporary1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temporary1 + temporary2) >>> 0;
    }
    state[0] = (state[0] + a) >>> 0;
    state[1] = (state[1] + b) >>> 0;
    state[2] = (state[2] + c) >>> 0;
    state[3] = (state[3] + d) >>> 0;
    state[4] = (state[4] + e) >>> 0;
    state[5] = (state[5] + f) >>> 0;
    state[6] = (state[6] + g) >>> 0;
    state[7] = (state[7] + h) >>> 0;
  }
  return [...state].map((part) => part.toString(16).padStart(8, "0")).join("");
};

const encodeUtf8 = (value) => UTF8_ENCODER.encode(value);
const sha256 = (bytes) => `sha256:${sha256Hex(bytes)}`;

const parseTimestamp = (value, label, { nullable = false } = {}) => {
  if (nullable && value === null) return null;
  const timestamp = requireString(value, label);
  const match = RFC3339_PATTERN.exec(timestamp);
  if (match === null || match.groups === undefined) {
    fail("INTAKE_INPUT_INVALID", `${label} must be an RFC 3339 timestamp`);
  }
  const {
    day: dayText,
    fraction = "",
    hour: hourText,
    minute: minuteText,
    month: monthText,
    offsetHour: offsetHourText,
    offsetMinute: offsetMinuteText,
    offsetSign,
    second: secondText,
    year: yearText,
  } = match.groups;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  const offsetHour = offsetHourText === undefined ? 0 : Number(offsetHourText);
  const offsetMinute = offsetMinuteText === undefined ? 0 : Number(offsetMinuteText);
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    hour > 23 ||
    minute > 59 ||
    second > 60 ||
    offsetHour > 23 ||
    offsetMinute > 59
  ) {
    fail("INTAKE_INPUT_INVALID", `${label} must be a valid RFC 3339 timestamp`);
  }
  const calendar = new Date(0);
  calendar.setUTCFullYear(year, month - 1, day);
  calendar.setUTCHours(hour, minute, Math.min(second, 59), 0);
  if (
    calendar.getUTCFullYear() !== year ||
    calendar.getUTCMonth() !== month - 1 ||
    calendar.getUTCDate() !== day ||
    calendar.getUTCHours() !== hour ||
    calendar.getUTCMinutes() !== minute ||
    calendar.getUTCSeconds() !== Math.min(second, 59)
  ) {
    fail("INTAKE_INPUT_INVALID", `${label} must be a valid RFC 3339 timestamp`);
  }
  let epochSecond = BigInt(Math.trunc(calendar.getTime() / 1000));
  if (second === 60) epochSecond += 1n;
  const offsetSeconds = BigInt(offsetHour * 3600 + offsetMinute * 60);
  if (offsetSign === "+") epochSecond -= offsetSeconds;
  if (offsetSign === "-") epochSecond += offsetSeconds;
  return { epochSecond, fraction, timestamp };
};

const validateTimestamp = (value, label, options = {}) =>
  parseTimestamp(value, label, options)?.timestamp ?? null;

const compareTimestamps = (left, right) => {
  if (left.epochSecond !== right.epochSecond) {
    return left.epochSecond < right.epochSecond ? -1 : 1;
  }
  const width = Math.max(left.fraction.length, right.fraction.length);
  const leftFraction = left.fraction.padEnd(width, "0");
  const rightFraction = right.fraction.padEnd(width, "0");
  return leftFraction === rightFraction ? 0 : leftFraction < rightFraction ? -1 : 1;
};

const requireScopeScalar = (value, label) => {
  if (value === null) return null;
  return requireNormalizedString(value, label);
};

const validateScopeMap = (value, label) => {
  const map = requireRecord(value, label);
  for (const [key, entry] of Object.entries(map)) {
    requireNormalizedString(key, `${label} key`);
    const values = Array.isArray(entry) ? entry : [entry];
    for (const [index, item] of values.entries()) {
      if (
        item !== null &&
        typeof item !== "string" &&
        typeof item !== "boolean" &&
        !(typeof item === "number" && Number.isFinite(item))
      ) {
        fail(
          "INTAKE_INPUT_INVALID",
          `${label}.${key}${Array.isArray(entry) ? `[${index}]` : ""} must be a JSON scalar`,
        );
      }
    }
  }
};

const validateScope = (scope) => {
  exactKeys(scope, SCOPE_KEYS, "insight_card.scope");
  for (const field of SCOPE_SCALAR_KEYS) {
    requireScopeScalar(scope[field], `insight_card.scope.${field}`);
  }
  requireScopeScalar(scope.comparator, "insight_card.scope.comparator");
  requireNormalizedStringArray(
    scope.inclusion_criteria,
    "insight_card.scope.inclusion_criteria",
  );
  requireNormalizedStringArray(
    scope.exclusion_criteria,
    "insight_card.scope.exclusion_criteria",
  );
  validateScopeMap(scope.conditions, "insight_card.scope.conditions");
  validateScopeMap(scope.domain_extensions, "insight_card.scope.domain_extensions");

  const intervention = scope.intervention_or_exposure;
  if (intervention === null) return;
  exactKeys(intervention, INTERVENTION_KEYS, "insight_card.scope.intervention_or_exposure");
  requireNormalizedString(
    intervention.name,
    "insight_card.scope.intervention_or_exposure.name",
  );
  for (const field of INTERVENTION_NULLABLE_TEXT_KEYS) {
    requireNormalizedString(
      intervention[field],
      `insight_card.scope.intervention_or_exposure.${field}`,
      { nullable: true },
    );
  }
  for (const field of ["min_value", "max_value"]) {
    const value = intervention[field];
    if (value !== null && !(typeof value === "number" && Number.isFinite(value))) {
      fail(
        "INTAKE_INPUT_INVALID",
        `insight_card.scope.intervention_or_exposure.${field} must be a finite number or null`,
      );
    }
  }
  if (
    intervention.rate !== null &&
    typeof intervention.rate !== "string" &&
    !(typeof intervention.rate === "number" && Number.isFinite(intervention.rate))
  ) {
    fail(
      "INTAKE_INPUT_INVALID",
      "insight_card.scope.intervention_or_exposure.rate must be a string, finite number, or null",
    );
  }
  if (typeof intervention.rate === "string") {
    requireNormalizedString(
      intervention.rate,
      "insight_card.scope.intervention_or_exposure.rate",
    );
  }
};

const validateInsightCard = (raw) => {
  exactKeys(raw, CARD_KEYS, "insight_card");
  const card = jsonClone(raw);
  requireNormalizedString(card.insight_id, "insight_card.insight_id");
  if (!ID_PATTERN.test(card.insight_id)) {
    fail(
      "INTAKE_INPUT_INVALID",
      "insight_card.insight_id does not match the canonical ID pattern",
    );
  }
  if (!Number.isInteger(card.revision) || card.revision < 1) {
    fail("INTAKE_INPUT_INVALID", "insight_card.revision must be a positive integer");
  }
  requireNormalizedString(card.statement, "insight_card.statement", { minimum: 10 });
  requireNormalizedStringArray(card.mechanism_path, "insight_card.mechanism_path", {
    minimum: 1,
  });
  requireNormalizedStringArray(card.predictions, "insight_card.predictions", { minimum: 1 });
  requireNormalizedStringArray(card.falsifiers, "insight_card.falsifiers", { minimum: 1 });
  requireNormalizedStringArray(
    card.alternative_hypotheses,
    "insight_card.alternative_hypotheses",
  );
  requireNormalizedString(card.null_model, "insight_card.null_model");
  requireEnum(card.registration_status, REGISTRATION_STATUSES, "insight_card.registration_status");
  requireNormalizedStringArray(card.lens_provenance, "insight_card.lens_provenance");
  card.lens_provenance.forEach((lens, index) =>
    requireEnum(lens, LENS_VALUES, `insight_card.lens_provenance[${index}]`),
  );
  validateTimestamp(card.created_at, "insight_card.created_at");
  requireString(card.registration_hash, "insight_card.registration_hash");
  if (!SHA256_PATTERN.test(card.registration_hash)) {
    fail("INTAKE_INPUT_INVALID", "insight_card.registration_hash must be canonical SHA-256");
  }
  requireEnum(card.risk_class, RISK_CLASSES, "insight_card.risk_class");
  requireNormalizedStringArray(card.terms_to_define, "insight_card.terms_to_define");
  requireNormalizedString(card.decision_context, "insight_card.decision_context");
  requireNormalizedString(card.created_by, "insight_card.created_by");
  requireNormalizedString(card.schema_version, "insight_card.schema_version");
  if (!SEMVER_PATTERN.test(card.schema_version)) {
    fail("INTAKE_INPUT_INVALID", "insight_card.schema_version must be a semantic version");
  }

  validateScope(card.scope);
  return card;
};

const unknownScopeShape = (scope) => {
  const allowed = new Map();
  const add = (path, unknown, required) => allowed.set(path, { required, unknown });
  for (const field of SCOPE_SCALAR_KEYS) {
    add(`scope.${field}`, scope[field] === null, scope[field] === null);
  }
  add("scope.comparator", scope.comparator === null, scope.comparator === null);
  for (const field of ["inclusion_criteria", "exclusion_criteria"]) {
    add(`scope.${field}`, scope[field].length === 0, false);
  }
  for (const field of ["conditions", "domain_extensions"]) {
    add(`scope.${field}`, Object.keys(scope[field]).length === 0, false);
  }
  const intervention = scope.intervention_or_exposure;
  add("scope.intervention_or_exposure", intervention === null, intervention === null);
  if (intervention !== null) {
    for (const field of [
      ...INTERVENTION_NULLABLE_TEXT_KEYS,
      "min_value",
      "max_value",
      "rate",
    ]) {
      add(
        `scope.intervention_or_exposure.${field}`,
        intervention[field] === null,
        intervention[field] === null,
      );
    }
  }
  return allowed;
};

const validateUnknownScope = (raw, scope) => {
  if (!Array.isArray(raw)) fail("INTAKE_INPUT_INVALID", "unknown_scope must be an array");
  const shapes = unknownScopeShape(scope);
  const normalized = raw.map((entry, index) => {
    exactKeys(entry, ["path", "source"], `unknown_scope[${index}]`);
    const result = {
      path: requireString(entry.path, `unknown_scope[${index}].path`),
      source: requireEnum(entry.source, UNKNOWN_SOURCES, `unknown_scope[${index}].source`),
    };
    if (!shapes.get(result.path)?.unknown) {
      fail(
        "INTAKE_UNKNOWN_SCOPE_CONFLICT",
        `${result.path} does not identify an unknown normalized scope value`,
      );
    }
    return result;
  });
  const keys = normalized.map(({ path }) => path);
  if (new Set(keys).size !== keys.length) {
    fail("INTAKE_INPUT_INVALID", "unknown_scope paths must be unique");
  }
  const missingRequired = [...shapes]
    .filter(([, shape]) => shape.required)
    .map(([path]) => path)
    .filter((path) => !keys.includes(path));
  if (missingRequired.length) {
    fail(
      "INTAKE_UNKNOWN_SCOPE_CONFLICT",
      "normalized null scope values require their I02 unknown-origin sidecar",
      { missing_paths: missingRequired.sort() },
    );
  }
  return normalized.sort((left, right) => left.path.localeCompare(right.path));
};

const validateCandidate = (raw, label) => {
  exactKeys(raw, CANDIDATE_KEYS, label);
  const candidate = jsonClone(raw);
  for (const field of ["construct_id", "canonical_label", "authority_ref"]) {
    requireNormalizedString(candidate[field], `${label}.${field}`);
  }
  requireEnum(candidate.entity_kind, ONTOLOGY_ENTITY_KINDS, `${label}.entity_kind`);
  requireBoolean(candidate.viable, `${label}.viable`);
  for (const field of ["matched_dimensions", "missing_dimensions", "conflicting_dimensions"]) {
    requireNormalizedStringArray(candidate[field], `${label}.${field}`, { unique: true });
  }
  const dimensionStates = [
    ...candidate.matched_dimensions.map((dimension) => [dimension, "matched"]),
    ...candidate.missing_dimensions.map((dimension) => [dimension, "missing"]),
    ...candidate.conflicting_dimensions.map((dimension) => [dimension, "conflicting"]),
  ];
  const duplicatedDimensions = dimensionStates
    .map(([dimension]) => dimension)
    .filter((dimension, index, dimensions) => dimensions.indexOf(dimension) !== index);
  if (duplicatedDimensions.length) {
    fail(
      "INTAKE_ONTOLOGY_STATE_CONFLICT",
      `${label} cannot assign one dimension to multiple assessment states`,
      { dimensions: [...new Set(duplicatedDimensions)].sort() },
    );
  }
  if (candidate.viable !== (candidate.conflicting_dimensions.length === 0)) {
    fail(
      "INTAKE_ONTOLOGY_STATE_CONFLICT",
      `${label}.viable must match the I03 conflicting-dimension rule`,
    );
  }
  return candidate;
};

const validateReviewItem = (raw, label) => {
  exactKeys(raw, REVIEW_ITEM_KEYS, label);
  const item = jsonClone(raw);
  requireString(item.review_item_id, `${label}.review_item_id`);
  requireString(item.mapping_key_hash, `${label}.mapping_key_hash`);
  if (!SHA256_PATTERN.test(item.mapping_key_hash)) {
    fail("INTAKE_INPUT_INVALID", `${label}.mapping_key_hash must be canonical SHA-256`);
  }
  requireStringArray(item.candidate_construct_ids, `${label}.candidate_construct_ids`, {
    unique: true,
  });
  requireString(item.proposed_construct_id, `${label}.proposed_construct_id`, { nullable: true });
  requireStringArray(item.reasons, `${label}.reasons`, { minimum: 1, unique: true });
  requireString(item.policy_version, `${label}.policy_version`);
  if (item.required_authority_artifact !== "HumanDecision") {
    fail(
      "INTAKE_AUTHORITY_INVALID",
      `${label}.required_authority_artifact must remain HumanDecision`,
    );
  }
  return item;
};

const validateOntologyResolutions = (raw) => {
  if (!Array.isArray(raw)) {
    fail("INTAKE_INPUT_INVALID", "ontology_resolutions must be an array");
  }
  const normalized = raw.map((entry, index) => {
    const label = `ontology_resolutions[${index}]`;
    exactKeys(entry, ONTOLOGY_KEYS, label);
    const resolution = jsonClone(entry);
    requireString(resolution.resolver_version, `${label}.resolver_version`);
    requireString(resolution.mapping_key_hash, `${label}.mapping_key_hash`);
    if (!SHA256_PATTERN.test(resolution.mapping_key_hash)) {
      fail("INTAKE_INPUT_INVALID", `${label}.mapping_key_hash must be canonical SHA-256`);
    }
    requireEnum(resolution.status, ONTOLOGY_STATUSES, `${label}.status`);
    requireNormalizedString(resolution.selected_construct_id, `${label}.selected_construct_id`, {
      nullable: true,
    });
    requireNormalizedString(resolution.proposed_construct_id, `${label}.proposed_construct_id`, {
      nullable: true,
    });
    if (!Array.isArray(resolution.candidates)) {
      fail("INTAKE_INPUT_INVALID", `${label}.candidates must be an array`);
    }
    resolution.candidates = resolution.candidates.map((candidate, candidateIndex) =>
      validateCandidate(candidate, `${label}.candidates[${candidateIndex}]`),
    );
    requireNormalizedStringArray(resolution.abstention_reasons, `${label}.abstention_reasons`, {
      unique: true,
    });
    if (!Array.isArray(resolution.review_queue_items)) {
      fail("INTAKE_INPUT_INVALID", `${label}.review_queue_items must be an array`);
    }
    resolution.review_queue_items = resolution.review_queue_items.map((item, itemIndex) =>
      validateReviewItem(item, `${label}.review_queue_items[${itemIndex}]`),
    );
    const candidateIds = resolution.candidates.map(({ construct_id }) => construct_id);
    if (new Set(candidateIds).size !== candidateIds.length) {
      fail("INTAKE_ONTOLOGY_STATE_CONFLICT", `${label} candidate construct IDs must be unique`);
    }
    for (const item of resolution.review_queue_items) {
      if (item.mapping_key_hash !== resolution.mapping_key_hash) {
        fail(
          "INTAKE_ONTOLOGY_STATE_CONFLICT",
          "review item mapping_key_hash must match its resolution",
        );
      }
      if (
        item.candidate_construct_ids.some((constructId) => !candidateIds.includes(constructId)) ||
        item.proposed_construct_id !== resolution.proposed_construct_id
      ) {
        fail(
          "INTAKE_ONTOLOGY_STATE_CONFLICT",
          "review item candidates and proposal must remain bound to their resolution",
        );
      }
    }
    const completeCandidates = resolution.candidates.filter(
      (candidate) =>
        candidate.viable &&
        candidate.missing_dimensions.length === 0 &&
        candidate.conflicting_dimensions.length === 0,
    );
    if (resolution.status === "RESOLVED") {
      if (
        resolution.selected_construct_id === null ||
        resolution.proposed_construct_id !== resolution.selected_construct_id ||
        completeCandidates.length !== 1 ||
        completeCandidates[0].construct_id !== resolution.selected_construct_id ||
        resolution.abstention_reasons.length ||
        resolution.review_queue_items.length
      ) {
        fail(
          "INTAKE_ONTOLOGY_STATE_CONFLICT",
          "RESOLVED ontology mappings require exactly one selected complete candidate and no review item",
        );
      }
    } else if (resolution.selected_construct_id !== null) {
      fail("INTAKE_ONTOLOGY_STATE_CONFLICT", "unresolved ontology mappings cannot claim a selected construct");
    }
    if (resolution.status === "PENDING_APPROVAL") {
      if (
        resolution.proposed_construct_id === null ||
        completeCandidates.length !== 1 ||
        completeCandidates[0].construct_id !== resolution.proposed_construct_id ||
        !resolution.abstention_reasons.includes("HUMAN_APPROVAL_REQUIRED") ||
        !resolution.review_queue_items.length
      ) {
        fail(
          "INTAKE_ONTOLOGY_STATE_CONFLICT",
          "PENDING_APPROVAL requires one complete proposal, abstention, and visible review item",
        );
      }
    } else if (resolution.status !== "RESOLVED") {
      if (resolution.proposed_construct_id !== null || !resolution.abstention_reasons.length) {
        fail(
          "INTAKE_ONTOLOGY_STATE_CONFLICT",
          "AMBIGUOUS and UNKNOWN mappings must abstain without proposing a construct",
        );
      }
    }
    return resolution;
  });
  const keys = normalized.map(({ mapping_key_hash }) => mapping_key_hash);
  if (new Set(keys).size !== keys.length) {
    fail("INTAKE_INPUT_INVALID", "ontology mapping keys must be unique");
  }
  return normalized.sort((left, right) => left.mapping_key_hash.localeCompare(right.mapping_key_hash));
};

const validateMeasurementCompatibilities = (raw) => {
  if (!Array.isArray(raw)) {
    fail("INTAKE_INPUT_INVALID", "measurement_compatibilities must be an array");
  }
  const normalized = raw.map((entry, index) => {
    const label = `measurement_compatibilities[${index}]`;
    exactKeys(entry, MEASUREMENT_KEYS, label);
    const result = jsonClone(entry);
    for (const field of ["left_measurement_id", "right_measurement_id"]) {
      requireString(result[field], `${label}.${field}`);
    }
    for (const field of ["left_identity_hash", "right_identity_hash"]) {
      requireString(result[field], `${label}.${field}`);
      if (!SHA256_PATTERN.test(result[field])) {
        fail("INTAKE_INPUT_INVALID", `${label}.${field} must be canonical SHA-256`);
      }
    }
    requireEnum(result.compatibility_status, COMPATIBILITY_STATUSES, `${label}.compatibility_status`);
    requireEnum(result.construct_equivalence, CONSTRUCT_EQUIVALENCE, `${label}.construct_equivalence`);
    requireStringArray(result.required_transformations, `${label}.required_transformations`, {
      unique: true,
    });
    requireStringArray(result.method_threats, `${label}.method_threats`, { unique: true });
    requireEnum(result.promotion_ceiling, PROMOTION_CEILINGS, `${label}.promotion_ceiling`);
    requireString(result.bridge_id, `${label}.bridge_id`, { nullable: true });
    requireBoolean(result.aggregation_allowed, `${label}.aggregation_allowed`);
    const expectedAggregation =
      result.construct_equivalence === "SAME" &&
      ["DIRECTLY_COMPARABLE", "CONVERTIBLE"].includes(result.compatibility_status) &&
      ["NO_RESTRICTION", "CONDITIONAL_ONLY"].includes(result.promotion_ceiling);
    if (result.aggregation_allowed !== expectedAggregation) {
      fail(
        "INTAKE_MEASUREMENT_STATE_CONFLICT",
        "aggregation_allowed must exactly match the I03 compatibility decision",
      );
    }
    if (
      result.promotion_ceiling === "NO_RESTRICTION" &&
      (result.construct_equivalence !== "SAME" ||
        result.compatibility_status !== "DIRECTLY_COMPARABLE")
    ) {
      fail(
        "INTAKE_MEASUREMENT_STATE_CONFLICT",
        "NO_RESTRICTION requires SAME and DIRECTLY_COMPARABLE",
      );
    }
    if (
      result.compatibility_status === "CONVERTIBLE" &&
      (!result.required_transformations.length || result.bridge_id === null)
    ) {
      fail(
        "INTAKE_MEASUREMENT_STATE_CONFLICT",
        "CONVERTIBLE requires an explicit transformation and bridge",
      );
    }
    if (
      result.compatibility_status === "DIRECTLY_COMPARABLE" &&
      result.required_transformations.length
    ) {
      fail(
        "INTAKE_MEASUREMENT_STATE_CONFLICT",
        "DIRECTLY_COMPARABLE cannot require a transformation",
      );
    }
    return result;
  });
  const keys = normalized.map(
    ({ left_identity_hash, right_identity_hash }) => `${left_identity_hash}:${right_identity_hash}`,
  );
  if (new Set(keys).size !== keys.length) {
    fail("INTAKE_INPUT_INVALID", "measurement identity pairs must be unique");
  }
  return normalized.sort((left, right) =>
    `${left.left_identity_hash}:${left.right_identity_hash}`.localeCompare(
      `${right.left_identity_hash}:${right.right_identity_hash}`,
    ),
  );
};

const validateConsentRecord = (raw, label) => {
  exactKeys(raw, CONSENT_RECORD_KEYS, label);
  const record = jsonClone(raw);
  for (const field of ["consent_id", "subject_id", "workspace_id", "recorded_by"]) {
    requireString(record[field], `${label}.${field}`, { minimum: 3 });
  }
  for (const field of ["purposes", "data_classes", "scopes"]) {
    requireStringArray(record[field], `${label}.${field}`, { minimum: 1, unique: true });
  }
  requireEnum(record.decision, CONSENT_DECISIONS, `${label}.decision`);
  for (const field of ["granted_at", "expires_at", "revoked_at"]) {
    validateTimestamp(record[field], `${label}.${field}`, { nullable: true });
  }
  for (const field of ["policy_hash", "record_hash"]) {
    requireString(record[field], `${label}.${field}`);
    if (!SHA256_PATTERN.test(record[field])) {
      fail("INTAKE_INPUT_INVALID", `${label}.${field} must be canonical SHA-256`);
    }
  }
  return record;
};

const validateConsentRequirement = (raw) => {
  exactKeys(raw, CONSENT_REQUIREMENT_KEYS, "consent_requirement");
  const requirement = jsonClone(raw);
  requireBoolean(requirement.required, "consent_requirement.required");
  validateTimestamp(requirement.evaluated_at, "consent_requirement.evaluated_at", {
    nullable: true,
  });
  for (const field of ["required_purposes", "required_data_classes", "required_scopes"]) {
    requireStringArray(requirement[field], `consent_requirement.${field}`, { unique: true });
  }
  if (!Array.isArray(requirement.records)) {
    fail("INTAKE_INPUT_INVALID", "consent_requirement.records must be an array");
  }
  requirement.records = requirement.records.map((record, index) =>
    validateConsentRecord(record, `consent_requirement.records[${index}]`),
  );
  if (requirement.required) {
    for (const field of ["required_purposes", "required_data_classes", "required_scopes"]) {
      if (!requirement[field].length) {
        fail("INTAKE_CONSENT_REQUIREMENT_INVALID", `required consent must declare ${field}`);
      }
    }
  }
  const ids = requirement.records.map(({ consent_id }) => consent_id);
  if (new Set(ids).size !== ids.length) {
    fail("INTAKE_INPUT_INVALID", "consent record IDs must be unique");
  }
  requirement.records.sort((left, right) => left.consent_id.localeCompare(right.consent_id));
  return requirement;
};

const blocker = (source, code, subject, message) => ({ code, message, source, subject });
const notice = (source, code, subject, message) => ({ code, message, source, subject });

const consentCovers = (record, requirement) => {
  const containsAll = (actual, expected) => expected.every((value) => actual.includes(value));
  if (
    record.decision !== "GRANTED" ||
    record.granted_at === null ||
    record.revoked_at !== null ||
    !containsAll(record.purposes, requirement.required_purposes) ||
    !containsAll(record.data_classes, requirement.required_data_classes) ||
    !containsAll(record.scopes, requirement.required_scopes)
  ) {
    return false;
  }
  if (requirement.evaluated_at === null) return record.expires_at === null;
  const evaluated = parseTimestamp(
    requirement.evaluated_at,
    "consent_requirement.evaluated_at",
  );
  const granted = parseTimestamp(
    record.granted_at,
    `consent record ${record.consent_id}.granted_at`,
  );
  if (compareTimestamps(granted, evaluated) > 0) return false;
  if (record.expires_at === null) return true;
  const expires = parseTimestamp(
    record.expires_at,
    `consent record ${record.consent_id}.expires_at`,
  );
  return compareTimestamps(expires, evaluated) > 0;
};

const deriveCouncilExpectations = (card) => {
  const expected = [];
  if (card.registration_status !== "eligible") {
    expected.push("COUNCIL_REGISTRATION_STATUS_NOT_ELIGIBLE");
  }
  for (const field of ["domain", "population", "unit_of_analysis"]) {
    if (card.scope[field] === null) expected.push(`COUNCIL_SCOPE_${field.toUpperCase()}_UNKNOWN`);
  }
  if (card.terms_to_define.length) expected.push("COUNCIL_UNDEFINED_CONSTRUCTS");
  return expected;
};

const deriveGate = ({
  card,
  consentRequirement,
  councilBlockers,
  measurementCompatibilities,
  ontologyResolutions,
  unknownScope,
}) => {
  const blockers = councilBlockers.map((code) =>
    blocker("I02", code, card.insight_id, `Frame compiler blocker: ${code}`),
  );
  const notices = unknownScope.map(({ path, source }) =>
    notice("I02", "SCOPE_VALUE_UNKNOWN", path, `${path} remains unknown (${source})`),
  );

  for (const resolution of ontologyResolutions) {
    if (resolution.status !== "RESOLVED") {
      blockers.push(
        blocker(
          "I03",
          resolution.status === "PENDING_APPROVAL"
            ? "ONTOLOGY_HUMAN_APPROVAL_REQUIRED"
            : "ONTOLOGY_RESOLUTION_REQUIRED",
          resolution.mapping_key_hash,
          `Ontology mapping remains ${resolution.status}`,
        ),
      );
    }
    for (const item of resolution.review_queue_items) {
      notices.push(
        notice(
          "I03",
          "ONTOLOGY_REVIEW_QUEUED",
          item.review_item_id,
          `${item.required_authority_artifact} is required for ${item.review_item_id}`,
        ),
      );
    }
  }

  for (const result of measurementCompatibilities) {
    const subject = `${result.left_measurement_id}/${result.right_measurement_id}`;
    if (result.compatibility_status === "UNKNOWN") {
      blockers.push(
        blocker("I03", "MEASUREMENT_RESOLUTION_REQUIRED", subject, "Measurement compatibility is UNKNOWN"),
      );
    } else if (
      result.compatibility_status === "NOT_COMPARABLE" ||
      result.promotion_ceiling === "BLOCK_AGGREGATION"
    ) {
      blockers.push(
        blocker(
          "I03",
          "MEASUREMENT_AGGREGATION_BLOCKED",
          subject,
          `Measurement result is ${result.compatibility_status} with ${result.promotion_ceiling}`,
        ),
      );
    } else if (
      result.compatibility_status !== "DIRECTLY_COMPARABLE" ||
      result.promotion_ceiling !== "NO_RESTRICTION"
    ) {
      notices.push(
        notice(
          "I03",
          "MEASUREMENT_BOUNDARY_VISIBLE",
          subject,
          `Measurement boundary: ${result.compatibility_status}, ceiling ${result.promotion_ceiling}`,
        ),
      );
    }
  }

  if (consentRequirement.required) {
    if (consentRequirement.evaluated_at === null) {
      blockers.push(
        blocker(
          "CONSENT",
          "CONSENT_EVALUATION_TIME_REQUIRED",
          card.insight_id,
          "Consent validity cannot be proven without an evaluation time",
        ),
      );
    } else if (!consentRequirement.records.some((record) => consentCovers(record, consentRequirement))) {
      blockers.push(
        blocker(
          "CONSENT",
          "CONSENT_REQUIRED",
          card.insight_id,
          "No active ConsentRecord covers the required purpose, data class, and scope",
        ),
      );
    }
  }

  const uniqueSorted = (entries) => {
    const byKey = new Map();
    for (const entry of entries) {
      const key = `${entry.source}:${entry.code}:${entry.subject}`;
      if (!byKey.has(key)) byKey.set(key, entry);
    }
    return [...byKey.values()].sort((left, right) => {
      const leftKey = `${left.source}:${left.code}:${left.subject}`;
      const rightKey = `${right.source}:${right.code}:${right.subject}`;
      return leftKey.localeCompare(rightKey);
    });
  };
  return { blockers: uniqueSorted(blockers), notices: uniqueSorted(notices) };
};

export function assembleIntakeFrame(input) {
  exactKeys(input, INPUT_KEYS, "intake input");
  const card = validateInsightCard(input.insight_card);
  const councilReady = requireBoolean(input.council_ready, "council_ready");
  const councilBlockers = requireStringArray(input.council_blockers, "council_blockers", {
    unique: true,
  });
  const expectedCouncilBlockers = deriveCouncilExpectations(card);
  const missingCouncilBlockers = expectedCouncilBlockers.filter(
    (code) => !councilBlockers.includes(code),
  );
  const extraCouncilBlockers = councilBlockers.filter(
    (code) => !expectedCouncilBlockers.includes(code),
  );
  const councilOrderMatches =
    councilBlockers.length === expectedCouncilBlockers.length &&
    councilBlockers.every((code, index) => code === expectedCouncilBlockers[index]);
  if (!councilOrderMatches) {
    fail("INTAKE_COUNCIL_STATE_CONFLICT", "I02 blockers must exactly match canonical output", {
      actual_blockers: councilBlockers,
      expected_blockers: expectedCouncilBlockers,
      extra_blockers: extraCouncilBlockers,
      missing_blockers: missingCouncilBlockers,
    });
  }
  if (card.registration_status === "eligible" && expectedCouncilBlockers.length) {
    fail(
      "INTAKE_COUNCIL_STATE_CONFLICT",
      "I02 cannot emit an eligible InsightCard that retains council blockers",
    );
  }
  if (councilReady !== (councilBlockers.length === 0)) {
    fail("INTAKE_COUNCIL_STATE_CONFLICT", "council_ready must agree with council_blockers");
  }
  if (councilReady && card.registration_status !== "eligible") {
    fail("INTAKE_COUNCIL_STATE_CONFLICT", "only an eligible card can be council-ready");
  }

  const unknownScope = validateUnknownScope(input.unknown_scope, card.scope);
  const ontologyResolutions = validateOntologyResolutions(input.ontology_resolutions);
  const measurementCompatibilities = validateMeasurementCompatibilities(
    input.measurement_compatibilities,
  );
  const consentRequirement = validateConsentRequirement(input.consent_requirement);
  const gate = deriveGate({
    card,
    consentRequirement,
    councilBlockers,
    measurementCompatibilities,
    ontologyResolutions,
    unknownScope,
  });

  return deepFreeze({
    blockers: gate.blockers,
    consent_requirement: consentRequirement,
    council_blockers: [...councilBlockers],
    council_ready: councilReady,
    exportable: councilReady && gate.blockers.length === 0,
    insight_card: card,
    kind: INTAKE_FRAME_KIND,
    measurement_compatibilities: measurementCompatibilities,
    notices: gate.notices,
    ontology_resolutions: ontologyResolutions,
    unknown_scope: unknownScope,
    version: INTAKE_FRAME_VERSION,
  });
}

const sourceInputFromFrame = (frame) => ({
  consent_requirement: frame.consent_requirement,
  council_blockers: frame.council_blockers,
  council_ready: frame.council_ready,
  insight_card: frame.insight_card,
  measurement_compatibilities: frame.measurement_compatibilities,
  ontology_resolutions: frame.ontology_resolutions,
  unknown_scope: frame.unknown_scope,
});

const validateAssembledFrame = (candidate) => {
  const frame = requireRecord(candidate, "frame");
  const rebuilt = assembleIntakeFrame(sourceInputFromFrame(frame));
  if (canonicalJson(frame) !== canonicalJson(rebuilt)) {
    fail("INTAKE_FRAME_DERIVATION_MISMATCH", "frame-derived gate fields do not match authority inputs");
  }
  return rebuilt;
};

export function validateIntakeFrame(candidate) {
  return validateAssembledFrame(candidate);
}

export function serializeIntakeFrame(candidate) {
  const frame = validateAssembledFrame(candidate);
  if (!frame.exportable) {
    fail("INTAKE_EXPORT_BLOCKED", "frame export is denied while blockers remain", {
      blockers: frame.blockers.map(({ code, source, subject }) => ({ code, source, subject })),
    });
  }
  const preimage = {
    format: INTAKE_EXPORT_FORMAT,
    frame,
  };
  const frameHash = sha256(encodeUtf8(canonicalJson(preimage)));
  return encodeUtf8(canonicalJson({ ...preimage, frame_hash: frameHash }));
}

const decodeUtf8 = (serialized) => {
  if (
    typeof serialized !== "string" &&
    !(serialized instanceof Uint8Array)
  ) {
    fail("INTAKE_FRAME_INVALID", "serialized frame must be UTF-8 text or bytes");
  }
  if (typeof serialized === "string") return serialized;
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(serialized);
  } catch (error) {
    throw new IntakeContractError("INTAKE_FRAME_INVALID_UTF8", "serialized frame is not valid UTF-8", {
      cause: error.name,
    });
  }
};

export function parseIntakeFrame(serialized) {
  const text = decodeUtf8(serialized);
  let envelope;
  try {
    envelope = JSON.parse(text);
  } catch (error) {
    throw new IntakeContractError("INTAKE_FRAME_INVALID_JSON", "serialized frame is not valid JSON", {
      cause: error.name,
    });
  }
  exactKeys(envelope, ["format", "frame", "frame_hash"], "export envelope");
  if (envelope.format !== INTAKE_EXPORT_FORMAT) {
    fail("INTAKE_FRAME_FORMAT_UNSUPPORTED", "export envelope format is not supported");
  }
  requireString(envelope.frame_hash, "export envelope.frame_hash");
  if (!SHA256_PATTERN.test(envelope.frame_hash)) {
    fail("INTAKE_FRAME_HASH_INVALID", "export envelope.frame_hash is not canonical SHA-256");
  }
  const preimage = { format: envelope.format, frame: envelope.frame };
  const expectedHash = sha256(encodeUtf8(canonicalJson(preimage)));
  if (envelope.frame_hash !== expectedHash) {
    fail("INTAKE_FRAME_HASH_MISMATCH", "export envelope content does not match frame_hash");
  }
  if (text !== canonicalJson(envelope)) {
    fail("INTAKE_FRAME_NOT_CANONICAL", "export envelope must use deterministic canonical JSON bytes");
  }
  const frame = validateAssembledFrame(envelope.frame);
  if (!frame.exportable) {
    fail("INTAKE_EXPORT_BLOCKED", "a serialized frame cannot retain export blockers");
  }
  return frame;
}

export function frameSha256(candidate) {
  return sha256(serializeIntakeFrame(candidate));
}

export const intakeInternalsForTests = Object.freeze({ canonicalJson });
