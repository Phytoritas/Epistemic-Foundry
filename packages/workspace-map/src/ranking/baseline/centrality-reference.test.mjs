import assert from "node:assert/strict";
import test from "node:test";

import {
  buildWorkspaceInventory,
  extractWorkspaceEdges,
} from "../../inventory/index.mjs";
import {
  BASELINE_CENTRALITY_ALGORITHM,
  BASELINE_CENTRALITY_VERSION,
  BaselineCentralityError,
  computeBaselineCentrality,
  computeBaselineCentralityHash,
  validateBaselineCentrality,
} from "./index.mjs";

const HASH = `sha256:${"a".repeat(64)}`;
const PARAMETERS = Object.freeze({ alpha: 0.85, max_iterations: 500, tolerance: 1e-13 });
const errorCode = (code) => (error) =>
  error instanceof BaselineCentralityError && error.code === code;

const packageEntity = (nodeId) => ({
  entity_id: nodeId,
  kind: "PACKAGE",
  label: nodeId,
  path: `packages/${nodeId.toLowerCase()}/package.json`,
  locator: null,
  content_hash: HASH,
  owner: nodeId,
  source_class: "SOURCE",
  aliases: [],
});

const reference = (source, target, overrides = {}) => ({
  source_entity_id: source,
  kind: "PACKAGE_DEPENDS_ON",
  target_identity: { namespace: "ENTITY_ID", value: target },
  target_hint: null,
  source_locator: `manifest:${source}->${target}`,
  owner: source,
  ...overrides,
});

const graph = (nodeIds, pairs, unresolved = []) => {
  const inventory = buildWorkspaceInventory({
    workspace_id: "WS-M02-reference",
    root_hash: HASH,
    entities: nodeIds.map(packageEntity),
    unreadable_paths: [],
  });
  const extraction = extractWorkspaceEdges({
    inventory,
    references: [
      ...pairs.map(([source, target], index) =>
        reference(source, target, {
          source_locator: `manifest:${source}->${target}`,
        }),
      ),
      ...unresolved,
    ],
  });
  return { inventory, extraction };
};

const compute = (nodeIds, pairs, unresolved = []) => {
  const inputs = graph(nodeIds, pairs, unresolved);
  return {
    ...inputs,
    ranking: computeBaselineCentrality({ ...inputs, parameters: PARAMETERS }),
  };
};

test("centrality_reference_test: weighted PageRank constants are explicit", () => {
  assert.equal(BASELINE_CENTRALITY_ALGORITHM, "WEIGHTED_PAGERANK");
  assert.equal(BASELINE_CENTRALITY_VERSION, "4.0.0-m02.1");
});

test("centrality_reference_test: two-node analytical reference is reproduced", () => {
  const { ranking } = compute(["NODE-A", "NODE-B"], [["NODE-A", "NODE-B"]]);
  const scores = Object.fromEntries(
    ranking.results.map((row) => [row.node_id, row.baseline_centrality]),
  );
  assert.ok(Math.abs(scores["NODE-A"] - 0.350877192982456) < 1e-12);
  assert.ok(Math.abs(scores["NODE-B"] - 0.649122807017544) < 1e-12);
  assert.deepEqual(ranking.ranking_order, ["NODE-B", "NODE-A"]);
  assert.ok(Math.abs(ranking.convergence.score_sum - 1) < 1e-12);
});

test("centrality_reference_test: directed chain has a real non-uniform order", () => {
  const { ranking } = compute(
    ["NODE-A", "NODE-B", "NODE-C"],
    [["NODE-A", "NODE-B"], ["NODE-B", "NODE-C"]],
  );
  assert.deepEqual(ranking.ranking_order, ["NODE-C", "NODE-B", "NODE-A"]);
  assert.equal(ranking.uniformity.all_equal, false);
  assert.equal(ranking.uniformity.structurally_asymmetric, true);
});

test("centrality_reference_test: algorithm inputs and parameters are recorded", () => {
  const missing = reference("NODE-A", "NODE-MISSING", {
    source_locator: "manifest:missing",
  });
  const { ranking, extraction } = compute(
    ["NODE-A", "NODE-B"],
    [["NODE-A", "NODE-B"]],
    [missing],
  );
  assert.deepEqual(ranking.algorithm, {
    alpha: 0.85,
    convergence_norm: "L1",
    dangling_policy: "UNIFORM_REDISTRIBUTION",
    direction: "SOURCE_TO_TARGET",
    edge_weight_policy: "UNIT_PER_RESOLVED_TYPED_EDGE",
    implementation_version: "4.0.0-m02.1",
    max_iterations: 500,
    name: "WEIGHTED_PAGERANK",
    ranking_tie_breaker: "UTF8_NODE_ID",
    result_order: "UTF8_NODE_ID",
    tolerance: 1e-13,
  });
  assert.equal(ranking.algorithm_inputs.node_count, 2);
  assert.equal(ranking.algorithm_inputs.resolved_edge_count, 1);
  assert.deepEqual(
    ranking.algorithm_inputs.excluded_unresolved_edge_ids,
    extraction.unresolved_edges.map((edge) => edge.edge_id),
  );
});

test("centrality_reference_test: unresolved edges are recorded but never influence scores", () => {
  const unresolved = reference("NODE-A", "NODE-MISSING", {
    source_locator: "manifest:unresolved-score-control",
  });
  const withUnresolved = compute(
    ["NODE-A", "NODE-B", "NODE-C"],
    [["NODE-A", "NODE-B"], ["NODE-B", "NODE-C"]],
    [unresolved],
  );
  const resolvedOnly = compute(
    ["NODE-A", "NODE-B", "NODE-C"],
    [["NODE-A", "NODE-B"], ["NODE-B", "NODE-C"]],
  );
  assert.deepEqual(
    withUnresolved.ranking.results,
    resolvedOnly.ranking.results,
  );
  assert.equal(withUnresolved.ranking.algorithm_inputs.unresolved_edge_count, 1);
  assert.deepEqual(
    withUnresolved.ranking.algorithm_inputs.excluded_unresolved_edge_ids,
    withUnresolved.extraction.unresolved_edges.map((edge) => edge.edge_id),
  );
  assert.notEqual(withUnresolved.ranking.ranking_hash, resolvedOnly.ranking.ranking_hash);
});

test("centrality_reference_test: weak components and isolates are retained", () => {
  const { ranking } = compute(
    ["NODE-A", "NODE-B", "NODE-C", "NODE-D"],
    [["NODE-A", "NODE-B"]],
  );
  const rows = Object.fromEntries(ranking.results.map((row) => [row.node_id, row]));
  assert.equal(rows["NODE-A"].weak_component_id, rows["NODE-B"].weak_component_id);
  assert.equal(rows["NODE-A"].weak_component_size, 2);
  assert.equal(rows["NODE-C"].is_isolate, true);
  assert.equal(rows["NODE-C"].weak_component_size, 1);
  assert.notEqual(rows["NODE-C"].weak_component_id, rows["NODE-D"].weak_component_id);
});

test("centrality_reference_test: result order is node-id canonical and ranking order is separate", () => {
  const { ranking } = compute(
    ["NODE-C", "NODE-A", "NODE-B"],
    [["NODE-A", "NODE-B"], ["NODE-B", "NODE-C"]],
  );
  assert.deepEqual(ranking.results.map((row) => row.node_id), ["NODE-A", "NODE-B", "NODE-C"]);
  assert.deepEqual(ranking.ranking_order, ["NODE-C", "NODE-B", "NODE-A"]);
});

test("centrality_reference_test: input permutation leaves hash and ID unchanged", () => {
  const first = graph(
    ["NODE-A", "NODE-B", "NODE-C"],
    [["NODE-A", "NODE-B"], ["NODE-B", "NODE-C"]],
  );
  const second = graph(
    ["NODE-C", "NODE-A", "NODE-B"],
    [["NODE-B", "NODE-C"], ["NODE-A", "NODE-B"]],
  );
  const one = computeBaselineCentrality({ ...first, parameters: PARAMETERS });
  const two = computeBaselineCentrality({ ...second, parameters: PARAMETERS });
  assert.equal(one.ranking_hash, two.ranking_hash);
  assert.equal(one.ranking_id, two.ranking_id);
  assert.deepEqual(one, two);
});

test("centrality_reference_test: validation rebuild and hash helpers agree", () => {
  const { inventory, extraction, ranking } = compute(
    ["NODE-A", "NODE-B"],
    [["NODE-A", "NODE-B"]],
  );
  assert.deepEqual(validateBaselineCentrality(ranking, inventory, extraction), ranking);
  assert.equal(
    computeBaselineCentralityHash(ranking, inventory, extraction),
    ranking.ranking_hash,
  );
  assert.ok(Object.isFrozen(ranking));
  assert.ok(Object.isFrozen(ranking.results));
});

test("centrality_reference_test: score tampering fails closed", () => {
  const { inventory, extraction, ranking } = compute(
    ["NODE-A", "NODE-B"],
    [["NODE-A", "NODE-B"]],
  );
  const tampered = structuredClone(ranking);
  tampered.results[0].baseline_centrality += 0.01;
  assert.throws(
    () => validateBaselineCentrality(tampered, inventory, extraction),
    errorCode("BASELINE_CENTRALITY_REBUILD_MISMATCH"),
  );
});

test("centrality_reference_test: ranking hash tampering fails closed", () => {
  const { inventory, extraction, ranking } = compute(
    ["NODE-A", "NODE-B"],
    [["NODE-A", "NODE-B"]],
  );
  const tampered = structuredClone(ranking);
  tampered.ranking_hash = `sha256:${"b".repeat(64)}`;
  assert.throws(
    () => validateBaselineCentrality(tampered, inventory, extraction),
    errorCode("BASELINE_CENTRALITY_HASH_MISMATCH"),
  );
});

test("centrality_reference_test: unsupported input fields and accessors fail closed", () => {
  const inputs = graph(["NODE-A"], []);
  assert.throws(
    () => computeBaselineCentrality({ ...inputs, parameters: PARAMETERS, score: "vibes" }),
    errorCode("INVALID_BASELINE_CENTRALITY_INPUT"),
  );
  const accessor = { ...inputs, parameters: PARAMETERS };
  Object.defineProperty(accessor, "parameters", { enumerable: true, get: () => PARAMETERS });
  assert.throws(
    () => computeBaselineCentrality(accessor),
    errorCode("INVALID_BASELINE_CENTRALITY_INPUT"),
  );
});

test("centrality_reference_test: validation rejects nested algorithm accessors without invoking them", () => {
  const { inventory, extraction, ranking } = compute(
    ["NODE-A", "NODE-B"],
    [["NODE-A", "NODE-B"]],
  );
  const hostile = structuredClone(ranking);
  let invoked = false;
  Object.defineProperty(hostile.algorithm, "alpha", {
    enumerable: true,
    get() {
      invoked = true;
      throw new Error("must not execute");
    },
  });
  assert.throws(
    () => validateBaselineCentrality(hostile, inventory, extraction),
    errorCode("INVALID_BASELINE_CENTRALITY_ALGORITHM"),
  );
  assert.equal(invoked, false);
});
