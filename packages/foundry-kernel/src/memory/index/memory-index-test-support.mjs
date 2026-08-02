import {
  sealConsentRecord,
  sealMemoryPolicy,
} from "../policy/index.mjs";

import { buildMemoryIndex } from "./memory-index.mjs";


export const HASH_A = `sha256:${"a".repeat(64)}`;
export const HASH_B = `sha256:${"b".repeat(64)}`;
export const HASH_C = `sha256:${"c".repeat(64)}`;
export const EVALUATED_AT = "2026-07-31T00:00:00.000Z";

export const makePolicy = (overrides = {}) =>
  sealMemoryPolicy({
    policy_id: "MP-L02-001",
    workspace_id: "WS-L02-001",
    allowed_classes: ["SESSION", "WORKSPACE", "USER", "EVIDENCE"],
    default_retention_days: 30,
    class_rules: [
      {
        class: "SESSION",
        retention_days: 7,
        requires_consent: false,
        external_sync: "DENY",
        redaction_profile: "session-default",
      },
      {
        class: "WORKSPACE",
        retention_days: 90,
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
        retention_days: 730,
        requires_consent: false,
        external_sync: "DENY",
        redaction_profile: "evidence-default",
      },
    ],
    cross_workspace_retrieval: "DENY",
    effective_at: "2026-01-01T00:00:00.000Z",
    ...overrides,
  });

export const makeConsent = (policy, overrides = {}) =>
  sealConsentRecord({
    consent_id: "CONS-L02-001",
    subject_id: "USER-L02-001",
    workspace_id: policy.workspace_id,
    purposes: ["resume research"],
    data_classes: ["research context"],
    scopes: ["WORKSPACE", "USER"],
    decision: "GRANTED",
    granted_at: "2026-01-01T00:00:00.000Z",
    expires_at: "2027-01-01T00:00:00.000Z",
    revoked_at: null,
    recorded_by: "USER-L02-001",
    policy_hash: policy.policy_hash,
    ...overrides,
  });

export const memoryRecord = (overrides = {}) => ({
  memory_id: "MEM-L02-001",
  class: "WORKSPACE",
  workspace_id: "WS-L02-001",
  search_text: "prior scope decision about strawberry spacing",
  source_hash: HASH_A,
  created_at: "2026-07-01T00:00:00.000Z",
  ...overrides,
});

export const makeRecords = () => [
  memoryRecord(),
  memoryRecord({
    memory_id: "MEM-L02-002",
    class: "WORKSPACE",
    search_text: "prior scope decision with boundary evidence",
    source_hash: HASH_B,
  }),
  memoryRecord({
    memory_id: "MEM-L02-003",
    class: "SESSION",
    search_text: "current session note about scope",
    source_hash: HASH_C,
    created_at: "2026-07-30T00:00:00.000Z",
  }),
  memoryRecord({
    memory_id: "MEM-L02-004",
    class: "USER",
    workspace_id: "WS-L02-OTHER",
    search_text: "cross workspace personal scope preference",
    source_hash: HASH_A,
    created_at: "2026-01-02T00:00:00.000Z",
  }),
  memoryRecord({
    memory_id: "MEM-L02-005",
    class: "REGULATED",
    search_text: "prior scope decision regulated",
    source_hash: HASH_B,
  }),
  memoryRecord({
    memory_id: "MEM-L02-006",
    class: "EVIDENCE",
    search_text: "published boundary evidence",
    source_hash: HASH_C,
    created_at: "2025-01-01T00:00:00.000Z",
  }),
];

export const makeIndex = (records = makeRecords()) => buildMemoryIndex(records);

export const makeRequest = (overrides = {}) => {
  const policy = overrides.policy ?? makePolicy();
  const requestedClasses = overrides.requested_classes ?? ["WORKSPACE"];
  const needsConsent = requestedClasses.some((value) => value === "WORKSPACE" || value === "USER");
  return {
    query: "prior scope decision",
    workspace_id: policy.workspace_id,
    target_workspace_id: policy.workspace_id,
    purpose: "resume research",
    data_class: "research context",
    requested_classes: requestedClasses,
    policy,
    consent_record:
      Object.hasOwn(overrides, "consent_record")
        ? overrides.consent_record
        : needsConsent
          ? makeConsent(policy)
          : null,
    evaluated_at: EVALUATED_AT,
    cross_workspace_opt_in: false,
    limit: 10,
    context_capsule_id: "CC-L02-001",
    ...overrides,
    policy,
    requested_classes: requestedClasses,
  };
};

