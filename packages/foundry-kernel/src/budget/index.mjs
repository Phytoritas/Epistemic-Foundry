/**
 * Typed budgets, adaptive fleet and performance controls (Y01).
 *
 * Public surface for the budget subsystem. The budget vocabulary is composed
 * from the sealed contract registry (source of truth
 * `schemas/budget-envelope.schema.json`); nothing here restates it.
 */

export {
  budgetVocabulary,
  boundingEnforcement,
  breachPolicySet,
  deriveBudgetVocabulary,
  enforcementBoundsSpend,
  enforcementLabelSet,
} from "./budget-vocabulary.mjs";
export {
  assertBudgetEnvelope,
  createBudgetMeter,
  sealBudgetEnvelope,
  spendIsBounded,
} from "./budget-meter.mjs";
export { createAdaptiveFleet } from "./adaptive-fleet.mjs";
export { BudgetControlError } from "./budget-primitives.mjs";
