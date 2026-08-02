import assert from "node:assert/strict";
import test from "node:test";

import { makeRoleSpec } from "../contracts/role-spec-test-support.mjs";
import {
  ADAPTER_CONTRACT_VERSION,
  EXECUTION_ENVELOPE_SCHEMA_REF,
  SPAWN_DESCRIPTOR_REQUIRED_FIELDS,
  compileClaudeSpawnDescriptor,
  compileCodexSpawnDescriptor,
  compileRoleSpawnDescriptor,
  sha256AdapterJson,
  verifySpawnDescriptorIntegrity,
} from "./index.mjs";
import {
  assertContractError,
  makeCompileRequest,
  makeHostCapabilityReport,
  makeModelResolution,
} from "./adapter-test-support.mjs";

test("adapter_compilation_test: Codex compilation is deterministic, immutable, and content-addressed", () => {
  const request = makeCompileRequest();
  const before = structuredClone(request);
  const first = compileCodexSpawnDescriptor(request);
  const second = compileCodexSpawnDescriptor(structuredClone(request));

  assert.deepEqual(request, before, "compiler must not mutate caller input");
  assert.deepEqual(first, second);
  assert.equal(first.adapter_contract_version, ADAPTER_CONTRACT_VERSION);
  assert.match(first.spawn_descriptor_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(first.spawn_descriptor_id, `SPAWN-${first.spawn_descriptor_hash.slice(7)}`);
  assert.deepEqual(Object.keys(first).sort(), [...SPAWN_DESCRIPTOR_REQUIRED_FIELDS].sort());
  assert.deepEqual(verifySpawnDescriptorIntegrity(structuredClone(first)), first);
  assert.ok(Object.isFrozen(first));
  assert.ok(Object.isFrozen(first.model_binding));
  assert.ok(Object.isFrozen(first.host_descriptor));
});

test("adapter_compilation_test: Codex and Claude preserve identical canonical role authority", () => {
  const roleSpec = makeRoleSpec();
  const codex = compileCodexSpawnDescriptor(makeCompileRequest({ roleSpec }));
  const claude = compileClaudeSpawnDescriptor(
    makeCompileRequest({ host: "claude_code", roleSpec }),
  );

  for (const field of [
    "role_spec_id",
    "role_spec_hash",
    "canonical_role_prompt",
    "canonical_role_prompt_hash",
  ]) {
    assert.equal(codex[field], claude[field]);
  }
  assert.deepEqual(codex.execution_binding, claude.execution_binding);
  assert.deepEqual(codex.result_contract, claude.result_contract);
  assert.equal(codex.host, "codex_cli");
  assert.equal(claude.host, "claude_code");
  assert.equal(codex.host_descriptor.target, "explorer");
  assert.equal(claude.host_descriptor.target, "ef-evidence-scout");
});

test("adapter_compilation_test: descriptor binds exact runtime, routing receipt, output, and count", () => {
  const descriptor = compileCodexSpawnDescriptor(makeCompileRequest());

  assert.deepEqual(descriptor.model_binding, {
    provider_id: "provider_fixture",
    model_id: "model-balanced-2026-07-31",
    model_version: "2026.07.31-r1",
    runtime_id: "codex_runtime",
    runtime_version: "2026.07.31",
    model_tier: "balanced",
    routing_receipt_id: "MRR-fixture-001",
    routing_receipt_hash: `sha256:${"c".repeat(64)}`,
    fallback_used: false,
    fallback_policy_decision_id: null,
  });
  assert.equal(
    descriptor.result_contract.execution_envelope_schema_ref,
    EXECUTION_ENVELOPE_SCHEMA_REF,
  );
  assert.equal(
    descriptor.result_contract.business_output_schema_ref,
    "schemas/result-envelope.schema.json",
  );
  assert.equal(descriptor.result_contract.expected_count, 1);
  assert.equal(descriptor.result_contract.prose_completion_is_authority, false);
});

test("adapter_compilation_test: subagent unavailability uses only explicit serial fallback", () => {
  const report = makeHostCapabilityReport({
    subagentState: "UNSUPPORTED",
    serialState: "SUPPORTED",
  });
  const descriptor = compileCodexSpawnDescriptor(
    makeCompileRequest({ hostCapabilityReport: report }),
  );

  assert.equal(descriptor.host_binding.execution_mode, "serial");
  assert.equal(descriptor.host_descriptor.descriptor_kind, "codex_serial");
  assert.equal(descriptor.host_descriptor.target, "main_session");
});

test("adapter_compilation_test: missing subagent and serial capabilities blocks instead of substituting", () => {
  const report = makeHostCapabilityReport({
    subagentState: "UNSUPPORTED",
    serialState: "UNKNOWN",
  });
  assertContractError(assert, "HOST_EXECUTION_CAPABILITY_MISSING", () =>
    compileCodexSpawnDescriptor(makeCompileRequest({ hostCapabilityReport: report })),
  );
});

test("adapter_compilation_test: blocked and safe-mode hosts cannot compile executable work", () => {
  for (const mode of ["BLOCKED", "SAFE_MODE"]) {
    const report = makeHostCapabilityReport({ mode, blockers: [`HOST_${mode}`] });
    assertContractError(assert, "HOST_EXECUTION_BLOCKED", () =>
      compileCodexSpawnDescriptor(makeCompileRequest({ hostCapabilityReport: report })),
    );
  }
});

test("adapter_compilation_test: a read-only host cannot receive a write-capable RoleSpec", () => {
  const report = makeHostCapabilityReport({ mode: "READ_ONLY" });
  assertContractError(assert, "HOST_READ_ONLY_SCOPE_CONFLICT", () =>
    compileCodexSpawnDescriptor(makeCompileRequest({ hostCapabilityReport: report })),
  );

  const readOnlyRole = makeRoleSpec({
    write_scope: [],
    tool_acl: ["artifact_read", "fulltext_search"],
  });
  const descriptor = compileCodexSpawnDescriptor(
    makeCompileRequest({ roleSpec: readOnlyRole, hostCapabilityReport: report }),
  );
  assert.equal(descriptor.host_binding.host_mode, "READ_ONLY");
});

test("adapter_compilation_test: policy-approved RoleSpec fallback tier is explicit and recorded", () => {
  const resolution = makeModelResolution({
    model_id: "model-economy-2026-07-31",
    model_tier: "economy",
    fallback_policy_decision_id: "POLICY-fallback-001",
  });
  const descriptor = compileCodexSpawnDescriptor(
    makeCompileRequest({ modelResolution: resolution }),
  );
  assert.equal(descriptor.model_binding.fallback_used, true);
  assert.equal(
    descriptor.model_binding.fallback_policy_decision_id,
    "POLICY-fallback-001",
  );
});

test("adapter_compilation_test: unauthorized or unapproved model fallback fails closed", () => {
  assertContractError(assert, "MODEL_TIER_NOT_AUTHORIZED", () =>
    compileCodexSpawnDescriptor(
      makeCompileRequest({
        modelResolution: makeModelResolution({
          model_tier: "frontier",
          fallback_policy_decision_id: "POLICY-fallback-001",
        }),
      }),
    ),
  );
  assertContractError(assert, "MODEL_FALLBACK_APPROVAL_MISSING", () =>
    compileCodexSpawnDescriptor(
      makeCompileRequest({
        modelResolution: makeModelResolution({ model_tier: "economy" }),
      }),
    ),
  );
  assertContractError(assert, "INVALID_MODEL_RESOLUTION", () =>
    compileCodexSpawnDescriptor(
      makeCompileRequest({
        modelResolution: makeModelResolution({
          fallback_policy_decision_id: "POLICY-unneeded-001",
        }),
      }),
    ),
  );
});

test("adapter_compilation_test: floating model and runtime references are rejected", () => {
  for (const [field, value] of [
    ["model_id", "provider/latest"],
    ["model_version", "main"],
    ["runtime_version", "^4.0.0"],
    ["runtime_version", ">=4.0.0"],
    ["model_version", "2026.x"],
  ]) {
    assertContractError(assert, "FLOATING_MODEL_REFERENCE", () =>
      compileCodexSpawnDescriptor(
        makeCompileRequest({ modelResolution: makeModelResolution({ [field]: value }) }),
      ),
    );
  }
});

test("adapter_compilation_test: capability report hash and host identity are verified", () => {
  const tampered = makeHostCapabilityReport();
  tampered.mode = "DEGRADED";
  assertContractError(assert, "HOST_CAPABILITY_REPORT_HASH_MISMATCH", () =>
    compileCodexSpawnDescriptor(makeCompileRequest({ hostCapabilityReport: tampered })),
  );

  const claudeReport = makeHostCapabilityReport({ host: "claude_code" });
  assertContractError(assert, "HOST_CAPABILITY_MISMATCH", () =>
    compileCodexSpawnDescriptor(
      makeCompileRequest({ host: "claude_code", hostCapabilityReport: claudeReport }),
    ),
  );
});

test("adapter_compilation_test: rehashed non-canonical capability reports fail closed", () => {
  const cases = [
    (report) => {
      report.detected_at = "not-a-date";
    },
    (report) => {
      report.hook_events = ["PostToolUse", "PreToolUse"];
    },
    (report) => {
      report.hook_events = ["ProviderInventedHook"];
    },
    (report) => {
      report.unobserved_tool_paths = ["z_path", "a_path"];
    },
    (report) => {
      report.blockers = ["Z_BLOCKER", "A_BLOCKER"];
    },
    (report) => {
      report.capabilities.serial_execution.limitations = ["Z_LIMIT", "A_LIMIT"];
    },
  ];

  for (const mutate of cases) {
    const report = makeHostCapabilityReport();
    mutate(report);
    const preimage = Object.fromEntries(
      Object.entries(report).filter(([key]) => key !== "report_hash"),
    );
    report.report_hash = sha256AdapterJson(preimage);
    assertContractError(assert, "HOST_CAPABILITY_REPORT_INVALID", () =>
      compileCodexSpawnDescriptor(makeCompileRequest({ hostCapabilityReport: report })),
    );
  }
});

test("adapter_compilation_test: a tampered RoleSpec never reaches host compilation", () => {
  const tampered = structuredClone(makeRoleSpec());
  tampered.tool_acl = [...tampered.tool_acl, "database_write"].sort();
  assertContractError(assert, "ROLE_SPEC_HASH_MISMATCH", () =>
    compileCodexSpawnDescriptor(makeCompileRequest({ roleSpec: tampered })),
  );
});

test("adapter_compilation_test: serialized descriptor mutation is detected", () => {
  const descriptor = structuredClone(
    compileCodexSpawnDescriptor(makeCompileRequest()),
  );
  descriptor.model_binding.model_id = "different-model-2026-07-31";
  assertContractError(assert, "SPAWN_DESCRIPTOR_HASH_MISMATCH", () =>
    verifySpawnDescriptorIntegrity(descriptor),
  );
});

test("adapter_compilation_test: attacker rehash cannot authorize an altered internal binding", () => {
  const descriptor = structuredClone(
    compileCodexSpawnDescriptor(makeCompileRequest()),
  );
  descriptor.host_descriptor.target = "worker";
  const preimage = Object.fromEntries(
    Object.entries(descriptor).filter(
      ([key]) => key !== "spawn_descriptor_id" && key !== "spawn_descriptor_hash",
    ),
  );
  descriptor.spawn_descriptor_hash = sha256AdapterJson(preimage);
  descriptor.spawn_descriptor_id = `SPAWN-${descriptor.spawn_descriptor_hash.slice(7)}`;

  assertContractError(assert, "HOST_DESCRIPTOR_SEMANTIC_MISMATCH", () =>
    verifySpawnDescriptorIntegrity(descriptor),
  );
});

test("adapter_compilation_test: Codex Desktop is explicit and still preserves RoleSpec authority", () => {
  const report = makeHostCapabilityReport({ host: "codex_desktop" });
  const descriptor = compileCodexSpawnDescriptor(
    makeCompileRequest({ host: "codex_desktop", hostCapabilityReport: report }),
    "codex_desktop",
  );
  assert.equal(descriptor.host, "codex_desktop");
  assert.equal(descriptor.role_spec_id, descriptor.host_descriptor.prompt.match(/ROLE-[0-9a-f]{64}/u)?.[0]);
});

test("adapter_compilation_test: unknown host and unknown Codex built-in role both fail closed", () => {
  assertContractError(assert, "UNSUPPORTED_ADAPTER_HOST", () =>
    compileRoleSpawnDescriptor("other", makeCompileRequest()),
  );
  const roleSpec = makeRoleSpec({ host_agent_type: "provider_super_agent" });
  assertContractError(assert, "UNKNOWN_CODEX_AGENT_TYPE", () =>
    compileCodexSpawnDescriptor(makeCompileRequest({ roleSpec })),
  );
});
