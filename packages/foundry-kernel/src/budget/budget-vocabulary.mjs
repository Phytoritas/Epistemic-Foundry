/**
 * Canonical budget vocabulary, composed — never restated — from the sealed
 * contract registry (`@epistemic-foundry/contracts`), whose source of truth is
 * `schemas/budget-envelope.schema.json` (EF4-I28).
 *
 * The Python owner `src/epistemic_foundry/budgets/envelope.py` encodes
 * the same semantics: only the `HARD_*` enforcement labels actually bound spend;
 * `SOFT_ESTIMATE` is a forecast and `UNMETERED` is no meter at all. Rather than
 * re-listing the labels here (which would silently drift from the schema), this
 * module derives them from the registry contract and applies the `HARD_` prefix
 * rule so the "does this label bound spend?" question has a single truthful
 * source.
 */

import { contractByTitle } from "@epistemic-foundry/contracts";

import { deepFreeze, fail, requirePlainRecord } from "./budget-primitives.mjs";

const BUDGET_ENVELOPE_TITLE = "BudgetEnvelope";
const BUDGET_ENVELOPE_SCHEMA_FILE = "schemas/budget-envelope.schema.json";
const BUDGET_ENVELOPE_SCHEMA_ID =
  "https://epistemic-foundry.local/schemas/budget-envelope.schema.json";

/** Enforcement labels bound spend iff they carry the HARD_ prefix (EF4-I28). */
const HARD_PREFIX = "HARD_";

const property = (contract, name) => {
  const entry = contract.properties.find((candidate) => candidate.name === name);
  if (entry === undefined) {
    fail("BUDGET_VOCABULARY_INVALID", `budget contract is missing the ${name} property`, { name });
  }
  return entry;
};

const enumValues = (contract, name) => {
  const values = property(contract, name).schema.enum;
  if (!Array.isArray(values) || values.length === 0 || values.some((v) => typeof v !== "string")) {
    fail("BUDGET_VOCABULARY_INVALID", `${name} enum is not a non-empty list of labels`, { name });
  }
  return [...values];
};

/**
 * Derive the frozen canonical vocabulary from a registry contract entry.
 *
 * Fail-closed: a tampered or unexpected contract (wrong title/id, missing
 * enums, missing limit dimensions) is refused rather than silently accepted,
 * because a mislabeled vocabulary would let an over-budget operation look
 * bounded.
 */
export const deriveBudgetVocabulary = (contract) => {
  requirePlainRecord(contract, "BudgetEnvelope contract", { code: "BUDGET_VOCABULARY_INVALID" });
  if (contract.title !== BUDGET_ENVELOPE_TITLE) {
    fail("BUDGET_VOCABULARY_INVALID", "budget contract title is not BudgetEnvelope", {
      title: contract.title,
    });
  }
  if (contract.schema_id !== BUDGET_ENVELOPE_SCHEMA_ID) {
    fail("BUDGET_VOCABULARY_INVALID", "budget contract schema id is not canonical", {
      schema_id: contract.schema_id,
    });
  }

  const enforcementLabels = enumValues(contract, "enforcement");
  const breachPolicies = enumValues(contract, "breach_policy");

  const hardLimitsSchema = property(contract, "hard_limits").schema;
  const dimensionNames =
    hardLimitsSchema && hardLimitsSchema.properties
      ? Object.keys(hardLimitsSchema.properties)
      : [];
  const requiredDimensions = Array.isArray(hardLimitsSchema?.required)
    ? hardLimitsSchema.required
    : [];
  if (dimensionNames.length === 0 || requiredDimensions.length !== dimensionNames.length) {
    fail("BUDGET_VOCABULARY_INVALID", "hard_limits must declare every limit dimension as required");
  }
  for (const dimension of dimensionNames) {
    if (!requiredDimensions.includes(dimension)) {
      fail("BUDGET_VOCABULARY_INVALID", "hard_limits dimension is not required", { dimension });
    }
  }

  const bounding = enforcementLabels.filter((label) => label.startsWith(HARD_PREFIX));
  const advisory = enforcementLabels.filter((label) => !label.startsWith(HARD_PREFIX));
  if (bounding.length === 0) {
    fail("BUDGET_VOCABULARY_INVALID", "no HARD_ enforcement label bounds spend");
  }

  return deepFreeze({
    schema_file: BUDGET_ENVELOPE_SCHEMA_FILE,
    schema_id: BUDGET_ENVELOPE_SCHEMA_ID,
    source_sha256: contract.source_sha256,
    required_fields: [...contract.required_fields],
    enforcement_labels: enforcementLabels,
    bounding_enforcement: bounding,
    advisory_enforcement: advisory,
    breach_policies: breachPolicies,
    limit_dimensions: dimensionNames,
    // The five cumulative dimensions a running operation can spend against.
    // `concurrency` is a point-in-time gauge owned by the adaptive fleet, not a
    // cumulative meter, so it is excluded from reservation accounting.
    reservation_dimensions: dimensionNames.filter((name) => name !== "concurrency"),
  });
};

let cached;

/** The canonical budget vocabulary, loaded once from the sealed registry. */
export const budgetVocabulary = () => {
  if (cached === undefined) {
    const contract = contractByTitle.get(BUDGET_ENVELOPE_TITLE);
    if (contract === undefined) {
      fail("BUDGET_VOCABULARY_INVALID", "BudgetEnvelope contract is absent from the registry");
    }
    cached = deriveBudgetVocabulary(contract);
  }
  return cached;
};

export const boundingEnforcement = () => new Set(budgetVocabulary().bounding_enforcement);
export const enforcementLabelSet = () => new Set(budgetVocabulary().enforcement_labels);
export const breachPolicySet = () => new Set(budgetVocabulary().breach_policies);

/** True only for labels the schema marks as spend-bounding (HARD_*). */
export const enforcementBoundsSpend = (enforcement) =>
  boundingEnforcement().has(enforcement);
