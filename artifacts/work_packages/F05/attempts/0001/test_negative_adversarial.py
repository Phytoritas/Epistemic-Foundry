"""negative_and_adversarial_tests — the return edge cannot be abused.

Looping is how a search runs and also how it escapes its own limits, so every
abuse is attacked directly: a jump the workflow never declared, a loop back
without a sealed checkpoint, a checkpoint that binds a configuration which never
existed, a run that loops past its declared budget, a run that simply ends
without certifying why, and a certificate naming a resume point the run never
committed.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.evolution.v4_f05 import (
    EvolveStateError,
    Transition,
    evaluate_run,
    require_valid_run,
)
from fixtures import (
    GRAPH,
    LOOP_ENTRY,
    LOOP_EXIT,
    ROOT,
    clean_run,
    forward_path,
    loop_back,
    loop_contract,
    stop_certificate,
)


def refused(payload: dict) -> EvolveStateError:
    with pytest.raises(EvolveStateError) as caught:
        require_valid_run(evaluate_run(ROOT, **payload))
    return caught.value


def raises_on_build(payload: dict) -> EvolveStateError:
    with pytest.raises(EvolveStateError) as caught:
        evaluate_run(ROOT, **payload)
    return caught.value


def test_a_return_edge_without_a_checkpoint_is_refused() -> None:
    payload = clean_run()
    payload["transitions"] = [
        *forward_path(),
        Transition(LOOP_EXIT, LOOP_ENTRY),
    ]

    error = refused(payload)
    assert error.code == "RETURN_EDGE_UNCHECKPOINTED"
    assert error.context["uncheckpointed_return_edges"][0]["target"] == LOOP_ENTRY


def test_a_return_edge_across_an_incomplete_checkpoint_is_refused() -> None:
    payload = clean_run()
    payload["transitions"] = [*forward_path(), loop_back(1, complete=False)]

    error = refused(payload)
    assert error.code == "CHECKPOINT_INCOMPLETE"
    assert error.context["incomplete_checkpoints"][0]["missing"]


def test_a_jump_the_workflow_never_declared_is_refused() -> None:
    payload = clean_run()
    payload["transitions"] = [
        *forward_path(),
        # Skipping straight from qualification to promotion would bypass every
        # generation, evaluation and audit node between them.
        Transition("qualify_evolution_run", "run_evidence_parliament_promotion"),
    ]

    error = refused(payload)
    assert error.code == "TRANSITION_UNDECLARED"


def test_a_return_edge_between_unbounded_nodes_is_refused() -> None:
    payload = clean_run()
    payload["transitions"] = [
        *forward_path(),
        Transition(
            "rank_pareto_and_update_niches",
            "route_mutation_models",
            checkpoint_id="CP-1",
        ),
    ]

    error = refused(payload)
    assert error.code in {"RETURN_EDGE_MISPLACED", "TRANSITION_UNDECLARED"}
    assert evaluate_run(ROOT, **payload)["misplaced_return_edges"]


def test_looping_past_the_declared_budget_is_refused() -> None:
    payload = clean_run(iterations=4)
    payload["loop_contract"] = loop_contract(max_iterations=3)

    error = refused(payload)
    assert error.code == "ITERATION_BUDGET_EXCEEDED"
    assert error.context["used"] == 4
    assert error.context["limit"] == 3


def test_a_run_that_never_certifies_its_stop_is_refused() -> None:
    payload = clean_run()
    payload["stop_certificate"] = None

    error = refused(payload)
    assert error.code == "RUN_UNTERMINATED"


def test_a_certificate_naming_an_uncommitted_checkpoint_is_refused() -> None:
    # A certified resume point the run never committed would restore a state
    # the run never reached.
    payload = clean_run()
    payload["stop_certificate"] = stop_certificate(checkpoint_id="CP-NEVER")

    error = refused(payload)
    assert error.code == "STOP_CERTIFICATE_INVALID"
    assert error.context["findings"]["uncommitted_checkpoint"] == "CP-NEVER"


def test_a_certificate_naming_a_committed_checkpoint_is_accepted() -> None:
    payload = clean_run(iterations=2)
    payload["stop_certificate"] = stop_certificate(checkpoint_id="CP-2")
    report = evaluate_run(ROOT, **payload)

    assert report["stop_certificate"].get("uncommitted_checkpoint") is None
    require_valid_run(report)


@pytest.mark.parametrize("reason", ["blocked", "failed", "safety_stop"])
def test_an_adverse_stop_is_classified_as_such(reason: str) -> None:
    payload = clean_run()
    payload["stop_certificate"] = stop_certificate(
        reason, conditions=("the run could not continue",)
    )
    report = evaluate_run(ROOT, **payload)

    assert report["stopped_adversely"] is True


def test_a_certificate_with_an_unknown_stop_reason_is_refused() -> None:
    payload = clean_run()
    payload["stop_certificate"] = stop_certificate("we_stopped")

    error = refused(payload)
    assert error.code == "STOP_CERTIFICATE_INVALID"
    assert "unknown_stop_reason" in error.context["findings"]


def test_a_certificate_that_records_no_condition_is_refused() -> None:
    payload = clean_run()
    payload["stop_certificate"] = stop_certificate(conditions=())

    error = refused(payload)
    assert error.code == "STOP_CERTIFICATE_INVALID"
    assert "no_conditions_observed" in error.context["findings"]


def test_a_certificate_that_hides_partial_work_is_refused() -> None:
    payload = clean_run()
    payload["stop_certificate"] = stop_certificate(partial_visible=False)

    error = refused(payload)
    assert error.code == "STOP_CERTIFICATE_INVALID"
    assert "partial_work_hidden" in error.context["findings"]


def test_a_certificate_without_a_checkpoint_is_refused() -> None:
    payload = clean_run()
    payload["stop_certificate"] = stop_certificate(checkpoint_id="   ")

    error = refused(payload)
    assert error.code == "STOP_CERTIFICATE_INVALID"
    assert "no_checkpoint" in error.context["findings"]


def test_a_stop_reason_that_is_not_a_string_is_refused() -> None:
    payload = clean_run()
    certificate = stop_certificate()
    certificate["stop_reason"] = 7
    payload["stop_certificate"] = certificate

    error = raises_on_build(payload)
    assert error.code == "INPUT_INVALID"


def test_a_transition_from_an_undeclared_node_is_refused() -> None:
    payload = clean_run()
    payload["transitions"] = [
        *forward_path(),
        Transition("a_node_that_was_removed", LOOP_ENTRY, checkpoint_id="CP-1"),
    ]

    error = raises_on_build(payload)
    assert error.code == "NODE_UNDECLARED"


def test_a_transition_to_an_undeclared_node_is_refused() -> None:
    payload = clean_run()
    payload["transitions"] = [
        *forward_path(),
        Transition(LOOP_EXIT, "a_node_that_was_removed", checkpoint_id="CP-1"),
    ]

    error = raises_on_build(payload)
    assert error.code == "NODE_UNDECLARED"


def test_a_non_transition_entry_is_refused() -> None:
    payload = clean_run()
    payload["transitions"] = [*forward_path(), {"source": LOOP_EXIT}]

    error = raises_on_build(payload)
    assert error.code == "INPUT_INVALID"


def test_the_machine_reports_each_failure_class_separately() -> None:
    payload = clean_run()
    payload["transitions"] = [
        *forward_path(),
        Transition(LOOP_EXIT, LOOP_ENTRY),
        loop_back(2, complete=False),
    ]
    report = evaluate_run(ROOT, **payload)

    assert report["uncheckpointed_return_edges"]
    assert report["incomplete_checkpoints"]
    assert report["valid"] is False


def test_a_run_cannot_reach_promotion_without_its_declared_upstream() -> None:
    promotion = "run_evidence_parliament_promotion"
    upstream = GRAPH.depends_on(promotion)

    assert upstream, "promotion must depend on something"
    for source in upstream:
        report = evaluate_run(
            ROOT,
            transitions=[Transition(source, promotion)],
            loop_contract=loop_contract(),
            stop_certificate=stop_certificate(),
            dry_rounds_observed=1,
        )
        assert report["undeclared_transitions"] == [], source
