"""negative_and_adversarial_tests — every way the effect surface can be broken.

Each refusal here is asserted by code *and* by the pair it names.  A gate that
reported "a conflict occurred" would leave the reader to find which two actions
collided, and in a fan-out of dozens that is the whole cost of the failure.

The adversarial half is the interesting one: the inputs below are not malformed,
they are plausible.  A key reused for a second request, a retry that quietly
mints its own receipt, one key spanning two targets, a schedule that omits the
action it would have lost — each is what a runtime that *almost* implements
idempotency actually produces, and each must be named rather than absorbed.
"""

from __future__ import annotations

import pytest
from epistemic_foundry.effects.v4_e06 import (
    BEGIN,
    COMMIT,
    EFFECT,
    ConcurrentEffectError,
    check_serializability,
    require_concurrent_effect_gate,
    run_concurrency_gate,
    settle_interleaving,
)
from fixtures import (
    INITIAL_REVISIONS,
    REV_0,
    REV_1,
    REV_2,
    TARGET_A,
    TARGET_B,
    UNKNOWN,
    action,
    disjoint_actions,
    disjoint_gate,
    effect_receipt,
    interleaved,
    lane,
    schedules,
    serial,
)


def _settle(actions, events, **kwargs):
    return settle_interleaving(
        actions=actions,
        events=events,
        initial_revisions=INITIAL_REVISIONS,
        interleaving_id="IL-1",
        **kwargs,
    )


def _first_refusal(settlement):
    assert settlement["admitted"] is False
    assert len(settlement["refusals"]) == 1
    return settlement["refusals"][0]


def _two_actions_on_one_key(*, payloads, receipts, targets=(TARGET_A, TARGET_B)):
    return [
        action(
            f"ACT-{index + 1}",
            candidate_id=f"CAND-{index + 1}",
            idempotency_key="IDEM-1",
            receipt=receipts[index],
            target_ref=targets[index],
            payload=payloads[index],
        )
        for index in range(2)
    ]


def test_one_key_with_two_payloads_is_refused() -> None:
    receipt = effect_receipt("INT-1", "IDEM-1")
    settlement = _settle(
        _two_actions_on_one_key(
            payloads=[{"claim": "one"}, {"claim": "two"}],
            receipts=[receipt, receipt],
        ),
        serial("ACT-1", "ACT-2"),
    )
    refusal = _first_refusal(settlement)

    assert refusal["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert refusal["conflicting_pair"] == ["ACT-1", "ACT-2"]
    assert refusal["context"]["idempotency_key"] == "IDEM-1"


def test_a_reused_key_names_both_fingerprints() -> None:
    receipt = effect_receipt("INT-1", "IDEM-1")
    settlement = _settle(
        _two_actions_on_one_key(
            payloads=[{"claim": "one"}, {"claim": "two"}],
            receipts=[receipt, receipt],
        ),
        serial("ACT-1", "ACT-2"),
    )
    context = _first_refusal(settlement)["context"]

    assert context["bound_fingerprint"] != context["arriving_fingerprint"]


def test_one_key_minting_two_receipts_is_refused() -> None:
    """The duplicated external effect the key exists to prevent."""
    first = effect_receipt("INT-1", "IDEM-1")
    second = effect_receipt("INT-2", "IDEM-1")
    settlement = _settle(
        _two_actions_on_one_key(
            payloads=[{"claim": "one"}, {"claim": "one"}], receipts=[first, second]
        ),
        serial("ACT-1", "ACT-2"),
    )
    refusal = _first_refusal(settlement)

    assert refusal["code"] == "DOUBLE_MINT"
    assert refusal["conflicting_pair"] == [first["receipt_id"], second["receipt_id"]]


def test_a_lost_update_names_the_pair_that_collided() -> None:
    first = effect_receipt("INT-1", "IDEM-1")
    second = effect_receipt("INT-2", "IDEM-2")
    actions = [
        action("ACT-1", candidate_id="CAND-1", idempotency_key="IDEM-1", receipt=first),
        action(
            "ACT-2",
            candidate_id="CAND-2",
            idempotency_key="IDEM-2",
            receipt=second,
            new_revision=REV_2,
        ),
    ]
    refusal = _first_refusal(_settle(actions, interleaved("ACT-1", "ACT-2")))

    assert refusal["code"] == "LOST_UPDATE"
    assert refusal["conflicting_pair"] == ["ACT-1", "ACT-2"]
    assert refusal["context"] == {
        "declared_base": REV_0,
        "target_ref": TARGET_A,
        "target_revision": REV_1,
    }


def test_a_write_over_an_unobserved_effect_is_refused() -> None:
    unobserved = effect_receipt("INT-1", "IDEM-1", UNKNOWN)
    other = effect_receipt("INT-2", "IDEM-2")
    actions = [
        action(
            "ACT-1", candidate_id="CAND-1", idempotency_key="IDEM-1", receipt=unobserved
        ),
        action(
            "ACT-2",
            candidate_id="CAND-2",
            idempotency_key="IDEM-2",
            receipt=other,
            new_revision=REV_2,
        ),
    ]
    refusal = _first_refusal(_settle(actions, serial("ACT-1", "ACT-2")))

    assert refusal["code"] == "UNOBSERVED_STATE_ADVANCED"
    assert refusal["conflicting_pair"] == ["ACT-1", "ACT-2"]
    assert refusal["context"]["status"] == UNKNOWN


def test_a_second_unobserved_write_is_refused_too() -> None:
    """Stacking unknowns on one target is the hazard, not a side note."""
    first = effect_receipt("INT-1", "IDEM-1", UNKNOWN)
    second = effect_receipt("INT-2", "IDEM-2", UNKNOWN)
    actions = [
        action("ACT-1", candidate_id="CAND-1", idempotency_key="IDEM-1", receipt=first),
        action(
            "ACT-2", candidate_id="CAND-2", idempotency_key="IDEM-2", receipt=second
        ),
    ]
    refusal = _first_refusal(_settle(actions, serial("ACT-1", "ACT-2")))

    assert refusal["code"] == "UNOBSERVED_STATE_ADVANCED"


def test_a_base_revision_the_target_never_held_is_refused() -> None:
    receipt = effect_receipt("INT-1", "IDEM-1")
    actions = [
        action(
            "ACT-1",
            candidate_id="CAND-1",
            idempotency_key="IDEM-1",
            receipt=receipt,
            base_revision=REV_2,
        )
    ]
    refusal = _first_refusal(_settle(actions, lane("L1", "ACT-1")))

    assert refusal["code"] == "STALE_BASE_REVISION"
    assert refusal["conflicting_pair"] == []
    assert refusal["context"]["declared_base"] == REV_2


def test_one_key_spanning_two_targets_makes_the_ledger_schedule_dependent() -> None:
    """The dedup window swallows a distinct effect, so the ledger diverges."""
    receipt = effect_receipt("INT-1", "IDEM-1")
    report = check_serializability(
        actions=_two_actions_on_one_key(
            payloads=[{"claim": "one"}, {"claim": "one"}], receipts=[receipt, receipt]
        ),
        interleavings=schedules("ACT-1", "ACT-2"),
        initial_revisions=INITIAL_REVISIONS,
    )

    assert report["serializable"] is False
    assert report["divergent_pair"] == ["IL-SERIAL", "IL-REVERSED"]
    assert report["agreed_ledger_hash"] is None


def test_a_divergent_ledger_is_refused_by_code() -> None:
    receipt = effect_receipt("INT-1", "IDEM-1")
    report = run_concurrency_gate(
        actions=_two_actions_on_one_key(
            payloads=[{"claim": "one"}, {"claim": "one"}], receipts=[receipt, receipt]
        ),
        interleavings=schedules("ACT-1", "ACT-2"),
        initial_revisions=INITIAL_REVISIONS,
        proposed=["CAND-1", "CAND-2"],
        generated=["CAND-1", "CAND-2"],
        evaluated=["CAND-1", "CAND-2"],
        persisted=["CAND-1", "CAND-2"],
    )

    assert report["reconciled"] is False
    with pytest.raises(ConcurrentEffectError) as caught:
        require_concurrent_effect_gate(report)

    assert caught.value.code == "INTERLEAVING_DIVERGENT"
    assert caught.value.context["divergent_pair"] == ["IL-SERIAL", "IL-REVERSED"]


def test_a_refused_schedule_refuses_the_whole_run() -> None:
    """One schedule the runtime can produce is one the runtime does produce."""
    first = effect_receipt("INT-1", "IDEM-1")
    second = effect_receipt("INT-2", "IDEM-2")
    report = run_concurrency_gate(
        actions=[
            action(
                "ACT-1", candidate_id="CAND-1", idempotency_key="IDEM-1", receipt=first
            ),
            action(
                "ACT-2",
                candidate_id="CAND-2",
                idempotency_key="IDEM-2",
                receipt=second,
                new_revision=REV_2,
            ),
        ],
        interleavings=schedules("ACT-1", "ACT-2"),
        initial_revisions=INITIAL_REVISIONS,
        proposed=["CAND-1", "CAND-2"],
        generated=["CAND-1", "CAND-2"],
        evaluated=["CAND-1", "CAND-2"],
        persisted=["CAND-1", "CAND-2"],
    )

    with pytest.raises(ConcurrentEffectError) as caught:
        require_concurrent_effect_gate(report)

    assert caught.value.code == "LOST_UPDATE"
    assert caught.value.context["conflicting_pair"] == ["ACT-1", "ACT-2"]


def test_an_e05_refusal_is_carried_out_as_an_unreconciled_gate() -> None:
    """Concurrency can hold while the run's accounting does not."""
    payload = disjoint_gate()
    payload["mutation_receipts"] = []
    report = run_concurrency_gate(**payload)

    assert report["concurrency"]["serializable"] is True
    assert report["reconciled"] is False
    with pytest.raises(ConcurrentEffectError) as caught:
        require_concurrent_effect_gate(report)

    assert caught.value.code == "GATE_UNRECONCILED"
    assert caught.value.context["effect_reconciliation_refusal"]["code"]


def test_a_schedule_omitting_an_action_cannot_hide_its_conflict() -> None:
    first = effect_receipt("INT-1", "IDEM-1")
    second = effect_receipt("INT-2", "IDEM-2")
    actions = [
        action("ACT-1", candidate_id="CAND-1", idempotency_key="IDEM-1", receipt=first),
        action(
            "ACT-2",
            candidate_id="CAND-2",
            idempotency_key="IDEM-2",
            receipt=second,
            new_revision=REV_2,
        ),
    ]

    with pytest.raises(ConcurrentEffectError) as caught:
        _settle(actions, lane("L1", "ACT-1"))

    assert caught.value.code == "ACTION_UNREPLAYED"
    assert caught.value.context["unreplayed"] == ["ACT-2"]


def test_a_lane_running_two_actions_at_once_is_refused() -> None:
    events = [
        {"action_id": "ACT-1", "lane": "L1", "phase": BEGIN},
        {"action_id": "ACT-2", "lane": "L1", "phase": BEGIN},
    ]

    with pytest.raises(ConcurrentEffectError) as caught:
        _settle(disjoint_actions(), events)

    assert caught.value.code == "LANE_BUSY"
    assert caught.value.context["open"] == "ACT-1"


def test_an_effect_before_its_begin_is_refused() -> None:
    events = [{"action_id": "ACT-1", "lane": "L1", "phase": EFFECT}]

    with pytest.raises(ConcurrentEffectError) as caught:
        _settle(disjoint_actions(), events)

    assert caught.value.code == "PHASE_OUT_OF_ORDER"


def test_a_commit_that_skips_its_effect_is_refused() -> None:
    events = [
        {"action_id": "ACT-1", "lane": "L1", "phase": BEGIN},
        {"action_id": "ACT-1", "lane": "L1", "phase": COMMIT},
    ]

    with pytest.raises(ConcurrentEffectError) as caught:
        _settle(disjoint_actions(), events)

    assert caught.value.code == "PHASE_OUT_OF_ORDER"


def test_an_action_beginning_twice_is_refused() -> None:
    events = lane("L1", "ACT-1") + [
        {"action_id": "ACT-1", "lane": "L2", "phase": BEGIN}
    ]

    with pytest.raises(ConcurrentEffectError) as caught:
        _settle(disjoint_actions(), events)

    assert caught.value.code == "PHASE_OUT_OF_ORDER"


def test_a_schedule_ending_mid_action_is_refused() -> None:
    events = lane("L1", "ACT-1")[:2] + lane("L2", "ACT-2")

    with pytest.raises(ConcurrentEffectError) as caught:
        _settle(disjoint_actions(), events)

    assert caught.value.code == "LANE_UNCLOSED"


def test_an_undeclared_phase_is_refused() -> None:
    events = [{"action_id": "ACT-1", "lane": "L1", "phase": "maybe"}]

    with pytest.raises(ConcurrentEffectError) as caught:
        _settle(disjoint_actions(), events)

    assert caught.value.code == "PHASE_UNDECLARED"


def test_an_event_naming_an_unknown_action_is_refused() -> None:
    events = [{"action_id": "ACT-9", "lane": "L1", "phase": BEGIN}]

    with pytest.raises(ConcurrentEffectError) as caught:
        _settle(disjoint_actions(), events)

    assert caught.value.code == "ACTION_UNKNOWN"


def test_two_records_claiming_one_action_id_are_refused() -> None:
    actions = disjoint_actions()
    actions[1] = dict(actions[1]) | {"action_id": "ACT-1"}

    with pytest.raises(ConcurrentEffectError) as caught:
        _settle(actions, serial("ACT-1", "ACT-1"))

    assert caught.value.code == "ACTION_DUPLICATED"


def test_a_receipt_bound_to_another_key_is_refused() -> None:
    """The receipt would be evidence for a request this action never made."""
    actions = disjoint_actions()
    actions[0] = dict(actions[0]) | {"idempotency_key": "IDEM-9"}

    with pytest.raises(ConcurrentEffectError) as caught:
        _settle(actions, serial("ACT-1", "ACT-2"))

    assert caught.value.code == "KEY_RECEIPT_UNBOUND"


def test_a_target_with_no_declared_starting_revision_is_refused() -> None:
    with pytest.raises(ConcurrentEffectError) as caught:
        settle_interleaving(
            actions=disjoint_actions(),
            events=serial("ACT-1", "ACT-2"),
            initial_revisions={TARGET_A: REV_0},
            interleaving_id="IL-1",
        )

    assert caught.value.code == "REVISION_UNDECLARED"
    assert caught.value.context["missing"] == [TARGET_B]


def test_a_gate_with_no_schedule_proves_nothing_and_says_so() -> None:
    with pytest.raises(ConcurrentEffectError) as caught:
        check_serializability(
            actions=disjoint_actions(),
            interleavings=[],
            initial_revisions=INITIAL_REVISIONS,
        )

    assert caught.value.code == "INTERLEAVINGS_MISSING"


def test_two_schedules_sharing_an_id_are_refused() -> None:
    with pytest.raises(ConcurrentEffectError) as caught:
        check_serializability(
            actions=disjoint_actions(),
            interleavings=[
                {"events": serial("ACT-1", "ACT-2"), "interleaving_id": "IL-1"},
                {"events": serial("ACT-2", "ACT-1"), "interleaving_id": "IL-1"},
            ],
            initial_revisions=INITIAL_REVISIONS,
        )

    assert caught.value.code == "INTERLEAVING_DUPLICATED"


def test_a_gate_with_no_action_is_refused() -> None:
    with pytest.raises(ConcurrentEffectError) as caught:
        _settle([], [])

    assert caught.value.code == "INPUT_INVALID"


def test_an_action_missing_a_field_is_refused() -> None:
    actions = disjoint_actions()
    del actions[0]["base_revision"]

    with pytest.raises(ConcurrentEffectError) as caught:
        _settle(actions, serial("ACT-1", "ACT-2"))

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context["missing"] == ["base_revision"]


def test_a_payload_that_cannot_be_canonicalized_is_refused() -> None:
    actions = disjoint_actions()
    actions[0] = dict(actions[0]) | {"payload": {"weight": float("nan")}}

    with pytest.raises(ConcurrentEffectError) as caught:
        _settle(actions, serial("ACT-1", "ACT-2"))

    assert caught.value.code == "INPUT_INVALID"


def test_a_report_admitting_no_schedule_is_refused_even_with_no_refusal() -> None:
    """The guard behind the guard.

    In a whole report a refused schedule always carries its refusal, so this
    shape only arises when the settlements were filtered or truncated on the way
    here.  That is precisely when a fall-through would be silent, so the check
    exists and is asserted directly rather than assumed unreachable.
    """
    report = run_concurrency_gate(**disjoint_gate())
    report["concurrency"] = dict(report["concurrency"]) | {
        "admitted_interleaving_ids": [],
        "settlements": [],
    }
    report["reconciled"] = False

    with pytest.raises(ConcurrentEffectError) as caught:
        require_concurrent_effect_gate(report)

    assert caught.value.code == "NO_INTERLEAVING_ADMITTED"


def test_a_report_without_its_concurrency_check_is_refused() -> None:
    with pytest.raises(ConcurrentEffectError) as caught:
        require_concurrent_effect_gate({"reconciled": True})

    assert caught.value.code == "INPUT_INVALID"


def test_a_report_marked_unreconciled_without_a_finding_is_refused() -> None:
    """No refusal, no divergence, and still not reconciled: say so, do not pass."""
    report = run_concurrency_gate(**disjoint_gate())
    report["reconciled"] = False

    with pytest.raises(ConcurrentEffectError) as caught:
        require_concurrent_effect_gate(report)

    assert caught.value.code == "GATE_INCOMPLETE"
