import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  EpistemicWorkClassifierError,
  applyHumanClassificationOverride,
  evaluateEpistemicWork,
  sha256ClassificationJson,
} from "./epistemic-work-classifier.mjs";
import { classificationInput, testHash } from "./classifier-test-support.mjs";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../..",
);
const fixture = JSON.parse(
  fs.readFileSync(
    path.join(repositoryRoot, "tests/golden/forge/f01_classifier_override_cases.json"),
    "utf8",
  ),
);

const expectCode = (code) => (error) =>
  error instanceof EpistemicWorkClassifierError && error.code === code;

const humanDecisionFor = (base, label) => {
  const decision = {
    decision_id: `HD-${label}`,
    run_id: base.run_id,
    subject_id: base.classification_id,
    decision_type: "correct",
    decision: `Authorize an upward-only classification override for ${base.classification_id}.`,
    authority_id: "HUMAN-F01-test-authority",
    authority_role: "product_owner",
    rationale: "Exercise the immutable canonical HumanDecision override contract.",
    evidence_artifact_ids: [base.classification_id],
    affected_artifact_ids: [base.classification_id],
    supersedes_decision_id: null,
    non_mutation_acknowledgement: true,
    created_at: "2026-07-29T00:45:00.000Z",
  };
  return { ...decision, decision_hash: sha256ClassificationJson(decision) };
};

test("classifier_immutable_override_test: every fixed override is upward-only and immutable", () => {
  assert.equal(fixture.cases.length, 6);
  for (const row of fixture.cases) {
    const base = evaluateEpistemicWork(
      classificationInput({
        runId: `RUN-${row.case_id}`,
        requestId: `REQ-${row.case_id}`,
        requestText: `fixed override case ${row.case_id}`,
        policyBundleHash: testHash(`F01-override-policy-${row.case_id}`),
        requestSignals: row.base_signals,
      }),
    );
    const humanDecision = humanDecisionFor(base, `F01-${row.case_id}`);
    const command = {
      target_work_class: row.target_work_class,
      add_interview: row.add_interview,
      interview_rule: row.interview_rule,
      human_decision: humanDecision,
      human_decision_hash: humanDecision.decision_hash,
    };
    if (row.expected_error !== undefined) {
      assert.throws(
        () => applyHumanClassificationOverride(base, command),
        expectCode(row.expected_error),
        row.case_id,
      );
      assert.equal(base.supersedes_classification_hash, null, row.case_id);
      continue;
    }
    const overridden = applyHumanClassificationOverride(base, command);
    assert.deepEqual(
      {
        work_class: overridden.work_class,
        required_phases: overridden.required_phases,
        default_role_count: overridden.default_role_count,
        human_gate_required: overridden.human_gate_required,
      },
      row.expected,
      row.case_id,
    );
    assert.equal(
      overridden.supersedes_classification_hash,
      base.classification_hash,
      row.case_id,
    );
    assert.equal(overridden.human_decision_hash, command.human_decision_hash, row.case_id);
    assert.notEqual(overridden.classification_id, base.classification_id, row.case_id);
    assert.equal(
      overridden.reasons.at(-1),
      `OVERRIDE:${command.human_decision_hash}`,
      row.case_id,
    );
  }
});
