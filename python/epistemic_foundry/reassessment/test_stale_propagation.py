"""stale_propagation_test — no dependent Passport survives an update as FRESH."""

from __future__ import annotations

import pytest

from .contracts import (
    PASSPORT_STATES,
    ReassessmentError,
    apply_passport_states,
    assess_update,
    dependent_closure,
    validate_graph,
)
from .test_retraction_fixture import CREATED_AT, RUN_ID, assess, graph


def deep_graph() -> list[dict[str, object]]:
    """A five-hop chain plus a diamond and a provenance cycle."""

    return [
        {"artifact_class": "document", "artifact_id": "DOC-A", "depends_on": []},
        {"artifact_class": "evidence", "artifact_id": "EV-A", "depends_on": ["DOC-A"]},
        {"artifact_class": "claim", "artifact_id": "CLM-A", "depends_on": ["EV-A"]},
        {"artifact_class": "claim", "artifact_id": "CLM-B", "depends_on": ["EV-A"]},
        {
            "artifact_class": "pack",
            "artifact_id": "PACK-A",
            "depends_on": ["CLM-A", "CLM-B"],
        },
        {"artifact_class": "passport", "artifact_id": "HP-A", "depends_on": ["PACK-A"]},
        {"artifact_class": "passport", "artifact_id": "HP-B", "depends_on": ["HP-A"]},
        {
            "artifact_class": "claim",
            "artifact_id": "CLM-LOOP-1",
            "depends_on": ["CLM-LOOP-2"],
        },
        {
            "artifact_class": "claim",
            "artifact_id": "CLM-LOOP-2",
            "depends_on": ["CLM-LOOP-1"],
        },
    ]


def test_stale_propagation_test_closure_is_transitive_not_one_hop() -> None:
    indexed = validate_graph(deep_graph())

    closure = dependent_closure(["DOC-A"], indexed)

    assert closure == ["CLM-A", "CLM-B", "EV-A", "HP-A", "HP-B", "PACK-A"]


def test_stale_propagation_test_scalar_seed_is_not_split_into_artifact_ids() -> None:
    indexed = validate_graph(deep_graph())

    with pytest.raises(ReassessmentError) as raised:
        dependent_closure("DOC-A", indexed)

    assert raised.value.code == "INPUT_INVALID"


def test_stale_propagation_test_a_provenance_cycle_terminates() -> None:
    indexed = validate_graph(deep_graph())

    closure = dependent_closure(["CLM-LOOP-1"], indexed)

    assert closure == ["CLM-LOOP-2"]


def test_stale_propagation_test_every_reached_passport_is_marked() -> None:
    plan = assess_update(
        created_at=CREATED_AT,
        graph=deep_graph(),
        run_id=RUN_ID,
        trigger_artifact_ids=["DOC-A"],
        trigger_event_id="EVT-W03-DEEP",
        trigger_type="document_retraction",
    ).payload

    assert plan["affected_passport_ids"] == ["HP-A", "HP-B"]
    assert plan["passport_states"] == {"HP-A": "INVALIDATED", "HP-B": "INVALIDATED"}
    assert "FRESH" not in set(plan["passport_states"].values())


def test_stale_propagation_test_downstream_passport_cannot_stay_fresh() -> None:
    sealed = assess_update(
        created_at=CREATED_AT,
        graph=deep_graph(),
        run_id=RUN_ID,
        trigger_artifact_ids=["DOC-A"],
        trigger_event_id="EVT-W03-DEEP",
        trigger_type="claim_correction",
    )
    forged = sealed.payload
    forged["passport_states"]["HP-B"] = "FRESH"

    with pytest.raises(ReassessmentError) as raised:
        apply_passport_states(
            [
                {"passport_id": "HP-A", "revision": 1},
                {"passport_id": "HP-B", "revision": 1},
            ],
            forged,
        )
    assert raised.value.code in {
        "PASSPORT_STALENESS_NOT_APPLIED",
        "PLAN_HASH_MISMATCH",
    }


def test_stale_propagation_test_dropping_a_passport_state_fails_closed() -> None:
    sealed = assess_update(
        created_at=CREATED_AT,
        graph=deep_graph(),
        run_id=RUN_ID,
        trigger_artifact_ids=["DOC-A"],
        trigger_event_id="EVT-W03-DEEP",
        trigger_type="document_correction",
    )
    forged = sealed.payload
    del forged["passport_states"]["HP-B"]

    with pytest.raises(ReassessmentError) as raised:
        apply_passport_states([{"passport_id": "HP-A", "revision": 1}], forged)
    assert raised.value.code in {"PASSPORT_STATE_INCOMPLETE", "PLAN_HASH_MISMATCH"}


def test_stale_propagation_test_an_affected_passport_must_be_supplied() -> None:
    sealed = assess_update(
        created_at=CREATED_AT,
        graph=deep_graph(),
        run_id=RUN_ID,
        trigger_artifact_ids=["DOC-A"],
        trigger_event_id="EVT-W03-DEEP",
        trigger_type="document_correction",
    )

    with pytest.raises(ReassessmentError) as raised:
        apply_passport_states([{"passport_id": "HP-A", "revision": 1}], sealed.payload)
    assert raised.value.code == "PASSPORT_NOT_SUPPLIED"
    assert raised.value.details["passport_ids"] == ["HP-B"]


def test_stale_propagation_test_marking_is_idempotent_in_state_but_revisions_advance() -> (
    None
):
    sealed = assess()
    passports = [
        {"passport_id": "HP-1", "revision": 1},
        {"passport_id": "HP-2", "revision": 1},
    ]

    first = apply_passport_states(passports, sealed.payload)
    second = apply_passport_states(first, sealed.payload)

    first_hp1 = next(row for row in first if row["passport_id"] == "HP-1")
    second_hp1 = next(row for row in second if row["passport_id"] == "HP-1")
    assert first_hp1["revision"] == 2
    assert second_hp1["revision"] == 3
    assert (
        first_hp1["staleness_state"] == second_hp1["staleness_state"] == "INVALIDATED"
    )
    assert first_hp1["staleness_plan_id"] == second_hp1["staleness_plan_id"]


def test_stale_propagation_test_passport_input_contracts_fail_closed() -> None:
    sealed = assess()

    with pytest.raises(ReassessmentError) as raised:
        apply_passport_states(
            [
                {"passport_id": "HP-1", "revision": 0},
                {"passport_id": "HP-2", "revision": 1},
            ],
            sealed.payload,
        )
    assert raised.value.code == "INPUT_INVALID"

    with pytest.raises(ReassessmentError) as raised:
        apply_passport_states(
            [
                {"passport_id": "HP-1", "revision": 1},
                {"passport_id": "HP-1", "revision": 2},
            ],
            sealed.payload,
        )
    assert raised.value.code == "DUPLICATE_VALUE"


def test_stale_propagation_test_state_vocabulary_is_closed() -> None:
    assert PASSPORT_STATES == ("FRESH", "STALE", "INVALIDATED")
    plan = assess().payload
    assert set(plan["passport_states"].values()) <= set(PASSPORT_STATES)
    assert graph()  # the shared fixture stays available to this module
