"""unit_and_contract_tests — the gate admits exactly what its contract allows.

The happy paths: a prompt-affecting operator qualified out of quarantine for a
future run and within a bounded token budget is admitted with a claim, an
activation and a budget assessment; an operator that touches no prompt is
admitted on registration plus budget alone; and the context-budget check on its
own admits work that fits and reports the headroom.  Each admission composes the
sealed J05/S05 and budget surfaces rather than re-deciding what they own.
"""

from __future__ import annotations

from epistemic_foundry.operators.v4_j06 import (
    ADMITTED,
    admit_operator_application,
    assess_context_budget,
    verify_gate_receipt,
)
from fixtures import (
    EVIDENCE,
    SOURCE_RUN,
    TARGET_RUN,
    admission_arguments,
    budget_envelope,
    context_manifest,
    hypothesis_admission_arguments,
)


def test_a_qualified_prompt_operator_within_budget_is_admitted() -> None:
    receipt = admit_operator_application(**admission_arguments())

    assert receipt["gate_outcome"] == ADMITTED
    assert receipt["operator_prompt_affecting"] is True
    assert receipt["target_run_id"] == TARGET_RUN
    assert receipt["source_run_id"] == SOURCE_RUN
    assert verify_gate_receipt(receipt) == receipt["receipt_hash"]


def test_the_admission_binds_the_composed_claim_and_activation() -> None:
    receipt = admit_operator_application(**admission_arguments())

    assert receipt["prompt_claim_hash"]
    assert receipt["prompt_activation_hash"]
    assert receipt["qualification_evidence_ids"] == sorted(EVIDENCE)


def test_the_admission_carries_a_verdict_not_a_score() -> None:
    receipt = admit_operator_application(**admission_arguments())

    # J06 is a gate, not an evaluator: nothing in the receipt is a fitness,
    # promotion, ranking or score of any kind.
    forbidden = ("score", "fitness", "promotion", "rank", "reward")
    keys = " ".join(receipt).lower()
    for word in forbidden:
        assert word not in keys


def test_a_non_prompt_operator_is_admitted_on_registration_and_budget() -> None:
    receipt = admit_operator_application(**hypothesis_admission_arguments())

    assert receipt["gate_outcome"] == ADMITTED
    assert receipt["operator_prompt_affecting"] is False
    assert receipt["prompt_claim_hash"] is None
    assert receipt["prompt_activation_hash"] is None
    assert receipt["source_run_id"] is None
    assert receipt["qualification_evidence_ids"] == []


def test_the_budget_assessment_reports_the_derived_headroom() -> None:
    assessment = assess_context_budget(
        context_manifest=context_manifest(
            instruction_tokens=100, evidence_tokens=200, tool_tokens=50
        ),
        budget_envelope=budget_envelope(hard_limits={"tokens": 1000}),
    )

    assert assessment["within_budget"] is True
    assert assessment["total_tokens"] == 350
    assert assessment["token_ceiling"] == 1000
    assert assessment["token_headroom"] == 650


def test_work_exactly_at_the_ceiling_is_admitted() -> None:
    assessment = assess_context_budget(
        context_manifest=context_manifest(
            instruction_tokens=500, evidence_tokens=400, tool_tokens=100
        ),
        budget_envelope=budget_envelope(hard_limits={"tokens": 1000}),
    )

    assert assessment["total_tokens"] == 1000
    assert assessment["token_headroom"] == 0


def test_a_hard_preallocated_budget_also_bounds_spend() -> None:
    assessment = assess_context_budget(
        context_manifest=context_manifest(),
        budget_envelope=budget_envelope(
            enforcement="HARD_PREALLOCATED", hard_limits={"tokens": 5000}
        ),
    )

    assert assessment["within_budget"] is True
    assert assessment["enforcement"] == "HARD_PREALLOCATED"


def test_the_assessment_names_its_budget_and_manifest_by_id_and_hash() -> None:
    envelope = budget_envelope()
    manifest = context_manifest()

    assessment = assess_context_budget(
        context_manifest=manifest, budget_envelope=envelope
    )

    assert assessment["budget_id"] == envelope["budget_id"]
    assert assessment["budget_hash"] == envelope["budget_hash"]
    assert assessment["manifest_id"] == manifest["manifest_id"]
    assert assessment["context_hash"] == manifest["context_hash"]
