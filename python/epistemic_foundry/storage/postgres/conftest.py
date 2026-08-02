from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


@dataclass(frozen=True)
class PostgresTestCluster:
    admin_dsn: str
    admin_database_dsn: str
    database_name: str
    owner_name: str
    owner_dsn: str
    runtime_names: dict[str, str]
    runtime_dsns: dict[str, str]

    def factory(self, principal: str):
        dsn = self.runtime_dsns[principal]
        return lambda: psycopg.connect(dsn)


def _dsn(base_dsn: str, **overrides: str) -> str:
    values = conninfo_to_dict(base_dsn)
    values.update(overrides)
    return make_conninfo(**values)


@pytest.fixture(scope="session")
def postgres_cluster() -> PostgresTestCluster:
    admin_dsn = os.environ.get("EF_D02_POSTGRES_ADMIN_DSN")
    if not admin_dsn:
        pytest.fail("EF_D02_POSTGRES_ADMIN_DSN is required; mock-only D02 tests are forbidden")

    token = secrets.token_hex(5)
    database_name = f"ef_d02_{token}"
    owner_name = f"ef_d02_owner_{token}"
    role_a = f"ef_d02_a_{token}"
    role_b = f"ef_d02_b_{token}"
    owner_password = secrets.token_urlsafe(24)
    password_a = secrets.token_urlsafe(24)
    password_b = secrets.token_urlsafe(24)
    role_passwords = {role_a: password_a, role_b: password_b}

    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        for role, password in [(owner_name, owner_password), *role_passwords.items()]:
            admin.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}"
                ).format(sql.Identifier(role), sql.Literal(password))
            )
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(database_name),
                sql.Identifier(owner_name),
            )
        )

        owner_dsn = _dsn(
            admin_dsn,
            dbname=database_name,
            user=owner_name,
            password=owner_password,
        )
        admin_database_dsn = _dsn(admin_dsn, dbname=database_name)
        migration = (
            Path(__file__).resolve().parents[4] / "migrations" / "postgres" / "0001_team_store.sql"
        ).read_text(encoding="utf-8")
        with psycopg.connect(owner_dsn, autocommit=True) as owner:
            owner.execute(migration, prepare=False)
            for role in role_passwords:
                role_identifier = sql.Identifier(role)
                owner.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(database_name), role_identifier
                    )
                )
                owner.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA epistemic_foundry TO {}").format(
                        role_identifier
                    )
                )
                owner.execute(
                    sql.SQL(
                        "GRANT SELECT ON epistemic_foundry.store_metadata TO {}"
                    ).format(role_identifier)
                )
                owner.execute(
                    sql.SQL(
                        "GRANT SELECT "
                        "ON epistemic_foundry.revisioned_records TO {}"
                    ).format(role_identifier)
                )
                for signature in (
                    "epistemic_foundry.scope_is_authorized(text, text)",
                    "epistemic_foundry.acquire_writer_lock(text, text)",
                    "epistemic_foundry.create_revisioned_record("
                    "text, text, text, text, json)",
                    "epistemic_foundry.compare_and_swap_revision("
                    "text, text, text, text, bigint, json)",
                ):
                    owner.execute(
                        sql.SQL("GRANT EXECUTE ON FUNCTION {} TO {}").format(
                            sql.SQL(signature),
                            role_identifier,
                        )
                    )

            owner.execute(
                """
                INSERT INTO epistemic_foundry.principal_scopes
                    (principal_name, tenant_id, workspace_id)
                VALUES (%s, 'TENANT-A', 'WORKSPACE-1'),
                       (%s, 'TENANT-A', 'WORKSPACE-2'),
                       (%s, 'TENANT-B', 'WORKSPACE-1')
                """,
                (role_a, role_a, role_b),
            )

        runtime_dsns = {
            role: _dsn(
                admin_dsn,
                dbname=database_name,
                user=role,
                password=password,
            )
            for role, password in role_passwords.items()
        }
        cluster = PostgresTestCluster(
            admin_dsn=admin_dsn,
            admin_database_dsn=admin_database_dsn,
            database_name=database_name,
            owner_name=owner_name,
            owner_dsn=owner_dsn,
            runtime_names={"A": role_a, "B": role_b},
            runtime_dsns={"A": runtime_dsns[role_a], "B": runtime_dsns[role_b]},
        )
        yield cluster
    finally:
        try:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )
        finally:
            for role in (role_a, role_b, owner_name):
                try:
                    admin.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role))
                    )
                except Exception:
                    pass
            admin.close()


@pytest.fixture(autouse=True)
def clean_revisioned_records(postgres_cluster: PostgresTestCluster) -> None:
    with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
        owner.execute("TRUNCATE epistemic_foundry.revisioned_records")
