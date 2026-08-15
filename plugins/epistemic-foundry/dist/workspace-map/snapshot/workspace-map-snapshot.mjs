// WorkspaceMapSnapshot assembly.
//
// Every map semantic already exists: M01 owns typed inventory and edge
// extraction, M02 owns weighted PageRank baseline centrality, and M03 owns
// query personalization and risk/change impact.  This module is the missing
// composition root.  It calls those modules exactly once each and projects
// their output into the canonical snapshot shape; it re-derives no ranking,
// no vocabulary, and no hash basis of its own.
//
// The snapshot is computed on demand over a caller-frozen input.  Nothing here
// writes, persists, caches durably, or issues a receipt.

import {
  computeWorkspaceEdgeExtractionHash,
  computeWorkspaceInventoryHash,
  validateWorkspaceEdgeExtraction,
  validateWorkspaceInventory,
  buildWorkspaceInventory,
  extractWorkspaceEdges,
} from "../inventory/index.mjs";
import {
  BASELINE_CENTRALITY_ALGORITHM,
  BASELINE_CENTRALITY_VERSION,
  BASELINE_CENTRALITY_DEFAULT_PARAMETERS,
  computeBaselineCentrality,
} from "../ranking/baseline/index.mjs";
import {
  QUERY_PERSONALIZATION_ALGORITHM,
  QUERY_PERSONALIZATION_VERSION,
  RISK_CHANGE_IMPACT_VERSION,
  canonicalizeQueryRankingJson,
  computeQueryPersonalization,
  computeRiskAndChangeImpact,
} from "../ranking/query/index.mjs";
import { REPOSITORY_PROFILE_SCOPES, scanRepositoryWorkspace } from "./repository-scan.mjs";

export const WORKSPACE_MAP_SNAPSHOT_VERSION = "4.0.0-m04.1";

export class WorkspaceMapSnapshotError extends Error {
  constructor(code, message, details = null) {
    super(message);
    this.name = "WorkspaceMapSnapshotError";
    this.code = code;
    this.details = details;
  }
}

const fail = (code, message, details = null) => {
  throw new WorkspaceMapSnapshotError(code, message, details);
};

const requireText = (value, label) => {
  if (typeof value !== "string" || value.length === 0) {
    fail("INVALID_SNAPSHOT_INPUT", `${label} must be a non-empty string`);
  }
  return value;
};

const requireScopeList = (value, label) => {
  if (!Array.isArray(value)) {
    fail("INVALID_SNAPSHOT_INPUT", `${label} must be an array`);
  }
  return value.map((entry, index) => requireText(entry, `${label}[${index}]`));
};

/**
 * Index a ranking result by node so projection cannot silently mispair scores.
 *
 * A missing node is a hard failure rather than a zero: publishing 0 for an
 * unranked entity would be indistinguishable from a genuinely peripheral one.
 */
const scoreIndex = (rows, idKey, valueKey, label) => {
  const index = new Map();
  for (const row of rows) {
    const nodeId = row?.[idKey];
    const score = row?.[valueKey];
    if (typeof nodeId !== "string" || typeof score !== "number") {
      fail("INVALID_RANKING_OUTPUT", `${label} row is not a (${idKey}, ${valueKey}) pair`);
    }
    index.set(nodeId, score);
  }
  return index;
};

const readScore = (index, nodeId, label) => {
  const score = index.get(nodeId);
  if (typeof score !== "number") {
    fail("RANKING_COVERAGE_INCOMPLETE", `${label} has no score for ${nodeId}`);
  }
  return score;
};

/**
 * Compose an already-produced inventory, extraction, and the three ranking
 * dimensions into the canonical snapshot.
 *
 * Baseline centrality, query relevance, and risk are kept as separate node
 * fields exactly as the canonical schema requires; this function never blends
 * them into a single score.
 */
export const assembleWorkspaceMapSnapshot = ({
  inventory: inventoryCandidate,
  extraction: extractionCandidate,
  baseline,
  personalization,
  risk,
  query,
  includedScopes,
  excludedScopes,
  toolVersions,
  generatedAt,
  mapId,
}) => {
  const inventory = validateWorkspaceInventory(inventoryCandidate);
  const extraction = validateWorkspaceEdgeExtraction(extractionCandidate, inventory);

  const queryText = requireText(query, "query");
  const included = requireScopeList(includedScopes, "included_scopes");
  const excluded = requireScopeList(excludedScopes, "excluded_scopes");
  const generated = requireText(generatedAt, "generated_at");
  const snapshotId = requireText(mapId, "map_id");

  const baselineScores = scoreIndex(
    baseline?.results ?? [],
    "node_id",
    "baseline_centrality",
    "baseline centrality",
  );
  const relevanceScores = scoreIndex(
    personalization?.results ?? [],
    "node_id",
    "query_relevance",
    "query personalization",
  );
  const riskScores = scoreIndex(
    risk?.risk_results ?? [],
    "node_id",
    "risk_score",
    "risk assessment",
  );

  const nodes = inventory.entities.map((entity) => ({
    node_id: entity.entity_id,
    kind: entity.kind,
    label: entity.label,
    baseline_centrality: readScore(baselineScores, entity.entity_id, "baseline centrality"),
    query_relevance: readScore(relevanceScores, entity.entity_id, "query personalization"),
    risk_score: readScore(riskScores, entity.entity_id, "risk assessment"),
    content_hash: entity.content_hash ?? null,
  }));

  // Only resolved edges become graph edges.  An unresolved reference is a
  // recorded gap in the extraction, not a relationship between two known
  // entities, so inventing a target here would fabricate structure.  The
  // unresolved set stays visible through the extraction hash in tool_versions.
  const edges = extraction.resolved_edges.map((edge) => ({
    source: edge.source_entity_id,
    target: edge.target_entity_id,
    kind: edge.kind,
    weight: 1,
  }));

  const snapshot = {
    map_id: snapshotId,
    workspace_id: inventory.workspace_id,
    root_hash: inventory.root_hash,
    query: queryText,
    nodes,
    edges,
    ranking_algorithm: BASELINE_CENTRALITY_ALGORITHM,
    personalization: QUERY_PERSONALIZATION_ALGORITHM,
    included_scopes: included,
    excluded_scopes: excluded,
    tool_versions: {
      workspace_map_snapshot: WORKSPACE_MAP_SNAPSHOT_VERSION,
      baseline_centrality: BASELINE_CENTRALITY_VERSION,
      query_personalization: QUERY_PERSONALIZATION_VERSION,
      risk_change_impact: RISK_CHANGE_IMPACT_VERSION,
      inventory_hash: computeWorkspaceInventoryHash(inventory),
      extraction_hash: computeWorkspaceEdgeExtractionHash(extraction, inventory),
      ...(toolVersions ?? {}),
    },
    generated_at: generated,
    map_hash: "",
  };

  // map_hash seals every other field, so it is computed last.  The ranking
  // serializer is the correct one here: a snapshot carries fractional
  // centrality and relevance scores, which the integer-only inventory
  // serializer rejects by design.
  const { map_hash: _placeholder, ...preimage } = snapshot;
  snapshot.map_hash = sha256Hex(canonicalizeQueryRankingJson(preimage));
  return snapshot;
};

/**
 * Build a complete WorkspaceMapSnapshot for one query over a repository root.
 *
 * This is the producer `foundry.map.query` needs.  It is read-only and
 * computes on demand: nothing is written, cached durably, or receipted.
 *
 * The workspace is scanned twice.  If the second scan's root_hash differs, the
 * files changed while the graph was being built, so the nodes and edges may
 * describe a state that never existed.  That fails closed rather than
 * returning a plausible but incoherent map.
 */
export const buildRepositoryWorkspaceMapSnapshot = async ({
  workspaceRoot,
  workspaceId,
  query,
  generatedAt,
  mapId,
  changedNodeIds = [],
  owner = "M04",
}) => {
  const scan = await scanRepositoryWorkspace({ workspaceRoot, workspaceId, owner });

  const inventory = buildWorkspaceInventory(scan.inventoryInput);
  const extraction = extractWorkspaceEdges({ inventory, references: scan.references });

  const baseline = computeBaselineCentrality({
    inventory,
    extraction,
    parameters: { ...BASELINE_CENTRALITY_DEFAULT_PARAMETERS },
  });
  const personalization = computeQueryPersonalization({ inventory, extraction, query });

  // Risk requires a profile per node.  This profile has no authority metadata
  // source, so every node gets the same declared-unknown baseline rather than
  // a fabricated per-node authority level.
  const risk = computeRiskAndChangeImpact({
    inventory,
    extraction,
    changed_node_ids: [...changedNodeIds].sort(),
    risk_profiles: inventory.entities.map((entity) => ({
      node_id: entity.entity_id,
      authority_level: "LOCAL",
      write_scope_level: "BOUNDED",
      data_sensitivity: "PUBLIC",
      mutable_contract: false,
    })),
    shared_resources: [],
  });

  const snapshot = assembleWorkspaceMapSnapshot({
    inventory,
    extraction,
    baseline,
    personalization,
    risk,
    query,
    includedScopes: [...REPOSITORY_PROFILE_SCOPES.included],
    excludedScopes: [...REPOSITORY_PROFILE_SCOPES.excluded],
    toolVersions: { scanned_file_count: String(scan.scannedFileCount) },
    generatedAt,
    mapId,
  });

  const recheck = await scanRepositoryWorkspace({ workspaceRoot, workspaceId, owner });
  if (recheck.inventoryInput.root_hash !== scan.inventoryInput.root_hash) {
    fail(
      "WORKSPACE_CHANGED_DURING_SCAN",
      "the workspace changed while the snapshot was being assembled",
      { frozen: scan.inventoryInput.root_hash, observed: recheck.inventoryInput.root_hash },
    );
  }
  return snapshot;
};

const sha256Hex = (text) => {
  // Imported lazily so the pure composition path stays dependency-light.
  const { createHash } = nodeCrypto();
  return `sha256:${createHash("sha256").update(text, "utf8").digest("hex")}`;
};

let cryptoModule = null;
const nodeCrypto = () => {
  if (cryptoModule === null) {
    // eslint-disable-next-line no-undef
    cryptoModule = globalThis.process?.getBuiltinModule?.("node:crypto") ?? null;
  }
  if (cryptoModule === null) {
    fail("CRYPTO_UNAVAILABLE", "node:crypto is required to seal a snapshot");
  }
  return cryptoModule;
};
