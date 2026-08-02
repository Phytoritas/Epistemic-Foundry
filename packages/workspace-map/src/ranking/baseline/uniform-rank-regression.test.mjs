import assert from "node:assert/strict";
import test from "node:test";

import {
  buildWorkspaceInventory,
  extractWorkspaceEdges,
} from "../../inventory/index.mjs";
import {
  BaselineCentralityError,
  computeBaselineCentrality,
} from "./index.mjs";

const HASH = `sha256:${"c".repeat(64)}`;
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

const edgeReference = (source, target, index, kind = "PACKAGE_DEPENDS_ON") => ({
  source_entity_id: source,
  kind,
  target_identity: { namespace: "ENTITY_ID", value: target },
  target_hint: null,
  source_locator: `manifest:edge-${index}`,
  owner: source,
});

const build = (nodeIds, edges, parameters = PARAMETERS) => {
  const inventory = buildWorkspaceInventory({
    workspace_id: "WS-M02-uniform",
    root_hash: HASH,
    entities: nodeIds.map(packageEntity),
    unreadable_paths: [],
  });
  const extraction = extractWorkspaceEdges({
    inventory,
    references: edges.map(([source, target, kind], index) =>
      edgeReference(source, target, index, kind),
    ),
  });
  return computeBaselineCentrality({ inventory, extraction, parameters });
};

test("uniform_rank_regression: asymmetric star is never uniformly ranked", () => {
  const ranking = build(
    ["NODE-A", "NODE-B", "NODE-C", "NODE-HUB"],
    [["NODE-A", "NODE-HUB"], ["NODE-B", "NODE-HUB"], ["NODE-C", "NODE-HUB"]],
  );
  const scores = new Set(ranking.results.map((row) => row.baseline_centrality));
  assert.ok(scores.size > 1);
  assert.equal(ranking.uniformity.all_equal, false);
  assert.equal(ranking.ranking_order[0], "NODE-HUB");
});

test("uniform_rank_regression: asymmetric path receives distinct scores", () => {
  const ranking = build(
    ["NODE-A", "NODE-B", "NODE-C", "NODE-D"],
    [["NODE-A", "NODE-B"], ["NODE-B", "NODE-C"], ["NODE-C", "NODE-D"]],
  );
  assert.deepEqual(ranking.ranking_order, ["NODE-D", "NODE-C", "NODE-B", "NODE-A"]);
  assert.ok(ranking.uniformity.score_span > ranking.uniformity.guard_threshold);
});

test("uniform_rank_regression: directed regular cycle may have a legitimate tie", () => {
  const ranking = build(
    ["NODE-A", "NODE-B", "NODE-C"],
    [["NODE-A", "NODE-B"], ["NODE-B", "NODE-C"], ["NODE-C", "NODE-A"]],
  );
  assert.equal(ranking.uniformity.all_equal, true);
  assert.equal(ranking.uniformity.structurally_asymmetric, false);
  assert.deepEqual(ranking.ranking_order, ["NODE-A", "NODE-B", "NODE-C"]);
});

test("uniform_rank_regression: all-isolate graph retains normalized uniform scores", () => {
  const ranking = build(["NODE-A", "NODE-B", "NODE-C"], []);
  assert.equal(ranking.results.every((row) => row.is_isolate), true);
  assert.equal(ranking.uniformity.all_equal, true);
  assert.ok(Math.abs(ranking.convergence.score_sum - 1) < 1e-12);
});

test("uniform_rank_regression: empty graph is explicit and converged", () => {
  const ranking = build([], []);
  assert.deepEqual(ranking.results, []);
  assert.deepEqual(ranking.ranking_order, []);
  assert.deepEqual(ranking.convergence, {
    converged: true,
    final_l1_delta: 0,
    iterations: 0,
    score_sum: 0,
  });
});

test("uniform_rank_regression: single node has score one", () => {
  const ranking = build(["NODE-A"], []);
  assert.equal(ranking.results[0].baseline_centrality, 1);
  assert.deepEqual(ranking.ranking_order, ["NODE-A"]);
});

test("uniform_rank_regression: invalid alpha is rejected", () => {
  assert.throws(
    () => build(["NODE-A"], [], { ...PARAMETERS, alpha: 1 }),
    errorCode("INVALID_CENTRALITY_ALPHA"),
  );
  assert.throws(
    () => build(["NODE-A"], [], { ...PARAMETERS, alpha: 0 }),
    errorCode("INVALID_CENTRALITY_ALPHA"),
  );
});

test("uniform_rank_regression: invalid tolerance is rejected", () => {
  assert.throws(
    () => build(["NODE-A"], [], { ...PARAMETERS, tolerance: 0 }),
    errorCode("INVALID_CENTRALITY_TOLERANCE"),
  );
});

test("uniform_rank_regression: bounded non-convergence fails closed", () => {
  assert.throws(
    () =>
      build(
        ["NODE-A", "NODE-B"],
        [["NODE-A", "NODE-B"]],
        { alpha: 0.85, max_iterations: 1, tolerance: 1e-15 },
      ),
    errorCode("CENTRALITY_NON_CONVERGENCE"),
  );
});

test("uniform_rank_regression: parallel typed edges are recorded as unit weights", () => {
  const ranking = build(
    ["NODE-A", "NODE-B", "NODE-C"],
    [
      ["NODE-A", "NODE-B", "PACKAGE_DEPENDS_ON"],
      ["NODE-A", "NODE-B", "IMPORTS"],
      ["NODE-A", "NODE-C", "PACKAGE_DEPENDS_ON"],
    ],
  );
  assert.equal(ranking.algorithm_inputs.resolved_edge_count, 3);
  assert.equal(
    ranking.algorithm_inputs.resolved_edges.every((edge) => edge.weight === 1),
    true,
  );
  const scores = Object.fromEntries(
    ranking.results.map((row) => [row.node_id, row.baseline_centrality]),
  );
  assert.ok(scores["NODE-B"] > scores["NODE-C"]);
});

test("uniform_rank_regression: algorithm does not emit query or risk fields", () => {
  const ranking = build(["NODE-A", "NODE-B"], [["NODE-A", "NODE-B"]]);
  const serialized = JSON.stringify(ranking);
  assert.equal(serialized.includes("query_relevance"), false);
  assert.equal(serialized.includes("risk_score"), false);
  assert.equal(serialized.includes("blast_radius"), false);
});

test("uniform_rank_regression: caller inputs are not mutated", () => {
  const parameters = { alpha: 0.85, max_iterations: 500, tolerance: 1e-13 };
  const before = structuredClone(parameters);
  const ranking = build(["NODE-A", "NODE-B"], [["NODE-A", "NODE-B"]], parameters);
  assert.deepEqual(parameters, before);
  assert.ok(Object.isFrozen(ranking.algorithm_inputs));
});
