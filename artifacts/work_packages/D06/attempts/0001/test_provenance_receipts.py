"""provenance_and_receipt_audit - every effect here resolves to a receipt.

A migration's receipt is the journal row it left, and that row is only worth
something if it re-derives from the database rather than from the file that
claims to describe it.  A checkpoint's receipt is the attempt it closed: when
it opened, what it expected, when it closed and which resume point it produced.
An attempt that was given up keeps its reason.  Nothing here trusts a stored
value it cannot recompute.
"""

from __future__ import annotations

import hashlib
import re

from fixtures import (
    D05_MIGRATION,
    GATE_JOURNAL_ID,
    GATE_SCHEMA,
    MIGRATION,
    ROOT,
    STORE_JOURNAL_ID,
    STORE_SCHEMA,
    journal_rows,
    lineage_insert,
    open_attempt_call,
    pending,
    seal_and_close_call,
    verification,
)
from pg_harness import RUNTIME_ROLE, PostgresContainer

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
GRANTED_ENTRY_POINTS = {
    "abandon_checkpoint_attempt",
    "open_checkpoint_attempt",
    "require_intact_migration_journal",
    "schema_digest",
    "seal_and_close_attempt",
    "verify_migration_journal",
}


def test_the_migration_file_is_content_addressable() -> None:
    digest = hashlib.sha256(MIGRATION.read_bytes()).hexdigest()

    assert len(digest) == 64
    assert MIGRATION.read_text(encoding="utf-8").endswith("COMMIT;\n")


def test_the_two_migrations_are_distinct_deterministic_artifacts() -> None:
    gate = hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
    store = hashlib.sha256(D05_MIGRATION.read_bytes()).hexdigest()

    assert gate != store
    # Re-reading the same bytes must give the same address, which is the whole
    # basis for quoting either digest in a receipt.
    assert gate == hashlib.sha256(MIGRATION.read_bytes()).hexdigest()


def test_every_journalled_migration_id_names_a_file_on_disk(
    postgres: PostgresContainer,
) -> None:
    rows = journal_rows(postgres)

    for migration_id in rows:
        path = ROOT / "migrations" / f"{migration_id}.sql"
        assert path.is_file(), migration_id
    assert (ROOT / "migrations" / f"{GATE_JOURNAL_ID}.sql") == MIGRATION
    assert (ROOT / "migrations" / f"{STORE_JOURNAL_ID}.sql") == D05_MIGRATION


def test_every_journalled_hash_re_derives_from_the_live_catalog(
    postgres: PostgresContainer,
) -> None:
    rows = verification(postgres)

    assert len(rows) == 2
    for row in rows.values():
        assert DIGEST.match(row["observed_hash"]), row
        assert row["observed_hash"] == row["journalled_hash"], row
        assert row["matches"] is True, row


def test_the_digest_is_the_same_answer_every_time(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        f"SELECT {GATE_SCHEMA}.schema_digest('{STORE_SCHEMA}') AS first, "
        f"{GATE_SCHEMA}.schema_digest('{STORE_SCHEMA}') AS again"
    )

    assert rows[0]["first"] == rows[0]["again"]
    assert DIGEST.match(rows[0]["first"])


def test_the_digest_does_not_move_when_the_store_writes_rows(
    gate: PostgresContainer,
) -> None:
    # A journal that drifted every time a candidate was persisted would be
    # noise, so the digest reads structure and never contents.
    before = gate.query(
        f"SELECT {GATE_SCHEMA}.schema_digest('{STORE_SCHEMA}') AS digest"
    )[0]["digest"]
    gate.sql(lineage_insert("CAND-RECEIPT", generation=2), user=RUNTIME_ROLE)
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call(), user=RUNTIME_ROLE)
    after = gate.query(
        f"SELECT {GATE_SCHEMA}.schema_digest('{STORE_SCHEMA}') AS digest"
    )[0]["digest"]

    assert before == after


def test_both_journal_rows_were_written_in_one_moment(
    postgres: PostgresContainer,
) -> None:
    # One transaction, one statement timestamp: the journal records an apply,
    # not two independent claims that happen to sit in the same table.
    rows = postgres.query(
        "SELECT count(DISTINCT applied_at) AS moments, count(*) AS total "
        f"FROM {GATE_SCHEMA}.migration_journal"
    )

    assert rows[0]["total"] == 2
    assert rows[0]["moments"] == 1


def test_a_sealed_resume_point_carries_its_attempt_receipt(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call(), user=RUNTIME_ROLE)
    rows = gate.query(f"SELECT * FROM {GATE_SCHEMA}.checkpoint_recovery_points")
    receipt = rows[0]

    assert receipt["attempt_id"] == "AT-1"
    assert receipt["opened_at"] is not None
    assert receipt["closed_at"] is not None
    assert receipt["expected_candidate_count"] == 2
    assert DIGEST.match(receipt["checkpoint_hash"])
    assert DIGEST.match(receipt["evaluator_bundle_hash"])


def test_an_abandoned_attempt_records_when_and_why(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(
        f"SELECT {GATE_SCHEMA}.abandon_checkpoint_attempt("
        "'AT-1', 'the run was cancelled before the population settled') AS ok",
        user=RUNTIME_ROLE,
    )
    rows = gate.query(
        "SELECT closed_at IS NOT NULL AS stamped, abandon_reason "
        f"FROM {GATE_SCHEMA}.checkpoint_attempts WHERE attempt_id = 'AT-1'"
    )

    assert rows[0]["stamped"] is True
    assert rows[0]["abandon_reason"] == (
        "the run was cancelled before the population settled"
    )


def test_a_refused_seal_produces_no_receipt_at_all(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(expected=9), user=RUNTIME_ROLE)
    gate.refuses(seal_and_close_call(), user=RUNTIME_ROLE)
    points = gate.query(
        f"SELECT count(*) AS total FROM {GATE_SCHEMA}.checkpoint_recovery_points"
    )

    assert points[0]["total"] == 0
    # The attempt stays open, so the failure is still visible to recovery.
    assert len(pending(gate)) == 1


def test_every_gate_hash_column_is_a_checked_domain(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT table_name, column_name, domain_name "
        "FROM information_schema.columns "
        f"WHERE table_schema = '{GATE_SCHEMA}' AND column_name LIKE '%_hash' "
        "ORDER BY table_name, column_name"
    )

    assert rows
    for row in rows:
        assert row["domain_name"] == "sha256", row


def test_every_gate_timestamp_is_recorded_or_deliberately_absent(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT table_name, column_name, is_nullable "
        "FROM information_schema.columns "
        f"WHERE table_schema = '{GATE_SCHEMA}' "
        "AND data_type = 'timestamp with time zone' "
        "ORDER BY table_name, column_name"
    )
    nullable = {
        (row["table_name"], row["column_name"]): row["is_nullable"] for row in rows
    }

    assert nullable[("migration_journal", "applied_at")] == "NO"
    assert nullable[("checkpoint_attempts", "opened_at")] == "NO"
    # closed_at is the crash marker: its absence is the state, not an omission.
    assert nullable[("checkpoint_attempts", "closed_at")] == "YES"


def test_the_runtime_principal_gained_no_write_path_into_the_gate(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT DISTINCT privilege_type "
        "FROM information_schema.role_table_grants "
        f"WHERE table_schema = '{GATE_SCHEMA}' "
        f"AND grantee = '{RUNTIME_ROLE}' ORDER BY privilege_type"
    )

    assert [row["privilege_type"] for row in rows] == ["SELECT"]


def test_the_runtime_principal_holds_only_the_declared_entry_points(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT DISTINCT routine_name "
        "FROM information_schema.routine_privileges "
        f"WHERE specific_schema = '{GATE_SCHEMA}' "
        f"AND grantee = '{RUNTIME_ROLE}' ORDER BY routine_name"
    )

    assert {row["routine_name"] for row in rows} == GRANTED_ENTRY_POINTS
