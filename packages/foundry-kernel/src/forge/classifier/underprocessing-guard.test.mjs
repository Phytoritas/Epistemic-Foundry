import assert from "node:assert/strict";
import test from "node:test";

import {
  CLASSIFICATION_SIGNALS,
  EpistemicWorkClassifierError,
  SIGNAL_FLOORS,
  WORK_CLASSES,
  assertMonotonicProtection,
  evaluateEpistemicWork,
} from "./epistemic-work-classifier.mjs";
import { classificationInput, testHash } from "./classifier-test-support.mjs";

const classRank = new Map(WORK_CLASSES.map((workClass, index) => [workClass, index]));

const expectCode = (code) => (error) =>
  error instanceof EpistemicWorkClassifierError && error.code === code;

const decisionForMask = (mask) => {
  const signals = CLASSIFICATION_SIGNALS.filter((_, index) => (mask & (1 << index)) !== 0);
  return evaluateEpistemicWork(
    classificationInput({
      runId: "RUN-F01-guard",
      requestId: `REQ-F01-guard-${mask}`,
      requestText: `guard subset ${mask}`,
      policyBundleHash: testHash(`F01-guard-policy-${mask}`),
      requestSignals: signals,
    }),
  );
};

test("underprocessing_guard: all 1023 non-empty subsets use the exact maximum floor", () => {
  const decisions = new Array(1 << CLASSIFICATION_SIGNALS.length);
  for (let mask = 1; mask < decisions.length; mask += 1) {
    const decision = decisionForMask(mask);
    decisions[mask] = decision;
    const expectedRank = Math.max(
      ...CLASSIFICATION_SIGNALS.flatMap((signal, index) =>
        (mask & (1 << index)) === 0 ? [] : [classRank.get(SIGNAL_FLOORS[signal])],
      ),
    );
    assert.equal(decision.work_class, WORK_CLASSES[expectedRank], `mask ${mask}`);
    if ((mask & (1 << CLASSIFICATION_SIGNALS.indexOf("HIGH_STAKES"))) !== 0) {
      assert.equal(classRank.get(decision.work_class) >= classRank.get("E4"), true);
    }
    if ((mask & (1 << CLASSIFICATION_SIGNALS.indexOf("NOVELTY"))) !== 0) {
      assert.equal(decision.work_class, "E5");
    }
  }
  assert.equal(decisions.filter(Boolean).length, 1023);
});

test("underprocessing_guard: every non-empty subset-to-superset pair preserves protection", () => {
  const decisions = new Array(1 << CLASSIFICATION_SIGNALS.length);
  for (let mask = 1; mask < decisions.length; mask += 1) decisions[mask] = decisionForMask(mask);
  let comparisons = 0;
  for (let subset = 1; subset < decisions.length; subset += 1) {
    for (let superset = subset; superset < decisions.length; superset += 1) {
      if ((subset & superset) !== subset) continue;
      assert.equal(assertMonotonicProtection(decisions[subset], decisions[superset]), true);
      comparisons += 1;
    }
  }
  assert.equal(comparisons, 58025);
});

test("underprocessing_guard: empty input injects sticky AMBIGUOUS and cannot lose Interview", () => {
  const empty = evaluateEpistemicWork(
    classificationInput({
      requestId: "REQ-F01-empty",
      requestText: "Proceed.",
      requestSignals: [],
    }),
  );
  assert.deepEqual(empty.accepted_signals, ["AMBIGUOUS"]);
  assert.equal(empty.work_class, "E5");
  assert.deepEqual(empty.required_phases, ["I", "F", "O", "R", "G", "E"]);

  const sameRevision = evaluateEpistemicWork(
    classificationInput({
      requestId: empty.request_id,
      requestText: "Proceed.",
      requestSignals: ["LOOKUP"],
    }),
    {
      prior_classification: {
        request_id: empty.request_id,
        accepted_signals: empty.accepted_signals,
      },
    },
  );
  assert.deepEqual(sameRevision.accepted_signals, ["AMBIGUOUS", "LOOKUP"]);
  assert.equal(sameRevision.work_class, "E5");
  assert.equal(sameRevision.required_phases[0], "I");
});

test("underprocessing_guard: trusted unknown signals fail input validation", () => {
  assert.throws(
    () =>
      evaluateEpistemicWork(
        classificationInput({
          requestId: "REQ-F01-unknown-trusted",
          requestSignals: ["SUPER_SIMPLE"],
        }),
      ),
    expectCode("CLASSIFIER_INPUT_VALIDATION_FAILED"),
  );
});

test("underprocessing_guard: any class, gate, Interview, role, or phase regression fails", () => {
  const protectedDecision = decisionForMask(
    (1 << CLASSIFICATION_SIGNALS.indexOf("AMBIGUOUS")) |
      (1 << CLASSIFICATION_SIGNALS.indexOf("HIGH_STAKES")),
  );
  const regressions = [
    { ...protectedDecision, work_class: "E4" },
    { ...protectedDecision, human_gate_required: false },
    { ...protectedDecision, required_phases: ["F", "O", "R", "G", "E"] },
    { ...protectedDecision, default_role_count: 10 },
    { ...protectedDecision, required_phases: ["I", "F", "O", "R", "E"] },
  ];
  for (const candidate of regressions) {
    assert.throws(
      () => assertMonotonicProtection(protectedDecision, candidate),
      expectCode("UNDERPROCESSING_MONOTONICITY_VIOLATION"),
    );
  }
});
