import { makeRoleSpec } from "../contracts/role-spec-test-support.mjs";
import { sha256AdapterJson } from "./adapter-contract.mjs";

const HASH_A = `sha256:${"a".repeat(64)}`;
const HASH_B = `sha256:${"b".repeat(64)}`;
const HASH_C = `sha256:${"c".repeat(64)}`;

export const makeHostCapabilityReport = ({
  host = "codex_cli",
  mode = "FULL",
  subagentState = "SUPPORTED",
  serialState = "SUPPORTED",
  capabilityOverrides = {},
  blockers = [],
  unobservedToolPaths = [],
} = {}) => {
  const capabilities = {
    serial_execution: {
      state: serialState,
      evidence: "Bounded serial execution probe completed.",
      limitations: [],
    },
    subagent_dispatch: {
      state: subagentState,
      evidence: "Bounded subagent dispatch probe completed.",
      limitations: [],
    },
    ...capabilityOverrides,
  };
  const preimage = {
    report_id: `HCR-${host}-001`,
    host,
    host_version: host === "claude_code" ? "1.2.3" : "2026.07.31",
    plugin_version: "4.0.0",
    detected_at: "2026-07-31T01:00:00.000Z",
    capabilities: Object.fromEntries(
      Object.entries(capabilities).sort(([left], [right]) => left.localeCompare(right)),
    ),
    hook_events: [],
    unobserved_tool_paths: [...unobservedToolPaths].sort(),
    mode,
    blockers: [...blockers].sort(),
  };
  return { ...preimage, report_hash: sha256AdapterJson(preimage) };
};

export const makeExecutionBinding = (overrides = {}) => ({
  node_id: "retrieve_evidence",
  node_contract_id: "NODE-retrieve-evidence-001",
  node_contract_hash: HASH_A,
  context_capsule_id: "CTX-retrieve-evidence-001",
  context_capsule_hash: HASH_B,
  ...overrides,
});

export const makeModelResolution = (overrides = {}) => ({
  provider_id: "provider_fixture",
  model_id: "model-balanced-2026-07-31",
  model_version: "2026.07.31-r1",
  runtime_id: "codex_runtime",
  runtime_version: "2026.07.31",
  model_tier: "balanced",
  routing_receipt_id: "MRR-fixture-001",
  routing_receipt_hash: HASH_C,
  fallback_policy_decision_id: null,
  ...overrides,
});

export const makeCompileRequest = ({
  host = "codex_cli",
  roleSpec = makeRoleSpec(),
  hostCapabilityReport = makeHostCapabilityReport({ host }),
  executionBinding = makeExecutionBinding(),
  modelResolution = makeModelResolution({
    runtime_id: host === "claude_code" ? "claude_runtime" : "codex_runtime",
  }),
} = {}) => ({
  roleSpec,
  hostCapabilityReport,
  executionBinding,
  modelResolution,
});

export const assertContractError = (assert, code, operation) => {
  assert.throws(operation, (error) => {
    assert.equal(error?.code, code);
    return true;
  });
};
