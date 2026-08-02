import { ROLE_SPEC_VERSION, createRoleSpec } from "./role-spec.mjs";

export const makeRoleSpecInput = (overrides = {}) => ({
  role_spec_version: ROLE_SPEC_VERSION,
  role_id: "evidence_scout",
  mission: "Retrieve balanced evidence without deciding the scientific verdict.",
  forbidden_behaviors: [
    "change canonical state directly",
    "invent evidence",
    "self approve",
  ],
  host_agent_type: "explorer",
  model_tier: "balanced",
  fallback_model_tiers: ["economy"],
  read_scope: ["artifacts/evidence/**", "policy/current.json"],
  write_scope: ["artifacts/retrieval/evidence_scout/**"],
  tool_acl: ["artifact_read", "artifact_write", "fulltext_search"],
  network_acl: ["https://search.example"],
  evidence_acl: ["boundary", "counter", "null", "support"],
  input_schema_refs: ["schemas/evidence-pack.schema.json"],
  output_schema_ref: "schemas/result-envelope.schema.json",
  budget_tokens: 24_000,
  timeout_seconds: 1_200,
  expected_count: 1,
  independence_group: "retrieval_maker",
  acceptance_checks: [
    "counterevidence remains visible",
    "source references resolve",
  ],
  failure_policy: "fail_run",
  max_attempts: 2,
  depends_on: [],
  ...overrides,
});

export const makeRoleSpec = (overrides = {}) => createRoleSpec(makeRoleSpecInput(overrides));

export const assertRoleSpecError = (assert, code, operation) => {
  assert.throws(operation, (error) => {
    assert.equal(error?.name, "RoleSpecContractError");
    assert.equal(error?.code, code);
    return true;
  });
};
