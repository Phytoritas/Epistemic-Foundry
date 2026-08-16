import { createEffectCoordinator } from "../../effects/effect-coordinator.mjs";
import {
  createDurableMutationOrchestrator,
} from "../../effects/durable-mutation-orchestrator.mjs";
import {
  getCapabilityAuthorityDependencyIdentity,
} from "../../capabilities/capability-authority.mjs";
import {
  assertClassificationArtifactIntegrity,
} from "../classifier/index.mjs";
import {
  resolveClassificationWorkerAuthority,
} from "../classifier/classification-worker-authority.mjs";

import {
  ARRAY_IS_ARRAY,
  IS_PROXY,
  NUMBER_IS_SAFE_INTEGER,
  OBJECT_FREEZE,
  canonicalJson,
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
} from "./canonical-json.mjs";
import {
  DURABLE_FORGE_SESSION_RECORD_TYPES,
} from "./durable-forge-session.mjs";
import {
  resolveDurableForgeSessionWorkerAuthority,
} from "./session-worker-authority.mjs";

const TOOL_NAME = "foundry.session.open";
const HANDLER_OPERATION = "mutate_session_open";
const REQUIRED_CAPABILITY = "mcp.write.session";
const CATALOG_RISK_CLASS = "medium";
const APPROVAL_CLASS = "POLICY_CONDITIONAL";
const ACTION_RISK_CLASS = "controlled_effect";
const NODE_ID = "T02/foundry.session.open/mutate_session_open";
const IDENTITY_CONTRACT = "T02_SESSION_OPEN_WORKER_V1";
const DRY_RUN_OPERATION_ID = "urn:epistemic-foundry:non-effect:dry-run";
const PROTOCOL_VERSION = "2026-07-28";
const OPEN_REQUEST_PROVENANCE_ID = "PROV-T02-forge-open-request";
const OPEN_REQUEST_ENCRYPTION_KEY_REF = "local://t02-forge-open-request";
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const ACTOR_TYPES = new Set(["human", "agent", "service"]);
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
const TOOL_ARGUMENT_KEYS = OBJECT_FREEZE([
  "session_id",
  "classification_id",
  "corpus_snapshot_hash",
  "actor",
  "requested_at",
]);
const OPEN_REQUEST_KEYS = OBJECT_FREEZE([
  "request_id",
  "session_id",
  "workspace_id",
  "run_spec_id",
  "classification_id",
  "policy_hash",
  "corpus_snapshot_hash",
  "actor",
  "idempotency_key",
  "requested_at",
]);
const RUNTIME_REQUEST_FACTORY_KEYS = OBJECT_FREEZE([
  "auth",
  "validatedArguments",
  "requestId",
  "generatedAt",
]);
const PREPARATION_RESULT_KEYS = OBJECT_FREEZE([
  "status",
  "operation_id",
  "outbox_id",
  "session_id",
  "request_hash",
  "payload_artifact_id",
  "candidate_state_hash",
  "expected_ledger_head",
  "expected_revision",
  "new_revision",
]);

export class SessionOpenWorkerError extends Error {
  constructor(code, message, details = undefined, options = undefined) {
    super(message, options);
    this.name = "SessionOpenWorkerError";
    this.code = code;
    if (details !== undefined) this.details = detached(details);
  }
}

export class SessionOpenRuntimeUnavailableError extends SessionOpenWorkerError {
  constructor(reason, details = undefined) {
    super("MUTATION_RUNTIME_UNAVAILABLE", reason, details);
    this.name = "SessionOpenRuntimeUnavailableError";
    this.reason = reason;
  }
}

const fail = (code, message, details = undefined, options = undefined) => {
  throw new SessionOpenWorkerError(code, message, details, options);
};

const unavailable = (reason, details = undefined) => {
  throw new SessionOpenRuntimeUnavailableError(reason, details);
};

const dependencyMethod = (dependency, method, label) => {
  if (
    dependency === null ||
    !["object", "function"].includes(typeof dependency) ||
    IS_PROXY(dependency) ||
    typeof dependency[method] !== "function"
  ) {
    fail("SESSION_OPEN_INVALID_DEPENDENCY", `${label}.${method} is required`);
  }
};

const canonicalTimestamp = (candidate, label) => {
  const value = candidate instanceof Date ? candidate.toISOString() : candidate;
  requireTimestamp(value, label, "SESSION_OPEN_INPUT_INVALID");
  const canonical = new Date(value).toISOString();
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/u.test(canonical)) {
    fail("SESSION_OPEN_INPUT_INVALID", `${label} is outside the canonical range`);
  }
  return canonical;
};

const timestampFromClock = (clock) => {
  let value;
  try {
    value = clock();
  } catch (error) {
    fail("SESSION_OPEN_CLOCK_FAILED", "worker clock failed", undefined, {
      cause: error,
    });
  }
  if (value !== null && ["object", "function"].includes(typeof value) && "then" in value) {
    fail("SESSION_OPEN_ASYNC_CLOCK_DENIED", "worker clock must be synchronous");
  }
  return canonicalTimestamp(value, "clock result");
};

const latestTimestamp = (...values) =>
  values.reduce((latest, candidate) =>
    Date.parse(candidate) > Date.parse(latest) ? candidate : latest);

const requireUniqueStrings = (
  candidate,
  label,
  { min = 1, max = undefined, sort = true } = {},
) => {
  const entries = requireDenseArray(candidate, label, "SESSION_OPEN_INPUT_INVALID").map(
    (entry, index) => requireString(entry, `${label}[${index}]`, {
      min,
      max,
      code: "SESSION_OPEN_INPUT_INVALID",
    }),
  );
  if (new Set(entries).size !== entries.length) {
    fail("SESSION_OPEN_INPUT_INVALID", `${label} contains duplicate values`);
  }
  return OBJECT_FREEZE(sort ? [...entries].sort() : [...entries]);
};

const normalizeOpenRequest = (candidate) => {
  const value = exactKeys(
    candidate,
    OPEN_REQUEST_KEYS,
    "ForgeOpenRequest",
    "SESSION_OPEN_REQUEST_INVALID",
  );
  const actor = exactKeys(
    readDataProperty(value, "actor"),
    ["actor_id", "actor_type", "role"],
    "ForgeOpenRequest.actor",
    "SESSION_OPEN_REQUEST_INVALID",
  );
  const actorType = readDataProperty(actor, "actor_type");
  if (!ACTOR_TYPES.has(actorType)) {
    fail("SESSION_OPEN_REQUEST_INVALID", "Forge open actor_type is invalid");
  }
  return detached({
    request_id: requireString(readDataProperty(value, "request_id"), "request_id", {
      min: 3,
      max: 128,
      code: "SESSION_OPEN_REQUEST_INVALID",
    }),
    session_id: requireString(readDataProperty(value, "session_id"), "session_id", {
      min: 3,
      max: 128,
      code: "SESSION_OPEN_REQUEST_INVALID",
    }),
    workspace_id: requireString(readDataProperty(value, "workspace_id"), "workspace_id", {
      min: 3,
      max: 128,
      code: "SESSION_OPEN_REQUEST_INVALID",
    }),
    run_spec_id: requireString(readDataProperty(value, "run_spec_id"), "run_spec_id", {
      min: 3,
      max: 128,
      code: "SESSION_OPEN_REQUEST_INVALID",
    }),
    classification_id: requireString(
      readDataProperty(value, "classification_id"),
      "classification_id",
      { min: 3, max: 128, code: "SESSION_OPEN_REQUEST_INVALID" },
    ),
    policy_hash: requireHash(
      readDataProperty(value, "policy_hash"),
      "policy_hash",
      "SESSION_OPEN_REQUEST_INVALID",
    ),
    corpus_snapshot_hash: requireHash(
      readDataProperty(value, "corpus_snapshot_hash"),
      "corpus_snapshot_hash",
      "SESSION_OPEN_REQUEST_INVALID",
    ),
    actor: {
      actor_id: requireString(readDataProperty(actor, "actor_id"), "actor.actor_id", {
        min: 3,
        max: 128,
        code: "SESSION_OPEN_REQUEST_INVALID",
      }),
      actor_type: actorType,
      role: requireString(readDataProperty(actor, "role"), "actor.role", {
        code: "SESSION_OPEN_REQUEST_INVALID",
      }),
    },
    idempotency_key: requireString(
      readDataProperty(value, "idempotency_key"),
      "idempotency_key",
      { min: 8, code: "SESSION_OPEN_REQUEST_INVALID" },
    ),
    requested_at: requireTimestamp(
      readDataProperty(value, "requested_at"),
      "requested_at",
      "SESSION_OPEN_REQUEST_INVALID",
    ),
  });
};

const normalizeClassificationProjection = (candidate, classificationId) => {
  const code = "SESSION_OPEN_CLASSIFICATION_INVALID";
  const keys = [
    "projection_version",
    "classification",
    "identity_context",
    "artifact_binding",
    "ledger_binding",
    "projection_hash",
    "projection_id",
  ];
  const value = exactKeys(candidate, keys, "classification replay projection", code);
  if (value.projection_version !== "DURABLE_FORGE_V1") {
    fail(code, "classification replay projection version is incompatible");
  }
  const semantic = Object.fromEntries(
    keys
      .filter((key) => !["projection_hash", "projection_id"].includes(key))
      .map((key) => [key, readDataProperty(value, key)]),
  );
  const projectionHash = requireHash(value.projection_hash, "projection_hash", code);
  if (
    projectionHash !== hashJson(semantic) ||
    value.projection_id !== `F01RP-${projectionHash.slice("sha256:".length)}`
  ) {
    fail(code, "classification replay projection identity is invalid");
  }
  const classification = requirePlainRecord(value.classification, "classification", { code });
  const identityContext = requirePlainRecord(value.identity_context, "identity_context", { code });
  const artifactBinding = exactKeys(
    value.artifact_binding,
    ["artifact_id", "content_hash", "artifact_manifest_hash", "receipt_id", "receipt_hash", "schema_ref"],
    "artifact_binding",
    code,
  );
  const ledgerBinding = exactKeys(
    value.ledger_binding,
    ["run_id", "event_id", "sequence", "event_hash", "payload_hash"],
    "ledger_binding",
    code,
  );
  if (
    classification.classification_id !== classificationId ||
    artifactBinding.artifact_id !== classificationId
  ) {
    fail(code, "classification replay projection does not bind the requested classification");
  }
  requireString(classification.request_id, "classification.request_id", { min: 3, max: 128, code });
  requireHash(identityContext.policy_bundle_hash, "identity_context.policy_bundle_hash", code);
  requireString(ledgerBinding.run_id, "ledger_binding.run_id", { min: 3, code });
  if (!NUMBER_IS_SAFE_INTEGER(ledgerBinding.sequence) || ledgerBinding.sequence < 1) {
    fail(code, "classification ledger sequence is invalid");
  }
  for (const key of ["content_hash", "artifact_manifest_hash", "receipt_hash"]) {
    requireHash(artifactBinding[key], `artifact_binding.${key}`, code);
  }
  for (const key of ["event_hash", "payload_hash"]) {
    requireHash(ledgerBinding[key], `ledger_binding.${key}`, code);
  }
  try {
    assertClassificationArtifactIntegrity(classification, identityContext);
  } catch {
    fail(code, "classification replay projection contains an invalid F01 artifact");
  }
  return detached(value);
};

const resolveClassificationProjection = (classificationPort, classificationId) => {
  let projection;
  try {
    projection = classificationPort.readClassificationReplayProjection(classificationId);
  } catch {
    fail(
      "SESSION_OPEN_CLASSIFICATION_UNAVAILABLE",
      "sealed F01 replay projection is unavailable",
    );
  }
  return normalizeClassificationProjection(projection, classificationId);
};

export const publishSessionOpenRequest = (artifactStore, candidate) => {
  dependencyMethod(artifactStore, "putArtifact", "artifactStore");
  const request = normalizeOpenRequest(candidate);
  const bytes = Buffer.from(canonicalJson(request), "utf8");
  const contentHash = hashBytes(bytes);
  const artifactId = `FSOR-T02-${contentHash.slice("sha256:".length)}`;
  const receiptId = `AR-${artifactId}`;

  artifactStore.putArtifact(bytes, {
    artifact: {
      artifactId,
      artifactType: "forge_open_request",
      confidentiality: "internal",
      createdAt: request.requested_at,
      createdBy: request.actor.actor_id,
      encryption: {
        atRest: true,
        inTransit: true,
        keyRef: OPEN_REQUEST_ENCRYPTION_KEY_REF,
      },
      inputArtifactIds: [request.classification_id],
      license: null,
      lineageEventIds: [],
      mediaType: "application/json",
      provenanceManifestId: OPEN_REQUEST_PROVENANCE_ID,
      retentionClass: "project",
    },
    receipt: {
      actionIntentId: null,
      createdAt: request.requested_at,
      createdBy: {
        actorId: request.actor.actor_id,
        actorType: request.actor.actor_type,
      },
      receiptId,
      schemaRef: null,
      validationResults: [],
    },
  });

  return detached({ artifactId, receiptId, contentHash, request });
};

const normalizeInvocation = (candidate) => {
  const request = exactKeys(
    candidate,
    REQUEST_KEYS,
    "session OPEN worker request",
    "SESSION_OPEN_INPUT_INVALID",
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
    unavailable("the foundry.session.open catalog binding is unavailable");
  }
  const outer = exactKeys(
    readDataProperty(request, "validated_arguments"),
    MUTATION_ARGUMENT_KEYS,
    "validated_arguments",
    "SESSION_OPEN_INPUT_INVALID",
  );
  const toolArguments = exactKeys(
    readDataProperty(outer, "arguments"),
    TOOL_ARGUMENT_KEYS,
    "validated_arguments.arguments",
    "SESSION_OPEN_INPUT_INVALID",
  );
  const dryRun = readDataProperty(outer, "dry_run");
  if (typeof dryRun !== "boolean") {
    fail("SESSION_OPEN_INPUT_INVALID", "dry_run must be boolean");
  }
  if (readDataProperty(outer, "expected_revision") !== null) {
    fail("SESSION_OPEN_INPUT_INVALID", "expected_revision must be null");
  }
  const actor = exactKeys(
    readDataProperty(toolArguments, "actor"),
    ["actor_id", "actor_type", "role"],
    "validated_arguments.arguments.actor",
    "SESSION_OPEN_INPUT_INVALID",
  );
  if (!ACTOR_TYPES.has(readDataProperty(actor, "actor_type"))) {
    fail("SESSION_OPEN_INPUT_INVALID", "actor.actor_type is not canonical");
  }
  const auth = requirePlainRecord(readDataProperty(request, "auth"), "auth", {
    code: "SESSION_OPEN_INPUT_INVALID",
  });
  const semanticFingerprint = readDataProperty(request, "semantic_fingerprint");
  if (typeof semanticFingerprint !== "string" || !SHA256_PATTERN.test(semanticFingerprint)) {
    fail("SESSION_OPEN_INPUT_INVALID", "semantic_fingerprint is not canonical SHA-256");
  }
  return OBJECT_FREEZE({
    approvalRecordIds: requireUniqueStrings(
      readDataProperty(outer, "approval_record_ids"),
      "approval_record_ids",
    ),
    authPrincipalId: requireString(readDataProperty(auth, "principal_id"), "auth.principal_id", {
      min: 3,
      code: "SESSION_OPEN_INPUT_INVALID",
    }),
    authWorkspaceId: Object.hasOwn(auth, "workspace_id")
      ? requireString(readDataProperty(auth, "workspace_id"), "auth.workspace_id", {
          min: 3,
          code: "SESSION_OPEN_INPUT_INVALID",
        })
      : null,
    dryRun,
    actor: detached({
      actor_id: requireString(readDataProperty(actor, "actor_id"), "actor.actor_id", {
        min: 3,
        max: 128,
        code: "SESSION_OPEN_INPUT_INVALID",
      }),
      actor_type: readDataProperty(actor, "actor_type"),
      role: requireString(readDataProperty(actor, "role"), "actor.role", {
        min: 1,
        code: "SESSION_OPEN_INPUT_INVALID",
      }),
    }),
    classificationId: requireString(
      readDataProperty(toolArguments, "classification_id"),
      "arguments.classification_id",
      { min: 3, max: 128, code: "SESSION_OPEN_INPUT_INVALID" },
    ),
    corpusSnapshotHash: requireHash(
      readDataProperty(toolArguments, "corpus_snapshot_hash"),
      "arguments.corpus_snapshot_hash",
      "SESSION_OPEN_INPUT_INVALID",
    ),
    generatedAt: canonicalTimestamp(readDataProperty(request, "generated_at"), "generated_at"),
    idempotencyKey: requireString(
      readDataProperty(outer, "idempotency_key"),
      "idempotency_key",
      { min: 8, max: 200, code: "SESSION_OPEN_INPUT_INVALID" },
    ),
    requestId: requireString(readDataProperty(request, "request_id"), "request_id", {
      min: 1,
      code: "SESSION_OPEN_INPUT_INVALID",
    }),
    semanticFingerprint,
    sessionId: requireString(readDataProperty(toolArguments, "session_id"), "arguments.session_id", {
      min: 3,
      max: 128,
      code: "SESSION_OPEN_INPUT_INVALID",
    }),
    targetRef: requireString(readDataProperty(outer, "target_ref"), "target_ref", {
      min: 3,
      max: 128,
      code: "SESSION_OPEN_INPUT_INVALID",
    }),
    requestedAt: canonicalTimestamp(
      readDataProperty(toolArguments, "requested_at"),
      "arguments.requested_at",
    ),
    workspaceId: requireString(readDataProperty(outer, "workspace_id"), "workspace_id", {
      min: 3,
      max: 128,
      code: "SESSION_OPEN_INPUT_INVALID",
    }),
  });
};

export const createSessionOpenRuntimeRequest = (candidate) => {
  const value = exactKeys(
    candidate,
    RUNTIME_REQUEST_FACTORY_KEYS,
    "session OPEN runtime request options",
    "SESSION_OPEN_INPUT_INVALID",
  );
  const auth = requirePlainRecord(
    readDataProperty(value, "auth"),
    "auth",
    { code: "SESSION_OPEN_INPUT_INVALID" },
  );
  const validatedArguments = exactKeys(
    readDataProperty(value, "validatedArguments"),
    MUTATION_ARGUMENT_KEYS,
    "validatedArguments",
    "SESSION_OPEN_INPUT_INVALID",
  );
  const semanticFingerprint = hashJson({
    arguments: readDataProperty(validatedArguments, "arguments"),
    dry_run: Boolean(readDataProperty(validatedArguments, "dry_run")),
    expected_revision: readDataProperty(validatedArguments, "expected_revision"),
    principal_id: readDataProperty(auth, "principal_id"),
    protocol_version: PROTOCOL_VERSION,
    target_ref: readDataProperty(validatedArguments, "target_ref"),
    tool: TOOL_NAME,
    workspace_id: readDataProperty(validatedArguments, "workspace_id"),
  });
  const request = {
    tool_name: TOOL_NAME,
    handler_operation: HANDLER_OPERATION,
    capability: REQUIRED_CAPABILITY,
    risk_class: CATALOG_RISK_CLASS,
    approval_class: APPROVAL_CLASS,
    expected_revision_required: false,
    validated_arguments: validatedArguments,
    auth,
    semantic_fingerprint: semanticFingerprint,
    request_id: readDataProperty(value, "requestId"),
    generated_at: readDataProperty(value, "generatedAt"),
  };

  normalizeInvocation(request);
  return detached(request);
};

const normalizeDependencies = (options) => {
  const value = exactKeys(
    options,
    ["stateStore", "artifactStore", "ledger", "authority", "session", "classification", "clock", "runtime"],
    "session OPEN worker options",
    "SESSION_OPEN_INVALID_DEPENDENCY",
  );
  const dependencies = Object.fromEntries(
    ["stateStore", "artifactStore", "ledger", "authority", "session", "classification", "clock", "runtime"]
      .map((key) => [key, readDataProperty(value, key)]),
  );
  for (const method of ["transaction", "readRevisionedRecord", "createRevisionedRecord", "compareAndSwapRevision"]) {
    dependencyMethod(dependencies.stateStore, method, "stateStore");
  }
  for (const method of ["putArtifact", "readArtifact", "readManifest"]) {
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
  dependencyMethod(
    dependencies.classification,
    "readClassificationReplayProjection",
    "classification",
  );
  for (const method of ["openSession"]) {
    dependencyMethod(dependencies.session, method, "session");
  }
  if (typeof dependencies.clock !== "function" || IS_PROXY(dependencies.clock)) {
    fail("SESSION_OPEN_INVALID_DEPENDENCY", "clock must be a trusted synchronous function");
  }
  let authorityIdentity;
  let classificationAuthority;
  let sessionAuthority;
  try {
    authorityIdentity = getCapabilityAuthorityDependencyIdentity(dependencies.authority);
    classificationAuthority = resolveClassificationWorkerAuthority(
      dependencies.classification,
      dependencies,
    );
    sessionAuthority = resolveDurableForgeSessionWorkerAuthority(
      dependencies.session,
      { ...dependencies, classificationPort: dependencies.classification },
    );
  } catch (error) {
    fail(
      "SESSION_OPEN_INVALID_DEPENDENCY",
      "authority, classification, and session must be canonical Kernel ports",
      { causeCode: error?.code ?? error?.name ?? "unknown" },
      { cause: error },
    );
  }
  if (classificationAuthority === null) {
    fail(
      "SESSION_OPEN_DEPENDENCY_IDENTITY_MISMATCH",
      "classification does not share the worker dependencies",
    );
  }
  if (sessionAuthority === null) {
    fail(
      "SESSION_OPEN_DEPENDENCY_IDENTITY_MISMATCH",
      "session does not share the worker dependencies",
    );
  }
  for (const [label, identity] of [["authority", authorityIdentity]]) {
    for (const key of ["stateStore", "artifactStore", "ledger", "clock"]) {
      if (identity[key] !== dependencies[key]) {
        fail(
          "SESSION_OPEN_DEPENDENCY_IDENTITY_MISMATCH",
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
    "session OPEN runtime config",
    "SESSION_OPEN_INVALID_DEPENDENCY",
  );
  const leaseCommandFactory = readDataProperty(runtime, "leaseCommandFactory");
  if (typeof leaseCommandFactory !== "function" || IS_PROXY(leaseCommandFactory)) {
    fail(
      "SESSION_OPEN_INVALID_DEPENDENCY",
      "runtime.leaseCommandFactory must be a trusted synchronous function",
    );
  }
  return OBJECT_FREEZE({
    ...dependencies,
    sessionAuthority,
    effects,
    runtime: OBJECT_FREEZE({
      authorityPrincipalId: requireString(
        readDataProperty(runtime, "authorityPrincipalId"),
        "runtime.authorityPrincipalId",
        { min: 3, code: "SESSION_OPEN_INVALID_DEPENDENCY" },
      ),
      workerPrincipalId: requireString(
        readDataProperty(runtime, "workerPrincipalId"),
        "runtime.workerPrincipalId",
        { min: 3, code: "SESSION_OPEN_INVALID_DEPENDENCY" },
      ),
      leaseCommandFactory,
    }),
  });
};

const bindCallerInvocation = (invocation) => {
  if (
    invocation.targetRef !== invocation.sessionId
  ) {
    fail("SESSION_OPEN_BINDING_MISMATCH", "target_ref and session identities disagree");
  }
  if (
    (invocation.authWorkspaceId !== null && invocation.authWorkspaceId !== invocation.workspaceId)
  ) {
    fail("SESSION_OPEN_BINDING_MISMATCH", "authenticated workspace differs from workspace_id");
  }
  if (invocation.authPrincipalId !== invocation.actor.actor_id) {
    fail("SESSION_OPEN_BINDING_MISMATCH", "authenticated principal differs from request actor");
  }
};

const bindInvocation = ({ invocation, openRequest, classificationProjection }) => {
  if (
    invocation.sessionId !== openRequest.session_id ||
    invocation.workspaceId !== openRequest.workspace_id
  ) {
    fail("SESSION_OPEN_BINDING_MISMATCH", "completed OPEN caller bindings changed");
  }
  if (invocation.idempotencyKey !== openRequest.idempotency_key) {
    fail("SESSION_OPEN_BINDING_MISMATCH", "outer and stored idempotency keys disagree");
  }
  if (
    invocation.classificationId !== openRequest.classification_id ||
    invocation.corpusSnapshotHash !== openRequest.corpus_snapshot_hash ||
    classificationProjection.classification.classification_id !== openRequest.classification_id ||
    classificationProjection.classification.request_id !== openRequest.request_id ||
    classificationProjection.ledger_binding.run_id !== openRequest.run_spec_id ||
    classificationProjection.identity_context.policy_bundle_hash !== openRequest.policy_hash
  ) {
    fail("SESSION_OPEN_BINDING_MISMATCH", "caller and sealed F01 OPEN bindings disagree");
  }
};

const identitiesFor = (invocation, artifactContentHash) => {
  const digest = hashJson({
    contract: IDENTITY_CONTRACT,
    semantic_fingerprint: invocation.semanticFingerprint,
    idempotency_key: invocation.idempotencyKey,
    arguments_hash: artifactContentHash,
    tool_name: TOOL_NAME,
    handler_operation: HANDLER_OPERATION,
  }).slice("sha256:".length);
  return OBJECT_FREEZE({
    intentId: `AI-T02-${digest}`,
    attemptId: `ATT-T02-${digest}`,
    leaseId: `LEASE-T02-${digest}`,
    leaseUseOperationId: `USE-T02-${digest}`,
    dryReceiptId: `EFF-T02-NOT-EXECUTED-${digest}`,
    unknownReceiptId: `EFF-T02-UNKNOWN-${digest}`,
    successReceiptId: `EFF-T02-SUCCEEDED-${digest}`,
  });
};

const normalizeLeaseCommand = (candidate, expected) => {
  const value = exactKeys(
    candidate,
    ["lease_id", "run_id", "principal_id", "capabilities", "resource_scopes", "expires_at", "approval_ids"],
    "lease command factory result",
    "SESSION_OPEN_LEASE_COMMAND_INVALID",
  );
  const command = detached({
    lease_id: requireString(readDataProperty(value, "lease_id"), "lease_id", {
      min: 3,
      max: 128,
      code: "SESSION_OPEN_LEASE_COMMAND_INVALID",
    }),
    run_id: requireString(readDataProperty(value, "run_id"), "run_id", {
      min: 3,
      code: "SESSION_OPEN_LEASE_COMMAND_INVALID",
    }),
    principal_id: requireString(readDataProperty(value, "principal_id"), "principal_id", {
      min: 3,
      code: "SESSION_OPEN_LEASE_COMMAND_INVALID",
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
      "SESSION_OPEN_LEASE_COMMAND_INVALID",
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
    fail("SESSION_OPEN_LEASE_COMMAND_FAILED", "lease command factory failed", undefined, {
      cause: error,
    });
  }
  if (candidate !== null && ["object", "function"].includes(typeof candidate) && "then" in candidate) {
    fail("SESSION_OPEN_LEASE_COMMAND_FAILED", "lease command factory must be synchronous");
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
    fail("SESSION_OPEN_LEASE_INVALID", "E03 returned a lease outside the requested binding");
  }
  requireHash(lease.lease_hash, "lease.lease_hash", "SESSION_OPEN_LEASE_INVALID");
  return OBJECT_FREEZE({ command, lease });
};

const readLedgerEvents = (ledger, runId) => {
  let events;
  try {
    events = ledger.readEvents(runId);
  } catch (error) {
    fail("SESSION_OPEN_LEDGER_INVALID", "E01 readEvents failed", undefined, {
      cause: error,
    });
  }
  if (!ARRAY_IS_ARRAY(events)) {
    fail("SESSION_OPEN_LEDGER_INVALID", "E01 readEvents did not return an array");
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
      fail("SESSION_OPEN_LEDGER_INVALID", "E01 event sequence or identity is invalid");
    }
    requireHash(event.event_hash, "event.event_hash", "SESSION_OPEN_LEDGER_INVALID");
    eventIds.add(event.event_id);
  }
  return events;
};

const currentLedgerHead = (ledger, runId) => {
  const events = readLedgerEvents(ledger, runId);
  if (events.length === 0) {
    return detached({ event_count: 0, tail_event_id: null, tail_event_hash: null });
  }
  const tail = events[events.length - 1];
  return detached({
    event_count: events.length,
    tail_event_id: requireString(tail.event_id, "tail.event_id", {
      code: "SESSION_OPEN_LEDGER_INVALID",
    }),
    tail_event_hash: requireHash(
      tail.event_hash,
      "tail.event_hash",
      "SESSION_OPEN_LEDGER_INVALID",
    ),
  });
};

const normalizePreparationResult = (candidate, openRequest) => {
  const value = exactKeys(
    candidate,
    PREPARATION_RESULT_KEYS,
    "F04 open preparation result",
    "SESSION_OPEN_PREPARATION_INVALID",
  );
  if (!new Set(["PREPARED", "EXISTING"]).has(value.status)) {
    fail("SESSION_OPEN_PREPARATION_INVALID", "F04 preparation status is invalid");
  }
  for (const key of ["request_hash", "candidate_state_hash"]) {
    requireHash(value[key], `preparation.${key}`, "SESSION_OPEN_PREPARATION_INVALID");
  }
  if (
    value.session_id !== openRequest.session_id ||
    value.expected_revision !== null ||
    !NUMBER_IS_SAFE_INTEGER(value.new_revision) ||
    value.new_revision < 0
  ) {
    fail("SESSION_OPEN_PREPARATION_INVALID", "F04 preparation result changed open identity");
  }
  for (const key of ["operation_id", "outbox_id", "payload_artifact_id"]) {
    requireString(value[key], `preparation.${key}`, {
      min: 1,
      code: "SESSION_OPEN_PREPARATION_INVALID",
    });
  }
  return detached(value);
};

const preparationBinding = (preparation) => {
  const { status: _status, ...binding } = preparation;
  return binding;
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
    "SESSION_OPEN_RECOVERY_INVALID",
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
    "SESSION_OPEN_RECOVERY_INVALID",
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
    fail("SESSION_OPEN_RECOVERY_INVALID", "E03 lease-use recovery binding changed");
  }
  for (const key of ["request_hash", "lease_use_hash"]) {
    requireHash(value[key], `lease use.${key}`, "SESSION_OPEN_RECOVERY_INVALID");
  }
  for (const key of ["lease_use_id", "event_outbox_id"]) {
    requireString(value[key], `lease use.${key}`, {
      min: 1,
      code: "SESSION_OPEN_RECOVERY_INVALID",
    });
  }
  if (
    !new Set(["PUBLISHED", "PENDING_EVENT_RECONCILIATION"]).has(
      value.event_publication_status,
    ) ||
    (value.event_publication_status === "PUBLISHED") !== (event.event_hash !== null)
  ) {
    fail("SESSION_OPEN_RECOVERY_INVALID", "E03 event publication state is invalid");
  }
  requireString(event.event_id, "lease use event.event_id", {
    min: 1,
    code: "SESSION_OPEN_RECOVERY_INVALID",
  });
  requireString(event.payload_artifact_id, "lease use event.payload_artifact_id", {
    min: 1,
    code: "SESSION_OPEN_RECOVERY_INVALID",
  });
  canonicalTimestamp(event.occurred_at, "lease use event.occurred_at");
  if (event.event_hash !== null) {
    requireHash(event.event_hash, "lease use event.event_hash", "SESSION_OPEN_RECOVERY_INVALID");
  }
  return detached(value);
};

const normalizePublishedOpenInspection = ({ candidate, prepared, context }) => {
  const value = exactKeys(
    candidate,
    ["status", "preparation", "projection", "ledger_event", "artifact"],
    "F04 open inspection",
    "SESSION_OPEN_RECOVERY_INVALID",
  );
  if (!new Set(["ABSENT", "PENDING", "PUBLISHED", "CONFLICTED"]).has(value.status)) {
    fail("SESSION_OPEN_RECOVERY_INVALID", "F04 open inspection status is invalid");
  }
  if (value.status !== "PUBLISHED") return null;
  const inspectedPreparation = normalizePreparationResult(
    value.preparation,
    context.openRequest,
  );
  if (!sameCanonical(preparationBinding(inspectedPreparation), preparationBinding(prepared))) {
    fail("SESSION_OPEN_RECOVERY_INVALID", "F04 preparation identity changed during recovery");
  }
  const projection = requirePlainRecord(value.projection, "F04 operation projection", {
    code: "SESSION_OPEN_RECOVERY_INVALID",
  });
  const state = requirePlainRecord(projection.state, "F04 operation state", {
    code: "SESSION_OPEN_RECOVERY_INVALID",
  });
  const artifact = exactKeys(
    value.artifact,
    ["artifact_id", "content_hash", "manifest_hash", "receipt_id", "receipt_hash"],
    "F04 operation artifact",
    "SESSION_OPEN_RECOVERY_INVALID",
  );
  const ledgerEvent = requirePlainRecord(value.ledger_event, "F04 operation ledger event", {
    code: "SESSION_OPEN_RECOVERY_INVALID",
  });
  if (
    artifact.artifact_id !== prepared.payload_artifact_id ||
    state.session_id !== prepared.session_id ||
    state.revision !== prepared.new_revision ||
    state.state_hash !== prepared.candidate_state_hash ||
    ledgerEvent.run_id !== context.intent.run_id ||
    ledgerEvent.event_type !== "forge.session.opened" ||
    ledgerEvent.aggregate_type !== "forge_session" ||
    ledgerEvent.aggregate_id !== prepared.session_id ||
    ledgerEvent.actor_id !== context.openRequest.actor.actor_id ||
    ledgerEvent.payload_artifact_id !== prepared.payload_artifact_id ||
    projection.last_session_event_id !== ledgerEvent.event_id ||
    projection.last_session_event_hash !== ledgerEvent.event_hash
  ) {
    fail("SESSION_OPEN_RECOVERY_INVALID", "F04 published operation binding changed");
  }
  for (const key of ["content_hash", "manifest_hash", "receipt_hash"]) {
    requireHash(artifact[key], `F04 artifact.${key}`, "SESSION_OPEN_RECOVERY_INVALID");
  }
  requireHash(projection.projection_hash, "F04 projection_hash", "SESSION_OPEN_RECOVERY_INVALID");
  requireHash(ledgerEvent.event_hash, "F04 event_hash", "SESSION_OPEN_RECOVERY_INVALID");
  return detached({ artifact, ledgerEvent, projection });
};

const ledgerContainsExactEvent = ({ ledger, runId, event }) => {
  const events = readLedgerEvents(ledger, runId);
  const matching = events.filter((candidate) => candidate.event_id === event.event_id);
  return matching.length === 1 && sameCanonical(matching[0], event);
};

const ledgerProvesPublishedOpen = ({ ledger, runId, leaseUse, published }) => {
  const events = readLedgerEvents(ledger, runId);
  const byId = new Map(events.map((event) => [event.event_id, event]));
  const f04Event = byId.get(published.ledgerEvent.event_id);
  const e03Event = byId.get(leaseUse.event.event_id);
  if (f04Event === undefined || e03Event === undefined) return false;
  if (!sameCanonical(f04Event, published.ledgerEvent)) return false;
  if (f04Event.sequence >= e03Event.sequence) return false;
  if (e03Event.event_hash !== leaseUse.event.event_hash) return false;
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
    if (e03Event[key] !== leaseUse.event[key]) return false;
  }
  return true;
};

const strictF04Payload = (artifactStore, artifactId) => {
  const bytes = artifactStore.readArtifact(artifactId);
  if (!Buffer.isBuffer(bytes) && !(bytes instanceof Uint8Array)) {
    fail("SESSION_OPEN_RESULT_INVALID", "F04 result artifact bytes are unavailable");
  }
  const content = Buffer.from(bytes);
  const text = content.toString("utf8");
  if (!Buffer.from(text, "utf8").equals(content) || !text.endsWith("\n")) {
    fail("SESSION_OPEN_RESULT_INVALID", "F04 result artifact is not canonical UTF-8 JSON");
  }
  let payload;
  try {
    payload = JSON.parse(text.slice(0, -1));
  } catch (error) {
    fail("SESSION_OPEN_RESULT_INVALID", "F04 result artifact is malformed", undefined, {
      cause: error,
    });
  }
  if (`${canonicalJson(payload)}\n` !== text) {
    fail("SESSION_OPEN_RESULT_INVALID", "F04 result artifact is not canonical JSON");
  }
  return requirePlainRecord(payload, "F04 result payload", {
    code: "SESSION_OPEN_RESULT_INVALID",
  });
};

const resultRevisionFromReceipt = (artifactStore, receipt, openRequest) => {
  if (receipt.result_artifact_ids.length !== 1) {
    fail("SESSION_OPEN_RESULT_INVALID", "successful receipt must bind one F04 payload");
  }
  const payload = strictF04Payload(artifactStore, receipt.result_artifact_ids[0]);
  const candidateState = requirePlainRecord(payload.candidate_state, "F04 candidate_state", {
    code: "SESSION_OPEN_RESULT_INVALID",
  });
  if (
    payload.kind !== "OPEN" ||
    payload.operation_id !== receipt.external_operation_id ||
    payload.session_id !== openRequest.session_id ||
    !sameCanonical(payload.request, openRequest)
  ) {
    fail("SESSION_OPEN_RESULT_INVALID", "successful receipt differs from its F04 operation");
  }
  const revision = candidateState.revision;
  if (!NUMBER_IS_SAFE_INTEGER(revision) || revision < 0) {
    fail("SESSION_OPEN_RESULT_INVALID", "F04 result revision is invalid");
  }
  return String(revision);
};

const mutationPayload = ({
  invocation,
  leaseId,
  outcome,
  openRequest,
  artifactStore,
}) => {
  const receipt = outcome.receipt;
  if (receipt === null || receipt === undefined) {
    fail("SESSION_OPEN_RECEIPT_MISSING", "E02 outcome has no EffectReceipt");
  }
  const status = receipt.status;
  const committed = status === "UNKNOWN" ? null : status === "SUCCEEDED";
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
      new_revision:
        status === "SUCCEEDED"
          ? resultRevisionFromReceipt(artifactStore, receipt, openRequest)
          : null,
      reconciliation_required: status === "UNKNOWN",
    },
    preview: null,
  });
};

const unknownOpenReceiptInput = ({ dependencies, context, prepared }) => {
  const finishedAt = latestTimestamp(
    context.attempt.started_at,
    timestampFromClock(dependencies.clock),
  );
  return {
    receipt_id: context.identities.unknownReceiptId,
    intent_id: context.intent.intent_id,
    run_id: context.intent.run_id,
    external_operation_id: prepared?.operation_id ?? null,
    status: "UNKNOWN",
    result_artifact_ids: [],
    error_artifact_ids: [],
    observed_state_hash: context.classificationProjection.projection_hash,
    idempotency_key: context.invocation.idempotencyKey,
    started_at: context.attempt.started_at,
    finished_at: finishedAt,
    reconciliation_required: true,
  };
};

const dryRunOpenReceiptInput = ({ dependencies, context, outcome }) => ({
  receipt_id: context.identities.dryReceiptId,
  intent_id: context.intent.intent_id,
  run_id: context.intent.run_id,
  external_operation_id: DRY_RUN_OPERATION_ID,
  status: "NOT_EXECUTED",
  result_artifact_ids: [],
  error_artifact_ids: [],
  observed_state_hash: context.classificationProjection.projection_hash,
  idempotency_key: context.invocation.idempotencyKey,
  started_at: context.attempt.started_at,
  finished_at: latestTimestamp(
    context.attempt.started_at,
    outcome.receipt?.finished_at ?? context.attempt.started_at,
    timestampFromClock(dependencies.clock),
  ),
  reconciliation_required: false,
});

const succeededOpenReceiptInput = ({
  dependencies,
  context,
  outcome,
  prepared,
  projection,
}) => ({
  receipt_id: context.identities.successReceiptId,
  intent_id: context.intent.intent_id,
  run_id: context.intent.run_id,
  external_operation_id: prepared.operation_id,
  status: "SUCCEEDED",
  result_artifact_ids: [prepared.payload_artifact_id],
  error_artifact_ids: [],
  observed_state_hash: projection.projection_hash,
  idempotency_key: context.invocation.idempotencyKey,
  started_at: context.attempt.started_at,
  finished_at: latestTimestamp(
    context.attempt.started_at,
    projection.state.updated_at,
    outcome.receipt?.finished_at ?? context.attempt.started_at,
    timestampFromClock(dependencies.clock),
  ),
  reconciliation_required: false,
});

const RECOVERY_EVIDENCE_FAILURE_CODES = new Set([
  "SESSION_OPEN_RECOVERY_INVALID",
  "SESSION_OPEN_PREPARATION_INVALID",
  "SESSION_OPEN_INPUT_INVALID",
  "SESSION_OPEN_LEDGER_INVALID",
  "NON_CANONICAL_JSON",
  "CAPABILITY_STATE_INTEGRITY_FAILED",
  "CAPABILITY_STATE_MISSING",
  "FORGE_REQUEST_CONFLICT",
  "FORGE_IDEMPOTENCY_CONFLICT",
  "FORGE_INPUT_INVALID",
  "FORGE_CLASSIFICATION_BINDING_MISMATCH",
  "FORGE_OPERATION_BINDING_INTEGRITY_FAILED",
  "FORGE_OUTBOX_INTEGRITY_FAILED",
  "FORGE_PHASE_ARTIFACT_SET_IDENTITY_MISMATCH",
  "FORGE_SESSION_STATE_INTEGRITY_FAILED",
  "FORGE_CLASSIFICATION_INTEGRITY_FAILED",
]);

const isRecoveryEvidenceFailure = (error) =>
  error !== null &&
  typeof error === "object" &&
  RECOVERY_EVIDENCE_FAILURE_CODES.has(error.code);

const reconcilePublishedOpenProof = ({ dependencies, context, lease, outcome }) => {
  const inspectedLeaseUse = dependencies.authority.inspectLeaseUse(
    context.identities.leaseUseOperationId,
  );
  let leaseUse = normalizeLeaseUseInspection({
    candidate: inspectedLeaseUse,
    context,
    lease,
  });
  if (leaseUse === null) return null;

  const prepared = normalizePreparationResult(
    leaseUse.result,
    context.openRequest,
  );
  if (
    outcome.receipt?.external_operation_id !== null &&
    outcome.receipt?.external_operation_id !== undefined &&
    outcome.receipt.external_operation_id !== prepared.operation_id
  ) {
    fail(
      "SESSION_OPEN_RECOVERY_INVALID",
      "UNKNOWN receipt is bound to another F04 operation",
    );
  }

  const inspection = dependencies.sessionAuthority.inspectOpen({
    open_request: context.openRequest,
    expected_ledger_head: prepared.expected_ledger_head,
  });
  const published = normalizePublishedOpenInspection({
    candidate: inspection,
    prepared,
    context,
  });
  if (published === null) return null;
  if (!ledgerContainsExactEvent({
    ledger: dependencies.ledger,
    runId: context.intent.run_id,
    event: published.ledgerEvent,
  })) {
    return null;
  }
  if (leaseUse.event_publication_status !== "PUBLISHED") {
    leaseUse = normalizeLeaseUseInspection({
      candidate: dependencies.authority.reconcileLeaseUseEvent(
        context.identities.leaseUseOperationId,
      ),
      context,
      lease,
    });
    if (leaseUse?.event_publication_status !== "PUBLISHED") return null;
  }
  if (!ledgerProvesPublishedOpen({
    ledger: dependencies.ledger,
    runId: context.intent.run_id,
    leaseUse,
    published,
  })) {
    return null;
  }

  return OBJECT_FREEZE({
    prepared,
    effectResult: OBJECT_FREEZE({ projection: published.projection }),
  });
};

const executeOpenEffect = ({ dependencies, context, lease, setPrepared }) => {
  const runId = context.intent.run_id;
  const head = currentLedgerHead(dependencies.ledger, runId);
  const initialCandidate = detached({
    open_request: context.openRequest,
    expected_ledger_head: head,
    classification_projection: context.classificationProjection,
  });
  const leaseCommit = dependencies.authority.commitWithLeaseDeferredEvent(
    {
      operation_id: context.identities.leaseUseOperationId,
      run_id: runId,
      lease,
      principal_id: context.workerPrincipalId,
      capability: REQUIRED_CAPABILITY,
      resource_scopes: lease.resource_scopes,
    },
    (transactionStore) => dependencies.sessionAuthority.prepareOpen(
      transactionStore,
      initialCandidate,
    ),
    Object.values(DURABLE_FORGE_SESSION_RECORD_TYPES),
  );
  const prepared = normalizePreparationResult(leaseCommit.result, context.openRequest);
  setPrepared(prepared);
  const published = dependencies.session.openSession({
    ...context.openRequest,
    expected_ledger_head: prepared.expected_ledger_head,
  });
  if (
    published.state.revision !== prepared.new_revision ||
    published.state.state_hash !== prepared.candidate_state_hash
  ) {
    fail("SESSION_OPEN_RESULT_INVALID", "published F04 projection differs from preparation");
  }
  const inspection = dependencies.sessionAuthority.inspectOpen({
    open_request: context.openRequest,
    expected_ledger_head: prepared.expected_ledger_head,
  });
  const publishedEvidence = normalizePublishedOpenInspection({
    candidate: inspection,
    prepared,
    context,
  });
  if (
    publishedEvidence === null ||
    !ledgerContainsExactEvent({
      ledger: dependencies.ledger,
      runId,
      event: publishedEvidence.ledgerEvent,
    })
  ) {
    fail(
      "SESSION_OPEN_RESULT_INVALID",
      "F04 publication is not durably present in E01",
    );
  }
  let leaseUse = normalizeLeaseUseInspection({
    candidate: dependencies.authority.inspectLeaseUse(
      context.identities.leaseUseOperationId,
    ),
    context,
    lease,
  });
  if (leaseUse === null) {
    fail("SESSION_OPEN_RESULT_INVALID", "E03 lease use is missing after F04 publication");
  }
  const inspectedPreparation = normalizePreparationResult(
    leaseUse.result,
    context.openRequest,
  );
  if (!sameCanonical(
    preparationBinding(inspectedPreparation),
    preparationBinding(prepared),
  )) {
    fail("SESSION_OPEN_RESULT_INVALID", "E03 and F04 operation bindings disagree");
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
    !ledgerProvesPublishedOpen({
      ledger: dependencies.ledger,
      runId,
      leaseUse,
      published: publishedEvidence,
    })
  ) {
    fail(
      "SESSION_OPEN_RESULT_INVALID",
      "E01 does not prove the required F04 then E03 publication order",
    );
  }
  return OBJECT_FREEZE({ projection: publishedEvidence.projection });
};

const makeWorker = (dependencies) => createDurableMutationOrchestrator({
  behavior: OBJECT_FREEZE({
    existingDryRunAttemptInspectFallback: false,
    existingDryRunAttemptRequiresDefined: false,
    existingDryRunAttemptRequiresBoolean: false,
  }),
  effects: dependencies.effects,
  errors: OBJECT_FREEZE({
    effectInvalid: (message) => fail("SESSION_OPEN_EFFECT_INVALID", message),
    recoveryInvalid: (message) => fail("SESSION_OPEN_RECOVERY_INVALID", message),
    reconciliationRequired: (message, details = undefined, options = undefined) =>
      fail("SESSION_OPEN_RECONCILIATION_REQUIRED", message, details, options),
  }),
  hooks: OBJECT_FREEZE({
    bindOperation: ({ preparedCandidate, priorEffect }) => {
      const {
        classificationProjection,
        identities,
        invocation,
        openRequest,
        publishedRequest,
      } = preparedCandidate;
      const runId = requireString(openRequest.run_spec_id, "open_request.run_spec_id", {
        min: 3,
        code: "SESSION_OPEN_REQUEST_INVALID",
      });
      const startedAt = priorEffect?.intent?.created_at ?? invocation.generatedAt;
      return OBJECT_FREEZE({
        attemptId: identities.attemptId,
        classificationProjection,
        dryRun: invocation.dryRun,
        identities,
        intentInput: {
          intent_id: identities.intentId,
          run_id: runId,
          node_id: NODE_ID,
          action_type: HANDLER_OPERATION,
          target_ref: invocation.targetRef,
          arguments_artifact_id: publishedRequest.artifactId,
          arguments_hash: publishedRequest.contentHash,
          idempotency_key: invocation.idempotencyKey,
          required_capabilities: [REQUIRED_CAPABILITY],
          approval_record_ids: invocation.approvalRecordIds,
          risk_class: ACTION_RISK_CLASS,
          created_at: startedAt,
        },
        invocation,
        openRequest,
        publishedRequest,
        runId,
        startedAt,
      });
    },
    createContext: ({ attempt, intent, operation }) => OBJECT_FREEZE({
      attempt,
      classificationProjection: operation.classificationProjection,
      identities: operation.identities,
      intent,
      invocation: operation.invocation,
      openRequest: operation.openRequest,
      workerPrincipalId: dependencies.runtime.workerPrincipalId,
    }),
    dryRunReceiptInput: ({ context, outcome }) => dryRunOpenReceiptInput({
      dependencies,
      context,
      outcome,
    }),
    errorCode: (error) => error?.code ?? error?.name ?? "unknown",
    executeEffect: ({ context, lease, setPrepared }) => executeOpenEffect({
      dependencies,
      context,
      lease,
      setPrepared,
    }),
    existingAttemptReconciliationError: () => new SessionOpenWorkerError(
      "SESSION_OPEN_EFFECT_RECONCILING",
      "an existing Attempt cannot dispatch the F04 effect again",
    ),
    isRecoveryEvidenceFailure,
    issueLease: ({ operation }) => {
      const leaseContext = detached({
        leaseId: operation.identities.leaseId,
        runId: operation.runId,
        workerPrincipalId: dependencies.runtime.workerPrincipalId,
        approvalRecordIds: operation.invocation.approvalRecordIds,
        workspaceId: operation.invocation.workspaceId,
        targetRef: operation.invocation.targetRef,
        semanticFingerprint: operation.invocation.semanticFingerprint,
        idempotencyKey: operation.invocation.idempotencyKey,
        openRequestArtifactId: operation.publishedRequest.artifactId,
        requestedAt: operation.openRequest.requested_at,
      });
      return issueLease(dependencies, leaseContext).lease;
    },
    prepareCandidate: (candidate) => {
      const invocation = normalizeInvocation(candidate);
      bindCallerInvocation(invocation);
      const classificationProjection = resolveClassificationProjection(
        dependencies.classification,
        invocation.classificationId,
      );
      const openRequest = normalizeOpenRequest({
        request_id: classificationProjection.classification.request_id,
        session_id: invocation.sessionId,
        workspace_id: invocation.workspaceId,
        run_spec_id: classificationProjection.ledger_binding.run_id,
        classification_id: invocation.classificationId,
        policy_hash: classificationProjection.identity_context.policy_bundle_hash,
        corpus_snapshot_hash: invocation.corpusSnapshotHash,
        actor: invocation.actor,
        idempotency_key: invocation.idempotencyKey,
        requested_at: invocation.requestedAt,
      });
      bindInvocation({ invocation, openRequest, classificationProjection });
      const publishedRequest = publishSessionOpenRequest(
        dependencies.artifactStore,
        openRequest,
      );
      const identities = identitiesFor(invocation, publishedRequest.contentHash);
      return OBJECT_FREEZE({
        classificationProjection,
        identities,
        intentId: identities.intentId,
        invocation,
        openRequest,
        publishedRequest,
      });
    },
    projectResult: ({ lease, operation, outcome }) => mutationPayload({
      invocation: operation.invocation,
      leaseId: lease === null ? operation.identities.leaseId : lease.lease_id,
      outcome,
      openRequest: operation.openRequest,
      artifactStore: dependencies.artifactStore,
    }),
    recoverEffect: ({ context, lease, outcome }) =>
      reconcilePublishedOpenProof({ dependencies, context, lease, outcome }),
    sameRecord: sameCanonical,
    successReceiptInput: ({ context, effectResult, outcome, prepared }) =>
      succeededOpenReceiptInput({
        dependencies,
        context,
        outcome,
        prepared,
        projection: effectResult.projection,
      }),
    unknownReceiptInput: ({ context, prepared }) => unknownOpenReceiptInput({
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

export const createSessionOpenWorker = (options) =>
  makeWorker(normalizeDependencies(options));
