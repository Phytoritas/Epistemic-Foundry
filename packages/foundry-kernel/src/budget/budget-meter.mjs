/**
 * Typed budget enforcement (EF4-I28, Y01).
 *
 * A budget envelope is labeled HARD_METERED, HARD_PREALLOCATED, SOFT_ESTIMATE
 * or UNMETERED. Only the HARD_* labels bound spend. The point of the meter is
 * that an operation exceeding a declared hard limit is *refused* — the charge
 * throws BUDGET_LIMIT_EXCEEDED — rather than silently truncated. Advisory
 * labels (SOFT_ESTIMATE, UNMETERED) record usage as a forecast and never refuse,
 * so their non-bounding state stays truthful instead of masquerading as a limit.
 *
 * The meter acquires no authority: it neither mints capability leases nor
 * mutates external state. It only accounts for declared reservations and emits
 * deterministic, re-derivable receipts.
 */

import {
  BudgetControlError,
  cloneCanonical,
  deepFreeze,
  fail,
  requireEnum,
  requireFiniteNumber,
  requireHash,
  requireNullableString,
  requirePlainRecord,
  requireSafeInteger,
  requireString,
  requireTimestamp,
  sha256BudgetJson,
} from "./budget-primitives.mjs";
import {
  breachPolicySet,
  budgetVocabulary,
  enforcementBoundsSpend,
  enforcementLabelSet,
} from "./budget-vocabulary.mjs";

const ENVELOPE_CODE = "BUDGET_ENVELOPE_INVALID";

const normalizeHardLimits = (candidate, dimensions, code) => {
  const limits = requirePlainRecord(candidate, "hard_limits", {
    allowedKeys: dimensions,
    requiredKeys: dimensions,
    code,
  });
  return Object.fromEntries(
    dimensions.map((key) => {
      const value = limits[key];
      return [
        key,
        value === null ? null : requireSafeInteger(value, `hard_limits.${key}`, { minimum: 0, code }),
      ];
    }),
  );
};

const normalizeEnvelope = (candidate, { requireHash: withHash }) => {
  const vocab = budgetVocabulary();
  const required = withHash ? vocab.required_fields : vocab.required_fields.filter((f) => f !== "budget_hash");
  const budget = requirePlainRecord(candidate, "BudgetEnvelope", {
    allowedKeys: vocab.required_fields,
    requiredKeys: required,
    code: ENVELOPE_CODE,
  });

  const enforcement = requireEnum(budget.enforcement, enforcementLabelSet(), "enforcement", ENVELOPE_CODE);
  const softCostAmount =
    budget.soft_cost_amount === null
      ? null
      : requireFiniteNumber(budget.soft_cost_amount, "soft_cost_amount", { code: ENVELOPE_CODE });

  const normalized = {
    budget_id: requireString(budget.budget_id, "budget_id", { min: 3, max: 128, code: ENVELOPE_CODE }),
    enforcement,
    hard_limits: normalizeHardLimits(budget.hard_limits, vocab.limit_dimensions, ENVELOPE_CODE),
    soft_cost_currency: requireNullableString(budget.soft_cost_currency, "soft_cost_currency", ENVELOPE_CODE),
    soft_cost_amount: softCostAmount,
    metering_authority: requireNullableString(budget.metering_authority, "metering_authority", ENVELOPE_CODE),
    breach_policy: requireEnum(budget.breach_policy, breachPolicySet(), "breach_policy", ENVELOPE_CODE),
    created_at: requireTimestamp(budget.created_at, "created_at", ENVELOPE_CODE),
  };

  const bounds = enforcementBoundsSpend(enforcement);
  const anyHardLimit = vocab.limit_dimensions.some((key) => normalized.hard_limits[key] !== null);

  if (bounds) {
    if (normalized.metering_authority === null) {
      fail(ENVELOPE_CODE, "hard budget enforcement requires a metering authority");
    }
    if (!anyHardLimit) {
      fail(ENVELOPE_CODE, "hard budget enforcement declares a bound but no hard limit enforces it");
    }
  }
  if (enforcement === "UNMETERED") {
    if (anyHardLimit) {
      fail(ENVELOPE_CODE, "UNMETERED budgets cannot imply hard limits");
    }
    if (["CANCEL", "PAUSE_AND_ESCALATE"].includes(normalized.breach_policy)) {
      fail(ENVELOPE_CODE, "UNMETERED budgets have no meter to detect a breach", {
        breach_policy: normalized.breach_policy,
      });
    }
  }

  if (withHash) {
    const actual = requireHash(budget.budget_hash, "budget_hash", ENVELOPE_CODE);
    const expected = sha256BudgetJson(normalized);
    if (actual !== expected) {
      fail("BUDGET_HASH_MISMATCH", "BudgetEnvelope hash does not match canonical fields", {
        actual,
        expected,
      });
    }
    return { ...normalized, budget_hash: actual };
  }
  return normalized;
};

/** Seal a budget envelope, computing its deterministic content hash. */
export const sealBudgetEnvelope = (candidate) => {
  const normalized = normalizeEnvelope(candidate, { requireHash: false });
  return deepFreeze({ ...normalized, budget_hash: sha256BudgetJson(normalized) });
};

/** Validate an already-sealed envelope (hash-checked). */
export const assertBudgetEnvelope = (candidate) =>
  deepFreeze(normalizeEnvelope(candidate, { requireHash: true }));

/** True only when the envelope's label denotes an enforced limit. */
export const spendIsBounded = (envelope) => enforcementBoundsSpend(envelope.enforcement);

const normalizeReservation = (candidate, dimensions) => {
  const code = "BUDGET_RESERVATION_INVALID";
  const reservation = requirePlainRecord(candidate, "budget_reservation", {
    allowedKeys: dimensions,
    requiredKeys: dimensions,
    code,
  });
  return Object.fromEntries(
    dimensions.map((key) => [
      key,
      requireSafeInteger(reservation[key], `budget_reservation.${key}`, { minimum: 0, code }),
    ]),
  );
};

class BudgetMeter {
  #envelope;
  #dimensions;
  #bounded;
  #usage;
  #seq = 0;

  constructor(envelope) {
    this.#envelope = assertBudgetEnvelope(envelope);
    this.#dimensions = budgetVocabulary().reservation_dimensions;
    this.#bounded = spendIsBounded(this.#envelope);
    this.#usage = Object.fromEntries(this.#dimensions.map((key) => [key, 0]));
  }

  get enforcement() {
    return this.#envelope.enforcement;
  }

  get budgetHash() {
    return this.#envelope.budget_hash;
  }

  spendIsBounded() {
    return this.#bounded;
  }

  usage() {
    return deepFreeze({ ...this.#usage });
  }

  remaining(dimension) {
    if (!this.#dimensions.includes(dimension)) {
      fail("BUDGET_DIMENSION_UNKNOWN", "unknown reservation dimension", { dimension });
    }
    const limit = this.#envelope.hard_limits[dimension];
    if (!this.#bounded || limit === null) return null;
    return limit - this.#usage[dimension];
  }

  /**
   * Account for one operation's declared reservation.
   *
   * For a spend-bounding envelope, a reservation that would push any dimension
   * past its declared hard limit is REFUSED (throws BUDGET_LIMIT_EXCEEDED); the
   * usage is left unchanged so the refusal is not silently partially applied.
   * For advisory envelopes the reservation is always admitted and recorded as a
   * forecast. Returns a deterministic receipt.
   */
  charge(candidate) {
    const reservation = normalizeReservation(candidate, this.#dimensions);
    if (this.#bounded) {
      for (const key of this.#dimensions) {
        const limit = this.#envelope.hard_limits[key];
        if (limit !== null && this.#usage[key] + reservation[key] > limit) {
          throw new BudgetControlError(
            "BUDGET_LIMIT_EXCEEDED",
            "declared hard budget would be exceeded; operation refused rather than truncated",
            {
              dimension: key,
              current: this.#usage[key],
              requested: reservation[key],
              limit,
              breach_policy: this.#envelope.breach_policy,
            },
          );
        }
      }
    }
    for (const key of this.#dimensions) this.#usage[key] += reservation[key];
    this.#seq += 1;
    const receiptBody = {
      budget_hash: this.#envelope.budget_hash,
      enforcement: this.#envelope.enforcement,
      seq: this.#seq,
      spend_bounded: this.#bounded,
      reservation: cloneCanonical(reservation),
      usage_after: cloneCanonical(this.#usage),
    };
    return deepFreeze({ ...receiptBody, receipt_hash: sha256BudgetJson(receiptBody) });
  }
}

/** Create a typed budget meter over a sealed envelope. */
export const createBudgetMeter = ({ envelope } = {}) => new BudgetMeter(envelope);
