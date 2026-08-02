"""contradiction_fixture_test — every disagreement is typed before it is filed.

Exit criterion under test: "condition differences classified".  Two findings
pointing opposite ways are not automatically a contradiction; the engine must
say whether the conditions, the measurement, or the world differ, and a pair it
cannot type fails closed rather than defaulting to contradiction.
"""

from __future__ import annotations

import pytest

from .contracts import (
    ConflictType,
    Direction,
    ExplanationKind,
    ExplanationStatus,
    AporiaContractError,
    build_aporia_record,
    classify_conflict,
    classify_conflicts,
    directions_conflict,
    validate_aporia_record,
)

CREATED_AT = "2026-08-01T11:00:00Z"
SUBJECT = "INS-1"


def observation(
    observation_id: str,
    direction: str,
    *,
    conditions: dict[str, object] | None = None,
    measurement_ref: str | None = "METHOD-a",
    evidence_id: str | None = None,
) -> dict[str, object]:
    return {
        "conditions": dict(conditions or {}),
        "direction": direction,
        "evidence_id": evidence_id or f"EVN-{observation_id}",
        "measurement_ref": measurement_ref,
        "observation_id": observation_id,
        "provenance_ref": f"prov:{observation_id}",
    }


def explanation(
    explanation_id: str,
    kind: str,
    covers: list[str],
    *,
    status: str = ExplanationStatus.STANDING.value,
    refuted_by: list[str] | None = None,
    tests: list[str] | None = None,
) -> dict[str, object]:
    return {
        "covers": list(covers),
        "discriminating_tests": (
            [f"TEST-{explanation_id}"] if tests is None else list(tests)
        ),
        "explanation_id": explanation_id,
        "explanation_kind": kind,
        "refuted_by_evidence_ids": list(refuted_by or []),
        "statement": f"statement for {explanation_id}",
        "status": status,
    }


def contradiction_pair() -> list[dict[str, object]]:
    return [
        observation("OBS-a", Direction.POSITIVE.value),
        observation("OBS-b", Direction.NEGATIVE.value),
    ]


def two_kinds(conflict_id: str) -> list[dict[str, object]]:
    return [
        explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict_id]),
        explanation("EXP-2", ExplanationKind.CONFOUNDING.value, [conflict_id]),
    ]


def test_identical_conditions_and_measurement_are_a_direct_contradiction() -> None:
    conflicts = classify_conflicts(contradiction_pair())

    assert len(conflicts) == 1
    assert conflicts[0]["conflict_type"] == ConflictType.DIRECT_CONTRADICTION.value
    assert conflicts[0]["differing_conditions"] == []
    assert conflicts[0]["left_observation_id"] == "OBS-a"
    assert conflicts[0]["right_observation_id"] == "OBS-b"


def test_a_differing_condition_is_not_yet_a_contradiction() -> None:
    conflicts = classify_conflicts(
        [
            observation("OBS-a", Direction.POSITIVE.value, conditions={"temp_c": 20}),
            observation("OBS-b", Direction.NEGATIVE.value, conditions={"temp_c": 30}),
        ]
    )

    assert conflicts[0]["conflict_type"] == ConflictType.CONDITION_DIFFERENCE.value
    assert conflicts[0]["differing_conditions"] == ["temp_c"]
    assert "not yet a contradiction" in conflicts[0]["rationale"]


def test_a_strictly_refined_condition_set_is_reported_as_nested() -> None:
    conflicts = classify_conflicts(
        [
            observation("OBS-a", Direction.POSITIVE.value, conditions={"temp_c": 20}),
            observation(
                "OBS-b",
                Direction.NEGATIVE.value,
                conditions={"temp_c": 20, "co2_ppm": 800},
            ),
        ]
    )

    assert conflicts[0]["conflict_type"] == ConflictType.SCOPE_NESTED.value
    assert conflicts[0]["differing_conditions"] == ["co2_ppm"]
    assert "boundary case" in conflicts[0]["rationale"]


def test_the_same_conditions_measured_differently_is_a_measurement_difference() -> None:
    conflicts = classify_conflicts(
        [
            observation("OBS-a", Direction.POSITIVE.value, measurement_ref="METHOD-a"),
            observation("OBS-b", Direction.NEGATIVE.value, measurement_ref="METHOD-b"),
        ]
    )

    assert conflicts[0]["conflict_type"] == ConflictType.MEASUREMENT_DIFFERENCE.value
    assert "artefact of the instrument" in conflicts[0]["rationale"]


def test_a_missing_measurement_on_one_side_cannot_be_typed() -> None:
    record = classify_conflict(
        observation("OBS-a", Direction.POSITIVE.value, measurement_ref="METHOD-a"),
        observation("OBS-b", Direction.NEGATIVE.value, measurement_ref=None),
    )

    assert record is not None
    assert record["conflict_type"] == ConflictType.UNCLASSIFIED.value


def test_an_unclassified_conflict_cannot_be_sealed() -> None:
    observations = [
        observation("OBS-a", Direction.POSITIVE.value, measurement_ref="METHOD-a"),
        observation("OBS-b", Direction.NEGATIVE.value, measurement_ref=None),
    ]

    with pytest.raises(AporiaContractError) as caught:
        build_aporia_record(observations, [], subject_id=SUBJECT, created_at=CREATED_AT)

    assert caught.value.code == "CONFLICT_UNCLASSIFIED"


@pytest.mark.parametrize(
    ("left", "right", "conflicts"),
    [
        (Direction.POSITIVE.value, Direction.NEGATIVE.value, True),
        (Direction.POSITIVE.value, Direction.NULL.value, True),
        (Direction.NEGATIVE.value, Direction.NULL.value, True),
        (Direction.POSITIVE.value, Direction.NONMONOTONIC.value, True),
        (Direction.POSITIVE.value, Direction.POSITIVE.value, False),
        (Direction.POSITIVE.value, Direction.UNKNOWN.value, False),
        (Direction.NEGATIVE.value, Direction.MIXED.value, False),
        (Direction.NULL.value, Direction.NOT_APPLICABLE.value, False),
    ],
)
def test_only_assertive_opposite_directions_conflict(
    left: str, right: str, conflicts: bool
) -> None:
    assert directions_conflict(left, right) is conflicts
    assert directions_conflict(right, left) is conflicts


def test_agreeing_observations_produce_no_conflict_and_no_aporia() -> None:
    record = build_aporia_record(
        [
            observation("OBS-a", Direction.POSITIVE.value),
            observation("OBS-b", Direction.POSITIVE.value),
        ],
        [],
        subject_id=SUBJECT,
        created_at=CREATED_AT,
    ).payload

    assert record["conflicts"] == []
    assert record["status"] == "NO_CONFLICT"
    assert record["explanation_kind_counts"] == {}


def test_every_pair_is_examined_not_just_neighbours() -> None:
    conflicts = classify_conflicts(
        [
            observation("OBS-a", Direction.POSITIVE.value),
            observation("OBS-b", Direction.POSITIVE.value),
            observation("OBS-c", Direction.NEGATIVE.value),
        ]
    )

    assert len(conflicts) == 2
    assert {entry["right_observation_id"] for entry in conflicts} == {"OBS-c"}


def test_conflict_ids_are_stable_under_input_order() -> None:
    pair = contradiction_pair()

    forward = classify_conflicts(pair)
    reversed_order = classify_conflicts(list(reversed(pair)))

    assert forward == reversed_order


def test_a_duplicate_observation_id_is_refused() -> None:
    observations = [
        observation("OBS-a", Direction.POSITIVE.value),
        observation("OBS-a", Direction.NEGATIVE.value),
    ]

    with pytest.raises(AporiaContractError) as caught:
        build_aporia_record(observations, [], subject_id=SUBJECT, created_at=CREATED_AT)

    assert caught.value.code == "DUPLICATE_OBSERVATION"


def test_a_non_canonical_direction_is_refused() -> None:
    observations = [observation("OBS-a", "sort of positive")]

    with pytest.raises(AporiaContractError) as caught:
        build_aporia_record(observations, [], subject_id=SUBJECT, created_at=CREATED_AT)

    assert caught.value.code == "DIRECTION_INVALID"


def test_a_typed_conflict_seals_with_its_competing_explanations() -> None:
    observations = contradiction_pair()
    conflict_id = classify_conflicts(observations)[0]["conflict_id"]

    record = build_aporia_record(
        observations,
        two_kinds(conflict_id),
        subject_id=SUBJECT,
        created_at=CREATED_AT,
    ).payload

    assert record["status"] == "OPEN"
    assert (
        record["conflicts"][0]["conflict_type"]
        == ConflictType.DIRECT_CONTRADICTION.value
    )
    assert record["explanation_kind_counts"][conflict_id] == [
        "CONFOUNDING",
        "MODERATION",
    ]
    assert record["aporia_id"].startswith("AP-")


def test_the_record_is_deterministic_and_content_addressed() -> None:
    observations = contradiction_pair()
    conflict_id = classify_conflicts(observations)[0]["conflict_id"]

    first = build_aporia_record(
        observations, two_kinds(conflict_id), subject_id=SUBJECT, created_at=CREATED_AT
    )
    second = build_aporia_record(
        observations, two_kinds(conflict_id), subject_id=SUBJECT, created_at=CREATED_AT
    )

    assert first.canonical_bytes == second.canonical_bytes
    assert (
        validate_aporia_record(first.payload).canonical_bytes == first.canonical_bytes
    )


def test_a_tampered_record_is_rejected() -> None:
    observations = contradiction_pair()
    conflict_id = classify_conflicts(observations)[0]["conflict_id"]
    payload = build_aporia_record(
        observations, two_kinds(conflict_id), subject_id=SUBJECT, created_at=CREATED_AT
    ).payload
    payload["conflicts"][0]["conflict_type"] = ConflictType.CONDITION_DIFFERENCE.value

    with pytest.raises(AporiaContractError) as caught:
        validate_aporia_record(payload)

    assert caught.value.code == "APORIA_HASH_MISMATCH"


def test_downgrading_a_conflict_to_unclassified_is_refused_even_when_rehashed() -> None:
    from .contracts import _hash_excluding

    observations = contradiction_pair()
    conflict_id = classify_conflicts(observations)[0]["conflict_id"]
    payload = build_aporia_record(
        observations, two_kinds(conflict_id), subject_id=SUBJECT, created_at=CREATED_AT
    ).payload
    payload["conflicts"][0]["conflict_type"] = ConflictType.UNCLASSIFIED.value
    payload["aporia_hash"] = _hash_excluding(payload, "aporia_hash")

    with pytest.raises(AporiaContractError) as caught:
        validate_aporia_record(payload)

    assert caught.value.code == "CONFLICT_UNCLASSIFIED"


def test_an_unexplained_conflict_cannot_be_recorded_as_such() -> None:
    from .contracts import _hash_excluding

    observations = contradiction_pair()
    conflict_id = classify_conflicts(observations)[0]["conflict_id"]
    payload = build_aporia_record(
        observations, two_kinds(conflict_id), subject_id=SUBJECT, created_at=CREATED_AT
    ).payload
    payload["unexplained_conflict_ids"] = [conflict_id]
    payload["aporia_hash"] = _hash_excluding(payload, "aporia_hash")

    with pytest.raises(AporiaContractError) as caught:
        validate_aporia_record(payload)

    assert caught.value.code == "CONFLICT_UNEXPLAINED"
