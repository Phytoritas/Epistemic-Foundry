import { createHash } from "node:crypto";

import {
  sealLegalHold,
  sealMemoryLifecyclePolicy,
  sealMemoryLifecycleRequest,
  sealMemoryLifecycleState,
} from "./index.mjs";

export const FIXED_AT = "2026-07-31T01:00:00.000Z";
export const PREVIOUS_EVENT_HASH = `sha256:${"e".repeat(64)}`;

export const textHash = (value) =>
  `sha256:${createHash("sha256").update(value, "utf8").digest("hex")}`;

export const sourceArtifact = (content = "alpha secret omega") => ({
  source_hash: textHash(content),
  content,
});

export const retrievalHit = (source, overrides = {}) => ({
  memory_id: "MEM-L03-001",
  class: "WORKSPACE",
  score: 1,
  source_hash: source.source_hash,
  redacted: false,
  ...overrides,
});

export const directive = (source, overrides = {}) => ({
  directive_id: "RED-L03-001",
  source_hash: source.source_hash,
  start_byte: 6,
  end_byte: 12,
  replacement: "[REDACTED]",
  ...overrides,
});

export const lifecycleState = (overrides = {}) => {
  const content = overrides.content ?? "canonical memory content";
  return sealMemoryLifecycleState({
    memory_id: "MEM-L03-001",
    class: "WORKSPACE",
    workspace_id: "WS-L03-001",
    revision: 4,
    status: "ACTIVE",
    canonical_artifact_id: "ART-L03-001",
    source_hash: textHash(content),
    content,
    updated_at: "2026-07-30T01:00:00.000Z",
    ...overrides,
  });
};

export const lifecyclePolicy = (overrides = {}) =>
  sealMemoryLifecyclePolicy({
    policy_id: "MLP-L03-001",
    workspace_id: "WS-L03-001",
    permitted_actions: ["FORGET_MEMORY", "DELETE_MEMORY"],
    tombstone_hash_retention: "PROHIBITED",
    tombstone_authority_record_id: null,
    effective_at: "2026-01-01T00:00:00.000Z",
    ...overrides,
  });

export const lifecycleRequest = (overrides = {}) =>
  sealMemoryLifecycleRequest({
    request_id: "REQ-L03-001",
    run_id: "RUN-L03-001",
    memory_id: "MEM-L03-001",
    workspace_id: "WS-L03-001",
    action_type: "FORGET_MEMORY",
    target_kind: "CANONICAL_MEMORY",
    expected_revision: 4,
    actor_id: "ACT-L03-001",
    reason: "user requested governed forgetting",
    approval_record_ids: [],
    requested_at: FIXED_AT,
    idempotency_key: "IDEMP-L03-001",
    event_sequence: 2,
    previous_event_hash: PREVIOUS_EVENT_HASH,
    ...overrides,
  });

export const legalHold = (overrides = {}) =>
  sealLegalHold({
    hold_id: "HOLD-L03-001",
    scope: {
      workspace_id: "WS-L03-001",
      memory_ids: ["MEM-L03-001"],
      memory_classes: [],
    },
    authority_record_id: "AUTH-L03-001",
    reason: "bounded litigation preservation",
    starts_at: "2026-07-01T00:00:00.000Z",
    expires_at: "2026-08-31T00:00:00.000Z",
    ...overrides,
  });

export const lifecycleApplication = (overrides = {}) => ({
  request: lifecycleRequest(),
  state: lifecycleState(),
  policy: lifecyclePolicy(),
  legal_holds: [],
  prior_outcomes: [],
  ...overrides,
});
