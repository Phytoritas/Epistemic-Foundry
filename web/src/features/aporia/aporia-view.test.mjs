/**
 * U03 Aporia Engine view suite.
 *
 * The named tests below cover the five required checks the development manifest
 * declares for U03, without duplicating a single canonical vocabulary:
 *
 *   - schema_and_type_check         -> "vocabularies are the ones the argument-graph
 *                                       schema declares"
 *   - unit_and_contract_tests       -> "both kinds of open question render together";
 *                                       "contradictions partition into the engine's classes";
 *                                       "projection is deterministic, frozen and preserving"
 *   - negative_and_adversarial      -> "an undeclared edge, node type or status refuses";
 *                                       "a dangling or duplicated node refuses";
 *                                       "a hidden or invented open question refuses";
 *                                       "resolution overclaim refuses";
 *                                       "an unsound strict inference refuses";
 *                                       "proxies and accessors fail without execution";
 *                                       "hostile statements are escaped"
 *   - provenance_and_receipt_audit  -> "the view carries its graph receipt and binds only
 *                                       declared operations"
 *   - independent_review            -> "every finding code stands alone"
 *
 * There is no HTTP client, no DOM and no clock here.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  APORIA_FINDING_CODES,
  APORIA_OPERATION_IDS,
  APORIA_VIEW_VERSION,
  ARGUMENT_EDGE_TYPES,
  ARGUMENT_NODE_STATUSES,
  ARGUMENT_NODE_TYPES,
  AporiaViewError,
  CONTRADICTION_CLASSES,
  RESOLUTION_CLAIMS,
  aporiaGraphArtifactRequest,
  aporiaRunRequest,
  buildAporiaView,
  openQuestionIds,
  renderAporiaPanel,
  validateAporiaInput,
  validateArgumentGraph,
} from "./index.mjs";
import {
  GRAPH_HASH,
  aporiaInput,
  argumentGraph,
  edge,
  node,
  presentation,
} from "./aporia-test-fixtures.mjs";

const REPO = new URL("../../../../", import.meta.url);
const readJson = (relative) => JSON.parse(readFileSync(new URL(relative, REPO), "utf8"));
const MODULE_SOURCE = readFileSync(
  fileURLToPath(new URL("./aporia-view.mjs", import.meta.url)),
  "utf8",
);

const errorCode = (code) => (error) =>
  error instanceof AporiaViewError && error.code === code;

const withNodes = (mutate) => {
  const graph = argumentGraph();
  mutate(graph);
  return aporiaInput({ graph });
};

// --- schema_and_type_check ---------------------------------------------------

test("aporia_view: the node, status and edge vocabularies are the ones the schema declares", () => {
  const schema = readJson("schemas/argument-graph.schema.json");
  const nodeSchema = schema.properties.nodes.items.properties;
  assert.deepEqual([...ARGUMENT_NODE_TYPES], nodeSchema.node_type.enum);
  assert.deepEqual([...ARGUMENT_NODE_STATUSES], nodeSchema.status.enum);
  assert.deepEqual(
    [...ARGUMENT_EDGE_TYPES],
    [...schema.properties.edges.items.properties.edge_type.enum].sort(),
  );
  // The engine partition is closed: no edge type is left unclassified.
  for (const frozen of [ARGUMENT_EDGE_TYPES, ARGUMENT_NODE_TYPES, CONTRADICTION_CLASSES]) {
    assert.equal(Object.isFrozen(frozen), true);
  }
  assert.deepEqual([...RESOLUTION_CLAIMS], ["RESOLVED", "OPEN_QUESTIONS_REMAIN"]);
});

// --- unit_and_contract_tests -------------------------------------------------

test("aporia_view: both a hidden assumption and an unresolved objection render together", () => {
  const view = buildAporiaView(aporiaInput());
  assert.equal(view.resolution.claim, "OPEN_QUESTIONS_REMAIN");
  assert.equal(view.resolution.is_resolved, false);
  assert.equal(view.resolution.open_question_count, 2);
  const kinds = view.open_questions.map((item) => item.kind).sort();
  assert.deepEqual(kinds, ["HIDDEN_ASSUMPTION", "UNRESOLVED_OBJECTION"]);
  assert.deepEqual(openQuestionIds(validateArgumentGraph(argumentGraph())), ["AN-0002", "AN-0004"]);
  assert.equal(view.sections[0].id, "open-questions");
});

test("aporia_view: contradictions partition into exactly the engine's classes", () => {
  const view = buildAporiaView(aporiaInput());
  assert.deepEqual(view.contradiction_classes, [...CONTRADICTION_CLASSES]);
  assert.equal(view.contradictions_by_class.rebuts.count, 1);
  assert.deepEqual(view.contradictions_by_class.rebuts.edge_ids, ["AE-0003"]);
  assert.equal(view.contradictions_by_class.attacks.count, 0);
  assert.equal(view.contradiction_edges.length, 1);
  assert.equal(view.contradiction_edges[0].contradiction_class, "rebuts");
  // Strict, defeasible, dependency and contradiction stay four separate classes.
  assert.deepEqual(view.edge_classes.STRICT_INFERENCE, ["deductively_implies"]);
  assert.deepEqual(view.edge_classes.ASSUMPTION_DEPENDENCY, ["depends_on_assumption"]);
});

test("aporia_view: projection is deterministic, frozen and input preserving", () => {
  const input = aporiaInput();
  const before = structuredClone(input);
  const first = buildAporiaView(input);
  const second = buildAporiaView(aporiaInput());
  assert.deepEqual(first, second);
  assert.deepEqual(input, before);
  assert.equal(Object.isFrozen(first), true);
  assert.equal(Object.isFrozen(first.open_questions), true);
  assert.equal(Object.isFrozen(first.contradiction_edges), true);
  assert.equal(first.version, APORIA_VIEW_VERSION);
  assert.equal(/Date\.now|Math\.random|process\.env|new Date\(/u.test(MODULE_SOURCE), false);
});

// --- negative_and_adversarial_tests -----------------------------------------

test("aporia_view: an undeclared edge type, node type or status refuses", () => {
  assert.throws(
    () => buildAporiaView(withNodes((graph) => (graph.edges[2].edge_type = "disputes"))),
    errorCode("UNKNOWN_CONTRADICTION_CLASS"),
  );
  assert.throws(
    () => buildAporiaView(withNodes((graph) => (graph.nodes[0].node_type = "hypothesis"))),
    errorCode("UNKNOWN_NODE_TYPE"),
  );
  assert.throws(
    () => buildAporiaView(withNodes((graph) => (graph.nodes[0].status = "pending"))),
    errorCode("UNKNOWN_NODE_STATUS"),
  );
});

test("aporia_view: a dangling endpoint or a duplicated node refuses", () => {
  assert.throws(
    () => buildAporiaView(withNodes((graph) => (graph.edges[2].to_id = "AN-9999"))),
    errorCode("DANGLING_EDGE_ENDPOINT"),
  );
  assert.throws(
    () =>
      buildAporiaView(
        withNodes((graph) => {
          graph.nodes[3].argument_node_id = "AN-0001";
        }),
      ),
    errorCode("DUPLICATE_ARGUMENT_NODE"),
  );
});

test("aporia_view: a hidden or invented open question refuses", () => {
  assert.throws(
    () =>
      buildAporiaView(
        aporiaInput({ presentation: presentation({ open_question_ids: ["AN-0002"] }) }),
      ),
    errorCode("OPEN_QUESTION_HIDDEN"),
  );
  assert.throws(
    () =>
      buildAporiaView(
        aporiaInput({
          presentation: presentation({ open_question_ids: ["AN-0002", "AN-0004", "AN-0001"] }),
        }),
      ),
    errorCode("OPEN_QUESTION_HIDDEN"),
  );
});

test("aporia_view: a graph with open questions may not be presented as resolved", () => {
  assert.throws(
    () =>
      buildAporiaView(aporiaInput({ presentation: presentation({ resolution_claim: "RESOLVED" }) })),
    errorCode("RESOLVED_OVERCLAIM"),
  );
  // A resolved graph that still reports open questions also refuses.
  assert.throws(
    () =>
      buildAporiaView(
        aporiaInput({
          graph: argumentGraph({ hidden_assumption_ids: [], unresolved_objection_ids: [] }),
          presentation: presentation(),
        }),
      ),
    errorCode("OPEN_QUESTION_HIDDEN"),
  );
});

test("aporia_view: a strict inference from an open premise refuses as unsound", () => {
  assert.throws(
    () =>
      buildAporiaView(
        withNodes((graph) => {
          graph.nodes[0].status = "challenged";
        }),
      ),
    errorCode("STRICT_INFERENCE_UNSOUND"),
  );
  // A strict inference resting on an undeclared assumption refuses.
  assert.throws(
    () =>
      buildAporiaView(
        withNodes((graph) => {
          graph.edges[0].from_id = "AN-0002";
          graph.edges = [graph.edges[0], graph.edges[2]];
          graph.hidden_assumption_ids = ["AN-0002"];
        }),
      ),
    errorCode("STRICT_INFERENCE_UNSOUND"),
  );
});

test("aporia_view: proxies, accessors and unknown fields fail without execution", () => {
  const input = aporiaInput();
  assert.throws(() => buildAporiaView(new Proxy(input, {})), errorCode("APORIA_INPUT_INVALID"));

  let invoked = false;
  const accessor = { ...input };
  Object.defineProperty(accessor, "graph", {
    enumerable: true,
    get() {
      invoked = true;
      return input.graph;
    },
  });
  assert.throws(() => buildAporiaView(accessor), errorCode("APORIA_INPUT_INVALID"));
  assert.equal(invoked, false);

  assert.throws(
    () => buildAporiaView(withNodes((graph) => (graph.extra_field = true))),
    errorCode("APORIA_INPUT_INVALID"),
  );
});

test("aporia_view: hostile node statements are HTML escaped, open questions render first", () => {
  const html = renderAporiaPanel(
    withNodes((graph) => {
      graph.nodes[3].statement = '<script>alert("x")</script> objection';
    }),
  );
  assert.equal(html.includes("<script>"), false);
  assert.equal(html.includes("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; objection"), true);
  const open = html.indexOf('data-section="open-questions"');
  const contradictions = html.indexOf('data-section="contradiction-classes"');
  assert.ok(open > 0 && open < contradictions);
});

// --- provenance_and_receipt_audit -------------------------------------------

test("aporia_view: the view carries its graph receipt and binds only declared operations", () => {
  const view = buildAporiaView(aporiaInput());
  assert.deepEqual(view.source_receipt, {
    graph_hash: GRAPH_HASH,
    proof_trace_artifact_id: "PT-0001",
    operation_ids: [...APORIA_OPERATION_IDS],
  });

  const manifest = readJson("web/src/generated/ui-client/route-manifest.json");
  const declared = new Map(
    manifest.routeTable.operations.map((operation) => [operation.operationId, operation]),
  );
  for (const operationId of APORIA_OPERATION_IDS) assert.ok(declared.has(operationId));

  const artifact = aporiaGraphArtifactRequest({ artifact_id: "AG-0001" });
  assert.equal(artifact.operationId, "getArtifact");
  assert.equal(artifact.pathTemplate, declared.get("getArtifact").path);
  assert.equal(artifact.url, "/api/v1/artifacts/AG-0001");
  assert.equal(Object.isFrozen(artifact), true);

  const run = aporiaRunRequest({ run_id: "RUN-0001" });
  assert.equal(run.operationId, "getRun");
  assert.equal(run.url, "/api/v1/runs/RUN-0001");

  const sent = [];
  aporiaRunRequest({ run_id: "RUN-0002" }, (descriptor) => sent.push(descriptor));
  assert.equal(sent.length, 1);
  assert.equal(sent[0].url, "/api/v1/runs/RUN-0002");

  assert.throws(
    () => aporiaGraphArtifactRequest({ artifact_id: "" }),
    errorCode("APORIA_INPUT_INVALID"),
  );
});

// --- independent_review ------------------------------------------------------

test("aporia_view: every finding code stands alone with a distinct reason", () => {
  const codes = Object.keys(APORIA_FINDING_CODES);
  assert.ok(codes.length >= 8);
  const reasons = new Set();
  for (const code of codes) {
    assert.match(code, /^[A-Z][A-Z0-9_]+$/u);
    assert.ok(APORIA_FINDING_CODES[code].length > 50, code);
    assert.ok(MODULE_SOURCE.includes(code), code);
    reasons.add(APORIA_FINDING_CODES[code]);
  }
  assert.equal(reasons.size, codes.length);

  const raised = (() => {
    try {
      validateAporiaInput({});
      return null;
    } catch (error) {
      return error;
    }
  })();
  assert.ok(raised instanceof AporiaViewError);
  assert.equal(raised.reason, APORIA_FINDING_CODES.APORIA_INPUT_INVALID);
  assert.equal(Object.isFrozen(raised.context), true);
});
