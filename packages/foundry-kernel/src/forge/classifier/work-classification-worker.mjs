import { createEffectCoordinator } from "../../effects/effect-coordinator.mjs";
import {
  createDurableMutationOrchestrator,
} from "../../effects/durable-mutation-orchestrator.mjs";
import {
  getCapabilityAuthorityDependencyIdentity,
} from "../../capabilities/capability-authority.mjs";

import {
  ARRAY_IS_ARRAY,
  IS_PROXY,
  OBJECT_FREEZE,
  detached,
  exactKeys,
  hashBytes,
  hashJson,
  readDataProperty,
  requireDenseArray,
  requireHash,
  requirePlainRecord,
  requireString,
  requireTimestamp,
  sameCanonical,
} from "../session/canonical-json.mjs";
import {
  CLASSIFICATION_RECORD_TYPES,
  EpistemicWorkClassifierError,
  classify_epistemic_work,
} from "./classification-committer.mjs";
import {
  resolveClassificationWorkerAuthority,
} from "./classification-worker-authority.mjs";
import {
  canonicalizeClassificationJson,
  sha256ClassificationJson,
} from "./epistemic-work-classifier.mjs";

const TOOL_NAME = "foundry.work.classify";
const HANDLER_OPERATION = "mutate_work_classify";
const REQUIRED_CAPABILITY = "mcp.write.classification";
const CATALOG_RISK_CLASS = "medium";
const APPROVAL_CLASS = "POLICY_CONDITIONAL";
const ACTION_RISK_CLASS = "controlled_effect";
const NODE_ID = "T02/foundry.work.classify/mutate_work_classify";
const IDENTITY_CONTRACT = "T02_WORK_CLASSIFICATION_WORKER_V1";
const DRY_RUN_OPERATION_ID = "urn:epistemic-foundry:non-effect:dry-run";
const PROTOCOL_VERSION = "2026-07-28";
const ARGUMENTS_PROVENANCE_ID = "PROV-T02-work-classification-arguments";
const ARGUMENTS_ENCRYPTION_KEY_REF = "local://t02-work-classification-arguments";
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const CLASSIFICATION_ID_PATTERN = /^EWC-[0-9a-f]{64}$/u;

const REQUEST_KEYS = OBJECT_FREEZE([
  "tool_name",
  "handler_operation",
  "capability",
  "risk_class",
  "approval_class",
  "expected_revision_required",
  "validated_arguments",
  "auth",
  "semantic_fingerprint",
  "request_id",
  "generated_at",
]);
const MUTATION_ARGUMENT_KEYS = OBJECT_FREEZE([
  "workspace_id",
  "dry_run",
  "expected_revision",
  "idempotency_key",
  "approval_record_ids",
  "target_ref",
  "arguments",
]);
const RUNTIME_REQUEST_FACTORY_KEYS = OBJECT_FREEZE([
  "auth",
  "validatedArguments",
  "requestId",
  "generatedAt",
]);
const PREPARATION_RESULT_KEYS = OBJECT_FREEZE([
  "status",
  "classification_id",
  "classification_hash",
  "request_id",
  "run_id",
  "outbox_id",
]);
const REPLAY_PROJECTION_KEYS = OBJECT_FREEZE([
  "projection_version",
  "classification",
  "identity_context",
  "artifact_binding",
  "ledger_binding",
  "projection_hash",
  "projection_id",
]);

export class WorkClassificationWorkerError extends Error {
  constructor(code, message, details = undefined, options = undefined) {
    super(message, options);
    this.name = "WorkClassificationWorkerError";
    this.code = code;
    if (details !== undefined) this.details = detached(details);
  }
}

export class MutationRuntimeUnavailableError extends WorkClassificationWorkerError {
  constructor(reason, details = undefined) {
    super("MUTATION_RUNTIME_UNAVAILABLE", reason, details);
    this.name = "MutationRuntimeUnavailableError";
    this.reason = reason;
  }
}

const fail = (code, message, details = undefined, options = undefined) => {
  throw new WorkClassificationWorkerError(code, message, details, options);
};

const unavailable = (reason, details = undefined) => {
  throw new MutationRuntimeUnavailableError(reason, details);
};

const dependencyCauseCode = (error) =>
  error !== null && typeof error === "object" && typeof error.code === "string"
    ? error.code
    : error instanceof Error
      ? error.name
      : "unknown";

const dependencyMethod = (dependency, method, label) => {
  if (
    dependency === null ||
    !["object", "function"].includes(typeof dependency) ||
    IS_PROXY(dependency) ||
    typeof dependency[method] !== "function"
  ) {
    fail("WORK_CLASSIFICATION_INVALID_DEPENDENCY", `${label}.${method} is required`);
  }
};

const canonicalTimestamp = (candidate, label) => {
  const value = candidate instanceof Date ? candidate.toISOString() : candidate;
  requireTimestamp(value, label, "WORK_CLASSIFICATION_INPUT_INVALID");
  const canonical = new Date(value).toISOString();
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/u.test(canonical)) {
    fail("WORK_CLASSIFICATION_INPUT_INVALID", `${label} is outside the canonical range`);
  }
  return canonical;
};

const timestampFromClock = (clock) => {
  let value;
  try {
    value = clock();
  } catch (error) {
    fail("WORK_CLASSIFICATION_CLOCK_FAILED", "worker clock failed", undefined, {
      cause: error,
    });
  }
  if (value !== null && ["object", "function"].includes(typeof value) && "then" in value) {
    fail("WORK_CLASSIFICATION_ASYNC_CLOCK_DENIED", "worker clock must be synchronous");
  }
  return canonicalTimestamp(value, "clock result");
};

const latestTimestamp = (...values) =>
  values.reduce((latest, candidate) =>
    Date.parse(candidate) > Date.parse(latest) ? candidate : latest);

const freezeJson = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of Reflect.ownKeys(value)) freezeJson(value[key]);
  return OBJECT_FREEZE(value);
};

const classificationJsonClone = (value) =>
  freezeJson(JSON.parse(canonicalizeClassificationJson(value)));

const sameClassificationJson = (left, right) =>
  canonicalizeClassificationJson(left) === canonicalizeClassificationJson(right);

const requireUniqueStrings = (
  candidate,
  label,
  { min = 1, max = undefined, sort = true } = {},
) => {
  const entries = requireDenseArray(
    candidate,
    label,
    "WORK_CLASSIFICATION_INPUT_INVALID",
  ).map((entry, index) =>
    requireString(entry, `${label}[${index}]`, {
      min,
      max,
      code: "WORK_CLASSIFICATION_INPUT_INVALID",
    }));
  if (new Set(entries).size !== entries.length) {
    fail("WORK_CLASSIFICATION_INPUT_INVALID", `${label} contains duplicate values`);
  }
  return OBJECT_FREEZE(sort ? [...entries].sort() : [...entries]);
};

const normalizeClassificationArguments = (candidate) => {
  const value = requirePlainRecord(candidate, "classification arguments", {
    code: "WORK_CLASSIFICATION_INPUT_INVALID",
  });
  try {
    classify_epistemic_work(value);
    return classificationJsonClone(value);
  } catch (error) {
    if (error instanceof EpistemicWorkClassifierError) {
      fail(
        "WORK_CLASSIFICATION_INPUT_INVALID",
        "classification arguments were rejected by F01",
        { causeCode: dependencyCauseCode(error) },
        { cause: error },
      );
    }
    throw error;
  }
};

const semanticFingerprintFor = ({ auth, validatedArguments }) => {
  try {
    return sha256ClassificationJson({
      arguments: readDataProperty(validatedArguments, "arguments"),
      dry_run: readDataProperty(validatedArguments, "dry_run"),
      expected_revision: readDataProperty(validatedArguments, "expected_revision"),
      principal_id: readDataProperty(auth, "principal_id"),
      protocol_version: PROTOCOL_VERSION,
      target_ref: readDataProperty(validatedArguments, "target_ref"),
      tool: TOOL_NAME,
      workspace_id: readDataProperty(validatedArguments, "workspace_id"),
    });
  } catch (error) {
    if (error instanceof EpistemicWorkClassifierError) {
      fail(
        "WORK_CLASSIFICATION_INPUT_INVALID",
        "runtime request is not canonical F01 JSON",
        { causeCode: dependencyCauseCode(error) },
        { cause: error },
      );
    }
    throw error;
  }
};

const normalizeInvocation = (candidate) => {
  const request = exactKeys(
    candidate,
    REQUEST_KEYS,
    "work classification worker request",
    "WORK_CLASSIFICATION_INPUT_INVALID",
  );
  const toolName = readDataProperty(request, "tool_name");
  const handlerOperation = readDataProperty(request, "handler_operation");
  if (toolName !== TOOL_NAME || handlerOperation !== HANDLER_OPERATION) {
    unavailable("the injected Node mutation runtime does not implement this operation", {
      handlerOperation,
      toolName,
    });
  }
  if (
    readDataProperty(request, "capability") !== REQUIRED_CAPABILITY ||
    readDataProperty(request, "risk_class") !== CATALOG_RISK_CLASS ||
    readDataProperty(request, "approval_class") !== APPROVAL_CLASS ||
    readDataProperty(request, "expected_revision_required") !== false
  ) {
    unavailable("the foundry.work.classify catalog binding is unavailable");
  }
  const outer = exactKeys(
    readDataProperty(request, "validated_arguments"),
    MUTATION_ARGUMENT_KEYS,
    "validated_arguments",
    "WORK_CLASSIFICATION_INPUT_INVALID",
  );
  const classificationArguments = normalizeClassificationArguments(
    readDataProperty(outer, "arguments"),
  );
  const dryRun = readDataProperty(outer, "dry_run");
  if (typeof dryRun !== "boolean") {
    fail("WORK_CLASSIFICATION_INPUT_INVALID", "dry_run must be boolean");
  }
  if (readDataProperty(outer, "expected_revision") !== null) {
    fail("WORK_CLASSIFICATION_BINDING_MISMATCH", "expected_revision must be null");
  }
  const auth = requirePlainRecord(readDataProperty(request, "auth"), "auth", {
    code: "WORK_CLASSIFICATION_INPUT_INVALID",
  });
  const authPrincipalId = requireString(
    readDataProperty(auth, "principal_id"),
    "auth.principal_id",
    { min: 3, code: "WORK_CLASSIFICATION_INPUT_INVALID" },
  );
  const workspaceId = requireString(
    readDataProperty(outer, "workspace_id"),
    "workspace_id",
    { min: 1, code: "WORK_CLASSIFICATION_INPUT_INVALID" },
  );
  const authWorkspaceId = Object.hasOwn(auth, "workspace_id")
    ? requireString(readDataProperty(auth, "workspace_id"), "auth.workspace_id", {
        min: 1,
        code: "WORK_CLASSIFICATION_INPUT_INVALID",
      })
    : null;
  if (authWorkspaceId !== null && authWorkspaceId !== workspaceId) {
    fail("WORK_CLASSIFICATION_BINDING_MISMATCH", "authenticated workspace differs from request");
  }
  const targetRef = requireString(readDataProperty(outer, "target_ref"), "target_ref", {
    min: 1,
    code: "WORK_CLASSIFICATION_INPUT_INVALID",
  });
  if (targetRef !== classificationArguments.request_id) {
    fail(
      "WORK_CLASSIFICATION_BINDING_MISMATCH",
      "target_ref must equal classification arguments.request_id",
    );
  }
  const semanticFingerprint = readDataProperty(request, "semantic_fingerprint");
  if (typeof semanticFingerprint !== "string" || !SHA256_PATTERN.test(semanticFingerprint)) {
    fail("WORK_CLASSIFICATION_INPUT_INVALID", "semantic_fingerprint is not canonical SHA-256");
  }
  const expectedFingerprint = semanticFingerprintFor({ auth, validatedArguments: outer });
  if (semanticFingerprint !== expectedFingerprint) {
    fail("WORK_CLASSIFICATION_BINDING_MISMATCH", "semantic_fingerprint changed");
  }
  return OBJECT_FREEZE({
    approvalRecordIds: requireUniqueStrings(
      readDataProperty(outer, "approval_record_ids"),
      "approval_record_ids",
    ),
    authPrincipalId,
    authWorkspaceId,
    classificationArguments,
    dryRun,
    expectedRevision: null,
    generatedAt: canonicalTimestamp(readDataProperty(request, "generated_at"), "generated_at"),
    idempotencyKey: requireString(
      readDataProperty(outer, "idempotency_key"),
      "idempotency_key",
      { min: 1, max: 200, code: "WORK_CLASSIFICATION_INPUT_INVALID" },
    ),
    requestId: requireString(readDataProperty(request, "request_id"), "request_id", {
      min: 1,
      code: "WORK_CLASSIFICATION_INPUT_INVALID",
    }),
    runId: classificationArguments.run_id,
    semanticFingerprint,
    targetRef,
    workspaceId,
  });
};

export const createWorkClassificationRuntimeRequest = (candidate) => {
  const value = exactKeys(
    candidate,
    RUNTIME_REQUEST_FACTORY_KEYS,
    "work classification runtime request options",
    "WORK_CLASSIFICATION_INPUT_INVALID",
  );
  const auth = requirePlainRecord(readDataProperty(value, "auth"), "auth", {
    code: "WORK_CLASSIFICATION_INPUT_INVALID",
  });
  const validatedArguments = exactKeys(
    readDataProperty(value, "validatedArguments"),
    MUTATION_ARGUMENT_KEYS,
    "validatedArguments",
    "WORK_CLASSIFICATION_INPUT_INVALID",
  );
  const request = {
    tool_name: TOOL_NAME,
    handler_operation: HANDLER_OPERATION,
    capability: REQUIRED_CAPABILITY,
    risk_class: CATALOG_RISK_CLASS,
    approval_class: APPROVAL_CLASS,
    expected_revision_required: false,
    validated_arguments: validatedArguments,
    auth,
    semantic_fingerprint: semanticFingerprintFor({ auth, validatedArguments }),
    request_id: readDataProperty(value, "requestId"),
    generated_at: readDataProperty(value, "generatedAt"),
  };
  normalizeInvocation(request);
  return classificationJsonClone(request);
};

const normalizeDependencies = (options) => {
  const dependencyKeys = [
    "stateStore",
    "artifactStore",
    "ledger",
    "authority",
    "classification",
    "clock",
    "runtime",
  ];
  const value = exactKeys(
    options,
    dependencyKeys,
    "work classification worker options",
    "WORK_CLASSIFICATION_INVALID_DEPENDENCY",
  );
  const dependencies = Object.fromEntries(
    dependencyKeys.map((key) => [key, readDataProperty(value, key)]),
  );
  for (const method of [
    "transaction",
    "readRevisionedRecord",
    "createRevisionedRecord",
    "compareAndSwapRevision",
  ]) {
    dependencyMethod(dependencies.stateStore, method, "stateStore");
  }
  for (const method of [
    "putArtifact",
    "readArtifact",
    "readManifest",
    "readReceipt",
  ]) {
    dependencyMethod(dependencies.artifactStore, method, "artifactStore");
  }
  for (const method of ["append", "readEvents", "verifyRun"]) {
    dependencyMethod(dependencies.ledger, method, "ledger");
  }
  for (const method of [
    "issueLease",
    "commitWithLeaseDeferredEvent",
    "inspectLeaseUse",
    "reconcileLeaseUseEvent",
  ]) {
    dependencyMethod(dependencies.authority, method, "authority");
  }
  for (const method of ["classify", "readClassificationReplayProjection"]) {
    dependencyMethod(dependencies.classification, method, "classification");
  }
  if (typeof dependencies.clock !== "function" || IS_PROXY(dependencies.clock)) {
    fail(
      "WORK_CLASSIFICATION_INVALID_DEPENDENCY",
      "clock must be a trusted synchronous function",
    );
  }
  let authorityIdentity;
  let classificationAuthority;
  try {
    authorityIdentity = getCapabilityAuthorityDependencyIdentity(dependencies.authority);
    classificationAuthority = resolveClassificationWorkerAuthority(
      dependencies.classification,
      dependencies,
    );
  } catch (error) {
    fail(
      "WORK_CLASSIFICATION_INVALID_DEPENDENCY",
      "authority and classification must be canonical Kernel ports",
      { causeCode: dependencyCauseCode(error) },
      { cause: error },
    );
  }
  if (classificationAuthority === null) {
    fail(
      "WORK_CLASSIFICATION_DEPENDENCY_IDENTITY_MISMATCH",
      "classification does not share the worker dependencies",
    );
  }
  for (const [label, identity] of [["authority", authorityIdentity]]) {
    for (const key of ["stateStore", "artifactStore", "ledger", "clock"]) {
      if (identity[key] !== dependencies[key]) {
        fail(
          "WORK_CLASSIFICATION_DEPENDENCY_IDENTITY_MISMATCH",
          `${label} does not share the worker ${key}`,
        );
      }
    }
  }
  const effects = createEffectCoordinator({
    stateStore: dependencies.stateStore,
    artifactStore: dependencies.artifactStore,
    ledger: dependencies.ledger,
  });
  const runtime = exactKeys(
    dependencies.runtime,
    ["authorityPrincipalId", "workerPrincipalId", "leaseCommandFactory"],
    "work classification runtime config",
    "WORK_CLASSIFICATION_INVALID_DEPENDENCY",
  );
  const leaseCommandFactory = readDataProperty(runtime, "leaseCommandFactory");
  if (typeof leaseCommandFactory !== "function" || IS_PROXY(leaseCommandFactory)) {
    fail(
      "WORK_CLASSIFICATION_INVALID_DEPENDENCY",
      "runtime.leaseCommandFactory must be a trusted synchronous function",
    );
  }
  return OBJECT_FREEZE({
    ...dependencies,
    classificationAuthority,
    effects,
    runtime: OBJECT_FREEZE({
      authorityPrincipalId: requireString(
        readDataProperty(runtime, "authorityPrincipalId"),
        "runtime.authorityPrincipalId",
        { min: 3, code: "WORK_CLASSIFICATION_INVALID_DEPENDENCY" },
      ),
      workerPrincipalId: requireString(
        readDataProperty(runtime, "workerPrincipalId"),
        "runtime.workerPrincipalId",
        { min: 3, code: "WORK_CLASSIFICATION_INVALID_DEPENDENCY" },
      ),
      leaseCommandFactory,
    }),
  });
};

const identitiesFor = (invocation, argumentsHash) => {
  const digest = hashJson({
    contract: IDENTITY_CONTRACT,
    semantic_fingerprint: invocation.semanticFingerprint,
    idempotency_key: invocation.idempotencyKey,
    arguments_hash: argumentsHash,
    tool_name: TOOL_NAME,
    handler_operation: HANDLER_OPERATION,
  }).slice("sha256:".length);
  const argumentDigest = argumentsHash.slice("sha256:".length);
  return OBJECT_FREEZE({
    digest,
    argumentsArtifactId: `WCA-T02-${argumentDigest}`,
    argumentsReceiptId: `AR-WCA-T02-${argumentDigest}`,
    intentId: `AI-T02-${digest}`,
    attemptId: `ATT-T02-${digest}`,
    leaseId: `LEASE-T02-${digest}`,
    leaseUseOperationId: `USE-T02-${digest}`,
    dryReceiptId: `EFF-T02-NOT-EXECUTED-${digest}`,
    unknownReceiptId: `EFF-T02-UNKNOWN-${digest}`,
    successReceiptId: `EFF-T02-SUCCEEDED-${digest}`,
  });
};

const materializeArgumentsArtifact = ({
  dependencies,
  invocation,
  identities,
  bytes,
  contentHash,
  createdAt,
}) => {
  let stableCreatedAt = createdAt;
  try {
    const existingManifest = dependencies.artifactStore.readManifest(
      identities.argumentsArtifactId,
    );
    stableCreatedAt = canonicalTimestamp(
      existingManifest?.created_at,
      "classification arguments manifest.created_at",
    );
  } catch {
    // A missing deterministic registration is created below. Other D03 failures
    // remain fail-closed when putArtifact or the mandatory reopen is attempted.
  }
  const metadata = {
    artifact: {
      artifactId: identities.argumentsArtifactId,
      artifactType: "work_classification_arguments",
      confidentiality: "internal",
      createdAt: stableCreatedAt,
      createdBy: dependencies.runtime.workerPrincipalId,
      encryption: {
        atRest: true,
        inTransit: true,
        keyRef: ARGUMENTS_ENCRYPTION_KEY_REF,
      },
      inputArtifactIds: [],
      license: null,
      lineageEventIds: [],
      mediaType: "application/json",
      provenanceManifestId: ARGUMENTS_PROVENANCE_ID,
      retentionClass: "project",
    },
    receipt: {
      actionIntentId: null,
      createdAt: stableCreatedAt,
      createdBy: {
        actorId: dependencies.runtime.workerPrincipalId,
        actorType: "service",
      },
      receiptId: identities.argumentsReceiptId,
      schemaRef: null,
      validationResults: [
        {
          check: "f01_classification_input",
          status: "PASS",
          details: contentHash,
        },
      ],
    },
  };
  try {
    dependencies.artifactStore.putArtifact(bytes, metadata);
  } catch (error) {
    fail(
      "WORK_CLASSIFICATION_ARGUMENTS_UNAVAILABLE",
      "classification arguments could not be materialized through D03",
      { causeCode: dependencyCauseCode(error) },
      { cause: error },
    );
  }

  let reopened;
  let manifest;
  let receipt;
  try {
    reopened = dependencies.artifactStore.readArtifact(identities.argumentsArtifactId);
    manifest = dependencies.artifactStore.readManifest(identities.argumentsArtifactId);
    receipt = dependencies.artifactStore.readReceipt(identities.argumentsReceiptId);
  } catch (error) {
    fail(
      "WORK_CLASSIFICATION_ARGUMENTS_UNAVAILABLE",
      "classification arguments could not be reopened through D03",
      { causeCode: dependencyCauseCode(error) },
      { cause: error },
    );
  }
  if (!Buffer.isBuffer(reopened) && !(reopened instanceof Uint8Array)) {
    fail("WORK_CLASSIFICATION_ARGUMENTS_INVALID", "D03 did not return argument bytes");
  }
  const reopenedBytes = Buffer.from(reopened);
  if (
    !reopenedBytes.equals(bytes) ||
    hashBytes(reopenedBytes) !== contentHash ||
    manifest?.artifact_id !== identities.argumentsArtifactId ||
    manifest?.artifact_type !== "work_classification_arguments" ||
    manifest?.content_hash !== contentHash ||
    manifest?.created_at !== stableCreatedAt ||
    manifest?.created_by !== dependencies.runtime.workerPrincipalId ||
    manifest?.media_type !== "application/json" ||
    receipt?.receipt_id !== identities.argumentsReceiptId ||
    receipt?.artifact_id !== identities.argumentsArtifactId ||
    receipt?.action_intent_id !== null ||
    receipt?.content_hash !== contentHash ||
    receipt?.created_at !== stableCreatedAt ||
    receipt?.created_by?.actor_id !== dependencies.runtime.workerPrincipalId ||
    receipt?.created_by?.actor_type !== "service" ||
    receipt?.schema_ref !== null
  ) {
    fail(
      "WORK_CLASSIFICATION_ARGUMENTS_INVALID",
      "D03 classification argument binding changed",
    );
  }
  let parsed;
  try {
    parsed = JSON.parse(reopenedBytes.toString("utf8"));
  } catch (error) {
    fail(
      "WORK_CLASSIFICATION_ARGUMENTS_INVALID",
      "D03 classification arguments are malformed",
      undefined,
      { cause: error },
    );
  }
  if (
    canonicalizeClassificationJson(parsed) !== reopenedBytes.toString("utf8") ||
    !sameClassificationJson(parsed, invocation.classificationArguments)
  ) {
    fail(
      "WORK_CLASSIFICATION_ARGUMENTS_INVALID",
      "D03 classification arguments are not canonical",
    );
  }
  return OBJECT_FREEZE({
    artifactId: identities.argumentsArtifactId,
    contentHash,
    createdAt: stableCreatedAt,
  });
};

const normalizeLeaseCommand = (candidate, expected) => {
  const value = exactKeys(
    candidate,
    [
      "lease_id",
      "run_id",
      "principal_id",
      "capabilities",
      "resource_scopes",
      "expires_at",
      "approval_ids",
    ],
    "lease command factory result",
    "WORK_CLASSIFICATION_LEASE_COMMAND_INVALID",
  );
  const command = detached({
    lease_id: requireString(readDataProperty(value, "lease_id"), "lease_id", {
      min: 3,
      max: 128,
      code: "WORK_CLASSIFICATION_LEASE_COMMAND_INVALID",
    }),
    run_id: requireString(readDataProperty(value, "run_id"), "run_id", {
      min: 1,
      code: "WORK_CLASSIFICATION_LEASE_COMMAND_INVALID",
    }),
    principal_id: requireString(readDataProperty(value, "principal_id"), "principal_id", {
      min: 3,
      code: "WORK_CLASSIFICATION_LEASE_COMMAND_INVALID",
    }),
    capabilities: requireUniqueStrings(readDataProperty(value, "capabilities"), "capabilities"),
    resource_scopes: requireUniqueStrings(
      readDataProperty(value, "resource_scopes"),
      "resource_scopes",
    ),
    expires_at: canonicalTimestamp(readDataProperty(value, "expires_at"), "expires_at"),
    approval_ids: requireUniqueStrings(readDataProperty(value, "approval_ids"), "approval_ids"),
  });
  if (
    command.lease_id !== expected.leaseId ||
    command.run_id !== expected.runId ||
    command.principal_id !== expected.workerPrincipalId ||
    !sameCanonical(command.capabilities, [REQUIRED_CAPABILITY]) ||
    !sameCanonical(command.approval_ids, expected.approvalRecordIds)
  ) {
    fail(
      "WORK_CLASSIFICATION_LEASE_COMMAND_INVALID",
      "lease command factory escaped its deterministic policy-bound request",
    );
  }
  return command;
};

const issueLease = (dependencies, context) => {
  let candidate;
  try {
    candidate = dependencies.runtime.leaseCommandFactory(detached(context));
  } catch (error) {
    fail(
      "WORK_CLASSIFICATION_LEASE_COMMAND_FAILED",
      "lease command factory failed",
      undefined,
      { cause: error },
    );
  }
  if (candidate !== null && ["object", "function"].includes(typeof candidate) && "then" in candidate) {
    fail(
      "WORK_CLASSIFICATION_LEASE_COMMAND_FAILED",
      "lease command factory must be synchronous",
    );
  }
  const command = normalizeLeaseCommand(candidate, context);
  let lease;
  try {
    lease = dependencies.authority.issueLease(
      dependencies.runtime.authorityPrincipalId,
      command,
    );
  } catch (error) {
    if (error?.code !== "CAPABILITY_EVENT_RECONCILIATION_REQUIRED") throw error;
    lease = dependencies.authority.issueLease(
      dependencies.runtime.authorityPrincipalId,
      command,
    );
  }
  if (
    lease?.lease_id !== command.lease_id ||
    lease?.principal_id !== command.principal_id ||
    lease?.revoked !== false ||
    !sameCanonical(lease?.capabilities, command.capabilities) ||
    !sameCanonical(lease?.resource_scopes, command.resource_scopes) ||
    !sameCanonical(lease?.approval_ids, command.approval_ids)
  ) {
    fail("WORK_CLASSIFICATION_LEASE_INVALID", "E03 returned a lease outside the request binding");
  }
  requireHash(lease.lease_hash, "lease.lease_hash", "WORK_CLASSIFICATION_LEASE_INVALID");
  return OBJECT_FREEZE({ command, lease });
};

const normalizePreparationResult = (candidate, invocation) => {
  const value = exactKeys(
    candidate,
    PREPARATION_RESULT_KEYS,
    "F01 classification preparation result",
    "WORK_CLASSIFICATION_PREPARATION_INVALID",
  );
  if (!new Set(["CREATED", "EXISTING"]).has(value.status)) {
    fail("WORK_CLASSIFICATION_PREPARATION_INVALID", "F01 preparation status is invalid");
  }
  const classificationId = requireString(value.classification_id, "classification_id", {
    code: "WORK_CLASSIFICATION_PREPARATION_INVALID",
  });
  const classificationHash = requireHash(
    value.classification_hash,
    "classification_hash",
    "WORK_CLASSIFICATION_PREPARATION_INVALID",
  );
  if (
    !CLASSIFICATION_ID_PATTERN.test(classificationId) ||
    classificationId !== `EWC-${classificationHash.slice("sha256:".length)}` ||
    value.request_id !== invocation.classificationArguments.request_id ||
    value.run_id !== invocation.runId
  ) {
    fail(
      "WORK_CLASSIFICATION_PREPARATION_INVALID",
      "F01 preparation changed classification identity",
    );
  }
  requireString(value.outbox_id, "outbox_id", {
    code: "WORK_CLASSIFICATION_PREPARATION_INVALID",
  });
  return detached(value);
};

const normalizeClassificationResult = (candidate, prepared) => {
  const result = requirePlainRecord(candidate, "F01 classification result", {
    code: "WORK_CLASSIFICATION_RESULT_INVALID",
  });
  const classification = requirePlainRecord(
    readDataProperty(result, "classification"),
    "F01 classification result.classification",
    { code: "WORK_CLASSIFICATION_RESULT_INVALID" },
  );
  if (
    readDataProperty(result, "status") !== "EXISTING" ||
    readDataProperty(classification, "classification_id") !== prepared.classification_id ||
    readDataProperty(classification, "classification_hash") !== prepared.classification_hash ||
    readDataProperty(classification, "request_id") !== prepared.request_id
  ) {
    fail(
      "WORK_CLASSIFICATION_RESULT_INVALID",
      "published F01 result differs from its preparation",
    );
  }
  return classification;
};

const normalizeReplayProjection = ({ candidate, prepared }) => {
  const value = exactKeys(
    candidate,
    REPLAY_PROJECTION_KEYS,
    "F01 replay projection",
    "WORK_CLASSIFICATION_RECOVERY_INVALID",
  );
  const classification = requirePlainRecord(value.classification, "F01 replay classification", {
    code: "WORK_CLASSIFICATION_RECOVERY_INVALID",
  });
  const artifactBinding = requirePlainRecord(
    value.artifact_binding,
    "F01 replay artifact binding",
    { code: "WORK_CLASSIFICATION_RECOVERY_INVALID" },
  );
  const ledgerBinding = requirePlainRecord(
    value.ledger_binding,
    "F01 replay ledger binding",
    { code: "WORK_CLASSIFICATION_RECOVERY_INVALID" },
  );
  const projectionHash = requireHash(
    value.projection_hash,
    "projection_hash",
    "WORK_CLASSIFICATION_RECOVERY_INVALID",
  );
  if (
    value.projection_version !== "DURABLE_FORGE_V1" ||
    value.projection_id !== `F01RP-${projectionHash.slice("sha256:".length)}` ||
    classification.classification_id !== prepared.classification_id ||
    classification.classification_hash !== prepared.classification_hash ||
    classification.request_id !== prepared.request_id ||
    artifactBinding.artifact_id !== prepared.classification_id ||
    ledgerBinding.run_id !== prepared.run_id
  ) {
    fail("WORK_CLASSIFICATION_RECOVERY_INVALID", "F01 replay binding changed");
  }
  for (const key of ["content_hash", "artifact_manifest_hash", "receipt_hash"]) {
    requireHash(
      artifactBinding[key],
      `artifact_binding.${key}`,
      "WORK_CLASSIFICATION_RECOVERY_INVALID",
    );
  }
  for (const key of ["event_hash", "payload_hash"]) {
    requireHash(
      ledgerBinding[key],
      `ledger_binding.${key}`,
      "WORK_CLASSIFICATION_RECOVERY_INVALID",
    );
  }
  if (
    typeof ledgerBinding.sequence !== "number" ||
    !Number.isSafeInteger(ledgerBinding.sequence) ||
    ledgerBinding.sequence < 1 ||
    ledgerBinding.payload_hash !== artifactBinding.content_hash
  ) {
    fail("WORK_CLASSIFICATION_RECOVERY_INVALID", "F01 ledger binding is invalid");
  }
  requireString(ledgerBinding.event_id, "ledger_binding.event_id", {
    code: "WORK_CLASSIFICATION_RECOVERY_INVALID",
  });
  return detached(value);
};

const normalizeLeaseUseInspection = ({ candidate, context, lease }) => {
  if (candidate === null) return null;
  const value = exactKeys(
    candidate,
    [
      "status",
      "operation_id",
      "request_hash",
      "lease_id",
      "fencing_token",
      "result",
      "lease_use_id",
      "lease_use_hash",
      "event_outbox_id",
      "event_publication_status",
      "event",
    ],
    "E03 lease-use inspection",
    "WORK_CLASSIFICATION_RECOVERY_INVALID",
  );
  const event = exactKeys(
    value.event,
    [
      "event_id",
      "run_id",
      "event_type",
      "aggregate_type",
      "aggregate_id",
      "actor_id",
      "payload_artifact_id",
      "occurred_at",
      "schema_version",
      "event_hash",
    ],
    "E03 lease-use event binding",
    "WORK_CLASSIFICATION_RECOVERY_INVALID",
  );
  if (
    value.status !== "COMMITTED" ||
    value.operation_id !== context.identities.leaseUseOperationId ||
    value.lease_id !== lease.lease_id ||
    value.fencing_token !== lease.fencing_token ||
    event.run_id !== context.intent.run_id ||
    event.event_type !== "capability.lease-use.committed" ||
    event.aggregate_type !== "capability_lease" ||
    event.aggregate_id !== lease.lease_id ||
    event.actor_id !== context.workerPrincipalId ||
    event.schema_version !== "4.0.0"
  ) {
    fail("WORK_CLASSIFICATION_RECOVERY_INVALID", "E03 lease-use recovery binding changed");
  }
  for (const key of ["request_hash", "lease_use_hash"]) {
    requireHash(value[key], `lease use.${key}`, "WORK_CLASSIFICATION_RECOVERY_INVALID");
  }
  for (const key of ["lease_use_id", "event_outbox_id"]) {
    requireString(value[key], `lease use.${key}`, {
      code: "WORK_CLASSIFICATION_RECOVERY_INVALID",
    });
  }
  if (
    !new Set(["PUBLISHED", "PENDING_EVENT_RECONCILIATION"]).has(
      value.event_publication_status,
    ) ||
    (value.event_publication_status === "PUBLISHED") !== (event.event_hash !== null)
  ) {
    fail("WORK_CLASSIFICATION_RECOVERY_INVALID", "E03 event publication state is invalid");
  }
  requireString(event.event_id, "lease use event.event_id", {
    code: "WORK_CLASSIFICATION_RECOVERY_INVALID",
  });
  requireString(event.payload_artifact_id, "lease use event.payload_artifact_id", {
    code: "WORK_CLASSIFICATION_RECOVERY_INVALID",
  });
  canonicalTimestamp(event.occurred_at, "lease use event.occurred_at");
  if (event.event_hash !== null) {
    requireHash(
      event.event_hash,
      "lease use event.event_hash",
      "WORK_CLASSIFICATION_RECOVERY_INVALID",
    );
  }
  return detached(value);
};

const readLedgerEvents = (ledger, runId) => {
  let events;
  try {
    events = ledger.readEvents(runId);
  } catch (error) {
    fail("WORK_CLASSIFICATION_LEDGER_INVALID", "E01 readEvents failed", undefined, {
      cause: error,
    });
  }
  if (!ARRAY_IS_ARRAY(events)) {
    fail("WORK_CLASSIFICATION_LEDGER_INVALID", "E01 readEvents did not return an array");
  }
  const eventIds = new Set();
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    if (
      event?.sequence !== index + 1 ||
      event?.run_id !== runId ||
      typeof event.event_id !== "string" ||
      eventIds.has(event.event_id)
    ) {
      fail("WORK_CLASSIFICATION_LEDGER_INVALID", "E01 event sequence or identity is invalid");
    }
    requireHash(event.event_hash, "event.event_hash", "WORK_CLASSIFICATION_LEDGER_INVALID");
    eventIds.add(event.event_id);
  }
  return events;
};

const ledgerProvesClassificationBeforeLeaseUse = ({ ledger, replay, leaseUse }) => {
  const events = readLedgerEvents(ledger, replay.ledger_binding.run_id);
  const byId = new Map(events.map((event) => [event.event_id, event]));
  const classificationEvent = byId.get(replay.ledger_binding.event_id);
  const leaseUseEvent = byId.get(leaseUse.event.event_id);
  if (classificationEvent === undefined || leaseUseEvent === undefined) return false;
  if (
    classificationEvent.sequence !== replay.ledger_binding.sequence ||
    classificationEvent.event_hash !== replay.ledger_binding.event_hash ||
    classificationEvent.payload_hash !== replay.ledger_binding.payload_hash ||
    classificationEvent.sequence >= leaseUseEvent.sequence ||
    leaseUseEvent.event_hash !== leaseUse.event.event_hash
  ) {
    return false;
  }
  for (const key of [
    "event_id",
    "run_id",
    "event_type",
    "aggregate_type",
    "aggregate_id",
    "actor_id",
    "payload_artifact_id",
    "occurred_at",
    "schema_version",
  ]) {
    if (leaseUseEvent[key] !== leaseUse.event[key]) return false;
  }
  return true;
};

const mutationPayload = ({ invocation, leaseId, outcome }) => {
  const receipt = outcome.receipt;
  if (receipt === null || receipt === undefined) {
    fail("WORK_CLASSIFICATION_RECEIPT_MISSING", "E02 outcome has no EffectReceipt");
  }
  const status = receipt.status;
  const committed = status === "UNKNOWN" ? null : status === "SUCCEEDED";
  let newRevision = null;
  if (status === "SUCCEEDED") {
    if (
      receipt.result_artifact_ids.length !== 1 ||
      !CLASSIFICATION_ID_PATTERN.test(receipt.result_artifact_ids[0])
    ) {
      fail(
        "WORK_CLASSIFICATION_RESULT_INVALID",
        "successful E02 receipt does not bind one F01 classification",
      );
    }
    newRevision = receipt.result_artifact_ids[0];
  }
  return detached({
    mutation: {
      action_intent_id: outcome.intent.intent_id,
      capability_lease_id: leaseId,
      effect_receipt_id: receipt.receipt_id,
      dry_run: invocation.dryRun,
      effect_status: status,
      committed,
      expected_revision: null,
      observed_revision: null,
      new_revision: newRevision,
      reconciliation_required: status === "UNKNOWN",
    },
    preview: null,
  });
};

const unknownClassificationReceiptInput = ({ dependencies, context, prepared }) => ({
  receipt_id: context.identities.unknownReceiptId,
  intent_id: context.intent.intent_id,
  run_id: context.intent.run_id,
  external_operation_id: prepared?.outbox_id ?? null,
  status: "UNKNOWN",
  result_artifact_ids: [],
  error_artifact_ids: [],
  observed_state_hash: context.argumentsHash,
  idempotency_key: context.invocation.idempotencyKey,
  started_at: context.attempt.started_at,
  finished_at: latestTimestamp(
    context.attempt.started_at,
    timestampFromClock(dependencies.clock),
  ),
  reconciliation_required: true,
});

const dryRunClassificationReceiptInput = ({ dependencies, context, outcome }) => ({
  receipt_id: context.identities.dryReceiptId,
  intent_id: context.intent.intent_id,
  run_id: context.intent.run_id,
  external_operation_id: DRY_RUN_OPERATION_ID,
  status: "NOT_EXECUTED",
  result_artifact_ids: [],
  error_artifact_ids: [],
  observed_state_hash: context.argumentsHash,
  idempotency_key: context.invocation.idempotencyKey,
  started_at: context.attempt.started_at,
  finished_at: latestTimestamp(
    context.attempt.started_at,
    outcome.receipt?.finished_at ?? context.attempt.started_at,
    timestampFromClock(dependencies.clock),
  ),
  reconciliation_required: false,
});

const succeededClassificationReceiptInput = ({
  dependencies,
  context,
  outcome,
  prepared,
  replay,
}) => ({
  receipt_id: context.identities.successReceiptId,
  intent_id: context.intent.intent_id,
  run_id: context.intent.run_id,
  external_operation_id: prepared.outbox_id,
  status: "SUCCEEDED",
  result_artifact_ids: [prepared.classification_id],
  error_artifact_ids: [],
  observed_state_hash: replay.projection_hash,
  idempotency_key: context.invocation.idempotencyKey,
  started_at: context.attempt.started_at,
  finished_at: latestTimestamp(
    context.attempt.started_at,
    replay.classification.classified_at,
    outcome.receipt?.finished_at ?? context.attempt.started_at,
    timestampFromClock(dependencies.clock),
  ),
  reconciliation_required: false,
});

const RECOVERY_EVIDENCE_FAILURE_CODES = new Set([
  "WORK_CLASSIFICATION_RECOVERY_INVALID",
  "WORK_CLASSIFICATION_PREPARATION_INVALID",
  "WORK_CLASSIFICATION_INPUT_INVALID",
  "WORK_CLASSIFICATION_LEDGER_INVALID",
  "FORGE_NON_CANONICAL_JSON",
  "CAPABILITY_EVENT_RECONCILIATION_REQUIRED",
  "CAPABILITY_STATE_INTEGRITY_FAILED",
  "CAPABILITY_STATE_MISSING",
  "CLASSIFICATION_NOT_FOUND",
  "CLASSIFICATION_STATE_INTEGRITY_FAILED",
  "CLASSIFICATION_STATE_MISSING",
  "CLASSIFICATION_RECONCILIATION_REQUIRED",
  "CLASSIFICATION_INTEGRITY_FAILED",
  "REPLAY_DIVERGENCE",
]);

const isRecoveryEvidenceFailure = (error) =>
  error !== null &&
  typeof error === "object" &&
  RECOVERY_EVIDENCE_FAILURE_CODES.has(error.code);

const reconcilePublishedClassificationProof = ({ dependencies, context, lease, outcome }) => {
  let leaseUse = normalizeLeaseUseInspection({
    candidate: dependencies.authority.inspectLeaseUse(
      context.identities.leaseUseOperationId,
    ),
    context,
    lease,
  });
  if (leaseUse === null) return null;
  const prepared = normalizePreparationResult(leaseUse.result, context.invocation);
  if (
    outcome.receipt?.external_operation_id !== null &&
    outcome.receipt?.external_operation_id !== undefined &&
    outcome.receipt.external_operation_id !== prepared.outbox_id
  ) {
    fail(
      "WORK_CLASSIFICATION_RECOVERY_INVALID",
      "UNKNOWN receipt is bound to another F01 outbox",
    );
  }

  const replay = normalizeReplayProjection({
    candidate: dependencies.classification.readClassificationReplayProjection(
      prepared.classification_id,
    ),
    prepared,
  });
  if (leaseUse.event_publication_status !== "PUBLISHED") {
    leaseUse = normalizeLeaseUseInspection({
      candidate: dependencies.authority.reconcileLeaseUseEvent(
        context.identities.leaseUseOperationId,
      ),
      context,
      lease,
    });
  }
  if (
    leaseUse?.event_publication_status !== "PUBLISHED" ||
    !ledgerProvesClassificationBeforeLeaseUse({
      ledger: dependencies.ledger,
      replay,
      leaseUse,
    })
  ) {
    return null;
  }
  return OBJECT_FREEZE({
    prepared,
    effectResult: OBJECT_FREEZE({ replay }),
  });
};

const executeClassificationEffect = ({ dependencies, context, lease, setPrepared }) => {
  const leaseCommit = dependencies.authority.commitWithLeaseDeferredEvent(
    {
      operation_id: context.identities.leaseUseOperationId,
      run_id: context.invocation.runId,
      lease,
      principal_id: context.workerPrincipalId,
      capability: REQUIRED_CAPABILITY,
      resource_scopes: lease.resource_scopes,
    },
    (transactionStore) => dependencies.classificationAuthority.prepareClassification(
      transactionStore,
      context.invocation.classificationArguments,
    ),
    Object.values(CLASSIFICATION_RECORD_TYPES),
  );
  const prepared = normalizePreparationResult(leaseCommit.result, context.invocation);
  setPrepared(prepared);
  const classificationResult = dependencies.classification.classify(
    context.invocation.classificationArguments,
  );
  normalizeClassificationResult(classificationResult, prepared);
  const replay = normalizeReplayProjection({
    candidate: dependencies.classification.readClassificationReplayProjection(
      prepared.classification_id,
    ),
    prepared,
  });
  let leaseUse = normalizeLeaseUseInspection({
    candidate: dependencies.authority.inspectLeaseUse(
      context.identities.leaseUseOperationId,
    ),
    context,
    lease,
  });
  if (leaseUse === null) {
    fail("WORK_CLASSIFICATION_RESULT_INVALID", "E03 lease use is missing after F01 publication");
  }
  const inspectedPreparation = normalizePreparationResult(
    leaseUse.result,
    context.invocation,
  );
  if (!sameCanonical(inspectedPreparation, prepared)) {
    fail("WORK_CLASSIFICATION_RESULT_INVALID", "E03 and F01 operation bindings disagree");
  }
  if (leaseUse.event_publication_status !== "PUBLISHED") {
    leaseUse = normalizeLeaseUseInspection({
      candidate: dependencies.authority.reconcileLeaseUseEvent(
        context.identities.leaseUseOperationId,
      ),
      context,
      lease,
    });
  }
  if (
    leaseUse?.event_publication_status !== "PUBLISHED" ||
    !ledgerProvesClassificationBeforeLeaseUse({
      ledger: dependencies.ledger,
      replay,
      leaseUse,
    })
  ) {
    fail(
      "WORK_CLASSIFICATION_RESULT_INVALID",
      "E01 does not prove the required F01 then E03 publication order",
    );
  }
  return OBJECT_FREEZE({ replay });
};

const makeWorker = (dependencies) => createDurableMutationOrchestrator({
  behavior: OBJECT_FREEZE({
    existingDryRunAttemptInspectFallback: true,
    existingDryRunAttemptRequiresDefined: true,
    existingDryRunAttemptRequiresBoolean: true,
  }),
  effects: dependencies.effects,
  errors: OBJECT_FREEZE({
    effectInvalid: (message) => fail("WORK_CLASSIFICATION_EFFECT_INVALID", message),
    recoveryInvalid: (message) => fail("WORK_CLASSIFICATION_RECOVERY_INVALID", message),
    reconciliationRequired: (message, details = undefined, options = undefined) =>
      fail("WORK_CLASSIFICATION_RECONCILIATION_REQUIRED", message, details, options),
  }),
  hooks: OBJECT_FREEZE({
    bindOperation: ({ preparedCandidate, priorEffect }) => {
      const {
        argumentBytes,
        argumentsHash,
        identities,
        invocation,
      } = preparedCandidate;
      const startedAt = priorEffect?.intent?.created_at ?? invocation.generatedAt;
      materializeArgumentsArtifact({
        dependencies,
        invocation,
        identities,
        bytes: argumentBytes,
        contentHash: argumentsHash,
        createdAt: startedAt,
      });
      return OBJECT_FREEZE({
        argumentsHash,
        attemptId: identities.attemptId,
        dryRun: invocation.dryRun,
        identities,
        intentInput: {
          intent_id: identities.intentId,
          run_id: invocation.runId,
          node_id: NODE_ID,
          action_type: HANDLER_OPERATION,
          target_ref: invocation.targetRef,
          arguments_artifact_id: identities.argumentsArtifactId,
          arguments_hash: argumentsHash,
          idempotency_key: invocation.idempotencyKey,
          required_capabilities: [REQUIRED_CAPABILITY],
          approval_record_ids: invocation.approvalRecordIds,
          risk_class: ACTION_RISK_CLASS,
          created_at: startedAt,
        },
        invocation,
        startedAt,
      });
    },
    createContext: ({ attempt, intent, operation }) => OBJECT_FREEZE({
      argumentsHash: operation.argumentsHash,
      attempt,
      identities: operation.identities,
      intent,
      invocation: operation.invocation,
      workerPrincipalId: dependencies.runtime.workerPrincipalId,
    }),
    dryRunReceiptInput: ({ context, outcome }) => dryRunClassificationReceiptInput({
      dependencies,
      context,
      outcome,
    }),
    errorCode: dependencyCauseCode,
    executeEffect: ({ context, lease, setPrepared }) => executeClassificationEffect({
      dependencies,
      context,
      lease,
      setPrepared,
    }),
    existingAttemptReconciliationError: () => new WorkClassificationWorkerError(
      "WORK_CLASSIFICATION_EFFECT_RECONCILING",
      "an existing Attempt cannot dispatch the F01 effect again",
    ),
    isRecoveryEvidenceFailure,
    issueLease: ({ operation }) => {
      const leaseContext = detached({
        leaseId: operation.identities.leaseId,
        runId: operation.invocation.runId,
        workerPrincipalId: dependencies.runtime.workerPrincipalId,
        authPrincipalId: operation.invocation.authPrincipalId,
        approvalRecordIds: operation.invocation.approvalRecordIds,
        workspaceId: operation.invocation.workspaceId,
        targetRef: operation.invocation.targetRef,
        semanticFingerprint: operation.invocation.semanticFingerprint,
        idempotencyKey: operation.invocation.idempotencyKey,
        argumentsArtifactId: operation.identities.argumentsArtifactId,
        requestedAt: operation.startedAt,
      });
      return issueLease(dependencies, leaseContext).lease;
    },
    prepareCandidate: (candidate) => {
      const invocation = normalizeInvocation(candidate);
      const argumentBytes = Buffer.from(
        canonicalizeClassificationJson(invocation.classificationArguments),
        "utf8",
      );
      const argumentsHash = hashBytes(argumentBytes);
      const identities = identitiesFor(invocation, argumentsHash);
      return OBJECT_FREEZE({
        argumentBytes,
        argumentsHash,
        identities,
        intentId: identities.intentId,
        invocation,
      });
    },
    projectResult: ({ lease, operation, outcome }) => mutationPayload({
      invocation: operation.invocation,
      leaseId: lease === null ? operation.identities.leaseId : lease.lease_id,
      outcome,
    }),
    recoverEffect: ({ context, lease, outcome }) =>
      reconcilePublishedClassificationProof({ dependencies, context, lease, outcome }),
    sameRecord: sameCanonical,
    successReceiptInput: ({ context, effectResult, outcome, prepared }) =>
      succeededClassificationReceiptInput({
        dependencies,
        context,
        outcome,
        prepared,
        replay: effectResult.replay,
      }),
    unknownReceiptInput: ({ context, prepared }) => unknownClassificationReceiptInput({
      dependencies,
      context,
      prepared,
    }),
  }),
  messages: OBJECT_FREEZE({
    dryRunReconciliationRequired: "dry-run EffectReceipt event publication remains unresolved",
    existingDryRunAttemptPermitsExecution:
      "existing dry-run Attempt unexpectedly permits execution",
    omittedExecutePermitted: "E02 omitted execute_permitted",
    recoveryIdentityChanged: "E02 recovery identity changed",
    recoveredReconciliationRequired:
      "recovered EffectReceipt event publication remains unresolved",
    storedDryRunAttemptChanged: "stored dry-run Attempt binding changed",
    storedIntentChanged: "stored E02 ActionIntent differs from this semantic replay",
    successfulReconciliationRequired:
      "successful EffectReceipt event publication remains unresolved",
    terminalReconciliationRequired:
      "terminal E02 records still require event reconciliation",
    unknownIntentStatus: "E02 returned an unknown intent status",
    unknownReceiptPersistenceFailed:
      "post-Attempt failure could not be bound to an UNKNOWN EffectReceipt",
  }),
});

export const createWorkClassificationWorker = (options) =>
  makeWorker(normalizeDependencies(options));
