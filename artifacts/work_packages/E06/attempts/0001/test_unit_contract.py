"""unit_and_contract_tests — the effect surface holds across every schedule.

The claim this package makes is not "a run reconciles" — E05 already proves
that — but "a run reconciles the same way no matter how its lanes interleaved".
So each happy path here is stated over *all three* schedules two lanes can
produce, and the assertion is agreement between them rather than success of any
one.  A retry is the other half: the same candidate action presented twice under
one idempotency key must leave one effect receipt behind and settle to a ledger
that cannot tell which attempt arrived first.
"""

from __future__ import annotations

from epistemic_foundry.domain.hashing import canonical_json
from epistemic_foundry.effects.v4_e06 import (
    check_serializability,
    fingerprint_payload,
    require_concurrent_effect_gate,
    run_concurrency_gate,
    settle_interleaving,
)
from fixtures import (
    INITIAL_REVISIONS,
    REV_0,
    REV_1,
    REV_2,
    ROLLED_BACK,
    TARGET_A,
    TARGET_B,
    UNKNOWN,
    action,
    disjoint_actions,
    disjoint_gate,
    effect_receipt,
    interleaved,
    lane,
    mutation,
    retry_actions,
    retry_gate,
    schedules,
    serial,
)


def test_two_disjoint_candidates_reconcile() -> None:
    report = run_concurrency_gate(**disjoint_gate())

    assert report["reconciled"] is True
    require_concurrent_effect_gate(report)


def test_every_schedule_over_disjoint_targets_is_admitted() -> None:
    report = run_concurrency_gate(**disjoint_gate())

    assert report["concurrency"]["admitted_interleaving_ids"] == [
        "IL-SERIAL",
        "IL-REVERSED",
        "IL-CROSSED",
    ]
    assert report["concurrency"]["refused"] == []


def test_every_admitted_schedule_settles_to_one_ledger() -> None:
    """Serializability, stated as the equality it actually means."""
    report = run_concurrency_gate(**disjoint_gate())
    hashes = {entry["ledger_hash"] for entry in report["concurrency"]["settlements"]}

    assert len(hashes) == 1
    assert report["concurrency"]["agreed_ledger_hash"] in hashes
    assert report["concurrency"]["divergent_pair"] == []


def test_a_retry_under_one_key_leaves_one_effect_receipt() -> None:
    report = run_concurrency_gate(**retry_gate())

    assert report["reconciled"] is True
    assert len(report["settled_effect_receipt_ids"]) == 1
    require_concurrent_effect_gate(report)


def test_a_retry_is_recorded_as_a_suppressed_duplicate_not_a_failure() -> None:
    report = run_concurrency_gate(**retry_gate())
    codes = {
        notice["code"]
        for entry in report["concurrency"]["settlements"]
        for notice in entry["notices"]
    }

    assert codes == {"DUPLICATE_EFFECT_SUPPRESSED"}
    assert all(not entry["refusals"] for entry in report["concurrency"]["settlements"])


def test_a_retry_settles_the_same_ledger_whichever_attempt_arrived_first() -> None:
    """Which identical attempt won the race is exactly what must not matter."""
    report = run_concurrency_gate(**retry_gate())
    hashes = {entry["ledger_hash"] for entry in report["concurrency"]["settlements"]}

    assert len(hashes) == 1


def test_a_retry_binds_both_attempts_to_the_one_receipt() -> None:
    report = run_concurrency_gate(**retry_gate())
    settlement = report["concurrency"]["settlements"][0]
    bound = settlement["ledger"]["bindings"]["IDEM-1"]

    assert bound["action_ids"] == ["ACT-1", "ACT-1R"]
    assert report["settled_effect_receipt_ids"] == [bound["effect_receipt_id"]]


def test_a_retry_advances_its_target_exactly_once() -> None:
    report = run_concurrency_gate(**retry_gate())
    revisions = report["concurrency"]["settlements"][0]["ledger"]["revisions"]

    assert revisions == {TARGET_A: REV_1, TARGET_B: REV_0}


def test_the_report_carries_the_sealed_e05_reconciliation_inside_it() -> None:
    """The gate reports E05's verdict; it does not form a second opinion."""
    report = run_concurrency_gate(**disjoint_gate())
    reconciliation = report["effect_reconciliation"]

    assert report["effect_reconciliation_refusal"] is None
    assert reconciliation["reconciled"] is True
    assert reconciliation["candidates"]["counts"]["persisted"] == 2
    assert reconciliation["counts"] == {"effect_receipts": 2, "mutation_receipts": 2}


def test_only_the_surviving_receipts_reach_the_reconciliation() -> None:
    """The retry's second attempt must not be counted as a second effect."""
    report = run_concurrency_gate(**retry_gate())

    assert report["effect_reconciliation"]["counts"]["effect_receipts"] == 1


def test_an_effect_that_did_not_land_leaves_its_target_untouched() -> None:
    landed = effect_receipt("INT-1", "IDEM-1")
    rolled_back = effect_receipt("INT-2", "IDEM-2", ROLLED_BACK)
    actions = [
        action(
            "ACT-1",
            candidate_id="CAND-1",
            idempotency_key="IDEM-1",
            receipt=landed,
            target_ref=TARGET_A,
        ),
        action(
            "ACT-2",
            candidate_id="CAND-2",
            idempotency_key="IDEM-2",
            receipt=rolled_back,
            target_ref=TARGET_A,
            new_revision=REV_2,
        ),
    ]
    report = check_serializability(
        actions=actions,
        interleavings=schedules("ACT-1", "ACT-2"),
        initial_revisions=INITIAL_REVISIONS,
    )

    assert report["serializable"] is True
    assert len(report["admitted_interleaving_ids"]) == 3
    ledger = report["settlements"][0]["ledger"]
    assert ledger["unlanded_keys"] == ["IDEM-2"]
    assert ledger["revisions"][TARGET_A] == REV_1


def test_a_rolled_back_candidate_still_reconciles_as_terminal() -> None:
    landed = effect_receipt("INT-1", "IDEM-1")
    rolled_back = effect_receipt("INT-2", "IDEM-2", ROLLED_BACK)
    actions = [
        action(
            "ACT-1", candidate_id="CAND-1", idempotency_key="IDEM-1", receipt=landed
        ),
        action(
            "ACT-2",
            candidate_id="CAND-2",
            idempotency_key="IDEM-2",
            receipt=rolled_back,
            target_ref=TARGET_B,
        ),
    ]
    report = run_concurrency_gate(
        actions=actions,
        interleavings=schedules("ACT-1", "ACT-2"),
        initial_revisions=INITIAL_REVISIONS,
        proposed=["CAND-1", "CAND-2"],
        generated=["CAND-1", "CAND-2"],
        evaluated=["CAND-1", "CAND-2"],
        persisted=["CAND-1"],
        terminal_cancelled=["CAND-2"],
        mutation_receipts=[
            mutation("CAND-1", landed["receipt_id"]),
            mutation("CAND-2", rolled_back["receipt_id"]),
        ],
    )

    assert report["reconciled"] is True
    require_concurrent_effect_gate(report)


def test_an_unobserved_effect_keeps_its_obligation_open() -> None:
    """An outcome nobody saw is not a failure and not a success."""
    receipt = effect_receipt("INT-1", "IDEM-1", UNKNOWN)
    settlement = settle_interleaving(
        actions=[
            action(
                "ACT-1",
                candidate_id="CAND-1",
                idempotency_key="IDEM-1",
                receipt=receipt,
            )
        ],
        events=lane("L1", "ACT-1"),
        initial_revisions=INITIAL_REVISIONS,
        interleaving_id="IL-1",
    )

    assert settlement["admitted"] is True
    assert settlement["ledger"]["unobserved_keys"] == ["IDEM-1"]
    assert settlement["ledger"]["committed_keys"] == []
    assert settlement["ledger"]["revisions"][TARGET_A] == REV_0


def test_chained_revisions_refuse_the_order_that_never_read_them() -> None:
    """A revision chain pins the order, so the schedule that inverts it is out."""
    first = effect_receipt("INT-1", "IDEM-1")
    second = effect_receipt("INT-2", "IDEM-2")
    actions = [
        action("ACT-1", candidate_id="CAND-1", idempotency_key="IDEM-1", receipt=first),
        action(
            "ACT-2",
            candidate_id="CAND-2",
            idempotency_key="IDEM-2",
            receipt=second,
            base_revision=REV_1,
            new_revision=REV_2,
        ),
    ]
    report = check_serializability(
        actions=actions,
        interleavings=schedules("ACT-1", "ACT-2"),
        initial_revisions=INITIAL_REVISIONS,
    )

    assert report["admitted_interleaving_ids"] == ["IL-SERIAL", "IL-CROSSED"]
    assert report["serializable"] is True
    assert report["settlements"][0]["ledger"]["revisions"][TARGET_A] == REV_2


def test_the_crossed_schedule_settles_the_same_ledger_as_the_serial_one() -> None:
    actions = disjoint_actions()
    settlements = [
        settle_interleaving(
            actions=actions,
            events=events,
            initial_revisions=INITIAL_REVISIONS,
            interleaving_id=name,
        )
        for name, events in (
            ("IL-SERIAL", serial("ACT-1", "ACT-2")),
            ("IL-CROSSED", interleaved("ACT-1", "ACT-2")),
        )
    ]

    assert settlements[0]["ledger_hash"] == settlements[1]["ledger_hash"]
    assert settlements[0]["interleaving_id"] != settlements[1]["interleaving_id"]


def test_the_gate_is_deterministic() -> None:
    payload = disjoint_gate() | {"gate_id": "ECG-1"}

    assert run_concurrency_gate(**payload) == run_concurrency_gate(**payload)


def test_the_gate_does_not_mutate_its_inputs() -> None:
    payload = disjoint_gate()
    before = canonical_json(
        {"actions": payload["actions"], "interleavings": payload["interleavings"]}
    )
    run_concurrency_gate(**payload)
    after = canonical_json(
        {"actions": payload["actions"], "interleavings": payload["interleavings"]}
    )

    assert before == after


def test_a_payload_fingerprint_ignores_key_order() -> None:
    """Two spellings of one request are one request."""
    assert fingerprint_payload({"a": 1, "b": 2}) == fingerprint_payload(
        {"b": 2, "a": 1}
    )
    assert fingerprint_payload({"a": 1}) != fingerprint_payload({"a": 2})


def test_two_attempts_differing_only_in_action_id_share_a_fingerprint() -> None:
    first, retry = retry_actions()

    assert first["payload"] == retry["payload"]
    assert (
        first["effect_receipt"]["receipt_id"] == retry["effect_receipt"]["receipt_id"]
    )
