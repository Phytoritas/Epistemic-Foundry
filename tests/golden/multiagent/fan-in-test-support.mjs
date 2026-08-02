import {
  makeExecutionBinding,
  makeHostCapabilityReport,
  makeModelResolution,
} from "../../../packages/role-router/src/adapters/adapter-test-support.mjs";
import { compileCodexSpawnDescriptor } from "../../../packages/role-router/src/adapters/index.mjs";
import {
  createRoleSpec,
  projectRoleSpecToDispatchRole,
} from "../../../packages/role-router/src/contracts/index.mjs";
import {
  admissionFixture,
  createSchedulerFixture,
  nodeContractFixture,
  runNodeSuccessfully,
  schedulerHash,
} from "../../../packages/foundry-kernel/src/scheduler/scheduler-test-support.mjs";
import { sha256SchedulerJson } from "../../../packages/foundry-kernel/src/scheduler/index.mjs";

import {
  INDEPENDENT_REVIEW_VERSION,
  sealIndependentReview,
  sha256FanInJson,
} from "./fan-in-gate.mjs";

const ROLE_IDS = Object.freeze(["maker_alpha", "maker_beta", "independent_reviewer"]);

const roleSpec = ({ roleId, dependsOn, independenceGroup, mission }) =>
  createRoleSpec({
    role_spec_version: "4.0.0-n01.1",
    role_id: roleId,
    mission,
    forbidden_behaviors: ["invent evidence", "self approve"],
    host_agent_type: "explorer",
    model_tier: "balanced",
    fallback_model_tiers: ["economy"],
    read_scope: ["artifacts/n04/input/**"],
    write_scope: [`artifacts/n04/${roleId}/**`],
    tool_acl: ["artifact_read", "artifact_write"],
    network_acl: [],
    evidence_acl: ["implementation_contract"],
    input_schema_refs: ["schemas/role-dispatch-plan.schema.json"],
    output_schema_ref: "schemas/result-envelope.schema.json",
    budget_tokens: 8_000,
    timeout_seconds: 600,
    expected_count: 1,
    independence_group: independenceGroup,
    acceptance_checks: ["receipt-bound result exists"],
    failure_policy: "fail_run",
    max_attempts: 2,
    depends_on: dependsOn,
  });

const sealDispatchPlan = (roles, budgetEnvelopeId) => {
  const preimage = {
    plan_id: "RDP-N04-fixture",
    session_id: "SESSION-N04-fixture",
    roles: roles.map(projectRoleSpecToDispatchRole),
    expected_count: roles.length,
    fan_in_policy: "all_required",
    missing_result_policy: "fail_gate",
    max_concurrency: 3,
    budget_envelope_id: budgetEnvelopeId,
  };
  return { ...preimage, plan_hash: sha256FanInJson(preimage) };
};

const nodeContractForRole = (spec) => ({
  ...nodeContractFixture({
    nodeId: spec.role_id,
    dependsOn: spec.depends_on,
    capabilities: spec.tool_acl,
    maxAttempts: spec.max_attempts,
    failurePolicy: spec.failure_policy,
  }),
  purpose: spec.mission,
  executor_type: "llm",
  executor_ref: `epistemic_foundry.role_router:${spec.role_id}`,
  output_schema_ref: spec.output_schema_ref,
  read_scope: [...spec.read_scope],
  write_scope: [...spec.write_scope],
  capabilities: [...spec.tool_acl],
  model_tier: spec.model_tier,
  timeout_seconds: spec.timeout_seconds,
  acceptance_checks: [...spec.acceptance_checks],
  determinism_class: "provider_nondeterministic",
});

const compileDescriptor = (spec, nodeContract, index) => {
  const hostCapabilityReport = makeHostCapabilityReport();
  return compileCodexSpawnDescriptor({
    roleSpec: spec,
    hostCapabilityReport,
    executionBinding: makeExecutionBinding({
      node_id: spec.role_id,
      node_contract_id: `NODE-N04-${spec.role_id}`,
      node_contract_hash: sha256SchedulerJson(nodeContract),
      context_capsule_id: `CTX-N04-${spec.role_id}`,
      context_capsule_hash: schedulerHash(`context:${spec.role_id}`),
    }),
    modelResolution: makeModelResolution({
      routing_receipt_id: `MRR-N04-${index + 1}`,
      routing_receipt_hash: schedulerHash(`routing:${spec.role_id}`),
    }),
  });
};

const resultEnvelope = ({ roleId, attempt, outputArtifactIds }) => ({
  run_id: attempt.run_id,
  node_id: roleId,
  attempt: attempt.attempt,
  status: "success",
  output_artifact_ids: outputArtifactIds,
  evidence_ids: [`EVIDENCE-N04-${roleId}`],
  errors: [],
  metrics: { receipt_bound: true },
  input_hash: attempt.input_hash,
  output_hash: sha256FanInJson({ role_id: roleId, output_artifact_ids: outputArtifactIds }),
  started_at: attempt.started_at,
  finished_at: attempt.finished_at,
  completeness: {
    expected_count: 1,
    terminal_count: 1,
    missing_node_ids: [],
    partial_allowed: false,
  },
  effect_receipt_ids: attempt.effect_receipt_ids,
  policy_decision_ids: [],
  schema_validation_report_id: `SVR-N04-${roleId}`,
  terminal_reason: "receipt-bound role result completed",
});

const submission = ({ descriptor, attempt, outputArtifactIds }) => ({
  role_id: descriptor.canonical_role_spec.role_id,
  spawn_descriptor_id: descriptor.spawn_descriptor_id,
  terminal_receipt_id: attempt.terminal_receipt_id,
  result_envelope: resultEnvelope({
    roleId: descriptor.canonical_role_spec.role_id,
    attempt,
    outputArtifactIds,
  }),
});

export const buildFanInFixture = ({
  makerActorIds = ["ACTOR-N04-maker-alpha", "ACTOR-N04-maker-beta"],
  reviewerActorId = "ACTOR-N04-independent-reviewer",
  makerIndependenceGroups = ["maker_alpha_group", "maker_beta_group"],
  reviewerIndependenceGroup = "independent_review_group",
  reviewerDependsOn = [ROLE_IDS[0], ROLE_IDS[1]],
  reviewVerdict = "PASS",
} = {}) => {
  const roleSpecs = [
    roleSpec({
      roleId: ROLE_IDS[0],
      dependsOn: [],
      independenceGroup: makerIndependenceGroups[0],
      mission: "Produce the first receipt-bound maker result without approving it.",
    }),
    roleSpec({
      roleId: ROLE_IDS[1],
      dependsOn: [],
      independenceGroup: makerIndependenceGroups[1],
      mission: "Produce the second receipt-bound maker result without approving it.",
    }),
    roleSpec({
      roleId: ROLE_IDS[2],
      dependsOn: reviewerDependsOn,
      independenceGroup: reviewerIndependenceGroup,
      mission: "Independently review every maker terminal receipt and issue a verdict.",
    }),
  ];
  const nodes = roleSpecs.map(nodeContractForRole);
  const {
    scheduler,
    plan: schedulerPlan,
    budget: schedulerBudgetEnvelope,
  } = createSchedulerFixture({
    nodes,
    runId: "RUN-N04-fixture",
    workflowId: "n04_fan_in_fixture",
  });
  const dispatchPlan = sealDispatchPlan(roleSpecs, schedulerBudgetEnvelope.budget_id);
  const schedulerNodes = new Map(
    schedulerPlan.nodes.map((nodeContract) => [nodeContract.node_id, nodeContract]),
  );
  const spawnDescriptors = roleSpecs.map((spec, index) =>
    compileDescriptor(spec, schedulerNodes.get(spec.role_id), index),
  );
  const alpha = runNodeSuccessfully(scheduler, ROLE_IDS[0], {
    ownerId: makerActorIds[0],
    at: "2026-07-31T04:01:00.000Z",
    expiresAt: "2026-07-31T04:02:00.000Z",
    startAt: "2026-07-31T04:01:01.000Z",
    finishAt: "2026-07-31T04:01:02.000Z",
    admission: admissionFixture({
      capabilityLeaseIds: ["CAPLEASE-N04-maker-alpha"],
    }),
  }).attempt;
  const beta = runNodeSuccessfully(scheduler, ROLE_IDS[1], {
    ownerId: makerActorIds[1],
    at: "2026-07-31T04:02:00.000Z",
    expiresAt: "2026-07-31T04:03:00.000Z",
    startAt: "2026-07-31T04:02:01.000Z",
    finishAt: "2026-07-31T04:02:02.000Z",
    admission: admissionFixture({
      capabilityLeaseIds: ["CAPLEASE-N04-maker-beta"],
    }),
  }).attempt;
  const reviewer = runNodeSuccessfully(scheduler, ROLE_IDS[2], {
    ownerId: reviewerActorId,
    at: "2026-07-31T04:03:00.000Z",
    expiresAt: "2026-07-31T04:04:00.000Z",
    startAt: "2026-07-31T04:03:01.000Z",
    finishAt: "2026-07-31T04:03:02.000Z",
    admission: admissionFixture({
      capabilityLeaseIds: ["CAPLEASE-N04-independent-reviewer"],
    }),
  }).attempt;
  const schedulerSnapshot = scheduler.snapshot();
  const schedulerCommands = scheduler.commandLog();
  const alphaSubmission = submission({
    descriptor: spawnDescriptors[0],
    attempt: alpha,
    outputArtifactIds: ["ART-N04-maker-alpha"],
  });
  const betaSubmission = submission({
    descriptor: spawnDescriptors[1],
    attempt: beta,
    outputArtifactIds: ["ART-N04-maker-beta"],
  });
  const reviewedResultBindings = [alphaSubmission, betaSubmission]
    .map((entry) => ({
      role_id: entry.role_id,
      terminal_receipt_id: entry.terminal_receipt_id,
      output_artifact_ids: entry.result_envelope.output_artifact_ids,
      output_hash: entry.result_envelope.output_hash,
    }))
    .sort((left, right) => left.role_id.localeCompare(right.role_id));
  const independentReview = sealIndependentReview({
    review_version: INDEPENDENT_REVIEW_VERSION,
    reviewer_role_id: ROLE_IDS[2],
    reviewer_actor_id: reviewerActorId,
    reviewer_independence_group: reviewerIndependenceGroup,
    reviewer_terminal_receipt_id: reviewer.terminal_receipt_id,
    dispatch_plan_hash: dispatchPlan.plan_hash,
    scheduler_state_hash: schedulerSnapshot.state_hash,
    scheduler_command_log_hash: sha256SchedulerJson(schedulerCommands),
    reviewed_terminal_receipt_ids: [alpha.terminal_receipt_id, beta.terminal_receipt_id],
    reviewed_result_bindings: reviewedResultBindings,
    verdict: reviewVerdict,
    findings: [],
  });
  const resultSubmissions = [
    alphaSubmission,
    betaSubmission,
    submission({
      descriptor: spawnDescriptors[2],
      attempt: reviewer,
      outputArtifactIds: [independentReview.review_id],
    }),
  ];
  return {
    dispatchPlan,
    spawnDescriptors,
    schedulerPlan,
    schedulerBudgetEnvelope,
    schedulerCommands,
    schedulerSnapshot,
    resultSubmissions,
    independentReview,
  };
};

export const rehashDispatchPlan = (candidate) => {
  const copy = structuredClone(candidate);
  const preimage = Object.fromEntries(
    Object.entries(copy).filter(([key]) => key !== "plan_hash"),
  );
  copy.plan_hash = sha256FanInJson(preimage);
  return copy;
};

export const rehashSchedulerSnapshot = (candidate) => {
  const copy = structuredClone(candidate);
  const semantic = Object.fromEntries(
    Object.entries(copy).filter(([key]) => key !== "state_hash"),
  );
  copy.state_hash = sha256SchedulerJson(semantic);
  return copy;
};

export const resealIndependentReview = (candidate) => {
  const copy = structuredClone(candidate);
  return sealIndependentReview(
    Object.fromEntries(
      Object.entries(copy).filter(
        ([key]) => key !== "review_id" && key !== "review_hash",
      ),
    ),
  );
};

export const expectFanInCode = (assert, code, operation) => {
  assert.throws(operation, (error) => {
    assert.equal(error?.name, "FanInGateError");
    assert.equal(error?.code, code);
    return true;
  });
};

export { ROLE_IDS };
