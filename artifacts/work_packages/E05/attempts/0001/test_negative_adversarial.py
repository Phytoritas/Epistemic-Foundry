"""negative_and_adversarial_tests — every way a side effect could hide is refused.

The engine exists because a count can hide three different bugs, so each is
attacked separately: an effect with no candidate, a candidate with no effect, a
mutation with no lineage, a dangling receipt reference, an unobserved outcome
counted as done, and a ledger that disagrees with the pipeline about whether a
candidate persisted.  Each refusal must name its own failure class rather than
collapse into "unreconciled".
"""

from __future__ import annotations

import pytest

from epistemic_foundry.effects.v4_e05 import (
    EffectReconciliationError,
    reconcile_effect_ledger,
    require_effect_reconciliation,
)
from fixtures import (
    FAILED,
    SUCCEEDED,
    UNKNOWN,
    clean_fanout,
    effect,
    mutation,
)


def refused(payload: dict) -> EffectReconciliationError:
    with pytest.raises(EffectReconciliationError) as caught:
        require_effect_reconciliation(reconcile_effect_ledger(**payload))
    return caught.value


def raises_on_build(payload: dict) -> EffectReconciliationError:
    with pytest.raises(EffectReconciliationError) as caught:
        reconcile_effect_ledger(**payload)
    return caught.value


def test_an_effect_belonging_to_no_candidate_is_an_orphan() -> None:
    payload = clean_fanout()
    payload["effect_receipts"] = [*payload["effect_receipts"], effect("INT-STRAY")]

    error = refused(payload)
    assert error.code == "ORPHAN_SIDE_EFFECT"
    assert len(error.context["orphan_effect_receipts"]) == 1


def test_a_generated_candidate_without_a_mutation_receipt_is_refused() -> None:
    # Drop the effect too, so the only finding is the missing lineage rather
    # than the orphaned effect that dropping the mutation alone would leave.
    payload = clean_fanout()
    payload["mutation_receipts"] = payload["mutation_receipts"][:1]
    payload["effect_receipts"] = payload["effect_receipts"][:1]

    error = refused(payload)
    assert error.code == "MUTATION_RECEIPT_MISSING"
    assert error.context["unreceipted_candidates"] == ["CAND-2"]


def test_a_mutation_producing_an_unproposed_candidate_is_refused() -> None:
    payload = clean_fanout()
    stray = effect("INT-STRAY")
    payload["effect_receipts"] = [*payload["effect_receipts"], stray]
    payload["mutation_receipts"] = [
        *payload["mutation_receipts"],
        mutation("CAND-GHOST", stray["receipt_id"]),
    ]

    error = refused(payload)
    assert error.code == "MUTATION_WITHOUT_PROVENANCE"
    assert error.context["orphan_mutation_receipts"] == ["CAND-GHOST"]


def test_a_mutation_referencing_a_missing_effect_is_refused() -> None:
    payload = clean_fanout()
    payload["mutation_receipts"] = [
        mutation("CAND-1", "EF-GONE"),
        payload["mutation_receipts"][1],
    ]

    error = refused(payload)
    assert error.code == "EFFECT_RECEIPT_MISSING"
    assert error.context["dangling_effect_references"] == ["CAND-1"]


def test_an_unobserved_effect_leaves_its_candidate_unresolved() -> None:
    first = effect("INT-1", UNKNOWN)
    second = effect("INT-2")
    payload = {
        "proposed": ["CAND-1", "CAND-2"],
        "generated": ["CAND-1", "CAND-2"],
        "evaluated": ["CAND-1", "CAND-2"],
        "persisted": ["CAND-1", "CAND-2"],
        "effect_receipts": [first, second],
        "mutation_receipts": [
            mutation("CAND-1", first["receipt_id"]),
            mutation("CAND-2", second["receipt_id"]),
        ],
    }

    error = refused(payload)
    assert error.code == "EFFECT_UNRESOLVED"
    assert error.context["unresolved_candidates"] == ["CAND-1"]


def test_an_unknown_effect_cannot_be_relabelled_as_resolved() -> None:
    receipt = effect("INT-1", UNKNOWN)
    receipt["reconciliation_required"] = False

    payload = clean_fanout()
    payload["effect_receipts"] = [receipt, payload["effect_receipts"][1]]

    error = raises_on_build(payload)
    assert error.code == "RECONCILIATION_FLAG_INCONSISTENT"


def test_a_succeeded_effect_cannot_claim_it_needs_reconciliation() -> None:
    receipt = effect("INT-1")
    receipt["reconciliation_required"] = True

    payload = clean_fanout()
    payload["effect_receipts"] = [receipt, payload["effect_receipts"][1]]

    error = raises_on_build(payload)
    assert error.code == "RECONCILIATION_FLAG_INCONSISTENT"


def test_the_ledger_and_the_pipeline_must_agree_about_persistence() -> None:
    first = effect("INT-1", FAILED)
    second = effect("INT-2")
    payload = {
        "proposed": ["CAND-1", "CAND-2"],
        "generated": ["CAND-1", "CAND-2"],
        "evaluated": ["CAND-1", "CAND-2"],
        # The pipeline claims both persisted; the ledger says one failed.
        "persisted": ["CAND-1", "CAND-2"],
        "effect_receipts": [first, second],
        "mutation_receipts": [
            mutation("CAND-1", first["receipt_id"]),
            mutation("CAND-2", second["receipt_id"]),
        ],
    }

    error = refused(payload)
    assert error.code == "LEDGER_PIPELINE_DISAGREEMENT"
    finding = error.context["disagreements"][0]
    assert finding["candidate_id"] == "CAND-1"
    assert finding["effect_status"] == FAILED
    assert finding["pipeline_persisted"] is True


def test_a_pipeline_that_drops_a_persisted_candidate_is_refused() -> None:
    payload = clean_fanout()
    payload["persisted"] = ["CAND-1"]

    error = refused(payload)
    assert error.code in {
        "LEDGER_PIPELINE_DISAGREEMENT",
        "CANDIDATE_FANOUT_UNRECONCILED",
    }


def test_a_vanished_candidate_stops_the_ledger_agreement_from_saving_it() -> None:
    first = effect("INT-1")
    payload = {
        "proposed": ["CAND-1", "CAND-2"],
        "generated": ["CAND-1"],
        "evaluated": ["CAND-1"],
        "persisted": ["CAND-1"],
        "effect_receipts": [first],
        "mutation_receipts": [mutation("CAND-1", first["receipt_id"])],
    }

    error = refused(payload)
    assert error.code == "CANDIDATE_FANOUT_UNRECONCILED"
    assert error.context["missing"] == ["CAND-2"]


def test_two_effect_receipts_cannot_share_an_id() -> None:
    payload = clean_fanout()
    payload["effect_receipts"] = [
        payload["effect_receipts"][0],
        payload["effect_receipts"][0],
    ]

    error = raises_on_build(payload)
    assert error.code == "DUPLICATE_EFFECT_RECEIPT"


def test_two_mutation_receipts_cannot_share_an_id() -> None:
    payload = clean_fanout()
    payload["mutation_receipts"] = [
        payload["mutation_receipts"][0],
        payload["mutation_receipts"][0],
    ]

    error = raises_on_build(payload)
    assert error.code == "DUPLICATE_MUTATION_RECEIPT"


def test_one_candidate_cannot_be_the_output_of_two_mutations() -> None:
    payload = clean_fanout()
    second_effect = effect("INT-3")
    payload["effect_receipts"] = [*payload["effect_receipts"], second_effect]
    payload["mutation_receipts"] = [
        *payload["mutation_receipts"],
        mutation("CAND-1", second_effect["receipt_id"], parent_id="CAND-2"),
    ]

    error = raises_on_build(payload)
    assert error.code == "CANDIDATE_MUTATED_TWICE"
    assert error.context["candidate_id"] == "CAND-1"


def test_an_effect_receipt_missing_a_required_field_is_refused() -> None:
    payload = clean_fanout()
    receipt = dict(payload["effect_receipts"][0])
    del receipt["status"]
    payload["effect_receipts"] = [receipt, payload["effect_receipts"][1]]

    error = raises_on_build(payload)
    assert error.code == "FIELD_SET_INVALID"
    assert error.context["missing"] == ["status"]


def test_a_mutation_receipt_missing_a_required_field_is_refused() -> None:
    payload = clean_fanout()
    receipt = dict(payload["mutation_receipts"][0])
    del receipt["effect_receipt_id"]
    payload["mutation_receipts"] = [receipt, payload["mutation_receipts"][1]]

    error = raises_on_build(payload)
    assert error.code == "FIELD_SET_INVALID"


def test_a_non_mapping_receipt_is_refused() -> None:
    payload = clean_fanout()
    payload["effect_receipts"] = ["not a receipt", payload["effect_receipts"][1]]

    error = raises_on_build(payload)
    assert error.code == "INPUT_INVALID"


def test_a_status_the_table_does_not_map_is_refused() -> None:
    payload = clean_fanout()
    receipt = dict(payload["effect_receipts"][0])
    receipt["status"] = "INVENTED"
    payload["effect_receipts"] = [receipt, payload["effect_receipts"][1]]

    error = raises_on_build(payload)
    assert error.code == "STATUS_UNMAPPED"


def test_a_candidate_appearing_without_being_proposed_is_refused() -> None:
    payload = clean_fanout()
    payload["generated"] = ["CAND-1", "CAND-2", "CAND-INVENTED"]

    error = refused(payload)
    assert error.code == "CANDIDATE_FANOUT_UNRECONCILED"
    assert error.context["unknown_identities"]


def test_the_engine_reports_each_failure_class_separately() -> None:
    payload = clean_fanout()
    payload["mutation_receipts"] = payload["mutation_receipts"][:1]
    payload["effect_receipts"] = [*payload["effect_receipts"], effect("INT-STRAY")]
    report = reconcile_effect_ledger(**payload)

    assert report["unreceipted_candidates"] == ["CAND-2"]
    assert len(report["orphan_effect_receipts"]) == 2
    assert report["reconciled"] is False


def test_a_successful_effect_status_is_what_marks_persistence() -> None:
    payload = clean_fanout()
    report = reconcile_effect_ledger(**payload)

    assert report["reconciled"] is True
    assert all(receipt["status"] == SUCCEEDED for receipt in payload["effect_receipts"])
