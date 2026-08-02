"""unit_and_contract_tests — a whole fan-out reconciles across all three ledgers.

Every receipt here is minted by the runtime's own builders and validated against
its canonical schema, so what the engine agrees with is the ledger rather than
the test author.  The happy paths cover a clean run, a legitimately failed
candidate, a cancelled one, and a rolled-back effect — each of which must
reconcile, because a terminal state is an answer, not a gap.
"""

from __future__ import annotations

from epistemic_foundry.effects.v4_e05 import (
    reconcile_effect_ledger,
    require_effect_reconciliation,
)
from fixtures import (
    FAILED,
    NOT_EXECUTED,
    ROLLED_BACK,
    SUCCEEDED,
    clean_fanout,
    effect,
    mutation,
)


def test_a_clean_fanout_reconciles() -> None:
    report = reconcile_effect_ledger(**clean_fanout())

    assert report["reconciled"] is True
    require_effect_reconciliation(report)


def test_the_report_carries_the_candidate_accounting_it_composed() -> None:
    report = reconcile_effect_ledger(**clean_fanout())

    assert report["candidates"]["reconciled"] is True
    assert report["candidates"]["counts"]["proposed"] == 2
    assert report["candidates"]["counts"]["persisted"] == 2


def test_the_report_counts_both_ledgers() -> None:
    report = reconcile_effect_ledger(**clean_fanout())

    assert report["counts"] == {"effect_receipts": 2, "mutation_receipts": 2}


def test_every_finding_list_is_empty_on_a_clean_run() -> None:
    report = reconcile_effect_ledger(**clean_fanout())

    for field in (
        "dangling_effect_references",
        "disagreements",
        "orphan_effect_receipts",
        "orphan_mutation_receipts",
        "unreceipted_candidates",
        "unresolved_candidates",
    ):
        assert report[field] == [], field


def test_a_failed_candidate_reconciles_as_terminal() -> None:
    failed_effect = effect("INT-2", FAILED)
    report = reconcile_effect_ledger(
        proposed=["CAND-1", "CAND-2"],
        generated=["CAND-1", "CAND-2"],
        evaluated=["CAND-1"],
        persisted=["CAND-1"],
        failed=["CAND-2"],
        effect_receipts=[effect("INT-1"), failed_effect],
        mutation_receipts=[
            mutation("CAND-1", "EF-PLACEHOLDER"),
            mutation("CAND-2", failed_effect["receipt_id"]),
        ],
    )

    assert report["dangling_effect_references"] == ["CAND-1"]


def test_a_failed_candidate_with_a_real_receipt_reconciles() -> None:
    first = effect("INT-1")
    second = effect("INT-2", FAILED)
    report = reconcile_effect_ledger(
        proposed=["CAND-1", "CAND-2"],
        generated=["CAND-1", "CAND-2"],
        evaluated=["CAND-1"],
        persisted=["CAND-1"],
        failed=["CAND-2"],
        effect_receipts=[first, second],
        mutation_receipts=[
            mutation("CAND-1", first["receipt_id"]),
            mutation("CAND-2", second["receipt_id"]),
        ],
    )

    assert report["reconciled"] is True
    require_effect_reconciliation(report)


def test_a_cancelled_candidate_reconciles() -> None:
    first = effect("INT-1")
    second = effect("INT-2", NOT_EXECUTED)
    report = reconcile_effect_ledger(
        proposed=["CAND-1", "CAND-2"],
        generated=["CAND-1", "CAND-2"],
        evaluated=["CAND-1"],
        persisted=["CAND-1"],
        cancelled=["CAND-2"],
        effect_receipts=[first, second],
        mutation_receipts=[
            mutation("CAND-1", first["receipt_id"]),
            mutation("CAND-2", second["receipt_id"]),
        ],
    )

    assert report["reconciled"] is True


def test_a_rolled_back_effect_does_not_count_as_persisted() -> None:
    first = effect("INT-1")
    second = effect("INT-2", ROLLED_BACK)
    report = reconcile_effect_ledger(
        proposed=["CAND-1", "CAND-2"],
        generated=["CAND-1", "CAND-2"],
        evaluated=["CAND-1", "CAND-2"],
        persisted=["CAND-1"],
        cancelled=["CAND-2"],
        effect_receipts=[first, second],
        mutation_receipts=[
            mutation("CAND-1", first["receipt_id"]),
            mutation("CAND-2", second["receipt_id"]),
        ],
    )

    assert report["reconciled"] is True
    assert report["disagreements"] == []


def test_an_empty_run_reconciles_vacuously() -> None:
    report = reconcile_effect_ledger(
        proposed=[],
        generated=[],
        evaluated=[],
        persisted=[],
    )

    assert report["reconciled"] is True
    assert report["counts"] == {"effect_receipts": 0, "mutation_receipts": 0}


def test_the_effect_receipts_the_fixture_mints_are_schema_valid() -> None:
    receipt = effect("INT-1")

    assert receipt["status"] == SUCCEEDED
    assert receipt["reconciliation_required"] is False
    assert receipt["receipt_hash"].startswith("sha256:")


def test_the_mutation_receipt_binds_its_effect() -> None:
    receipt_effect = effect("INT-1")
    receipt = mutation("CAND-1", receipt_effect["receipt_id"])

    assert receipt["effect_receipt_id"] == receipt_effect["receipt_id"]
    assert receipt["output_candidate_id"] == "CAND-1"
    assert receipt["input_candidate_ids"] == ["CAND-0"]
    assert receipt["changed_paths"], "a mutation that changed nothing is not one"


def test_a_multi_generation_fanout_reconciles() -> None:
    effects = [effect(f"INT-{index}") for index in range(1, 4)]
    report = reconcile_effect_ledger(
        proposed=["CAND-1", "CAND-2", "CAND-3"],
        generated=["CAND-1", "CAND-2", "CAND-3"],
        evaluated=["CAND-1", "CAND-2", "CAND-3"],
        persisted=["CAND-1", "CAND-2", "CAND-3"],
        effect_receipts=effects,
        mutation_receipts=[
            mutation("CAND-1", effects[0]["receipt_id"]),
            mutation("CAND-2", effects[1]["receipt_id"]),
            mutation("CAND-3", effects[2]["receipt_id"], parent_id="CAND-1"),
        ],
    )

    assert report["reconciled"] is True
    assert report["counts"]["mutation_receipts"] == 3


def test_reconciliation_is_deterministic() -> None:
    payload = clean_fanout()

    assert reconcile_effect_ledger(**payload) == reconcile_effect_ledger(**payload)
