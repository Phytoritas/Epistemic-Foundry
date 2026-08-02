"""Negative and adversarial coverage for the O06 integration gate.

Every finding code the gate documents is exercised here, and a meta-test asserts
that the union of codes raised covers ``FINDING_CODES`` exactly, so a new refusal
added without a test fails the suite.  The adversarial cases are the ones the
gate exists for: a claim that never earned its search, a determination that
skipped a required source, a candidate role reaching for authority over its own
evaluation, and a tampered admissibility receipt.
"""

from __future__ import annotations

import copy

import fixtures as f
import pytest
from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.retrieval.v4_o05 import canonical_lane_order
from epistemic_foundry.retrieval.v4_o06 import (
    FINDING_CODES,
    SearchIntegrityRefused,
    build_search_completeness_certificate,
    evaluate_search_integrity_admissibility,
    require_certificate_identity,
)
from epistemic_foundry.retrieval.v4_o06 import gate as engine
from epistemic_foundry.verifier_firewall.firewall import CANDIDATE_GENERATING_ROLES

_RAISED: set[str] = set()


def _build(**overrides):
    args = f.certificate_arguments()
    args.update(overrides)
    return build_search_completeness_certificate(**args)


def _refuses(code: str, fn) -> None:
    with pytest.raises(SearchIntegrityRefused) as excinfo:
        fn()
    assert excinfo.value.code == code, (code, excinfo.value.code)
    _RAISED.add(excinfo.value.code)


# -- certificate reconciliation refusals ----------------------------------


def test_input_invalid_receipts() -> None:
    _refuses("INPUT_INVALID", lambda: _build(receipts=123))


def test_receipt_refused_on_invalid_receipt() -> None:
    receipts = f.receipts()
    broken = copy.deepcopy(receipts)
    broken[0].pop("lane")
    _refuses("RECEIPT_REFUSED", lambda: _build(receipts=broken))


def test_receipt_not_from_plan() -> None:
    receipts = f.receipts()
    foreign = copy.deepcopy(receipts)
    foreign[0]["plan_hash"] = "sha256:" + "1" * 64
    _refuses("RECEIPT_NOT_FROM_PLAN", lambda: _build(receipts=foreign))


def test_lane_undeclared_when_plan_omits_a_lane_disposition() -> None:
    """A receipt for a lane the plan does not disposition is refused.

    Constructed adversarially: the plan is re-identified without one lane's
    disposition and every receipt is rebound to it, so the receipt-plan binding
    check passes and the undeclared-lane check is the one that fires.
    """
    pinned = f.snapshot()
    declared = f.plan(pinned)
    order = canonical_lane_order()
    tampered = copy.deepcopy(declared)
    del tampered["lane_dispositions"][order[0]]
    body = {
        key: value
        for key, value in tampered.items()
        if key not in {"plan_id", "plan_hash"}
    }
    tampered["plan_id"] = "ERP-" + sha256_of_payload(body)[len("sha256:") :]
    tampered["plan_hash"] = hash_excluding(tampered, "plan_hash")
    rebound = [
        dict(receipt, plan_hash=tampered["plan_hash"])
        for receipt in f.receipts(declared, pinned)
    ]
    _refuses(
        "LANE_UNDECLARED",
        lambda: _build(plan=tampered, receipts=rebound),
    )


def test_lane_coverage_incomplete_when_a_lane_is_missing() -> None:
    _refuses("LANE_COVERAGE_INCOMPLETE", lambda: _build(receipts=f.receipts()[:-1]))


def test_lane_disposition_conflict() -> None:
    pinned = f.snapshot()
    declared = f.plan(pinned)
    order = canonical_lane_order()
    selected = set(declared["selected_lanes"])
    a_selected = next(lane for lane in order if lane in selected)
    a_sentinel = next(lane for lane in order if lane not in selected)
    receipts = f.receipts(declared, pinned)
    # Give the sentinel lane a searched-state receipt: what ran disagrees with
    # what the plan chose.
    receipts[order.index(a_sentinel)] = dict(
        f.searched_receipt(declared, pinned, a_selected), lane=a_sentinel
    )
    _refuses(
        "LANE_DISPOSITION_CONFLICT",
        lambda: _build(plan=declared, receipts=receipts),
    )


def test_work_class_undeclared() -> None:
    _refuses("WORK_CLASS_UNDECLARED", lambda: _build(work_class="E9"))


def test_required_lane_undeclared() -> None:
    _refuses("REQUIRED_LANE_UNDECLARED", lambda: _build(required_lanes=["not-a-lane"]))


def test_required_lane_not_searched() -> None:
    # 'lexical' is a sentinel lane in the happy plan, so requiring it is a lane
    # the run never selected and conclusively searched.
    _refuses("REQUIRED_LANE_NOT_SEARCHED", lambda: _build(required_lanes=["lexical"]))


def test_graded_class_without_required_lanes() -> None:
    _refuses("WORK_CLASS_LANE_RULE_VIOLATED", lambda: _build(required_lanes=[]))


def test_exempt_class_with_required_lanes() -> None:
    pinned = f.snapshot()
    order = canonical_lane_order()
    e0_plan = f.plan(pinned, lane_dispositions={lane: f._sentinel() for lane in order})
    _refuses(
        "WORK_CLASS_LANE_RULE_VIOLATED",
        lambda: build_search_completeness_certificate(
            plan=e0_plan,
            receipts=f.receipts(e0_plan, pinned),
            work_class="E0",
            required_lanes=["lexical"],
            subject_ref=f.SUBJECT_REF,
            generated_at=f.GENERATED_AT,
        ),
    )


# -- gate refusals ---------------------------------------------------------


def test_certificate_missing() -> None:
    _refuses(
        "CERTIFICATE_MISSING",
        lambda: evaluate_search_integrity_admissibility(
            **f.gate_arguments(certificate=None)
        ),
    )


def test_certificate_refused_when_schema_invalid() -> None:
    broken = dict(f.certificate())
    broken.pop("completion_state")
    _refuses(
        "CERTIFICATE_REFUSED",
        lambda: evaluate_search_integrity_admissibility(
            **f.gate_arguments(certificate=broken)
        ),
    )


def test_certificate_drift() -> None:
    drifted = dict(f.certificate())
    drifted["certificate_hash"] = "sha256:" + "0" * 64
    _refuses(
        "CERTIFICATE_DRIFT",
        lambda: evaluate_search_integrity_admissibility(
            **f.gate_arguments(certificate=drifted)
        ),
    )


def test_claim_refused_when_assessment_invalid() -> None:
    pinned = f.snapshot()
    certificate = f.certificate()
    assessment = dict(f.novelty_assessment(certificate["certificate_id"], pinned))
    assessment.pop("novelty_status")
    _refuses(
        "CLAIM_REFUSED",
        lambda: evaluate_search_integrity_admissibility(
            **f.gate_arguments(certificate=certificate, novelty_assessment=assessment)
        ),
    )


def test_claim_certificate_mismatch() -> None:
    pinned = f.snapshot()
    assessment = f.novelty_assessment("SCC-SOMETHING-ELSE", pinned)
    _refuses(
        "CLAIM_CERTIFICATE_MISMATCH",
        lambda: evaluate_search_integrity_admissibility(
            **f.gate_arguments(novelty_assessment=assessment)
        ),
    )


def test_subject_identity_mismatch() -> None:
    _refuses(
        "SUBJECT_IDENTITY_MISMATCH",
        lambda: evaluate_search_integrity_admissibility(
            **f.gate_arguments(subject_ref="a-different-subject")
        ),
    )


def test_novelty_claim_without_complete_search() -> None:
    pinned = f.snapshot()
    declared = f.plan(pinned)
    order = canonical_lane_order()
    receipts = f.receipts(declared, pinned)
    required = f.required_lanes()[0]
    receipts[order.index(required)] = f.failed_receipt(receipts[order.index(required)])
    certificate = build_search_completeness_certificate(
        plan=declared,
        receipts=receipts,
        work_class=f.WORK_CLASS,
        required_lanes=f.required_lanes(),
        subject_ref=f.SUBJECT_REF,
        generated_at=f.GENERATED_AT,
    )
    assessment = f.novelty_assessment(certificate["certificate_id"], pinned)
    _refuses(
        "NOVELTY_CLAIM_WITHOUT_COMPLETE_SEARCH",
        lambda: evaluate_search_integrity_admissibility(
            **f.gate_arguments(certificate=certificate, novelty_assessment=assessment)
        ),
    )


def test_prior_art_ignored_required_source() -> None:
    _refuses(
        "PRIOR_ART_IGNORED_REQUIRED_SOURCE",
        lambda: evaluate_search_integrity_admissibility(
            **f.gate_arguments(required_source_ids=["patent-registers"])
        ),
    )


def test_admissibility_receipt_refused_when_not_admit() -> None:
    receipt = dict(f.admissibility_receipt())
    receipt["decision"] = engine.REFUSE
    _refuses(
        "ADMISSIBILITY_RECEIPT_REFUSED",
        lambda: evaluate_search_integrity_admissibility(
            **f.gate_arguments(admissibility_receipt=receipt)
        ),
    )


def test_admissibility_receipt_refused_when_from_another_gate() -> None:
    receipt = dict(f.admissibility_receipt())
    receipt["gate"] = "some-other-gate"
    _refuses(
        "ADMISSIBILITY_RECEIPT_REFUSED",
        lambda: evaluate_search_integrity_admissibility(
            **f.gate_arguments(admissibility_receipt=receipt)
        ),
    )


def test_candidate_identity_mismatch() -> None:
    _refuses(
        "CANDIDATE_IDENTITY_MISMATCH",
        lambda: evaluate_search_integrity_admissibility(
            **f.gate_arguments(candidate_id="a-different-candidate")
        ),
    )


def test_candidate_role_holds_authority() -> None:
    role = sorted(CANDIDATE_GENERATING_ROLES)[0]
    _refuses(
        "CANDIDATE_ROLE_HOLDS_AUTHORITY",
        lambda: evaluate_search_integrity_admissibility(
            **f.gate_arguments(requesting_role=role)
        ),
    )


def test_input_invalid_on_the_gate_boundary() -> None:
    _refuses(
        "INPUT_INVALID",
        lambda: evaluate_search_integrity_admissibility(
            **f.gate_arguments(created_at="")
        ),
    )


# -- integrity of the finding-code contract -------------------------------


def test_undeclared_finding_code_is_itself_refused() -> None:
    with pytest.raises(SearchIntegrityRefused) as excinfo:
        engine._fail("NOT_A_REAL_CODE", "boom")
    assert excinfo.value.code == "INPUT_INVALID"


def test_every_finding_code_is_exercised() -> None:
    """The union of codes this module raised must cover FINDING_CODES exactly."""
    assert _RAISED == set(FINDING_CODES), set(FINDING_CODES) - _RAISED


def test_certificate_identity_guard_is_order_independent() -> None:
    """A certificate re-serialized in a different key order still re-derives."""
    certificate = f.certificate()
    shuffled = dict(reversed(list(certificate.items())))
    assert (
        require_certificate_identity(shuffled)["certificate_id"]
        == (certificate["certificate_id"])
    )
