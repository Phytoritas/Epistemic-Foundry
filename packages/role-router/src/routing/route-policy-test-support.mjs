import { ROUTE_TABLE_VERSION, createRouteTable } from "./route-policy.mjs";

// A declared, policy-approved route table fixture. The `mutation_generation`
// class exercises a three-step ordered fallback ending in a safe default; the
// `evidence_retrieval` class is a single-candidate class (its only candidate is
// itself the safe default). Costs and latencies increase toward the frontier,
// mirroring a cost/eval-basis-driven policy.
export const makeRouteTableInput = (overrides = {}) => ({
  route_table_version: ROUTE_TABLE_VERSION,
  task_classes: {
    mutation_generation: {
      policy: "safe_bandit",
      reward_basis: "delayed_holdout",
      exploration_probability: 0.15,
      safety_constraints: ["no_holdout_access", "sandbox_only"],
      route_order: [
        {
          model_id: "model-frontier-2026-07-31",
          provider_id: "provider_primary",
          model_tier: "frontier",
          estimated_cost: 40,
          estimated_latency_ms: 9_000,
          safe_default: false,
        },
        {
          model_id: "model-balanced-2026-07-31",
          provider_id: "provider_secondary",
          model_tier: "balanced",
          estimated_cost: 12,
          estimated_latency_ms: 4_000,
          safe_default: false,
        },
        {
          model_id: "model-economy-2026-07-31",
          provider_id: "provider_safe",
          model_tier: "economy",
          estimated_cost: 3,
          estimated_latency_ms: 1_500,
          safe_default: true,
        },
      ],
    },
    evidence_retrieval: {
      policy: "fixed",
      reward_basis: "none",
      exploration_probability: 0,
      safety_constraints: ["read_only"],
      route_order: [
        {
          model_id: "model-deterministic-2026-07-31",
          provider_id: "provider_safe",
          model_tier: "deterministic",
          estimated_cost: 1,
          estimated_latency_ms: 800,
          safe_default: true,
        },
      ],
    },
  },
  ...overrides,
});

export const makeRouteTable = (overrides = {}) => createRouteTable(makeRouteTableInput(overrides));

export const makeRoutingRequest = (overrides = {}) => ({
  task_class: "mutation_generation",
  unavailable_model_ids: [],
  ...overrides,
});

export const assertRoutePolicyError = (assert, code, operation) => {
  assert.throws(operation, (error) => {
    assert.equal(error?.name, "RoutePolicyError");
    assert.equal(error?.code, code);
    return true;
  });
};
