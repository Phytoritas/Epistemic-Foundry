// checkpoint_resume_test — a checkpoint is sealed only with proven replay, and
// resume requires an independent approved review plus exact replay identity.

import assert from "node:assert/strict";
import test from "node:test";

import {
  canonicalizeSchedulerJson,
  sha256SchedulerJson,
} from "../../scheduler/dag-scheduler.mjs";
import {
  createSchedulerFixture,
  nodeContractFixture,
  runNodeSuccessfully,
  schedulerHash,
} from "../../scheduler/scheduler-test-support.mjs";
import {
  CheckpointRuntimeError,
  pauseRun,
  pendingEffects,
  resumeFromCheckpoint,
  sealCheckpoint,
  validateCheckpointManifest,
} from "./checkpoint-runtime.mjs";

const CREATED_AT = "2026-08-01T00:00:00.000Z";

export function fixture() {
  return createSchedulerFixture({
    nodes: [
      nodeContractFixture({ nodeId: "ingest" }),
      nodeContractFixture({ nodeId: "analyze", dependsOn: ["ingest"] }),
    ],
  });
}

export function sealArgs(base, overrides = {}) {
  return {
    budget_envelope: base.budget,
    checkpoint_id: "CKPT-W02-1",
    created_at: CREATED_AT,
    layer_index: 0,
    plan: base.plan,
    run_id: base.runId,
    scheduler: base.scheduler,
    ...overrides,
  };
}

export function review(manifest, overrides = {}) {
  return {
    author_id: "AGENT-W02-AUTHOR",
    checkpoint_hash: manifest.checkpoint_hash,
    decision: "APPROVE",
    reviewer_id: "AGENT-W02-REVIEWER",
    ...overrides,
  };
}

function assertCode(fn, code) {
  try {
    fn();
  } catch (error) {
    assert.ok(error instanceof CheckpointRuntimeError, String(error));
    assert.equal(error.code, code, error.message);
    return error;
  }
  assert.fail(`expected ${code}`);
}

function resealManifest(candidate) {
  const { checkpoint_hash: _drop, ...semantic } = candidate;
  return {
    ...semantic,
    checkpoint_hash: sha256SchedulerJson(canonicalizeSchedulerJson(semantic)),
  };
}

test("checkpoint_resume_test: sealing proves replay rather than asserting it", () => {
  const base = fixture();
  runNodeSuccessfully(base.scheduler, "ingest");

  const sealed = sealCheckpoint(sealArgs(base));

  assert.equal(sealed.manifest.replay_verified, true);
  assert.equal(sealed.manifest.run_id, base.runId);
  assert.equal(sealed.manifest.state_hash, base.scheduler.snapshot().state_hash);
  assert.equal(sealed.manifest.event_sequence, base.scheduler.commandLog().length);
  assert.deepEqual(sealed.manifest.terminal_node_ids, ["ingest"]);
  assert.deepEqual(sealed.manifest.expected_node_ids, ["analyze", "ingest"]);
  assert.deepEqual(sealed.manifest.pending_effect_ids, []);
  validateCheckpointManifest(sealed.manifest);
});

test("checkpoint_resume_test: sealing is deterministic and hash-bound", () => {
  const base = fixture();
  runNodeSuccessfully(base.scheduler, "ingest");

  const first = sealCheckpoint(sealArgs(base));
  const second = sealCheckpoint(sealArgs(base));

  assert.deepEqual(first.manifest, second.manifest);

  const tampered = { ...first.manifest, layer_index: 7 };
  assertCode(() => validateCheckpointManifest(tampered), "CHECKPOINT_HASH_MISMATCH");

  const extra = { ...first.manifest, surprise: true };
  assertCode(() => validateCheckpointManifest(extra), "CHECKPOINT_FIELD_SET_INVALID");
});

test("checkpoint_resume_test: rehashed schema-invalid manifests cannot resume", () => {
  const base = fixture();
  runNodeSuccessfully(base.scheduler, "ingest");
  const sealed = sealCheckpoint(sealArgs(base));
  const invalid = [
    { created_at: "2026-02-30T00:00:00Z" },
    { created_at: "2026-06-30T23:58:60Z" },
    { created_at: "2026-06-30T22:59:60Z" },
    { artifact_ids: {} },
    { layer_index: -1 },
    { event_sequence: -1 },
    { checkpoint_id: "" },
  ];

  for (const override of invalid) {
    const forged = resealManifest({ ...sealed.manifest, ...override });
    assertCode(() => validateCheckpointManifest(forged), "CHECKPOINT_INPUT_INVALID");
  }

  const forged = resealManifest({
    ...sealed.manifest,
    created_at: "not-a-timestamp",
  });
  assertCode(
    () =>
      resumeFromCheckpoint({
        budget_envelope: base.budget,
        commands: sealed.commands,
        manifest: forged,
        plan: base.plan,
        review: review(forged),
      }),
    "CHECKPOINT_INPUT_INVALID",
  );
});

test("checkpoint_resume_test: schema-valid array identity and leap seconds are preserved", () => {
  const base = fixture();
  const sealed = sealCheckpoint(sealArgs(base));
  const forged = resealManifest({
    ...sealed.manifest,
    artifact_ids: ["z", "", "z", "a"],
    checkpoint_id: " ",
    created_at: "2026-07-01t05:29:60+05:30",
  });

  const validated = validateCheckpointManifest(forged);
  assert.deepEqual(validated.artifact_ids, ["z", "", "z", "a"]);
  assert.equal(validated.checkpoint_id, " ");
  assert.equal(validated.created_at, "2026-07-01t05:29:60+05:30");

  const yearZero = validateCheckpointManifest(
    resealManifest({
      ...sealed.manifest,
      created_at: "0000-03-01T00:00:00Z",
    }),
  );
  assert.equal(yearZero.created_at, "0000-03-01T00:00:00Z");
});

test("checkpoint_resume_test: run and plan identity are enforced when sealing", () => {
  const base = fixture();
  const other = fixture();

  assertCode(
    () => sealCheckpoint(sealArgs(base, { run_id: "RUN-OTHER" })),
    "CHECKPOINT_RUN_MISMATCH",
  );
  assertCode(
    () =>
      sealCheckpoint(
        sealArgs(base, {
          plan: createSchedulerFixture({
            nodes: [nodeContractFixture({ nodeId: "other_only" })],
            runId: base.runId,
          }).plan,
        }),
      ),
    "CHECKPOINT_PLAN_MISMATCH",
  );
  assert.notEqual(other.plan.plan_hash, undefined);
});

test("checkpoint_resume_test: resume rebuilds the exact sealed state", () => {
  const base = fixture();
  runNodeSuccessfully(base.scheduler, "ingest");
  const sealed = sealCheckpoint(sealArgs(base));

  const resumed = resumeFromCheckpoint({
    budget_envelope: base.budget,
    commands: sealed.commands,
    manifest: sealed.manifest,
    plan: base.plan,
    review: review(sealed.manifest),
  });

  assert.equal(resumed.state, "RUNNING");
  assert.equal(resumed.resumed_state_hash, sealed.manifest.state_hash);
  assert.equal(resumed.scheduler.snapshot().state_hash, sealed.manifest.state_hash);
  assert.deepEqual(resumed.scheduler.readyNodes(), base.scheduler.readyNodes());
});

test("checkpoint_resume_test: the resumed scheduler continues the run", () => {
  const base = fixture();
  runNodeSuccessfully(base.scheduler, "ingest");
  const sealed = sealCheckpoint(sealArgs(base));
  const resumed = resumeFromCheckpoint({
    budget_envelope: base.budget,
    commands: sealed.commands,
    manifest: sealed.manifest,
    plan: base.plan,
    review: review(sealed.manifest),
  });

  runNodeSuccessfully(resumed.scheduler, "analyze");
  runNodeSuccessfully(base.scheduler, "analyze");

  assert.equal(
    resumed.scheduler.snapshot().state_hash,
    base.scheduler.snapshot().state_hash,
  );
});

test("checkpoint_resume_test: resume requires an approved independent review", () => {
  const base = fixture();
  runNodeSuccessfully(base.scheduler, "ingest");
  const sealed = sealCheckpoint(sealArgs(base));
  const args = {
    budget_envelope: base.budget,
    commands: sealed.commands,
    manifest: sealed.manifest,
    plan: base.plan,
  };

  assertCode(
    () => resumeFromCheckpoint({ ...args, review: review(sealed.manifest, { decision: "REJECT" }) }),
    "CHECKPOINT_REVIEW_REJECTED",
  );
  assertCode(
    () =>
      resumeFromCheckpoint({
        ...args,
        review: review(sealed.manifest, { reviewer_id: "AGENT-W02-AUTHOR" }),
      }),
    "CHECKPOINT_REVIEW_NOT_INDEPENDENT",
  );
  assertCode(
    () =>
      resumeFromCheckpoint({
        ...args,
        review: review(sealed.manifest, { checkpoint_hash: schedulerHash("other") }),
      }),
    "CHECKPOINT_REVIEW_BINDING_INVALID",
  );
  assertCode(
    () =>
      resumeFromCheckpoint({
        ...args,
        review: review(sealed.manifest, { decision: "MAYBE" }),
      }),
    "CHECKPOINT_REVIEW_INVALID",
  );
});

test("checkpoint_resume_test: a divergent or truncated command log cannot resume", () => {
  const base = fixture();
  runNodeSuccessfully(base.scheduler, "ingest");
  const sealed = sealCheckpoint(sealArgs(base));
  const args = {
    budget_envelope: base.budget,
    manifest: sealed.manifest,
    plan: base.plan,
    review: review(sealed.manifest),
  };

  assertCode(
    () => resumeFromCheckpoint({ ...args, commands: sealed.commands.slice(0, -1) }),
    "CHECKPOINT_COMMAND_COUNT_MISMATCH",
  );

  const swapped = [...sealed.commands];
  [swapped[0], swapped[1]] = [swapped[1], swapped[0]];
  assert.throws(() => resumeFromCheckpoint({ ...args, commands: swapped }));
});

test("checkpoint_resume_test: an unverified checkpoint cannot resume", () => {
  const base = fixture();
  runNodeSuccessfully(base.scheduler, "ingest");
  const sealed = sealCheckpoint(sealArgs(base));
  const { checkpoint_hash: _drop, ...semantic } = sealed.manifest;
  const forged = { ...semantic, replay_verified: false };

  assertCode(() => validateCheckpointManifest(forged), "CHECKPOINT_FIELD_SET_INVALID");
});

test("checkpoint_resume_test: pause preserves in-flight work without admitting more", () => {
  const base = fixture();
  const lease = base.scheduler.acquireLease({
    admission: {
      approval_authorized: true,
      blocking_gate_ids: [],
      capability_authorized: true,
      capability_lease_ids: [],
      input_artifacts_resolved: true,
      policy_checks_passed: true,
    },
    at: "2026-07-31T00:01:00.000Z",
    budget_reservation: {
      calls: 1,
      network_bytes: 100,
      storage_bytes: 100,
      tokens: 100,
      wall_seconds: 60,
    },
    expires_at: "2026-07-31T00:02:00.000Z",
    idempotency_values: { input_hash: schedulerHash("input:ingest"), request_id: "REQ-W02-1" },
    input_hash: schedulerHash("input:ingest"),
    node_id: "ingest",
    owner_id: "WORKER-W02-1",
  });
  base.scheduler.startAttempt({ at: "2026-07-31T00:01:01.000Z", lease });

  const paused = pauseRun(sealArgs(base, { reason: "operator pause" }));

  assert.equal(paused.state, "PAUSED");
  assert.equal(paused.admission_open, false);
  assert.deepEqual(paused.in_flight_attempts, [
    { attempt: 1, node_id: "ingest", status: "RUNNING" },
  ]);
  assert.deepEqual(paused.manifest.pending_effect_ids, ["ingest#1"]);
  assert.deepEqual(pendingEffects(base.scheduler.snapshot()), paused.in_flight_attempts);
  validateCheckpointManifest(paused.manifest);
});
