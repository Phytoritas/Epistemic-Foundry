"""Negative and adversarial checks: every refusal the gate can raise.

There is at least one test per finding code, plus the adversarial cases that
matter for an integration gate: a genome that tries to carry promotion authority
in through the intake door, a falsifier or prediction that belongs to some other
hypothesis, an artifact scoped outside the bounds the genome declared, and the
proof that a refusal is a survey of every failure at once rather than the first
one encountered. The gate is also shown to hold none of the authority it would
need to score or promote anything.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.intake.v4_i06 import gate as g

import fixtures as fx


def _codes(**overrides: object) -> list[str]:
    receipt = g.gate_genome_intake(**fx.gate_arguments(**overrides))
    return receipt["finding_codes"]


# --- screening is deferred to I05 -------------------------------------------


def test_a_submission_the_screen_refuses_is_refused_here() -> None:
    receipt = g.gate_genome_intake(
        **fx.gate_arguments(submission=fx.submission(genome_kind="not-a-real-kind"))
    )
    assert receipt["admitted"] is False
    assert receipt["finding_codes"] == ["SCREENING_REFUSED"]
    assert receipt["findings"][0]["screen_reason_codes"]


def test_an_ineligible_genome_is_not_bound_to_scope_or_falsifiers() -> None:
    # A genome the screen refuses produces exactly the screening finding: the
    # binding survey never runs on a genome that failed eligibility.
    receipt = g.gate_genome_intake(
        **fx.gate_arguments(submission=fx.submission(genome_kind="challenge-genome"))
    )
    assert receipt["finding_codes"] == ["SCREENING_REFUSED"]


# --- authority ---------------------------------------------------------------


def test_a_genome_presenting_an_advanced_status_is_refused() -> None:
    statuses = default_registry().document(g.GENOME_KIND)["properties"]["status"][
        "enum"
    ]
    advanced = str(statuses[-1])
    assert advanced != g.intake_status()
    receipt = g.gate_genome_intake(
        **fx.gate_arguments(submission=fx.submission(genome=fx.genome(status=advanced)))
    )
    assert "AUTHORITY_STATUS_PRESUMED" in receipt["finding_codes"]


def test_the_gate_grants_no_scoring_or_promotion_authority() -> None:
    receipt = g.gate_genome_intake(**fx.gate_arguments())
    forbidden = {
        "score",
        "fitness",
        "rank",
        "promotion_decision_id",
        "promotion_recommendation",
        "granted_level",
        "evaluator_bundle_id",
        "holdout_manifest_id",
    }
    assert forbidden.isdisjoint(receipt)
    assert forbidden.isdisjoint(receipt["resolved_bindings"])


# --- scope binding -----------------------------------------------------------


def test_a_missing_scope_vector_is_refused() -> None:
    assert "SCOPE_VECTOR_MISSING" in _codes(scope_vector=None)


def test_a_malformed_scope_vector_is_refused() -> None:
    assert "SCOPE_VECTOR_MALFORMED" in _codes(scope_vector={"domain": None})


def test_a_scope_vector_of_the_wrong_type_is_refused() -> None:
    assert "SCOPE_VECTOR_MALFORMED" in _codes(scope_vector=["not", "a", "mapping"])


def test_a_prediction_scoped_outside_the_genome_bounds_is_refused() -> None:
    codes = _codes(prediction_genes=[fx.prediction_gene(scope_id=fx.OTHER_SCOPE_ID)])
    assert "PREDICTION_SCOPE_OUT_OF_BOUNDS" in codes


# --- falsifier binding -------------------------------------------------------


def test_a_declared_falsifier_with_no_supplied_gene_is_refused() -> None:
    codes = _codes(
        submission=fx.submission(
            genome=fx.genome(falsifier_ids=[fx.FALSIFIER_ID, "FG-MISSING"])
        )
    )
    assert "FALSIFIER_UNRESOLVED" in codes


def test_a_malformed_falsifier_gene_is_refused() -> None:
    broken = fx.falsifier_gene()
    del broken["decision_rule"]
    assert "FALSIFIER_MALFORMED" in _codes(falsifier_genes=[broken])


def test_a_falsifier_for_a_different_genome_is_refused() -> None:
    codes = _codes(falsifier_genes=[fx.falsifier_gene(genome_id="HG-OTHER")])
    assert "FALSIFIER_GENOME_MISMATCH" in codes


def test_an_undeclared_falsifier_gene_is_refused() -> None:
    codes = _codes(
        falsifier_genes=[fx.falsifier_gene(), fx.falsifier_gene("FG-SMUGGLED")]
    )
    assert "FALSIFIER_UNDECLARED" in codes


def test_a_falsifier_linking_an_undeclared_prediction_is_refused() -> None:
    codes = _codes(
        falsifier_genes=[fx.falsifier_gene(linked_prediction_ids=["PG-UNDECLARED"])]
    )
    assert "FALSIFIER_PREDICTION_UNLINKED" in codes


# --- prediction binding ------------------------------------------------------


def test_a_declared_prediction_with_no_supplied_gene_is_refused() -> None:
    codes = _codes(
        submission=fx.submission(
            genome=fx.genome(prediction_ids=[fx.PREDICTION_ID, "PG-MISSING"])
        )
    )
    assert "PREDICTION_UNRESOLVED" in codes


def test_a_malformed_prediction_gene_is_refused() -> None:
    broken = fx.prediction_gene()
    del broken["observable_id"]
    assert "PREDICTION_MALFORMED" in _codes(prediction_genes=[broken])


def test_a_prediction_for_a_different_genome_is_refused() -> None:
    codes = _codes(prediction_genes=[fx.prediction_gene(genome_id="HG-OTHER")])
    assert "PREDICTION_GENOME_MISMATCH" in codes


def test_an_undeclared_prediction_gene_is_refused() -> None:
    codes = _codes(
        prediction_genes=[fx.prediction_gene(), fx.prediction_gene("PG-SMUGGLED")]
    )
    assert "PREDICTION_UNDECLARED" in codes


# --- input shape -------------------------------------------------------------


def test_an_empty_decision_timestamp_is_refused() -> None:
    with pytest.raises(g.GenomeIntakeGateError) as raised:
        g.gate_genome_intake(**fx.gate_arguments(decided_at="   "))
    assert raised.value.code == "INPUT_INVALID"


def test_falsifier_genes_that_are_not_a_sequence_are_refused() -> None:
    with pytest.raises(g.GenomeIntakeGateError) as raised:
        g.gate_genome_intake(**fx.gate_arguments(falsifier_genes={"not": "a sequence"}))
    assert raised.value.code == "INPUT_INVALID"


def test_a_batch_request_that_is_not_a_mapping_is_refused() -> None:
    with pytest.raises(g.GenomeIntakeGateError) as raised:
        g.gate_intake_batch(["not a mapping"], decided_at=fx.DECIDED_AT)
    assert raised.value.code == "INPUT_INVALID"


def test_a_batch_over_a_non_sequence_is_refused() -> None:
    with pytest.raises(g.GenomeIntakeGateError) as raised:
        g.gate_intake_batch({"not": "a sequence"}, decided_at=fx.DECIDED_AT)
    assert raised.value.code == "INPUT_INVALID"


# --- contract drift ----------------------------------------------------------


def test_a_field_the_schema_stops_declaring_closes_the_gate(monkeypatch) -> None:
    patched = dict(g._CONTRACT_FIELDS)
    patched[g.FALSIFIER_KIND] = g._CONTRACT_FIELDS[g.FALSIFIER_KIND] + ("gone_field",)
    monkeypatch.setattr(g, "_CONTRACT_FIELDS", patched)
    with pytest.raises(g.GenomeIntakeGateError) as raised:
        g.verify_contract()
    assert raised.value.code == "CONTRACT_DRIFT"
    assert "gone_field" in raised.value.context["missing"]


def test_a_schema_the_registry_stops_declaring_closes_the_gate(monkeypatch) -> None:
    patched = dict(g._CONTRACT_FIELDS)
    patched["not-a-real-schema"] = ("whatever",)
    monkeypatch.setattr(g, "_CONTRACT_FIELDS", patched)
    with pytest.raises(g.GenomeIntakeGateError) as raised:
        g.verify_contract()
    assert raised.value.code == "CONTRACT_DRIFT"


# --- refusal is a complete survey --------------------------------------------


def test_a_refusal_names_every_binding_failure_at_once() -> None:
    receipt = g.gate_genome_intake(
        **fx.gate_arguments(
            scope_vector=None,
            falsifier_genes=[fx.falsifier_gene(genome_id="HG-OTHER")],
            prediction_genes=[fx.prediction_gene(genome_id="HG-OTHER")],
        )
    )
    assert set(receipt["finding_codes"]) >= {
        "SCOPE_VECTOR_MISSING",
        "FALSIFIER_GENOME_MISMATCH",
        "PREDICTION_GENOME_MISMATCH",
    }


def test_require_admissible_raises_the_first_code_and_carries_them_all() -> None:
    receipt = g.gate_genome_intake(
        **fx.gate_arguments(
            scope_vector=None,
            prediction_genes=[fx.prediction_gene(genome_id="HG-OTHER")],
        )
    )
    with pytest.raises(g.GenomeIntakeGateError) as raised:
        g.require_admissible(receipt)
    assert raised.value.code == sorted(receipt["finding_codes"])[0]
    assert set(raised.value.context["finding_codes"]) == set(receipt["finding_codes"])


def test_require_admissible_refuses_a_forged_empty_refusal() -> None:
    forged = {"admitted": False, "findings": [], "receipt_id": "GIR-FORGED"}
    with pytest.raises(g.GenomeIntakeGateError) as raised:
        g.require_admissible(forged)
    assert raised.value.code == "INPUT_INVALID"


def test_the_batch_counts_a_refused_genome() -> None:
    report = g.gate_intake_batch(
        [fx.request(), fx.request(scope_vector=None)],
        decided_at=fx.DECIDED_AT,
        report_id="GIB-MIX",
    )
    assert report["counts"] == {"admitted": 1, "refused": 1, "submitted": 2}
    assert report["finding_totals"]["SCOPE_VECTOR_MISSING"] == 1
