from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .compiler import FrameContractError, ScopeUnknown, UnknownSource, compile_frame


ROOT = Path(__file__).resolve().parents[4]


def sample() -> dict[str, object]:
    value = json.loads((ROOT / "examples/sample_insight.json").read_text(encoding="utf-8"))
    value["terms_to_define"] = []
    return value


def validate_canonical(card: dict[str, object]) -> None:
    scope_schema = json.loads(
        (ROOT / "schemas/scope-vector.schema.json").read_text(encoding="utf-8")
    )
    insight_schema = json.loads(
        (ROOT / "schemas/insight-card.schema.json").read_text(encoding="utf-8")
    )
    registry = Registry().with_resource(
        scope_schema["$id"], Resource.from_contents(scope_schema)
    )
    Draft202012Validator(
        insight_schema,
        registry=registry,
        format_checker=FormatChecker(),
    ).validate(card)


def test_frame_gold_test_sample_compiles_to_both_canonical_contracts() -> None:
    result = compile_frame(sample())

    validate_canonical(result.insight_card)
    Draft202012Validator(
        json.loads((ROOT / "schemas/scope-vector.schema.json").read_text(encoding="utf-8"))
    ).validate(result.scope_vector)
    assert result.council_ready is True
    assert result.council_blockers == ()


def test_frame_gold_test_preserves_sealed_metadata_without_generating_it() -> None:
    proposal = sample()
    result = compile_frame(proposal)

    assert result.insight_card["insight_id"] == proposal["insight_id"]
    assert result.insight_card["created_at"] == proposal["created_at"]
    assert result.insight_card["registration_hash"] == proposal["registration_hash"]
    assert result.insight_card["registration_hash"] == "sha256:" + "a" * 64


def test_frame_gold_test_mapping_order_does_not_change_compilation() -> None:
    proposal = sample()
    proposal["scope"] = dict(reversed(list(proposal["scope"].items())))  # type: ignore[union-attr]
    reversed_proposal = dict(reversed(list(proposal.items())))

    first = compile_frame(proposal)
    second = compile_frame(reversed_proposal)

    assert first == second
    assert first.insight_card_json == second.insight_card_json


def test_frame_gold_test_does_not_mutate_the_proposal() -> None:
    proposal = sample()
    before = copy.deepcopy(proposal)

    compile_frame(proposal)

    assert proposal == before


def test_frame_gold_test_missing_scope_values_remain_unknown_not_inferred() -> None:
    proposal = sample()
    proposal["registration_status"] = "inbox"
    proposal["scope"] = {
        "domain": "learning_science",
        "population": None,
        "unit_of_analysis": "   ",
    }

    result = compile_frame(proposal)
    scope = result.scope_vector
    unknowns = {(entry.path, entry.source) for entry in result.unknown_scope}

    assert scope["population"] is None
    assert scope["unit_of_analysis"] is None
    assert scope["geography"] is None
    assert scope["inclusion_criteria"] == []
    assert scope["conditions"] == {}
    assert ("scope.population", UnknownSource.EXPLICIT_NULL) in unknowns
    assert ("scope.unit_of_analysis", UnknownSource.BLANK_STRING) in unknowns
    assert ("scope.geography", UnknownSource.ABSENT) in unknowns
    assert ("scope.inclusion_criteria", UnknownSource.ABSENT) in unknowns
    assert ("scope.conditions", UnknownSource.ABSENT) in unknowns


def test_frame_gold_test_explicit_empty_collections_are_not_relabelled_unknown() -> None:
    proposal = sample()
    scope = proposal["scope"]
    assert isinstance(scope, dict)
    scope["inclusion_criteria"] = []
    scope["exclusion_criteria"] = []
    scope["conditions"] = {}
    scope["domain_extensions"] = {}

    result = compile_frame(proposal)
    unknown_paths = {entry.path for entry in result.unknown_scope}

    assert "scope.inclusion_criteria" not in unknown_paths
    assert "scope.exclusion_criteria" not in unknown_paths
    assert "scope.conditions" not in unknown_paths
    assert "scope.domain_extensions" not in unknown_paths


def test_frame_gold_test_partial_intervention_preserves_nested_unknowns() -> None:
    proposal = sample()
    scope = proposal["scope"]
    assert isinstance(scope, dict)
    scope["intervention_or_exposure"] = {"name": "retrieval practice"}

    result = compile_frame(proposal)
    intervention = result.scope_vector["intervention_or_exposure"]
    assert isinstance(intervention, dict)

    assert intervention["name"] == "retrieval practice"
    assert intervention["duration"] is None
    assert ScopeUnknown(
        "scope.intervention_or_exposure.duration", UnknownSource.ABSENT
    ) in result.unknown_scope
    validate_canonical(result.insight_card)


def test_frame_gold_test_domain_specific_axis_must_use_domain_extensions() -> None:
    proposal = sample()
    scope = proposal["scope"]
    assert isinstance(scope, dict)
    scope["cultivar"] = "Example"

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "SCOPE_FIELD_UNKNOWN"


def test_frame_gold_test_unknown_top_level_field_fails_closed() -> None:
    proposal = sample()
    proposal["model_confidence"] = 0.99

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "FRAME_FIELD_UNKNOWN"


def test_frame_gold_test_nonfinite_scope_value_fails_closed() -> None:
    proposal = sample()
    scope = proposal["scope"]
    assert isinstance(scope, dict)
    scope["conditions"] = {"effect": float("nan")}

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "SCOPE_INPUT_INVALID"


def test_frame_gold_test_missing_registration_hash_is_not_silently_generated() -> None:
    proposal = sample()
    del proposal["registration_hash"]

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "FRAME_FIELD_REQUIRED"


def test_frame_gold_test_naive_timestamp_is_rejected() -> None:
    proposal = sample()
    proposal["created_at"] = "2026-07-25T12:00:00"

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "FRAME_INPUT_INVALID"


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-07-25 12:00:00+00:00",
        "20260725T120000+00:00",
        "2026-07-25T12:00:00+0000",
    ],
)
def test_frame_gold_test_non_rfc3339_timestamp_forms_are_rejected(
    timestamp: str,
) -> None:
    proposal = sample()
    proposal["created_at"] = timestamp

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "FRAME_INPUT_INVALID"


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-02-29T12:00:00Z",
        "2026-07-25T24:00:00Z",
        "2026-07-25T12:00:00+24:00",
    ],
)
def test_frame_gold_test_invalid_rfc3339_calendar_or_offset_is_rejected(
    timestamp: str,
) -> None:
    proposal = sample()
    proposal["created_at"] = timestamp

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "FRAME_INPUT_INVALID"


def test_frame_gold_test_rfc3339_leap_second_is_preserved() -> None:
    proposal = sample()
    proposal["created_at"] = "2016-12-31T23:59:60Z"

    result = compile_frame(proposal)

    assert result.insight_card["created_at"] == "2016-12-31T23:59:60Z"
