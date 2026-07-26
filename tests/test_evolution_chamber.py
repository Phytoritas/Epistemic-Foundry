"""Evolution proposes but cannot certify itself."""

from __future__ import annotations

import pytest

from epistemic_foundry.evolution_chamber import (
    FORBIDDEN_MUTATION_PATHS,
    AuthorityMutationRefused,
    apply_mutation,
    build_evolution_run_spec,
    build_mutation_receipt,
)
from epistemic_foundry.evolution_chamber.run_spec import evaluator_binding_changed

CANDIDATE = {
    "genome_id": "HG-0001",
    "canonical_claim": "spaced practice improves delayed recall",
    "complexity_budget": 10,
    "uncertainty_notes": "effect size uncertain below n=100",
    "evaluator_bundle_id": "EB-0001",
    "holdout_manifest_id": "HM-0001",
    "status": "ELIGIBLE",
    "lineage_id": "LIN-0001",
    "provenance_hash": "sha256:" + "e" * 64,
}


# -- authority immutability --------------------------------------------


def test_ordinary_field_mutation_is_allowed() -> None:
    mutated = apply_mutation(CANDIDATE, {"canonical_claim": "spaced practice improves retention"})
    assert mutated["canonical_claim"] == "spaced practice improves retention"
    assert mutated["evaluator_bundle_id"] == CANDIDATE["evaluator_bundle_id"]


def test_evaluator_rebinding_is_refused() -> None:
    """A candidate may not choose the evaluator that judges it."""
    with pytest.raises(AuthorityMutationRefused) as excinfo:
        apply_mutation(CANDIDATE, {"evaluator_bundle_id": "EB-friendlier"})
    assert "may not certify itself" in str(excinfo.value)


def test_holdout_rebinding_is_refused() -> None:
    with pytest.raises(AuthorityMutationRefused):
        apply_mutation(CANDIDATE, {"holdout_manifest_id": "HM-easier"})


def test_self_promotion_is_refused() -> None:
    with pytest.raises(AuthorityMutationRefused):
        apply_mutation(CANDIDATE, {"status": "PROMOTED"})


def test_ledger_history_rewrite_is_refused() -> None:
    with pytest.raises(AuthorityMutationRefused):
        apply_mutation(CANDIDATE, {"ledger_event_ids": []})


def test_no_op_write_to_an_authority_field_is_still_refused() -> None:
    """Otherwise the boundary would depend on the value the operator picked."""
    with pytest.raises(AuthorityMutationRefused):
        apply_mutation(CANDIDATE, {"evaluator_bundle_id": CANDIDATE["evaluator_bundle_id"]})


def test_forbidden_set_covers_the_named_authority_surfaces() -> None:
    for field in (
        "evaluator_bundle_id",
        "holdout_manifest_id",
        "policy_bundle_id",
        "status",
        "gate_decision_ids",
        "approval_record_ids",
        "ledger_event_ids",
        "random_seed",
    ):
        assert field in FORBIDDEN_MUTATION_PATHS


# -- receipts -----------------------------------------------------------


def test_receipt_diff_is_derived_from_the_candidates() -> None:
    mutated = apply_mutation(CANDIDATE, {"complexity_budget": 12})
    receipt = build_mutation_receipt(
        evolution_run_id="ERS-0001",
        operator_id="OP-tighten-scope",
        input_candidates=[CANDIDATE],
        output_candidate=mutated,
        effect_receipt_id="EF-0001",
    )
    assert receipt["changed_paths"] == ["complexity_budget"]
    assert "evaluator_bundle_id" in receipt["preserved_paths"]


def test_receipt_catches_an_operator_that_edits_more_than_it_admits() -> None:
    """The diff is computed, so a smuggled authority edit is still caught."""
    smuggled = dict(CANDIDATE)
    smuggled["complexity_budget"] = 12
    smuggled["evaluator_bundle_id"] = "EB-smuggled"
    with pytest.raises(AuthorityMutationRefused) as excinfo:
        build_mutation_receipt(
            evolution_run_id="ERS-0001",
            operator_id="OP-sneaky",
            input_candidates=[CANDIDATE],
            output_candidate=smuggled,
            effect_receipt_id="EF-0001",
        )
    assert "evaluator_bundle_id" in str(excinfo.value)


def test_receipt_requires_an_input_candidate() -> None:
    with pytest.raises(ValueError):
        build_mutation_receipt(
            evolution_run_id="ERS-0001",
            operator_id="OP-1",
            input_candidates=[],
            output_candidate=CANDIDATE,
            effect_receipt_id="EF-0001",
        )


# -- run spec -----------------------------------------------------------


def _spec(**overrides) -> dict:
    kwargs = dict(
        base_run_spec_id="RS-0001",
        objective="maximize dependency-corrected support within scope",
        population_types=["hypothesis"],
        seed_genome_ids=["HG-0001"],
        evaluator_bundle_id="EB-0001",
        holdout_manifest_id="HM-0001",
        operator_registry_version="1.0.0",
        max_generations=5,
        max_candidates=50,
        budget_envelope_id="BE-0001",
        selection_policy="pareto with island migration",
        stop_policy="stop on budget exhaustion or dominated bound",
        random_seed=1234,
    )
    kwargs.update(overrides)
    return build_evolution_run_spec(**kwargs)


def test_run_spec_pins_evaluator_and_holdout() -> None:
    spec = _spec()
    assert spec["evaluator_bundle_id"] == "EB-0001"
    assert spec["holdout_manifest_id"] == "HM-0001"
    assert spec["spec_hash"].startswith("sha256:")


def test_unbounded_run_is_refused() -> None:
    """Search-until-something-passes has no stop certificate."""
    with pytest.raises(ValueError) as excinfo:
        _spec(max_candidates=0)
    assert "stop certificate" in str(excinfo.value)


def test_run_without_a_seed_genome_is_refused() -> None:
    with pytest.raises(ValueError):
        _spec(seed_genome_ids=[])


def test_evaluator_swap_between_specs_is_detectable() -> None:
    original = _spec()
    swapped = _spec(evaluator_bundle_id="EB-0002")
    assert evaluator_binding_changed(original, swapped) is True
    assert evaluator_binding_changed(original, _spec()) is False
