import assert from "node:assert/strict";
import test from "node:test";

import {
  EDGE_KINDS,
  WORKSPACE_EDGE_EXTRACTION_VERSION,
  WorkspaceInventoryError,
  buildWorkspaceInventory,
  canonicalizeWorkspaceMapJson,
  computeWorkspaceEdgeExtractionHash,
  extractWorkspaceEdges,
  validateWorkspaceEdgeExtraction,
} from "./index.mjs";

const HASH_A = `sha256:${"a".repeat(64)}`;
const HASH_B = `sha256:${"b".repeat(64)}`;

const errorCode = (code) => (error) =>
  error instanceof WorkspaceInventoryError && error.code === code;

const entity = (overrides = {}) => ({
  entity_id: "ENT-source",
  kind: "SOURCE_FILE",
  label: "source",
  path: "packages/app/src/index.mjs",
  locator: null,
  content_hash: HASH_A,
  owner: "PKG-app",
  source_class: "SOURCE",
  aliases: [],
  ...overrides,
});

const entities = () => [
  entity({
    entity_id: "ENT-package-app",
    kind: "PACKAGE",
    label: "application package",
    path: "packages/app/package.json",
    aliases: [{ namespace: "PACKAGE_NAME", value: "@example/app" }],
  }),
  entity({
    entity_id: "ENT-package-contracts",
    kind: "PACKAGE",
    label: "contracts package",
    path: "packages/contracts/package.json",
    owner: "PKG-contracts",
    aliases: [{ namespace: "PACKAGE_NAME", value: "@example/contracts" }],
  }),
  entity(),
  entity({
    entity_id: "ENT-dist",
    kind: "DIST_FILE",
    label: "distribution",
    path: "packages/app/dist/index.mjs",
    content_hash: HASH_B,
    source_class: "DIST",
  }),
  entity({
    entity_id: "ENT-symbol",
    kind: "CODE_SYMBOL",
    label: "exported symbol",
    path: null,
    locator: "symbol:packages/app/src/index.mjs#run",
    aliases: [{ namespace: "SYMBOL_ID", value: "SYM-run" }],
  }),
  entity({
    entity_id: "ENT-schema",
    kind: "SCHEMA",
    label: "RunSpec schema",
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
    entity_id: "ENT-api",
    kind: "API_CONTRACT",
    label: "REST v1 contract",
    path: "openapi/epistemic-foundry-v1.openapi.yaml",
    owner: "WP-C01",
  }),
  entity({
    entity_id: "ENT-test",
    kind: "TEST",
    label: "source test",
    path: "packages/app/src/index.test.mjs",
    source_class: "TEST",
  }),
  entity({
    entity_id: "ENT-workflow-a",
    kind: "WORKFLOW",
    label: "workflow A",
    path: "workflows/a.workflow.yaml",
    owner: "WP-F04",
    aliases: [{ namespace: "WORKFLOW_ID", value: "workflow_a" }],
  }),
  entity({
    entity_id: "ENT-workflow-b",
    kind: "WORKFLOW",
    label: "workflow B",
    path: "workflows/b.workflow.yaml",
    owner: "WP-F04",
    aliases: [{ namespace: "WORKFLOW_ID", value: "workflow_b" }],
  }),
  entity({
    entity_id: "ENT-wp-m01",
    kind: "WORK_PACKAGE",
    label: "M01",
    path: "manifests/development_manifest.yaml",
    owner: "PRODUCT-OWNER",
    aliases: [{ namespace: "WORK_PACKAGE_ID", value: "M01" }],
  }),
  entity({
    entity_id: "ENT-wp-c04",
    kind: "WORK_PACKAGE",
    label: "C04",
    path: null,
    locator: "manifest:work-package/C04",
    owner: "PRODUCT-OWNER",
    aliases: [{ namespace: "WORK_PACKAGE_ID", value: "C04" }],
  }),
  entity({
    entity_id: "ENT-paper-a",
    kind: "PAPER",
    label: "paper A",
    path: null,
    locator: "doi:10.1000/a",
    owner: "CORPUS-001",
    source_class: "RESEARCH",
    aliases: [{ namespace: "DOCUMENT_ID", value: "DOC-A" }],
  }),
  entity({
    entity_id: "ENT-paper-b",
    kind: "PAPER",
    label: "paper B",
    path: null,
    locator: "doi:10.1000/b",
    owner: "CORPUS-001",
    source_class: "RESEARCH",
    aliases: [{ namespace: "DOCUMENT_ID", value: "DOC-B" }],
  }),
  entity({
    entity_id: "ENT-dataset",
    kind: "DATASET",
    label: "dataset",
    path: "datasets/data.csv",
    owner: "CORPUS-001",
    source_class: "RESEARCH",
    aliases: [{ namespace: "DATASET_ID", value: "DATA-001" }],
  }),
  entity({
    entity_id: "ENT-span",
    kind: "SOURCE_SPAN",
    label: "source span",
    path: null,
    locator: "source-span:DOC-A#p1",
    owner: "CORPUS-001",
    source_class: "RESEARCH",
  }),
  entity({
    entity_id: "ENT-claim",
    kind: "CLAIM",
    label: "claim",
    path: null,
    locator: "ledger:claim/CLM-001",
    owner: "CORPUS-001",
    source_class: "RESEARCH",
    aliases: [{ namespace: "CLAIM_ID", value: "CLM-001" }],
  }),
  entity({
    entity_id: "ENT-evidence",
    kind: "EVIDENCE",
    label: "evidence",
    path: null,
    locator: "ledger:evidence/EV-001",
    owner: "CORPUS-001",
    source_class: "RESEARCH",
  }),
  entity({
    entity_id: "ENT-artifact-a",
    kind: "ARTIFACT",
    label: "artifact A",
    path: "artifacts/a.json",
    locator: "artifact://sha256/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    owner: "RUN-001",
    source_class: "ARTIFACT",
    aliases: [{ namespace: "ARTIFACT_ID", value: "ART-A" }],
  }),
  entity({
    entity_id: "ENT-artifact-b",
    kind: "ARTIFACT",
    label: "artifact B",
    path: "artifacts/b.json",
    locator: "artifact://sha256/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    owner: "RUN-001",
    source_class: "ARTIFACT",
    aliases: [{ namespace: "ARTIFACT_ID", value: "ART-B" }],
  }),
  entity({
    entity_id: "ENT-decision-a",
    kind: "DECISION",
    label: "decision A",
    path: null,
    locator: "ledger:decision/A",
    owner: "PRODUCT-OWNER",
    source_class: "ARTIFACT",
  }),
  entity({
    entity_id: "ENT-decision-b",
    kind: "DECISION",
    label: "decision B",
    path: null,
    locator: "ledger:decision/B",
    owner: "PRODUCT-OWNER",
    source_class: "ARTIFACT",
  }),
  entity({
    entity_id: "ENT-skill",
    kind: "SKILL",
    label: "mapping skill",
    path: "plugins/epistemic-foundry/skills/map/SKILL.md",
    aliases: [{ namespace: "SKILL_ID", value: "map" }],
  }),
  entity({
    entity_id: "ENT-tool",
    kind: "MCP_TOOL",
    label: "mapping tool",
    path: null,
    locator: "mcp:epistemic-foundry/map",
    aliases: [{ namespace: "MCP_TOOL_ID", value: "map_workspace" }],
  }),
  entity({
    entity_id: "ENT-hook",
    kind: "HOOK",
    label: "mapping hook",
    path: "packages/app/src/hook.mjs",
  }),
];

const makeInventory = () =>
  buildWorkspaceInventory({
    workspace_id: "WS-M01-EDGE",
    root_hash: HASH_B,
    entities: entities(),
    unreadable_paths: [],
  });

const reference = (overrides = {}) => ({
  source_entity_id: "ENT-source",
  kind: "IMPORTS",
  target_identity: { namespace: "ENTITY_ID", value: "ENT-dist" },
  target_hint: null,
  source_locator: "packages/app/src/index.mjs:1",
  owner: "PKG-app",
  ...overrides,
});

const representativeReferences = () => [
  reference(),
  reference({
    kind: "SCHEMA_REF",
    target_identity: {
      namespace: "SCHEMA_ID",
      value: "https://epistemic-foundry.local/schemas/run-spec.schema.json",
    },
    source_locator: "packages/app/src/index.mjs:2",
  }),
  reference({
    kind: "API_CONTRACT_REF",
    target_identity: { namespace: "PATH", value: "openapi/epistemic-foundry-v1.openapi.yaml" },
    source_locator: "packages/app/src/index.mjs:3",
  }),
  reference({
    source_entity_id: "ENT-test",
    kind: "TESTS",
    target_identity: { namespace: "SYMBOL_ID", value: "SYM-run" },
    source_locator: "packages/app/src/index.test.mjs:10",
  }),
  reference({
    source_entity_id: "ENT-workflow-a",
    kind: "WORKFLOW_DEPENDS_ON",
    target_identity: { namespace: "WORKFLOW_ID", value: "workflow_b" },
    source_locator: "workflows/a.workflow.yaml:nodes[1]",
    owner: "WP-F04",
  }),
  reference({
    source_entity_id: "ENT-package-app",
    kind: "PACKAGE_DEPENDS_ON",
    target_identity: { namespace: "PACKAGE_NAME", value: "@example/contracts" },
    source_locator: "packages/app/package.json:dependencies",
  }),
  reference({
    source_entity_id: "ENT-wp-m01",
    kind: "WORK_PACKAGE_DEPENDS_ON",
    target_identity: { namespace: "WORK_PACKAGE_ID", value: "C04" },
    source_locator: "manifests/development_manifest.yaml:M01.depends_on",
    owner: "PRODUCT-OWNER",
  }),
  reference({
    source_entity_id: "ENT-wp-m01",
    kind: "OWNS_CONTRACT",
    target_identity: { namespace: "ENTITY_ID", value: "ENT-schema" },
    source_locator: "manifests/development_manifest.yaml:M01.write_scope",
    owner: "PRODUCT-OWNER",
  }),
  reference({
    source_entity_id: "ENT-paper-a",
    kind: "CITES",
    target_identity: { namespace: "DOCUMENT_ID", value: "DOC-B" },
    source_locator: "doi:10.1000/a#references[1]",
    owner: "CORPUS-001",
  }),
  reference({
    source_entity_id: "ENT-paper-a",
    kind: "PUBLICATION_VERSION_OF",
    target_identity: { namespace: "DOCUMENT_ID", value: "DOC-B" },
    source_locator: "doi:10.1000/a#family",
    owner: "CORPUS-001",
  }),
  reference({
    source_entity_id: "ENT-paper-a",
    kind: "USES_DATASET",
    target_identity: { namespace: "DATASET_ID", value: "DATA-001" },
    source_locator: "doi:10.1000/a#data",
    owner: "CORPUS-001",
  }),
  reference({
    source_entity_id: "ENT-span",
    kind: "SOURCE_SPAN_OF",
    target_identity: { namespace: "DOCUMENT_ID", value: "DOC-A" },
    source_locator: "source-span:DOC-A#p1",
    owner: "CORPUS-001",
  }),
  reference({
    source_entity_id: "ENT-evidence",
    kind: "EVIDENCE_SUPPORTS_CLAIM",
    target_identity: { namespace: "CLAIM_ID", value: "CLM-001" },
    source_locator: "ledger:evidence/EV-001",
    owner: "CORPUS-001",
  }),
  reference({
    source_entity_id: "ENT-artifact-b",
    kind: "DERIVED_FROM",
    target_identity: { namespace: "ARTIFACT_ID", value: "ART-A" },
    source_locator: "artifact://sha256/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb#lineage",
    owner: "RUN-001",
  }),
  reference({
    source_entity_id: "ENT-artifact-b",
    kind: "PRODUCED_BY",
    target_identity: { namespace: "SYMBOL_ID", value: "SYM-run" },
    source_locator: "artifact://sha256/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb#receipt",
    owner: "RUN-001",
  }),
  reference({
    source_entity_id: "ENT-decision-b",
    kind: "SUPERSEDES",
    target_identity: { namespace: "ENTITY_ID", value: "ENT-decision-a" },
    source_locator: "ledger:decision/B#supersedes",
    owner: "PRODUCT-OWNER",
  }),
  reference({
    source_entity_id: "ENT-skill",
    kind: "SKILL_USES",
    target_identity: { namespace: "MCP_TOOL_ID", value: "map_workspace" },
    source_locator: "plugins/epistemic-foundry/skills/map/SKILL.md:tools",
    owner: "PKG-app",
  }),
  reference({
    source_entity_id: "ENT-hook",
    kind: "HOOK_DISPATCHES",
    target_identity: { namespace: "SYMBOL_ID", value: "SYM-run" },
    source_locator: "packages/app/src/hook.mjs:dispatch",
    owner: "PKG-app",
  }),
];

test("edge_resolution_test: code and contract references resolve through typed identity namespaces", () => {
  const extraction = extractWorkspaceEdges({
    inventory: makeInventory(),
    references: representativeReferences().slice(0, 8),
  });
  assert.equal(extraction.extraction_version, WORKSPACE_EDGE_EXTRACTION_VERSION);
  assert.equal(extraction.resolved_edges.length, 8);
  assert.equal(extraction.unresolved_edges.length, 0);
  assert.deepEqual(
    new Set(extraction.resolved_edges.map((edge) => edge.kind)),
    new Set([
      "IMPORTS",
      "SCHEMA_REF",
      "API_CONTRACT_REF",
      "TESTS",
      "WORKFLOW_DEPENDS_ON",
      "PACKAGE_DEPENDS_ON",
      "WORK_PACKAGE_DEPENDS_ON",
      "OWNS_CONTRACT",
    ]),
  );
  const imports = extraction.resolved_edges.find((edge) => edge.kind === "IMPORTS");
  assert.equal(imports.source_entity_id, "ENT-source");
  assert.equal(imports.target_entity_id, "ENT-dist");
  assert.deepEqual(imports.target_identity, { namespace: "ENTITY_ID", value: "ENT-dist" });
  assert.equal(imports.owner, "PKG-app");
});

test("edge_resolution_test: research, provenance, skill, and hook direction is retained", () => {
  const extraction = extractWorkspaceEdges({
    inventory: makeInventory(),
    references: representativeReferences().slice(8),
  });
  assert.equal(extraction.resolved_edges.length, 10);
  assert.equal(extraction.unresolved_edges.length, 0);
  const byKind = new Map(extraction.resolved_edges.map((edge) => [edge.kind, edge]));
  assert.equal(byKind.get("CITES").source_entity_id, "ENT-paper-a");
  assert.equal(byKind.get("CITES").target_entity_id, "ENT-paper-b");
  assert.equal(byKind.get("EVIDENCE_SUPPORTS_CLAIM").source_entity_id, "ENT-evidence");
  assert.equal(byKind.get("EVIDENCE_SUPPORTS_CLAIM").target_entity_id, "ENT-claim");
  assert.equal(byKind.get("DERIVED_FROM").source_entity_id, "ENT-artifact-b");
  assert.equal(byKind.get("DERIVED_FROM").target_entity_id, "ENT-artifact-a");
  assert.equal(byKind.get("SUPERSEDES").source_entity_id, "ENT-decision-b");
  assert.equal(byKind.get("SUPERSEDES").target_entity_id, "ENT-decision-a");
});

test("edge_resolution_test: missing research locators remain explicit unresolved edges", () => {
  const references = [
    reference({
      source_entity_id: "ENT-paper-a",
      kind: "CITES",
      target_identity: { namespace: "DOCUMENT_ID", value: "DOC-MISSING" },
      target_hint: "Unregistered prior work",
      source_locator: "doi:10.1000/a#references[99]",
      owner: "CORPUS-001",
    }),
    reference({
      source_entity_id: "ENT-paper-a",
      kind: "USES_DATASET",
      target_identity: null,
      target_hint: "Repository named in prose but no immutable locator was supplied",
      source_locator: "doi:10.1000/a#data-availability",
      owner: "CORPUS-001",
    }),
  ];
  const extraction = extractWorkspaceEdges({ inventory: makeInventory(), references });
  assert.equal(extraction.resolved_edges.length, 0);
  assert.equal(extraction.unresolved_edges.length, 2);
  assert.deepEqual(
    extraction.unresolved_edges.map((edge) => edge.unresolved_reason).sort(),
    ["MISSING_TARGET_LOCATOR", "TARGET_NOT_FOUND"],
  );
  assert.ok(extraction.unresolved_edges.every((edge) => edge.target_hint !== null));
  assert.equal(extraction.edge_counts.unresolved, 2);
  assert.equal(extraction.edge_counts.total, 2);
});

test("edge_resolution_test: set permutation preserves edge hashes, IDs, and partition order", () => {
  const inventory = makeInventory();
  const references = representativeReferences();
  const first = extractWorkspaceEdges({ inventory, references });
  const second = extractWorkspaceEdges({ inventory, references: [...references].reverse() });
  assert.equal(canonicalizeWorkspaceMapJson(first), canonicalizeWorkspaceMapJson(second));
  assert.equal(first.extraction_hash, second.extraction_hash);
  assert.equal(first.extraction_id, second.extraction_id);
  assert.equal(computeWorkspaceEdgeExtractionHash(first, inventory), first.extraction_hash);
  assert.ok(first.resolved_edges.every((edge) => edge.resolution === "RESOLVED"));
  assert.ok(first.unresolved_edges.every((edge) => edge.resolution === "UNRESOLVED"));
});

test("edge_resolution_test: extraction is pure, deeply immutable, and bound to inventory identity", () => {
  const inventory = makeInventory();
  const references = representativeReferences();
  const beforeInventory = structuredClone(inventory);
  const beforeReferences = structuredClone(references);
  const extraction = extractWorkspaceEdges({ inventory, references });
  assert.deepEqual(inventory, beforeInventory);
  assert.deepEqual(references, beforeReferences);
  assert.equal(Object.isFrozen(extraction), true);
  assert.equal(Object.isFrozen(extraction.resolved_edges), true);
  assert.equal(Object.isFrozen(extraction.resolved_edges[0]), true);

  const otherInventory = buildWorkspaceInventory({
    workspace_id: "WS-M01-OTHER",
    root_hash: HASH_A,
    entities: entities(),
    unreadable_paths: [],
  });
  assert.throws(
    () => validateWorkspaceEdgeExtraction(extraction, otherInventory),
    errorCode("EDGE_INVENTORY_BINDING_MISMATCH"),
  );
  assert.deepEqual(validateWorkspaceEdgeExtraction(extraction, inventory), extraction);
});

test("edge_resolution_test: edge content, count, hash, ID, and partition tampering is detected", () => {
  const inventory = makeInventory();
  const extraction = extractWorkspaceEdges({ inventory, references: representativeReferences() });
  const edgeTamper = structuredClone(extraction);
  edgeTamper.resolved_edges[0].source_locator = "tampered:1";
  assert.throws(
    () => validateWorkspaceEdgeExtraction(edgeTamper, inventory),
    errorCode("EDGE_EXTRACTION_HASH_MISMATCH"),
  );

  const countTamper = structuredClone(extraction);
  countTamper.edge_counts.total += 1;
  assert.throws(
    () => validateWorkspaceEdgeExtraction(countTamper, inventory),
    errorCode("EDGE_EXTRACTION_REBUILD_MISMATCH"),
  );

  const idTamper = structuredClone(extraction);
  idTamper.extraction_id = `WEDGESET-${"f".repeat(64)}`;
  assert.throws(
    () => validateWorkspaceEdgeExtraction(idTamper, inventory),
    errorCode("EDGE_EXTRACTION_ID_MISMATCH"),
  );

  const partitionTamper = structuredClone(extraction);
  partitionTamper.unresolved_edges.push(partitionTamper.resolved_edges.pop());
  assert.throws(
    () => validateWorkspaceEdgeExtraction(partitionTamper, inventory),
    errorCode("EDGE_EXTRACTION_REBUILD_MISMATCH"),
  );
});

test("edge_resolution_test: absent sources, owner mismatch, and self edges fail closed", () => {
  const inventory = makeInventory();
  assert.throws(
    () =>
      extractWorkspaceEdges({
        inventory,
        references: [reference({ source_entity_id: "ENT-missing" })],
      }),
    errorCode("EDGE_SOURCE_NOT_FOUND"),
  );
  assert.throws(
    () => extractWorkspaceEdges({ inventory, references: [reference({ owner: "OTHER" })] }),
    errorCode("EDGE_OWNER_MISMATCH"),
  );
  assert.throws(
    () =>
      extractWorkspaceEdges({
        inventory,
        references: [
          reference({
            target_identity: { namespace: "ENTITY_ID", value: "ENT-source" },
          }),
        ],
      }),
    errorCode("SELF_EDGE_DENIED"),
  );
});

test("edge_resolution_test: invalid source or target semantics fail closed", () => {
  const inventory = makeInventory();
  assert.throws(
    () =>
      extractWorkspaceEdges({
        inventory,
        references: [
          reference({
            source_entity_id: "ENT-paper-a",
            kind: "PACKAGE_DEPENDS_ON",
            target_identity: { namespace: "PACKAGE_NAME", value: "@example/contracts" },
            owner: "CORPUS-001",
          }),
        ],
      }),
    errorCode("EDGE_SOURCE_KIND_MISMATCH"),
  );
  assert.throws(
    () =>
      extractWorkspaceEdges({
        inventory,
        references: [
          reference({
            kind: "SCHEMA_REF",
            target_identity: { namespace: "DOCUMENT_ID", value: "DOC-A" },
          }),
        ],
      }),
    errorCode("EDGE_TARGET_KIND_MISMATCH"),
  );
  assert.throws(
    () =>
      extractWorkspaceEdges({
        inventory,
        references: [
          reference({
            source_entity_id: "ENT-decision-b",
            kind: "SUPERSEDES",
            target_identity: { namespace: "ARTIFACT_ID", value: "ART-A" },
            owner: "PRODUCT-OWNER",
          }),
        ],
      }),
    errorCode("EDGE_TARGET_KIND_MISMATCH"),
  );
});

test("edge_resolution_test: dependency edges cannot omit typed target identity or use unknown vocabulary", () => {
  const inventory = makeInventory();
  assert.throws(
    () =>
      extractWorkspaceEdges({
        inventory,
        references: [reference({ target_identity: null, target_hint: "maybe another module" })],
      }),
    errorCode("MISSING_TARGET_IDENTITY_DENIED"),
  );
  assert.throws(
    () =>
      extractWorkspaceEdges({
        inventory,
        references: [reference({ kind: "DEPENDS" })],
      }),
    errorCode("UNKNOWN_EDGE_KIND"),
  );
  assert.throws(
    () =>
      extractWorkspaceEdges({
        inventory,
        references: [
          reference({ target_identity: { namespace: "FREE_TEXT", value: "target" } }),
        ],
      }),
    errorCode("UNKNOWN_IDENTITY_NAMESPACE"),
  );
});

test("edge_resolution_test: duplicate references and hostile wrappers fail without accessor execution", () => {
  const inventory = makeInventory();
  const duplicate = reference();
  assert.throws(
    () => extractWorkspaceEdges({ inventory, references: [duplicate, structuredClone(duplicate)] }),
    errorCode("DUPLICATE_EDGE_REFERENCE"),
  );
  let getterCalls = 0;
  const accessor = reference();
  Object.defineProperty(accessor, "kind", {
    enumerable: true,
    get() {
      getterCalls += 1;
      return "IMPORTS";
    },
  });
  assert.throws(
    () => extractWorkspaceEdges({ inventory, references: [accessor] }),
    errorCode("INVALID_EDGE_REFERENCE"),
  );
  assert.equal(getterCalls, 0);
  assert.throws(
    () => extractWorkspaceEdges(new Proxy({ inventory, references: [] }, {})),
    errorCode("INVALID_EDGE_EXTRACTION_INPUT"),
  );
  const sparse = new Array(2);
  sparse[1] = reference();
  assert.throws(
    () => extractWorkspaceEdges({ inventory, references: sparse }),
    errorCode("INVALID_EDGE_EXTRACTION_INPUT"),
  );
});

test("edge_resolution_test: edge vocabulary is closed and contains every canonical layer relation", () => {
  assert.equal(new Set(EDGE_KINDS).size, EDGE_KINDS.length);
  for (const required of [
    "IMPORTS",
    "SCHEMA_REF",
    "TESTS",
    "CITES",
    "USES_DATASET",
    "EVIDENCE_SUPPORTS_CLAIM",
    "DERIVED_FROM",
    "PRODUCED_BY",
    "SUPERSEDES",
  ]) {
    assert.ok(EDGE_KINDS.includes(required), required);
  }
  assert.ok(!EDGE_KINDS.includes("RANKS_HIGHER_THAN"));
});
