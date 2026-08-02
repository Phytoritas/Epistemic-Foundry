/**
 * Honest observability result states (Y02).
 *
 * The cardinal rule of privacy-safe, trustworthy telemetry is that the system
 * never fabricates a healthy metric. An SLO with no observed samples is not
 * "OK" — it is `UNKNOWN`. A window with samples but zero successes is not a
 * degraded shade of healthy — it is `UNAVAILABLE`. This module makes those the
 * only reachable states, so a green dashboard always corresponds to real,
 * measured evidence.
 *
 * `ResultState` is the shared vocabulary other subsystems (e.g. the effect and
 * ledger surfaces) import to describe an outcome without inventing one.
 */

import {
  deepFreeze,
  fail,
  requireFiniteNumber,
  requirePlainRecord,
  requireSafeInteger,
} from "./observability-primitives.mjs";

/**
 * The four honest states a measured signal can report.
 *  - OK:          samples observed and the objective was met.
 *  - DEGRADED:    samples observed, some good, objective not met.
 *  - UNAVAILABLE: samples observed but none were good.
 *  - UNKNOWN:     no samples observed — health is not asserted, never assumed.
 */
export const ResultState = Object.freeze({
  OK: "OK",
  DEGRADED: "DEGRADED",
  UNAVAILABLE: "UNAVAILABLE",
  UNKNOWN: "UNKNOWN",
});

const RESULT_STATES = new Set(Object.values(ResultState));

/** True only for a canonical member of {@link ResultState}. */
export const isResultState = (value) => RESULT_STATES.has(value);

/**
 * Evaluate an SLO window into an honest {@link ResultState}.
 *
 * @param {object} window
 * @param {number} window.sample_count - total observations in the window.
 * @param {number} window.good_count   - observations meeting the objective.
 * @param {number} window.objective    - target good ratio in (0, 1].
 * @returns frozen `{ state, sample_count, good_count, observed_ratio, objective }`
 *   where `observed_ratio` is `null` when there is nothing to measure.
 */
export const evaluateSlo = (window) => {
  const input = requirePlainRecord(window, "slo window", {
    allowedKeys: ["sample_count", "good_count", "objective"],
    requiredKeys: ["sample_count", "good_count", "objective"],
    code: "SLO_INPUT_INVALID",
  });
  const sampleCount = requireSafeInteger(input.sample_count, "sample_count", {
    code: "SLO_INPUT_INVALID",
  });
  const goodCount = requireSafeInteger(input.good_count, "good_count", {
    code: "SLO_INPUT_INVALID",
  });
  const objective = requireFiniteNumber(input.objective, "objective", {
    minimum: Number.MIN_VALUE,
    maximum: 1,
    code: "SLO_INPUT_INVALID",
  });
  if (goodCount > sampleCount) {
    fail("SLO_INPUT_INVALID", "good_count cannot exceed sample_count", {
      good_count: goodCount,
      sample_count: sampleCount,
    });
  }

  let state;
  let observedRatio;
  if (sampleCount === 0) {
    // No evidence: refuse to assert health. This is the honest-state guarantee.
    state = ResultState.UNKNOWN;
    observedRatio = null;
  } else {
    observedRatio = goodCount / sampleCount;
    if (goodCount === 0) {
      state = ResultState.UNAVAILABLE;
    } else if (observedRatio >= objective) {
      state = ResultState.OK;
    } else {
      state = ResultState.DEGRADED;
    }
  }

  return deepFreeze({
    state,
    sample_count: sampleCount,
    good_count: goodCount,
    observed_ratio: observedRatio,
    objective,
  });
};
