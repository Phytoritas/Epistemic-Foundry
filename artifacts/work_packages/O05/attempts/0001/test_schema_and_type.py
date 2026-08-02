"""schema_and_type_check — the package reads its vocabulary, never restates it.

Lane names, lane order, receipt states, receipt kinds, sentinel reasons, stop
reasons, plan dispositions and novelty layers all come from the canonical
schemas that declare them, and every position the module selects by index is
asserted here against the schema text so the assumption cannot rot in silence.
Two of those assumptions are cross-schema — the certificate's positional lane
order against the receipt's lane set, and the receipt's first three states
against the four-state vocabulary `retrieval/search_state.py` owns — and both
are pinned rather than trusted.  The last test is the package-scoped form of
EF4-I22: these modules must hold *no* canonical enum value as a literal at all.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from epistemic_foundry.contracts import default_registry, validate_artifact
from epistemic_foundry.evaluation.novelty_layers import NOVELTY_LAYERS
from epistemic_foundry.evidence.v4_k05 import (
    NOVELTY_SCHEMA,
    NOVELTY_STATUS_POSITION,
    PROMOTION_CEILING_POSITION,
    scalar_enum_field,
)
from epistemic_foundry.retrieval.search_state import SearchState
from epistemic_foundry.retrieval.v4_o05 import (
    ADVERSARIAL_LANE_POSITIONS,
    CERTIFICATE_SCHEMA,
    EXECUTION_KIND_POSITION,
    EXHAUSTED_STOP_POSITION,
    EXTERNAL_LANE_POSITION,
    EXTERNAL_LAYER_POSITION,
    FINDING_CODES,
    NICHE_SCHEMA,
    RECEIPT_SCHEMA,
    SEARCHED_NONE_STATE_POSITION,
    SEARCHED_WITH_RESULTS_STATE_POSITION,
    SELECTED_DISPOSITION_POSITION,
    SENTINEL_KIND_POSITION,
    UNSEARCHED_STATE_POSITION,
    VECTOR_SCHEMA,
    AcquisitionError,
    adversarial_lanes,
    assess_layered_novelty,
    build_coverage_debt_acquisition_plan,
    canonical_lane_order,
    coverage_state,
    external_novelty_lane,
    lane_vocabulary,
    novelty_layer_vocabulary,
    plan_disposition_vocabulary,
    receipt_kind_vocabulary,
    receipt_state_vocabulary,
    sentinel_reason_vocabulary,
    stop_reason_vocabulary,
)
from epistemic_foundry.retrieval.v4_o05 import acquisition as acquisition_module
from fixtures import acquisition_arguments, layered_arguments, plan, receipts, snapshot

ROOT = Path(__file__).resolve().parents[5]
PACKAGE = ROOT / "src/epistemic_foundry/retrieval/v4_o05"


def string_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstrings.add(id(value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def canonical_enum_values() -> set[str]:
    values: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            enum = node.get("enum")
            if isinstance(enum, list):
                values.update(item for item in enum if isinstance(item, str))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    registry = default_registry()
    for name in registry.names():
        walk(registry.document(name))
    return values


def test_the_lane_vocabulary_is_the_receipt_schemas_own_declaration() -> None:
    document = default_registry().document(RECEIPT_SCHEMA)

    assert list(lane_vocabulary()) == document["$defs"]["lane"]["enum"]
    assert list(lane_vocabulary()) == [
        "lexical",
        "semantic",
        "citation",
        "entity_variable",
        "mechanism",
        "counterevidence",
        "null",
        "boundary",
        "method",
        "temporal",
        "external_novelty",
    ]


def test_the_certificate_pins_the_lane_order_the_receipt_only_sets() -> None:
    # The receipt declares the lanes as an unordered enum; only the
    # certificate's positional reconciliation slots pin an order, so the module
    # reads the order from there and cross-checks the two.
    document = default_registry().document(CERTIFICATE_SCHEMA)
    rows = document["properties"]["lane_reconciliations"]["prefixItems"]

    assert len(rows) == 11
    assert canonical_lane_order() == tuple(
        row["allOf"][1]["properties"]["lane"]["const"] for row in rows
    )
    assert set(canonical_lane_order()) == set(lane_vocabulary())


def test_the_adversarial_and_external_lane_positions_are_the_named_lanes() -> None:
    assert adversarial_lanes() == (
        "counterevidence",
        "null",
        "boundary",
        "method",
        "external_novelty",
    )
    assert external_novelty_lane() == "external_novelty"
    assert canonical_lane_order()[EXTERNAL_LANE_POSITION] == "external_novelty"
    assert set(ADVERSARIAL_LANE_POSITIONS) <= set(range(len(canonical_lane_order())))


def test_the_receipt_state_vocabulary_is_declared_unsearched_first() -> None:
    document = default_registry().document(RECEIPT_SCHEMA)

    assert document["properties"]["search_state"]["enum"] == [
        "UNSEARCHED",
        "SEARCHED_NONE",
        "SEARCHED_WITH_RESULTS",
        "PARTIAL",
        "BLOCKED",
        "FAILED",
    ]
    states = receipt_state_vocabulary()
    assert states[UNSEARCHED_STATE_POSITION] == SearchState.UNSEARCHED.value
    assert states[SEARCHED_NONE_STATE_POSITION] == SearchState.SEARCHED_NONE.value
    assert (
        states[SEARCHED_WITH_RESULTS_STATE_POSITION]
        == SearchState.SEARCHED_WITH_RESULTS.value
    )


def test_the_extra_receipt_states_project_onto_the_failed_coverage_state() -> None:
    # The three states the four-state vocabulary does not own are all cases
    # where the lane did not conclusively answer; projecting them onto
    # "searched and found nothing" is the inference EF4-I05 exists to block.
    states = receipt_state_vocabulary()
    conclusive = states[: SEARCHED_WITH_RESULTS_STATE_POSITION + 1]

    for state in conclusive:
        assert coverage_state(state) is SearchState(state)
    for state in states[SEARCHED_WITH_RESULTS_STATE_POSITION + 1 :]:
        assert coverage_state(state) is SearchState.SEARCH_FAILED


def test_the_receipt_kind_and_stop_reason_positions_match_the_schema() -> None:
    document = default_registry().document(RECEIPT_SCHEMA)

    assert document["properties"]["receipt_kind"]["enum"] == ["SENTINEL", "EXECUTION"]
    assert receipt_kind_vocabulary()[SENTINEL_KIND_POSITION] == "SENTINEL"
    assert receipt_kind_vocabulary()[EXECUTION_KIND_POSITION] == "EXECUTION"
    assert stop_reason_vocabulary()[EXHAUSTED_STOP_POSITION] == "exhausted_query_plan"
    assert stop_reason_vocabulary()[0] is None


def test_the_sentinel_reasons_align_positionally_with_the_dispositions() -> None:
    # A sentinel receipt carries the plan's own disposition rather than a second
    # vocabulary, which is only sound while the two lists agree position for
    # position after the selecting one.
    dispositions = plan_disposition_vocabulary()
    reasons = sentinel_reason_vocabulary()

    assert dispositions == ("SELECTED", "NOT_REQUIRED_FOR_CLASS", "NOT_APPLICABLE")
    assert reasons == (None, "NOT_REQUIRED_FOR_CLASS", "NOT_APPLICABLE")
    assert dispositions[SELECTED_DISPOSITION_POSITION] == "SELECTED"
    for position in range(SELECTED_DISPOSITION_POSITION + 1, len(dispositions)):
        assert dispositions[position] == reasons[position]


def test_the_novelty_layers_come_from_the_vector_schemas_own_dimensions() -> None:
    document = default_registry().document(VECTOR_SCHEMA)

    assert novelty_layer_vocabulary() == tuple(
        document["properties"]["dimensions"]["properties"]
    )
    # The layer owner restates the same list as a module constant; the two must
    # not drift, and this is where that is checked rather than assumed.
    assert novelty_layer_vocabulary() == NOVELTY_LAYERS
    assert novelty_layer_vocabulary()[EXTERNAL_LAYER_POSITION] == "external_prior_art"


def test_the_niche_schema_is_what_bounds_coverage_debt() -> None:
    document = default_registry().document(NICHE_SCHEMA)
    debt = document["properties"]["coverage_debt"]

    assert debt["minimum"] == 0
    assert debt["maximum"] == 1


def test_the_inherited_ladder_stays_below_the_top_of_both_canonical_ladders() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    layered = assess_layered_novelty(**layered_arguments(declared, pinned))
    _, status_ladder = scalar_enum_field(NOVELTY_SCHEMA, NOVELTY_STATUS_POSITION)
    _, ceiling_ladder = scalar_enum_field(NOVELTY_SCHEMA, PROMOTION_CEILING_POSITION)

    assert layered["inherited_status"] != status_ladder[-1]
    assert layered["inherited_ceiling"] != ceiling_ladder[-1]
    assert layered["inherited_status"] in status_ladder
    assert layered["inherited_ceiling"] in ceiling_ladder


def test_the_emitted_records_validate_against_their_canonical_schemas() -> None:
    pinned = snapshot()
    declared = plan(pinned)
    for receipt in receipts(declared, pinned):
        validate_artifact(RECEIPT_SCHEMA, receipt)
    layered = assess_layered_novelty(**layered_arguments(declared, pinned))
    validate_artifact(VECTOR_SCHEMA, layered["novelty_vector"])
    validate_artifact(NOVELTY_SCHEMA, layered["assessment"])
    acquisition = build_coverage_debt_acquisition_plan(
        **acquisition_arguments(declared, pinned)
    )
    assert acquisition["ranked_niche_count"] == 3


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 22
    for code, reason in FINDING_CODES.items():
        assert code == code.upper()
        assert code.replace("_", "").isalpha(), code
        assert len(reason) > 50, code


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = AcquisitionError("RESULT_OUTSIDE_SNAPSHOT", "message", {"a": 1})

    assert error.code == "RESULT_OUTSIDE_SNAPSHOT"
    assert str(error) == "message"
    assert error.context == {"a": 1}


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(AcquisitionError) as caught:
        acquisition_module._fail("INVENTED_CODE", "message")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context == {"code": "INVENTED_CODE"}


def test_the_package_holds_no_canonical_enum_literal_at_all() -> None:
    # The package-scoped form of EF4-I22. The repository gate says the same
    # thing for every module; running it here means an O05 regression is
    # attributed to O05 rather than surfacing as a repository-wide failure.
    held = {
        path.name: sorted(string_literals(path) & canonical_enum_values())
        for path in sorted(PACKAGE.glob("*.py"))
    }

    assert all(not values for values in held.values()), held
