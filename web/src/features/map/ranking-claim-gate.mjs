/**
 * M04 ranking-claim gate.
 *
 * The gate accepts only the sealed M01-M03 artifacts, revalidates each one
 * through its owning implementation, and derives a closed set of display
 * claims.  A UI cannot relabel a symbol inventory as importance, combine the
 * four dimensions into one score, or hide unresolved-edge exclusions.
 */

import { types as utilTypes } from "node:util";

import {
  validateWorkspaceEdgeExtraction,
  validateWorkspaceInventory,
} from "../../../../packages/workspace-map/src/inventory/index.mjs";
import { validateBaselineCentrality } from "../../../../packages/workspace-map/src/ranking/baseline/index.mjs";
import {
  validateQueryPersonalization,
  validateRiskAndChangeImpact,
} from "../../../../packages/workspace-map/src/ranking/query/index.mjs";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;

export const WORKSPACE_MAP_VIEW_VERSION = "4.0.0-m04.1";

export const RANKING_CLAIM_TYPES = OBJECT_FREEZE([
  "BASELINE_STRUCTURAL_CENTRALITY",
  "QUERY_LEXICAL_RELEVANCE",
  "INTRINSIC_RISK",
  "CHANGE_IMPACT",
]);

const RANKING_CLAIM_TYPE_SET = new Set(RANKING_CLAIM_TYPES);
const RANKING_CLAIM_STATUSES = new Set([
  "RANKED",
  "NOT_PERSONALIZED",
  "ORDERED_TRAVERSAL",
  "NO_CHANGE_INPUT",
]);

const MAP_INPUT_FIELDS = OBJECT_FREEZE([
  "inventory",
  "extraction",
  "baseline_centrality",
  "query_personalization",
  "risk_change_impact",
]);
const CLAIM_AUDIT_FIELDS = OBJECT_FREEZE([...MAP_INPUT_FIELDS, "claims"]);
const CLAIM_FIELDS = OBJECT_FREEZE([
  "claim_type",
  "label",
  "status",
  "algorithm_name",
  "algorithm_version",
  "artifact_hash",
  "order",
  "score_field",
  "excluded_unresolved_edge_ids",
]);

export class WorkspaceMapViewError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "WorkspaceMapViewError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(structuredClone(details));
  }
}

const fail = (code, message, details = undefined) => {
  throw new WorkspaceMapViewError(code, message, details);
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

const requirePlainDataObject = (value, label, fields, code) => {
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
  for (const key of REFLECT_OWN_KEYS(value)) {
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

const readDenseArray = (value, label, code) => {
  if (
    !ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== Array.prototype
  ) {
    fail(code, `${label} must be a non-proxy plain dense array`);
  }
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
      fail(code, `${label} contains a non-element property`);
    }
    const index = Number(key);
    if (!Number.isSafeInteger(index) || index >= value.length || String(index) !== key) {
      fail(code, `${label} contains an invalid element index`);
    }
  }
  const result = [];
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

const requireString = (value, label, code) => {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.normalize("NFC") !== value ||
    /\p{Cc}/u.test(value)
  ) {
    fail(code, `${label} must be a non-empty NFC string without controls`);
  }
  return value;
};

const normalizeStringArray = (value, label, code) => {
  const values = readDenseArray(value, label, code).map((entry, index) =>
    requireString(entry, `${label}[${index}]`, code),
  );
  if (new Set(values).size !== values.length) fail(code, `${label} contains duplicates`);
  return values;
};

const normalizeClaim = (candidate, index) => {
  const label = `claims[${index}]`;
  const claim = requirePlainDataObject(
    candidate,
    label,
    CLAIM_FIELDS,
    "INVALID_RANKING_CLAIM",
  );
  const claimType = requireString(
    readDataProperty(claim, "claim_type"),
    `${label}.claim_type`,
    "INVALID_RANKING_CLAIM",
  );
  if (!RANKING_CLAIM_TYPE_SET.has(claimType)) {
    fail("UNKNOWN_RANKING_CLAIM_TYPE", "claim_type is outside the closed vocabulary", {
      claim_type: claimType,
    });
  }
  const status = requireString(
    readDataProperty(claim, "status"),
    `${label}.status`,
    "INVALID_RANKING_CLAIM",
  );
  if (!RANKING_CLAIM_STATUSES.has(status)) {
    fail("UNKNOWN_RANKING_CLAIM_STATUS", "claim status is outside the closed vocabulary", {
      status,
    });
  }
  const artifactHash = readDataProperty(claim, "artifact_hash");
  if (typeof artifactHash !== "string" || !SHA256_PATTERN.test(artifactHash)) {
    fail("INVALID_RANKING_CLAIM", `${label}.artifact_hash must be sha256:<64 lowercase hex>`);
  }
  const scoreField = readDataProperty(claim, "score_field");
  if (scoreField !== null) {
    requireString(scoreField, `${label}.score_field`, "INVALID_RANKING_CLAIM");
  }
  return deepFreeze({
    claim_type: claimType,
    label: requireString(
      readDataProperty(claim, "label"),
      `${label}.label`,
      "INVALID_RANKING_CLAIM",
    ),
    status,
    algorithm_name: requireString(
      readDataProperty(claim, "algorithm_name"),
      `${label}.algorithm_name`,
      "INVALID_RANKING_CLAIM",
    ),
    algorithm_version: requireString(
      readDataProperty(claim, "algorithm_version"),
      `${label}.algorithm_version`,
      "INVALID_RANKING_CLAIM",
    ),
    artifact_hash: artifactHash,
    order: normalizeStringArray(
      readDataProperty(claim, "order"),
      `${label}.order`,
      "INVALID_RANKING_CLAIM",
    ),
    score_field: scoreField,
    excluded_unresolved_edge_ids: normalizeStringArray(
      readDataProperty(claim, "excluded_unresolved_edge_ids"),
      `${label}.excluded_unresolved_edge_ids`,
      "INVALID_RANKING_CLAIM",
    ),
  });
};

const inputFrom = (candidate, fields, label, code) => {
  const source = requirePlainDataObject(candidate, label, fields, code);
  return Object.fromEntries(fields.map((field) => [field, readDataProperty(source, field)]));
};

export function validateWorkspaceMapInput(candidate) {
  const input = inputFrom(candidate, MAP_INPUT_FIELDS, "WorkspaceMapInput", "MAP_INPUT_INVALID");
  const inventory = validateWorkspaceInventory(input.inventory);
  const extraction = validateWorkspaceEdgeExtraction(input.extraction, inventory);
  const baselineCentrality = validateBaselineCentrality(
    input.baseline_centrality,
    inventory,
    extraction,
  );
  const queryPersonalization = validateQueryPersonalization(
    input.query_personalization,
    inventory,
    extraction,
  );
  const riskChangeImpact = validateRiskAndChangeImpact(
    input.risk_change_impact,
    inventory,
    extraction,
  );
  return deepFreeze({
    inventory,
    extraction,
    baseline_centrality: baselineCentrality,
    query_personalization: queryPersonalization,
    risk_change_impact: riskChangeImpact,
  });
}

const expectedClaims = (artifacts) => {
  const baseline = artifacts.baseline_centrality;
  const query = artifacts.query_personalization;
  const riskImpact = artifacts.risk_change_impact;
  const queryIsPresent = query.query !== null;
  const changeIsPresent = riskImpact.algorithm_inputs.changed_node_ids.length > 0;
  return deepFreeze([
    {
      claim_type: "BASELINE_STRUCTURAL_CENTRALITY",
      label: "Baseline structural centrality",
      status: "RANKED",
      algorithm_name: baseline.algorithm.name,
      algorithm_version: baseline.algorithm.implementation_version,
      artifact_hash: baseline.ranking_hash,
      order: [...baseline.ranking_order],
      score_field: "baseline_centrality",
      excluded_unresolved_edge_ids: [
        ...baseline.algorithm_inputs.excluded_unresolved_edge_ids,
      ],
    },
    {
      claim_type: "QUERY_LEXICAL_RELEVANCE",
      label: queryIsPresent
        ? "Query lexical relevance"
        : "Query lexical relevance (no query supplied)",
      status: queryIsPresent ? "RANKED" : "NOT_PERSONALIZED",
      algorithm_name: query.algorithm.name,
      algorithm_version: query.algorithm.implementation_version,
      artifact_hash: query.ranking_hash,
      order: queryIsPresent ? [...query.ranking_order] : [],
      score_field: "query_relevance",
      excluded_unresolved_edge_ids: [
        ...query.algorithm_inputs.excluded_unresolved_edge_ids,
      ],
    },
    {
      claim_type: "INTRINSIC_RISK",
      label: "Intrinsic risk",
      status: "RANKED",
      algorithm_name: riskImpact.algorithm.name,
      algorithm_version: riskImpact.algorithm.implementation_version,
      artifact_hash: riskImpact.assessment_hash,
      order: [...riskImpact.risk_order],
      score_field: "risk_score",
      excluded_unresolved_edge_ids: [...riskImpact.excluded_unresolved_edge_ids],
    },
    {
      claim_type: "CHANGE_IMPACT",
      label: "Change impact / blast radius",
      status: changeIsPresent ? "ORDERED_TRAVERSAL" : "NO_CHANGE_INPUT",
      algorithm_name: riskImpact.algorithm.name,
      algorithm_version: riskImpact.algorithm.implementation_version,
      artifact_hash: riskImpact.assessment_hash,
      order: [...riskImpact.impact_order],
      score_field: null,
      excluded_unresolved_edge_ids: [...riskImpact.excluded_unresolved_edge_ids],
    },
  ]);
};

export function buildRankingClaims(candidate) {
  return expectedClaims(validateWorkspaceMapInput(candidate));
}

export function auditRankingClaims(candidate) {
  const input = inputFrom(
    candidate,
    CLAIM_AUDIT_FIELDS,
    "RankingClaimAuditInput",
    "RANKING_CLAIM_AUDIT_INPUT_INVALID",
  );
  const artifacts = validateWorkspaceMapInput(
    Object.fromEntries(MAP_INPUT_FIELDS.map((field) => [field, input[field]])),
  );
  const observed = readDenseArray(input.claims, "claims", "INVALID_RANKING_CLAIMS").map(
    normalizeClaim,
  );
  const expected = expectedClaims(artifacts);
  if (observed.length !== expected.length) {
    fail("RANKING_CLAIM_SET_MISMATCH", "exactly four separated ranking claims are required", {
      expected_count: expected.length,
      observed_count: observed.length,
    });
  }
  const observedTypes = observed.map((claim) => claim.claim_type);
  if (new Set(observedTypes).size !== observedTypes.length) {
    fail("RANKING_CLAIM_SET_MISMATCH", "ranking claim types must be unique");
  }
  for (let index = 0; index < expected.length; index += 1) {
    if (JSON.stringify(observed[index]) !== JSON.stringify(expected[index])) {
      fail("RANKING_CLAIM_MISMATCH", "displayed claim does not match its sealed algorithm", {
        claim_type: expected[index].claim_type,
        expected: expected[index],
        observed: observed[index],
      });
    }
  }
  return deepFreeze({
    status: "PASS",
    version: WORKSPACE_MAP_VIEW_VERSION,
    claim_count: expected.length,
    claim_types: [...RANKING_CLAIM_TYPES],
    inventory_hash: artifacts.inventory.inventory_hash,
    extraction_hash: artifacts.extraction.extraction_hash,
    artifact_hashes: [
      artifacts.baseline_centrality.ranking_hash,
      artifacts.query_personalization.ranking_hash,
      artifacts.risk_change_impact.assessment_hash,
    ],
  });
}

