BEGIN;

CREATE SCHEMA epistemic_foundry;
REVOKE ALL ON SCHEMA epistemic_foundry FROM PUBLIC;

CREATE TABLE epistemic_foundry.store_metadata (
    key text COLLATE pg_catalog."C" PRIMARY KEY,
    value text COLLATE pg_catalog."C" NOT NULL
);

INSERT INTO epistemic_foundry.store_metadata (key, value) VALUES
    ('schema_version', '1'),
    ('contract_id', 'epistemic-foundry-postgres-team-store/v1'),
    ('identifier_encoding', 'utf16be-lowerhex-v1'),
    ('identity_collation', 'pg_catalog.C-deterministic'),
    ('identity_uniqueness', 'serialized-exact-match-no-length-limited-index'),
    ('revision_genesis', '0'),
    ('revision_ceiling', '9007199254740991'),
    ('isolation_policy', 'principal+tenant+workspace+transaction-local-context');

CREATE TABLE epistemic_foundry.principal_scopes (
    principal_name name NOT NULL,
    tenant_id text COLLATE pg_catalog."C" NOT NULL,
    workspace_id text COLLATE pg_catalog."C" NOT NULL,
    granted_at timestamp with time zone NOT NULL DEFAULT statement_timestamp(),
    CONSTRAINT principal_scopes_pk
        PRIMARY KEY (principal_name, tenant_id, workspace_id),
    CONSTRAINT principal_scopes_principal_nonempty
        CHECK (principal_name <> ''::name),
    CONSTRAINT principal_scopes_tenant_nonempty
        CHECK (tenant_id <> ''),
    CONSTRAINT principal_scopes_workspace_nonempty
        CHECK (workspace_id <> '')
);

CREATE TABLE epistemic_foundry.revisioned_records (
    tenant_id text COLLATE pg_catalog."C" NOT NULL,
    workspace_id text COLLATE pg_catalog."C" NOT NULL,
    record_type text COLLATE pg_catalog."C" NOT NULL,
    record_id text COLLATE pg_catalog."C" NOT NULL,
    revision bigint NOT NULL,
    value_json json NOT NULL,
    CONSTRAINT revisioned_records_tenant_nonempty
        CHECK (tenant_id <> ''),
    CONSTRAINT revisioned_records_workspace_nonempty
        CHECK (workspace_id <> ''),
    CONSTRAINT revisioned_records_type_nonempty
        CHECK (record_type <> ''),
    CONSTRAINT revisioned_records_type_encoding
        CHECK (record_type ~ '^u16be:([0-9a-f]{4})+$'),
    CONSTRAINT revisioned_records_id_nonempty
        CHECK (record_id <> ''),
    CONSTRAINT revisioned_records_id_encoding
        CHECK (record_id ~ '^u16be:([0-9a-f]{4})+$'),
    CONSTRAINT revisioned_records_revision_range
        CHECK (revision >= 0 AND revision <= 9007199254740991)
);

CREATE FUNCTION epistemic_foundry.scope_is_authorized(
    requested_tenant text,
    requested_workspace text
) RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
    SELECT EXISTS (
        SELECT 1
          FROM epistemic_foundry.principal_scopes AS scope
         WHERE scope.principal_name = session_user::name
           AND scope.tenant_id = requested_tenant
           AND scope.workspace_id = requested_workspace
    )
$function$;

REVOKE ALL ON FUNCTION epistemic_foundry.scope_is_authorized(text, text) FROM PUBLIC;

CREATE FUNCTION epistemic_foundry.acquire_writer_lock(
    requested_tenant text,
    requested_workspace text
) RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
BEGIN
    IF NULLIF(
        current_setting('epistemic_foundry.tenant_id', true),
        ''
    ) IS DISTINCT FROM requested_tenant
       OR NULLIF(
           current_setting('epistemic_foundry.workspace_id', true),
           ''
       ) IS DISTINCT FROM requested_workspace
       OR NOT epistemic_foundry.scope_is_authorized(
           requested_tenant,
           requested_workspace
       ) THEN
        RAISE EXCEPTION 'writer lock scope is not authorized'
            USING ERRCODE = '42501';
    END IF;

    LOCK TABLE epistemic_foundry.revisioned_records
        IN SHARE ROW EXCLUSIVE MODE;
    RETURN true;
END
$function$;

REVOKE ALL ON FUNCTION
    epistemic_foundry.acquire_writer_lock(text, text)
    FROM PUBLIC;

CREATE FUNCTION epistemic_foundry.create_revisioned_record(
    requested_tenant text,
    requested_workspace text,
    requested_record_type text,
    requested_record_id text,
    requested_value_json json
) RETURNS TABLE (
    record_type text,
    record_id text,
    revision bigint,
    value_json json,
    created boolean
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
BEGIN
    LOCK TABLE epistemic_foundry.revisioned_records
        IN SHARE ROW EXCLUSIVE MODE;

    IF EXISTS (
        SELECT 1
          FROM epistemic_foundry.revisioned_records AS target
         WHERE target.tenant_id = requested_tenant
           AND target.workspace_id = requested_workspace
           AND target.record_type = requested_record_type
           AND target.record_id = requested_record_id
    ) THEN
        RETURN QUERY
        SELECT target.record_type,
               target.record_id,
               target.revision,
               target.value_json,
               false
          FROM epistemic_foundry.revisioned_records AS target
         WHERE target.tenant_id = requested_tenant
           AND target.workspace_id = requested_workspace
           AND target.record_type = requested_record_type
           AND target.record_id = requested_record_id;
        RETURN;
    END IF;

    RETURN QUERY
    INSERT INTO epistemic_foundry.revisioned_records AS target
        (tenant_id, workspace_id, record_type, record_id, revision, value_json)
    VALUES (
        requested_tenant,
        requested_workspace,
        requested_record_type,
        requested_record_id,
        0,
        requested_value_json
    )
    RETURNING target.record_type,
              target.record_id,
              target.revision,
              target.value_json,
              true;
END
$function$;

REVOKE ALL ON FUNCTION
    epistemic_foundry.create_revisioned_record(text, text, text, text, json)
    FROM PUBLIC;

CREATE FUNCTION epistemic_foundry.compare_and_swap_revision(
    requested_tenant text,
    requested_workspace text,
    requested_record_type text,
    requested_record_id text,
    requested_expected_revision bigint,
    requested_value_json json
) RETURNS TABLE (
    record_type text,
    record_id text,
    revision bigint,
    value_json json
)
LANGUAGE sql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
    UPDATE epistemic_foundry.revisioned_records AS target
       SET revision = target.revision + 1,
           value_json = requested_value_json
     WHERE target.tenant_id = NULLIF(
               requested_tenant,
               ''
           )
       AND target.workspace_id = NULLIF(requested_workspace, '')
       AND target.record_type = requested_record_type
       AND target.record_id = requested_record_id
       AND target.revision = requested_expected_revision
       AND target.revision < 9007199254740991
    RETURNING target.record_type, target.record_id, target.revision, target.value_json
$function$;

REVOKE ALL ON FUNCTION
    epistemic_foundry.compare_and_swap_revision(
        text, text, text, text, bigint, json
    )
    FROM PUBLIC;

ALTER TABLE epistemic_foundry.revisioned_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE epistemic_foundry.revisioned_records FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_workspace_isolation
    ON epistemic_foundry.revisioned_records
    AS PERMISSIVE
    FOR ALL
    USING (
        tenant_id = NULLIF(
            current_setting('epistemic_foundry.tenant_id', true),
            ''
        )
        AND workspace_id = NULLIF(
            current_setting('epistemic_foundry.workspace_id', true),
            ''
        )
        AND epistemic_foundry.scope_is_authorized(tenant_id, workspace_id)
    )
    WITH CHECK (
        tenant_id = NULLIF(
            current_setting('epistemic_foundry.tenant_id', true),
            ''
        )
        AND workspace_id = NULLIF(
            current_setting('epistemic_foundry.workspace_id', true),
            ''
        )
        AND epistemic_foundry.scope_is_authorized(tenant_id, workspace_id)
    );

REVOKE ALL ON ALL TABLES IN SCHEMA epistemic_foundry FROM PUBLIC;

COMMENT ON TABLE epistemic_foundry.revisioned_records IS
    'D02 tenant/workspace-scoped canonical revision primitive; access requires RLS context and principal scope.';
COMMENT ON TABLE epistemic_foundry.principal_scopes IS
    'Administrative binding from immutable PostgreSQL session_user to authorized tenant/workspace scopes.';
COMMENT ON FUNCTION epistemic_foundry.scope_is_authorized(text, text) IS
    'RLS helper bound to session_user; SECURITY DEFINER uses a fixed pg_catalog search_path.';
COMMENT ON FUNCTION epistemic_foundry.acquire_writer_lock(text, text) IS
    'Serializes writer transactions before callback entry after revalidating bound tenant/workspace authority.';
COMMENT ON FUNCTION epistemic_foundry.create_revisioned_record(
    text, text, text, text, json
) IS
    'Only runtime create path; binds tenant/workspace from transaction-local context and fixes genesis revision at zero.';
COMMENT ON FUNCTION epistemic_foundry.compare_and_swap_revision(
    text, text, text, text, bigint, json
) IS
    'Only runtime update path; performs one atomic revision compare-and-swap under forced RLS.';

COMMIT;
