/**
 * U02 explicit health-state suite.
 *
 * The invariant under test is that every component health reading the console
 * renders is one of the declared health enum values, with no implicit "assume
 * healthy": a missing or not-yet-received reading renders as an explicit UNKNOWN
 * rather than a blank or a PASS.  This suite exercises the honest states; the
 * refusals live in the adversarial suite.  There is no HTTP client or DOM here.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  buildHealthView,
  HEALTH_CHECK_STATUSES,
  HEALTH_OVERALL_STATES,
  HEALTH_PROFILES,
  HEALTH_RENDER_STATES,
  LIVENESS_RENDER_STATES,
  rederiveHealthRecordHash,
  unknownHealthView,
  validateHealthReport,
} from "./index.mjs";
import {
  authenticatedSession,
  degradedHealthReport,
  healthReport,
  livenessReceipt,
  readinessProblemReceipt,
  readinessReceipt,
} from "./health-test-fixtures.mjs";

const SHA256 = /^sha256:[0-9a-f]{64}$/u;

test("health_states: the declared vocabularies match the plugin health report schema", () => {
  assert.deepEqual(HEALTH_OVERALL_STATES, ["PASS", "DEGRADED", "FAIL", "SAFE_MODE"]);
  assert.deepEqual(HEALTH_CHECK_STATUSES, ["PASS", "WARN", "FAIL", "NOT_RUN"]);
  assert.deepEqual(HEALTH_PROFILES, ["LITE", "RESEARCH", "TEAM", "REGULATED"]);
  // The console adds exactly one client-local state to the declared overalls.
  assert.deepEqual(HEALTH_RENDER_STATES, ["UNKNOWN", ...HEALTH_OVERALL_STATES]);
  assert.deepEqual(LIVENESS_RENDER_STATES, ["UNKNOWN", "LIVE", "UNAVAILABLE"]);
});

test("health_states: a console with no readings renders explicit UNKNOWN, never blank", () => {
  const view = unknownHealthView(authenticatedSession());
  assert.equal(view.overall, "UNKNOWN");
  assert.equal(view.data_state, "UNKNOWN");
  assert.equal(view.overall_is_declared_by_api, false);
  assert.equal(view.liveness.state, "UNKNOWN");
  assert.equal(view.profile, null);
  // Every section carries an explicit state string; none is empty or blank.
  for (const section of view.sections) {
    assert.equal(typeof section.state, "string");
    assert.equal(section.state.length > 0, true);
    assert.notEqual(section.state, "PASS");
  }
  const overallSection = view.sections.find((section) => section.id === "overall-health-state");
  assert.equal(overallSection.state, "UNKNOWN");
});

test("health_states: a healthy readiness report renders PASS with its profile", () => {
  const view = buildHealthView({
    auth: authenticatedSession(),
    readiness_receipt: readinessReceipt(),
    liveness_receipt: livenessReceipt(),
  });
  assert.equal(view.overall, "PASS");
  assert.equal(view.data_state, "READY");
  assert.equal(view.overall_is_declared_by_api, true);
  assert.equal(view.profile, "RESEARCH");
  assert.equal(view.liveness.state, "LIVE");
  assert.equal(view.degraded_checks.length, 0);
  assert.equal(HEALTH_OVERALL_STATES.includes(view.overall), true);
});

test("health_states: a degraded report renders DEGRADED with its non-passing checks visible", () => {
  const view = buildHealthView({
    auth: authenticatedSession(),
    readiness_receipt: readinessReceipt(degradedHealthReport()),
  });
  assert.equal(view.overall, "DEGRADED");
  assert.equal(view.data_state, "READY");
  assert.equal(view.degraded_checks.length, 1);
  assert.equal(view.degraded_checks[0].status, "WARN");
  const degradedSection = view.sections.find((section) => section.id === "degraded-and-failed-checks");
  assert.equal(degradedSection.state, "POPULATED");
  assert.equal(degradedSection.items.length, 1);
});

test("health_states: liveness is not readiness", () => {
  // A live process with no readiness answer still renders overall UNKNOWN.
  const view = buildHealthView({
    auth: authenticatedSession(),
    liveness_receipt: livenessReceipt(),
  });
  assert.equal(view.liveness.state, "LIVE");
  assert.equal(view.overall, "UNKNOWN");
  assert.equal(view.overall_is_declared_by_api, false);
});

test("health_states: a readiness backend problem renders UNAVAILABLE, not empty and not PASS", () => {
  const view = buildHealthView({
    auth: authenticatedSession(),
    readiness_receipt: readinessProblemReceipt(),
  });
  assert.equal(view.overall, "UNKNOWN");
  assert.equal(view.data_state, "UNAVAILABLE");
  assert.equal(view.readiness.outcome, "PROBLEM");
  assert.notEqual(view.data_state, "READY");
});

test("health_states: a liveness transport failure renders UNAVAILABLE liveness", () => {
  const view = buildHealthView({
    auth: authenticatedSession(),
    liveness_receipt: { body: null, body_hash: null, operation_id: "getLiveness", outcome: "TRANSPORT_FAILURE", status: null },
  });
  assert.equal(view.liveness.state, "UNAVAILABLE");
  assert.equal(LIVENESS_RENDER_STATES.includes(view.liveness.state), true);
});

test("health_states: a matching claimed overall is accepted", () => {
  const view = buildHealthView({
    auth: authenticatedSession(),
    readiness_receipt: readinessReceipt(degradedHealthReport()),
    claimed_overall: "DEGRADED",
  });
  assert.equal(view.overall, "DEGRADED");
});

test("health_states: the health view is deeply frozen, deterministic and hash re-derivable", () => {
  const input = {
    auth: authenticatedSession(),
    readiness_receipt: readinessReceipt(),
    liveness_receipt: livenessReceipt(),
  };
  const first = buildHealthView(input);
  const second = buildHealthView({
    auth: authenticatedSession(),
    readiness_receipt: readinessReceipt(),
    liveness_receipt: livenessReceipt(),
  });
  assert.deepEqual(first, second);
  assert.equal(Object.isFrozen(first), true);
  assert.equal(Object.isFrozen(first.sections), true);
  assert.equal(Object.isFrozen(first.checks), true);
  assert.match(first.record_hash, SHA256);
  assert.equal(first.record_hash, rederiveHealthRecordHash(first));
});

test("health_states: validateHealthReport freezes a well-formed report and preserves it", () => {
  const report = validateHealthReport(healthReport());
  assert.equal(Object.isFrozen(report), true);
  assert.equal(report.overall, "PASS");
  assert.equal(report.checks.length, 2);
  assert.match(report.report_hash, SHA256);
});
