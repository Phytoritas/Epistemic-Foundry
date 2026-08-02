from __future__ import annotations

import psycopg
import pytest
from psycopg import sql

from epistemic_foundry.storage.postgres import (
    POSTGRES_STORE_MODE,
    PostgresStateStoreError,
    open_postgres_state_store,
)


def _open(cluster, principal: str, tenant: str, workspace: str):
    return open_postgres_state_store(cluster.factory(principal), tenant, workspace)


def test_tenant_isolation_same_record_key_is_partitioned_by_tenant_and_workspace(
    postgres_cluster,
) -> None:
    a1 = _open(postgres_cluster, "A", "TENANT-A", "WORKSPACE-1")
    a2 = _open(postgres_cluster, "A", "TENANT-A", "WORKSPACE-2")
    b1 = _open(postgres_cluster, "B", "TENANT-B", "WORKSPACE-1")
    try:
        a1.create_revisioned_record(
            record_type="session", record_id="shared-id", value={"scope": "A1"}
        )
        a2.create_revisioned_record(
            record_type="session", record_id="shared-id", value={"scope": "A2"}
        )
        b1.create_revisioned_record(
            record_type="session", record_id="shared-id", value={"scope": "B1"}
        )
        assert a1.read_revisioned_record("session", "shared-id")["value"] == {"scope": "A1"}
        assert a2.read_revisioned_record("session", "shared-id")["value"] == {"scope": "A2"}
        assert b1.read_revisioned_record("session", "shared-id")["value"] == {"scope": "B1"}
    finally:
        a1.close()
        a2.close()
        b1.close()


def test_tenant_isolation_unauthorized_scope_is_rejected_before_store_use(
    postgres_cluster,
) -> None:
    with pytest.raises(PostgresStateStoreError) as denied:
        _open(postgres_cluster, "A", "TENANT-B", "WORKSPACE-1")
    assert denied.value.code == "SCOPE_NOT_AUTHORIZED"

    with pytest.raises(PostgresStateStoreError) as denied_workspace:
        _open(postgres_cluster, "B", "TENANT-B", "WORKSPACE-2")
    assert denied_workspace.value.code == "SCOPE_NOT_AUTHORIZED"


def test_tenant_isolation_raw_guc_impersonation_cannot_bypass_principal_binding(
    postgres_cluster,
) -> None:
    a1 = _open(postgres_cluster, "A", "TENANT-A", "WORKSPACE-1")
    try:
        a1.create_revisioned_record(
            record_type="claim", record_id="foreign", value={"owner": "A"}
        )
    finally:
        a1.close()

    with psycopg.connect(postgres_cluster.runtime_dsns["B"], autocommit=True) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with connection.transaction():
                connection.execute(
                    "SELECT set_config('epistemic_foundry.tenant_id', 'TENANT-A', true), "
                    "set_config('epistemic_foundry.workspace_id', 'WORKSPACE-1', true)"
                )
                count = connection.execute(
                    "SELECT count(*) FROM epistemic_foundry.revisioned_records"
                ).fetchone()[0]
                assert count == 0
                connection.execute(
                    """
                    INSERT INTO epistemic_foundry.revisioned_records
                        (tenant_id, workspace_id, record_type, record_id, revision, value_json)
                    VALUES ('TENANT-A', 'WORKSPACE-1', 'claim', 'forged', 0, '{}'::json)
                    """
                )
        assert connection.execute("SELECT 1").fetchone()[0] == 1


def test_tenant_isolation_missing_context_is_default_deny_and_context_does_not_leak(
    postgres_cluster,
) -> None:
    store = _open(postgres_cluster, "A", "TENANT-A", "WORKSPACE-1")
    try:
        store.create_revisioned_record(
            record_type="claim", record_id="context", value={"visible": True}
        )
    finally:
        store.close()

    with psycopg.connect(postgres_cluster.runtime_dsns["A"], autocommit=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM epistemic_foundry.revisioned_records"
        ).fetchone()[0] == 0
        with connection.transaction():
            connection.execute(
                "SELECT set_config('epistemic_foundry.tenant_id', 'TENANT-A', true), "
                "set_config('epistemic_foundry.workspace_id', 'WORKSPACE-1', true)"
            )
            assert connection.execute(
                "SELECT count(*) FROM epistemic_foundry.revisioned_records"
            ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM epistemic_foundry.revisioned_records"
        ).fetchone()[0] == 0


def test_tenant_isolation_runtime_cannot_read_or_mutate_scope_authority(
    postgres_cluster,
) -> None:
    with psycopg.connect(postgres_cluster.runtime_dsns["A"], autocommit=True) as connection:
        forbidden_statements = [
            "SELECT * FROM epistemic_foundry.principal_scopes",
            "INSERT INTO epistemic_foundry.principal_scopes "
            "(principal_name, tenant_id, workspace_id) "
            "VALUES (session_user, 'TENANT-B', 'WORKSPACE-1')",
            "UPDATE epistemic_foundry.principal_scopes "
            "SET tenant_id = 'TENANT-B' WHERE principal_name = session_user",
            "DELETE FROM epistemic_foundry.principal_scopes "
            "WHERE principal_name = session_user",
            "CREATE TABLE epistemic_foundry.forbidden_runtime_table(id integer)",
            "INSERT INTO epistemic_foundry.revisioned_records "
            "(tenant_id, workspace_id, record_type, record_id, revision, value_json) "
            "VALUES ('TENANT-A', 'WORKSPACE-1', 'claim', 'direct-insert', 0, '{}'::json)",
            "UPDATE epistemic_foundry.revisioned_records SET revision = revision + 1",
            "DELETE FROM epistemic_foundry.revisioned_records",
            "TRUNCATE epistemic_foundry.revisioned_records",
        ]
        for statement in forbidden_statements:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(statement)


def test_tenant_isolation_bounded_functions_cannot_bypass_scope_binding(
    postgres_cluster,
) -> None:
    with psycopg.connect(postgres_cluster.runtime_dsns["B"], autocommit=True) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with connection.transaction():
                connection.execute(
                    "SELECT set_config('epistemic_foundry.tenant_id', 'TENANT-A', true), "
                    "set_config('epistemic_foundry.workspace_id', 'WORKSPACE-1', true)"
                )
                connection.execute(
                    "SELECT * FROM epistemic_foundry.create_revisioned_record("
                    "'TENANT-A', 'WORKSPACE-1', "
                    "'claim', 'forged-function', '{}'::json)"
                )

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "SELECT * FROM epistemic_foundry.create_revisioned_record("
                "'TENANT-B', 'WORKSPACE-1', "
                "'claim', 'missing-context', '{}'::json)"
            )

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with connection.transaction():
                connection.execute(
                    "SELECT set_config('epistemic_foundry.tenant_id', 'TENANT-A', true), "
                    "set_config('epistemic_foundry.workspace_id', 'WORKSPACE-1', true)"
                )
                connection.execute(
                    "SELECT epistemic_foundry.acquire_writer_lock("
                    "'TENANT-A', 'WORKSPACE-1')"
                )


def test_tenant_isolation_store_scope_survives_callback_guc_tampering(
    postgres_cluster,
) -> None:
    store = _open(postgres_cluster, "A", "TENANT-A", "WORKSPACE-1")
    try:
        def tamper_and_write(tx):
            tx._execute(
                "SELECT set_config("
                "'epistemic_foundry.workspace_id', 'WORKSPACE-2', true)"
            )
            tx.create_revisioned_record(
                record_type="claim",
                record_id="tampered-context",
                value={"must": "rollback"},
            )

        with pytest.raises(PostgresStateStoreError) as changed:
            store.transaction(tamper_and_write)
        assert changed.value.code == "BOUND_SCOPE_CONTEXT_CHANGED"
        assert store.read_revisioned_record("claim", "tampered-context") is None
    finally:
        store.close()

    workspace_two = _open(postgres_cluster, "A", "TENANT-A", "WORKSPACE-2")
    try:
        assert workspace_two.read_revisioned_record("claim", "tampered-context") is None
    finally:
        workspace_two.close()


def test_tenant_isolation_precommit_rejects_scope_tampering_without_store_operation(
    postgres_cluster,
) -> None:
    store = _open(postgres_cluster, "A", "TENANT-A", "WORKSPACE-1")
    try:
        def tamper_and_return(tx):
            tx._execute(
                "SELECT set_config("
                "'epistemic_foundry.tenant_id', 'TENANT-B', true)"
            )
            return "must-not-commit"

        with pytest.raises(PostgresStateStoreError) as changed:
            store.transaction(tamper_and_return)
        assert changed.value.code == "BOUND_SCOPE_CONTEXT_CHANGED"
        assert store.mode == POSTGRES_STORE_MODE.ACTIVE
    finally:
        store.close()


def test_tenant_isolation_unconfirmed_rollback_enters_safe_mode(postgres_cluster) -> None:
    store = _open(postgres_cluster, "A", "TENANT-A", "WORKSPACE-1")
    try:
        def close_connection(tx):
            tx._connection.close()
            return "outcome-is-not-observable"

        with pytest.raises(PostgresStateStoreError) as uncertain:
            store.transaction(close_connection)
        assert uncertain.value.code == "POSTGRES_TRANSACTION_OUTCOME_UNCERTAIN"
        assert store.mode == POSTGRES_STORE_MODE.SAFE_MODE
        with pytest.raises(PostgresStateStoreError) as denied:
            store.read_revisioned_record("claim", "after-uncertain-outcome")
        assert denied.value.code == "STORE_SAFE_MODE"
    finally:
        store.close()


def test_tenant_isolation_privilege_drift_is_rejected(postgres_cluster) -> None:
    principal = postgres_cluster.runtime_names["A"]
    with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
        owner.execute(
            "GRANT SELECT ON epistemic_foundry.principal_scopes TO "
            + psycopg.sql.Identifier(principal).as_string(owner)
        )
    try:
        denied = _open(postgres_cluster, "A", "TENANT-A", "WORKSPACE-1")
        try:
            assert denied.mode == POSTGRES_STORE_MODE.SAFE_MODE
            assert denied.safe_mode_reason["code"] == "POSTGRES_SCHEMA_ACL_MISMATCH"
        finally:
            denied.close()
    finally:
        with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
            owner.execute(
                "REVOKE SELECT ON epistemic_foundry.principal_scopes FROM "
                + psycopg.sql.Identifier(principal).as_string(owner)
            )


def test_tenant_isolation_column_privilege_drift_is_rejected(postgres_cluster) -> None:
    principal = postgres_cluster.runtime_names["A"]
    identifier = psycopg.sql.Identifier(principal)
    with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
        owner.execute(
            psycopg.sql.SQL(
                "GRANT UPDATE (value_json) ON "
                "epistemic_foundry.revisioned_records TO {}"
            ).format(identifier)
        )
    try:
        denied = _open(postgres_cluster, "A", "TENANT-A", "WORKSPACE-1")
        try:
            assert denied.mode == POSTGRES_STORE_MODE.SAFE_MODE
            assert denied.safe_mode_reason["code"] == "POSTGRES_SCHEMA_ACL_MISMATCH"
            assert denied.safe_mode_reason["details"]["columns"]
        finally:
            denied.close()
    finally:
        with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
            owner.execute(
                psycopg.sql.SQL(
                    "REVOKE UPDATE (value_json) ON "
                    "epistemic_foundry.revisioned_records FROM {}"
                ).format(identifier)
            )


def test_tenant_isolation_runtime_role_membership_is_rejected(postgres_cluster) -> None:
    principal = postgres_cluster.runtime_names["A"]
    membership_role = f"{principal}_membership"
    with psycopg.connect(postgres_cluster.admin_database_dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(membership_role))
        )
        admin.execute(
            sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(membership_role),
                sql.Identifier(principal),
            )
        )
    try:
        with pytest.raises(PostgresStateStoreError) as denied:
            _open(postgres_cluster, "A", "TENANT-A", "WORKSPACE-1")
        assert denied.value.code == "POSTGRES_PRINCIPAL_ROLE_MEMBERSHIP_DENIED"
    finally:
        with psycopg.connect(postgres_cluster.admin_database_dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL("REVOKE {} FROM {}").format(
                    sql.Identifier(membership_role),
                    sql.Identifier(principal),
                )
            )
            admin.execute(
                sql.SQL("DROP ROLE {}").format(sql.Identifier(membership_role))
            )


def test_tenant_isolation_force_rls_applies_to_non_superuser_table_owner(
    postgres_cluster,
) -> None:
    runtime = _open(postgres_cluster, "A", "TENANT-A", "WORKSPACE-1")
    try:
        runtime.create_revisioned_record(
            record_type="claim",
            record_id="owner-must-not-see",
            value={"visible": "runtime-only"},
        )
    finally:
        runtime.close()

    with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
        attributes = owner.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = session_user"
        ).fetchone()
        assert attributes == (False, False)
        assert owner.execute(
            "SELECT count(*) FROM epistemic_foundry.revisioned_records"
        ).fetchone()[0] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            owner.execute(
                """
                INSERT INTO epistemic_foundry.revisioned_records
                    (tenant_id, workspace_id, record_type, record_id, revision, value_json)
                VALUES ('TENANT-A', 'WORKSPACE-1', 'claim', 'owner-bypass', 0, '{}'::json)
                """
            )
