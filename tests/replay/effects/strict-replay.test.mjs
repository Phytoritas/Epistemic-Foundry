import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { E03_IDS } from "../../../packages/foundry-kernel/src/capabilities/capability-test-support.mjs";
import { NoeticLedgerError } from "../../../packages/foundry-kernel/src/ledger/noetic-ledger.mjs";
import {
  E04_IDS,
  assertReplayReportIntegrity,
  createEPhaseReplayFixture,
  emptyEPhaseReplayState,
  executeEPhaseScenario,
  liveEPhaseProjection,
  payloadContentPath,
  reduceEPhaseEvent,
  replayPins,
  sealReplayReport,
  validateReplayReportSchema,
} from "./replay-test-support.mjs";

const expectLedgerCode = (...codes) => (error) =>
  error instanceof NoeticLedgerError && codes.includes(error.code);

const rebuild = (ledger) =>
  ledger.rebuild(E04_IDS.RUN, {
    initialState: emptyEPhaseReplayState(),
    reducer: reduceEPhaseEvent,
  });

test("strict_replay_test: E02 and E03 durable events rebuild exactly and match live projections", (t) => {
  const fixture = createEPhaseReplayFixture(t);
  const scenario = executeEPhaseScenario(fixture);

  const first = rebuild(fixture.ledger);
  const second = rebuild(fixture.ledger);
  assert.deepEqual(second, first);
  assert.equal(first.event_count, 7);
  assert.match(first.state_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.deepEqual(
    first.state.event_order.map((event) => event.event_type),
    [
      "effect.action-intent.recorded",
      "effect.attempt.started",
      "effect.receipt.recorded",
      "capability.approval.recorded",
      "capability.lease.issued",
      "capability.lease-use.committed",
      "capability.lease.revoked",
    ],
  );

  const live = liveEPhaseProjection(fixture);
  assert.deepEqual(first.state.effects, live.effects);
  assert.deepEqual(first.state.approvals, live.approvals);
  assert.deepEqual(first.state.leases, live.leases);
  assert.deepEqual(first.state.lease_uses[E04_IDS.OPERATION].result, scenario.committed.result);
  assert.equal(first.state.lease_uses[E04_IDS.OPERATION].lease_id, E04_IDS.LEASE);
  assert.equal(first.state.leases[E04_IDS.LEASE].revoked, true);
  assert.equal(fixture.coordinator.verify(E04_IDS.INTENT).completion_proven, true);
  assert.deepEqual(fixture.authority.reconcileEvents(), {
    existing: 4,
    published: 0,
    total: 4,
  });
});

test("strict_replay_test: reopening both durable stores preserves stream and reducer identity", (t) => {
  const fixture = createEPhaseReplayFixture(t);
  executeEPhaseScenario(fixture);
  const before = rebuild(fixture.ledger);

  fixture.reopen();
  const after = rebuild(fixture.ledger);
  assert.deepEqual(after, before);
  assert.deepEqual(after.state.effects, liveEPhaseProjection(fixture).effects);
  assert.deepEqual(after.state.leases, liveEPhaseProjection(fixture).leases);
});

test("strict_replay_test: exact retries append no events and do not change replay state", (t) => {
  const fixture = createEPhaseReplayFixture(t);
  const scenario = executeEPhaseScenario(fixture);
  const before = rebuild(fixture.ledger);

  assert.equal(fixture.coordinator.registerIntent(scenario.intent).status, "EXISTING");
  const attemptRetry = fixture.coordinator.beginAttempt({
    attempt_id: scenario.attempt.attempt_id,
    intent_id: scenario.intent.intent_id,
    started_at: scenario.attempt.started_at,
  });
  assert.equal(attemptRetry.status, "EXISTING_RESULT");
  assert.equal(
    fixture.coordinator.recordReceipt({
      attempt_id: scenario.attempt.attempt_id,
      receipt: scenario.receipt,
    }).status,
    "EXISTING",
  );
  assert.deepEqual(
    fixture.authority.issueApproval(E03_IDS.APPROVER, scenario.approvalCommand),
    scenario.approval,
  );
  assert.deepEqual(
    fixture.authority.issueLease(E03_IDS.AUTHORITY, scenario.leaseCommand),
    scenario.revoked,
  );
  let callbackCalls = 0;
  const useRetry = fixture.authority.commitWithLease(scenario.useCommand, () => {
    callbackCalls += 1;
    return { forbidden_rerun: true };
  });
  assert.equal(useRetry.status, "EXISTING");
  assert.equal(callbackCalls, 0);
  assert.deepEqual(
    fixture.authority.revokeLease(E03_IDS.AUTHORITY, scenario.revokeCommand),
    scenario.revoked,
  );

  const after = rebuild(fixture.ledger);
  assert.deepEqual(after, before);
  assert.equal(fixture.ledger.readEvents(E04_IDS.RUN).length, 7);
});

test("strict_replay_test: exact pins and identical stream identity produce a schema-valid EXACT report", (t) => {
  const fixture = createEPhaseReplayFixture(t);
  executeEPhaseScenario(fixture);
  const replay = rebuild(fixture.ledger);
  const pins = replayPins();
  const comparisonSide = {
    gates: { strict_reducer_equivalence: "PASS" },
    pins,
    semantic_projection: replay.state,
    strict_identity: {
      event_count: replay.event_count,
      state_hash: replay.state_hash,
      tail_event_hash: replay.tail_event_hash,
    },
    verdicts: { e_phase_replay: "PASS" },
  };
  const report = sealReplayReport({
    mode: "strict",
    replay: comparisonSide,
    replayId: "REPLAY-E04-strict",
    replayRunId: E04_IDS.RUN,
    source: comparisonSide,
    sourceRunId: E04_IDS.RUN,
  });

  assert.equal(report.event_equivalence, "EXACT");
  assert.equal(report.artifact_hash_matches, 8);
  assert.equal(report.artifact_hash_mismatches, 0);
  assert.equal(report.pinned_artifacts.length, 16);
  assert.ok(report.pinned_artifacts.some((pin) => pin.startsWith("source:run_spec=sha256:")));
  assert.ok(report.pinned_artifacts.some((pin) => pin.startsWith("replay:run_spec=sha256:")));
  assert.equal(report.drift_classification, "NONE");
  assert.equal(assertReplayReportIntegrity(report), true);
  assert.equal(validateReplayReportSchema(report), "ReplayReport valid");
});

for (const fault of ["tampered", "missing"]) {
  test(`strict_replay_test: ${fault} payload bytes fail closed before equivalence`, (t) => {
    const fixture = createEPhaseReplayFixture(t);
    executeEPhaseScenario(fixture);
    const firstEvent = fixture.ledger.readEvents(E04_IDS.RUN)[0];
    const contentPath = payloadContentPath(
      fixture.artifactStore,
      fixture.artifactRoot,
      firstEvent.payload_artifact_id,
    );
    if (fault === "tampered") fs.writeFileSync(contentPath, Buffer.from('{"tampered":true}', "utf8"));
    else fs.rmSync(contentPath);

    assert.throws(
      () => rebuild(fixture.ledger),
      expectLedgerCode("PAYLOAD_RESOLUTION_FAILED", "PAYLOAD_HASH_MISMATCH"),
    );
  });
}

test("strict_replay_test: duplicate logical payload identities fail closed", (t) => {
  const fixture = createEPhaseReplayFixture(t);
  const scenario = executeEPhaseScenario(fixture);
  const replay = rebuild(fixture.ledger);
  const duplicateEvent = {
    aggregate_id: scenario.approval.approval_id,
    aggregate_type: "approval",
    event_id: "EVT-E04-duplicate-approval",
    event_type: "capability.approval.recorded",
    run_id: E04_IDS.RUN,
    sequence: replay.event_count + 1,
  };

  assert.throws(
    () =>
      reduceEPhaseEvent(replay.state, {
        event: duplicateEvent,
        payloadBytes: Buffer.from(JSON.stringify({ approval: scenario.approval }), "utf8"),
      }),
    (error) => error.code === "E04_REPLAY_SEQUENCE_INVALID",
  );
});

test("strict_replay_test: event envelopes cannot rebind a valid payload to another aggregate", (t) => {
  const fixture = createEPhaseReplayFixture(t);
  executeEPhaseScenario(fixture);
  const event = fixture.ledger.readEvents(E04_IDS.RUN)[0];
  const payloadBytes = fixture.artifactStore.readArtifact(event.payload_artifact_id);

  assert.throws(
    () =>
      reduceEPhaseEvent(emptyEPhaseReplayState(), {
        event: { ...event, aggregate_id: "INTENT-E04-forged" },
        payloadBytes,
      }),
    (error) => error.code === "E04_REPLAY_EVENT_BINDING_INVALID",
  );
});
