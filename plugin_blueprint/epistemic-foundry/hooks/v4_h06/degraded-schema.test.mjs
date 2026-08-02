// schema_and_type_check — H06 reads its vocabulary, it never restates it.
//
// Three sealed sources define everything this gate can say.  Hosts, event types
// and coverage dispositions come from the hook gateway; capability states and
// operating modes come from the H04 capability probe; the observation surface
// being degraded, and the rank that orders its dispositions, come from H05.  The
// degraded-mode policy adds exactly one thing none of them can derive — which
// gateway host a given host capability report describes — and that binding is
// checked against the gateway vocabulary rather than trusted.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  CAPABILITY_STATES,
  HOST_CAPABILITY_MODES,
} from "../../../../packages/plugin-host/src/capability-probe/capability-probe.mjs";
import {
  HOOK_COVERAGE,
  HOOK_EVENT_TYPES,
  HOOK_HOSTS,
} from "../../../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  DECLARING_SOURCES as OBSERVABILITY_DECLARING_SOURCES,
  loadObservability,
} from "../v4_h05/index.mjs";
import {
  assertStepProvenance,
  DECLARING_SOURCES,
  degradedCoverageReport,
  deriveCoverageOrder,
  FINDING_CODES,
  loadDegradedModePolicy,
  openDegradedGate,
  POLICY_PATH,
  REPOSITORY_ROOT,
  UNVERIFIED_REASONS,
} from "./index.mjs";
import {
  enabledClaudeState,
  enabledCodexState,
  hostedBypassCodexState,
  workflowStep,
} from "./degraded-fixtures.mjs";

const policy = loadDegradedModePolicy();
const observability = loadObservability();
const gate = openDegradedGate({ hostStates: [enabledCodexState(), enabledClaudeState()] });
const readRepo = (relative) => readFileSync(join(REPOSITORY_ROOT, relative), "utf8");

test("h06_schema: every enabled capability state is one the sealed probe declares", () => {
  for (const state of policy.enabledStates) assert.ok(CAPABILITY_STATES.includes(state), state);
  assert.ok(policy.enabledStates.size > 0);
  assert.ok(policy.enabledStates.size < CAPABILITY_STATES.length);
});

test("h06_schema: the full and degraded modes partition the sealed probe vocabulary", () => {
  const full = [...policy.fullModes];
  const degraded = [...policy.degradedModes];

  assert.deepEqual([...full, ...degraded].sort(), [...HOST_CAPABILITY_MODES].sort());
  assert.equal(full.some((mode) => degraded.includes(mode)), false);
});

test("h06_schema: every host binding targets a host the sealed gateway declares", () => {
  for (const gatewayHost of policy.bindings.values()) {
    assert.ok(HOOK_HOSTS.includes(gatewayHost), gatewayHost);
  }
  assert.deepEqual([...new Set(policy.bindings.values())].sort(), [...HOOK_HOSTS].sort());
});

test("h06_schema: the coverage order is derived from the H05 rank, not restated", () => {
  const order = deriveCoverageOrder(observability);
  const rank = observability.declaration.coverage_rank;

  assert.deepEqual([order.least, order.intermediate, order.greatest].sort(), [...HOOK_COVERAGE].sort());
  assert.ok(rank[order.least] < rank[order.intermediate]);
  assert.ok(rank[order.intermediate] < rank[order.greatest]);
});

test("h06_schema: the policy declares exactly the fields the loader requires", () => {
  assert.deepEqual(Object.keys(policy.declared).sort(), [
    "degraded_modes",
    "enabled_capability_states",
    "full_modes",
    "hook_capability_name",
    "host_bindings",
    "hosted_tool_capability_name",
    "policy_id",
    "policy_version",
  ]);
  for (const binding of policy.declared.host_bindings) {
    assert.deepEqual(Object.keys(binding).sort(), ["capability_report_host", "gateway_host"]);
  }
});

test("h06_schema: the capability names the policy binds are the ones host reports carry", () => {
  const state = gate.hostStates.get("codex");

  assert.ok(Object.hasOwn(state.report.capabilities, policy.hookCapabilityName));
  assert.ok(Object.hasOwn(state.report.capabilities, policy.hostedToolCapabilityName));
  assert.notEqual(policy.hookCapabilityName, policy.hostedToolCapabilityName);
});

test("h06_schema: every finding code carries a code and a reason", () => {
  assert.equal(Object.keys(FINDING_CODES).length, 31);
  for (const [code, reason] of Object.entries(FINDING_CODES)) {
    assert.equal(code, code.toUpperCase());
    assert.ok(reason.length > 50, code);
  }
});

test("h06_schema: every unverified reason carries a code and a reason", () => {
  assert.deepEqual(Object.keys(UNVERIFIED_REASONS).sort(), [
    "HOOKS_DISABLED",
    "HOSTED_TOOL_BYPASS",
    "UNOBSERVED_TOOL_PATH",
  ]);
  for (const [code, reason] of Object.entries(UNVERIFIED_REASONS)) {
    assert.equal(code, code.toUpperCase());
    assert.ok(reason.length > 50, code);
  }
});

test("h06_schema: the declaring sources are H05's plus this package's policy", () => {
  assert.deepEqual(
    [...DECLARING_SOURCES],
    [...OBSERVABILITY_DECLARING_SOURCES, POLICY_PATH].sort(),
  );
  for (const path of DECLARING_SOURCES) assert.ok(readRepo(path).length > 0, path);
});

test("h06_schema: the degraded report names every gateway host and event type", () => {
  const report = degradedCoverageReport(gate);

  assert.deepEqual(
    report.event_types.map((row) => row.event_type).sort(),
    [...HOOK_EVENT_TYPES].sort(),
  );
  for (const row of report.event_types) {
    assert.ok(HOOK_COVERAGE.includes(row.coverage), row.event_type);
    assert.equal(
      row.hosts_observed.length + row.hosts_unobserved.length,
      HOOK_HOSTS.length,
      row.event_type,
    );
    assert.deepEqual(Object.keys(row).sort(), [
      "coverage",
      "event_type",
      "hosts_observed",
      "hosts_unobserved",
      "hosts_withdrawn",
      "in_evolution_surface",
    ]);
  }
});

test("h06_schema: every gateway host the registrations observe declares a host state", () => {
  for (const host of observability.observedHosts) assert.ok(gate.hostStates.has(host), host);
  for (const host of gate.hostStates.keys()) assert.ok(HOOK_HOSTS.includes(host), host);
});

test("h06_schema: an unverified action names its host, path and reasons", () => {
  const hosted = openDegradedGate({
    hostStates: [hostedBypassCodexState(), enabledClaudeState()],
  });

  for (const action of degradedCoverageReport(hosted).unverified_actions) {
    assert.deepEqual(Object.keys(action).sort(), ["gateway_host", "reasons", "tool_path"]);
    assert.ok(HOOK_HOSTS.includes(action.gateway_host), action.gateway_host);
    assert.ok(action.reasons.length > 0, action.tool_path);
    for (const reason of action.reasons) {
      assert.ok(Object.hasOwn(UNVERIFIED_REASONS, reason), reason);
    }
  }
});

test("h06_schema: a judged workflow step declares exactly the fields the gate publishes", () => {
  const judged = assertStepProvenance(gate, workflowStep());

  assert.deepEqual(Object.keys(judged).sort(), [
    "claimed_coverage",
    "event_type",
    "gateway_host",
    "hook_verified",
    "step_id",
    "tool_path",
    "unverified_reasons",
  ]);
  assert.ok(HOOK_COVERAGE.includes(judged.claimed_coverage));
  assert.ok(HOOK_EVENT_TYPES.includes(judged.event_type));
});

test("h06_schema: the degraded report reports only gateway coverage dispositions", () => {
  const report = degradedCoverageReport(gate);

  for (const [eventType, coverage] of Object.entries(report.coverage_by_event_type)) {
    assert.ok(HOOK_EVENT_TYPES.includes(eventType), eventType);
    assert.ok(HOOK_COVERAGE.includes(coverage), coverage);
  }
  assert.equal(
    Object.keys(report.coverage_by_event_type).length,
    HOOK_EVENT_TYPES.length,
  );
});
