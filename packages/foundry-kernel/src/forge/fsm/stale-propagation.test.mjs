import assert from "node:assert/strict";
import test from "node:test";

import { ForgeFsmError, reduceForgeTransition } from "./forge-fsm.mjs";
import {
  classificationFixture,
  phaseArtifactSetFixture,
  sessionStateFixture,
  transitionEventFixture,
  transitionRequestFixture,
} from "./fsm-test-support.mjs";

const expectCode = (code) => (error) => error instanceof ForgeFsmError && error.code === code;

const allPhaseSets = () =>
  ["I", "F", "O", "R", "G", "E"].map((phase) => phaseArtifactSetFixture({ phase }));

const FORWARD_HISTORY = Object.freeze([
  { from: "IDLE", to: "F", event_id: "EVT-F02-h1", at: "2026-07-29T01:01:00.000Z" },
  { from: "F", to: "O", event_id: "EVT-F02-h2", at: "2026-07-29T01:02:00.000Z" },
  { from: "O", to: "R", event_id: "EVT-F02-h3", at: "2026-07-29T01:03:00.000Z" },
  { from: "R", to: "G", event_id: "EVT-F02-h4", at: "2026-07-29T01:04:00.000Z" },
  { from: "G", to: "E", event_id: "EVT-F02-h5", at: "2026-07-29T01:05:00.000Z" },
]);

const historyAt = (phase) => {
  const index = ["F", "O", "R", "G", "E"].indexOf(phase);
  if (index < 0) throw new Error(`unsupported F02 fixture phase: ${phase}`);
  return FORWARD_HISTORY.slice(0, index + 1);
};

const stateAt = (phase, phaseSets, revision = 6) =>
  sessionStateFixture({
    workClass: "E3",
    phase,
    revision,
    phaseSets,
    phaseHistory: historyAt(phase),
  });

const reduceReturn = ({ from, to, phaseSets, revision = 6, eventSuffix = `${from}-${to}` }) => {
  const fixture = classificationFixture({ signal: "MECHANISM" });
  return reduceForgeTransition({
    current_state: stateAt(from, phaseSets, revision),
    transition_request: transitionRequestFixture({ from, to, revision }),
    ...fixture,
    phase_artifact_sets: phaseSets,
    event: transitionEventFixture({ suffix: eventSuffix, minute: 8 }),
  });
};

test("stale_propagation_test: G to O stales target and every downstream projection", () => {
  const phaseSets = allPhaseSets();
  const before = structuredClone(phaseSets);
  const result = reduceReturn({ from: "G", to: "O", phaseSets });

  assert.deepEqual(phaseSets, before, "source PhaseArtifactSets remain immutable history");
  assert.deepEqual(result.transition.stale_phases, ["O", "R", "G", "E"]);
  assert.deepEqual(
    result.superseded_phase_artifact_sets.map((entry) => entry.phase),
    ["O", "R", "G", "E"],
  );
  const current = new Map(result.phase_artifact_sets.map((set) => [set.phase, set]));
  assert.equal(current.get("I").set_id, "PAS-F02-I");
  assert.equal(current.get("F").set_id, "PAS-F02-F");
  for (const phase of ["O", "R", "G", "E"]) {
    assert.match(current.get(phase).set_id, /^PAS-STALE-[0-9a-f]{64}$/u);
    assert.equal(current.get(phase).complete, false);
    assert.equal(current.get(phase).required_artifacts[0].status, "STALE");
    assert.match(current.get(phase).set_hash, /^sha256:[0-9a-f]{64}$/u);
  }
  assert.deepEqual(result.transition.stale_artifact_ids, [
    "ART-F02-E",
    "ART-F02-G",
    "ART-F02-O",
    "ART-F02-R",
  ]);
  assert.deepEqual(result.state.artifact_ids, stateAt("G", phaseSets).artifact_ids);
});

test("stale_propagation_test: every legal return edge has the target-inclusive suffix", () => {
  const phaseSets = allPhaseSets();
  const rows = [
    ["F", "I", ["I", "F", "O", "R", "G", "E"]],
    ["O", "I", ["I", "F", "O", "R", "G", "E"]],
    ["R", "I", ["I", "F", "O", "R", "G", "E"]],
    ["G", "I", ["I", "F", "O", "R", "G", "E"]],
    ["R", "O", ["O", "R", "G", "E"]],
    ["G", "O", ["O", "R", "G", "E"]],
    ["G", "R", ["R", "G", "E"]],
    ["E", "F", ["F", "O", "R", "G", "E"]],
  ];
  for (const [from, to, expected] of rows) {
    const revision = from === "E" ? 6 : 6;
    const result = reduceReturn({
      from,
      to,
      phaseSets,
      revision,
      eventSuffix: `matrix-${from}-${to}`,
    });
    assert.equal(result.transition.kind, "RETURN", `${from}->${to}`);
    assert.deepEqual(result.transition.stale_phases, expected, `${from}->${to}`);
    assert.equal(result.transition.stale_projection_rule, "RETURN_TARGET_INCLUSIVE");
  }
});

test("stale_propagation_test: stale suffix contains only phases reachable for the class", () => {
  const fixture = classificationFixture({ signal: "LOOKUP" });
  const phaseSets = ["I", "F", "O", "E"].map((phase) =>
    phaseArtifactSetFixture({ phase, suffix: `e1-${phase}` }),
  );
  const state = sessionStateFixture({
    workClass: "E1",
    phase: "E",
    revision: 3,
    phaseSets,
    phaseHistory: [
      { from: "IDLE", to: "F", event_id: "EVT-F02-e1-1", at: "2026-07-29T01:01:00.000Z" },
      { from: "F", to: "O", event_id: "EVT-F02-e1-2", at: "2026-07-29T01:02:00.000Z" },
      { from: "O", to: "E", event_id: "EVT-F02-e1-3", at: "2026-07-29T01:03:00.000Z" },
    ],
  });
  const result = reduceForgeTransition({
    current_state: state,
    transition_request: transitionRequestFixture({ from: "E", to: "F", revision: 3 }),
    ...fixture,
    phase_artifact_sets: phaseSets,
    event: transitionEventFixture({ suffix: "e1-reframe", minute: 4 }),
  });

  assert.deepEqual(result.transition.stale_phases, ["F", "O", "E"]);
  assert.deepEqual(
    result.superseded_phase_artifact_sets.map((entry) => entry.phase),
    ["F", "O", "E"],
  );
  assert.equal(
    result.phase_artifact_sets.find((entry) => entry.phase === "I").set_id,
    "PAS-F02-e1-I",
  );
});

test("stale_propagation_test: forward and close edges do not stale artifacts", () => {
  const fixture = classificationFixture({ signal: "MECHANISM" });
  const phaseSets = [phaseArtifactSetFixture({ phase: "F" })];
  const forwardState = sessionStateFixture({ workClass: "E3", phaseSets });
  const forward = reduceForgeTransition({
    current_state: forwardState,
    transition_request: transitionRequestFixture({ from: "IDLE", to: "F", revision: 0 }),
    ...fixture,
    phase_artifact_sets: phaseSets,
    event: transitionEventFixture({ suffix: "forward-no-stale" }),
  });
  assert.deepEqual(forward.transition.stale_phases, []);
  assert.deepEqual(forward.superseded_phase_artifact_sets, []);
  assert.deepEqual(forward.phase_artifact_sets, phaseSets);
});

test("stale_propagation_test: projection identity is deterministic and event-bound", () => {
  const phaseSets = allPhaseSets();
  const left = reduceReturn({ from: "G", to: "R", phaseSets, eventSuffix: "stable" });
  const right = reduceReturn({
    from: "G",
    to: "R",
    phaseSets: structuredClone(phaseSets).reverse(),
    eventSuffix: "stable",
  });
  assert.deepEqual(right.phase_artifact_sets, left.phase_artifact_sets);
  assert.deepEqual(right.transition.stale_artifact_ids, left.transition.stale_artifact_ids);

  const later = reduceReturn({ from: "G", to: "R", phaseSets, eventSuffix: "different-event" });
  assert.notDeepEqual(
    later.superseded_phase_artifact_sets.map((entry) => entry.projection_set_id),
    left.superseded_phase_artifact_sets.map((entry) => entry.projection_set_id),
  );
});

test("stale_propagation_test: cross-session and unretained artifact sets fail closed", () => {
  const fixture = classificationFixture({ signal: "MECHANISM" });
  const foreign = phaseArtifactSetFixture({ phase: "R", sessionId: "FS-F02-foreign" });
  const local = phaseArtifactSetFixture({ phase: "G" });
  const state = sessionStateFixture({
    workClass: "E3",
    phase: "G",
    revision: 4,
    phaseSets: [local],
    phaseHistory: [
      { from: "R", to: "G", event_id: "EVT-F02-local", at: "2026-07-29T01:04:00.000Z" },
    ],
  });
  const request = transitionRequestFixture({ from: "G", to: "R", revision: 4 });
  const event = transitionEventFixture({ suffix: "invalid-set" });

  assert.throws(
    () =>
      reduceForgeTransition({
        current_state: state,
        transition_request: request,
        ...fixture,
        phase_artifact_sets: [foreign],
        event,
      }),
    expectCode("PHASE_ARTIFACT_SESSION_MISMATCH"),
  );

  const unretained = phaseArtifactSetFixture({ phase: "R" });
  assert.throws(
    () =>
      reduceForgeTransition({
        current_state: state,
        transition_request: request,
        ...fixture,
        phase_artifact_sets: [unretained],
        event,
      }),
    expectCode("PHASE_ARTIFACT_NOT_IN_STATE"),
  );

  const tampered = {
    ...local,
    required_artifacts: [
      {
        ...local.required_artifacts[0],
        kind: "TamperedAfterSeal",
      },
    ],
  };
  assert.throws(
    () =>
      reduceForgeTransition({
        current_state: state,
        transition_request: request,
        ...fixture,
        phase_artifact_sets: [tampered],
        event,
      }),
    expectCode("PHASE_ARTIFACT_SET_HASH_MISMATCH"),
  );
});
