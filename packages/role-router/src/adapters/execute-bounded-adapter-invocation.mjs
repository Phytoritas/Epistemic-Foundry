import { isDeepStrictEqual, types as utilTypes } from "node:util";

import { verifySpawnDescriptorIntegrity } from "./adapter-contract.mjs";
import {
  AdapterExecutionError,
  failAdapterExecution,
  wrapAdapterExecutionError,
} from "./adapter-execution-errors.mjs";
import {
  LOCAL_SCRIPTED_ACTION_TYPE,
  LOCAL_SCRIPTED_ADAPTER_KIND,
  LOCAL_SCRIPTED_TERMINAL_REASON,
  verifyLocalScriptedAdapter,
} from "./local-scripted-adapter.mjs";

export const BOUNDED_ADAPTER_EXECUTOR_VERSION = "4.0.0-n02.bounded.3";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const RFC3339_PATTERN =
  /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$/u;
const MAX_PLAIN_DATA_DEPTH = 64;
const MAX_PLAIN_DATA_NODES = 10_000;
const MAX_PLAIN_DATA_UTF8_BYTES = 1024 * 1024;
const DENIED_OBJECT_KEYS = new Set(["__proto__", "constructor", "prototype"]);

const boundedUnicodeScalarLength = (value, maxLength) => {
  if (typeof value !== "string") return -1;
  let length = 0;
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return -1;
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      return -1;
    }
    length += 1;
    if (length > maxLength) return length;
  }
  return length;
};

const EXECUTION_REQUEST_FIELDS = Object.freeze([
  "actionIntent",
  "adapter",
  "attemptId",
  "effectReceiptId",
  "nodeInvocation",
  "spawnDescriptor",
]);

const EXECUTOR_DEPENDENCY_FIELDS = Object.freeze([
  "artifactWriter",
  "cancellation",
  "clock",
  "contractValidator",
  "effectCoordinator",
  "effectSealer",
  "executionAuthority",
  "replayResolver",
]);

const requirePlainRecord = (
  candidate,
  label,
  allowedFields = undefined,
  requiredFields = allowedFields,
) => {
  if (
    candidate === null ||
    typeof candidate !== "object" ||
    ARRAY_IS_ARRAY(candidate) ||
    IS_PROXY(candidate) ||
    (OBJECT_GET_PROTOTYPE_OF(candidate) !== Object.prototype &&
      OBJECT_GET_PROTOTYPE_OF(candidate) !== null)
  ) {
    failAdapterExecution(
      "ADAPTER_EXECUTION_INPUT_INVALID",
      label + " must be a non-proxy plain data object",
    );
  }
  const allowed = allowedFields === undefined ? null : new Set(allowedFields);
  for (const key of REFLECT_OWN_KEYS(candidate)) {
    if (typeof key !== "string" || (allowed !== null && !allowed.has(key))) {
      failAdapterExecution(
        "ADAPTER_EXECUTION_INPUT_INVALID",
        label + " contains an unsupported field",
      );
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(candidate, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      failAdapterExecution(
        "ADAPTER_EXECUTION_INPUT_INVALID",
        label + "." + String(key) + " must be an enumerable data property",
      );
    }
  }
  if (requiredFields !== undefined) {
    for (const field of requiredFields) {
      if (!OBJECT_HAS_OWN(candidate, field)) {
        failAdapterExecution(
          "ADAPTER_EXECUTION_INPUT_INVALID",
          label + "." + field + " is required",
        );
      }
    }
  }
  return candidate;
};

const readDataProperty = (record, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(record, key).value;

const requireText = (value, label, { maxLength = 4_096 } = {}) => {
  const length = boundedUnicodeScalarLength(value, maxLength);
  if (
    typeof value !== "string" ||
    length < 1 ||
    length > maxLength ||
    value.trim().length === 0
  ) {
    failAdapterExecution(
      "ADAPTER_EXECUTION_INPUT_INVALID",
      label + " must be a bounded non-blank string",
    );
  }
  return value;
};

const requireHash = (value, label) => {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) {
    failAdapterExecution(
      "ADAPTER_EXECUTION_INPUT_INVALID",
      label + " must be a canonical SHA-256 digest",
    );
  }
  return value;
};

const requireTimestamp = (value, label) => {
  if (
    typeof value !== "string" ||
    !RFC3339_PATTERN.test(value) ||
    Number.isNaN(Date.parse(value))
  ) {
    failAdapterExecution(
      "ADAPTER_EXECUTION_PORT_INVALID",
      label + " must be an RFC 3339 date-time",
    );
  }
  return value;
};

const compareTimestamps = (left, right) => {
  const leftMatch = RFC3339_PATTERN.exec(left);
  const rightMatch = RFC3339_PATTERN.exec(right);
  const leftWholeSecond = Date.parse(leftMatch[1] + leftMatch[3]);
  const rightWholeSecond = Date.parse(rightMatch[1] + rightMatch[3]);
  if (leftWholeSecond !== rightWholeSecond) {
    return leftWholeSecond < rightWholeSecond ? -1 : 1;
  }

  const leftFraction = leftMatch[2] ?? "";
  const rightFraction = rightMatch[2] ?? "";
  const precision = Math.max(leftFraction.length, rightFraction.length);
  const normalizedLeft = leftFraction.padEnd(precision, "0");
  const normalizedRight = rightFraction.padEnd(precision, "0");
  if (normalizedLeft === normalizedRight) return 0;
  return normalizedLeft < normalizedRight ? -1 : 1;
};

const requireStringArray = (candidate, label) => {
  if (
    !ARRAY_IS_ARRAY(candidate) ||
    IS_PROXY(candidate) ||
    OBJECT_GET_PROTOTYPE_OF(candidate) !== Array.prototype
  ) {
    failAdapterExecution(
      "ADAPTER_EXECUTION_INPUT_INVALID",
      label + " must be a non-proxy plain dense array",
    );
  }
  const output = new Array(candidate.length);
  for (const key of REFLECT_OWN_KEYS(candidate)) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
      failAdapterExecution(
        "ADAPTER_EXECUTION_INPUT_INVALID",
        label + " contains a non-element property",
      );
    }
  }
  for (let index = 0; index < candidate.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(
      candidate,
      String(index),
    );
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      failAdapterExecution(
        "ADAPTER_EXECUTION_INPUT_INVALID",
        label + " contains a sparse or accessor-backed element",
      );
    }
    output[index] = requireText(
      descriptor.value,
      label + "[" + index + "]",
      { maxLength: 1_024 },
    );
  }
  if (new Set(output).size !== output.length) {
    failAdapterExecution(
      "ADAPTER_EXECUTION_INPUT_INVALID",
      label + " must contain unique values",
    );
  }
  return output;
};

const requireCallable = (candidate, label) => {
  if (typeof candidate !== "function") {
    failAdapterExecution(
      "ADAPTER_EXECUTION_PORT_INVALID",
      label + " must be a function",
    );
  }
  return candidate;
};

const bindMethod = (candidate, method, label) => {
  if (
    candidate === null ||
    (typeof candidate !== "object" && typeof candidate !== "function") ||
    typeof candidate[method] !== "function"
  ) {
    failAdapterExecution(
      "ADAPTER_EXECUTION_PORT_INVALID",
      label + "." + method + " must be callable",
    );
  }
  return candidate[method].bind(candidate);
};

const sortUtf8Keys = (keys) => {
  const encoded = new Map(
    keys.map((key) => [key, Buffer.from(key, "utf8")]),
  );
  return keys.sort((left, right) =>
    Buffer.compare(encoded.get(left), encoded.get(right)),
  );
};

const hasOnlyUnicodeScalars = (value) =>
  boundedUnicodeScalarLength(value, Number.MAX_SAFE_INTEGER) >= 0;

const chargePlainDataBudget = (budget, { nodes = 0, utf8Bytes = 0 } = {}) => {
  budget.nodes += nodes;
  budget.utf8Bytes += utf8Bytes;
  if (
    budget.nodes > MAX_PLAIN_DATA_NODES ||
    budget.utf8Bytes > MAX_PLAIN_DATA_UTF8_BYTES
  ) {
    failAdapterExecution(
      "ADAPTER_EXECUTION_DATA_LIMIT_EXCEEDED",
      "canonical execution data exceeds the bounded node or UTF-8 byte budget",
    );
  }
};

const cloneFrozenPlainData = (
  value,
  label,
  budget,
  ancestors,
  depth,
) => {
  if (depth > MAX_PLAIN_DATA_DEPTH) {
    failAdapterExecution(
      "ADAPTER_EXECUTION_DATA_LIMIT_EXCEEDED",
      label + " exceeds the bounded plain-data depth",
    );
  }
  chargePlainDataBudget(budget, { nodes: 1 });
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") {
    if (!hasOnlyUnicodeScalars(value)) {
      failAdapterExecution(
        "ADAPTER_EXECUTION_DATA_INVALID",
        label + " contains an invalid Unicode scalar sequence",
      );
    }
    chargePlainDataBudget(budget, { utf8Bytes: Buffer.byteLength(value, "utf8") });
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      failAdapterExecution(
        "ADAPTER_EXECUTION_DATA_INVALID",
        label + " contains a non-finite number",
      );
    }
    return value;
  }
  if (typeof value !== "object" || IS_PROXY(value)) {
    failAdapterExecution(
      "ADAPTER_EXECUTION_DATA_INVALID",
      label + " must contain only non-proxy JSON plain data",
    );
  }
  if (ancestors.has(value)) {
    failAdapterExecution(
      "ADAPTER_EXECUTION_DATA_INVALID",
      label + " must not contain cycles",
    );
  }
  ancestors.add(value);
  try {
    if (ARRAY_IS_ARRAY(value)) {
      if (OBJECT_GET_PROTOTYPE_OF(value) !== Array.prototype) {
        failAdapterExecution(
          "ADAPTER_EXECUTION_DATA_INVALID",
          label + " arrays must use Array.prototype",
        );
      }
      if (value.length > MAX_PLAIN_DATA_NODES - budget.nodes) {
        failAdapterExecution(
          "ADAPTER_EXECUTION_DATA_LIMIT_EXCEEDED",
          label + " exceeds the bounded array element budget",
        );
      }
      for (const key of REFLECT_OWN_KEYS(value)) {
        if (key === "length") continue;
        if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
          failAdapterExecution(
            "ADAPTER_EXECUTION_DATA_INVALID",
            label + " contains a non-element array property",
          );
        }
      }
      const output = new Array(value.length);
      for (let index = 0; index < value.length; index += 1) {
        const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
        if (
          descriptor === undefined ||
          !descriptor.enumerable ||
          !OBJECT_HAS_OWN(descriptor, "value")
        ) {
          failAdapterExecution(
            "ADAPTER_EXECUTION_DATA_INVALID",
            label + " contains a sparse or accessor-backed array element",
          );
        }
        output[index] = cloneFrozenPlainData(
          descriptor.value,
          label,
          budget,
          ancestors,
          depth + 1,
        );
      }
      return Object.freeze(output);
    }

    if (
      OBJECT_GET_PROTOTYPE_OF(value) !== Object.prototype &&
      OBJECT_GET_PROTOTYPE_OF(value) !== null
    ) {
      failAdapterExecution(
        "ADAPTER_EXECUTION_DATA_INVALID",
        label + " objects must use Object.prototype or a null prototype",
      );
    }
    const keys = REFLECT_OWN_KEYS(value);
    if (keys.length > MAX_PLAIN_DATA_NODES - budget.nodes) {
      failAdapterExecution(
        "ADAPTER_EXECUTION_DATA_LIMIT_EXCEEDED",
        label + " exceeds the bounded object member budget",
      );
    }
    if (keys.some((key) => typeof key !== "string")) {
      failAdapterExecution(
        "ADAPTER_EXECUTION_DATA_INVALID",
        label + " must not contain symbol keys",
      );
    }
    const output = {};
    for (const key of keys) {
      if (DENIED_OBJECT_KEYS.has(key) || !hasOnlyUnicodeScalars(key)) {
        failAdapterExecution(
          "ADAPTER_EXECUTION_DATA_INVALID",
          label + " contains an unsafe object key",
        );
      }
      chargePlainDataBudget(budget, { utf8Bytes: Buffer.byteLength(key, "utf8") });
    }
    for (const key of sortUtf8Keys(keys)) {
      const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
      if (
        descriptor === undefined ||
        !descriptor.enumerable ||
        !OBJECT_HAS_OWN(descriptor, "value")
      ) {
        failAdapterExecution(
          "ADAPTER_EXECUTION_DATA_INVALID",
          label + " contains an accessor-backed or hidden property",
        );
      }
      Object.defineProperty(output, key, {
        configurable: false,
        enumerable: true,
        value: cloneFrozenPlainData(
          descriptor.value,
          label,
          budget,
          ancestors,
          depth + 1,
        ),
        writable: false,
      });
    }
    return Object.freeze(output);
  } finally {
    ancestors.delete(value);
  }
};

const snapshotPlainData = (value, label) =>
  cloneFrozenPlainData(value, label, { nodes: 0, utf8Bytes: 0 }, new Set(), 0);

const deepFreeze = (value, seen = new Set()) => {
  if (value === null || typeof value !== "object" || seen.has(value)) return value;
  seen.add(value);
  for (const key of REFLECT_OWN_KEYS(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value, seen);
    }
  }
  return Object.freeze(value);
};

const errorState = (state, stage) => ({
  stage,
  adapterInvoked: state.adapterInvoked,
  intentState: state.intentState,
  attemptState: state.attemptState,
  artifactState: state.artifactState,
  receiptState: state.receiptState,
});

const callPort = async (state, stage, code, message, operation) => {
  state.stage = stage;
  try {
    return await operation();
  } catch (error) {
    throw wrapAdapterExecutionError(
      error,
      code,
      message,
      errorState(state, stage),
    );
  }
};

const normalizeOutputContract = (candidate, schemaRef, schemaHash) => {
  const contract = requirePlainRecord(
    candidate,
    "validated output contract",
    ["schema_hash", "schema_ref"],
  );
  if (
    readDataProperty(contract, "schema_ref") !== schemaRef ||
    readDataProperty(contract, "schema_hash") !== schemaHash
  ) {
    failAdapterExecution(
      "OUTPUT_CONTRACT_BINDING_MISMATCH",
      "validated output contract does not bind the descriptor and invocation",
    );
  }
  return Object.freeze({ schema_hash: schemaHash, schema_ref: schemaRef });
};

const normalizeCompleteness = (candidate, expectedCount) => {
  const completeness = requirePlainRecord(candidate, "completeness", [
    "expected_count",
    "missing_node_ids",
    "partial_allowed",
    "terminal_count",
  ]);
  const observedExpected = readDataProperty(completeness, "expected_count");
  const terminalCount = readDataProperty(completeness, "terminal_count");
  const partialAllowed = readDataProperty(completeness, "partial_allowed");
  const missingNodeIds = requireStringArray(
    readDataProperty(completeness, "missing_node_ids"),
    "completeness.missing_node_ids",
  );
  if (
    !Number.isSafeInteger(observedExpected) ||
    !Number.isSafeInteger(terminalCount) ||
    observedExpected < 0 ||
    terminalCount < 0
  ) {
    failAdapterExecution(
      "BUSINESS_OUTPUT_INCOMPLETE",
      "completeness counts must be non-negative safe integers",
    );
  }
  if (
    observedExpected !== expectedCount ||
    terminalCount !== expectedCount ||
    missingNodeIds.length !== 0 ||
    partialAllowed !== false
  ) {
    failAdapterExecution(
      "BUSINESS_OUTPUT_INCOMPLETE",
      "local_scripted success requires exact complete output accounting",
      {
        details: {
          expectedCount,
          missingNodeCount: missingNodeIds.length,
          observedExpected,
          partialAllowed,
          terminalCount,
        },
      },
    );
  }
  return Object.freeze({
    expected_count: expectedCount,
    terminal_count: terminalCount,
    missing_node_ids: Object.freeze([]),
    partial_allowed: false,
  });
};

const normalizeBusinessValidation = (candidate, expectedCount) => {
  const validation = requirePlainRecord(
    candidate,
    "business output validation",
    ["completeness", "schema_validation_report_id"],
  );
  return Object.freeze({
    schema_validation_report_id: requireText(
      readDataProperty(validation, "schema_validation_report_id"),
      "schema_validation_report_id",
      { maxLength: 256 },
    ),
    completeness: normalizeCompleteness(
      readDataProperty(validation, "completeness"),
      expectedCount,
    ),
  });
};

const normalizeArtifactWrite = (
  candidate,
  expectedSchemaHash,
  authorizationDecision,
) => {
  const write = requirePlainRecord(candidate, "artifact write result", [
    "artifact_id",
    "artifact_receipt",
    "authorization_hash",
    "authorization_id",
    "content_hash",
    "schema_hash",
  ]);
  const schemaHash = requireHash(
    readDataProperty(write, "schema_hash"),
    "artifact write schema_hash",
  );
  if (schemaHash !== expectedSchemaHash) {
    failAdapterExecution(
      "ARTIFACT_SCHEMA_HASH_MISMATCH",
      "persisted artifact metadata does not bind the expected business schema",
    );
  }
  if (
    readDataProperty(write, "authorization_id") !==
      authorizationDecision.authorization_id ||
    readDataProperty(write, "authorization_hash") !==
      authorizationDecision.authorization_hash
  ) {
    failAdapterExecution(
      "ARTIFACT_AUTHORIZATION_BINDING_MISMATCH",
      "persisted artifact metadata does not bind the kernel authorization",
    );
  }
  return Object.freeze({
    artifact_id: requireText(
      readDataProperty(write, "artifact_id"),
      "artifact_id",
      { maxLength: 256 },
    ),
    content_hash: requireHash(
      readDataProperty(write, "content_hash"),
      "content_hash",
    ),
    schema_hash: schemaHash,
    artifact_receipt: readDataProperty(write, "artifact_receipt"),
    authorization_hash: authorizationDecision.authorization_hash,
    authorization_id: authorizationDecision.authorization_id,
  });
};

const assertArtifactReceiptBinding = (
  receipt,
  artifactWrite,
  intentId,
  schemaRef,
) => {
  const normalized = requirePlainRecord(receipt, "ArtifactReceipt");
  if (
    readDataProperty(normalized, "artifact_id") !== artifactWrite.artifact_id ||
    readDataProperty(normalized, "action_intent_id") !== intentId ||
    readDataProperty(normalized, "content_hash") !== artifactWrite.content_hash ||
    readDataProperty(normalized, "schema_ref") !== schemaRef
  ) {
    failAdapterExecution(
      "ARTIFACT_RECEIPT_BINDING_MISMATCH",
      "ArtifactReceipt does not bind the output artifact, schema, and ActionIntent",
    );
  }
  const validationResults = readDataProperty(normalized, "validation_results");
  if (
    !ARRAY_IS_ARRAY(validationResults) ||
    validationResults.length === 0 ||
    validationResults.some(
      (entry) =>
        entry === null ||
        typeof entry !== "object" ||
        readDataProperty(requirePlainRecord(entry, "validation result"), "status") !==
          "PASS",
    )
  ) {
    failAdapterExecution(
      "ARTIFACT_RECEIPT_VALIDATION_INCOMPLETE",
      "successful output artifacts require only resolving PASS validations",
    );
  }
  return normalized;
};

const assertIntentBinding = (intent, invocation, descriptor) => {
  const normalized = requirePlainRecord(intent, "sealed ActionIntent");
  const inputArtifactIds = requireStringArray(
    readDataProperty(invocation, "input_artifact_ids"),
    "NodeInvocation.input_artifact_ids",
  );
  if (
    readDataProperty(normalized, "run_id") !==
      readDataProperty(invocation, "run_id") ||
    readDataProperty(normalized, "node_id") !==
      readDataProperty(invocation, "node_id") ||
    readDataProperty(normalized, "action_type") !==
      LOCAL_SCRIPTED_ACTION_TYPE ||
    readDataProperty(normalized, "target_ref") !==
      descriptor.spawn_descriptor_id ||
    readDataProperty(normalized, "arguments_hash") !==
      readDataProperty(invocation, "input_hash") ||
    !inputArtifactIds.includes(
      readDataProperty(normalized, "arguments_artifact_id"),
    ) ||
    readDataProperty(normalized, "risk_class") !== "bounded_compute"
  ) {
    failAdapterExecution(
      "ACTION_INTENT_BINDING_MISMATCH",
      "ActionIntent does not bind the local_scripted invocation without broadening authority",
    );
  }
  const roleCapabilities = new Set(
    descriptor.canonical_role_spec.tool_acl,
  );
  const requiredCapabilities = requireStringArray(
    readDataProperty(normalized, "required_capabilities"),
    "ActionIntent.required_capabilities",
  );
  if (
    requiredCapabilities.length === 0 ||
    requiredCapabilities.some((capability) => !roleCapabilities.has(capability))
  ) {
    failAdapterExecution(
      "ACTION_INTENT_CAPABILITY_MISMATCH",
      "ActionIntent capabilities must be a non-empty subset of the canonical RoleSpec ACL",
    );
  }
  requireHash(readDataProperty(normalized, "intent_hash"), "intent_hash");
  return normalized;
};

const normalizeAuthorizationResult = (
  candidate,
  intent,
  invocation,
  descriptor,
  checkedAt,
) => {
  const decision = requirePlainRecord(candidate, "execution authorization", [
    "approval_record_ids",
    "authorization_hash",
    "authorization_id",
    "authorized",
    "capability_grant_ids",
    "checked_at",
    "deadline_at",
    "expected_output_schema_hash",
    "input_hash",
    "intent_hash",
    "intent_id",
    "lease_token",
    "node_id",
    "policy_bundle_id",
    "required_capabilities",
    "routing_receipt_hash",
    "routing_receipt_id",
    "run_id",
    "spawn_descriptor_hash",
  ]);
  const capabilityGrantIds = requireStringArray(
    readDataProperty(decision, "capability_grant_ids"),
    "authorization.capability_grant_ids",
  );
  const invocationCapabilityGrantIds = requireStringArray(
    readDataProperty(invocation, "capability_grant_ids"),
    "NodeInvocation.capability_grant_ids",
  );
  const requiredCapabilities = requireStringArray(
    readDataProperty(decision, "required_capabilities"),
    "authorization.required_capabilities",
  );
  const intentRequiredCapabilities = requireStringArray(
    readDataProperty(intent, "required_capabilities"),
    "ActionIntent.required_capabilities",
  );
  const approvalRecordIds = requireStringArray(
    readDataProperty(decision, "approval_record_ids"),
    "authorization.approval_record_ids",
  );
  const intentApprovalRecordIds = requireStringArray(
    readDataProperty(intent, "approval_record_ids"),
    "ActionIntent.approval_record_ids",
  );
  const leaseToken = readDataProperty(decision, "lease_token");
  if (
    readDataProperty(decision, "authorized") !== true ||
    readDataProperty(decision, "intent_id") !==
      readDataProperty(intent, "intent_id") ||
    readDataProperty(decision, "intent_hash") !==
      readDataProperty(intent, "intent_hash") ||
    readDataProperty(decision, "run_id") !==
      readDataProperty(invocation, "run_id") ||
    readDataProperty(decision, "node_id") !==
      readDataProperty(invocation, "node_id") ||
    readDataProperty(decision, "input_hash") !==
      readDataProperty(invocation, "input_hash") ||
    readDataProperty(decision, "policy_bundle_id") !==
      readDataProperty(invocation, "policy_bundle_id") ||
    !Number.isSafeInteger(leaseToken) ||
    leaseToken !== readDataProperty(invocation, "lease_token") ||
    readDataProperty(decision, "deadline_at") !==
      readDataProperty(invocation, "deadline_at") ||
    readDataProperty(decision, "expected_output_schema_hash") !==
      readDataProperty(invocation, "expected_output_schema_hash") ||
    readDataProperty(decision, "spawn_descriptor_hash") !==
      descriptor.spawn_descriptor_hash ||
    readDataProperty(decision, "routing_receipt_id") !==
      descriptor.model_binding.routing_receipt_id ||
    readDataProperty(decision, "routing_receipt_hash") !==
      descriptor.model_binding.routing_receipt_hash ||
    readDataProperty(decision, "checked_at") !== checkedAt ||
    !isDeepStrictEqual(capabilityGrantIds, invocationCapabilityGrantIds) ||
    !isDeepStrictEqual(requiredCapabilities, intentRequiredCapabilities) ||
    !isDeepStrictEqual(approvalRecordIds, intentApprovalRecordIds)
  ) {
    failAdapterExecution(
      "EXECUTION_AUTHORIZATION_BINDING_MISMATCH",
      "kernel authorization does not bind the exact intent, grants, policy, lease, route, and deadline",
    );
  }
  return Object.freeze({
    authorization_hash: requireHash(
      readDataProperty(decision, "authorization_hash"),
      "authorization.authorization_hash",
    ),
    authorization_id: requireText(
      readDataProperty(decision, "authorization_id"),
      "authorization.authorization_id",
      { maxLength: 256 },
    ),
    checked_at: requireTimestamp(
      readDataProperty(decision, "checked_at"),
      "authorization.checked_at",
    ),
  });
};

const assertDescriptorInvocationBinding = (descriptor, invocation, adapter) => {
  if (
    descriptor.execution_binding.node_id !==
    readDataProperty(invocation, "node_id")
  ) {
    failAdapterExecution(
      "EXECUTION_BINDING_MISMATCH",
      "SpawnDescriptor and NodeInvocation name different nodes",
    );
  }
  if (
    descriptor.model_binding.provider_id !== LOCAL_SCRIPTED_ADAPTER_KIND ||
    descriptor.model_binding.runtime_id !== LOCAL_SCRIPTED_ADAPTER_KIND ||
    descriptor.model_binding.runtime_version !== adapter.profile.adapter_version ||
    descriptor.model_binding.model_version !== adapter.profile.fixture_set_hash ||
    descriptor.model_binding.fallback_used !== false ||
    descriptor.model_binding.fallback_policy_decision_id !== null
  ) {
    failAdapterExecution(
      "LOCAL_SCRIPTED_ROUTE_MISMATCH",
      "local_scripted requires an explicit fixture-digest-bound non-fallback route",
    );
  }
};

const readClock = (clock, state, stage) => {
  state.stage = stage;
  try {
    return requireTimestamp(clock(), "clock result");
  } catch (error) {
    throw wrapAdapterExecutionError(
      error,
      "CLOCK_PORT_FAILED",
      "clock port failed",
      errorState(state, stage),
    );
  }
};

const assertNotCancelled = (cancellation, state, stage) => {
  state.stage = stage;
  let cancelled;
  try {
    cancelled = cancellation();
  } catch (error) {
    throw wrapAdapterExecutionError(
      error,
      "CANCELLATION_PORT_FAILED",
      "cancellation port failed",
      errorState(state, stage),
    );
  }
  if (typeof cancelled !== "boolean") {
    failAdapterExecution(
      "CANCELLATION_PORT_INVALID",
      "cancellation port must return a boolean",
      errorState(state, stage),
    );
  }
  if (cancelled) {
    failAdapterExecution(
      "ADAPTER_EXECUTION_CANCELLED",
      "bounded adapter execution was cancelled",
      errorState(state, stage),
    );
  }
};

const assertBeforeDeadline = (invocation, clock, state, stage) => {
  const deadline = readDataProperty(invocation, "deadline_at");
  if (deadline === null) return;
  requireTimestamp(deadline, "NodeInvocation.deadline_at");
  const now = readClock(clock, state, stage);
  if (compareTimestamps(now, deadline) >= 0) {
    failAdapterExecution(
      "ADAPTER_EXECUTION_DEADLINE_EXCEEDED",
      "NodeInvocation deadline has expired",
      { ...errorState(state, stage), details: { deadline, now } },
    );
  }
};

const assertPreEffectGuards = (invocation, cancellation, clock, state, stage) => {
  assertNotCancelled(cancellation, state, stage);
  assertBeforeDeadline(invocation, clock, state, stage);
};

const assertRegisteredIntent = (candidate, intent) => {
  const result = requirePlainRecord(candidate, "registerIntent result");
  const status = readDataProperty(result, "status");
  const registeredIntent = requirePlainRecord(
    readDataProperty(result, "intent"),
    "registered ActionIntent",
  );
  if (
    !["EXISTING", "REGISTERED"].includes(status) ||
    !["CONFIRMED", "EXISTING"].includes(
      readDataProperty(result, "event_status"),
    ) ||
    !isDeepStrictEqual(registeredIntent, intent)
  ) {
    failAdapterExecution(
      "ACTION_INTENT_REGISTRATION_UNCONFIRMED",
      "effect coordinator did not confirm the exact ActionIntent",
    );
  }
  return result;
};

const normalizeAttemptResult = (
  candidate,
  attemptId,
  intentId,
  requestedStartedAt,
) => {
  const result = requirePlainRecord(candidate, "beginAttempt result");
  const executePermitted = readDataProperty(result, "execute_permitted");
  if (typeof executePermitted !== "boolean") {
    failAdapterExecution(
      "EFFECT_ATTEMPT_RESULT_INVALID",
      "effect coordinator did not return an execution decision",
    );
  }
  const attempt = requirePlainRecord(
    readDataProperty(result, "attempt"),
    "Attempt",
  );
  if (
    readDataProperty(attempt, "intent_id") !== intentId ||
    (executePermitted && readDataProperty(attempt, "attempt_id") !== attemptId)
  ) {
    failAdapterExecution(
      "EFFECT_ATTEMPT_BINDING_MISMATCH",
      "effect coordinator returned an attempt for a different intent",
    );
  }
  const attemptStartedAt = requireTimestamp(
    readDataProperty(attempt, "started_at"),
    "Attempt.started_at",
  );
  const status = readDataProperty(result, "status");
  if (
    (executePermitted && status !== "STARTED") ||
    (!executePermitted &&
      !["EXISTING_ATTEMPT", "EXISTING_RESULT"].includes(status))
    || !["CONFIRMED", "EXISTING"].includes(
      readDataProperty(result, "event_status"),
    )
  ) {
    failAdapterExecution(
      "EFFECT_ATTEMPT_RESULT_INVALID",
      "effect coordinator returned an incoherent attempt status",
    );
  }
  if (
    executePermitted &&
    status === "STARTED" &&
    attemptStartedAt !== requestedStartedAt
  ) {
    failAdapterExecution(
      "EFFECT_ATTEMPT_BINDING_MISMATCH",
      "effect coordinator did not preserve the requested attempt start time",
    );
  }
  return Object.freeze({ attempt, executePermitted, result, status });
};

const assertRecordedReceipt = (candidate, effectReceipt) => {
  const result = requirePlainRecord(candidate, "recordReceipt result");
  const status = readDataProperty(result, "status");
  const recordedReceipt = requirePlainRecord(
    readDataProperty(result, "receipt"),
    "recorded EffectReceipt",
  );
  const outcome = requirePlainRecord(
    readDataProperty(result, "outcome"),
    "recordReceipt outcome",
  );
  if (
    !["EXISTING", "RECORDED"].includes(status) ||
    !["CONFIRMED", "EXISTING"].includes(
      readDataProperty(result, "event_status"),
    ) ||
    !isDeepStrictEqual(recordedReceipt, effectReceipt) ||
    readDataProperty(outcome, "status") !== "SUCCEEDED" ||
    readDataProperty(outcome, "completion_proven") !== true ||
    readDataProperty(outcome, "outcome_resolved") !== true
  ) {
    failAdapterExecution(
      "EFFECT_RECEIPT_RECORD_UNCONFIRMED",
      "effect coordinator did not confirm the exact resolving receipt",
    );
  }
  return result;
};

const assertEffectReceiptBinding = (
  receipt,
  effectReceiptId,
  intent,
  attempt,
  artifactWrite,
  finishedAt,
) => {
  const normalized = requirePlainRecord(receipt, "sealed EffectReceipt");
  if (
    readDataProperty(normalized, "receipt_id") !== effectReceiptId ||
    readDataProperty(normalized, "intent_id") !==
      readDataProperty(intent, "intent_id") ||
    readDataProperty(normalized, "run_id") !==
      readDataProperty(intent, "run_id") ||
    readDataProperty(normalized, "status") !== "SUCCEEDED" ||
    readDataProperty(normalized, "idempotency_key") !==
      readDataProperty(intent, "idempotency_key") ||
    readDataProperty(normalized, "started_at") !==
      readDataProperty(attempt, "started_at") ||
    readDataProperty(normalized, "observed_state_hash") !==
      artifactWrite.content_hash ||
    readDataProperty(normalized, "external_operation_id") !== null ||
    readDataProperty(normalized, "finished_at") !== finishedAt ||
    readDataProperty(normalized, "reconciliation_required") !== false
  ) {
    failAdapterExecution(
      "EFFECT_RECEIPT_BINDING_MISMATCH",
      "EffectReceipt does not resolve the exact local_scripted attempt",
    );
  }
  const resultArtifactIds = requireStringArray(
    readDataProperty(normalized, "result_artifact_ids"),
    "EffectReceipt.result_artifact_ids",
  );
  const errorArtifactIds = requireStringArray(
    readDataProperty(normalized, "error_artifact_ids"),
    "EffectReceipt.error_artifact_ids",
  );
  if (
    resultArtifactIds.length !== 1 ||
    resultArtifactIds[0] !== artifactWrite.artifact_id ||
    errorArtifactIds.length !== 0
  ) {
    failAdapterExecution(
      "EFFECT_RECEIPT_BINDING_MISMATCH",
      "EffectReceipt must bind exactly the persisted output artifact",
    );
  }
  requireHash(readDataProperty(normalized, "receipt_hash"), "receipt_hash");
  return normalized;
};

const assertReplayEnvelopeBinding = (
  envelope,
  invocation,
  descriptor,
  effectReceipt,
  authorizationDecision,
) => {
  const normalized = requirePlainRecord(envelope, "replayed ResultEnvelope");
  const outputArtifactIds = requireStringArray(
    readDataProperty(normalized, "output_artifact_ids"),
    "ResultEnvelope.output_artifact_ids",
  );
  const effectReceiptIds = requireStringArray(
    readDataProperty(normalized, "effect_receipt_ids"),
    "ResultEnvelope.effect_receipt_ids",
  );
  const evidenceIds = requireStringArray(
    readDataProperty(normalized, "evidence_ids"),
    "ResultEnvelope.evidence_ids",
  );
  const errors = requireStringArray(
    readDataProperty(normalized, "errors"),
    "ResultEnvelope.errors",
  );
  const policyDecisionIds = requireStringArray(
    readDataProperty(normalized, "policy_decision_ids"),
    "ResultEnvelope.policy_decision_ids",
  );
  const metrics = requirePlainRecord(
    readDataProperty(normalized, "metrics"),
    "ResultEnvelope.metrics",
    [],
    [],
  );
  const completeness = normalizeCompleteness(
    readDataProperty(normalized, "completeness"),
    descriptor.result_contract.expected_count,
  );
  if (
    readDataProperty(normalized, "run_id") !==
      readDataProperty(invocation, "run_id") ||
    readDataProperty(normalized, "node_id") !==
      readDataProperty(invocation, "node_id") ||
    readDataProperty(normalized, "attempt") !==
      readDataProperty(invocation, "attempt") ||
    readDataProperty(normalized, "status") !== "success" ||
    readDataProperty(normalized, "terminal_reason") !==
      LOCAL_SCRIPTED_TERMINAL_REASON ||
    readDataProperty(normalized, "input_hash") !==
      readDataProperty(invocation, "input_hash") ||
    readDataProperty(normalized, "started_at") !==
      readDataProperty(effectReceipt, "started_at") ||
    readDataProperty(normalized, "finished_at") !==
      readDataProperty(effectReceipt, "finished_at") ||
    readDataProperty(normalized, "output_hash") !==
      readDataProperty(effectReceipt, "observed_state_hash") ||
    outputArtifactIds.length !== 1 ||
    outputArtifactIds[0] !==
      readDataProperty(effectReceipt, "result_artifact_ids")[0] ||
    effectReceiptIds.length !== 1 ||
    effectReceiptIds[0] !== readDataProperty(effectReceipt, "receipt_id") ||
    evidenceIds.length !== 0 ||
    errors.length !== 0 ||
    policyDecisionIds.length !== 1 ||
    policyDecisionIds[0] !== authorizationDecision.authorization_id ||
    REFLECT_OWN_KEYS(metrics).length !== 0 ||
    !isDeepStrictEqual(
      readDataProperty(normalized, "completeness"),
      completeness,
    )
  ) {
    failAdapterExecution(
      "REPLAY_RESULT_BINDING_MISMATCH",
      "replayed ResultEnvelope is not the exact receipt-bound local result",
    );
  }
  return normalized;
};

/**
 * Create the N02-only bounded execution boundary.
 *
 * All canonical validation, effect coordination, sealing, artifact persistence,
 * time, and cancellation behavior is supplied by the caller. This module does
 * not import a provider transport, Foundry Kernel implementation, ledger, or
 * artifact store.
 */
export const createBoundedAdapterExecutor = (candidate) => {
  const dependencies = requirePlainRecord(
    candidate,
    "bounded adapter executor dependencies",
    EXECUTOR_DEPENDENCY_FIELDS,
  );
  const contractValidator = readDataProperty(
    dependencies,
    "contractValidator",
  );
  const executionAuthority = readDataProperty(
    dependencies,
    "executionAuthority",
  );
  const effectCoordinator = readDataProperty(
    dependencies,
    "effectCoordinator",
  );
  const effectSealer = readDataProperty(dependencies, "effectSealer");
  const artifactWriter = readDataProperty(dependencies, "artifactWriter");
  const replayResolver = readDataProperty(dependencies, "replayResolver");
  const clock = requireCallable(readDataProperty(dependencies, "clock"), "clock");
  const cancellation = requireCallable(
    readDataProperty(dependencies, "cancellation"),
    "cancellation",
  );

  const validateNodeInvocation = bindMethod(
    contractValidator,
    "validateNodeInvocation",
    "contractValidator",
  );
  const validateOutputContract = bindMethod(
    contractValidator,
    "validateOutputContract",
    "contractValidator",
  );
  const validateBusinessOutput = bindMethod(
    contractValidator,
    "validateBusinessOutput",
    "contractValidator",
  );
  const validateArtifactReceipt = bindMethod(
    contractValidator,
    "validateArtifactReceipt",
    "contractValidator",
  );
  const validateEffectReceipt = bindMethod(
    contractValidator,
    "validateEffectReceipt",
    "contractValidator",
  );
  const validateResultEnvelope = bindMethod(
    contractValidator,
    "validateResultEnvelope",
    "contractValidator",
  );
  const sealActionIntent = bindMethod(
    effectSealer,
    "sealActionIntent",
    "effectSealer",
  );
  const sealEffectReceipt = bindMethod(
    effectSealer,
    "sealEffectReceipt",
    "effectSealer",
  );
  const registerIntent = bindMethod(
    effectCoordinator,
    "registerIntent",
    "effectCoordinator",
  );
  const beginAttempt = bindMethod(
    effectCoordinator,
    "beginAttempt",
    "effectCoordinator",
  );
  const recordReceipt = bindMethod(
    effectCoordinator,
    "recordReceipt",
    "effectCoordinator",
  );
  const writeOutputArtifact = bindMethod(
    artifactWriter,
    "writeOutputArtifact",
    "artifactWriter",
  );
  const resolveExistingResult = bindMethod(
    replayResolver,
    "resolveExistingResult",
    "replayResolver",
  );
  const authorizeExecution = bindMethod(
    executionAuthority,
    "authorizeExecution",
    "executionAuthority",
  );
  const validateStoredAuthorization = bindMethod(
    executionAuthority,
    "validateStoredAuthorization",
    "executionAuthority",
  );

  const executor = {
    kind: "bounded_adapter_executor",
    version: BOUNDED_ADAPTER_EXECUTOR_VERSION,
    async execute(requestCandidate) {
      const state = {
        adapterInvoked: false,
        artifactState: "NOT_STARTED",
        attemptState: "NOT_STARTED",
        intentState: "NOT_STARTED",
        receiptState: "NOT_STARTED",
        stage: "preflight",
      };
      try {
        const request = requirePlainRecord(
          requestCandidate,
          "bounded adapter execution request",
          EXECUTION_REQUEST_FIELDS,
          EXECUTION_REQUEST_FIELDS,
        );
        const attemptId = requireText(
          readDataProperty(request, "attemptId"),
          "attemptId",
          { maxLength: 256 },
        );
        const effectReceiptId = requireText(
          readDataProperty(request, "effectReceiptId"),
          "effectReceiptId",
          { maxLength: 256 },
        );

        assertNotCancelled(cancellation, state, "preflight");
        const adapter = verifyLocalScriptedAdapter(
          readDataProperty(request, "adapter"),
        );
        const actionIntentInput = snapshotPlainData(
          readDataProperty(request, "actionIntent"),
          "ActionIntent input",
        );
        const nodeInvocationInput = snapshotPlainData(
          readDataProperty(request, "nodeInvocation"),
          "NodeInvocation input",
        );
        const spawnDescriptorInput = snapshotPlainData(
          readDataProperty(request, "spawnDescriptor"),
          "SpawnDescriptor input",
        );
        const descriptorCandidate = await callPort(
          state,
          "descriptor_validation",
          "SPAWN_DESCRIPTOR_INVALID",
          "SpawnDescriptor integrity validation failed",
          () => verifySpawnDescriptorIntegrity(spawnDescriptorInput),
        );
        const descriptor = snapshotPlainData(
          descriptorCandidate,
          "validated SpawnDescriptor",
        );
        const invocationCandidate = await callPort(
          state,
          "invocation_validation",
          "NODE_INVOCATION_INVALID",
          "NodeInvocation validation failed",
          () => validateNodeInvocation(nodeInvocationInput),
        );
        const invocation = snapshotPlainData(
          invocationCandidate,
          "validated NodeInvocation",
        );
        if (!isDeepStrictEqual(invocation, nodeInvocationInput)) {
          failAdapterExecution(
            "NODE_INVOCATION_SEMANTIC_MISMATCH",
            "NodeInvocation validator changed the submitted invocation",
          );
        }
        requirePlainRecord(invocation, "validated NodeInvocation");
        assertDescriptorInvocationBinding(descriptor, invocation, adapter);
        const inputHash = requireHash(
          readDataProperty(invocation, "input_hash"),
          "NodeInvocation.input_hash",
        );
        if (!adapter.hasResponseForInputHash(inputHash)) {
          failAdapterExecution(
            "LOCAL_SCRIPTED_RESPONSE_NOT_FOUND",
            "no fixture is bound to NodeInvocation.input_hash",
          );
        }
        assertPreEffectGuards(
          invocation,
          cancellation,
          clock,
          state,
          "validated_preflight",
        );

        const schemaRef =
          descriptor.result_contract.business_output_schema_ref;
        const schemaHash = requireHash(
          readDataProperty(invocation, "expected_output_schema_hash"),
          "NodeInvocation.expected_output_schema_hash",
        );
        const outputContractCandidate = await callPort(
          state,
          "output_contract_validation",
          "OUTPUT_CONTRACT_UNAVAILABLE",
          "expected output contract validation failed",
          () =>
            validateOutputContract({
              schema_hash: schemaHash,
              schema_ref: schemaRef,
            }),
        );
        const outputContract = snapshotPlainData(
          outputContractCandidate,
          "validated output contract",
        );
        normalizeOutputContract(
          outputContract,
          schemaRef,
          schemaHash,
        );

        const sealedIntentCandidate = await callPort(
          state,
          "action_intent_seal",
          "ACTION_INTENT_SEAL_FAILED",
          "ActionIntent sealing failed",
          () => sealActionIntent(actionIntentInput),
        );
        const sealedIntent = snapshotPlainData(
          sealedIntentCandidate,
          "sealed ActionIntent",
        );
        const intent = assertIntentBinding(
          sealedIntent,
          invocation,
          descriptor,
        );
        assertPreEffectGuards(
          invocation,
          cancellation,
          clock,
          state,
          "before_execution_authorization",
        );
        const authorizationCheckedAt = readClock(
          clock,
          state,
          "execution_authorization_clock",
        );
        const authorizationCandidate = await callPort(
          state,
          "execution_authorization",
          "EXECUTION_AUTHORIZATION_FAILED",
          "kernel execution authorization failed",
          () =>
            authorizeExecution({
              action_intent: intent,
              checked_at: authorizationCheckedAt,
              node_invocation: invocation,
              spawn_descriptor: descriptor,
            }),
        );
        const authorization = snapshotPlainData(
          authorizationCandidate,
          "execution authorization",
        );
        const authorizationDecision = normalizeAuthorizationResult(
          authorization,
          intent,
          invocation,
          descriptor,
          authorizationCheckedAt,
        );
        assertPreEffectGuards(
          invocation,
          cancellation,
          clock,
          state,
          "before_intent_registration",
        );

        state.intentState = "UNKNOWN";
        const registrationResult = await callPort(
          state,
          "intent_registration",
          "ACTION_INTENT_REGISTRATION_FAILED",
          "ActionIntent registration failed",
          () => registerIntent(intent),
        );
        const registeredIntentResult = snapshotPlainData(
          registrationResult,
          "registerIntent result",
        );
        assertRegisteredIntent(registeredIntentResult, intent);
        state.intentState = "CONFIRMED";
        assertPreEffectGuards(
          invocation,
          cancellation,
          clock,
          state,
          "before_attempt",
        );
        const startedAt = readClock(clock, state, "attempt_start_clock");
        if (compareTimestamps(startedAt, authorizationCheckedAt) < 0) {
          failAdapterExecution(
            "EXECUTION_CHRONOLOGY_INVALID",
            "attempt start time precedes execution authorization",
            {
              ...errorState(state, "before_attempt"),
              details: {
                authorizationCheckedAt,
                startedAt,
              },
            },
          );
        }
        state.attemptState = "UNKNOWN";
        const attemptResult = await callPort(
          state,
          "attempt_start",
          "EFFECT_ATTEMPT_START_FAILED",
          "effect attempt could not be started",
          () =>
            beginAttempt({
              attempt_id: attemptId,
              intent_id: readDataProperty(intent, "intent_id"),
              started_at: startedAt,
            }),
        );
        const attemptResultSnapshot = snapshotPlainData(
          attemptResult,
          "beginAttempt result",
        );
        const attemptResolution = normalizeAttemptResult(
          attemptResultSnapshot,
          attemptId,
          readDataProperty(intent, "intent_id"),
          startedAt,
        );
        state.attemptState = "CONFIRMED";

        if (!attemptResolution.executePermitted) {
          if (attemptResolution.status !== "EXISTING_RESULT") {
            failAdapterExecution(
              "EFFECT_RECONCILIATION_REQUIRED",
              "an existing unresolved attempt prevents duplicate execution",
              errorState(state, "attempt_replay"),
            );
          }
          const outcome = requirePlainRecord(
            readDataProperty(attemptResolution.result, "outcome"),
            "existing effect outcome",
          );
          if (
            readDataProperty(outcome, "status") !== "SUCCEEDED" ||
            readDataProperty(outcome, "completion_proven") !== true ||
            readDataProperty(outcome, "outcome_resolved") !== true
          ) {
            failAdapterExecution(
              "EFFECT_REPLAY_NOT_RESOLVING",
              "only a canonically resolved success can be replayed",
              errorState(state, "attempt_replay"),
            );
          }
          const existingReceiptCandidate = readDataProperty(
            outcome,
            "receipt",
          );
          const existingReceiptValidatedCandidate = await callPort(
            state,
            "existing_receipt_validation",
            "EXISTING_EFFECT_RECEIPT_INVALID",
            "existing EffectReceipt validation failed",
            () => validateEffectReceipt(existingReceiptCandidate),
          );
          const existingReceipt = snapshotPlainData(
            existingReceiptValidatedCandidate,
            "validated existing EffectReceipt",
          );
          if (!isDeepStrictEqual(existingReceipt, existingReceiptCandidate)) {
            failAdapterExecution(
              "EXISTING_EFFECT_RECEIPT_SEMANTIC_MISMATCH",
              "EffectReceipt validator changed the stored receipt",
              errorState(state, "existing_receipt_validation"),
            );
          }
          const existingResultArtifactIds = requireStringArray(
            readDataProperty(existingReceipt, "result_artifact_ids"),
            "existing EffectReceipt.result_artifact_ids",
          );
          const existingArtifactWrite = Object.freeze({
            artifact_id:
              existingResultArtifactIds.length === 1
                ? existingResultArtifactIds[0]
                : "",
            content_hash: requireHash(
              readDataProperty(existingReceipt, "observed_state_hash"),
              "existing EffectReceipt.observed_state_hash",
            ),
            schema_hash: schemaHash,
          });
          assertEffectReceiptBinding(
            existingReceipt,
            readDataProperty(existingReceipt, "receipt_id"),
            intent,
            attemptResolution.attempt,
            existingArtifactWrite,
            readDataProperty(existingReceipt, "finished_at"),
          );
          state.receiptState = "CONFIRMED";

          const replayCandidate = await callPort(
            state,
            "existing_result_resolution",
            "EXISTING_RESULT_RESOLUTION_FAILED",
            "existing result could not be resolved from canonical storage",
            () =>
              resolveExistingResult({
                access_authorization: authorizationDecision,
                effect_receipt: existingReceipt,
                expected_schema_hash: schemaHash,
                node_invocation: invocation,
                schema_ref: schemaRef,
                spawn_descriptor: descriptor,
              }),
          );
          const replaySnapshot = snapshotPlainData(
            replayCandidate,
            "existing result resolution",
          );
          const replay = requirePlainRecord(
            replaySnapshot,
            "existing result resolution",
            [
              "artifact_receipt",
              "authorization_hash",
              "authorization_id",
              "result_envelope",
              "schema_hash",
              "stored_authorization",
            ],
          );
          if (
            requireHash(
              readDataProperty(replay, "schema_hash"),
              "replayed artifact schema_hash",
            ) !== schemaHash
          ) {
            failAdapterExecution(
              "REPLAY_ARTIFACT_SCHEMA_HASH_MISMATCH",
              "stored artifact metadata does not bind the current exact schema hash",
              errorState(state, "existing_result_resolution"),
            );
          }
          const storedAuthorizationCandidate = readDataProperty(
            replay,
            "stored_authorization",
          );
          const validatedStoredAuthorizationCandidate = await callPort(
            state,
            "stored_authorization_validation",
            "STORED_AUTHORIZATION_INVALID",
            "stored execution authorization validation failed",
            () => validateStoredAuthorization(storedAuthorizationCandidate),
          );
          const validatedStoredAuthorization = snapshotPlainData(
            validatedStoredAuthorizationCandidate,
            "validated stored authorization",
          );
          if (
            !isDeepStrictEqual(
              validatedStoredAuthorization,
              storedAuthorizationCandidate,
            )
          ) {
            failAdapterExecution(
              "STORED_AUTHORIZATION_SEMANTIC_MISMATCH",
              "authorization validator changed the stored authorization",
              errorState(state, "stored_authorization_validation"),
            );
          }
          const storedCheckedAt = requireTimestamp(
            readDataProperty(validatedStoredAuthorization, "checked_at"),
            "stored authorization.checked_at",
          );
          const storedAuthorizationDecision = normalizeAuthorizationResult(
            validatedStoredAuthorization,
            intent,
            invocation,
            descriptor,
            storedCheckedAt,
          );
          const invocationDeadline = readDataProperty(invocation, "deadline_at");
          if (
            compareTimestamps(
              storedAuthorizationDecision.checked_at,
              readDataProperty(attemptResolution.attempt, "started_at"),
            ) > 0 ||
            (invocationDeadline !== null &&
              compareTimestamps(
                storedAuthorizationDecision.checked_at,
                invocationDeadline,
              ) >= 0)
          ) {
            failAdapterExecution(
              "STORED_AUTHORIZATION_CHRONOLOGY_INVALID",
              "stored authorization does not precede the original attempt and deadline",
              errorState(state, "stored_authorization_validation"),
            );
          }
          if (
            readDataProperty(replay, "authorization_id") !==
              storedAuthorizationDecision.authorization_id ||
            readDataProperty(replay, "authorization_hash") !==
              storedAuthorizationDecision.authorization_hash
          ) {
            failAdapterExecution(
              "REPLAY_ARTIFACT_AUTHORIZATION_MISMATCH",
              "stored artifact metadata does not bind the original execution authorization",
              errorState(state, "existing_result_resolution"),
            );
          }
          const replayArtifactReceiptCandidate = await callPort(
            state,
            "existing_artifact_receipt_validation",
            "EXISTING_ARTIFACT_RECEIPT_INVALID",
            "existing ArtifactReceipt validation failed",
            () =>
              validateArtifactReceipt(
                readDataProperty(replay, "artifact_receipt"),
              ),
          );
          const replayArtifactReceipt = snapshotPlainData(
            replayArtifactReceiptCandidate,
            "validated existing ArtifactReceipt",
          );
          if (
            !isDeepStrictEqual(
              replayArtifactReceipt,
              readDataProperty(replay, "artifact_receipt"),
            )
          ) {
            failAdapterExecution(
              "EXISTING_ARTIFACT_RECEIPT_SEMANTIC_MISMATCH",
              "ArtifactReceipt validator changed the stored receipt",
              errorState(state, "existing_artifact_receipt_validation"),
            );
          }
          assertArtifactReceiptBinding(
            replayArtifactReceipt,
            existingArtifactWrite,
            readDataProperty(intent, "intent_id"),
            schemaRef,
          );
          state.artifactState = "CONFIRMED";
          const replayEnvelopeCandidate = readDataProperty(
            replay,
            "result_envelope",
          );
          const replayEnvelopeValidatedCandidate = await callPort(
            state,
            "existing_result_envelope_validation",
            "EXISTING_RESULT_ENVELOPE_INVALID",
            "existing ResultEnvelope validation failed",
            () => validateResultEnvelope(replayEnvelopeCandidate),
          );
          const replayEnvelope = snapshotPlainData(
            replayEnvelopeValidatedCandidate,
            "validated replay ResultEnvelope",
          );
          if (!isDeepStrictEqual(replayEnvelope, replayEnvelopeCandidate)) {
            failAdapterExecution(
              "REPLAY_RESULT_SEMANTIC_MISMATCH",
              "ResultEnvelope validator changed the replayed result",
              errorState(state, "existing_result_envelope_validation"),
            );
          }
          assertReplayEnvelopeBinding(
            replayEnvelope,
            invocation,
            descriptor,
            existingReceipt,
            storedAuthorizationDecision,
          );
          return deepFreeze(replayEnvelope);
        }
        const attempt = attemptResolution.attempt;
        assertPreEffectGuards(
          invocation,
          cancellation,
          clock,
          state,
          "before_adapter_call",
        );

        state.stage = "adapter_call";
        state.adapterInvoked = true;
        let scriptedOutput;
        try {
          scriptedOutput = adapter.execute({ nodeInvocation: invocation });
        } catch (error) {
          throw wrapAdapterExecutionError(
            error,
            "LOCAL_SCRIPTED_EXECUTION_FAILED",
            "local_scripted adapter execution failed",
            errorState(state, "adapter_call"),
          );
        }

        const businessValidationCandidate = await callPort(
          state,
          "business_output_validation",
          "BUSINESS_OUTPUT_VALIDATION_FAILED",
          "local_scripted output failed its business schema",
          () =>
            validateBusinessOutput({
              expected_count: descriptor.result_contract.expected_count,
              output: scriptedOutput,
              schema_hash: schemaHash,
              schema_ref: schemaRef,
            }),
        );
        const businessValidationSnapshot = snapshotPlainData(
          businessValidationCandidate,
          "business output validation",
        );
        const businessValidation = normalizeBusinessValidation(
          businessValidationSnapshot,
          descriptor.result_contract.expected_count,
        );

        assertPreEffectGuards(
          invocation,
          cancellation,
          clock,
          state,
          "before_artifact_write",
        );
        state.artifactState = "UNKNOWN";
        const artifactWriteCandidate = await callPort(
          state,
          "artifact_write",
          "OUTPUT_ARTIFACT_WRITE_FAILED",
          "validated local_scripted output could not be persisted",
          () =>
            writeOutputArtifact({
              action_intent: intent,
              execution_authority: authorizationDecision,
              business_output: scriptedOutput,
              fixture_set_hash: adapter.profile.fixture_set_hash,
              media_type: "application/json",
              node_invocation: {
                attempt: readDataProperty(invocation, "attempt"),
                input_hash: readDataProperty(invocation, "input_hash"),
                node_id: readDataProperty(invocation, "node_id"),
                run_id: readDataProperty(invocation, "run_id"),
              },
              schema_hash: schemaHash,
              schema_ref: schemaRef,
              schema_validation_report_id:
                businessValidation.schema_validation_report_id,
              spawn_descriptor_id: descriptor.spawn_descriptor_id,
            }),
        );
        const artifactWriteSnapshot = snapshotPlainData(
          artifactWriteCandidate,
          "artifact write result",
        );
        const artifactWrite = normalizeArtifactWrite(
          artifactWriteSnapshot,
          schemaHash,
          authorizationDecision,
        );
        const validatedArtifactReceiptCandidate = await callPort(
          state,
          "artifact_receipt_validation",
          "ARTIFACT_RECEIPT_INVALID",
          "ArtifactReceipt validation failed",
          () => validateArtifactReceipt(artifactWrite.artifact_receipt),
        );
        const validatedArtifactReceipt = snapshotPlainData(
          validatedArtifactReceiptCandidate,
          "validated ArtifactReceipt",
        );
        if (
          !isDeepStrictEqual(
            validatedArtifactReceipt,
            artifactWrite.artifact_receipt,
          )
        ) {
          failAdapterExecution(
            "ARTIFACT_RECEIPT_SEMANTIC_MISMATCH",
            "ArtifactReceipt validator changed the persisted receipt",
            errorState(state, "artifact_receipt_validation"),
          );
        }
        assertArtifactReceiptBinding(
          validatedArtifactReceipt,
          artifactWrite,
          readDataProperty(intent, "intent_id"),
          schemaRef,
        );
        state.artifactState = "CONFIRMED";

        const finishedAt = readClock(clock, state, "effect_receipt_clock");
        if (
          compareTimestamps(
            finishedAt,
            readDataProperty(attempt, "started_at"),
          ) < 0
        ) {
          failAdapterExecution(
            "EXECUTION_CHRONOLOGY_INVALID",
            "effect finish time precedes the confirmed attempt start",
            {
              ...errorState(state, "before_effect_receipt"),
              details: {
                finishedAt,
                startedAt: readDataProperty(attempt, "started_at"),
              },
            },
          );
        }
        const sealedEffectReceiptCandidate = await callPort(
          state,
          "effect_receipt_seal",
          "EFFECT_RECEIPT_SEAL_FAILED",
          "EffectReceipt sealing failed",
          () =>
            sealEffectReceipt({
              error_artifact_ids: [],
              external_operation_id: null,
              finished_at: finishedAt,
              idempotency_key: readDataProperty(intent, "idempotency_key"),
              intent_id: readDataProperty(intent, "intent_id"),
              observed_state_hash: artifactWrite.content_hash,
              receipt_id: effectReceiptId,
              reconciliation_required: false,
              result_artifact_ids: [artifactWrite.artifact_id],
              run_id: readDataProperty(intent, "run_id"),
              started_at: readDataProperty(attempt, "started_at"),
              status: "SUCCEEDED",
            }),
        );
        const sealedEffectReceipt = snapshotPlainData(
          sealedEffectReceiptCandidate,
          "sealed EffectReceipt",
        );
        const validatedEffectReceiptCandidate = await callPort(
          state,
          "effect_receipt_validation",
          "EFFECT_RECEIPT_INVALID",
          "sealed EffectReceipt validation failed",
          () => validateEffectReceipt(sealedEffectReceipt),
        );
        const validatedEffectReceipt = snapshotPlainData(
          validatedEffectReceiptCandidate,
          "validated EffectReceipt",
        );
        if (!isDeepStrictEqual(validatedEffectReceipt, sealedEffectReceipt)) {
          failAdapterExecution(
            "EFFECT_RECEIPT_SEMANTIC_MISMATCH",
            "EffectReceipt validator changed the sealed receipt",
            errorState(state, "effect_receipt_validation"),
          );
        }
        const effectReceipt = assertEffectReceiptBinding(
          validatedEffectReceipt,
          effectReceiptId,
          intent,
          attempt,
          artifactWrite,
          finishedAt,
        );
        state.receiptState = "UNKNOWN";
        const receiptRecordResult = await callPort(
          state,
          "effect_receipt_record",
          "EFFECT_RECEIPT_RECORD_FAILED",
          "EffectReceipt recording failed",
          () =>
            recordReceipt({
              attempt_id: attemptId,
              receipt: effectReceipt,
            }),
        );
        const receiptRecordSnapshot = snapshotPlainData(
          receiptRecordResult,
          "recordReceipt result",
        );
        assertRecordedReceipt(receiptRecordSnapshot, effectReceipt);
        state.receiptState = "CONFIRMED";

        const resultEnvelope = snapshotPlainData({
          run_id: readDataProperty(invocation, "run_id"),
          node_id: readDataProperty(invocation, "node_id"),
          attempt: readDataProperty(invocation, "attempt"),
          status: "success",
          output_artifact_ids: [artifactWrite.artifact_id],
          evidence_ids: [],
          errors: [],
          metrics: {},
          input_hash: readDataProperty(invocation, "input_hash"),
          output_hash: artifactWrite.content_hash,
          started_at: readDataProperty(attempt, "started_at"),
          finished_at: finishedAt,
          completeness: businessValidation.completeness,
          effect_receipt_ids: [effectReceiptId],
          policy_decision_ids: [authorizationDecision.authorization_id],
          schema_validation_report_id:
            businessValidation.schema_validation_report_id,
          terminal_reason: LOCAL_SCRIPTED_TERMINAL_REASON,
        }, "ResultEnvelope preimage");
        const validatedEnvelopeCandidate = await callPort(
          state,
          "result_envelope_validation",
          "RESULT_ENVELOPE_INVALID",
          "ResultEnvelope validation failed",
          () => validateResultEnvelope(resultEnvelope),
        );
        const validatedEnvelope = snapshotPlainData(
          validatedEnvelopeCandidate,
          "validated ResultEnvelope",
        );
        if (!isDeepStrictEqual(validatedEnvelope, resultEnvelope)) {
          failAdapterExecution(
            "RESULT_ENVELOPE_SEMANTIC_MISMATCH",
            "ResultEnvelope validator changed the bounded execution result",
            errorState(state, "result_envelope_validation"),
          );
        }
        return deepFreeze(validatedEnvelope);
      } catch (error) {
        const internal = error instanceof AdapterExecutionError;
        const failureStage =
          internal && error.stage !== "preflight" ? error.stage : state.stage;
        throw wrapAdapterExecutionError(
          error,
          internal ? error.code : "BOUNDED_ADAPTER_EXECUTION_FAILED",
          internal ? error.message : "bounded adapter execution failed",
          {
            ...errorState(state, failureStage),
            details: internal ? error.details : undefined,
          },
        );
      }
    },
  };
  return Object.freeze(executor);
};
