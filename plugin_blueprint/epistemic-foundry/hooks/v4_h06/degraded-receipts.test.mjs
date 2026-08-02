// provenance_and_receipt_audit — the gate can prove what it read and what it withdrew.
//
// A degraded-mode decision that cannot name its inputs is an opinion, and one
// that cannot name what it withdrew is a cover-up.  The receipt binds every
// declaring source — H05's plus this package's policy — by the sealed gateway's
// own canonical-JSON digest, binds the H05 observability receipt it degrades by
// hash rather than restating it, publishes the withdrawn pairs and the unverified
// actions beside the coverage it still claims, records the recovery evidence it
// accepted, and re-derives its own hash from exactly the fields it publishes.
//
// It carries no clock and no randomness: the same declared host states over the
// same repository always produce the same receipt, and any changed input — a
// policy version, a host report, a withdrawn pair — always produces a different
// one.  So the receipt is re-derivable evidence of degradation, never an assertion
// of it.

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
  sha256HookJson,
} from "../../../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import { loadObservability, observabilityReceipt } from "../v4_h05/index.mjs";
import {
  DECLARING_SOURCES,
  degradedCoverageReport,
  degradedModeReceipt,
  openDegradedGate,
  recoverHookHost,
  REPOSITORY_ROOT,
  validateDegradedModeReceipt,
} from "./index.mjs";
import {
  disabledCodexState,
  enabledClaudeState,
  enabledCodexState,
  hostedBypassCodexState,
  recoveredCodexState,
  recoveryEvidence,
  stageObservability,
  stagePolicy,
} from "./degraded-fixtures.mjs";

const enabledGate = openDegradedGate({ hostStates: [enabledCodexState(), enabledClaudeState()] });
const disabledGate = openDegradedGate({ hostStates: [disabledCodexState(), enabledClaudeState()] });
const hostedGate = openDegradedGate({ hostStates: [hostedBypassCodexState(), enabledClaudeState()] });
const receipt = degradedModeReceipt(disabledGate);
const textHashOf = (relative) => sha256HookJson(readFileSync(join(REPOSITORY_ROOT, relative), "utf8"));

test("h06_receipt: the receipt re-derives its own hash from the fields it publishes", () => {
  const preimage = { ...receipt };
  delete preimage.receipt_id;
  delete preimage.receipt_hash;

  assert.equal(sha256HookJson(preimage), receipt.receipt_hash);
});

test("h06_receipt: the receipt identifier is derived from the hash", () => {
  assert.equal(receipt.receipt_id, `EFH06-DEGRADED-MODE-${receipt.receipt_hash.slice(7, 23)}`);
  assert.match(receipt.receipt_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("h06_receipt: the same host states over the same repository yield the same receipt", () => {
  const again = degradedModeReceipt(
    openDegradedGate({ hostStates: [disabledCodexState(), enabledClaudeState()] }),
  );

  assert.deepEqual(again, receipt);
});

test("h06_receipt: every declaring source is bound by its actual digest", () => {
  assert.deepEqual(
    receipt.declaring_sources.map((row) => row.path),
    [...DECLARING_SOURCES].sort(),
  );
  for (const row of receipt.declaring_sources) {
    assert.equal(row.text_hash, textHashOf(row.path));
    assert.match(row.text_hash, /^sha256:[0-9a-f]{64}$/u);
  }
});

test("h06_receipt: the H05 observability receipt it degrades is bound by hash, not restated", () => {
  assert.equal(receipt.observability_receipt_hash, observabilityReceipt(loadObservability()).receipt_hash);
  assert.match(receipt.observability_receipt_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("h06_receipt: what was withdrawn is recorded rather than implied", () => {
  assert.deepEqual(receipt.hook_disabled_hosts, ["codex"]);
  assert.deepEqual(receipt.hook_enabled_hosts, ["claude"]);
  assert.deepEqual(receipt.withdrawn_pairs, ["codex:PostToolUse", "codex:PreToolUse"]);
  for (const pair of receipt.withdrawn_pairs) assert.ok(receipt.not_observed.includes(pair), pair);
});

test("h06_receipt: the unverified actions are named with their host, path and reasons", () => {
  assert.ok(receipt.unverified_actions.length > 0);
  for (const action of receipt.unverified_actions) {
    assert.deepEqual(Object.keys(action).sort(), ["gateway_host", "reasons", "tool_path"]);
    assert.ok(HOOK_HOSTS.includes(action.gateway_host), action.gateway_host);
    assert.ok(action.reasons.length > 0, action.tool_path);
  }
});

test("h06_receipt: the host states record the exact report they were derived from", () => {
  const codex = receipt.host_states.find((row) => row.gateway_host === "codex");

  assert.equal(codex.capability_report_host, "codex_cli");
  assert.equal(codex.hooks_enabled, false);
  assert.equal(codex.capability_report_id, disabledGate.hostStates.get("codex").report.report_id);
  assert.equal(codex.capability_report_hash, disabledGate.hostStates.get("codex").report.report_hash);
});

test("h06_receipt: the capability and gateway vocabularies are republished, not restated", () => {
  assert.deepEqual(receipt.capability_vocabulary.capability_states, [...CAPABILITY_STATES]);
  assert.deepEqual(receipt.capability_vocabulary.host_capability_modes, [...HOST_CAPABILITY_MODES]);
  assert.deepEqual(receipt.gateway_vocabulary.coverage, [...HOOK_COVERAGE]);
  assert.deepEqual(receipt.gateway_vocabulary.event_types, [...HOOK_EVENT_TYPES]);
  assert.deepEqual(receipt.gateway_vocabulary.hosts, [...HOOK_HOSTS]);
});

test("h06_receipt: the degraded coverage never ranks above the full coverage it publishes", () => {
  const rank = disabledGate.observability.declaration.coverage_rank;
  for (const [eventType, coverage] of Object.entries(receipt.coverage_by_event_type)) {
    assert.ok(rank[coverage] <= rank[receipt.full_coverage_by_event_type[eventType]], eventType);
  }
});

test("h06_receipt: a changed policy version changes the receipt", (t) => {
  const root = stagePolicy(t, (policy) => {
    policy.policy_version = "4.0.0-h06.2";
  });
  const changed = degradedModeReceipt(
    openDegradedGate({ hostStates: [disabledCodexState(), enabledClaudeState()], root }),
  );

  assert.notEqual(changed.receipt_hash, receipt.receipt_hash);
  assert.equal(changed.policy_version, "4.0.0-h06.2");
});

test("h06_receipt: a changed observability surface changes the receipt", (t) => {
  const root = stageObservability(t, (declaration) => {
    declaration.registration_set_version = "4.0.0-h05.2";
  });
  const changed = degradedModeReceipt(
    openDegradedGate({ hostStates: [disabledCodexState(), enabledClaudeState()], root }),
  );

  assert.notEqual(changed.receipt_hash, receipt.receipt_hash);
  assert.notEqual(changed.observability_receipt_hash, receipt.observability_receipt_hash);
});

test("h06_receipt: a different host report changes the receipt", () => {
  const changed = degradedModeReceipt(
    openDegradedGate({
      hostStates: [disabledCodexState({ reportId: "HCR-H06-CODEX-DISABLED-ALT-0001" }), enabledClaudeState()],
    }),
  );

  assert.notEqual(changed.receipt_hash, receipt.receipt_hash);
});

test("h06_receipt: an enabled host set reproduces the full coverage and withdraws nothing", () => {
  const enabled = degradedModeReceipt(enabledGate);

  assert.deepEqual(enabled.coverage_by_event_type, enabled.full_coverage_by_event_type);
  assert.deepEqual(enabled.withdrawn_pairs, []);
  assert.deepEqual(enabled.recoveries, []);
});

test("h06_receipt: hosted-tool bypass records the unverified action without withdrawing coverage", () => {
  const hosted = degradedModeReceipt(hostedGate);

  assert.deepEqual(hosted.withdrawn_pairs, []);
  assert.deepEqual(hosted.coverage_by_event_type, hosted.full_coverage_by_event_type);
  assert.deepEqual(hosted.unverified_actions, [
    { gateway_host: "codex", reasons: ["HOSTED_TOOL_BYPASS", "UNOBSERVED_TOOL_PATH"], tool_path: "hosted_search" },
  ]);
});

test("h06_receipt: a recovery receipt records the evidence that re-enabled the host", () => {
  const recovered = recoverHookHost(disabledGate, {
    hostState: recoveredCodexState(),
    recovery: recoveryEvidence(),
  });
  const recoveredReceipt = degradedModeReceipt(recovered);

  assert.equal(recoveredReceipt.recoveries.length, 1);
  const record = recoveredReceipt.recoveries[0];
  assert.deepEqual(Object.keys(record).sort(), [
    "evidence_hash",
    "from_report_id",
    "gateway_host",
    "hook_bundle_hash",
    "to_report_id",
  ]);
  assert.equal(record.gateway_host, "codex");
  assert.match(record.evidence_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.deepEqual(recoveredReceipt.withdrawn_pairs, []);
});

test("h06_receipt: a prior receipt re-validates and re-derives its own hash", () => {
  const validated = validateDegradedModeReceipt(receipt);

  assert.deepEqual(validated, receipt);
  const preimage = { ...validated };
  delete preimage.receipt_id;
  delete preimage.receipt_hash;
  assert.equal(sha256HookJson(preimage), validated.receipt_hash);
});

test("h06_receipt: the degraded report and receipt agree on what is observed and withdrawn", () => {
  const report = degradedCoverageReport(disabledGate);

  assert.deepEqual(receipt.coverage_by_event_type, report.coverage_by_event_type);
  assert.deepEqual(receipt.not_observed, report.not_observed);
  assert.deepEqual(receipt.withdrawn_pairs, report.withdrawn_pairs);
  assert.equal(receipt.observed_pair_count, report.observed_pair_count);
});

test("h06_receipt: the gate module holds no clock and no randomness", () => {
  const source = readFileSync(
    join(REPOSITORY_ROOT, "plugin_blueprint/epistemic-foundry/hooks/v4_h06/degraded-mode.mjs"),
    "utf8",
  );

  for (const forbidden of ["Date.now", "new Date", "Math.random", "process.env"]) {
    assert.ok(!source.includes(forbidden), forbidden);
  }
});

test("h06_receipt: the receipt is canonical JSON and deeply frozen", () => {
  assert.ok(Object.isFrozen(receipt));
  assert.ok(Object.isFrozen(receipt.withdrawn_pairs));
  assert.ok(Object.isFrozen(receipt.host_states));
  assert.deepEqual(JSON.parse(JSON.stringify(receipt)), { ...receipt });
  assert.equal(sha256HookJson(JSON.parse(JSON.stringify(receipt))), sha256HookJson(receipt));
});
