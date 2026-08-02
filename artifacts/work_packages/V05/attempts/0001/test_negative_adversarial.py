"""Negative and adversarial tests for the V05 advancement gate.

Every declared finding code is provoked at least once, and the adversarial cases
target the ways a claim could try to advance without earning it: a candidate role
driving its own decision, a tampered or foreign statistical clearance, a
qualifying replication borrowed from another candidate, a non-OOD challenge
dressed as OOD coverage, and a later cascade stage run to overturn an earlier
hard failure.
"""

from __future__ import annotations

import fixtures as fx
import pytest
from epistemic_foundry.validation.v4_v05 import cascade_gate as engine
from epistemic_foundry.validation_bay.cascade import (
    CascadeViolation,
    build_stage_result,
)


def _refuse(**overrides: object) -> dict[str, object]:
    return engine.derive_validation_advancement(**fx.gate_arguments(**overrides))


def _raise_code(**overrides: object) -> str:
    with pytest.raises(engine.ValidationCascadeRefused) as excinfo:
        engine.derive_validation_advancement(**fx.gate_arguments(**overrides))
    return excinfo.value.code


# --------------------------------------------------------------------------- #
# Substantive refusals (recorded on the receipt)
# --------------------------------------------------------------------------- #
def test_cascade_not_passed() -> None:
    assert (
        _refuse(stage_results=fx.stage_results(final_status="FAIL"))["finding_code"]
        == "CASCADE_NOT_PASSED"
    )


def test_admissibility_not_admitted() -> None:
    assert (
        _refuse(admissibility_receipt=fx.refused_admissibility_receipt())[
            "finding_code"
        ]
        == "ADMISSIBILITY_NOT_ADMITTED"
    )


def test_ood_challenge_absent_when_no_ood_challenge_ran() -> None:
    assert (
        _refuse(challenge_genomes=[fx.other_genome()], challenge_results=[])[
            "finding_code"
        ]
        == "OOD_CHALLENGE_ABSENT"
    )


def test_non_ood_challenge_does_not_count_as_ood_coverage() -> None:
    # A confounder challenge, even if survived, is not OOD coverage.
    survived = fx.ood_result(genome_id="CG-V05-OTHER")
    assert (
        _refuse(challenge_genomes=[fx.other_genome()], challenge_results=[survived])[
            "finding_code"
        ]
        == "OOD_CHALLENGE_ABSENT"
    )


def test_ood_challenge_refuted() -> None:
    refuted = fx.ood_result(outcome=fx._adverse_outcome())
    assert _refuse(challenge_results=[refuted])["finding_code"] == (
        "OOD_CHALLENGE_REFUTED"
    )


def test_ood_challenge_unresolved_is_not_survival() -> None:
    unresolved = fx.ood_result(outcome=fx._unresolved_outcome())
    assert _refuse(challenge_results=[unresolved])["finding_code"] == (
        "OOD_CHALLENGE_UNRESOLVED"
    )


def test_replication_ceiling_below_required() -> None:
    assert _refuse(replication_plan=None)["finding_code"] == (
        "REPLICATION_CEILING_BELOW_REQUIRED"
    )


# --------------------------------------------------------------------------- #
# Input-integrity refusals (raised)
# --------------------------------------------------------------------------- #
def test_candidate_generating_role_is_refused() -> None:
    assert _raise_code(requesting_role=fx.GENERATOR_ROLE) == (
        "CANDIDATE_ROLE_HOLDS_AUTHORITY"
    )


def test_foreign_candidate_stage_result_is_refused() -> None:
    foreign = fx.stage_results()
    foreign[0]["candidate_id"] = "HG-OTHER"
    assert _raise_code(stage_results=foreign) == "CANDIDATE_IDENTITY_MISMATCH"


def test_foreign_candidate_replication_plan_cannot_lift_the_ceiling() -> None:
    assert (
        _raise_code(replication_plan=fx.replication_plan(candidate_id="HG-OTHER"))
        == "CANDIDATE_IDENTITY_MISMATCH"
    )


def test_foreign_candidate_admissibility_receipt_is_refused() -> None:
    assert (
        _raise_code(
            admissibility_receipt=fx.admissibility_receipt(candidate_id="HG-OTHER")
        )
        == "CANDIDATE_IDENTITY_MISMATCH"
    )


def test_tampered_admissibility_receipt_is_refused() -> None:
    tampered = dict(fx.admissibility_receipt())
    tampered["message"] = "manually raised to ADMIT"
    assert _raise_code(admissibility_receipt=tampered) == (
        "ADMISSIBILITY_RECEIPT_UNVERIFIED"
    )


def test_admissibility_receipt_from_another_gate_is_refused() -> None:
    foreign = dict(fx.admissibility_receipt())
    foreign["gate"] = "some-other-gate"
    # Re-seal so only the gate identity, not the hash, is wrong.
    from epistemic_foundry.domain.hashing import hash_excluding

    foreign.pop("receipt_hash", None)
    foreign["receipt_hash"] = hash_excluding(foreign, "receipt_hash")
    assert _raise_code(admissibility_receipt=foreign) == (
        "ADMISSIBILITY_RECEIPT_UNVERIFIED"
    )


def test_stage_result_from_another_plan_is_refused() -> None:
    foreign = fx.stage_results()
    foreign[0]["cascade_plan_id"] = "VCP-OTHER"
    assert _raise_code(stage_results=foreign) == "INPUT_INVALID"


def test_unknown_required_promotion_level_is_refused() -> None:
    assert _raise_code(required_promotion_level="NOT_A_LEVEL") == "INPUT_INVALID"


def test_non_mapping_admissibility_receipt_is_refused() -> None:
    assert _raise_code(admissibility_receipt=["not", "a", "mapping"]) == "INPUT_INVALID"


def test_malformed_stage_result_is_refused() -> None:
    broken = fx.stage_results()
    broken[0].pop("status")
    assert _raise_code(stage_results=broken) == "INPUT_INVALID"


# --------------------------------------------------------------------------- #
# Adversarial: composed-owner refusals travel with their own type
# --------------------------------------------------------------------------- #
def test_out_of_order_cascade_raises_the_owners_violation() -> None:
    plan = fx.cascade_plan()
    passing = engine.cascade_pass_status()
    specs = list(plan["stages"])
    results = []
    for index, spec in enumerate(specs):
        status = "FAIL" if index == 0 else passing
        results.append(
            build_stage_result(
                cascade_plan_id=str(plan["cascade_plan_id"]),
                candidate_id=fx.CANDIDATE_ID,
                stage_id=str(spec["stage_id"]),
                status=status,
                metric_values={},
                uncertainty_summary="x",
                started_at=fx.CREATED_AT,
                completed_at=fx.CREATED_AT,
                stage_result_id=f"SER-ADV-{index}",
            )
        )
    with pytest.raises(CascadeViolation):
        engine.derive_validation_advancement(
            **fx.gate_arguments(cascade_plan=plan, stage_results=results)
        )


def test_a_high_stage_metric_cannot_override_a_failed_cascade() -> None:
    # No scalar advances a claim: a failing stage refuses however high its metric.
    loaded = fx.stage_results(final_status="FAIL")
    loaded[-1]["metric_values"] = {"score": 0.999}
    loaded[-1].pop("result_hash", None)
    from epistemic_foundry.domain.hashing import hash_excluding

    loaded[-1]["result_hash"] = hash_excluding(loaded[-1], "result_hash")
    assert _refuse(stage_results=loaded)["finding_code"] == "CASCADE_NOT_PASSED"


def test_every_finding_code_is_reachable() -> None:
    # A guard against a code that documents a refusal the gate can never produce.
    produced = {
        _refuse(stage_results=fx.stage_results(final_status="FAIL"))["finding_code"],
        _refuse(admissibility_receipt=fx.refused_admissibility_receipt())[
            "finding_code"
        ],
        _refuse(challenge_genomes=[fx.other_genome()], challenge_results=[])[
            "finding_code"
        ],
        _refuse(challenge_results=[fx.ood_result(outcome=fx._adverse_outcome())])[
            "finding_code"
        ],
        _refuse(challenge_results=[fx.ood_result(outcome=fx._unresolved_outcome())])[
            "finding_code"
        ],
        _refuse(replication_plan=None)["finding_code"],
    }
    raised = {
        _raise_code(requesting_role=fx.GENERATOR_ROLE),
        _raise_code(required_promotion_level="NOT_A_LEVEL"),
        _raise_code(admissibility_receipt=fx.admissibility_receipt(candidate_id="X")),
        _raise_code(admissibility_receipt={"gate": "x"}),
    }
    covered = produced | raised | {"CANDIDATE_IDENTITY_MISMATCH"}
    assert set(engine.FINDING_CODES) <= covered
