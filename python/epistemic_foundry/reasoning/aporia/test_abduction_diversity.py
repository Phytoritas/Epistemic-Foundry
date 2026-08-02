"""abduction_diversity_test — competing explanations survive.

Exit criterion under test: "competing explanations survive".  A conflict
explained by one kind of story is a monoculture and is refused; an explanation
with no discriminating test cannot compete; a refuted explanation stays in the
record with its refutation; and R03 never selects a winner.
"""

from __future__ import annotations

import pytest

from .contracts import (
    ADJUDICATION_OWNER,
    EXPLANATION_KINDS,
    MINIMUM_COMPETING_EXPLANATIONS,
    AporiaContractError,
    ExplanationKind,
    ExplanationStatus,
    build_aporia_record,
    classify_conflicts,
    competing_kinds,
    validate_aporia_record,
)
from .test_contradiction_fixture import (
    CREATED_AT,
    SUBJECT,
    contradiction_pair,
    explanation,
    observation,
)
from .contracts import Direction


def conflict_id_for(observations: list[dict[str, object]]) -> str:
    return classify_conflicts(observations)[0]["conflict_id"]


def sealed(
    observations: list[dict[str, object]], explanations: list[dict[str, object]]
) -> dict[str, object]:
    return build_aporia_record(
        observations, explanations, subject_id=SUBJECT, created_at=CREATED_AT
    ).payload


def test_two_distinct_kinds_satisfy_the_diversity_floor() -> None:
    observations = contradiction_pair()
    conflict = conflict_id_for(observations)

    record = sealed(
        observations,
        [
            explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
            explanation(
                "EXP-2", ExplanationKind.MEASUREMENT_ARTIFACT.value, [conflict]
            ),
        ],
    )

    assert MINIMUM_COMPETING_EXPLANATIONS == 2
    assert record["explanation_kind_counts"][conflict] == [
        "MEASUREMENT_ARTIFACT",
        "MODERATION",
    ]


def test_a_single_explanation_is_a_monoculture() -> None:
    observations = contradiction_pair()
    conflict = conflict_id_for(observations)

    with pytest.raises(AporiaContractError) as caught:
        sealed(
            observations,
            [explanation("EXP-1", ExplanationKind.CHANCE.value, [conflict])],
        )

    assert caught.value.code == "EXPLANATION_MONOCULTURE"
    assert caught.value.context["required"] == 2


def test_two_restatements_of_one_kind_are_not_competing() -> None:
    observations = contradiction_pair()
    conflict = conflict_id_for(observations)

    with pytest.raises(AporiaContractError) as caught:
        sealed(
            observations,
            [
                explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
                explanation("EXP-2", ExplanationKind.MODERATION.value, [conflict]),
            ],
        )

    assert caught.value.code == "EXPLANATION_MONOCULTURE"
    assert caught.value.context["conflicts"][0]["standing_kinds"] == ["MODERATION"]


def test_an_explanation_with_no_discriminating_test_cannot_compete() -> None:
    observations = contradiction_pair()
    conflict = conflict_id_for(observations)

    with pytest.raises(AporiaContractError) as caught:
        sealed(
            observations,
            [
                explanation(
                    "EXP-1", ExplanationKind.MODERATION.value, [conflict], tests=[]
                ),
                explanation("EXP-2", ExplanationKind.CHANCE.value, [conflict]),
            ],
        )

    assert caught.value.code == "EXPLANATION_UNDISCRIMINATING"


def test_a_refuted_explanation_is_retained_with_its_refutation() -> None:
    observations = contradiction_pair()
    conflict = conflict_id_for(observations)

    record = sealed(
        observations,
        [
            explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
            explanation("EXP-2", ExplanationKind.CHANCE.value, [conflict]),
            explanation(
                "EXP-3",
                ExplanationKind.DATA_ERROR.value,
                [conflict],
                status=ExplanationStatus.REFUTED.value,
                refuted_by=["EVN-refute"],
            ),
        ],
    )

    assert [entry["explanation_id"] for entry in record["explanations"]] == [
        "EXP-1",
        "EXP-2",
        "EXP-3",
    ]
    refuted = record["explanations"][2]
    assert refuted["status"] == ExplanationStatus.REFUTED.value
    assert refuted["refuted_by_evidence_ids"] == ["EVN-refute"]
    # A refuted kind is kept but no longer counts toward diversity.
    assert record["explanation_kind_counts"][conflict] == ["CHANCE", "MODERATION"]


def test_refuting_the_field_down_to_one_kind_is_a_monoculture() -> None:
    observations = contradiction_pair()
    conflict = conflict_id_for(observations)

    with pytest.raises(AporiaContractError) as caught:
        sealed(
            observations,
            [
                explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
                explanation(
                    "EXP-2",
                    ExplanationKind.CHANCE.value,
                    [conflict],
                    status=ExplanationStatus.REFUTED.value,
                    refuted_by=["EVN-refute"],
                ),
            ],
        )

    assert caught.value.code == "EXPLANATION_MONOCULTURE"


def test_a_refutation_without_cited_evidence_is_refused() -> None:
    observations = contradiction_pair()
    conflict = conflict_id_for(observations)

    with pytest.raises(AporiaContractError) as caught:
        sealed(
            observations,
            [
                explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
                explanation("EXP-2", ExplanationKind.CHANCE.value, [conflict]),
                explanation(
                    "EXP-3",
                    ExplanationKind.DATA_ERROR.value,
                    [conflict],
                    status=ExplanationStatus.REFUTED.value,
                ),
            ],
        )

    assert caught.value.code == "REFUTATION_UNSUPPORTED"


def test_a_standing_explanation_may_not_cite_refuting_evidence() -> None:
    observations = contradiction_pair()
    conflict = conflict_id_for(observations)

    with pytest.raises(AporiaContractError) as caught:
        sealed(
            observations,
            [
                explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
                explanation(
                    "EXP-2",
                    ExplanationKind.CHANCE.value,
                    [conflict],
                    refuted_by=["EVN-refute"],
                ),
            ],
        )

    assert caught.value.code == "INPUT_INVALID"


def test_an_explanation_must_attach_to_a_classified_conflict() -> None:
    observations = contradiction_pair()
    conflict = conflict_id_for(observations)

    with pytest.raises(AporiaContractError) as caught:
        sealed(
            observations,
            [
                explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
                explanation("EXP-2", ExplanationKind.CHANCE.value, ["CF-ghost"]),
            ],
        )

    assert caught.value.code == "EXPLANATION_UNATTACHED"
    assert caught.value.context["conflict_ids"] == ["CF-ghost"]


def test_an_explanation_covering_nothing_is_refused() -> None:
    observations = contradiction_pair()
    conflict = conflict_id_for(observations)

    with pytest.raises(AporiaContractError) as caught:
        sealed(
            observations,
            [
                explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
                explanation("EXP-2", ExplanationKind.CHANCE.value, []),
            ],
        )

    assert caught.value.code == "EXPLANATION_UNATTACHED"


def test_a_non_canonical_explanation_kind_is_refused() -> None:
    observations = contradiction_pair()
    conflict = conflict_id_for(observations)

    with pytest.raises(AporiaContractError) as caught:
        sealed(
            observations,
            [
                explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
                explanation("EXP-2", "SPOOKY_ACTION", [conflict]),
            ],
        )

    assert caught.value.code == "EXPLANATION_KIND_INVALID"


def test_a_duplicate_explanation_id_is_refused() -> None:
    observations = contradiction_pair()
    conflict = conflict_id_for(observations)

    with pytest.raises(AporiaContractError) as caught:
        sealed(
            observations,
            [
                explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
                explanation("EXP-1", ExplanationKind.CHANCE.value, [conflict]),
            ],
        )

    assert caught.value.code == "DUPLICATE_EXPLANATION"


def test_every_conflict_needs_its_own_competing_field() -> None:
    observations = [
        observation("OBS-a", Direction.POSITIVE.value),
        observation("OBS-b", Direction.NEGATIVE.value),
        observation("OBS-c", Direction.NEGATIVE.value, conditions={"temp_c": 30}),
    ]
    # OBS-b and OBS-c agree, so only the two pairs against OBS-a conflict.
    conflicts = [entry["conflict_id"] for entry in classify_conflicts(observations)]
    assert len(conflicts) == 2

    with pytest.raises(AporiaContractError) as caught:
        sealed(
            observations,
            [
                explanation("EXP-1", ExplanationKind.MODERATION.value, conflicts),
                explanation("EXP-2", ExplanationKind.CHANCE.value, [conflicts[0]]),
            ],
        )

    assert caught.value.code == "EXPLANATION_MONOCULTURE"
    # Only the conflict EXP-2 does not cover is left with one standing kind.
    assert [entry["conflict_id"] for entry in caught.value.context["conflicts"]] == [
        conflicts[1]
    ]


def test_r03_never_selects_a_winner() -> None:
    observations = contradiction_pair()
    conflict = conflict_id_for(observations)

    record = sealed(
        observations,
        [
            explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
            explanation("EXP-2", ExplanationKind.CHANCE.value, [conflict]),
        ],
    )

    assert record["selected_explanation_id"] is None
    assert record["adjudication_owner"] == ADJUDICATION_OWNER == "EVIDENCE_PARLIAMENT"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("selected_explanation_id", "EXP-1"),
        ("adjudication_owner", "R03"),
    ],
)
def test_taking_adjudication_authority_is_refused(field: str, value: str) -> None:
    from .contracts import _hash_excluding

    observations = contradiction_pair()
    conflict = conflict_id_for(observations)
    payload = sealed(
        observations,
        [
            explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
            explanation("EXP-2", ExplanationKind.CHANCE.value, [conflict]),
        ],
    )
    payload[field] = value
    payload["aporia_hash"] = _hash_excluding(payload, "aporia_hash")

    with pytest.raises(AporiaContractError) as caught:
        validate_aporia_record(payload)

    assert caught.value.code == "ADJUDICATION_FORBIDDEN"


def test_dropping_explanations_from_a_rehashed_record_fails_closed() -> None:
    from .contracts import _hash_excluding

    observations = contradiction_pair()
    conflict = conflict_id_for(observations)
    payload = sealed(
        observations,
        [
            explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
            explanation("EXP-2", ExplanationKind.CHANCE.value, [conflict]),
        ],
    )
    payload["explanations"] = payload["explanations"][:1]
    payload["aporia_hash"] = _hash_excluding(payload, "aporia_hash")

    with pytest.raises(AporiaContractError) as caught:
        validate_aporia_record(payload)

    assert caught.value.code == "EXPLANATION_COUNT_MISMATCH"


def test_inflating_the_recorded_kind_counts_fails_closed() -> None:
    from .contracts import _hash_excluding

    observations = contradiction_pair()
    conflict = conflict_id_for(observations)
    payload = sealed(
        observations,
        [
            explanation("EXP-1", ExplanationKind.MODERATION.value, [conflict]),
            explanation("EXP-2", ExplanationKind.CHANCE.value, [conflict]),
        ],
    )
    payload["explanation_kind_counts"][conflict] = ["CHANCE", "MODERATION", "SELECTION"]
    payload["aporia_hash"] = _hash_excluding(payload, "aporia_hash")

    with pytest.raises(AporiaContractError) as caught:
        validate_aporia_record(payload)

    assert caught.value.code == "EXPLANATION_COUNT_MISMATCH"


def test_competing_kinds_counts_only_standing_explanations() -> None:
    explanations = [
        explanation("EXP-1", ExplanationKind.MODERATION.value, ["CF-1"]),
        explanation(
            "EXP-2",
            ExplanationKind.CHANCE.value,
            ["CF-1"],
            status=ExplanationStatus.REFUTED.value,
            refuted_by=["EVN-1"],
        ),
        explanation("EXP-3", ExplanationKind.SELECTION.value, ["CF-2"]),
    ]

    assert competing_kinds("CF-1", explanations) == ["MODERATION"]
    assert competing_kinds("CF-2", explanations) == ["SELECTION"]
    assert competing_kinds("CF-3", explanations) == []


def test_the_kind_vocabulary_is_closed_and_covers_the_usual_suspects() -> None:
    assert set(EXPLANATION_KINDS) == {
        "CHANCE",
        "CONFOUNDING",
        "DATA_ERROR",
        "MEASUREMENT_ARTIFACT",
        "MECHANISM_DIFFERENCE",
        "MODERATION",
        "PUBLICATION_BIAS",
        "SCOPE_BOUNDARY",
        "SELECTION",
    }
