# PostgreSQL team-store migration

`0001_team_store.sql` is the D02 authority for the generic revisioned-record
primitive used by the TEAM profile. Apply it once as a dedicated,
non-superuser migration owner. Runtime principals must be `NOSUPERUSER` and
`NOBYPASSRLS`; neither the migration owner nor a role that owns the table is a
runtime credential.

Provision each runtime login explicitly. Replace the identifiers and values
below through an administrator-controlled migration/provisioning tool; do not
construct this SQL from untrusted strings.

Runtime logins receive these grants directly and must not be members of any
other PostgreSQL role. The adapter rejects role membership even when it does
not currently add an effective privilege, because later grants to that role
would otherwise silently widen the runtime authority boundary.

```sql
GRANT USAGE ON SCHEMA epistemic_foundry TO runtime_principal;
GRANT SELECT ON epistemic_foundry.store_metadata TO runtime_principal;
GRANT SELECT ON epistemic_foundry.revisioned_records TO runtime_principal;
GRANT EXECUTE
    ON FUNCTION epistemic_foundry.scope_is_authorized(text, text)
    TO runtime_principal;
GRANT EXECUTE
    ON FUNCTION epistemic_foundry.acquire_writer_lock(text, text)
    TO runtime_principal;
GRANT EXECUTE
    ON FUNCTION epistemic_foundry.create_revisioned_record(
        text, text, text, text, json
    )
    TO runtime_principal;
GRANT EXECUTE
    ON FUNCTION epistemic_foundry.compare_and_swap_revision(
        text, text, text, text, bigint, json
    )
    TO runtime_principal;

INSERT INTO epistemic_foundry.principal_scopes
    (principal_name, tenant_id, workspace_id)
VALUES ('runtime_principal', 'TENANT-ID', 'WORKSPACE-ID');
```

Isolation has three conjunctive controls:

1. `session_user` must have an administrative `principal_scopes` binding.
2. The transaction-local `epistemic_foundry.tenant_id` and
   `epistemic_foundry.workspace_id` settings must match the row.
3. `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` apply the policy
   to normal users and the table owner. PostgreSQL superusers and
   `BYPASSRLS` roles remain outside the runtime trust boundary and are rejected
   by the Python adapter.

The custom settings are set with `set_config(..., true)`, so they expire on
commit or rollback. Absence of either setting is default-deny. The runtime
role has no access to `principal_scopes` and cannot grant itself a scope.
It also has no direct `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`,
or `TRIGGER` privilege on `revisioned_records`. Creates and updates cross the
database boundary only through the two fixed `SECURITY DEFINER` functions,
which remain subject to forced RLS and preserve revision genesis, atomic CAS,
and the absence of a runtime delete path.

Explicit transactions and implicit mutations call the bounded
`acquire_writer_lock` function before user code or mutation logic executes.
This mirrors D01's `BEGIN IMMEDIATE` writer serialization: concurrent callbacks
cannot both observe the same pre-write state and later overwrite one another.
The function revalidates transaction-local scope and principal authorization
before acquiring the table lock; reads do not acquire it.

Logical `record_type` and `record_id` strings are encoded as canonical
`utf16be-lowerhex-v1` text before storage. This reversible ASCII projection is
required because PostgreSQL `text` cannot contain NUL while D01 identifiers
may contain any non-empty JavaScript string, including NUL and lone UTF-16
surrogates. Database constraints reject non-canonical encoded identifiers.
Every contract text column that participates in identity, scope, or metadata
comparison uses deterministic `pg_catalog."C"` collation. Equality therefore
does not inherit a deployment database's locale or nondeterministic ICU
rules; the runtime catalog fingerprint verifies the collation namespace,
name, provider, and determinism.

The generic value column uses PostgreSQL `json`, not `jsonb`. This is
intentional parity with the D01 local store: JSON member order, control
characters, and escaped lone UTF-16 surrogates round-trip as values, while
semantic non-finite numbers such as `1e400` are detected fail-closed by the
adapter's integrity validation.
