import assert from "node:assert/strict";
import test from "node:test";

import {
  EDGE_KINDS,
  buildWorkspaceInventory,
  extractWorkspaceEdges,
} from "../../inventory/index.mjs";
import {
  IMPACT_EDGE_DIRECTION_BY_KIND,
  RISK_CHANGE_IMPACT_ALGORITHM,
  RISK_CHANGE_IMPACT_VERSION,
  SHARED_RESOURCE_KINDS,
  WorkspaceMapQueryRankingError,
  computeRiskAndChangeImpact,
  computeRiskAndChangeImpactHash,
  validateRiskAndChangeImpact,
} from "./index.mjs";

const HASH = `sha256:${"c".repeat(64)}`;
const errorCode = (code) => (error) =>
  error instanceof WorkspaceMapQueryRankingError && error.code === code;

const entity = (overrides = {}) => ({
  entity_id: "ENT-package-app",
  kind: "PACKAGE",
  label: "App package",
  path: "packages/app/package.json",
  locator: null,
  content_hash: HASH,
  owner: "WP-APP",
  source_class: "SOURCE",
  aliases: [{ namespace: "PACKAGE_NAME", value: "@example/app" }],
  ...overrides,
});

const entities = () => [
  entity(),
  entity({
    entity_id: "ENT-package-core",
    label: "Core package",
    path: "packages/core/package.json",
    owner: "WP-CORE",
    aliases: [{ namespace: "PACKAGE_NAME", value: "@example/core" }],
  }),
  entity({
    entity_id: "ENT-package-isolate",
    label: "Isolated package",
    path: "packages/isolate/package.json",
    owner: "WP-ISOLATE",
    aliases: [{ namespace: "PACKAGE_NAME", value: "@example/isolate" }],
  }),
  entity({
    entity_id: "ENT-schema",
    kind: "SCHEMA",
    label: "Mutable Run Spec",
    path: "schemas/run-spec.schema.json",
    owner: "WP-C01",
    aliases: [
      {
        namespace: "SCHEMA_ID",
        value: "https://epistemic-foundry.local/schemas/run-spec.schema.json",
      },
    ],
  }),
  entity({
    entity_id: "ENT-work-package",
    kind: "WORK_PACKAGE",
    label: "C01",
    path: null,
    locator: "manifest:work-package/C01",
    owner: "PRODUCT-OWNER",
    aliases: [{ namespace: "WORK_PACKAGE_ID", value: "C01" }],
  }),
  entity({
    entity_id: "ENT-evidence",
    kind: "EVIDENCE",
    label: "Evidence",
    path: null,
    locator: "ledger:evidence/EV-001",
    owner: "CORPUS-001",
    source_class: "RESEARCH",
    aliases: [{ namespace: "EVIDENCE_ID", value: "EV-001" }],
  }),
  entity({
    entity_id: "ENT-claim",
    kind: "CLAIM",
    label: "Claim",
    path: null,
    locator: "ledger:claim/CLM-001",
    owner: "CORPUS-001",
    source_class: "RESEARCH",
    aliases: [{ namespace: "CLAIM_ID", value: "CLM-001" }],
  }),
  entity({
    entity_id: "ENT-artifact-source",
    kind: "ARTIFACT",
    label: "Source artifact",
    path: "artifacts/source.json",
    locator: "artifact://sha256/cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    owner: "RUN-001",
    source_class: "ARTIFACT",
    aliases: [{ namespace: "ARTIFACT_ID", value: "ART-SOURCE" }],
  }),
  entity({
    entity_id: "ENT-artifact-derived",
    kind: "ARTIFACT",
    label: "Derived artifact",
    path: "artifacts/derived.json",
    locator: "artifact://sha256/dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    owner: "RUN-001",
    source_class: "ARTIFACT",
    aliases: [{ namespace: "ARTIFACT_ID", value: "ART-DERIVED" }],
  }),
  entity({
    entity_id: "ENT-decision-old",
    kind: "DECISION",
    label: "Old decision",
    path: null,
    locator: "ledger:decision/OLD",
    owner: "PRODUCT-OWNER",
    source_class: "ARTIFACT",
    aliases: [{ namespace: "DECISION_ID", value: "DEC-OLD" }],
  }),
  entity({
    entity_id: "ENT-decision-new",
    kind: "DECISION",
    label: "New decision",
    path: null,
    locator: "ledger:decision/NEW",
    owner: "PRODUCT-OWNER",
    source_class: "ARTIFACT",
    aliases: [{ namespace: "DECISION_ID", value: "DEC-NEW" }],
  }),
];

const reference = (source, kind, target, owner, index) => ({
  source_entity_id: source,
  kind,
  target_identity: { namespace: "ENTITY_ID", value: target },
  target_hint: null,
  source_locator: `fixture:edge-${index}`,
  owner,
});

const references = () => [
  reference("ENT-package-app", "PACKAGE_DEPENDS_ON", "ENT-package-core", "WP-APP", 1),
  reference("ENT-package-app", "SCHEMA_REF", "ENT-schema", "WP-APP", 2),
  reference("ENT-work-package", "OWNS_CONTRACT", "ENT-schema", "PRODUCT-OWNER", 3),
  reference(
    "ENT-evidence",
    "EVIDENCE_SUPPORTS_CLAIM",
    "ENT-claim",
    "CORPUS-001",
    4,
  ),
  reference(
    "ENT-artifact-derived",
    "DERIVED_FROM",
    "ENT-artifact-source",
    "RUN-001",
    5,
  ),
  reference(
    "ENT-decision-new",
    "SUPERSEDES",
    "ENT-decision-old",
    "PRODUCT-OWNER",
    6,
  ),
  {
    source_entity_id: "ENT-evidence",
    kind: "EVIDENCE_COUNTERS_CLAIM",
    target_identity: { namespace: "CLAIM_ID", value: "CLM-MISSING" },
    target_hint: "claim not present in this bounded inventory",
    source_locator: "fixture:edge-unresolved",
    owner: "CORPUS-001",
  },
];

const graph = ({ reverseEntities = false, reverseReferences = false } = {}) => {
  const inventory = buildWorkspaceInventory({
    workspace_id: "WS-M03-impact",
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

const profiles = (overrides = {}) =>
  entities().map((row) => ({
    node_id: row.entity_id,
    authority_level: "NONE",
    write_scope_level: "READ_ONLY",
    data_sensitivity: "PUBLIC",
    mutable_contract: false,
    ...(overrides[row.entity_id] ?? {}),
  }));

const compute = ({
  changedNodeIds = ["ENT-package-core"],
  riskProfiles = profiles(),
  sharedResources = [],
  inputs = graph(),
} = {}) =>
  computeRiskAndChangeImpact({
    ...inputs,
    changed_node_ids: changedNodeIds,
    risk_profiles: riskProfiles,
    shared_resources: sharedResources,
  });

test("blast_radius_test: algorithm, version, and closed direction table are explicit", () => {
  assert.equal(
    RISK_CHANGE_IMPACT_ALGORITHM,
    "TYPED_RISK_PLUS_DETERMINISTIC_IMPACT_TRAVERSAL",
  );
  assert.equal(RISK_CHANGE_IMPACT_VERSION, "4.0.0-m03.1");
  assert.deepEqual(
    Object.keys(IMPACT_EDGE_DIRECTION_BY_KIND).sort(),
    [...EDGE_KINDS].sort(),
  );
  assert.equal(IMPACT_EDGE_DIRECTION_BY_KIND.PACKAGE_DEPENDS_ON, "TARGET_TO_SOURCE");
  assert.equal(IMPACT_EDGE_DIRECTION_BY_KIND.EVIDENCE_SUPPORTS_CLAIM, "SOURCE_TO_TARGET");
  assert.equal(IMPACT_EDGE_DIRECTION_BY_KIND.OWNS_CONTRACT, "BIDIRECTIONAL");
});

test("blast_radius_test: dependency target changes propagate to dependants", () => {
  const output = compute({ changedNodeIds: ["ENT-package-core"] });
  assert.deepEqual(output.affected_node_ids, ["ENT-package-app"]);
  const app = output.impact_results.find((row) => row.node_id === "ENT-package-app");
  assert.equal(app.impact_status, "AFFECTED");
  assert.equal(app.distance, 1);
  assert.equal(app.origin_node_id, "ENT-package-core");
});

test("blast_radius_test: evidence changes propagate forward to claims", () => {
  const output = compute({ changedNodeIds: ["ENT-evidence"] });
  assert.ok(output.affected_node_ids.includes("ENT-claim"));
  const claim = output.impact_results.find((row) => row.node_id === "ENT-claim");
  assert.equal(claim.distance, 1);
  assert.equal(claim.origin_node_id, "ENT-evidence");
});

test("blast_radius_test: provenance and supersession target changes propagate to dependants", () => {
  const output = compute({
    changedNodeIds: ["ENT-artifact-source", "ENT-decision-old"],
  });
  assert.ok(output.affected_node_ids.includes("ENT-artifact-derived"));
  assert.ok(output.affected_node_ids.includes("ENT-decision-new"));
});

test("blast_radius_test: contract ownership is bidirectional", () => {
  const fromContract = compute({ changedNodeIds: ["ENT-schema"] });
  assert.ok(fromContract.affected_node_ids.includes("ENT-work-package"));
  assert.ok(fromContract.affected_node_ids.includes("ENT-package-app"));
  const fromOwner = compute({ changedNodeIds: ["ENT-work-package"] });
  assert.ok(fromOwner.affected_node_ids.includes("ENT-schema"));
});

test("blast_radius_test: every hidden shared-resource kind materializes effective edges", () => {
  for (const kind of SHARED_RESOURCE_KINDS) {
    const output = compute({
      changedNodeIds: ["ENT-package-isolate"],
      sharedResources: [
        {
          resource_id: `RES-${kind}`,
          kind,
          node_ids: ["ENT-package-isolate", "ENT-package-core"],
        },
      ],
    });
    assert.ok(output.affected_node_ids.includes("ENT-package-core"), kind);
    assert.ok(output.affected_node_ids.includes("ENT-package-app"), kind);
    const sharedEdges = output.effective_edges.filter(
      (edge) => edge.resource_id === `RES-${kind}`,
    );
    assert.equal(sharedEdges.length, 2, kind);
    assert.ok(sharedEdges.every((edge) => edge.origin === "SHARED_RESOURCE"), kind);
  }
});

test("blast_radius_test: shared resource participants form deterministic pairwise edges", () => {
  const output = compute({
    sharedResources: [
      {
        resource_id: "RES-shared-write",
        kind: "SHARED_WRITE",
        node_ids: ["ENT-package-isolate", "ENT-package-core", "ENT-package-app"],
      },
    ],
  });
  const sharedEdges = output.effective_edges.filter(
    (edge) => edge.resource_id === "RES-shared-write",
  );
  assert.equal(sharedEdges.length, 6);
  assert.equal(new Set(sharedEdges.map((edge) => edge.impact_edge_id)).size, 6);
});

test("blast_radius_test: unresolved edges are recorded and excluded from propagation", () => {
  const output = compute({ changedNodeIds: ["ENT-evidence"] });
  assert.equal(output.algorithm_inputs.unresolved_edge_count, 1);
  assert.deepEqual(
    output.excluded_unresolved_edge_ids,
    graph().extraction.unresolved_edges.map((edge) => edge.edge_id),
  );
  assert.equal(
    output.effective_edges.some((edge) => edge.source_edge_id === output.excluded_unresolved_edge_ids[0]),
    false,
  );
});

test("blast_radius_test: intrinsic risk uses authority, write scope, sensitivity, and mutability", () => {
  const output = compute({
    riskProfiles: profiles({
      "ENT-schema": {
        authority_level: "CANONICAL",
        write_scope_level: "GLOBAL",
        data_sensitivity: "RESTRICTED",
        mutable_contract: true,
      },
      "ENT-package-app": {
        authority_level: "LOCAL",
        write_scope_level: "BOUNDED",
        data_sensitivity: "PUBLIC",
        mutable_contract: false,
      },
    }),
  });
  const rows = Object.fromEntries(output.risk_results.map((row) => [row.node_id, row]));
  assert.equal(rows["ENT-schema"].risk_score, 1);
  assert.ok(rows["ENT-package-app"].risk_score > 0);
  assert.equal(rows["ENT-package-isolate"].risk_score, 0);
  assert.equal(output.risk_order[0], "ENT-schema");
  assert.equal(rows["ENT-schema"].weighted_components.mutable_contract, 4);
});

test("blast_radius_test: risk and blast radius remain separate dimensions", () => {
  const highRiskIsolate = compute({
    changedNodeIds: ["ENT-package-core"],
    riskProfiles: profiles({
      "ENT-package-isolate": {
        authority_level: "CANONICAL",
        write_scope_level: "GLOBAL",
        data_sensitivity: "RESTRICTED",
        mutable_contract: true,
      },
    }),
  });
  const isolateRisk = highRiskIsolate.risk_results.find(
    (row) => row.node_id === "ENT-package-isolate",
  );
  const isolateImpact = highRiskIsolate.impact_results.find(
    (row) => row.node_id === "ENT-package-isolate",
  );
  assert.equal(isolateRisk.risk_score, 1);
  assert.equal(isolateImpact.impact_status, "UNAFFECTED");
  const serialized = JSON.stringify(highRiskIsolate);
  assert.equal(serialized.includes("baseline_centrality"), false);
  assert.equal(serialized.includes("query_relevance"), false);
});

test("blast_radius_test: multi-source traversal handles cycles without duplicates", () => {
  const inputs = graph();
  const cyclicExtraction = extractWorkspaceEdges({
    inventory: inputs.inventory,
    references: [
      ...references(),
      reference("ENT-package-core", "PACKAGE_DEPENDS_ON", "ENT-package-app", "WP-CORE", 7),
    ],
  });
  const output = compute({
    changedNodeIds: ["ENT-package-core", "ENT-evidence"],
    inputs: { inventory: inputs.inventory, extraction: cyclicExtraction },
  });
  assert.equal(new Set(output.affected_node_ids).size, output.affected_node_ids.length);
  assert.equal(output.blast_radius_count, output.affected_node_ids.length);
  assert.equal(
    output.impact_results.filter((row) => row.impact_status === "CHANGED").length,
    2,
  );
});

test("blast_radius_test: empty changed set is an explicit no-change assessment", () => {
  const output = compute({ changedNodeIds: [] });
  assert.equal(output.blast_radius_count, 0);
  assert.deepEqual(output.affected_node_ids, []);
  assert.deepEqual(output.impact_order, []);
  assert.equal(
    output.impact_results.every(
      (row) =>
        row.impact_status === "UNAFFECTED" &&
        row.distance === null &&
        row.origin_node_id === null &&
        row.path_edge_ids.length === 0,
    ),
    true,
  );
});

test("blast_radius_test: equal-length paths use a deterministic canonical witness", () => {
  const inputs = graph();
  const diamondExtraction = extractWorkspaceEdges({
    inventory: inputs.inventory,
    references: [
      ...references(),
      reference(
        "ENT-package-isolate",
        "PACKAGE_DEPENDS_ON",
        "ENT-package-core",
        "WP-ISOLATE",
        8,
      ),
      reference(
        "ENT-package-isolate",
        "SCHEMA_REF",
        "ENT-schema",
        "WP-ISOLATE",
        9,
      ),
    ],
  });
  const first = compute({
    changedNodeIds: ["ENT-package-core", "ENT-schema"],
    inputs: { inventory: inputs.inventory, extraction: diamondExtraction },
  });
  const second = compute({
    changedNodeIds: ["ENT-schema", "ENT-package-core"],
    inputs: { inventory: inputs.inventory, extraction: diamondExtraction },
  });
  const firstRow = first.impact_results.find(
    (row) => row.node_id === "ENT-package-isolate",
  );
  const secondRow = second.impact_results.find(
    (row) => row.node_id === "ENT-package-isolate",
  );
  assert.equal(firstRow.distance, 1);
  assert.equal(firstRow.origin_node_id, "ENT-package-core");
  assert.deepEqual(firstRow, secondRow);
});

test("blast_radius_test: input permutation preserves assessment hash and ID", () => {
  const one = compute({
    changedNodeIds: ["ENT-evidence", "ENT-package-core"],
    sharedResources: [
      {
        resource_id: "RES-approval",
        kind: "APPROVAL",
        node_ids: ["ENT-package-isolate", "ENT-package-core"],
      },
    ],
  });
  const two = compute({
    changedNodeIds: ["ENT-package-core", "ENT-evidence"],
    riskProfiles: profiles().reverse(),
    sharedResources: [
      {
        resource_id: "RES-approval",
        kind: "APPROVAL",
        node_ids: ["ENT-package-core", "ENT-package-isolate"],
      },
    ],
    inputs: graph({ reverseEntities: true, reverseReferences: true }),
  });
  assert.deepEqual(one, two);
  assert.equal(one.assessment_hash, two.assessment_hash);
  assert.equal(one.assessment_id, two.assessment_id);
});

test("blast_radius_test: validation, hash helper, and immutability hold", () => {
  const inputs = graph();
  const output = compute({ inputs });
  assert.deepEqual(
    validateRiskAndChangeImpact(output, inputs.inventory, inputs.extraction),
    output,
  );
  assert.equal(
    computeRiskAndChangeImpactHash(output, inputs.inventory, inputs.extraction),
    output.assessment_hash,
  );
  assert.equal(Object.isFrozen(output), true);
  assert.equal(Object.isFrozen(output.effective_edges), true);
  assert.equal(Object.isFrozen(output.risk_results[0]), true);
});

test("blast_radius_test: impact, risk, and hash tampering fail closed", () => {
  const inputs = graph();
  const output = compute({ inputs });
  for (const mutate of [
    (value) => {
      value.blast_radius_count += 1;
    },
    (value) => {
      value.risk_results[0].risk_score = 1;
    },
    (value) => {
      value.effective_edges[0].weight += 1;
    },
  ]) {
    const tampered = structuredClone(output);
    mutate(tampered);
    assert.throws(
      () => validateRiskAndChangeImpact(tampered, inputs.inventory, inputs.extraction),
      errorCode("RISK_CHANGE_IMPACT_REBUILD_MISMATCH"),
    );
  }
  const hashTamper = structuredClone(output);
  hashTamper.assessment_hash = `sha256:${"f".repeat(64)}`;
  assert.throws(
    () => validateRiskAndChangeImpact(hashTamper, inputs.inventory, inputs.extraction),
    errorCode("RISK_CHANGE_IMPACT_HASH_MISMATCH"),
  );
});

test("blast_radius_test: risk profile coverage and changed-node identity fail closed", () => {
  assert.throws(
    () => compute({ riskProfiles: profiles().slice(1) }),
    errorCode("RISK_PROFILE_COVERAGE_MISMATCH"),
  );
  assert.throws(
    () => compute({ changedNodeIds: ["ENT-missing"] }),
    errorCode("CHANGED_NODE_NOT_FOUND"),
  );
  assert.throws(
    () => compute({ changedNodeIds: ["ENT-package-core", "ENT-package-core"] }),
    errorCode("DUPLICATE_CHANGED_NODE_ID"),
  );
});

test("blast_radius_test: unknown risk and shared-resource vocabularies fail closed", () => {
  const badProfiles = profiles({ "ENT-package-app": { authority_level: "ROOT" } });
  assert.throws(() => compute({ riskProfiles: badProfiles }), errorCode("UNKNOWN_AUTHORITY_LEVEL"));
  assert.throws(
    () =>
      compute({
        sharedResources: [
          {
            resource_id: "RES-unknown",
            kind: "SOMETHING_SHARED",
            node_ids: ["ENT-package-core", "ENT-package-isolate"],
          },
        ],
      }),
    errorCode("UNKNOWN_SHARED_RESOURCE_KIND"),
  );
});

test("blast_radius_test: duplicate or malformed shared resources fail closed", () => {
  const resource = {
    resource_id: "RES-approval",
    kind: "APPROVAL",
    node_ids: ["ENT-package-core", "ENT-package-isolate"],
  };
  assert.throws(
    () => compute({ sharedResources: [resource, structuredClone(resource)] }),
    errorCode("DUPLICATE_SHARED_RESOURCE_ID"),
  );
  assert.throws(
    () => compute({ sharedResources: [{ ...resource, node_ids: ["ENT-package-core"] }] }),
    errorCode("INVALID_SHARED_RESOURCE"),
  );
});

test("blast_radius_test: hostile wrappers, accessors, and sparse arrays fail without access", () => {
  const inputs = graph();
  const candidate = {
    ...inputs,
    changed_node_ids: ["ENT-package-core"],
    risk_profiles: profiles(),
    shared_resources: [],
  };
  assert.throws(
    () => computeRiskAndChangeImpact(new Proxy(candidate, {})),
    errorCode("INVALID_RISK_CHANGE_IMPACT_INPUT"),
  );
  let invoked = false;
  const hostile = structuredClone(candidate);
  Object.defineProperty(hostile.risk_profiles[0], "authority_level", {
    enumerable: true,
    get() {
      invoked = true;
      return "NONE";
    },
  });
  assert.throws(
    () => computeRiskAndChangeImpact(hostile),
    errorCode("INVALID_RISK_PROFILE"),
  );
  assert.equal(invoked, false);
  const sparse = new Array(2);
  sparse[1] = profiles()[0];
  assert.throws(
    () => computeRiskAndChangeImpact({ ...candidate, risk_profiles: sparse }),
    errorCode("INVALID_RISK_PROFILES"),
  );
});

test("blast_radius_test: caller inputs remain unchanged", () => {
  const inputs = graph();
  const candidate = {
    ...inputs,
    changed_node_ids: ["ENT-package-core"],
    risk_profiles: profiles(),
    shared_resources: [
      {
        resource_id: "RES-credential",
        kind: "CREDENTIAL",
        node_ids: ["ENT-package-core", "ENT-package-isolate"],
      },
    ],
  };
  const before = structuredClone(candidate);
  computeRiskAndChangeImpact(candidate);
  assert.deepEqual(candidate, before);
});
