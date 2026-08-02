import assert from "node:assert/strict";
import test from "node:test";

import { SchedulerError } from "./dag-scheduler.mjs";
import {
  acquireFixture,
  createSchedulerFixture,
  hardBudgetFixture,
  nodeContractFixture,
} from "./scheduler-test-support.mjs";

const expectCode = (code) => (error) => error instanceof SchedulerError && error.code === code;

test("resource_conflict_test: exclusive resources admit exactly one owner", () => {
  const nodes = [
    nodeContractFixture({ nodeId: "writer_a", resources: ["exclusive:evidence_projection"] }),
    nodeContractFixture({ nodeId: "writer_b", resources: ["exclusive:evidence_projection"] }),
  ];
  const { scheduler } = createSchedulerFixture({ nodes });
  const first = scheduler.acquireLease(acquireFixture({ nodeId: "writer_a" }));
  assert.throws(
    () => scheduler.acquireLease(acquireFixture({ nodeId: "writer_b", inputLabel: "writer-b" })),
    expectCode("RESOURCE_CONFLICT"),
  );
  const snapshot = scheduler.snapshot();
  assert.deepEqual(snapshot.resource_owners["exclusive:evidence_projection"], [first.lease_id]);
  assert.equal(snapshot.node_attempts.writer_b.length, 0);
  assert.equal(snapshot.fencing_counter, 1);
});

test("resource_conflict_test: multi-resource acquisition is all-or-none", () => {
  const nodes = [
    nodeContractFixture({ nodeId: "holder", resources: ["exclusive:shared"] }),
    nodeContractFixture({
      nodeId: "contender",
      resources: ["exclusive:free", "exclusive:shared"],
    }),
    nodeContractFixture({ nodeId: "observer", resources: ["exclusive:free"] }),
  ];
  const { scheduler } = createSchedulerFixture({ nodes });
  scheduler.acquireLease(acquireFixture({ nodeId: "holder" }));
  const before = scheduler.snapshot();
  assert.throws(
    () => scheduler.acquireLease(acquireFixture({ nodeId: "contender", inputLabel: "contender" })),
    expectCode("RESOURCE_CONFLICT"),
  );
  const after = scheduler.snapshot();
  assert.equal(after.fencing_counter, before.fencing_counter);
  assert.equal(after.node_attempts.contender.length, 0);
  assert.equal(Object.hasOwn(after.resource_owners, "exclusive:free"), false);
  const observer = scheduler.acquireLease(
    acquireFixture({ nodeId: "observer", inputLabel: "observer" }),
  );
  assert.deepEqual(scheduler.snapshot().resource_owners["exclusive:free"], [observer.lease_id]);
});

test("resource_conflict_test: bounded quota permits capacity owners and rejects overflow", () => {
  const resource = "quota:retrieval:semantic";
  const nodes = [
    nodeContractFixture({ nodeId: "query_a", resources: [resource] }),
    nodeContractFixture({ nodeId: "query_b", resources: [resource] }),
    nodeContractFixture({ nodeId: "query_c", resources: [resource] }),
  ];
  const { scheduler } = createSchedulerFixture({
    nodes,
    resourceCapacities: { [resource]: 2 },
    budget: hardBudgetFixture({ concurrency: 3 }),
  });
  const first = scheduler.acquireLease(acquireFixture({ nodeId: "query_a" }));
  const second = scheduler.acquireLease(acquireFixture({ nodeId: "query_b", inputLabel: "query-b" }));
  assert.throws(
    () => scheduler.acquireLease(acquireFixture({ nodeId: "query_c", inputLabel: "query-c" })),
    expectCode("RESOURCE_CONFLICT"),
  );
  assert.deepEqual(scheduler.snapshot().resource_owners[resource],
    [first.lease_id, second.lease_id].sort());

  scheduler.startAttempt({ lease: first, at: "2026-07-31T00:01:01.000Z" });
  scheduler.recordSuccess({
    lease: first,
    at: "2026-07-31T00:01:02.000Z",
    terminal_receipt_id: "RR-N03-query-a",
    effect_receipt_ids: [],
  });
  const third = scheduler.acquireLease(
    acquireFixture({ nodeId: "query_c", inputLabel: "query-c", ownerId: "WORKER-N03-query-c" }),
  );
  assert.equal(third.fencing_token, 3);
  scheduler.startAttempt({ lease: second, at: "2026-07-31T00:01:03.000Z" });
  assert.equal(scheduler.inspectNode("query_b").attempts[0].status, "RUNNING");
});

test("resource_conflict_test: quota capacities must be explicit and exclusive capacity cannot broaden", () => {
  const quotaNode = nodeContractFixture({
    nodeId: "quota_user",
    resources: ["quota:provider:calls"],
  });
  assert.throws(
    () => createSchedulerFixture({ nodes: [quotaNode] }),
    expectCode("RESOURCE_CAPACITY_MISSING"),
  );
  const exclusiveNode = nodeContractFixture({
    nodeId: "exclusive_user",
    resources: ["exclusive:ledger_commit"],
  });
  assert.throws(
    () =>
      createSchedulerFixture({
        nodes: [exclusiveNode],
        resourceCapacities: { "exclusive:ledger_commit": 2 },
      }),
    expectCode("RESOURCE_CAPACITY_INVALID"),
  );
});

test("resource_conflict_test: expiry releases ownership only into reconciliation", () => {
  const nodes = [
    nodeContractFixture({ nodeId: "old_worker", resources: ["exclusive:checkpoint"] }),
    nodeContractFixture({ nodeId: "new_worker", resources: ["exclusive:checkpoint"] }),
  ];
  const { scheduler } = createSchedulerFixture({ nodes });
  const oldLease = scheduler.acquireLease(acquireFixture({ nodeId: "old_worker" }));
  scheduler.startAttempt({ lease: oldLease, at: "2026-07-31T00:01:01.000Z" });
  const orphaned = scheduler.reconcileExpired({ at: oldLease.expires_at });
  assert.equal(orphaned.length, 1);
  assert.equal(scheduler.inspectNode("old_worker").attempts[0].status, "RECONCILING");

  const newLease = scheduler.acquireLease(
    acquireFixture({
      nodeId: "new_worker",
      inputLabel: "new-worker",
      at: "2026-07-31T00:02:01.000Z",
      expiresAt: "2026-07-31T00:03:01.000Z",
    }),
  );
  assert.ok(newLease.fencing_token > oldLease.fencing_token);
  assert.throws(
    () => scheduler.startAttempt({ lease: oldLease, at: "2026-07-31T00:02:02.000Z" }),
    expectCode("STALE_FENCING_TOKEN"),
  );
  assert.equal(scheduler.inspectNode("old_worker").attempts[0].status, "RECONCILING");
});

test("resource_conflict_test: stale token cannot commit after a newer node lease", () => {
  const nodes = [nodeContractFixture({ nodeId: "retryable", maxAttempts: 2 })];
  const { scheduler } = createSchedulerFixture({ nodes });
  const oldLease = scheduler.acquireLease(acquireFixture({ nodeId: "retryable" }));
  scheduler.startAttempt({ lease: oldLease, at: "2026-07-31T00:01:01.000Z" });
  scheduler.recordFailure({
    lease: oldLease,
    at: "2026-07-31T00:01:02.000Z",
    failure_code: "PROVIDER_TIMEOUT",
    terminal_receipt_id: "RR-N03-old-timeout",
    effect_state: "KNOWN_NO_EFFECT",
  });
  const newLease = scheduler.acquireLease(
    acquireFixture({
      nodeId: "retryable",
      ownerId: "WORKER-N03-new",
      at: "2026-07-31T00:02:10.000Z",
      expiresAt: "2026-07-31T00:03:10.000Z",
    }),
  );
  assert.throws(
    () =>
      scheduler.recordSuccess({
        lease: oldLease,
        at: "2026-07-31T00:02:11.000Z",
        terminal_receipt_id: "RR-N03-stale-success",
        effect_receipt_ids: [],
      }),
    expectCode("STALE_FENCING_TOKEN"),
  );
  scheduler.startAttempt({ lease: newLease, at: "2026-07-31T00:02:11.000Z" });
  assert.equal(scheduler.inspectNode("retryable").attempts[1].status, "RUNNING");
});

test("resource_conflict_test: exact acquisition retry returns one lease and one reservation", () => {
  const nodes = [nodeContractFixture({ nodeId: "idempotent_lease" })];
  const { scheduler } = createSchedulerFixture({ nodes });
  const request = acquireFixture({ nodeId: "idempotent_lease" });
  const first = scheduler.acquireLease(request);
  const second = scheduler.acquireLease(structuredClone(request));
  assert.deepEqual(second, first);
  const snapshot = scheduler.snapshot();
  assert.equal(snapshot.node_attempts.idempotent_lease.length, 1);
  assert.equal(snapshot.budget_usage.calls, 1);
  assert.equal(snapshot.fencing_counter, 1);
});

test("resource_conflict_test: active lease retry rejects changed admission or reservation", () => {
  const nodes = [nodeContractFixture({ nodeId: "bound_request" })];
  const { scheduler } = createSchedulerFixture({ nodes });
  const request = acquireFixture({ nodeId: "bound_request" });
  const lease = scheduler.acquireLease(request);
  const changedReservation = structuredClone(request);
  changedReservation.budget_reservation.calls = 2;
  assert.throws(
    () => scheduler.acquireLease(changedReservation),
    expectCode("IDEMPOTENCY_CONFLICT"),
  );
  const changedAdmission = structuredClone(request);
  changedAdmission.admission.capability_lease_ids = ["CAPLEASE-N03-changed"];
  assert.throws(
    () => scheduler.acquireLease(changedAdmission),
    expectCode("IDEMPOTENCY_CONFLICT"),
  );
  const snapshot = scheduler.snapshot();
  assert.deepEqual(snapshot.active_leases, [lease]);
  assert.equal(snapshot.node_attempts.bound_request.length, 1);
  assert.equal(snapshot.budget_usage.calls, 1);
});

test("resource_conflict_test: failed admission does not consume token, budget, or resource", () => {
  const nodes = [nodeContractFixture({ nodeId: "gated", resources: ["exclusive:gated"] })];
  const { scheduler } = createSchedulerFixture({ nodes });
  const before = scheduler.snapshot();
  assert.throws(
    () =>
      scheduler.acquireLease(
        acquireFixture({
          nodeId: "gated",
          admission: {
            input_artifacts_resolved: true,
            capability_authorized: true,
            approval_authorized: true,
            policy_checks_passed: true,
            blocking_gate_ids: ["GATE-N03-deny"],
            capability_lease_ids: [],
          },
        }),
      ),
    expectCode("BLOCKING_GATE_PRESENT"),
  );
  const after = scheduler.snapshot();
  assert.equal(after.fencing_counter, before.fencing_counter);
  assert.deepEqual(after.budget_usage, before.budget_usage);
  assert.deepEqual(after.resource_owners, before.resource_owners);
  assert.equal(after.node_attempts.gated.length, 0);
});
