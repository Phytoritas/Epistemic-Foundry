import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");

export const sampleInsight = () => {
  const card = JSON.parse(
    readFileSync(resolve(repositoryRoot, "examples/sample_insight.json"), "utf8"),
  );
  card.terms_to_define = [];
  return card;
};

export const sampleConsent = () =>
  JSON.parse(
    readFileSync(resolve(repositoryRoot, "examples/sample_consent-record.json"), "utf8"),
  );

export const emptyConsentRequirement = () => ({
  evaluated_at: null,
  records: [],
  required: false,
  required_data_classes: [],
  required_purposes: [],
  required_scopes: [],
});

export const readyInput = () => ({
  consent_requirement: emptyConsentRequirement(),
  council_blockers: [],
  council_ready: true,
  insight_card: sampleInsight(),
  measurement_compatibilities: [],
  ontology_resolutions: [],
  unknown_scope: [
    { path: "scope.geography", source: "EXPLICIT_NULL" },
    { path: "scope.intervention_or_exposure.rate", source: "EXPLICIT_NULL" },
    { path: "scope.jurisdiction", source: "EXPLICIT_NULL" },
    { path: "scope.lifecycle_stage", source: "EXPLICIT_NULL" },
    { path: "scope.time_period", source: "EXPLICIT_NULL" },
  ],
});

export const ontologyResolution = (overrides = {}) => ({
  abstention_reasons: [],
  candidates: [
    {
      authority_ref: "ONTOLOGY-4.0.0",
      canonical_label: "engagement",
      conflicting_dimensions: [],
      construct_id: "construct-engagement",
      entity_kind: "LATENT_CONSTRUCT",
      matched_dimensions: ["method_id"],
      missing_dimensions: [],
      viable: true,
    },
  ],
  mapping_key_hash: `sha256:${"1".repeat(64)}`,
  proposed_construct_id: "construct-engagement",
  resolver_version: "4.0.0-i03.1",
  review_queue_items: [],
  selected_construct_id: "construct-engagement",
  status: "RESOLVED",
  ...overrides,
});

export const measurementCompatibility = (overrides = {}) => ({
  aggregation_allowed: true,
  bridge_id: null,
  compatibility_status: "DIRECTLY_COMPARABLE",
  construct_equivalence: "SAME",
  left_identity_hash: `sha256:${"2".repeat(64)}`,
  left_measurement_id: "MEASUREMENT-left",
  method_threats: [],
  promotion_ceiling: "NO_RESTRICTION",
  required_transformations: [],
  right_identity_hash: `sha256:${"3".repeat(64)}`,
  right_measurement_id: "MEASUREMENT-right",
  ...overrides,
});
