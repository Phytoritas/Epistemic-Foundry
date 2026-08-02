import assert from "node:assert/strict";
import test from "node:test";

import {
  SchedulerError,
  assertSchedulerPlanIntegrity,
  compileSchedulerPlan,
  createDagScheduler,
  replaySchedulerCommands,
  sealBudgetEnvelope,
  sealLoopContract,
} from "./dag-scheduler.mjs";
import {
  acquireFixture,
  admissionFixture,
  compilePlanFixture,
  createSchedulerFixture,
  hardBudgetFixture,
  nodeContractFixture,
  runNodeSuccessfully,
  schedulerHash,
  twoNodeLoopFixture,
} from "./scheduler-test-support.mjs";

const expectCode = (code) => (error) => error instanceof SchedulerError && error.code === code;

const permute = (values) => {
  if (values.length <= 1) return [values];
  return values.flatMap((value, index) =>
    permute([...values.slice(0, index), ...values.slice(index + 1)]).map((tail) => [value, ...tail]),
  );
};

test("scheduler_property_test: graph compilation is deterministic across every node permutation", () => {
  const nodes = [
    nodeContractFixture({ nodeId: "root" }),
    nodeContractFixture({ nodeId: "left", dependsOn: ["root"] }),
    nodeContractFixture({ nodeId: "right", dependsOn: ["root"] }),
    nodeContractFixture({ nodeId: "join", dependsOn: ["right", "left"] }),
  ];
  const plans = permute(nodes).map((ordered) => compilePlanFixture({ nodes: ordered }));
  assert.equal(plans.length, 24);
  for (const plan of plans) {
    assert.equal(plan.plan_hash, plans[0].plan_hash);
    assert.deepEqual(plan, plans[0]);
    assert.deepEqual(plan.topological_order, ["root", "left", "right", "join"]);
    assertSchedulerPlanIntegrity(plan);
  }
});

test("scheduler_property_test: unknown, duplicate, self, and hostile dependencies fail closed", () => {
  assert.throws(
    () =>
      compilePlanFixture({
        nodes: [nodeContractFixture({ nodeId: "consumer", dependsOn: ["missing"] })],
      }),
    expectCode("UNKNOWN_DEPENDENCY"),
  );
  assert.throws(
    () =>
      compilePlanFixture({
        nodes: [
          nodeContractFixture({ nodeId: "duplicate" }),
          nodeContractFixture({ nodeId: "duplicate" }),
        ],
      }),
    expectCode("DUPLICATE_NODE_ID"),
  );
  assert.throws(
    () =>
      compilePlanFixture({
        nodes: [nodeContractFixture({ nodeId: "recursive", dependsOn: ["recursive"] })],
      }),
    expectCode("SELF_DEPENDENCY"),
  );

  let trapCount = 0;
  const hostile = new Proxy(nodeContractFixture({ nodeId: "hostile" }), {
    get() {
      trapCount += 1;
      throw new Error("must not execute");
    },
    ownKeys() {
      trapCount += 1;
      throw new Error("must not execute");
    },
  });
  assert.throws(
    () => compilePlanFixture({ nodes: [hostile] }),
    expectCode("NODE_CONTRACT_INVALID"),
  );
  assert.equal(trapCount, 0);
});

test("scheduler_property_test: every real cycle requires one hash-valid matching LoopContract", () => {
  const cyclicNodes = [
    nodeContractFixture({ nodeId: "discover", dependsOn: ["evaluate"] }),
    nodeContractFixture({ nodeId: "evaluate", dependsOn: ["discover"] }),
  ];
  assert.throws(
    () => compilePlanFixture({ nodes: cyclicNodes }),
    expectCode("DAG_CYCLE_WITHOUT_LOOP_CONTRACT"),
  );

  const fixture = twoNodeLoopFixture();
  const plan = compilePlanFixture({
    workflowId: "n03_loop_fixture",
    nodes: fixture.nodes,
    loopContracts: [fixture.loop],
  });
  assert.deepEqual(plan.topological_order, ["discover", "evaluate"]);
  assert.deepEqual(plan.loop_groups, [
    {
      loop_id: fixture.loop.loop_id,
      entry_node_id: "discover",
      exit_node_id: "evaluate",
      node_ids: ["discover", "evaluate"],
      contract_hash: fixture.loop.contract_hash,
    },
  ]);

  assert.throws(
    () =>
      compilePlanFixture({
        workflowId: "n03_loop_fixture",
        nodes: fixture.nodes,
        loopContracts: [{ ...fixture.loop, max_iterations: fixture.loop.max_iterations + 1 }],
      }),
    expectCode("LOOP_CONTRACT_HASH_MISMATCH"),
  );
  assert.throws(
    () =>
      compilePlanFixture({
        workflowId: "n03_loop_fixture",
        nodes: [nodeContractFixture({ nodeId: "plain" })],
        loopContracts: [fixture.loop],
      }),
    expectCode("LOOP_CONTRACT_UNUSED"),
  );

  const threeNodeLoop = sealLoopContract({
    loop_id: "LOOP-N03-three-node",
    workflow_id: "n03_three_node_loop",
    entry_node_id: "discover",
    exit_node_id: "evaluate",
    state_artifact_id: "ART-N03-three-node-loop-state",
    convergence_metric: "fresh_candidate_count",
    convergence_predicate: "fresh_candidate_count == 0",
    max_iterations: 3,
    max_cost_units: 10,
    max_wall_seconds: 600,
    dry_rounds_required: 2,
    dedupe_key: "candidate_hash",
    seen_set_scope: "run",
    on_nonconvergence: "ESCALATE",
  });
  const threeNodePlan = compilePlanFixture({
    workflowId: "n03_three_node_loop",
    loopContracts: [threeNodeLoop],
    nodes: [
      nodeContractFixture({
        nodeId: "evaluate",
        dependsOn: ["score"],
        loopContractRef: threeNodeLoop.loop_id,
      }),
      nodeContractFixture({
        nodeId: "discover",
        dependsOn: ["evaluate"],
        loopContractRef: threeNodeLoop.loop_id,
      }),
      nodeContractFixture({
        nodeId: "score",
        dependsOn: ["discover"],
        loopContractRef: threeNodeLoop.loop_id,
      }),
    ],
  });
  assert.deepEqual(threeNodePlan.topological_order, ["discover", "score", "evaluate"]);
  assert.deepEqual(threeNodePlan.loop_groups[0].node_ids, ["discover", "score", "evaluate"]);
});

test("scheduler_property_test: readiness requires successful predecessor terminal receipts", () => {
  const nodes = [
    nodeContractFixture({ nodeId: "collect" }),
    nodeContractFixture({ nodeId: "analyze", dependsOn: ["collect"] }),
  ];
  const { scheduler } = createSchedulerFixture({ nodes });
  assert.deepEqual(scheduler.readyNodes(), ["collect"]);
  assert.deepEqual(scheduler.inspectNode("analyze").blockers, [
    { code: "PREDECESSOR_NOT_SUCCEEDED", dependency: "collect", status: "MISSING" },
  ]);

  runNodeSuccessfully(scheduler, "collect");
  assert.deepEqual(scheduler.readyNodes(), ["analyze"]);
  assert.equal(scheduler.inspectNode("collect").attempts[0].terminal_receipt_id, "RR-N03-collect-1");
});

test("scheduler_property_test: admission evidence is explicit and capability leases remain external", () => {
  const nodes = [nodeContractFixture({ nodeId: "write_result", capabilities: ["artifact_write"] })];
  const { scheduler } = createSchedulerFixture({ nodes });
  assert.throws(
    () => scheduler.acquireLease(acquireFixture({ nodeId: "write_result" })),
    expectCode("CAPABILITY_LEASE_EVIDENCE_MISSING"),
  );
  assert.throws(
    () =>
      scheduler.acquireLease(
        acquireFixture({ nodeId: "write_result", admission: admissionFixture({ authorized: false }) }),
      ),
    expectCode("INPUT_ARTIFACTS_UNRESOLVED"),
  );
  assert.throws(
    () =>
      scheduler.acquireLease(
        acquireFixture({
          nodeId: "write_result",
          admission: admissionFixture({
            capabilityLeaseIds: ["CAPLEASE-N03-external"],
            blockingGateIds: ["GATE-N03-blocking"],
          }),
        }),
      ),
    expectCode("BLOCKING_GATE_PRESENT"),
  );
  const lease = scheduler.acquireLease(
    acquireFixture({
      nodeId: "write_result",
      admission: admissionFixture({ capabilityLeaseIds: ["CAPLEASE-N03-external"] }),
    }),
  );
  assert.deepEqual(lease.capability_lease_ids, ["CAPLEASE-N03-external"]);
  assert.equal(Object.hasOwn(lease, "capabilities"), false);
  assert.equal(Object.hasOwn(lease, "authority_role"), false);
});

test("scheduler_property_test: retries create immutable attempts and preserve idempotency", () => {
  const nodes = [nodeContractFixture({ nodeId: "retrieve", maxAttempts: 2 })];
  const { scheduler } = createSchedulerFixture({ nodes });
  const lease1 = scheduler.acquireLease(acquireFixture({ nodeId: "retrieve" }));
  scheduler.startAttempt({ lease: lease1, at: "2026-07-31T00:01:01.000Z" });
  const failed = scheduler.recordFailure({
    lease: lease1,
    at: "2026-07-31T00:01:02.000Z",
    failure_code: "PROVIDER_TIMEOUT",
    terminal_receipt_id: "RR-N03-retrieve-timeout",
    effect_state: "KNOWN_NO_EFFECT",
  });
  assert.equal(failed.status, "FAILED_RETRYABLE");

  const beforeRetry = scheduler.inspectNode("retrieve").attempts[0];
  const lease2 = scheduler.acquireLease(
    acquireFixture({
      nodeId: "retrieve",
      ownerId: "WORKER-N03-retry",
      at: "2026-07-31T00:02:10.000Z",
      expiresAt: "2026-07-31T00:03:10.000Z",
    }),
  );
  assert.equal(lease2.attempt, 2);
  assert.ok(lease2.fencing_token > lease1.fencing_token);
  assert.deepEqual(scheduler.inspectNode("retrieve").attempts[0], beforeRetry);
  scheduler.startAttempt({ lease: lease2, at: "2026-07-31T00:02:11.000Z" });
  const final = scheduler.recordFailure({
    lease: lease2,
    at: "2026-07-31T00:02:12.000Z",
    failure_code: "TRANSIENT_RATE_LIMIT",
    terminal_receipt_id: "RR-N03-retrieve-rate-limit",
    effect_state: "KNOWN_NO_EFFECT",
  });
  assert.equal(final.status, "FAILED_FINAL");
  assert.equal(scheduler.inspectNode("retrieve").attempts.length, 2);
  assert.throws(
    () =>
      scheduler.acquireLease(
        acquireFixture({
          nodeId: "retrieve",
          ownerId: "WORKER-N03-third",
          at: "2026-07-31T00:03:20.000Z",
          expiresAt: "2026-07-31T00:04:20.000Z",
        }),
      ),
    expectCode("NODE_NOT_READY"),
  );
});

test("scheduler_property_test: idempotency conflicts and semantic failures never retry", () => {
  const nodes = [nodeContractFixture({ nodeId: "validate", maxAttempts: 3 })];
  const { scheduler } = createSchedulerFixture({ nodes });
  const lease = scheduler.acquireLease(acquireFixture({ nodeId: "validate" }));
  scheduler.startAttempt({ lease, at: "2026-07-31T00:01:01.000Z" });
  const failure = scheduler.recordFailure({
    lease,
    at: "2026-07-31T00:01:02.000Z",
    failure_code: "SCHEMA_INVALID",
    terminal_receipt_id: "RR-N03-schema-invalid",
    effect_state: "KNOWN_NO_EFFECT",
  });
  assert.equal(failure.status, "FAILED_FINAL");

  const other = createSchedulerFixture({ nodes }).scheduler;
  const first = other.acquireLease(acquireFixture({ nodeId: "validate" }));
  other.startAttempt({ lease: first, at: "2026-07-31T00:01:01.000Z" });
  other.recordFailure({
    lease: first,
    at: "2026-07-31T00:01:02.000Z",
    failure_code: "PROVIDER_TIMEOUT",
    terminal_receipt_id: "RR-N03-retryable",
    effect_state: "KNOWN_NO_EFFECT",
  });
  assert.throws(
    () =>
      other.acquireLease(
        acquireFixture({
          nodeId: "validate",
          ownerId: "WORKER-N03-conflict",
          at: "2026-07-31T00:02:10.000Z",
          expiresAt: "2026-07-31T00:03:10.000Z",
          inputLabel: "different-input",
        }),
      ),
    expectCode("IDEMPOTENCY_CONFLICT"),
  );
});

test("scheduler_property_test: attempt activity and retry lease clocks never regress", () => {
  const nodes = [nodeContractFixture({ nodeId: "clocked", maxAttempts: 2 })];
  const { scheduler } = createSchedulerFixture({ nodes });
  const lease = scheduler.acquireLease(acquireFixture({ nodeId: "clocked" }));
  scheduler.startAttempt({ lease, at: "2026-07-31T00:01:01.000Z" });
  scheduler.heartbeat({ lease, at: "2026-07-31T00:01:10.000Z" });
  assert.throws(
    () => scheduler.heartbeat({ lease, at: "2026-07-31T00:01:09.000Z" }),
    expectCode("HEARTBEAT_CLOCK_REGRESSION"),
  );
  assert.throws(
    () =>
      scheduler.recordSuccess({
        lease,
        at: "2026-07-31T00:01:09.000Z",
        terminal_receipt_id: "RR-N03-clock-regressed-success",
        effect_receipt_ids: [],
      }),
    expectCode("ATTEMPT_CLOCK_REGRESSION"),
  );
  assert.equal(scheduler.inspectNode("clocked").attempts[0].last_heartbeat_at,
    "2026-07-31T00:01:10.000Z");
  scheduler.recordFailure({
    lease,
    at: "2026-07-31T00:01:11.000Z",
    failure_code: "PROVIDER_TIMEOUT",
    terminal_receipt_id: "RR-N03-clock-timeout",
    effect_state: "KNOWN_NO_EFFECT",
  });
  assert.throws(
    () =>
      scheduler.acquireLease(
        acquireFixture({
          nodeId: "clocked",
          ownerId: "WORKER-N03-clocked-retry",
          at: "2026-07-31T00:01:10.000Z",
          expiresAt: "2026-07-31T00:02:10.000Z",
        }),
      ),
    expectCode("ATTEMPT_CLOCK_REGRESSION"),
  );
  assert.equal(scheduler.inspectNode("clocked").attempts.length, 1);
});

test("scheduler_property_test: expired attempts reconcile before a retry can be assigned", () => {
  const nodes = [nodeContractFixture({ nodeId: "remote_call", maxAttempts: 2 })];
  const { scheduler } = createSchedulerFixture({ nodes });
  const lease = scheduler.acquireLease(acquireFixture({ nodeId: "remote_call" }));
  scheduler.startAttempt({ lease, at: "2026-07-31T00:01:01.000Z" });
  assert.deepEqual(scheduler.reconcileExpired({ at: "2026-07-31T00:02:00.000Z" }), [
    { node_id: "remote_call", attempt: 1, lease_id: lease.lease_id },
  ]);
  assert.equal(scheduler.inspectNode("remote_call").attempts[0].status, "RECONCILING");
  assert.throws(
    () =>
      scheduler.acquireLease(
        acquireFixture({
          nodeId: "remote_call",
          at: "2026-07-31T00:02:10.000Z",
          expiresAt: "2026-07-31T00:03:10.000Z",
        }),
      ),
    expectCode("NODE_NOT_READY"),
  );
  const reconciled = scheduler.resolveReconciliation({
    node_id: "remote_call",
    attempt: 1,
    at: "2026-07-31T00:02:05.000Z",
    outcome: "NO_EFFECT",
    reconciliation_receipt_id: "RECON-N03-remote-call",
    terminal_receipt_id: "RR-N03-orphan-resolved",
    effect_receipt_ids: [],
  });
  assert.equal(reconciled.status, "FAILED_RETRYABLE");
  const retry = scheduler.acquireLease(
    acquireFixture({
      nodeId: "remote_call",
      ownerId: "WORKER-N03-reconciled-retry",
      at: "2026-07-31T00:02:10.000Z",
      expiresAt: "2026-07-31T00:03:10.000Z",
    }),
  );
  assert.equal(retry.attempt, 2);
});

test("scheduler_property_test: unknown effects can reconcile to success only with receipts", () => {
  const nodes = [
    nodeContractFixture({
      nodeId: "external_effect",
      expectedEffects: ["publish_artifact"],
      maxAttempts: 2,
    }),
  ];
  const { scheduler } = createSchedulerFixture({ nodes });
  const lease = scheduler.acquireLease(acquireFixture({ nodeId: "external_effect" }));
  scheduler.startAttempt({ lease, at: "2026-07-31T00:01:01.000Z" });
  const unknown = scheduler.recordFailure({
    lease,
    at: "2026-07-31T00:01:02.000Z",
    failure_code: "NETWORK_INTERRUPTION_BEFORE_RECEIPT",
    terminal_receipt_id: "RR-N03-effect-unknown",
    effect_state: "UNKNOWN",
  });
  assert.equal(unknown.status, "RECONCILING");
  assert.throws(
    () =>
      scheduler.resolveReconciliation({
        node_id: "external_effect",
        attempt: 1,
        at: "2026-07-31T00:01:10.000Z",
        outcome: "EFFECT_SUCCEEDED",
        reconciliation_receipt_id: "RECON-N03-effect",
        terminal_receipt_id: "RR-N03-effect-success",
        effect_receipt_ids: [],
      }),
    expectCode("EFFECT_RECEIPT_MISSING"),
  );
  const success = scheduler.resolveReconciliation({
    node_id: "external_effect",
    attempt: 1,
    at: "2026-07-31T00:01:10.000Z",
    outcome: "EFFECT_SUCCEEDED",
    reconciliation_receipt_id: "RECON-N03-effect",
    terminal_receipt_id: "RR-N03-effect-success",
    effect_receipt_ids: ["ER-N03-effect"],
  });
  assert.equal(success.status, "SUCCEEDED");
  assert.deepEqual(success.effect_receipt_ids, ["ER-N03-effect"]);
});

test("scheduler_property_test: typed hard budgets enforce calls and concurrency without inventing meters", () => {
  const nodes = [
    nodeContractFixture({ nodeId: "first" }),
    nodeContractFixture({ nodeId: "second" }),
  ];
  const limited = createSchedulerFixture({
    nodes,
    budget: hardBudgetFixture({ calls: 1, concurrency: 1 }),
  }).scheduler;
  limited.acquireLease(acquireFixture({ nodeId: "first" }));
  assert.throws(
    () => limited.acquireLease(acquireFixture({ nodeId: "second", inputLabel: "second" })),
    (error) =>
      error instanceof SchedulerError &&
      ["BUDGET_LIMIT_EXCEEDED", "CONCURRENCY_LIMIT_EXCEEDED"].includes(error.code),
  );

  assert.throws(
    () =>
      sealBudgetEnvelope({
        budget_id: "BUD-N03-invalid-hard",
        enforcement: "HARD_METERED",
        hard_limits: {
          tokens: 10,
          calls: 1,
          wall_seconds: 1,
          concurrency: 1,
          storage_bytes: 1,
          network_bytes: 1,
        },
        soft_cost_currency: null,
        soft_cost_amount: null,
        metering_authority: null,
        breach_policy: "CANCEL",
        created_at: "2026-07-31T00:00:00.000Z",
      }),
    expectCode("BUDGET_ENVELOPE_INVALID"),
  );
  const unmetered = hardBudgetFixture({ enforcement: "UNMETERED" });
  assert.equal(unmetered.enforcement, "UNMETERED");
  assert.equal(unmetered.metering_authority, null);
});

test("scheduler_property_test: bounded loops dedupe all seen items and enforce dry rounds and limits", () => {
  const fixture = twoNodeLoopFixture();
  const { scheduler } = createSchedulerFixture({
    workflowId: "n03_loop_fixture",
    nodes: fixture.nodes,
    loopContracts: [fixture.loop],
  });
  assert.deepEqual(scheduler.readyNodes(), ["discover"]);

  const first = scheduler.recordLoopRound({
    loop_id: fixture.loop.loop_id,
    at: "2026-07-31T00:01:00.000Z",
    observed_item_keys: ["candidate-b", "candidate-a"],
    cost_units: 2,
    convergence_met: false,
  });
  assert.deepEqual(first.seen_item_keys, ["candidate-a", "candidate-b"]);
  assert.equal(first.dry_rounds, 0);
  assert.throws(
    () =>
      scheduler.recordLoopRound({
        loop_id: fixture.loop.loop_id,
        at: "2026-07-31T00:00:59.000Z",
        observed_item_keys: ["candidate-c"],
        cost_units: 1,
        convergence_met: false,
      }),
    expectCode("LOOP_CLOCK_REGRESSION"),
  );
  assert.equal(scheduler.snapshot().loop_states[fixture.loop.loop_id].iterations, 1);
  const second = scheduler.recordLoopRound({
    loop_id: fixture.loop.loop_id,
    at: "2026-07-31T00:02:00.000Z",
    observed_item_keys: ["candidate-a"],
    cost_units: 2,
    convergence_met: true,
  });
  assert.equal(second.dry_rounds, 1);
  const third = scheduler.recordLoopRound({
    loop_id: fixture.loop.loop_id,
    at: "2026-07-31T00:03:00.000Z",
    observed_item_keys: ["candidate-b"],
    cost_units: 2,
    convergence_met: true,
  });
  assert.equal(third.status, "CONVERGED");
  assert.equal(third.dry_rounds, 2);
  assert.throws(
    () =>
      scheduler.recordLoopRound({
        loop_id: fixture.loop.loop_id,
        at: "2026-07-31T00:04:00.000Z",
        observed_item_keys: [],
        cost_units: 0,
        convergence_met: true,
      }),
    expectCode("LOOP_TERMINAL"),
  );
});

test("scheduler_property_test: failure policy remains visible to downstream readiness", () => {
  for (const [failurePolicy, expectedCode] of [
    ["fail_run", "PREDECESSOR_FAILED_RUN"],
    ["mark_partial", "PARTIAL_PREDECESSOR_NOT_AUTHORIZED"],
    ["skip_downstream", "PREDECESSOR_SKIPS_DOWNSTREAM"],
    ["escalate", "PREDECESSOR_ESCALATION_REQUIRED"],
  ]) {
    const nodes = [
      nodeContractFixture({ nodeId: "producer", failurePolicy, maxAttempts: 1 }),
      nodeContractFixture({ nodeId: "consumer", dependsOn: ["producer"] }),
    ];
    const { scheduler } = createSchedulerFixture({ nodes, runId: `RUN-N03-${failurePolicy}` });
    const lease = scheduler.acquireLease(acquireFixture({ nodeId: "producer" }));
    scheduler.startAttempt({ lease, at: "2026-07-31T00:01:01.000Z" });
    scheduler.recordFailure({
      lease,
      at: "2026-07-31T00:01:02.000Z",
      failure_code: "DETERMINISTIC_TEST_FAILURE",
      terminal_receipt_id: `RR-N03-${failurePolicy}`,
      effect_state: "KNOWN_NO_EFFECT",
    });
    assert.deepEqual(scheduler.inspectNode("consumer").blockers, [
      { code: expectedCode, dependency: "producer", status: "FAILED_FINAL" },
    ]);
  }
});

test("scheduler_property_test: command replay reproduces exact state and rejects tamper", () => {
  const nodes = [nodeContractFixture({ nodeId: "deterministic" })];
  const { scheduler, plan, budget, runId } = createSchedulerFixture({ nodes });
  runNodeSuccessfully(scheduler, "deterministic");
  const commands = scheduler.commandLog();
  const direct = scheduler.snapshot();
  const replay = replaySchedulerCommands({
    run_id: runId,
    plan,
    budget_envelope: budget,
    commands,
  });
  assert.deepEqual(replay.snapshot, direct);
  assert.deepEqual(replay.commands, commands);
  assert.match(direct.state_hash, /^sha256:[0-9a-f]{64}$/u);

  const tampered = structuredClone(commands);
  tampered[0].input.input_hash = schedulerHash("tampered");
  assert.throws(
    () =>
      replaySchedulerCommands({
        run_id: runId,
        plan,
        budget_envelope: budget,
        commands: tampered,
      }),
    (error) => error instanceof SchedulerError,
  );
});

test("scheduler_property_test: plan, lease, attempt, and snapshot outputs are immutable", () => {
  const plan = compilePlanFixture({ nodes: [nodeContractFixture({ nodeId: "immutable" })] });
  const scheduler = createDagScheduler({
    run_id: "RUN-N03-immutable",
    plan,
    budget_envelope: hardBudgetFixture(),
  });
  const lease = scheduler.acquireLease(acquireFixture({ nodeId: "immutable" }));
  const attempt = scheduler.startAttempt({ lease, at: "2026-07-31T00:01:01.000Z" });
  const snapshot = scheduler.snapshot();
  assert.equal(Object.isFrozen(plan), true);
  assert.equal(Object.isFrozen(plan.nodes[0]), true);
  assert.equal(Object.isFrozen(lease), true);
  assert.equal(Object.isFrozen(attempt), true);
  assert.equal(Object.isFrozen(snapshot), true);
  assert.deepEqual(snapshot.active_lease_ids, [lease.lease_id]);
  assert.deepEqual(snapshot.active_leases, [lease]);
  assert.equal(snapshot.idempotency_bindings.immutable, lease.idempotency_hash);
  assert.throws(() => {
    lease.fencing_token = 999;
  }, TypeError);
});
