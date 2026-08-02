// unit_and_contract_tests — what the gate says when the declaration is honest.
//
// The contract has three halves that must not blur into each other.  Hook
// availability decides which observability claims survive; hosted-tool bypass
// decides which actions can carry provenance; and neither of them may be
// inferred from the other.  A host that turns hooks off withdraws coverage but
// keeps its tool paths declared; a host whose hosted tool bypasses local hooks
// keeps every coverage claim it had and loses only the provenance of that path.
//
// Recovery is a third, separate contract: it changes the gate only when the
// re-registration evidence the sealed hook-trust verifier accepts is present.

import assert from "node:assert/strict";
import test from "node:test";

import { HOOK_HOSTS } from "../../../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import { coverageReport, loadObservability } from "../v4_h05/index.mjs";
import {
  assertDegradedCoverageClaim,
  assertStepProvenance,
  degradedCoverageReport,
  degradedModeReceipt,
  openDegradedGate,
  recoverHookHost,
  unverifiedActions,
} from "./index.mjs";
import {
  disabledClaudeState,
  disabledCodexState,
  enabledClaudeState,
  enabledCodexState,
  hostedBypassCodexState,
  recoveredCodexState,
  recoveryEvidence,
  workflowStep,
} from "./degraded-fixtures.mjs";

const observability = loadObservability();
const fullCoverage = coverageReport(observability);
const enabledGate = openDegradedGate({
  hostStates: [enabledCodexState(), enabledClaudeState()],
});
const disabledGate = openDegradedGate({
  hostStates: [disabledCodexState(), enabledClaudeState()],
});
const hostedGate = openDegradedGate({
  hostStates: [hostedBypassCodexState(), enabledClaudeState()],
});
const claimFrom = (report) => ({
  coverage_by_event_type: { ...report.coverage_by_event_type },
  not_observed: [...report.not_observed],
});

test("h06_contract: a fully enabled host set reproduces the H05 coverage exactly", () => {
  const report = degradedCoverageReport(enabledGate);

  assert.deepEqual(report.coverage_by_event_type, fullCoverage.coverage_by_event_type);
  assert.deepEqual(report.not_observed, [...fullCoverage.not_observed]);
  assert.deepEqual(report.withdrawn_pairs, []);
  assert.deepEqual(report.hook_disabled_hosts, []);
});

test("h06_contract: a hook-disabled host withdraws exactly the pairs it observed", () => {
  const report = degradedCoverageReport(disabledGate);

  assert.deepEqual(report.hook_disabled_hosts, ["codex"]);
  assert.deepEqual(report.hook_enabled_hosts, ["claude"]);
  assert.deepEqual(report.withdrawn_pairs, ["codex:PostToolUse", "codex:PreToolUse"]);
  for (const row of report.event_types) {
    assert.equal(row.hosts_observed.includes("codex"), false, row.event_type);
  }
});

test("h06_contract: every withdrawn pair is named in not_observed, never implied", () => {
  const report = degradedCoverageReport(disabledGate);

  for (const pair of report.withdrawn_pairs) {
    assert.ok(report.not_observed.includes(pair), pair);
    assert.equal(fullCoverage.not_observed.includes(pair), false, pair);
  }
  assert.equal(
    report.not_observed.length,
    fullCoverage.not_observed.length + report.withdrawn_pairs.length,
  );
});

test("h06_contract: the degraded report never ranks above the H05 report", () => {
  const rank = observability.declaration.coverage_rank;
  for (const gate of [enabledGate, disabledGate, hostedGate]) {
    const report = degradedCoverageReport(gate);
    for (const [eventType, coverage] of Object.entries(report.coverage_by_event_type)) {
      assert.ok(rank[coverage] <= rank[fullCoverage.coverage_by_event_type[eventType]], eventType);
    }
  }
});

test("h06_contract: disabling every observing host empties the observed set", () => {
  const gate = openDegradedGate({
    hostStates: [disabledCodexState(), disabledClaudeState()],
  });
  const report = degradedCoverageReport(gate);

  assert.deepEqual(report.hook_enabled_hosts, []);
  assert.equal(report.observed_pair_count, 0);
  for (const row of report.event_types) assert.deepEqual(row.hosts_observed, []);
  assert.equal(report.not_observed.length, HOOK_HOSTS.length * report.event_types.length);
});

test("h06_contract: an honest degraded claim is accepted", () => {
  const report = degradedCoverageReport(disabledGate);

  assert.deepEqual(assertDegradedCoverageClaim(disabledGate, claimFrom(report)), report);
});

test("h06_contract: a hook-disabled host marks every declared tool path unverified", () => {
  const actions = unverifiedActions(disabledGate);
  const state = disabledGate.hostStates.get("codex");

  assert.deepEqual(actions.map((row) => row.tool_path), [...state.toolPaths]);
  for (const action of actions) {
    assert.equal(action.gateway_host, "codex");
    assert.deepEqual(action.reasons, ["HOOKS_DISABLED"]);
  }
});

test("h06_contract: hosted-tool bypass names the bypassed action and only it", () => {
  const actions = unverifiedActions(hostedGate);

  assert.deepEqual(actions, [
    {
      gateway_host: "codex",
      reasons: ["HOSTED_TOOL_BYPASS", "UNOBSERVED_TOOL_PATH"],
      tool_path: "hosted_search",
    },
  ]);
});

test("h06_contract: hosted-tool bypass withdraws no observability claim", () => {
  const report = degradedCoverageReport(hostedGate);

  assert.deepEqual(report.withdrawn_pairs, []);
  assert.deepEqual(report.coverage_by_event_type, fullCoverage.coverage_by_event_type);
  assert.deepEqual(assertDegradedCoverageClaim(hostedGate, claimFrom(report)), report);
});

test("h06_contract: a step on an enabled local path is hook-verified", () => {
  const judged = assertStepProvenance(hostedGate, workflowStep({ tool_path: "local_shell" }));

  assert.equal(judged.hook_verified, true);
  assert.deepEqual(judged.unverified_reasons, []);
});

test("h06_contract: a step that claims nothing is accepted and carries its reasons", () => {
  const judged = assertStepProvenance(
    hostedGate,
    workflowStep({ claimed_coverage: "UNOBSERVED", tool_path: "hosted_search" }),
  );

  assert.equal(judged.hook_verified, false);
  assert.deepEqual(judged.unverified_reasons, ["HOSTED_TOOL_BYPASS", "UNOBSERVED_TOOL_PATH"]);
});

test("h06_contract: a step on a hook-disabled host is never hook-verified", () => {
  const judged = assertStepProvenance(
    disabledGate,
    workflowStep({ claimed_coverage: "UNOBSERVED", tool_path: "repo_write" }),
  );

  assert.equal(judged.hook_verified, false);
  assert.deepEqual(judged.unverified_reasons, ["HOOKS_DISABLED"]);
});

test("h06_contract: a step with no tool path is judged on coverage alone", () => {
  const judged = assertStepProvenance(
    enabledGate,
    workflowStep({ event_type: "Stop", gateway_host: "claude", tool_path: null }),
  );

  assert.equal(judged.hook_verified, true);
  assert.equal(judged.tool_path, null);
});

test("h06_contract: recovery restores the withdrawn pairs and records its evidence", () => {
  const recovered = recoverHookHost(disabledGate, {
    hostState: recoveredCodexState(),
    recovery: recoveryEvidence(),
  });
  const report = degradedCoverageReport(recovered);

  assert.deepEqual(recovered.enabledHosts, ["claude", "codex"]);
  assert.deepEqual(report.withdrawn_pairs, []);
  assert.deepEqual(report.coverage_by_event_type, fullCoverage.coverage_by_event_type);
  assert.equal(recovered.recoveries.length, 1);
  assert.deepEqual(Object.keys(recovered.recoveries[0]).sort(), [
    "evidence_hash",
    "from_report_id",
    "gateway_host",
    "hook_bundle_hash",
    "to_report_id",
  ]);
});

test("h06_contract: the recovery record binds the re-registered bundle to the new report", () => {
  const recovered = recoverHookHost(disabledGate, {
    hostState: recoveredCodexState(),
    recovery: recoveryEvidence(),
  });
  const record = recovered.recoveries[0];
  const state = recovered.hostStates.get("codex");

  assert.equal(record.hook_bundle_hash, state.hookCapability.observed_hash);
  assert.equal(record.to_report_id, state.report.report_id);
  assert.equal(record.from_report_id, disabledGate.hostStates.get("codex").report.report_id);
});

test("h06_contract: a gate opened without a prior receipt claims no recovery", () => {
  assert.deepEqual(enabledGate.recoveries, []);
  assert.equal(enabledGate.priorReceipt, null);
  assert.deepEqual(disabledGate.recoveries, []);
});

test("h06_contract: the gate and its reports are frozen and hold no writable state", () => {
  const report = degradedCoverageReport(disabledGate);

  assert.equal(Object.isFrozen(enabledGate), true);
  assert.equal(Object.isFrozen(enabledGate.hostStates), true);
  assert.equal(Object.isFrozen(report), true);
  assert.equal(Object.isFrozen(report.event_types), true);
  assert.equal(Object.isFrozen(report.event_types[0].hosts_observed), true);
  assert.equal(Object.isFrozen(unverifiedActions(disabledGate)), true);
});

test("h06_contract: judging a step does not change the gate or its report", () => {
  const before = degradedModeReceipt(hostedGate).receipt_hash;
  assertStepProvenance(hostedGate, workflowStep({ tool_path: "local_shell" }));

  assert.equal(degradedModeReceipt(hostedGate).receipt_hash, before);
  assert.deepEqual(degradedCoverageReport(hostedGate).unverified_actions.length, 1);
});

test("h06_contract: the H05 surface it degrades is read, never rewritten", () => {
  const report = coverageReport(observability);

  assert.deepEqual(report.coverage_by_event_type, fullCoverage.coverage_by_event_type);
  assert.deepEqual(report.not_observed, [...fullCoverage.not_observed]);
  assert.deepEqual([...disabledGate.observability.observedHosts], ["claude", "codex"]);
});
