"""A genome must be testable; a refutation must replicate before it stands."""

from __future__ import annotations

import inspect

import pytest

from epistemic_foundry.evolution_chamber.genome import (
    EVOLVABILITY_REQUIRED,
    GenomeIncomplete,
    build_hypothesis_genome,
    evolvability_gaps,
    is_evolvable,
    require_evolvable,
)
from epistemic_foundry.red_queen_lab.challenges import (
    REFUTATION_REPLICATION_REQUIRED,
    RefutationNotReplicated,
    build_challenge_result,
    partition_adverse_outcomes,
    refutation_stands,
    require_replicated_refutation,
)

HASH = "sha256:" + "a" * 64


def _genome(**overrides) -> dict:
    kwargs = dict(
        canonical_claim="spaced practice improves delayed recall",
        scope_vector_id="SV-1",
        mechanism_graph_id="MG-1",
        prediction_gene_ids=["PG-1"],
        falsifier_gene_ids=["FG-1"],
        alternative_hypothesis_ids=["ALT-1"],
        measurement_contract_ids=["MC-1"],
        evidence_pack_id="EP-1",
        validation_plan_id="VP-1",
        lineage_id="LIN-1",
        complexity_budget=10,
        uncertainty_notes=["effect size uncertain below n=100"],
        provenance_hash=HASH,
    )
    kwargs.update(overrides)
    return build_hypothesis_genome(**kwargs)


def _raw_genome(**overrides) -> dict:
    """A genome dict bypassing the builder, standing in for one arriving from
    an external adapter where the schema gate has not yet run."""
    genome = dict(_genome())
    genome.update(overrides)
    return genome


# -- EF4-I42 genome completeness ----------------------------------------


def test_complete_genome_is_eligible() -> None:
    genome = _genome()
    assert genome["status"] == "ELIGIBLE"
    assert is_evolvable(genome) is True


def test_status_is_not_a_parameter() -> None:
    """A caller able to assert ELIGIBLE could seed an untestable draft."""
    assert "status" not in inspect.signature(build_hypothesis_genome).parameters


def test_builder_cannot_even_represent_a_falsifier_free_genome() -> None:
    """The schema requires non-empty gene lists, so this fails at construction."""
    from epistemic_foundry.contracts import ContractViolation

    with pytest.raises(ContractViolation):
        _genome(falsifier_gene_ids=[])


def test_externally_supplied_genome_without_a_falsifier_is_not_evolvable() -> None:
    genome = _raw_genome(falsifier_gene_ids=[])
    assert is_evolvable(genome) is False
    assert evolvability_gaps(genome) == ["falsifier_gene_ids"]


def test_externally_supplied_genome_without_alternatives_is_not_evolvable() -> None:
    assert is_evolvable(_raw_genome(alternative_hypothesis_ids=[])) is False


def test_empty_list_is_as_unevolvable_as_a_missing_field() -> None:
    """Declaring a field and leaving it blank must not pass."""
    assert evolvability_gaps(_raw_genome(prediction_gene_ids=[])) == ["prediction_gene_ids"]


@pytest.mark.parametrize("field", EVOLVABILITY_REQUIRED)
def test_every_required_element_is_checked(field: str) -> None:
    genome = _raw_genome()
    genome[field] = [] if isinstance(genome[field], list) else ""
    assert field in evolvability_gaps(genome)


def test_incomplete_genome_cannot_enter_the_population() -> None:
    genome = _raw_genome(falsifier_gene_ids=[])
    with pytest.raises(GenomeIncomplete) as excinfo:
        require_evolvable(genome)
    assert "shown wrong" in str(excinfo.value)


def test_complete_genome_passes_the_gate() -> None:
    require_evolvable(_genome())


# -- EF4-I51 refutation replication -------------------------------------


def _result(outcome: str, *, candidate: str = "CAND-1", challenge: str = "CG-1") -> dict:
    return build_challenge_result(
        challenge_genome_id=challenge,
        target_candidate_id=candidate,
        stage_result_id="SER-1",
        outcome=outcome,
        severity="major",
        observed_effect=f"observed {outcome.lower()}",
        reproduction_artifact_ids=["REPRO-1"],
    )


def test_single_refutation_does_not_stand() -> None:
    """One adverse result may be a flake in the challenge, not a defect."""
    assert refutation_stands("CG-1", "CAND-1", [_result("REFUTED")]) is False


def test_replicated_refutation_stands() -> None:
    results = [_result("REFUTED"), _result("REFUTED")]
    assert refutation_stands("CG-1", "CAND-1", results) is True


def test_replication_threshold_is_at_least_two() -> None:
    assert REFUTATION_REPLICATION_REQUIRED >= 2


def test_unreplicated_refutation_raises_with_the_symmetry_named() -> None:
    with pytest.raises(RefutationNotReplicated) as excinfo:
        require_replicated_refutation("CG-1", "CAND-1", [_result("REFUTED")])
    assert "unreplicated success" in str(excinfo.value)


def test_refutations_of_other_candidates_do_not_count() -> None:
    results = [_result("REFUTED"), _result("REFUTED", candidate="CAND-2")]
    assert refutation_stands("CG-1", "CAND-1", results) is False


def test_refutations_from_other_challenges_do_not_count() -> None:
    """Replication means the same challenge run again, not a different attack."""
    results = [_result("REFUTED"), _result("REFUTED", challenge="CG-2")]
    assert refutation_stands("CG-1", "CAND-1", results) is False


def test_survivals_never_accumulate_into_a_refutation() -> None:
    results = [_result("SURVIVED"), _result("SURVIVED")]
    assert refutation_stands("CG-1", "CAND-1", results) is False


def test_boundary_restrictions_stay_distinct_from_refutations() -> None:
    """A single failed bucket would erase the boundary knowledge."""
    results = [
        _result("REFUTED", candidate="CAND-1"),
        _result("SCOPE_RESTRICTED", candidate="CAND-2"),
    ]
    partition = partition_adverse_outcomes(results)
    assert partition["refuted"] == ["CAND-1"]
    assert partition["scope_restricted"] == ["CAND-2"]


def test_scope_restriction_also_needs_replication_to_stand() -> None:
    """A restriction narrows a claim, so it carries the same evidential bar."""
    assert refutation_stands("CG-1", "CAND-1", [_result("SCOPE_RESTRICTED")]) is False
    twice = [_result("SCOPE_RESTRICTED"), _result("SCOPE_RESTRICTED")]
    assert refutation_stands("CG-1", "CAND-1", twice) is True
