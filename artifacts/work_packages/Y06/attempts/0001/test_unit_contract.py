"""unit_and_contract_tests — the happy paths hold their contracts.

Every gate produces a content-addressed receipt that re-derives its own
identifier and hash, and every receipt is a pure function of its inputs.  These
tests exercise the compositions the way a full 2,000-document qualification run
would: reconcile the declared counts against the sealed ledgers, attest a bounded
budget with measured cost and latency inside it, keep the surrogate within its
ceiling, contain authority, and seal the whole run into one verdict.
"""

from __future__ import annotations

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.operations.v4_y06 import (
    qualify_evolution_run,
    reconcile_qualification_counts,
    require_bounded_qualification_budget,
    require_no_scale_authority_capture,
    require_surrogate_within_ceiling,
)
from fixtures import (
    PROMOTION_CAPABILITY,
    bounded_budget,
    clean_fanout,
    deferred_triage,
    expected_counts,
    measured_usage,
    qualification_kwargs,
    triage,
)


def _rederives(record: dict[str, object]) -> bool:
    return hash_excluding(dict(record), "receipt_hash") == record["receipt_hash"]


def test_counts_reconcile_when_declaration_matches_the_ledger() -> None:
    fanout = clean_fanout()
    receipt = reconcile_qualification_counts(
        qualification_run_id="QUAL-1",
        expected_counts=expected_counts(),
        proposed=fanout["proposed"],
        generated=fanout["generated"],
        evaluated=fanout["evaluated"],
        persisted=fanout["persisted"],
        effect_receipts=fanout["effect_receipts"],
        mutation_receipts=fanout["mutation_receipts"],
    )
    assert receipt["reconciled"] is True
    assert receipt["stage_counts"]["proposed"] == 2
    assert receipt["stage_counts"]["persisted"] == 2
    assert receipt["receipt_id"].startswith("QIC-")
    assert _rederives(receipt)


def test_partial_declaration_reconciles_against_only_the_stages_named() -> None:
    fanout = clean_fanout()
    receipt = reconcile_qualification_counts(
        qualification_run_id="QUAL-1",
        expected_counts=expected_counts(persisted=2),
        proposed=fanout["proposed"],
        generated=fanout["generated"],
        evaluated=fanout["evaluated"],
        persisted=fanout["persisted"],
        effect_receipts=fanout["effect_receipts"],
        mutation_receipts=fanout["mutation_receipts"],
    )
    assert receipt["reconciled"] is True


def test_bounded_budget_with_usage_inside_the_ceiling_is_attested() -> None:
    receipt = require_bounded_qualification_budget(
        budget_envelope=bounded_budget(),
        measured_cost=40.0,
        measured_usage=measured_usage(),
    )
    assert receipt["spend_is_bounded"] is True
    assert receipt["within_budget"] is True
    assert receipt["escalates_on_breach"] is False  # MARK_PARTIAL only warns
    assert receipt["measured_cost"] == 40.0
    assert receipt["receipt_id"].startswith("QBG-")
    assert _rederives(receipt)


def test_cost_exactly_at_the_declared_amount_is_within_budget() -> None:
    receipt = require_bounded_qualification_budget(
        budget_envelope=bounded_budget(soft_cost_amount=40.0),
        measured_cost=40.0,
        measured_usage={},
    )
    assert receipt["within_budget"] is True


def test_surrogate_within_ceiling_counts_only_accepted_reports() -> None:
    receipt = require_surrogate_within_ceiling(
        triage_reports=[triage("CAND-1"), deferred_triage("CAND-2")],
        surrogate_ceiling=1,
    )
    # One EVALUATE_NOW acceptance and one deferral: the deferral is not counted.
    assert receipt["accepted_count"] == 1
    assert receipt["report_count"] == 2
    assert receipt["within_ceiling"] is True
    assert receipt["receipt_id"].startswith("QSC-")
    assert _rederives(receipt)


def test_authority_claim_without_capture_is_recorded() -> None:
    receipt = require_no_scale_authority_capture(
        authority_claims=[
            {
                "capability_id": "foundry:read",
                "holder_id": "CAND-1",
                "holder_is_search_space": True,
            },
            {
                "capability_id": PROMOTION_CAPABILITY,
                "holder_id": "deterministic-gate-node",
                "holder_is_search_space": False,
                "decision_basis": {"gate_verdict_hash": "sha256:" + "0" * 64},
            },
        ]
    )
    assert receipt["no_authority_captured"] is True
    # The promotion-commit capability is recorded as protected even though the
    # claim did not declare it so.
    protected = [c for c in receipt["authority_claims"] if c["protected_authority"]]
    assert len(protected) == 1
    assert receipt["receipt_id"].startswith("QAG-")
    assert _rederives(receipt)


def test_qualify_evolution_run_seals_a_verdict_binding_every_subreceipt() -> None:
    verdict = qualify_evolution_run(**qualification_kwargs())
    assert verdict["qualification_passed"] is True
    assert verdict["receipt_id"].startswith("QVR-")
    for field in (
        "count_receipt_hash",
        "budget_receipt_hash",
        "surrogate_receipt_hash",
        "authority_receipt_hash",
    ):
        assert verdict[field].startswith("sha256:")
    assert _rederives(verdict)


def test_qualification_is_a_pure_function_of_its_inputs() -> None:
    assert qualify_evolution_run(**qualification_kwargs()) == qualify_evolution_run(
        **qualification_kwargs()
    )
