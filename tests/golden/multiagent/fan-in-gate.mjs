import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

import {
  ROLE_DISPATCH_PROJECTION_FIELDS,
  canonicalizeRoleSpecJson,
  projectRoleSpecToDispatchRole,
} from "../../../packages/role-router/src/contracts/index.mjs";
import { verifySpawnDescriptorIntegrity } from "../../../packages/role-router/src/adapters/index.mjs";
import {
  assertSchedulerPlanIntegrity,
  canonicalizeSchedulerJson,
  replaySchedulerCommands,
  sha256SchedulerJson,
} from "../../../packages/foundry-kernel/src/scheduler/index.mjs";

export const FAN_IN_GATE_VERSION = "4.0.0-n04.1";
export const INDEPENDENT_REVIEW_VERSION = "4.0.0-n04.1";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;

const PLAN_FIELDS = Object.freeze([
  "plan_id",
  "session_id",
  "roles",
  "expected_count",
  "fan_in_policy",
  "missing_result_policy",
  "max_concurrency",
  "budget_envelope_id",
  "plan_hash",
]);

const SUBMISSION_FIELDS = Object.freeze([
  "role_id",
  "spawn_descriptor_id",
  "terminal_receipt_id",
  "result_envelope",
]);

const RESULT_ENVELOPE_FIELDS = Object.freeze([
  "run_id",
  "node_id",
  "attempt",
  "status",
  "output_artifact_ids",
  "evidence_ids",
  "errors",
  "metrics",
  "input_hash",
  "output_hash",
  "started_at",
  "finished_at",
  "completeness",
  "effect_receipt_ids",
  "policy_decision_ids",
  "schema_validation_report_id",
  "terminal_reason",
]);

const COMPLETENESS_FIELDS = Object.freeze([
  "expected_count",
  "terminal_count",
  "missing_node_ids",
  "partial_allowed",
]);

const SCHEDULER_SNAPSHOT_FIELDS = Object.freeze([
  "run_id",
  "plan_hash",
  "budget_hash",
  "budget_enforcement",
  "budget_usage",
  "fencing_counter",
  "active_lease_ids",
  "active_leases",
  "idempotency_bindings",
  "resource_owners",
  "resource_fencing_heads",
  "node_fencing_heads",
  "node_attempts",
  "loop_states",
  "ready_node_ids",
  "state_hash",
]);

const REVIEW_PREIMAGE_FIELDS = Object.freeze([
  "review_version",
  "reviewer_role_id",
  "reviewer_actor_id",
  "reviewer_independence_group",
  "reviewer_terminal_receipt_id",
  "dispatch_plan_hash",
  "scheduler_state_hash",
  "scheduler_command_log_hash",
  "reviewed_terminal_receipt_ids",
  "reviewed_result_bindings",
  "verdict",
  "findings",
]);

const REVIEWED_RESULT_BINDING_FIELDS = Object.freeze([
  "role_id",
  "terminal_receipt_id",
  "output_artifact_ids",
  "output_hash",
]);

const REVIEW_FIELDS = Object.freeze([
  "review_id",
  ...REVIEW_PREIMAGE_FIELDS,
  "review_hash",
]);

export class FanInGateError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "FanInGateError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(canonicalClone(details));
  }
}

const fail = (code, message, details = undefined) => {
  throw new FanInGateError(code, message, details);
};

const compareUtf8 = (left, right) =>
  Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of REFLECT_OWN_KEYS(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};

const canonicalClone = (value) => JSON.parse(canonicalizeRoleSpecJson(value));

export const sha256FanInJson = (value) =>
  `sha256:${createHash("sha256")
    .update(canonicalizeRoleSpecJson(value), "utf8")
    .digest("hex")}`;

const requirePlainRecord = (value, label, fields = undefined) => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    (OBJECT_GET_PROTOTYPE_OF(value) !== Object.prototype &&
      OBJECT_GET_PROTOTYPE_OF(value) !== null)
  ) {
    fail("INVALID_INPUT", `${label} must be a non-proxy plain data object`);
  }
  const allowed = fields === undefined ? null : new Set(fields);
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (typeof key !== "string" || (allowed !== null && !allowed.has(key))) {
      fail("UNEXPECTED_FIELD", `${label} contains an unsupported field`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail("ACCESSOR_FIELD_DENIED", `${label}.${String(key)} must be data`);
    }
  }
  if (fields !== undefined) {
    for (const field of fields) {
      if (!OBJECT_HAS_OWN(value, field)) {
        fail("MISSING_FIELD", `${label}.${field} is required`);
      }
    }
  }
  return value;
};

const read = (record, key) => OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(record, key).value;

const requireDenseArray = (value, label) => {
  if (
    !ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== Array.prototype
  ) {
    fail("INVALID_INPUT", `${label} must be a non-proxy plain dense array`);
  }
  const result = new Array(value.length);
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
      fail("INVALID_INPUT", `${label} contains a non-element property`);
    }
  }
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail("INVALID_INPUT", `${label} contains a sparse or accessor element`);
    }
    result[index] = descriptor.value;
  }
  return result;
};

const requireString = (value, label) => {
  if (typeof value !== "string" || value.length === 0 || value.trim().length === 0) {
    fail("INVALID_INPUT", `${label} must be a non-blank string`);
  }
  return value;
};

const requireHash = (value, label, code = "INVALID_HASH") => {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) {
    fail(code, `${label} must be sha256:<64 lowercase hex>`);
  }
  return value;
};

const requireInteger = (value, label, minimum = 0, maximum = Number.MAX_SAFE_INTEGER) => {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    fail("INVALID_INPUT", `${label} must be an integer in [${minimum}, ${maximum}]`);
  }
  return value;
};

const requireBoolean = (value, label) => {
  if (typeof value !== "boolean") fail("INVALID_INPUT", `${label} must be boolean`);
  return value;
};

const requireStringArray = (
  value,
  label,
  { allowEmpty = true, canonical = false, sort = false } = {},
) => {
  const entries = requireDenseArray(value, label).map((entry, index) =>
    requireString(entry, `${label}[${index}]`),
  );
  if (!allowEmpty && entries.length === 0) {
    fail("INVALID_INPUT", `${label} must not be empty`);
  }
  if (new Set(entries).size !== entries.length) {
    fail("DUPLICATE_VALUE", `${label} must contain unique values`);
  }
  const sorted = [...entries].sort(compareUtf8);
  if (canonical && entries.some((entry, index) => entry !== sorted[index])) {
    fail("NON_CANONICAL_ORDER", `${label} must use ascending UTF-8 order`);
  }
  return sort ? sorted : entries;
};

const sameCanonical = (left, right) =>
  canonicalizeRoleSpecJson(left) === canonicalizeRoleSpecJson(right);

const sameStringSet = (left, right) => {
  const a = [...left].sort(compareUtf8);
  const b = [...right].sort(compareUtf8);
  return a.length === b.length && a.every((entry, index) => entry === b[index]);
};

const normalizeDispatchRole = (candidate, index) => {
  const record = requirePlainRecord(
    candidate,
    `RoleDispatchPlan.roles[${index}]`,
    ROLE_DISPATCH_PROJECTION_FIELDS,
  );
  return {
    role_id: requireString(read(record, "role_id"), `roles[${index}].role_id`),
    host_agent_type: requireString(
      read(record, "host_agent_type"),
      `roles[${index}].host_agent_type`,
    ),
    model_tier: requireString(read(record, "model_tier"), `roles[${index}].model_tier`),
    tool_acl: requireStringArray(read(record, "tool_acl"), `roles[${index}].tool_acl`),
    evidence_acl: requireStringArray(
      read(record, "evidence_acl"),
      `roles[${index}].evidence_acl`,
    ),
    read_scope: requireStringArray(read(record, "read_scope"), `roles[${index}].read_scope`),
    write_scope: requireStringArray(
      read(record, "write_scope"),
      `roles[${index}].write_scope`,
    ),
    depends_on: requireStringArray(read(record, "depends_on"), `roles[${index}].depends_on`),
    budget_tokens: requireInteger(
      read(record, "budget_tokens"),
      `roles[${index}].budget_tokens`,
    ),
    timeout_seconds: requireInteger(
      read(record, "timeout_seconds"),
      `roles[${index}].timeout_seconds`,
      1,
    ),
    independence_group: requireString(
      read(record, "independence_group"),
      `roles[${index}].independence_group`,
    ),
  };
};

const verifyDispatchPlan = (candidate) => {
  const record = requirePlainRecord(candidate, "RoleDispatchPlan", PLAN_FIELDS);
  const roles = requireDenseArray(read(record, "roles"), "RoleDispatchPlan.roles").map(
    normalizeDispatchRole,
  );
  if (roles.length === 0) fail("EMPTY_DISPATCH_PLAN", "RoleDispatchPlan must contain roles");
  const roleIds = roles.map((role) => role.role_id);
  if (new Set(roleIds).size !== roleIds.length) {
    fail("DUPLICATE_ROLE_ID", "RoleDispatchPlan role identities must be unique");
  }
  const expectedCount = requireInteger(
    read(record, "expected_count"),
    "RoleDispatchPlan.expected_count",
    1,
    16,
  );
  if (expectedCount !== roles.length) {
    fail("EXPECTED_COUNT_MISMATCH", "expected_count must equal the sealed role identity count", {
      expected_count: expectedCount,
      role_identity_count: roles.length,
    });
  }
  const known = new Set(roleIds);
  for (const role of roles) {
    if (role.depends_on.includes(role.role_id)) {
      fail("SELF_DEPENDENCY", "a dispatch role cannot depend on itself", { role_id: role.role_id });
    }
    const unknown = role.depends_on.filter((dependency) => !known.has(dependency));
    if (unknown.length > 0) {
      fail("UNKNOWN_ROLE_DEPENDENCY", "a dispatch role references an unknown dependency", {
        role_id: role.role_id,
        unknown,
      });
    }
  }
  const fanInPolicy = requireString(read(record, "fan_in_policy"), "fan_in_policy");
  const missingResultPolicy = requireString(
    read(record, "missing_result_policy"),
    "missing_result_policy",
  );
  if (fanInPolicy !== "all_required" || missingResultPolicy !== "fail_gate") {
    fail(
      "PARTIAL_FAN_IN_NOT_AUTHORIZED",
      "N04 acceptance requires all_required plus fail_gate; partial results remain non-PASS",
      { fan_in_policy: fanInPolicy, missing_result_policy: missingResultPolicy },
    );
  }
  const preimage = {
    plan_id: requireString(read(record, "plan_id"), "plan_id"),
    session_id: requireString(read(record, "session_id"), "session_id"),
    roles,
    expected_count: expectedCount,
    fan_in_policy: fanInPolicy,
    missing_result_policy: missingResultPolicy,
    max_concurrency: requireInteger(read(record, "max_concurrency"), "max_concurrency", 1, 16),
    budget_envelope_id: requireString(
      read(record, "budget_envelope_id"),
      "budget_envelope_id",
    ),
  };
  const observedHash = requireHash(read(record, "plan_hash"), "plan_hash");
  const expectedHash = sha256FanInJson(preimage);
  if (observedHash !== expectedHash) {
    fail("DISPATCH_PLAN_HASH_MISMATCH", "RoleDispatchPlan hash does not bind its contents", {
      expected: expectedHash,
      observed: observedHash,
    });
  }
  return { ...preimage, plan_hash: observedHash };
};

const verifyDescriptors = (candidate, plan) => {
  const entries = requireDenseArray(candidate, "spawnDescriptors");
  const expectedRoles = new Map(plan.roles.map((role) => [role.role_id, role]));
  const byRole = new Map();
  const descriptorIds = new Set();
  for (let index = 0; index < entries.length; index += 1) {
    let descriptor;
    try {
      descriptor = verifySpawnDescriptorIntegrity(entries[index]);
    } catch (error) {
      fail("SPAWN_DESCRIPTOR_INVALID", "N02 spawn descriptor integrity failed", {
        index,
        cause_code: error?.code ?? error?.name ?? "UNKNOWN",
      });
    }
    const roleId = descriptor.role_spec_id === descriptor.canonical_role_spec.role_spec_id
      ? descriptor.canonical_role_spec.role_id
      : null;
    if (roleId === null) {
      fail("SPAWN_DESCRIPTOR_INVALID", "descriptor RoleSpec identity is inconsistent", { index });
    }
    if (!expectedRoles.has(roleId)) {
      fail("UNEXPECTED_SPAWN_DESCRIPTOR", "descriptor role is not in RoleDispatchPlan", {
        role_id: roleId,
      });
    }
    if (byRole.has(roleId)) {
      fail("DUPLICATE_SPAWN_DESCRIPTOR", "a role has more than one spawn descriptor", {
        role_id: roleId,
      });
    }
    if (descriptorIds.has(descriptor.spawn_descriptor_id)) {
      fail("DUPLICATE_SPAWN_DESCRIPTOR", "spawn descriptor identity is duplicated", {
        spawn_descriptor_id: descriptor.spawn_descriptor_id,
      });
    }
    if (descriptor.execution_binding.node_id !== roleId) {
      fail("DESCRIPTOR_NODE_MISMATCH", "descriptor node identity must equal its role identity", {
        role_id: roleId,
        node_id: descriptor.execution_binding.node_id,
      });
    }
    if (
      descriptor.result_contract.expected_count !== 1 ||
      descriptor.result_contract.prose_completion_is_authority !== false
    ) {
      fail(
        "DESCRIPTOR_RESULT_CONTRACT_MISMATCH",
        "N04 requires one receipt-bound ResultEnvelope per sealed role identity",
        { role_id: roleId },
      );
    }
    const projection = projectRoleSpecToDispatchRole(descriptor.canonical_role_spec);
    if (!sameCanonical(projection, expectedRoles.get(roleId))) {
      fail("ROLE_DESCRIPTOR_MISMATCH", "descriptor RoleSpec differs from dispatch projection", {
        role_id: roleId,
      });
    }
    descriptorIds.add(descriptor.spawn_descriptor_id);
    byRole.set(roleId, descriptor);
  }
  const missing = [...expectedRoles.keys()].filter((roleId) => !byRole.has(roleId)).sort(compareUtf8);
  if (missing.length > 0 || byRole.size !== plan.expected_count) {
    fail("MISSING_SPAWN_DESCRIPTOR", "not every expected role has one descriptor", { missing });
  }
  return byRole;
};

const verifySchedulerExecution = ({
  candidate,
  schedulerPlan,
  schedulerBudgetEnvelope,
  schedulerCommands,
  dispatchPlan,
  descriptors,
  expectedRoleIds,
}) => {
  const record = requirePlainRecord(
    candidate,
    "schedulerSnapshot",
    SCHEDULER_SNAPSHOT_FIELDS,
  );
  const semantic = {};
  for (const field of SCHEDULER_SNAPSHOT_FIELDS) {
    if (field !== "state_hash") semantic[field] = read(record, field);
  }
  const observedHash = requireHash(read(record, "state_hash"), "schedulerSnapshot.state_hash");
  let expectedHash;
  try {
    expectedHash = sha256SchedulerJson(semantic);
  } catch (error) {
    fail("SCHEDULER_SNAPSHOT_INVALID", "N03 scheduler snapshot is not canonical", {
      cause_code: error?.code ?? error?.name ?? "UNKNOWN",
    });
  }
  if (observedHash !== expectedHash) {
    fail("SCHEDULER_SNAPSHOT_HASH_MISMATCH", "scheduler state hash does not bind snapshot", {
      expected: expectedHash,
      observed: observedHash,
    });
  }
  const runId = requireString(read(record, "run_id"), "schedulerSnapshot.run_id");

  let verifiedPlan;
  try {
    verifiedPlan = assertSchedulerPlanIntegrity(schedulerPlan);
  } catch (error) {
    fail("SCHEDULER_PLAN_INVALID", "N03 SchedulerPlan integrity validation failed", {
      cause_code: error?.code ?? error?.name ?? "UNKNOWN",
    });
  }
  if (read(record, "plan_hash") !== verifiedPlan.plan_hash) {
    fail(
      "SCHEDULER_PLAN_BINDING_MISMATCH",
      "scheduler snapshot does not bind the supplied canonical SchedulerPlan",
      { expected: verifiedPlan.plan_hash, observed: read(record, "plan_hash") },
    );
  }
  const schedulerNodeIds = verifiedPlan.nodes.map((node) => node.node_id);
  if (!sameStringSet(schedulerNodeIds, expectedRoleIds)) {
    fail(
      "SCHEDULER_PLAN_NODE_SET_MISMATCH",
      "SchedulerPlan node identities do not match RoleDispatchPlan roles",
      {
        expected: [...expectedRoleIds].sort(compareUtf8),
        actual: [...schedulerNodeIds].sort(compareUtf8),
      },
    );
  }
  if (verifiedPlan.loop_contracts.length !== 0) {
    fail(
      "SCHEDULER_LOOP_NOT_AUTHORIZED",
      "RoleDispatchPlan has no loop authority; N04 fan-in requires an acyclic SchedulerPlan",
    );
  }
  const dispatchRoles = new Map(dispatchPlan.roles.map((role) => [role.role_id, role]));
  const schedulerNodes = new Map(verifiedPlan.nodes.map((node) => [node.node_id, node]));
  for (const roleId of expectedRoleIds) {
    const role = dispatchRoles.get(roleId);
    const node = schedulerNodes.get(roleId);
    const descriptor = descriptors.get(roleId);
    const nodeContractHash = sha256SchedulerJson(node);
    if (descriptor.execution_binding.node_contract_hash !== nodeContractHash) {
      fail(
        "DESCRIPTOR_NODE_CONTRACT_MISMATCH",
        "spawn descriptor does not bind the exact N03 SchedulerPlan NodeContract",
        {
          role_id: roleId,
          expected: nodeContractHash,
          observed: descriptor.execution_binding.node_contract_hash,
        },
      );
    }
    if (
      node.node_id !== role.role_id ||
      !sameStringSet(node.depends_on, role.depends_on) ||
      !sameStringSet(node.read_scope, role.read_scope) ||
      !sameStringSet(node.write_scope, role.write_scope) ||
      !sameStringSet(node.capabilities, role.tool_acl) ||
      node.model_tier !== role.model_tier ||
      node.timeout_seconds !== role.timeout_seconds ||
      node.output_schema_ref !== descriptor.result_contract.business_output_schema_ref
    ) {
      fail(
        "DISPATCH_SCHEDULER_CONTRACT_MISMATCH",
        "RoleDispatchPlan authority differs from its executable N03 NodeContract",
        { role_id: roleId },
      );
    }
  }

  const verifiedBudget = JSON.parse(canonicalizeSchedulerJson(schedulerBudgetEnvelope));
  if (
    verifiedBudget.budget_id !== dispatchPlan.budget_envelope_id ||
    verifiedBudget.budget_hash !== read(record, "budget_hash") ||
    verifiedBudget.enforcement !== read(record, "budget_enforcement")
  ) {
    fail(
      "SCHEDULER_BUDGET_BINDING_MISMATCH",
      "RoleDispatchPlan, BudgetEnvelope, and scheduler snapshot budget bindings differ",
    );
  }
  const activeLeaseIds = requireStringArray(read(record, "active_lease_ids"), "active_lease_ids");
  const activeLeases = requireDenseArray(read(record, "active_leases"), "active_leases");
  if (activeLeaseIds.length > 0 || activeLeases.length > 0) {
    fail("SCHEDULER_NOT_TERMINAL", "fan-in cannot pass while scheduler leases remain active");
  }
  const attemptsRecord = requirePlainRecord(read(record, "node_attempts"), "node_attempts");
  const actualRoleIds = REFLECT_OWN_KEYS(attemptsRecord).filter((key) => typeof key === "string");
  if (!sameStringSet(actualRoleIds, expectedRoleIds)) {
    fail("SCHEDULER_NODE_SET_MISMATCH", "scheduler node identities do not match dispatch roles", {
      expected: [...expectedRoleIds].sort(compareUtf8),
      actual: actualRoleIds.sort(compareUtf8),
    });
  }
  const terminals = new Map();
  const receiptIds = new Set();
  for (const roleId of expectedRoleIds) {
    const attempts = requireDenseArray(read(attemptsRecord, roleId), `node_attempts.${roleId}`);
    if (attempts.length === 0) {
      fail("MISSING_NODE_ATTEMPT", "expected scheduler node has no attempt", { role_id: roleId });
    }
    for (let index = 0; index < attempts.length; index += 1) {
      const attempt = requirePlainRecord(
        attempts[index],
        `node_attempts.${roleId}[${index}]`,
      );
      if (
        read(attempt, "run_id") !== runId ||
        read(attempt, "node_id") !== roleId ||
        read(attempt, "attempt") !== index + 1
      ) {
        fail(
          "ATTEMPT_IDENTITY_MISMATCH",
          "every scheduler attempt must bind its snapshot run, node, and contiguous identity",
          { role_id: roleId, index },
        );
      }
      if (index < attempts.length - 1 && read(attempt, "status") !== "FAILED_RETRYABLE") {
        fail(
          "ATTEMPT_HISTORY_INVALID",
          "only a terminal retryable failure may precede another scheduler attempt",
          { role_id: roleId, attempt: index + 1, status: read(attempt, "status") },
        );
      }
    }
    const last = requirePlainRecord(attempts.at(-1), `node_attempts.${roleId}.last`);
    const attemptNumber = requireInteger(read(last, "attempt"), `${roleId}.attempt`, 1, 10);
    if (attemptNumber !== attempts.length) {
      fail("ATTEMPT_SEQUENCE_MISMATCH", "scheduler attempts are not contiguous", {
        role_id: roleId,
        attempt: attemptNumber,
        count: attempts.length,
      });
    }
    if (read(last, "node_id") !== roleId || read(last, "status") !== "SUCCEEDED") {
      fail("NODE_NOT_SUCCESSFUL", "every expected scheduler node must end in SUCCEEDED", {
        role_id: roleId,
        status: read(last, "status"),
      });
    }
    const terminalReceiptId = requireString(
      read(last, "terminal_receipt_id"),
      `${roleId}.terminal_receipt_id`,
    );
    if (receiptIds.has(terminalReceiptId)) {
      fail("DUPLICATE_TERMINAL_RECEIPT", "terminal receipt identity is duplicated", {
        terminal_receipt_id: terminalReceiptId,
      });
    }
    receiptIds.add(terminalReceiptId);
    terminals.set(roleId, {
      attempt: attemptNumber,
      owner_id: requireString(read(last, "owner_id"), `${roleId}.owner_id`),
      input_hash: requireHash(read(last, "input_hash"), `${roleId}.input_hash`),
      started_at: requireString(read(last, "started_at"), `${roleId}.started_at`),
      finished_at: requireString(read(last, "finished_at"), `${roleId}.finished_at`),
      terminal_receipt_id: terminalReceiptId,
      effect_receipt_ids: requireStringArray(
        read(last, "effect_receipt_ids"),
        `${roleId}.effect_receipt_ids`,
        { sort: true },
      ),
    });
  }
  let replay;
  try {
    replay = replaySchedulerCommands({
      run_id: runId,
      plan: verifiedPlan,
      budget_envelope: schedulerBudgetEnvelope,
      commands: schedulerCommands,
    });
  } catch (error) {
    fail("SCHEDULER_REPLAY_INVALID", "N03 scheduler command replay failed", {
      cause_code: error?.code ?? error?.name ?? "UNKNOWN",
    });
  }
  if (canonicalizeSchedulerJson(replay.snapshot) !== canonicalizeSchedulerJson(record)) {
    fail(
      "SCHEDULER_REPLAY_MISMATCH",
      "scheduler snapshot is not the exact result of its N03 command log",
      {
        expected_state_hash: replay.snapshot.state_hash,
        observed_state_hash: observedHash,
      },
    );
  }
  const schedulerCommandLogHash = sha256SchedulerJson(replay.commands);
  return {
    run_id: runId,
    plan_hash: verifiedPlan.plan_hash,
    budget_hash: verifiedBudget.budget_hash,
    command_log_hash: schedulerCommandLogHash,
    state_hash: observedHash,
    terminals,
  };
};

const normalizeResultEnvelope = (candidate, roleId, terminal, runId) => {
  const record = requirePlainRecord(
    candidate,
    `ResultEnvelope(${roleId})`,
    RESULT_ENVELOPE_FIELDS,
  );
  const completeness = requirePlainRecord(
    read(record, "completeness"),
    `ResultEnvelope(${roleId}).completeness`,
    COMPLETENESS_FIELDS,
  );
  const outputArtifactIds = requireStringArray(
    read(record, "output_artifact_ids"),
    `${roleId}.output_artifact_ids`,
    { allowEmpty: false, sort: true },
  );
  const errors = requireStringArray(read(record, "errors"), `${roleId}.errors`);
  const missingNodeIds = requireStringArray(
    read(completeness, "missing_node_ids"),
    `${roleId}.missing_node_ids`,
  );
  const effectReceiptIds = requireStringArray(
    read(record, "effect_receipt_ids"),
    `${roleId}.effect_receipt_ids`,
    { sort: true },
  );
  requirePlainRecord(read(record, "metrics"), `${roleId}.metrics`);
  if (
    read(record, "run_id") !== runId ||
    read(record, "node_id") !== roleId ||
    read(record, "attempt") !== terminal.attempt ||
    read(record, "status") !== "success" ||
    read(record, "input_hash") !== terminal.input_hash ||
    read(record, "started_at") !== terminal.started_at ||
    read(record, "finished_at") !== terminal.finished_at ||
    !sameStringSet(effectReceiptIds, terminal.effect_receipt_ids)
  ) {
    fail("RESULT_SCHEDULER_BINDING_MISMATCH", "ResultEnvelope differs from N03 terminal attempt", {
      role_id: roleId,
    });
  }
  if (
    errors.length !== 0 ||
    read(completeness, "expected_count") !== 1 ||
    read(completeness, "terminal_count") !== 1 ||
    missingNodeIds.length !== 0 ||
    requireBoolean(read(completeness, "partial_allowed"), `${roleId}.partial_allowed`) !== false
  ) {
    fail("RESULT_COMPLETENESS_MISMATCH", "ResultEnvelope does not prove complete one-of-one execution", {
      role_id: roleId,
    });
  }
  return {
    output_artifact_ids: outputArtifactIds,
    output_hash: requireHash(read(record, "output_hash"), `${roleId}.output_hash`),
  };
};

const verifySubmissions = (candidate, plan, descriptors, scheduler) => {
  const entries = requireDenseArray(candidate, "resultSubmissions");
  const expectedRoles = new Set(plan.roles.map((role) => role.role_id));
  const byRole = new Map();
  const outputArtifactIds = new Set();
  for (let index = 0; index < entries.length; index += 1) {
    const submission = requirePlainRecord(
      entries[index],
      `resultSubmissions[${index}]`,
      SUBMISSION_FIELDS,
    );
    const roleId = requireString(read(submission, "role_id"), `resultSubmissions[${index}].role_id`);
    if (!expectedRoles.has(roleId)) {
      fail("UNEXPECTED_RESULT_IDENTITY", "result role is not in RoleDispatchPlan", { role_id: roleId });
    }
    if (byRole.has(roleId)) {
      fail("DUPLICATE_RESULT_IDENTITY", "a role has more than one result", { role_id: roleId });
    }
    const descriptor = descriptors.get(roleId);
    if (read(submission, "spawn_descriptor_id") !== descriptor.spawn_descriptor_id) {
      fail("RESULT_DESCRIPTOR_MISMATCH", "result does not bind the role spawn descriptor", {
        role_id: roleId,
      });
    }
    const terminal = scheduler.terminals.get(roleId);
    if (read(submission, "terminal_receipt_id") !== terminal.terminal_receipt_id) {
      fail("TERMINAL_RECEIPT_MISMATCH", "result does not bind the N03 terminal receipt", {
        role_id: roleId,
      });
    }
    const envelope = normalizeResultEnvelope(
      read(submission, "result_envelope"),
      roleId,
      terminal,
      scheduler.run_id,
    );
    for (const artifactId of envelope.output_artifact_ids) {
      if (outputArtifactIds.has(artifactId)) {
        fail("DUPLICATE_OUTPUT_ARTIFACT", "two results claim the same business artifact", {
          artifact_id: artifactId,
        });
      }
      outputArtifactIds.add(artifactId);
    }
    byRole.set(roleId, { terminal_receipt_id: terminal.terminal_receipt_id, ...envelope });
  }
  const missing = [...expectedRoles].filter((roleId) => !byRole.has(roleId)).sort(compareUtf8);
  if (missing.length > 0 || byRole.size !== plan.expected_count) {
    fail("MISSING_RESULT_IDENTITY", "not every expected role produced one result", { missing });
  }
  return byRole;
};

const normalizeReviewedResultBindings = (candidate, { canonical = false } = {}) => {
  const entries = requireDenseArray(candidate, "reviewed_result_bindings").map(
    (entry, index) => {
      const record = requirePlainRecord(
        entry,
        `reviewed_result_bindings[${index}]`,
        REVIEWED_RESULT_BINDING_FIELDS,
      );
      return {
        role_id: requireString(read(record, "role_id"), `reviewed_result_bindings[${index}].role_id`),
        terminal_receipt_id: requireString(
          read(record, "terminal_receipt_id"),
          `reviewed_result_bindings[${index}].terminal_receipt_id`,
        ),
        output_artifact_ids: requireStringArray(
          read(record, "output_artifact_ids"),
          `reviewed_result_bindings[${index}].output_artifact_ids`,
          { allowEmpty: false, canonical, sort: true },
        ),
        output_hash: requireHash(
          read(record, "output_hash"),
          `reviewed_result_bindings[${index}].output_hash`,
        ),
      };
    },
  );
  const roleIds = entries.map((entry) => entry.role_id);
  if (new Set(roleIds).size !== roleIds.length) {
    fail("DUPLICATE_REVIEW_RESULT", "reviewed result role identities must be unique");
  }
  const sorted = [...entries].sort((left, right) => compareUtf8(left.role_id, right.role_id));
  if (canonical && entries.some((entry, index) => entry.role_id !== sorted[index].role_id)) {
    fail(
      "NON_CANONICAL_ORDER",
      "reviewed_result_bindings must use ascending role identity order",
    );
  }
  return sorted;
};

const normalizeReviewPreimage = (candidate, { canonical = false } = {}) => {
  const record = requirePlainRecord(candidate, "IndependentReview preimage", REVIEW_PREIMAGE_FIELDS);
  const version = requireString(read(record, "review_version"), "review_version");
  if (version !== INDEPENDENT_REVIEW_VERSION) {
    fail("REVIEW_VERSION_UNSUPPORTED", `review_version must be ${INDEPENDENT_REVIEW_VERSION}`);
  }
  return {
    review_version: version,
    reviewer_role_id: requireString(read(record, "reviewer_role_id"), "reviewer_role_id"),
    reviewer_actor_id: requireString(read(record, "reviewer_actor_id"), "reviewer_actor_id"),
    reviewer_independence_group: requireString(
      read(record, "reviewer_independence_group"),
      "reviewer_independence_group",
    ),
    reviewer_terminal_receipt_id: requireString(
      read(record, "reviewer_terminal_receipt_id"),
      "reviewer_terminal_receipt_id",
    ),
    dispatch_plan_hash: requireHash(read(record, "dispatch_plan_hash"), "dispatch_plan_hash"),
    scheduler_state_hash: requireHash(
      read(record, "scheduler_state_hash"),
      "scheduler_state_hash",
    ),
    scheduler_command_log_hash: requireHash(
      read(record, "scheduler_command_log_hash"),
      "scheduler_command_log_hash",
    ),
    reviewed_terminal_receipt_ids: requireStringArray(
      read(record, "reviewed_terminal_receipt_ids"),
      "reviewed_terminal_receipt_ids",
      { allowEmpty: false, canonical, sort: true },
    ),
    reviewed_result_bindings: normalizeReviewedResultBindings(
      read(record, "reviewed_result_bindings"),
      { canonical },
    ),
    verdict: requireString(read(record, "verdict"), "verdict"),
    findings: requireStringArray(read(record, "findings"), "findings", {
      canonical,
      sort: true,
    }),
  };
};

export const sealIndependentReview = (candidate) => {
  const preimage = normalizeReviewPreimage(candidate);
  const reviewHash = sha256FanInJson(preimage);
  return deepFreeze({
    review_id: `REVIEW-${reviewHash.slice("sha256:".length)}`,
    ...canonicalClone(preimage),
    review_hash: reviewHash,
  });
};

const verifyIndependentReview = (candidate) => {
  if (candidate === null || candidate === undefined) {
    fail("INDEPENDENT_REVIEW_MISSING", "N04 cannot pass without an independent review artifact");
  }
  const record = requirePlainRecord(candidate, "IndependentReview", REVIEW_FIELDS);
  const preimageCandidate = {};
  for (const field of REVIEW_PREIMAGE_FIELDS) preimageCandidate[field] = read(record, field);
  const preimage = normalizeReviewPreimage(preimageCandidate, { canonical: true });
  const observedHash = requireHash(read(record, "review_hash"), "review_hash");
  const expectedHash = sha256FanInJson(preimage);
  if (observedHash !== expectedHash) {
    fail("REVIEW_HASH_MISMATCH", "review hash does not bind the review scope and verdict", {
      expected: expectedHash,
      observed: observedHash,
    });
  }
  const observedId = requireString(read(record, "review_id"), "review_id");
  const expectedId = `REVIEW-${expectedHash.slice("sha256:".length)}`;
  if (observedId !== expectedId) {
    fail("REVIEW_ID_MISMATCH", "review ID must derive from review hash", {
      expected: expectedId,
      observed: observedId,
    });
  }
  return { review_id: observedId, ...preimage, review_hash: observedHash };
};

export const evaluateFanInGate = ({
  dispatchPlan,
  spawnDescriptors,
  schedulerPlan,
  schedulerBudgetEnvelope,
  schedulerCommands,
  schedulerSnapshot,
  resultSubmissions,
  independentReview,
}) => {
  const plan = verifyDispatchPlan(dispatchPlan);
  const expectedRoleIds = plan.roles.map((role) => role.role_id).sort(compareUtf8);
  const descriptors = verifyDescriptors(spawnDescriptors, plan);
  const scheduler = verifySchedulerExecution({
    candidate: schedulerSnapshot,
    schedulerPlan,
    schedulerBudgetEnvelope,
    schedulerCommands,
    dispatchPlan: plan,
    descriptors,
    expectedRoleIds,
  });
  const submissions = verifySubmissions(
    resultSubmissions,
    plan,
    descriptors,
    scheduler,
  );
  const review = verifyIndependentReview(independentReview);
  const roleById = new Map(plan.roles.map((role) => [role.role_id, role]));
  const reviewerRole = roleById.get(review.reviewer_role_id);
  if (reviewerRole === undefined) {
    fail("UNKNOWN_REVIEWER_ROLE", "reviewer role is not in RoleDispatchPlan", {
      reviewer_role_id: review.reviewer_role_id,
    });
  }
  const makerRoleIds = expectedRoleIds.filter((roleId) => roleId !== review.reviewer_role_id);
  if (makerRoleIds.length === 0) {
    fail("MAKER_ROLE_MISSING", "independent review requires at least one maker role");
  }
  const reviewerTerminal = scheduler.terminals.get(review.reviewer_role_id);
  if (review.reviewer_actor_id !== reviewerTerminal.owner_id) {
    fail("REVIEWER_ACTOR_MISMATCH", "review actor differs from the scheduler owner", {
      reviewer_role_id: review.reviewer_role_id,
    });
  }
  if (review.reviewer_terminal_receipt_id !== reviewerTerminal.terminal_receipt_id) {
    fail("REVIEWER_RECEIPT_MISMATCH", "review artifact does not bind reviewer terminal receipt");
  }
  if (
    review.dispatch_plan_hash !== plan.plan_hash ||
    review.scheduler_state_hash !== scheduler.state_hash ||
    review.scheduler_command_log_hash !== scheduler.command_log_hash
  ) {
    fail(
      "REVIEW_EXECUTION_BINDING_MISMATCH",
      "independent review must bind the exact dispatch plan, scheduler state, and command log",
    );
  }
  const makerActorIds = new Set(
    makerRoleIds.map((roleId) => scheduler.terminals.get(roleId).owner_id),
  );
  if (makerActorIds.has(review.reviewer_actor_id)) {
    fail("REVIEWER_SELF_APPROVAL", "a maker actor cannot approve its own fan-in");
  }
  if (review.reviewer_independence_group !== reviewerRole.independence_group) {
    fail("REVIEWER_GROUP_MISMATCH", "review artifact group differs from reviewer RoleSpec");
  }
  const makerGroups = new Set(
    makerRoleIds.map((roleId) => roleById.get(roleId).independence_group),
  );
  if (makerGroups.has(review.reviewer_independence_group)) {
    fail(
      "REVIEWER_NOT_INDEPENDENT",
      "reviewer shares an independence group with a maker role",
      { independence_group: review.reviewer_independence_group },
    );
  }
  const makerReceiptIds = makerRoleIds
    .map((roleId) => scheduler.terminals.get(roleId).terminal_receipt_id)
    .sort(compareUtf8);
  if (!sameStringSet(review.reviewed_terminal_receipt_ids, makerReceiptIds)) {
    fail("REVIEW_SCOPE_MISMATCH", "review must cover every and only maker terminal receipt", {
      expected: makerReceiptIds,
      observed: review.reviewed_terminal_receipt_ids,
    });
  }
  if (!sameStringSet(reviewerRole.depends_on, makerRoleIds)) {
    fail(
      "REVIEWER_DEPENDENCY_MISMATCH",
      "independent reviewer must execute after every and only maker role",
      { expected: makerRoleIds, observed: reviewerRole.depends_on },
    );
  }
  const makerResultBindings = makerRoleIds
    .map((roleId) => ({
      role_id: roleId,
      terminal_receipt_id: submissions.get(roleId).terminal_receipt_id,
      output_artifact_ids: submissions.get(roleId).output_artifact_ids,
      output_hash: submissions.get(roleId).output_hash,
    }))
    .sort((left, right) => compareUtf8(left.role_id, right.role_id));
  if (!sameCanonical(review.reviewed_result_bindings, makerResultBindings)) {
    fail(
      "REVIEW_RESULT_SCOPE_MISMATCH",
      "independent review must bind every and only maker output and output hash",
      { expected: makerResultBindings, observed: review.reviewed_result_bindings },
    );
  }
  if (review.verdict !== "PASS") {
    fail("INDEPENDENT_REVIEW_NOT_PASS", "independent review verdict must be PASS", {
      verdict: review.verdict,
    });
  }
  const reviewerResult = submissions.get(review.reviewer_role_id);
  if (!reviewerResult.output_artifact_ids.includes(review.review_id)) {
    fail(
      "REVIEW_ARTIFACT_BINDING_MISSING",
      "reviewer ResultEnvelope must emit the exact independent review artifact",
    );
  }

  const descriptorBindings = expectedRoleIds.map((roleId) => ({
    role_id: roleId,
    spawn_descriptor_id: descriptors.get(roleId).spawn_descriptor_id,
    spawn_descriptor_hash: descriptors.get(roleId).spawn_descriptor_hash,
  }));
  const resultBindings = expectedRoleIds.map((roleId) => ({
    role_id: roleId,
    terminal_receipt_id: submissions.get(roleId).terminal_receipt_id,
    output_hash: submissions.get(roleId).output_hash,
  }));
  const preimage = {
    gate_version: FAN_IN_GATE_VERSION,
    status: "PASS",
    plan_id: plan.plan_id,
    plan_hash: plan.plan_hash,
    scheduler_run_id: scheduler.run_id,
    scheduler_plan_hash: scheduler.plan_hash,
    scheduler_budget_hash: scheduler.budget_hash,
    scheduler_command_log_hash: scheduler.command_log_hash,
    scheduler_state_hash: scheduler.state_hash,
    expected_count: plan.expected_count,
    expected_role_ids: expectedRoleIds,
    completed_role_ids: expectedRoleIds,
    descriptor_bindings: descriptorBindings,
    result_bindings: resultBindings,
    maker_terminal_receipt_ids: makerReceiptIds,
    review_id: review.review_id,
    review_hash: review.review_hash,
    reviewer_role_id: review.reviewer_role_id,
    reviewer_actor_id: review.reviewer_actor_id,
    reviewer_independence_group: review.reviewer_independence_group,
  };
  const decisionHash = sha256FanInJson(preimage);
  return deepFreeze({
    decision_id: `FANIN-${decisionHash.slice("sha256:".length)}`,
    ...canonicalClone(preimage),
    decision_hash: decisionHash,
  });
};
