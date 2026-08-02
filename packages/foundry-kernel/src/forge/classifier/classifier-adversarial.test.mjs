import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  EpistemicWorkClassifierError,
  assertClassificationArtifactIntegrity,
  assertMonotonicProtection,
  assertStrictClassificationReplay,
  evaluateEpistemicWork,
  materializeClassificationArtifact,
  sha256ClassificationJson,
  validateClassificationResultEnvelope,
  validateClassifierCapabilities,
} from "./index.mjs";
import {
  ClassificationCommitterError,
} from "./classification-committer.mjs";
import {
  classificationInput,
  createClassifierFixture,
  testHash,
} from "./classifier-test-support.mjs";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../..",
);
const fixture = JSON.parse(
  fs.readFileSync(
    path.join(repositoryRoot, "tests/golden/forge/f01_classifier_adversarial_cases.json"),
    "utf8",
  ),
);

const expectCode = (code) => (error) =>
  (error instanceof EpistemicWorkClassifierError ||
    error instanceof ClassificationCommitterError) &&
  error.code === code;

const decisionInput = (row, overrides = {}) =>
  classificationInput({
    runId: `RUN-${row.case_id}`,
    requestId: `REQ-${row.case_id}`,
    requestText: row.request_text,
    policyBundleHash: testHash(`F01-adversarial-policy-${row.case_id}`),
    policySignals: row.policy_bundle_signals ?? [],
    requestSignals: row.typed_request_metadata?.signals ?? row.signals ?? [],
    detectorSignals: row.deterministic_detector_signals ?? [],
    proposals: row.llm_signal_proposals ?? [],
    missingContractFlags: row.missing_contract_flags ?? [],
    ...overrides,
  });

const projection = (decision) => ({
  accepted_signals: decision.accepted_signals,
  work_class: decision.work_class,
  required_phases: decision.required_phases,
  default_role_count: decision.default_role_count,
  human_gate_required: decision.human_gate_required,
});

const humanDecisionFor = (base, label, { runId = base.run_id } = {}) => {
  const decision = {
    decision_id: `HD-${label}`,
    run_id: runId,
    subject_id: base.classification_id,
    decision_type: "correct",
    decision: `Authorize an upward-only classification override for ${base.classification_id}.`,
    authority_id: "HUMAN-F01-test-authority",
    authority_role: "product_owner",
    rationale: "Exercise the immutable resolved HumanDecision override contract.",
    evidence_artifact_ids: [base.classification_id],
    affected_artifact_ids: [base.classification_id],
    supersedes_decision_id: null,
    non_mutation_acknowledgement: true,
    created_at: "2026-07-29T00:45:00.000Z",
  };
  return { ...decision, decision_hash: sha256ClassificationJson(decision) };
};

const registerHumanDecision = (lifecycle, decision) => {
  lifecycle.artifactStore.putArtifact(Buffer.from(JSON.stringify(decision), "utf8"), {
    artifact: {
      artifactId: decision.decision_id,
      artifactType: "human_decision",
      confidentiality: "internal",
      createdAt: decision.created_at,
      createdBy: decision.authority_id,
      encryption: { atRest: true, inTransit: true, keyRef: "local://f01-test-key" },
      inputArtifactIds: decision.evidence_artifact_ids,
      license: null,
      lineageEventIds: [],
      mediaType: "application/json",
      provenanceManifestId: `PROV-${decision.decision_id}`,
      retentionClass: "project",
    },
    receipt: {
      actionIntentId: null,
      createdAt: decision.created_at,
      createdBy: { actorId: decision.authority_id, actorType: "human" },
      receiptId: `AR-${decision.decision_id}`,
      schemaRef: "schemas/human-decision.schema.json",
      validationResults: [
        { check: "human_decision_fixture", status: "PASS", details: decision.decision_hash },
      ],
    },
  });
};

const permutations = (items) => {
  if (items.length === 0) return [[]];
  return items.flatMap((item, index) =>
    permutations([...items.slice(0, index), ...items.slice(index + 1)]).map((tail) => [
      item,
      ...tail,
    ]),
  );
};

test("classifier_adversarial_test: all 16 fixed attacks fail closed or preserve the exact projection", async (t) => {
  assert.equal(fixture.classifier_version, "4.0.1-f01.1");
  assert.equal(fixture.cases.length, 16);

  for (const row of fixture.cases) {
    await t.test(row.case_id, () => {
      switch (row.case_id) {
        case "A01_USER_DEMANDS_E0":
        case "A02_PROMPT_INJECTION_IN_SOURCE":
        case "A03_LLM_OMITS_HARD_SIGNAL":
        case "A07_DUPLICATE_SIGNALS": {
          const decision = evaluateEpistemicWork(decisionInput(row));
          assert.deepEqual(projection(decision), row.expected);
          break;
        }
        case "A04_LLM_PROPOSES_UNKNOWN_SIGNAL":
        case "A05_UNSUPPORTED_LLM_PROPOSAL": {
          const decision = evaluateEpistemicWork(decisionInput(row));
          assert.deepEqual(projection(decision), row.expected);
          assert.equal(
            decision.classifier_trace.llm_proposals[0].reason,
            row.expected_rejection_reason,
          );
          assert.equal(
            decision.accepted_signals.includes(
              row.llm_signal_proposals[0].signal,
            ),
            false,
          );
          break;
        }
        case "A06_SIGNAL_ORDER_PERMUTATION": {
          const decisions = permutations(row.signals).map((signals) =>
            evaluateEpistemicWork(decisionInput(row, { requestSignals: signals })),
          );
          const [reference] = decisions;
          assert.deepEqual(
            {
              accepted_signals: reference.accepted_signals,
              work_class: reference.work_class,
            },
            row.expected,
          );
          for (const decision of decisions.slice(1)) {
            assert.deepEqual(decision.reasons, reference.reasons);
            assert.equal(decision.classification_hash, reference.classification_hash);
            assert.equal(decision.classification_id, reference.classification_id);
          }
          break;
        }
        case "A08_MONOTONIC_ADDITION": {
          const initial = evaluateEpistemicWork(
            decisionInput(row, { requestSignals: row.initial_signals }),
          );
          const final = evaluateEpistemicWork(
            decisionInput(row, {
              requestSignals: [...row.initial_signals, ...row.additional_signals],
            }),
          );
          assert.equal(initial.work_class, row.expected_initial_class);
          assert.equal(final.work_class, row.expected_final_class);
          assert.equal(assertMonotonicProtection(initial, final), true);
          break;
        }
        case "A09_OVERRIDE_LOWERING": {
          const base = evaluateEpistemicWork(
            decisionInput(row, { requestSignals: row.base_signals }),
          );
          assert.throws(
            () =>
              fixtureOverride(base, row.target_work_class, false, null, row.case_id),
            expectCode(row.expected_error),
          );
          assert.equal(base.work_class, "E4");
          break;
        }
        case "A10_OVERRIDE_RAISE": {
          const lifecycle = createClassifierFixture(t);
          const input = decisionInput(row, {
            requestSignals: row.base_signals,
            runId: `RUN-${row.case_id}`,
            requestId: `REQ-${row.case_id}`,
          });
          const first = lifecycle.committer.classify(input);
          const humanDecision = humanDecisionFor(first.classification, `F01-${row.case_id}`, {
            runId: input.run_id,
          });
          registerHumanDecision(lifecycle, humanDecision);
          lifecycle.setTime("2026-07-29T01:00:00.000Z");
          const raised = lifecycle.committer.override({
            request_id: input.request_id,
            base_classification_id: first.classification.classification_id,
            target_work_class: row.target_work_class,
            add_interview: false,
            interview_rule: null,
            human_decision_id: humanDecision.decision_id,
            human_decision_hash: humanDecision.decision_hash,
          });
          assert.equal(raised.classification.work_class, row.expected_work_class);
          assert.deepEqual(
            lifecycle.committer.readClassification(first.classification.classification_id)
              .classification,
            first.classification,
          );
          assert.equal(
            lifecycle.committer.readActiveClassification(input.request_id).classification
              .classification_id,
            raised.classification.classification_id,
          );
          const edge = lifecycle.ledger.readEvents(input.run_id).at(-1);
          assert.equal(edge.event_type, row.expected_event_type);
          assert.equal(edge.aggregate_id, first.classification.classification_id);
          assert.equal(edge.payload_artifact_id, raised.classification.classification_id);
          break;
        }
        case "A11_RESULT_ENVELOPE_ONLY":
          assert.throws(
            () => validateClassificationResultEnvelope(row.result_envelope, null),
            expectCode(row.expected_error),
          );
          break;
        case "A12_CAPABILITY_ALIAS":
          for (const capabilities of row.capability_sets) {
            assert.throws(
              () => validateClassifierCapabilities(capabilities),
              expectCode(row.expected_error),
            );
          }
          break;
        case "A13_RETRY_IDENTITY": {
          const lifecycle = createClassifierFixture(t);
          const input = decisionInput(row, { requestSignals: row.signals });
          const first = lifecycle.committer.classify(input);
          lifecycle.setTime("2026-07-29T05:00:00.000Z");
          const retry = lifecycle.committer.classify(input);
          assert.equal(retry.status, "EXISTING");
          assert.deepEqual(retry.classification, first.classification);
          assert.deepEqual(retry.artifact_receipt, first.artifact_receipt);
          assert.equal(
            lifecycle.artifactStore.enumerateArtifacts().length,
            row.expected_artifact_count,
          );
          break;
        }
        case "A14_HASH_SELF_FIELD_MUTATION": {
          const decision = evaluateEpistemicWork(
            decisionInput(row, { requestSignals: row.signals }),
          );
          const identityContext = {
            request_input_hash: decision.request_input_hash,
            policy_bundle_hash: decision.policy_bundle_hash,
            accepted_signals: decision.accepted_signals,
            supersedes_classification_hash: decision.supersedes_classification_hash,
            human_decision_hash: decision.human_decision_hash,
          };
          const recorded = materializeClassificationArtifact(
            decision,
            row.initial_classified_at,
          );
          const timestampMutation = {
            ...recorded,
            classified_at: row.mutated_classified_at,
          };
          assert.equal(
            assertClassificationArtifactIntegrity(timestampMutation, identityContext),
            true,
          );
          assert.equal(timestampMutation.classification_hash, recorded.classification_hash);
          assert.throws(
            () => assertStrictClassificationReplay(recorded, timestampMutation),
            expectCode(row.expected_replay_error),
          );
          assert.throws(
            () =>
              assertClassificationArtifactIntegrity(
                { ...recorded, classification_id: `EWC-${"f".repeat(64)}` },
                identityContext,
              ),
            expectCode(row.expected_identity_error),
          );
          break;
        }
        case "A15_AMBIGUITY_REMOVAL_SAME_REVISION": {
          const initial = evaluateEpistemicWork(
            decisionInput(row, { requestSignals: row.initial_signals }),
          );
          const later = evaluateEpistemicWork(
            decisionInput(row, { requestSignals: row.later_signals }),
            {
              prior_classification: {
                request_id: initial.request_id,
                accepted_signals: initial.accepted_signals,
              },
            },
          );
          assert.deepEqual(later.accepted_signals, row.expected_signals);
          assert.equal(later.work_class, row.expected_work_class);
          assert.equal(later.required_phases[0], "I");
          break;
        }
        case "A16_LLM_DIRECT_CLASS_OUTPUT": {
          const decision = evaluateEpistemicWork(decisionInput(row));
          assert.deepEqual(projection(decision), row.expected);
          assert.deepEqual(
            decision.classifier_trace.llm_proposals[0].ignored_fields,
            row.expected_ignored_fields,
          );
          break;
        }
        default:
          assert.fail(`unhandled adversarial case ${row.case_id}`);
      }
    });
  }
});

test("classifier authority guards reject a forged request hash and any non-frozen version", () => {
  const row = fixture.cases[0];
  const valid = decisionInput(row);
  assert.throws(
    () =>
      evaluateEpistemicWork({
        ...valid,
        request_input_hash: testHash("F01-forged-request-hash"),
      }),
    expectCode("REQUEST_INPUT_HASH_MISMATCH"),
  );
  assert.throws(
    () =>
      evaluateEpistemicWork({
        ...valid,
        classifier_version: "4.0.1-f01.2",
      }),
    expectCode("CLASSIFIER_VERSION_MISMATCH"),
  );
});

function fixtureOverride(base, targetWorkClass, addInterview, interviewRule, label) {
  const humanDecision = humanDecisionFor(base, `F01-${label}`);
  return importOverride(base, {
    target_work_class: targetWorkClass,
    add_interview: addInterview,
    interview_rule: interviewRule,
    human_decision: humanDecision,
    human_decision_hash: humanDecision.decision_hash,
  });
}

function importOverride(base, command) {
  return overrideImplementation(base, command);
}

import { applyHumanClassificationOverride as overrideImplementation } from "./epistemic-work-classifier.mjs";
