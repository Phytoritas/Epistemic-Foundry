"""negative_and_adversarial_tests — every refusal, including every leakage path.

This gate exists to refuse, so its refusals are the contract.  Every declared
finding code is exercised here, and the three the invariant turns on — a stale
evidence/holdout version, a hidden-holdout exposure, and evaluator feedback
leaking back into the candidate or the search — are exercised from more than one
angle, including against a *lying firewall* that reports the holdout is
reachable.  The gate must re-verify rather than trust the surface it composes.
"""

from __future__ import annotations

import copy

import pytest

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evidence.v4_k06 import (
    FINDING_CODES,
    admit_candidate_execution_against_version,
    admit_evaluator_feedback_against_version,
    admit_retrieval_against_version,
    admit_search_results_against_version,
    bind_evidence_holdout_version,
    require_version_identity,
)
from epistemic_foundry.evidence.v4_k06.gate import LeakageGateError
from epistemic_foundry.verifier_firewall.firewall import VerifierFirewall
from fixtures import (
    ADVERSARIAL_ID,
    AUDITOR,
    HIDDEN_ID,
    OOD_ID,
    VIS_1,
    VIS_2,
    boundary,
    evaluator_bundle,
    execution_arguments,
    feedback_arguments,
    firewall,
    foreign_partition,
    foreign_snapshot,
    holdout,
    partition,
    plan,
    searched_receipt,
    snapshot,
    version_arguments,
)


class _LyingFirewall(VerifierFirewall):
    """A firewall that falsely reports every holdout read is permitted."""

    def may_read_holdout(self, principal_id: str, role: str) -> bool:  # noqa: D401
        return True


def _refusal(code, fn) -> None:
    with pytest.raises(LeakageGateError) as excinfo:
        fn()
    assert excinfo.value.code == code, (code, excinfo.value.code, str(excinfo.value))


def _bound(pinned=None):
    pinned = pinned if pinned is not None else snapshot()
    arguments = version_arguments(pinned)
    return arguments, bind_evidence_holdout_version(**arguments)


# -- version binding refusals ---------------------------------------------


def test_a_snapshot_that_does_not_re_derive_is_refused() -> None:
    arguments = version_arguments()
    arguments["snapshot"] = dict(arguments["snapshot"])
    arguments["snapshot"]["snapshot_hash"] = "sha256:" + "0" * 64
    _refusal("SNAPSHOT_REFUSED", lambda: bind_evidence_holdout_version(**arguments))


def test_a_partition_from_another_snapshot_is_refused() -> None:
    pinned = snapshot()
    other = snapshot(corpus_id="CORPUS-OTHER")
    arguments = version_arguments(pinned)
    arguments["partition"] = partition(other)
    _refusal(
        "PARTITION_NOT_FROM_SNAPSHOT",
        lambda: bind_evidence_holdout_version(**arguments),
    )


def test_a_boundary_over_another_snapshot_is_refused() -> None:
    pinned = snapshot()
    other = snapshot(corpus_id="CORPUS-OTHER")
    arguments = version_arguments(pinned)
    arguments["boundary"] = boundary(other)
    _refusal(
        "BOUNDARY_NOT_FROM_SNAPSHOT",
        lambda: bind_evidence_holdout_version(**arguments),
    )


def test_a_holdout_not_drawn_from_the_snapshot_is_refused() -> None:
    pinned = snapshot()
    arguments = version_arguments(pinned)
    # A holdout sealed over genuinely different bytes binds handles this
    # snapshot cannot derive; K05 owns that refusal and the gate surfaces it.
    foreign = foreign_snapshot()
    foreign_split = foreign_partition(foreign)
    arguments["holdout"] = holdout(foreign, foreign_split)
    arguments["evaluator_bundle"] = evaluator_bundle(arguments["holdout"])
    arguments["firewall"] = firewall(
        arguments["holdout"], arguments["evaluator_bundle"]
    )
    _refusal(
        "HOLDOUT_NOT_FROM_SNAPSHOT",
        lambda: bind_evidence_holdout_version(**arguments),
    )


def test_a_firewall_guarding_a_different_holdout_is_refused() -> None:
    pinned = snapshot()
    arguments = version_arguments(pinned)
    # A different partition seals a different holdout; pairing it with the
    # snapshot's own bundle would mean the firewall guards material the bound
    # partition does not conceal.
    other_split = partition(
        pinned,
        visible_document_ids=[VIS_1],
        hidden_document_ids=[VIS_2, HIDDEN_ID],
        ood_document_ids=[OOD_ID],
        adversarial_document_ids=[ADVERSARIAL_ID],
    )
    other_holdout = holdout(pinned, other_split)
    other_bundle = evaluator_bundle(other_holdout)
    arguments["firewall"] = firewall(other_holdout, other_bundle)
    arguments["evaluator_bundle"] = other_bundle
    _refusal(
        "FIREWALL_HOLDOUT_MISMATCH",
        lambda: bind_evidence_holdout_version(**arguments),
    )


def test_a_bundle_that_drifted_from_the_firewall_is_refused() -> None:
    arguments = version_arguments()
    tampered = copy.deepcopy(arguments["evaluator_bundle"])
    tampered["evaluator_version"] = "9.9.9"
    tampered["bundle_hash"] = hash_excluding(tampered, "bundle_hash")
    arguments["evaluator_bundle"] = tampered
    # The recomputed hash no longer equals the firewall's sealed hash.
    _refusal(
        "FIREWALL_HOLDOUT_MISMATCH",
        lambda: bind_evidence_holdout_version(**arguments),
    )


def test_a_bundle_whose_content_drifted_under_its_hash_is_refused() -> None:
    arguments = version_arguments()
    tampered = copy.deepcopy(arguments["evaluator_bundle"])
    # Change the content but leave the recorded hash equal to the firewall's
    # sealed one: the equality check passes and the recompute catches the drift.
    tampered["evaluator_version"] = "9.9.9"
    arguments["evaluator_bundle"] = tampered
    _refusal(
        "EVALUATOR_BUNDLE_DRIFT",
        lambda: bind_evidence_holdout_version(**arguments),
    )


def test_a_manifest_leaving_a_candidate_surface_open_is_refused() -> None:
    arguments = version_arguments()
    tampered = copy.deepcopy(arguments["holdout"])
    tampered["candidate_access"] = True
    tampered["manifest_hash"] = hash_excluding(tampered, "manifest_hash")
    arguments["holdout"] = tampered
    _refusal("HOLDOUT_ACCESS_OPEN", lambda: bind_evidence_holdout_version(**arguments))


def test_a_lying_firewall_reporting_the_holdout_reachable_is_refused() -> None:
    arguments = version_arguments()
    liar = _LyingFirewall(
        arguments["evaluator_bundle"],
        arguments["holdout"],
        holdout_read_principal_ids=[AUDITOR],
    )
    arguments["firewall"] = liar
    _refusal("HOLDOUT_ACCESS_OPEN", lambda: bind_evidence_holdout_version(**arguments))


def test_an_empty_bound_at_is_refused() -> None:
    arguments = version_arguments()
    arguments["bound_at"] = "   "
    _refusal("INPUT_INVALID", lambda: bind_evidence_holdout_version(**arguments))


# -- admission refusals ----------------------------------------------------


def test_a_tampered_version_is_refused_at_admission() -> None:
    pinned = snapshot()
    _, version = _bound(pinned)
    tampered = dict(version)
    tampered["as_of_date"] = "1999-01-01"
    _refusal("VERSION_DRIFT", lambda: require_version_identity(tampered))
    _refusal(
        "VERSION_DRIFT",
        lambda: admit_retrieval_against_version(version=tampered, plan=plan(pinned)),
    )


def test_a_plan_pinning_another_evidence_version_is_refused() -> None:
    pinned = snapshot()
    other = snapshot(corpus_id="CORPUS-OTHER")
    _, version = _bound(pinned)
    stale = plan(other, subject_document_ids=[VIS_1, VIS_2])
    _refusal(
        "STALE_EVIDENCE_VERSION",
        lambda: admit_retrieval_against_version(version=version, plan=stale),
    )


def test_a_plan_naming_a_concealed_subject_is_refused() -> None:
    pinned = snapshot()
    _, version = _bound(pinned)
    exposing = plan(pinned, subject_document_ids=[VIS_1, HIDDEN_ID])
    _refusal(
        "HOLDOUT_EXPOSURE",
        lambda: admit_retrieval_against_version(version=version, plan=exposing),
    )


def test_a_plan_that_does_not_re_derive_is_refused() -> None:
    pinned = snapshot()
    _, version = _bound(pinned)
    broken = dict(plan(pinned))
    broken["plan_hash"] = "sha256:" + "0" * 64
    _refusal(
        "PLAN_REFUSED",
        lambda: admit_retrieval_against_version(version=version, plan=broken),
    )


def test_a_non_mapping_plan_is_refused() -> None:
    _, version = _bound()
    _refusal(
        "PLAN_REFUSED",
        lambda: admit_retrieval_against_version(version=version, plan="not-a-plan"),
    )


def test_a_lane_receipt_returning_a_concealed_document_is_refused() -> None:
    pinned = snapshot()
    _, version = _bound(pinned)
    exposing = searched_receipt(plan(pinned), pinned, result_document_ids=[HIDDEN_ID])
    _refusal(
        "HOLDOUT_EXPOSURE",
        lambda: admit_search_results_against_version(version=version, receipt=exposing),
    )


def test_a_lane_receipt_from_another_snapshot_is_refused() -> None:
    pinned = snapshot()
    other = snapshot(corpus_id="CORPUS-OTHER")
    _, version = _bound(pinned)
    stale = searched_receipt(plan(other), other, result_document_ids=[VIS_1])
    _refusal(
        "STALE_EVIDENCE_VERSION",
        lambda: admit_search_results_against_version(version=version, receipt=stale),
    )


def test_a_lane_receipt_that_fails_its_schema_is_refused() -> None:
    _, version = _bound()
    _refusal(
        "RECEIPT_REFUSED",
        lambda: admit_search_results_against_version(
            version=version, receipt={"lane": "mechanism"}
        ),
    )


def test_a_candidate_of_an_unqualified_kind_is_refused() -> None:
    arguments, version = _bound()
    call = execution_arguments(
        version, arguments["firewall"], candidate_kind="not-a-genome"
    )
    _refusal(
        "EXECUTION_REFUSED",
        lambda: admit_candidate_execution_against_version(**call),
    )


def test_a_candidate_qualified_against_another_evaluator_is_refused() -> None:
    pinned = snapshot()
    _, version = _bound(pinned)
    other = snapshot(corpus_id="CORPUS-OTHER")
    other_holdout = holdout(other, partition(other))
    other_bundle = evaluator_bundle(other_holdout, evaluator_version="9.9.9")
    other_firewall = firewall(other_holdout, other_bundle)
    call = execution_arguments(version, other_firewall)
    _refusal(
        "STALE_EVIDENCE_VERSION",
        lambda: admit_candidate_execution_against_version(**call),
    )


def test_evaluator_feedback_intersecting_the_holdout_is_refused() -> None:
    arguments, version = _bound()
    leaked_handle = version["concealed_partition_handles"][0]
    call = feedback_arguments(
        version,
        arguments["firewall"],
        feedback_artifact_ids=["FB-CLEAN", leaked_handle],
    )
    _refusal(
        "EVALUATOR_FEEDBACK_LEAKAGE",
        lambda: admit_evaluator_feedback_against_version(**call),
    )


def test_feedback_audited_against_another_evaluator_is_refused() -> None:
    pinned = snapshot()
    _, version = _bound(pinned)
    other = snapshot(corpus_id="CORPUS-OTHER")
    other_holdout = holdout(other, partition(other))
    other_bundle = evaluator_bundle(other_holdout, evaluator_version="9.9.9")
    other_firewall = firewall(other_holdout, other_bundle)
    call = feedback_arguments(version, other_firewall)
    _refusal(
        "STALE_EVIDENCE_VERSION",
        lambda: admit_evaluator_feedback_against_version(**call),
    )


def test_feedback_audit_missing_a_required_surface_is_refused() -> None:
    arguments, version = _bound()
    call = feedback_arguments(version, arguments["firewall"], surfaces_checked=["tool"])
    _refusal(
        "LEAKAGE_AUDIT_REFUSED",
        lambda: admit_evaluator_feedback_against_version(**call),
    )


def test_every_declared_finding_code_has_a_negative_test() -> None:
    # A guard against a code being declared but never exercised: this suite
    # names each one it drives, and the two access-open branches share a code.
    exercised = {
        "SNAPSHOT_REFUSED",
        "PARTITION_NOT_FROM_SNAPSHOT",
        "BOUNDARY_NOT_FROM_SNAPSHOT",
        "HOLDOUT_NOT_FROM_SNAPSHOT",
        "FIREWALL_HOLDOUT_MISMATCH",
        "EVALUATOR_BUNDLE_DRIFT",
        "HOLDOUT_ACCESS_OPEN",
        "INPUT_INVALID",
        "VERSION_DRIFT",
        "STALE_EVIDENCE_VERSION",
        "HOLDOUT_EXPOSURE",
        "PLAN_REFUSED",
        "RECEIPT_REFUSED",
        "EXECUTION_REFUSED",
        "EVALUATOR_FEEDBACK_LEAKAGE",
        "LEAKAGE_AUDIT_REFUSED",
    }
    assert exercised == set(FINDING_CODES)
