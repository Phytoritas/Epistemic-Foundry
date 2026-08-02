import assert from "node:assert/strict";
import test from "node:test";

import {
  ClassificationCommitterError,
  EpistemicWorkClassifierError,
  sha256ClassificationJson,
} from "./index.mjs";
import {
  classificationInput,
  createClassifierFixture,
  testHash,
} from "./classifier-test-support.mjs";

const expectCode = (code) => (error) =>
  (error instanceof ClassificationCommitterError ||
    error instanceof EpistemicWorkClassifierError) &&
  error.code === code;

const humanDecisionFor = (base, runId, label) => {
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
    created_at: "2026-07-29T01:45:00.000Z",
  };
  return { ...decision, decision_hash: sha256ClassificationJson(decision) };
};

const registerHumanDecision = (
  fixture,
  decision,
  { actorType = "human", schemaRef = "schemas/human-decision.schema.json" } = {},
) => {
  fixture.artifactStore.putArtifact(Buffer.from(JSON.stringify(decision), "utf8"), {
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
      createdBy: { actorId: decision.authority_id, actorType },
      receiptId: `AR-${decision.decision_id}`,
      schemaRef,
      validationResults: [
        { check: "human_decision_fixture", status: "PASS", details: decision.decision_hash },
      ],
    },
  });
};

test("classification committer: commit, retry, replay, reclassification, and override preserve immutable identity", (t) => {
  const fixture = createClassifierFixture(t);
  const initialInput = classificationInput({
    requestId: "REQ-F01-lifecycle",
    requestText: "Look up the specified source fact.",
    requestSignals: ["LOOKUP"],
  });

  const first = fixture.committer.classify(initialInput);
  assert.equal(first.status, "CREATED");
  assert.equal(first.classification.work_class, "E1");
  assert.equal(first.classification.classified_at, "2026-07-29T00:00:00.000Z");
  assert.equal(first.artifact_receipt.artifact_id, first.classification.classification_id);
  assert.match(first.artifact_receipt.content_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.deepEqual(
    first.artifact_receipt.validation_results.find(
      ({ check }) => check === "epistemic_work_classification_contract",
    ),
    {
      check: "epistemic_work_classification_contract",
      status: "PASS",
      details: first.classification.classification_hash,
    },
  );
  assert.deepEqual(
    JSON.parse(
      fixture.artifactStore
        .readArtifact(first.classification.classification_id)
        .toString("utf8"),
    ),
    first.classification,
  );
  assert.deepEqual(
    fixture.ledger.readEvents(initialInput.run_id).map((event) => event.event_type),
    ["forge.epistemic-work.classified"],
  );

  fixture.setTime("2026-07-29T00:30:00.000Z");
  const retry = fixture.committer.classify(initialInput);
  assert.equal(retry.status, "EXISTING");
  assert.deepEqual(retry.classification, first.classification);
  assert.deepEqual(retry.artifact_receipt, first.artifact_receipt);
  assert.equal(fixture.artifactStore.enumerateArtifacts().length, 1);
  assert.equal(fixture.artifactStore.enumerateReceipts().length, 1);
  assert.equal(fixture.ledger.readEvents(initialInput.run_id).length, 1);

  const replay = fixture.committer.strictReplay(
    first.classification.classification_id,
    initialInput,
  );
  assert.deepEqual(replay.classification, first.classification);

  fixture.setTime("2026-07-29T01:00:00.000Z");
  const reclassificationInput = {
    ...initialInput,
    policy_bundle_hash: testHash("F01-policy-high-stakes"),
    policy_bundle_signals: ["HIGH_STAKES"],
  };
  const reclassified = fixture.committer.classify(reclassificationInput);
  assert.equal(reclassified.status, "CREATED");
  assert.equal(reclassified.classification.work_class, "E4");
  assert.equal(reclassified.classification.human_gate_required, true);
  assert.notEqual(
    reclassified.classification.classification_id,
    first.classification.classification_id,
  );
  assert.deepEqual(
    fixture.committer.readClassification(first.classification.classification_id).classification,
    first.classification,
  );
  assert.deepEqual(
    fixture.committer.readActiveClassification(initialInput.request_id).classification,
    reclassified.classification,
  );

  fixture.setTime("2026-07-29T02:00:00.000Z");
  const humanDecision = humanDecisionFor(
    reclassified.classification,
    initialInput.run_id,
    "F01-human-override-E5",
  );
  registerHumanDecision(fixture, humanDecision);
  const humanDecisionHash = humanDecision.decision_hash;
  const overridden = fixture.committer.override({
    request_id: initialInput.request_id,
    base_classification_id: reclassified.classification.classification_id,
    target_work_class: "E5",
    add_interview: true,
    interview_rule: "I04_MISSING_SCOPE",
    human_decision_id: humanDecision.decision_id,
    human_decision_hash: humanDecisionHash,
  });
  assert.equal(overridden.status, "CREATED");
  assert.equal(overridden.classification.work_class, "E5");
  assert.deepEqual(overridden.classification.required_phases, ["I", "F", "O", "R", "G", "E"]);
  assert.equal(
    overridden.classification.reasons.at(-1),
    `OVERRIDE:${humanDecisionHash}`,
  );
  assert.deepEqual(
    fixture.committer.readActiveClassification(initialInput.request_id).classification,
    overridden.classification,
  );
  assert.deepEqual(
    fixture.ledger.readEvents(initialInput.run_id).map((event) => event.event_type),
    [
      "forge.epistemic-work.classified",
      "forge.epistemic-work.reclassified",
      "forge.epistemic-work.override-recorded",
    ],
  );
  const supersessionEvents = fixture.ledger.readEvents(initialInput.run_id).slice(1);
  assert.deepEqual(
    supersessionEvents.map((event) => ({
      aggregate_type: event.aggregate_type,
      aggregate_id: event.aggregate_id,
      payload_artifact_id: event.payload_artifact_id,
    })),
    [
      {
        aggregate_type: "epistemic_work_classification_supersession",
        aggregate_id: first.classification.classification_id,
        payload_artifact_id: reclassified.classification.classification_id,
      },
      {
        aggregate_type: "epistemic_work_classification_supersession",
        aggregate_id: reclassified.classification.classification_id,
        payload_artifact_id: overridden.classification.classification_id,
      },
    ],
  );
  assert.equal(fixture.artifactStore.enumerateArtifacts().length, 4);
  assert.equal(fixture.artifactStore.enumerateReceipts().length, 4);

  fixture.setTime("2026-07-29T03:00:00.000Z");
  const overrideRetry = fixture.committer.override({
    request_id: initialInput.request_id,
    base_classification_id: reclassified.classification.classification_id,
    target_work_class: "E5",
    add_interview: true,
    interview_rule: "I04_MISSING_SCOPE",
    human_decision_id: humanDecision.decision_id,
    human_decision_hash: humanDecisionHash,
  });
  assert.equal(overrideRetry.status, "EXISTING");
  assert.deepEqual(overrideRetry.classification, overridden.classification);
  assert.equal(fixture.ledger.readEvents(initialInput.run_id).length, 3);
  assert.deepEqual(fixture.committer.reconcileEvents(), {
    total: 3,
    published: 0,
    existing: 3,
  });
});

test("classification committer: same idempotency key with a changed preimage fails closed", (t) => {
  const fixture = createClassifierFixture(t);
  const input = classificationInput({
    requestId: "REQ-F01-idempotency",
    requestText: "Look up the specified source fact.",
    requestSignals: ["LOOKUP"],
  });
  fixture.committer.classify(input);
  assert.throws(
    () =>
      fixture.committer.classify({
        ...input,
        deterministic_detector_signals: ["CAUSAL"],
      }),
    expectCode("IDEMPOTENCY_CONFLICT"),
  );
  assert.equal(fixture.artifactStore.enumerateArtifacts().length, 1);
  assert.equal(fixture.ledger.readEvents(input.run_id).length, 1);
});

test("classification committer: same-revision lowering and stale override are rejected without mutation", (t) => {
  const fixture = createClassifierFixture(t);
  const input = classificationInput({
    requestId: "REQ-F01-override-denial",
    requestText: "Evaluate the causal effect in a high-stakes decision.",
    requestSignals: ["CAUSAL", "HIGH_STAKES"],
  });
  const initial = fixture.committer.classify(input);
  const humanDecision = humanDecisionFor(
    initial.classification,
    input.run_id,
    "F01-illegal-lowering",
  );
  registerHumanDecision(fixture, humanDecision);
  assert.throws(
    () =>
      fixture.committer.override({
        request_id: input.request_id,
        base_classification_id: initial.classification.classification_id,
        target_work_class: "E1",
        add_interview: false,
        interview_rule: null,
        human_decision_id: humanDecision.decision_id,
        human_decision_hash: humanDecision.decision_hash,
      }),
    expectCode("HUMAN_OVERRIDE_LOWERING_DENIED"),
  );
  assert.deepEqual(
    fixture.committer.readActiveClassification(input.request_id).classification,
    initial.classification,
  );
  assert.equal(fixture.artifactStore.enumerateArtifacts().length, 2);
  assert.equal(fixture.ledger.readEvents(input.run_id).length, 1);
});

test("classification committer: only a resolved canonical HumanDecision can authorize override", (t) => {
  const fixture = createClassifierFixture(t);
  const input = classificationInput({
    requestId: "REQ-F01-unresolved-human-decision",
    requestText: "Synthesize the bounded evidence.",
    requestSignals: ["SYNTHESIS"],
  });
  const initial = fixture.committer.classify(input);
  const command = {
    request_id: input.request_id,
    base_classification_id: initial.classification.classification_id,
    target_work_class: "E4",
    add_interview: false,
    interview_rule: null,
    human_decision_hash: testHash("F01-arbitrary-unresolved-decision"),
  };

  assert.throws(
    () => fixture.committer.override(command),
    expectCode("HUMAN_DECISION_ARTIFACT_REQUIRED"),
  );
  assert.throws(
    () =>
      fixture.committer.override({
        ...command,
        human_decision_id: "HD-F01-does-not-exist",
      }),
    expectCode("HUMAN_DECISION_ARTIFACT_INVALID"),
  );
  assert.deepEqual(
    fixture.committer.readActiveClassification(input.request_id).classification,
    initial.classification,
  );
  assert.equal(fixture.artifactStore.enumerateArtifacts().length, 1);
  assert.equal(fixture.ledger.readEvents(input.run_id).length, 1);

  const humanDecision = humanDecisionFor(
    initial.classification,
    input.run_id,
    "F01-resolved-human-decision",
  );
  registerHumanDecision(fixture, humanDecision);
  assert.throws(
    () =>
      fixture.committer.override({
        ...command,
        human_decision_id: humanDecision.decision_id,
      }),
    expectCode("HUMAN_DECISION_INTEGRITY_FAILED"),
  );
  assert.equal(fixture.ledger.readEvents(input.run_id).length, 1);

  const accepted = fixture.committer.override({
    ...command,
    human_decision_id: humanDecision.decision_id,
    human_decision_hash: humanDecision.decision_hash,
  });
  assert.equal(accepted.status, "CREATED");
  assert.equal(accepted.classification.work_class, "E4");
  assert.equal(
    accepted.classification.reasons.at(-1),
    `OVERRIDE:${humanDecision.decision_hash}`,
  );
  assert.equal(fixture.artifactStore.enumerateArtifacts().length, 3);
  assert.equal(fixture.ledger.readEvents(input.run_id).length, 2);
});

test("classification committer: non-correct or non-human decisions cannot authorize override", (t) => {
  const fixture = createClassifierFixture(t);
  const input = classificationInput({
    requestId: "REQ-F01-human-authority-semantics",
    requestText: "Synthesize the bounded evidence.",
    requestSignals: ["SYNTHESIS"],
  });
  const initial = fixture.committer.classify(input);
  const commandFor = (decision) => ({
    request_id: input.request_id,
    base_classification_id: initial.classification.classification_id,
    target_work_class: "E4",
    add_interview: false,
    interview_rule: null,
    human_decision_id: decision.decision_id,
    human_decision_hash: decision.decision_hash,
  });

  const rejectionPreimage = {
    ...humanDecisionFor(initial.classification, input.run_id, "F01-reject-is-not-authority"),
    decision_type: "reject",
    decision: "Reject the requested classification override.",
  };
  delete rejectionPreimage.decision_hash;
  const rejection = {
    ...rejectionPreimage,
    decision_hash: sha256ClassificationJson(rejectionPreimage),
  };
  registerHumanDecision(fixture, rejection);
  assert.throws(
    () => fixture.committer.override(commandFor(rejection)),
    expectCode("HUMAN_DECISION_AUTHORITY_MISMATCH"),
  );

  const serviceDecision = humanDecisionFor(
    initial.classification,
    input.run_id,
    "F01-service-cannot-claim-human-authority",
  );
  registerHumanDecision(fixture, serviceDecision, { actorType: "service" });
  assert.throws(
    () => fixture.committer.override(commandFor(serviceDecision)),
    expectCode("HUMAN_DECISION_AUTHORITY_MISMATCH"),
  );

  assert.deepEqual(
    fixture.committer.readActiveClassification(input.request_id).classification,
    initial.classification,
  );
  assert.equal(fixture.ledger.readEvents(input.run_id).length, 1);
});
