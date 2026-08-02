/**
 * Deterministic fixtures for the Y01 budget and adaptive fleet checks.
 */

import { budgetVocabulary } from "./budget-vocabulary.mjs";
import { sealBudgetEnvelope } from "./budget-meter.mjs";

const FIXED_CREATED_AT = "2026-07-31T00:00:00.000Z";

const nullLimits = () =>
  Object.fromEntries(budgetVocabulary().limit_dimensions.map((key) => [key, null]));

/** A sealed envelope for the requested enforcement label with sensible defaults. */
export const budgetEnvelopeFixture = ({
  enforcement = "HARD_PREALLOCATED",
  hardLimits = {},
  breachPolicy,
  meteringAuthority,
  softCostCurrency = null,
  softCostAmount = null,
  budgetId = "BUD-Y01-fixture",
} = {}) => {
  const bounds = enforcement.startsWith("HARD_");
  const defaultBounded = {
    tokens: 100000,
    calls: 20,
    wall_seconds: 3600,
    concurrency: 4,
    storage_bytes: 1000000,
    network_bytes: 1000000,
  };
  const limits = bounds
    ? { ...nullLimits(), ...defaultBounded, ...hardLimits }
    : { ...nullLimits(), ...hardLimits };
  return sealBudgetEnvelope({
    budget_id: budgetId,
    enforcement,
    hard_limits: limits,
    soft_cost_currency: softCostCurrency,
    soft_cost_amount: softCostAmount,
    metering_authority:
      meteringAuthority !== undefined ? meteringAuthority : bounds ? "METER-Y01-fixture" : null,
    breach_policy: breachPolicy ?? (bounds ? "PAUSE_AND_ESCALATE" : "WARN"),
    created_at: FIXED_CREATED_AT,
  });
};

/** A full reservation over the five cumulative dimensions. */
export const reservationFixture = (overrides = {}) => ({
  tokens: 100,
  calls: 1,
  wall_seconds: 60,
  storage_bytes: 100,
  network_bytes: 100,
  ...overrides,
});
