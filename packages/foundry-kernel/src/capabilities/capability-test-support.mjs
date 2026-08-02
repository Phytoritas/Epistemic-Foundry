import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { openContentAddressedArtifactStore } from "../artifacts/content-addressed-artifact-store.mjs";
import { createNoeticLedger } from "../ledger/noetic-ledger.mjs";
import { openSQLiteStateStore } from "../state/sqlite/sqlite-state-store.mjs";
import { createCapabilityAuthority, sealCapabilityPolicy } from "./capability-authority.mjs";

export const E03_IDS = Object.freeze({
  APPROVER: "HUMAN-E03-approver",
  AUTHORITY: "SVC-E03-authority",
  CANDIDATE: "CAND-E03-candidate",
  LEASE: "LEASE-E03-default",
  MAKER: "HUMAN-E03-maker",
  RUN: "RUN-E03-default",
  WORKER: "AG-E03-worker",
});

export const policyHash = (label = "default") =>
  `sha256:${createHash("sha256").update(`E03-policy:${label}`, "utf8").digest("hex")}`;

export const leaseSubject = ({
  subjectId,
  runId = E03_IDS.RUN,
  makerPrincipalIds = [E03_IDS.MAKER],
  capabilities = ["artifact:write", "sandbox:execute"],
  resourceScopes = ["artifact/e03", "workspace/e03"],
} = {}) => ({
  subject_id: subjectId,
  run_id: runId,
  maker_principal_ids: makerPrincipalIds,
  capabilities,
  resource_scopes: resourceScopes,
});

export const defaultPolicyInput = ({
  hash = policyHash(),
  subjects = [
    leaseSubject({ subjectId: E03_IDS.LEASE }),
    leaseSubject({
      subjectId: "LEASE-E03-approved",
      capabilities: ["promotion:commit"],
      resourceScopes: ["passport/e03"],
    }),
    leaseSubject({
      subjectId: "WORK-E03-self",
      makerPrincipalIds: [E03_IDS.APPROVER],
      capabilities: [],
      resourceScopes: [],
    }),
  ],
} = {}) => ({
  policy_hash: hash,
  principals: [
    {
      principal_id: E03_IDS.AUTHORITY,
      principal_type: "service",
      identity_class: "service",
      capabilities: ["capability:issue", "capability:revoke"],
      resource_scopes: ["authority/e03"],
      authority_role: null,
      approval_types: [],
    },
    {
      principal_id: E03_IDS.WORKER,
      principal_type: "agent",
      identity_class: "agent",
      capabilities: ["artifact:write", "sandbox:execute", "promotion:commit"],
      resource_scopes: ["workspace/e03", "artifact/e03", "passport/e03"],
      authority_role: null,
      approval_types: [],
    },
    {
      principal_id: E03_IDS.APPROVER,
      principal_type: "human",
      identity_class: "human",
      capabilities: ["approval:issue"],
      resource_scopes: [],
      authority_role: "product_owner",
      approval_types: ["capability", "external_effect"],
    },
    {
      principal_id: E03_IDS.MAKER,
      principal_type: "human",
      identity_class: "human",
      capabilities: ["approval:issue"],
      resource_scopes: [],
      authority_role: "product_owner",
      approval_types: ["capability"],
    },
    {
      principal_id: E03_IDS.CANDIDATE,
      principal_type: "agent",
      identity_class: "candidate",
      capabilities: ["sandbox:execute"],
      resource_scopes: ["workspace/e03"],
      authority_role: null,
      approval_types: [],
    },
  ],
  subjects,
  approval_rules: [
    {
      approval_type: "capability",
      authority_roles: ["product_owner"],
      evidence_required: true,
    },
    {
      approval_type: "external_effect",
      authority_roles: ["product_owner"],
      evidence_required: true,
    },
  ],
  capability_rules: [
    { capability: "capability:issue", required_approval_type: null },
    { capability: "capability:revoke", required_approval_type: null },
    { capability: "approval:issue", required_approval_type: null },
    { capability: "artifact:write", required_approval_type: null },
    { capability: "sandbox:execute", required_approval_type: null },
    { capability: "promotion:commit", required_approval_type: "capability" },
  ],
});

export const createCapabilityFixture = (t, options = {}) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "ef-e03-"));
  const databasePath = path.join(root, "foundry.db");
  const artifactRoot = path.join(root, "artifacts");
  const stateStore = openSQLiteStateStore(databasePath);
  const artifactStore = openContentAddressedArtifactStore(artifactRoot);
  const ledger = createNoeticLedger({ artifactStore, stateStore });
  const policy = sealCapabilityPolicy(options.policy ?? defaultPolicyInput());
  let currentTime = options.now ?? "2026-07-28T05:00:00Z";
  const clock = () => currentTime;
  const authority = createCapabilityAuthority({ artifactStore, ledger, stateStore, policy, clock });
  const setTime = (value) => {
    currentTime = value;
  };
  t.after(() => {
    stateStore.close();
    artifactStore.close();
    fs.rmSync(root, { recursive: true, force: true });
  });
  return { artifactRoot, artifactStore, authority, databasePath, ledger, policy, root, setTime, stateStore };
};

export const defaultLeaseCommand = (overrides = {}) => ({
  lease_id: E03_IDS.LEASE,
  run_id: E03_IDS.RUN,
  principal_id: E03_IDS.WORKER,
  capabilities: ["artifact:write", "sandbox:execute"],
  resource_scopes: ["workspace/e03", "artifact/e03"],
  expires_at: "2026-07-28T06:00:00Z",
  approval_ids: [],
  ...overrides,
});

export const issueDefaultLease = (authority, overrides = {}) =>
  authority.issueLease(E03_IDS.AUTHORITY, defaultLeaseCommand(overrides));

export const defaultUseCommand = (lease, overrides = {}) => ({
  operation_id: "OP-E03-default",
  run_id: E03_IDS.RUN,
  lease,
  principal_id: E03_IDS.WORKER,
  capability: "artifact:write",
  resource_scopes: ["artifact/e03"],
  ...overrides,
});

export const issueCapabilityApproval = (authority, overrides = {}) =>
  authority.issueApproval(E03_IDS.APPROVER, {
    approval_id: "APR-E03-capability",
    run_id: E03_IDS.RUN,
    subject_id: "LEASE-E03-approved",
    approval_type: "capability",
    decision: "APPROVE",
    reason: "G00-G13 evidence authorizes a bounded promotion commit lease.",
    evidence_artifact_ids: ["ART-E03-gates"],
    conditions: ["promotion pack hash remains unchanged"],
    expires_at: "2026-07-28T06:00:00Z",
    ...overrides,
  });
