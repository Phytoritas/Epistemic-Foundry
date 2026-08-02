"""Unit and contract behaviour for the Q05 admissibility gate.

The happy path: a passing multi-objective fitness vector behind a sealed hidden
evaluation, with a complete corrected statistical record whose selective verdict
is ``ALLOW``, is forwarded to promotion review — and nothing more. These tests
pin what admission means and, just as importantly, what it does not grant.
"""

from __future__ import annotations

from epistemic_foundry.evaluation.v4_q05 import gate
from epistemic_foundry.evaluation.v4_q05.gate import SelectiveAdmissibilityRefused
from fixtures import CANDIDATE_ID, gate_arguments


def test_a_fully_bound_candidate_is_admitted() -> None:
    receipt = gate.evaluate_selective_admissibility(**gate_arguments())
    assert receipt["decision"] == gate.ADMIT
    assert receipt["admissible_for_promotion_review"] is True
    assert receipt["finding_code"] is None
    assert receipt["candidate_id"] == CANDIDATE_ID


def test_derive_and_evaluate_agree_on_an_admissible_candidate() -> None:
    arguments = gate_arguments()
    derived = gate.derive_selective_admissibility(**arguments)
    enforced = gate.evaluate_selective_admissibility(**arguments)
    assert derived == enforced


def test_admission_forwards_to_review_and_grants_no_promotion() -> None:
    """The gate decides admissibility to review, never a promotion.

    The receipt carries no granted level and no promotion authority field; the
    fitness surface it composed also refuses to promote on a score.
    """
    from epistemic_foundry.evaluation.fitness import may_promote_on_score

    receipt = gate.evaluate_selective_admissibility(**gate_arguments())
    assert "granted_level" not in receipt
    assert may_promote_on_score(gate_arguments()["fitness_vector"]) is False


def test_the_receipt_records_the_hidden_evaluation_only_by_hash() -> None:
    """A hidden evaluation stays hidden: the receipt binds it by hash alone."""
    receipt = gate.evaluate_selective_admissibility(**gate_arguments())
    assert receipt["evaluator_bundle_hash"].startswith("sha256:")
    assert receipt["holdout_manifest_hash"].startswith("sha256:")
    assert receipt["hidden_result_disclosed"] is False
    text = repr(receipt)
    for forbidden in ("HID-Q05-1", "OOD-Q05-1", "ADV-Q05-1"):
        assert forbidden not in text


def test_the_receipt_surfaces_the_selective_verdict() -> None:
    receipt = gate.evaluate_selective_admissibility(**gate_arguments())
    assert receipt["winner_curse_risk"] == "low"
    assert receipt["promotion_recommendation"] == "ALLOW"
    assert receipt["missing_statistical_artifacts"] == []


def test_permitted_disclosure_requires_approval_and_access() -> None:
    """With an approval and holdout access the hidden result may be disclosed."""
    receipt = gate.evaluate_selective_admissibility(
        **gate_arguments(
            disclose_hidden_result=True,
            unblinding_approval_id="UNBLIND-1",
        )
    )
    assert receipt["hidden_result_disclosed"] is True
    assert receipt["decision"] == gate.ADMIT


def test_the_enforcing_entrypoint_raises_on_a_non_admissible_candidate() -> None:
    arguments = gate_arguments(fitness_vector=_failing_fitness())
    try:
        gate.evaluate_selective_admissibility(**arguments)
    except SelectiveAdmissibilityRefused as error:
        assert error.code == "FITNESS_HARD_GATE_NOT_PASSED"
    else:  # pragma: no cover - the fitness above always refuses
        raise AssertionError("the gate should have refused")


def _failing_fitness() -> dict[str, object]:
    from fixtures import fitness_vector

    return fitness_vector(hard_gate_status="FAIL", hard_gate_failures=["G07_LEAKAGE"])
