import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  CLASSIFIER_VERSION,
  evaluateEpistemicWork,
  classificationInputHash,
} from "./epistemic-work-classifier.mjs";
import { testHash } from "./classifier-test-support.mjs";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../..",
);
const fixture = JSON.parse(
  fs.readFileSync(
    path.join(repositoryRoot, "tests/golden/forge/f01_classifier_gold_cases.json"),
    "utf8",
  ),
);

const project = (decision) => ({
  accepted_signals: decision.accepted_signals,
  work_class: decision.work_class,
  required_phases: decision.required_phases,
  default_role_count: decision.default_role_count,
  human_gate_required: decision.human_gate_required,
});

test("classifier_gold_test: all 14 fixed cases have exact deterministic projections", () => {
  assert.equal(fixture.classifier_version, CLASSIFIER_VERSION);
  assert.equal(fixture.cases.length, 14);
  for (const row of fixture.cases) {
    const decision = evaluateEpistemicWork({
      run_id: `RUN-${row.case_id}`,
      request_id: `REQ-${row.case_id}`,
      request_text: row.request_text,
      request_input_hash: classificationInputHash(row.request_text),
      classifier_version: fixture.classifier_version,
      policy_bundle_hash: testHash("F01-gold-policy"),
      policy_bundle_signals: row.policy_bundle_signals,
      typed_request_metadata: row.typed_request_metadata,
      deterministic_detector_signals: row.deterministic_detector_signals,
      llm_signal_proposals: row.llm_signal_proposals,
      missing_contract_flags: row.missing_contract_flags,
    });
    assert.deepEqual(project(decision), row.expected, row.case_id);
    assert.equal(
      decision.reasons.includes(`FLOOR:${decision.floor_work_class}`),
      true,
      row.case_id,
    );
  }
});

test("classifier_gold_test: input ordering and duplicate signals do not change identity", () => {
  const base = {
    run_id: "RUN-F01-order",
    request_id: "REQ-F01-order",
    request_text: "Synthesize evidence and assess a causal mechanism.",
    request_input_hash: classificationInputHash(
      "Synthesize evidence and assess a causal mechanism.",
    ),
    classifier_version: CLASSIFIER_VERSION,
    policy_bundle_hash: testHash("F01-order-policy"),
    policy_bundle_signals: [],
    typed_request_metadata: { signals: ["SYNTHESIS", "CAUSAL", "CAUSAL"] },
    deterministic_detector_signals: ["LOOKUP"],
    llm_signal_proposals: [],
    missing_contract_flags: [],
  };
  const left = evaluateEpistemicWork(base);
  const right = evaluateEpistemicWork({
    ...base,
    typed_request_metadata: { signals: ["CAUSAL", "SYNTHESIS"] },
    deterministic_detector_signals: ["LOOKUP", "LOOKUP"],
  });
  assert.deepEqual(right.accepted_signals, ["CAUSAL", "SYNTHESIS", "LOOKUP"]);
  assert.deepEqual(right.reasons, left.reasons);
  assert.equal(right.classification_hash, left.classification_hash);
  assert.equal(right.classification_id, left.classification_id);
});
