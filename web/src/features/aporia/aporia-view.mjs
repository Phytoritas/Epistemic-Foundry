/**
 * U03 Aporia Engine read model.
 *
 * The Aporia panel renders an argument graph together with the questions it
 * leaves open.  Contradiction classes come from the engine's own vocabulary:
 * every `edge_type` the argument-graph schema declares is partitioned exactly as
 * `src/epistemic_foundry/aporia_engine/argument.py` partitions it, into strict
 * inference, defeasible support, assumption dependency, and the contradiction
 * classes that remain.  An edge type outside that vocabulary is refused with
 * `UNKNOWN_CONTRADICTION_CLASS`; it is never bucketed into an invented "other"
 * class, because a reader could not tell an unrecognised attack from a known
 * one.
 *
 * The port of the engine's rules is deliberate and complete:
 *   - dangling edge endpoints refuse, as `build_argument_graph` refuses them;
 *   - a graph with open questions may not be presented as resolved, mirroring
 *     `is_resolved`;
 *   - both kinds of open item are shown together, mirroring `open_questions`;
 *   - a strict inference resting on a challenged, unresolved, or undeclared
 *     assumption node refuses, mirroring `reasoning_mode_separation_holds`.
 *
 * Declaring sources:
 *   - `schemas/argument-graph.schema.json` (node, status and edge vocabularies)
 *   - `src/epistemic_foundry/aporia_engine/argument.py` (the partition itself)
 *   - `web/src/generated/ui-client/index.mjs` (the only route binding allowed)
 *
 * The module reads no clock, no random source, no environment and no file.
 */

import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

import { canonicalJsonSha256, SHA256_PATTERN } from "../../app/record-hash.mjs";
import { OPERATIONS, getArtifact, getRun } from "../../generated/ui-client/index.mjs";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_DEFINE_PROPERTY = Object.defineProperty;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;

export const APORIA_VIEW_VERSION = "4.0.0-u03.1";

/** `argument.py` `STRICT_EDGE_TYPES`. */
export const STRICT_INFERENCE_EDGE_TYPES = OBJECT_FREEZE(["deductively_implies"]);

/** `argument.py` `DEFEASIBLE_EDGE_TYPES`. */
export const DEFEASIBLE_SUPPORT_EDGE_TYPES = OBJECT_FREEZE([
  "supports",
  "inductively_supports",
  "explains",
  "predicts",
]);

/** The declared dependency edge, which is neither support nor contradiction. */
export const DEPENDENCY_EDGE_TYPES = OBJECT_FREEZE(["depends_on_assumption"]);

/** The contradiction classes the engine declares; nothing may be added here. */
export const CONTRADICTION_CLASSES = OBJECT_FREEZE([
  "attacks",
  "competes_with",
  "falsified_by",
  "rebuts",
  "undercuts",
]);

/** `schemas/argument-graph.schema.json` `edges[].edge_type`. */
export const ARGUMENT_EDGE_TYPES = OBJECT_FREEZE(
  [
    ...STRICT_INFERENCE_EDGE_TYPES,
    ...DEFEASIBLE_SUPPORT_EDGE_TYPES,
    ...DEPENDENCY_EDGE_TYPES,
    ...CONTRADICTION_CLASSES,
  ].sort(),
);

/** `schemas/argument-graph.schema.json` `nodes[].node_type`. */
export const ARGUMENT_NODE_TYPES = OBJECT_FREEZE([
  "premise",
  "assumption",
  "rule",
  "claim",
  "prediction",
  "falsifier",
  "alternative",
  "objection",
  "response",
  "conclusion",
]);

/** `schemas/argument-graph.schema.json` `nodes[].status`. */
export const ARGUMENT_NODE_STATUSES = OBJECT_FREEZE([
  "asserted",
  "accepted",
  "challenged",
  "rejected",
  "unresolved",
]);

/** `argument.py` `OPEN_NODE_STATUSES`. */
export const OPEN_NODE_STATUSES = OBJECT_FREEZE(["challenged", "unresolved"]);

/** Operation ids from the generated client this view is permitted to bind. */
export const APORIA_OPERATION_IDS = OBJECT_FREEZE(["getArtifact", "getRun"]);

export const APORIA_FINDING_CODES = OBJECT_FREEZE({
  APORIA_INPUT_INVALID:
    "The argument graph handed to the Aporia view is not a plain data object carrying exactly the field set the argument-graph schema declares, so no node or edge could be read without guessing what the caller meant.",
  ARGUMENT_GRAPH_HASH_MISMATCH:
    "The argument graph digest does not bind its current nodes, edges, and open-question ledger, so the view cannot trust that it is rendering the graph the Aporia engine sealed.",
  ARGUMENT_GRAPH_CANONICALIZATION_DIALECT_UNRATIFIED:
    "The graph digest is consistent with the Python producer's number-rendering dialect but not this JavaScript verifier's canonical form, so the unratified Foundry cross-language canonical JSON number-rendering contract leaves the graph unverifiable; this diagnostic is not by itself evidence of tampering and cannot authorize rendering.",
  UNKNOWN_CONTRADICTION_CLASS:
    "An edge declares a type outside the vocabulary the aporia engine partitions, and bucketing an unrecognised conflict into a generic class would present an unknown attack as an understood one.",
  UNKNOWN_NODE_TYPE:
    "A node declares a type outside the argument-graph vocabulary, so the panel could not say whether the statement is a premise, an assumption, an objection, or a conclusion.",
  UNKNOWN_NODE_STATUS:
    "A node declares a status outside the argument-graph vocabulary, so the view cannot tell whether the premise is settled, challenged, or still entirely unresolved.",
  DANGLING_EDGE_ENDPOINT:
    "An edge points at a node identifier the graph does not contain, so a reader could not tell whether the missing node was dropped from the rendering or never written at all.",
  DUPLICATE_ARGUMENT_NODE:
    "Two nodes share one identifier, so every edge referring to that identifier would be ambiguous and the rendered graph would silently pick one of the two statements.",
  OPEN_QUESTION_HIDDEN:
    "The graph records a hidden assumption or an unresolved objection that the rendering omits, and an aporia panel that hides open questions defeats the only purpose it has.",
  RESOLVED_OVERCLAIM:
    "The rendering claims the argument is resolved while the graph still records hidden assumptions or unresolved objections, which would close an open question by presentation alone.",
  STRICT_INFERENCE_UNSOUND:
    "A strict inference edge starts from a challenged or unresolved node, or from an assumption whose dependency is undeclared, so rendering it as a proof would present a defeasible chain as entailment.",
  OPERATION_NOT_DECLARED:
    "The Aporia view may only bind operations the generated OpenAPI client exports, and the requested operation id is not one of them, so the request would target an undeclared route.",
});

export class AporiaViewError extends Error {
  constructor(code, detail, context = {}) {
    super(`${code}: ${detail}`);
    this.name = "AporiaViewError";
    this.code = code;
    this.detail = detail;
    this.reason = APORIA_FINDING_CODES[code];
    this.context = OBJECT_FREEZE({ ...context });
  }
}

const fail = (code, detail, context = {}) => {
  if (!OBJECT_HAS_OWN(APORIA_FINDING_CODES, code)) {
    throw new Error(`undeclared Aporia finding code ${code}`);
  }
  throw new AporiaViewError(code, detail, context);
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

const CODE = "APORIA_INPUT_INVALID";

const isPlainDataObject = (value) =>
  value !== null &&
  typeof value === "object" &&
  !ARRAY_IS_ARRAY(value) &&
  !IS_PROXY(value) &&
  (OBJECT_GET_PROTOTYPE_OF(value) === PLAIN_OBJECT_PROTOTYPE ||
    OBJECT_GET_PROTOTYPE_OF(value) === null);

const requireFields = (value, label, fields, code = CODE) => {
  if (!isPlainDataObject(value)) fail(code, `${label} must be a plain data object`);
  const allowed = new Set(fields);
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (typeof key !== "string" || !allowed.has(key)) {
      fail(code, `${label} carries the unsupported field ${String(key)}`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor === undefined || !descriptor.enumerable || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail(code, `${label}.${String(key)} must be an enumerable data property`);
    }
  }
  for (const field of fields) {
    if (!OBJECT_HAS_OWN(value, field)) fail(code, `${label}.${field} is required`);
  }
  return value;
};

const readValue = (object, key) => OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(object, key).value;

const requireArray = (value, label, code = CODE) => {
  if (
    !ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== Array.prototype
  ) {
    fail(code, `${label} must be a plain dense array`);
  }
  const allowedKeys = new Set(["length"]);
  for (let index = 0; index < value.length; index += 1) allowedKeys.add(String(index));
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (typeof key !== "string" || !allowedKeys.has(key)) {
      fail(code, `${label} carries the unsupported array field ${String(key)}`);
    }
  }
  const result = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (descriptor === undefined || !descriptor.enumerable || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail(code, `${label} contains a sparse or accessor-backed element`);
    }
    result.push(descriptor.value);
  }
  return result;
};

const requireString = (value, label, code = CODE) => {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.normalize("NFC") !== value ||
    /\p{Cc}/u.test(value)
  ) {
    fail(code, `${label} must be a non-empty NFC string without control characters`);
  }
  return value;
};

const requireStringArray = (value, label) => {
  const values = requireArray(value, label).map((entry, index) =>
    requireString(entry, `${label}[${index}]`),
  );
  if (new Set(values).size !== values.length) fail(CODE, `${label} contains duplicate entries`);
  return values;
};

const GRAPH_FIELDS = OBJECT_FREEZE([
  "argument_graph_id",
  "run_id",
  "hypothesis_id",
  "nodes",
  "edges",
  "hidden_assumption_ids",
  "unresolved_objection_ids",
  "proof_trace_artifact_id",
  "graph_hash",
  "created_at",
]);
const NODE_FIELDS = OBJECT_FREEZE([
  "argument_node_id",
  "node_type",
  "statement",
  "evidence_ids",
  "scope",
  "status",
]);
const EDGE_FIELDS = OBJECT_FREEZE([
  "edge_id",
  "from_id",
  "to_id",
  "edge_type",
  "rule_ref",
  "confidence",
]);
const SCOPE_FIELDS = OBJECT_FREEZE([
  "domain",
  "population",
  "entity_type",
  "entity_subtype",
  "unit_of_analysis",
  "setting",
  "geography",
  "jurisdiction",
  "language",
  "lifecycle_stage",
  "spatial_scale",
  "temporal_scale",
  "time_period",
  "measurement_time",
  "intervention_or_exposure",
  "comparator",
  "inclusion_criteria",
  "exclusion_criteria",
  "conditions",
  "domain_extensions",
]);
const SCOPE_NULLABLE_STRING_FIELDS = OBJECT_FREEZE([
  "domain",
  "population",
  "entity_type",
  "entity_subtype",
  "unit_of_analysis",
  "setting",
  "geography",
  "jurisdiction",
  "language",
  "lifecycle_stage",
  "spatial_scale",
  "temporal_scale",
  "time_period",
  "measurement_time",
  "comparator",
]);
const INTERVENTION_FIELDS = OBJECT_FREEZE([
  "name",
  "category",
  "min_value",
  "max_value",
  "unit",
  "duration",
  "frequency",
  "rate",
  "route_or_delivery",
]);
const INTERVENTION_NULLABLE_STRING_FIELDS = OBJECT_FREEZE([
  "category",
  "unit",
  "duration",
  "frequency",
  "route_or_delivery",
]);
const PRESENTATION_FIELDS = OBJECT_FREEZE([
  "resolution_claim",
  "open_question_ids",
  "contradiction_classes",
]);
const INPUT_FIELDS = OBJECT_FREEZE(["graph", "presentation"]);

/** The resolution states an Aporia rendering may claim. */
export const RESOLUTION_CLAIMS = OBJECT_FREEZE(["RESOLVED", "OPEN_QUESTIONS_REMAIN"]);

const EDGE_TYPE_SET = new Set(ARGUMENT_EDGE_TYPES);
const CONTRADICTION_SET = new Set(CONTRADICTION_CLASSES);
const STRICT_SET = new Set(STRICT_INFERENCE_EDGE_TYPES);
const OPEN_STATUS_SET = new Set(OPEN_NODE_STATUSES);

const edgeClassOf = (edgeType) => {
  if (STRICT_SET.has(edgeType)) return "STRICT_INFERENCE";
  if (DEFEASIBLE_SUPPORT_EDGE_TYPES.includes(edgeType)) return "DEFEASIBLE_SUPPORT";
  if (DEPENDENCY_EDGE_TYPES.includes(edgeType)) return "ASSUMPTION_DEPENDENCY";
  return "CONTRADICTION";
};

const requireNullableString = (value, label) => {
  if (value !== null && typeof value !== "string") {
    fail(CODE, `${label} must be a string or null`);
  }
  return value;
};

const normalizeScopeScalar = (value, label) => {
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  ) {
    return value;
  }
  fail(CODE, `${label} must be a string, finite number, boolean, or null`);
};

const normalizeScopeScalarOrList = (value, label) => {
  if (!ARRAY_IS_ARRAY(value)) return normalizeScopeScalar(value, label);
  return requireArray(value, label).map((entry, index) =>
    normalizeScopeScalar(entry, `${label}[${index}]`),
  );
};

const normalizeScopeMap = (candidate, label) => {
  if (!isPlainDataObject(candidate)) fail(CODE, `${label} must be a plain data object`);
  const result = {};
  for (const key of REFLECT_OWN_KEYS(candidate)) {
    if (typeof key !== "string") fail(CODE, `${label} carries a non-string field`);
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(candidate, key);
    if (descriptor === undefined || !descriptor.enumerable || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail(CODE, `${label}.${key} must be an enumerable data property`);
    }
    OBJECT_DEFINE_PROPERTY(result, key, {
      configurable: true,
      enumerable: true,
      value: normalizeScopeScalarOrList(descriptor.value, `${label}.${key}`),
      writable: true,
    });
  }
  return result;
};

const normalizeScopeStringArray = (candidate, label) =>
  requireArray(candidate, label).map((entry, index) => {
    if (typeof entry !== "string") fail(CODE, `${label}[${index}] must be a string`);
    return entry;
  });

const normalizeIntervention = (candidate, label) => {
  if (candidate === null) return null;
  const intervention = requireFields(candidate, label, INTERVENTION_FIELDS);
  const name = readValue(intervention, "name");
  if (typeof name !== "string" || name.length === 0) {
    fail(CODE, `${label}.name must be a non-empty string`);
  }
  const normalized = { name };
  for (const field of INTERVENTION_NULLABLE_STRING_FIELDS) {
    normalized[field] = requireNullableString(
      readValue(intervention, field),
      `${label}.${field}`,
    );
  }
  for (const field of ["min_value", "max_value"]) {
    const value = readValue(intervention, field);
    if (value !== null && (typeof value !== "number" || !Number.isFinite(value))) {
      fail(CODE, `${label}.${field} must be a finite number or null`);
    }
    normalized[field] = value;
  }
  const rate = readValue(intervention, "rate");
  if (
    rate !== null &&
    typeof rate !== "string" &&
    (typeof rate !== "number" || !Number.isFinite(rate))
  ) {
    fail(CODE, `${label}.rate must be a string, finite number, or null`);
  }
  normalized.rate = rate;
  return normalized;
};

const normalizeScope = (candidate, label) => {
  const scope = requireFields(candidate, label, SCOPE_FIELDS);
  const normalized = {};
  for (const field of SCOPE_NULLABLE_STRING_FIELDS) {
    normalized[field] = requireNullableString(readValue(scope, field), `${label}.${field}`);
  }
  normalized.intervention_or_exposure = normalizeIntervention(
    readValue(scope, "intervention_or_exposure"),
    `${label}.intervention_or_exposure`,
  );
  normalized.inclusion_criteria = normalizeScopeStringArray(
    readValue(scope, "inclusion_criteria"),
    `${label}.inclusion_criteria`,
  );
  normalized.exclusion_criteria = normalizeScopeStringArray(
    readValue(scope, "exclusion_criteria"),
    `${label}.exclusion_criteria`,
  );
  normalized.conditions = normalizeScopeMap(
    readValue(scope, "conditions"),
    `${label}.conditions`,
  );
  normalized.domain_extensions = normalizeScopeMap(
    readValue(scope, "domain_extensions"),
    `${label}.domain_extensions`,
  );
  return normalized;
};

const UNRATIFIED_NUMBER_CANONICALIZATION_CONTRACT =
  "Foundry cross-language canonical JSON number-rendering contract";

const compareCodePoints = (left, right) => {
  const leftPoints = [...left];
  const rightPoints = [...right];
  const shared = Math.min(leftPoints.length, rightPoints.length);
  for (let index = 0; index < shared; index += 1) {
    const difference = leftPoints[index].codePointAt(0) - rightPoints[index].codePointAt(0);
    if (difference !== 0) return difference < 0 ? -1 : 1;
  }
  if (leftPoints.length === rightPoints.length) return 0;
  return leftPoints.length < rightPoints.length ? -1 : 1;
};

const pythonReprNumber = (value) => {
  if (!Number.isFinite(value)) {
    throw new TypeError("Python-dialect JSON cannot encode a non-finite number");
  }
  if (Object.is(value, -0)) return "-0.0";
  const magnitude = Math.abs(value);
  if (magnitude !== 0 && (magnitude < 1e-4 || magnitude >= 1e16)) {
    const [mantissa, exponent] = value.toExponential().split("e");
    const sign = exponent.startsWith("-") ? "-" : "+";
    const digits = exponent.replace(/^[+-]/u, "").padStart(2, "0");
    return `${mantissa}e${sign}${digits}`;
  }
  const rendered = String(value);
  return Number.isInteger(value) ? `${rendered}.0` : rendered;
};

/**
 * Diagnostic only: parsed Numbers no longer retain Python int/float identity.
 * Integral Numbers are therefore treated as floats, which can misclassify a
 * mismatch and must never turn a refused graph into an accepted one.
 */
const pythonNumberDialectJson = (value) => {
  if (value === null) return "null";
  const kind = typeof value;
  if (kind === "string" || kind === "boolean") return JSON.stringify(value);
  if (kind === "number") return pythonReprNumber(value);
  if (ARRAY_IS_ARRAY(value)) {
    return `[${value.map((entry) => pythonNumberDialectJson(entry)).join(",")}]`;
  }
  if (kind !== "object") {
    throw new TypeError(`Python-dialect JSON cannot encode a ${kind} value`);
  }
  return `{${Object.keys(value)
    .sort(compareCodePoints)
    .map((key) => `${JSON.stringify(key)}:${pythonNumberDialectJson(value[key])}`)
    .join(",")}}`;
};

const pythonNumberDialectSha256 = (value) =>
  `sha256:${createHash("sha256")
    .update(pythonNumberDialectJson(value), "utf8")
    .digest("hex")}`;

const normalizeNode = (candidate, index) => {
  const label = `nodes[${index}]`;
  const node = requireFields(candidate, label, NODE_FIELDS);
  const nodeType = requireString(readValue(node, "node_type"), `${label}.node_type`);
  if (!ARGUMENT_NODE_TYPES.includes(nodeType)) {
    fail("UNKNOWN_NODE_TYPE", `${label}.node_type is outside the declared vocabulary`, {
      node_type: nodeType,
    });
  }
  const status = requireString(readValue(node, "status"), `${label}.status`);
  if (!ARGUMENT_NODE_STATUSES.includes(status)) {
    fail("UNKNOWN_NODE_STATUS", `${label}.status is outside the declared vocabulary`, { status });
  }
  return {
    argument_node_id: requireString(
      readValue(node, "argument_node_id"),
      `${label}.argument_node_id`,
    ),
    node_type: nodeType,
    statement: requireString(readValue(node, "statement"), `${label}.statement`),
    evidence_ids: requireStringArray(readValue(node, "evidence_ids"), `${label}.evidence_ids`),
    scope: normalizeScope(readValue(node, "scope"), `${label}.scope`),
    status,
  };
};

const normalizeEdge = (candidate, index) => {
  const label = `edges[${index}]`;
  const edge = requireFields(candidate, label, EDGE_FIELDS);
  const edgeType = requireString(readValue(edge, "edge_type"), `${label}.edge_type`);
  if (!EDGE_TYPE_SET.has(edgeType)) {
    fail("UNKNOWN_CONTRADICTION_CLASS", `${label}.edge_type is outside the engine vocabulary`, {
      edge_type: edgeType,
      declared: [...ARGUMENT_EDGE_TYPES],
    });
  }
  const ruleRef = readValue(edge, "rule_ref");
  if (ruleRef !== null) requireString(ruleRef, `${label}.rule_ref`);
  const confidence = readValue(edge, "confidence");
  if (
    confidence !== null &&
    (typeof confidence !== "number" || !Number.isFinite(confidence) || confidence < 0 || confidence > 1)
  ) {
    fail(CODE, `${label}.confidence must be null or within the closed unit interval`);
  }
  return {
    edge_id: requireString(readValue(edge, "edge_id"), `${label}.edge_id`),
    from_id: requireString(readValue(edge, "from_id"), `${label}.from_id`),
    to_id: requireString(readValue(edge, "to_id"), `${label}.to_id`),
    edge_type: edgeType,
    edge_class: edgeClassOf(edgeType),
    contradiction_class: CONTRADICTION_SET.has(edgeType) ? edgeType : null,
    rule_ref: ruleRef,
    confidence,
  };
};

/** Validate one argument graph and re-apply the engine's own separation rule. */
export function validateArgumentGraph(candidate) {
  const graph = requireFields(candidate, "ArgumentGraph", GRAPH_FIELDS);
  const nodes = requireArray(readValue(graph, "nodes"), "nodes").map(normalizeNode);
  if (nodes.length === 0) fail(CODE, "an argument graph must contain at least one node");
  const nodeIds = nodes.map((node) => node.argument_node_id);
  if (new Set(nodeIds).size !== nodeIds.length) {
    fail("DUPLICATE_ARGUMENT_NODE", "two nodes share one argument node identifier");
  }
  const edges = requireArray(readValue(graph, "edges"), "edges").map(normalizeEdge);
  const edgeIds = edges.map((edge) => edge.edge_id);
  if (new Set(edgeIds).size !== edgeIds.length) fail(CODE, "edges contains duplicate identifiers");
  const known = new Set(nodeIds);
  for (const edge of edges) {
    for (const endpoint of ["from_id", "to_id"]) {
      if (!known.has(edge[endpoint])) {
        fail("DANGLING_EDGE_ENDPOINT", "an edge endpoint is not a node in this graph", {
          edge_id: edge.edge_id,
          endpoint,
          node_id: edge[endpoint],
        });
      }
    }
  }
  const nodeType = new Map(nodes.map((node) => [node.argument_node_id, node.node_type]));
  const nodeStatus = new Map(nodes.map((node) => [node.argument_node_id, node.status]));
  const declaredAssumptionEdges = new Set(
    edges.filter((edge) => edge.edge_type === "depends_on_assumption").map((edge) => edge.from_id),
  );
  for (const edge of edges) {
    if (!STRICT_SET.has(edge.edge_type)) continue;
    if (OPEN_STATUS_SET.has(nodeStatus.get(edge.from_id))) {
      fail("STRICT_INFERENCE_UNSOUND", "a strict inference starts from an open premise", {
        edge_id: edge.edge_id,
        from_id: edge.from_id,
        status: nodeStatus.get(edge.from_id),
      });
    }
    if (nodeType.get(edge.from_id) === "assumption" && !declaredAssumptionEdges.has(edge.from_id)) {
      fail("STRICT_INFERENCE_UNSOUND", "a strict inference rests on an undeclared assumption", {
        edge_id: edge.edge_id,
        from_id: edge.from_id,
      });
    }
  }
  const hidden = requireStringArray(
    readValue(graph, "hidden_assumption_ids"),
    "hidden_assumption_ids",
  );
  const unresolved = requireStringArray(
    readValue(graph, "unresolved_objection_ids"),
    "unresolved_objection_ids",
  );
  for (const id of [...hidden, ...unresolved]) {
    if (!known.has(id)) {
      fail("DANGLING_EDGE_ENDPOINT", "an open question names a node this graph does not contain", {
        node_id: id,
      });
    }
  }
  const proofTrace = readValue(graph, "proof_trace_artifact_id");
  if (proofTrace !== null) requireString(proofTrace, "proof_trace_artifact_id");
  const graphHash = readValue(graph, "graph_hash");
  if (typeof graphHash !== "string" || !SHA256_PATTERN.test(graphHash)) {
    fail(CODE, "graph_hash must match sha256:<64 lowercase hex characters>");
  }
  const argumentGraphId = requireString(
    readValue(graph, "argument_graph_id"),
    "argument_graph_id",
  );
  const runId = requireString(readValue(graph, "run_id"), "run_id");
  const hypothesisId = requireString(readValue(graph, "hypothesis_id"), "hypothesis_id");
  const createdAt = requireString(readValue(graph, "created_at"), "created_at");
  const normalizedGraph = {
    argument_graph_id: argumentGraphId,
    run_id: runId,
    hypothesis_id: hypothesisId,
    nodes,
    edges,
    hidden_assumption_ids: hidden,
    unresolved_objection_ids: unresolved,
    proof_trace_artifact_id: proofTrace,
    graph_hash: graphHash,
    created_at: createdAt,
  };
  const hashPreimage = {};
  for (const field of GRAPH_FIELDS) {
    if (field !== "graph_hash") hashPreimage[field] = readValue(graph, field);
  }
  const derivedGraphHash = canonicalJsonSha256(hashPreimage);
  if (graphHash !== derivedGraphHash) {
    const pythonDialectDigest = pythonNumberDialectSha256(hashPreimage);
    if (graphHash === pythonDialectDigest) {
      fail(
        "ARGUMENT_GRAPH_CANONICALIZATION_DIALECT_UNRATIFIED",
        `graph_hash is consistent with a Python/JavaScript canonicalization-dialect divergence; the ${UNRATIFIED_NUMBER_CANONICALIZATION_CONTRACT} is unratified, so the graph remains refused and the mismatch is not by itself evidence of tampering`,
        {
          claimed_digest: graphHash,
          derived_digest: derivedGraphHash,
          python_dialect_digest: pythonDialectDigest,
          unratified_contract: UNRATIFIED_NUMBER_CANONICALIZATION_CONTRACT,
        },
      );
    }
    fail(
      "ARGUMENT_GRAPH_HASH_MISMATCH",
      "graph_hash does not match the canonical argument graph content",
      { claimed_digest: graphHash, derived_digest: derivedGraphHash },
    );
  }
  return deepFreeze(normalizedGraph);
}

/** Every open item, so a panel cannot show only one kind. */
export function openQuestionIds(graph) {
  return [...graph.hidden_assumption_ids, ...graph.unresolved_objection_ids].sort();
}

const normalizePresentation = (candidate) => {
  const presentation = requireFields(candidate, "presentation", PRESENTATION_FIELDS);
  const claim = requireString(
    readValue(presentation, "resolution_claim"),
    "presentation.resolution_claim",
  );
  if (!RESOLUTION_CLAIMS.includes(claim)) {
    fail("RESOLVED_OVERCLAIM", "the resolution claim is outside the declared vocabulary", {
      resolution_claim: claim,
    });
  }
  return {
    resolution_claim: claim,
    open_question_ids: requireStringArray(
      readValue(presentation, "open_question_ids"),
      "presentation.open_question_ids",
    ),
    contradiction_classes: requireStringArray(
      readValue(presentation, "contradiction_classes"),
      "presentation.contradiction_classes",
    ),
  };
};

/** Validate the graph and the rendering the caller proposes for it. */
export function validateAporiaInput(candidate) {
  const input = requireFields(candidate, "AporiaViewInput", INPUT_FIELDS);
  const graph = validateArgumentGraph(readValue(input, "graph"));
  const presentation = normalizePresentation(readValue(input, "presentation"));
  const open = openQuestionIds(graph);
  for (const id of open) {
    if (!presentation.open_question_ids.includes(id)) {
      fail("OPEN_QUESTION_HIDDEN", "the rendering omits a recorded open question", {
        node_id: id,
      });
    }
  }
  for (const id of presentation.open_question_ids) {
    if (!open.includes(id)) {
      fail("OPEN_QUESTION_HIDDEN", "the rendering invents an open question the graph never recorded", {
        node_id: id,
      });
    }
  }
  if (presentation.resolution_claim === "RESOLVED" && open.length !== 0) {
    fail("RESOLVED_OVERCLAIM", "a graph with open questions may not be presented as resolved", {
      open_question_count: open.length,
    });
  }
  if (presentation.resolution_claim === "OPEN_QUESTIONS_REMAIN" && open.length === 0) {
    fail("RESOLVED_OVERCLAIM", "the rendering reports open questions the graph does not record");
  }
  const declaredClasses = [...presentation.contradiction_classes].sort();
  if (JSON.stringify(declaredClasses) !== JSON.stringify([...CONTRADICTION_CLASSES])) {
    fail(
      "UNKNOWN_CONTRADICTION_CLASS",
      "the rendering does not declare exactly the engine's contradiction classes",
      { expected: [...CONTRADICTION_CLASSES], observed: declaredClasses },
    );
  }
  return deepFreeze({ graph, presentation, open_question_ids: open });
}

const contradictionProjection = (graph) => {
  const byClass = {};
  for (const contradictionClass of CONTRADICTION_CLASSES) {
    byClass[contradictionClass] = { count: 0, edge_ids: [] };
  }
  for (const edge of graph.edges) {
    if (edge.contradiction_class === null) continue;
    byClass[edge.contradiction_class].count += 1;
    byClass[edge.contradiction_class].edge_ids.push(edge.edge_id);
  }
  return byClass;
};

/** Build the Aporia read model. */
export function buildAporiaView(candidate) {
  const input = validateAporiaInput(candidate);
  const graph = input.graph;
  const byId = new Map(graph.nodes.map((node) => [node.argument_node_id, node]));
  const contradictions = contradictionProjection(graph);
  const openQuestions = input.open_question_ids.map((id) => ({
    argument_node_id: id,
    kind: graph.hidden_assumption_ids.includes(id) ? "HIDDEN_ASSUMPTION" : "UNRESOLVED_OBJECTION",
    node_type: byId.get(id).node_type,
    status: byId.get(id).status,
    statement: byId.get(id).statement,
  }));
  const contradictionEdges = graph.edges.filter((edge) => edge.contradiction_class !== null);
  return deepFreeze({
    kind: "EpistemicFoundryAporiaView",
    version: APORIA_VIEW_VERSION,
    heading: "Aporia",
    aporia_identity: {
      argument_graph_id: graph.argument_graph_id,
      run_id: graph.run_id,
      hypothesis_id: graph.hypothesis_id,
      created_at: graph.created_at,
    },
    source_receipt: {
      graph_hash: graph.graph_hash,
      proof_trace_artifact_id: graph.proof_trace_artifact_id,
      operation_ids: [...APORIA_OPERATION_IDS],
    },
    resolution: {
      claim: input.presentation.resolution_claim,
      open_question_count: openQuestions.length,
      is_resolved: openQuestions.length === 0,
    },
    open_questions: openQuestions,
    contradiction_classes: [...CONTRADICTION_CLASSES],
    contradictions_by_class: contradictions,
    contradiction_edges: contradictionEdges.map((edge) => ({
      edge_id: edge.edge_id,
      contradiction_class: edge.contradiction_class,
      from_id: edge.from_id,
      to_id: edge.to_id,
      from_statement: byId.get(edge.from_id).statement,
      to_statement: byId.get(edge.to_id).statement,
      confidence: edge.confidence,
    })),
    edge_classes: {
      STRICT_INFERENCE: [...STRICT_INFERENCE_EDGE_TYPES],
      DEFEASIBLE_SUPPORT: [...DEFEASIBLE_SUPPORT_EDGE_TYPES],
      ASSUMPTION_DEPENDENCY: [...DEPENDENCY_EDGE_TYPES],
      CONTRADICTION: [...CONTRADICTION_CLASSES],
    },
    nodes: graph.nodes,
    edges: graph.edges,
    sections: [
      {
        id: "open-questions",
        title: "Open questions",
        state: openQuestions.length ? "OPEN_QUESTIONS_REMAIN" : "NONE_RECORDED",
        visible: true,
      },
      {
        id: "contradiction-classes",
        title: "Contradiction classes",
        state: contradictionEdges.length ? "POPULATED" : "NONE_RECORDED",
        visible: true,
      },
      {
        id: "inference-separation",
        title: "Inference separation",
        state: "VERIFIED",
        visible: true,
      },
      {
        id: "argument-nodes",
        title: "Argument nodes",
        state: graph.nodes.length ? "POPULATED" : "EMPTY_CONFIRMED",
        visible: true,
      },
    ],
  });
}

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const renderList = (items, emptyText, renderItem) =>
  items.length
    ? `<ol>${items.map((item) => `<li>${renderItem(item)}</li>`).join("")}</ol>`
    : `<p class="aporia-empty">${escapeHtml(emptyText)}</p>`;

/** Render the Aporia panel; open questions precede every other section. */
export function renderAporiaPanel(candidate) {
  const view = buildAporiaView(candidate);
  return [
    `<main class="aporia" data-aporia-version="${escapeHtml(view.version)}">`,
    `<header><h1>${escapeHtml(view.heading)}</h1><p data-resolution="${escapeHtml(
      view.resolution.claim,
    )}">${escapeHtml(view.resolution.claim)}</p></header>`,
    '<section class="aporia-open" data-section="open-questions"><h2>Open questions</h2>',
    renderList(
      view.open_questions,
      "This graph records no hidden assumption and no unresolved objection.",
      (item) =>
        `<span>${escapeHtml(item.kind)}</span> <code>${escapeHtml(
          item.argument_node_id,
        )}</code> <span>${escapeHtml(item.status)}</span> <p>${escapeHtml(item.statement)}</p>`,
    ),
    "</section>",
    '<section class="aporia-contradictions" data-section="contradiction-classes">',
    "<h2>Contradiction classes</h2><dl>",
    view.contradiction_classes
      .map(
        (contradictionClass) =>
          `<dt data-contradiction-class="${escapeHtml(contradictionClass)}">${escapeHtml(
            contradictionClass,
          )}</dt><dd>${escapeHtml(view.contradictions_by_class[contradictionClass].count)}</dd>`,
      )
      .join(""),
    "</dl>",
    renderList(
      view.contradiction_edges,
      "No contradiction edge was recorded.",
      (edge) =>
        `<code>${escapeHtml(edge.edge_id)}</code> <span>${escapeHtml(
          edge.contradiction_class,
        )}</span> <p>${escapeHtml(edge.from_statement)} &rarr; ${escapeHtml(
          edge.to_statement,
        )}</p>`,
    ),
    "</section>",
    '<section class="aporia-separation" data-section="inference-separation">',
    "<h2>Inference separation</h2>",
    `<p>Strict inference, defeasible support, assumption dependency and contradiction stay separate classes.</p></section>`,
    '<section class="aporia-nodes" data-section="argument-nodes"><h2>Argument nodes</h2>',
    renderList(
      view.nodes,
      "This graph carries no node.",
      (node) =>
        `<code>${escapeHtml(node.argument_node_id)}</code> <span>${escapeHtml(
          node.node_type,
        )}</span> <span>${escapeHtml(node.status)}</span> <p>${escapeHtml(node.statement)}</p>`,
    ),
    "</section></main>",
  ].join("");
}

const requireDeclaredOperation = (operationId) => {
  if (!APORIA_OPERATION_IDS.includes(operationId) || !OBJECT_HAS_OWN(OPERATIONS, operationId)) {
    fail("OPERATION_NOT_DECLARED", `${operationId} is not an Aporia-bindable operation`, {
      operation_id: operationId,
    });
  }
};

/**
 * Bind `GET /artifacts/{artifact_id}` for the argument-graph artifact.
 *
 * The canonical document declares no argument-graph route of its own, so the
 * graph is read as the artifact it is rather than through an invented path.
 */
export function aporiaGraphArtifactRequest({ artifact_id: artifactId }, transport) {
  requireDeclaredOperation("getArtifact");
  requireString(artifactId, "artifact_id");
  return getArtifact({ path: { artifact_id: artifactId } }, transport);
}

/** Bind `GET /runs/{run_id}` for the run that produced the graph. */
export function aporiaRunRequest({ run_id: runId }, transport) {
  requireDeclaredOperation("getRun");
  requireString(runId, "run_id");
  return getRun({ path: { run_id: runId } }, transport);
}
