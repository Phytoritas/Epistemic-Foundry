# S03-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  packages/skill-vault. Reviewer: this seal-prep session, a distinct actor
  that did not author the Skill Vault boundary. The author never approves
  its own work, so actor_independence HOLDS for this review; external
  actor-independent certification does NOT, and no such claim is made. S03
  is risk_class=medium and governs the skill supply chain, so quarantine,
  static scanning, locking, and activation were attacked on their contracts
  rather than skimmed.
- Remote skills are quarantined and inactive until approved (fail closed).
  quarantineCandidate admits a remote candidate only into an inert
  QUARANTINED record with executable:false, active:false, and
  authorityEligible:false that exposes no raw files or content own-property,
  and it rejects hostile input shapes -- path traversal, absolute,
  backslash, and portable-reserved (NUL) names (PATH_ESCAPE_DENIED),
  case-folding name collisions (PATH_COLLISION), accessor-bearing fields
  (ACCESSOR_FIELD_DENIED), and Proxy inputs (PROXY_INPUT_DENIED) -- with the
  getter-call counter proving no getter ran. scanCandidate never executes a
  candidate byte (noScriptsExecuted:true) yet flags install hooks
  (PACKAGE_INSTALL_HOOK), dynamic evaluation (DYNAMIC_EVALUATION),
  self-authority claims (SELF_AUTHORITY_CLAIM), symlink content that it
  inventories without following (SYMLINK_CONTENT), a failed signature
  (SIGNATURE_VERIFICATION_FAILED), and script-shaped members (SCRIPT_CONTENT)
  while inferring the implied PROCESS_EXECUTE, SECRET_READ, and NETWORK
  permissions. Any CRITICAL finding makes issueReviewDecision fail closed
  with CRITICAL_FINDING_BLOCKS_APPROVAL, so a hostile fixture can never be
  approved.
- Approval binds the exact reviewed subject. A review must attest the exact
  source, revision, content hash, and the full inferred permission envelope
  or it is rejected (REVIEW_SUBJECT_MISMATCH, INFERRED_PERMISSION_MISSING),
  and a claimed remote signature is only a claim -- the reviewer must state a
  status explicitly (MISSING_FIELD). A candidate or scan minted by one vault
  boundary cannot be approved or rescanned by another, and a JSON-copied
  candidate is not recognized (UNRECOGNIZED_CANDIDATE), so brand identity is
  enforced by WeakMap rather than by trusting record shape.
- Approved skills are hash/license/permission pinned. createSkillLockfile
  emits a v1 lockfile that pins, per skill, the exact source, revision,
  content_hash, license, sorted permissions, sorted approver ids, and
  review_status under a lock_hash taken over canonical JSON; the hash is
  identical across review, permission, and approver input order, and the
  lockfile and its entries are deeply frozen. verifySkillLockfileSnapshot
  recomputes the lock_hash and refuses a mutated field (LOCK_HASH_MISMATCH),
  a reordered permission list (NON_CANONICAL_ORDER), or an accessor field
  (ACCESSOR_FIELD_DENIED) without invoking getters, and a serialized snapshot
  is verifiable but never a live authority (isSkillLockfile:false). A
  rejected decision stays locked as REJECTED with empty approvers and cannot
  be installed (SKILL_NOT_APPROVED).
- Disabled install and activation stay inert and non-expanding. A disabled
  installation requires the exact approved content hash (INSTALL_HASH_MISMATCH)
  and surfaces name collisions as BLOCKED_NAME_COLLISION that cannot receive
  passing conformance (INSTALLATION_NOT_CONFORMABLE); conformance cannot
  report a permission outside the lockfile (UNDECLARED_PERMISSION); and
  authorizeActivation requires the exact policy hash (POLICY_HASH_MISMATCH),
  a permission both locked and observed in conformance
  (UNVERIFIED_PERMISSION_DENIED), and a non-expanding request
  (PERMISSION_EXPANSION_DENIED), refuses artifacts mixed across boundaries
  (UNRECOGNIZED_LOCKFILE), and returns an ALLOW authorization that only
  describes the intent (effectPerformed:false, rollbackAvailable:true,
  explicitApprovalLinked:true) -- it never fetches, writes, imports, evals,
  or executes the candidate.
- Non-blocking note (disclosed, not a finding). skill-vault.mjs returns
  schemas/skill-lockfile.schema.json as a string schemaRef only; the schema
  file is neither read nor validated against, it lies outside the
  packages/skill-vault/** write scope, and no required check depends on it.
  Wiring a real Draft 2020-12 validation is a later, out-of-scope refinement
  and does not weaken the S03 contract.
- Dependencies and checks: the Skill Vault builds on the sealed S01 skill
  supply-chain package (S01 report PASS) and adds no new production
  dependency. Ruff lint and format, the two required checks
  (malicious_skill_fixture_test 11/11, skill_lockfile_test 10/10), targeted 21/21, full Python 1261/1261, full Node 1274/1274 across 113 files, and git diff --check all pass with
  zero failures.
- Residual limitations: S03 provides skill quarantine, static scanning,
  the SkillLockfile, and disabled-install and activation gating only; the
  S-phase threat model and red-team gate (S04) and the wider runtime skill
  execution surface remain later packages. Verdict: PASS on the exact S03
  package contract.
