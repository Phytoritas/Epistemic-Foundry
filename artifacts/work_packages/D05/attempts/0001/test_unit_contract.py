"""unit_and_contract_tests — the happy paths the store exists to serve.

Lineage records ancestry, islands specialise, the archive keeps niches, and a
checkpoint seals a resume point in one statement.  Every result here is the
real engine's, executed as the runtime principal wherever the runtime would do
it, so a privilege the runtime lacks shows up as a failure rather than as a
convenient superuser success.
"""

from __future__ import annotations

from pg_harness import RUNTIME_ROLE, PostgresContainer

SCHEMA = "epistemic_foundry_evolution"
SEALED = "sha256:" + "9" * 64


def checkpoint_call(
    checkpoint_id: str = "CP-1",
    run_id: str = "RUN-1",
    generation: int = 1,
    evaluator: str = "sha256:" + "a" * 64,
) -> str:
    return (
        f"SELECT {SCHEMA}.seal_checkpoint("
        f"'{checkpoint_id}', '{run_id}', {generation}, "
        f"'{SEALED}', '{SEALED}', '{SEALED}', '{SEALED}', '{SEALED}', "
        f"'{SEALED}', '{evaluator}', '{SEALED}') AS ok"
    )


def test_the_seeded_run_binds_one_evaluator(store: PostgresContainer) -> None:
    rows = store.query(f"SELECT * FROM {SCHEMA}.evolution_runs")

    assert len(rows) == 1
    assert rows[0]["evaluator_bundle_hash"] == "sha256:" + "a" * 64
    assert rows[0]["holdout_manifest_hash"] == "sha256:" + "b" * 64


def test_lineage_records_ancestry(store: PostgresContainer) -> None:
    rows = store.query(
        "SELECT candidate_id, parent_candidate_id, generation "
        f"FROM {SCHEMA}.candidate_lineage ORDER BY candidate_id"
    )

    assert [row["candidate_id"] for row in rows] == ["CAND-0", "CAND-1", "CAND-2"]
    assert rows[0]["parent_candidate_id"] is None
    assert rows[0]["generation"] == 0
    assert rows[1]["parent_candidate_id"] == "CAND-0"
    assert rows[2]["parent_candidate_id"] == "CAND-0"


def test_a_descendant_chain_resolves_to_its_root(store: PostgresContainer) -> None:
    store.sql(
        f"INSERT INTO {SCHEMA}.candidate_lineage "
        "(candidate_id, run_id, parent_candidate_id, generation, genome_hash, "
        "operator_id) VALUES "
        f"('CAND-3', 'RUN-1', 'CAND-1', 2, '{SEALED}', 'OP-MUTATE');",
        user=RUNTIME_ROLE,
    )
    rows = store.query(
        "WITH RECURSIVE ancestry AS ("
        "  SELECT candidate_id, parent_candidate_id, 0 AS depth "
        f"    FROM {SCHEMA}.candidate_lineage WHERE candidate_id = 'CAND-3'"
        "  UNION ALL"
        "  SELECT l.candidate_id, l.parent_candidate_id, ancestry.depth + 1 "
        f"    FROM {SCHEMA}.candidate_lineage l "
        "    JOIN ancestry ON l.candidate_id = ancestry.parent_candidate_id"
        ") SELECT candidate_id, depth FROM ancestry ORDER BY depth"
    )

    assert [row["candidate_id"] for row in rows] == ["CAND-3", "CAND-1", "CAND-0"]


def test_the_runtime_principal_can_append_lineage(
    store: PostgresContainer,
) -> None:
    store.sql(
        f"INSERT INTO {SCHEMA}.candidate_lineage "
        "(candidate_id, run_id, parent_candidate_id, generation, genome_hash, "
        "operator_id) VALUES "
        f"('CAND-9', 'RUN-1', 'CAND-2', 1, '{SEALED}', 'OP-CROSS');",
        user=RUNTIME_ROLE,
    )
    rows = store.query(f"SELECT count(*) AS total FROM {SCHEMA}.candidate_lineage")

    assert rows[0]["total"] == 4


def test_an_island_carries_its_specialization(store: PostgresContainer) -> None:
    rows = store.query(f"SELECT * FROM {SCHEMA}.island_states")

    assert len(rows) == 1
    assert rows[0]["specialization"] == "MECHANISM"


def test_the_archive_keeps_the_whole_niche_not_only_the_best(
    store: PostgresContainer,
) -> None:
    rows = store.query(
        "SELECT entry_id, combined_score, protection_reason "
        f"FROM {SCHEMA}.archive_entries WHERE evicted_at IS NULL "
        "ORDER BY entry_id"
    )

    assert [row["entry_id"] for row in rows] == ["AE-NULL", "AE-STRONG", "AE-WEAK"]
    assert min(row["combined_score"] for row in rows) < 0.1


def test_an_unprotected_entry_can_be_evicted_with_a_reason(
    store: PostgresContainer,
) -> None:
    store.query(
        f"SELECT {SCHEMA}.evict_archive_entry('AE-WEAK', 'superseded in niche') AS ok",
        user=RUNTIME_ROLE,
    )
    rows = store.query(
        "SELECT evicted_at, eviction_reason "
        f"FROM {SCHEMA}.archive_entries WHERE entry_id = 'AE-WEAK'"
    )

    assert rows[0]["evicted_at"] is not None
    assert rows[0]["eviction_reason"] == "superseded in niche"


def test_an_eviction_leaves_the_row_in_place(store: PostgresContainer) -> None:
    store.query(
        f"SELECT {SCHEMA}.evict_archive_entry('AE-WEAK', 'superseded') AS ok",
        user=RUNTIME_ROLE,
    )
    rows = store.query(f"SELECT count(*) AS total FROM {SCHEMA}.archive_entries")

    assert rows[0]["total"] == 3


def test_sealing_a_checkpoint_binds_all_seven_at_once(
    store: PostgresContainer,
) -> None:
    store.query(checkpoint_call(), user=RUNTIME_ROLE)
    rows = store.query(
        "SELECT population_hash, archive_hash, islands_hash, "
        "bandit_state_hash, budget_state_hash, testing_ledger_hash, "
        f"evaluator_bundle_hash FROM {SCHEMA}.evolution_checkpoints"
    )

    assert len(rows) == 1
    assert all(value is not None for value in rows[0].values())


def test_a_run_may_seal_successive_generations(
    store: PostgresContainer,
) -> None:
    store.query(checkpoint_call("CP-1", generation=1), user=RUNTIME_ROLE)
    store.query(checkpoint_call("CP-2", generation=2), user=RUNTIME_ROLE)
    rows = store.query(
        f"SELECT generation FROM {SCHEMA}.evolution_checkpoints ORDER BY generation"
    )

    assert [row["generation"] for row in rows] == [1, 2]


def test_the_checkpoint_binds_the_run_evaluator(
    store: PostgresContainer,
) -> None:
    store.query(checkpoint_call(), user=RUNTIME_ROLE)
    rows = store.query(
        "SELECT c.evaluator_bundle_hash AS checkpoint_evaluator, "
        "r.evaluator_bundle_hash AS run_evaluator "
        f"FROM {SCHEMA}.evolution_checkpoints c "
        f"JOIN {SCHEMA}.evolution_runs r ON r.run_id = c.run_id"
    )

    assert rows[0]["checkpoint_evaluator"] == rows[0]["run_evaluator"]


def test_a_resume_point_reads_back_every_binding(
    store: PostgresContainer,
) -> None:
    store.query(checkpoint_call("CP-RESUME", generation=7), user=RUNTIME_ROLE)
    rows = store.query(
        f"SELECT * FROM {SCHEMA}.evolution_checkpoints "
        "WHERE checkpoint_id = 'CP-RESUME'"
    )
    row = rows[0]

    for column in (
        "population_hash",
        "archive_hash",
        "islands_hash",
        "bandit_state_hash",
        "budget_state_hash",
        "testing_ledger_hash",
        "evaluator_bundle_hash",
        "checkpoint_hash",
    ):
        assert row[column].startswith("sha256:"), column
    assert row["generation"] == 7


def test_the_live_niche_index_serves_the_archive_query(
    store: PostgresContainer,
) -> None:
    rows = store.query(
        "SELECT indexname FROM pg_catalog.pg_indexes "
        f"WHERE schemaname = '{SCHEMA}' AND tablename = 'archive_entries' "
        "ORDER BY indexname"
    )

    assert "archive_entries_live_niche_idx" in [row["indexname"] for row in rows]
    assert "archive_entries_protected_idx" in [row["indexname"] for row in rows]
