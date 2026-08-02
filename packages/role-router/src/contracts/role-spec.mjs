import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;

export const ROLE_SPEC_VERSION = "4.0.0-n01.1";
export const ROLE_SPEC_ID_PREFIX = "ROLE-";

export const MODEL_TIERS = OBJECT_FREEZE([
  "balanced",
  "deterministic",
  "economy",
  "frontier",
]);

export const FAILURE_POLICIES = OBJECT_FREEZE([
  "escalate",
  "fail_run",
  "mark_partial",
]);

// This is the exact active workflow capability vocabulary at N01 freeze time.
// Dotted and colon-delimited aliases are deliberately absent.
export const TOOL_CAPABILITIES = OBJECT_FREEZE([
  "approved_external_search",
  "artifact_read",
  "artifact_write",
  "database_read",
  "database_write",
  "document_register",
  "filesystem_read",
  "filesystem_write",
  "fulltext_search",
  "graph_query",
  "human_approval",
  "human_input",
  "ledger_append",
  "llm_inference",
  "network_fetch",
  "network_read",
  "object_store_read",
  "object_store_write",
  "python_analysis",
  "sandbox_execute",
  "signing_service",
  "subagent_dispatch",
  "vector_search",
  "workflow_dispatch",
]);

// These labels are the bounded evidence views declared by the current role
// authority. `all_permitted` is an explicit privileged view, not a default.
export const EVIDENCE_CLASSES = OBJECT_FREEZE([
  "adapter_test_results",
  "adjudication_pack",
  "all_permitted",
  "archive_public",
  "attestation_pack",
  "backend_manifest",
  "boundary",
  "candidate_parent",
  "candidate_public",
  "challenge_archive",
  "citation",
  "counter",
  "evaluation_results",
  "evaluator_public",
  "evidence_pack",
  "evolution_state",
  "external_novelty",
  "fitness_public",
  "holdout_metadata",
  "implementation_contract",
  "measurement_contract",
  "mechanism",
  "method",
  "methods",
  "null",
  "primary_results",
  "prompt_quarantine",
  "replication_pack",
  "results",
  "sealed_promotion_pack",
  "selection_events",
  "source_span",
  "support",
  "temporal",
  "theory",
  "validation_plan",
]);

const MODEL_TIER_SET = new Set(MODEL_TIERS);
const FAILURE_POLICY_SET = new Set(FAILURE_POLICIES);
const TOOL_CAPABILITY_SET = new Set(TOOL_CAPABILITIES);
const EVIDENCE_CLASS_SET = new Set(EVIDENCE_CLASSES);
const ACL_KINDS = new Set(["evidence", "network", "read", "tool", "write"]);
const ID_PATTERN = /^[a-z][a-z0-9_]{2,127}$/u;
const ROLE_SPEC_ID_PATTERN = /^ROLE-[0-9a-f]{64}$/u;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const SCOPE_SEGMENT_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]*$/u;
const SCHEMA_REF_PATTERN = /^schemas\/[A-Za-z0-9][A-Za-z0-9._/-]*\.schema\.json$/u;

const ROLE_SPEC_PREIMAGE_FIELDS = OBJECT_FREEZE([
  "role_spec_version",
  "role_id",
  "mission",
  "forbidden_behaviors",
  "host_agent_type",
  "model_tier",
  "fallback_model_tiers",
  "read_scope",
  "write_scope",
  "tool_acl",
  "network_acl",
  "evidence_acl",
  "input_schema_refs",
  "output_schema_ref",
  "budget_tokens",
  "timeout_seconds",
  "expected_count",
  "independence_group",
  "acceptance_checks",
  "failure_policy",
  "max_attempts",
  "depends_on",
]);

const ROLE_SPEC_FIELDS = OBJECT_FREEZE([
  "role_spec_id",
  ...ROLE_SPEC_PREIMAGE_FIELDS,
  "role_spec_hash",
]);

const DISPATCH_ROLE_FIELDS = OBJECT_FREEZE([
  "role_id",
  "host_agent_type",
  "model_tier",
  "tool_acl",
  "evidence_acl",
  "read_scope",
  "write_scope",
  "depends_on",
  "budget_tokens",
  "timeout_seconds",
  "independence_group",
]);

export class RoleSpecContractError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "RoleSpecContractError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(canonicalClone(details));
  }
}

const fail = (code, message, details = undefined) => {
  throw new RoleSpecContractError(code, message, details);
};

const compareUtf8 = (left, right) =>
  Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));

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

const requireText = (
  value,
  label,
  { minLength = 1, maxLength = 4_096, code = "INVALID_INPUT" } = {},
) => {
  const length = typeof value === "string" ? [...value].length : -1;
  if (
    typeof value !== "string" ||
    !hasOnlyUnicodeScalars(value) ||
    value.normalize("NFC") !== value ||
    /\p{Cc}/u.test(value) ||
    length < minLength ||
    length > maxLength ||
    (minLength > 0 && value.trim().length === 0)
  ) {
    fail(code, `${label} must be a bounded non-blank NFC Unicode scalar string`);
  }
  return value;
};

const requireIdentifier = (value, label) => {
  const identifier = requireText(value, label, { minLength: 3, maxLength: 128 });
  if (!ID_PATTERN.test(identifier)) {
    fail("INVALID_IDENTIFIER", `${label} must use canonical lowercase snake_case`);
  }
  return identifier;
};

const requirePlainDataObject = (value, label, fields) => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    (OBJECT_GET_PROTOTYPE_OF(value) !== Object.prototype &&
      OBJECT_GET_PROTOTYPE_OF(value) !== null)
  ) {
    fail("INVALID_INPUT", `${label} must be a non-proxy plain data object`);
  }
  const allowed = new Set(fields);
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
      fail(
        "ACCESSOR_FIELD_DENIED",
        `${label}.${String(key)} must be an enumerable data property`,
      );
    }
  }
  for (const field of fields) {
    if (!OBJECT_HAS_OWN(value, field)) {
      fail("MISSING_FIELD", `${label}.${field} is required`);
    }
  }
  return value;
};

const readDataProperty = (record, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(record, key).value;

const readDenseArray = (value, label) => {
  if (
    !ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== Array.prototype
  ) {
    fail("INVALID_INPUT", `${label} must be a non-proxy plain dense array`);
  }
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
      fail("INVALID_INPUT", `${label} contains a non-element property`);
    }
    const index = Number(key);
    if (!Number.isSafeInteger(index) || index >= value.length || String(index) !== key) {
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
      fail("INVALID_INPUT", `${label} contains a sparse or accessor-backed element`);
    }
    result[index] = descriptor.value;
  }
  return result;
};

const requireSafeInteger = (value, label, { minimum, maximum }) => {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    fail("INVALID_INTEGER", `${label} must be an integer in [${minimum}, ${maximum}]`);
  }
  return value;
};

const requireEnum = (value, label, values, code) => {
  if (typeof value !== "string" || !values.has(value)) {
    fail(code, `${label} is outside the canonical vocabulary`);
  }
  return value;
};

const normalizeUniqueArray = (
  value,
  label,
  validator,
  { allowEmpty = true, sort = true, requireCanonical = false } = {},
) => {
  const entries = readDenseArray(value, label).map((entry, index) =>
    validator(entry, `${label}[${index}]`),
  );
  if (!allowEmpty && entries.length === 0) {
    fail("EMPTY_REQUIRED_ARRAY", `${label} must not be empty`);
  }
  if (new Set(entries).size !== entries.length) {
    fail("DUPLICATE_VALUE", `${label} must contain unique values`);
  }
  if (sort) {
    const sorted = [...entries].sort(compareUtf8);
    if (requireCanonical && entries.some((entry, index) => entry !== sorted[index])) {
      fail("NON_CANONICAL_ORDER", `${label} must use ascending UTF-8 byte order`);
    }
    return sorted;
  }
  return entries;
};

const requireScope = (value, label, { patternAllowed }) => {
  const scope = requireText(value, label, { minLength: 1, maxLength: 512 });
  if (
    scope.includes("\\") ||
    scope.startsWith("/") ||
    /^[A-Za-z]:/u.test(scope) ||
    scope.includes("//") ||
    scope.includes("?") ||
    scope.includes("#") ||
    scope === "**"
  ) {
    fail("INVALID_SCOPE", `${label} must be a safe repository-relative scope`);
  }
  const segments = scope.split("/");
  const hasPattern = segments.at(-1) === "**";
  if (hasPattern && (!patternAllowed || segments.length < 2)) {
    fail("INVALID_SCOPE", `${label} uses a forbidden broadening pattern`);
  }
  const pathSegments = hasPattern ? segments.slice(0, -1) : segments;
  if (
    pathSegments.length === 0 ||
    pathSegments.some(
      (segment) =>
        segment === "." ||
        segment === ".." ||
        !SCOPE_SEGMENT_PATTERN.test(segment),
    ) ||
    (!hasPattern && segments.includes("**"))
  ) {
    fail("INVALID_SCOPE", `${label} must not traverse or contain wildcard segments`);
  }
  return scope;
};

const requireScopePattern = (value, label) =>
  requireScope(value, label, { patternAllowed: true });

const requireResourcePath = (value, label) =>
  requireScope(value, label, { patternAllowed: false });

const requireSchemaRef = (value, label) => {
  const reference = requireResourcePath(value, label);
  if (!SCHEMA_REF_PATTERN.test(reference)) {
    fail("INVALID_SCHEMA_REF", `${label} must reference schemas/*.schema.json`);
  }
  return reference;
};

const requireNetworkOrigin = (value, label) => {
  const origin = requireText(value, label, { minLength: 12, maxLength: 512 });
  let parsed;
  try {
    parsed = new URL(origin);
  } catch {
    fail("INVALID_NETWORK_ORIGIN", `${label} must be an exact HTTPS origin`);
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    parsed.pathname !== "/" ||
    parsed.search !== "" ||
    parsed.hash !== "" ||
    parsed.origin !== origin ||
    origin.includes("*") ||
    parsed.hostname !== parsed.hostname.toLowerCase()
  ) {
    fail(
      "INVALID_NETWORK_ORIGIN",
      `${label} must be a canonical exact HTTPS origin without credentials or path`,
    );
  }
  return origin;
};

const requireToolCapability = (value, label) => {
  if (typeof value === "string" && /[.:]/u.test(value)) {
    fail(
      "CAPABILITY_VOCABULARY_MISMATCH",
      `${label} must not use dotted or colon-delimited capability aliases`,
    );
  }
  return requireEnum(
    value,
    label,
    TOOL_CAPABILITY_SET,
    "UNKNOWN_TOOL_CAPABILITY",
  );
};

const requireEvidenceClass = (value, label) =>
  requireEnum(value, label, EVIDENCE_CLASS_SET, "UNKNOWN_EVIDENCE_CLASS");

const requireModelTier = (value, label) =>
  requireEnum(value, label, MODEL_TIER_SET, "UNKNOWN_MODEL_TIER");

const requireFailurePolicy = (value, label) =>
  requireEnum(value, label, FAILURE_POLICY_SET, "UNKNOWN_FAILURE_POLICY");

const normalizePreimage = (candidate, { requireCanonical }) => {
  const record = requirePlainDataObject(
    candidate,
    "RoleSpec preimage",
    ROLE_SPEC_PREIMAGE_FIELDS,
  );
  const roleSpecVersion = readDataProperty(record, "role_spec_version");
  if (roleSpecVersion !== ROLE_SPEC_VERSION) {
    fail(
      "ROLE_SPEC_VERSION_UNSUPPORTED",
      `role_spec_version must be ${ROLE_SPEC_VERSION}`,
    );
  }
  const roleId = requireIdentifier(readDataProperty(record, "role_id"), "role_id");
  const modelTier = requireModelTier(readDataProperty(record, "model_tier"), "model_tier");
  const fallbackModelTiers = normalizeUniqueArray(
    readDataProperty(record, "fallback_model_tiers"),
    "fallback_model_tiers",
    requireModelTier,
    { sort: false },
  );
  if (fallbackModelTiers.includes(modelTier)) {
    fail(
      "INVALID_MODEL_FALLBACK",
      "fallback_model_tiers must not repeat the primary model_tier",
    );
  }
  const dependsOn = normalizeUniqueArray(
    readDataProperty(record, "depends_on"),
    "depends_on",
    requireIdentifier,
    { requireCanonical },
  );
  if (dependsOn.includes(roleId)) {
    fail("SELF_DEPENDENCY", "a RoleSpec cannot depend on itself");
  }
  return {
    role_spec_version: roleSpecVersion,
    role_id: roleId,
    mission: requireText(readDataProperty(record, "mission"), "mission", {
      minLength: 3,
      maxLength: 2_048,
    }),
    forbidden_behaviors: normalizeUniqueArray(
      readDataProperty(record, "forbidden_behaviors"),
      "forbidden_behaviors",
      (entry, label) => requireText(entry, label, { minLength: 3, maxLength: 512 }),
      { allowEmpty: false, requireCanonical },
    ),
    host_agent_type: requireIdentifier(
      readDataProperty(record, "host_agent_type"),
      "host_agent_type",
    ),
    model_tier: modelTier,
    fallback_model_tiers: fallbackModelTiers,
    read_scope: normalizeUniqueArray(
      readDataProperty(record, "read_scope"),
      "read_scope",
      requireScopePattern,
      { requireCanonical },
    ),
    write_scope: normalizeUniqueArray(
      readDataProperty(record, "write_scope"),
      "write_scope",
      requireScopePattern,
      { requireCanonical },
    ),
    tool_acl: normalizeUniqueArray(
      readDataProperty(record, "tool_acl"),
      "tool_acl",
      requireToolCapability,
      { requireCanonical },
    ),
    network_acl: normalizeUniqueArray(
      readDataProperty(record, "network_acl"),
      "network_acl",
      requireNetworkOrigin,
      { requireCanonical },
    ),
    evidence_acl: normalizeUniqueArray(
      readDataProperty(record, "evidence_acl"),
      "evidence_acl",
      requireEvidenceClass,
      { requireCanonical },
    ),
    input_schema_refs: normalizeUniqueArray(
      readDataProperty(record, "input_schema_refs"),
      "input_schema_refs",
      requireSchemaRef,
      { allowEmpty: false, requireCanonical },
    ),
    output_schema_ref: requireSchemaRef(
      readDataProperty(record, "output_schema_ref"),
      "output_schema_ref",
    ),
    budget_tokens: requireSafeInteger(readDataProperty(record, "budget_tokens"), "budget_tokens", {
      minimum: 0,
      maximum: Number.MAX_SAFE_INTEGER,
    }),
    timeout_seconds: requireSafeInteger(
      readDataProperty(record, "timeout_seconds"),
      "timeout_seconds",
      { minimum: 1, maximum: 86_400 },
    ),
    expected_count: requireSafeInteger(
      readDataProperty(record, "expected_count"),
      "expected_count",
      { minimum: 1, maximum: 16 },
    ),
    independence_group: requireIdentifier(
      readDataProperty(record, "independence_group"),
      "independence_group",
    ),
    acceptance_checks: normalizeUniqueArray(
      readDataProperty(record, "acceptance_checks"),
      "acceptance_checks",
      (entry, label) => requireText(entry, label, { minLength: 3, maxLength: 512 }),
      { allowEmpty: false, requireCanonical },
    ),
    failure_policy: requireFailurePolicy(
      readDataProperty(record, "failure_policy"),
      "failure_policy",
    ),
    max_attempts: requireSafeInteger(readDataProperty(record, "max_attempts"), "max_attempts", {
      minimum: 1,
      maximum: 10,
    }),
    depends_on: dependsOn,
  };
};

const normalizePersistedRoleSpec = (candidate) => {
  const record = requirePlainDataObject(candidate, "RoleSpec", ROLE_SPEC_FIELDS);
  const preimageCandidate = {};
  for (const field of ROLE_SPEC_PREIMAGE_FIELDS) {
    preimageCandidate[field] = readDataProperty(record, field);
  }
  const preimage = normalizePreimage(preimageCandidate, { requireCanonical: true });
  const roleSpecHash = readDataProperty(record, "role_spec_hash");
  if (typeof roleSpecHash !== "string" || !SHA256_PATTERN.test(roleSpecHash)) {
    fail("INVALID_HASH", "role_spec_hash must be sha256:<64 lowercase hex>");
  }
  const expectedHash = sha256CanonicalJson(preimage);
  if (roleSpecHash !== expectedHash) {
    fail("ROLE_SPEC_HASH_MISMATCH", "role_spec_hash does not bind the canonical RoleSpec", {
      expected: expectedHash,
      observed: roleSpecHash,
    });
  }
  const roleSpecId = readDataProperty(record, "role_spec_id");
  if (typeof roleSpecId !== "string" || !ROLE_SPEC_ID_PATTERN.test(roleSpecId)) {
    fail("INVALID_ROLE_SPEC_ID", "role_spec_id must be ROLE-<64 lowercase hex>");
  }
  const expectedId = `${ROLE_SPEC_ID_PREFIX}${expectedHash.slice("sha256:".length)}`;
  if (roleSpecId !== expectedId) {
    fail("ROLE_SPEC_ID_MISMATCH", "role_spec_id does not derive from role_spec_hash", {
      expected: expectedId,
      observed: roleSpecId,
    });
  }
  return { role_spec_id: roleSpecId, ...preimage, role_spec_hash: roleSpecHash };
};

const canonicalizeValue = (value, ancestors) => {
  if (value === null) return "null";
  if (typeof value === "string") {
    if (!hasOnlyUnicodeScalars(value) || value.normalize("NFC") !== value) {
      fail("NON_CANONICAL_JSON", "canonical JSON string must be NFC Unicode scalar text");
    }
    return JSON.stringify(value);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || Object.is(value, -0)) {
      fail("NON_CANONICAL_JSON", "RoleSpec canonical JSON only accepts safe integers");
    }
    return JSON.stringify(value);
  }
  if (ARRAY_IS_ARRAY(value)) {
    if (ancestors.has(value)) fail("NON_CANONICAL_JSON", "canonical JSON cannot contain a cycle");
    const entries = readDenseArray(value, "canonical JSON array");
    ancestors.add(value);
    try {
      return `[${entries.map((entry) => canonicalizeValue(entry, ancestors)).join(",")}]`;
    } finally {
      ancestors.delete(value);
    }
  }
  if (
    value === undefined ||
    typeof value !== "object" ||
    IS_PROXY(value) ||
    (OBJECT_GET_PROTOTYPE_OF(value) !== Object.prototype &&
      OBJECT_GET_PROTOTYPE_OF(value) !== null)
  ) {
    fail("NON_CANONICAL_JSON", "canonical JSON contains an unsupported value");
  }
  if (ancestors.has(value)) fail("NON_CANONICAL_JSON", "canonical JSON cannot contain a cycle");
  const keys = REFLECT_OWN_KEYS(value);
  if (keys.some((key) => typeof key !== "string")) {
    fail("NON_CANONICAL_JSON", "canonical JSON object contains a symbol key");
  }
  keys.sort(compareUtf8);
  ancestors.add(value);
  try {
    return `{${keys
      .map((key) => {
        const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
        if (
          descriptor === undefined ||
          !descriptor.enumerable ||
          !OBJECT_HAS_OWN(descriptor, "value")
        ) {
          fail("NON_CANONICAL_JSON", "canonical JSON object contains an accessor field");
        }
        return `${JSON.stringify(key)}:${canonicalizeValue(descriptor.value, ancestors)}`;
      })
      .join(",")}}`;
  } finally {
    ancestors.delete(value);
  }
};

export const canonicalizeRoleSpecJson = (value) => canonicalizeValue(value, new Set());

const canonicalClone = (value) => JSON.parse(canonicalizeRoleSpecJson(value));

const sha256CanonicalJson = (value) =>
  `sha256:${createHash("sha256")
    .update(canonicalizeRoleSpecJson(value), "utf8")
    .digest("hex")}`;

function deepFreeze(value) {
  if (value === null || typeof value !== "object") return value;
  for (const key of REFLECT_OWN_KEYS(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
}

export const computeRoleSpecHash = (preimageCandidate) => {
  const preimage = normalizePreimage(preimageCandidate, { requireCanonical: false });
  return sha256CanonicalJson(preimage);
};

/** Create a deterministic immutable RoleSpec without consulting a provider or host. */
export const createRoleSpec = (preimageCandidate) => {
  const preimage = normalizePreimage(preimageCandidate, { requireCanonical: false });
  const roleSpecHash = sha256CanonicalJson(preimage);
  return deepFreeze({
    role_spec_id: `${ROLE_SPEC_ID_PREFIX}${roleSpecHash.slice("sha256:".length)}`,
    ...preimage,
    role_spec_hash: roleSpecHash,
  });
};

/** Verify serialized RoleSpec identity, canonical ordering, and content integrity. */
export const verifyRoleSpecIntegrity = (candidate) =>
  deepFreeze(normalizePersistedRoleSpec(candidate));

const scopeMatches = (scope, resource) => {
  if (!scope.endsWith("/**")) return scope === resource;
  const prefix = scope.slice(0, -3);
  return resource.startsWith(`${prefix}/`);
};

const normalizeAuthorizationRequest = (candidate) => {
  const record = requirePlainDataObject(candidate, "authorization request", ["acl", "resource"]);
  const acl = requireEnum(
    readDataProperty(record, "acl"),
    "authorization request.acl",
    ACL_KINDS,
    "UNKNOWN_ACL_KIND",
  );
  const rawResource = readDataProperty(record, "resource");
  let resource;
  if (acl === "tool") resource = requireToolCapability(rawResource, "authorization request.resource");
  else if (acl === "evidence") {
    resource = requireEvidenceClass(rawResource, "authorization request.resource");
    if (resource === "all_permitted") {
      fail("INVALID_EVIDENCE_REQUEST", "all_permitted is an ACL grant, not an evidence class request");
    }
  } else if (acl === "network") {
    resource = requireNetworkOrigin(rawResource, "authorization request.resource");
  } else {
    resource = requireResourcePath(rawResource, "authorization request.resource");
  }
  return { acl, resource };
};

/**
 * Evaluate one exact access request. Unknown vocabulary is an error; known but
 * undeclared access is an immutable DENY decision.
 */
export const authorizeRoleAccess = (roleSpecCandidate, requestCandidate) => {
  const roleSpec = verifyRoleSpecIntegrity(roleSpecCandidate);
  const request = normalizeAuthorizationRequest(requestCandidate);
  let allowed = false;
  if (request.acl === "tool") allowed = roleSpec.tool_acl.includes(request.resource);
  else if (request.acl === "evidence") {
    allowed =
      roleSpec.evidence_acl.includes("all_permitted") ||
      roleSpec.evidence_acl.includes(request.resource);
  } else if (request.acl === "network") {
    allowed = roleSpec.network_acl.includes(request.resource);
  } else if (request.acl === "read") {
    allowed = roleSpec.read_scope.some((scope) => scopeMatches(scope, request.resource));
  } else if (request.acl === "write") {
    allowed = roleSpec.write_scope.some((scope) => scopeMatches(scope, request.resource));
  }
  return deepFreeze({
    role_spec_id: roleSpec.role_spec_id,
    role_spec_hash: roleSpec.role_spec_hash,
    acl: request.acl,
    resource: request.resource,
    decision: allowed ? "ALLOW" : "DENY",
    reason: allowed ? "EXPLICIT_ROLE_SPEC_GRANT" : "DENY_BY_DEFAULT",
  });
};

/** Project only fields accepted by the current nested RoleDispatchPlan role. */
export const projectRoleSpecToDispatchRole = (roleSpecCandidate) => {
  const roleSpec = verifyRoleSpecIntegrity(roleSpecCandidate);
  const projection = {};
  for (const field of DISPATCH_ROLE_FIELDS) projection[field] = roleSpec[field];
  return deepFreeze(canonicalClone(projection));
};

export const ROLE_SPEC_REQUIRED_FIELDS = ROLE_SPEC_FIELDS;
export const ROLE_DISPATCH_PROJECTION_FIELDS = DISPATCH_ROLE_FIELDS;
