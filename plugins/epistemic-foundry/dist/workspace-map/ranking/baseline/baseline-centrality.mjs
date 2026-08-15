/**
 * M02 deterministic baseline centrality.
 *
 * The implementation consumes the immutable M01 inventory and edge extraction,
 * computes weighted PageRank over resolved typed edges, retains isolates, and
 * records every effective algorithm input. It does not compute query relevance,
 * risk, blast radius, or a WorkspaceMapSnapshot owned by later M packages.
 */

import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

import {
  validateWorkspaceEdgeExtraction,
  validateWorkspaceInventory,
} from "../../inventory/index.mjs";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;

const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;

export const BASELINE_CENTRALITY_VERSION = "4.0.0-m02.1";
export const BASELINE_CENTRALITY_ALGORITHM = "WEIGHTED_PAGERANK";
export const BASELINE_CENTRALITY_DEFAULT_PARAMETERS = OBJECT_FREEZE({
  alpha: 0.85,
  max_iterations: 200,
  tolerance: 1e-12,
});

const INPUT_FIELDS = OBJECT_FREEZE(["inventory", "extraction", "parameters"]);
const PARAMETER_FIELDS = OBJECT_FREEZE(["alpha", "max_iterations", "tolerance"]);
const ALGORITHM_FIELDS = OBJECT_FREEZE([
  "name",
  "implementation_version",
  "alpha",
  "tolerance",
  "max_iterations",
  "convergence_norm",
  "dangling_policy",
  "edge_weight_policy",
  "direction",
  "result_order",
  "ranking_tie_breaker",
]);
const OUTPUT_FIELDS = OBJECT_FREEZE([
  "ranking_id",
  "ranking_version",
  "inventory_id",
  "inventory_hash",
  "extraction_id",
  "extraction_hash",
  "algorithm",
  "algorithm_inputs",
  "results",
  "ranking_order",
  "convergence",
  "uniformity",
  "ranking_hash",
]);

export class BaselineCentralityError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "BaselineCentralityError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(canonicalClone(details));
  }
}

const fail = (code, message, details = undefined) => {
  throw new BaselineCentralityError(code, message, details);
};

const compareUtf8 = (left, right) =>
  Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));

const requirePlainDataObject = (value, label, fields, code = "INVALID_INPUT") => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    (OBJECT_GET_PROTOTYPE_OF(value) !== PLAIN_OBJECT_PROTOTYPE &&
      OBJECT_GET_PROTOTYPE_OF(value) !== null)
  ) {
    fail(code, `${label} must be a non-proxy plain data object`);
  }
  const allowed = new Set(fields);
  const keys = REFLECT_OWN_KEYS(value);
  for (const key of keys) {
    if (typeof key !== "string" || !allowed.has(key)) {
      fail(code, `${label} contains an unsupported field`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail(code, `${label}.${String(key)} must be an enumerable data property`);
    }
  }
  for (const field of fields) {
    if (!OBJECT_HAS_OWN(value, field)) fail(code, `${label}.${field} is required`);
  }
  return value;
};

const readDataProperty = (object, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(object, key).value;

const readDenseArray = (value, label, code = "INVALID_INPUT") => {
  if (
    !ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== Array.prototype
  ) {
    fail(code, `${label} must be a non-proxy plain dense array`);
  }
  const result = [];
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
      fail(code, `${label} contains a non-element property`);
    }
  }
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail(code, `${label} contains a sparse or accessor-backed element`);
    }
    result.push(descriptor.value);
  }
  return result;
};

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of REFLECT_OWN_KEYS(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};

const canonicalizeValue = (value, ancestors) => {
  if (value === null) return "null";
  if (typeof value === "string") {
    if (value.normalize("NFC") !== value || /[\u0000-\u001f]/u.test(value)) {
      fail("NON_CANONICAL_JSON", "canonical JSON strings must be NFC without controls");
    }
    return JSON.stringify(value);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value) || Object.is(value, -0)) {
      fail("NON_CANONICAL_JSON", "canonical JSON accepts finite non-negative-zero numbers");
    }
    return JSON.stringify(value);
  }
  if (ARRAY_IS_ARRAY(value)) {
    if (ancestors.has(value)) fail("NON_CANONICAL_JSON", "canonical JSON cannot contain a cycle");
    const entries = readDenseArray(value, "canonical JSON array", "NON_CANONICAL_JSON");
    ancestors.add(value);
    try {
      return `[${entries.map((entry) => canonicalizeValue(entry, ancestors)).join(",")}]`;
    } finally {
      ancestors.delete(value);
    }
  }
  if (value === undefined || typeof value !== "object" || IS_PROXY(value)) {
    fail("NON_CANONICAL_JSON", "canonical JSON contains an unsupported value");
  }
  const prototype = OBJECT_GET_PROTOTYPE_OF(value);
  if (prototype !== PLAIN_OBJECT_PROTOTYPE && prototype !== null) {
    fail("NON_CANONICAL_JSON", "canonical JSON object has a custom prototype");
  }
  if (ancestors.has(value)) fail("NON_CANONICAL_JSON", "canonical JSON cannot contain a cycle");
  const keys = REFLECT_OWN_KEYS(value);
  if (keys.some((key) => typeof key !== "string")) {
    fail("NON_CANONICAL_JSON", "canonical JSON object contains a symbol key");
  }
  keys.sort(compareUtf8);
  ancestors.add(value);
  try {
    return `{${keys
      .map((key) => {
        const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
        if (
          descriptor === undefined ||
          !descriptor.enumerable ||
          !OBJECT_HAS_OWN(descriptor, "value")
        ) {
          fail("NON_CANONICAL_JSON", "canonical JSON object contains an accessor field");
        }
        return `${JSON.stringify(key)}:${canonicalizeValue(descriptor.value, ancestors)}`;
      })
      .join(",")}}`;
  } finally {
    ancestors.delete(value);
  }
};

export const canonicalizeBaselineCentralityJson = (value) =>
  canonicalizeValue(value, new Set());

const canonicalClone = (value) =>
  deepFreeze(JSON.parse(canonicalizeBaselineCentralityJson(value)));

const sha256CanonicalJson = (value) =>
  `sha256:${createHash("sha256")
    .update(canonicalizeBaselineCentralityJson(value), "utf8")
    .digest("hex")}`;

const requireNumber = (value, label, minimum, maximum, code) => {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    Object.is(value, -0) ||
    value < minimum ||
    value > maximum
  ) {
    fail(code, `${label} must be a finite number in [${minimum}, ${maximum}]`);
  }
  return value;
};

const normalizeParameters = (candidate) => {
  const parameters = requirePlainDataObject(
    candidate,
    "parameters",
    PARAMETER_FIELDS,
    "INVALID_CENTRALITY_PARAMETERS",
  );
  const alpha = requireNumber(
    readDataProperty(parameters, "alpha"),
    "parameters.alpha",
    Number.EPSILON,
    1 - Number.EPSILON,
    "INVALID_CENTRALITY_ALPHA",
  );
  const tolerance = requireNumber(
    readDataProperty(parameters, "tolerance"),
    "parameters.tolerance",
    1e-15,
    1e-3,
    "INVALID_CENTRALITY_TOLERANCE",
  );
  const maxIterations = readDataProperty(parameters, "max_iterations");
  if (!Number.isSafeInteger(maxIterations) || maxIterations < 1 || maxIterations > 100_000) {
    fail(
      "INVALID_CENTRALITY_MAX_ITERATIONS",
      "parameters.max_iterations must be an integer in [1, 100000]",
    );
  }
  return canonicalClone({ alpha, max_iterations: maxIterations, tolerance });
};

const componentMetrics = (nodeIds, edges) => {
  const neighbours = new Map(nodeIds.map((nodeId) => [nodeId, new Set()]));
  for (const edge of edges) {
    neighbours.get(edge.source_entity_id).add(edge.target_entity_id);
    neighbours.get(edge.target_entity_id).add(edge.source_entity_id);
  }
  const assignments = new Map();
  for (const start of nodeIds) {
    if (assignments.has(start)) continue;
    const members = [];
    const pending = [start];
    assignments.set(start, null);
    while (pending.length > 0) {
      const current = pending.pop();
      members.push(current);
      const ordered = [...neighbours.get(current)].sort(compareUtf8).reverse();
      for (const next of ordered) {
        if (!assignments.has(next)) {
          assignments.set(next, null);
          pending.push(next);
        }
      }
    }
    members.sort(compareUtf8);
    const componentHash = sha256CanonicalJson({ members });
    const componentId = `WCOMP-${componentHash.slice("sha256:".length)}`;
    for (const member of members) {
      assignments.set(member, { component_id: componentId, component_size: members.length });
    }
  }
  return assignments;
};

const algorithmDescriptor = (parameters) =>
  canonicalClone({
    name: BASELINE_CENTRALITY_ALGORITHM,
    implementation_version: BASELINE_CENTRALITY_VERSION,
    alpha: parameters.alpha,
    tolerance: parameters.tolerance,
    max_iterations: parameters.max_iterations,
    convergence_norm: "L1",
    dangling_policy: "UNIFORM_REDISTRIBUTION",
    edge_weight_policy: "UNIT_PER_RESOLVED_TYPED_EDGE",
    direction: "SOURCE_TO_TARGET",
    result_order: "UTF8_NODE_ID",
    ranking_tie_breaker: "UTF8_NODE_ID",
  });

const computePageRank = (nodeIds, edges, parameters) => {
  const nodeCount = nodeIds.length;
  if (nodeCount === 0) {
    return { converged: true, delta: 0, iterations: 0, ranks: new Map(), scoreSum: 0 };
  }
  const indexById = new Map(nodeIds.map((nodeId, index) => [nodeId, index]));
  const outWeights = new Float64Array(nodeCount);
  const indexedEdges = edges.map((edge) => {
    const source = indexById.get(edge.source_entity_id);
    const target = indexById.get(edge.target_entity_id);
    outWeights[source] += edge.weight;
    return { source, target, weight: edge.weight };
  });
  let current = new Float64Array(nodeCount);
  current.fill(1 / nodeCount);
  let delta = Number.POSITIVE_INFINITY;
  let iterations = 0;
  while (iterations < parameters.max_iterations) {
    const next = new Float64Array(nodeCount);
    let danglingMass = 0;
    for (let index = 0; index < nodeCount; index += 1) {
      if (outWeights[index] === 0) danglingMass += current[index];
    }
    const floor =
      (1 - parameters.alpha) / nodeCount +
      (parameters.alpha * danglingMass) / nodeCount;
    next.fill(floor);
    for (const edge of indexedEdges) {
      next[edge.target] +=
        parameters.alpha * current[edge.source] * (edge.weight / outWeights[edge.source]);
    }
    delta = 0;
    for (let index = 0; index < nodeCount; index += 1) {
      delta += Math.abs(next[index] - current[index]);
    }
    current = next;
    iterations += 1;
    if (delta <= parameters.tolerance) break;
  }
  if (delta > parameters.tolerance) {
    fail("CENTRALITY_NON_CONVERGENCE", "weighted PageRank did not converge within the bound", {
      delta,
      iterations,
      max_iterations: parameters.max_iterations,
      tolerance: parameters.tolerance,
    });
  }
  let scoreSum = 0;
  const ranks = new Map();
  for (let index = 0; index < nodeCount; index += 1) {
    const score = current[index];
    if (!Number.isFinite(score) || score < 0) {
      fail("CENTRALITY_NUMERIC_INTEGRITY", "weighted PageRank emitted an invalid score");
    }
    ranks.set(nodeIds[index], score);
    scoreSum += score;
  }
  if (Math.abs(scoreSum - 1) > Math.max(parameters.tolerance * 10, 1e-12)) {
    fail("CENTRALITY_NORMALIZATION_FAILURE", "weighted PageRank scores do not sum to one", {
      score_sum: scoreSum,
    });
  }
  return { converged: true, delta, iterations, ranks, scoreSum };
};

const topologyMetrics = (nodeIds, edges) => {
  const inDegree = new Map(nodeIds.map((nodeId) => [nodeId, 0]));
  const outDegree = new Map(nodeIds.map((nodeId) => [nodeId, 0]));
  for (const edge of edges) {
    outDegree.set(edge.source_entity_id, outDegree.get(edge.source_entity_id) + edge.weight);
    inDegree.set(edge.target_entity_id, inDegree.get(edge.target_entity_id) + edge.weight);
  }
  return { inDegree, outDegree };
};

const uniformityRecord = (nodeIds, ranks, metrics, tolerance) => {
  if (nodeIds.length === 0) {
    return canonicalClone({
      all_equal: true,
      score_span: 0,
      structurally_asymmetric: false,
      guard_threshold: Math.max(tolerance * 10, Number.EPSILON * 32),
    });
  }
  const values = nodeIds.map((nodeId) => ranks.get(nodeId));
  const scoreSpan = Math.max(...values) - Math.min(...values);
  const degreeSignatures = new Set(
    nodeIds.map((nodeId) => `${metrics.inDegree.get(nodeId)}:${metrics.outDegree.get(nodeId)}`),
  );
  const guardThreshold = Math.max(tolerance * 10, Number.EPSILON * 32);
  const record = canonicalClone({
    all_equal: scoreSpan <= guardThreshold,
    score_span: scoreSpan,
    structurally_asymmetric: degreeSignatures.size > 1,
    guard_threshold: guardThreshold,
  });
  if (record.structurally_asymmetric && record.all_equal) {
    fail(
      "UNIFORM_RANK_REGRESSION",
      "a structurally asymmetric graph received uniform baseline centrality",
      record,
    );
  }
  return record;
};

const rankingPreimage = ({ inventory, extraction, parameters }) => {
  const nodeIds = inventory.entities.map((entity) => entity.entity_id).sort(compareUtf8);
  const resolvedEdges = extraction.resolved_edges
    .map((edge) =>
      canonicalClone({
        edge_id: edge.edge_id,
        kind: edge.kind,
        source_entity_id: edge.source_entity_id,
        target_entity_id: edge.target_entity_id,
        weight: 1,
      }),
    )
    .sort((left, right) => compareUtf8(left.edge_id, right.edge_id));
  const unresolvedEdgeIds = extraction.unresolved_edges
    .map((edge) => edge.edge_id)
    .sort(compareUtf8);
  const metrics = topologyMetrics(nodeIds, resolvedEdges);
  const components = componentMetrics(nodeIds, resolvedEdges);
  const pageRank = computePageRank(nodeIds, resolvedEdges, parameters);
  const uniformity = uniformityRecord(nodeIds, pageRank.ranks, metrics, parameters.tolerance);
  const results = nodeIds.map((nodeId) => {
    const component = components.get(nodeId);
    return canonicalClone({
      node_id: nodeId,
      baseline_centrality: pageRank.ranks.get(nodeId),
      in_degree: metrics.inDegree.get(nodeId),
      out_degree: metrics.outDegree.get(nodeId),
      is_isolate: metrics.inDegree.get(nodeId) === 0 && metrics.outDegree.get(nodeId) === 0,
      weak_component_id: component.component_id,
      weak_component_size: component.component_size,
    });
  });
  const rankingOrder = [...results]
    .sort(
      (left, right) =>
        right.baseline_centrality - left.baseline_centrality ||
        compareUtf8(left.node_id, right.node_id),
    )
    .map((row) => row.node_id);
  return canonicalClone({
    ranking_version: BASELINE_CENTRALITY_VERSION,
    inventory_id: inventory.inventory_id,
    inventory_hash: inventory.inventory_hash,
    extraction_id: extraction.extraction_id,
    extraction_hash: extraction.extraction_hash,
    algorithm: algorithmDescriptor(parameters),
    algorithm_inputs: {
      node_count: nodeIds.length,
      node_ids: nodeIds,
      resolved_edge_count: resolvedEdges.length,
      resolved_edges: resolvedEdges,
      unresolved_edge_count: unresolvedEdgeIds.length,
      excluded_unresolved_edge_ids: unresolvedEdgeIds,
    },
    results,
    ranking_order: rankingOrder,
    convergence: {
      converged: pageRank.converged,
      iterations: pageRank.iterations,
      final_l1_delta: pageRank.delta,
      score_sum: pageRank.scoreSum,
    },
    uniformity,
  });
};

export const computeBaselineCentrality = (candidate) => {
  const input = requirePlainDataObject(
    candidate,
    "BaselineCentralityInput",
    INPUT_FIELDS,
    "INVALID_BASELINE_CENTRALITY_INPUT",
  );
  const inventory = validateWorkspaceInventory(readDataProperty(input, "inventory"));
  const extraction = validateWorkspaceEdgeExtraction(
    readDataProperty(input, "extraction"),
    inventory,
  );
  const parameters = normalizeParameters(readDataProperty(input, "parameters"));
  const preimage = rankingPreimage({ inventory, extraction, parameters });
  const rankingHash = sha256CanonicalJson(preimage);
  return canonicalClone({
    ranking_id: `WBASE-${rankingHash.slice("sha256:".length)}`,
    ...preimage,
    ranking_hash: rankingHash,
  });
};

export const validateBaselineCentrality = (candidate, inventoryCandidate, extractionCandidate) => {
  const output = requirePlainDataObject(
    candidate,
    "BaselineCentrality",
    OUTPUT_FIELDS,
    "INVALID_BASELINE_CENTRALITY",
  );
  const algorithm = requirePlainDataObject(
    readDataProperty(output, "algorithm"),
    "algorithm",
    ALGORITHM_FIELDS,
    "INVALID_BASELINE_CENTRALITY_ALGORITHM",
  );
  const parameters = {
    alpha: readDataProperty(algorithm, "alpha"),
    max_iterations: readDataProperty(algorithm, "max_iterations"),
    tolerance: readDataProperty(algorithm, "tolerance"),
  };
  const rebuilt = computeBaselineCentrality({
    inventory: inventoryCandidate,
    extraction: extractionCandidate,
    parameters,
  });
  const observedHash = readDataProperty(output, "ranking_hash");
  if (typeof observedHash !== "string" || !SHA256_PATTERN.test(observedHash)) {
    fail("INVALID_BASELINE_CENTRALITY_HASH", "ranking_hash must be sha256:<64 lowercase hex>");
  }
  if (observedHash !== rebuilt.ranking_hash) {
    fail("BASELINE_CENTRALITY_HASH_MISMATCH", "ranking_hash does not bind the result", {
      expected: rebuilt.ranking_hash,
      observed: observedHash,
    });
  }
  if (readDataProperty(output, "ranking_id") !== rebuilt.ranking_id) {
    fail("BASELINE_CENTRALITY_ID_MISMATCH", "ranking_id does not bind ranking_hash");
  }
  if (
    canonicalizeBaselineCentralityJson(output) !==
    canonicalizeBaselineCentralityJson(rebuilt)
  ) {
    fail("BASELINE_CENTRALITY_REBUILD_MISMATCH", "result differs from its canonical rebuild");
  }
  return rebuilt;
};

export const computeBaselineCentralityHash = (candidate, inventory, extraction) =>
  validateBaselineCentrality(candidate, inventory, extraction).ranking_hash;
