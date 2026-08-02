import assert from "node:assert/strict";
import test from "node:test";

import {
  ForgeFsmError,
  compileForgePlan,
  reduceForgeTransition,
  replayForgeTransitionEvents,
  sha256ForgeJson,
} from "../../../packages/foundry-kernel/src/forge/fsm/index.mjs";
import {
  GOLDEN_FLOW_DEFINITIONS,
  assertUnderdeterminedAdjudication,
  executeGoldenFlow,
} from "./f04-test-support.mjs";

const expectFsmCode = (code) => (error) =>
  error instanceof ForgeFsmError && error.code === code;

test(
  "forge_golden_flows: E1 minimum and E3/E5 full paths admit, reduce, replay, and complete",
  async (t) => {
    for (const definition of GOLDEN_FLOW_DEFINITIONS) {
      await t.test(definition.case_id, (subtest) => {
        const result = executeGoldenFlow(subtest, definition);
        assert.equal(result.classification.artifact.work_class, definition.expected_work_class);
        assert.deepEqual(
          result.classification.artifact.required_phases,
          definition.expected_required_phases,
        );
        assert.deepEqual(result.plan.required_phases, definition.expected_required_phases);
        assert.equal(result.admissions.every((row) => row.admission.decision === "ADMIT"), true);
        assert.equal(
          result.directTransitions.length,
          definition.expected_required_phases.length + 1,
        );
        assert.deepEqual(result.replay.transitions, result.directTransitions);
        assert.deepEqual(result.replay.state, result.finalState);
        assert.deepEqual(result.replay.phase_artifact_sets, result.finalPhaseSets);
        assert.deepEqual(
          result.persistedTransitions.map((row) => row.record),
          result.directTransitions,
        );
        assert.equal(result.finalState.phase, "IDLE");
        assert.equal(result.finalState.status, "COMPLETED");
        assert.equal(result.storeIntegrity.ok, true);
        assertUnderdeterminedAdjudication(result.phaseRecords.get("E").document);
      });
    }
  },
);

test("forge_golden_flows: UNDERDETERMINED is a receipt-bound truthful terminal outcome", (t) => {
  const definition = GOLDEN_FLOW_DEFINITIONS.find(
    (row) => row.case_id === "E5_AMBIGUOUS_INTERVIEW_FULL",
  );
  const result = executeGoldenFlow(t, definition);
  const outcome = result.phaseRecords.get("E");
  const resolved = result.store.resolveReceipt(outcome.entry.receipt_id);
  const persisted = JSON.parse(resolved.bytes.toString("utf8"));
  assert.equal(persisted.verdict, "UNDERDETERMINED");
  assert.equal(persisted.promotion_recommendation, "BLOCK");
  assert.equal(resolved.receipt.schema_ref, "schemas/adjudication.schema.json");
  assert.equal(outcome.phaseSet.complete, true);
  assert.equal(outcome.entry.status, "VALID");
  assert.equal(result.finalState.status, "COMPLETED");
  assert.equal(result.finalState.open_blockers.length, 0);
});

test("forge_golden_flows: admission cannot bypass F02 classification identity context", (t) => {
  const definition = GOLDEN_FLOW_DEFINITIONS.find(
    (row) => row.case_id === "E3_MECHANISM_FULL",
  );
  const result = executeGoldenFlow(t, definition);
  assert.equal(result.admissions[0].admission.decision, "ADMIT");
  const mutatedContext = {
    ...result.classification.identityContext,
    policy_bundle_hash: sha256ForgeJson({ mutation: "F04 identity-context mismatch" }),
  };
  assert.throws(
    () =>
      compileForgePlan({
        classification: result.classification.artifact,
        classification_identity_context: mutatedContext,
      }),
    expectFsmCode("CLASSIFICATION_INTEGRITY_FAILED"),
  );
  assert.throws(
    () =>
      reduceForgeTransition({
        current_state: result.initialState,
        transition_request: result.transitionEntries[0].transition_request,
        classification: result.classification.artifact,
        classification_identity_context: mutatedContext,
        phase_artifact_sets: result.phaseSets,
        event: result.transitionEntries[0].event,
      }),
    expectFsmCode("CLASSIFICATION_INTEGRITY_FAILED"),
  );
  assert.throws(
    () =>
      replayForgeTransitionEvents({
        initial_state: result.initialState,
        transitions: result.transitionEntries,
        classification: result.classification.artifact,
        classification_identity_context: mutatedContext,
        phase_artifact_sets: result.phaseSets,
      }),
    expectFsmCode("CLASSIFICATION_INTEGRITY_FAILED"),
  );
});
