"""unit_and_contract_tests — the gate composes the sealed surfaces correctly.

These tests drive the happy path of every gate: a version is bound from one
coherent set of sealed surfaces, and a plan, a lane receipt, a candidate
execution and an evaluator-feedback surface are each admitted against it.  The
contract is that admission is *derived* from the composed records — the plan's
own version fields, the receipt's own results, the firewall's own leakage set —
rather than asserted by the caller.
"""

from __future__ import annotations

from epistemic_foundry.evidence.v4_k06 import (
    EXECUTION_RECEIPT_PREFIX,
    FEEDBACK_RECEIPT_PREFIX,
    RESULTS_RECEIPT_PREFIX,
    RETRIEVAL_RECEIPT_PREFIX,
    admit_candidate_execution_against_version,
    admit_evaluator_feedback_against_version,
    admit_retrieval_against_version,
    admit_search_results_against_version,
    bind_evidence_holdout_version,
    require_version_identity,
)
from fixtures import (
    HIDDEN_ID,
    VIS_1,
    VIS_2,
    execution_arguments,
    feedback_arguments,
    plan,
    searched_receipt,
    sentinel_receipt,
    snapshot,
    version_arguments,
)


def _bound(pinned=None):
    pinned = pinned if pinned is not None else snapshot()
    arguments = version_arguments(pinned)
    return arguments, bind_evidence_holdout_version(**arguments)


def test_a_bound_version_re_derives_its_own_identity() -> None:
    _, version = _bound()
    assert require_version_identity(version) == version


def test_a_retrieval_plan_over_visible_subjects_is_admitted() -> None:
    pinned = snapshot()
    _, version = _bound(pinned)
    declared = plan(pinned, subject_document_ids=[VIS_1, VIS_2])
    receipt = admit_retrieval_against_version(version=version, plan=declared)
    assert receipt["receipt_id"].startswith(RETRIEVAL_RECEIPT_PREFIX)
    assert receipt["version_id"] == version["version_id"]
    assert receipt["plan_id"] == declared["plan_id"]
    assert receipt["admitted_subject_document_ids"] == [VIS_1, VIS_2]


def test_an_execution_lane_receipt_over_visible_results_is_admitted() -> None:
    pinned = snapshot()
    _, version = _bound(pinned)
    declared = plan(pinned)
    receipt = searched_receipt(declared, pinned, result_document_ids=[VIS_1])
    admission = admit_search_results_against_version(version=version, receipt=receipt)
    assert admission["receipt_id"].startswith(RESULTS_RECEIPT_PREFIX)
    assert admission["source_receipt_id"] == receipt["receipt_id"]
    assert admission["admitted_result_ids"] == [VIS_1]


def test_a_sentinel_lane_receipt_pins_no_snapshot_and_is_admitted() -> None:
    pinned = snapshot()
    _, version = _bound(pinned)
    declared = plan(pinned)
    receipt = sentinel_receipt(declared, pinned, lane="lexical")
    # A truthful "never looked" sentinel carries no snapshot hash, so it must
    # not be read as a stale-version reuse.
    assert receipt["corpus_snapshot_hash"] is None
    admission = admit_search_results_against_version(version=version, receipt=receipt)
    assert admission["admitted_result_ids"] == []


def test_a_candidate_execution_under_the_bound_evaluator_is_admitted() -> None:
    arguments, version = _bound()
    admission = admit_candidate_execution_against_version(
        **execution_arguments(version, arguments["firewall"])
    )
    assert admission["receipt_id"].startswith(EXECUTION_RECEIPT_PREFIX)
    assert admission["evaluator_bundle_hash"] == version["evaluator_bundle_hash"]
    assert admission["qualification_id"] == "EXQ-K06-1"


def test_clean_evaluator_feedback_is_admitted_with_its_audit() -> None:
    arguments, version = _bound()
    admission = admit_evaluator_feedback_against_version(
        **feedback_arguments(version, arguments["firewall"])
    )
    assert admission["receipt_id"].startswith(FEEDBACK_RECEIPT_PREFIX)
    audit = admission["leakage_audit"]
    assert audit["detected_exposures"] == []
    assert audit["required_actions"] == []
    # The audit id is deterministic, not the builder's random default, so the
    # whole receipt replays.
    assert admission["leakage_audit_id"] == audit["leakage_audit_id"]


def test_admission_receipts_bind_the_version_they_were_checked_against() -> None:
    pinned = snapshot()
    arguments, version = _bound(pinned)
    declared = plan(pinned)
    receipts = [
        admit_retrieval_against_version(version=version, plan=declared),
        admit_search_results_against_version(
            version=version, receipt=searched_receipt(declared, pinned)
        ),
        admit_candidate_execution_against_version(
            **execution_arguments(version, arguments["firewall"])
        ),
        admit_evaluator_feedback_against_version(
            **feedback_arguments(version, arguments["firewall"])
        ),
    ]
    for receipt in receipts:
        assert receipt["version_id"] == version["version_id"]
        assert receipt["version_hash"] == version["version_hash"]


def test_a_plan_naming_a_concealed_subject_is_still_buildable_upstream() -> None:
    # The upstream O05 surface has no notion of the partition, so it will build
    # a plan whose subject is a hidden document; the K06 gate is the only place
    # that refuses it.  This asserts the division of labour the gate relies on.
    pinned = snapshot()
    declared = plan(pinned, subject_document_ids=[VIS_1, HIDDEN_ID])
    assert HIDDEN_ID in declared["subject_document_ids"]
