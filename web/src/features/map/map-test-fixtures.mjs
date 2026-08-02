import {
  buildWorkspaceInventory,
  extractWorkspaceEdges,
} from "../../../../packages/workspace-map/src/inventory/index.mjs";
import { computeBaselineCentrality } from "../../../../packages/workspace-map/src/ranking/baseline/index.mjs";
import {
  computeQueryPersonalization,
  computeRiskAndChangeImpact,
} from "../../../../packages/workspace-map/src/ranking/query/index.mjs";

const HASH = `sha256:${"d".repeat(64)}`;
const PARAMETERS = Object.freeze({ alpha: 0.85, max_iterations: 500, tolerance: 1e-13 });

const entity = (overrides = {}) => ({
  entity_id: "ENT-package-app",
  kind: "PACKAGE",
  label: "Application package",
  path: "packages/app/package.json",
  locator: null,
  content_hash: HASH,
  owner: "WP-APP",
  source_class: "SOURCE",
  aliases: [{ namespace: "PACKAGE_NAME", value: "@example/app" }],
  ...overrides,
});

const entities = (hostileLabel) => [
  entity(),
  entity({
    entity_id: "ENT-package-core",
    label: hostileLabel ?? "Core package",
    path: "packages/core/package.json",
    owner: "WP-CORE",
    aliases: [{ namespace: "PACKAGE_NAME", value: "@example/core" }],
  }),
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
    entity_id: "ENT-workflow",
    kind: "WORKFLOW",
    label: "Evolution workflow",
    path: "workflows/evolution_chamber.workflow.yaml",
    owner: "WP-F04",
    aliases: [{ namespace: "WORKFLOW_ID", value: "evolution_chamber" }],
  }),
];

const references = (hostileHint) => [
  {
    source_entity_id: "ENT-package-app",
    kind: "PACKAGE_DEPENDS_ON",
    target_identity: { namespace: "ENTITY_ID", value: "ENT-package-core" },
    target_hint: null,
    source_locator: "packages/app/package.json:dependencies",
    owner: "WP-APP",
  },
  {
    source_entity_id: "ENT-package-app",
    kind: "SCHEMA_REF",
    target_identity: { namespace: "ENTITY_ID", value: "ENT-schema-run-spec" },
    target_hint: null,
    source_locator: "packages/app/src/run.mjs:1",
    owner: "WP-APP",
  },
  {
    source_entity_id: "ENT-workflow",
    kind: "WORKFLOW_DEPENDS_ON",
    target_identity: { namespace: "WORKFLOW_ID", value: "missing_backend_workflow" },
    target_hint: hostileHint ?? "Plugin workflow is unavailable in this bounded inventory",
    source_locator: "workflows/evolution_chamber.workflow.yaml:depends_on",
    owner: "WP-F04",
  },
];

const riskProfiles = () => [
  {
    node_id: "ENT-package-app",
    authority_level: "LOCAL",
    write_scope_level: "BOUNDED",
    data_sensitivity: "INTERNAL",
    mutable_contract: false,
  },
  {
    node_id: "ENT-package-core",
    authority_level: "SHARED",
    write_scope_level: "SHARED",
    data_sensitivity: "INTERNAL",
    mutable_contract: false,
  },
  {
    node_id: "ENT-schema-run-spec",
    authority_level: "CANONICAL",
    write_scope_level: "GLOBAL",
    data_sensitivity: "CONFIDENTIAL",
    mutable_contract: true,
  },
  {
    node_id: "ENT-workflow",
    authority_level: "SHARED",
    write_scope_level: "BOUNDED",
    data_sensitivity: "PUBLIC",
    mutable_contract: true,
  },
];

export function workspaceMapFixture({
  query = "Evolution Run Spec",
  hostileLabel = null,
  hostileHint = null,
  reverse = false,
} = {}) {
  const entityRows = entities(hostileLabel);
  const referenceRows = references(hostileHint);
  const inventory = buildWorkspaceInventory({
    workspace_id: "WS-M04-map-ui",
    root_hash: HASH,
    entities: reverse ? entityRows.reverse() : entityRows,
    unreadable_paths: [
      { path: "restricted/licensed-corpus.pdf", error_code: "ACCESS_DENIED" },
    ],
  });
  const extraction = extractWorkspaceEdges({
    inventory,
    references: reverse ? referenceRows.reverse() : referenceRows,
  });
  const baselineCentrality = computeBaselineCentrality({
    inventory,
    extraction,
    parameters: PARAMETERS,
  });
  const queryPersonalization = computeQueryPersonalization({
    inventory,
    extraction,
    query,
  });
  const riskChangeImpact = computeRiskAndChangeImpact({
    inventory,
    extraction,
    changed_node_ids: ["ENT-package-core"],
    risk_profiles: reverse ? riskProfiles().reverse() : riskProfiles(),
    shared_resources: [],
  });
  return {
    inventory,
    extraction,
    baseline_centrality: baselineCentrality,
    query_personalization: queryPersonalization,
    risk_change_impact: riskChangeImpact,
  };
}

