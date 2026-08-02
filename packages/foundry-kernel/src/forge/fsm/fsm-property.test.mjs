import assert from "node:assert/strict";
import test from "node:test";

import {
  ForgeFsmError,
  FORGE_PHASES,
  compileForgePlan,
  describeForgeTransition,
  reduceForgeTransition,
  replayForgeTransitionEvents,
} from "./forge-fsm.mjs";
import {
  classificationFixture,
  phaseArtifactSetFixture,
  sessionStateFixture,
  transitionEventFixture,
  transitionRequestFixture,
} from "./fsm-test-support.mjs";

const expectCode = (code) => (error) => error instanceof ForgeFsmError && error.code === code;

const edgeSet = (pairs) => new Set(pairs.map(([from, to]) => `${from}->${to}`));

const FULL_EDGE_SET = edgeSet([
  ["IDLE", "F"],
  ["I", "F"],
  ["F", "O"],
  ["O", "R"],
  ["R", "G"],
  ["G", "E"],
  ["E", "IDLE"],
  ["F", "I"],
  ["O", "I"],
  ["R", "I"],
  ["G", "I"],
  ["R", "O"],
  ["G", "O"],
  ["G", "R"],
  ["E", "F"],
]);

const EXPECTED_EDGES = Object.freeze({
  E0: edgeSet([]),
  E1: edgeSet([
    ["IDLE", "F"],
    ["I", "F"],
    ["F", "O"],
    ["O", "E"],
    ["E", "IDLE"],
    ["F", "I"],
    ["O", "I"],
    ["E", "F"],
  ]),
  E2: FULL_EDGE_SET,
  E3: FULL_EDGE_SET,
  E4: FULL_EDGE_SET,
  E5_NO_INTERVIEW: FULL_EDGE_SET,
  E5: edgeSet([
    ["IDLE", "I"],
    ["I", "F"],
    ["F", "O"],
    ["O", "R"],
    ["R", "G"],
    ["G", "E"],
    ["E", "IDLE"],
    ["F", "I"],
    ["O", "I"],
    ["R", "I"],
    ["G", "I"],
    ["R", "O"],
    ["G", "O"],
    ["G", "R"],
    ["E", "F"],
  ]),
});

const CASES = Object.freeze([
  { key: "E0", fixture: classificationFixture({ signal: "TRANSFORM" }) },
  { key: "E1", fixture: classificationFixture({ signal: "LOOKUP" }) },
  { key: "E2", fixture: classificationFixture({ signal: "SYNTHESIS" }) },
  { key: "E3", fixture: classificationFixture({ signal: "MECHANISM" }) },
  { key: "E4", fixture: classificationFixture({ signal: "CAUSAL" }) },
  { key: "E5_NO_INTERVIEW", fixture: classificationFixture({ signal: "NOVELTY" }) },
  { key: "E5", fixture: classificationFixture({ signal: "AMBIGUOUS" }) },
]);

test("fsm_property_test: every phase pair matches the exact class-specific FORGE graph", () => {
  for (const row of CASES) {
    const plan = compileForgePlan(row.fixture);
    for (const from of FORGE_PHASES) {
      for (const to of FORGE_PHASES) {
        const actual = describeForgeTransition(plan, from, to);
        assert.equal(actual.legal, EXPECTED_EDGES[row.key].has(`${from}->${to}`), {
          workClass: row.key,
          from,
          to,
          actual,
        });
      }
    }
  }
});

test("fsm_property_test: F01 exact projection drives forward edges and cannot be weakened", () => {
  const e1 = CASES.find((row) => row.key === "E1").fixture;
  const plan = compileForgePlan(e1);
  assert.deepEqual(plan.required_phases, ["F", "O", "E"]);
  assert.equal(describeForgeTransition(plan, "O", "E").kind, "FORWARD");
  assert.equal(describeForgeTransition(plan, "O", "R").legal, false);

  const forged = {
    ...e1.classification,
    required_phases: ["F", "O", "R", "G", "E"],
  };
  assert.throws(
    () => compileForgePlan({ ...e1, classification: forged }),
    expectCode("INVALID_CLASSIFICATION_PROJECTION"),
  );
});

test("fsm_property_test: reducer is immutable, revision-bound, and hash deterministic", () => {
  const fixture = classificationFixture({ signal: "MECHANISM" });
  const state = sessionStateFixture({ workClass: "E3" });
  const request = transitionRequestFixture({ from: "IDLE", to: "F", revision: 0 });
  const event = transitionEventFixture({ suffix: "start" });
  const beforeState = structuredClone(state);
  const beforeRequest = structuredClone(request);

  const first = reduceForgeTransition({
    current_state: state,
    transition_request: request,
    ...fixture,
    event,
  });
  const second = reduceForgeTransition({
    current_state: structuredClone(state),
    transition_request: structuredClone(request),
    ...fixture,
    event: structuredClone(event),
  });

  assert.deepEqual(state, beforeState);
  assert.deepEqual(request, beforeRequest);
  assert.deepEqual(second, first);
  assert.equal(first.state.revision, 1);
  assert.equal(first.state.phase, "F");
  assert.equal(first.transition.kind, "FORWARD");
  assert.match(first.state.state_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.match(first.transition.transition_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(Object.isFrozen(first.state), true);
});

test("fsm_property_test: sealed inputs fail closed and transition identity binds semantic inputs", () => {
  const fixture = classificationFixture({ signal: "MECHANISM" });
  const firstSet = phaseArtifactSetFixture({ phase: "F", suffix: "binding-a" });
  const secondSet = phaseArtifactSetFixture({ phase: "F", suffix: "binding-b" });
  const state = sessionStateFixture({ workClass: "E3", phaseSets: [firstSet, secondSet] });
  const request = transitionRequestFixture({ from: "IDLE", to: "F", revision: 0 });
  const event = transitionEventFixture({ suffix: "binding" });

  assert.throws(
    () =>
      reduceForgeTransition({
        current_state: { ...state, open_blockers: ["tampered-after-seal"] },
        transition_request: request,
        ...fixture,
        event,
      }),
    expectCode("FORGE_STATE_HASH_MISMATCH"),
  );
  assert.throws(
    () =>
      compileForgePlan({
        classification: {
          ...fixture.classification,
          reasons: [...fixture.classification.reasons, "SIGNAL:LOOKUP"],
        },
        classification_identity_context: fixture.classification_identity_context,
      }),
    expectCode("CLASSIFICATION_INTEGRITY_FAILED"),
  );

  const baseline = reduceForgeTransition({
    current_state: state,
    transition_request: request,
    ...fixture,
    phase_artifact_sets: [firstSet],
    event,
  });
  const changedRequest = reduceForgeTransition({
    current_state: state,
    transition_request: { ...request, reason: `${request.reason} with another rationale` },
    ...fixture,
    phase_artifact_sets: [firstSet],
    event,
  });
  const changedEvent = reduceForgeTransition({
    current_state: state,
    transition_request: request,
    ...fixture,
    phase_artifact_sets: [firstSet],
    event: transitionEventFixture({ suffix: "binding-other", minute: 2 }),
  });
  const changedPhaseSet = reduceForgeTransition({
    current_state: state,
    transition_request: request,
    ...fixture,
    phase_artifact_sets: [secondSet],
    event,
  });

  assert.notEqual(changedRequest.transition.transition_hash, baseline.transition.transition_hash);
  assert.notEqual(changedEvent.transition.transition_hash, baseline.transition.transition_hash);
  assert.notEqual(changedPhaseSet.transition.transition_hash, baseline.transition.transition_hash);
  assert.notEqual(changedEvent.state.state_hash, baseline.state.state_hash);
});

test("fsm_property_test: stale revision, wrong from phase, and illegal edges make no state", () => {
  const fixture = classificationFixture({ signal: "MECHANISM" });
  const state = sessionStateFixture({ workClass: "E3" });
  const event = transitionEventFixture({ suffix: "reject" });
  const baseline = structuredClone(state);

  assert.throws(
    () =>
      reduceForgeTransition({
        current_state: state,
        transition_request: transitionRequestFixture({ from: "IDLE", to: "F", revision: 1 }),
        ...fixture,
        event,
      }),
    expectCode("STALE_REVISION"),
  );
  assert.throws(
    () =>
      reduceForgeTransition({
        current_state: state,
        transition_request: transitionRequestFixture({ from: "F", to: "O", revision: 0 }),
        ...fixture,
        event,
      }),
    expectCode("FROM_PHASE_MISMATCH"),
  );
  assert.throws(
    () =>
      reduceForgeTransition({
        current_state: state,
        transition_request: transitionRequestFixture({ from: "IDLE", to: "E", revision: 0 }),
        ...fixture,
        event,
      }),
    expectCode("ILLEGAL_FORGE_TRANSITION"),
  );
  assert.deepEqual(state, baseline);
});

test("fsm_property_test: E closes to completed IDLE and completed sessions cannot restart", () => {
  const fixture = classificationFixture({ signal: "LOOKUP" });
  const validState = sessionStateFixture({
    workClass: "E1",
    phase: "E",
    revision: 3,
    phaseHistory: [
      { from: "IDLE", to: "F", event_id: "EVT-F02-1", at: "2026-07-29T01:01:00.000Z" },
      { from: "F", to: "O", event_id: "EVT-F02-2", at: "2026-07-29T01:02:00.000Z" },
      { from: "O", to: "E", event_id: "EVT-F02-3", at: "2026-07-29T01:03:00.000Z" },
    ],
  });
  const closed = reduceForgeTransition({
    current_state: validState,
    transition_request: transitionRequestFixture({ from: "E", to: "IDLE", revision: 3 }),
    ...fixture,
    event: transitionEventFixture({ suffix: "close", minute: 4 }),
  });
  assert.equal(closed.state.status, "COMPLETED");
  assert.equal(closed.state.phase, "IDLE");
  assert.throws(
    () =>
      reduceForgeTransition({
        current_state: closed.state,
        transition_request: transitionRequestFixture({ from: "IDLE", to: "F", revision: 4 }),
        ...fixture,
        event: transitionEventFixture({ suffix: "restart", minute: 5 }),
      }),
    expectCode("FORGE_SESSION_NOT_TRANSITIONABLE"),
  );
});

test("fsm_property_test: strict event replay reproduces the direct reducer chain", () => {
  const fixture = classificationFixture({ signal: "LOOKUP" });
  const initial = sessionStateFixture({ workClass: "E1" });
  const transitions = [
    {
      transition_request: transitionRequestFixture({ from: "IDLE", to: "F", revision: 0 }),
      event: transitionEventFixture({ suffix: "replay-1", minute: 1 }),
    },
    {
      transition_request: transitionRequestFixture({ from: "F", to: "O", revision: 1 }),
      event: transitionEventFixture({ suffix: "replay-2", minute: 2 }),
    },
    {
      transition_request: transitionRequestFixture({ from: "O", to: "E", revision: 2 }),
      event: transitionEventFixture({ suffix: "replay-3", minute: 3 }),
    },
  ];
  const left = replayForgeTransitionEvents({ initial_state: initial, transitions, ...fixture });
  const right = replayForgeTransitionEvents({
    initial_state: structuredClone(initial),
    transitions: structuredClone(transitions),
    ...fixture,
  });
  assert.deepEqual(right, left);
  assert.equal(left.state.phase, "E");
  assert.equal(left.transitions.length, 3);
  assert.match(left.replay_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("fsm_property_test: empty replay still verifies every sealed initial input", () => {
  const fixture = classificationFixture({ signal: "MECHANISM" });
  const phaseSet = phaseArtifactSetFixture({ phase: "F", suffix: "empty-replay" });
  const state = sessionStateFixture({ workClass: "E3", phaseSets: [phaseSet] });
  const accepted = replayForgeTransitionEvents({
    initial_state: state,
    transitions: [],
    ...fixture,
    phase_artifact_sets: [phaseSet],
  });
  assert.deepEqual(accepted.state, state);
  assert.deepEqual(accepted.phase_artifact_sets, [phaseSet]);

  const sameClassDifferentIdentity = replayForgeTransitionEvents({
    initial_state: state,
    transitions: [],
    ...classificationFixture({ signal: "MECHANISM", requestId: "REQ-F02-other-E3" }),
    phase_artifact_sets: [phaseSet],
  });
  assert.notEqual(sameClassDifferentIdentity.replay_hash, accepted.replay_hash);

  assert.throws(
    () =>
      replayForgeTransitionEvents({
        initial_state: { ...state, revision: 1 },
        transitions: [],
        ...fixture,
        phase_artifact_sets: [phaseSet],
      }),
    expectCode("FORGE_STATE_HASH_MISMATCH"),
  );
  assert.throws(
    () =>
      replayForgeTransitionEvents({
        initial_state: state,
        transitions: [],
        ...fixture,
        phase_artifact_sets: [{ ...phaseSet, complete: false }],
      }),
    expectCode("PHASE_ARTIFACT_SET_HASH_MISMATCH"),
  );
  assert.throws(
    () =>
      replayForgeTransitionEvents({
        initial_state: state,
        transitions: [],
        ...classificationFixture({ signal: "LOOKUP" }),
        phase_artifact_sets: [phaseSet],
    }),
    expectCode("CLASSIFICATION_STATE_MISMATCH"),
  );

  const lookupFixture = classificationFixture({ signal: "LOOKUP" });
  const unreachableState = sessionStateFixture({ workClass: "E1", phase: "R" });
  assert.throws(
    () =>
      replayForgeTransitionEvents({
        initial_state: unreachableState,
        transitions: [],
        ...lookupFixture,
      }),
    expectCode("PHASE_NOT_REACHABLE_FOR_CLASSIFICATION"),
  );

  const unreachablePhaseSet = phaseArtifactSetFixture({
    phase: "R",
    suffix: "unreachable-for-e1",
  });
  const lookupState = sessionStateFixture({
    workClass: "E1",
    phaseSets: [unreachablePhaseSet],
  });
  assert.throws(
    () =>
      replayForgeTransitionEvents({
        initial_state: lookupState,
        transitions: [],
        ...lookupFixture,
        phase_artifact_sets: [unreachablePhaseSet],
      }),
    expectCode("PHASE_NOT_REACHABLE_FOR_CLASSIFICATION"),
  );
});
