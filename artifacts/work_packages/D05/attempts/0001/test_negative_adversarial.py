"""negative_and_adversarial_tests — the invariants hold against a hostile writer.

Every attack here is executed as the runtime principal against a real server,
so what is proved is that the database refuses it — not that some caller
declines to try.  Protected memory is attacked from the fitness side, the
direct-UPDATE side and the DELETE side; the checkpoint is attacked by omitting
bindings, swapping the evaluator, and rewriting a sealed row; lineage is
attacked by rewriting history and by inventing ancestry.
"""

from __future__ import annotations

import pytest

from pg_harness import RUNTIME_ROLE, PostgresContainer

SCHEMA = "epistemic_foundry_evolution"
SEALED = "sha256:" + "9" * 64
RUN_EVALUATOR = "sha256:" + "a" * 64


def seal(
    store: PostgresContainer,
    checkpoint_id: str,
    *,
    generation: int = 1,
    evaluator: str = RUN_EVALUATOR,
    run_id: str = "RUN-1",
) -> str:
    return store.refuses(
        f"SELECT {SCHEMA}.seal_checkpoint("
        f"'{checkpoint_id}', '{run_id}', {generation}, "
        f"'{SEALED}', '{SEALED}', '{SEALED}', '{SEALED}', '{SEALED}', "
        f"'{SEALED}', '{evaluator}', '{SEALED}');",
        user=RUNTIME_ROLE,
    )


# --- EF4-I49: protected negative memory ------------------------------------


def test_a_protected_entry_cannot_be_evicted_for_low_fitness(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"SELECT {SCHEMA}.evict_archive_entry('AE-NULL', 'low fitness');",
        user=RUNTIME_ROLE,
    )

    assert "protected archive entry cannot be evicted" in message
    assert "NULL_RESULT" in message


@pytest.mark.parametrize(
    "reason",
    [
        "COUNTEREXAMPLE",
        "FAILED_REPLICATION",
        "MINORITY_LINEAGE",
        "UNSAFE_FAILURE",
    ],
)
def test_every_protection_reason_blocks_eviction(
    store: PostgresContainer, reason: str
) -> None:
    store.sql(
        f"INSERT INTO {SCHEMA}.archive_entries "
        "(entry_id, run_id, candidate_id, niche_id, fitness_vector_hash, "
        "combined_score, protection_reason) VALUES "
        f"('AE-{reason}', 'RUN-1', 'CAND-2', 'NICHE-1', '{SEALED}', 0.0, "
        f"'{reason}');",
        user=RUNTIME_ROLE,
    )
    message = store.refuses(
        f"SELECT {SCHEMA}.evict_archive_entry('AE-{reason}', 'pruning');",
        user=RUNTIME_ROLE,
    )

    assert reason in message


def test_a_protected_entry_cannot_be_evicted_by_direct_update(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"UPDATE {SCHEMA}.archive_entries "
        "SET evicted_at = now(), eviction_reason = 'pruning' "
        "WHERE entry_id = 'AE-NULL';",
        user=RUNTIME_ROLE,
    )

    assert "permission denied" in message or "protected" in message


def test_the_runtime_principal_has_no_delete_privilege(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"DELETE FROM {SCHEMA}.archive_entries WHERE entry_id = 'AE-NULL';",
        user=RUNTIME_ROLE,
    )

    assert "permission denied" in message


def test_even_a_superuser_delete_hits_the_append_only_guard(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"DELETE FROM {SCHEMA}.archive_entries WHERE entry_id = 'AE-NULL';"
    )

    assert "append-only" in message


def test_protection_cannot_be_stripped_to_enable_eviction(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"UPDATE {SCHEMA}.archive_entries SET protection_reason = NULL "
        "WHERE entry_id = 'AE-NULL';"
    )

    assert "immutable" in message


def test_an_unknown_protection_reason_is_refused(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.archive_entries "
        "(entry_id, run_id, candidate_id, niche_id, fitness_vector_hash, "
        "combined_score, protection_reason) VALUES "
        f"('AE-BAD', 'RUN-1', 'CAND-1', 'NICHE-1', '{SEALED}', 0.5, "
        "'INCONVENIENT');",
        user=RUNTIME_ROLE,
    )

    assert "protection_reason" in message or "foreign key" in message


def test_an_eviction_without_a_reason_is_refused(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"SELECT {SCHEMA}.evict_archive_entry('AE-WEAK', '');",
        user=RUNTIME_ROLE,
    )

    assert "eviction requires a reason" in message


def test_evicting_a_missing_entry_is_refused(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"SELECT {SCHEMA}.evict_archive_entry('AE-GHOST', 'pruning');",
        user=RUNTIME_ROLE,
    )

    assert "archive entry does not exist" in message


def test_a_double_eviction_is_refused(store: PostgresContainer) -> None:
    store.query(
        f"SELECT {SCHEMA}.evict_archive_entry('AE-WEAK', 'superseded') AS ok",
        user=RUNTIME_ROLE,
    )
    message = store.refuses(
        f"SELECT {SCHEMA}.evict_archive_entry('AE-WEAK', 'again');",
        user=RUNTIME_ROLE,
    )

    assert "already evicted" in message


def test_an_eviction_cannot_be_reversed(store: PostgresContainer) -> None:
    store.query(
        f"SELECT {SCHEMA}.evict_archive_entry('AE-WEAK', 'superseded') AS ok",
        user=RUNTIME_ROLE,
    )
    message = store.refuses(
        f"UPDATE {SCHEMA}.archive_entries SET evicted_at = NULL, "
        "eviction_reason = NULL WHERE entry_id = 'AE-WEAK';"
    )

    assert "cannot be reversed" in message or "immutable" in message


def test_an_entry_cannot_be_born_protected_and_evicted(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.archive_entries "
        "(entry_id, run_id, candidate_id, niche_id, fitness_vector_hash, "
        "combined_score, protection_reason, evicted_at, eviction_reason) "
        f"VALUES ('AE-SNEAK', 'RUN-1', 'CAND-1', 'NICHE-1', '{SEALED}', 0.0, "
        "'NULL_RESULT', now(), 'pruned at birth');",
        user=RUNTIME_ROLE,
    )

    assert "archive_entries_protected_never_evicted" in message


def test_an_eviction_timestamp_without_a_reason_is_refused(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.archive_entries "
        "(entry_id, run_id, candidate_id, niche_id, fitness_vector_hash, "
        "combined_score, evicted_at) VALUES "
        f"('AE-SILENT', 'RUN-1', 'CAND-1', 'NICHE-1', '{SEALED}', 0.0, now());",
        user=RUNTIME_ROLE,
    )

    assert "archive_entries_eviction_is_reasoned" in message


# --- EF4-I61: atomic checkpoints -------------------------------------------


CHECKPOINT_BINDINGS = (
    "population_hash",
    "archive_hash",
    "islands_hash",
    "bandit_state_hash",
    "budget_state_hash",
    "testing_ledger_hash",
    "evaluator_bundle_hash",
)


def insert_checkpoint_without(store: PostgresContainer, column: str) -> str:
    kept = [name for name in CHECKPOINT_BINDINGS if name != column]
    values = ", ".join(
        f"'{RUN_EVALUATOR}'" if name == "evaluator_bundle_hash" else f"'{SEALED}'"
        for name in kept
    )
    return store.refuses(
        f"INSERT INTO {SCHEMA}.evolution_checkpoints "
        "(checkpoint_id, run_id, generation, checkpoint_hash, "
        + ", ".join(kept)
        + ") VALUES ('CP-PARTIAL', 'RUN-1', 1, "
        + f"'{SEALED}', {values});",
        user=RUNTIME_ROLE,
    )


@pytest.mark.parametrize(
    "column", [name for name in CHECKPOINT_BINDINGS if name != "evaluator_bundle_hash"]
)
def test_a_checkpoint_missing_any_binding_is_refused(
    store: PostgresContainer, column: str
) -> None:
    message = insert_checkpoint_without(store, column)

    assert "null value" in message.lower()
    assert column in message


def test_a_checkpoint_missing_its_evaluator_is_refused_by_the_guard(
    store: PostgresContainer,
) -> None:
    # The evaluator guard fires before the NOT NULL check and names the
    # semantic failure rather than the column, which is the better refusal:
    # an absent evaluator is a resume point bound to no evaluator at all.
    message = insert_checkpoint_without(store, "evaluator_bundle_hash")

    assert "checkpoint evaluator does not match the run evaluator" in message


def test_a_checkpoint_cannot_swap_the_run_evaluator(
    store: PostgresContainer,
) -> None:
    message = seal(store, "CP-SWAP", evaluator="sha256:" + "7" * 64)

    assert "checkpoint evaluator does not match the run evaluator" in message


def test_a_sealed_checkpoint_cannot_be_rewritten(
    store: PostgresContainer,
) -> None:
    store.query(
        f"SELECT {SCHEMA}.seal_checkpoint("
        f"'CP-1', 'RUN-1', 1, '{SEALED}', '{SEALED}', '{SEALED}', '{SEALED}', "
        f"'{SEALED}', '{SEALED}', '{RUN_EVALUATOR}', '{SEALED}') AS ok",
        user=RUNTIME_ROLE,
    )
    message = store.refuses(
        f"UPDATE {SCHEMA}.evolution_checkpoints "
        f"SET population_hash = '{'sha256:' + '8' * 64}' "
        "WHERE checkpoint_id = 'CP-1';"
    )

    assert "append-only" in message


def test_a_generation_cannot_carry_two_checkpoints(
    store: PostgresContainer,
) -> None:
    store.query(
        f"SELECT {SCHEMA}.seal_checkpoint("
        f"'CP-1', 'RUN-1', 3, '{SEALED}', '{SEALED}', '{SEALED}', '{SEALED}', "
        f"'{SEALED}', '{SEALED}', '{RUN_EVALUATOR}', '{SEALED}') AS ok",
        user=RUNTIME_ROLE,
    )
    message = seal(store, "CP-2", generation=3)

    assert "evolution_checkpoints_one_per_generation" in message


def test_a_checkpoint_for_an_unknown_run_is_refused(
    store: PostgresContainer,
) -> None:
    message = seal(store, "CP-GHOST", run_id="RUN-GHOST")

    assert "does not match the run evaluator" in message or "foreign key" in message


def test_a_negative_generation_is_refused(store: PostgresContainer) -> None:
    message = seal(store, "CP-NEG", generation=-1)

    assert "evolution_checkpoints_generation_range" in message


# --- lineage and islands ----------------------------------------------------


def test_lineage_cannot_be_rewritten(store: PostgresContainer) -> None:
    message = store.refuses(
        f"UPDATE {SCHEMA}.candidate_lineage "
        "SET parent_candidate_id = 'CAND-2' WHERE candidate_id = 'CAND-1';"
    )

    assert "append-only" in message


def test_lineage_cannot_be_deleted(store: PostgresContainer) -> None:
    message = store.refuses(
        f"DELETE FROM {SCHEMA}.candidate_lineage WHERE candidate_id = 'CAND-2';"
    )

    assert "append-only" in message


def test_a_candidate_cannot_invent_an_absent_parent(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.candidate_lineage "
        "(candidate_id, run_id, parent_candidate_id, generation, genome_hash, "
        f"operator_id) VALUES ('CAND-X', 'RUN-1', 'CAND-GHOST', 1, "
        f"'{SEALED}', 'OP-MUTATE');",
        user=RUNTIME_ROLE,
    )

    assert "foreign key" in message or "candidate_lineage" in message


def test_a_candidate_cannot_be_its_own_parent(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.candidate_lineage "
        "(candidate_id, run_id, parent_candidate_id, generation, genome_hash, "
        f"operator_id) VALUES ('CAND-LOOP', 'RUN-1', 'CAND-LOOP', 1, "
        f"'{SEALED}', 'OP-MUTATE');",
        user=RUNTIME_ROLE,
    )

    assert "candidate_lineage_not_its_own_parent" in message or (
        "foreign key" in message
    )


def test_a_root_candidate_must_be_generation_zero(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.candidate_lineage "
        "(candidate_id, run_id, parent_candidate_id, generation, genome_hash, "
        f"operator_id) VALUES ('CAND-ROOTLESS', 'RUN-1', NULL, 4, "
        f"'{SEALED}', 'OP-SEED');",
        user=RUNTIME_ROLE,
    )

    assert "candidate_lineage_root_is_generation_zero" in message


def test_a_descendant_may_not_claim_generation_zero(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.candidate_lineage "
        "(candidate_id, run_id, parent_candidate_id, generation, genome_hash, "
        f"operator_id) VALUES ('CAND-FLAT', 'RUN-1', 'CAND-0', 0, "
        f"'{SEALED}', 'OP-MUTATE');",
        user=RUNTIME_ROLE,
    )

    assert "candidate_lineage_root_is_generation_zero" in message


def test_a_candidate_cannot_join_two_islands(store: PostgresContainer) -> None:
    store.sql(
        f"INSERT INTO {SCHEMA}.island_states "
        f"(island_id, run_id, specialization, state_hash) VALUES "
        f"('ISL-2', 'RUN-1', 'SCOPE', '{SEALED}');",
        user=RUNTIME_ROLE,
    )
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.island_membership (island_id, candidate_id) "
        "VALUES ('ISL-2', 'CAND-1');",
        user=RUNTIME_ROLE,
    )

    assert "island_membership_one_island_per_candidate" in message


def test_an_island_cannot_hold_an_unknown_candidate(
    store: PostgresContainer,
) -> None:
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.island_membership (island_id, candidate_id) "
        "VALUES ('ISL-1', 'CAND-GHOST');",
        user=RUNTIME_ROLE,
    )

    assert "foreign key" in message


def test_a_run_cannot_be_rewritten(store: PostgresContainer) -> None:
    message = store.refuses(
        f"UPDATE {SCHEMA}.evolution_runs "
        f"SET evaluator_bundle_hash = '{SEALED}' WHERE run_id = 'RUN-1';"
    )

    assert "append-only" in message


def test_a_non_finite_score_is_refused(store: PostgresContainer) -> None:
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.archive_entries "
        "(entry_id, run_id, candidate_id, niche_id, fitness_vector_hash, "
        "combined_score) VALUES "
        f"('AE-INF', 'RUN-1', 'CAND-1', 'NICHE-1', '{SEALED}', "
        "'Infinity'::double precision);",
        user=RUNTIME_ROLE,
    )

    assert "archive_entries_score_is_finite" in message


def test_a_nan_score_is_refused(store: PostgresContainer) -> None:
    message = store.refuses(
        f"INSERT INTO {SCHEMA}.archive_entries "
        "(entry_id, run_id, candidate_id, niche_id, fitness_vector_hash, "
        "combined_score) VALUES "
        f"('AE-NAN', 'RUN-1', 'CAND-1', 'NICHE-1', '{SEALED}', "
        "'NaN'::double precision);",
        user=RUNTIME_ROLE,
    )

    assert "archive_entries_score_is_finite" in message
