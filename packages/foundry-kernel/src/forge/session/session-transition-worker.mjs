import {
  createEffectCoordinator,
  sealActionIntent,
  sealEffectReceipt,
} from "../../effects/effect-coordinator.mjs";
import {
  getCapabilityAuthorityDependencyIdentity,
} from "../../capabilities/capability-authority.mjs";

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
  getDurableForgeSessionDependencyIdentity,
} from "./durable-forge-session.mjs";

const TOOL_NAME = "foundry.session.transition";
const HANDLER_OPERATION = "mutate_session_transition";
const REQUIRED_CAPABILITY = "mcp.write.session";
const CATALOG_RISK_CLASS = "medium";
const APPROVAL_CLASS = "POLICY_CONDITIONAL";
const ACTION_RISK_CLASS = "controlled_effect";
const NODE_ID = "T02/foundry.session.transition/mutate_session_transition";
const IDENTITY_CONTRACT = "T02_SESSION_TRANSITION_WORKER_V1";
const DRY_RUN_OPERATION_ID = "urn:epistemic-foundry:non-effect:dry-run";
const PROTOCOL_VERSION = "2026-07-28";
const TRANSITION_REQUEST_SCHEMA_REF =
  "https://epistemic-foundry.local/schemas/forge-transition-request.schema.json";
const TRANSITION_REQUEST_PROVENANCE_ID = "PROV-T02-forge-transition-request";
const TRANSITION_REQUEST_ENCRYPTION_KEY_REF = "local://t02-forge-transition-request";
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const UNSIGNED_DECIMAL_PATTERN = /^(?:0|[1-9][0-9]*)$/u;
const OUTER_PHASE_TO_FORGE = OBJECT_FREEZE({
  FRAME: "F",
  OBSERVE: "O",
  REASON: "R",
  GATE: "G",
  EXPORT: "E",
  IDLE: "IDLE",
});
const FORGE_PHASES = new Set(["IDLE", "I", "F", "O", "R", "G", "E"]);
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
  "to_phase",
  "transition_request_artifact_id",
]);
const TRANSITION_REQUEST_KEYS = OBJECT_FREEZE([
  "request_id",
  "session_id",
  "expected_revision",
  "from_phase",
  "to_phase",
  "actor",
  "artifact_receipt_ids",
  "gate_result_ids",
  "human_decision_id",
  "reason",
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

export class SessionTransitionWorkerError extends Error {
  constructor(code, message, details = undefined, options = undefined) {
    super(message, options);
    this.name = "SessionTransitionWorkerError";
    this.code = code;
    if (details !== undefined) this.details = detached(details);
  }
}

export class MutationRuntimeUnavailableError extends SessionTransitionWorkerError {
  constructor(reason, details = undefined) {
    super("MUTATION_RUNTIME_UNAVAILABLE", reason, details);
    this.name = "MutationRuntimeUnavailableError";
    this.reason = reason;
  }
}

const fail = (code, message, details = undefined, options = undefined) => {
  throw new SessionTransitionWorkerError(code, message, details, options);
};

const unavailable = (reason, details = undefined) => {
  throw new MutationRuntimeUnavailableError(reason, details);
};

const dependencyMethod = (dependency, method, label) => {
  if (
    dependency === null ||
    !["object", "function"].includes(typeof dependency) ||
    IS_PROXY(dependency) ||
    typeof dependency[method] !== "function"
  ) {
    fail("SESSION_TRANSITION_INVALID_DEPENDENCY", `${label}.${method} is required`);
  }
};

const canonicalTimestamp = (candidate, label) => {
  const value = candidate instanceof Date ? candidate.toISOString() : candidate;
  requireTimestamp(value, label, "SESSION_TRANSITION_INPUT_INVALID");
  const canonical = new Date(value).toISOString();
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/u.test(canonical)) {
    fail("SESSION_TRANSITION_INPUT_INVALID", `${label} is outside the canonical range`);
  }
  return canonical;
};

const timestampFromClock = (clock) => {
  let value;
  try {
    value = clock();
  } catch (error) {
    fail("SESSION_TRANSITION_CLOCK_FAILED", "worker clock failed", undefined, {
      cause: error,
    });
  }
  if (value !== null && ["object", "function"].includes(typeof value) && "then" in value) {
    fail("SESSION_TRANSITION_ASYNC_CLOCK_DENIED", "worker clock must be synchronous");
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
  const entries = requireDenseArray(candidate, label, "SESSION_TRANSITION_INPUT_INVALID").map(
    (entry, index) => requireString(entry, `${label}[${index}]`, {
      min,
      max,
      code: "SESSION_TRANSITION_INPUT_INVALID",
    }),
  );
  if (new Set(entries).size !== entries.length) {
    fail("SESSION_TRANSITION_INPUT_INVALID", `${label} contains duplicate values`);
  }
  return OBJECT_FREEZE(sort ? [...entries].sort() : [...entries]);
};

const requireUnsignedRevision = (candidate, label) => {
  if (typeof candidate !== "string" || !UNSIGNED_DECIMAL_PATTERN.test(candidate)) {
    fail("SESSION_TRANSITION_BINDING_MISMATCH", `${label} is not canonical unsigned decimal`);
  }
  const value = Number(candidate);
  if (!NUMBER_IS_SAFE_INTEGER(value) || value < 0 || String(value) !== candidate) {
    fail("SESSION_TRANSITION_BINDING_MISMATCH", `${label} is outside the safe revision range`);
  }
  return value;
};

const normalizeTransitionRequest = (candidate) => {
  const value = exactKeys(
    candidate,
    TRANSITION_REQUEST_KEYS,
    "ForgeTransitionRequest",
    "SESSION_TRANSITION_REQUEST_INVALID",
  );
  const expectedRevision = readDataProperty(value, "expected_revision");
  if (!NUMBER_IS_SAFE_INTEGER(expectedRevision) || expectedRevision < 0) {
    fail("SESSION_TRANSITION_REQUEST_INVALID", "expected_revision is invalid");
  }
  const fromPhase = readDataProperty(value, "from_phase");
  const toPhase = readDataProperty(value, "to_phase");
  if (!FORGE_PHASES.has(fromPhase) || !FORGE_PHASES.has(toPhase)) {
    fail("SESSION_TRANSITION_REQUEST_INVALID", "Forge transition phase is invalid");
  }
  const actor = exactKeys(
    readDataProperty(value, "actor"),
    ["actor_id", "actor_type", "role"],
    "ForgeTransitionRequest.actor",
    "SESSION_TRANSITION_REQUEST_INVALID",
  );
  const actorType = readDataProperty(actor, "actor_type");
  if (!ACTOR_TYPES.has(actorType)) {
    fail("SESSION_TRANSITION_REQUEST_INVALID", "Forge transition actor_type is invalid");
  }
  const humanDecisionId = readDataProperty(value, "human_decision_id");
  if (humanDecisionId !== null) {
    requireString(humanDecisionId, "human_decision_id", {
      code: "SESSION_TRANSITION_REQUEST_INVALID",
    });
  }
  return detached({
    request_id: requireString(readDataProperty(value, "request_id"), "request_id", {
      min: 3,
      max: 128,
      code: "SESSION_TRANSITION_REQUEST_INVALID",
    }),
    session_id: requireString(readDataProperty(value, "session_id"), "session_id", {
      min: 3,
      max: 128,
      code: "SESSION_TRANSITION_REQUEST_INVALID",
    }),
    expected_revision: expectedRevision,
    from_phase: fromPhase,
    to_phase: toPhase,
    actor: {
      actor_id: requireString(readDataProperty(actor, "actor_id"), "actor.actor_id", {
        min: 3,
        max: 128,
        code: "SESSION_TRANSITION_REQUEST_INVALID",
      }),
      actor_type: actorType,
      role: requireString(readDataProperty(actor, "role"), "actor.role", {
        code: "SESSION_TRANSITION_REQUEST_INVALID",
      }),
    },
    artifact_receipt_ids: requireUniqueStrings(
      readDataProperty(value, "artifact_receipt_ids"),
      "artifact_receipt_ids",
      { min: 3, max: 128, sort: false },
    ),
    gate_result_ids: requireUniqueStrings(
      readDataProperty(value, "gate_result_ids"),
      "gate_result_ids",
      { min: 3, max: 128, sort: false },
    ),
    human_decision_id: humanDecisionId,
    reason: requireString(readDataProperty(value, "reason"), "reason", {
      min: 1,
      code: "SESSION_TRANSITION_REQUEST_INVALID",
    }),
    idempotency_key: requireString(
      readDataProperty(value, "idempotency_key"),
      "idempotency_key",
      { min: 8, code: "SESSION_TRANSITION_REQUEST_INVALID" },
    ),
    requested_at: requireTimestamp(
      readDataProperty(value, "requested_at"),
      "requested_at",
      "SESSION_TRANSITION_REQUEST_INVALID",
    ),
  });
};

export const publishSessionTransitionRequest = (artifactStore, candidate) => {
  dependencyMethod(artifactStore, "putArtifact", "artifactStore");
  const request = normalizeTransitionRequest(candidate);
  const bytes = Buffer.from(canonicalJson(request), "utf8");
  const contentHash = hashBytes(bytes);
  const artifactId = `FTR-T02-${contentHash.slice("sha256:".length)}`;
  const receiptId = `AR-${artifactId}`;

  artifactStore.putArtifact(bytes, {
    artifact: {
      artifactId,
      artifactType: "forge_transition_request",
      confidentiality: "internal",
      createdAt: request.requested_at,
      createdBy: request.actor.actor_id,
      encryption: {
        atRest: true,
        inTransit: true,
        keyRef: TRANSITION_REQUEST_ENCRYPTION_KEY_REF,
      },
      inputArtifactIds: [],
      license: null,
      lineageEventIds: [],
      mediaType: "application/json",
      provenanceManifestId: TRANSITION_REQUEST_PROVENANCE_ID,
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
      schemaRef: TRANSITION_REQUEST_SCHEMA_REF,
      validationResults: [],
    },
  });

  return detached({ artifactId, receiptId, contentHash, request });
};

const resolveTransitionRequestArtifact = (artifactStore, artifactId) => {
  let bytes;
  let manifest;
  try {
    bytes = artifactStore.readArtifact(artifactId);
    manifest = artifactStore.readManifest(artifactId);
  } catch (error) {
    fail(
      "SESSION_TRANSITION_ARTIFACT_UNAVAILABLE",
      "ForgeTransitionRequest artifact could not be resolved through D03",
      { artifactId, causeCode: error?.code ?? error?.name ?? "unknown" },
      { cause: error },
    );
  }
  if (!Buffer.isBuffer(bytes) && !(bytes instanceof Uint8Array)) {
    fail("SESSION_TRANSITION_ARTIFACT_INVALID", "D03 did not return artifact bytes");
  }
  const content = Buffer.from(bytes);
  const text = content.toString("utf8");
  if (!Buffer.from(text, "utf8").equals(content)) {
    fail("SESSION_TRANSITION_ARTIFACT_INVALID", "ForgeTransitionRequest is not canonical UTF-8");
  }
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    fail("SESSION_TRANSITION_ARTIFACT_INVALID", "ForgeTransitionRequest is malformed JSON", undefined, {
      cause: error,
    });
  }
  if (canonicalJson(parsed) !== text) {
    fail("SESSION_TRANSITION_ARTIFACT_INVALID", "ForgeTransitionRequest bytes are not canonical JSON");
  }
  const contentHash = hashBytes(content);
  if (
    manifest?.artifact_id !== artifactId ||
    manifest?.content_hash !== contentHash
  ) {
    fail("SESSION_TRANSITION_ARTIFACT_INVALID", "D03 artifact binding changed during resolution");
  }
  return OBJECT_FREEZE({
    contentHash,
    request: normalizeTransitionRequest(parsed),
  });
};

const normalizeInvocation = (candidate) => {
  const request = exactKeys(
    candidate,
    REQUEST_KEYS,
    "session transition worker request",
    "SESSION_TRANSITION_INPUT_INVALID",
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
    readDataProperty(request, "expected_revision_required") !== true
  ) {
    unavailable("the foundry.session.transition catalog binding is unavailable");
  }
  const outer = exactKeys(
    readDataProperty(request, "validated_arguments"),
    MUTATION_ARGUMENT_KEYS,
    "validated_arguments",
    "SESSION_TRANSITION_INPUT_INVALID",
  );
  const toolArguments = exactKeys(
    readDataProperty(outer, "arguments"),
    TOOL_ARGUMENT_KEYS,
    "validated_arguments.arguments",
    "SESSION_TRANSITION_INPUT_INVALID",
  );
  const dryRun = readDataProperty(outer, "dry_run");
  if (typeof dryRun !== "boolean") {
    fail("SESSION_TRANSITION_INPUT_INVALID", "dry_run must be boolean");
  }
  const outerPhase = readDataProperty(toolArguments, "to_phase");
  if (!Object.hasOwn(OUTER_PHASE_TO_FORGE, outerPhase)) {
    fail("SESSION_TRANSITION_INPUT_INVALID", "to_phase is not canonical");
  }
  const auth = requirePlainRecord(readDataProperty(request, "auth"), "auth", {
    code: "SESSION_TRANSITION_INPUT_INVALID",
  });
  const semanticFingerprint = readDataProperty(request, "semantic_fingerprint");
  if (typeof semanticFingerprint !== "string" || !SHA256_PATTERN.test(semanticFingerprint)) {
    fail("SESSION_TRANSITION_INPUT_INVALID", "semantic_fingerprint is not canonical SHA-256");
  }
  return OBJECT_FREEZE({
    approvalRecordIds: requireUniqueStrings(
      readDataProperty(outer, "approval_record_ids"),
      "approval_record_ids",
    ),
    authPrincipalId: requireString(readDataProperty(auth, "principal_id"), "auth.principal_id", {
      min: 3,
      code: "SESSION_TRANSITION_INPUT_INVALID",
    }),
    authWorkspaceId: Object.hasOwn(auth, "workspace_id")
      ? requireString(readDataProperty(auth, "workspace_id"), "auth.workspace_id", {
          min: 1,
          code: "SESSION_TRANSITION_INPUT_INVALID",
        })
      : null,
    dryRun,
    expectedRevision: requireString(
      readDataProperty(outer, "expected_revision"),
      "expected_revision",
      { min: 1, code: "SESSION_TRANSITION_INPUT_INVALID" },
    ),
    generatedAt: canonicalTimestamp(readDataProperty(request, "generated_at"), "generated_at"),
    idempotencyKey: requireString(
      readDataProperty(outer, "idempotency_key"),
      "idempotency_key",
      { min: 1, max: 200, code: "SESSION_TRANSITION_INPUT_INVALID" },
    ),
    outerPhase,
    requestId: requireString(readDataProperty(request, "request_id"), "request_id", {
      min: 1,
      code: "SESSION_TRANSITION_INPUT_INVALID",
    }),
    semanticFingerprint,
    sessionId: requireString(readDataProperty(toolArguments, "session_id"), "arguments.session_id", {
      min: 1,
      code: "SESSION_TRANSITION_INPUT_INVALID",
    }),
    targetRef: requireString(readDataProperty(outer, "target_ref"), "target_ref", {
      min: 1,
      code: "SESSION_TRANSITION_INPUT_INVALID",
    }),
    transitionRequestArtifactId: requireString(
      readDataProperty(toolArguments, "transition_request_artifact_id"),
      "arguments.transition_request_artifact_id",
      { min: 1, code: "SESSION_TRANSITION_INPUT_INVALID" },
    ),
    workspaceId: requireString(readDataProperty(outer, "workspace_id"), "workspace_id", {
      min: 1,
      code: "SESSION_TRANSITION_INPUT_INVALID",
    }),
  });
};

export const createSessionTransitionRuntimeRequest = (candidate) => {
  const value = exactKeys(
    candidate,
    RUNTIME_REQUEST_FACTORY_KEYS,
    "session transition runtime request options",
    "SESSION_TRANSITION_INPUT_INVALID",
  );
  const auth = requirePlainRecord(
    readDataProperty(value, "auth"),
    "auth",
    { code: "SESSION_TRANSITION_INPUT_INVALID" },
  );
  const validatedArguments = exactKeys(
    readDataProperty(value, "validatedArguments"),
    MUTATION_ARGUMENT_KEYS,
    "validatedArguments",
    "SESSION_TRANSITION_INPUT_INVALID",
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
    expected_revision_required: true,
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
    ["stateStore", "artifactStore", "ledger", "authority", "session", "clock", "runtime"],
    "session transition worker options",
    "SESSION_TRANSITION_INVALID_DEPENDENCY",
  );
  const dependencies = Object.fromEntries(
    ["stateStore", "artifactStore", "ledger", "authority", "session", "clock", "runtime"]
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
  for (const method of [
    "readSession",
    "inspectTransition",
    "prepareTransition",
    "transitionSession",
  ]) {
    dependencyMethod(dependencies.session, method, "session");
  }
  if (typeof dependencies.clock !== "function" || IS_PROXY(dependencies.clock)) {
    fail("SESSION_TRANSITION_INVALID_DEPENDENCY", "clock must be a trusted synchronous function");
  }
  let authorityIdentity;
  let sessionIdentity;
  try {
    authorityIdentity = getCapabilityAuthorityDependencyIdentity(dependencies.authority);
    sessionIdentity = getDurableForgeSessionDependencyIdentity(dependencies.session);
  } catch (error) {
    fail(
      "SESSION_TRANSITION_INVALID_DEPENDENCY",
      "authority and session must be canonical Kernel ports",
      { causeCode: error?.code ?? error?.name ?? "unknown" },
      { cause: error },
    );
  }
  for (const [label, identity] of [
    ["authority", authorityIdentity],
    ["session", sessionIdentity],
  ]) {
    for (const key of ["stateStore", "artifactStore", "ledger", "clock"]) {
      if (identity[key] !== dependencies[key]) {
        fail(
          "SESSION_TRANSITION_DEPENDENCY_IDENTITY_MISMATCH",
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
    "session transition runtime config",
    "SESSION_TRANSITION_INVALID_DEPENDENCY",
  );
  const leaseCommandFactory = readDataProperty(runtime, "leaseCommandFactory");
  if (typeof leaseCommandFactory !== "function" || IS_PROXY(leaseCommandFactory)) {
    fail(
      "SESSION_TRANSITION_INVALID_DEPENDENCY",
      "runtime.leaseCommandFactory must be a trusted synchronous function",
    );
  }
  return OBJECT_FREEZE({
    ...dependencies,
    effects,
    runtime: OBJECT_FREEZE({
      authorityPrincipalId: requireString(
        readDataProperty(runtime, "authorityPrincipalId"),
        "runtime.authorityPrincipalId",
        { min: 3, code: "SESSION_TRANSITION_INVALID_DEPENDENCY" },
      ),
      workerPrincipalId: requireString(
        readDataProperty(runtime, "workerPrincipalId"),
        "runtime.workerPrincipalId",
        { min: 3, code: "SESSION_TRANSITION_INVALID_DEPENDENCY" },
      ),
      leaseCommandFactory,
    }),
  });
};

const bindInvocation = ({ invocation, transitionRequest, published, requireCurrentState }) => {
  const state = requirePlainRecord(published?.state, "published session state", {
    code: "SESSION_TRANSITION_SESSION_INVALID",
  });
  const revision = readDataProperty(state, "revision");
  const outerRevision = requireUnsignedRevision(invocation.expectedRevision, "expected_revision");
  if (
    invocation.targetRef !== invocation.sessionId ||
    invocation.sessionId !== transitionRequest.session_id ||
    transitionRequest.session_id !== readDataProperty(state, "session_id")
  ) {
    fail("SESSION_TRANSITION_BINDING_MISMATCH", "target_ref and session identities disagree");
  }
  if (
    invocation.workspaceId !== readDataProperty(state, "workspace_id") ||
    (invocation.authWorkspaceId !== null && invocation.authWorkspaceId !== invocation.workspaceId)
  ) {
    fail("SESSION_TRANSITION_BINDING_MISMATCH", "workspace binding disagrees with F04 state");
  }
  if (invocation.authPrincipalId !== transitionRequest.actor.actor_id) {
    fail("SESSION_TRANSITION_BINDING_MISMATCH", "authenticated principal differs from request actor");
  }
  if (invocation.idempotencyKey !== transitionRequest.idempotency_key) {
    fail("SESSION_TRANSITION_BINDING_MISMATCH", "outer and stored idempotency keys disagree");
  }
  if (
    outerRevision !== transitionRequest.expected_revision ||
    (requireCurrentState && outerRevision !== revision)
  ) {
    fail("SESSION_TRANSITION_BINDING_MISMATCH", "expected revision differs from request or F04 state");
  }
  if (
    transitionRequest.to_phase !== OUTER_PHASE_TO_FORGE[invocation.outerPhase] ||
    (requireCurrentState && transitionRequest.from_phase !== readDataProperty(state, "phase"))
  ) {
    fail("SESSION_TRANSITION_BINDING_MISMATCH", "outer or stored transition phase disagrees with F04 state");
  }
  return OBJECT_FREEZE({ outerRevision, state });
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
    "SESSION_TRANSITION_LEASE_COMMAND_INVALID",
  );
  const command = detached({
    lease_id: requireString(readDataProperty(value, "lease_id"), "lease_id", {
      min: 3,
      max: 128,
      code: "SESSION_TRANSITION_LEASE_COMMAND_INVALID",
    }),
    run_id: requireString(readDataProperty(value, "run_id"), "run_id", {
      min: 1,
      code: "SESSION_TRANSITION_LEASE_COMMAND_INVALID",
    }),
    principal_id: requireString(readDataProperty(value, "principal_id"), "principal_id", {
      min: 3,
      code: "SESSION_TRANSITION_LEASE_COMMAND_INVALID",
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
      "SESSION_TRANSITION_LEASE_COMMAND_INVALID",
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
    fail("SESSION_TRANSITION_LEASE_COMMAND_FAILED", "lease command factory failed", undefined, {
      cause: error,
    });
  }
  if (candidate !== null && ["object", "function"].includes(typeof candidate) && "then" in candidate) {
    fail("SESSION_TRANSITION_LEASE_COMMAND_FAILED", "lease command factory must be synchronous");
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
    fail("SESSION_TRANSITION_LEASE_INVALID", "E03 returned a lease outside the requested binding");
  }
  requireHash(lease.lease_hash, "lease.lease_hash", "SESSION_TRANSITION_LEASE_INVALID");
  return OBJECT_FREEZE({ command, lease });
};

const readLedgerEvents = (ledger, runId) => {
  let events;
  try {
    events = ledger.readEvents(runId);
  } catch (error) {
    fail("SESSION_TRANSITION_LEDGER_INVALID", "E01 readEvents failed", undefined, {
      cause: error,
    });
  }
  if (!ARRAY_IS_ARRAY(events)) {
    fail("SESSION_TRANSITION_LEDGER_INVALID", "E01 readEvents did not return an array");
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
      fail("SESSION_TRANSITION_LEDGER_INVALID", "E01 event sequence or identity is invalid");
    }
    requireHash(event.event_hash, "event.event_hash", "SESSION_TRANSITION_LEDGER_INVALID");
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
      code: "SESSION_TRANSITION_LEDGER_INVALID",
    }),
    tail_event_hash: requireHash(
      tail.event_hash,
      "tail.event_hash",
      "SESSION_TRANSITION_LEDGER_INVALID",
    ),
  });
};

const normalizePreparationResult = (candidate, transitionRequest) => {
  const value = exactKeys(
    candidate,
    PREPARATION_RESULT_KEYS,
    "F04 transition preparation result",
    "SESSION_TRANSITION_PREPARATION_INVALID",
  );
  if (!new Set(["PREPARED", "EXISTING"]).has(value.status)) {
    fail("SESSION_TRANSITION_PREPARATION_INVALID", "F04 preparation status is invalid");
  }
  for (const key of ["request_hash", "candidate_state_hash"]) {
    requireHash(value[key], `preparation.${key}`, "SESSION_TRANSITION_PREPARATION_INVALID");
  }
  if (
    value.session_id !== transitionRequest.session_id ||
    value.expected_revision !== transitionRequest.expected_revision ||
    !NUMBER_IS_SAFE_INTEGER(value.new_revision) ||
    value.new_revision < 0
  ) {
    fail("SESSION_TRANSITION_PREPARATION_INVALID", "F04 preparation result changed transition identity");
  }
  for (const key of ["operation_id", "outbox_id", "payload_artifact_id"]) {
    requireString(value[key], `preparation.${key}`, {
      min: 1,
      code: "SESSION_TRANSITION_PREPARATION_INVALID",
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
    "SESSION_TRANSITION_RECOVERY_INVALID",
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
    "SESSION_TRANSITION_RECOVERY_INVALID",
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
    fail("SESSION_TRANSITION_RECOVERY_INVALID", "E03 lease-use recovery binding changed");
  }
  for (const key of ["request_hash", "lease_use_hash"]) {
    requireHash(value[key], `lease use.${key}`, "SESSION_TRANSITION_RECOVERY_INVALID");
  }
  for (const key of ["lease_use_id", "event_outbox_id"]) {
    requireString(value[key], `lease use.${key}`, {
      min: 1,
      code: "SESSION_TRANSITION_RECOVERY_INVALID",
    });
  }
  if (
    !new Set(["PUBLISHED", "PENDING_EVENT_RECONCILIATION"]).has(
      value.event_publication_status,
    ) ||
    (value.event_publication_status === "PUBLISHED") !== (event.event_hash !== null)
  ) {
    fail("SESSION_TRANSITION_RECOVERY_INVALID", "E03 event publication state is invalid");
  }
  requireString(event.event_id, "lease use event.event_id", {
    min: 1,
    code: "SESSION_TRANSITION_RECOVERY_INVALID",
  });
  requireString(event.payload_artifact_id, "lease use event.payload_artifact_id", {
    min: 1,
    code: "SESSION_TRANSITION_RECOVERY_INVALID",
  });
  canonicalTimestamp(event.occurred_at, "lease use event.occurred_at");
  if (event.event_hash !== null) {
    requireHash(event.event_hash, "lease use event.event_hash", "SESSION_TRANSITION_RECOVERY_INVALID");
  }
  return detached(value);
};

const normalizePublishedTransitionInspection = ({ candidate, prepared, context }) => {
  const value = exactKeys(
    candidate,
    ["status", "preparation", "projection", "ledger_event", "artifact"],
    "F04 transition inspection",
    "SESSION_TRANSITION_RECOVERY_INVALID",
  );
  if (!new Set(["ABSENT", "PENDING", "PUBLISHED", "CONFLICTED"]).has(value.status)) {
    fail("SESSION_TRANSITION_RECOVERY_INVALID", "F04 transition inspection status is invalid");
  }
  if (value.status !== "PUBLISHED") return null;
  const inspectedPreparation = normalizePreparationResult(
    value.preparation,
    context.transitionRequest,
  );
  if (!sameCanonical(preparationBinding(inspectedPreparation), preparationBinding(prepared))) {
    fail("SESSION_TRANSITION_RECOVERY_INVALID", "F04 preparation identity changed during recovery");
  }
  const projection = requirePlainRecord(value.projection, "F04 operation projection", {
    code: "SESSION_TRANSITION_RECOVERY_INVALID",
  });
  const state = requirePlainRecord(projection.state, "F04 operation state", {
    code: "SESSION_TRANSITION_RECOVERY_INVALID",
  });
  const artifact = exactKeys(
    value.artifact,
    ["artifact_id", "content_hash", "manifest_hash", "receipt_id", "receipt_hash"],
    "F04 operation artifact",
    "SESSION_TRANSITION_RECOVERY_INVALID",
  );
  const ledgerEvent = requirePlainRecord(value.ledger_event, "F04 operation ledger event", {
    code: "SESSION_TRANSITION_RECOVERY_INVALID",
  });
  if (
    artifact.artifact_id !== prepared.payload_artifact_id ||
    state.session_id !== prepared.session_id ||
    state.revision !== prepared.new_revision ||
    state.state_hash !== prepared.candidate_state_hash ||
    ledgerEvent.run_id !== context.intent.run_id ||
    ledgerEvent.event_type !== "forge.session.transitioned" ||
    ledgerEvent.aggregate_type !== "forge_session" ||
    ledgerEvent.aggregate_id !== prepared.session_id ||
    ledgerEvent.actor_id !== context.transitionRequest.actor.actor_id ||
    ledgerEvent.payload_artifact_id !== prepared.payload_artifact_id ||
    projection.last_session_event_id !== ledgerEvent.event_id ||
    projection.last_session_event_hash !== ledgerEvent.event_hash
  ) {
    fail("SESSION_TRANSITION_RECOVERY_INVALID", "F04 published operation binding changed");
  }
  for (const key of ["content_hash", "manifest_hash", "receipt_hash"]) {
    requireHash(artifact[key], `F04 artifact.${key}`, "SESSION_TRANSITION_RECOVERY_INVALID");
  }
  requireHash(projection.projection_hash, "F04 projection_hash", "SESSION_TRANSITION_RECOVERY_INVALID");
  requireHash(ledgerEvent.event_hash, "F04 event_hash", "SESSION_TRANSITION_RECOVERY_INVALID");
  return detached({ artifact, ledgerEvent, projection });
};

const ledgerContainsExactEvent = ({ ledger, runId, event }) => {
  const events = readLedgerEvents(ledger, runId);
  const matching = events.filter((candidate) => candidate.event_id === event.event_id);
  return matching.length === 1 && sameCanonical(matching[0], event);
};

const ledgerProvesPublishedTransition = ({ ledger, runId, leaseUse, published }) => {
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
    fail("SESSION_TRANSITION_RESULT_INVALID", "F04 result artifact bytes are unavailable");
  }
  const content = Buffer.from(bytes);
  const text = content.toString("utf8");
  if (!Buffer.from(text, "utf8").equals(content) || !text.endsWith("\n")) {
    fail("SESSION_TRANSITION_RESULT_INVALID", "F04 result artifact is not canonical UTF-8 JSON");
  }
  let payload;
  try {
    payload = JSON.parse(text.slice(0, -1));
  } catch (error) {
    fail("SESSION_TRANSITION_RESULT_INVALID", "F04 result artifact is malformed", undefined, {
      cause: error,
    });
  }
  if (`${canonicalJson(payload)}\n` !== text) {
    fail("SESSION_TRANSITION_RESULT_INVALID", "F04 result artifact is not canonical JSON");
  }
  return requirePlainRecord(payload, "F04 result payload", {
    code: "SESSION_TRANSITION_RESULT_INVALID",
  });
};

const resultRevisionFromReceipt = (artifactStore, receipt, transitionRequest) => {
  if (receipt.result_artifact_ids.length !== 1) {
    fail("SESSION_TRANSITION_RESULT_INVALID", "successful receipt must bind one F04 payload");
  }
  const payload = strictF04Payload(artifactStore, receipt.result_artifact_ids[0]);
  const candidateState = requirePlainRecord(payload.candidate_state, "F04 candidate_state", {
    code: "SESSION_TRANSITION_RESULT_INVALID",
  });
  if (
    payload.kind !== "TRANSITION" ||
    payload.operation_id !== receipt.external_operation_id ||
    payload.session_id !== transitionRequest.session_id ||
    payload.request?.idempotency_key !== transitionRequest.idempotency_key ||
    payload.request?.expected_revision !== transitionRequest.expected_revision
  ) {
    fail("SESSION_TRANSITION_RESULT_INVALID", "successful receipt differs from its F04 operation");
  }
  const revision = candidateState.revision;
  if (!NUMBER_IS_SAFE_INTEGER(revision) || revision < 0) {
    fail("SESSION_TRANSITION_RESULT_INVALID", "F04 result revision is invalid");
  }
  return String(revision);
};

const mutationPayload = ({
  invocation,
  leaseId,
  outcome,
  transitionRequest,
  artifactStore,
}) => {
  const receipt = outcome.receipt;
  if (receipt === null || receipt === undefined) {
    fail("SESSION_TRANSITION_RECEIPT_MISSING", "E02 outcome has no EffectReceipt");
  }
  const status = receipt.status;
  if (status !== "UNKNOWN" && outcome.reconciliation_required) {
    fail(
      "SESSION_TRANSITION_RECONCILIATION_REQUIRED",
      "terminal E02 records still require event reconciliation",
    );
  }
  const committed = status === "UNKNOWN" ? null : status === "SUCCEEDED";
  return detached({
    mutation: {
      action_intent_id: outcome.intent.intent_id,
      capability_lease_id: leaseId,
      effect_receipt_id: receipt.receipt_id,
      dry_run: invocation.dryRun,
      effect_status: status,
      committed,
      expected_revision: invocation.expectedRevision,
      observed_revision: invocation.expectedRevision,
      new_revision:
        status === "SUCCEEDED"
          ? resultRevisionFromReceipt(artifactStore, receipt, transitionRequest)
          : null,
      reconciliation_required: status === "UNKNOWN",
    },
    preview: null,
  });
};

const persistReceipt = (effects, attemptId, receipt, mode) => {
  const method = mode === "RECONCILIATION" ? "reconcile" : "recordReceipt";
  try {
    return effects[method]({ attempt_id: attemptId, receipt }).outcome;
  } catch (error) {
    let inspected;
    try {
      inspected = effects.inspect(receipt.intent_id);
    } catch {
      throw error;
    }
    if (inspected.receipt?.receipt_id !== receipt.receipt_id) throw error;
    try {
      return effects[method]({ attempt_id: attemptId, receipt }).outcome;
    } catch {
      return effects.inspect(receipt.intent_id);
    }
  }
};

const republishExistingReceipt = (effects, outcome) => {
  if (
    (!outcome.event_reconciliation_required && !outcome.publication_confirmation_required) ||
    outcome.receipt === null
  ) {
    return outcome;
  }
  const mode = outcome.receipt_count > 1 ? "RECONCILIATION" : "EXECUTION";
  return persistReceipt(effects, outcome.attempt.attempt_id, outcome.receipt, mode);
};

const terminalOutcome = (outcome) =>
  outcome.receipt !== null && outcome.receipt.status !== "UNKNOWN";

const recordUnknown = ({ dependencies, context, error, prepared }) => {
  let outcome = dependencies.effects.inspect(context.intent.intent_id);
  if (terminalOutcome(outcome)) {
    if (outcome.reconciliation_required) {
      fail(
        "SESSION_TRANSITION_RECONCILIATION_REQUIRED",
        "terminal E02 records still require event reconciliation",
      );
    }
    return outcome;
  }
  if (outcome.receipt?.status === "UNKNOWN") return outcome;
  const finishedAt = latestTimestamp(
    context.attempt.started_at,
    timestampFromClock(dependencies.clock),
  );
  const receipt = sealEffectReceipt({
    receipt_id: context.identities.unknownReceiptId,
    intent_id: context.intent.intent_id,
    run_id: context.intent.run_id,
    external_operation_id: prepared?.operation_id ?? null,
    status: "UNKNOWN",
    result_artifact_ids: [],
    error_artifact_ids: [],
    observed_state_hash: context.initialProjection.projection_hash,
    idempotency_key: context.invocation.idempotencyKey,
    started_at: context.attempt.started_at,
    finished_at: finishedAt,
    reconciliation_required: true,
  });
  try {
    outcome = persistReceipt(
      dependencies.effects,
      context.attempt.attempt_id,
      receipt,
      "EXECUTION",
    );
  } catch (receiptError) {
    fail(
      "SESSION_TRANSITION_RECONCILIATION_REQUIRED",
      "post-Attempt failure could not be bound to an UNKNOWN EffectReceipt",
      {
        causeCode: error?.code ?? error?.name ?? "unknown",
        receiptCauseCode: receiptError?.code ?? receiptError?.name ?? "unknown",
      },
      { cause: receiptError },
    );
  }
  return outcome;
};

const sealNotExecutedTransitionReceipt = ({ dependencies, context, outcome }) =>
  sealEffectReceipt({
    receipt_id: context.identities.dryReceiptId,
    intent_id: context.intent.intent_id,
    run_id: context.intent.run_id,
    external_operation_id: DRY_RUN_OPERATION_ID,
    status: "NOT_EXECUTED",
    result_artifact_ids: [],
    error_artifact_ids: [],
    observed_state_hash: context.initialProjection.projection_hash,
    idempotency_key: context.invocation.idempotencyKey,
    started_at: context.attempt.started_at,
    finished_at: latestTimestamp(
      context.attempt.started_at,
      outcome.receipt?.finished_at ?? context.attempt.started_at,
      timestampFromClock(dependencies.clock),
    ),
    reconciliation_required: false,
  });

const completeDryRun = ({ dependencies, context, outcome, mode }) => {
  const receipt = sealNotExecutedTransitionReceipt({ dependencies, context, outcome });
  const completed = persistReceipt(
    dependencies.effects,
    context.attempt.attempt_id,
    receipt,
    mode,
  );
  if (completed.reconciliation_required) {
    fail(
      "SESSION_TRANSITION_RECONCILIATION_REQUIRED",
      "dry-run EffectReceipt event publication remains unresolved",
    );
  }
  return completed;
};

const sealSucceededTransitionReceipt = ({
  dependencies,
  context,
  outcome,
  prepared,
  projection,
}) => sealEffectReceipt({
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
  "SESSION_TRANSITION_RECOVERY_INVALID",
  "SESSION_TRANSITION_PREPARATION_INVALID",
  "SESSION_TRANSITION_INPUT_INVALID",
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

const reconcilePublishedTransitionProof = ({ dependencies, context, lease, outcome }) => {
  if (
    outcome.intent.intent_id !== context.intent.intent_id ||
    outcome.attempt?.attempt_id !== context.attempt.attempt_id
  ) {
    fail("SESSION_TRANSITION_RECOVERY_INVALID", "E02 recovery identity changed");
  }
  if (outcome.receipt !== null && outcome.receipt.status !== "UNKNOWN") return outcome;

  const inspectedLeaseUse = dependencies.authority.inspectLeaseUse(
    context.identities.leaseUseOperationId,
  );
  let leaseUse = normalizeLeaseUseInspection({
    candidate: inspectedLeaseUse,
    context,
    lease,
  });
  if (leaseUse === null) return outcome;

  const prepared = normalizePreparationResult(
    leaseUse.result,
    context.transitionRequest,
  );
  if (
    outcome.receipt?.external_operation_id !== null &&
    outcome.receipt?.external_operation_id !== undefined &&
    outcome.receipt.external_operation_id !== prepared.operation_id
  ) {
    fail(
      "SESSION_TRANSITION_RECOVERY_INVALID",
      "UNKNOWN receipt is bound to another F04 operation",
    );
  }

  const inspection = dependencies.session.inspectTransition({
    transition_request: context.transitionRequest,
    expected_ledger_head: prepared.expected_ledger_head,
  });
  const published = normalizePublishedTransitionInspection({
    candidate: inspection,
    prepared,
    context,
  });
  if (published === null) return outcome;
  if (!ledgerContainsExactEvent({
    ledger: dependencies.ledger,
    runId: context.intent.run_id,
    event: published.ledgerEvent,
  })) {
    return outcome;
  }
  if (leaseUse.event_publication_status !== "PUBLISHED") {
    leaseUse = normalizeLeaseUseInspection({
      candidate: dependencies.authority.reconcileLeaseUseEvent(
        context.identities.leaseUseOperationId,
      ),
      context,
      lease,
    });
    if (leaseUse?.event_publication_status !== "PUBLISHED") return outcome;
  }
  if (!ledgerProvesPublishedTransition({
    ledger: dependencies.ledger,
    runId: context.intent.run_id,
    leaseUse,
    published,
  })) {
    return outcome;
  }

  const receipt = sealSucceededTransitionReceipt({
    dependencies,
    context,
    outcome,
    prepared,
    projection: published.projection,
  });
  const reconciled = persistReceipt(
    dependencies.effects,
    context.attempt.attempt_id,
    receipt,
    "RECONCILIATION",
  );
  if (reconciled.reconciliation_required) {
    fail(
      "SESSION_TRANSITION_RECONCILIATION_REQUIRED",
      "recovered EffectReceipt event publication remains unresolved",
    );
  }
  return reconciled;
};

const reconcilePublishedTransition = (candidate) => {
  try {
    return reconcilePublishedTransitionProof(candidate);
  } catch (error) {
    if (isRecoveryEvidenceFailure(error)) return candidate.outcome;
    throw error;
  }
};

const makeWorker = (dependencies) => {
  const execute = (candidate) => {
    const invocation = normalizeInvocation(candidate);
    const resolved = resolveTransitionRequestArtifact(
      dependencies.artifactStore,
      invocation.transitionRequestArtifactId,
    );
    const transitionRequest = resolved.request;
    const initialProjection = dependencies.session.readSession(invocation.sessionId);
    if (initialProjection === null) {
      fail("SESSION_TRANSITION_SESSION_NOT_FOUND", "published F04 session does not exist");
    }
    const identities = identitiesFor(invocation, resolved.contentHash);
    let priorEffect = null;
    try {
      priorEffect = dependencies.effects.inspect(identities.intentId);
    } catch (error) {
      if (error?.code !== "EFFECT_RECORD_MISSING") throw error;
    }
    const { state } = bindInvocation({
      invocation,
      transitionRequest,
      published: initialProjection,
      requireCurrentState: priorEffect === null,
    });
    const runId = requireString(state.run_spec_id, "session.run_spec_id", {
      min: 1,
      code: "SESSION_TRANSITION_SESSION_INVALID",
    });
    const effectStartedAt = priorEffect?.intent?.created_at ?? invocation.generatedAt;
    const intent = sealActionIntent({
      intent_id: identities.intentId,
      run_id: runId,
      node_id: NODE_ID,
      action_type: HANDLER_OPERATION,
      target_ref: invocation.targetRef,
      arguments_artifact_id: invocation.transitionRequestArtifactId,
      arguments_hash: resolved.contentHash,
      idempotency_key: invocation.idempotencyKey,
      required_capabilities: [REQUIRED_CAPABILITY],
      approval_record_ids: invocation.approvalRecordIds,
      risk_class: ACTION_RISK_CLASS,
      created_at: effectStartedAt,
    });
    if (priorEffect !== null && !sameCanonical(priorEffect.intent, intent)) {
      fail(
        "SESSION_TRANSITION_EFFECT_INVALID",
        "stored E02 ActionIntent differs from this semantic replay",
      );
    }
    if (invocation.dryRun && priorEffect !== null && priorEffect.attempt !== null) {
      const storedAttempt = priorEffect.attempt;
      if (
        storedAttempt.attempt_id !== identities.attemptId ||
        storedAttempt.intent_id !== intent.intent_id ||
        storedAttempt.started_at !== effectStartedAt
      ) {
        fail("SESSION_TRANSITION_EFFECT_INVALID", "stored dry-run Attempt binding changed");
      }
      let registration;
      try {
        registration = dependencies.effects.registerIntent(intent);
      } catch {
        registration = dependencies.effects.registerIntent(intent);
      }
      if (!new Set(["REGISTERED", "EXISTING"]).has(registration.status)) {
        fail("SESSION_TRANSITION_EFFECT_INVALID", "E02 returned an unknown intent status");
      }
      let attemptResult;
      try {
        attemptResult = dependencies.effects.beginAttempt({
          attempt_id: storedAttempt.attempt_id,
          intent_id: intent.intent_id,
          started_at: storedAttempt.started_at,
        });
      } catch {
        attemptResult = dependencies.effects.beginAttempt({
          attempt_id: storedAttempt.attempt_id,
          intent_id: intent.intent_id,
          started_at: storedAttempt.started_at,
        });
      }
      if (
        attemptResult.execute_permitted !== false ||
        !sameCanonical(attemptResult.attempt, storedAttempt)
      ) {
        fail(
          "SESSION_TRANSITION_EFFECT_INVALID",
          "existing dry-run Attempt unexpectedly permits execution",
        );
      }
      const context = OBJECT_FREEZE({
        attempt: storedAttempt,
        identities,
        initialProjection,
        intent,
        invocation,
        transitionRequest,
        workerPrincipalId: dependencies.runtime.workerPrincipalId,
      });
      let outcome = republishExistingReceipt(
        dependencies.effects,
        dependencies.effects.inspect(intent.intent_id),
      );
      if (!terminalOutcome(outcome)) {
        outcome = completeDryRun({
          dependencies,
          context,
          outcome,
          mode: "RECONCILIATION",
        });
      }
      if (outcome.reconciliation_required) {
        fail(
          "SESSION_TRANSITION_RECONCILIATION_REQUIRED",
          "dry-run EffectReceipt event publication remains unresolved",
        );
      }
      return mutationPayload({
        invocation,
        leaseId: identities.leaseId,
        outcome,
        transitionRequest,
        artifactStore: dependencies.artifactStore,
      });
    }
    const leaseContext = detached({
      leaseId: identities.leaseId,
      runId,
      workerPrincipalId: dependencies.runtime.workerPrincipalId,
      approvalRecordIds: invocation.approvalRecordIds,
      workspaceId: invocation.workspaceId,
      targetRef: invocation.targetRef,
      semanticFingerprint: invocation.semanticFingerprint,
      idempotencyKey: invocation.idempotencyKey,
      transitionRequestArtifactId: invocation.transitionRequestArtifactId,
      requestedAt: transitionRequest.requested_at,
    });
    const { lease } = issueLease(dependencies, leaseContext);

    let registration;
    try {
      registration = dependencies.effects.registerIntent(intent);
    } catch {
      registration = dependencies.effects.registerIntent(intent);
    }
    if (!new Set(["REGISTERED", "EXISTING"]).has(registration.status)) {
      fail("SESSION_TRANSITION_EFFECT_INVALID", "E02 returned an unknown intent status");
    }

    let attemptResult;
    try {
      attemptResult = dependencies.effects.beginAttempt({
        attempt_id: identities.attemptId,
        intent_id: intent.intent_id,
        started_at: effectStartedAt,
      });
    } catch (error) {
      try {
        attemptResult = dependencies.effects.beginAttempt({
          attempt_id: identities.attemptId,
          intent_id: intent.intent_id,
          started_at: effectStartedAt,
        });
      } catch {
        let inspected;
        try {
          inspected = dependencies.effects.inspect(intent.intent_id);
        } catch {
          throw error;
        }
        if (inspected.attempt === null) throw error;
        attemptResult = OBJECT_FREEZE({
          attempt: inspected.attempt,
          execute_permitted: false,
          status: "EXISTING_ATTEMPT",
        });
      }
    }
    const attempt = attemptResult.attempt;
    if (typeof attemptResult.execute_permitted !== "boolean") {
      fail("SESSION_TRANSITION_EFFECT_INVALID", "E02 omitted execute_permitted");
    }
    const context = OBJECT_FREEZE({
      attempt,
      identities,
      initialProjection,
      intent,
      invocation,
      transitionRequest,
      workerPrincipalId: dependencies.runtime.workerPrincipalId,
    });
    let outcome;
    try {
      outcome = republishExistingReceipt(
        dependencies.effects,
        dependencies.effects.inspect(intent.intent_id),
      );
    } catch (error) {
      outcome = recordUnknown({ dependencies, context, error, prepared: null });
      return mutationPayload({
        invocation,
        leaseId: lease.lease_id,
        outcome,
        transitionRequest,
        artifactStore: dependencies.artifactStore,
      });
    }
    if (terminalOutcome(outcome)) {
      if (outcome.reconciliation_required) {
        fail(
          "SESSION_TRANSITION_RECONCILIATION_REQUIRED",
          "terminal E02 records still require event reconciliation",
        );
      }
      return mutationPayload({
        invocation,
        leaseId: lease.lease_id,
        outcome,
        transitionRequest,
        artifactStore: dependencies.artifactStore,
      });
    }

    if (!attemptResult.execute_permitted) {
      if (invocation.dryRun) {
        outcome = completeDryRun({
          dependencies,
          context,
          outcome,
          mode: "RECONCILIATION",
        });
        return mutationPayload({
          invocation,
          leaseId: lease.lease_id,
          outcome,
          transitionRequest,
          artifactStore: dependencies.artifactStore,
        });
      }
      outcome = reconcilePublishedTransition({
        dependencies,
        context,
        lease,
        outcome,
      });
      if (terminalOutcome(outcome)) {
        return mutationPayload({
          invocation,
          leaseId: lease.lease_id,
          outcome,
          transitionRequest,
          artifactStore: dependencies.artifactStore,
        });
      }
      if (outcome.receipt?.status !== "UNKNOWN") {
        outcome = recordUnknown({
          dependencies,
          context,
          error: new SessionTransitionWorkerError(
            "SESSION_TRANSITION_EFFECT_RECONCILING",
            "an existing Attempt cannot dispatch the F04 effect again",
          ),
          prepared: null,
        });
      }
      return mutationPayload({
        invocation,
        leaseId: lease.lease_id,
        outcome,
        transitionRequest,
        artifactStore: dependencies.artifactStore,
      });
    }

    if (invocation.dryRun) {
      outcome = completeDryRun({
        dependencies,
        context,
        outcome,
        mode: outcome.receipt?.status === "UNKNOWN" ? "RECONCILIATION" : "EXECUTION",
      });
      return mutationPayload({
        invocation,
        leaseId: lease.lease_id,
        outcome,
        transitionRequest,
        artifactStore: dependencies.artifactStore,
      });
    }

    let prepared = null;
    try {
      const head = currentLedgerHead(dependencies.ledger, runId);
      const initialCandidate = detached({
        transition_request: transitionRequest,
        expected_ledger_head: head,
      });
      const leaseCommit = dependencies.authority.commitWithLeaseDeferredEvent(
        {
          operation_id: identities.leaseUseOperationId,
          run_id: runId,
          lease,
          principal_id: dependencies.runtime.workerPrincipalId,
          capability: REQUIRED_CAPABILITY,
          resource_scopes: lease.resource_scopes,
        },
        (transactionStore) => dependencies.session.prepareTransition(
          transactionStore,
          initialCandidate,
        ),
        Object.values(DURABLE_FORGE_SESSION_RECORD_TYPES),
      );
      prepared = normalizePreparationResult(leaseCommit.result, transitionRequest);
      const published = dependencies.session.transitionSession({
        transition_request: transitionRequest,
        expected_ledger_head: prepared.expected_ledger_head,
      });
      if (
        published.state.revision !== prepared.new_revision ||
        published.state.state_hash !== prepared.candidate_state_hash
      ) {
        fail("SESSION_TRANSITION_RESULT_INVALID", "published F04 projection differs from preparation");
      }
      const inspection = dependencies.session.inspectTransition({
        transition_request: transitionRequest,
        expected_ledger_head: prepared.expected_ledger_head,
      });
      const publishedEvidence = normalizePublishedTransitionInspection({
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
          "SESSION_TRANSITION_RESULT_INVALID",
          "F04 publication is not durably present in E01",
        );
      }
      let leaseUse = normalizeLeaseUseInspection({
        candidate: dependencies.authority.inspectLeaseUse(
          identities.leaseUseOperationId,
        ),
        context,
        lease,
      });
      if (leaseUse === null) {
        fail("SESSION_TRANSITION_RESULT_INVALID", "E03 lease use is missing after F04 publication");
      }
      const inspectedPreparation = normalizePreparationResult(
        leaseUse.result,
        transitionRequest,
      );
      if (!sameCanonical(
        preparationBinding(inspectedPreparation),
        preparationBinding(prepared),
      )) {
        fail("SESSION_TRANSITION_RESULT_INVALID", "E03 and F04 operation bindings disagree");
      }
      if (leaseUse.event_publication_status !== "PUBLISHED") {
        leaseUse = normalizeLeaseUseInspection({
          candidate: dependencies.authority.reconcileLeaseUseEvent(
            identities.leaseUseOperationId,
          ),
          context,
          lease,
        });
      }
      if (
        leaseUse?.event_publication_status !== "PUBLISHED" ||
        !ledgerProvesPublishedTransition({
          ledger: dependencies.ledger,
          runId,
          leaseUse,
          published: publishedEvidence,
        })
      ) {
        fail(
          "SESSION_TRANSITION_RESULT_INVALID",
          "E01 does not prove the required F04 then E03 publication order",
        );
      }
      outcome = dependencies.effects.inspect(intent.intent_id);
      const receipt = sealSucceededTransitionReceipt({
        dependencies,
        context,
        outcome,
        prepared,
        projection: publishedEvidence.projection,
      });
      outcome = persistReceipt(
        dependencies.effects,
        attempt.attempt_id,
        receipt,
        outcome.receipt?.status === "UNKNOWN" ? "RECONCILIATION" : "EXECUTION",
      );
      if (outcome.reconciliation_required) {
        fail(
          "SESSION_TRANSITION_RECONCILIATION_REQUIRED",
          "successful EffectReceipt event publication remains unresolved",
        );
      }
    } catch (error) {
      outcome = recordUnknown({ dependencies, context, error, prepared });
    }
    return mutationPayload({
      invocation,
      leaseId: lease.lease_id,
      outcome,
      transitionRequest,
      artifactStore: dependencies.artifactStore,
    });
  };

  return OBJECT_FREEZE({ execute });
};

export const createSessionTransitionWorker = (options) =>
  makeWorker(normalizeDependencies(options));
