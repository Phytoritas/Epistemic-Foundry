"""schema_and_type_check — the store's shape is what the migration declares.

Every assertion here is PostgreSQL's own catalog answer after the migration
ran: the tables that exist, the columns that are NOT NULL, the domains that
constrain content addresses, and the constraints and triggers that carry the
invariants.  A hand-read of the SQL would prove nothing about what the engine
actually built.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pg_harness import MIGRATION, PostgresContainer

SCHEMA = "epistemic_foundry_evolution"
#: The seven bindings a safe resume point requires (EF4-I61).
CHECKPOINT_BINDINGS = (
    "archive_hash",
    "bandit_state_hash",
    "budget_state_hash",
    "evaluator_bundle_hash",
    "islands_hash",
    "population_hash",
    "testing_ledger_hash",
)
EXPECTED_TABLES = (
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


def test_the_migration_creates_exactly_the_declared_tables(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema = '{SCHEMA}' ORDER BY table_name"
    )

    assert tuple(row["table_name"] for row in rows) == EXPECTED_TABLES


def test_the_store_metadata_declares_its_contract(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        f"SELECT key, value FROM {SCHEMA}.store_metadata ORDER BY key"
    )
    metadata = {row["key"]: row["value"] for row in rows}

    assert metadata["contract_id"] == ("epistemic-foundry-postgres-evolution-store/v1")
    assert metadata["schema_version"] == "1"
    assert metadata["runtime_delete_path"] == "none"
    assert metadata["checkpoint_atomicity"] == "seven-binding-not-null-immutable"
    assert metadata["protected_memory_policy"] == (
        "no-fitness-eviction-of-protected-entries"
    )


@pytest.mark.parametrize("column", CHECKPOINT_BINDINGS)
def test_every_checkpoint_binding_is_not_null(
    postgres: PostgresContainer, column: str
) -> None:
    rows = postgres.query(
        "SELECT is_nullable FROM information_schema.columns "
        f"WHERE table_schema = '{SCHEMA}' "
        f"AND table_name = 'evolution_checkpoints' AND column_name = '{column}'"
    )

    assert rows, column
    assert rows[0]["is_nullable"] == "NO", column


def test_the_checkpoint_carries_all_seven_bindings_and_no_fewer(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT column_name FROM information_schema.columns "
        f"WHERE table_schema = '{SCHEMA}' "
        "AND table_name = 'evolution_checkpoints' "
        "AND column_name LIKE '%_hash' ORDER BY column_name"
    )
    names = {row["column_name"] for row in rows}

    assert set(CHECKPOINT_BINDINGS) <= names
    assert "checkpoint_hash" in names
    assert len(names) == len(CHECKPOINT_BINDINGS) + 1


def test_a_content_address_domain_constrains_its_shape(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT domain_name FROM information_schema.domains "
        f"WHERE domain_schema = '{SCHEMA}' ORDER BY domain_name"
    )

    assert [row["domain_name"] for row in rows] == ["identifier", "sha256"]


def test_the_sha256_domain_rejects_a_non_digest(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.evolution_runs "
        "(run_id, evaluator_bundle_hash, holdout_manifest_hash) "
        "VALUES ('RUN-BAD', 'not-a-digest', 'sha256:" + "a" * 64 + "');"
    )

    assert "sha256" in message


def test_the_sha256_domain_rejects_uppercase_hex(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.evolution_runs "
        "(run_id, evaluator_bundle_hash, holdout_manifest_hash) "
        "VALUES ('RUN-BAD', 'sha256:" + "A" * 64 + "', 'sha256:" + "a" * 64 + "');"
    )

    assert "sha256" in message


def test_the_identifier_domain_rejects_an_empty_id(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.evolution_runs "
        "(run_id, evaluator_bundle_hash, holdout_manifest_hash) "
        "VALUES ('', 'sha256:" + "a" * 64 + "', 'sha256:" + "b" * 64 + "');"
    )

    assert "identifier" in message


def test_the_identity_columns_use_deterministic_collation(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT c.collname, c.collisdeterministic "
        "FROM pg_catalog.pg_type t "
        "JOIN pg_catalog.pg_collation c ON c.oid = t.typcollation "
        "JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace "
        f"WHERE n.nspname = '{SCHEMA}' AND t.typname = 'sha256'"
    )

    assert rows[0]["collname"] == "C"
    assert rows[0]["collisdeterministic"] is True


def test_the_invariant_guards_are_installed_as_triggers(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT tgname FROM pg_catalog.pg_trigger tg "
        "JOIN pg_catalog.pg_class c ON c.oid = tg.tgrelid "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = '{SCHEMA}' AND NOT tg.tgisinternal "
        "ORDER BY tgname"
    )
    names = [row["tgname"] for row in rows]

    assert names == [
        "archive_entries_guard_trigger",
        "candidate_lineage_append_only_trigger",
        "evolution_checkpoints_append_only_trigger",
        "evolution_checkpoints_evaluator_trigger",
        "evolution_runs_append_only_trigger",
    ]


def test_the_mutating_entry_points_are_security_definer(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT p.proname, p.prosecdef FROM pg_catalog.pg_proc p "
        "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
        f"WHERE n.nspname = '{SCHEMA}' AND p.prosecdef ORDER BY p.proname"
    )

    assert [row["proname"] for row in rows] == [
        "evict_archive_entry",
        "seal_checkpoint",
    ]


def test_the_archive_protects_exactly_the_declared_reasons(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        f"SELECT reason FROM {SCHEMA}.protection_reasons ORDER BY reason"
    )

    assert [row["reason"] for row in rows] == [
        "COUNTEREXAMPLE",
        "FAILED_REPLICATION",
        "MINORITY_LINEAGE",
        "NULL_RESULT",
        "UNSAFE_FAILURE",
    ]


def test_the_migration_is_one_transaction() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    statements = [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]

    assert statements[0] == "BEGIN;"
    assert statements[-1] == "COMMIT;"
    assert statements.count("BEGIN;") == 1
    assert statements.count("COMMIT;") == 1
    assert "ROLLBACK" not in text


def test_the_migration_grants_nothing_to_public() -> None:
    text = MIGRATION.read_text(encoding="utf-8")

    assert "REVOKE ALL ON SCHEMA" in text
    assert not re.search(r"GRANT\s+[^;]*TO\s+PUBLIC", text, re.IGNORECASE)


def test_the_migration_file_is_the_one_under_the_write_scope() -> None:
    assert MIGRATION == Path(MIGRATION).resolve()
    assert MIGRATION.parent.name == "v4_d05"
    assert MIGRATION.parent.parent.name == "migrations"
