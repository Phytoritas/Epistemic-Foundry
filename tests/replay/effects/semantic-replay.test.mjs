import assert from "node:assert/strict";
import test from "node:test";

import {
  assertReplayReportIntegrity,
  canonicalJson,
  pinHash,
  replayPins,
  sealReplayReport,
  sha256Canonical,
  validateReplayReportSchema,
} from "./replay-test-support.mjs";

const semanticProjection = Object.freeze({
  effect_outcomes: [{ status: "SUCCEEDED", result_kind: "validated_artifact" }],
  lease_decisions: [{ capability: "artifact:write", committed: true, revoked: true }],
});

const side = ({
  pins = replayPins(),
  identity = {},
  projection = semanticProjection,
  gates = { receipt_integrity: "PASS", replayability: "PASS" },
  verdicts = { effect: "SUCCEEDED" },
} = {}) => ({
  gates,
  pins,
  semantic_projection: projection,
  strict_identity: identity,
  verdicts,
});

const report = ({
  mode = "semantic",
  source = side({ identity: { event_ids: ["EVT-source"] } }),
  replay = side({ identity: { event_ids: ["EVT-replay"] } }),
  sourceRunId = "RUN-E04-source",
  replayRunId = "RUN-E04-replay",
  replayId = "REPLAY-E04-semantic",
} = {}) =>
  sealReplayReport({
    mode,
    replay,
    replayId,
    replayRunId,
    source,
    sourceRunId,
  });

test("semantic_replay_report: distinct run and event identities are semantic, never strict exact", () => {
  const semantic = report();
  assert.equal(semantic.event_equivalence, "SEMANTICALLY_EQUIVALENT");
  assert.equal(semantic.drift_classification, "NONE");
  assert.equal(semantic.artifact_hash_mismatches, 0);

  const identity = {
    event_count: 1,
    state_hash: sha256Canonical(semanticProjection),
    tail_event_hash: pinHash("semantic-tail"),
  };
  const strict = report({
    mode: "strict",
    replay: side({ identity }),
    replayId: "REPLAY-E04-not-exact",
    source: side({ identity }),
  });
  assert.equal(strict.event_equivalence, "DRIFT");
  assert.notEqual(strict.event_equivalence, "EXACT");
});

test("semantic_replay_report: model pin drift remains visible across equivalent outcomes", () => {
  const sourcePins = replayPins();
  const replayedPins = replayPins({ adapter_model: pinHash("adapter_model:v2") });
  const actual = report({
    replay: side({ identity: { event_ids: ["EVT-model-replay"] }, pins: replayedPins }),
    source: side({ identity: { event_ids: ["EVT-model-source"] }, pins: sourcePins }),
  });

  assert.equal(actual.event_equivalence, "SEMANTICALLY_EQUIVALENT");
  assert.equal(actual.drift_classification, "MODEL");
  assert.equal(actual.artifact_hash_matches, 7);
  assert.equal(actual.artifact_hash_mismatches, 1);
  assert.ok(
    actual.pinned_artifacts.includes(`source:adapter_model=${sourcePins.adapter_model}`),
  );
  assert.ok(
    actual.pinned_artifacts.includes(`replay:adapter_model=${replayedPins.adapter_model}`),
  );
  assert.equal(assertReplayReportIntegrity(actual), true);
  assert.equal(validateReplayReportSchema(actual), "ReplayReport valid");
});

test("semantic_replay_report: multiple changed pins are classified without erasure", () => {
  const actual = report({
    replay: side({
      pins: replayPins({
        adapter_model: pinHash("adapter_model:v2"),
        prompts: pinHash("prompts:v2"),
      }),
    }),
  });

  assert.equal(actual.event_equivalence, "SEMANTICALLY_EQUIVALENT");
  assert.equal(actual.drift_classification, "MULTIPLE");
  assert.equal(actual.artifact_hash_mismatches, 2);
});

test("semantic_replay_report: gate and verdict changes are explicit semantic DRIFT", () => {
  const actual = report({
    replay: side({
      gates: { receipt_integrity: "FAIL", replayability: "PASS" },
      verdicts: { effect: "BLOCKED" },
    }),
  });

  assert.equal(actual.event_equivalence, "DRIFT");
  assert.deepEqual(actual.gate_differences, ['receipt_integrity:"PASS"->"FAIL"']);
  assert.deepEqual(actual.verdict_differences, ['effect:"SUCCEEDED"->"BLOCKED"']);
  assert.equal(actual.drift_classification, "NONE");
  assert.equal(validateReplayReportSchema(actual), "ReplayReport valid");
});

test("semantic_replay_report: changed semantic state is DRIFT even when gates and verdicts match", () => {
  const actual = report({
    replay: side({
      projection: {
        effect_outcomes: [{ status: "FAILED", result_kind: "validated_artifact" }],
        lease_decisions: [{ capability: "artifact:write", committed: true, revoked: true }],
      },
    }),
  });

  assert.equal(actual.event_equivalence, "DRIFT");
  assert.deepEqual(actual.gate_differences, []);
  assert.deepEqual(actual.verdict_differences, []);
});

test("semantic_replay_report: missing required pins make the runs NOT_COMPARABLE", () => {
  const actual = report({
    replay: side({ pins: replayPins({ corpus: undefined }) }),
  });

  assert.equal(actual.event_equivalence, "NOT_COMPARABLE");
  assert.deepEqual(actual.unavailable_pins, ["replay:corpus"]);
  assert.equal(actual.drift_classification, "UNKNOWN");
  assert.equal(actual.artifact_hash_matches, 7);
  assert.equal(actual.artifact_hash_mismatches, 0);
});

test("semantic_replay_report: report hash excludes itself and rejects mutation or placeholders", () => {
  const sealed = report();
  assert.equal(assertReplayReportIntegrity(sealed), true);

  assert.throws(
    () =>
      assertReplayReportIntegrity({
        ...sealed,
        event_equivalence: "DRIFT",
      }),
    (error) => error.code === "E04_REPLAY_REPORT_HASH_MISMATCH",
  );
  assert.throws(
    () =>
      assertReplayReportIntegrity({
        ...sealed,
        report_hash: `sha256:${"4".repeat(64)}`,
      }),
    (error) => error.code === "E04_REPLAY_REPORT_HASH_MISMATCH",
  );
});

test("semantic_replay_report: floating or malformed pins are rejected before comparison", () => {
  assert.throws(
    () => report({ replay: side({ pins: { ...replayPins(), adapter_model: "latest" } }) }),
    (error) => error.code === "E04_PIN_INVALID",
  );
});

test("semantic_replay_report: strict identity cannot be empty or detached from replay state", () => {
  assert.throws(
    () => report({ mode: "strict" }),
    (error) => error.code === "E04_STRICT_IDENTITY_INVALID",
  );
  const detachedIdentity = {
    event_count: 1,
    state_hash: pinHash("not-the-semantic-state"),
    tail_event_hash: pinHash("tail"),
  };
  assert.throws(
    () =>
      report({
        mode: "strict",
        replay: side({ identity: detachedIdentity }),
        source: side({ identity: detachedIdentity }),
      }),
    (error) => error.code === "E04_STRICT_IDENTITY_INVALID",
  );
});

test("semantic_replay_report: canonical hashing rejects accessors and invalid Unicode without execution", () => {
  let getterCalls = 0;
  const accessor = {};
  Object.defineProperty(accessor, "secret", {
    enumerable: true,
    get() {
      getterCalls += 1;
      return "must-not-run";
    },
  });
  assert.throws(
    () => canonicalJson(accessor),
    (error) => error.code === "E04_NON_CANONICAL_JSON",
  );
  assert.equal(getterCalls, 0);
  assert.throws(
    () => canonicalJson({ text: "\ud800" }),
    (error) => error.code === "E04_NON_CANONICAL_JSON",
  );
});
