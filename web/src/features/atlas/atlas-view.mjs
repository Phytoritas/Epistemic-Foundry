/**
 * U03 Evidence Atlas read model.
 *
 * The Atlas renders one `CoverageSnapshot` exactly as the response carries it.
 * Coverage is the one thing a research console is most tempted to overstate, so
 * this module follows the M04 ranking-claim gate: display claims are derived
 * from the response by `buildCoverageClaims`, and `auditCoverageClaims` refuses
 * any claim set a caller assembled by hand that does not match.  A cell whose
 * `search_state` is `UNSEARCHED` cannot be presented as searched-and-empty, and
 * an axis cross-product with missing cells is reported as missing rather than
 * silently treated as complete.
 *
 * Declaring sources:
 *   - `schemas/coverage-snapshot.schema.json` (field set, `search_state` enum)
 *   - `web/src/generated/ui-client/index.mjs` (the only route binding allowed)
 *
 * The module reads no clock, no random source, no environment and no file: a
 * view is a pure projection of the response it was handed.
 */

import { types as utilTypes } from "node:util";

import {
  OPERATIONS,
  createRetrievalRun,
  getCoverageSnapshot,
} from "../../generated/ui-client/index.mjs";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;

export const ATLAS_VIEW_VERSION = "4.0.0-u03.1";

/** `schemas/coverage-snapshot.schema.json` `$defs.cell.search_state`. */
export const ATLAS_SEARCH_STATES = OBJECT_FREEZE([
  "UNSEARCHED",
  "PARTIAL",
  "SEARCHED_NONE",
  "SEARCHED_WITH_RESULTS",
]);

/** The closed set of coverage claims this view is allowed to display. */
export const COVERAGE_CLAIM_TYPES = OBJECT_FREEZE([
  "SEARCH_STATE_DISTRIBUTION",
  "AXIS_CELL_COVERAGE",
  "UNSEARCHED_SCOPES",
  "EVIDENCE_INDEPENDENCE",
  "LENS_CONCENTRATION",
  "SNAPSHOT_FRESHNESS",
]);

/** Every status a coverage claim may carry. */
export const COVERAGE_CLAIM_STATUSES = OBJECT_FREEZE([
  "MEASURED",
  "PARTIAL",
  "NOT_COMPUTED",
]);

/** Operation ids from the generated client this view is permitted to bind. */
export const ATLAS_OPERATION_IDS = OBJECT_FREEZE([
  "getCoverageSnapshot",
  "createRetrievalRun",
]);

export const ATLAS_FINDING_CODES = OBJECT_FREEZE({
  ATLAS_INPUT_INVALID:
    "The coverage snapshot handed to the Atlas view is not a plain data object carrying exactly the field set the coverage-snapshot schema declares, so no field could be read without guessing what the caller meant.",
  UNKNOWN_SEARCH_STATE:
    "A cell declares a search state outside the coverage-snapshot vocabulary, and bucketing it into a generic label would present an unrecognised state as if the Atlas understood it.",
  SEARCH_STATE_CONTRADICTS_COUNTS:
    "A cell reports counts or evidence identifiers that contradict its own declared search state, so rendering it would show searched-and-empty where nothing was searched or the reverse.",
  CELL_COORDINATE_UNDECLARED:
    "A cell coordinate names an axis or a bucket the snapshot does not declare, so the cell cannot be placed on the rendered grid without inventing an axis the response never carried.",
  DUPLICATE_CELL_COORDINATE:
    "Two cells occupy the same axis coordinate, so any rendered grid would silently drop one of them and understate or overstate the evidence at that position.",
  INDEPENDENCE_OVERCLAIM:
    "The snapshot claims more effectively independent evidence than it carries distinct evidence identifiers, which would render a stronger independence story than the response supports.",
  UNKNOWN_COVERAGE_CLAIM_TYPE:
    "A supplied coverage claim uses a claim type outside the closed display vocabulary, so the view cannot verify it against the snapshot that is supposed to justify it.",
  UNKNOWN_COVERAGE_CLAIM_STATUS:
    "A supplied coverage claim uses a status outside the closed vocabulary, so a not-computed measurement could be displayed as if it had actually been measured.",
  INVALID_COVERAGE_CLAIM:
    "A supplied coverage claim is not a plain data object with exactly the declared claim fields, so it cannot be compared field by field against the derived claim it purports to be.",
  COVERAGE_CLAIM_SET_MISMATCH:
    "The supplied coverage claim set is not exactly the derived claim set, so the rendering would either hide a coverage limitation or add a coverage statement the snapshot never made.",
  COVERAGE_CLAIM_MISMATCH:
    "A supplied coverage claim differs from the claim derived from the snapshot, so the displayed coverage statement is not the one the response actually supports.",
  OPERATION_NOT_DECLARED:
    "The Atlas view may only bind operations the generated OpenAPI client exports, and the requested operation id is not one of them, so the request would target an undeclared route.",
});

export class AtlasViewError extends Error {
  constructor(code, detail, context = {}) {
    super(`${code}: ${detail}`);
    this.name = "AtlasViewError";
    this.code = code;
    this.detail = detail;
    this.reason = ATLAS_FINDING_CODES[code];
    this.context = OBJECT_FREEZE({ ...context });
  }
}

const fail = (code, detail, context = {}) => {
  if (!OBJECT_HAS_OWN(ATLAS_FINDING_CODES, code)) {
    throw new Error(`undeclared Atlas finding code ${code}`);
  }
  throw new AtlasViewError(code, detail, context);
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

/** Key-order independent serialization, so claim comparison is structural. */
const canonicalJson = (value) => {
  if (ARRAY_IS_ARRAY(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
};

const isPlainDataObject = (value) =>
  value !== null &&
  typeof value === "object" &&
  !ARRAY_IS_ARRAY(value) &&
  !IS_PROXY(value) &&
  (OBJECT_GET_PROTOTYPE_OF(value) === PLAIN_OBJECT_PROTOTYPE ||
    OBJECT_GET_PROTOTYPE_OF(value) === null);

const requireFields = (value, label, fields, code) => {
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

const requireArray = (value, label, code) => {
  if (
    !ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== Array.prototype
  ) {
    fail(code, `${label} must be a plain dense array`);
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

const requireString = (value, label, code) => {
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

const requireStringArray = (value, label, code, { unique = true } = {}) => {
  const values = requireArray(value, label, code).map((entry, index) =>
    requireString(entry, `${label}[${index}]`, code),
  );
  if (unique && new Set(values).size !== values.length) {
    fail(code, `${label} contains duplicate entries`);
  }
  return values;
};

const requireCount = (value, label, code) => {
  if (!Number.isSafeInteger(value) || value < 0) {
    fail(code, `${label} must be a non-negative safe integer`);
  }
  return value;
};

const requireHash = (value, label, code) => {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) {
    fail(code, `${label} must match sha256:<64 lowercase hex characters>`);
  }
  return value;
};

const requireUnitOrNull = (value, label, code) => {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
    fail(code, `${label} must be null or a finite number within the closed unit interval`);
  }
  return value;
};

const SNAPSHOT_FIELDS = OBJECT_FREEZE([
  "snapshot_id",
  "insight_id",
  "insight_revision",
  "corpus_snapshot_hash",
  "axes",
  "cells",
  "lens_entropy",
  "dominant_lens",
  "unsearched_scopes",
  "created_at",
  "provenance_manifest_id",
  "search_lane_receipt_ids",
  "bias_risk_register_id",
  "coverage_certificate_hash",
  "effective_independent_evidence_count",
  "stale",
]);
const AXIS_FIELDS = OBJECT_FREEZE(["axis_id", "label", "buckets"]);
const CELL_FIELDS = OBJECT_FREEZE([
  "coordinate",
  "search_state",
  "support_count",
  "counter_count",
  "null_count",
  "boundary_count",
  "method_count",
  "independent_cluster_count",
  "evidence_ids",
  "gap_labels",
]);
const CELL_COUNT_FIELDS = OBJECT_FREEZE([
  "support_count",
  "counter_count",
  "null_count",
  "boundary_count",
  "method_count",
  "independent_cluster_count",
]);
const CLAIM_FIELDS = OBJECT_FREEZE([
  "claim_type",
  "label",
  "status",
  "source_field",
  "value",
  "artifact_hash",
]);

const SEARCH_STATE_SET = new Set(ATLAS_SEARCH_STATES);
const CLAIM_TYPE_SET = new Set(COVERAGE_CLAIM_TYPES);
const CLAIM_STATUS_SET = new Set(COVERAGE_CLAIM_STATUSES);
const CODE = "ATLAS_INPUT_INVALID";

const normalizeAxis = (candidate, index) => {
  const label = `axes[${index}]`;
  const axis = requireFields(candidate, label, AXIS_FIELDS, CODE);
  const buckets = requireStringArray(readValue(axis, "buckets"), `${label}.buckets`, CODE);
  if (buckets.length === 0) fail(CODE, `${label}.buckets must declare at least one bucket`);
  return {
    axis_id: requireString(readValue(axis, "axis_id"), `${label}.axis_id`, CODE),
    label: requireString(readValue(axis, "label"), `${label}.label`, CODE),
    buckets,
  };
};

const normalizeCoordinate = (candidate, label, axes) => {
  if (!isPlainDataObject(candidate)) fail(CODE, `${label} must be a plain data object`);
  const keys = REFLECT_OWN_KEYS(candidate);
  if (keys.length === 0) fail(CODE, `${label} must name at least one axis`);
  const coordinate = {};
  for (const key of keys) {
    if (typeof key !== "string") fail(CODE, `${label} carries a non-string axis key`);
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(candidate, key);
    if (descriptor === undefined || !descriptor.enumerable || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail(CODE, `${label}.${key} must be an enumerable data property`);
    }
    const axis = axes.find((entry) => entry.axis_id === key);
    if (axis === undefined) {
      fail("CELL_COORDINATE_UNDECLARED", `${label} names the undeclared axis ${key}`, {
        axis_id: key,
      });
    }
    const bucket = requireString(descriptor.value, `${label}.${key}`, CODE);
    if (!axis.buckets.includes(bucket)) {
      fail("CELL_COORDINATE_UNDECLARED", `${label}.${key} names the undeclared bucket ${bucket}`, {
        axis_id: key,
        bucket,
      });
    }
    coordinate[key] = bucket;
  }
  for (const axis of axes) {
    if (!OBJECT_HAS_OWN(coordinate, axis.axis_id)) {
      fail("CELL_COORDINATE_UNDECLARED", `${label} omits the declared axis ${axis.axis_id}`, {
        axis_id: axis.axis_id,
      });
    }
  }
  return coordinate;
};

const coordinateKey = (coordinate, axes) =>
  axes.map((axis) => `${axis.axis_id}=${coordinate[axis.axis_id]}`).join("|");

const normalizeCell = (candidate, index, axes) => {
  const label = `cells[${index}]`;
  const cell = requireFields(candidate, label, CELL_FIELDS, CODE);
  const searchState = requireString(
    readValue(cell, "search_state"),
    `${label}.search_state`,
    CODE,
  );
  if (!SEARCH_STATE_SET.has(searchState)) {
    fail("UNKNOWN_SEARCH_STATE", `${label}.search_state is outside the declared vocabulary`, {
      search_state: searchState,
    });
  }
  const coordinate = normalizeCoordinate(readValue(cell, "coordinate"), `${label}.coordinate`, axes);
  const counts = {};
  for (const field of CELL_COUNT_FIELDS) {
    counts[field] = requireCount(readValue(cell, field), `${label}.${field}`, CODE);
  }
  const evidenceIds = requireStringArray(
    readValue(cell, "evidence_ids"),
    `${label}.evidence_ids`,
    CODE,
  );
  const gapLabels = requireStringArray(readValue(cell, "gap_labels"), `${label}.gap_labels`, CODE);
  const countTotal = CELL_COUNT_FIELDS.reduce((total, field) => total + counts[field], 0);
  if (searchState === "UNSEARCHED" && (countTotal !== 0 || evidenceIds.length !== 0)) {
    fail(
      "SEARCH_STATE_CONTRADICTS_COUNTS",
      `${label} declares UNSEARCHED while carrying counted or identified evidence`,
      { coordinate: coordinateKey(coordinate, axes) },
    );
  }
  if (searchState === "SEARCHED_NONE" && (countTotal !== 0 || evidenceIds.length !== 0)) {
    fail(
      "SEARCH_STATE_CONTRADICTS_COUNTS",
      `${label} declares SEARCHED_NONE while carrying counted or identified evidence`,
      { coordinate: coordinateKey(coordinate, axes) },
    );
  }
  if (searchState === "SEARCHED_WITH_RESULTS" && evidenceIds.length === 0) {
    fail(
      "SEARCH_STATE_CONTRADICTS_COUNTS",
      `${label} declares SEARCHED_WITH_RESULTS while carrying no evidence identifier`,
      { coordinate: coordinateKey(coordinate, axes) },
    );
  }
  if (counts.independent_cluster_count > evidenceIds.length) {
    fail(
      "INDEPENDENCE_OVERCLAIM",
      `${label} claims more independent clusters than it carries evidence identifiers`,
      { coordinate: coordinateKey(coordinate, axes) },
    );
  }
  return {
    coordinate,
    coordinate_key: coordinateKey(coordinate, axes),
    search_state: searchState,
    ...counts,
    evidence_ids: evidenceIds,
    gap_labels: gapLabels,
  };
};

/** Validate one `atlas.query` coverage response without repairing it. */
export function validateCoverageSnapshot(candidate) {
  const snapshot = requireFields(candidate, "CoverageSnapshot", SNAPSHOT_FIELDS, CODE);
  const axes = requireArray(readValue(snapshot, "axes"), "axes", CODE).map(normalizeAxis);
  if (axes.length < 2) fail(CODE, "axes must declare at least two dimensions");
  if (new Set(axes.map((axis) => axis.axis_id)).size !== axes.length) {
    fail(CODE, "axes contains duplicate axis identifiers");
  }
  const cells = requireArray(readValue(snapshot, "cells"), "cells", CODE).map((cell, index) =>
    normalizeCell(cell, index, axes),
  );
  const seen = new Set();
  for (const cell of cells) {
    if (seen.has(cell.coordinate_key)) {
      fail("DUPLICATE_CELL_COORDINATE", "two cells occupy the same axis coordinate", {
        coordinate: cell.coordinate_key,
      });
    }
    seen.add(cell.coordinate_key);
  }
  const distinctEvidence = new Set(cells.flatMap((cell) => cell.evidence_ids));
  const independent = readValue(snapshot, "effective_independent_evidence_count");
  if (typeof independent !== "number" || !Number.isFinite(independent) || independent < 0) {
    fail(CODE, "effective_independent_evidence_count must be a finite non-negative number");
  }
  if (independent > distinctEvidence.size) {
    fail(
      "INDEPENDENCE_OVERCLAIM",
      "effective independent evidence exceeds the distinct evidence the snapshot carries",
      { effective: independent, distinct: distinctEvidence.size },
    );
  }
  const stale = readValue(snapshot, "stale");
  if (typeof stale !== "boolean") fail(CODE, "stale must be a boolean");
  const dominantLens = readValue(snapshot, "dominant_lens");
  if (dominantLens !== null) requireString(dominantLens, "dominant_lens", CODE);
  const revision = readValue(snapshot, "insight_revision");
  if (!Number.isSafeInteger(revision) || revision < 1) {
    fail(CODE, "insight_revision must be a safe integer of at least one");
  }
  return deepFreeze({
    snapshot_id: requireString(readValue(snapshot, "snapshot_id"), "snapshot_id", CODE),
    insight_id: requireString(readValue(snapshot, "insight_id"), "insight_id", CODE),
    insight_revision: revision,
    corpus_snapshot_hash: requireHash(
      readValue(snapshot, "corpus_snapshot_hash"),
      "corpus_snapshot_hash",
      CODE,
    ),
    axes,
    cells,
    lens_entropy: requireUnitOrNull(readValue(snapshot, "lens_entropy"), "lens_entropy", CODE),
    dominant_lens: dominantLens,
    unsearched_scopes: requireStringArray(
      readValue(snapshot, "unsearched_scopes"),
      "unsearched_scopes",
      CODE,
    ),
    created_at: requireString(readValue(snapshot, "created_at"), "created_at", CODE),
    provenance_manifest_id: requireString(
      readValue(snapshot, "provenance_manifest_id"),
      "provenance_manifest_id",
      CODE,
    ),
    search_lane_receipt_ids: requireStringArray(
      readValue(snapshot, "search_lane_receipt_ids"),
      "search_lane_receipt_ids",
      CODE,
    ),
    bias_risk_register_id: requireString(
      readValue(snapshot, "bias_risk_register_id"),
      "bias_risk_register_id",
      CODE,
    ),
    coverage_certificate_hash: requireHash(
      readValue(snapshot, "coverage_certificate_hash"),
      "coverage_certificate_hash",
      CODE,
    ),
    effective_independent_evidence_count: independent,
    stale,
    distinct_evidence_count: distinctEvidence.size,
  });
}

const searchStateDistribution = (snapshot) => {
  const distribution = {};
  for (const state of ATLAS_SEARCH_STATES) distribution[state] = 0;
  for (const cell of snapshot.cells) distribution[cell.search_state] += 1;
  return distribution;
};

const axisCellCoverage = (snapshot) => {
  const declared = snapshot.axes.reduce((total, axis) => total * axis.buckets.length, 1);
  return {
    declared_cell_count: declared,
    present_cell_count: snapshot.cells.length,
    missing_cell_count: declared - snapshot.cells.length,
  };
};

const claimsFrom = (snapshot) => {
  const distribution = searchStateDistribution(snapshot);
  const cellCoverage = axisCellCoverage(snapshot);
  const gridComplete = cellCoverage.missing_cell_count === 0;
  const searched = distribution.SEARCHED_NONE + distribution.SEARCHED_WITH_RESULTS;
  const claim = (claimType, label, status, sourceField, value) => ({
    claim_type: claimType,
    label,
    status,
    source_field: sourceField,
    value,
    artifact_hash: snapshot.coverage_certificate_hash,
  });
  return deepFreeze([
    claim(
      "SEARCH_STATE_DISTRIBUTION",
      "Search state by cell",
      searched === snapshot.cells.length && snapshot.cells.length > 0 ? "MEASURED" : "PARTIAL",
      "cells[].search_state",
      distribution,
    ),
    claim(
      "AXIS_CELL_COVERAGE",
      "Declared axis cells present in this snapshot",
      gridComplete ? "MEASURED" : "PARTIAL",
      "axes[].buckets",
      cellCoverage,
    ),
    claim(
      "UNSEARCHED_SCOPES",
      "Scopes the snapshot records as unsearched",
      snapshot.unsearched_scopes.length === 0 ? "MEASURED" : "PARTIAL",
      "unsearched_scopes",
      [...snapshot.unsearched_scopes],
    ),
    claim(
      "EVIDENCE_INDEPENDENCE",
      "Effectively independent evidence",
      "MEASURED",
      "effective_independent_evidence_count",
      {
        effective_independent_evidence_count: snapshot.effective_independent_evidence_count,
        distinct_evidence_count: snapshot.distinct_evidence_count,
      },
    ),
    claim(
      "LENS_CONCENTRATION",
      "Lens concentration",
      snapshot.lens_entropy === null ? "NOT_COMPUTED" : "MEASURED",
      "lens_entropy",
      { lens_entropy: snapshot.lens_entropy, dominant_lens: snapshot.dominant_lens },
    ),
    claim(
      "SNAPSHOT_FRESHNESS",
      "Snapshot freshness",
      "MEASURED",
      "stale",
      { stale: snapshot.stale },
    ),
  ]);
};

/** Derive the closed display-claim set the snapshot actually supports. */
export function buildCoverageClaims(candidate) {
  return claimsFrom(validateCoverageSnapshot(candidate));
}

const normalizeClaim = (candidate, index) => {
  const label = `claims[${index}]`;
  const supplied = requireFields(candidate, label, CLAIM_FIELDS, "INVALID_COVERAGE_CLAIM");
  const claimType = requireString(
    readValue(supplied, "claim_type"),
    `${label}.claim_type`,
    "INVALID_COVERAGE_CLAIM",
  );
  if (!CLAIM_TYPE_SET.has(claimType)) {
    fail("UNKNOWN_COVERAGE_CLAIM_TYPE", `${label}.claim_type is outside the closed vocabulary`, {
      claim_type: claimType,
    });
  }
  const status = requireString(
    readValue(supplied, "status"),
    `${label}.status`,
    "INVALID_COVERAGE_CLAIM",
  );
  if (!CLAIM_STATUS_SET.has(status)) {
    fail("UNKNOWN_COVERAGE_CLAIM_STATUS", `${label}.status is outside the closed vocabulary`, {
      status,
    });
  }
  return {
    claim_type: claimType,
    label: requireString(readValue(supplied, "label"), `${label}.label`, "INVALID_COVERAGE_CLAIM"),
    status,
    source_field: requireString(
      readValue(supplied, "source_field"),
      `${label}.source_field`,
      "INVALID_COVERAGE_CLAIM",
    ),
    value: readValue(supplied, "value"),
    artifact_hash: requireHash(
      readValue(supplied, "artifact_hash"),
      `${label}.artifact_hash`,
      "INVALID_COVERAGE_CLAIM",
    ),
  };
};

/** Refuse any displayed coverage claim the snapshot does not carry. */
export function auditCoverageClaims(candidate) {
  const input = requireFields(
    candidate,
    "CoverageClaimAuditInput",
    ["snapshot", "claims"],
    "INVALID_COVERAGE_CLAIM",
  );
  const snapshot = validateCoverageSnapshot(readValue(input, "snapshot"));
  const expected = claimsFrom(snapshot);
  const observed = requireArray(
    readValue(input, "claims"),
    "claims",
    "INVALID_COVERAGE_CLAIM",
  ).map(normalizeClaim);
  if (observed.length !== expected.length) {
    fail("COVERAGE_CLAIM_SET_MISMATCH", "the displayed claim set is not the derived claim set", {
      expected_count: expected.length,
      observed_count: observed.length,
    });
  }
  const observedTypes = observed.map((entry) => entry.claim_type);
  if (new Set(observedTypes).size !== observedTypes.length) {
    fail("COVERAGE_CLAIM_SET_MISMATCH", "coverage claim types must be unique");
  }
  for (let index = 0; index < expected.length; index += 1) {
    if (canonicalJson(observed[index]) !== canonicalJson(expected[index])) {
      fail("COVERAGE_CLAIM_MISMATCH", "a displayed coverage claim is not the derived claim", {
        claim_type: expected[index].claim_type,
        expected: expected[index],
        observed: observed[index],
      });
    }
  }
  return deepFreeze({
    status: "PASS",
    version: ATLAS_VIEW_VERSION,
    claim_count: expected.length,
    claim_types: [...COVERAGE_CLAIM_TYPES],
    snapshot_id: snapshot.snapshot_id,
    coverage_certificate_hash: snapshot.coverage_certificate_hash,
    corpus_snapshot_hash: snapshot.corpus_snapshot_hash,
  });
}

/** Build the Atlas read model from one coverage response. */
export function buildAtlasView(candidate) {
  const snapshot = validateCoverageSnapshot(candidate);
  const claims = claimsFrom(snapshot);
  auditCoverageClaims({ snapshot: candidate, claims });
  const distribution = searchStateDistribution(snapshot);
  const cellCoverage = axisCellCoverage(snapshot);
  const limited =
    cellCoverage.missing_cell_count !== 0 ||
    distribution.UNSEARCHED !== 0 ||
    distribution.PARTIAL !== 0 ||
    snapshot.unsearched_scopes.length !== 0 ||
    snapshot.stale;
  const gaps = snapshot.cells
    .filter((cell) => cell.search_state !== "SEARCHED_WITH_RESULTS" || cell.gap_labels.length > 0)
    .map((cell) => ({
      coordinate_key: cell.coordinate_key,
      search_state: cell.search_state,
      gap_labels: [...cell.gap_labels],
    }));
  return deepFreeze({
    kind: "EpistemicFoundryAtlasView",
    version: ATLAS_VIEW_VERSION,
    heading: "Evidence atlas",
    atlas_identity: {
      snapshot_id: snapshot.snapshot_id,
      insight_id: snapshot.insight_id,
      insight_revision: snapshot.insight_revision,
      created_at: snapshot.created_at,
    },
    source_receipt: {
      corpus_snapshot_hash: snapshot.corpus_snapshot_hash,
      coverage_certificate_hash: snapshot.coverage_certificate_hash,
      provenance_manifest_id: snapshot.provenance_manifest_id,
      bias_risk_register_id: snapshot.bias_risk_register_id,
      search_lane_receipt_ids: [...snapshot.search_lane_receipt_ids],
      operation_ids: [...ATLAS_OPERATION_IDS],
    },
    coverage_state: limited ? "VISIBLE_LIMITATIONS" : "COMPLETE_FOR_DECLARED_SCOPE",
    search_state_distribution: distribution,
    cell_coverage: cellCoverage,
    unsearched_scopes: [...snapshot.unsearched_scopes],
    stale: snapshot.stale,
    coverage_claims: claims,
    axes: snapshot.axes,
    cells: snapshot.cells,
    gaps,
    sections: [
      {
        id: "coverage-and-search-state",
        title: "Coverage and search state",
        state: limited ? "VISIBLE_LIMITATIONS" : "COMPLETE_FOR_DECLARED_SCOPE",
        visible: true,
      },
      {
        id: "unsearched-and-gaps",
        title: "Unsearched scopes and gaps",
        state: gaps.length || snapshot.unsearched_scopes.length ? "POPULATED" : "NONE_RECORDED",
        visible: true,
      },
      {
        id: "coverage-claims",
        title: "Coverage claims and their sources",
        state: "VERIFIED",
        visible: true,
      },
      {
        id: "atlas-cells",
        title: "Atlas cells",
        state: snapshot.cells.length ? "POPULATED" : "EMPTY_CONFIRMED",
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
    : `<p class="atlas-empty">${escapeHtml(emptyText)}</p>`;

/** Render the Atlas panel; every untrusted string is escaped. */
export function renderAtlasPanel(candidate) {
  const view = buildAtlasView(candidate);
  return [
    `<main class="atlas" data-atlas-version="${escapeHtml(view.version)}">`,
    `<header><h1>${escapeHtml(view.heading)}</h1><p>${escapeHtml(
      view.atlas_identity.insight_id,
    )} revision ${escapeHtml(view.atlas_identity.insight_revision)}</p></header>`,
    `<section class="atlas-coverage" data-section="coverage-and-search-state" data-state="${escapeHtml(
      view.coverage_state,
    )}"><h2>Coverage and search state</h2><dl>`,
    ATLAS_SEARCH_STATES.map(
      (state) =>
        `<dt>${escapeHtml(state)}</dt><dd>${escapeHtml(view.search_state_distribution[state])}</dd>`,
    ).join(""),
    `<dt>Declared cells</dt><dd>${escapeHtml(view.cell_coverage.declared_cell_count)}</dd>`,
    `<dt>Present cells</dt><dd>${escapeHtml(view.cell_coverage.present_cell_count)}</dd>`,
    `<dt>Missing cells</dt><dd>${escapeHtml(view.cell_coverage.missing_cell_count)}</dd>`,
    `<dt>Stale</dt><dd>${escapeHtml(String(view.stale))}</dd></dl></section>`,
    '<section class="atlas-gaps" data-section="unsearched-and-gaps"><h2>Unsearched scopes and gaps</h2>',
    renderList(view.unsearched_scopes, "No unsearched scope was recorded.", (scope) =>
      escapeHtml(scope),
    ),
    renderList(
      view.gaps,
      "No cell gap was recorded.",
      (gap) =>
        `<code>${escapeHtml(gap.coordinate_key)}</code> <span>${escapeHtml(
          gap.search_state,
        )}</span> <span>${escapeHtml(gap.gap_labels.join(", "))}</span>`,
    ),
    "</section>",
    '<section class="atlas-claims" data-section="coverage-claims"><h2>Coverage claims and their sources</h2>',
    renderList(
      view.coverage_claims,
      "No coverage claim is displayable.",
      (claim) =>
        `<strong>${escapeHtml(claim.label)}</strong> <span>${escapeHtml(
          claim.status,
        )}</span> <code>${escapeHtml(claim.source_field)}</code> <code>${escapeHtml(
          claim.artifact_hash,
        )}</code>`,
    ),
    "</section>",
    '<section class="atlas-cells" data-section="atlas-cells"><h2>Atlas cells</h2>',
    renderList(
      view.cells,
      "This snapshot carries no cell.",
      (cell) =>
        `<code>${escapeHtml(cell.coordinate_key)}</code> <span>${escapeHtml(
          cell.search_state,
        )}</span> <span>support ${escapeHtml(cell.support_count)}</span> <span>counter ${escapeHtml(
          cell.counter_count,
        )}</span> <span>null ${escapeHtml(cell.null_count)}</span>`,
    ),
    "</section></main>",
  ].join("");
}

const requireDeclaredOperation = (operationId) => {
  if (!ATLAS_OPERATION_IDS.includes(operationId) || !OBJECT_HAS_OWN(OPERATIONS, operationId)) {
    fail("OPERATION_NOT_DECLARED", `${operationId} is not an Atlas-bindable declared operation`, {
      operation_id: operationId,
    });
  }
};

/** Bind `GET /coverage-snapshots/{id}` through the generated client only. */
export function atlasSnapshotRequest({ snapshot_id: snapshotId }, transport) {
  requireDeclaredOperation("getCoverageSnapshot");
  requireString(snapshotId, "snapshot_id", CODE);
  return getCoverageSnapshot({ path: { coverage_snapshot_id: snapshotId } }, transport);
}

/** Bind `POST /retrieval-runs` (the declared Atlas query entry) through the client. */
export function atlasQueryRequest({ query_plan: queryPlan }, transport) {
  requireDeclaredOperation("createRetrievalRun");
  if (!isPlainDataObject(queryPlan)) fail(CODE, "query_plan must be a plain data object");
  return createRetrievalRun({ body: queryPlan }, transport);
}
