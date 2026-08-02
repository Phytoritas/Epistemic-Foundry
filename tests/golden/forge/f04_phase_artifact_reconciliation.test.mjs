import assert from "node:assert/strict";
import test from "node:test";

import {
  GOLDEN_FLOW_DEFINITIONS,
  executeGoldenFlow,
  reconcileGoldenFlows,
} from "./f04-test-support.mjs";

test(
  "phase_artifact_reconciliation: every expected F04 transition and phase set resolves exactly once",
  (t) => {
    const results = GOLDEN_FLOW_DEFINITIONS.map((definition) =>
      executeGoldenFlow(t, definition));
    const reconciliation = reconcileGoldenFlows(results);
    assert.deepEqual(reconciliation, {
      status: "PASS",
      flow_count: 3,
      expected_transition_count: 17,
      generated_transition_count: 17,
      admitted_transition_count: 17,
      reduced_transition_count: 17,
      replayed_transition_count: 17,
      persisted_transition_count: 17,
      expected_phase_artifact_set_count: 14,
      generated_phase_artifact_set_count: 14,
      admitted_phase_artifact_set_count: 14,
      underdetermined_terminal_outcome_count: 3,
      failed_count: 0,
      cancelled_count: 0,
      missing_transition_ids: [],
      duplicate_transition_ids: [],
      missing_phase_artifact_set_ids: [],
    });
  },
);

test("phase_artifact_reconciliation: a missing persisted transition fails closed", (t) => {
  const result = executeGoldenFlow(t, GOLDEN_FLOW_DEFINITIONS[0]);
  const incomplete = {
    ...result,
    persistedTransitions: result.persistedTransitions.slice(0, -1),
  };
  const reconciliation = reconcileGoldenFlows([incomplete]);
  assert.equal(reconciliation.status, "FAIL");
  assert.equal(reconciliation.expected_transition_count, 4);
  assert.equal(reconciliation.persisted_transition_count, 3);
  assert.deepEqual(reconciliation.missing_transition_ids, [result.expectedTransitionIds.at(-1)]);
});
