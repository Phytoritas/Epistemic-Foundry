import assert from "node:assert/strict";
import test from "node:test";

import {
  ENTITY_KINDS,
  ENTITY_LAYERS,
  SOURCE_CLASSES,
  WORKSPACE_INVENTORY_VERSION,
  WorkspaceInventoryError,
  buildWorkspaceInventory,
  canonicalizeWorkspaceMapJson,
  computeWorkspaceInventoryHash,
  validateWorkspaceInventory,
} from "./index.mjs";

const HASH_A = `sha256:${"a".repeat(64)}`;
const HASH_B = `sha256:${"b".repeat(64)}`;
const HASH_C = `sha256:${"c".repeat(64)}`;

const errorCode = (code) => (error) =>
  error instanceof WorkspaceInventoryError && error.code === code;

const entity = (overrides = {}) => ({
  entity_id: "ENT-source",
  kind: "SOURCE_FILE",
  label: "source module",
  path: "packages/example/src/index.mjs",
  locator: null,
  content_hash: HASH_A,
  owner: "PKG-example",
  source_class: "SOURCE",
  aliases: [],
  ...overrides,
});

const representativeEntities = () => [
  entity({
    entity_id: "ENT-package",
    kind: "PACKAGE",
    label: "example package",
    path: "packages/example/package.json",
    aliases: [{ namespace: "PACKAGE_NAME", value: "@example/core" }],
  }),
  entity(),
  entity({
    entity_id: "ENT-dist",
    kind: "DIST_FILE",
    label: "compiled distribution",
    path: "packages/example/dist/index.mjs",
    content_hash: HASH_B,
    source_class: "DIST",
  }),
  entity({
    entity_id: "ENT-generated",
    kind: "GENERATED_FILE",
    label: "generated contracts",
    path: "packages/contracts/src/generated/models.mjs",
    owner: "PKG-contracts",
    source_class: "GENERATED",
  }),
  entity({
    entity_id: "ENT-vendor",
    kind: "VENDOR_FILE",
    label: "vendored parser fixture",
    path: "vendor/parser/index.js",
    owner: "VENDOR-parser",
    source_class: "VENDOR",
  }),
  entity({
    entity_id: "ENT-test",
    kind: "TEST",
    label: "inventory test",
    path: "packages/example/src/index.test.mjs",
    source_class: "TEST",
    aliases: [{ namespace: "TEST_ID", value: "TEST-example-index" }],
  }),
  entity({
    entity_id: "ENT-schema",
    kind: "SCHEMA",
    label: "example schema",
    path: "schemas/example.schema.json",
    owner: "WP-C01",
    aliases: [
      {
        namespace: "SCHEMA_ID",
        value: "https://epistemic-foundry.local/schemas/example.schema.json",
      },
    ],
  }),
  entity({
    entity_id: "ENT-workflow",
    kind: "WORKFLOW",
    label: "example workflow",
    path: "workflows/example.workflow.yaml",
    owner: "WP-F04",
    aliases: [{ namespace: "WORKFLOW_ID", value: "example_workflow" }],
  }),
  entity({
    entity_id: "ENT-work-package",
    kind: "WORK_PACKAGE",
    label: "M01 package declaration",
    path: "manifests/development_manifest.yaml",
    owner: "PRODUCT-OWNER",
    aliases: [{ namespace: "WORK_PACKAGE_ID", value: "M01" }],
  }),
  entity({
    entity_id: "ENT-paper",
    kind: "PAPER",
    label: "registered paper",
    path: null,
    locator: "doi:10.1000/example",
    owner: "CORPUS-001",
    source_class: "RESEARCH",
    aliases: [{ namespace: "DOCUMENT_ID", value: "DOC-001" }],
  }),
  entity({
    entity_id: "ENT-dataset",
    kind: "DATASET",
    label: "registered dataset",
    path: "datasets/example.csv",
    locator: "artifact://sha256/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    owner: "CORPUS-001",
    source_class: "RESEARCH",
    aliases: [{ namespace: "DATASET_ID", value: "DATASET-001" }],
  }),
  entity({
    entity_id: "ENT-claim",
    kind: "CLAIM",
    label: "bounded claim",
    path: null,
    locator: "ledger:claim/CLM-001",
    owner: "CORPUS-001",
    source_class: "RESEARCH",
    aliases: [{ namespace: "CLAIM_ID", value: "CLM-001" }],
  }),
  entity({
    entity_id: "ENT-evidence",
    kind: "EVIDENCE",
    label: "source-linked evidence",
    path: null,
    locator: "ledger:evidence/EV-001",
    owner: "CORPUS-001",
    source_class: "RESEARCH",
    aliases: [{ namespace: "EVIDENCE_ID", value: "EV-001" }],
  }),
  entity({
    entity_id: "ENT-artifact",
    kind: "ARTIFACT",
    label: "immutable result artifact",
    path: "artifacts/sha256/aa/result.json",
    locator: "artifact://sha256/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    content_hash: HASH_B,
    owner: "RUN-001",
    source_class: "ARTIFACT",
    aliases: [{ namespace: "ARTIFACT_ID", value: "ART-001" }],
  }),
  entity({
    entity_id: "ENT-decision",
    kind: "DECISION",
    label: "human decision",
    path: null,
    locator: "ledger:decision/HD-001",
    content_hash: HASH_C,
    owner: "PRODUCT-OWNER",
    source_class: "ARTIFACT",
    aliases: [{ namespace: "DECISION_ID", value: "HD-001" }],
  }),
];

const inventoryInput = (overrides = {}) => ({
  workspace_id: "WS-M01-001",
  root_hash: HASH_C,
  entities: representativeEntities(),
  unreadable_paths: [
    { path: "restricted/licensed-source.pdf", error_code: "ACCESS_DENIED" },
  ],
  ...overrides,
});

test("map_inventory_test: code, research, and artifact layers are indexed with explicit source classes", () => {
  const inventory = buildWorkspaceInventory(inventoryInput());
  assert.equal(inventory.inventory_version, WORKSPACE_INVENTORY_VERSION);
  assert.deepEqual(
    Object.keys(inventory.layer_counts).toSorted(),
    [...ENTITY_LAYERS].toSorted(),
  );
  assert.equal(inventory.layer_counts.CODE, 9);
  assert.equal(inventory.layer_counts.RESEARCH, 4);
  assert.equal(inventory.layer_counts.ARTIFACT, 2);
  assert.equal(inventory.source_class_counts.SOURCE, 5);
  assert.equal(inventory.source_class_counts.DIST, 1);
  assert.equal(inventory.source_class_counts.GENERATED, 1);
  assert.equal(inventory.source_class_counts.VENDOR, 1);
  assert.equal(inventory.source_class_counts.TEST, 1);
  assert.equal(inventory.source_class_counts.RESEARCH, 4);
  assert.equal(inventory.source_class_counts.ARTIFACT, 2);
  assert.deepEqual(inventory.unreadable_paths, [
    { error_code: "ACCESS_DENIED", path: "restricted/licensed-source.pdf" },
  ]);
  assert.equal(inventory.entity_count, 15);
  assert.match(inventory.inventory_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(inventory.inventory_id, `WINV-${inventory.inventory_hash.slice(7)}`);
});

test("map_inventory_test: source, dist, generated, vendor, and test identities remain distinct", () => {
  const inventory = buildWorkspaceInventory(inventoryInput());
  const indexed = new Map(inventory.entities.map((entry) => [entry.entity_id, entry]));
  assert.deepEqual(
    ["ENT-source", "ENT-dist", "ENT-generated", "ENT-vendor", "ENT-test"].map((id) => [
      indexed.get(id).kind,
      indexed.get(id).source_class,
      indexed.get(id).path,
    ]),
    [
      ["SOURCE_FILE", "SOURCE", "packages/example/src/index.mjs"],
      ["DIST_FILE", "DIST", "packages/example/dist/index.mjs"],
      ["GENERATED_FILE", "GENERATED", "packages/contracts/src/generated/models.mjs"],
      ["VENDOR_FILE", "VENDOR", "vendor/parser/index.js"],
      ["TEST", "TEST", "packages/example/src/index.test.mjs"],
    ],
  );
});

test("map_inventory_test: input permutation produces byte-identical deterministic inventory", () => {
  const input = inventoryInput();
  const first = buildWorkspaceInventory(input);
  const second = buildWorkspaceInventory({
    ...input,
    entities: [...input.entities].reverse(),
    unreadable_paths: [...input.unreadable_paths].reverse(),
  });
  assert.equal(canonicalizeWorkspaceMapJson(first), canonicalizeWorkspaceMapJson(second));
  assert.equal(first.inventory_hash, second.inventory_hash);
  assert.equal(first.inventory_id, second.inventory_id);
  assert.equal(computeWorkspaceInventoryHash(first), first.inventory_hash);
});

test("map_inventory_test: the mapper is pure and returns deeply immutable data", () => {
  const input = inventoryInput();
  const before = structuredClone(input);
  const inventory = buildWorkspaceInventory(input);
  assert.deepEqual(input, before);
  assert.equal(Object.isFrozen(inventory), true);
  assert.equal(Object.isFrozen(inventory.entities), true);
  assert.equal(Object.isFrozen(inventory.entities[0]), true);
  assert.equal(Object.isFrozen(inventory.entities.find((entry) => entry.aliases.length > 0).aliases), true);
  assert.equal(Object.isFrozen(inventory.unreadable_paths), true);
});

test("map_inventory_test: canonical validation detects entity, count, hash, and ID tampering", () => {
  const inventory = buildWorkspaceInventory(inventoryInput());
  const contentTamper = structuredClone(inventory);
  contentTamper.entities[0].label = "tampered";
  assert.throws(() => validateWorkspaceInventory(contentTamper), errorCode("INVENTORY_HASH_MISMATCH"));

  const countTamper = structuredClone(inventory);
  countTamper.layer_counts.CODE += 1;
  assert.throws(() => validateWorkspaceInventory(countTamper), errorCode("INVENTORY_REBUILD_MISMATCH"));

  const idTamper = structuredClone(inventory);
  idTamper.inventory_id = `WINV-${"f".repeat(64)}`;
  assert.throws(() => validateWorkspaceInventory(idTamper), errorCode("INVENTORY_ID_MISMATCH"));
  assert.deepEqual(validateWorkspaceInventory(inventory), inventory);
});

test("map_inventory_test: duplicate entity IDs, paths, and aliases fail closed", () => {
  const duplicateId = [entity(), entity({ path: "packages/other.mjs" })];
  assert.throws(
    () => buildWorkspaceInventory(inventoryInput({ entities: duplicateId })),
    errorCode("DUPLICATE_ENTITY_ID"),
  );

  const duplicatePath = [
    entity(),
    entity({ entity_id: "ENT-other", path: "PACKAGES/EXAMPLE/SRC/INDEX.MJS" }),
  ];
  assert.throws(
    () => buildWorkspaceInventory(inventoryInput({ entities: duplicatePath })),
    errorCode("DUPLICATE_ENTITY_PATH"),
  );

  const duplicateAlias = [
    entity({ aliases: [{ namespace: "SYMBOL_ID", value: "SYM-shared" }] }),
    entity({
      entity_id: "ENT-other",
      path: "packages/example/src/other.mjs",
      aliases: [{ namespace: "SYMBOL_ID", value: "SYM-shared" }],
    }),
  ];
  assert.throws(
    () => buildWorkspaceInventory(inventoryInput({ entities: duplicateAlias })),
    errorCode("DUPLICATE_ENTITY_IDENTITY"),
  );
});

test("map_inventory_test: portable paths reject traversal, absolute, drive, and separator variants", () => {
  for (const maliciousPath of [
    "../outside.mjs",
    "/absolute/file.mjs",
    "C:/absolute/file.mjs",
    "packages\\example\\index.mjs",
    "packages//example/index.mjs",
    "packages/CON/file.mjs",
    "packages/example./file.mjs",
  ]) {
    assert.throws(
      () => buildWorkspaceInventory(inventoryInput({ entities: [entity({ path: maliciousPath })] })),
      errorCode("INVALID_PORTABLE_PATH"),
      maliciousPath,
    );
  }
});

test("map_inventory_test: unknown vocabularies and source-class mismatches fail closed", () => {
  assert.throws(
    () => buildWorkspaceInventory(inventoryInput({ entities: [entity({ kind: "MODULE" })] })),
    errorCode("UNKNOWN_ENTITY_KIND"),
  );
  assert.throws(
    () => buildWorkspaceInventory(inventoryInput({ entities: [entity({ source_class: "CACHE" })] })),
    errorCode("UNKNOWN_SOURCE_CLASS"),
  );
  assert.throws(
    () => buildWorkspaceInventory(inventoryInput({ entities: [entity({ source_class: "DIST" })] })),
    errorCode("SOURCE_CLASS_KIND_MISMATCH"),
  );
  assert.throws(
    () =>
      buildWorkspaceInventory(
        inventoryInput({
          entities: [entity({ kind: "PAPER", source_class: "SOURCE" })],
        }),
      ),
    errorCode("SOURCE_CLASS_LAYER_MISMATCH"),
  );
});

test("map_inventory_test: location, locator, hash, and unreadable-path contracts are explicit", () => {
  assert.throws(
    () => buildWorkspaceInventory(inventoryInput({ entities: [entity({ path: null })] })),
    errorCode("ENTITY_LOCATION_MISSING"),
  );
  assert.throws(
    () => buildWorkspaceInventory(inventoryInput({ entities: [entity({ locator: "not a locator" })] })),
    errorCode("INVALID_LOCATOR"),
  );
  assert.throws(
    () => buildWorkspaceInventory(inventoryInput({ entities: [entity({ content_hash: "sha256:bad" })] })),
    errorCode("INVALID_HASH"),
  );
  assert.throws(
    () =>
      buildWorkspaceInventory(
        inventoryInput({ unreadable_paths: [{ path: "private/file", error_code: "denied" }] }),
      ),
    errorCode("INVALID_UNREADABLE_PATH"),
  );
  assert.throws(
    () =>
      buildWorkspaceInventory(
        inventoryInput({
          entities: [entity()],
          unreadable_paths: [
            { path: "packages/example/src/index.mjs", error_code: "ACCESS_DENIED" },
          ],
        }),
      ),
    errorCode("READABILITY_CONFLICT"),
  );
});

test("map_inventory_test: hostile getters, Proxies, sparse arrays, and extra fields are rejected without access", () => {
  let getterCalls = 0;
  const accessor = entity();
  Object.defineProperty(accessor, "label", {
    enumerable: true,
    get() {
      getterCalls += 1;
      return "stolen";
    },
  });
  assert.throws(
    () => buildWorkspaceInventory(inventoryInput({ entities: [accessor] })),
    errorCode("INVALID_ENTITY"),
  );
  assert.equal(getterCalls, 0);
  assert.throws(
    () => buildWorkspaceInventory(new Proxy(inventoryInput(), {})),
    errorCode("INVALID_INVENTORY_INPUT"),
  );
  const sparse = new Array(2);
  sparse[1] = entity();
  assert.throws(
    () => buildWorkspaceInventory(inventoryInput({ entities: sparse })),
    errorCode("INVALID_INVENTORY_INPUT"),
  );
  assert.throws(
    () => buildWorkspaceInventory({ ...inventoryInput(), ranking: "pagerank" }),
    errorCode("INVALID_INVENTORY_INPUT"),
  );

  const cyclicCanonicalValue = {};
  cyclicCanonicalValue.self = cyclicCanonicalValue;
  assert.throws(
    () => canonicalizeWorkspaceMapJson(cyclicCanonicalValue),
    errorCode("NON_CANONICAL_JSON"),
  );

  const cyclicKind = {};
  cyclicKind.self = cyclicKind;
  assert.throws(
    () => buildWorkspaceInventory(inventoryInput({ entities: [entity({ kind: cyclicKind })] })),
    errorCode("UNKNOWN_ENTITY_KIND"),
  );
});

test("map_inventory_test: canonical vocabularies are closed, unique, and mapped", () => {
  assert.equal(new Set(ENTITY_KINDS).size, ENTITY_KINDS.length);
  assert.equal(new Set(SOURCE_CLASSES).size, SOURCE_CLASSES.length);
  assert.equal(new Set(ENTITY_LAYERS).size, ENTITY_LAYERS.length);
  assert.deepEqual(ENTITY_LAYERS, ["CODE", "RESEARCH", "ARTIFACT"]);
  assert.ok(ENTITY_KINDS.includes("SCHEMA"));
  assert.ok(ENTITY_KINDS.includes("PAPER"));
  assert.ok(ENTITY_KINDS.includes("ARTIFACT"));
  assert.ok(!ENTITY_KINDS.includes("RANKING"));
});
