import { createHash } from "node:crypto";

import {
  MemoryIndexError,
  buildMemoryIndex,
  emitMemoryRetrievalReceipt,
  executeMemorySearch,
  validateMemoryRetrievalReceipt,
} from "../../../packages/foundry-kernel/src/memory/index/index.mjs";
import {
  redactAndDeduplicateMemory,
  validateMemorySelection,
} from "../../../packages/foundry-kernel/src/memory/lifecycle/index.mjs";
import {
  sealConsentRecord,
  sealMemoryPolicy,
} from "../../../packages/foundry-kernel/src/memory/policy/index.mjs";


export const PRIMARY_WORKSPACE = "WS-L04-PRIMARY";
export const PRIVATE_WORKSPACE = "WS-L04-PRIVATE";
export const THIRD_WORKSPACE = "WS-L04-THIRD";
export const EVALUATED_AT = "2026-07-31T02:00:00.000Z";
export const PURPOSE = "resume bounded research";
export const DATA_CLASS = "research context";

export const sha256Text = (value) =>
  `sha256:${createHash("sha256").update(value, "utf8").digest("hex")}`;

export const memoryFixture = ({
  memoryId,
  memoryClass = "WORKSPACE",
  workspaceId = PRIMARY_WORKSPACE,
  searchText,
  sourceContent = searchText,
  createdAt = "2026-07-01T00:00:00.000Z",
}) => ({
  memory_id: memoryId,
  class: memoryClass,
  workspace_id: workspaceId,
  search_text: searchText,
  source_hash: sha256Text(sourceContent),
  created_at: createdAt,
  source_content: sourceContent,
});

export const makePolicy = ({
  workspaceId = PRIMARY_WORKSPACE,
  crossWorkspaceRetrieval = "DENY",
} = {}) =>
  sealMemoryPolicy({
    policy_id: `MP-L04-${workspaceId}`,
    workspace_id: workspaceId,
    allowed_classes: ["SESSION", "WORKSPACE", "USER", "EVIDENCE"],
    default_retention_days: 365,
    class_rules: [
      {
        class: "SESSION",
        retention_days: 30,
        requires_consent: false,
        external_sync: "DENY",
        redaction_profile: "session-default",
      },
      {
        class: "WORKSPACE",
        retention_days: 365,
        requires_consent: true,
        external_sync: "DENY",
        redaction_profile: "workspace-default",
      },
      {
        class: "USER",
        retention_days: 365,
        requires_consent: true,
        external_sync: "ALLOW_REDACTED",
        redaction_profile: "user-strict",
      },
      {
        class: "EVIDENCE",
        retention_days: 3650,
        requires_consent: false,
        external_sync: "DENY",
        redaction_profile: "evidence-default",
      },
    ],
    cross_workspace_retrieval: crossWorkspaceRetrieval,
    effective_at: "2026-01-01T00:00:00.000Z",
  });

export const makeConsent = (policy, {
  scopes = ["WORKSPACE", "USER"],
  decision = "GRANTED",
  revokedAt = null,
  expiresAt = "2027-01-01T00:00:00.000Z",
} = {}) =>
  sealConsentRecord({
    consent_id: `CONS-L04-${policy.workspace_id}`,
    subject_id: "USER-L04-001",
    workspace_id: policy.workspace_id,
    purposes: [PURPOSE],
    data_classes: [DATA_CLASS],
    scopes,
    decision,
    granted_at: "2026-01-01T00:00:00.000Z",
    expires_at: expiresAt,
    revoked_at: revokedAt,
    recorded_by: "USER-L04-001",
    policy_hash: policy.policy_hash,
  });

export const makeRequest = ({
  query,
  policy = makePolicy(),
  workspaceId = policy.workspace_id,
  targetWorkspaceId = workspaceId,
  requestedClasses = ["WORKSPACE"],
  consentRecord,
  crossWorkspaceOptIn = false,
  limit = 10,
  contextCapsuleId = "CC-L04-001",
} = {}) => {
  const needsConsent = requestedClasses.some(
    (memoryClass) => memoryClass === "WORKSPACE" || memoryClass === "USER",
  );
  return {
    query,
    workspace_id: workspaceId,
    target_workspace_id: targetWorkspaceId,
    purpose: PURPOSE,
    data_class: DATA_CLASS,
    requested_classes: requestedClasses,
    policy,
    consent_record:
      consentRecord === undefined
        ? needsConsent
          ? makeConsent(policy)
          : null
        : consentRecord,
    evaluated_at: EVALUATED_AT,
    cross_workspace_opt_in: crossWorkspaceOptIn,
    limit,
    context_capsule_id: contextCapsuleId,
  };
};

const indexRecord = (fixture) => ({
  memory_id: fixture.memory_id,
  class: fixture.class,
  workspace_id: fixture.workspace_id,
  search_text: fixture.search_text,
  source_hash: fixture.source_hash,
  created_at: fixture.created_at,
});

const sourceArtifactsForHits = (fixtures, hits) => {
  const byHash = new Map(fixtures.map((fixture) => [fixture.source_hash, fixture]));
  return [...new Set(hits.map((hit) => hit.source_hash))].map((sourceHash) => {
    const fixture = byHash.get(sourceHash);
    if (fixture === undefined) throw new Error(`fixture source missing for ${sourceHash}`);
    return { source_hash: sourceHash, content: fixture.source_content };
  });
};

export const byteDirective = ({
  directiveId,
  fixture,
  secret,
  replacement = "[REDACTED]",
}) => {
  const characterIndex = fixture.source_content.indexOf(secret);
  if (characterIndex < 0) throw new Error(`secret not found in ${fixture.memory_id}`);
  const prefix = fixture.source_content.slice(0, characterIndex);
  return {
    directive_id: directiveId,
    source_hash: fixture.source_hash,
    start_byte: Buffer.byteLength(prefix, "utf8"),
    end_byte: Buffer.byteLength(prefix + secret, "utf8"),
    replacement,
  };
};

export const runRecallEvaluation = ({ fixtures, request, directives = [] }) => {
  const index = buildMemoryIndex(fixtures.map(indexRecord));
  const searchExecution = executeMemorySearch({ index, request });
  const selection = validateMemorySelection(
    redactAndDeduplicateMemory({
      hits: searchExecution.hits,
      source_artifacts: sourceArtifactsForHits(fixtures, searchExecution.hits),
      redaction_directives: directives,
      required_redaction_profile: null,
    }),
  );
  const receipt = validateMemoryRetrievalReceipt(
    emitMemoryRetrievalReceipt({
      search_execution: searchExecution,
      selected_hits: selection.selected_hits,
      redaction_count: selection.redaction_count,
      retrieved_at: searchExecution.plan.evaluated_at,
    }),
  );
  return Object.freeze({ index, searchExecution, selection, receipt });
};

export const selectedIds = (evaluation) =>
  evaluation.selection.selected_hits.map((hit) => hit.memory_id);

export const searchedIds = (evaluation) =>
  evaluation.searchExecution.hits.map((hit) => hit.memory_id);

export const leakedIds = (evaluation, forbiddenIds) => {
  const forbidden = new Set(forbiddenIds);
  return selectedIds(evaluation).filter((memoryId) => forbidden.has(memoryId));
};

export const errorCode = (code) => (error) =>
  error instanceof MemoryIndexError && error.code === code;

