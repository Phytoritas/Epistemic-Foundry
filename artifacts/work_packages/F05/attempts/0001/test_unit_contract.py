"""unit_and_contract_tests — a run that searches and stops properly is accepted.

The happy paths are the ones a real EVOLVE run takes: walk the declared graph,
loop back across a sealed checkpoint once per generation, and leave through a
typed stop certificate.  Each of the orderly stop reasons must be acceptable,
because a machine that only admits one way to finish would force runs to
misreport why they stopped.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.evolution.v4_f05 import (
    Transition,
    evaluate_run,
    require_valid_run,
)
from epistemic_foundry.evolution_chamber.checkpoint import ORDERLY_STOPS
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


def test_a_clean_run_is_valid() -> None:
    report = evaluate_run(ROOT, **clean_run())

    assert report["valid"] is True
    require_valid_run(report)


def test_every_forward_edge_follows_a_declared_dependency() -> None:
    report = evaluate_run(ROOT, **clean_run())

    assert report["counts"]["forward_edges"] == sum(
        len(GRAPH.depends_on(node)) for node in GRAPH.nodes
    )


def test_the_return_edges_are_counted_separately_from_forward_moves() -> None:
    report = evaluate_run(ROOT, **clean_run(iterations=3))

    assert report["counts"]["return_edges"] == 3
    assert report["iterations"]["used"] == 3
    assert report["iterations"]["over_budget"] is False


def test_a_run_with_no_return_edge_is_still_valid() -> None:
    report = evaluate_run(
        ROOT,
        transitions=forward_path(),
        loop_contract=loop_contract(),
        stop_certificate=stop_certificate(),
        dry_rounds_observed=1,
    )

    assert report["counts"]["return_edges"] == 0
    require_valid_run(report)


def test_looping_exactly_to_the_limit_is_allowed() -> None:
    report = evaluate_run(ROOT, **clean_run(iterations=3))

    assert report["iterations"]["used"] == report["iterations"]["limit"]
    require_valid_run(report)


@pytest.mark.parametrize("reason", sorted(ORDERLY_STOPS))
def test_every_orderly_stop_reason_is_accepted(reason: str) -> None:
    payload = clean_run()
    payload["stop_certificate"] = stop_certificate(reason)

    require_valid_run(evaluate_run(ROOT, **payload))


def test_a_run_that_looped_then_hit_a_safety_stop_is_accepted() -> None:
    # Looping and then stopping for safety is the normal shape of a run that
    # discovered a problem; the stop is terminal, the loops preceded it.
    payload = clean_run()
    payload["stop_certificate"] = stop_certificate(
        "safety_stop", conditions=("challenge produced an unsafe artifact",)
    )
    report = evaluate_run(ROOT, **payload)

    assert report["stopped_adversely"] is True
    require_valid_run(report)


def test_the_report_records_the_loop_the_contract_bound() -> None:
    report = evaluate_run(ROOT, **clean_run())

    assert report["loop"] == {
        "entry_node_id": LOOP_ENTRY,
        "exit_node_id": LOOP_EXIT,
    }


def test_the_dry_round_budget_is_reported_with_its_minimum() -> None:
    payload = clean_run()
    payload["dry_rounds_observed"] = 2
    report = evaluate_run(ROOT, **payload)

    assert report["dry_round_budget"] == {
        "minimum": 1,
        "observed": 2,
        "shortfall": 0,
    }


def test_a_short_dry_round_count_is_reported_rather_than_hidden() -> None:
    payload = clean_run()
    payload["dry_rounds_observed"] = 0
    payload["loop_contract"] = loop_contract(dry_rounds_required=2)
    report = evaluate_run(ROOT, **payload)

    assert report["dry_round_budget"]["shortfall"] == 2


def test_the_certificate_preserved_work_is_counted() -> None:
    report = evaluate_run(ROOT, **clean_run())

    assert report["stop_certificate"]["preserved_work"] == {
        "unassessed_niches": 1,
        "unresolved_candidates": 1,
    }


def test_a_run_still_in_progress_reports_without_a_certificate() -> None:
    payload = clean_run()
    payload["stop_certificate"] = None
    report = evaluate_run(ROOT, **payload)

    assert report["terminated"] is False
    assert report["stop_certificate"] is None
    # Still-running is not the same as invalid; only require_valid_run refuses.
    assert report["undeclared_transitions"] == []


def test_a_checkpoint_payload_is_optional_when_the_id_is_present() -> None:
    moves = [*forward_path(), Transition(LOOP_EXIT, LOOP_ENTRY, checkpoint_id="CP-1")]
    report = evaluate_run(
        ROOT,
        transitions=moves,
        loop_contract=loop_contract(),
        stop_certificate=stop_certificate(),
        dry_rounds_observed=1,
    )

    assert report["counts"]["return_edges"] == 1
    require_valid_run(report)


def test_a_complete_checkpoint_payload_is_accepted() -> None:
    report = evaluate_run(
        ROOT,
        transitions=[*forward_path(), loop_back(1)],
        loop_contract=loop_contract(),
        stop_certificate=stop_certificate(),
        dry_rounds_observed=1,
    )

    assert report["incomplete_checkpoints"] == []
    require_valid_run(report)


def test_evaluation_is_deterministic() -> None:
    payload = clean_run()

    assert evaluate_run(ROOT, **payload) == evaluate_run(ROOT, **payload)


def test_the_report_is_serialisable_evidence() -> None:
    import json

    report = evaluate_run(ROOT, **clean_run())

    assert json.loads(json.dumps(report, ensure_ascii=False, sort_keys=True)) == report
