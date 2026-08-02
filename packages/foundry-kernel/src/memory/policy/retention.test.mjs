import assert from "node:assert/strict";
import test from "node:test";

import {
  MemoryPolicyError,
  evaluateMemoryAccess,
  retentionDaysForClass,
  sealMemoryPolicy,
} from "./memory-policy.mjs";

const policy = () =>
  sealMemoryPolicy({
    policy_id: "MP-L01-retention",
    workspace_id: "WS-L01-retention",
    allowed_classes: ["SESSION", "WORKSPACE", "EPHEMERAL"],
    default_retention_days: 30,
    class_rules: [
      {
        class: "WORKSPACE",
        retention_days: 90,
        requires_consent: false,
        external_sync: "DENY",
        redaction_profile: "workspace-default",
      },
      {
        class: "EPHEMERAL",
        retention_days: 0,
        requires_consent: false,
        external_sync: "DENY",
        redaction_profile: "ephemeral",
      },
    ],
    cross_workspace_retrieval: "DENY",
    effective_at: "2026-01-01T00:00:00Z",
  });

const request = (overrides = {}) => ({
  workspace_id: "WS-L01-retention",
  target_workspace_id: "WS-L01-retention",
  memory_class: "SESSION",
  purpose: "resume the current FORGE run",
  data_class: "session state",
  scope: "SESSION",
  memory_created_at: "2026-07-01T00:00:00Z",
  evaluated_at: "2026-07-31T00:00:00Z",
  cross_workspace_opt_in: false,
  ...overrides,
});

const evaluate = (overrides = {}) =>
  evaluateMemoryAccess({ policy: policy(), request: request(overrides), consent_record: null });

const expectErrorCode = (code) => (error) =>
  error instanceof MemoryPolicyError && error.code === code;

test("retention_test: class-specific retention overrides the policy default", () => {
  const sealed = policy();
  assert.equal(retentionDaysForClass(sealed, "SESSION"), 30);
  assert.equal(retentionDaysForClass(sealed, "WORKSPACE"), 90);
  assert.equal(evaluate({ memory_class: "WORKSPACE", evaluated_at: "2026-09-29T00:00:00Z" }).decision, "ALLOW");
  assert.equal(evaluate({ memory_class: "SESSION", evaluated_at: "2026-09-29T00:00:00Z" }).reason_code, "RETENTION_EXPIRED");
});

test("retention_test: the exact retention boundary is valid and the next millisecond is expired", () => {
  assert.equal(evaluate().decision, "ALLOW");
  const expired = evaluate({ evaluated_at: "2026-07-31T00:00:00.001Z" });
  assert.equal(expired.decision, "DENY");
  assert.equal(expired.reason_code, "RETENTION_EXPIRED");
  assert.equal(expired.retention_days, 30);
});

test("retention_test: future memory timestamps are rejected instead of producing negative age", () => {
  const result = evaluate({ memory_created_at: "2026-08-01T00:00:00Z" });
  assert.equal(result.reason_code, "MEMORY_TIMESTAMP_IN_FUTURE");
});

test("retention_test: zero-day EPHEMERAL memory survives only its creation instant", () => {
  const atCreation = evaluate({
    memory_class: "EPHEMERAL",
    memory_created_at: "2026-07-31T00:00:00Z",
  });
  assert.equal(atCreation.decision, "ALLOW");
  assert.equal(
    evaluate({
      memory_class: "EPHEMERAL",
      memory_created_at: "2026-07-31T00:00:00Z",
      evaluated_at: "2026-07-31T00:00:00.001Z",
    }).reason_code,
    "RETENTION_EXPIRED",
  );
});

test("retention_test: canonical but disallowed classes fail closed before retrieval", () => {
  const result = evaluate({ memory_class: "REGULATED" });
  assert.equal(result.decision, "DENY");
  assert.equal(result.reason_code, "MEMORY_CLASS_NOT_ALLOWED");
  assert.throws(() => retentionDaysForClass(policy(), "REGULATED"), expectErrorCode("MEMORY_CLASS_NOT_ALLOWED"));
});

test("retention_test: unknown classes and malformed timestamps are invalid input, not fallback", () => {
  assert.throws(() => evaluate({ memory_class: "PROFILE" }), expectErrorCode("UNKNOWN_MEMORY_CLASS"));
  assert.throws(
    () => evaluate({ memory_created_at: "not-a-timestamp" }),
    expectErrorCode("MEMORY_ACCESS_REQUEST_INVALID"),
  );
});

test("retention_test: access decisions preserve the policy hash and are deeply immutable", () => {
  const result = evaluate();
  assert.equal(result.policy_hash, policy().policy_hash);
  assert.ok(Object.isFrozen(result));
  assert.throws(() => {
    result.reason_code = "FORGED";
  }, TypeError);
});
