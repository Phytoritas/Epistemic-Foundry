"""provenance_and_receipt_audit — every stored effect resolves to a receipt.

A transactional store's receipt is the row it wrote and the content address it
carries.  Every hash column is a checked domain rather than free text, every
eviction records who decided and why, and a crashed transaction leaves nothing
behind — which is exactly what makes the sealed checkpoint a safe resume point
rather than a hopeful one.
"""

from __future__ import annotations

import hashlib

from pg_harness import MIGRATION, RUNTIME_ROLE, PostgresContainer

SCHEMA = "epistemic_foundry_evolution"
SEALED = "sha256:" + "9" * 64
RUN_EVALUATOR = "sha256:" + "a" * 64


def test_the_migration_file_is_content_addressable() -> None:
    digest = hashlib.sha256(MIGRATION.read_bytes()).hexdigest()

    assert len(digest) == 64
    assert MIGRATION.read_text(encoding="utf-8").endswith("COMMIT;\n")


def test_every_hash_column_is_a_checked_domain(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT c.table_name, c.column_name, c.domain_name "
        "FROM information_schema.columns c "
        f"WHERE c.table_schema = '{SCHEMA}' AND c.column_name LIKE '%_hash' "
        "ORDER BY c.table_name, c.column_name"
    )

    assert rows
    for row in rows:
        assert row["domain_name"] == "sha256", row


def test_an_eviction_records_when_and_why(store: PostgresContainer) -> None:
    store.query(
        f"SELECT {SCHEMA}.evict_archive_entry('AE-WEAK', 'dominated in niche') AS ok",
        user=RUNTIME_ROLE,
    )
    rows = store.query(
        "SELECT evicted_at IS NOT NULL AS stamped, eviction_reason "
        f"FROM {SCHEMA}.archive_entries WHERE entry_id = 'AE-WEAK'"
    )

    assert rows[0]["stamped"] is True
    assert rows[0]["eviction_reason"] == "dominated in niche"


def test_a_failed_checkpoint_leaves_nothing_behind(
    store: PostgresContainer,
) -> None:
    store.refuses(
        f"SELECT {SCHEMA}.seal_checkpoint("
        f"'CP-FAIL', 'RUN-1', 1, '{SEALED}', '{SEALED}', '{SEALED}', "
        f"'{SEALED}', '{SEALED}', '{SEALED}', 'sha256:{'7' * 64}', "
        f"'{SEALED}');",
        user=RUNTIME_ROLE,
    )
    rows = store.query(f"SELECT count(*) AS total FROM {SCHEMA}.evolution_checkpoints")

    assert rows[0]["total"] == 0


def test_a_rolled_back_transaction_leaves_nothing_behind(
    store: PostgresContainer,
) -> None:
    store.sql(
        "BEGIN;\n"
        f"INSERT INTO {SCHEMA}.candidate_lineage "
        "(candidate_id, run_id, parent_candidate_id, generation, genome_hash, "
        f"operator_id) VALUES ('CAND-ROLLBACK', 'RUN-1', 'CAND-0', 1, "
        f"'{SEALED}', 'OP-MUTATE');\n"
        "ROLLBACK;",
        user=RUNTIME_ROLE,
    )
    rows = store.query(
        f"SELECT count(*) AS total FROM {SCHEMA}.candidate_lineage "
        "WHERE candidate_id = 'CAND-ROLLBACK'"
    )

    assert rows[0]["total"] == 0


def test_a_partially_written_checkpoint_cannot_survive_a_crash(
    store: PostgresContainer,
) -> None:
    # A caller that seals, then fails before committing, must leave no resume
    # point at all — a half-bound checkpoint would be worse than none.
    store.sql(
        "BEGIN;\n"
        f"SELECT {SCHEMA}.seal_checkpoint("
        f"'CP-CRASH', 'RUN-1', 5, '{SEALED}', '{SEALED}', '{SEALED}', "
        f"'{SEALED}', '{SEALED}', '{SEALED}', '{RUN_EVALUATOR}', "
        f"'{SEALED}');\n"
        "ROLLBACK;",
        user=RUNTIME_ROLE,
    )
    rows = store.query(f"SELECT count(*) AS total FROM {SCHEMA}.evolution_checkpoints")

    assert rows[0]["total"] == 0


def test_a_committed_checkpoint_survives_and_reads_back_whole(
    store: PostgresContainer,
) -> None:
    store.sql(
        "BEGIN;\n"
        f"SELECT {SCHEMA}.seal_checkpoint("
        f"'CP-COMMIT', 'RUN-1', 6, '{SEALED}', '{SEALED}', '{SEALED}', "
        f"'{SEALED}', '{SEALED}', '{SEALED}', '{RUN_EVALUATOR}', "
        f"'{SEALED}');\n"
        "COMMIT;",
        user=RUNTIME_ROLE,
    )
    rows = store.query(
        "SELECT checkpoint_id, generation, evaluator_bundle_hash "
        f"FROM {SCHEMA}.evolution_checkpoints"
    )

    assert len(rows) == 1
    assert rows[0]["checkpoint_id"] == "CP-COMMIT"
    assert rows[0]["evaluator_bundle_hash"] == RUN_EVALUATOR


def test_every_row_carries_its_own_timestamp(store: PostgresContainer) -> None:
    rows = postgres_timestamps(store)

    assert rows, "no timestamp columns were declared"
    for row in rows:
        assert row["is_nullable"] == "NO" or row["column_name"] == "evicted_at"


def postgres_timestamps(store: PostgresContainer) -> list[dict]:
    return store.query(
        "SELECT table_name, column_name, is_nullable "
        "FROM information_schema.columns "
        f"WHERE table_schema = '{SCHEMA}' "
        "AND data_type = 'timestamp with time zone' "
        "ORDER BY table_name, column_name"
    )


def test_the_runtime_principal_holds_no_privilege_it_was_not_granted(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT DISTINCT privilege_type "
        "FROM information_schema.role_table_grants "
        f"WHERE table_schema = '{SCHEMA}' AND grantee = '{RUNTIME_ROLE}' "
        "ORDER BY privilege_type"
    )

    assert [row["privilege_type"] for row in rows] == ["INSERT", "SELECT"]


def test_the_runtime_principal_is_not_a_superuser(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        "SELECT rolsuper, rolbypassrls FROM pg_catalog.pg_roles "
        f"WHERE rolname = '{RUNTIME_ROLE}'"
    )

    assert rows[0]["rolsuper"] is False
    assert rows[0]["rolbypassrls"] is False


def test_the_archive_keeps_evicted_rows_as_evidence(
    store: PostgresContainer,
) -> None:
    before = store.query(f"SELECT count(*) AS total FROM {SCHEMA}.archive_entries")[0][
        "total"
    ]
    store.query(
        f"SELECT {SCHEMA}.evict_archive_entry('AE-WEAK', 'dominated') AS ok",
        user=RUNTIME_ROLE,
    )
    after = store.query(f"SELECT count(*) AS total FROM {SCHEMA}.archive_entries")[0][
        "total"
    ]

    assert before == after == 3
