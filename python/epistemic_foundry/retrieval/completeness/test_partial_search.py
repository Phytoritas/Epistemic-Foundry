"""partial_search_test — ignorance is never zero evidence."""

from __future__ import annotations

import pytest

from ..evidence_pack.contracts import assemble_evidence_pack
from ..evidence_pack.test_pack_diversity import (
    default_assignments,
    default_units,
    pack_inputs,
    sealed_run as sealed_pack_run,
)
from .contracts import (
    CompletenessGateError,
    assert_pack_consistent_with_ignorance,
    lane_evidence_classification,
    seal_absence_claim,
    zero_evidence_report,
)
from .test_absence_claim import CREATED_AT, claim_kwargs, sealed_run


def test_partial_search_test_partial_lane_rejects_full_scope_claims() -> None:
    plan, receipts, certificate = sealed_run(overrides={"counterevidence": "PARTIAL"})

    with pytest.raises(CompletenessGateError) as raised:
        seal_absence_claim(plan, receipts, certificate, **claim_kwargs())
    assert raised.value.code == "PARTIAL_REQUIRES_SCOPE_BOUND"


def test_partial_search_test_partial_lane_supports_only_demoted_bounded_claims() -> (
    None
):
    plan, receipts, certificate = sealed_run(overrides={"counterevidence": "PARTIAL"})
    reconciliation = next(
        row
        for row in certificate.payload["lane_reconciliations"]
        if row["lane"] == "counterevidence"
    )
    scope_id = reconciliation["executed_scope_ids"][0]

    claim = seal_absence_claim(
        plan, receipts, certificate, **claim_kwargs(scope_id=scope_id)
    ).payload

    assert claim["claim_class"] == "SCOPE_BOUNDED"
    assert claim["lane_reconciled_state"] == "PARTIAL"
    assert claim["ceiling"] == "LOCAL_CORPUS_ONLY"


@pytest.mark.parametrize("state", ["FAILED", "BLOCKED"])
def test_partial_search_test_failed_lane_never_equals_zero_evidence(state: str) -> None:
    plan, receipts, certificate = sealed_run(overrides={"counterevidence": state})

    with pytest.raises(CompletenessGateError) as raised:
        seal_absence_claim(plan, receipts, certificate, **claim_kwargs())
    assert raised.value.code == "ABSENCE_WITHOUT_SEARCH"

    report = zero_evidence_report(plan, receipts, certificate)
    assert "counterevidence" in report["ignorance_lanes"]
    assert "counterevidence" not in report["zero_evidence_lanes"]


def test_partial_search_test_classification_separates_evidence_zero_and_ignorance() -> (
    None
):
    plan, receipts, certificate = sealed_run(
        overrides={
            "lexical": "SEARCHED_WITH_RESULTS",
            "semantic": "PARTIAL",
            "null": "FAILED",
            "boundary": "BLOCKED",
        }
    )

    classification = lane_evidence_classification(certificate.payload)

    assert classification["lexical"] == "EVIDENCE"
    assert classification["counterevidence"] == "ZERO_EVIDENCE"
    assert classification["semantic"] == "IGNORANCE"
    assert classification["null"] == "IGNORANCE"
    assert classification["boundary"] == "IGNORANCE"
    assert classification["mechanism"] == "IGNORANCE"

    report = zero_evidence_report(plan, receipts, certificate)
    assert report["evidence_lanes"] == ["lexical"]
    assert "counterevidence" in report["zero_evidence_lanes"]
    assert set(report["ignorance_lanes"]) >= {
        "boundary",
        "external_novelty",
        "mechanism",
        "null",
        "semantic",
    }


def test_partial_search_test_blocked_counter_pack_is_gate_consistent() -> None:
    run = sealed_pack_run({"counterevidence": "BLOCKED"})
    plan, receipts, certificate = run
    units = [entry for entry in default_units() if entry["evidence_id"] != "EVN-0101"]
    assignments = default_assignments()
    assignments["counter"] = []

    pack, _clusters = assemble_evidence_pack(
        units, **pack_inputs(run=run, lane_assignments=assignments)
    )

    verdict = assert_pack_consistent_with_ignorance(
        pack.payload, plan, receipts, certificate
    )
    assert verdict["status"] == "PASS"
    assert verdict["lane_classification"]["counterevidence"] == "IGNORANCE"


def test_partial_search_test_ignorance_lane_reported_complete_fails_closed() -> None:
    run = sealed_pack_run({"counterevidence": "BLOCKED"})
    plan, receipts, certificate = run
    units = [entry for entry in default_units() if entry["evidence_id"] != "EVN-0101"]
    assignments = default_assignments()
    assignments["counter"] = []
    pack, _clusters = assemble_evidence_pack(
        units, **pack_inputs(run=run, lane_assignments=assignments)
    )

    forged = pack.payload
    forged["completeness"]["counter_lane_complete"] = True

    with pytest.raises(CompletenessGateError) as raised:
        assert_pack_consistent_with_ignorance(forged, plan, receipts, certificate)
    assert raised.value.code == "IGNORANCE_COUNTED_AS_ZERO_EVIDENCE"
    assert raised.value.details["violations"][0]["lane"] == "counterevidence"


def test_partial_search_test_pack_must_bind_the_recomputed_certificate() -> None:
    run = sealed_pack_run()
    plan, receipts, certificate = run
    pack, _clusters = assemble_evidence_pack(default_units(), **pack_inputs(run=run))

    foreign_plan, foreign_receipts, foreign_certificate = sealed_run(
        overrides={"counterevidence": "SEARCHED_NONE"}
    )

    with pytest.raises(CompletenessGateError) as raised:
        assert_pack_consistent_with_ignorance(
            pack.payload, foreign_plan, foreign_receipts, foreign_certificate
        )
    assert raised.value.code == "PACK_CERTIFICATE_MISMATCH"


def test_partial_search_test_created_at_constant_matches_module_contract() -> None:
    assert CREATED_AT.endswith("Z")
