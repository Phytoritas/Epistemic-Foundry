from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "migrations" / "postgres" / "0001_team_store.sql"
POSTGRES_IMAGE = (
    "pgvector/pgvector@sha256:"
    "7d400e340efb42f4d8c9c12c6427adb253f726881a9985d2a471bf0eed824dff"
)
OWNER = "ef_d04_owner"
RUNTIME = "ef_d04_runtime"
SOURCE_DATABASE = "ef_d04_source"
STAGING_DATABASE = "ef_d04_restore_staging"
RECOVERED_DATABASE = "ef_d04_recovered"
CORRUPT_DATABASE = "ef_d04_corrupt_must_not_exist"


def _run(
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
    check: bool = True,
    timeout: int = 90,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        arguments,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=timeout,
    )


def _docker_exec(
    container: str,
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    command = ["docker", "exec"]
    if input_bytes is not None:
        command.append("-i")
    command.extend([container, *arguments])
    return _run(command, input_bytes=input_bytes, check=check)


def _psql(
    container: str,
    database: str,
    sql_text: str,
    *,
    user: str = "postgres",
) -> list[str]:
    result = _docker_exec(
        container,
        [
            "psql",
            "-X",
            "--no-psqlrc",
            "-v",
            "ON_ERROR_STOP=1",
            "-Atq",
            "-U",
            user,
            "-d",
            database,
        ],
        input_bytes=sql_text.encode("utf-8"),
    )
    return result.stdout.decode("utf-8").splitlines()


def _stored_identifier(value: str) -> str:
    return "u16be:" + value.encode("utf-16-be", errors="surrogatepass").hex()


def _database_exists(container: str, database: str) -> bool:
    rows = _psql(
        container,
        "postgres",
        "SELECT count(*) FROM pg_catalog.pg_database "
        f"WHERE datname = '{database}';\n",
    )
    return rows == ["1"]


def _validate_archive(container: str, archive: bytes) -> list[str]:
    result = _docker_exec(
        container,
        ["pg_restore", "--list"],
        input_bytes=archive,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("PostgreSQL backup archive failed validation")
    lines = result.stdout.decode("utf-8").splitlines()
    if not any("TABLE DATA epistemic_foundry revisioned_records" in line for line in lines):
        raise ValueError("PostgreSQL backup archive lacks revisioned-record data")
    if not any("FUNCTION epistemic_foundry" in line for line in lines):
        raise ValueError("PostgreSQL backup archive lacks canonical functions")
    return lines


def _catalog_snapshot(container: str, database: str) -> dict[str, object]:
    rows = _psql(
        container,
        database,
        """
        SELECT json_build_object(
            'functions', (
                SELECT count(*)
                  FROM pg_catalog.pg_proc AS p
                  JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'epistemic_foundry'
            ),
            'records', (
                SELECT count(*) FROM epistemic_foundry.revisioned_records
            ),
            'snapshot_records', (
                SELECT count(*) FROM epistemic_foundry.revisioned_records
                 WHERE record_id = 'u16be:0073006e0061007000730068006f0074'
            ),
            'post_backup_records', (
                SELECT count(*) FROM epistemic_foundry.revisioned_records
                 WHERE record_id = 'u16be:0070006f00730074002d006200610063006b00750070'
            ),
            'rls_enabled', (
                SELECT relrowsecurity AND relforcerowsecurity
                  FROM pg_catalog.pg_class AS c
                  JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'epistemic_foundry'
                   AND c.relname = 'revisioned_records'
            ),
            'schema_owner', (
                SELECT pg_catalog.pg_get_userbyid(nspowner)
                  FROM pg_catalog.pg_namespace
                 WHERE nspname = 'epistemic_foundry'
            )
        )::text;
        """,
    )
    assert len(rows) == 1
    return json.loads(rows[0])


def _validate_runtime_read(container: str, database: str) -> None:
    rows = _psql(
        container,
        database,
        """
        BEGIN;
        SELECT set_config('epistemic_foundry.tenant_id', 'TENANT-A', true);
        SELECT set_config('epistemic_foundry.workspace_id', 'WORKSPACE-1', true);
        SELECT epistemic_foundry.scope_is_authorized('TENANT-A', 'WORKSPACE-1');
        SELECT value_json::text
          FROM epistemic_foundry.revisioned_records
         WHERE tenant_id = 'TENANT-A'
           AND workspace_id = 'WORKSPACE-1'
           AND record_id = 'u16be:0073006e0061007000730068006f0074';
        ROLLBACK;
        """,
        user=RUNTIME,
    )
    assert rows[-2] == "t"
    assert json.loads(rows[-1]) == {"state": "SNAPSHOT"}


def _create_runtime_record(
    container: str,
    database: str,
    *,
    record_id: str,
    state: str,
) -> None:
    rows = _psql(
        container,
        database,
        f"""
        BEGIN;
        SELECT set_config('epistemic_foundry.tenant_id', 'TENANT-A', true);
        SELECT set_config('epistemic_foundry.workspace_id', 'WORKSPACE-1', true);
        SELECT created
          FROM epistemic_foundry.create_revisioned_record(
              'TENANT-A',
              'WORKSPACE-1',
              '{_stored_identifier("run")}',
              '{_stored_identifier(record_id)}',
              '{{"state":"{state}"}}'::json
          );
        COMMIT;
        """,
        user=RUNTIME,
    )
    assert rows[-1] == "t"


def test_backup_restore_test_postgres_staging_restore_preserves_corrupt_source(
    tmp_path: Path,
) -> None:
    assert shutil.which("docker") is not None, "Docker is required for the D04 gate"
    _run(["docker", "image", "inspect", POSTGRES_IMAGE])
    container = f"ef-d04-postgres-{uuid.uuid4().hex[:10]}"
    started = False
    try:
        _run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                container,
                "--env",
                "POSTGRES_PASSWORD=d04-local-fixture",
                POSTGRES_IMAGE,
            ]
        )
        started = True
        for _ in range(60):
            ready = _docker_exec(
                container,
                ["pg_isready", "-U", "postgres", "-d", "postgres"],
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.25)
        else:
            raise AssertionError("disposable D04 PostgreSQL did not become ready")

        _psql(
            container,
            "postgres",
            f"""
            CREATE ROLE {OWNER} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                NOINHERIT NOBYPASSRLS;
            CREATE ROLE {RUNTIME} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                NOINHERIT NOBYPASSRLS;
            CREATE DATABASE {SOURCE_DATABASE} OWNER {OWNER};
            """,
        )
        _psql(
            container,
            SOURCE_DATABASE,
            MIGRATION.read_text(encoding="utf-8"),
            user=OWNER,
        )
        _psql(
            container,
            SOURCE_DATABASE,
            f"""
            GRANT USAGE ON SCHEMA epistemic_foundry TO {RUNTIME};
            GRANT SELECT ON epistemic_foundry.store_metadata TO {RUNTIME};
            GRANT SELECT ON epistemic_foundry.revisioned_records TO {RUNTIME};
            GRANT EXECUTE ON FUNCTION epistemic_foundry.scope_is_authorized(text, text)
                TO {RUNTIME};
            GRANT EXECUTE ON FUNCTION epistemic_foundry.acquire_writer_lock(text, text)
                TO {RUNTIME};
            GRANT EXECUTE ON FUNCTION epistemic_foundry.create_revisioned_record(
                text, text, text, text, json
            ) TO {RUNTIME};
            GRANT EXECUTE ON FUNCTION epistemic_foundry.compare_and_swap_revision(
                text, text, text, text, bigint, json
            ) TO {RUNTIME};
            INSERT INTO epistemic_foundry.principal_scopes
                (principal_name, tenant_id, workspace_id)
            VALUES ('{RUNTIME}', 'TENANT-A', 'WORKSPACE-1');
            """,
            user=OWNER,
        )
        _create_runtime_record(
            container,
            SOURCE_DATABASE,
            record_id="snapshot",
            state="SNAPSHOT",
        )

        dump = _docker_exec(
            container,
            [
                "pg_dump",
                "--format=custom",
                "--serializable-deferrable",
                "-U",
                "postgres",
                "-d",
                SOURCE_DATABASE,
            ],
        ).stdout
        assert len(dump) > 1_000
        dump_hash = hashlib.sha256(dump).hexdigest()
        archive_path = tmp_path / "postgres.custom.dump"
        archive_path.write_bytes(dump)
        assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == dump_hash
        toc = _validate_archive(container, dump)
        assert len(toc) > 10

        _create_runtime_record(
            container,
            SOURCE_DATABASE,
            record_id="post-backup",
            state="MUST_NOT_RESTORE",
        )
        _psql(
            container,
            SOURCE_DATABASE,
            f"""
            DROP FUNCTION epistemic_foundry.compare_and_swap_revision(
                text, text, text, text, bigint, json
            );
            """,
            user=OWNER,
        )
        corrupt_source = _catalog_snapshot(container, SOURCE_DATABASE)
        assert corrupt_source["functions"] == 3
        assert corrupt_source["records"] == 2

        _psql(
            container,
            "postgres",
            f"CREATE DATABASE {STAGING_DATABASE} OWNER {OWNER};\n",
        )
        _docker_exec(
            container,
            [
                "pg_restore",
                "--exit-on-error",
                "--single-transaction",
                "-U",
                "postgres",
                "-d",
                STAGING_DATABASE,
            ],
            input_bytes=dump,
        )
        restored = _catalog_snapshot(container, STAGING_DATABASE)
        assert restored == {
            "functions": 4,
            "records": 1,
            "snapshot_records": 1,
            "post_backup_records": 0,
            "rls_enabled": True,
            "schema_owner": OWNER,
        }
        _validate_runtime_read(container, STAGING_DATABASE)

        _psql(
            container,
            "postgres",
            f"ALTER DATABASE {STAGING_DATABASE} RENAME TO {RECOVERED_DATABASE};\n",
        )
        assert not _database_exists(container, STAGING_DATABASE)
        assert _database_exists(container, RECOVERED_DATABASE)
        assert _catalog_snapshot(container, RECOVERED_DATABASE) == restored
        _validate_runtime_read(container, RECOVERED_DATABASE)
        assert _catalog_snapshot(container, SOURCE_DATABASE) == corrupt_source

        corrupt_archive = b"X" + dump[1:]
        try:
            _validate_archive(container, corrupt_archive)
        except ValueError:
            pass
        else:
            raise AssertionError("corrupt PostgreSQL archive passed pre-restore validation")
        assert not _database_exists(container, CORRUPT_DATABASE)
        assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == dump_hash
    finally:
        if started:
            _run(["docker", "stop", "--time", "5", container], check=False, timeout=30)
