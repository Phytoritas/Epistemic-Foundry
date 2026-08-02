import assert from "node:assert/strict";
import test from "node:test";

import {
  buildWorkspaceMapView,
  renderWorkspaceMapPanel,
  WorkspaceMapViewError,
} from "./index.mjs";
import { workspaceMapFixture } from "./map-test-fixtures.mjs";

const errorCode = (code) => (error) =>
  error instanceof WorkspaceMapViewError && error.code === code;

test("map_ui_test: coverage and exclusions are the first visible section", () => {
  const view = buildWorkspaceMapView(workspaceMapFixture());
  assert.equal(view.sections[0].id, "coverage-and-exclusions");
  assert.equal(view.sections[0].visible, true);
  assert.equal(view.sections[0].state, "VISIBLE_LIMITATIONS");
  assert.equal(view.coverage.indexed_entity_count, 4);
  assert.equal(view.coverage.resolved_edge_count, 2);
  assert.equal(view.coverage.unresolved_edge_count, 1);
  assert.equal(view.coverage.unreadable_path_count, 1);
});

test("map_ui_test: unresolved edges remain visible and excluded in every dimension", () => {
  const view = buildWorkspaceMapView(workspaceMapFixture());
  const unresolvedIds = view.coverage.unresolved_edges.map(({ edge_id: edgeId }) => edgeId);
  assert.equal(unresolvedIds.length, 1);
  assert.deepEqual(view.coverage.exclusions_by_dimension, {
    baseline_structural_centrality: unresolvedIds,
    query_lexical_relevance: unresolvedIds,
    intrinsic_risk: unresolvedIds,
    change_impact: unresolvedIds,
  });
  assert.equal(view.edges.unresolved[0].unresolved_reason, "TARGET_NOT_FOUND");
});

test("map_ui_test: four ranking dimensions remain separate per node", () => {
  const view = buildWorkspaceMapView(workspaceMapFixture());
  const schema = view.nodes.find((node) => node.node_id === "ENT-schema-run-spec");
  assert.deepEqual(Object.keys(schema.dimensions), [
    "baseline_structural_centrality",
    "query_lexical_relevance",
    "intrinsic_risk",
    "change_impact",
  ]);
  assert.equal(typeof schema.dimensions.baseline_structural_centrality.score, "number");
  assert.equal(schema.dimensions.query_lexical_relevance.score, 1);
  assert.equal(schema.dimensions.intrinsic_risk.score > 0, true);
  assert.equal(typeof schema.dimensions.change_impact.status, "string");
});

test("map_ui_test: no aggregate importance, confidence, verdict, or semantic rank is invented", () => {
  const serialized = JSON.stringify(buildWorkspaceMapView(workspaceMapFixture()));
  assert.equal(/overall[_ ]importance/iu.test(serialized), false);
  assert.equal(/combined[_ ]score/iu.test(serialized), false);
  assert.equal(/confidence/iu.test(serialized), false);
  assert.equal(/verdict/iu.test(serialized), false);
  assert.equal(/semantic[_ ]rank/iu.test(serialized), false);
});

test("map_ui_test: query and semantic status retain explicit null semantics", () => {
  const view = buildWorkspaceMapView(workspaceMapFixture({ query: null }));
  assert.equal(view.query.value, null);
  assert.equal(view.query.personalization, null);
  assert.equal(view.query.semantic_score, null);
  assert.equal(view.query.semantic_status, "NOT_COMPUTED");
  assert.equal(view.ranking_claims[1].status, "NOT_PERSONALIZED");
  assert.deepEqual(view.ranking_claims[1].order, []);
  assert.ok(
    view.nodes.every(
      (node) =>
        node.dimensions.query_lexical_relevance.semantic_score === null &&
        node.dimensions.query_lexical_relevance.semantic_status === "NOT_COMPUTED",
    ),
  );
});

test("map_ui_test: algorithm name, version, artifact hash, and labels are visible", () => {
  const view = buildWorkspaceMapView(workspaceMapFixture());
  assert.equal(view.algorithms.length, 4);
  assert.deepEqual(
    view.algorithms.map(({ label }) => label),
    [
      "Baseline structural centrality",
      "Query lexical relevance",
      "Intrinsic risk",
      "Change impact / blast radius",
    ],
  );
  for (const algorithm of view.algorithms) {
    assert.match(algorithm.algorithm_name, /^[A-Z][A-Z0-9_]+$/u);
    assert.match(algorithm.algorithm_version, /^4\.0\.0-m0[23]\.1$/u);
    assert.match(algorithm.artifact_hash, /^sha256:[0-9a-f]{64}$/u);
  }
});

test("map_ui_test: intrinsic risk is not inferred from blast radius", () => {
  const view = buildWorkspaceMapView(workspaceMapFixture());
  const schema = view.nodes.find((node) => node.node_id === "ENT-schema-run-spec");
  assert.equal(schema.dimensions.intrinsic_risk.score > 0.5, true);
  assert.equal(schema.dimensions.change_impact.status, "UNAFFECTED");
  const app = view.nodes.find((node) => node.node_id === "ENT-package-app");
  assert.equal(app.dimensions.change_impact.status, "AFFECTED");
  assert.equal(app.dimensions.change_impact.origin_node_id, "ENT-package-core");
});

test("map_ui_test: untrusted label, query, and unresolved hint are HTML escaped", () => {
  const fixture = workspaceMapFixture({
    query: "Evolution Run Spec <script>alert</script>",
    hostileLabel: '<img src=x onerror="boom"> Core',
    hostileHint: '<svg onload="boom"> missing workflow',
  });
  const html = renderWorkspaceMapPanel(fixture);
  assert.equal(html.includes("<script>alert</script>"), false);
  assert.equal(html.includes("<img src=x"), false);
  assert.equal(html.includes("<svg onload"), false);
  assert.equal(html.includes("&lt;script&gt;alert&lt;/script&gt;"), true);
  assert.equal(html.includes("&lt;img src=x onerror=&quot;boom&quot;&gt;"), true);
  assert.equal(html.includes("&lt;svg onload=&quot;boom&quot;&gt;"), true);
});

test("map_ui_test: rendered coverage precedes algorithm and entity sections", () => {
  const html = renderWorkspaceMapPanel(workspaceMapFixture());
  const coverage = html.indexOf('data-section="coverage-and-exclusions"');
  const algorithms = html.indexOf('data-section="algorithm-bindings"');
  const entities = html.indexOf('data-section="workspace-entities"');
  assert.ok(coverage > 0);
  assert.ok(coverage < algorithms);
  assert.ok(algorithms < entities);
  assert.equal(html.includes("NOT_COMPUTED"), true);
});

test("map_ui_test: view building is deterministic, deeply frozen, and input preserving", () => {
  const fixture = workspaceMapFixture();
  const before = structuredClone(fixture);
  const first = buildWorkspaceMapView(fixture);
  const second = buildWorkspaceMapView(workspaceMapFixture({ reverse: true }));
  assert.deepEqual(first, second);
  assert.deepEqual(fixture, before);
  assert.equal(Object.isFrozen(first), true);
  assert.equal(Object.isFrozen(first.nodes), true);
  assert.equal(Object.isFrozen(first.nodes[0].dimensions), true);
});

test("map_ui_test: tampered upstream artifacts fail closed", () => {
  const fixture = workspaceMapFixture();
  const tampered = structuredClone(fixture);
  tampered.baseline_centrality.results[0].baseline_centrality += 0.01;
  assert.throws(() => buildWorkspaceMapView(tampered));

  const queryTamper = structuredClone(fixture);
  queryTamper.query_personalization.ranking_hash = `sha256:${"0".repeat(64)}`;
  assert.throws(() => buildWorkspaceMapView(queryTamper));
});

test("map_ui_test: top-level proxies, accessors, and unknown fields fail without execution", () => {
  const fixture = workspaceMapFixture();
  assert.throws(
    () => buildWorkspaceMapView(new Proxy(fixture, {})),
    errorCode("MAP_INPUT_INVALID"),
  );
  let invoked = false;
  const accessor = { ...fixture };
  Object.defineProperty(accessor, "inventory", {
    enumerable: true,
    get() {
      invoked = true;
      return fixture.inventory;
    },
  });
  assert.throws(() => buildWorkspaceMapView(accessor), errorCode("MAP_INPUT_INVALID"));
  assert.equal(invoked, false);
  assert.throws(
    () => buildWorkspaceMapView({ ...fixture, overall_importance: 1 }),
    errorCode("MAP_INPUT_INVALID"),
  );
});

