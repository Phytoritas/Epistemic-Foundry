"""provenance_and_receipt_audit — every identifier is derived, nothing is minted.

This package mints five kinds of identifier and not one of them is chosen: each
is the digest of the record's own content, so two runs over equal inputs produce
byte-equal records and a relabelled record is detectably inconsistent with
itself.  That property only holds while the module reads no clock and draws no
entropy, so the module source is inspected for both rather than trusted, and
every timestamp that reaches a record is traced back to a caller argument.

The second half audits the binding chain: a lane receipt carries the plan hash
and the snapshot hash it ran inside, and the acquisition plan carries the plan
hash and every receipt identifier it reconciled, so a reader holding only the
acquisition plan can walk back to the pinned bytes.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.domain.hashing import is_schema_digest, sha256_of_payload
from epistemic_foundry.retrieval.v4_o05 import (
    ACQUISITION_ID_PREFIX,
    LAYERED_ID_PREFIX,
    PLAN_ID_PREFIX,
    RECEIPT_ID_PREFIX,
    TARGET_ID_PREFIX,
    VECTOR_ID_PREFIX,
    acquisition_plan_is_rederivable,
    assess_layered_novelty,
    build_coverage_debt_acquisition_plan,
    canonical_lane_order,
    rank_acquisition_targets,
)
from fixtures import (
    ASSESSED_AT,
    FINISHED_AT,
    STARTED_AT,
    acquisition_arguments,
    layered_arguments,
    niches,
    plan,
    receipts,
    snapshot,
)

ROOT = Path(__file__).resolve().parents[5]
PACKAGE = ROOT / "src/epistemic_foundry/retrieval/v4_o05"

#: Names that would make a record unreproducible: a clock, entropy, or an
#: identifier minted from either.
FORBIDDEN_IMPORTS = {"datetime", "random", "secrets", "time", "uuid"}
FORBIDDEN_CALLS = {"new_id", "utc_now_iso", "now", "today", "uuid4", "monotonic"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
            names.update(alias.name for alias in node.names)
    return names


def called_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name):
            names.add(function.id)
        elif isinstance(function, ast.Attribute):
            names.add(function.attr)
    return names


def test_the_package_imports_no_clock_and_no_entropy_source() -> None:
    for path in sorted(PACKAGE.glob("*.py")):
        held = imported_modules(path) & FORBIDDEN_IMPORTS
        assert not held, (path.name, sorted(held))


def test_the_package_calls_no_clock_and_mints_no_random_identifier() -> None:
    for path in sorted(PACKAGE.glob("*.py")):
        held = called_names(path) & FORBIDDEN_CALLS
        assert not held, (path.name, sorted(held))


def test_every_minted_identifier_carries_its_declared_prefix() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    rows = receipts(declared, pinned)
    layered = assess_layered_novelty(**layered_arguments(declared, pinned))
    acquisition = build_coverage_debt_acquisition_plan(
        **acquisition_arguments(declared, pinned)
    )

    assert declared["plan_id"].startswith(PLAN_ID_PREFIX)
    assert all(receipt["receipt_id"].startswith(RECEIPT_ID_PREFIX) for receipt in rows)
    assert layered["layered_novelty_id"].startswith(LAYERED_ID_PREFIX)
    assert layered["novelty_vector"]["novelty_vector_id"].startswith(VECTOR_ID_PREFIX)
    assert acquisition["acquisition_plan_id"].startswith(ACQUISITION_ID_PREFIX)
    assert all(
        target["target_id"].startswith(TARGET_ID_PREFIX)
        for target in acquisition["acquisition_targets"]
    )


def test_every_record_hash_is_the_canonical_digest_shape() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    acquisition = build_coverage_debt_acquisition_plan(
        **acquisition_arguments(declared, pinned)
    )
    layered = assess_layered_novelty(**layered_arguments(declared, pinned))

    assert is_schema_digest(declared["plan_hash"])
    assert is_schema_digest(acquisition["acquisition_plan_hash"])
    assert is_schema_digest(layered["layered_novelty_hash"])
    for receipt in receipts(declared, pinned):
        assert is_schema_digest(receipt["receipt_hash"])
        assert is_schema_digest(receipt["plan_hash"])


def test_two_runs_over_equal_inputs_produce_byte_equal_records() -> None:
    pinned = snapshot()

    first_plan = plan(pinned)
    second_plan = plan(pinned)
    assert sha256_of_payload(first_plan) == sha256_of_payload(second_plan)
    assert sha256_of_payload(receipts(first_plan, pinned)) == sha256_of_payload(
        receipts(second_plan, pinned)
    )
    assert sha256_of_payload(
        assess_layered_novelty(**layered_arguments(first_plan, pinned))
    ) == sha256_of_payload(
        assess_layered_novelty(**layered_arguments(second_plan, pinned))
    )
    assert sha256_of_payload(
        build_coverage_debt_acquisition_plan(
            **acquisition_arguments(first_plan, pinned)
        )
    ) == sha256_of_payload(
        build_coverage_debt_acquisition_plan(
            **acquisition_arguments(second_plan, pinned)
        )
    )


def test_identifiers_are_a_function_of_content_not_of_call_order() -> None:
    rows = niches()
    forward = rank_acquisition_targets(niches=rows)
    backward = rank_acquisition_targets(niches=list(reversed(rows)))

    assert [target["target_id"] for target in forward] == [
        target["target_id"] for target in backward
    ]


def test_a_change_of_content_changes_the_identifier() -> None:
    pinned = snapshot()
    first = plan(pinned)
    second = plan(pinned, run_id="ER-O05-2")

    assert first["plan_id"] != second["plan_id"]
    assert first["plan_hash"] != second["plan_hash"]


def test_every_timestamp_in_a_record_came_from_a_caller_argument() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    rows = receipts(declared, pinned)
    layered = assess_layered_novelty(**layered_arguments(declared, pinned))
    executed = [receipt for receipt in rows if receipt["started_at"] is not None]

    assert executed
    for receipt in executed:
        assert receipt["started_at"] == STARTED_AT
        assert receipt["finished_at"] == FINISHED_AT
    assert layered["assessment"]["assessed_at"] == ASSESSED_AT
    assert layered["novelty_vector"]["computed_at"] == ASSESSED_AT


def test_a_lane_receipt_binds_the_plan_and_the_pinned_snapshot_it_ran_inside() -> None:
    pinned = snapshot()
    declared = plan(pinned)

    for receipt in receipts(declared, pinned):
        assert receipt["plan_hash"] == declared["plan_hash"]
        assert receipt["query_plan_id"] == declared["query_plan_id"]
        assert receipt["run_id"] == declared["run_id"]
        if receipt["corpus_snapshot_hash"] is not None:
            assert receipt["corpus_snapshot_hash"] == pinned["snapshot_hash"]


def test_the_acquisition_plan_names_every_receipt_it_reconciled() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    rows = receipts(declared, pinned)
    acquisition = build_coverage_debt_acquisition_plan(
        **acquisition_arguments(declared, pinned, receipts=rows)
    )

    assert acquisition["lane_receipt_ids"] == [
        receipt["receipt_id"]
        for lane in canonical_lane_order()
        for receipt in rows
        if receipt["lane"] == lane
    ]
    assert acquisition["plan_hash"] == declared["plan_hash"]
    assert acquisition["corpus_snapshot_hash"] == pinned["snapshot_hash"]
    assert acquisition["snapshot_id"] == pinned["snapshot_id"]


def test_the_acquisition_plan_replays_exactly_from_the_inputs_it_names() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    arguments = acquisition_arguments(declared, pinned)
    acquisition = build_coverage_debt_acquisition_plan(**arguments)

    assert acquisition_plan_is_rederivable(
        acquisition, plan=declared, receipts=arguments["receipts"], niches=niches()
    )


def test_a_replay_over_different_niches_does_not_reproduce_the_plan() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    arguments = acquisition_arguments(declared, pinned)
    acquisition = build_coverage_debt_acquisition_plan(**arguments)
    altered = [dict(niche, coverage_debt=0.1) for niche in niches()]

    assert not acquisition_plan_is_rederivable(
        acquisition, plan=declared, receipts=arguments["receipts"], niches=altered
    )


def test_the_layered_record_binds_the_plan_the_boundary_and_both_artifacts() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    layered = assess_layered_novelty(**layered_arguments(declared, pinned))

    assert layered["plan_hash"] == declared["plan_hash"]
    assert layered["boundary_hash"] == declared["boundary_hash"]
    assert layered["assessment"]["corpus_snapshot_hash"] == pinned["snapshot_hash"]
    assert (
        layered["novelty_vector"]["external_search_certificate_id"]
        == layered["assessment"]["search_completeness_certificate_id"]
    )


def test_the_novelty_vector_identifier_is_derived_from_the_scores_it_holds() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    first = assess_layered_novelty(**layered_arguments(declared, pinned))
    second = assess_layered_novelty(
        **layered_arguments(
            declared, pinned, layer_scores={**first["layer_scores"], "scope_shift": 0.7}
        )
    )

    assert (
        first["novelty_vector"]["novelty_vector_id"]
        != second["novelty_vector"]["novelty_vector_id"]
    )
    assert first["layered_novelty_id"] != second["layered_novelty_id"]
