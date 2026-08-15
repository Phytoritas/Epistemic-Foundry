/**
 * Deterministic fixtures for the U03 Hypothesis Passport view suite.
 *
 * Every value is a literal.  No clock, no random source and no environment read,
 * so two runs of the same suite build byte-identical views.  Each factory takes a
 * shallow override object so a single adversarial field can be perturbed.
 */

import { REQUIRED_VISIBLE_FIELDS } from "./index.mjs";

export const REVISION = 2;

/** The seven confidence dimensions, each within the closed unit interval. */
export const confidenceVector = (overrides = {}) => ({
  grounding: 0.7,
  directness: 0.6,
  independence: 0.5,
  scope_match: 0.65,
  method_validity: 0.55,
  causal_identifiability: 0.4,
  testability: 0.8,
  ...overrides,
});

/** The six scored assessment dimensions plus the calibration status. */
export const epistemicAssessment = (overrides = {}) => ({
  grounding: 0.7,
  evidence_sufficiency: 0.6,
  consistency: 0.65,
  method_fitness: 0.55,
  scope_transportability: 0.5,
  falsifiability: 0.75,
  calibration_status: "CALIBRATED",
  ...overrides,
});

/** One complete ScopeVector for the greenhouse tomato and elevated-CO2 story. */
export const scopeVector = (overrides = {}) => ({
  domain: "plant science",
  population: "greenhouse-grown tomato plants",
  entity_type: "plant",
  entity_subtype: "tomato",
  unit_of_analysis: "individual tomato plant",
  setting: "greenhouse",
  geography: null,
  jurisdiction: null,
  language: "English",
  lifecycle_stage: "fruiting",
  spatial_scale: "individual plant",
  temporal_scale: "greenhouse crop cycle",
  time_period: null,
  measurement_time: "harvest",
  intervention_or_exposure: {
    name: "elevated CO2",
    category: "atmospheric exposure",
    min_value: null,
    max_value: null,
    unit: null,
    duration: null,
    frequency: null,
    rate: null,
    route_or_delivery: "greenhouse atmosphere",
  },
  comparator: "ambient CO2 under the same greenhouse regime",
  inclusion_criteria: ["tomato plants grown under the stated greenhouse regime"],
  exclusion_criteria: [],
  conditions: { greenhouse_regime: "stated" },
  domain_extensions: { crop: "tomato" },
  ...overrides,
});

/** One immutable hypothesis passport revision, overridable field by field. */
export const passport = (overrides = {}) => ({
  hypothesis_id: "HYP-0001",
  revision: REVISION,
  canonical_statement: "Elevated CO2 raises tomato yield under the stated greenhouse regime.",
  scope: scopeVector(),
  reasoning_modes: ["deductive", "causal"],
  mechanism_chain: ["MC-0001"],
  prediction_ids: ["PR-0001"],
  falsifier_ids: ["FL-0001"],
  evidence_pack_id: "EP-0001",
  strongest_counterevidence_id: "EV-9001",
  unresolved_objection_ids: ["OBJ-0001"],
  epistemic_status: "SUPPORTED",
  causal_status: "ASSUMPTION_DEPENDENT",
  novelty_status: "CORPUS_NOVEL",
  promotion_level: "CANDIDATE",
  confidence_vector: confidenceVector(),
  minority_report_id: "MR-0001",
  next_experiment_ticket_id: "ET-0001",
  run_id: "RUN-0001",
  attestation_id: "AT-0001",
  provenance_manifest_id: "PM-0001",
  epistemic_assessment: epistemicAssessment(),
  bias_risk_register_id: "BRR-0001",
  decision_stability_report_id: "DSR-0001",
  search_completeness: "PARTIAL",
  human_decision_ids: ["HD-0001"],
  lifecycle_status: "active",
  stale_reasons: [],
  ...overrides,
});

/** The rendering: every required field visible, no mutating affordance. */
export const presentation = (overrides = {}) => ({
  revision: REVISION,
  visible_fields: [...REQUIRED_VISIBLE_FIELDS],
  affordances: ["READ_REVISION", "COPY_IDENTIFIER", "OPEN_EVIDENCE_PACK", "REQUEST_NEW_REVISION"],
  ...overrides,
});

/** A complete, well-formed Passport view input. */
export const passportInput = (overrides = {}) => ({
  passport: passport(),
  presentation: presentation(),
  ...overrides,
});
