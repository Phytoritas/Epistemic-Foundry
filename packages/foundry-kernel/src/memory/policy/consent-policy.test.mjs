import assert from "node:assert/strict";
import test from "node:test";

import {
  MEMORY_CLASSES,
  MemoryPolicyError,
  evaluateMemoryAccess,
  requireMemoryAccess,
  sealConsentRecord,
  sealMemoryPolicy,
  validateConsentRecord,
  validateMemoryPolicy,
} from "./memory-policy.mjs";

const policyInput = (overrides = {}) => ({
  policy_id: "MP-L01-001",
  workspace_id: "WS-L01-A",
  allowed_classes: ["USER", "WORKSPACE", "SESSION"],
  default_retention_days: 90,
  class_rules: [
    {
      class: "USER",
      retention_days: 365,
      requires_consent: true,
      external_sync: "DENY",
      redaction_profile: "user-default",
    },
    {
      class: "WORKSPACE",
      retention_days: 120,
      requires_consent: true,
      external_sync: "DENY",
      redaction_profile: "workspace-default",
    },
  ],
  cross_workspace_retrieval: "DENY",
  effective_at: "2026-07-01T00:00:00Z",
  ...overrides,
});

const consentInput = (policy, overrides = {}) => ({
  consent_id: "CONS-L01-001",
  subject_id: "USER-L01-001",
  workspace_id: policy.workspace_id,
  purposes: ["recall prior research"],
  data_classes: ["research decisions"],
  scopes: ["WORKSPACE", "USER"],
  decision: "GRANTED",
  granted_at: "2026-07-01T00:00:00Z",
  expires_at: "2027-07-01T00:00:00Z",
  revoked_at: null,
  recorded_by: "USER-L01-001",
  policy_hash: policy.policy_hash,
  ...overrides,
});

const requestInput = (overrides = {}) => ({
  workspace_id: "WS-L01-A",
  target_workspace_id: "WS-L01-A",
  memory_class: "WORKSPACE",
  purpose: "recall prior research",
  data_class: "research decisions",
  scope: "WORKSPACE",
  memory_created_at: "2026-07-15T00:00:00Z",
  evaluated_at: "2026-07-31T00:00:00Z",
  cross_workspace_opt_in: false,
  ...overrides,
});

const evaluate = ({ policy = sealMemoryPolicy(policyInput()), request = requestInput(), consent } = {}) => {
  const effectiveConsent = consent === undefined ? sealConsentRecord(consentInput(policy)) : consent;
  return evaluateMemoryAccess({ policy, request, consent_record: effectiveConsent });
};

const expectErrorCode = (code) => (error) =>
  error instanceof MemoryPolicyError && error.code === code;

test("consent_policy_test: policy and consent projections are canonical, hash-bound, and immutable", () => {
  const policy = sealMemoryPolicy(policyInput());
  const consent = sealConsentRecord(consentInput(policy));
  assert.deepEqual(policy.allowed_classes, ["SESSION", "WORKSPACE", "USER"]);
  assert.deepEqual(policy.class_rules.map((rule) => rule.class), ["WORKSPACE", "USER"]);
  assert.match(policy.policy_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.match(consent.record_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.ok(Object.isFrozen(policy));
  assert.ok(Object.isFrozen(policy.class_rules[0]));
  assert.ok(Object.isFrozen(consent));
  assert.deepEqual(validateMemoryPolicy(structuredClone(policy)), policy);
  assert.deepEqual(validateConsentRecord(structuredClone(consent)), consent);

  const tamperedPolicy = structuredClone(policy);
  tamperedPolicy.default_retention_days += 1;
  assert.throws(() => validateMemoryPolicy(tamperedPolicy), expectErrorCode("MEMORY_POLICY_HASH_MISMATCH"));
  const tamperedConsent = structuredClone(consent);
  tamperedConsent.purposes = ["different purpose"];
  assert.throws(() => validateConsentRecord(tamperedConsent), expectErrorCode("CONSENT_RECORD_HASH_MISMATCH"));
});

test("consent_policy_test: memory classes and class rules are closed and unambiguous", () => {
  assert.deepEqual(MEMORY_CLASSES, [
    "EPHEMERAL",
    "SESSION",
    "WORKSPACE",
    "USER",
    "EVIDENCE",
    "REGULATED",
  ]);
  assert.throws(
    () => sealMemoryPolicy(policyInput({ allowed_classes: ["WORKSPACE", "PROFILE"] })),
    expectErrorCode("UNKNOWN_MEMORY_CLASS"),
  );
  assert.throws(
    () => sealMemoryPolicy(policyInput({ class_rules: [] })),
    expectErrorCode("CLASS_RULE_MISSING"),
  );
  assert.throws(
    () =>
      sealMemoryPolicy(
        policyInput({
          class_rules: [policyInput().class_rules[0], { ...policyInput().class_rules[0] }],
        }),
      ),
    expectErrorCode("DUPLICATE_CLASS_RULE"),
  );
  assert.throws(
    () =>
      sealMemoryPolicy(
        policyInput({
          allowed_classes: ["WORKSPACE"],
          class_rules: [policyInput().class_rules[0]],
        }),
      ),
    expectErrorCode("CLASS_RULE_NOT_ALLOWED"),
  );
});

test("consent_policy_test: cross-workspace access is denied by default below retrieval", () => {
  const result = evaluate({
    request: requestInput({
      target_workspace_id: "WS-L01-B",
      memory_class: "USER",
      cross_workspace_opt_in: true,
    }),
  });
  assert.equal(result.decision, "DENY");
  assert.equal(result.reason_code, "CROSS_WORKSPACE_DENIED");
  assert.equal(result.cross_workspace, true);
});

test("consent_policy_test: USER cross-workspace recall requires policy and explicit opt-in", () => {
  const policy = sealMemoryPolicy(policyInput({ cross_workspace_retrieval: "EXPLICIT_ONLY" }));
  const request = requestInput({
    target_workspace_id: "WS-L01-B",
    memory_class: "USER",
    scope: "USER",
  });
  assert.equal(evaluate({ policy, request }).reason_code, "CROSS_WORKSPACE_OPT_IN_REQUIRED");
  const allowed = evaluate({ policy, request: { ...request, cross_workspace_opt_in: true } });
  assert.equal(allowed.decision, "ALLOW");
  assert.equal(allowed.consent_id, "CONS-L01-001");
  assert.ok(Object.isFrozen(allowed));
});

test("consent_policy_test: non-USER classes cannot become cross-workspace through a permissive mode", () => {
  const policy = sealMemoryPolicy(policyInput({ cross_workspace_retrieval: "ALLOW_BY_POLICY" }));
  const result = evaluate({
    policy,
    request: requestInput({ target_workspace_id: "WS-L01-B", cross_workspace_opt_in: true }),
  });
  assert.equal(result.reason_code, "CROSS_WORKSPACE_CLASS_DENIED");
});

test("consent_policy_test: purpose, class, scope, policy, and workspace remain bound", async (t) => {
  const policy = sealMemoryPolicy(policyInput());
  const cases = [
    ["CONSENT_PURPOSE_MISMATCH", { purposes: ["different purpose"] }],
    ["CONSENT_DATA_CLASS_MISMATCH", { data_classes: ["personal profile"] }],
    ["CONSENT_SCOPE_MISMATCH", { scopes: ["SESSION"] }],
    ["CONSENT_POLICY_MISMATCH", { policy_hash: `sha256:${"a".repeat(64)}` }],
    ["CONSENT_WORKSPACE_MISMATCH", { workspace_id: "WS-L01-C" }],
  ];
  for (const [expected, overrides] of cases) {
    await t.test(expected, () => {
      const consent = sealConsentRecord(consentInput(policy, overrides));
      assert.equal(evaluate({ policy, consent }).reason_code, expected);
    });
  }
});

test("consent_policy_test: requested scope cannot claim a different memory class", () => {
  assert.equal(
    evaluate({ request: requestInput({ scope: "USER" }) }).reason_code,
    "CONSENT_SCOPE_MISMATCH",
  );
});

test("consent_policy_test: optional consent is validated but is not recorded as authority", () => {
  const policy = sealMemoryPolicy(
    policyInput({
      class_rules: [
        {
          class: "WORKSPACE",
          retention_days: 120,
          requires_consent: false,
          external_sync: "DENY",
          redaction_profile: "workspace-default",
        },
      ],
    }),
  );
  const consent = sealConsentRecord(consentInput(policy));
  const result = evaluate({ policy, consent });
  assert.equal(result.decision, "ALLOW");
  assert.equal(result.consent_id, null);
});

test("consent_policy_test: only an effective GRANTED consent can authorize access", async (t) => {
  const policy = sealMemoryPolicy(policyInput());
  const cases = [
    ["DENIED", { decision: "DENIED", granted_at: null }, "CONSENT_DENIED"],
    ["REVOKED", { decision: "REVOKED", revoked_at: "2026-07-20T00:00:00Z" }, "CONSENT_REVOKED"],
    ["EXPIRED", { decision: "EXPIRED", expires_at: "2026-07-20T00:00:00Z" }, "CONSENT_EXPIRED"],
  ];
  for (const [label, overrides, expected] of cases) {
    await t.test(label, () => {
      const consent = sealConsentRecord(consentInput(policy, overrides));
      assert.equal(evaluate({ policy, consent }).reason_code, expected);
    });
  }
  assert.equal(evaluate({ policy, consent: null }).reason_code, "CONSENT_REQUIRED");
});

test("consent_policy_test: expiry and revocation take effect at their exact boundary", () => {
  const policy = sealMemoryPolicy(policyInput());
  const atBoundary = requestInput({ evaluated_at: "2026-07-31T00:00:00Z" });
  const expired = sealConsentRecord(
    consentInput(policy, { expires_at: atBoundary.evaluated_at }),
  );
  assert.equal(evaluate({ policy, request: atBoundary, consent: expired }).reason_code, "CONSENT_EXPIRED");

  const staleGranted = sealConsentRecord(
    consentInput(policy, { decision: "GRANTED", revoked_at: atBoundary.evaluated_at }),
  );
  assert.equal(
    evaluate({ policy, request: atBoundary, consent: staleGranted }).reason_code,
    "CONSENT_REVOKED",
  );
});

test("consent_policy_test: not-yet-effective policy and consent fail closed", () => {
  const futurePolicy = sealMemoryPolicy(policyInput({ effective_at: "2026-08-01T00:00:00Z" }));
  assert.equal(evaluate({ policy: futurePolicy }).reason_code, "POLICY_NOT_YET_EFFECTIVE");
  const policy = sealMemoryPolicy(policyInput());
  const futureConsent = sealConsentRecord(
    consentInput(policy, { granted_at: "2026-08-01T00:00:00Z" }),
  );
  assert.equal(evaluate({ policy, consent: futureConsent }).reason_code, "CONSENT_NOT_YET_VALID");
});

test("consent_policy_test: the enforcement API throws the typed denial and never implies search", () => {
  const policy = sealMemoryPolicy(policyInput());
  assert.throws(
    () =>
      requireMemoryAccess({
        policy,
        request: requestInput({ target_workspace_id: "WS-L01-B", memory_class: "USER" }),
        consent_record: sealConsentRecord(consentInput(policy)),
      }),
    expectErrorCode("CROSS_WORKSPACE_DENIED"),
  );
});
