# D02-0001 independent review of bounded-agent work

- Author: a bounded implementation agent (disjoint write scope over
  python/epistemic_foundry/storage/postgres/** and migrations/postgres/**,
  frozen contracts) under the product owner's explicit instruction.
  Reviewer: the sealing agent, which did not author this attempt;
  author/reviewer separation holds with actor_independence=true, while
  external actor-independent certification does not.
- Team store matches D01 local semantics: the logical identity is
  (tenant_id, workspace_id, record_type, record_id); a created record has
  revision genesis zero; compare_and_swap_revision increments by exactly
  one under the expected-revision guard; a stale expected revision is
  refused STALE_REVISION, a duplicate create returns the existing record
  (RECORD_ALREADY_EXISTS on the create contract), a missing record is
  refused RECORD_NOT_FOUND, and the 9007199254740991 ceiling refuses
  REVISION_EXHAUSTED.
- JSON and identifier edge values round-trip: PostgreSQL json (not jsonb)
  plus adapter integrity validation preserves JSON member order, control
  characters, and escaped lone UTF-16 surrogates as values while
  fail-closing on semantic non-finite numbers such as 1e400; record_type
  and record_id use the reversible utf16be-lowerhex-v1 (u16be:) projection
  so NUL, astral characters, lone surrogates, and long strings keep exact
  full-text identity under deterministic pg_catalog."C" collation rather
  than a length-limited key.
- Tenant/workspace isolation is genuinely enforced against real roles:
  records are partitioned by tenant_id + workspace_id; access requires the
  runtime role's administrative principal_scopes binding on session_user,
  the transaction-local epistemic_foundry.tenant_id/workspace_id GUCs, and
  scope_is_authorized. Unauthorized scope is denied at open
  (SCOPE_NOT_AUTHORIZED); a GUC set for a scope the principal lacks cannot
  bypass the binding and raises 42501/InsufficientPrivilege; a missing
  context is default-deny; ENABLE plus FORCE ROW LEVEL SECURITY binds even
  the non-superuser table owner; superuser/BYPASSRLS principals are
  rejected by the adapter; and privilege, column, policy, role-membership,
  and catalog drift enter fail-closed SAFE_MODE rather than a permissive
  fallback.
- Fixed security-definer boundary: four SECURITY DEFINER functions
  (scope_is_authorized, acquire_writer_lock, create_revisioned_record,
  compare_and_swap_revision) pin search_path=pg_catalog with PUBLIC EXECUTE
  revoked; the runtime role has no direct INSERT/UPDATE/DELETE/TRUNCATE on
  revisioned_records, so create and update cross the boundary only through
  the two fixed functions under forced RLS, mirroring D01's writer
  serialization.
- Real-server execution, not mocks: conftest.py provisions an ephemeral
  database and dedicated NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
  NOBYPASSRLS runtime roles from an administrator DSN read from the
  environment, and the fixture refuses a mock-only run. The two required
  suites are green against postgres:16 (postgres_contract_test 30/30,
  tenant_isolation_test 13/13, 43 targeted). No assertion was weakened or
  skipped.
- Boundary: the adapter imports the standard library alone and injects no
  driver; a caller supplies the PostgreSQL connection factory. D01 is a
  manifest-order dependency, not composed code. The component ships under
  python/ and stays out of the wheel.
- Integration gates at review time: ruff check clean, git diff --check
  clean, the two required suites green at 30/30 and 13/13, the EF4-I22
  wire-literal gate 5/5, packaging discovery PASS, full Python 1261/1261
  and full Node 1702/1702 across the 136-file inventory. Zero blocking
  findings.
- Preserved observation (non-blocking, outside D02 scope): on the first
  full-Node sweep one test in
  packages/foundry-kernel/src/artifacts/orphan-receipt.test.mjs
  ("concurrent readers tolerate transient staging and lock handoff")
  flaked once with a Windows EPERM under ARTIFACT_STORE_STRUCTURE_INVALID.
  It passed 4/4 in isolation and the full sweep re-ran clean at 1702/1702.
  The file is D03 (artifact-store) territory, outside D02's write scope,
  and D02 changed no Node-relevant file; the flake is a pre-existing
  Windows-concurrency artifact, not a D02 regression, and is recorded here
  rather than hidden.
