/**
 * M03 deterministic risk and change-impact projection.
 *
 * Intrinsic risk is computed from explicit authority, write-scope, data
 * sensitivity, and mutable-contract metadata. Blast radius is a separate
 * graph traversal. Shared resources are materialized as bidirectional typed
 * edges. Unresolved M01 edges remain visible but never propagate impact.
 */

import {
  EDGE_KINDS,
  validateWorkspaceEdgeExtraction,
  validateWorkspaceInventory,
} from "../../inventory/index.mjs";
import {
  SHA256_PATTERN,
  assertUniqueStrings,
  canonicalClone,
  canonicalizeQueryRankingJson,
  compareUtf8,
  fail,
  readDataProperty,
  readDenseArray,
  requireBoolean,
  requireEnum,
  requireIdentifier,
  requirePlainDataObject,
  roundedScore,
  sha256CanonicalJson,
} from "./query-ranking-common.mjs";

export const RISK_CHANGE_IMPACT_VERSION = "4.0.0-m03.1";
export const RISK_CHANGE_IMPACT_ALGORITHM =
  "TYPED_RISK_PLUS_DETERMINISTIC_IMPACT_TRAVERSAL";

export const IMPACT_EDGE_DIRECTION_BY_KIND = Object.freeze({
  IMPORTS: "TARGET_TO_SOURCE",
  SCHEMA_REF: "TARGET_TO_SOURCE",
  API_CONTRACT_REF: "TARGET_TO_SOURCE",
  TESTS: "TARGET_TO_SOURCE",
  WORKFLOW_DEPENDS_ON: "TARGET_TO_SOURCE",
  PACKAGE_DEPENDS_ON: "TARGET_TO_SOURCE",
  WORK_PACKAGE_DEPENDS_ON: "TARGET_TO_SOURCE",
  OWNS_CONTRACT: "BIDIRECTIONAL",
  CITES: "TARGET_TO_SOURCE",
  PUBLICATION_VERSION_OF: "TARGET_TO_SOURCE",
  USES_DATASET: "TARGET_TO_SOURCE",
  SOURCE_SPAN_OF: "TARGET_TO_SOURCE",
  EVIDENCE_SUPPORTS_CLAIM: "SOURCE_TO_TARGET",
  EVIDENCE_COUNTERS_CLAIM: "SOURCE_TO_TARGET",
  DERIVED_FROM: "TARGET_TO_SOURCE",
  PRODUCED_BY: "TARGET_TO_SOURCE",
  SUPERSEDES: "TARGET_TO_SOURCE",
  SKILL_USES: "TARGET_TO_SOURCE",
  HOOK_DISPATCHES: "TARGET_TO_SOURCE",
});

export const SHARED_RESOURCE_KINDS = Object.freeze([
  "SHARED_WRITE",
  "MUTABLE_CONTRACT",
  "QUOTA",
  "APPROVAL",
  "CREDENTIAL",
  "PRIVACY_BOUNDARY",
  "MIGRATION",
  "EXCLUSIVE_RESOURCE",
]);

export const SHARED_RESOURCE_WEIGHTS = Object.freeze({
  SHARED_WRITE: 4,
  MUTABLE_CONTRACT: 5,
  QUOTA: 2,
  APPROVAL: 3,
  CREDENTIAL: 5,
  PRIVACY_BOUNDARY: 5,
  MIGRATION: 4,
  EXCLUSIVE_RESOURCE: 4,
});

export const RISK_COMPONENT_WEIGHTS = Object.freeze({
  authority_level: 4,
  write_scope_level: 3,
  data_sensitivity: 4,
  mutable_contract: 4,
});

const AUTHORITY_LEVELS = Object.freeze({ NONE: 0, LOCAL: 1, SHARED: 2, CANONICAL: 3 });
const WRITE_SCOPE_LEVELS = Object.freeze({
  READ_ONLY: 0,
  BOUNDED: 1,
  SHARED: 2,
  GLOBAL: 3,
});
const DATA_SENSITIVITY_LEVELS = Object.freeze({
  PUBLIC: 0,
  INTERNAL: 1,
  CONFIDENTIAL: 2,
  RESTRICTED: 3,
});
const AUTHORITY_SET = new Set(Object.keys(AUTHORITY_LEVELS));
const WRITE_SCOPE_SET = new Set(Object.keys(WRITE_SCOPE_LEVELS));
const DATA_SENSITIVITY_SET = new Set(Object.keys(DATA_SENSITIVITY_LEVELS));
const SHARED_RESOURCE_SET = new Set(SHARED_RESOURCE_KINDS);

const INPUT_FIELDS = Object.freeze([
  "inventory",
  "extraction",
  "changed_node_ids",
  "risk_profiles",
  "shared_resources",
]);
const PROFILE_FIELDS = Object.freeze([
  "node_id",
  "authority_level",
  "write_scope_level",
  "data_sensitivity",
  "mutable_contract",
]);
const SHARED_RESOURCE_FIELDS = Object.freeze(["resource_id", "kind", "node_ids"]);
const ALGORITHM_INPUT_FIELDS = Object.freeze([
  "node_count",
  "changed_node_ids",
  "risk_profiles",
  "shared_resources",
  "resolved_edge_count",
  "unresolved_edge_count",
]);
const OUTPUT_FIELDS = Object.freeze([
  "assessment_id",
  "assessment_version",
  "inventory_id",
  "inventory_hash",
  "extraction_id",
  "extraction_hash",
  "algorithm",
  "algorithm_inputs",
  "effective_edges",
  "excluded_unresolved_edge_ids",
  "risk_results",
  "risk_order",
  "impact_results",
  "impact_order",
  "affected_node_ids",
  "unaffected_node_ids",
  "blast_radius_count",
  "assessment_hash",
]);

const assertDirectionTableComplete = () => {
  const expected = [...EDGE_KINDS].sort(compareUtf8);
  const observed = Object.keys(IMPACT_EDGE_DIRECTION_BY_KIND).sort(compareUtf8);
  if (canonicalizeQueryRankingJson(expected) !== canonicalizeQueryRankingJson(observed)) {
    fail("IMPACT_DIRECTION_TABLE_INCOMPLETE", "every M01 edge kind requires one impact rule", {
      expected,
      observed,
    });
  }
};

assertDirectionTableComplete();

const normalizeChangedNodeIds = (candidate, nodeIds) => {
  const values = readDenseArray(
    candidate,
    "changed_node_ids",
    "INVALID_CHANGED_NODE_IDS",
  ).map((value, index) =>
    requireIdentifier(value, `changed_node_ids[${index}]`, "INVALID_CHANGED_NODE_IDS"),
  );
  assertUniqueStrings(values, "changed_node_ids", "DUPLICATE_CHANGED_NODE_ID");
  const known = new Set(nodeIds);
  for (const value of values) {
    if (!known.has(value)) {
      fail("CHANGED_NODE_NOT_FOUND", "changed_node_ids contains an unknown node", {
        node_id: value,
      });
    }
  }
  return canonicalClone(values.sort(compareUtf8));
};

const normalizeRiskProfile = (candidate, label) => {
  const profile = requirePlainDataObject(
    candidate,
    label,
    PROFILE_FIELDS,
    "INVALID_RISK_PROFILE",
  );
  return canonicalClone({
    node_id: requireIdentifier(
      readDataProperty(profile, "node_id"),
      `${label}.node_id`,
      "INVALID_RISK_PROFILE",
    ),
    authority_level: requireEnum(
      readDataProperty(profile, "authority_level"),
      `${label}.authority_level`,
      AUTHORITY_SET,
      "UNKNOWN_AUTHORITY_LEVEL",
    ),
    write_scope_level: requireEnum(
      readDataProperty(profile, "write_scope_level"),
      `${label}.write_scope_level`,
      WRITE_SCOPE_SET,
      "UNKNOWN_WRITE_SCOPE_LEVEL",
    ),
    data_sensitivity: requireEnum(
      readDataProperty(profile, "data_sensitivity"),
      `${label}.data_sensitivity`,
      DATA_SENSITIVITY_SET,
      "UNKNOWN_DATA_SENSITIVITY",
    ),
    mutable_contract: requireBoolean(
      readDataProperty(profile, "mutable_contract"),
      `${label}.mutable_contract`,
      "INVALID_RISK_PROFILE",
    ),
  });
};

const normalizeRiskProfiles = (candidate, nodeIds) => {
  const profiles = readDenseArray(candidate, "risk_profiles", "INVALID_RISK_PROFILES")
    .map((profile, index) => normalizeRiskProfile(profile, `risk_profiles[${index}]`))
    .sort((left, right) => compareUtf8(left.node_id, right.node_id));
  const profileNodeIds = profiles.map((profile) => profile.node_id);
  assertUniqueStrings(profileNodeIds, "risk profile node IDs", "DUPLICATE_RISK_PROFILE");
  const expected = [...nodeIds].sort(compareUtf8);
  if (canonicalizeQueryRankingJson(profileNodeIds) !== canonicalizeQueryRankingJson(expected)) {
    fail(
      "RISK_PROFILE_COVERAGE_MISMATCH",
      "risk profiles must cover every inventory node exactly once",
      { expected_node_ids: expected, observed_node_ids: profileNodeIds },
    );
  }
  return canonicalClone(profiles);
};

const normalizeSharedResource = (candidate, label, knownNodeIds) => {
  const resource = requirePlainDataObject(
    candidate,
    label,
    SHARED_RESOURCE_FIELDS,
    "INVALID_SHARED_RESOURCE",
  );
  const nodeIds = readDenseArray(
    readDataProperty(resource, "node_ids"),
    `${label}.node_ids`,
    "INVALID_SHARED_RESOURCE",
  ).map((nodeId, index) =>
    requireIdentifier(
      nodeId,
      `${label}.node_ids[${index}]`,
      "INVALID_SHARED_RESOURCE",
    ),
  );
  if (nodeIds.length < 2 || nodeIds.length > 256) {
    fail("INVALID_SHARED_RESOURCE", `${label}.node_ids must contain between 2 and 256 nodes`);
  }
  assertUniqueStrings(nodeIds, `${label}.node_ids`, "DUPLICATE_SHARED_RESOURCE_NODE");
  for (const nodeId of nodeIds) {
    if (!knownNodeIds.has(nodeId)) {
      fail("SHARED_RESOURCE_NODE_NOT_FOUND", `${label} refers to an unknown node`, {
        node_id: nodeId,
      });
    }
  }
  return canonicalClone({
    resource_id: requireIdentifier(
      readDataProperty(resource, "resource_id"),
      `${label}.resource_id`,
      "INVALID_SHARED_RESOURCE",
    ),
    kind: requireEnum(
      readDataProperty(resource, "kind"),
      `${label}.kind`,
      SHARED_RESOURCE_SET,
      "UNKNOWN_SHARED_RESOURCE_KIND",
    ),
    node_ids: nodeIds.sort(compareUtf8),
  });
};

const normalizeSharedResources = (candidate, nodeIds) => {
  const knownNodeIds = new Set(nodeIds);
  const resources = readDenseArray(
    candidate,
    "shared_resources",
    "INVALID_SHARED_RESOURCES",
  )
    .map((resource, index) =>
      normalizeSharedResource(resource, `shared_resources[${index}]`, knownNodeIds),
    )
    .sort((left, right) => compareUtf8(left.resource_id, right.resource_id));
  assertUniqueStrings(
    resources.map((resource) => resource.resource_id),
    "shared resource IDs",
    "DUPLICATE_SHARED_RESOURCE_ID",
  );
  return canonicalClone(resources);
};

const effectiveEdge = ({
  origin,
  kind,
  sourceEdgeId,
  resourceId,
  fromNodeId,
  toNodeId,
  weight,
  directionRule,
}) => {
  const semantic = canonicalClone({
    origin,
    kind,
    source_edge_id: sourceEdgeId,
    resource_id: resourceId,
    from_node_id: fromNodeId,
    to_node_id: toNodeId,
    weight,
    direction_rule: directionRule,
  });
  const hash = sha256CanonicalJson(semantic);
  return canonicalClone({
    impact_edge_id: `WIMPACT-${hash.slice("sha256:".length)}`,
    ...semantic,
  });
};

const structuralEffectiveEdges = (extraction) => {
  const result = [];
  for (const edge of extraction.resolved_edges) {
    const rule = IMPACT_EDGE_DIRECTION_BY_KIND[edge.kind];
    const add = (fromNodeId, toNodeId) =>
      result.push(
        effectiveEdge({
          origin: "STRUCTURAL",
          kind: edge.kind,
          sourceEdgeId: edge.edge_id,
          resourceId: null,
          fromNodeId,
          toNodeId,
          weight: 1,
          directionRule: rule,
        }),
      );
    if (rule === "SOURCE_TO_TARGET" || rule === "BIDIRECTIONAL") {
      add(edge.source_entity_id, edge.target_entity_id);
    }
    if (rule === "TARGET_TO_SOURCE" || rule === "BIDIRECTIONAL") {
      add(edge.target_entity_id, edge.source_entity_id);
    }
  }
  return result;
};

const sharedResourceEffectiveEdges = (resources) => {
  const result = [];
  for (const resource of resources) {
    for (let left = 0; left < resource.node_ids.length; left += 1) {
      for (let right = left + 1; right < resource.node_ids.length; right += 1) {
        const first = resource.node_ids[left];
        const second = resource.node_ids[right];
        for (const [fromNodeId, toNodeId] of [
          [first, second],
          [second, first],
        ]) {
          result.push(
            effectiveEdge({
              origin: "SHARED_RESOURCE",
              kind: resource.kind,
              sourceEdgeId: null,
              resourceId: resource.resource_id,
              fromNodeId,
              toNodeId,
              weight: SHARED_RESOURCE_WEIGHTS[resource.kind],
              directionRule: "BIDIRECTIONAL",
            }),
          );
        }
      }
    }
  }
  return result;
};

const buildEffectiveEdges = (extraction, resources) => {
  const edges = [
    ...structuralEffectiveEdges(extraction),
    ...sharedResourceEffectiveEdges(resources),
  ].sort((left, right) => compareUtf8(left.impact_edge_id, right.impact_edge_id));
  assertUniqueStrings(
    edges.map((edge) => edge.impact_edge_id),
    "impact edge IDs",
    "DUPLICATE_IMPACT_EDGE_ID",
  );
  return canonicalClone(edges);
};

const riskRecord = (profile) => {
  const components = {
    authority_level: AUTHORITY_LEVELS[profile.authority_level],
    write_scope_level: WRITE_SCOPE_LEVELS[profile.write_scope_level],
    data_sensitivity: DATA_SENSITIVITY_LEVELS[profile.data_sensitivity],
    mutable_contract: profile.mutable_contract ? 1 : 0,
  };
  const weightedComponents = {
    authority_level: components.authority_level * RISK_COMPONENT_WEIGHTS.authority_level,
    write_scope_level:
      components.write_scope_level * RISK_COMPONENT_WEIGHTS.write_scope_level,
    data_sensitivity:
      components.data_sensitivity * RISK_COMPONENT_WEIGHTS.data_sensitivity,
    mutable_contract:
      components.mutable_contract * RISK_COMPONENT_WEIGHTS.mutable_contract,
  };
  const numerator = Object.values(weightedComponents).reduce((total, value) => total + value, 0);
  const denominator =
    3 * RISK_COMPONENT_WEIGHTS.authority_level +
    3 * RISK_COMPONENT_WEIGHTS.write_scope_level +
    3 * RISK_COMPONENT_WEIGHTS.data_sensitivity +
    RISK_COMPONENT_WEIGHTS.mutable_contract;
  return canonicalClone({
    node_id: profile.node_id,
    risk_score: roundedScore(numerator / denominator),
    authority_level: profile.authority_level,
    write_scope_level: profile.write_scope_level,
    data_sensitivity: profile.data_sensitivity,
    mutable_contract: profile.mutable_contract,
    component_ordinals: components,
    weighted_components: weightedComponents,
  });
};

const comparePath = (left, right) => {
  const leftKey = canonicalizeQueryRankingJson(left.path_edge_ids);
  const rightKey = canonicalizeQueryRankingJson(right.path_edge_ids);
  return compareUtf8(left.origin_node_id, right.origin_node_id) || compareUtf8(leftKey, rightKey);
};

const traverseImpact = (nodeIds, changedNodeIds, effectiveEdges) => {
  const adjacency = new Map(nodeIds.map((nodeId) => [nodeId, []]));
  for (const edge of effectiveEdges) adjacency.get(edge.from_node_id).push(edge);
  for (const rows of adjacency.values()) {
    rows.sort(
      (left, right) =>
        compareUtf8(left.to_node_id, right.to_node_id) ||
        compareUtf8(left.impact_edge_id, right.impact_edge_id),
    );
  }
  const records = new Map();
  const queue = [];
  for (const nodeId of changedNodeIds) {
    const record = {
      distance: 0,
      origin_node_id: nodeId,
      path_edge_ids: [],
    };
    records.set(nodeId, record);
    queue.push(nodeId);
  }
  let cursor = 0;
  while (cursor < queue.length) {
    const currentNodeId = queue[cursor];
    cursor += 1;
    const current = records.get(currentNodeId);
    for (const edge of adjacency.get(currentNodeId)) {
      if (changedNodeIds.includes(edge.to_node_id)) continue;
      const candidate = {
        distance: current.distance + 1,
        origin_node_id: current.origin_node_id,
        path_edge_ids: [...current.path_edge_ids, edge.impact_edge_id],
      };
      const prior = records.get(edge.to_node_id);
      if (
        prior === undefined ||
        candidate.distance < prior.distance ||
        (candidate.distance === prior.distance && comparePath(candidate, prior) < 0)
      ) {
        records.set(edge.to_node_id, candidate);
        queue.push(edge.to_node_id);
      }
    }
  }
  const changedSet = new Set(changedNodeIds);
  const results = nodeIds.map((nodeId) => {
    const record = records.get(nodeId);
    if (record === undefined) {
      return canonicalClone({
        node_id: nodeId,
        impact_status: "UNAFFECTED",
        distance: null,
        origin_node_id: null,
        path_edge_ids: [],
      });
    }
    return canonicalClone({
      node_id: nodeId,
      impact_status: changedSet.has(nodeId) ? "CHANGED" : "AFFECTED",
      distance: record.distance,
      origin_node_id: record.origin_node_id,
      path_edge_ids: record.path_edge_ids,
    });
  });
  const affectedNodeIds = results
    .filter((row) => row.impact_status === "AFFECTED")
    .map((row) => row.node_id);
  const unaffectedNodeIds = results
    .filter((row) => row.impact_status === "UNAFFECTED")
    .map((row) => row.node_id);
  const impactOrder = results
    .filter((row) => row.impact_status !== "UNAFFECTED")
    .sort(
      (left, right) =>
        left.distance - right.distance || compareUtf8(left.node_id, right.node_id),
    )
    .map((row) => row.node_id);
  return canonicalClone({
    results,
    affected_node_ids: affectedNodeIds,
    unaffected_node_ids: unaffectedNodeIds,
    impact_order: impactOrder,
    blast_radius_count: affectedNodeIds.length,
  });
};

const algorithmDescriptor = () =>
  canonicalClone({
    name: RISK_CHANGE_IMPACT_ALGORITHM,
    implementation_version: RISK_CHANGE_IMPACT_VERSION,
    edge_direction_rules: IMPACT_EDGE_DIRECTION_BY_KIND,
    shared_resource_policy: "PAIRWISE_BIDIRECTIONAL_TYPED_EDGES",
    shared_resource_weights: SHARED_RESOURCE_WEIGHTS,
    risk_component_weights: RISK_COMPONENT_WEIGHTS,
    risk_formula: "WEIGHTED_EXPLICIT_PROFILE_COMPONENTS_NORMALIZED_TO_ONE",
    risk_independent_of_blast_radius: true,
    traversal: "DETERMINISTIC_MULTI_SOURCE_BFS_SHORTEST_PATH",
    unresolved_edge_policy: "RECORDED_AND_EXCLUDED_FROM_PROPAGATION",
    result_order: "UTF8_NODE_ID",
    tie_breaker: "ORIGIN_THEN_IMPACT_EDGE_ID_PATH_UTF8",
  });

const assessmentPreimage = ({
  inventory,
  extraction,
  changedNodeIds,
  riskProfiles,
  sharedResources,
}) => {
  const nodeIds = inventory.entities.map((entity) => entity.entity_id).sort(compareUtf8);
  const effectiveEdges = buildEffectiveEdges(extraction, sharedResources);
  const riskResults = riskProfiles.map(riskRecord);
  const riskOrder = [...riskResults]
    .sort(
      (left, right) =>
        right.risk_score - left.risk_score || compareUtf8(left.node_id, right.node_id),
    )
    .map((row) => row.node_id);
  const impact = traverseImpact(nodeIds, changedNodeIds, effectiveEdges);
  const unresolvedEdgeIds = extraction.unresolved_edges
    .map((edge) => edge.edge_id)
    .sort(compareUtf8);
  return canonicalClone({
    assessment_version: RISK_CHANGE_IMPACT_VERSION,
    inventory_id: inventory.inventory_id,
    inventory_hash: inventory.inventory_hash,
    extraction_id: extraction.extraction_id,
    extraction_hash: extraction.extraction_hash,
    algorithm: algorithmDescriptor(),
    algorithm_inputs: {
      node_count: nodeIds.length,
      changed_node_ids: changedNodeIds,
      risk_profiles: riskProfiles,
      shared_resources: sharedResources,
      resolved_edge_count: extraction.resolved_edges.length,
      unresolved_edge_count: extraction.unresolved_edges.length,
    },
    effective_edges: effectiveEdges,
    excluded_unresolved_edge_ids: unresolvedEdgeIds,
    risk_results: riskResults,
    risk_order: riskOrder,
    impact_results: impact.results,
    impact_order: impact.impact_order,
    affected_node_ids: impact.affected_node_ids,
    unaffected_node_ids: impact.unaffected_node_ids,
    blast_radius_count: impact.blast_radius_count,
  });
};

export const computeRiskAndChangeImpact = (candidate) => {
  const input = requirePlainDataObject(
    candidate,
    "RiskChangeImpactInput",
    INPUT_FIELDS,
    "INVALID_RISK_CHANGE_IMPACT_INPUT",
  );
  const inventory = validateWorkspaceInventory(readDataProperty(input, "inventory"));
  const extraction = validateWorkspaceEdgeExtraction(
    readDataProperty(input, "extraction"),
    inventory,
  );
  const nodeIds = inventory.entities.map((entity) => entity.entity_id);
  const changedNodeIds = normalizeChangedNodeIds(
    readDataProperty(input, "changed_node_ids"),
    nodeIds,
  );
  const riskProfiles = normalizeRiskProfiles(readDataProperty(input, "risk_profiles"), nodeIds);
  const sharedResources = normalizeSharedResources(
    readDataProperty(input, "shared_resources"),
    nodeIds,
  );
  const preimage = assessmentPreimage({
    inventory,
    extraction,
    changedNodeIds,
    riskProfiles,
    sharedResources,
  });
  const assessmentHash = sha256CanonicalJson(preimage);
  return canonicalClone({
    assessment_id: `WRISK-${assessmentHash.slice("sha256:".length)}`,
    ...preimage,
    assessment_hash: assessmentHash,
  });
};

export const validateRiskAndChangeImpact = (
  candidate,
  inventoryCandidate,
  extractionCandidate,
) => {
  const output = requirePlainDataObject(
    candidate,
    "RiskChangeImpact",
    OUTPUT_FIELDS,
    "INVALID_RISK_CHANGE_IMPACT",
  );
  const inputs = requirePlainDataObject(
    readDataProperty(output, "algorithm_inputs"),
    "algorithm_inputs",
    ALGORITHM_INPUT_FIELDS,
    "INVALID_RISK_CHANGE_IMPACT_ALGORITHM_INPUTS",
  );
  const rebuilt = computeRiskAndChangeImpact({
    inventory: inventoryCandidate,
    extraction: extractionCandidate,
    changed_node_ids: readDataProperty(inputs, "changed_node_ids"),
    risk_profiles: readDataProperty(inputs, "risk_profiles"),
    shared_resources: readDataProperty(inputs, "shared_resources"),
  });
  const observedHash = readDataProperty(output, "assessment_hash");
  if (typeof observedHash !== "string" || !SHA256_PATTERN.test(observedHash)) {
    fail(
      "INVALID_RISK_CHANGE_IMPACT_HASH",
      "assessment_hash must be sha256:<64 lowercase hex>",
    );
  }
  if (observedHash !== rebuilt.assessment_hash) {
    fail("RISK_CHANGE_IMPACT_HASH_MISMATCH", "assessment_hash does not bind the result", {
      expected: rebuilt.assessment_hash,
      observed: observedHash,
    });
  }
  if (readDataProperty(output, "assessment_id") !== rebuilt.assessment_id) {
    fail("RISK_CHANGE_IMPACT_ID_MISMATCH", "assessment_id does not bind assessment_hash");
  }
  if (canonicalizeQueryRankingJson(output) !== canonicalizeQueryRankingJson(rebuilt)) {
    fail(
      "RISK_CHANGE_IMPACT_REBUILD_MISMATCH",
      "risk and change impact differs from its canonical rebuild",
    );
  }
  return rebuilt;
};

export const computeRiskAndChangeImpactHash = (candidate, inventory, extraction) =>
  validateRiskAndChangeImpact(candidate, inventory, extraction).assessment_hash;
