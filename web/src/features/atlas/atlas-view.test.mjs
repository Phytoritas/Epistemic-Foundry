import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  ATLAS_FINDING_CODES,
  ATLAS_OPERATION_IDS,
  ATLAS_SEARCH_STATES,
  AtlasViewError,
  COVERAGE_CLAIM_TYPES,
  atlasQueryRequest,
  atlasSnapshotRequest,
  auditCoverageClaims,
  buildAtlasView,
  buildCoverageClaims,
  renderAtlasPanel,
} from "./index.mjs";

const REPO = new URL("../../../../", import.meta.url);
const readJson = (relative) => JSON.parse(readFileSync(new URL(relative, REPO), "utf8"));
const MODULE_SOURCE = readFileSync(
  fileURLToPath(new URL("./atlas-view.mjs", import.meta.url)),
  "utf8",
);

const errorCode = (code) => (error) =>
  error instanceof AtlasViewError && error.code === code;

const HASH_A = `sha256:${"a".repeat(64)}`;
const HASH_B = `sha256:${"b".repeat(64)}`;

const snapshotFixture = ({ hostileGap = "no controlled trial", cells, extra } = {}) => ({
  snapshot_id: "CS-0001",
  insight_id: "INS-0001",
  insight_revision: 3,
  corpus_snapshot_hash: HASH_A,
  axes: [
    { axis_id: "method", label: "Method", buckets: ["observational", "experimental"] },
    { axis_id: "population", label: "Population", buckets: ["greenhouse", "field"] },
  ],
  cells: cells ?? [
    {
      coordinate: { method: "observational", population: "greenhouse" },
      search_state: "SEARCHED_WITH_RESULTS",
      support_count: 2,
      counter_count: 1,
      null_count: 0,
      boundary_count: 0,
      method_count: 1,
      independent_cluster_count: 2,
      evidence_ids: ["EV-0001", "EV-0002"],
      gap_labels: [],
    },
    {
      coordinate: { method: "experimental", population: "greenhouse" },
      search_state: "SEARCHED_NONE",
      support_count: 0,
      counter_count: 0,
      null_count: 0,
      boundary_count: 0,
      method_count: 0,
      independent_cluster_count: 0,
      evidence_ids: [],
      gap_labels: [hostileGap],
    },
    {
      coordinate: { method: "observational", population: "field" },
      search_state: "UNSEARCHED",
      support_count: 0,
      counter_count: 0,
      null_count: 0,
      boundary_count: 0,
      method_count: 0,
      independent_cluster_count: 0,
      evidence_ids: [],
      gap_labels: ["never searched"],
    },
  ],
  lens_entropy: null,
  dominant_lens: null,
  unsearched_scopes: ["publications before 2019"],
  created_at: "2026-01-02T03:04:05Z",
  provenance_manifest_id: "PM-0001",
  search_lane_receipt_ids: ["SLR-0001"],
  bias_risk_register_id: "BRR-0001",
  coverage_certificate_hash: HASH_B,
  effective_independent_evidence_count: 2,
  stale: false,
  ...extra,
});

test("atlas_view: the search-state vocabulary is the one the coverage schema declares", () => {
  const schema = readJson("schemas/coverage-snapshot.schema.json");
  assert.deepEqual(
    [...ATLAS_SEARCH_STATES].sort(),
    [...schema.$defs.cell.properties.search_state.enum].sort(),
  );
  assert.deepEqual([...ATLAS_SEARCH_STATES], ATLAS_SEARCH_STATES);
  assert.equal(Object.isFrozen(ATLAS_SEARCH_STATES), true);
});

test("atlas_view: coverage reports the cells the snapshot never carried", () => {
  const view = buildAtlasView(snapshotFixture());
  assert.deepEqual(view.cell_coverage, {
    declared_cell_count: 4,
    present_cell_count: 3,
    missing_cell_count: 1,
  });
  assert.deepEqual(view.search_state_distribution, {
    UNSEARCHED: 1,
    PARTIAL: 0,
    SEARCHED_NONE: 1,
    SEARCHED_WITH_RESULTS: 1,
  });
  assert.equal(view.coverage_state, "VISIBLE_LIMITATIONS");
  assert.equal(view.sections[0].id, "coverage-and-search-state");
  assert.equal(view.sections[0].visible, true);
  assert.deepEqual(view.unsearched_scopes, ["publications before 2019"]);
});

test("atlas_view: derived claims are the closed vocabulary bound to the certificate hash", () => {
  const claims = buildCoverageClaims(snapshotFixture());
  assert.deepEqual(
    claims.map((claim) => claim.claim_type),
    [...COVERAGE_CLAIM_TYPES],
  );
  for (const claim of claims) {
    assert.equal(claim.artifact_hash, HASH_B);
    assert.match(claim.source_field, /^[a-z_[\].]+$/u);
  }
  assert.equal(claims[0].status, "PARTIAL");
  assert.equal(claims[1].status, "PARTIAL");
  assert.equal(claims[4].status, "NOT_COMPUTED");
  assert.equal(
    auditCoverageClaims({ snapshot: snapshotFixture(), claims }).status,
    "PASS",
  );
});

test("atlas_view: a claim set the response does not carry refuses", () => {
  const snapshot = snapshotFixture();
  const claims = structuredClone(buildCoverageClaims(snapshot));
  claims[1].value.missing_cell_count = 0;
  claims[1].status = "MEASURED";
  assert.throws(
    () => auditCoverageClaims({ snapshot, claims }),
    errorCode("COVERAGE_CLAIM_MISMATCH"),
  );

  const dropped = structuredClone(buildCoverageClaims(snapshot)).slice(0, 5);
  assert.throws(
    () => auditCoverageClaims({ snapshot, claims: dropped }),
    errorCode("COVERAGE_CLAIM_SET_MISMATCH"),
  );

  const invented = structuredClone(buildCoverageClaims(snapshot));
  invented[0].claim_type = "TOTAL_COVERAGE";
  assert.throws(
    () => auditCoverageClaims({ snapshot, claims: invented }),
    errorCode("UNKNOWN_COVERAGE_CLAIM_TYPE"),
  );

  const restated = structuredClone(buildCoverageClaims(snapshot));
  restated[4].status = "MEASURED";
  assert.throws(
    () => auditCoverageClaims({ snapshot, claims: restated }),
    errorCode("COVERAGE_CLAIM_MISMATCH"),
  );
});

test("atlas_view: an unknown search state refuses instead of being bucketed", () => {
  const fixture = snapshotFixture();
  fixture.cells[2].search_state = "PROBABLY_SEARCHED";
  assert.throws(() => buildAtlasView(fixture), errorCode("UNKNOWN_SEARCH_STATE"));
});

test("atlas_view: a cell whose counts contradict its search state refuses", () => {
  const unsearched = snapshotFixture();
  unsearched.cells[2].evidence_ids = ["EV-0003"];
  assert.throws(
    () => buildAtlasView(unsearched),
    errorCode("SEARCH_STATE_CONTRADICTS_COUNTS"),
  );

  const none = snapshotFixture();
  none.cells[1].support_count = 1;
  assert.throws(() => buildAtlasView(none), errorCode("SEARCH_STATE_CONTRADICTS_COUNTS"));

  const withResults = snapshotFixture();
  withResults.cells[0].evidence_ids = [];
  assert.throws(
    () => buildAtlasView(withResults),
    errorCode("SEARCH_STATE_CONTRADICTS_COUNTS"),
  );
});

test("atlas_view: independence cannot exceed the evidence actually carried", () => {
  const snapshot = snapshotFixture();
  snapshot.effective_independent_evidence_count = 5;
  assert.throws(() => buildAtlasView(snapshot), errorCode("INDEPENDENCE_OVERCLAIM"));

  const cell = snapshotFixture();
  cell.cells[0].independent_cluster_count = 7;
  assert.throws(() => buildAtlasView(cell), errorCode("INDEPENDENCE_OVERCLAIM"));
});

test("atlas_view: undeclared and duplicated coordinates refuse", () => {
  const undeclared = snapshotFixture();
  undeclared.cells[0].coordinate = { method: "observational", population: "orbital" };
  assert.throws(() => buildAtlasView(undeclared), errorCode("CELL_COORDINATE_UNDECLARED"));

  const partial = snapshotFixture();
  partial.cells[0].coordinate = { method: "observational" };
  assert.throws(() => buildAtlasView(partial), errorCode("CELL_COORDINATE_UNDECLARED"));

  const duplicated = snapshotFixture();
  duplicated.cells[2].coordinate = { method: "observational", population: "greenhouse" };
  duplicated.cells[2].search_state = "SEARCHED_NONE";
  assert.throws(() => buildAtlasView(duplicated), errorCode("DUPLICATE_CELL_COORDINATE"));
});

test("atlas_view: proxies, accessors, and unknown fields fail without execution", () => {
  const fixture = snapshotFixture();
  assert.throws(() => buildAtlasView(new Proxy(fixture, {})), errorCode("ATLAS_INPUT_INVALID"));

  let invoked = false;
  const accessor = { ...fixture };
  Object.defineProperty(accessor, "cells", {
    enumerable: true,
    get() {
      invoked = true;
      return fixture.cells;
    },
  });
  assert.throws(() => buildAtlasView(accessor), errorCode("ATLAS_INPUT_INVALID"));
  assert.equal(invoked, false);

  assert.throws(
    () => buildAtlasView(snapshotFixture({ extra: { coverage_is_complete: true } })),
    errorCode("ATLAS_INPUT_INVALID"),
  );

  const sparse = snapshotFixture();
  // eslint-disable-next-line no-sparse-arrays
  sparse.unsearched_scopes = ["a", , "c"];
  assert.throws(() => buildAtlasView(sparse), errorCode("ATLAS_INPUT_INVALID"));
});

test("atlas_view: projection is deterministic, frozen, and input preserving", () => {
  const fixture = snapshotFixture();
  const before = structuredClone(fixture);
  const first = buildAtlasView(fixture);
  const second = buildAtlasView(snapshotFixture());
  assert.deepEqual(first, second);
  assert.deepEqual(fixture, before);
  assert.equal(Object.isFrozen(first), true);
  assert.equal(Object.isFrozen(first.cells), true);
  assert.equal(Object.isFrozen(first.coverage_claims[0]), true);
  assert.equal(/Date\.now|Math\.random|process\.env|new Date\(/u.test(MODULE_SOURCE), false);
});

test("atlas_view: untrusted gap labels and scopes are HTML escaped", () => {
  const html = renderAtlasPanel(
    snapshotFixture({ hostileGap: '<img src=x onerror="boom"> gap' }),
  );
  assert.equal(html.includes("<img src=x"), false);
  assert.equal(html.includes("&lt;img src=x onerror=&quot;boom&quot;&gt; gap"), true);
  const coverage = html.indexOf('data-section="coverage-and-search-state"');
  const gaps = html.indexOf('data-section="unsearched-and-gaps"');
  const claims = html.indexOf('data-section="coverage-claims"');
  assert.ok(coverage > 0 && coverage < gaps && gaps < claims);
  assert.equal(html.includes("UNSEARCHED"), true);
});

test("atlas_view: requests are built by the generated client from declared routes", () => {
  const manifest = readJson("web/src/generated/ui-client/route-manifest.json");
  const declared = new Map(
    manifest.routeTable.operations.map((operation) => [operation.operationId, operation]),
  );
  for (const operationId of ATLAS_OPERATION_IDS) assert.ok(declared.has(operationId));

  const snapshot = atlasSnapshotRequest({ snapshot_id: "CS-0001" });
  assert.equal(snapshot.operationId, "getCoverageSnapshot");
  assert.equal(snapshot.method, declared.get("getCoverageSnapshot").method);
  assert.equal(snapshot.pathTemplate, declared.get("getCoverageSnapshot").path);
  assert.equal(snapshot.url, "/api/v1/coverage-snapshots/CS-0001");
  assert.equal(Object.isFrozen(snapshot), true);

  const query = atlasQueryRequest({ query_plan: { query_plan_id: "QP-0001" } });
  assert.equal(query.operationId, "createRetrievalRun");
  assert.equal(query.method, "POST");
  assert.equal(query.url, "/api/v1/retrieval-runs");

  const sent = [];
  atlasSnapshotRequest({ snapshot_id: "CS-0002" }, (descriptor) => sent.push(descriptor));
  assert.equal(sent.length, 1);
  assert.equal(sent[0].url, "/api/v1/coverage-snapshots/CS-0002");
  assert.throws(() => atlasSnapshotRequest({ snapshot_id: "" }), errorCode("ATLAS_INPUT_INVALID"));
});

test("atlas_view: the view carries its source receipt and every finding code stands alone", () => {
  const view = buildAtlasView(snapshotFixture());
  assert.deepEqual(view.source_receipt, {
    corpus_snapshot_hash: HASH_A,
    coverage_certificate_hash: HASH_B,
    provenance_manifest_id: "PM-0001",
    bias_risk_register_id: "BRR-0001",
    search_lane_receipt_ids: ["SLR-0001"],
    operation_ids: [...ATLAS_OPERATION_IDS],
  });
  const codes = Object.keys(ATLAS_FINDING_CODES);
  assert.ok(codes.length >= 10);
  for (const code of codes) {
    assert.match(code, /^[A-Z][A-Z0-9_]+$/u);
    assert.ok(ATLAS_FINDING_CODES[code].length > 50, code);
    assert.ok(MODULE_SOURCE.includes(`"${code}"`), code);
  }
  const raised = (() => {
    try {
      buildAtlasView({});
      return null;
    } catch (error) {
      return error;
    }
  })();
  assert.ok(raised instanceof AtlasViewError);
  assert.equal(raised.reason, ATLAS_FINDING_CODES.ATLAS_INPUT_INVALID);
  assert.equal(Object.isFrozen(raised.context), true);
});
