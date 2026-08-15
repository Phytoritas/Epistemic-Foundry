// cancellation_test — cancelling a run reconciles every pending effect, and an
// unresolved effect never becomes a clean stop.

import assert from "node:assert/strict";
import test from "node:test";

import {
  admissionFixture,
  createSchedulerFixture,
  nodeContractFixture,
  reservationFixture,
  runNodeSuccessfully,
  schedulerHash,
} from "../../scheduler/scheduler-test-support.mjs";
import {
  CANCELLATION_OUTCOMES,
  CheckpointRuntimeError,
  cancelRun,
  validateCheckpointManifest,
} from "./checkpoint-runtime.mjs";
import { fixture, sealArgs } from "./checkpoint-resume.test.mjs";

function startInFlight(scheduler, nodeId, ownerSuffix = "1") {
  const lease = scheduler.acquireLease({
    admission: admissionFixture(),
    at: "2026-07-31T00:01:00.000Z",
    budget_reservation: reservationFixture(),
    expires_at: "2026-07-31T00:02:00.000Z",
    idempotency_values: {
      input_hash: schedulerHash(`input:${nodeId}`),
      request_id: `REQ-W02-${nodeId}-${ownerSuffix}`,
    },
    input_hash: schedulerHash(`input:${nodeId}`),
    node_id: nodeId,
    owner_id: `WORKER-W02-${ownerSuffix}`,
  });
  scheduler.startAttempt({ at: "2026-07-31T00:01:01.000Z", lease });
  return lease;
}

function cancelArgs(base, overrides = {}) {
  return {
    ...sealArgs(base, { checkpoint_id: "CKPT-W02-CANCEL" }),
    reason: "operator cancellation",
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

test("cancellation_test: a run with no pending effect cancels cleanly", () => {
  const base = fixture();
  runNodeSuccessfully(base.scheduler, "ingest");

  const result = cancelRun(cancelArgs(base));

  assert.equal(result.outcome, "CANCELLED");
  assert.equal(result.state, "CANCELLED");
  assert.deepEqual(result.pending_effect_ids, []);
  assert.deepEqual(result.unresolved_effects, []);
  assert.deepEqual(result.reconciled_effects, []);
  validateCheckpointManifest(result.manifest);
});

test("cancellation_test: an in-flight effect without a receipt is not a clean stop", () => {
  const base = fixture();
  startInFlight(base.scheduler, "ingest");

  const result = cancelRun(cancelArgs(base));

  assert.equal(result.outcome, "CANCELLED_WITH_UNRESOLVED_EFFECTS");
  assert.deepEqual(result.pending_effect_ids, ["ingest#1"]);
  assert.deepEqual(result.unresolved_effects, [
    { effect_id: "ingest#1", reason: "NO_RESOLVING_RECEIPT" },
  ]);
  assert.deepEqual(result.reconciled_effects, []);
});

test("cancellation_test: terminal receipts reconcile the pending effects", () => {
  const base = fixture();
  startInFlight(base.scheduler, "ingest");

  const result = cancelRun(
    cancelArgs(base, {
      effect_receipts: [
        { effect_id: "ingest#1", receipt_id: "EF-W02-1", status: "ROLLED_BACK" },
      ],
    }),
  );

  assert.equal(result.outcome, "CANCELLED");
  assert.deepEqual(result.reconciled_effects, [
    { effect_id: "ingest#1", receipt_id: "EF-W02-1", status: "ROLLED_BACK" },
  ]);
  assert.deepEqual(result.unresolved_effects, []);
});

test("cancellation_test: an UNKNOWN receipt stays unresolved", () => {
  const base = fixture();
  startInFlight(base.scheduler, "ingest");

  const result = cancelRun(
    cancelArgs(base, {
      effect_receipts: [
        { effect_id: "ingest#1", receipt_id: "EF-W02-UNKNOWN", status: "UNKNOWN" },
      ],
    }),
  );

  assert.equal(result.outcome, "CANCELLED_WITH_UNRESOLVED_EFFECTS");
  assert.deepEqual(result.unresolved_effects, [
    { effect_id: "ingest#1", reason: "RECEIPT_STATUS_UNKNOWN" },
  ]);
  assert.deepEqual(result.reconciled_effects, []);
});

test("cancellation_test: partial reconciliation stays partial", () => {
  const base = createSchedulerFixture({
    nodes: [
      nodeContractFixture({ nodeId: "ingest" }),
      nodeContractFixture({ nodeId: "probe" }),
    ],
  });
  startInFlight(base.scheduler, "ingest", "1");
  startInFlight(base.scheduler, "probe", "2");

  const result = cancelRun(
    cancelArgs(base, {
      effect_receipts: [
        { effect_id: "ingest#1", receipt_id: "EF-W02-1", status: "FAILED" },
      ],
    }),
  );

  assert.equal(result.outcome, "CANCELLED_WITH_UNRESOLVED_EFFECTS");
  assert.deepEqual(result.pending_effect_ids, ["ingest#1", "probe#1"]);
  assert.deepEqual(result.reconciled_effects, [
    { effect_id: "ingest#1", receipt_id: "EF-W02-1", status: "FAILED" },
  ]);
  assert.deepEqual(result.unresolved_effects, [
    { effect_id: "probe#1", reason: "NO_RESOLVING_RECEIPT" },
  ]);
});

test("cancellation_test: one receipt id cannot resolve two pending effects", () => {
  const base = createSchedulerFixture({
    nodes: [
      nodeContractFixture({ nodeId: "ingest" }),
      nodeContractFixture({ nodeId: "probe" }),
    ],
  });
  startInFlight(base.scheduler, "ingest", "1");
  startInFlight(base.scheduler, "probe", "2");

  assertCode(
    () =>
      cancelRun(
        cancelArgs(base, {
          effect_receipts: [
            { effect_id: "ingest#1", receipt_id: "EF-W02-SHARED", status: "SUCCEEDED" },
            { effect_id: "probe#1", receipt_id: "EF-W02-SHARED", status: "FAILED" },
          ],
        }),
      ),
    "EFFECT_RECEIPT_INVALID",
  );
});

test("cancellation_test: an unknown effect takes precedence over a reused receipt id", () => {
  const base = fixture();
  startInFlight(base.scheduler, "ingest");

  assertCode(
    () =>
      cancelRun(
        cancelArgs(base, {
          effect_receipts: [
            { effect_id: "ingest#1", receipt_id: "EF-W02-SHARED", status: "SUCCEEDED" },
            { effect_id: "ghost#9", receipt_id: "EF-W02-SHARED", status: "FAILED" },
          ],
        }),
      ),
    "EFFECT_RECEIPT_UNKNOWN_EFFECT",
  );
});

test("cancellation_test: foreign, duplicate, and malformed receipts fail closed", () => {
  const base = fixture();
  startInFlight(base.scheduler, "ingest");

  assertCode(
    () =>
      cancelRun(
        cancelArgs(base, {
          effect_receipts: [
            { effect_id: "ghost#9", receipt_id: "EF-W02-X", status: "SUCCEEDED" },
          ],
        }),
      ),
    "EFFECT_RECEIPT_UNKNOWN_EFFECT",
  );
  assertCode(
    () =>
      cancelRun(
        cancelArgs(base, {
          effect_receipts: [
            { effect_id: "ingest#1", receipt_id: "EF-W02-A", status: "SUCCEEDED" },
            { effect_id: "ingest#1", receipt_id: "EF-W02-B", status: "FAILED" },
          ],
        }),
      ),
    "EFFECT_RECEIPT_INVALID",
  );
  assertCode(
    () =>
      cancelRun(
        cancelArgs(base, {
          effect_receipts: [
            { effect_id: "ingest#1", receipt_id: "EF-W02-C", status: "MAYBE" },
          ],
        }),
      ),
    "EFFECT_RECEIPT_INVALID",
  );
  assertCode(
    () => cancelRun(cancelArgs(base, { effect_receipts: {} })),
    "CHECKPOINT_INPUT_INVALID",
  );
  assertCode(() => cancelRun(cancelArgs(base, { reason: "" })), "CHECKPOINT_INPUT_INVALID");
});

test("cancellation_test: cancellation seals a replay-verified checkpoint", () => {
  const base = fixture();
  runNodeSuccessfully(base.scheduler, "ingest");
  startInFlight(base.scheduler, "analyze");

  const result = cancelRun(cancelArgs(base));

  assert.equal(result.manifest.replay_verified, true);
  assert.equal(result.manifest.state_hash, base.scheduler.snapshot().state_hash);
  assert.deepEqual(result.manifest.terminal_node_ids, ["ingest"]);
  validateCheckpointManifest(result.manifest);
  assert.ok(CANCELLATION_OUTCOMES.includes(result.outcome));
});

test("cancellation_test: cancellation does not mutate the scheduler", () => {
  const base = fixture();
  runNodeSuccessfully(base.scheduler, "ingest");
  const before = base.scheduler.snapshot().state_hash;
  const commandsBefore = base.scheduler.commandLog().length;

  cancelRun(cancelArgs(base));

  assert.equal(base.scheduler.snapshot().state_hash, before);
  assert.equal(base.scheduler.commandLog().length, commandsBefore);
});

test("cancellation_test: cancellation is deterministic", () => {
  const base = fixture();
  startInFlight(base.scheduler, "ingest");

  const first = cancelRun(cancelArgs(base));
  const second = cancelRun(cancelArgs(base));

  assert.deepEqual(first.manifest, second.manifest);
  assert.deepEqual(first.unresolved_effects, second.unresolved_effects);
});
