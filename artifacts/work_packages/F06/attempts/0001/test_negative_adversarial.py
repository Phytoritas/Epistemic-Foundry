"""negative_and_adversarial_tests — every refusal fires for its own reason.

Each test is one deviation from the admitted happy case, so a refusal isolates
exactly the axis it names.  Together they cover every declared finding code, the
split between an input-integrity refusal that raises before any receipt exists
and a decision refusal that produces one, and the adversarial cases the gate
exists to close: a run that swaps its evaluator mid-search, a replay report that
flatters itself, and a lifecycle that jumps a return edge its budget never bound.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evolution.v4_f05 import Transition
from epistemic_foundry.evolution.v4_f06 import (
    ADMIT,
    FINDING_CODES,
    LifecycleReplayRefused,
    derive_lifecycle_replay,
    evaluate_lifecycle_replay,
)
from fixtures import (
    EVALUATOR_HASH,
    OTHER_EVALUATOR_HASH,
    deep_copy_case,
    happy_case,
    submission,
    transitions,
)


def _refusal_code(case: dict) -> str:
    receipt = derive_lifecycle_replay(**case)
    assert receipt["decision"] != ADMIT
    return str(receipt["finding_code"])


def _seal_stop_certificate(case: dict) -> None:
    certificate = case["run"]["stop_certificate"]
    if certificate is None:
        return
    certificate["certificate_hash"] = hash_excluding(
        certificate, "certificate_hash"
    )


def _perturb(mutate) -> dict:
    case = deep_copy_case(happy_case())
    mutate(case)
    _seal_stop_certificate(case)
    return case


# --------------------------------------------------------------------------- #
# Input-integrity refusals raise before a decision receipt exists.
# --------------------------------------------------------------------------- #
def test_a_forge_session_that_fails_its_schema_is_refused() -> None:
    case = _perturb(lambda c: c["forge_session"].__setitem__("revision", -1))
    with pytest.raises(LifecycleReplayRefused) as caught:
        derive_lifecycle_replay(**case)
    assert caught.value.code == "FORGE_SESSION_CONTRACT_VIOLATED"


def test_a_replay_report_that_fails_its_schema_is_refused() -> None:
    case = _perturb(lambda c: c["replay_report"].__setitem__("mode", "sideways"))
    with pytest.raises(LifecycleReplayRefused) as caught:
        derive_lifecycle_replay(**case)
    assert caught.value.code == "REPLAY_REPORT_CONTRACT_VIOLATED"


def test_a_malformed_run_is_refused_as_input_invalid() -> None:
    case = _perturb(lambda c: c["run"].__setitem__("evolution_run_id", ""))
    with pytest.raises(LifecycleReplayRefused) as caught:
        derive_lifecycle_replay(**case)
    assert caught.value.code == "INPUT_INVALID"


def test_a_transition_that_is_not_an_f05_object_is_refused() -> None:
    case = _perturb(
        lambda c: c["run"].__setitem__(
            "transitions", [*c["run"]["transitions"], {"source": "x", "target": "y"}]
        )
    )
    with pytest.raises(LifecycleReplayRefused) as caught:
        derive_lifecycle_replay(**case)
    assert caught.value.code == "INPUT_INVALID"


# --------------------------------------------------------------------------- #
# FORGE handoff.
# --------------------------------------------------------------------------- #
def test_a_session_not_in_the_handoff_phase_is_refused() -> None:
    def mutate(c: dict) -> None:
        from fixtures import _phases

        c["forge_session"]["phase"] = _phases()[0]
        c["forge_session"]["phase_history"] = []

    assert _refusal_code(_perturb(mutate)) == "FORGE_HANDOFF_ABSENT"


def test_a_session_with_no_transition_into_the_handoff_phase_is_refused() -> None:
    assert (
        _refusal_code(
            _perturb(lambda c: c["forge_session"].__setitem__("phase_history", []))
        )
        == "FORGE_HANDOFF_ABSENT"
    )


def test_a_session_bound_to_a_different_run_spec_is_refused() -> None:
    assert (
        _refusal_code(
            _perturb(
                lambda c: c["forge_session"].__setitem__("run_spec_id", "RS-OTHER")
            )
        )
        == "FORGE_RUN_SPEC_MISBOUND"
    )


# --------------------------------------------------------------------------- #
# Lifecycle and stop certificate (composed F05 verdict).
# --------------------------------------------------------------------------- #
def test_a_run_that_loops_past_its_budget_is_refused() -> None:
    assert (
        _refusal_code(
            _perturb(
                lambda c: c["run"]["loop_contract"].__setitem__("max_iterations", 1)
            )
        )
        == "LIFECYCLE_TRANSITIONS_INCONSISTENT"
    )


def test_a_run_that_stops_without_a_certificate_is_refused() -> None:
    assert (
        _refusal_code(
            _perturb(lambda c: c["run"].__setitem__("stop_certificate", None))
        )
        == "STOP_CERTIFICATE_INCONSISTENT"
    )


def test_a_stop_certificate_for_a_different_run_is_refused() -> None:
    assert (
        _refusal_code(
            _perturb(
                lambda c: c["run"]["stop_certificate"].__setitem__(
                    "evolution_run_id", "ER-SOMEWHERE-ELSE"
                )
            )
        )
        == "STOP_CERTIFICATE_INCONSISTENT"
    )


def test_a_return_edge_the_loop_never_bounded_is_refused() -> None:
    # A return edge between nodes the loop contract does not bound is a jump the
    # iteration budget never applied to — the adversarial case F05 owns and the
    # gate composes.
    def mutate(c: dict) -> None:
        moves = list(c["run"]["transitions"])
        moves.append(
            Transition(
                source="validate_candidate_contracts",
                target="select_epistemic_parents",
                checkpoint_id="CP-STRAY",
            )
        )
        c["run"]["transitions"] = moves

    assert _refusal_code(_perturb(mutate)) == "LIFECYCLE_TRANSITIONS_INCONSISTENT"


# --------------------------------------------------------------------------- #
# Evaluator immutability (EF4-I43).
# --------------------------------------------------------------------------- #
def test_a_run_that_swaps_its_evaluator_mid_search_is_refused() -> None:
    def mutate(c: dict) -> None:
        c["run"]["transitions"] = transitions(
            2, evaluator_hashes=[EVALUATOR_HASH, OTHER_EVALUATOR_HASH]
        )

    assert _refusal_code(_perturb(mutate)) == "EVALUATOR_BUNDLE_MUTATED"


def test_a_committed_return_checkpoint_without_an_evaluator_binding_is_refused() -> (
    None
):
    def mutate(c: dict) -> None:
        moves = list(c["run"]["transitions"])
        for position, move in enumerate(moves):
            if move.checkpoint_id != "CP-2":
                continue
            moves[position] = Transition(
                source=move.source,
                target=move.target,
                checkpoint_id=move.checkpoint_id,
            )
            break
        else:  # pragma: no cover - a fixture contract failure, not a gate branch
            raise AssertionError("the happy case declares no CP-2 return checkpoint")
        c["run"]["transitions"] = moves

    case = _perturb(mutate)
    with pytest.raises(LifecycleReplayRefused) as caught:
        evaluate_lifecycle_replay(**case)
    assert caught.value.code == "EVALUATOR_BUNDLE_UNBOUND"
    receipt = caught.value.context["receipt"]
    assert receipt["decision"] != ADMIT
    [finding] = receipt["decision_context"]["unbound_checkpoints"]
    assert finding["checkpoint_id"] == "CP-2"
    assert finding["reason"] == "checkpoint_payload_missing"


def test_a_confirmed_evaluator_swap_precedes_an_unbound_checkpoint() -> None:
    def mutate(c: dict) -> None:
        moves = transitions(
            3,
            evaluator_hashes=[
                EVALUATOR_HASH,
                OTHER_EVALUATOR_HASH,
                EVALUATOR_HASH,
            ],
        )
        for position, move in enumerate(moves):
            if move.checkpoint_id != "CP-3":
                continue
            moves[position] = Transition(
                source=move.source,
                target=move.target,
                checkpoint_id=move.checkpoint_id,
            )
            break
        else:  # pragma: no cover - a fixture contract failure, not a gate branch
            raise AssertionError("the constructed run declares no CP-3 return checkpoint")
        c["run"]["transitions"] = moves

    receipt = derive_lifecycle_replay(**_perturb(mutate))
    assert receipt["decision"] != ADMIT
    assert receipt["finding_code"] == "EVALUATOR_BUNDLE_MUTATED"
    assert receipt["decision_context"]["evaluator_bundle_hashes"] == [
        EVALUATOR_HASH,
        OTHER_EVALUATOR_HASH,
    ]
    [finding] = receipt["decision_context"]["unbound_checkpoints"]
    assert finding["checkpoint_id"] == "CP-3"
    assert finding["reason"] == "checkpoint_payload_missing"


# --------------------------------------------------------------------------- #
# Seed intake (composed I05).
# --------------------------------------------------------------------------- #
def test_an_unfalsifiable_seed_is_refused_by_intake() -> None:
    assert (
        _refusal_code(
            _perturb(
                lambda c: c["run"].__setitem__(
                    "seed_submissions", [submission("HG-1", falsifier_gene_ids=[])]
                )
            )
        )
        == "SEED_INTAKE_REFUSED"
    )


def test_declared_seeds_that_intake_did_not_admit_are_refused() -> None:
    def mutate(c: dict) -> None:
        c["run"]["seed_genome_ids"] = ["HG-PHANTOM"]
        c["run"]["candidate_genome_ids"] = ["HG-PHANTOM", "HG-CHILD-1"]

    assert _refusal_code(_perturb(mutate)) == "SEED_POPULATION_UNRECONCILED"


# --------------------------------------------------------------------------- #
# Operators (composed R05) and candidate reconciliation (EF4-I60).
# --------------------------------------------------------------------------- #
def test_an_operator_the_registry_does_not_declare_is_refused() -> None:
    def mutate(c: dict) -> None:
        c["run"]["operator_applications"] = [
            {"operator_id": "hand-rolled-operator", "child_genome_id": "HG-CHILD-1"}
        ]

    assert _refusal_code(_perturb(mutate)) == "OPERATOR_UNDECLARED"


def test_an_unaccounted_candidate_is_refused() -> None:
    def mutate(c: dict) -> None:
        c["run"]["candidate_genome_ids"] = ["HG-1", "HG-CHILD-1", "HG-SMUGGLED"]

    assert _refusal_code(_perturb(mutate)) == "CANDIDATE_SET_UNRECONCILED"


def test_a_dropped_candidate_child_is_refused() -> None:
    def mutate(c: dict) -> None:
        c["run"]["candidate_genome_ids"] = ["HG-1"]

    assert _refusal_code(_perturb(mutate)) == "CANDIDATE_SET_UNRECONCILED"


# --------------------------------------------------------------------------- #
# Replay honesty and byte-for-byte reproduction.
# --------------------------------------------------------------------------- #
def test_a_replay_of_a_different_run_is_refused() -> None:
    assert (
        _refusal_code(
            _perturb(
                lambda c: c["replay_report"].__setitem__("source_run_id", "ER-NOT-THIS")
            )
        )
        == "REPLAY_RUN_MISBOUND"
    )


def test_a_report_claiming_exact_over_a_hash_mismatch_is_refused_as_dishonest() -> None:
    assert (
        _refusal_code(
            _perturb(
                lambda c: c["replay_report"].__setitem__("artifact_hash_mismatches", 4)
            )
        )
        == "REPLAY_REPORT_DISHONEST"
    )


def test_a_report_claiming_exact_over_a_missing_pin_is_refused_as_dishonest() -> None:
    assert (
        _refusal_code(
            _perturb(
                lambda c: c["replay_report"].__setitem__("unavailable_pins", ["PIN-9"])
            )
        )
        == "REPLAY_REPORT_DISHONEST"
    )


def test_a_report_claiming_no_drift_over_a_gate_difference_is_refused_as_dishonest() -> (
    None
):
    assert (
        _refusal_code(
            _perturb(
                lambda c: c["replay_report"].__setitem__(
                    "gate_differences", ["S3:PASS->FAIL"]
                )
            )
        )
        == "REPLAY_REPORT_DISHONEST"
    )


def test_a_semantic_only_replay_is_not_byte_for_byte() -> None:
    def mutate(c: dict) -> None:
        c["replay_report"]["mode"] = "semantic"
        c["replay_report"]["event_equivalence"] = "SEMANTICALLY_EQUIVALENT"

    assert _refusal_code(_perturb(mutate)) == "REPLAY_NOT_BYTE_FOR_BYTE"


def test_a_replay_with_zero_matched_artifacts_is_not_byte_for_byte() -> None:
    # An "exact" replay that matched no artifact at all reproduced nothing.
    assert (
        _refusal_code(
            _perturb(
                lambda c: c["replay_report"].__setitem__("artifact_hash_matches", 0)
            )
        )
        == "REPLAY_NOT_BYTE_FOR_BYTE"
    )


# --------------------------------------------------------------------------- #
# Coverage: every declared finding code is exercised by this suite.
# --------------------------------------------------------------------------- #
def test_every_declared_finding_code_is_reachable() -> None:
    exercised = {
        "INPUT_INVALID",
        "FORGE_SESSION_CONTRACT_VIOLATED",
        "REPLAY_REPORT_CONTRACT_VIOLATED",
        "FORGE_HANDOFF_ABSENT",
        "FORGE_RUN_SPEC_MISBOUND",
        "LIFECYCLE_TRANSITIONS_INCONSISTENT",
        "STOP_CERTIFICATE_INCONSISTENT",
        "EVALUATOR_BUNDLE_MUTATED",
        "EVALUATOR_BUNDLE_UNBOUND",
        "SEED_INTAKE_REFUSED",
        "SEED_POPULATION_UNRECONCILED",
        "OPERATOR_UNDECLARED",
        "CANDIDATE_SET_UNRECONCILED",
        "REPLAY_RUN_MISBOUND",
        "REPLAY_REPORT_DISHONEST",
        "REPLAY_NOT_BYTE_FOR_BYTE",
    }
    assert exercised == set(FINDING_CODES)
