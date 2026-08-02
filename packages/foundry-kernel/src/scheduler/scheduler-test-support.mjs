import { createHash } from "node:crypto";

import {
  compileSchedulerPlan,
  createDagScheduler,
  sealBudgetEnvelope,
  sealLoopContract,
} from "./dag-scheduler.mjs";

export const schedulerHash = (label) =>
  `sha256:${createHash("sha256").update(`N03:${label}`, "utf8").digest("hex")}`;

export const nodeContractFixture = ({
  nodeId,
  dependsOn = [],
  resources = [],
  capabilities = [],
  expectedEffects = [],
  maxAttempts = 2,
  failurePolicy = "fail_run",
  loopContractRef = null,
} = {}) => ({
  node_id: nodeId,
  purpose: `Execute deterministic N03 fixture ${nodeId}`,
  executor_type: "deterministic",
  executor_ref: `epistemic_foundry.scheduler.fixtures:${nodeId}`,
  input_schema_ref: "schemas/node-invocation.schema.json",
  output_schema_ref: "schemas/result-envelope.schema.json",
  depends_on: dependsOn,
  read_scope: [`artifacts/n03/${nodeId}/input/**`],
  write_scope: [`artifacts/n03/${nodeId}/output/**`],
  capabilities,
  model_tier: "deterministic",
  timeout_seconds: 60,
  max_attempts: maxAttempts,
  failure_policy: failurePolicy,
  acceptance_checks: [`${nodeId} result receipt present`],
  resource_dependencies: resources,
  determinism_class: "deterministic",
  idempotency_key_fields: ["request_id", "input_hash"],
  loop_contract_ref: loopContractRef,
  expected_effects: expectedEffects,
  required_policy_checks: ["n03 scheduler policy permits execution"],
});

export const hardBudgetFixture = ({
  calls = 20,
  concurrency = 4,
  enforcement = "HARD_PREALLOCATED",
} = {}) =>
  sealBudgetEnvelope({
    budget_id: "BUD-N03-default",
    enforcement,
    hard_limits:
      enforcement === "UNMETERED"
        ? {
            tokens: null,
            calls: null,
            wall_seconds: null,
            concurrency: null,
            storage_bytes: null,
            network_bytes: null,
          }
        : {
            tokens: 100000,
            calls,
            wall_seconds: 3600,
            concurrency,
            storage_bytes: 1000000,
            network_bytes: 1000000,
          },
    soft_cost_currency: null,
    soft_cost_amount: null,
    metering_authority: enforcement === "UNMETERED" ? null : "METER-N03-fixture",
    breach_policy: enforcement === "UNMETERED" ? "WARN" : "PAUSE_AND_ESCALATE",
    created_at: "2026-07-31T00:00:00.000Z",
  });

export const compilePlanFixture = ({
  nodes = [
    nodeContractFixture({ nodeId: "collect" }),
    nodeContractFixture({ nodeId: "analyze", dependsOn: ["collect"] }),
  ],
  loopContracts = [],
  resourceCapacities = {},
  workflowId = "n03_fixture",
} = {}) =>
  compileSchedulerPlan({
    workflow_id: workflowId,
    nodes,
    loop_contracts: loopContracts,
    resource_capacities: resourceCapacities,
  });

export const createSchedulerFixture = ({
  nodes,
  loopContracts = [],
  resourceCapacities = {},
  budget = hardBudgetFixture(),
  runId = "RUN-N03-fixture",
  workflowId = "n03_fixture",
} = {}) => {
  const plan = compilePlanFixture({
    nodes,
    loopContracts,
    resourceCapacities,
    workflowId,
  });
  return {
    budget,
    plan,
    runId,
    scheduler: createDagScheduler({ run_id: runId, plan, budget_envelope: budget }),
  };
};

export const admissionFixture = ({
  authorized = true,
  capabilityLeaseIds = [],
  blockingGateIds = [],
} = {}) => ({
  input_artifacts_resolved: authorized,
  capability_authorized: authorized,
  approval_authorized: authorized,
  policy_checks_passed: authorized,
  blocking_gate_ids: blockingGateIds,
  capability_lease_ids: capabilityLeaseIds,
});

export const reservationFixture = ({ calls = 1 } = {}) => ({
  tokens: 100,
  calls,
  wall_seconds: 60,
  storage_bytes: 100,
  network_bytes: 100,
});

export const acquireFixture = ({
  nodeId,
  ownerId = `WORKER-N03-${nodeId}`,
  at = "2026-07-31T00:01:00.000Z",
  expiresAt = "2026-07-31T00:02:00.000Z",
  inputLabel = nodeId,
  admission = admissionFixture(),
  reservation = reservationFixture(),
} = {}) => ({
  node_id: nodeId,
  owner_id: ownerId,
  at,
  expires_at: expiresAt,
  input_hash: schedulerHash(`input:${inputLabel}`),
  idempotency_values: {
    request_id: `REQ-N03-${inputLabel}`,
    input_hash: schedulerHash(`input:${inputLabel}`),
  },
  admission,
  budget_reservation: reservation,
});

export const runNodeSuccessfully = (
  scheduler,
  nodeId,
  {
    ownerId,
    at = "2026-07-31T00:01:00.000Z",
    expiresAt = "2026-07-31T00:02:00.000Z",
    startAt = "2026-07-31T00:01:01.000Z",
    finishAt = "2026-07-31T00:01:02.000Z",
    effectReceiptIds = [],
    admission = admissionFixture(),
  } = {},
) => {
  const lease = scheduler.acquireLease(
    acquireFixture({ nodeId, ownerId, at, expiresAt, admission }),
  );
  scheduler.startAttempt({ lease, at: startAt });
  const attempt = scheduler.recordSuccess({
    lease,
    at: finishAt,
    terminal_receipt_id: `RR-N03-${nodeId}-${lease.attempt}`,
    effect_receipt_ids: effectReceiptIds,
  });
  return { attempt, lease };
};

export const twoNodeLoopFixture = () => {
  const loop = sealLoopContract({
    loop_id: "LOOP-N03-bounded",
    workflow_id: "n03_loop_fixture",
    entry_node_id: "discover",
    exit_node_id: "evaluate",
    state_artifact_id: "ART-N03-loop-state",
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
  return {
    loop,
    nodes: [
      nodeContractFixture({
        nodeId: "discover",
        dependsOn: ["evaluate"],
        loopContractRef: loop.loop_id,
      }),
      nodeContractFixture({
        nodeId: "evaluate",
        dependsOn: ["discover"],
        loopContractRef: loop.loop_id,
      }),
    ],
  };
};
