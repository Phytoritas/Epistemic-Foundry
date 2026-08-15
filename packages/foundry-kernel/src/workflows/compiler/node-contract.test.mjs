// node_contract_test — canonical NodeContract vocabulary and fail-closed
// validation, derived from schemas/node-contract.schema.json (EF4-I22).

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { contractBySchemaFile } from "@epistemic-foundry/contracts";

import {
  WorkflowCompileError,
  createWorkflowCompiler,
  deriveNodeVocabulary,
} from "./workflow-compiler.mjs";

const ROOT = fileURLToPath(new URL("../../../../..", import.meta.url));
const SCHEMA_PATH = join(ROOT, "schemas", "node-contract.schema.json");
const nodeContractSchema = JSON.parse(readFileSync(SCHEMA_PATH, "utf8"));
const knownSchemaFiles = new Set(
  readdirSync(join(ROOT, "schemas"))
    .filter((name) => name.endsWith(".schema.json"))
    .map((name) => `schemas/${name}`),
);

export function validNode(overrides = {}) {
  return {
    node_id: "node_a",
    purpose: "bounded fixture node",
    executor_type: "deterministic",
    executor_ref: "epistemic_foundry.kernel.actions:issue_intent",
    input_schema_ref: "schemas/node-invocation.schema.json",
    output_schema_ref: "schemas/result-envelope.schema.json",
    depends_on: [],
    read_scope: ["request"],
    write_scope: ["artifacts/node_a/**"],
    capabilities: ["artifact_write"],
    model_tier: "deterministic",
    timeout_seconds: 300,
    max_attempts: 2,
    failure_policy: "fail_run",
    acceptance_checks: ["output validates"],
    resource_dependencies: [],
    determinism_class: "deterministic",
    idempotency_key_fields: ["node_id"],
    loop_contract_ref: null,
    expected_effects: [],
    required_policy_checks: [],
    ...overrides,
  };
}

export function validDocument(overrides = {}) {
  const nodeA = validNode();
  const nodeB = validNode({
    node_id: "node_b",
    depends_on: ["node_a"],
    write_scope: ["artifacts/node_b/**"],
  });
  return {
    workflow_id: "fixture_flow",
    version: "4.0.0",
    kind: "dag",
    description: "bounded compiler fixture",
    input_schema_ref: "schemas/node-invocation.schema.json",
    output_schema_ref: "schemas/result-envelope.schema.json",
    canonical_runtime: "Foundry Kernel",
    state_authority: "Noetic Ledger",
    invariants: ["fixture invariant"],
    terminal_states: ["PASS", "BLOCKED", "SPEC_GAP", "FAIL"],
    completeness_contract: {
      expected_node_count_source: "compiled_run_spec",
      missing_node_policy: "FAIL",
      partial_result_policy: "typed_and_visible_only",
    },
    nodes: [nodeA, nodeB],
    ...overrides,
  };
}

export function compiler() {
  return createWorkflowCompiler({ nodeContractSchema, knownSchemaFiles });
}

function compileNode(nodeOverrides) {
  const document = validDocument();
  document.nodes = [validNode(nodeOverrides)];
  return compiler().compile(document);
}

function assertCode(fn, code) {
  try {
    fn();
  } catch (error) {
    assert.ok(error instanceof WorkflowCompileError, String(error));
    assert.equal(error.code, code, error.message);
    return error;
  }
  assert.fail(`expected ${code}`);
}

test("node_contract_test: vocabulary derives from the canonical schema", () => {
  const vocabulary = deriveNodeVocabulary(nodeContractSchema);

  assert.equal(vocabulary.fields.length, 22);
  assert.equal(vocabulary.required_fields.length, 21);
  assert.deepEqual(vocabulary.executor_statuses, ["executor_bound", "executor_unbound"]);
  assert.deepEqual(vocabulary.executor_types, [
    "deterministic",
    "llm",
    "parser",
    "retrieval",
    "sandbox",
    "subworkflow",
    "policy",
    "human_gate",
  ]);
  assert.equal(vocabulary.determinism_classes.length, 3);
  assert.equal(vocabulary.failure_policies.length, 4);
  assert.equal(vocabulary.model_tiers.length, 4);
});

test("node_contract_test: the schema file matches the sealed contracts registry", () => {
  const entry = contractBySchemaFile.get("schemas/node-contract.schema.json");
  assert.ok(entry, "registry entry missing");
  const digest = createHash("sha256").update(readFileSync(SCHEMA_PATH)).digest("hex");

  assert.equal(entry.source_sha256, `sha256:${digest}`);
});

test("node_contract_test: unknown executors are blocked with the canonical list", () => {
  const error = assertCode(
    () => compileNode({ executor_type: "shell" }),
    "UNKNOWN_EXECUTOR_BLOCKED",
  );
  assert.deepEqual(error.details.canonical, [
    "deterministic",
    "llm",
    "parser",
    "retrieval",
    "sandbox",
    "subworkflow",
    "policy",
    "human_gate",
  ]);
});

test("node_contract_test: non-canonical vocabulary values fail closed", () => {
  assertCode(() => compileNode({ determinism_class: "random" }), "NODE_CONTRACT_INVALID");
  assertCode(() => compileNode({ failure_policy: "ignore" }), "NODE_CONTRACT_INVALID");
  assertCode(() => compileNode({ model_tier: "gigantic" }), "NODE_CONTRACT_INVALID");
  assertCode(() => compileNode({ executor_status: "maybe" }), "NODE_CONTRACT_INVALID");
});

test("node_contract_test: optional executor status remains identity-bearing and fail-closed", () => {
  const absent = compileNode({});
  const bound = compileNode({ executor_status: "executor_bound" });

  assert.deepEqual(absent.executor_status_by_node, [
    { executor_status: null, node_id: "node_a" },
  ]);
  assert.deepEqual(absent.executor_status_census, {
    executor_bound: 0,
    executor_unbound: 0,
    unverified: 1,
  });
  assert.deepEqual(bound.executor_status_by_node, [
    { executor_status: "executor_bound", node_id: "node_a" },
  ]);
  assert.deepEqual(bound.executor_status_census, {
    executor_bound: 1,
    executor_unbound: 0,
    unverified: 0,
  });
  assert.notEqual(absent.compiled_sha256, bound.compiled_sha256);
  assert.equal(absent.scheduler_plan_sha256, bound.scheduler_plan_sha256);
  assertCode(
    () => compileNode({ executor_status: "executor_unbound" }),
    "EXECUTOR_UNBOUND",
  );
});

test("node_contract_test: the field set is exact", () => {
  const missing = validNode();
  delete missing.acceptance_checks;
  const extra = validNode({ surprise: true });
  const document = validDocument();

  document.nodes = [missing];
  assertCode(() => compiler().compile(document), "NODE_CONTRACT_INVALID");
  document.nodes = [extra];
  assertCode(() => compiler().compile(document), "NODE_CONTRACT_INVALID");
});

test("node_contract_test: schema references must resolve to canonical files", () => {
  assertCode(
    () => compileNode({ input_schema_ref: "schemas/not-a-real.schema.json" }),
    "SCHEMA_REF_UNRESOLVED",
  );
  assertCode(
    () => compileNode({ output_schema_ref: "openapi/epistemic-foundry-v1.openapi.yaml" }),
    "SCHEMA_REF_INVALID",
  );
});

test("node_contract_test: executor references follow the canonical conventions", () => {
  assertCode(
    () => compileNode({ executor_type: "llm", executor_ref: "not-a-prompt", model_tier: "balanced" }),
    "EXECUTOR_REF_INVALID",
  );
  assertCode(
    () => compileNode({ executor_type: "subworkflow", executor_ref: "prompts/x.md" }),
    "EXECUTOR_REF_INVALID",
  );
  assertCode(
    () => compileNode({ executor_ref: "just some words" }),
    "EXECUTOR_REF_INVALID",
  );

  const llm = compileNode({
    executor_type: "llm",
    executor_ref: "prompts/plugin/detect_recall_intent.md",
    model_tier: "balanced",
  });
  const sub = compileNode({
    executor_type: "subworkflow",
    executor_ref: "workflows/memory_recall.workflow.yaml",
  });
  const tool = compileNode({ executor_ref: "tools/run_288_lens_audit.py" });

  assert.equal(llm.node_count, 1);
  assert.equal(sub.node_count, 1);
  assert.equal(tool.node_count, 1);
});

test("node_contract_test: numeric bounds and loop refs fail closed", () => {
  assertCode(() => compileNode({ timeout_seconds: 0 }), "NODE_CONTRACT_INVALID");
  assertCode(() => compileNode({ max_attempts: 11 }), "NODE_CONTRACT_INVALID");
  assertCode(() => compileNode({ max_attempts: 0 }), "NODE_CONTRACT_INVALID");
  assertCode(() => compileNode({ loop_contract_ref: 7 }), "NODE_CONTRACT_INVALID");
  assertCode(
    () => compileNode({ write_scope: ["artifacts/x/**", "artifacts/x/**"] }),
    "WORKFLOW_DOCUMENT_INVALID",
  );
});

test("node_contract_test: a tampered canonical schema is rejected at factory time", () => {
  const open = structuredClone(nodeContractSchema);
  open.additionalProperties = true;
  assertCode(
    () => createWorkflowCompiler({ nodeContractSchema: open, knownSchemaFiles }),
    "NODE_SCHEMA_INVALID",
  );

  const wrongId = structuredClone(nodeContractSchema);
  wrongId.$id = "https://example.invalid/node-contract.schema.json";
  assertCode(
    () => createWorkflowCompiler({ nodeContractSchema: wrongId, knownSchemaFiles }),
    "NODE_SCHEMA_INVALID",
  );

  const noEnum = structuredClone(nodeContractSchema);
  delete noEnum.properties.executor_type.enum;
  assertCode(
    () => createWorkflowCompiler({ nodeContractSchema: noEnum, knownSchemaFiles }),
    "NODE_SCHEMA_INVALID",
  );
});
