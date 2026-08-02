// workflow_compile_test — deterministic workflow compilation, DAG and
// resource-edge validation, and fail-closed document contracts.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  SchedulerError,
  assertSchedulerPlanIntegrity,
} from "../../scheduler/dag-scheduler.mjs";
import { WorkflowCompileError } from "./workflow-compiler.mjs";
import { compiler, validDocument, validNode } from "./node-contract.test.mjs";

const FIXTURE = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("./memory-recall.workflow.fixture.json", import.meta.url)),
    "utf8",
  ),
);

function assertCode(fn, code, ErrorClass = WorkflowCompileError) {
  try {
    fn();
  } catch (error) {
    assert.ok(error instanceof ErrorClass, String(error));
    assert.equal(error.code, code, error.message);
    return error;
  }
  assert.fail(`expected ${code}`);
}

test("workflow_compile_test: a valid document compiles deterministically", () => {
  const first = compiler().compile(validDocument());
  const second = compiler().compile(validDocument());

  assert.equal(first.workflow_id, "fixture_flow");
  assert.equal(first.node_count, 2);
  assert.deepEqual(first.topological_order, second.topological_order);
  assert.equal(first.compiled_sha256, second.compiled_sha256);
  assert.equal(first.scheduler_plan_sha256, second.scheduler_plan_sha256);
  assertSchedulerPlanIntegrity(first.scheduler_plan);
  assert.ok(Object.isFrozen(first));
});

test("workflow_compile_test: compilation does not mutate the input document", () => {
  const document = validDocument();
  const before = JSON.stringify(document);

  compiler().compile(document);

  assert.equal(JSON.stringify(document), before);
});

test("workflow_compile_test: ordered write-scope sharing yields an ordered resource edge", () => {
  const document = validDocument();
  document.nodes[1].write_scope = ["artifacts/node_a/inner/**"];

  const compiled = compiler().compile(document);

  assert.deepEqual(compiled.resource_edges, [
    { nodes: ["node_a", "node_b"], ordered: true, shared_resources: [] },
  ]);
});

test("workflow_compile_test: unordered write-scope sharing needs a declared resource", () => {
  const document = validDocument();
  document.nodes[1].depends_on = [];
  document.nodes[1].write_scope = ["artifacts/node_a/**"];

  assertCode(() => compiler().compile(document), "WRITE_SCOPE_CONFLICT_UNDECLARED");

  document.nodes[0].resource_dependencies = ["exclusive:node_a_artifacts"];
  document.nodes[1].resource_dependencies = ["exclusive:node_a_artifacts"];
  const compiled = compiler().compile(document);

  assert.deepEqual(compiled.resource_edges, [
    {
      nodes: ["node_a", "node_b"],
      ordered: false,
      shared_resources: ["exclusive:node_a_artifacts"],
    },
  ]);
  assert.equal(
    compiled.scheduler_plan.resource_capacities["exclusive:node_a_artifacts"],
    1,
  );
});

test("workflow_compile_test: DAG violations are blocked by the sealed scheduler", () => {
  const duplicate = validDocument();
  duplicate.nodes[1] = validNode({ write_scope: ["artifacts/dup/**"] });
  assertCode(() => compiler().compile(duplicate), "DUPLICATE_NODE_ID", SchedulerError);

  const unknown = validDocument();
  unknown.nodes[1].depends_on = ["ghost"];
  assertCode(() => compiler().compile(unknown), "UNKNOWN_DEPENDENCY", SchedulerError);

  const self = validDocument();
  self.nodes[1].depends_on = ["node_b"];
  assertCode(() => compiler().compile(self), "SELF_DEPENDENCY", SchedulerError);

  const cycle = validDocument();
  cycle.nodes[0].depends_on = ["node_b"];
  cycle.nodes[1].depends_on = ["node_a"];
  assert.throws(() => compiler().compile(cycle), SchedulerError);
});

test("workflow_compile_test: document contract violations fail closed", () => {
  assertCode(
    () => compiler().compile(validDocument({ kind: "pipeline" })),
    "WORKFLOW_DOCUMENT_INVALID",
  );
  assertCode(
    () => compiler().compile(validDocument({ version: "4.0" })),
    "WORKFLOW_DOCUMENT_INVALID",
  );
  assertCode(
    () => compiler().compile(validDocument({ workflow_id: "Fixture-Flow" })),
    "WORKFLOW_DOCUMENT_INVALID",
  );
  assertCode(
    () => compiler().compile(validDocument({ terminal_states: ["PASS", "BLOCKED"] })),
    "WORKFLOW_DOCUMENT_INVALID",
  );
  assertCode(
    () =>
      compiler().compile(
        validDocument({
          completeness_contract: {
            expected_node_count_source: "compiled_run_spec",
            missing_node_policy: "SKIP",
            partial_result_policy: "typed_and_visible_only",
          },
        }),
      ),
    "WORKFLOW_DOCUMENT_INVALID",
  );
  assertCode(
    () => compiler().compile(validDocument({ input_schema_ref: "schemas/nope.schema.json" })),
    "SCHEMA_REF_UNRESOLVED",
  );
  assertCode(() => compiler().compile(validDocument({ nodes: [] })), "WORKFLOW_DOCUMENT_INVALID");

  const document = validDocument();
  delete document.invariants;
  assertCode(() => compiler().compile(document), "WORKFLOW_DOCUMENT_INVALID");
});

test("workflow_compile_test: capacity overrides are bounded and validated", () => {
  const document = validDocument();
  document.nodes[0].resource_dependencies = ["quota:grobid"];

  const compiled = compiler().compile(document, {
    resourceCapacities: { "quota:grobid": 3 },
  });
  assert.equal(compiled.scheduler_plan.resource_capacities["quota:grobid"], 3);

  assertCode(
    () => compiler().compile(document, { resourceCapacities: { "quota:ghost": 2 } }),
    "WORKFLOW_DOCUMENT_INVALID",
  );
  assertCode(
    () =>
      compiler().compile(document, {
        resourceCapacities: { "quota:grobid": 0 },
      }),
    "RESOURCE_CAPACITY_INVALID",
    SchedulerError,
  );

  const exclusive = validDocument();
  exclusive.nodes[0].resource_dependencies = ["exclusive:projection"];
  assertCode(
    () =>
      compiler().compile(exclusive, {
        resourceCapacities: { "exclusive:projection": 2 },
      }),
    "RESOURCE_CAPACITY_INVALID",
    SchedulerError,
  );
});

test("workflow_compile_test: the canonical memory_recall projection compiles", () => {
  assert.equal(FIXTURE.source, "workflows/memory_recall.workflow.yaml");
  assert.match(FIXTURE.source_sha256, /^sha256:[0-9a-f]{64}$/);

  const compiled = compiler().compile(FIXTURE.document);

  assert.equal(compiled.workflow_id, "memory_recall");
  assert.equal(compiled.node_count, 8);
  assert.equal(compiled.topological_order.length, 8);
  assert.equal(
    compiled.topological_order[0],
    "detect_recall_intent",
    "policy resolution must follow intent detection",
  );
  assertSchedulerPlanIntegrity(compiled.scheduler_plan);
});
