"""Negative and adversarial tests for the Q06 governance-integration gate.

Every declared finding code is provoked at least once, and the adversarial cases
target the ways a selection could try to be governed as cleared without earning
it: a candidate role driving its own governance decision, a tampered or foreign
sealed verdict, a V05 advancement stitched onto a Q05 clearance it never
composed, a rosier selective report laundered past the winner's-curse deflation
Q05 already priced in, and a calibrated evaluation borrowed to cover an
uncalibrated one.
"""

from __future__ import annotations

import fixtures as fx
import pytest
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evaluation.v4_q06 import gate as engine


def _refuse(**overrides: object) -> dict[str, object]:
    return engine.derive_governance_integration(**fx.gate_arguments(**overrides))


def _raise_code(**overrides: object) -> str:
    with pytest.raises(engine.GovernanceIntegrationRefused) as excinfo:
        engine.derive_governance_integration(**fx.gate_arguments(**overrides))
    return excinfo.value.code


# --------------------------------------------------------------------------- #
# Substantive refusals (recorded on the receipt)
# --------------------------------------------------------------------------- #
def test_admissibility_not_admitted() -> None:
    report = fx.selective_report(replication_count=0)
    clearance = fx.admissibility_receipt(report=report)
    assert (
        _refuse(
            admissibility_receipt=clearance,
            advancement_receipt=fx.advancement_receipt(admissibility=clearance),
            selective_report=report,
        )["finding_code"]
        == "ADMISSIBILITY_NOT_ADMITTED"
    )


def test_advancement_not_advanced() -> None:
    clearance = fx.admissibility_receipt()
    assert (
        _refuse(
            admissibility_receipt=clearance,
            advancement_receipt=fx.advancement_receipt(
                admissibility=clearance, advanced=False
            ),
        )["finding_code"]
        == "ADVANCEMENT_NOT_ADVANCED"
    )


def test_calibration_not_passed() -> None:
    assert (
        _refuse(
            calibration_report=fx.calibration_report(
                status=fx._non_passing_calibration_status()
            )
        )["finding_code"]
        == "CALIBRATION_NOT_PASSED"
    )


# --------------------------------------------------------------------------- #
# Input-integrity refusals (raised)
# --------------------------------------------------------------------------- #
def test_candidate_generating_role_is_refused() -> None:
    assert _raise_code(requesting_role=fx.GENERATOR_ROLE) == (
        "CANDIDATE_ROLE_HOLDS_AUTHORITY"
    )


def test_foreign_candidate_admissibility_receipt_is_refused() -> None:
    assert _raise_code(candidate_id="HG-OTHER") == "CANDIDATE_IDENTITY_MISMATCH"


def test_foreign_candidate_selective_report_is_refused() -> None:
    # A selective report about another candidate, re-hashed so only its identity
    # is wrong, is refused as a candidate mismatch before the hash binding.
    foreign = fx.selective_report(candidate_id="HG-OTHER")
    assert _raise_code(selective_report=foreign) in {
        "CANDIDATE_IDENTITY_MISMATCH",
        "SELECTIVE_REPORT_MISBOUND",
    }


def test_tampered_admissibility_receipt_is_refused() -> None:
    tampered = dict(fx.admissibility_receipt())
    tampered["message"] = "manually raised to ADMIT"
    assert _raise_code(admissibility_receipt=tampered) == (
        "ADMISSIBILITY_RECEIPT_UNVERIFIED"
    )


def test_admissibility_receipt_from_another_gate_is_refused() -> None:
    foreign = dict(fx.admissibility_receipt())
    foreign["gate"] = "some-other-gate"
    foreign.pop("receipt_hash", None)
    foreign["receipt_hash"] = hash_excluding(foreign, "receipt_hash")
    assert _raise_code(admissibility_receipt=foreign) == (
        "ADMISSIBILITY_RECEIPT_UNVERIFIED"
    )


def test_tampered_advancement_receipt_is_refused() -> None:
    clearance = fx.admissibility_receipt()
    tampered = dict(fx.advancement_receipt(admissibility=clearance))
    tampered["message"] = "manually flipped to ADVANCE"
    assert (
        _raise_code(admissibility_receipt=clearance, advancement_receipt=tampered)
        == "ADVANCEMENT_RECEIPT_UNVERIFIED"
    )


def test_advancement_receipt_without_boolean_verdict_is_refused() -> None:
    clearance = fx.admissibility_receipt()
    broken = dict(fx.advancement_receipt(admissibility=clearance))
    broken["advanced"] = "yes"  # not a bool
    broken.pop("receipt_hash", None)
    broken["receipt_hash"] = hash_excluding(broken, "receipt_hash")
    assert (
        _raise_code(admissibility_receipt=clearance, advancement_receipt=broken)
        == "ADVANCEMENT_RECEIPT_UNVERIFIED"
    )


def test_advancement_stitched_onto_a_foreign_clearance_is_refused() -> None:
    # The advancement receipt re-derives its own hash but binds a different
    # admissibility hash than the Q05 clearance supplied, so the two sealed
    # verdicts describe different selections.
    clearance = fx.admissibility_receipt()
    stitched = dict(fx.advancement_receipt(admissibility=clearance))
    stitched["statistical_admissibility_receipt_hash"] = "sha256:" + "9" * 64
    stitched.pop("receipt_hash", None)
    stitched["receipt_hash"] = hash_excluding(stitched, "receipt_hash")
    assert (
        _raise_code(admissibility_receipt=clearance, advancement_receipt=stitched)
        == "ADVANCEMENT_ADMISSIBILITY_UNBOUND"
    )


def test_calibration_contract_violation_is_refused() -> None:
    broken = fx.calibration_report()
    broken.pop("brier_score")  # a required field
    assert _raise_code(calibration_report=broken) == "CALIBRATION_CONTRACT_VIOLATED"


def test_calibration_for_a_foreign_evaluation_is_refused() -> None:
    assert (
        _raise_code(
            calibration_report=fx.calibration_report(evaluation_id="EVAL-OTHER")
        )
        == "CALIBRATION_EVALUATION_MISMATCH"
    )


def test_selective_report_contract_violation_is_refused() -> None:
    assert (
        _raise_code(selective_report={"candidate_id": fx.CANDIDATE_ID})
        == "SELECTIVE_REPORT_CONTRACT_VIOLATED"
    )


def test_laundered_selective_report_is_refused() -> None:
    # A different, equally valid ALLOW report is substituted for the one Q05
    # accounted the winner's-curse over; its content hash no longer matches.
    other = fx.selective_report(report_id="SIR-LAUNDERED")
    assert _raise_code(selective_report=other) == "SELECTIVE_REPORT_MISBOUND"


def test_non_mapping_admissibility_receipt_is_refused() -> None:
    assert _raise_code(admissibility_receipt=["not", "a", "mapping"]) == "INPUT_INVALID"


def test_empty_created_at_is_refused() -> None:
    assert _raise_code(created_at="") == "INPUT_INVALID"


def test_vocabulary_drift_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A calibration schema with no status ladder must not silently pick a token."""

    class _Registry:
        def document(self, _name: str) -> dict[str, object]:
            return {"properties": {"calibration_status": {"enum": []}}}

    engine._vocab.cache_clear()
    monkeypatch.setattr(engine, "default_registry", lambda: _Registry())
    try:
        with pytest.raises(engine.GovernanceIntegrationRefused) as excinfo:
            engine.calibration_pass_status()
        assert excinfo.value.code == "VOCABULARY_DRIFT"
    finally:
        engine._vocab.cache_clear()


# --------------------------------------------------------------------------- #
# Reachability guard
# --------------------------------------------------------------------------- #
def test_every_finding_code_is_reachable() -> None:
    # A guard against a code that documents a refusal the gate can never produce.
    report0 = fx.selective_report(replication_count=0)
    clr0 = fx.admissibility_receipt(report=report0)
    clr = fx.admissibility_receipt()

    produced = {
        _refuse(
            admissibility_receipt=clr0,
            advancement_receipt=fx.advancement_receipt(admissibility=clr0),
            selective_report=report0,
        )["finding_code"],
        _refuse(
            admissibility_receipt=clr,
            advancement_receipt=fx.advancement_receipt(
                admissibility=clr, advanced=False
            ),
        )["finding_code"],
        _refuse(
            calibration_report=fx.calibration_report(
                status=fx._non_passing_calibration_status()
            )
        )["finding_code"],
    }

    stitched = dict(fx.advancement_receipt(admissibility=clr))
    stitched["statistical_admissibility_receipt_hash"] = "sha256:" + "9" * 64
    stitched.pop("receipt_hash", None)
    stitched["receipt_hash"] = hash_excluding(stitched, "receipt_hash")

    broken_adv = dict(fx.advancement_receipt(admissibility=clr))
    broken_adv["advanced"] = "yes"
    broken_adv.pop("receipt_hash", None)
    broken_adv["receipt_hash"] = hash_excluding(broken_adv, "receipt_hash")

    broken_cal = fx.calibration_report()
    broken_cal.pop("brier_score")

    raised = {
        _raise_code(requesting_role=fx.GENERATOR_ROLE),
        _raise_code(candidate_id="HG-OTHER"),
        _raise_code(admissibility_receipt={"gate": "x"}),
        _raise_code(admissibility_receipt=["not", "a", "mapping"]),
        _raise_code(admissibility_receipt=clr, advancement_receipt=stitched),
        _raise_code(admissibility_receipt=clr, advancement_receipt=broken_adv),
        _raise_code(calibration_report=broken_cal),
        _raise_code(calibration_report=fx.calibration_report(evaluation_id="X")),
        _raise_code(selective_report={"candidate_id": fx.CANDIDATE_ID}),
        _raise_code(selective_report=fx.selective_report(report_id="SIR-X")),
    }
    covered = produced | raised | {"VOCABULARY_DRIFT"}
    assert set(engine.FINDING_CODES) <= covered
