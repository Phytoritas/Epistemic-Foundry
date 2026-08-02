import assert from "node:assert/strict";
import test from "node:test";

import { evaluateFanInGate } from "./fan-in-gate.mjs";
import {
  ROLE_IDS,
  buildFanInFixture,
  expectFanInCode,
  rehashDispatchPlan,
  rehashSchedulerSnapshot,
} from "./fan-in-test-support.mjs";

test("missing_node_detection_test: exact N02/N03 fan-in is deterministic, immutable, and receipt-bound", () => {
  const fixture = buildFanInFixture();
  const first = evaluateFanInGate(fixture);
  const permuted = evaluateFanInGate({
    ...fixture,
    spawnDescriptors: [...fixture.spawnDescriptors].reverse(),
    resultSubmissions: [...fixture.resultSubmissions].reverse(),
  });

  assert.deepEqual(permuted, first);
  assert.equal(first.status, "PASS");
  assert.equal(first.expected_count, 3);
  assert.deepEqual(first.expected_role_ids, [...ROLE_IDS].sort());
  assert.deepEqual(first.completed_role_ids, first.expected_role_ids);
  assert.match(first.decision_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(first.decision_id, `FANIN-${first.decision_hash.slice(7)}`);
  assert.equal(Object.isFrozen(first), true);
  assert.equal(Object.isFrozen(first.result_bindings), true);
});

test("missing_node_detection_test: dispatch expected count and role identity count must agree", () => {
  const fixture = buildFanInFixture();
  const plan = structuredClone(fixture.dispatchPlan);
  plan.expected_count = 2;
  fixture.dispatchPlan = rehashDispatchPlan(plan);
  expectFanInCode(assert, "EXPECTED_COUNT_MISMATCH", () => evaluateFanInGate(fixture));
});

test("missing_node_detection_test: partial fan-in policies cannot pass the N04 gate", () => {
  const fixture = buildFanInFixture();
  const plan = structuredClone(fixture.dispatchPlan);
  plan.fan_in_policy = "quorum_with_partial_label";
  plan.missing_result_policy = "partial_only";
  fixture.dispatchPlan = rehashDispatchPlan(plan);
  expectFanInCode(assert, "PARTIAL_FAN_IN_NOT_AUTHORIZED", () => evaluateFanInGate(fixture));
});

test("missing_node_detection_test: a missing or duplicate spawn descriptor is visible", () => {
  const missing = buildFanInFixture();
  missing.spawnDescriptors = missing.spawnDescriptors.slice(0, -1);
  expectFanInCode(assert, "MISSING_SPAWN_DESCRIPTOR", () => evaluateFanInGate(missing));

  const duplicate = buildFanInFixture();
  duplicate.spawnDescriptors = [
    duplicate.spawnDescriptors[0],
    duplicate.spawnDescriptors[0],
    duplicate.spawnDescriptors[2],
  ];
  expectFanInCode(assert, "DUPLICATE_SPAWN_DESCRIPTOR", () => evaluateFanInGate(duplicate));
});

test("missing_node_detection_test: descriptor tampering is rejected by the N02 integrity boundary", () => {
  const fixture = buildFanInFixture();
  fixture.spawnDescriptors = structuredClone(fixture.spawnDescriptors);
  fixture.spawnDescriptors[0].execution_binding.node_id = "maker_beta";
  expectFanInCode(assert, "SPAWN_DESCRIPTOR_INVALID", () => evaluateFanInGate(fixture));
});

test("missing_node_detection_test: scheduler missing and unexpected node identities fail closed", () => {
  const missing = buildFanInFixture();
  const missingSnapshot = structuredClone(missing.schedulerSnapshot);
  delete missingSnapshot.node_attempts.maker_beta;
  missing.schedulerSnapshot = rehashSchedulerSnapshot(missingSnapshot);
  expectFanInCode(assert, "SCHEDULER_NODE_SET_MISMATCH", () => evaluateFanInGate(missing));

  const unexpected = buildFanInFixture();
  const unexpectedSnapshot = structuredClone(unexpected.schedulerSnapshot);
  unexpectedSnapshot.node_attempts.unexpected_worker = structuredClone(
    unexpectedSnapshot.node_attempts.maker_alpha,
  );
  unexpectedSnapshot.node_attempts.unexpected_worker[0].node_id = "unexpected_worker";
  unexpected.schedulerSnapshot = rehashSchedulerSnapshot(unexpectedSnapshot);
  expectFanInCode(assert, "SCHEDULER_NODE_SET_MISMATCH", () => evaluateFanInGate(unexpected));
});

test("missing_node_detection_test: snapshot must be exact N03 command replay for the bound plan and run", () => {
  const wrongRun = buildFanInFixture();
  const wrongRunSnapshot = structuredClone(wrongRun.schedulerSnapshot);
  wrongRunSnapshot.node_attempts.maker_alpha[0].run_id = "RUN-N04-fabricated";
  wrongRun.schedulerSnapshot = rehashSchedulerSnapshot(wrongRunSnapshot);
  expectFanInCode(assert, "ATTEMPT_IDENTITY_MISMATCH", () => evaluateFanInGate(wrongRun));

  const wrongPlan = buildFanInFixture();
  const wrongPlanSnapshot = structuredClone(wrongPlan.schedulerSnapshot);
  wrongPlanSnapshot.plan_hash = `sha256:${"f".repeat(64)}`;
  wrongPlan.schedulerSnapshot = rehashSchedulerSnapshot(wrongPlanSnapshot);
  expectFanInCode(assert, "SCHEDULER_PLAN_BINDING_MISMATCH", () =>
    evaluateFanInGate(wrongPlan),
  );
});

test("missing_node_detection_test: a rehashed fabricated earlier attempt cannot enter fan-in", () => {
  const fixture = buildFanInFixture();
  const snapshot = structuredClone(fixture.schedulerSnapshot);
  const fabricated = structuredClone(snapshot.node_attempts.maker_alpha[0]);
  fabricated.status = "FAILED_RETRYABLE";
  fabricated.failure_code = "PROVIDER_TIMEOUT";
  fabricated.terminal_receipt_id = "RR-N04-fabricated-prior";
  snapshot.node_attempts.maker_alpha = [
    fabricated,
    { ...snapshot.node_attempts.maker_alpha[0], attempt: 2 },
  ];
  fixture.schedulerSnapshot = rehashSchedulerSnapshot(snapshot);
  expectFanInCode(assert, "SCHEDULER_REPLAY_MISMATCH", () => evaluateFanInGate(fixture));
});

test("missing_node_detection_test: truncated scheduler command history cannot support completion", () => {
  const fixture = buildFanInFixture();
  fixture.schedulerCommands = fixture.schedulerCommands.slice(0, -1);
  expectFanInCode(assert, "SCHEDULER_REPLAY_MISMATCH", () => evaluateFanInGate(fixture));
});

test("missing_node_detection_test: non-terminal scheduler attempts cannot be narrated as success", () => {
  const fixture = buildFanInFixture();
  const snapshot = structuredClone(fixture.schedulerSnapshot);
  const attempt = snapshot.node_attempts.maker_alpha.at(-1);
  attempt.status = "RUNNING";
  attempt.finished_at = null;
  attempt.terminal_receipt_id = null;
  fixture.schedulerSnapshot = rehashSchedulerSnapshot(snapshot);
  expectFanInCode(assert, "NODE_NOT_SUCCESSFUL", () => evaluateFanInGate(fixture));
});

test("missing_node_detection_test: terminal receipt mismatch remains visible", () => {
  const fixture = buildFanInFixture();
  fixture.resultSubmissions = structuredClone(fixture.resultSubmissions);
  fixture.resultSubmissions[0].terminal_receipt_id = "RR-N04-fabricated";
  expectFanInCode(assert, "TERMINAL_RECEIPT_MISMATCH", () => evaluateFanInGate(fixture));
});

test("missing_node_detection_test: ResultEnvelope completeness must reconcile one-of-one", () => {
  const fixture = buildFanInFixture();
  fixture.resultSubmissions = structuredClone(fixture.resultSubmissions);
  fixture.resultSubmissions[0].result_envelope.completeness.terminal_count = 0;
  fixture.resultSubmissions[0].result_envelope.completeness.missing_node_ids = ["maker_alpha"];
  expectFanInCode(assert, "RESULT_COMPLETENESS_MISMATCH", () => evaluateFanInGate(fixture));
});

test("missing_node_detection_test: prose-only success without a business artifact is rejected", () => {
  const fixture = buildFanInFixture();
  fixture.resultSubmissions = structuredClone(fixture.resultSubmissions);
  fixture.resultSubmissions[0].result_envelope.output_artifact_ids = [];
  expectFanInCode(assert, "INVALID_INPUT", () => evaluateFanInGate(fixture));
});

test("missing_node_detection_test: missing, duplicate, and unexpected result identities fail closed", () => {
  const missing = buildFanInFixture();
  missing.resultSubmissions = missing.resultSubmissions.slice(0, -1);
  expectFanInCode(assert, "MISSING_RESULT_IDENTITY", () => evaluateFanInGate(missing));

  const duplicate = buildFanInFixture();
  duplicate.resultSubmissions = [
    duplicate.resultSubmissions[0],
    duplicate.resultSubmissions[0],
    duplicate.resultSubmissions[2],
  ];
  expectFanInCode(assert, "DUPLICATE_RESULT_IDENTITY", () => evaluateFanInGate(duplicate));

  const unexpected = buildFanInFixture();
  unexpected.resultSubmissions = structuredClone(unexpected.resultSubmissions);
  unexpected.resultSubmissions[0].role_id = "unexpected_worker";
  expectFanInCode(assert, "UNEXPECTED_RESULT_IDENTITY", () => evaluateFanInGate(unexpected));
});
