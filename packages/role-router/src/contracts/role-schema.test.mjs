import assert from "node:assert/strict";
import test from "node:test";

import {
  ROLE_DISPATCH_PROJECTION_FIELDS,
  ROLE_SPEC_REQUIRED_FIELDS,
  ROLE_SPEC_VERSION,
  canonicalizeRoleSpecJson,
  computeRoleSpecHash,
  createRoleSpec,
  projectRoleSpecToDispatchRole,
  verifyRoleSpecIntegrity,
} from "./index.mjs";
import {
  assertRoleSpecError,
  makeRoleSpec,
  makeRoleSpecInput,
} from "./role-spec-test-support.mjs";

test("role_schema_test: creates a deterministic content-addressed immutable RoleSpec", () => {
  const input = makeRoleSpecInput();
  const before = structuredClone(input);
  const first = createRoleSpec(input);
  const second = createRoleSpec(structuredClone(input));

  assert.deepEqual(input, before, "caller input must not be mutated");
  assert.deepEqual(first, second);
  assert.equal(first.role_spec_version, ROLE_SPEC_VERSION);
  assert.match(first.role_spec_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(first.role_spec_id, `ROLE-${first.role_spec_hash.slice(7)}`);
  assert.equal(first.role_spec_hash, computeRoleSpecHash(input));
  assert.deepEqual(Object.keys(first).sort(), [...ROLE_SPEC_REQUIRED_FIELDS].sort());
  assert.ok(Object.isFrozen(first));
  for (const value of Object.values(first)) {
    if (Array.isArray(value)) assert.ok(Object.isFrozen(value));
  }
});

test("role_schema_test: set-semantic fields canonicalize while fallback precedence is preserved", () => {
  const left = makeRoleSpecInput({
    forbidden_behaviors: ["self approve", "invent evidence", "change canonical state directly"],
    tool_acl: ["fulltext_search", "artifact_write", "artifact_read"],
    evidence_acl: ["support", "null", "counter", "boundary"],
    input_schema_refs: [
      "schemas/result-envelope.schema.json",
      "schemas/evidence-pack.schema.json",
    ],
    fallback_model_tiers: ["economy", "deterministic"],
    depends_on: ["method_auditor", "claim_extractor"],
  });
  const right = makeRoleSpecInput({
    forbidden_behaviors: ["change canonical state directly", "invent evidence", "self approve"],
    tool_acl: ["artifact_read", "artifact_write", "fulltext_search"],
    evidence_acl: ["boundary", "counter", "null", "support"],
    input_schema_refs: [
      "schemas/evidence-pack.schema.json",
      "schemas/result-envelope.schema.json",
    ],
    fallback_model_tiers: ["economy", "deterministic"],
    depends_on: ["claim_extractor", "method_auditor"],
  });
  assert.deepEqual(createRoleSpec(left), createRoleSpec(right));

  const reversedFallback = makeRoleSpecInput({
    ...right,
    fallback_model_tiers: ["deterministic", "economy"],
  });
  assert.notEqual(
    createRoleSpec(right).role_spec_hash,
    createRoleSpec(reversedFallback).role_spec_hash,
    "fallback order is semantic priority, not a set",
  );
});

test("role_schema_test: persisted integrity requires canonical ordering, hash, and derived ID", () => {
  const roleSpec = makeRoleSpec();
  assert.deepEqual(verifyRoleSpecIntegrity(structuredClone(roleSpec)), roleSpec);

  const contentTamper = structuredClone(roleSpec);
  contentTamper.mission = "A different mission must not inherit the prior identity.";
  assertRoleSpecError(assert, "ROLE_SPEC_HASH_MISMATCH", () =>
    verifyRoleSpecIntegrity(contentTamper),
  );

  const idTamper = structuredClone(roleSpec);
  idTamper.role_spec_id = `ROLE-${"f".repeat(64)}`;
  assertRoleSpecError(assert, "ROLE_SPEC_ID_MISMATCH", () => verifyRoleSpecIntegrity(idTamper));

  const orderTamper = structuredClone(roleSpec);
  orderTamper.evidence_acl.reverse();
  assertRoleSpecError(assert, "NON_CANONICAL_ORDER", () =>
    verifyRoleSpecIntegrity(orderTamper),
  );
});

test("role_schema_test: mission, forbidden behavior, schemas, budget, and expected count are mandatory", () => {
  for (const [field, value, code] of [
    ["mission", "   ", "INVALID_INPUT"],
    ["forbidden_behaviors", [], "EMPTY_REQUIRED_ARRAY"],
    ["input_schema_refs", [], "EMPTY_REQUIRED_ARRAY"],
    ["budget_tokens", -1, "INVALID_INTEGER"],
    ["timeout_seconds", 0, "INVALID_INTEGER"],
    ["expected_count", 0, "INVALID_INTEGER"],
    ["max_attempts", 0, "INVALID_INTEGER"],
  ]) {
    const candidate = makeRoleSpecInput({ [field]: value });
    assertRoleSpecError(assert, code, () => createRoleSpec(candidate));
  }

  const missing = makeRoleSpecInput();
  delete missing.expected_count;
  assertRoleSpecError(assert, "MISSING_FIELD", () => createRoleSpec(missing));

  assertRoleSpecError(assert, "INVALID_SCHEMA_REF", () =>
    createRoleSpec(makeRoleSpecInput({ output_schema_ref: "openapi/result.yaml" })),
  );
});

test("role_schema_test: closed vocabularies and relationship constraints fail closed", () => {
  assertRoleSpecError(assert, "ROLE_SPEC_VERSION_UNSUPPORTED", () =>
    createRoleSpec(makeRoleSpecInput({ role_spec_version: "latest" })),
  );
  assertRoleSpecError(assert, "UNKNOWN_MODEL_TIER", () =>
    createRoleSpec(makeRoleSpecInput({ model_tier: "provider_default" })),
  );
  assertRoleSpecError(assert, "INVALID_MODEL_FALLBACK", () =>
    createRoleSpec(makeRoleSpecInput({ fallback_model_tiers: ["balanced"] })),
  );
  assertRoleSpecError(assert, "UNKNOWN_FAILURE_POLICY", () =>
    createRoleSpec(makeRoleSpecInput({ failure_policy: "ignore" })),
  );
  assertRoleSpecError(assert, "SELF_DEPENDENCY", () =>
    createRoleSpec(makeRoleSpecInput({ depends_on: ["evidence_scout"] })),
  );
  assertRoleSpecError(assert, "UNEXPECTED_FIELD", () =>
    createRoleSpec({ ...makeRoleSpecInput(), provider: "specific-provider" }),
  );
});

test("role_schema_test: scopes reject traversal, absolute paths, separators, and malformed broadening", () => {
  for (const scope of [
    "../secrets",
    "artifacts/../secrets",
    "/etc/passwd",
    "C:/secrets",
    "artifacts\\secret",
    "**",
    "artifacts/*/secret",
    "artifacts/**/secret",
    "artifacts//secret",
  ]) {
    assertRoleSpecError(assert, "INVALID_SCOPE", () =>
      createRoleSpec(makeRoleSpecInput({ read_scope: [scope] })),
    );
  }
  const allowed = createRoleSpec(
    makeRoleSpecInput({ read_scope: ["artifacts/**"], write_scope: [] }),
  );
  assert.deepEqual(allowed.read_scope, ["artifacts/**"]);
});

test("role_schema_test: duplicates are rejected rather than silently deduplicated", () => {
  for (const [field, value] of [
    ["forbidden_behaviors", ["invent evidence", "invent evidence"]],
    ["tool_acl", ["artifact_read", "artifact_read"]],
    ["evidence_acl", ["support", "support"]],
    ["read_scope", ["artifacts/evidence/**", "artifacts/evidence/**"]],
    ["network_acl", ["https://search.example", "https://search.example"]],
  ]) {
    assertRoleSpecError(assert, "DUPLICATE_VALUE", () =>
      createRoleSpec(makeRoleSpecInput({ [field]: value })),
    );
  }
});

test("role_schema_test: hostile wrappers, accessors, sparse arrays, and custom prototypes are inert", () => {
  let trapCount = 0;
  const proxy = new Proxy(makeRoleSpecInput(), {
    get() {
      trapCount += 1;
      throw new Error("must not execute");
    },
  });
  assertRoleSpecError(assert, "INVALID_INPUT", () => createRoleSpec(proxy));
  assert.equal(trapCount, 0);

  let getterCount = 0;
  const accessor = makeRoleSpecInput();
  Object.defineProperty(accessor, "mission", {
    enumerable: true,
    get() {
      getterCount += 1;
      throw new Error("must not execute");
    },
  });
  assertRoleSpecError(assert, "ACCESSOR_FIELD_DENIED", () => createRoleSpec(accessor));
  assert.equal(getterCount, 0);

  const sparse = new Array(2);
  sparse[1] = "invent evidence";
  assertRoleSpecError(assert, "INVALID_INPUT", () =>
    createRoleSpec(makeRoleSpecInput({ forbidden_behaviors: sparse })),
  );

  const customArray = ["invent evidence"];
  Object.setPrototypeOf(customArray, { attacker: true });
  assertRoleSpecError(assert, "INVALID_INPUT", () =>
    createRoleSpec(makeRoleSpecInput({ forbidden_behaviors: customArray })),
  );

  const customObject = Object.create({ attacker: true });
  Object.assign(customObject, makeRoleSpecInput());
  assertRoleSpecError(assert, "INVALID_INPUT", () => createRoleSpec(customObject));
});

test("role_schema_test: RoleDispatchPlan projection is exact, immutable, and provider-neutral", () => {
  const roleSpec = makeRoleSpec();
  const projection = projectRoleSpecToDispatchRole(roleSpec);
  assert.deepEqual(Object.keys(projection).sort(), [...ROLE_DISPATCH_PROJECTION_FIELDS].sort());
  assert.equal(projection.role_id, roleSpec.role_id);
  assert.equal(projection.host_agent_type, roleSpec.host_agent_type);
  assert.equal(projection.model_tier, roleSpec.model_tier);
  assert.deepEqual(projection.tool_acl, roleSpec.tool_acl);
  assert.deepEqual(projection.evidence_acl, roleSpec.evidence_acl);
  assert.equal(projection.budget_tokens, roleSpec.budget_tokens);
  assert.equal(projection.timeout_seconds, roleSpec.timeout_seconds);
  assert.ok(Object.isFrozen(projection));
  assert.ok(Object.isFrozen(projection.tool_acl));
  assert.equal("provider" in projection, false);
  assert.equal("role_spec_hash" in projection, false);
});

test("role_schema_test: canonical JSON rejects cycles and non-canonical numeric values", () => {
  const cycle = {};
  cycle.self = cycle;
  assertRoleSpecError(assert, "NON_CANONICAL_JSON", () => canonicalizeRoleSpecJson(cycle));
  assertRoleSpecError(assert, "NON_CANONICAL_JSON", () => canonicalizeRoleSpecJson(-0));
  assertRoleSpecError(assert, "NON_CANONICAL_JSON", () => canonicalizeRoleSpecJson(1.5));
});
