/** M04 deterministic workspace-map read model and HTML projection. */

import {
  auditRankingClaims,
  buildRankingClaims,
  validateWorkspaceMapInput,
  WORKSPACE_MAP_VIEW_VERSION,
} from "./ranking-claim-gate.mjs";

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const entry of Object.values(value)) deepFreeze(entry);
  return Object.freeze(value);
};

const byNodeId = (rows) => new Map(rows.map((row) => [row.node_id, row]));

const coverageProjection = ({ inventory, extraction, baseline, query, riskImpact }) => ({
  indexed_entity_count: inventory.entity_count,
  unreadable_path_count: inventory.unreadable_paths.length,
  unreadable_paths: inventory.unreadable_paths.map(({ path, error_code: errorCode }) => ({
    path,
    error_code: errorCode,
  })),
  resolved_edge_count: extraction.edge_counts.resolved,
  unresolved_edge_count: extraction.edge_counts.unresolved,
  unresolved_edges: extraction.unresolved_edges.map((edge) => ({
    edge_id: edge.edge_id,
    kind: edge.kind,
    source_entity_id: edge.source_entity_id,
    target_identity: edge.target_identity,
    target_hint: edge.target_hint,
    unresolved_reason: edge.unresolved_reason,
  })),
  exclusions_by_dimension: {
    baseline_structural_centrality: [
      ...baseline.algorithm_inputs.excluded_unresolved_edge_ids,
    ],
    query_lexical_relevance: [...query.algorithm_inputs.excluded_unresolved_edge_ids],
    intrinsic_risk: [...riskImpact.excluded_unresolved_edge_ids],
    change_impact: [...riskImpact.excluded_unresolved_edge_ids],
  },
  source_class_counts: { ...inventory.source_class_counts },
  layer_counts: { ...inventory.layer_counts },
});

const algorithmProjection = (claims) =>
  claims.map((claim) => ({
    claim_type: claim.claim_type,
    label: claim.label,
    status: claim.status,
    algorithm_name: claim.algorithm_name,
    algorithm_version: claim.algorithm_version,
    artifact_hash: claim.artifact_hash,
    score_field: claim.score_field,
  }));

export function buildWorkspaceMapView(candidate) {
  const artifacts = validateWorkspaceMapInput(candidate);
  const baseline = artifacts.baseline_centrality;
  const query = artifacts.query_personalization;
  const riskImpact = artifacts.risk_change_impact;
  const claims = buildRankingClaims(artifacts);
  auditRankingClaims({ ...artifacts, claims });

  const baselineRows = byNodeId(baseline.results);
  const queryRows = byNodeId(query.results);
  const riskRows = byNodeId(riskImpact.risk_results);
  const impactRows = byNodeId(riskImpact.impact_results);
  const nodes = artifacts.inventory.entities.map((entity) => {
    const baselineRow = baselineRows.get(entity.entity_id);
    const queryRow = queryRows.get(entity.entity_id);
    const riskRow = riskRows.get(entity.entity_id);
    const impactRow = impactRows.get(entity.entity_id);
    return {
      node_id: entity.entity_id,
      label: entity.label,
      layer: entity.layer,
      kind: entity.kind,
      source_class: entity.source_class,
      path: entity.path,
      locator: entity.locator,
      owner: entity.owner,
      dimensions: {
        baseline_structural_centrality: {
          score: baselineRow.baseline_centrality,
          in_degree: baselineRow.in_degree,
          out_degree: baselineRow.out_degree,
          is_isolate: baselineRow.is_isolate,
        },
        query_lexical_relevance: {
          score: queryRow.query_relevance,
          lexical_score: queryRow.lexical_score,
          semantic_score: queryRow.semantic_score,
          semantic_status: queryRow.semantic_status,
        },
        intrinsic_risk: {
          score: riskRow.risk_score,
          authority_level: riskRow.authority_level,
          write_scope_level: riskRow.write_scope_level,
          data_sensitivity: riskRow.data_sensitivity,
          mutable_contract: riskRow.mutable_contract,
        },
        change_impact: {
          status: impactRow.impact_status,
          distance: impactRow.distance,
          origin_node_id: impactRow.origin_node_id,
          path_edge_ids: [...impactRow.path_edge_ids],
        },
      },
    };
  });

  const coverage = coverageProjection({
    inventory: artifacts.inventory,
    extraction: artifacts.extraction,
    baseline,
    query,
    riskImpact,
  });
  const view = {
    kind: "EpistemicFoundryWorkspaceMapView",
    version: WORKSPACE_MAP_VIEW_VERSION,
    heading: "Workspace map",
    map_identity: {
      workspace_id: artifacts.inventory.workspace_id,
      inventory_id: artifacts.inventory.inventory_id,
      inventory_hash: artifacts.inventory.inventory_hash,
      extraction_id: artifacts.extraction.extraction_id,
      extraction_hash: artifacts.extraction.extraction_hash,
    },
    query: {
      value: query.query,
      personalization: query.personalization,
      semantic_score: null,
      semantic_status: "NOT_COMPUTED",
    },
    coverage,
    ranking_claims: claims.map((claim) => ({ ...claim, order: [...claim.order] })),
    algorithms: algorithmProjection(claims),
    nodes,
    edges: {
      resolved: artifacts.extraction.resolved_edges.map((edge) => ({
        edge_id: edge.edge_id,
        kind: edge.kind,
        source_entity_id: edge.source_entity_id,
        target_entity_id: edge.target_entity_id,
        resolution: edge.resolution,
      })),
      unresolved: coverage.unresolved_edges,
    },
    sections: [
      {
        id: "coverage-and-exclusions",
        title: "Coverage and exclusions",
        state: coverage.unresolved_edge_count || coverage.unreadable_path_count
          ? "VISIBLE_LIMITATIONS"
          : "COMPLETE_FOR_DECLARED_SCOPE",
        visible: true,
      },
      {
        id: "algorithm-bindings",
        title: "Algorithm bindings",
        state: "VERIFIED",
        visible: true,
      },
      {
        id: "separate-ranking-dimensions",
        title: "Separate ranking dimensions",
        state: "VERIFIED",
        visible: true,
      },
      {
        id: "workspace-entities",
        title: "Workspace entities",
        state: nodes.length ? "POPULATED" : "EMPTY_CONFIRMED",
        visible: true,
      },
    ],
  };
  return deepFreeze(view);
}

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const displayNullable = (value) => (value === null ? "not available" : String(value));

const renderList = (items, emptyText, renderItem) =>
  items.length
    ? `<ol>${items.map((item) => `<li>${renderItem(item)}</li>`).join("")}</ol>`
    : `<p class="map-empty">${escapeHtml(emptyText)}</p>`;

const renderCoverage = (view) => {
  const coverage = view.coverage;
  return [
    `<section class="map-coverage" data-section="coverage-and-exclusions" data-state="${escapeHtml(
      view.sections[0].state,
    )}">`,
    "<h2>Coverage and exclusions</h2>",
    `<dl><dt>Indexed entities</dt><dd>${coverage.indexed_entity_count}</dd>`,
    `<dt>Resolved edges</dt><dd>${coverage.resolved_edge_count}</dd>`,
    `<dt>Unresolved edges</dt><dd>${coverage.unresolved_edge_count}</dd>`,
    `<dt>Unreadable paths</dt><dd>${coverage.unreadable_path_count}</dd></dl>`,
    "<h3>Unreadable paths</h3>",
    renderList(
      coverage.unreadable_paths,
      "No unreadable paths were recorded.",
      (item) => `<code>${escapeHtml(item.path)}</code> <span>${escapeHtml(item.error_code)}</span>`,
    ),
    "<h3>Unresolved edges excluded from ranking and impact</h3>",
    renderList(
      coverage.unresolved_edges,
      "No unresolved edges were recorded.",
      (edge) =>
        `<code>${escapeHtml(edge.edge_id)}</code> <span>${escapeHtml(
          edge.kind,
        )}</span> <span>${escapeHtml(edge.target_hint ?? edge.unresolved_reason)}</span>`,
    ),
    "</section>",
  ].join("");
};

const renderAlgorithms = (view) => [
  '<section class="map-algorithms" data-section="algorithm-bindings">',
  "<h2>Algorithm bindings</h2>",
  renderList(view.algorithms, "No algorithm bindings.", (algorithm) => [
    `<strong>${escapeHtml(algorithm.label)}</strong>`,
    ` <code>${escapeHtml(algorithm.algorithm_name)}</code>`,
    ` <span>${escapeHtml(algorithm.algorithm_version)}</span>`,
    ` <code>${escapeHtml(algorithm.artifact_hash)}</code>`,
    ` <span>${escapeHtml(algorithm.status)}</span>`,
  ].join("")),
  "</section>",
].join("");

const renderNode = (node) => {
  const dimensions = node.dimensions;
  return [
    `<article class="map-node" data-node-id="${escapeHtml(node.node_id)}">`,
    `<h3>${escapeHtml(node.label)}</h3>`,
    `<p><code>${escapeHtml(node.kind)}</code> <span>${escapeHtml(node.source_class)}</span></p>`,
    `<p>${escapeHtml(node.path ?? node.locator)}</p>`,
    "<dl>",
    `<dt>Baseline structural centrality</dt><dd>${escapeHtml(
      dimensions.baseline_structural_centrality.score,
    )}</dd>`,
    `<dt>Query lexical relevance</dt><dd>${escapeHtml(
      dimensions.query_lexical_relevance.score,
    )}</dd>`,
    `<dt>Semantic score</dt><dd>${escapeHtml(
      displayNullable(dimensions.query_lexical_relevance.semantic_score),
    )} (${escapeHtml(dimensions.query_lexical_relevance.semantic_status)})</dd>`,
    `<dt>Intrinsic risk</dt><dd>${escapeHtml(dimensions.intrinsic_risk.score)}</dd>`,
    `<dt>Change impact</dt><dd>${escapeHtml(
      dimensions.change_impact.status,
    )}; distance ${escapeHtml(displayNullable(dimensions.change_impact.distance))}</dd>`,
    "</dl></article>",
  ].join("");
};

export function renderWorkspaceMapPanel(candidate) {
  const view = buildWorkspaceMapView(candidate);
  return [
    `<main class="workspace-map" data-map-version="${escapeHtml(view.version)}">`,
    `<header><h1>${escapeHtml(view.heading)}</h1><p>Query: ${escapeHtml(
      displayNullable(view.query.value),
    )}</p></header>`,
    renderCoverage(view),
    renderAlgorithms(view),
    '<section class="map-dimensions" data-section="separate-ranking-dimensions">',
    "<h2>Separate ranking dimensions</h2>",
    `<p>Baseline structural centrality, query lexical relevance, intrinsic risk, and change impact are independent projections.</p>`,
    "</section>",
    '<section class="map-entities" data-section="workspace-entities"><h2>Workspace entities</h2>',
    view.nodes.map(renderNode).join(""),
    "</section></main>",
  ].join("");
}

