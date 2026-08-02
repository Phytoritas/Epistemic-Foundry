"""negative_and_adversarial_tests - the gate holds against a crash and a liar.

Two hostile things are simulated here against a real server.  The first is a
crash: a transaction that does work and then aborts, exactly as a killed
process would, with the question being whether the store still knows the work
was started.  The second is tampering: a forged journal row, a dropped NOT
NULL, a guard function redefined to agree with whoever calls it - each applied
inside a transaction that is never committed, so the tamper is observed by the
database and then discarded rather than described in prose.

Every attack runs as the principal that would really attempt it, and every
refusal is the server's own message.
"""

from __future__ import annotations

import pytest

from fixtures import (
    GATE_SCHEMA,
    SEALED,
    STORE_JOURNAL_ID,
    STORE_SCHEMA,
    lineage_insert,
    open_attempt_call,
    pending,
    probe_in_aborted_transaction,
    seal_and_close_call,
    store_seal_call,
)
from pg_harness import RUNTIME_ROLE, PostgresContainer

RUN_EVALUATOR = "sha256:" + "a" * 64
FORGED = "sha256:" + "0" * 64
CHECKPOINT_BINDINGS = (
    "population_hash",
    "archive_hash",
    "islands_hash",
    "bandit_state_hash",
    "budget_state_hash",
    "testing_ledger_hash",
)
VERIFY_QUERY = f"SELECT * FROM {GATE_SCHEMA}.verify_migration_journal()"
FORGED_JOURNAL_ROW = (
    f"INSERT INTO {GATE_SCHEMA}.migration_journal "
    "(migration_id, digest_scope, content_hash) VALUES "
    f"('v4_d06/0002_invented', '{GATE_SCHEMA}', '{FORGED}');"
)


def verify_rows(container: PostgresContainer, *statements: str) -> dict:
    rows = probe_in_aborted_transaction(
        container, statements=tuple(statements), query=VERIFY_QUERY
    )
    return {row["journalled_migration_id"]: row for row in rows}


# --- the crash the gate exists to survive ----------------------------------


def test_a_crash_after_opening_leaves_the_marker_behind(
    gate: PostgresContainer,
) -> None:
    # The attempt is committed first, on purpose: the marker has to outlive the
    # work it guards, or a crash would erase the only evidence that the
    # generation was ever touched.
    gate.query(open_attempt_call(expected=3), user=RUNTIME_ROLE)
    gate.sql(
        "BEGIN;\n" + lineage_insert("CAND-CRASH") + "\nROLLBACK;",
        user=RUNTIME_ROLE,
    )
    rows = pending(gate)

    assert len(rows) == 1
    assert rows[0]["attempt_id"] == "AT-1"
    assert rows[0]["expected_candidate_count"] == 3
    # Recovery can see how far the crashed work got: one candidate short.
    assert rows[0]["observed_candidate_count"] == 2
    assert rows[0]["checkpoint_present"] is False


def test_a_crash_during_sealing_leaves_no_resume_point(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.sql(
        "BEGIN;\n" + seal_and_close_call() + ";\nROLLBACK;",
        user=RUNTIME_ROLE,
    )
    checkpoints = gate.query(
        f"SELECT count(*) AS total FROM {STORE_SCHEMA}.evolution_checkpoints"
    )
    rows = pending(gate)

    assert checkpoints[0]["total"] == 0
    assert len(rows) == 1
    assert rows[0]["attempt_id"] == "AT-1"


def test_a_marker_that_was_never_committed_cannot_be_found(
    gate: PostgresContainer,
) -> None:
    # The contract the caller must honour, stated as a failure: an attempt
    # opened inside the same transaction as the work disappears with it.
    gate.sql(
        "BEGIN;\n" + open_attempt_call() + ";\nROLLBACK;",
        user=RUNTIME_ROLE,
    )

    assert pending(gate) == []


def test_a_crashed_attempt_cannot_be_deleted_by_the_runtime(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    message = gate.refuses(
        f"DELETE FROM {GATE_SCHEMA}.checkpoint_attempts WHERE attempt_id = 'AT-1';",
        user=RUNTIME_ROLE,
    )

    assert "permission denied" in message


def test_even_a_superuser_delete_hits_the_append_only_guard(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    message = gate.refuses(
        f"DELETE FROM {GATE_SCHEMA}.checkpoint_attempts WHERE attempt_id = 'AT-1';"
    )

    assert "append-only" in message


def test_a_closed_attempt_cannot_be_reopened(gate: PostgresContainer) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call(), user=RUNTIME_ROLE)
    message = gate.refuses(
        f"UPDATE {GATE_SCHEMA}.checkpoint_attempts SET closed_at = NULL, "
        "checkpoint_id = NULL WHERE attempt_id = 'AT-1';"
    )

    assert "cannot be reopened" in message


def test_an_attempt_cannot_be_rewritten_once_opened(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    message = gate.refuses(
        f"UPDATE {GATE_SCHEMA}.checkpoint_attempts "
        "SET expected_candidate_count = 0 WHERE attempt_id = 'AT-1';"
    )

    assert "immutable once opened" in message


def test_the_runtime_cannot_forge_an_attempt(gate: PostgresContainer) -> None:
    message = gate.refuses(
        f"INSERT INTO {GATE_SCHEMA}.checkpoint_attempts "
        "(attempt_id, run_id, generation, expected_candidate_count) "
        "VALUES ('AT-FORGED', 'RUN-1', 1, 0);",
        user=RUNTIME_ROLE,
    )

    assert "permission denied" in message


def test_the_runtime_cannot_forge_a_journal_row(
    gate: PostgresContainer,
) -> None:
    message = gate.refuses(FORGED_JOURNAL_ROW, user=RUNTIME_ROLE)

    assert "permission denied" in message


# --- the gate over D05's checkpoint table ----------------------------------


def test_sealing_without_an_open_attempt_is_refused(
    gate: PostgresContainer,
) -> None:
    message = gate.refuses(store_seal_call(), user=RUNTIME_ROLE)

    assert "open recovery attempt" in message


def test_sealing_after_the_attempt_was_abandoned_is_refused(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(
        f"SELECT {GATE_SCHEMA}.abandon_checkpoint_attempt('AT-1', 'gave up') AS ok",
        user=RUNTIME_ROLE,
    )
    message = gate.refuses(store_seal_call(), user=RUNTIME_ROLE)

    assert "open recovery attempt" in message


def test_an_attempt_cannot_cover_a_generation_it_never_opened(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(generation=1), user=RUNTIME_ROLE)
    message = gate.refuses(store_seal_call(generation=2), user=RUNTIME_ROLE)

    assert "open recovery attempt" in message
    assert "generation 2" in message


def test_two_open_attempts_for_one_generation_are_refused(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    message = gate.refuses(open_attempt_call("AT-2"), user=RUNTIME_ROLE)

    assert "checkpoint_attempts_one_open_per_generation" in message


def test_opening_an_attempt_on_a_sealed_generation_is_refused(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call(), user=RUNTIME_ROLE)
    message = gate.refuses(open_attempt_call("AT-2"), user=RUNTIME_ROLE)

    assert "already sealed" in message


def test_counts_that_do_not_reconcile_refuse_the_seal(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(expected=5), user=RUNTIME_ROLE)
    message = gate.refuses(seal_and_close_call(), user=RUNTIME_ROLE)

    assert "checkpoint counts do not reconcile" in message
    assert "the store holds 2" in message


def test_a_seal_refused_on_counts_leaves_no_checkpoint_and_an_open_attempt(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(expected=5), user=RUNTIME_ROLE)
    gate.refuses(seal_and_close_call(), user=RUNTIME_ROLE)
    checkpoints = gate.query(
        f"SELECT count(*) AS total FROM {STORE_SCHEMA}.evolution_checkpoints"
    )

    assert checkpoints[0]["total"] == 0
    assert len(pending(gate)) == 1


@pytest.mark.parametrize("column", CHECKPOINT_BINDINGS)
def test_a_checkpoint_missing_a_binding_is_refused_inside_an_open_attempt(
    gate: PostgresContainer, column: str
) -> None:
    # The gate never becomes the reason a partial checkpoint is refused: D05's
    # NOT NULL is still what stops it, with the attempt legitimately open.
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    kept = [name for name in CHECKPOINT_BINDINGS if name != column]
    values = ", ".join(f"'{SEALED}'" for _ in kept)
    message = gate.refuses(
        f"INSERT INTO {STORE_SCHEMA}.evolution_checkpoints "
        "(checkpoint_id, run_id, generation, checkpoint_hash, "
        "evaluator_bundle_hash, " + ", ".join(kept) + ") VALUES "
        f"('CP-PARTIAL', 'RUN-1', 1, '{SEALED}', '{RUN_EVALUATOR}', {values});",
        user=RUNTIME_ROLE,
    )

    assert "null value" in message.lower()
    assert column in message


def test_the_evaluator_cannot_be_swapped_through_the_gate(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    message = gate.refuses(
        seal_and_close_call(evaluator="sha256:" + "7" * 64),
        user=RUNTIME_ROLE,
    )

    assert "checkpoint evaluator does not match the run evaluator" in message


def test_a_sealed_checkpoint_still_cannot_be_rewritten(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call(), user=RUNTIME_ROLE)
    message = gate.refuses(
        f"UPDATE {STORE_SCHEMA}.evolution_checkpoints "
        f"SET population_hash = '{FORGED}' WHERE checkpoint_id = 'CP-1';"
    )

    assert "append-only" in message


def test_an_attempt_cannot_be_closed_twice(gate: PostgresContainer) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call(), user=RUNTIME_ROLE)
    message = gate.refuses(
        seal_and_close_call(checkpoint_id="CP-AGAIN"), user=RUNTIME_ROLE
    )

    assert "already closed" in message


def test_abandoning_a_closed_attempt_is_refused(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    gate.query(seal_and_close_call(), user=RUNTIME_ROLE)
    message = gate.refuses(
        f"SELECT {GATE_SCHEMA}.abandon_checkpoint_attempt('AT-1', 'late');",
        user=RUNTIME_ROLE,
    )

    assert "already closed" in message


def test_abandoning_without_a_reason_is_refused(
    gate: PostgresContainer,
) -> None:
    gate.query(open_attempt_call(), user=RUNTIME_ROLE)
    message = gate.refuses(
        f"SELECT {GATE_SCHEMA}.abandon_checkpoint_attempt('AT-1', '');",
        user=RUNTIME_ROLE,
    )

    assert "requires a reason" in message


def test_closing_an_attempt_that_does_not_exist_is_refused(
    gate: PostgresContainer,
) -> None:
    message = gate.refuses(seal_and_close_call("AT-GHOST"), user=RUNTIME_ROLE)

    assert "checkpoint attempt does not exist" in message


def test_an_attempt_for_an_unknown_run_is_refused(
    gate: PostgresContainer,
) -> None:
    message = gate.refuses(open_attempt_call(run_id="RUN-GHOST"), user=RUNTIME_ROLE)

    assert "foreign key" in message or "checkpoint_attempts_run_id" in message


def test_a_negative_expected_count_is_refused(
    gate: PostgresContainer,
) -> None:
    message = gate.refuses(open_attempt_call(expected=-1), user=RUNTIME_ROLE)

    assert "checkpoint_attempts_expected_count_range" in message


# --- tampering with the record ---------------------------------------------


def test_the_journal_cannot_be_updated(postgres: PostgresContainer) -> None:
    message = postgres.refuses(
        f"UPDATE {GATE_SCHEMA}.migration_journal SET content_hash = '{FORGED}' "
        f"WHERE migration_id = '{STORE_JOURNAL_ID}';"
    )

    assert "append-only" in message


def test_the_journal_cannot_be_deleted(postgres: PostgresContainer) -> None:
    message = postgres.refuses(
        f"DELETE FROM {GATE_SCHEMA}.migration_journal "
        f"WHERE migration_id = '{STORE_JOURNAL_ID}';"
    )

    assert "append-only" in message


def test_a_forged_journal_row_fails_re_derivation(
    postgres: PostgresContainer,
) -> None:
    rows = verify_rows(postgres, FORGED_JOURNAL_ROW)

    assert rows["v4_d06/0002_invented"]["matches"] is False
    assert rows[STORE_JOURNAL_ID]["matches"] is True


def test_the_fail_closed_check_refuses_a_forged_journal_row(
    postgres: PostgresContainer,
) -> None:
    message = postgres.refuses(
        "BEGIN;\n"
        + FORGED_JOURNAL_ROW
        + f"\nSELECT {GATE_SCHEMA}.require_intact_migration_journal();"
    )

    assert "no longer describes this database" in message
    assert "v4_d06/0002_invented" in message


def test_a_dropped_not_null_on_the_store_is_detected(
    postgres: PostgresContainer,
) -> None:
    # The digest reads the catalog, so weakening D05 moves it even though the
    # journal row itself was never touched.
    rows = verify_rows(
        postgres,
        f"ALTER TABLE {STORE_SCHEMA}.evolution_checkpoints "
        "ALTER COLUMN population_hash DROP NOT NULL;",
    )

    assert rows[STORE_JOURNAL_ID]["matches"] is False


def test_a_guard_function_rewritten_to_agree_with_its_caller_is_detected(
    postgres: PostgresContainer,
) -> None:
    # The most dangerous tamper D05 could suffer: an eviction function that
    # stops refusing protected entries.  Function bodies are in the digest for
    # exactly this reason.
    rows = verify_rows(
        postgres,
        f"CREATE OR REPLACE FUNCTION {STORE_SCHEMA}.evict_archive_entry("
        "requested_entry_id text, requested_reason text) RETURNS boolean "
        "LANGUAGE plpgsql AS $rogue$ BEGIN RETURN true; END $rogue$;",
    )

    assert rows[STORE_JOURNAL_ID]["matches"] is False


def test_a_relaxed_check_constraint_is_detected(
    postgres: PostgresContainer,
) -> None:
    rows = verify_rows(
        postgres,
        f"ALTER TABLE {STORE_SCHEMA}.archive_entries "
        "DROP CONSTRAINT archive_entries_protected_never_evicted;",
    )

    assert rows[STORE_JOURNAL_ID]["matches"] is False


def test_a_column_added_to_the_gate_is_detected(
    postgres: PostgresContainer,
) -> None:
    rows = verify_rows(
        postgres,
        f"ALTER TABLE {GATE_SCHEMA}.checkpoint_attempts "
        "ADD COLUMN convenient_override boolean;",
    )

    assert rows["v4_d06/0001_archive_migration_gate"]["matches"] is False
    assert rows[STORE_JOURNAL_ID]["matches"] is True


def test_the_tampering_probes_left_nothing_behind(
    postgres: PostgresContainer,
) -> None:
    # Every probe above ran in a transaction that was never committed, so the
    # journal must still verify against the live catalog.
    rows = postgres.query(
        f"SELECT {GATE_SCHEMA}.require_intact_migration_journal() AS intact"
    )

    assert rows[0]["intact"] is True


def test_a_protected_entry_still_cannot_be_evicted(
    gate: PostgresContainer,
) -> None:
    message = gate.refuses(
        f"SELECT {STORE_SCHEMA}.evict_archive_entry('AE-NULL', 'low fitness');",
        user=RUNTIME_ROLE,
    )

    assert "protected archive entry cannot be evicted" in message
