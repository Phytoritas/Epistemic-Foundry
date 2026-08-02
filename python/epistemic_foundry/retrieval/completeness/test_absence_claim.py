"""absence_claim_test — absence and novelty claims carry recomputed certificates."""

from __future__ import annotations

import pytest

from ..planning.contracts import PlanningContractError
from ..planning.test_receipt_completeness import complete_receipts, plan_for
from ..planning.contracts import reconcile_search_run
from .contracts import (
    CompletenessGateError,
    seal_absence_claim,
    validate_absence_claim,
)

CREATED_AT = "2026-08-01T00:00:00Z"


def sealed_run(work_class: str = "E2", overrides: dict[str, str] | None = None):
    plan = plan_for(work_class)
    receipts = complete_receipts(plan, overrides or {})
    certificate = reconcile_search_run(
        plan,
        receipts,
        certificate_id="SCC-O04",
        run_id="RUN-1",
        subject_ref="INS-1",
        generated_at="2026-08-01T00:00:00Z",
    )
    return plan, receipts, certificate


def claim_kwargs(**overrides):
    values = {
        "lane": "counterevidence",
        "statement": "no counterevidence exists in the searched corpus scope",
        "created_at": CREATED_AT,
    }
    values.update(overrides)
    return values


def test_absence_claim_test_searched_none_lane_grounds_a_full_scope_claim() -> None:
    plan, receipts, certificate = sealed_run()

    claim = seal_absence_claim(plan, receipts, certificate, **claim_kwargs()).payload

    assert claim["claim_kind"] == "ABSENCE"
    assert claim["claim_class"] == "FULL_SCOPE"
    assert claim["lane_reconciled_state"] == "SEARCHED_NONE"
    assert claim["ceiling"] == "CORPUS_CONDITIONAL"
    assert claim["certificate_hash"] == certificate.payload["certificate_hash"]
    assert claim["claim_id"].startswith("ACL-")


def test_absence_claim_test_unsearched_lane_is_ignorance() -> None:
    plan, receipts, certificate = sealed_run()

    with pytest.raises(CompletenessGateError) as raised:
        seal_absence_claim(
            plan, receipts, certificate, **claim_kwargs(lane="mechanism")
        )
    assert raised.value.code == "ABSENCE_WITHOUT_SEARCH"


def test_absence_claim_test_results_contradict_an_absence_claim() -> None:
    plan, receipts, certificate = sealed_run(
        overrides={"counterevidence": "SEARCHED_WITH_RESULTS"}
    )

    with pytest.raises(CompletenessGateError) as raised:
        seal_absence_claim(plan, receipts, certificate, **claim_kwargs())
    assert raised.value.code == "ABSENCE_CONTRADICTED"


def test_absence_claim_test_novelty_claims_follow_the_novelty_ceiling() -> None:
    plan, receipts, certificate = sealed_run("E5")
    claim = seal_absence_claim(
        plan,
        receipts,
        certificate,
        **claim_kwargs(
            lane="external_novelty",
            statement="no prior art was found in the searched external scope",
        ),
    ).payload

    assert claim["claim_kind"] == "NOVELTY"
    assert claim["ceiling"] == "SEARCH_CONDITIONAL"

    plan, receipts, certificate = sealed_run(
        "E5", overrides={"external_novelty": "SEARCHED_WITH_RESULTS"}
    )
    with pytest.raises(CompletenessGateError) as raised:
        seal_absence_claim(
            plan,
            receipts,
            certificate,
            **claim_kwargs(lane="external_novelty", statement="novel"),
        )
    assert raised.value.code == "NOVELTY_CONTRADICTED"


def test_absence_claim_test_unexecuted_scope_cannot_be_claimed() -> None:
    plan, receipts, certificate = sealed_run()

    with pytest.raises(CompletenessGateError) as raised:
        seal_absence_claim(
            plan,
            receipts,
            certificate,
            **claim_kwargs(scope_id="lane:counterevidence:scope:sha256:" + "0" * 64),
        )
    assert raised.value.code == "SCOPE_NOT_EXECUTED"


def test_absence_claim_test_executed_scope_yields_a_bounded_demoted_claim() -> None:
    plan, receipts, certificate = sealed_run()
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
    assert claim["scope_id"] == scope_id
    assert claim["ceiling"] == "LOCAL_CORPUS_ONLY"


def test_absence_claim_test_roundtrip_and_tampering_fail_closed() -> None:
    plan, receipts, certificate = sealed_run()
    sealed = seal_absence_claim(plan, receipts, certificate, **claim_kwargs())

    rebuilt = validate_absence_claim(sealed.payload, plan, receipts, certificate)
    assert rebuilt.canonical_bytes == sealed.canonical_bytes

    tampered = sealed.payload
    tampered["ceiling"] = "EXTERNAL_CONDITIONAL"
    tampered["claim_hash"] = "sha256:" + "0" * 64
    with pytest.raises(CompletenessGateError) as raised:
        validate_absence_claim(tampered, plan, receipts, certificate)
    assert raised.value.code == "CLAIM_HASH_MISMATCH"

    from .contracts import _hash_excluding

    rehashed = sealed.payload
    rehashed["statement"] = "a stronger unearned statement"
    rehashed["claim_hash"] = _hash_excluding(rehashed, "claim_hash")
    with pytest.raises(CompletenessGateError) as raised:
        validate_absence_claim(rehashed, plan, receipts, certificate)
    assert raised.value.code == "CLAIM_RECONSTRUCTION_MISMATCH"

    extra = sealed.payload
    extra["surprise"] = True
    with pytest.raises(CompletenessGateError) as raised:
        validate_absence_claim(extra, plan, receipts, certificate)
    assert raised.value.code == "FIELD_SET_INVALID"


def test_absence_claim_test_certificate_tampering_fails_before_any_claim() -> None:
    plan, receipts, certificate = sealed_run()
    broken = certificate.payload
    broken["absence_claim_ceiling"] = "EXTERNAL_CONDITIONAL"

    with pytest.raises(PlanningContractError):
        seal_absence_claim(plan, receipts, broken, **claim_kwargs())


def test_absence_claim_test_sealing_is_deterministic() -> None:
    plan, receipts, certificate = sealed_run()

    first = seal_absence_claim(plan, receipts, certificate, **claim_kwargs())
    second = seal_absence_claim(plan, receipts, certificate, **claim_kwargs())

    assert first.canonical_bytes == second.canonical_bytes
