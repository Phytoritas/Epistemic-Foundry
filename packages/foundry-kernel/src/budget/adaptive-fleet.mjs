/**
 * Adaptive fleet controls (Y01).
 *
 * A fleet scales worker fan-out deterministically within *declared* bounds:
 * `[min_workers, max_workers]`, further capped by the budget envelope's
 * `concurrency` hard limit when the envelope bounds spend. Fan-out is therefore
 * bounded by construction — a declared maximum that would exceed a bounding
 * concurrency limit is refused, not clamped, because the fleet must not quietly
 * pretend a larger declaration is safe.
 *
 * Scaling is a pure deterministic function of the declared bounds and the
 * observed backlog: the same backlog always yields the same target and the same
 * receipt hash. The fleet acquires no authority — it computes counts and emits
 * re-derivable receipts only; it never mints leases or mutates external state.
 */

import {
  cloneCanonical,
  deepFreeze,
  fail,
  requirePlainRecord,
  requireSafeInteger,
  sha256BudgetJson,
} from "./budget-primitives.mjs";
import { assertBudgetEnvelope, spendIsBounded } from "./budget-meter.mjs";

const FLEET_CODE = "FLEET_CONTRACT_INVALID";

const clamp = (value, low, high) => (value < low ? low : value > high ? high : value);

class AdaptiveFleet {
  #envelope;
  #minWorkers;
  #maxWorkers;
  #effectiveMax;
  #concurrencyLimit;

  constructor({ envelope, min_workers: minWorkers, max_workers: maxWorkers }) {
    this.#envelope = assertBudgetEnvelope(envelope);

    this.#minWorkers = requireSafeInteger(minWorkers, "min_workers", { minimum: 0, code: FLEET_CODE });
    this.#maxWorkers = requireSafeInteger(maxWorkers, "max_workers", { minimum: 1, code: FLEET_CODE });
    if (this.#minWorkers > this.#maxWorkers) {
      fail(FLEET_CODE, "min_workers cannot exceed max_workers", {
        min_workers: this.#minWorkers,
        max_workers: this.#maxWorkers,
      });
    }

    // A spend-bounding budget with a declared concurrency ceiling is an
    // independent upper bound on fan-out. A fleet that declares more workers
    // than the budget permits is not truthfully bounded, so it is refused.
    const concurrency = spendIsBounded(this.#envelope) ? this.#envelope.hard_limits.concurrency : null;
    this.#concurrencyLimit = concurrency;
    if (concurrency !== null && this.#maxWorkers > concurrency) {
      fail("FLEET_BOUND_EXCEEDS_BUDGET", "declared max_workers exceeds the budget concurrency limit", {
        max_workers: this.#maxWorkers,
        concurrency_limit: concurrency,
      });
    }
    this.#effectiveMax = concurrency === null ? this.#maxWorkers : Math.min(this.#maxWorkers, concurrency);
    if (this.#effectiveMax < this.#minWorkers) {
      fail("FLEET_BOUND_EXCEEDS_BUDGET", "budget concurrency limit is below min_workers", {
        min_workers: this.#minWorkers,
        concurrency_limit: concurrency,
      });
    }
  }

  get minWorkers() {
    return this.#minWorkers;
  }

  get maxWorkers() {
    return this.#maxWorkers;
  }

  get effectiveMaxWorkers() {
    return this.#effectiveMax;
  }

  get budgetHash() {
    return this.#envelope.budget_hash;
  }

  #receipt(body) {
    const canonical = cloneCanonical(body);
    return deepFreeze({ ...canonical, receipt_hash: sha256BudgetJson(canonical) });
  }

  /**
   * Deterministically size the fleet for an observed backlog.
   *
   * `target_workers = clamp(backlog, min_workers, effective_max_workers)`. The
   * target can never exceed the declared, budget-bounded maximum, so fan-out
   * stays bounded regardless of backlog. Returns a re-derivable receipt.
   */
  plan(backlog) {
    const observed = requireSafeInteger(backlog, "backlog", { minimum: 0, code: FLEET_CODE });
    const target = clamp(observed, this.#minWorkers, this.#effectiveMax);
    return this.#receipt({
      budget_hash: this.#envelope.budget_hash,
      enforcement: this.#envelope.enforcement,
      min_workers: this.#minWorkers,
      max_workers: this.#maxWorkers,
      concurrency_limit: this.#concurrencyLimit,
      effective_max_workers: this.#effectiveMax,
      backlog: observed,
      target_workers: target,
    });
  }

  /**
   * Admit an explicit worker-count request, refusing any count outside the
   * declared, budget-bounded window. Returns a re-derivable receipt.
   */
  assertRequest(candidate) {
    const requested = requireSafeInteger(candidate, "requested_workers", { minimum: 0, code: FLEET_CODE });
    if (requested < this.#minWorkers || requested > this.#effectiveMax) {
      fail("FLEET_BOUND_EXCEEDED", "requested worker count is outside the declared fleet bounds", {
        requested,
        min_workers: this.#minWorkers,
        effective_max_workers: this.#effectiveMax,
      });
    }
    return this.#receipt({
      budget_hash: this.#envelope.budget_hash,
      min_workers: this.#minWorkers,
      effective_max_workers: this.#effectiveMax,
      requested_workers: requested,
      admitted: true,
    });
  }
}

/** Create an adaptive fleet bounded by declared limits and the budget. */
export const createAdaptiveFleet = (spec) => {
  requirePlainRecord(spec, "adaptive fleet spec", {
    allowedKeys: ["envelope", "min_workers", "max_workers"],
    requiredKeys: ["envelope", "min_workers", "max_workers"],
    code: FLEET_CODE,
  });
  return new AdaptiveFleet(spec);
};
