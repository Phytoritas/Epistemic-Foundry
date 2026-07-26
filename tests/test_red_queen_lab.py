"""Survival must be earned, not assumed."""

from __future__ import annotations

import pytest

from epistemic_foundry.red_queen_lab import (
    ChallengeContractViolation,
    build_challenge_genome,
    build_challenge_result,
    build_red_queen_round,
    survived_challenges,
)
from epistemic_foundry.red_queen_lab.challenges import unresolved_matches


def _genome(**overrides) -> dict:
    kwargs = dict(
        target_genome_id="HG-0001",
        challenge_class="counterexample",
        construction="hold total study time fixed and vary only spacing schedule",
        success_criterion="delayed-recall advantage disappears at p>0.05",
        required_capabilities=["dataset_access"],
        lineage_id="LIN-CG-0001",
    )
    kwargs.update(overrides)
    return build_challenge_genome(**kwargs)


def _result(outcome: str, *, candidate: str = "CAND-1", artifacts=("REPRO-1",)) -> dict:
    return build_challenge_result(
        challenge_genome_id="CG-0001",
        target_candidate_id=candidate,
        stage_result_id="SER-0001",
        outcome=outcome,
        severity="major",
        observed_effect=f"observed {outcome.lower()}",
        reproduction_artifact_ids=artifacts,
    )


# -- challenge construction --------------------------------------------


def test_challenge_genome_matches_the_canonical_schema() -> None:
    genome = _genome()
    assert genome["challenge_class"] == "counterexample"
    assert genome["safety_class"] == "safe"


def test_challenge_without_a_success_criterion_is_refused() -> None:
    """An unadjudicable challenge proves nothing either way."""
    with pytest.raises(ChallengeContractViolation) as excinfo:
        _genome(success_criterion="   ")
    assert "unadjudicable" in str(excinfo.value)


def test_challenge_without_a_construction_is_refused() -> None:
    with pytest.raises(ChallengeContractViolation):
        _genome(construction="")


def test_leakage_probe_is_a_first_class_challenge_class() -> None:
    assert _genome(challenge_class="leakage_probe")["challenge_class"] == "leakage_probe"


# -- result contracts ---------------------------------------------------


def test_refutation_requires_a_reproduction_artifact() -> None:
    """An irreproducible refutation is an assertion, not evidence."""
    with pytest.raises(ChallengeContractViolation) as excinfo:
        _result("REFUTED", artifacts=())
    assert "irreproducible refutation" in str(excinfo.value)


def test_scope_restriction_also_requires_reproduction() -> None:
    with pytest.raises(ChallengeContractViolation):
        _result("SCOPE_RESTRICTED", artifacts=())


def test_survival_does_not_require_a_reproduction_artifact() -> None:
    assert _result("SURVIVED", artifacts=())["outcome"] == "SURVIVED"


# -- survival semantics -------------------------------------------------


def test_unchallenged_candidate_has_not_survived() -> None:
    """Promotion must not credit robustness that was never tested."""
    assert survived_challenges("CAND-1", []) is False


def test_candidate_surviving_every_match_survives() -> None:
    results = [_result("SURVIVED"), _result("SURVIVED")]
    assert survived_challenges("CAND-1", results) is True


def test_one_refutation_defeats_survival() -> None:
    results = [_result("SURVIVED"), _result("REFUTED")]
    assert survived_challenges("CAND-1", results) is False


def test_inconclusive_match_is_not_a_win() -> None:
    """A crashed or ambiguous adversary must not read as a passed test."""
    assert survived_challenges("CAND-1", [_result("INCONCLUSIVE")]) is False


def test_errored_match_is_not_a_win() -> None:
    assert survived_challenges("CAND-1", [_result("ERROR")]) is False


def test_method_failure_is_not_a_win() -> None:
    assert survived_challenges("CAND-1", [_result("METHOD_FAILURE")]) is False


def test_other_candidates_matches_do_not_confer_survival() -> None:
    results = [_result("SURVIVED", candidate="CAND-2")]
    assert survived_challenges("CAND-1", results) is False


def test_unresolved_matches_are_reported_for_rerun() -> None:
    results = [_result("SURVIVED"), _result("INCONCLUSIVE"), _result("ERROR")]
    assert len(unresolved_matches(results)) == 2


# -- rounds -------------------------------------------------------------


def _round(**overrides) -> dict:
    kwargs = dict(
        evolution_run_id="ERS-0001",
        generation=3,
        hypothesis_candidate_ids=["CAND-1", "CAND-2"],
        challenge_candidate_ids=["CG-0001"],
        results=[_result("SURVIVED", candidate="CAND-1"), _result("REFUTED", candidate="CAND-2")],
        challenge_overfit_checks=["held-out challenge family transfer test"],
    )
    kwargs.update(overrides)
    return build_red_queen_round(**kwargs)


def test_round_derives_survivors_and_refuted_from_results() -> None:
    """A caller-declared survivor list is how an untested candidate looks robust."""
    record = _round()
    assert record["survivor_ids"] == ["CAND-1"]
    assert record["refuted_ids"] == ["CAND-2"]


def test_round_survivor_list_is_not_a_parameter() -> None:
    import inspect

    params = inspect.signature(build_red_queen_round).parameters
    assert "survivor_ids" not in params
    assert "refuted_ids" not in params


def test_unchallenged_candidate_is_not_listed_as_a_survivor() -> None:
    record = _round(results=[_result("SURVIVED", candidate="CAND-1")])
    assert record["survivor_ids"] == ["CAND-1"]
    assert "CAND-2" not in record["survivor_ids"]


def test_round_requires_challenge_overfit_checks() -> None:
    """Co-evolved challenges can overfit their target and then measure nothing."""
    with pytest.raises(ChallengeContractViolation) as excinfo:
        _round(challenge_overfit_checks=[])
    assert "overfit" in str(excinfo.value)


def test_round_binds_match_ids_to_the_recorded_results() -> None:
    results = [_result("SURVIVED", candidate="CAND-1")]
    record = _round(results=results)
    assert record["match_ids"] == [results[0]["challenge_result_id"]]
