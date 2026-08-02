"""schema_and_type_check - the gate's shape is what the migration declares.

Every assertion here is PostgreSQL's own catalog answer after both migrations
ran: the objects the gate added, the domains it reused instead of redeclaring,
the journal rows it left behind, and - just as important - the D05 surface it
did not touch.  A hand-read of the SQL would prove none of that, and the one
property that holds without a server (the file is a single transaction) is read
through the same lint the named check runs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fixtures import (
    GATE_JOURNAL_ID,
    GATE_SCHEMA,
    MIGRATION,
    STORE_JOURNAL_ID,
    STORE_SCHEMA,
    journal_rows,
)
from lint_migration import GRANT_TO_PUBLIC, lint, statements
from pg_harness import PostgresContainer

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
#: The seven bindings D05 requires of a safe resume point (EF4-I61).  The gate
#: must leave every one of them NOT NULL.
CHECKPOINT_BINDINGS = (
    "archive_hash",
    "bandit_state_hash",
    "budget_state_hash",
    "evaluator_bundle_hash",
    "islands_hash",
    "population_hash",
    "testing_ledger_hash",
)
GATE_TABLES = ("checkpoint_attempts", "gate_metadata", "migration_journal")
GATE_VIEWS = (
    "checkpoint_recovery_points",
    "pending_recovery",
    "unreconciled_checkpoints",
)
STORE_TABLES = (
    "archive_entries",
    "candidate_lineage",
    "epistemic_niches",
    "evolution_checkpoints",
    "evolution_runs",
    "island_membership",
    "island_states",
    "protection_reasons",
    "store_metadata",
)


def test_the_gate_creates_exactly_the_declared_tables(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema = '{GATE_SCHEMA}' AND table_type = 'BASE TABLE' "
        "ORDER BY table_name"
    )

    assert tuple(row["table_name"] for row in rows) == GATE_TABLES


def test_the_gate_creates_exactly_the_declared_views(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema = '{GATE_SCHEMA}' AND table_type = 'VIEW' "
        "ORDER BY table_name"
    )

    assert tuple(row["table_name"] for row in rows) == GATE_VIEWS


def test_the_gate_metadata_declares_its_contract(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        f"SELECT key, value FROM {GATE_SCHEMA}.gate_metadata ORDER BY key"
    )
    metadata = {row["key"]: row["value"] for row in rows}

    assert metadata["contract_id"] == ("epistemic-foundry-postgres-recovery-gate/v1")
    assert metadata["applies_on_top_of"] == (
        "epistemic-foundry-postgres-evolution-store/v1"
    )
    assert metadata["reapply_policy"] == "refuse-before-any-ddl"
    assert metadata["crash_marker"] == "checkpoint_attempts-with-null-closed_at"
    assert metadata["count_reconciliation"] == (
        "expected-equals-persisted-lineage-at-generation"
    )


def test_the_gate_declares_no_domain_of_its_own(
    postgres: PostgresContainer,
) -> None:
    # A second sha256 domain would be a second shape to weaken, so the gate
    # reuses D05's rather than declaring one that only looks the same.
    rows = postgres.query(
        "SELECT domain_name FROM information_schema.domains "
        f"WHERE domain_schema = '{GATE_SCHEMA}'"
    )

    assert rows == []


def test_every_gate_hash_column_is_the_store_domain(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT table_name, column_name, domain_schema, domain_name "
        "FROM information_schema.columns "
        f"WHERE table_schema = '{GATE_SCHEMA}' AND column_name LIKE '%_hash' "
        "ORDER BY table_name, column_name"
    )

    assert rows
    for row in rows:
        assert row["domain_schema"] == STORE_SCHEMA, row
        assert row["domain_name"] == "sha256", row


def test_the_gate_identifiers_reuse_the_store_domain(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT column_name, domain_name FROM information_schema.columns "
        f"WHERE table_schema = '{GATE_SCHEMA}' "
        "AND table_name = 'checkpoint_attempts' "
        "AND domain_name IS NOT NULL ORDER BY column_name"
    )
    names = {row["column_name"]: row["domain_name"] for row in rows}

    assert names == {
        "attempt_id": "identifier",
        "checkpoint_id": "identifier",
        "run_id": "identifier",
    }


def test_the_store_still_declares_every_table_it_owned(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema = '{STORE_SCHEMA}' ORDER BY table_name"
    )

    assert tuple(row["table_name"] for row in rows) == STORE_TABLES


def test_the_gate_adds_one_trigger_to_the_store_and_removes_none(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT tgname FROM pg_catalog.pg_trigger tg "
        "JOIN pg_catalog.pg_class c ON c.oid = tg.tgrelid "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = '{STORE_SCHEMA}' AND NOT tg.tgisinternal "
        "ORDER BY tgname"
    )

    assert [row["tgname"] for row in rows] == [
        "archive_entries_guard_trigger",
        "candidate_lineage_append_only_trigger",
        "evolution_checkpoints_append_only_trigger",
        "evolution_checkpoints_evaluator_trigger",
        # The gate's own refusal sorts after D05's evaluator guard, so a D05
        # refusal is never masked by this one.
        "evolution_checkpoints_recovery_gate_trigger",
        "evolution_runs_append_only_trigger",
    ]


@pytest.mark.parametrize("column", CHECKPOINT_BINDINGS)
def test_every_checkpoint_binding_is_still_not_null(
    postgres: PostgresContainer, column: str
) -> None:
    rows = postgres.query(
        "SELECT is_nullable FROM information_schema.columns "
        f"WHERE table_schema = '{STORE_SCHEMA}' "
        f"AND table_name = 'evolution_checkpoints' AND column_name = '{column}'"
    )

    assert rows, column
    assert rows[0]["is_nullable"] == "NO", column


def test_the_store_keeps_its_own_checkpoint_constraints(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT conname FROM pg_catalog.pg_constraint con "
        "JOIN pg_catalog.pg_class c ON c.oid = con.conrelid "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = '{STORE_SCHEMA}' "
        "AND c.relname = 'evolution_checkpoints' ORDER BY conname"
    )
    names = [row["conname"] for row in rows]

    assert "evolution_checkpoints_generation_range" in names
    assert "evolution_checkpoints_one_per_generation" in names


def test_the_attempt_declares_which_columns_may_be_absent(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT column_name, is_nullable FROM information_schema.columns "
        f"WHERE table_schema = '{GATE_SCHEMA}' "
        "AND table_name = 'checkpoint_attempts' ORDER BY column_name"
    )
    nullable = {row["column_name"]: row["is_nullable"] for row in rows}

    # Everything an attempt is opened with is required; everything that only a
    # close can supply is absent until then, and closed_at is the crash marker.
    assert nullable == {
        "abandon_reason": "YES",
        "attempt_id": "NO",
        "checkpoint_id": "YES",
        "closed_at": "YES",
        "expected_candidate_count": "NO",
        "generation": "NO",
        "opened_at": "NO",
        "run_id": "NO",
    }


def test_only_one_attempt_per_generation_may_be_open(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT indexdef FROM pg_catalog.pg_indexes "
        f"WHERE schemaname = '{GATE_SCHEMA}' "
        "AND indexname = 'checkpoint_attempts_one_open_per_generation'"
    )

    assert rows
    assert "UNIQUE" in rows[0]["indexdef"]
    assert "closed_at IS NULL" in rows[0]["indexdef"]


def test_the_attempt_is_bound_to_the_store_by_foreign_key(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT con.conname, target.relname AS references_table, "
        "target_schema.nspname AS references_schema "
        "FROM pg_catalog.pg_constraint con "
        "JOIN pg_catalog.pg_class c ON c.oid = con.conrelid "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_catalog.pg_class target ON target.oid = con.confrelid "
        "JOIN pg_catalog.pg_namespace target_schema "
        "  ON target_schema.oid = target.relnamespace "
        f"WHERE n.nspname = '{GATE_SCHEMA}' "
        "AND c.relname = 'checkpoint_attempts' AND con.contype = 'f' "
        "ORDER BY con.conname"
    )
    targets = {(row["references_schema"], row["references_table"]) for row in rows}

    assert targets == {
        (STORE_SCHEMA, "evolution_runs"),
        (STORE_SCHEMA, "evolution_checkpoints"),
    }


def test_the_mutating_entry_points_are_security_definer(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT p.proname, p.prosecdef FROM pg_catalog.pg_proc p "
        "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
        f"WHERE n.nspname = '{GATE_SCHEMA}' ORDER BY p.proname"
    )
    definer = {row["proname"]: row["prosecdef"] for row in rows}

    assert definer == {
        "abandon_checkpoint_attempt": True,
        "checkpoint_attempts_guard": False,
        "checkpoint_requires_open_attempt": False,
        "open_checkpoint_attempt": True,
        "require_intact_migration_journal": False,
        "schema_digest": False,
        "seal_and_close_attempt": True,
        "verify_migration_journal": False,
    }


def test_the_journal_records_both_migrations_with_a_content_hash(
    postgres: PostgresContainer,
) -> None:
    rows = journal_rows(postgres)

    assert set(rows) == {STORE_JOURNAL_ID, GATE_JOURNAL_ID}
    assert rows[STORE_JOURNAL_ID]["digest_scope"] == STORE_SCHEMA
    assert rows[GATE_JOURNAL_ID]["digest_scope"] == GATE_SCHEMA
    for row in rows.values():
        assert DIGEST.match(row["content_hash"]), row


def test_the_journal_is_append_only_by_declaration(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT tgname FROM pg_catalog.pg_trigger tg "
        "JOIN pg_catalog.pg_class c ON c.oid = tg.tgrelid "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = '{GATE_SCHEMA}' AND NOT tg.tgisinternal "
        "ORDER BY tgname"
    )

    assert [row["tgname"] for row in rows] == [
        "checkpoint_attempts_guard_trigger",
        "migration_journal_append_only_trigger",
    ]


def test_the_migration_passes_its_own_lint() -> None:
    assert lint(MIGRATION) == []


def test_the_migration_is_one_transaction() -> None:
    body = statements(MIGRATION.read_text(encoding="utf-8"))

    assert body[0] == "BEGIN;"
    assert body[-1] == "COMMIT;"
    assert body.count("BEGIN;") == 1
    assert body.count("COMMIT;") == 1
    assert "ROLLBACK" not in MIGRATION.read_text(encoding="utf-8")


def test_the_migration_grants_nothing_to_public() -> None:
    text = MIGRATION.read_text(encoding="utf-8")

    assert "REVOKE ALL ON SCHEMA" in text
    assert not GRANT_TO_PUBLIC.search(text)


def test_the_migration_file_is_the_one_under_the_write_scope() -> None:
    assert MIGRATION == Path(MIGRATION).resolve()
    assert MIGRATION.parent.name == "v4_d06"
    assert MIGRATION.parent.parent.name == "migrations"
