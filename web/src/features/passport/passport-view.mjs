/**
 * U03 Hypothesis Passport read model.
 *
 * A passport revision is an immutable record.  This view renders one revision
 * with its verdict, its stability, its falsifiers and its next test all visible
 * at once, and it refuses two specific temptations:
 *
 *   - a rendering that hides a counter-evidence field - the strongest
 *     counter-evidence, the unresolved objections, the minority report, or the
 *     staleness reasons - fails with `COUNTER_EVIDENCE_HIDDEN`;
 *   - an affordance record that offers to edit, overwrite, or delete a
 *     published revision fails with `IMMUTABLE_REVISION_EDIT_AFFORDANCE`,
 *     because a revision is superseded by a new revision, never rewritten.
 *
 * The seven confidence dimensions stay seven dimensions; an aggregate display
 * field that would collapse them into one number is refused.
 *
 * Declaring sources:
 *   - `schemas/hypothesis-passport.schema.json` (field set and vocabularies)
 *   - `web/src/generated/ui-client/index.mjs` (the only route binding allowed)
 *
 * The canonical OpenAPI document declares exactly one passport operation,
 * `getPassport`; it declares no passport publish, patch, or delete route, so no
 * write affordance can be bound here even if a caller asked for one.
 *
 * The module reads no clock, no random source, no environment and no file.
 */

import { types as utilTypes } from "node:util";

import { OPERATIONS, getPassport } from "../../generated/ui-client/index.mjs";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;

export const PASSPORT_VIEW_VERSION = "4.0.0-u03.1";

/** `schemas/hypothesis-passport.schema.json` `epistemic_status`. */
export const EPISTEMIC_STATUSES = OBJECT_FREEZE([
  "ENTAILED",
  "SUPPORTED",
  "CONDITIONAL",
  "MIXED",
  "CONTRADICTED",
  "UNDERDETERMINED",
  "UNTESTABLE",
]);

/** `schemas/hypothesis-passport.schema.json` `causal_status`. */
export const CAUSAL_STATUSES = OBJECT_FREEZE([
  "IDENTIFIED",
  "ASSUMPTION_DEPENDENT",
  "NOT_IDENTIFIED",
  "NOT_APPLICABLE",
]);

/** `schemas/hypothesis-passport.schema.json` `novelty_status`. */
export const NOVELTY_STATUSES = OBJECT_FREEZE([
  "PRIOR_ART_FOUND",
  "CORPUS_NOVEL",
  "NOT_FOUND_WITHIN_SEARCH_SCOPE",
  "NOT_ASSESSED",
]);

/** `schemas/hypothesis-passport.schema.json` `promotion_level`. */
export const PROMOTION_LEVELS = OBJECT_FREEZE([
  "INBOX",
  "CANDIDATE",
  "LITERATURE_GROUNDED",
  "VALIDATION_SCREENED",
  "EMPIRICALLY_TESTED",
  "REPLICATED",
]);

/** `schemas/hypothesis-passport.schema.json` `search_completeness`. */
export const SEARCH_COMPLETENESS_STATES = OBJECT_FREEZE([
  "COMPLETE_FOR_POLICY",
  "PARTIAL",
  "BLOCKED",
  "NOT_ASSESSED",
]);

/** `schemas/hypothesis-passport.schema.json` `lifecycle_status`. */
export const LIFECYCLE_STATUSES = OBJECT_FREEZE(["active", "stale", "withdrawn", "superseded"]);

/** `schemas/hypothesis-passport.schema.json` `epistemic_assessment.calibration_status`. */
export const CALIBRATION_STATUSES = OBJECT_FREEZE([
  "CALIBRATED",
  "UNCALIBRATED",
  "INSUFFICIENT_DATA",
]);

/** `schemas/hypothesis-passport.schema.json` `reasoning_modes`. */
export const REASONING_MODES = OBJECT_FREEZE([
  "deductive",
  "inductive",
  "abductive",
  "causal",
  "mechanistic",
  "computational",
  "formal",
  "simulation",
]);

/** The seven confidence dimensions, which stay seven dimensions. */
export const CONFIDENCE_DIMENSIONS = OBJECT_FREEZE([
  "grounding",
  "directness",
  "independence",
  "scope_match",
  "method_validity",
  "causal_identifiability",
  "testability",
]);

/** The six scored assessment dimensions plus the calibration status. */
export const ASSESSMENT_DIMENSIONS = OBJECT_FREEZE([
  "grounding",
  "evidence_sufficiency",
  "consistency",
  "method_fitness",
  "scope_transportability",
  "falsifiability",
]);

/** Counter-evidence fields a rendering may never drop. */
export const COUNTER_EVIDENCE_FIELDS = OBJECT_FREEZE([
  "minority_report_id",
  "stale_reasons",
  "strongest_counterevidence_id",
  "unresolved_objection_ids",
]);

/** Affordances a published revision may offer. */
export const PASSPORT_AFFORDANCES = OBJECT_FREEZE([
  "COPY_IDENTIFIER",
  "OPEN_EVIDENCE_PACK",
  "OPEN_MINORITY_REPORT",
  "OPEN_NEXT_EXPERIMENT_TICKET",
  "READ_REVISION",
  "REQUEST_NEW_REVISION",
]);

/** Affordances that would mutate a published revision in place. */
export const MUTATING_AFFORDANCES = OBJECT_FREEZE([
  "DELETE_REVISION",
  "EDIT_FIELD",
  "EDIT_VERDICT",
  "INLINE_EDIT",
  "OVERWRITE_REVISION",
  "RETRACT_IN_PLACE",
]);

/** Display fields that would collapse the separate dimensions into one score. */
export const AGGREGATE_DISPLAY_FIELDS = OBJECT_FREEZE([
  "composite_confidence",
  "confidence_score",
  "overall_confidence",
  "overall_score",
  "single_score",
]);

/** Operation ids from the generated client this view is permitted to bind. */
export const PASSPORT_OPERATION_IDS = OBJECT_FREEZE(["getPassport"]);

export const PASSPORT_FINDING_CODES = OBJECT_FREEZE({
  PASSPORT_INPUT_INVALID:
    "The passport revision handed to the view is not a plain data object carrying exactly the field set the hypothesis-passport schema declares, so no field could be read without guessing what the caller meant.",
  UNKNOWN_PASSPORT_VOCABULARY:
    "A passport status field carries a value outside the canonical vocabulary its schema declares, so the rendered verdict, causal status, or lifecycle state would not be one the contract defines.",
  COUNTER_EVIDENCE_HIDDEN:
    "The rendering omits a counter-evidence field the revision carries, and a passport panel that hides its strongest counter-evidence, unresolved objections, minority report, or staleness reasons misrepresents the record.",
  REQUIRED_FIELD_HIDDEN:
    "The rendering omits a field the passport panel must always show, so the verdict, stability, falsifiers, or next test would be absent from a surface whose whole purpose is to display them together.",
  UNKNOWN_DISPLAY_FIELD:
    "The rendering names a display field the passport schema does not declare, so the panel would present a value that has no canonical field behind it.",
  CONFIDENCE_AGGREGATED:
    "The rendering names an aggregate confidence field, but the seven confidence dimensions are kept separate on purpose and collapsing them into one number would hide which dimension is weak.",
  UNKNOWN_AFFORDANCE:
    "The affordance record names an interaction outside the declared vocabulary, so the panel cannot tell whether the offered control would read the revision or change it.",
  IMMUTABLE_REVISION_EDIT_AFFORDANCE:
    "The affordance record offers to edit, overwrite, or delete a published passport revision, but a revision is immutable and is superseded by a new revision rather than rewritten in place.",
  REVISION_MISMATCH:
    "The rendering declares a revision number that is not the revision the passport carries, so the panel would attribute this evidence and this verdict to a different revision of the hypothesis.",
  OPERATION_NOT_DECLARED:
    "The Passport view may only bind operations the generated OpenAPI client exports, and the requested operation id is not one of them; the canonical document declares no passport write route at all.",
});

export class PassportViewError extends Error {
  constructor(code, detail, context = {}) {
    super(`${code}: ${detail}`);
    this.name = "PassportViewError";
    this.code = code;
    this.detail = detail;
    this.reason = PASSPORT_FINDING_CODES[code];
    this.context = OBJECT_FREEZE({ ...context });
  }
}

const fail = (code, detail, context = {}) => {
  if (!OBJECT_HAS_OWN(PASSPORT_FINDING_CODES, code)) {
    throw new Error(`undeclared Passport finding code ${code}`);
  }
  throw new PassportViewError(code, detail, context);
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

const CODE = "PASSPORT_INPUT_INVALID";

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

const requireStringArray = (value, label, code = CODE) => {
  const values = requireArray(value, label, code).map((entry, index) =>
    requireString(entry, `${label}[${index}]`, code),
  );
  if (new Set(values).size !== values.length) fail(code, `${label} contains duplicate entries`);
  return values;
};

const requireNullableString = (value, label) =>
  value === null ? null : requireString(value, label);

const requireMember = (value, label, vocabulary) => {
  const text = requireString(value, label);
  if (!vocabulary.includes(text)) {
    fail("UNKNOWN_PASSPORT_VOCABULARY", `${label} is outside the canonical vocabulary`, {
      field: label,
      value: text,
    });
  }
  return text;
};

const requireUnit = (value, label) => {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
    fail(CODE, `${label} must be a finite number within the closed unit interval`);
  }
  return value;
};

const PASSPORT_FIELDS = OBJECT_FREEZE([
  "hypothesis_id",
  "revision",
  "canonical_statement",
  "scope",
  "reasoning_modes",
  "mechanism_chain",
  "prediction_ids",
  "falsifier_ids",
  "evidence_pack_id",
  "strongest_counterevidence_id",
  "unresolved_objection_ids",
  "epistemic_status",
  "causal_status",
  "novelty_status",
  "promotion_level",
  "confidence_vector",
  "minority_report_id",
  "next_experiment_ticket_id",
  "run_id",
  "attestation_id",
  "provenance_manifest_id",
  "epistemic_assessment",
  "bias_risk_register_id",
  "decision_stability_report_id",
  "search_completeness",
  "human_decision_ids",
  "lifecycle_status",
  "stale_reasons",
]);
const PRESENTATION_FIELDS = OBJECT_FREEZE(["revision", "visible_fields", "affordances"]);
const INPUT_FIELDS = OBJECT_FREEZE(["passport", "presentation"]);

/** Every display field name a Passport rendering may name. */
export const PASSPORT_DISPLAY_FIELDS = OBJECT_FREEZE(
  [
    ...PASSPORT_FIELDS,
    ...CONFIDENCE_DIMENSIONS.map((dimension) => `confidence_vector.${dimension}`),
    ...ASSESSMENT_DIMENSIONS.map((dimension) => `epistemic_assessment.${dimension}`),
    "epistemic_assessment.calibration_status",
  ].sort(),
);

/** Display fields the Passport panel must always show. */
export const REQUIRED_VISIBLE_FIELDS = OBJECT_FREEZE(
  [
    ...COUNTER_EVIDENCE_FIELDS,
    "canonical_statement",
    "causal_status",
    "decision_stability_report_id",
    "epistemic_assessment.calibration_status",
    "epistemic_status",
    "falsifier_ids",
    "lifecycle_status",
    "next_experiment_ticket_id",
    "novelty_status",
    "prediction_ids",
    "promotion_level",
    "revision",
    "search_completeness",
    ...CONFIDENCE_DIMENSIONS.map((dimension) => `confidence_vector.${dimension}`),
  ].sort(),
);

const normalizeConfidenceVector = (candidate) => {
  const vector = requireFields(candidate, "confidence_vector", CONFIDENCE_DIMENSIONS);
  const normalized = {};
  for (const dimension of CONFIDENCE_DIMENSIONS) {
    normalized[dimension] = requireUnit(
      readValue(vector, dimension),
      `confidence_vector.${dimension}`,
    );
  }
  return normalized;
};

const normalizeAssessment = (candidate) => {
  const assessment = requireFields(candidate, "epistemic_assessment", [
    ...ASSESSMENT_DIMENSIONS,
    "calibration_status",
  ]);
  const normalized = {};
  for (const dimension of ASSESSMENT_DIMENSIONS) {
    normalized[dimension] = requireUnit(
      readValue(assessment, dimension),
      `epistemic_assessment.${dimension}`,
    );
  }
  normalized.calibration_status = requireMember(
    readValue(assessment, "calibration_status"),
    "epistemic_assessment.calibration_status",
    CALIBRATION_STATUSES,
  );
  return normalized;
};

/** Validate one immutable passport revision without repairing it. */
export function validateHypothesisPassport(candidate) {
  const passport = requireFields(candidate, "HypothesisPassport", PASSPORT_FIELDS);
  const revision = readValue(passport, "revision");
  if (!Number.isSafeInteger(revision) || revision < 1) {
    fail(CODE, "revision must be a safe integer of at least one");
  }
  const statement = requireString(readValue(passport, "canonical_statement"), "canonical_statement");
  if (statement.length < 10) fail(CODE, "canonical_statement must carry at least ten characters");
  const scope = readValue(passport, "scope");
  if (!isPlainDataObject(scope)) fail(CODE, "scope must be a plain data object");
  const reasoningModes = requireStringArray(
    readValue(passport, "reasoning_modes"),
    "reasoning_modes",
  );
  if (reasoningModes.length === 0) fail(CODE, "reasoning_modes must carry at least one mode");
  for (const mode of reasoningModes) requireMember(mode, "reasoning_modes[]", REASONING_MODES);
  const predictionIds = requireStringArray(readValue(passport, "prediction_ids"), "prediction_ids");
  if (predictionIds.length === 0) fail(CODE, "prediction_ids must carry at least one prediction");
  const falsifierIds = requireStringArray(readValue(passport, "falsifier_ids"), "falsifier_ids");
  if (falsifierIds.length === 0) fail(CODE, "falsifier_ids must carry at least one falsifier");
  return deepFreeze({
    hypothesis_id: requireString(readValue(passport, "hypothesis_id"), "hypothesis_id"),
    revision,
    canonical_statement: statement,
    scope: { ...scope },
    reasoning_modes: reasoningModes,
    mechanism_chain: requireStringArray(
      readValue(passport, "mechanism_chain"),
      "mechanism_chain",
    ),
    prediction_ids: predictionIds,
    falsifier_ids: falsifierIds,
    evidence_pack_id: requireString(readValue(passport, "evidence_pack_id"), "evidence_pack_id"),
    strongest_counterevidence_id: requireNullableString(
      readValue(passport, "strongest_counterevidence_id"),
      "strongest_counterevidence_id",
    ),
    unresolved_objection_ids: requireStringArray(
      readValue(passport, "unresolved_objection_ids"),
      "unresolved_objection_ids",
    ),
    epistemic_status: requireMember(
      readValue(passport, "epistemic_status"),
      "epistemic_status",
      EPISTEMIC_STATUSES,
    ),
    causal_status: requireMember(
      readValue(passport, "causal_status"),
      "causal_status",
      CAUSAL_STATUSES,
    ),
    novelty_status: requireMember(
      readValue(passport, "novelty_status"),
      "novelty_status",
      NOVELTY_STATUSES,
    ),
    promotion_level: requireMember(
      readValue(passport, "promotion_level"),
      "promotion_level",
      PROMOTION_LEVELS,
    ),
    confidence_vector: normalizeConfidenceVector(readValue(passport, "confidence_vector")),
    minority_report_id: requireNullableString(
      readValue(passport, "minority_report_id"),
      "minority_report_id",
    ),
    next_experiment_ticket_id: requireNullableString(
      readValue(passport, "next_experiment_ticket_id"),
      "next_experiment_ticket_id",
    ),
    run_id: requireString(readValue(passport, "run_id"), "run_id"),
    attestation_id: requireString(readValue(passport, "attestation_id"), "attestation_id"),
    provenance_manifest_id: requireString(
      readValue(passport, "provenance_manifest_id"),
      "provenance_manifest_id",
    ),
    epistemic_assessment: normalizeAssessment(readValue(passport, "epistemic_assessment")),
    bias_risk_register_id: requireString(
      readValue(passport, "bias_risk_register_id"),
      "bias_risk_register_id",
    ),
    decision_stability_report_id: requireString(
      readValue(passport, "decision_stability_report_id"),
      "decision_stability_report_id",
    ),
    search_completeness: requireMember(
      readValue(passport, "search_completeness"),
      "search_completeness",
      SEARCH_COMPLETENESS_STATES,
    ),
    human_decision_ids: requireStringArray(
      readValue(passport, "human_decision_ids"),
      "human_decision_ids",
    ),
    lifecycle_status: requireMember(
      readValue(passport, "lifecycle_status"),
      "lifecycle_status",
      LIFECYCLE_STATUSES,
    ),
    stale_reasons: requireStringArray(readValue(passport, "stale_reasons"), "stale_reasons"),
  });
}

const normalizePresentation = (candidate) => {
  const presentation = requireFields(candidate, "presentation", PRESENTATION_FIELDS);
  const revision = readValue(presentation, "revision");
  if (!Number.isSafeInteger(revision) || revision < 1) {
    fail(CODE, "presentation.revision must be a safe integer of at least one");
  }
  const visibleFields = requireStringArray(
    readValue(presentation, "visible_fields"),
    "presentation.visible_fields",
  );
  for (const field of visibleFields) {
    if (AGGREGATE_DISPLAY_FIELDS.includes(field)) {
      fail("CONFIDENCE_AGGREGATED", "an aggregate confidence field may not be displayed", {
        field,
      });
    }
    if (!PASSPORT_DISPLAY_FIELDS.includes(field)) {
      fail("UNKNOWN_DISPLAY_FIELD", "the rendering names an undeclared display field", { field });
    }
  }
  const affordances = requireStringArray(
    readValue(presentation, "affordances"),
    "presentation.affordances",
  );
  for (const affordance of affordances) {
    if (MUTATING_AFFORDANCES.includes(affordance)) {
      fail(
        "IMMUTABLE_REVISION_EDIT_AFFORDANCE",
        "a published passport revision may not offer an in-place edit affordance",
        { affordance, revision },
      );
    }
    if (!PASSPORT_AFFORDANCES.includes(affordance)) {
      fail("UNKNOWN_AFFORDANCE", "the affordance record names an undeclared interaction", {
        affordance,
      });
    }
  }
  return { revision, visible_fields: visibleFields, affordances };
};

/** Validate the revision and the rendering the caller proposes for it. */
export function validatePassportInput(candidate) {
  const input = requireFields(candidate, "PassportViewInput", INPUT_FIELDS);
  const passport = validateHypothesisPassport(readValue(input, "passport"));
  const presentation = normalizePresentation(readValue(input, "presentation"));
  if (presentation.revision !== passport.revision) {
    fail("REVISION_MISMATCH", "the rendering declares a revision the passport does not carry", {
      expected: passport.revision,
      observed: presentation.revision,
    });
  }
  for (const field of COUNTER_EVIDENCE_FIELDS) {
    if (!presentation.visible_fields.includes(field)) {
      fail("COUNTER_EVIDENCE_HIDDEN", "the rendering hides a counter-evidence field", { field });
    }
  }
  for (const field of REQUIRED_VISIBLE_FIELDS) {
    if (!presentation.visible_fields.includes(field)) {
      fail("REQUIRED_FIELD_HIDDEN", "the rendering hides a field the panel must always show", {
        field,
      });
    }
  }
  return deepFreeze({ passport, presentation });
}

/** Build the Passport read model for one immutable revision. */
export function buildPassportView(candidate) {
  const input = validatePassportInput(candidate);
  const passport = input.passport;
  const counterEvidence = {
    strongest_counterevidence_id: passport.strongest_counterevidence_id,
    strongest_counterevidence_state:
      passport.strongest_counterevidence_id === null ? "NONE_RECORDED" : "RECORDED",
    unresolved_objection_ids: [...passport.unresolved_objection_ids],
    minority_report_id: passport.minority_report_id,
    minority_report_state: passport.minority_report_id === null ? "NONE_RECORDED" : "PRESERVED",
    stale_reasons: [...passport.stale_reasons],
  };
  return deepFreeze({
    kind: "EpistemicFoundryPassportView",
    version: PASSPORT_VIEW_VERSION,
    heading: "Hypothesis passport",
    passport_identity: {
      hypothesis_id: passport.hypothesis_id,
      revision: passport.revision,
      run_id: passport.run_id,
      immutability: "IMMUTABLE_REVISION",
    },
    source_receipt: {
      attestation_id: passport.attestation_id,
      provenance_manifest_id: passport.provenance_manifest_id,
      evidence_pack_id: passport.evidence_pack_id,
      bias_risk_register_id: passport.bias_risk_register_id,
      decision_stability_report_id: passport.decision_stability_report_id,
      operation_ids: [...PASSPORT_OPERATION_IDS],
    },
    statement: passport.canonical_statement,
    scope: passport.scope,
    reasoning_modes: [...passport.reasoning_modes],
    verdict: {
      epistemic_status: passport.epistemic_status,
      causal_status: passport.causal_status,
      novelty_status: passport.novelty_status,
      promotion_level: passport.promotion_level,
      basis: "PASSPORT_REVISION_RECORD",
    },
    stability: {
      decision_stability_report_id: passport.decision_stability_report_id,
      calibration_status: passport.epistemic_assessment.calibration_status,
      lifecycle_status: passport.lifecycle_status,
      search_completeness: passport.search_completeness,
      stale_reasons: [...passport.stale_reasons],
      state: passport.stale_reasons.length ? "STALENESS_RECORDED" : "NO_STALENESS_RECORDED",
    },
    falsifiers: {
      falsifier_ids: [...passport.falsifier_ids],
      prediction_ids: [...passport.prediction_ids],
      mechanism_chain: [...passport.mechanism_chain],
    },
    next_test: {
      next_experiment_ticket_id: passport.next_experiment_ticket_id,
      state: passport.next_experiment_ticket_id === null ? "NOT_SCHEDULED" : "SCHEDULED",
    },
    counter_evidence: counterEvidence,
    confidence_vector: passport.confidence_vector,
    epistemic_assessment: passport.epistemic_assessment,
    human_decision_ids: [...passport.human_decision_ids],
    affordances: [...input.presentation.affordances],
    visible_fields: [...input.presentation.visible_fields].sort(),
    sections: [
      { id: "verdict", title: "Verdict", state: "VERIFIED", visible: true },
      {
        id: "counter-evidence",
        title: "Counter-evidence and dissent",
        state:
          counterEvidence.strongest_counterevidence_id !== null ||
          counterEvidence.unresolved_objection_ids.length ||
          counterEvidence.minority_report_id !== null
            ? "POPULATED"
            : "NONE_RECORDED",
        visible: true,
      },
      {
        id: "stability",
        title: "Stability",
        state: passport.stale_reasons.length ? "STALENESS_RECORDED" : "NO_STALENESS_RECORDED",
        visible: true,
      },
      {
        id: "falsifiers-and-next-test",
        title: "Falsifiers and next test",
        state: passport.next_experiment_ticket_id === null ? "NOT_SCHEDULED" : "SCHEDULED",
        visible: true,
      },
      {
        id: "confidence-dimensions",
        title: "Confidence dimensions",
        state: "SEPARATE_DIMENSIONS",
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

const displayNullable = (value) => (value === null ? "not recorded" : String(value));

const renderList = (items, emptyText, renderItem) =>
  items.length
    ? `<ol>${items.map((item) => `<li>${renderItem(item)}</li>`).join("")}</ol>`
    : `<p class="passport-empty">${escapeHtml(emptyText)}</p>`;

/** Render the Passport panel; counter-evidence sits beside the verdict. */
export function renderPassportPanel(candidate) {
  const view = buildPassportView(candidate);
  return [
    `<main class="passport" data-passport-version="${escapeHtml(
      view.version,
    )}" data-immutability="${escapeHtml(view.passport_identity.immutability)}">`,
    `<header><h1>${escapeHtml(view.heading)}</h1><p>${escapeHtml(
      view.passport_identity.hypothesis_id,
    )} revision ${escapeHtml(view.passport_identity.revision)}</p>`,
    `<p>${escapeHtml(view.statement)}</p></header>`,
    '<section class="passport-verdict" data-section="verdict"><h2>Verdict</h2><dl>',
    `<dt>Epistemic status</dt><dd>${escapeHtml(view.verdict.epistemic_status)}</dd>`,
    `<dt>Causal status</dt><dd>${escapeHtml(view.verdict.causal_status)}</dd>`,
    `<dt>Novelty status</dt><dd>${escapeHtml(view.verdict.novelty_status)}</dd>`,
    `<dt>Promotion level</dt><dd>${escapeHtml(view.verdict.promotion_level)}</dd></dl></section>`,
    `<section class="passport-counter" data-section="counter-evidence" data-state="${escapeHtml(
      view.sections[1].state,
    )}"><h2>Counter-evidence and dissent</h2><dl>`,
    `<dt>Strongest counter-evidence</dt><dd>${escapeHtml(
      displayNullable(view.counter_evidence.strongest_counterevidence_id),
    )}</dd>`,
    `<dt>Minority report</dt><dd>${escapeHtml(
      displayNullable(view.counter_evidence.minority_report_id),
    )}</dd></dl>`,
    renderList(
      view.counter_evidence.unresolved_objection_ids,
      "No unresolved objection is recorded.",
      (id) => escapeHtml(id),
    ),
    renderList(view.counter_evidence.stale_reasons, "No staleness reason is recorded.", (reason) =>
      escapeHtml(reason),
    ),
    "</section>",
    `<section class="passport-stability" data-section="stability" data-state="${escapeHtml(
      view.stability.state,
    )}"><h2>Stability</h2><dl>`,
    `<dt>Decision stability report</dt><dd>${escapeHtml(
      view.stability.decision_stability_report_id,
    )}</dd>`,
    `<dt>Calibration</dt><dd>${escapeHtml(view.stability.calibration_status)}</dd>`,
    `<dt>Lifecycle</dt><dd>${escapeHtml(view.stability.lifecycle_status)}</dd>`,
    `<dt>Search completeness</dt><dd>${escapeHtml(
      view.stability.search_completeness,
    )}</dd></dl></section>`,
    '<section class="passport-falsifiers" data-section="falsifiers-and-next-test">',
    "<h2>Falsifiers and next test</h2>",
    renderList(view.falsifiers.falsifier_ids, "No falsifier is recorded.", (id) => escapeHtml(id)),
    `<p data-next-test="${escapeHtml(view.next_test.state)}">Next test: ${escapeHtml(
      displayNullable(view.next_test.next_experiment_ticket_id),
    )} (${escapeHtml(view.next_test.state)})</p></section>`,
    '<section class="passport-confidence" data-section="confidence-dimensions">',
    "<h2>Confidence dimensions</h2><dl>",
    CONFIDENCE_DIMENSIONS.map(
      (dimension) =>
        `<dt>${escapeHtml(dimension)}</dt><dd>${escapeHtml(
          view.confidence_vector[dimension],
        )}</dd>`,
    ).join(""),
    "</dl></section></main>",
  ].join("");
}

const requireDeclaredOperation = (operationId) => {
  if (typeof operationId !== "string" || operationId.length === 0) {
    fail("OPERATION_NOT_DECLARED", "an operation id must be a non-empty string");
  }
  if (!PASSPORT_OPERATION_IDS.includes(operationId) || !OBJECT_HAS_OWN(OPERATIONS, operationId)) {
    fail("OPERATION_NOT_DECLARED", `${operationId} is not a Passport-bindable operation`, {
      operation_id: operationId,
      declared: [...PASSPORT_OPERATION_IDS],
    });
  }
};

/** Bind one declared passport operation; anything else refuses. */
export function passportOperationRequest(operationId, input = {}, transport) {
  requireDeclaredOperation(operationId);
  return getPassport(input, transport);
}

/** Bind `GET /passports/{passport_id}` through the generated client only. */
export function passportRevisionRequest({ passport_id: passportId }, transport) {
  requireString(passportId, "passport_id");
  return passportOperationRequest("getPassport", { path: { passport_id: passportId } }, transport);
}
