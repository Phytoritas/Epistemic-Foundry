"""schema_and_type_check — the planner reads its vocabulary, never invents it.

Every value this component decides against is declared somewhere in
``schemas/``: the plan and cascade field sets, the stage classes and failure
actions, the prediction directions, the falsifier trigger types and
severities, the port collections and the canonical ``sha256`` pattern V01
already reads.  The two local decision tables — which port collections each
plan surface may reference, and which comparators can falsify each declared
direction — are pinned here against the schema that declares their keys and
values, because a schema edit that reordered or renamed an enum would silently
move a rule, and this suite is where that has to fail instead.

The comparator set is the one vocabulary with no canonical declaration
anywhere in ``schemas/``; it is local by necessity, so it is pinned here in its
exact form to keep that visible.  The finding vocabulary is checked for the
thing that makes a refusal usable: a reason a reader can act on rather than a
bare code, and a code for every criterion the module actually decides.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .contracts import (
    COMPARATORS,
    DIRECTION_COMPARATORS,
    FALSIFIER_SCHEMA_PATH,
    FINDING_CODES,
    PLAN_SCHEMA_PATH,
    PREDICTION_SCHEMA_PATH,
    REFERENCE_DIRECTION,
    SEALED_PLAN_FIELDS,
    CASCADE_SCHEMA_PATH,
    ValidationPlanError,
    cascade_fields,
    direction_table,
    falsifier_fields,
    falsifier_severities,
    falsifier_trigger_types,
    falsifying_comparators,
    plan_fields,
    plan_validator,
    port_collections,
    prediction_directions,
    prediction_fields,
    stage_classes,
    stage_failure_actions,
    stage_fields,
)

ROOT = Path(__file__).resolve().parents[4]
MINIMUM_REASON_LENGTH = 50


def schema(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_the_plan_field_set_comes_from_the_schema() -> None:
    document = schema(PLAN_SCHEMA_PATH)

    assert plan_fields(ROOT) == frozenset(document["required"])
    assert len(plan_fields(ROOT)) == 27


def test_the_cascade_and_stage_field_sets_come_from_the_schema() -> None:
    document = schema(CASCADE_SCHEMA_PATH)

    assert cascade_fields(ROOT) == frozenset(document["required"])
    assert stage_fields(ROOT) == frozenset(
        document["properties"]["stages"]["items"]["required"]
    )


def test_the_stage_classes_and_failure_actions_come_from_the_schema() -> None:
    stage = schema(CASCADE_SCHEMA_PATH)["properties"]["stages"]["items"]["properties"]

    assert stage_classes(ROOT) == tuple(stage["stage_class"]["enum"])
    assert stage_failure_actions(ROOT) == tuple(stage["failure_action"]["enum"])
    assert len(stage_classes(ROOT)) == 8


def test_the_prediction_directions_come_from_the_schema() -> None:
    document = schema(PREDICTION_SCHEMA_PATH)

    assert prediction_directions(ROOT) == tuple(
        document["properties"]["expected_direction"]["enum"]
    )
    assert prediction_fields(ROOT) == frozenset(document["required"])


def test_the_falsifier_vocabulary_comes_from_the_schema() -> None:
    document = schema(FALSIFIER_SCHEMA_PATH)

    assert falsifier_trigger_types(ROOT) == tuple(
        document["properties"]["trigger_type"]["enum"]
    )
    assert falsifier_severities(ROOT) == tuple(
        document["properties"]["severity"]["enum"]
    )
    assert falsifier_fields(ROOT) == frozenset(document["required"])


def test_the_port_collections_are_read_from_the_manifest_schema() -> None:
    assert port_collections(ROOT) == (
        "inputs",
        "outputs",
        "parameters",
        "state_variables",
    )


def test_the_reference_direction_table_covers_only_declared_collections() -> None:
    table = direction_table(ROOT)

    assert set(table) == set(REFERENCE_DIRECTION)
    for allowed in table.values():
        assert set(allowed) <= set(port_collections(ROOT))
    assert table["observables"] == ("outputs",)
    assert table["falsification_rule"] == ("outputs",)


def test_the_comparator_set_is_local_and_pinned() -> None:
    # No canonical schema declares a comparator vocabulary, so this set has no
    # schema to be checked against; pinning it here is what keeps it visible.
    assert COMPARATORS == ("<", "<=", "==", "!=", ">=", ">")


def test_the_falsifying_comparator_table_covers_every_declared_direction() -> None:
    table = falsifying_comparators(ROOT)

    assert set(table) == set(prediction_directions(ROOT))
    assert set(DIRECTION_COMPARATORS) == set(prediction_directions(ROOT))
    for allowed in table.values():
        assert set(allowed) <= set(COMPARATORS)


def test_a_qualitative_prediction_has_no_comparator_that_could_refute_it() -> None:
    table = falsifying_comparators(ROOT)

    assert table["qualitative"] == ()
    assert table["increase"] == ("<", "<=")
    assert table["decrease"] == (">", ">=")


def test_the_sealed_plan_fields_are_a_subset_of_the_plan_fields() -> None:
    # The seal freezes what would have to move for a result to change the plan;
    # every sealed field must therefore be a real plan field, and the title and
    # objective must stay outside the seal so a plan may be re-described.
    assert set(SEALED_PLAN_FIELDS) <= set(plan_fields(ROOT))
    assert "objective" not in SEALED_PLAN_FIELDS
    assert "plan_id" not in SEALED_PLAN_FIELDS
    assert "preregistration_hash" not in SEALED_PLAN_FIELDS


def test_the_plan_validator_resolves_its_cross_document_references() -> None:
    assert plan_validator(ROOT) is not None


def test_every_finding_code_carries_an_actionable_reason() -> None:
    short = {
        code: reason
        for code, reason in FINDING_CODES.items()
        if len(reason) <= MINIMUM_REASON_LENGTH
    }

    assert short == {}
    assert sorted(FINDING_CODES) == list(FINDING_CODES)


def test_an_unreadable_schema_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValidationPlanError) as error:
        plan_fields(tmp_path)

    assert error.value.code == "SCHEMA_UNREADABLE"
