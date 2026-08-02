// negative_and_adversarial_tests — every way the gate can be pushed to lie, refused.
//
// A degraded-mode gate fails in exactly the directions that matter: it treats an
// absent host declaration as good news, reads a full-coverage claim while hooks
// are off, lets a hosted-tool action inherit hook-verified provenance, or waves a
// host back to hook-enabled without the re-registration evidence H04 requires.
// So each hostile input is one thing wrong at a time — a mutated policy, a forged
// host report, a tampered receipt, or a dishonest claim, step or recovery — and
// each must be refused by its own finding code.
//
// The hook gateway and the capability probe are imported code rather than staged
// files, so their vocabularies are the sealed ones in every case below.  Where a
// case needs a report the probe would never emit, `forgeReport` rebuilds the
// canonical hash too, so the gate's own cross-checks are what refuse it.

import assert from "node:assert/strict";
import test from "node:test";

import { CAPABILITY_STATES } from "../../../../packages/plugin-host/src/capability-probe/capability-probe.mjs";
import {
  assertDegradedCoverageClaim,
  assertStepProvenance,
  DegradedModeError,
  degradedCoverageReport,
  degradedModeReceipt,
  deriveCoverageOrder,
  loadDegradedModePolicy,
  openDegradedGate,
  recoverHookHost,
  validateDegradedModeReceipt,
} from "./index.mjs";
import { loadObservability } from "../v4_h05/index.mjs";
import {
  APPROVED_HOOK_HASH,
  CHANGED_HOOK_HASH,
  OTHER_HOOK_HASH,
  desktopCodexState,
  disabledClaudeState,
  disabledCodexState,
  enabledClaudeState,
  enabledCodexState,
  forgeReceipt,
  forgeReport,
  hostedBypassCodexState,
  hostState,
  recoveredCodexState,
  recoveryEvidence,
  refusal,
  stageObservability,
  stagePolicy,
  stageWithoutPolicy,
  workflowStep,
} from "./degraded-fixtures.mjs";

const enabledGate = openDegradedGate({ hostStates: [enabledCodexState(), enabledClaudeState()] });
const disabledGate = openDegradedGate({ hostStates: [disabledCodexState(), enabledClaudeState()] });
const hostedGate = openDegradedGate({ hostStates: [hostedBypassCodexState(), enabledClaudeState()] });
const fullReport = degradedCoverageReport(enabledGate);
const claimFrom = (report) => ({
  coverage_by_event_type: { ...report.coverage_by_event_type },
  not_observed: [...report.not_observed],
});

/** Run `run`, assert it raised a DegradedModeError, and return that error. */
const refuse = (run) => {
  const error = refusal(run);
  assert.ok(error instanceof DegradedModeError, error.message);
  return error;
};

// --- policy-shaped refusals (the binding between host reports and hosts) --------

test("h06_refuse: an enabled capability state the probe does not declare is refused", (t) => {
  const root = stagePolicy(t, (policy) => {
    policy.enabled_capability_states = ["FLYING"];
  });

  const error = refuse(() => loadDegradedModePolicy({ root }));
  assert.equal(error.code, "CAPABILITY_STATE_UNDECLARED");
  assert.equal(error.context.value, "FLYING");
});

test("h06_refuse: an enabled-state set covering the whole vocabulary is refused as vacuous", (t) => {
  const root = stagePolicy(t, (policy) => {
    policy.enabled_capability_states = [...CAPABILITY_STATES].sort();
  });

  const error = refuse(() => loadDegradedModePolicy({ root }));
  assert.equal(error.code, "ENABLED_STATE_SET_VACUOUS");
});

test("h06_refuse: an operating mode the probe does not declare is refused", (t) => {
  const root = stagePolicy(t, (policy) => {
    policy.full_modes = ["HOVER"];
  });

  const error = refuse(() => loadDegradedModePolicy({ root }));
  assert.equal(error.code, "MODE_UNDECLARED");
  assert.equal(error.context.value, "HOVER");
});

test("h06_refuse: full and degraded modes that do not partition the vocabulary are refused", (t) => {
  const root = stagePolicy(t, (policy) => {
    policy.degraded_modes = policy.degraded_modes.filter((mode) => mode !== "BLOCKED");
  });

  const error = refuse(() => loadDegradedModePolicy({ root }));
  assert.equal(error.code, "MODE_PARTITION_INCOMPLETE");
  assert.ok(error.context.vocabulary.includes("BLOCKED"));
});

test("h06_refuse: a host binding that leaves a gateway host unreached is refused", (t) => {
  const root = stagePolicy(t, (policy) => {
    policy.host_bindings = policy.host_bindings.filter((row) => row.gateway_host !== "claude");
  });

  const error = refuse(() => loadDegradedModePolicy({ root }));
  assert.equal(error.code, "HOST_BINDING_INCOMPLETE");
  assert.deepEqual(error.context.unreached, ["claude"]);
});

test("h06_refuse: a missing policy file is refused rather than treated as permissive", (t) => {
  const root = stageWithoutPolicy(t);

  const error = refuse(() => loadDegradedModePolicy({ root }));
  assert.equal(error.code, "POLICY_UNREADABLE");
});

test("h06_refuse: a coverage rank that is not three distinct ranks is refused", (t) => {
  const root = stageObservability(t, (declaration) => {
    for (const key of Object.keys(declaration.coverage_rank)) declaration.coverage_rank[key] = 0;
  });

  const error = refuse(() =>
    openDegradedGate({ hostStates: [enabledCodexState(), enabledClaudeState()], root }),
  );
  assert.equal(error.code, "COVERAGE_RANK_AMBIGUOUS");
});

// --- host-state refusals (what a declared host report may and may not say) ------

test("h06_refuse: a host report that fails probe revalidation is refused", () => {
  const tampered = { ...enabledCodexState().capability_report, mode: "DEGRADED" };
  const state = { capability_report: tampered, hosted_tool_paths: [], tool_paths: ["local_shell", "repo_write"] };

  const error = refuse(() => openDegradedGate({ hostStates: [state, enabledClaudeState()] }));
  assert.equal(error.code, "REPORT_REJECTED");
});

test("h06_refuse: a host report bound to no gateway host is refused", (t) => {
  const root = stagePolicy(t, (policy) => {
    policy.host_bindings = policy.host_bindings.filter(
      (row) => row.capability_report_host !== "codex_desktop",
    );
  });

  const error = refuse(() =>
    openDegradedGate({ hostStates: [desktopCodexState(), enabledClaudeState()], root }),
  );
  assert.equal(error.code, "HOST_BINDING_UNDECLARED");
  assert.equal(error.context.capability_report_host, "codex_desktop");
});

test("h06_refuse: a host state whose tool paths are unsorted is refused", () => {
  const state = {
    capability_report: enabledCodexState().capability_report,
    hosted_tool_paths: [],
    tool_paths: ["repo_write", "local_shell"],
  };

  const error = refuse(() => openDegradedGate({ hostStates: [state, enabledClaudeState()] }));
  assert.equal(error.code, "DECLARATION_NONCANONICAL");
});

test("h06_refuse: a hosted tool path outside the bounded tool set is refused", () => {
  const state = {
    capability_report: hostedBypassCodexState().capability_report,
    hosted_tool_paths: ["ghost_tool"],
    tool_paths: ["hosted_search", "local_shell"],
  };

  const error = refuse(() => openDegradedGate({ hostStates: [state, enabledClaudeState()] }));
  assert.equal(error.code, "TOOL_PATH_UNDECLARED");
  assert.equal(error.context.value, "ghost_tool");
});

test("h06_refuse: a host with no observation of the hook capability is refused", () => {
  const report = forgeReport(enabledCodexState().capability_report, (draft) => {
    delete draft.capabilities.plugin_hooks;
  });
  const state = hostState({ report, toolPaths: ["local_shell", "repo_write"] });

  const error = refuse(() => openDegradedGate({ hostStates: [state, enabledClaudeState()] }));
  assert.equal(error.code, "HOOK_CAPABILITY_ABSENT");
  assert.equal(error.context.capability, "plugin_hooks");
});

test("h06_refuse: a full operating mode over a non-enabled capability is refused", () => {
  const report = forgeReport(enabledCodexState().capability_report, (draft) => {
    draft.capabilities.local_state.state = "DISABLED";
  });
  const state = hostState({ report, toolPaths: ["local_shell", "repo_write"] });

  const error = refuse(() => openDegradedGate({ hostStates: [state, enabledClaudeState()] }));
  assert.equal(error.code, "DEGRADATION_UNDECLARED");
  assert.equal(error.context.capability, "local_state");
});

test("h06_refuse: a hosted tool declared bypassing yet reported observed is refused", () => {
  const state = hostState({
    hostedToolPaths: ["hosted_search"],
    report: recoveredCodexStateReport(),
    toolPaths: ["hosted_search", "local_shell"],
  });

  const error = refuse(() => openDegradedGate({ hostStates: [state, enabledClaudeState()] }));
  assert.equal(error.code, "HOSTED_TOOL_OBSERVATION_CONTRADICTED");
  assert.equal(error.context.tool_path, "hosted_search");
});

test("h06_refuse: a disabled hosted tool that names no bypassed path is refused", () => {
  const report = forgeReport(enabledCodexState().capability_report, (draft) => {
    draft.capabilities.hosted_tool_hooks.state = "DISABLED";
    draft.mode = "DEGRADED";
  });
  const state = hostState({ report, toolPaths: ["local_shell", "repo_write"] });

  const error = refuse(() => openDegradedGate({ hostStates: [state, enabledClaudeState()] }));
  assert.equal(error.code, "HOSTED_TOOL_ACTIONS_UNNAMED");
});

test("h06_refuse: two host states binding one gateway host are refused", () => {
  const error = refuse(() =>
    openDegradedGate({
      hostStates: [enabledCodexState(), desktopCodexState(), enabledClaudeState()],
    }),
  );
  assert.equal(error.code, "HOST_STATE_DUPLICATED");
  assert.equal(error.context.gateway_host, "codex");
});

test("h06_refuse: an observed gateway host with no declared host state is refused", () => {
  const error = refuse(() => openDegradedGate({ hostStates: [enabledCodexState()] }));
  assert.equal(error.code, "HOST_STATE_MISSING");
  assert.equal(error.context.gateway_host, "claude");
});

test("h06_refuse: host states that are not an array are refused", () => {
  const error = refuse(() => openDegradedGate({ hostStates: "codex" }));
  assert.equal(error.code, "DECLARATION_UNREADABLE");
});

// --- claim and step refusals (never assert more than the enabled set holds) -----

test("h06_refuse: presenting the full-coverage report while hooks are off is refused", () => {
  const error = refuse(() => assertDegradedCoverageClaim(disabledGate, claimFrom(fullReport)));
  assert.equal(error.code, "DEGRADED_OVERCLAIMED");
});

test("h06_refuse: a claim that understates observation the enabled set has is refused", () => {
  const claim = claimFrom(fullReport);
  claim.coverage_by_event_type.PreToolUse = "UNOBSERVED";

  const error = refuse(() => assertDegradedCoverageClaim(enabledGate, claim));
  assert.equal(error.code, "DEGRADED_UNDERSTATED");
  assert.equal(error.context.event_type, "PreToolUse");
});

test("h06_refuse: a claim outside the gateway coverage vocabulary is refused", () => {
  const claim = claimFrom(fullReport);
  claim.coverage_by_event_type.Stop = "TOTAL";

  const error = refuse(() => assertDegradedCoverageClaim(enabledGate, claim));
  assert.equal(error.code, "COVERAGE_UNDECLARED");
  assert.equal(error.context.event_type, "Stop");
});

test("h06_refuse: a coverage claim that is not the declared object is refused", () => {
  const error = refuse(() =>
    assertDegradedCoverageClaim(enabledGate, { coverage_by_event_type: {}, not_observed: [], extra: 1 }),
  );
  assert.equal(error.code, "DECLARATION_UNREADABLE");
});

test("h06_refuse: a step claiming provenance for a hosted-tool bypass is refused", () => {
  const error = refuse(() =>
    assertStepProvenance(hostedGate, workflowStep({ claimed_coverage: "OBSERVED", tool_path: "hosted_search" })),
  );
  assert.equal(error.code, "HOSTED_TOOL_PROVENANCE_CLAIMED");
  assert.ok(error.context.reasons.includes("HOSTED_TOOL_BYPASS"));
});

test("h06_refuse: a step claiming provenance on a hook-disabled host is refused", () => {
  const error = refuse(() =>
    assertStepProvenance(disabledGate, workflowStep({ claimed_coverage: "PARTIAL", tool_path: "repo_write" })),
  );
  assert.equal(error.code, "HOSTED_TOOL_PROVENANCE_CLAIMED");
  assert.deepEqual(error.context.reasons, ["HOOKS_DISABLED"]);
});

test("h06_refuse: a step naming a host the gateway does not declare is refused", () => {
  const error = refuse(() => assertStepProvenance(enabledGate, workflowStep({ gateway_host: "gemini" })));
  assert.equal(error.code, "HOST_UNDECLARED");
  assert.equal(error.context.value, "gemini");
});

test("h06_refuse: a step naming an event type the gateway does not declare is refused", () => {
  const error = refuse(() => assertStepProvenance(enabledGate, workflowStep({ event_type: "PreThought" })));
  assert.equal(error.code, "EVENT_TYPE_UNDECLARED");
  assert.equal(error.context.event_type, "PreThought");
});

test("h06_refuse: a step claiming coverage outside the gateway vocabulary is refused", () => {
  const error = refuse(() => assertStepProvenance(enabledGate, workflowStep({ claimed_coverage: "TOTAL" })));
  assert.equal(error.code, "COVERAGE_UNDECLARED");
  assert.equal(error.context.step_id, "STEP-H06-0001");
});

test("h06_refuse: a step naming a tool path its host does not declare is refused", () => {
  const error = refuse(() => assertStepProvenance(enabledGate, workflowStep({ tool_path: "ghost_tool" })));
  assert.equal(error.code, "TOOL_PATH_UNDECLARED");
  assert.equal(error.context.tool_path, "ghost_tool");
});

test("h06_refuse: a workflow step that is not the declared object is refused", () => {
  const error = refuse(() =>
    assertStepProvenance(enabledGate, {
      claimed_coverage: "OBSERVED",
      event_type: "PreToolUse",
      gateway_host: "codex",
      step_id: "STEP-H06-BAD",
    }),
  );
  assert.equal(error.code, "DECLARATION_UNREADABLE");
});

// --- receipt and recovery refusals (recovery is never assumed from a report) ----

test("h06_refuse: a receipt that does not re-derive its own hash is refused", () => {
  const receipt = degradedModeReceipt(disabledGate);

  const error = refuse(() => validateDegradedModeReceipt({ ...receipt, withdrawn_pairs: [] }));
  assert.equal(error.code, "RECEIPT_REJECTED");
});

test("h06_refuse: a prior receipt issued under a different policy is refused", () => {
  const tampered = forgeReceipt(degradedModeReceipt(disabledGate), (draft) => {
    draft.policy_id = "SOME-OTHER-POLICY";
  });

  const error = refuse(() =>
    openDegradedGate({
      hostStates: [enabledCodexState(), enabledClaudeState()],
      priorReceipt: tampered,
    }),
  );
  assert.equal(error.code, "RECEIPT_REJECTED");
  assert.equal(error.context.prior_policy_id, "SOME-OTHER-POLICY");
});

test("h06_refuse: re-enabling a host without re-registration evidence is refused", () => {
  const error = refuse(() =>
    openDegradedGate({
      hostStates: [recoveredCodexState(), enabledClaudeState()],
      priorReceipt: degradedModeReceipt(disabledGate),
      recoveries: [],
    }),
  );
  assert.equal(error.code, "RECOVERY_EVIDENCE_MISSING");
  assert.equal(error.context.gateway_host, "codex");
});

test("h06_refuse: a recovery for a host the prior receipt never disabled is refused", () => {
  const error = refuse(() =>
    openDegradedGate({
      hostStates: [enabledCodexState(), enabledClaudeState()],
      priorReceipt: degradedModeReceipt(disabledGate),
      recoveries: [recoveryEvidence({ gatewayHost: "claude" })],
    }),
  );
  assert.equal(error.code, "RECOVERY_HOST_NOT_DISABLED");
  assert.equal(error.context.gateway_host, "claude");
});

test("h06_refuse: a recovery whose host still reports hooks disabled is refused", () => {
  const error = refuse(() =>
    recoverHookHost(disabledGate, {
      hostState: disabledCodexState({ reportId: "HCR-H06-CODEX-STILL-DISABLED-0001" }),
      recovery: recoveryEvidence(),
    }),
  );
  assert.equal(error.code, "RECOVERY_COVERAGE_UNRESTORED");
  assert.equal(error.context.gateway_host, "codex");
});

test("h06_refuse: a recovery re-presenting the disabled host report is refused", () => {
  const error = refuse(() =>
    recoverHookHost(disabledGate, {
      hostState: recoveredCodexState({ reportId: "HCR-H06-CODEX-DISABLED-0001" }),
      recovery: recoveryEvidence(),
    }),
  );
  assert.equal(error.code, "RECOVERY_UNCHANGED_REPORT");
  assert.equal(error.context.gateway_host, "codex");
});

test("h06_refuse: re-registration evidence outside the approved trust set is refused", () => {
  const error = refuse(() =>
    recoverHookHost(disabledGate, {
      hostState: recoveredCodexState(),
      recovery: recoveryEvidence({ observedHash: OTHER_HOOK_HASH, trustedHookHashes: [APPROVED_HOOK_HASH] }),
    }),
  );
  assert.equal(error.code, "RECOVERY_RETRUST_REQUIRED");
  assert.equal(error.context.gateway_host, "codex");
});

test("h06_refuse: re-registration evidence binding a different hook bundle is refused", () => {
  const error = refuse(() =>
    recoverHookHost(disabledGate, {
      hostState: recoveredCodexState(),
      recovery: recoveryEvidence({ observedHash: CHANGED_HOOK_HASH, trustedHookHashes: [CHANGED_HOOK_HASH] }),
    }),
  );
  assert.equal(error.code, "RECOVERY_EVIDENCE_MISMATCHED");
  assert.equal(error.context.gateway_host, "codex");
});

// --- the two coverage scopes it derives are never assumed equal -----------------

test("h06_refuse: the coverage order is derived, and a two-rank observability is refused", (t) => {
  const order = deriveCoverageOrder(loadObservability());
  assert.equal(order.rank[order.least] < order.rank[order.greatest], true);

  const root = stageObservability(t, (declaration) => {
    for (const key of Object.keys(declaration.coverage_rank)) {
      declaration.coverage_rank[key] = key === "UNOBSERVED" ? 0 : 1;
    }
  });
  const error = refuse(() => deriveCoverageOrder(loadObservability({ root })));
  assert.equal(error.code, "COVERAGE_RANK_AMBIGUOUS");
});

// A codex report whose hosted search path is (contradictorily) reported observed.
function recoveredCodexStateReport() {
  return recoveredCodexState({
    knownToolPaths: ["hosted_search", "local_shell"],
    observedToolPaths: ["hosted_search", "local_shell"],
    reportId: "HCR-H06-CODEX-CONTRADICT-0001",
  }).capability_report;
}
