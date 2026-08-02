"""load_shedding_test — under overload the system sheds excess load gracefully.

Required check: ``load_shedding_test``.  Offered load beyond a hard admission
capacity (Y01) is served up to the guaranteed capacity and the excess is shed;
every offered item terminates as either ``ADMITTED`` or ``SHED`` and the two
reconcile to the offered total exactly (EF4-I26) — nothing is silently dropped.
Admitted work is processed correctly and within its hard budget, the degradation
is bounded (the full hard capacity is always served), and the honest observability
state (Y02) is ``DEGRADED`` while work is shed — never a shade of healthy ``OK``.

The refusal cases prove the shedding is honest rather than cosmetic: admitting
beyond the hard capacity, dropping items so admitted + shed no longer equals the
offered load, and claiming ``OK`` while work was shed are each refused with a
typed error.
"""

from __future__ import annotations

import pytest

from scale_harness import (
    ScaleError,
    content_hash,
    evaluate_load_shedding,
    load_budget_vocabulary,
    load_dataset,
    run_load_shedding,
)

DATASET = load_dataset()
VOCAB = load_budget_vocabulary()
SCENARIO = DATASET["overload_scenario"]


def test_overload_sheds_the_excess_and_serves_the_full_capacity() -> None:
    report = evaluate_load_shedding()
    result = report["result"]

    assert report["status"] == "PASS"
    assert result["graceful"] is True
    assert result["offered_load"] == SCENARIO["offered_load"]
    assert result["admitted"] == SCENARIO["hard_admission_capacity"]
    assert (
        result["shed"] == SCENARIO["offered_load"] - SCENARIO["hard_admission_capacity"]
    )
    assert result["shed"] > 0


def test_every_offered_item_is_admitted_or_shed_with_nothing_dropped() -> None:
    result = evaluate_load_shedding()["result"]

    assert result["admitted"] + result["shed"] == result["offered_load"]
    assert result["reconciled"] is True
    # Shed work is visible and reason-tagged, not a silent drop.
    assert result["shed_reason"] == SCENARIO["shed_reason"]


def test_shedding_reports_the_honest_degraded_state_not_ok() -> None:
    result = evaluate_load_shedding()["result"]

    assert result["state"] == "DEGRADED"
    assert result["partial"] is True
    # The hard budget over the admitted work is honoured and the breach policy
    # is surfaced, never absorbed.
    assert result["admitted_within_budget"] is True
    assert result["breach_applied"] == SCENARIO["breach_policy"]


def test_degradation_is_bounded_by_the_guaranteed_capacity() -> None:
    result = evaluate_load_shedding()["result"]

    assert result["served_floor_met"] is True
    assert result["bounded_degradation"] is True
    assert result["admitted"] <= result["hard_admission_capacity"]


def test_no_overload_serves_everything_and_reports_ok() -> None:
    calm = dict(SCENARIO)
    calm["offered_load"] = SCENARIO["hard_admission_capacity"]
    result = run_load_shedding(calm, VOCAB)

    assert result["shed"] == 0
    assert result["partial"] is False
    assert result["state"] == "OK"
    assert result["graceful"] is True
    assert result["breach_applied"] is None


def test_the_report_is_deterministic_and_self_hashing() -> None:
    first = evaluate_load_shedding()
    second = evaluate_load_shedding()
    assert first["report_hash"] == second["report_hash"]
    assert first["report_hash"] == content_hash(first, drop_key="report_hash")


# --- Fail-closed refusals: shedding is honest, not cosmetic. ---------------- #
def test_admitting_beyond_the_hard_capacity_is_refused() -> None:
    with pytest.raises(ScaleError) as caught:
        run_load_shedding(
            SCENARIO, VOCAB, admit=SCENARIO["hard_admission_capacity"] + 1
        )
    assert caught.value.code == "ADMISSION_OVERRUN"


def test_silently_dropping_offered_work_is_refused() -> None:
    # Admit the capacity but under-declare the shed count: 100 items vanish.
    capacity = SCENARIO["hard_admission_capacity"]
    honest_shed = SCENARIO["offered_load"] - capacity
    with pytest.raises(ScaleError) as caught:
        run_load_shedding(
            SCENARIO, VOCAB, admit=capacity, declared_shed=honest_shed - 100
        )
    assert caught.value.code == "SHED_RECONCILIATION_FAILURE"


def test_claiming_ok_while_load_was_shed_is_refused() -> None:
    with pytest.raises(ScaleError) as caught:
        run_load_shedding(SCENARIO, VOCAB, forced_state="OK")
    assert caught.value.code == "STATE_DISHONEST"


def test_an_unbounded_admission_enforcement_is_refused() -> None:
    soft = dict(SCENARIO)
    soft["admission_enforcement"] = "SOFT_ESTIMATE"
    with pytest.raises(ScaleError) as caught:
        run_load_shedding(soft, VOCAB)
    assert caught.value.code == "ADMISSION_UNBOUNDED"


def test_a_corrupted_admitted_result_drops_the_state_out_of_ok() -> None:
    calm = dict(SCENARIO)
    calm["offered_load"] = SCENARIO["hard_admission_capacity"]
    result = run_load_shedding(calm, VOCAB, corrupt_admitted=1)

    assert result["admitted_good"] == result["admitted"] - 1
    assert result["state"] == "DEGRADED"
    assert result["graceful"] is False
