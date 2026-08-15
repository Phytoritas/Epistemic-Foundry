// Store-backed projections for the six stateful T01 PURE_READ operations.
//
// This module owns no state and creates no parallel index. It reads the
// existing F04 session projection and the existing D03 manifest/receipt tree.
// Domain artifacts are selected by the schema_ref already sealed into their
// D03 receipts, then matched by their runtime-native identity fields.

const SCHEMA_REF = Object.freeze({
  claim: "https://epistemic-foundry.local/schemas/claim-card.schema.json",
  coverage: "https://epistemic-foundry.local/schemas/coverage-snapshot.schema.json",
  passport: "https://epistemic-foundry.local/schemas/hypothesis-passport.schema.json",
  replay: "https://epistemic-foundry.local/schemas/replay-report.schema.json",
});

const OPERATIONS = new Set([
  "read_session",
  "read_artifact",
  "read_claim",
  "read_atlas",
  "read_passport",
  "read_replay_diff",
]);

export class StoreReadModelError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "StoreReadModelError";
    this.code = code;
  }
}

function fail(code, message) {
  throw new StoreReadModelError(code, message);
}

function text(value, label) {
  if (typeof value !== "string" || value.length === 0) {
    fail("READ_MODEL_INPUT_INVALID", `${label} must be a non-empty string`);
  }
  return value;
}

function plainObject(value, label) {
  if (
    value === null ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.getPrototypeOf(value) !== Object.prototype
  ) {
    fail("READ_MODEL_INTEGRITY_INVALID", `${label} is not a JSON object`);
  }
  return value;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function dependency(value, methods, label) {
  if (value === null || !["object", "function"].includes(typeof value)) {
    fail("READ_MODEL_DEPENDENCY_INVALID", `${label} is unavailable`);
  }
  for (const method of methods) {
    if (typeof value[method] !== "function") {
      fail("READ_MODEL_DEPENDENCY_INVALID", `${label}.${method} is unavailable`);
    }
  }
  return value;
}

function ready(data) {
  return Object.freeze({ found: true, state: "READY", data, reason: null });
}

function empty() {
  return Object.freeze({
    found: false,
    state: "EMPTY_CONFIRMED",
    data: null,
    reason: null,
  });
}

function unavailable(reason) {
  return Object.freeze({
    found: false,
    state: "UNAVAILABLE",
    data: null,
    reason,
  });
}

function readableConfidentiality(manifest) {
  return manifest?.confidentiality === "public" || manifest?.confidentiality === "internal";
}

function parseResolvedArtifact(resolved, schemaRef, validateDomainArtifact) {
  plainObject(resolved, "resolved artifact binding");
  if (!Buffer.isBuffer(resolved.bytes)) {
    fail("READ_MODEL_INTEGRITY_INVALID", "resolved artifact bytes are unavailable");
  }
  let document;
  try {
    document = validateDomainArtifact(schemaRef, Buffer.from(resolved.bytes));
  } catch {
    fail("READ_MODEL_INTEGRITY_INVALID", "resolved artifact failed canonical validation");
  }
  return plainObject(document, "resolved artifact");
}

function compareText(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function exactDistinct(rows) {
  return new Map(rows.map((row) => [JSON.stringify(row), row]));
}

function selectHighestRevision(rows, numericField) {
  for (const row of rows) {
    if (!Number.isSafeInteger(row[numericField]) || row[numericField] < 1) {
      fail("READ_MODEL_INTEGRITY_INVALID", "stored revision identity is invalid");
    }
  }
  const highest = Math.max(...rows.map((row) => row[numericField]));
  const finalists = exactDistinct(rows.filter((row) => row[numericField] === highest));
  return finalists.size === 1
    ? { ambiguous: false, value: [...finalists.values()][0] }
    : { ambiguous: true, value: null };
}

export function createStoreReadModel({
  workspaceId,
  artifactStore,
  sessionPort,
  validateDomainArtifact,
}) {
  const configuredWorkspaceId = text(workspaceId, "workspaceId");
  const artifacts = dependency(
    artifactStore,
    ["readManifest", "enumerateReceipts", "resolveReceipt"],
    "artifactStore",
  );
  const sessions = dependency(sessionPort, ["readSession"], "sessionPort");

  function requireWorkspace(requestedWorkspaceId) {
    if (text(requestedWorkspaceId, "workspace_id") !== configuredWorkspaceId) {
      fail("READ_MODEL_NOT_FOUND", "resource does not exist in the authorized workspace");
    }
  }

  function schemaArtifacts(schemaRef) {
    if (typeof validateDomainArtifact !== "function") {
      fail(
        "READ_MODEL_DOMAIN_VALIDATOR_UNAVAILABLE",
        "canonical domain validator is unavailable",
      );
    }
    const resolvedByArtifact = new Map();
    for (const receipt of artifacts.enumerateReceipts()) {
      if (receipt?.schema_ref !== schemaRef) continue;
      const artifactId = text(receipt.artifact_id, "artifact receipt artifact_id");
      if (resolvedByArtifact.has(artifactId)) continue;
      const resolved = artifacts.resolveReceipt(receipt.receipt_id);
      if (
        resolved.artifactId !== artifactId ||
        resolved.receipt?.schema_ref !== schemaRef
      ) {
        fail("READ_MODEL_INTEGRITY_INVALID", "artifact receipt binding changed");
      }
      if (!readableConfidentiality(resolved.manifest)) continue;
      resolvedByArtifact.set(
        artifactId,
        parseResolvedArtifact(resolved, schemaRef, validateDomainArtifact),
      );
    }
    return [...resolvedByArtifact.values()];
  }

  function readSession(arguments_) {
    const sessionId = text(arguments_.session_id, "session_id");
    let published;
    try {
      published = sessions.readSession(sessionId);
    } catch (error) {
      if (error?.code === "FORGE_INPUT_INVALID") {
        fail("READ_MODEL_INPUT_INVALID", "session_id is outside the runtime ID contract");
      }
      throw error;
    }
    if (published === null) return empty();
    const projection = plainObject(published, "published session projection");
    const state = plainObject(projection.state, "published session state");
    if (state.workspace_id !== configuredWorkspaceId) return empty();
    return ready(clone(state));
  }

  function readArtifact(arguments_) {
    const artifactId = text(arguments_.artifact_id, "artifact_id");
    let manifest;
    try {
      manifest = artifacts.readManifest(artifactId);
    } catch (error) {
      if (error?.code === "ARTIFACT_NOT_FOUND") return empty();
      if (error?.code === "INVALID_INPUT") {
        fail("READ_MODEL_INPUT_INVALID", "artifact_id is outside the runtime ID contract");
      }
      throw error;
    }
    if (!readableConfidentiality(manifest)) return empty();
    const receipts = artifacts
      .enumerateReceipts()
      .filter((receipt) => receipt.artifact_id === artifactId)
      .sort((left, right) => compareText(left.receipt_id, right.receipt_id));
    return ready({ manifest: clone(manifest), receipts: clone(receipts) });
  }

  function readClaim(arguments_) {
    const claimId = text(arguments_.claim_id, "claim_id");
    const matches = schemaArtifacts(SCHEMA_REF.claim).filter(
      (claim) => claim.claim_id === claimId,
    );
    if (matches.length === 0) return empty();
    const selected = selectHighestRevision(matches, "version");
    return selected.ambiguous
      ? unavailable("multiple distinct claim artifacts share the latest claim version")
      : ready(clone(selected.value));
  }

  function readAtlas(arguments_) {
    const subjectId = text(arguments_.subject_id, "subject_id");
    if (arguments_.view !== "coverage") {
      return unavailable(
        "the durable store currently contains only canonical coverage-snapshot atlas views",
      );
    }
    const matches = schemaArtifacts(SCHEMA_REF.coverage).filter(
      (snapshot) => snapshot.insight_id === subjectId,
    );
    if (matches.length === 0) return empty();
    const selected = selectHighestRevision(matches, "insight_revision");
    return selected.ambiguous
      ? unavailable("multiple distinct coverage snapshots share the latest revision")
      : ready(clone(selected.value));
  }

  function readPassport(arguments_) {
    const passportId = text(arguments_.passport_id, "passport_id");
    const revision = arguments_.revision ?? null;
    if (
      revision !== null &&
      (!Number.isSafeInteger(revision) || revision < 1)
    ) {
      fail("READ_MODEL_INPUT_INVALID", "revision must be a positive integer or null");
    }
    const matches = schemaArtifacts(SCHEMA_REF.passport).filter(
      (passport) =>
        passport.hypothesis_id === passportId &&
        (revision === null || passport.revision === revision),
    );
    if (matches.length === 0) return empty();
    const selected = selectHighestRevision(matches, "revision");
    return selected.ambiguous
      ? unavailable("multiple distinct passport artifacts share the selected revision")
      : ready(clone(selected.value));
  }

  function readReplayDiff(arguments_) {
    const runId = text(arguments_.run_id, "run_id");
    const baselineRunId = text(arguments_.baseline_run_id, "baseline_run_id");
    const matches = schemaArtifacts(SCHEMA_REF.replay).filter(
      (report) =>
        report.replay_run_id === runId && report.source_run_id === baselineRunId,
    );
    if (matches.length === 0) return empty();
    const distinct = exactDistinct(matches);
    if (distinct.size > 1) {
      return unavailable(
        "multiple replay reports or modes exist for this run pair and the current request does not select one",
      );
    }
    return ready(clone([...distinct.values()][0]));
  }

  function fetch(operation, requestedWorkspaceId, arguments_) {
    if (!OPERATIONS.has(operation)) {
      fail("READ_MODEL_OPERATION_UNKNOWN", "read operation is not supported");
    }
    requireWorkspace(requestedWorkspaceId);
    const input = plainObject(arguments_, "read arguments");
    try {
      switch (operation) {
        case "read_session":
          return readSession(input);
        case "read_artifact":
          return readArtifact(input);
        case "read_claim":
          return readClaim(input);
        case "read_atlas":
          return readAtlas(input);
        case "read_passport":
          return readPassport(input);
        case "read_replay_diff":
          return readReplayDiff(input);
        default:
          fail("READ_MODEL_OPERATION_UNKNOWN", "read operation is not supported");
      }
    } catch (error) {
      if (
        error instanceof StoreReadModelError &&
        new Set([
          "READ_MODEL_INPUT_INVALID",
          "READ_MODEL_NOT_FOUND",
          "READ_MODEL_OPERATION_UNKNOWN",
        ]).has(error.code)
      ) {
        throw error;
      }
      return unavailable("the durable read model could not be resolved");
    }
  }

  return Object.freeze({ fetch });
}
