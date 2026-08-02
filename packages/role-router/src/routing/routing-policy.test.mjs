import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  MODEL_ROUTING_RECEIPT_FIELDS,
  REWARD_BASES,
  ROUTING_POLICIES,
  ROUTING_RECEIPT_ID_PREFIX,
  createRouteTable,
  deriveModelRouting,
  verifyModelRoutingReceipt,
  verifyRouteTableIntegrity,
} from "./index.mjs";
import {
  assertRoutePolicyError,
  makeRouteTable,
  makeRouteTableInput,
  makeRoutingRequest,
} from "./route-policy-test-support.mjs";

const routingReceiptSchema = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../../../schemas/model-routing-receipt.schema.json", import.meta.url)),
    "utf8",
  ),
);

test("routing_policy_test: routing vocabulary composes the declared schema vocabulary", () => {
  assert.deepEqual([...ROUTING_POLICIES], routingReceiptSchema.properties.policy.enum);
  assert.deepEqual([...REWARD_BASES], routingReceiptSchema.properties.reward_basis.enum);
});

test("routing_policy_test: derivation runs the declared table deterministically and is content-addressed", () => {
  const routeTable = makeRouteTable();
  const request = makeRoutingRequest();
  const before = structuredClone(request);

  const first = deriveModelRouting(routeTable, request);
  const second = deriveModelRouting(structuredClone(routeTable), structuredClone(request));

  assert.deepEqual(request, before, "derivation must not mutate caller input");
  assert.deepEqual(first, second, "derivation must be deterministic and re-derivable");
  assert.match(first.routing_decision_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(
    first.routing_decision_id,
    `RTD-${first.routing_decision_hash.slice("sha256:".length)}`,
  );
  assert.ok(Object.isFrozen(first));
  assert.ok(Object.isFrozen(first.receipt));
  assert.ok(Object.isFrozen(first.fallback_chain));
});

test("routing_policy_test: primary route is selected when every candidate is available", () => {
  const decision = deriveModelRouting(makeRouteTable(), makeRoutingRequest());

  assert.equal(decision.selected_route_index, 0);
  assert.equal(decision.selected_model_id, "model-frontier-2026-07-31");
  assert.equal(decision.fallback_used, false);
  assert.equal(decision.fallback_policy_decision_id, null);
  assert.deepEqual(decision.fallback_chain, []);
});

test("routing_policy_test: the emitted receipt satisfies the ModelRoutingReceipt schema", () => {
  const decision = deriveModelRouting(makeRouteTable(), makeRoutingRequest());
  const receipt = decision.receipt;

  assert.deepEqual(Object.keys(receipt).sort(), [...routingReceiptSchema.required].sort());
  assert.deepEqual(Object.keys(receipt).sort(), [...MODEL_ROUTING_RECEIPT_FIELDS].sort());
  assert.equal(receipt.task_class, "mutation_generation");
  assert.deepEqual(receipt.eligible_model_ids, [
    "model-frontier-2026-07-31",
    "model-balanced-2026-07-31",
    "model-economy-2026-07-31",
  ]);
  assert.equal(receipt.selected_model_id, "model-frontier-2026-07-31");
  assert.ok(ROUTING_POLICIES.includes(receipt.policy));
  assert.ok(REWARD_BASES.includes(receipt.reward_basis));
  assert.equal(receipt.estimated_cost, 40);
  assert.equal(receipt.estimated_latency_ms, 9_000);
  assert.equal(receipt.exploration_probability, 0.15);
  assert.deepEqual(receipt.safety_constraints, ["no_holdout_access", "sandbox_only"]);
  assert.match(receipt.receipt_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(receipt.receipt_id, `${ROUTING_RECEIPT_ID_PREFIX}${receipt.receipt_hash.slice(7)}`);
});

test("routing_policy_test: the receipt is independently re-derivable from its own content", () => {
  const decision = deriveModelRouting(makeRouteTable(), makeRoutingRequest());
  const reverified = verifyModelRoutingReceipt(structuredClone(decision.receipt));

  assert.deepEqual(reverified, decision.receipt);
});

test("routing_policy_test: a tampered receipt hash is refused", () => {
  const decision = deriveModelRouting(makeRouteTable(), makeRoutingRequest());
  const tampered = { ...decision.receipt, estimated_cost: 1 };
  assertRoutePolicyError(assert, "ROUTING_RECEIPT_HASH_MISMATCH", () =>
    verifyModelRoutingReceipt(tampered),
  );
});

test("routing_policy_test: an undeclared task class is refused, never invented", () => {
  assertRoutePolicyError(assert, "UNDECLARED_TASK_CLASS", () =>
    deriveModelRouting(makeRouteTable(), makeRoutingRequest({ task_class: "unlisted_class" })),
  );
});

test("routing_policy_test: marking an unrouted model unavailable is refused", () => {
  assertRoutePolicyError(assert, "UNKNOWN_ROUTE_CANDIDATE", () =>
    deriveModelRouting(
      makeRouteTable(),
      makeRoutingRequest({ unavailable_model_ids: ["model-not-in-table-2026-07-31"] }),
    ),
  );
});

test("routing_policy_test: no route may acquire evaluator, holdout, or promotion authority", () => {
  for (const authority of ["evaluator", "holdout", "promotion"]) {
    const input = makeRouteTableInput();
    input.task_classes[`${authority}_gate`] = input.task_classes.evidence_retrieval;
    assertRoutePolicyError(assert, "ROUTE_AUTHORITY_FORBIDDEN", () => createRouteTable(input));
  }
});

test("routing_policy_test: a floating model reference is refused", () => {
  const input = makeRouteTableInput();
  input.task_classes.mutation_generation.route_order[0].model_id = "model-latest";
  assertRoutePolicyError(assert, "FLOATING_MODEL_REFERENCE", () => createRouteTable(input));
});

test("routing_policy_test: an unexpected route-table field is refused", () => {
  const table = makeRouteTable();
  const malformed = structuredClone(table);
  malformed.injected_authority = "promotion";
  assertRoutePolicyError(assert, "UNEXPECTED_FIELD", () => verifyRouteTableIntegrity(malformed));
});

test("routing_policy_test: an unsupported route-table version is refused", () => {
  assertRoutePolicyError(assert, "ROUTE_TABLE_VERSION_UNSUPPORTED", () =>
    createRouteTable(makeRouteTableInput({ route_table_version: "0.0.0-bogus" })),
  );
});

test("routing_policy_test: a tampered route-table hash is refused", () => {
  const table = makeRouteTable();
  const malformed = { ...structuredClone(table), route_table_hash: `sha256:${"0".repeat(64)}` };
  assertRoutePolicyError(assert, "ROUTE_TABLE_HASH_MISMATCH", () =>
    verifyRouteTableIntegrity(malformed),
  );
});

test("routing_policy_test: an unknown routing policy is refused", () => {
  const input = makeRouteTableInput();
  input.task_classes.mutation_generation.policy = "coin_flip";
  assertRoutePolicyError(assert, "UNKNOWN_ROUTING_POLICY", () => createRouteTable(input));
});
