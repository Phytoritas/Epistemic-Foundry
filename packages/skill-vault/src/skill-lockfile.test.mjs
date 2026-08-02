import assert from "node:assert/strict";
import test from "node:test";

import {
  CONFORMANCE_STATUS,
  REVIEW_DECISION,
  SIGNATURE_STATUS,
  createSkillVaultBoundary,
} from "./skill-vault.mjs";

const POLICY_HASH = `sha256:${"1".repeat(64)}`;
const OTHER_POLICY_HASH = `sha256:${"2".repeat(64)}`;

const buildApproved = (
  boundary,
  {
    skillId = "skill-approved-001",
    permissions = ["network", "filesystem_read"],
    reviewerIds = ["reviewer-zeta", "reviewer-alpha"],
  } = {},
) => {
  const candidate = boundary.guard.quarantineCandidate({
    skillId,
    source: `https://catalog.example/skills/${skillId}`,
    revision: "commit-fedcba9876543210",
    signatureStatus: SIGNATURE_STATUS.VERIFIED,
    declaredLicense: "MIT",
    declaredPermissions: permissions,
    files: [{ path: "SKILL.md", kind: "file", content: "# Reviewed skill\nStatic metadata only." }],
  });
  const scan = boundary.guard.scanCandidate(candidate);
  const review = boundary.issuer.issueReviewDecision({
    decisionId: `review-${skillId}`,
    candidate,
    scanReport: scan,
    reviewerIds,
    decision: REVIEW_DECISION.APPROVED,
    reviewedSource: candidate.source,
    reviewedRevision: candidate.revision,
    reviewedContentHash: candidate.contentHash,
    signatureStatus: SIGNATURE_STATUS.VERIFIED,
    license: "MIT",
    permissions,
    rationale: "Reviewed the exact normalized tree and permission envelope.",
  });
  return { candidate, scan, review };
};

const createLock = (boundary, reviews) => boundary.issuer.createSkillLockfile({
  workspaceId: "workspace-foundry-001",
  generatedAt: "2026-07-27T01:02:03.000Z",
  policyHash: POLICY_HASH,
  reviewDecisions: reviews,
});

const installAndConform = (boundary, lockfile, candidate, permissions) => {
  const installation = boundary.issuer.issueDisabledInstallation({
    installId: `install-${candidate.skillId}`,
    lockfile,
    skillId: candidate.skillId,
    observedContentHash: candidate.contentHash,
    collisionSkillIds: [],
  });
  const conformance = boundary.issuer.issueConformanceAttestation({
    conformanceId: `conformance-${candidate.skillId}`,
    installation,
    status: CONFORMANCE_STATUS.PASS,
    observedPermissions: permissions,
    uninstallVerified: true,
    explicitInvocationOnly: true,
    sandboxProfileId: "sandbox-skill-conformance-001",
  });
  return { installation, conformance };
};

test("SkillLockfile pins exact source, revision, hash, license, permissions, and approvers", () => {
  const boundary = createSkillVaultBoundary();
  const approved = buildApproved(boundary);
  const lockfile = createLock(boundary, [approved.review]);
  const entry = lockfile.skills[0];

  assert.equal(lockfile.lock_version, 1);
  assert.equal(lockfile.workspace_id, "workspace-foundry-001");
  assert.equal(lockfile.policy_hash, POLICY_HASH);
  assert.match(lockfile.lock_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(entry.skill_id, approved.candidate.skillId);
  assert.equal(entry.source, approved.candidate.source);
  assert.equal(entry.revision, approved.candidate.revision);
  assert.equal(entry.content_hash, approved.candidate.contentHash);
  assert.equal(entry.license, "MIT");
  assert.deepEqual(entry.permissions, ["filesystem_read", "network"]);
  assert.deepEqual(entry.approved_by_ids, ["reviewer-alpha", "reviewer-zeta"]);
  assert.equal(entry.review_status, "APPROVED");
  assert.ok(Object.isFrozen(lockfile));
  assert.ok(Object.isFrozen(lockfile.skills));
  assert.ok(Object.isFrozen(entry));
  assert.equal(boundary.guard.verifySkillLockfileSnapshot(lockfile).valid, true);
});

test("lock hashing is deterministic across review, permission, and approver input order", () => {
  const first = createSkillVaultBoundary();
  const firstA = buildApproved(first, {
    skillId: "skill-alpha-001",
    permissions: ["network", "filesystem_read"],
    reviewerIds: ["reviewer-zeta", "reviewer-alpha"],
  });
  const firstB = buildApproved(first, {
    skillId: "skill-beta-001",
    permissions: [],
    reviewerIds: ["reviewer-beta"],
  });
  const firstLock = createLock(first, [firstB.review, firstA.review]);

  const second = createSkillVaultBoundary();
  const secondA = buildApproved(second, {
    skillId: "skill-alpha-001",
    permissions: ["filesystem_read", "network"],
    reviewerIds: ["reviewer-alpha", "reviewer-zeta"],
  });
  const secondB = buildApproved(second, {
    skillId: "skill-beta-001",
    permissions: [],
    reviewerIds: ["reviewer-beta"],
  });
  const secondLock = createLock(second, [secondA.review, secondB.review]);

  assert.deepEqual(firstLock, secondLock);
  assert.equal(firstLock.lock_hash, secondLock.lock_hash);
  assert.deepEqual(firstLock.skills.map(({ skill_id: skillId }) => skillId), [
    "skill-alpha-001",
    "skill-beta-001",
  ]);
});

test("serialized lockfiles can be integrity-checked but do not acquire runtime authority", () => {
  const boundary = createSkillVaultBoundary();
  const approved = buildApproved(boundary);
  const lockfile = createLock(boundary, [approved.review]);
  const serialized = JSON.parse(JSON.stringify(lockfile));

  assert.equal(boundary.guard.verifySkillLockfileSnapshot(serialized).valid, true);
  assert.equal(boundary.guard.isSkillLockfile(serialized), false);
  serialized.skills[0].license = "Unknown";
  assert.throws(
    () => boundary.guard.verifySkillLockfileSnapshot(serialized),
    (error) => error.code === "LOCK_HASH_MISMATCH",
  );
});

test("rejected decisions remain locked as rejected and cannot be installed", () => {
  const boundary = createSkillVaultBoundary();
  const candidate = boundary.guard.quarantineCandidate({
    skillId: "skill-rejected-001",
    source: "https://catalog.example/skills/rejected",
    revision: "revision-rejected-001",
    signatureStatus: SIGNATURE_STATUS.UNVERIFIED,
    declaredLicense: "UNKNOWN",
    declaredPermissions: [],
    files: [{ path: "SKILL.md", kind: "file", content: "unverified metadata" }],
  });
  const scan = boundary.guard.scanCandidate(candidate);
  const review = boundary.issuer.issueReviewDecision({
    decisionId: "review-rejected-001",
    candidate,
    scanReport: scan,
    reviewerIds: ["reviewer-security-001"],
    decision: REVIEW_DECISION.REJECTED,
    reviewedSource: candidate.source,
    reviewedRevision: candidate.revision,
    reviewedContentHash: candidate.contentHash,
    signatureStatus: SIGNATURE_STATUS.UNVERIFIED,
    license: "UNKNOWN",
    permissions: [],
    rationale: "License and signature provenance are insufficient.",
  });
  const lockfile = createLock(boundary, [review]);

  assert.equal(lockfile.skills[0].review_status, "REJECTED");
  assert.deepEqual(lockfile.skills[0].approved_by_ids, []);
  assert.throws(
    () => boundary.issuer.issueDisabledInstallation({
      installId: "install-rejected-001",
      lockfile,
      skillId: candidate.skillId,
      observedContentHash: candidate.contentHash,
      collisionSkillIds: [],
    }),
    (error) => error.code === "SKILL_NOT_APPROVED",
  );
});

test("disabled installation requires the exact approved content hash", () => {
  const boundary = createSkillVaultBoundary();
  const approved = buildApproved(boundary);
  const lockfile = createLock(boundary, [approved.review]);

  assert.throws(
    () => boundary.issuer.issueDisabledInstallation({
      installId: "install-mismatch-001",
      lockfile,
      skillId: approved.candidate.skillId,
      observedContentHash: `sha256:${"f".repeat(64)}`,
      collisionSkillIds: [],
    }),
    (error) => error.code === "INSTALL_HASH_MISMATCH",
  );
});

test("passing conformance cannot report permissions outside the lockfile", () => {
  const boundary = createSkillVaultBoundary();
  const approved = buildApproved(boundary, { permissions: [] });
  const lockfile = createLock(boundary, [approved.review]);
  const installation = boundary.issuer.issueDisabledInstallation({
    installId: "install-conformance-001",
    lockfile,
    skillId: approved.candidate.skillId,
    observedContentHash: approved.candidate.contentHash,
    collisionSkillIds: [],
  });

  assert.throws(
    () => boundary.issuer.issueConformanceAttestation({
      conformanceId: "conformance-expanded-001",
      installation,
      status: CONFORMANCE_STATUS.PASS,
      observedPermissions: ["network"],
      uninstallVerified: true,
      explicitInvocationOnly: true,
      sandboxProfileId: "sandbox-skill-conformance-001",
    }),
    (error) => error.code === "UNDECLARED_PERMISSION",
  );
});

test("activation cannot request a locked permission absent from conformance observations", () => {
  const boundary = createSkillVaultBoundary();
  const approved = buildApproved(boundary, { permissions: ["filesystem_read", "network"] });
  const lockfile = createLock(boundary, [approved.review]);
  const { installation, conformance } = installAndConform(
    boundary,
    lockfile,
    approved.candidate,
    ["filesystem_read"],
  );

  assert.throws(
    () => boundary.guard.authorizeActivation({
      requestId: "activation-unobserved-001",
      skillId: approved.candidate.skillId,
      lockfile,
      installation,
      conformanceReport: conformance,
      expectedPolicyHash: POLICY_HASH,
      requestedPermissions: ["network"],
      activationScopeId: "workspace-session-001",
    }),
    (error) => error.code === "UNVERIFIED_PERMISSION_DENIED",
  );
});

test("activation requires exact policy, passing conformance, and a non-expanding scope", () => {
  const boundary = createSkillVaultBoundary();
  const permissions = ["filesystem_read", "network"];
  const approved = buildApproved(boundary, { permissions });
  const lockfile = createLock(boundary, [approved.review]);
  const { installation, conformance } = installAndConform(
    boundary,
    lockfile,
    approved.candidate,
    permissions,
  );
  const baseRequest = {
    requestId: "activation-request-001",
    skillId: approved.candidate.skillId,
    lockfile,
    installation,
    conformanceReport: conformance,
    expectedPolicyHash: POLICY_HASH,
    requestedPermissions: ["filesystem_read"],
    activationScopeId: "workspace-session-001",
  };

  assert.throws(
    () => boundary.guard.authorizeActivation({
      ...baseRequest,
      expectedPolicyHash: OTHER_POLICY_HASH,
    }),
    (error) => error.code === "POLICY_HASH_MISMATCH",
  );
  assert.throws(
    () => boundary.guard.authorizeActivation({
      ...baseRequest,
      requestedPermissions: ["filesystem_write"],
    }),
    (error) => error.code === "PERMISSION_EXPANSION_DENIED",
  );

  const authorization = boundary.guard.authorizeActivation(baseRequest);
  assert.equal(authorization.decision, "ALLOW");
  assert.equal(authorization.purpose, "explicit_skill_activation");
  assert.equal(authorization.contentHash, approved.candidate.contentHash);
  assert.equal(authorization.lockHash, lockfile.lock_hash);
  assert.equal(authorization.explicitApprovalLinked, true);
  assert.equal(authorization.rollbackAvailable, true);
  assert.equal(authorization.effectPerformed, false);
  assert.equal(boundary.guard.isActivationAuthorization(authorization), true);
  assert.equal(boundary.guard.isActivationAuthorization(JSON.parse(JSON.stringify(authorization))), false);
});

test("activation artifacts cannot be mixed across independent vault boundaries", () => {
  const first = createSkillVaultBoundary();
  const approved = buildApproved(first);
  const lockfile = createLock(first, [approved.review]);
  const { installation, conformance } = installAndConform(
    first,
    lockfile,
    approved.candidate,
    ["filesystem_read", "network"],
  );
  const second = createSkillVaultBoundary();

  assert.throws(
    () => second.guard.authorizeActivation({
      requestId: "activation-foreign-001",
      skillId: approved.candidate.skillId,
      lockfile,
      installation,
      conformanceReport: conformance,
      expectedPolicyHash: POLICY_HASH,
      requestedPermissions: [],
      activationScopeId: "workspace-session-001",
    }),
    (error) => error.code === "UNRECOGNIZED_LOCKFILE",
  );
});

test("non-canonical or accessor-bearing lock snapshots fail closed", () => {
  const boundary = createSkillVaultBoundary();
  const approved = buildApproved(boundary);
  const lockfile = createLock(boundary, [approved.review]);
  const unsorted = JSON.parse(JSON.stringify(lockfile));
  unsorted.skills[0].permissions.reverse();
  assert.throws(
    () => boundary.guard.verifySkillLockfileSnapshot(unsorted),
    (error) => error.code === "NON_CANONICAL_ORDER",
  );

  const accessor = JSON.parse(JSON.stringify(lockfile));
  let getterCalls = 0;
  Object.defineProperty(accessor, "lock_hash", {
    enumerable: true,
    get() {
      getterCalls += 1;
      return lockfile.lock_hash;
    },
  });
  assert.throws(
    () => boundary.guard.verifySkillLockfileSnapshot(accessor),
    (error) => error.code === "ACCESSOR_FIELD_DENIED",
  );
  assert.equal(getterCalls, 0);
});
