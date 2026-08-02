# D02 PostgreSQL team store and tenant isolation review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Final verdict: `PASS`

blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

The product owner requires serial primary-session execution without Fleet or
subagents and explicitly approves all independent reviews. This review is
therefore a procedurally separate adversarial pass in the primary session. It
does not claim external actor-independent certification.

## Authority and final reviewed bytes

- `MASTER_SPEC.md`, `MASTER_EXECUTION_PROMPT.md`, `AGENTS.md`, and D02 in
  `manifests/development_manifest.yaml`;
- D01 dependency report —
  `sha256:00d44672b4c9680589ecd85c39f617c29bdfe79afd288a2769cafb1ba59a9a91`;
- `migrations/postgres/0001_team_store.sql` —
  `sha256:21f349f098a03b8e7e2f4a82cef69f5df0fe2e73d88224ab197191260e316682`;
- `migrations/postgres/README.md` —
  `sha256:5ecaffa635dd57485cfd2396818293e3a55febfcb544dc055f6f2fc5dcf83824`;
- `python/epistemic_foundry/storage/postgres/__init__.py` —
  `sha256:31c6f062cb222577dcc7075214b846d9f8a3675cfec2a130381d66d87eac9b35`;
- `python/epistemic_foundry/storage/postgres/store.py` —
  `sha256:ce99d637676c7044e8279d0778de94870e6f78946ed4884dbff2a19c2b8b875e`;
- `python/epistemic_foundry/storage/postgres/pytest.ini` —
  `sha256:66c104fc7cf9ee25275c59ce534e0ba856e4dc09e1720c6ad8f9d39ff1685af3`;
- `python/epistemic_foundry/storage/postgres/conftest.py` —
  `sha256:c0dc0003e1046a8323919bacdaccd798a321dd6c79c81e6bb700f9280c001d45`;
- `python/epistemic_foundry/storage/postgres/test_postgres_contract.py` —
  `sha256:d4dab6fc3bf06c8a82367d1862896e605e82376342e6e867fae9c952e47f875c`;
- `python/epistemic_foundry/storage/postgres/test_tenant_isolation.py` —
  `sha256:013f69760a94fadf74eb6c0910f6d307de5dbb0bb36fddae39f227febca85882`.

## Resolved blocking findings

1. **D02-RF001 — quoted SQL literal normalization.** The original catalog
   fingerprint normalizer collapsed whitespace inside quoted literals, so a
   function containing `''` could compare equal to one containing `' '`. The
   implementation now uses a lexical normalizer that preserves quoted string
   and identifier content while normalizing only insignificant SQL layout.
   A real function-literal drift fixture now fails closed.
2. **D02-RF002 — deployment-independent text identity.** PostgreSQL `text`
   columns inherited the database default collation, leaving exact logical
   identity semantics dependent on locale or ICU configuration. Identity,
   scope, and metadata text columns now use deterministic
   `pg_catalog."C"`; the catalog fingerprint binds collation namespace, name,
   provider, and determinism. A collation-drift fixture now fails closed.

## Final findings

1. **D01 semantic parity — PASS.** The store uses the logical identity
   `(tenant_id, workspace_id, record_type, record_id)`, revision genesis zero,
   synchronous transactions, and atomic compare-and-swap semantics. PostgreSQL
   `json` plus runtime validation preserves the D01 JSON/IEEE-754 contract.
2. **Unbounded JavaScript string identity — PASS.** Non-empty `record_type`
   and `record_id` values, including NUL, astral characters, lone surrogates,
   and long strings, round-trip through the reversible
   `utf16be-lowerhex-v1` (`u16be:`) projection. Exact full-text identity is
   checked while writers are serialized rather than truncated into a
   length-limited key.
3. **Transaction serialization — PASS.** Explicit and implicit mutation paths
   acquire the writer-table lock before user callback entry. A per-store
   `RLock` and explicit callback-thread ownership prevent overlapping or
   escaped transactions. Async callbacks and hostile custom awaitables are
   rejected without partial persistence.
4. **Tenant/workspace isolation — PASS.** Tables have `ENABLE` and `FORCE ROW
   LEVEL SECURITY`. Access requires the runtime role plus transaction-local
   tenant/workspace and principal-scope GUCs. Direct DML, privileged/runtime
   role membership, `SET ROLE`, wrong-scope access, and candidate privilege
   escalation are denied.
5. **Fixed security-definer boundary — PASS.** Four fixed
   `SECURITY DEFINER` functions use `search_path=pg_catalog`; PUBLIC execute is
   revoked. Exact function, ACL, policy, index, constraint, trigger, schema,
   and collation fingerprints are verified.
6. **Fail-closed integrity — PASS.** Missing resources, hash or catalog drift,
   duplicate identity, invalid persisted values, uncertain rollback, and
   tampering enter typed failure or `SAFE_MODE`; there is no source-tree or
   permissive fallback.
7. **Real PostgreSQL verification — PASS.** PostgreSQL 16.13 contract and
   isolation tests record 43/43. Ten independent final contention runs cover
   CAS, create, and callback-entry serialization: 30/30 targeted executions
   passed.
8. **Regression — PASS for D02.** Python records 912/912; D01 plus
   foundry-kernel security records 72/72. Structure, boundary, lock,
   CI-matrix/cache-policy, strict UTF-8, and whitespace checks pass.

## Preserved failures and limitations

- The repository-wide Node set records 103 passed and one existing non-D02
  failure, `S04-TM004`, because the stored
  `development_manifest.yaml` hash binding is stale. D02 does not own S04.
- `scripts/build/double_build.py` retains the existing non-D02 failure because
  staged source omits `scripts/`, which the build hook requires. D02 does not
  own the build integration surface.
- The first collation-catalog probe used SQL alias `collation`, which produced
  PostgreSQL syntax error `42601`; the alias was changed to
  `collation_definition`, after which both targeted tests passed. This is
  preserved in `commands.jsonl` rather than hidden.
- Two attempted generated `__pycache__` cleanup commands were rejected before
  execution by the command-safety policy. No files changed. Generated caches
  are outside D02 evidence and no destructive retry was made.
- The PostgreSQL dependency `psycopg[binary]==3.2.10` was used transiently for
  tests. Dependency manifests were not changed because they are outside D02
  write scope.

## Decision

D02 satisfies its exact package contract. The PostgreSQL team store matches
the local logical semantics and enforces tenant/workspace isolation with
fail-closed catalog and authorization checks. No non-waivable D02 finding
remains. The overall Foundry objective is not complete; `completion_ready`
remains false and the next dependency-ready package is D03.
