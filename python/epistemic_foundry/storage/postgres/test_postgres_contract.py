from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Barrier, Event

import psycopg
import pytest

from epistemic_foundry.storage.postgres import (
    POSTGRES_STORE_MODE,
    PostgresStateStoreError,
    open_postgres_state_store,
)


def _store(cluster):
    return open_postgres_state_store(cluster.factory("A"), "TENANT-A", "WORKSPACE-1")


def _stored_identifier(value: str) -> str:
    return "u16be:" + value.encode("utf-16-be", errors="surrogatepass").hex()


def _incompressible_identifier(blocks: int = 160) -> str:
    return "".join(hashlib.sha256(str(index).encode()).hexdigest() for index in range(blocks))


def test_postgres_contract_create_read_commit_and_rollback(postgres_cluster) -> None:
    store = _store(postgres_cluster)
    try:
        assert store.mode == POSTGRES_STORE_MODE.ACTIVE, store.safe_mode_reason
        assert store.health()["backend"] == "postgresql"
        created = store.create_revisioned_record(
            record_type="session",
            record_id="committed",
            value={"state": "RUNNING"},
        )
        assert created == {
            "recordType": "session",
            "recordId": "committed",
            "revision": 0,
            "value": {"state": "RUNNING"},
        }

        store.transaction(
            lambda tx: tx.compare_and_swap_revision(
                record_type="session",
                record_id="committed",
                expected_revision=0,
                value={"state": "PAUSED"},
            )
        )
        assert store.read_revisioned_record("session", "committed")["revision"] == 1

        def rollback(tx):
            tx.create_revisioned_record(
                record_type="session", record_id="partial", value={"state": "NO"}
            )
            tx.compare_and_swap_revision(
                record_type="session",
                record_id="committed",
                expected_revision=1,
                value={"state": "MUST_ROLL_BACK"},
            )
            raise RuntimeError("synthetic rollback")

        with pytest.raises(RuntimeError, match="synthetic rollback"):
            store.transaction(rollback)
        assert store.read_revisioned_record("session", "partial") is None
        assert store.read_revisioned_record("session", "committed") == {
            "recordType": "session",
            "recordId": "committed",
            "revision": 1,
            "value": {"state": "PAUSED"},
        }
    finally:
        store.close()


def test_postgres_contract_duplicate_stale_missing_and_revision_exhaustion(
    postgres_cluster,
) -> None:
    store = _store(postgres_cluster)
    try:
        store.create_revisioned_record(
            record_type="candidate", record_id="one", value={"winner": None}
        )
        with pytest.raises(PostgresStateStoreError) as duplicate:
            store.create_revisioned_record(
                record_type="candidate", record_id="one", value={"winner": "duplicate"}
            )
        assert duplicate.value.code == "RECORD_ALREADY_EXISTS"

        updated = store.compare_and_swap_revision(
            record_type="candidate",
            record_id="one",
            expected_revision=0,
            value={"winner": "A"},
        )
        assert updated["ok"] is True
        assert updated["status"] == "UPDATED"
        assert updated["previousRevision"] == 0
        assert updated["currentRevision"] == 1

        stale = store.compare_and_swap_revision(
            record_type="candidate",
            record_id="one",
            expected_revision=0,
            value={"winner": "stale"},
        )
        assert stale["ok"] is False
        assert stale["code"] == "STALE_REVISION"
        assert stale["currentRevision"] == 1
        assert stale["record"]["value"] == {"winner": "A"}

        missing = store.compare_and_swap_revision(
            record_type="candidate",
            record_id="missing",
            expected_revision=0,
            value={"winner": "none"},
        )
        assert missing == {
            "ok": False,
            "status": "RECORD_NOT_FOUND",
            "code": "RECORD_NOT_FOUND",
            "expectedRevision": 0,
            "currentRevision": None,
            "record": None,
        }
    finally:
        store.close()

    with psycopg.connect(postgres_cluster.admin_database_dsn, autocommit=True) as admin:
        result = admin.execute(
            """
            UPDATE epistemic_foundry.revisioned_records
               SET revision = 9007199254740991
             WHERE tenant_id = 'TENANT-A'
               AND workspace_id = 'WORKSPACE-1'
               AND record_type = %s
               AND record_id = %s
            """,
            (_stored_identifier("candidate"), _stored_identifier("one")),
        )
        assert result.rowcount == 1
    store = _store(postgres_cluster)
    try:
        with pytest.raises(PostgresStateStoreError) as exhausted:
            store.compare_and_swap_revision(
                record_type="candidate",
                record_id="one",
                expected_revision=9_007_199_254_740_991,
                value={"winner": "must-not-write"},
            )
        assert exhausted.value.code == "REVISION_EXHAUSTED"
        assert store.read_revisioned_record("candidate", "one")["value"] == {"winner": "A"}
    finally:
        store.close()


def test_postgres_contract_rejects_invalid_values_nested_and_async_transactions(
    postgres_cluster,
) -> None:
    store = _store(postgres_cluster)
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    try:
        for index, value in enumerate(
            [
                float("nan"),
                float("inf"),
                -0.0,
                9_007_199_254_740_993,
                {"missing": object()},
                cyclic,
            ]
        ):
            with pytest.raises(PostgresStateStoreError) as invalid:
                store.create_revisioned_record(
                    record_type="invalid", record_id=str(index), value=value
                )
            assert invalid.value.code == "INVALID_RECORD_VALUE"

        with pytest.raises(PostgresStateStoreError) as nested:
            store.transaction(lambda tx: tx.transaction(lambda _: None))
        assert nested.value.code == "NESTED_TRANSACTION_DENIED"

        async def asynchronous(_):
            return "must not commit"

        with pytest.raises(PostgresStateStoreError) as async_error:
            store.transaction(asynchronous)
        assert async_error.value.code == "ASYNC_TRANSACTION_DENIED"
        assert store.mode == POSTGRES_STORE_MODE.SAFE_MODE
        with pytest.raises(PostgresStateStoreError) as denied:
            store.read_revisioned_record("invalid", "0")
        assert denied.value.code == "STORE_SAFE_MODE"
    finally:
        store.close()


def test_postgres_contract_rejects_custom_awaitable_without_running_user_hooks(
    postgres_cluster,
) -> None:
    store = _store(postgres_cluster)
    calls = {"await": 0, "close": 0}

    class HostileAwaitable:
        def __await__(self):
            calls["await"] += 1
            raise AssertionError("custom __await__ must not execute")

        @property
        def close(self):
            calls["close"] += 1
            raise AssertionError("custom close accessor must not execute")

    try:
        def return_hostile_awaitable(tx):
            tx.create_revisioned_record(
                record_type="async-boundary",
                record_id="must-roll-back",
                value={"committed": False},
            )
            return HostileAwaitable()

        with pytest.raises(PostgresStateStoreError) as denied:
            store.transaction(return_hostile_awaitable)
        assert denied.value.code == "ASYNC_TRANSACTION_DENIED"
        assert calls == {"await": 0, "close": 0}
        assert store.mode == POSTGRES_STORE_MODE.SAFE_MODE
    finally:
        store.close()

    observer = _store(postgres_cluster)
    try:
        assert observer.read_revisioned_record(
            "async-boundary", "must-roll-back"
        ) is None
    finally:
        observer.close()


def test_postgres_contract_round_trips_d01_json_edge_values(postgres_cluster) -> None:
    store = _store(postgres_cluster)
    intended = {
        "text": "control:\x01 nul:\x00 astral:😀 lone-high:\ud800",
        "key\x00": "lone-low:\udc00",
        "number": 9_007_199_254_740_992,
    }
    try:
        created = store.create_revisioned_record(
            record_type="strict-json",
            record_id="edge-values",
            value=intended,
        )
        assert created["value"] == intended
    finally:
        store.close()

    reopened = _store(postgres_cluster)
    try:
        assert reopened.read_revisioned_record("strict-json", "edge-values") == {
            "recordType": "strict-json",
            "recordId": "edge-values",
            "revision": 0,
            "value": intended,
        }
    finally:
        reopened.close()


def test_postgres_contract_round_trips_d01_identifier_edge_values(postgres_cluster) -> None:
    store = _store(postgres_cluster)
    record_type = "type\x00lone-high:\ud800"
    record_id = "id\x00astral:😀lone-low:\udc00"
    try:
        assert store.create_revisioned_record(
            record_type=record_type,
            record_id=record_id,
            value={"preserved": True},
        ) == {
            "recordType": record_type,
            "recordId": record_id,
            "revision": 0,
            "value": {"preserved": True},
        }
    finally:
        store.close()

    reopened = _store(postgres_cluster)
    try:
        assert reopened.read_revisioned_record(record_type, record_id) == {
            "recordType": record_type,
            "recordId": record_id,
            "revision": 0,
            "value": {"preserved": True},
        }
    finally:
        reopened.close()

    with psycopg.connect(postgres_cluster.admin_database_dsn, autocommit=True) as admin:
        stored = admin.execute(
            """
            SELECT record_type, record_id
              FROM epistemic_foundry.revisioned_records
             WHERE tenant_id = 'TENANT-A'
               AND workspace_id = 'WORKSPACE-1'
            """
        ).fetchone()
        assert stored == (
            _stored_identifier(record_type),
            _stored_identifier(record_id),
        )


def test_postgres_contract_round_trips_unbounded_incompressible_identity(
    postgres_cluster,
) -> None:
    store = _store(postgres_cluster)
    record_type = _incompressible_identifier()
    record_id = _incompressible_identifier(161)
    try:
        created = store.create_revisioned_record(
            record_type=record_type,
            record_id=record_id,
            value={"revision": 0},
        )
        assert created["recordType"] == record_type
        assert created["recordId"] == record_id
        updated = store.compare_and_swap_revision(
            record_type=record_type,
            record_id=record_id,
            expected_revision=0,
            value={"revision": 1},
        )
        assert updated["ok"] is True
        assert updated["record"]["value"] == {"revision": 1}
    finally:
        store.close()

    reopened = _store(postgres_cluster)
    try:
        record = reopened.read_revisioned_record(record_type, record_id)
        assert record["revision"] == 1
        assert record["value"] == {"revision": 1}
    finally:
        reopened.close()


def test_postgres_contract_duplicate_can_be_handled_inside_transaction(
    postgres_cluster,
) -> None:
    store = _store(postgres_cluster)
    try:
        store.create_revisioned_record(
            record_type="candidate",
            record_id="existing",
            value={"original": True},
        )

        def handle_duplicate_and_continue(tx):
            with pytest.raises(PostgresStateStoreError) as duplicate:
                tx.create_revisioned_record(
                    record_type="candidate",
                    record_id="existing",
                    value={"mustNotReplace": True},
                )
            assert duplicate.value.code == "RECORD_ALREADY_EXISTS"
            return tx.create_revisioned_record(
                record_type="candidate",
                record_id="after-duplicate",
                value={"committed": True},
            )

        continued = store.transaction(handle_duplicate_and_continue)
        assert continued["recordId"] == "after-duplicate"
        assert store.read_revisioned_record("candidate", "existing")["value"] == {
            "original": True
        }
        assert store.read_revisioned_record("candidate", "after-duplicate")["value"] == {
            "committed": True
        }
    finally:
        store.close()


def test_postgres_contract_integrity_check_reuses_explicit_transaction(
    postgres_cluster,
) -> None:
    store = _store(postgres_cluster)
    try:
        def check_then_write(tx):
            integrity = tx.check_integrity()
            assert integrity["ok"] is True
            assert integrity["mode"] == POSTGRES_STORE_MODE.ACTIVE
            return tx.create_revisioned_record(
                record_type="integrity-transaction",
                record_id="after-check",
                value={"committed": True},
            )

        created = store.transaction(check_then_write)
        assert created["recordId"] == "after-check"
        assert store.read_revisioned_record(
            "integrity-transaction", "after-check"
        )["value"] == {"committed": True}
    finally:
        store.close()


def test_postgres_contract_concurrent_create_has_one_exact_winner(postgres_cluster) -> None:
    barrier = Barrier(2)
    record_id = _incompressible_identifier()

    def create(value: str):
        store = _store(postgres_cluster)
        try:
            barrier.wait(timeout=10)
            try:
                record = store.create_revisioned_record(
                    record_type="concurrent-create",
                    record_id=record_id,
                    value={"winner": value},
                )
                return ("CREATED", record["value"]["winner"])
            except PostgresStateStoreError as error:
                return (error.code, None)
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(create, ["A", "B"]))
    assert sum(outcome[0] == "CREATED" for outcome in outcomes) == 1
    assert sum(outcome[0] == "RECORD_ALREADY_EXISTS" for outcome in outcomes) == 1


def test_postgres_contract_same_store_serializes_independent_thread_operations(
    postgres_cluster,
) -> None:
    store = _store(postgres_cluster)
    barrier = Barrier(2)

    def create(record_id: str):
        barrier.wait(timeout=10)
        return store.create_revisioned_record(
            record_type="same-store-thread",
            record_id=record_id,
            value={"recordId": record_id},
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            records = list(executor.map(create, ["A", "B"]))
        assert {record["recordId"] for record in records} == {"A", "B"}
    finally:
        store.close()


def test_postgres_contract_explicit_transaction_rejects_cross_thread_handle_use(
    postgres_cluster,
) -> None:
    store = _store(postgres_cluster)
    result: Queue[object] = Queue()

    def transaction_callback(tx):
        def cross_thread_use():
            try:
                tx.create_revisioned_record(
                    record_type="cross-thread",
                    record_id="must-not-write",
                    value={"denied": True},
                )
            except Exception as error:
                result.put(error)

        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(cross_thread_use).result(timeout=10)
        error = result.get(timeout=10)
        assert isinstance(error, PostgresStateStoreError)
        assert error.code == "CONCURRENT_TRANSACTION_ACCESS_DENIED"
        return tx.create_revisioned_record(
            record_type="cross-thread",
            record_id="owner-thread",
            value={"committed": True},
        )

    try:
        committed = store.transaction(transaction_callback)
        assert committed["recordId"] == "owner-thread"
        assert store.read_revisioned_record("cross-thread", "must-not-write") is None
    finally:
        store.close()


def test_postgres_contract_explicit_transactions_serialize_before_callback_entry(
    postgres_cluster,
) -> None:
    first = _store(postgres_cluster)
    second = _store(postgres_cluster)
    first_entered = Event()
    release_first = Event()
    second_entered = Event()

    def hold_first(tx):
        first_entered.set()
        assert release_first.wait(timeout=10)
        return tx.create_revisioned_record(
            record_type="writer-serialization",
            record_id="first",
            value={"order": 1},
        )

    def run_second(tx):
        second_entered.set()
        return tx.create_revisioned_record(
            record_type="writer-serialization",
            record_id="second",
            value={"order": 2},
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(first.transaction, hold_first)
            assert first_entered.wait(timeout=10)
            second_future = executor.submit(second.transaction, run_second)

            deadline = time.monotonic() + 10
            waiting_lock_observed = False
            with psycopg.connect(
                postgres_cluster.admin_database_dsn,
                autocommit=True,
            ) as admin:
                while time.monotonic() < deadline:
                    granted, waiting = admin.execute(
                        """
                        SELECT count(*) FILTER (WHERE lock_state.granted),
                               count(*) FILTER (WHERE NOT lock_state.granted)
                          FROM pg_catalog.pg_locks AS lock_state
                          JOIN pg_catalog.pg_class AS relation
                            ON relation.oid = lock_state.relation
                          JOIN pg_catalog.pg_namespace AS namespace
                            ON namespace.oid = relation.relnamespace
                         WHERE namespace.nspname = 'epistemic_foundry'
                           AND relation.relname = 'revisioned_records'
                           AND lock_state.mode = 'ShareRowExclusiveLock'
                        """
                    ).fetchone()
                    if granted >= 1 and waiting >= 1:
                        waiting_lock_observed = True
                        break
                    time.sleep(0.01)

            assert waiting_lock_observed is True
            assert second_entered.is_set() is False
            release_first.set()
            assert first_future.result(timeout=10)["recordId"] == "first"
            assert second_future.result(timeout=10)["recordId"] == "second"
            assert second_entered.is_set() is True
    finally:
        release_first.set()
        first.close()
        second.close()


@pytest.mark.parametrize("invalid_json", ["1e400", "-0", "-0.0"])
def test_postgres_contract_semantic_json_corruption_enters_safe_mode(
    postgres_cluster,
    invalid_json: str,
) -> None:
    store = _store(postgres_cluster)
    try:
        store.create_revisioned_record(
            record_type="candidate",
            record_id="corrupt-json",
            value={"valid": True},
        )
    finally:
        store.close()

    with psycopg.connect(postgres_cluster.admin_database_dsn, autocommit=True) as admin:
        result = admin.execute(
            """
            UPDATE epistemic_foundry.revisioned_records
               SET value_json = %s::json
             WHERE tenant_id = 'TENANT-A'
               AND workspace_id = 'WORKSPACE-1'
               AND record_type = %s
               AND record_id = %s
            """,
            (
                invalid_json,
                _stored_identifier("candidate"),
                _stored_identifier("corrupt-json"),
            ),
        )
        assert result.rowcount == 1

    corrupted = _store(postgres_cluster)
    try:
        assert corrupted.mode == POSTGRES_STORE_MODE.SAFE_MODE
        assert corrupted.safe_mode_reason["code"] == "POSTGRES_PERSISTED_JSON_INVALID"
        with pytest.raises(PostgresStateStoreError) as denied:
            corrupted.create_revisioned_record(
                record_type="candidate",
                record_id="must-not-write",
                value={"valid": False},
            )
        assert denied.value.code == "STORE_SAFE_MODE"
    finally:
        corrupted.close()


def test_postgres_contract_atomic_compare_and_swap_under_contention(postgres_cluster) -> None:
    seed = _store(postgres_cluster)
    try:
        seed.create_revisioned_record(
            record_type="candidate", record_id="race", value={"winner": None}
        )
    finally:
        seed.close()

    barrier = Barrier(2)

    def contend(winner: str):
        store = _store(postgres_cluster)
        try:
            barrier.wait(timeout=10)
            return store.compare_and_swap_revision(
                record_type="candidate",
                record_id="race",
                expected_revision=0,
                value={"winner": winner},
            )
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(contend, ["A", "B"]))
    assert sum(result["ok"] is True for result in results) == 1
    assert sum(result["code"] == "STALE_REVISION" for result in results if not result["ok"]) == 1


def test_postgres_contract_schema_drift_enters_safe_mode(postgres_cluster) -> None:
    store = _store(postgres_cluster)
    try:
        with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
            owner.execute(
                "ALTER TABLE epistemic_foundry.revisioned_records NO FORCE ROW LEVEL SECURITY"
            )
        result = store.check_integrity()
        assert result["ok"] is False
        assert result["mode"] == POSTGRES_STORE_MODE.SAFE_MODE
        assert store.safe_mode_reason["code"] == "POSTGRES_RLS_CONFIGURATION_MISMATCH"
        with pytest.raises(PostgresStateStoreError) as denied:
            store.create_revisioned_record(
                record_type="session", record_id="denied", value={"state": "NO"}
            )
        assert denied.value.code == "STORE_SAFE_MODE"
    finally:
        with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
            owner.execute(
                "ALTER TABLE epistemic_foundry.revisioned_records FORCE ROW LEVEL SECURITY"
            )
        store.close()


def test_postgres_contract_rejects_superuser_and_owner_runtime_credentials(
    postgres_cluster,
) -> None:
    with pytest.raises(PostgresStateStoreError) as superuser:
        open_postgres_state_store(
            lambda: psycopg.connect(postgres_cluster.admin_database_dsn),
            "TENANT-A",
            "WORKSPACE-1",
        )
    assert superuser.value.code == "PRIVILEGED_PRINCIPAL_DENIED"

    with pytest.raises(PostgresStateStoreError) as owner:
        open_postgres_state_store(
            lambda: psycopg.connect(postgres_cluster.owner_dsn),
            "TENANT-A",
            "WORKSPACE-1",
        )
    assert owner.value.code == "POSTGRES_PRINCIPAL_PRIVILEGE_MISMATCH"


def test_postgres_contract_schema_version_drift_enters_safe_mode(postgres_cluster) -> None:
    with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
        owner.execute(
            """
            UPDATE epistemic_foundry.store_metadata
               SET value = '999'
             WHERE key = 'schema_version'
            """
        )
    try:
        store = _store(postgres_cluster)
        try:
            assert store.mode == POSTGRES_STORE_MODE.SAFE_MODE
            assert store.safe_mode_reason == {
                "code": "POSTGRES_SCHEMA_VERSION_MISMATCH",
                "details": {"expected": "1", "actual": "999"},
            }
            with pytest.raises(PostgresStateStoreError) as denied:
                store.read_revisioned_record("candidate", "denied")
            assert denied.value.code == "STORE_SAFE_MODE"
        finally:
            store.close()
    finally:
        with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
            owner.execute(
                """
                UPDATE epistemic_foundry.store_metadata
                   SET value = '1'
                 WHERE key = 'schema_version'
                """
            )


def test_postgres_contract_extra_permissive_policy_is_fail_closed(postgres_cluster) -> None:
    with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
        owner.execute(
            """
            CREATE POLICY forbidden_allow_all
                ON epistemic_foundry.revisioned_records
                FOR SELECT
                USING (true)
            """
        )
    try:
        store = _store(postgres_cluster)
        try:
            assert store.mode == POSTGRES_STORE_MODE.SAFE_MODE
            assert store.safe_mode_reason["code"] == "POSTGRES_RLS_POLICY_MISMATCH"
        finally:
            store.close()
    finally:
        with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
            owner.execute(
                "DROP POLICY forbidden_allow_all "
                "ON epistemic_foundry.revisioned_records"
            )


def test_postgres_contract_public_schema_acl_is_fail_closed(postgres_cluster) -> None:
    with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
        owner.execute("GRANT USAGE ON SCHEMA epistemic_foundry TO PUBLIC")
    try:
        store = _store(postgres_cluster)
        try:
            assert store.mode == POSTGRES_STORE_MODE.SAFE_MODE
            assert store.safe_mode_reason["code"] == "POSTGRES_SCHEMA_ACL_MISMATCH"
        finally:
            store.close()
    finally:
        with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
            owner.execute("REVOKE USAGE ON SCHEMA epistemic_foundry FROM PUBLIC")


def test_postgres_contract_duplicate_persisted_identity_enters_safe_mode(
    postgres_cluster,
) -> None:
    store = _store(postgres_cluster)
    try:
        store.create_revisioned_record(
            record_type="candidate",
            record_id="duplicate-corruption",
            value={"copy": 1},
        )
    finally:
        store.close()

    with psycopg.connect(postgres_cluster.admin_database_dsn, autocommit=True) as admin:
        admin.execute(
            """
            INSERT INTO epistemic_foundry.revisioned_records
                (tenant_id, workspace_id, record_type, record_id, revision, value_json)
            VALUES ('TENANT-A', 'WORKSPACE-1', %s, %s, 0, '{"copy":2}'::json)
            """,
            (
                _stored_identifier("candidate"),
                _stored_identifier("duplicate-corruption"),
            ),
        )

    corrupted = _store(postgres_cluster)
    try:
        assert corrupted.mode == POSTGRES_STORE_MODE.SAFE_MODE
        assert corrupted.safe_mode_reason["code"] == "POSTGRES_PERSISTED_IDENTITY_DUPLICATE"
        with pytest.raises(PostgresStateStoreError) as denied:
            corrupted.read_revisioned_record("candidate", "duplicate-corruption")
        assert denied.value.code == "STORE_SAFE_MODE"
    finally:
        corrupted.close()


@pytest.mark.parametrize(
    ("mutate_sql", "restore_sql", "expected_code"),
    [
        (
            "ALTER TABLE epistemic_foundry.revisioned_records "
            "DROP CONSTRAINT revisioned_records_revision_range",
            "ALTER TABLE epistemic_foundry.revisioned_records "
            "ADD CONSTRAINT revisioned_records_revision_range "
            "CHECK (revision >= 0 AND revision <= 9007199254740991)",
            "POSTGRES_SCHEMA_CONSTRAINT_MISMATCH",
        ),
        (
            "CREATE OR REPLACE FUNCTION epistemic_foundry.scope_is_authorized("
            "requested_tenant text, requested_workspace text) RETURNS boolean "
            "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog "
            "AS 'SELECT true'",
            "CREATE OR REPLACE FUNCTION epistemic_foundry.scope_is_authorized("
            "requested_tenant text, requested_workspace text) RETURNS boolean "
            "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog "
            "AS 'SELECT EXISTS (SELECT 1 FROM "
            "epistemic_foundry.principal_scopes AS scope WHERE "
            "scope.principal_name = session_user::name AND "
            "scope.tenant_id = requested_tenant AND "
            "scope.workspace_id = requested_workspace)'",
            "POSTGRES_RLS_FUNCTION_MISMATCH",
        ),
        (
            "CREATE FUNCTION epistemic_foundry.forbidden_trigger() RETURNS trigger "
            "LANGUAGE plpgsql AS 'BEGIN RETURN NEW; END'; "
            "CREATE TRIGGER forbidden_trigger BEFORE INSERT ON "
            "epistemic_foundry.revisioned_records FOR EACH ROW "
            "EXECUTE FUNCTION epistemic_foundry.forbidden_trigger()",
            "DROP TRIGGER forbidden_trigger ON "
            "epistemic_foundry.revisioned_records; "
            "DROP FUNCTION epistemic_foundry.forbidden_trigger()",
            "POSTGRES_SCHEMA_TRIGGER_MISMATCH",
        ),
        (
            "CREATE INDEX forbidden_revision_index ON "
            "epistemic_foundry.revisioned_records(revision)",
            "DROP INDEX epistemic_foundry.forbidden_revision_index",
            "POSTGRES_SCHEMA_INDEX_MISMATCH",
        ),
        (
            "CREATE FUNCTION epistemic_foundry.forbidden_extra_function() "
            "RETURNS integer LANGUAGE sql AS 'SELECT 1'",
            "DROP FUNCTION epistemic_foundry.forbidden_extra_function()",
            "POSTGRES_RLS_FUNCTION_MISMATCH",
        ),
    ],
    ids=[
        "revision-check",
        "scope-function-body",
        "unexpected-trigger",
        "unexpected-index",
        "unexpected-function",
    ],
)
def test_postgres_contract_structural_drift_is_fail_closed(
    postgres_cluster,
    mutate_sql: str,
    restore_sql: str,
    expected_code: str,
) -> None:
    with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
        owner.execute(mutate_sql, prepare=False)
    try:
        store = _store(postgres_cluster)
        try:
            assert store.mode == POSTGRES_STORE_MODE.SAFE_MODE
            assert store.safe_mode_reason["code"] == expected_code
        finally:
            store.close()
    finally:
        with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
            owner.execute(restore_sql, prepare=False)


def test_postgres_contract_function_literal_whitespace_drift_is_fail_closed(
    postgres_cluster,
) -> None:
    signature = "epistemic_foundry.acquire_writer_lock(text,text)"
    with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
        original = owner.execute(
            "SELECT pg_get_functiondef(%s::regprocedure)",
            (signature,),
        ).fetchone()[0]
        needle = (
            "current_setting('epistemic_foundry.tenant_id', true),\n"
            "        ''"
        )
        mutated = original.replace(
            needle,
            "current_setting('epistemic_foundry.tenant_id', true),\n        ' '",
            1,
        )
        assert mutated != original
        owner.execute(mutated, prepare=False)
    try:
        store = _store(postgres_cluster)
        try:
            assert store.mode == POSTGRES_STORE_MODE.SAFE_MODE
            assert store.safe_mode_reason["code"] == "POSTGRES_RLS_FUNCTION_MISMATCH"
        finally:
            store.close()
    finally:
        with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
            owner.execute(original, prepare=False)


def test_postgres_contract_identity_collation_drift_is_fail_closed(
    postgres_cluster,
) -> None:
    with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
        owner.execute(
            "ALTER TABLE epistemic_foundry.revisioned_records "
            "ALTER COLUMN record_id TYPE text "
            "COLLATE pg_catalog.\"default\""
        )
    try:
        store = _store(postgres_cluster)
        try:
            assert store.mode == POSTGRES_STORE_MODE.SAFE_MODE
            assert store.safe_mode_reason["code"] == "POSTGRES_SCHEMA_COLUMN_MISMATCH"
        finally:
            store.close()
    finally:
        with psycopg.connect(postgres_cluster.owner_dsn, autocommit=True) as owner:
            owner.execute(
                "ALTER TABLE epistemic_foundry.revisioned_records "
                "ALTER COLUMN record_id TYPE text COLLATE pg_catalog.\"C\""
            )
