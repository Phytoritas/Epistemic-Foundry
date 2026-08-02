import assert from "node:assert/strict";
import test from "node:test";

import { evaluateFanInGate } from "./fan-in-gate.mjs";
import {
  buildFanInFixture,
  expectFanInCode,
  resealIndependentReview,
} from "./fan-in-test-support.mjs";

test("independent_review_test: a distinct actor and independence group can approve full maker scope", () => {
  const fixture = buildFanInFixture();
  const decision = evaluateFanInGate(fixture);
  assert.equal(decision.status, "PASS");
  assert.equal(decision.reviewer_role_id, "independent_reviewer");
  assert.equal(decision.maker_terminal_receipt_ids.length, 2);
  assert.notEqual(decision.reviewer_actor_id, "ACTOR-N04-maker-alpha");
  assert.notEqual(decision.reviewer_actor_id, "ACTOR-N04-maker-beta");
});

test("independent_review_test: an absent review cannot be inferred from successful execution", () => {
  const fixture = buildFanInFixture();
  fixture.independentReview = null;
  expectFanInCode(assert, "INDEPENDENT_REVIEW_MISSING", () => evaluateFanInGate(fixture));
});

test("independent_review_test: an author cannot self-approve", () => {
  const fixture = buildFanInFixture({
    makerActorIds: ["ACTOR-N04-shared", "ACTOR-N04-maker-beta"],
    reviewerActorId: "ACTOR-N04-shared",
  });
  expectFanInCode(assert, "REVIEWER_SELF_APPROVAL", () => evaluateFanInGate(fixture));
});

test("independent_review_test: reviewer cannot share a maker independence group", () => {
  const fixture = buildFanInFixture({
    makerIndependenceGroups: ["shared_group", "maker_beta_group"],
    reviewerIndependenceGroup: "shared_group",
  });
  expectFanInCode(assert, "REVIEWER_NOT_INDEPENDENT", () => evaluateFanInGate(fixture));
});

test("independent_review_test: only a PASS verdict satisfies the gate", () => {
  const fixture = buildFanInFixture({ reviewVerdict: "FAIL" });
  expectFanInCode(assert, "INDEPENDENT_REVIEW_NOT_PASS", () => evaluateFanInGate(fixture));
});

test("independent_review_test: review scope must contain every and only maker receipt", () => {
  const missing = buildFanInFixture();
  const missingReview = structuredClone(missing.independentReview);
  missingReview.reviewed_terminal_receipt_ids = missingReview.reviewed_terminal_receipt_ids.slice(0, 1);
  missing.independentReview = resealIndependentReview(missingReview);
  expectFanInCode(assert, "REVIEW_SCOPE_MISMATCH", () => evaluateFanInGate(missing));

  const extra = buildFanInFixture();
  const extraReview = structuredClone(extra.independentReview);
  extraReview.reviewed_terminal_receipt_ids.push("RR-N04-unexpected-maker");
  extra.independentReview = resealIndependentReview(extraReview);
  expectFanInCode(assert, "REVIEW_SCOPE_MISMATCH", () => evaluateFanInGate(extra));
});

test("independent_review_test: review binds the exact dispatch and replayed scheduler state", () => {
  const fixture = buildFanInFixture();
  const review = structuredClone(fixture.independentReview);
  review.scheduler_state_hash = `sha256:${"f".repeat(64)}`;
  fixture.independentReview = resealIndependentReview(review);
  expectFanInCode(assert, "REVIEW_EXECUTION_BINDING_MISMATCH", () =>
    evaluateFanInGate(fixture),
  );
});

test("independent_review_test: every maker output and output hash is in review scope", () => {
  const fixture = buildFanInFixture();
  fixture.resultSubmissions = structuredClone(fixture.resultSubmissions);
  const maker = fixture.resultSubmissions[0].result_envelope;
  maker.output_artifact_ids = ["ART-N04-maker-alpha-replaced"];
  maker.output_hash = `sha256:${"e".repeat(64)}`;
  expectFanInCode(assert, "REVIEW_RESULT_SCOPE_MISMATCH", () => evaluateFanInGate(fixture));
});

test("independent_review_test: reviewer must be scheduled after every maker role", () => {
  const fixture = buildFanInFixture({ reviewerDependsOn: [] });
  expectFanInCode(assert, "REVIEWER_DEPENDENCY_MISMATCH", () =>
    evaluateFanInGate(fixture),
  );
});

test("independent_review_test: review hash and derived ID reject mutation", () => {
  const hashTamper = buildFanInFixture();
  hashTamper.independentReview = structuredClone(hashTamper.independentReview);
  hashTamper.independentReview.verdict = "FAIL";
  expectFanInCode(assert, "REVIEW_HASH_MISMATCH", () => evaluateFanInGate(hashTamper));

  const idTamper = buildFanInFixture();
  idTamper.independentReview = structuredClone(idTamper.independentReview);
  idTamper.independentReview.review_id = `REVIEW-${"f".repeat(64)}`;
  expectFanInCode(assert, "REVIEW_ID_MISMATCH", () => evaluateFanInGate(idTamper));
});

test("independent_review_test: reviewer actor and receipt must bind the N03 terminal attempt", () => {
  const actorMismatch = buildFanInFixture();
  const actorReview = structuredClone(actorMismatch.independentReview);
  actorReview.reviewer_actor_id = "ACTOR-N04-not-the-scheduler-owner";
  actorMismatch.independentReview = resealIndependentReview(actorReview);
  expectFanInCode(assert, "REVIEWER_ACTOR_MISMATCH", () => evaluateFanInGate(actorMismatch));

  const receiptMismatch = buildFanInFixture();
  const receiptReview = structuredClone(receiptMismatch.independentReview);
  receiptReview.reviewer_terminal_receipt_id = "RR-N04-not-the-reviewer-receipt";
  receiptMismatch.independentReview = resealIndependentReview(receiptReview);
  expectFanInCode(assert, "REVIEWER_RECEIPT_MISMATCH", () => evaluateFanInGate(receiptMismatch));
});

test("independent_review_test: reviewer ResultEnvelope must emit the sealed review artifact", () => {
  const fixture = buildFanInFixture();
  fixture.resultSubmissions = structuredClone(fixture.resultSubmissions);
  fixture.resultSubmissions[2].result_envelope.output_artifact_ids = ["ART-N04-prose-summary"];
  expectFanInCode(assert, "REVIEW_ARTIFACT_BINDING_MISSING", () => evaluateFanInGate(fixture));
});
