import assert from "node:assert/strict";
import test from "node:test";

import { deriveModelRouting } from "./index.mjs";
import {
  assertRoutePolicyError,
  makeRouteTable,
  makeRouteTableInput,
  makeRoutingRequest,
} from "./route-policy-test-support.mjs";

const FRONTIER = "model-frontier-2026-07-31";
const BALANCED = "model-balanced-2026-07-31";
const ECONOMY = "model-economy-2026-07-31";

test("fallback_provenance_test: the declared route order terminates in exactly one safe default", () => {
  const decision = deriveModelRouting(makeRouteTable(), makeRoutingRequest());

  assert.equal(decision.safe_default_model_id, ECONOMY);
  assert.equal(decision.eligible_model_ids.at(-1), ECONOMY);
});

test("fallback_provenance_test: a route order without a terminal safe default is refused", () => {
  const input = makeRouteTableInput();
  input.task_classes.mutation_generation.route_order.at(-1).safe_default = false;
  assertRoutePolicyError(assert, "SAFE_DEFAULT_POSITION_INVALID", () => makeRouteTable(input));
});

test("fallback_provenance_test: a non-terminal safe default is refused", () => {
  const input = makeRouteTableInput();
  input.task_classes.mutation_generation.route_order[0].safe_default = true;
  assertRoutePolicyError(assert, "SAFE_DEFAULT_POSITION_INVALID", () => makeRouteTable(input));
});

test("fallback_provenance_test: skipping the unavailable primary records ordered provenance", () => {
  const decision = deriveModelRouting(
    makeRouteTable(),
    makeRoutingRequest({ unavailable_model_ids: [FRONTIER] }),
  );

  assert.equal(decision.fallback_used, true);
  assert.equal(decision.selected_route_index, 1);
  assert.equal(decision.selected_model_id, BALANCED);
  assert.deepEqual(decision.fallback_chain, [
    { model_id: FRONTIER, model_tier: "frontier", reason: "UNAVAILABLE" },
  ]);
});

test("fallback_provenance_test: a used fallback is policy-approved with a recorded decision id", () => {
  const decision = deriveModelRouting(
    makeRouteTable(),
    makeRoutingRequest({ unavailable_model_ids: [FRONTIER] }),
  );

  assert.equal(typeof decision.fallback_policy_decision_id, "string");
  assert.match(decision.fallback_policy_decision_id, /^RFB-[0-9a-f]{64}$/u);
  assert.equal(decision.receipt.selected_model_id, BALANCED);
  assert.equal(decision.receipt.estimated_cost, 12);
});

test("fallback_provenance_test: exhausting every earlier candidate lands on the safe default", () => {
  const decision = deriveModelRouting(
    makeRouteTable(),
    makeRoutingRequest({ unavailable_model_ids: [FRONTIER, BALANCED] }),
  );

  assert.equal(decision.selected_model_id, ECONOMY);
  assert.equal(decision.selected_route_index, 2);
  assert.equal(decision.fallback_used, true);
  assert.deepEqual(
    decision.fallback_chain.map((step) => step.model_id),
    [FRONTIER, BALANCED],
  );
});

test("fallback_provenance_test: the terminal safe default may never be declared unavailable", () => {
  assertRoutePolicyError(assert, "SAFE_DEFAULT_UNAVAILABLE", () =>
    deriveModelRouting(
      makeRouteTable(),
      makeRoutingRequest({ unavailable_model_ids: [FRONTIER, BALANCED, ECONOMY] }),
    ),
  );
});

test("fallback_provenance_test: fallback derivation is order-independent and re-derivable", () => {
  const routeTable = makeRouteTable();
  const forward = deriveModelRouting(
    routeTable,
    makeRoutingRequest({ unavailable_model_ids: [FRONTIER, BALANCED] }),
  );
  const reversed = deriveModelRouting(
    routeTable,
    makeRoutingRequest({ unavailable_model_ids: [BALANCED, FRONTIER] }),
  );

  assert.deepEqual(forward, reversed);
  assert.deepEqual(forward.requested_unavailable_model_ids, [BALANCED, FRONTIER]);
});

test("fallback_provenance_test: a single-candidate class routes to its own safe default with no fallback", () => {
  const decision = deriveModelRouting(
    makeRouteTable(),
    makeRoutingRequest({ task_class: "evidence_retrieval" }),
  );

  assert.equal(decision.selected_model_id, "model-deterministic-2026-07-31");
  assert.equal(decision.safe_default_model_id, "model-deterministic-2026-07-31");
  assert.equal(decision.selected_route_index, 0);
  assert.equal(decision.fallback_used, false);
  assert.equal(decision.fallback_policy_decision_id, null);
  assert.deepEqual(decision.fallback_chain, []);
});

test("fallback_provenance_test: distinct fallback depths yield distinct policy decision ids", () => {
  const routeTable = makeRouteTable();
  const shallow = deriveModelRouting(
    routeTable,
    makeRoutingRequest({ unavailable_model_ids: [FRONTIER] }),
  );
  const deep = deriveModelRouting(
    routeTable,
    makeRoutingRequest({ unavailable_model_ids: [FRONTIER, BALANCED] }),
  );

  assert.notEqual(shallow.fallback_policy_decision_id, deep.fallback_policy_decision_id);
});
