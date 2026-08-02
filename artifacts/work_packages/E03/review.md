# E03 Capability leases, fencing and approval policy review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Final verdict: `PASS`

blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

The product owner requires serial primary-session execution without Fleet or
subagents and explicitly authorizes the independent-review artifacts. This is a
procedurally separate adversarial review of the final E03 bytes. It is not
external actor-independent certification.

## Authority and reviewed boundary

- `MASTER_SPEC.md`, `MASTER_EXECUTION_PROMPT.md`, `AGENTS.md`, and E03 in
  `manifests/development_manifest.yaml`;
- invariant `EF4-I17` (immutable, scoped human authority) and the no-self-
  approval, kernel-authority, receipt, and replay boundaries that E03 consumes;
- canonical `schemas/capability-lease.schema.json` —
  `sha256:c5eb61b41328b055f75466fd4d1d29ed93a535a2d2375a7596fd8a77ba51946c`;
- canonical `schemas/approval-record.schema.json` —
  `sha256:0b0554c764c185f75a568dbf308a17bab291896b6a28bd7633c0b2f7aedaa7eb`;
- E01 dependency report —
  `sha256:beddc2a3019fcf680435ea6d5f907b5e7b50b0fa8a384673917c6198f49f32e1`;
- unchanged dependency implementations: D01 SQLite store
  (`sha256:6619dccb72f40e92fdaae3d023a2d6591f8d63bdfe789ba5c36b53ce7dbe1380`),
  D03 artifact store
  (`sha256:75e69756d30ab5b5112fd908f3fec312660f30e603fe1201566db2ad263c8c8e`),
  and E01 Noetic Ledger
  (`sha256:58ea9dc0d52d9c20720b33970ee3b8d8d05703ba7dd0fb4f51a483d9f505f1ed`);
- final E03 files:
  - `packages/foundry-kernel/src/capabilities/capability-authority.mjs` —
    `sha256:a8e3376568350229ca1a997aafbc1c4c138f2f01fbee945c916d390283a3720a`;
  - `packages/foundry-kernel/src/capabilities/capability-test-support.mjs` —
    `sha256:6b08085736247a17b3c477617aa820274a09ca8206d616acc44cd12a1358e2fa`;
  - `packages/foundry-kernel/src/capabilities/fencing.test.mjs` —
    `sha256:e66558d061c74f2c3be7c5a648b1230ad22f566359d608c6135b62f626940884`;
  - `packages/foundry-kernel/src/capabilities/lease-expiry.test.mjs` —
    `sha256:ec179fea28039c9e53cc1df8d6d39e1b97ce45b8d60edb0193f64f472ac2f640`.

E03 owns only `packages/foundry-kernel/src/capabilities/**` plus its declared
evidence artifacts. No canonical schema, E01 ledger, D01 state store, D03
artifact store, manifest, or other package implementation was changed to make
E03 pass.

## Adversarial findings

1. **Canonical lease and approval integrity — PASS.** `CapabilityLease` and
   `ApprovalRecord` accept plain canonical JSON only, bind every authority field
   except their own hash, enforce exact SHA-256 and RFC 3339 forms, and validate
   emitted fixtures against the unchanged Draft 2020-12 schemas. Public
   commands cannot assert authority roles, principal types, issue times, policy
   hashes, fencing tokens, or record hashes.
2. **Sealed policy authority — PASS.** The runtime accepts only locally sealed
   policy projections. Every principal, subject, capability rule, approval rule,
   run, maker identity, capability, and resource scope is normalized and
   immutable. The externally supplied `policy_hash` is supplemented by an exact
   capability-projection hash, so reusing one PolicyBundle hash with different
   authority data fails closed.
3. **Privilege separation and self-approval — PASS.** Candidate, model, prompt,
   and backend identities cannot receive holdout, evaluator, policy, approval,
   promotion-commit, ledger-rewrite, or capability-minting authority. An
   authority role alone is insufficient without `approval:issue`, and a maker
   cannot approve its own subject. `capability:issue`, `capability:revoke`, and
   `approval:issue` remain distinct grants.
4. **Scoped, expiring leases — PASS.** A lease binds the exact principal, run,
   capability set, resource-scope set, issue/expiry interval, approval IDs,
   policy hash, and monotonic fencing token. Missing, expired, not-yet-valid,
   revoked, forged, cross-run, cross-principal, under-scoped, or policy-mismatched
   leases fail before the protected callback can commit.
5. **Fencing and atomicity — PASS.** D01 allocates one global monotonic fencing
   counter and records a head for every leased resource scope. Replacing any
   overlapping scope invalidates the whole older multi-scope lease. Lease
   validation occurs before and after the synchronous callback, while the
   protected mutation, immutable lease-use record, and event outbox entry share
   one D01 transaction. Callback failure, async return, expiry, clock regression,
   or stale fencing rolls back all protected writes.
6. **Approval head and downstream invalidation — PASS.** Only the current exact
   `(subject_id, approval_type)` head can satisfy an approval-gated capability.
   A later `DENY`, `EXPIRE`, or `REVOKE` therefore invalidates an earlier
   `APPROVE` without rewriting history. Distinct decisions require strictly
   increasing trusted authority time: clock regression and same-instant
   ambiguous ordering both fail closed and roll back the proposed record.
7. **Idempotency and retry — PASS.** Lease issuance, approval issuance, and
   lease-protected operations bind canonical request hashes. Same-ID changed
   requests conflict. Exact issuance retries return the immutable logical result
   even after its expiry, rather than consulting current time or minting a new
   token. A revoked lease retry returns the current revoked revision and the
   original fencing token. Exact committed-operation retries never rerun the
   callback, even after lease expiry.
8. **Private-state and publication boundary — PASS.** The callback receives a
   narrowed D01 facade and cannot read or mutate any E03 private record type.
   Canonical state commits before E01 publication; an E01 outage yields
   `CAPABILITY_EVENT_RECONCILIATION_REQUIRED`, never a false rollback claim.
   The indexed outbox replays the exact event once and verifies the resulting
   payload/event hashes.
9. **Regression and repeatability — PASS for E03.** The final targeted gate is
   30/30, five independent final repeats are 150/150, and coverage of
   `capability-authority.mjs` is 90.27% lines, 72.05% branches, and 97.12%
   functions. Python is 913/913. Repository structure, package boundaries,
   toolchain/locks, CI matrix/cache, ten CI policy mutation tests, syntax,
   strict UTF-8, marker audit, and `git diff --check` pass. Final repository-wide
   Node discovery is 219 passed with only the pre-existing out-of-scope
   `S04-TM004` stale manifest-hash binding.

## Resolved review findings

- `E03-RF001_POLICY_PROJECTION_REBIND`: the exact normalized authority
  projection is now sealed and persisted beside the external PolicyBundle hash.
- `E03-RF002_REVOKED_ISSUANCE_RETRY`: exact retry reads the current lease
  revision and cannot mint a replacement fencing token.
- `E03-RF003_APPROVAL_SCHEMA_PROOF`: emitted `ApprovalRecord` now has a direct
  canonical-schema validation test.
- `E03-RF004_APPROVAL_CLOCK_REGRESSION`: an older authority time cannot replace
  a newer approval head.
- `E03-RF005_APPROVAL_TIMESTAMP_CONFLICT`: distinct same-instant decisions are
  rejected instead of receiving storage-order authority.
- `E03-RF006_EXPIRED_EXACT_RETRY`: existing lease and approval bindings are
  resolved before new-issuance clock admission, preserving idempotency after
  expiry.

## Preserved failed and residual observations

- Repository-wide Node discovery ends at 219 passed and 1 failed. The sole
  failure is `S04-TM004`, whose historical threat-model fixture expects the old
  `development_manifest.yaml` hash
  `456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7`
  while the authorized manifest is
  `a0a0db29da459d29c655827eaa0f7253d1becc3e75106f369850335ac7b88345`.
  E03 has no S04 write authority and does not alter or hide this failure.
- `scripts/build/double_build.py` still fails while building its staged source
  because that staging path omits the existing `scripts/` build-hook package.
  E03 has no B02/B04 packaging authority; the failure is preserved.
- One exploratory PowerShell `rg` command used an unsafe double-quoted alternation
  and was parsed as commands. It changed no state; the retry used a single-quoted
  pattern. This command-safety event remains in `commands.jsonl`.

## Assurance limitations

- E03 qualifies local authority, lease, fencing, approval-head, and outbox
  semantics over the D01/D03/E01 dependencies. It does not prove distributed
  consensus, remote-clock trust, or cross-region exactly-once execution.
- The callback facade blocks E03 private record types. Domain packages remain
  responsible for mapping their own record types and resource scopes to the
  granted capability; E04 and downstream integration gates must verify those
  compositions.
- E03 consumes an externally canonical `PolicyBundle.policy_hash` and seals the
  capability projection it actually enforces. It does not redefine or
  independently recompute the full PolicyBundle schema hash.
- `approval:issue` is the kernel authority grant. Transport capabilities such as
  `promotion:approve` and `action:approve` remain adapter mappings and are not
  redefined by E03.
- The separate review is user-authorized and procedurally independent within
  the primary session; it is not external actor-independent certification.

## Decision

E03 satisfies its exact package contract. Leases are scoped and expiring,
stale fencing tokens are rejected, approval authority is immutable and
fail-closed, and retries cannot mint authority from time drift or narration.
The overall Foundry objective remains active and `completion_ready=false`.
