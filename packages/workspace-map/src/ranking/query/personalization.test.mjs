import assert from "node:assert/strict";
import test from "node:test";

import {
  buildWorkspaceInventory,
  extractWorkspaceEdges,
} from "../../inventory/index.mjs";
import {
  QUERY_PERSONALIZATION_ALGORITHM,
  QUERY_PERSONALIZATION_VERSION,
  WorkspaceMapQueryRankingError,
  computeQueryPersonalization,
  computeQueryPersonalizationHash,
  validateQueryPersonalization,
} from "./index.mjs";

const HASH = `sha256:${"a".repeat(64)}`;
const errorCode = (code) => (error) =>
  error instanceof WorkspaceMapQueryRankingError && error.code === code;

const entity = (overrides = {}) => ({
  entity_id: "ENT-package",
  kind: "PACKAGE",
  label: "Foundry Kernel",
  path: "packages/foundry-kernel/package.json",
  locator: null,
  content_hash: HASH,
  owner: "WP-B03",
  source_class: "SOURCE",
  aliases: [{ namespace: "PACKAGE_NAME", value: "@epistemic-foundry/foundry-kernel" }],
  ...overrides,
});

const entities = () => [
  entity(),
  entity({
    entity_id: "ENT-schema-run-spec",
    kind: "SCHEMA",
    label: "Evolution Run Spec",
    path: "schemas/evolution-run-spec.schema.json",
    owner: "WP-C01",
    aliases: [
      {
        namespace: "SCHEMA_ID",
        value: "https://epistemic-foundry.local/schemas/evolution-run-spec.schema.json",
      },
    ],
  }),
  entity({
    entity_id: "ENT-schema-policy",
    kind: "SCHEMA",
    label: "Policy Bundle",
    path: "schemas/policy-bundle.schema.json",
    owner: "WP-C01",
    aliases: [
      {
        namespace: "SCHEMA_ID",
        value: "https://epistemic-foundry.local/schemas/policy-bundle.schema.json",
      },
    ],
  }),
  entity({
    entity_id: "ENT-workflow",
    kind: "WORKFLOW",
    label: "Evolution Chamber Workflow",
    path: "workflows/evolution_chamber.workflow.yaml",
    owner: "WP-F04",
    aliases: [{ namespace: "WORKFLOW_ID", value: "evolution_chamber" }],
  }),
];

const references = () => [
  {
    source_entity_id: "ENT-package",
    kind: "SCHEMA_REF",
    target_identity: { namespace: "ENTITY_ID", value: "ENT-schema-run-spec" },
    target_hint: null,
    source_locator: "packages/foundry-kernel/src/run.mjs:1",
    owner: "WP-B03",
  },
  {
    source_entity_id: "ENT-workflow",
    kind: "WORKFLOW_DEPENDS_ON",
    target_identity: { namespace: "WORKFLOW_ID", value: "missing_workflow" },
    target_hint: "workflow declared by an unavailable plugin",
    source_locator: "workflows/evolution_chamber.workflow.yaml:depends_on",
    owner: "WP-F04",
  },
];

const graph = ({ reverseEntities = false, reverseReferences = false } = {}) => {
  const inventory = buildWorkspaceInventory({
    workspace_id: "WS-M03-personalization",
    root_hash: HASH,
    entities: reverseEntities ? entities().reverse() : entities(),
    unreadable_paths: [],
  });
  const refs = references();
  const extraction = extractWorkspaceEdges({
    inventory,
    references: reverseReferences ? refs.reverse() : refs,
  });
  return { inventory, extraction };
};

test("personalization_test: algorithm and version are explicit", () => {
  assert.equal(
    QUERY_PERSONALIZATION_ALGORITHM,
    "DETERMINISTIC_FIELD_WEIGHTED_TOKEN_OVERLAP",
  );
  assert.equal(QUERY_PERSONALIZATION_VERSION, "4.0.0-m03.1");
});

test("personalization_test: absent query produces explicit null personalization", () => {
  const inputs = graph();
  const output = computeQueryPersonalization({ ...inputs, query: null });
  assert.equal(output.query, null);
  assert.equal(output.query_hash, null);
  assert.equal(output.personalization, null);
  assert.deepEqual(output.algorithm_inputs.query_tokens, []);
  assert.equal(output.algorithm_inputs.query_token_count, 0);
  assert.ok(output.results.every((row) => row.query_relevance === 0));
  assert.ok(output.results.every((row) => row.semantic_score === null));
  assert.ok(output.results.every((row) => row.semantic_status === "NOT_COMPUTED"));
});

test("personalization_test: field-weighted token and phrase relevance is real", () => {
  const inputs = graph();
  const output = computeQueryPersonalization({ ...inputs, query: "Evolution Run Spec" });
  const rows = Object.fromEntries(output.results.map((row) => [row.node_id, row]));
  assert.equal(output.personalization, QUERY_PERSONALIZATION_ALGORITHM);
  assert.deepEqual(output.algorithm_inputs.query_tokens, ["evolution", "run", "spec"]);
  assert.equal(rows["ENT-schema-run-spec"].query_relevance, 1);
  assert.equal(rows["ENT-schema-run-spec"].exact_phrase_match, true);
  assert.deepEqual(rows["ENT-schema-run-spec"].matched_tokens, [
    "evolution",
    "run",
    "spec",
  ]);
  assert.ok(rows["ENT-workflow"].query_relevance > 0);
  assert.equal(rows["ENT-schema-policy"].query_relevance, 0);
  assert.equal(output.ranking_order[0], "ENT-schema-run-spec");
});

test("personalization_test: relevance is separate from semantic, centrality, and risk", () => {
  const output = computeQueryPersonalization({ ...graph(), query: "policy" });
  const serialized = JSON.stringify(output);
  assert.equal(serialized.includes("baseline_centrality"), false);
  assert.equal(serialized.includes("risk_score"), false);
  assert.equal(serialized.includes("blast_radius"), false);
  assert.equal(output.results.every((row) => row.semantic_score === null), true);
  assert.equal(output.algorithm.semantic_score_policy, "EXPLICIT_NULL_NOT_COMPUTED");
});

test("personalization_test: unresolved edges are recorded but do not alter node scores", () => {
  const withUnresolved = graph();
  const resolvedOnly = extractWorkspaceEdges({
    inventory: withUnresolved.inventory,
    references: references().slice(0, 1),
  });
  const one = computeQueryPersonalization({ ...withUnresolved, query: "evolution" });
  const two = computeQueryPersonalization({
    inventory: withUnresolved.inventory,
    extraction: resolvedOnly,
    query: "evolution",
  });
  assert.deepEqual(one.results, two.results);
  assert.equal(one.algorithm_inputs.unresolved_edge_count, 1);
  assert.deepEqual(
    one.algorithm_inputs.excluded_unresolved_edge_ids,
    withUnresolved.extraction.unresolved_edges.map((edge) => edge.edge_id),
  );
  assert.notEqual(one.ranking_hash, two.ranking_hash);
});

test("personalization_test: input permutation preserves output hash and ID", () => {
  const one = computeQueryPersonalization({ ...graph(), query: "policy bundle" });
  const two = computeQueryPersonalization({
    ...graph({ reverseEntities: true, reverseReferences: true }),
    query: "policy bundle",
  });
  assert.deepEqual(one, two);
  assert.equal(one.ranking_hash, two.ranking_hash);
  assert.equal(one.ranking_id, two.ranking_id);
});

test("personalization_test: result order and tie break are deterministic", () => {
  const output = computeQueryPersonalization({ ...graph(), query: "not-present" });
  const expected = output.results.map((row) => row.node_id);
  assert.deepEqual(expected, [...expected].sort());
  assert.deepEqual(output.ranking_order, [...expected].sort());
});

test("personalization_test: validation, hash helper, and deep immutability hold", () => {
  const inputs = graph();
  const output = computeQueryPersonalization({ ...inputs, query: "kernel" });
  assert.deepEqual(
    validateQueryPersonalization(output, inputs.inventory, inputs.extraction),
    output,
  );
  assert.equal(
    computeQueryPersonalizationHash(output, inputs.inventory, inputs.extraction),
    output.ranking_hash,
  );
  assert.equal(Object.isFrozen(output), true);
  assert.equal(Object.isFrozen(output.results), true);
  assert.equal(Object.isFrozen(output.results[0]), true);
});

test("personalization_test: score and hash tampering fail closed", () => {
  const inputs = graph();
  const output = computeQueryPersonalization({ ...inputs, query: "kernel" });
  const scoreTamper = structuredClone(output);
  scoreTamper.results[0].query_relevance =
    scoreTamper.results[0].query_relevance === 0.123 ? 0.124 : 0.123;
  assert.throws(
    () => validateQueryPersonalization(scoreTamper, inputs.inventory, inputs.extraction),
    errorCode("QUERY_PERSONALIZATION_REBUILD_MISMATCH"),
  );
  const hashTamper = structuredClone(output);
  hashTamper.ranking_hash = `sha256:${"b".repeat(64)}`;
  assert.throws(
    () => validateQueryPersonalization(hashTamper, inputs.inventory, inputs.extraction),
    errorCode("QUERY_PERSONALIZATION_HASH_MISMATCH"),
  );
});

test("personalization_test: blank, non-indexable, and non-NFC queries fail closed", () => {
  const inputs = graph();
  assert.throws(
    () => computeQueryPersonalization({ ...inputs, query: "   " }),
    errorCode("INVALID_QUERY"),
  );
  assert.throws(
    () => computeQueryPersonalization({ ...inputs, query: "---" }),
    errorCode("QUERY_HAS_NO_INDEXABLE_TOKENS"),
  );
  assert.throws(
    () => computeQueryPersonalization({ ...inputs, query: "e\u0301" }),
    errorCode("INVALID_QUERY"),
  );
});

test("personalization_test: hostile wrappers and accessors fail without execution", () => {
  const inputs = graph();
  assert.throws(
    () => computeQueryPersonalization(new Proxy({ ...inputs, query: "kernel" }, {})),
    errorCode("INVALID_QUERY_PERSONALIZATION_INPUT"),
  );
  let invoked = false;
  const hostile = { ...inputs, query: "kernel" };
  Object.defineProperty(hostile, "query", {
    enumerable: true,
    get() {
      invoked = true;
      return "stolen";
    },
  });
  assert.throws(
    () => computeQueryPersonalization(hostile),
    errorCode("INVALID_QUERY_PERSONALIZATION_INPUT"),
  );
  assert.equal(invoked, false);
});

test("personalization_test: caller inputs are unchanged", () => {
  const inputs = graph();
  const candidate = { ...inputs, query: "Evolution Run Spec" };
  const before = structuredClone(candidate);
  computeQueryPersonalization(candidate);
  assert.deepEqual(candidate, before);
});
