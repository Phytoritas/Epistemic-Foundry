# N01-0001 canonical RoleSpec and evidence/tool ACL review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed N01
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. `RoleSpec` requires an explicit mission, non-empty forbidden behaviors,
   input/output schema references, budget, timeout, expected count,
   independence group, acceptance checks, and failure/retry policy. Unknown or
   missing fields fail closed.
2. Tool, read, write, network, and evidence authority remain five independent
   ACL dimensions. A grant in one dimension implies no grant in another, and
   every known undeclared request returns deterministic `DENY_BY_DEFAULT`.
3. The tool vocabulary is closed to the 24 active canonical snake_case
   capabilities. Dotted and colon aliases fail with
   `CAPABILITY_VOCABULARY_MISMATCH`; unknown capability, evidence, and ACL
   labels are errors rather than silently denied aliases.
4. The evidence vocabulary is closed to 36 role-authority labels.
   `all_permitted` is an explicit privileged grant and cannot be requested as
   an evidence class. Defender and prosecutor fixtures prove asymmetric views.
5. Scopes reject absolute paths, drive paths, traversal, backslashes, ambiguous
   separators, and malformed wildcards. Network access binds exact canonical
   HTTPS origins without credentials, paths, wildcard hosts, or case aliases.
6. Role identity is deterministic and content-addressed. The SHA-256 hash binds
   canonical RoleSpec content and derives `ROLE-<64 hex>`; persisted ordering,
   content, and ID tampering fail closed.
7. Proxy objects, accessors, sparse arrays, decorated arrays, custom
   prototypes, unsupported Unicode/numbers, and cycles are rejected without
   invoking attacker-controlled getters. Inputs remain unmodified and emitted
   artifacts and ACL decisions are deeply immutable.
8. Projection to the existing nested `RoleDispatchPlan` role contains exactly
   the schema-accepted provider-neutral fields. `expected_count` remains sealed
   in the RoleSpec and plan-level authority remains with `RoleDispatchPlan`.
   Host-specific Codex/Claude compilation remains N02 responsibility.
9. Required checks pass 21/21: 10
   `role_schema_test` and 11 `acl_test` cases. Adjacent Python security passes
   26/26 and dispatch contracts pass 5/5. Full Node passes
   740/740
   across 73 files; full Python passes
   1064/1064.
   Codegen remains 126/126; structure, boundaries, syntax, and diff checks pass.
10. All five product files are BOM-less UTF-8 and remain inside exact
    `packages/role-router/src/contracts/**` scope. Existing dirty worktree
    changes and every historical report/evidence/generation are preserved.

## Assurance boundary

This gate establishes the canonical RoleSpec construction/integrity contract,
ACL decision semantics, evidence asymmetry, and provider-neutral dispatch-role
projection. It does not implement host compilation/spawning (N02), scheduler
leases/retries (N03), fan-in/reviewer independence enforcement (N04), overall
product completion, release readiness, or `completion_ready=true`. Global
`implementation_gate=fail` and `completion_ready=false` remain required.
