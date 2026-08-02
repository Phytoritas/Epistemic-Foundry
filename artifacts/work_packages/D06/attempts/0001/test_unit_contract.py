"""unit_and_contract_tests - the paths the gate exists to serve.

A run opens an attempt, does its work, and seals a resume point that closes the
attempt in the same statement; recovery then has nothing to do.  A run that
gives up says why, and the generation stays available.  Every call here is made
as the runtime principal wherever the runtime would make it, against a real
server, so a privilege the runtime does not hold shows up as a failure rather
than as a convenient superuser success.
"""

from __future__ import annotations

from fixtures import (
    GATE_JOURNAL_ID,
    GATE_SCHEMA,
    MIGRATION,
    SEEDED_CANDIDATE_COUNT,
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

BINDINGS = (
    "population_hash",
    "archive_hash",
    "islands_hash",
    "bandit_state_hash",
    "budget_state_hash",
    "testing_ledger_hash",
    "evaluator_bundle_hash",
)


def test_opening_an_attempt_records_an_in_progress_marker(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    rows = pending(gate)

    assert len(rows) == 1
    assert rows[0]["attempt_id"] == "AT-1"
    assert rows[0]["checkpoint_present"] is False


def test_the_marker_names_the_count_the_generation_must_reconcile_to(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    rows = pending(gate)

    assert rows[0]["expected_candidate_count"] == SEEDED_CANDIDATE_COUNT
    assert rows[0]["observed_candidate_count"] == SEEDED_CANDIDATE_COUNT


def test_sealing_and_closing_leaves_recovery_nothing_to_do(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call(), user=RUNTIME_ROLE)

    assert pending(gate) == []


def test_the_sealed_checkpoint_still_binds_all_seven(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call(), user=RUNTIME_ROLE)
    rows = gate.query(
        f"SELECT * FROM {STORE_SCHEMA}.evolution_checkpoints "
        "WHERE checkpoint_id = 'CP-1'"
    )

    assert len(rows) == 1
    for column in BINDINGS:
        assert rows[0][column].startswith("sha256:"), column


def test_a_resume_point_resolves_to_exactly_one_attempt(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call(), user=RUNTIME_ROLE)
    rows = gate.query(
        f"SELECT * FROM {GATE_SCHEMA}.checkpoint_recovery_points ORDER BY checkpoint_id"
    )

    assert len(rows) == 1
    assert rows[0]["checkpoint_id"] == "CP-1"
    assert rows[0]["attempt_id"] == "AT-1"
    assert rows[0]["closed_at"] is not None


def test_no_checkpoint_is_left_unreconciled_on_the_happy_path(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call(), user=RUNTIME_ROLE)
    rows = gate.query(f"SELECT * FROM {GATE_SCHEMA}.unreconciled_checkpoints")

    assert rows == []


def test_successive_generations_seal_through_the_gate(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call(), user=RUNTIME_ROLE)
    gate.sql(lineage_insert("CAND-3", generation=2), user=RUNTIME_ROLE)
    gate.query(open_attempt_call("AT-2", generation=2, expected=1), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call("AT-2", "CP-2"), user=RUNTIME_ROLE)
    rows = gate.query(
        "SELECT generation, checkpoint_id "
        f"FROM {STORE_SCHEMA}.evolution_checkpoints ORDER BY generation"
    )

    assert [row["generation"] for row in rows] == [1, 2]
    assert pending(gate) == []


def test_abandoning_an_attempt_closes_it_with_a_reason(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(
        f"SELECT {GATE_SCHEMA}.abandon_checkpoint_attempt("
        "'AT-1', 'the evaluator bundle was withdrawn mid-generation') AS ok",
        user=RUNTIME_ROLE,
    )
    rows = gate.query(
        "SELECT closed_at, abandon_reason, checkpoint_id "
        f"FROM {GATE_SCHEMA}.checkpoint_attempts WHERE attempt_id = 'AT-1'"
    )

    assert pending(gate) == []
    assert rows[0]["closed_at"] is not None
    assert rows[0]["checkpoint_id"] is None
    assert rows[0]["abandon_reason"] == (
        "the evaluator bundle was withdrawn mid-generation"
    )


def test_an_abandoned_generation_may_be_attempted_again(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(
        f"SELECT {GATE_SCHEMA}.abandon_checkpoint_attempt("
        "'AT-1', 'crashed before the population settled') AS ok",
        user=RUNTIME_ROLE,
    )
    gate.query(open_attempt_call("AT-RETRY"), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call("AT-RETRY", "CP-RETRY"), user=RUNTIME_ROLE)
    rows = gate.query(f"SELECT checkpoint_id FROM {STORE_SCHEMA}.evolution_checkpoints")

    assert [row["checkpoint_id"] for row in rows] == ["CP-RETRY"]
    assert pending(gate) == []


def test_abandoning_keeps_the_crashed_attempt_as_evidence(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(
        f"SELECT {GATE_SCHEMA}.abandon_checkpoint_attempt('AT-1', 'gave up') AS ok",
        user=RUNTIME_ROLE,
    )
    rows = gate.query(
        f"SELECT count(*) AS total FROM {GATE_SCHEMA}.checkpoint_attempts"
    )

    assert rows[0]["total"] == 1


def test_reapplying_the_migration_is_refused(
    postgres: PostgresContainer,
) -> None:
    # The declared policy is refusal rather than a silent no-op: a second run
    # cannot tell "already applied" from "applied to the wrong database", and
    # the journal row it would write would be a claim, not a record.
    message = postgres.refuses(MIGRATION.read_text(encoding="utf-8"))

    assert "already applied" in message
    assert "v4_d06/0001_archive_migration_gate" in message


def test_a_refused_reapply_changes_nothing(
    postgres: PostgresContainer,
) -> None:
    before = journal_rows(postgres)
    postgres.refuses(MIGRATION.read_text(encoding="utf-8"))
    after = journal_rows(postgres)

    assert before == after
    assert set(after) == {STORE_JOURNAL_ID, GATE_JOURNAL_ID}


def test_the_journal_verifies_against_the_live_catalog(
    postgres: PostgresContainer,
) -> None:
    rows = verification(postgres)

    assert set(rows) == {STORE_JOURNAL_ID, GATE_JOURNAL_ID}
    for row in rows.values():
        assert row["matches"] is True, row
        assert row["observed_hash"] == row["journalled_hash"], row


def test_the_fail_closed_journal_check_passes_at_rest(
    postgres: PostgresContainer,
) -> None:
    rows = postgres.query(
        f"SELECT {GATE_SCHEMA}.require_intact_migration_journal() AS intact",
        user=RUNTIME_ROLE,
    )

    assert rows[0]["intact"] is True


def test_the_store_still_serves_its_own_happy_path(
    gate: PostgresContainer,
) -> None:
    # The gate tightened the checkpoint path; nothing else about D05 changed,
    # and an unprotected entry can still be evicted with a reason.
    gate.query(
        f"SELECT {STORE_SCHEMA}.evict_archive_entry("
        "'AE-WEAK', 'superseded in niche') AS ok",
        user=RUNTIME_ROLE,
    )
    rows = gate.query(
        "SELECT evicted_at, eviction_reason "
        f"FROM {STORE_SCHEMA}.archive_entries WHERE entry_id = 'AE-WEAK'"
    )

    assert rows[0]["evicted_at"] is not None
    assert rows[0]["eviction_reason"] == "superseded in niche"
