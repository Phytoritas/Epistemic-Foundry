"""provenance_and_receipt_audit — a stop is certified, not merely recorded.

The receipt that matters here is the stop certificate: it is what turns "the run
ended" into evidence a later reader can act on.  So the audit checks that the
certificate the runtime actually mints satisfies its canonical schema, that it
carries a self-hash re-derivable from its content, that it cannot hide partial
work, and that the checkpoint it names binds every component a resume point
needs.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.evolution.v4_f05 import evaluate_run, require_valid_run
from epistemic_foundry.evolution_chamber.checkpoint import (
    CHECKPOINT_COMPONENTS,
    build_evolution_checkpoint,
    build_stop_certificate,
    missing_components,
    stop_was_orderly,
)
from epistemic_foundry.noetic_ledger.receipts import hash_excluding
from fixtures import ROOT, RUN_ID, checkpoint, clean_run, stop_certificate


def minted_certificate(reason: str = "dry_rounds") -> dict:
    """A certificate from the runtime's own builder, schema-validated."""

    return build_stop_certificate(
        evolution_run_id=RUN_ID,
        stop_reason=reason,
        conditions_observed=["no fresh candidates for two rounds"],
        unresolved_candidates=["CAND-9"],
        unassessed_niches=["NICHE-3"],
        checkpoint_id="CP-1",
    )


def test_the_minted_certificate_hash_is_recomputable() -> None:
    certificate = minted_certificate()

    assert (
        hash_excluding(certificate, "certificate_hash")
        == (certificate["certificate_hash"])
    )


def test_the_minted_certificate_cannot_hide_partial_work() -> None:
    certificate = minted_certificate()

    assert certificate["partial_results_visible"] is True
    assert certificate["unresolved_candidates"] == ["CAND-9"]
    assert certificate["unassessed_niches"] == ["NICHE-3"]


def test_an_unexplained_stop_has_no_certificate() -> None:
    with pytest.raises(ValueError):
        build_stop_certificate(
            evolution_run_id=RUN_ID,
            stop_reason="dry_rounds",
            conditions_observed=[],
            unresolved_candidates=[],
            unassessed_niches=[],
            checkpoint_id="CP-1",
        )


def test_the_machine_accepts_the_runtime_minted_certificate() -> None:
    payload = clean_run()
    payload["stop_certificate"] = minted_certificate()

    require_valid_run(evaluate_run(ROOT, **payload))


def test_an_orderly_stop_is_classified_by_the_declaring_module() -> None:
    assert stop_was_orderly(minted_certificate()) is True
    assert stop_was_orderly(minted_certificate("failed")) is False


def test_a_complete_checkpoint_reports_no_missing_component() -> None:
    assert missing_components(checkpoint()) == []


def test_every_declared_component_is_required_for_a_resume_point() -> None:
    for component in CHECKPOINT_COMPONENTS:
        payload = checkpoint()
        del payload[component]
        assert missing_components(payload) == [component], component


def test_a_minted_checkpoint_carries_a_recomputable_hash() -> None:
    built = build_evolution_checkpoint(
        evolution_run_id=RUN_ID,
        generation=1,
        **checkpoint(),
    )

    assert hash_excluding(built, "checkpoint_hash") == built["checkpoint_hash"]
    assert built["evolution_run_id"] == RUN_ID


def test_the_report_names_the_checkpoint_each_return_edge_crossed() -> None:
    report = evaluate_run(ROOT, **clean_run(iterations=2))

    assert report["counts"]["return_edges"] == 2
    assert report["incomplete_checkpoints"] == []
    assert report["uncheckpointed_return_edges"] == []


def test_the_machine_mints_nothing_of_its_own() -> None:
    """The state machine reads receipts; it does not create them."""

    payload = clean_run()
    before = dict(payload["stop_certificate"])
    evaluate_run(ROOT, **payload)

    assert payload["stop_certificate"] == before


def test_a_certificate_the_machine_rejects_still_reports_its_preserved_work() -> None:
    payload = clean_run()
    payload["stop_certificate"] = stop_certificate(partial_visible=False)
    report = evaluate_run(ROOT, **payload)

    assert report["stop_certificate"]["partial_work_hidden"] is True
    assert report["stop_certificate"]["preserved_work"]["unresolved_candidates"] == 1
