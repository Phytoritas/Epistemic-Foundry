"""R03 deterministic abduction, contradiction and moderator contracts.

The engine takes findings that disagree and does two things it must never
shortcut.

It classifies every conflict.  Two findings that point opposite ways are not
automatically a contradiction: they may have been measured under different
conditions.  Each conflicting pair is typed as a direct contradiction, a
condition difference, a nested scope, or a measurement difference, and a pair
the engine cannot type fails closed rather than being filed as a contradiction
by default.

It keeps competing explanations alive.  Abduction here proposes and preserves;
it never adjudicates.  A conflict explained by only one kind of story is a
monoculture and is refused, an explanation with no discriminating test cannot
compete, and a refuted explanation stays in the record with its refutation
rather than disappearing.  Selection belongs to the Evidence Parliament and to
R04, never here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

from epistemic_foundry.reasoning.induction.contracts import (
    DIRECTION_ORDER,
    Direction,
)

SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
RFC3339_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)


class ConflictType(str, Enum):
    """Why two findings disagree.  ``UNCLASSIFIED`` is never a resting state."""

    DIRECT_CONTRADICTION = "DIRECT_CONTRADICTION"
    CONDITION_DIFFERENCE = "CONDITION_DIFFERENCE"
    SCOPE_NESTED = "SCOPE_NESTED"
    MEASUREMENT_DIFFERENCE = "MEASUREMENT_DIFFERENCE"
    UNCLASSIFIED = "UNCLASSIFIED"


class ExplanationKind(str, Enum):
    """Closed vocabulary of competing explanations for a conflict."""

    CHANCE = "CHANCE"
    CONFOUNDING = "CONFOUNDING"
    DATA_ERROR = "DATA_ERROR"
    MEASUREMENT_ARTIFACT = "MEASUREMENT_ARTIFACT"
    MECHANISM_DIFFERENCE = "MECHANISM_DIFFERENCE"
    MODERATION = "MODERATION"
    PUBLICATION_BIAS = "PUBLICATION_BIAS"
    SCOPE_BOUNDARY = "SCOPE_BOUNDARY"
    SELECTION = "SELECTION"


class ExplanationStatus(str, Enum):
    """Refuted explanations are retained, never removed."""

    STANDING = "STANDING"
    REFUTED = "REFUTED"


class AporiaStatus(str, Enum):
    OPEN = "OPEN"
    NO_CONFLICT = "NO_CONFLICT"


CONFLICT_TYPES: Final = tuple(entry.value for entry in ConflictType)
EXPLANATION_KINDS: Final = tuple(entry.value for entry in ExplanationKind)
EXPLANATION_STATUSES: Final = tuple(entry.value for entry in ExplanationStatus)
#: Directions that make no positional claim and therefore cannot conflict.
NON_ASSERTIVE_DIRECTIONS: Final = (
    Direction.UNKNOWN.value,
    Direction.NOT_APPLICABLE.value,
    Direction.MIXED.value,
)
#: Direction pairs that genuinely point opposite ways.
CONFLICTING_DIRECTION_PAIRS: Final = (
    (Direction.POSITIVE.value, Direction.NEGATIVE.value),
    (Direction.POSITIVE.value, Direction.NULL.value),
    (Direction.NEGATIVE.value, Direction.NULL.value),
    (Direction.POSITIVE.value, Direction.NONMONOTONIC.value),
    (Direction.NEGATIVE.value, Direction.NONMONOTONIC.value),
)
#: Fewer competing explanation kinds than this is a monoculture.
MINIMUM_COMPETING_EXPLANATIONS: Final = 2
#: R03 proposes and preserves; adjudication belongs elsewhere.
ADJUDICATION_OWNER: Final = "EVIDENCE_PARLIAMENT"

OBSERVATION_FIELDS: Final = frozenset(
    {
        "observation_id",
        "evidence_id",
        "direction",
        "conditions",
        "measurement_ref",
        "provenance_ref",
    }
)
EXPLANATION_FIELDS: Final = frozenset(
    {
        "explanation_id",
        "statement",
        "explanation_kind",
        "covers",
        "discriminating_tests",
        "status",
        "refuted_by_evidence_ids",
    }
)
APORIA_FIELDS: Final = frozenset(
    {
        "aporia_id",
        "subject_id",
        "created_at",
        "status",
        "adjudication_owner",
        "selected_explanation_id",
        "observation_ids",
        "conflicts",
        "explanations",
        "explanation_kind_counts",
        "unexplained_conflict_ids",
        "aporia_hash",
    }
)
_CONFLICT_FIELDS: Final = frozenset(
    {
        "conflict_id",
        "conflict_type",
        "left_observation_id",
        "right_observation_id",
        "left_direction",
        "right_direction",
        "differing_conditions",
        "rationale",
    }
)


class AporiaContractError(ValueError):
    """Typed fail-closed R03 contract error."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context) if context is not None else {}


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    raise AporiaContractError(code, message, context)


@dataclass(frozen=True)
class SealedArtifact:
    """Immutable canonical JSON snapshot with a fresh projection on access."""

    artifact_type: str
    _canonical_bytes: bytes

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self._canonical_bytes.decode("utf-8"))
        if type(value) is not dict:  # pragma: no cover - construction invariant
            raise AssertionError("sealed artifact is not an object")
        return value


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        _fail("CANONICALIZATION_FAILED", f"value is not canonical JSON: {error}")
        raise  # pragma: no cover - _fail always raises


def _hex_digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _digest(value: object) -> str:
    return "sha256:" + _hex_digest(value)


def _hash_excluding(payload: Mapping[str, Any], field: str) -> str:
    return _digest({key: value for key, value in payload.items() if key != field})


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping")
    result: dict[str, Any] = {}
    for key, entry in value.items():  # type: ignore[union-attr]
        if not isinstance(key, str):
            _fail("INPUT_INVALID", f"{label} keys must be strings")
        result[key] = entry
    return result


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail("INPUT_INVALID", f"{label} must be an array")
    return list(value)  # type: ignore[arg-type]


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        _fail(
            "FIELD_SET_INVALID",
            f"{label} field set is invalid",
            {"missing": missing, "unknown": unknown},
        )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string")
    return str(value)


def _month_length(year: int, month: int) -> int:
    leap_year = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return (
        31,
        29 if leap_year else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    )[month - 1]


def _shift_calendar_day(
    year: int, month: int, day: int, day_delta: int
) -> tuple[int, int, int]:
    while day_delta > 0:
        day += 1
        if day > _month_length(year, month):
            day = 1
            month += 1
            if month > 12:
                month = 1
                year += 1
        day_delta -= 1
    while day_delta < 0:
        day -= 1
        if day < 1:
            month -= 1
            if month < 1:
                month = 12
                year -= 1
            day = _month_length(year, month)
        day_delta += 1
    return year, month, day


def _timestamp(value: object, label: str) -> str:
    text = _text(value, label)
    if RFC3339_PATTERN.fullmatch(text) is None:
        _fail("INPUT_INVALID", f"{label} must be an RFC3339 timestamp")
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    hour = int(text[11:13])
    minute = int(text[14:16])
    second = int(text[17:19])
    if (
        month < 1
        or month > 12
        or day < 1
        or day > _month_length(year, month)
        or hour > 23
        or minute > 59
        or second > 60
    ):
        _fail("INPUT_INVALID", f"{label} must be a real RFC3339 timestamp")
    offset_minutes = 0
    if not text.endswith("Z"):
        offset_hour = int(text[-5:-3])
        offset_minute = int(text[-2:])
        if offset_hour > 23 or offset_minute > 59:
            _fail("INPUT_INVALID", f"{label} must be a real RFC3339 timestamp")
        offset_minutes = offset_hour * 60 + offset_minute
        if text[-6] == "-":
            offset_minutes = -offset_minutes
    if second == 60:
        utc_day_delta, utc_minute = divmod(
            hour * 60 + minute - offset_minutes,
            1440,
        )
        utc_year, utc_month, utc_day = _shift_calendar_day(
            year,
            month,
            day,
            utc_day_delta,
        )
        if utc_minute != 1439 or utc_day != _month_length(utc_year, utc_month):
            _fail(
                "INPUT_INVALID",
                f"{label} leap second must be at a UTC month end",
            )
    return text


def _validate_observation(value: object, index: int) -> dict[str, Any]:
    observation = _mapping(value, f"observations[{index}]")
    _exact_fields(observation, OBSERVATION_FIELDS, f"observations[{index}]")
    observation_id = _text(observation["observation_id"], "observation_id")
    direction = _text(observation["direction"], "direction")
    if direction not in DIRECTION_ORDER:
        _fail(
            "DIRECTION_INVALID",
            "direction must be a canonical claim direction",
            {"observation_id": observation_id, "value": direction},
        )
    conditions = _mapping(observation["conditions"], "conditions")
    normalized: dict[str, Any] = {}
    for key in sorted(conditions):
        normalized[_text(key, "condition name")] = conditions[key]
    measurement_ref = observation["measurement_ref"]
    if measurement_ref is not None:
        measurement_ref = _text(measurement_ref, "measurement_ref")
    return {
        "conditions": normalized,
        "direction": direction,
        "evidence_id": _text(observation["evidence_id"], "evidence_id"),
        "measurement_ref": measurement_ref,
        "observation_id": observation_id,
        "provenance_ref": _text(observation["provenance_ref"], "provenance_ref"),
    }


def directions_conflict(left: str, right: str) -> bool:
    """True only when two directions genuinely point opposite ways.

    ``unknown``, ``not_applicable``, and ``mixed`` assert no position, so they
    can never manufacture a contradiction.
    """

    if left in NON_ASSERTIVE_DIRECTIONS or right in NON_ASSERTIVE_DIRECTIONS:
        return False
    pair = (left, right)
    return (
        pair in CONFLICTING_DIRECTION_PAIRS or pair[::-1] in CONFLICTING_DIRECTION_PAIRS
    )


def _condition_difference(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> tuple[list[str], str | None]:
    """Differing condition keys, and which side is nested inside the other."""

    differing = sorted(
        key for key in set(left) | set(right) if left.get(key) != right.get(key)
    )
    nesting: str | None = None
    if set(left) < set(right) and all(
        right[key] == value for key, value in left.items()
    ):
        nesting = "right_within_left"
    elif set(right) < set(left) and all(
        left[key] == value for key, value in right.items()
    ):
        nesting = "left_within_right"
    return differing, nesting


def _conflict_id(left_observation_id: str, right_observation_id: str) -> str:
    left, right = sorted((left_observation_id, right_observation_id))
    return "CF-" + _hex_digest({"left": left, "right": right})


def classify_conflict(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Type one pair of observations, or return ``None`` when they agree.

    A pair whose type cannot be established is returned as ``UNCLASSIFIED``,
    which the sealing path refuses: an unexplained disagreement must never be
    filed as a contradiction by default.
    """

    if not directions_conflict(str(left["direction"]), str(right["direction"])):
        return None
    differing, nesting = _condition_difference(left["conditions"], right["conditions"])
    measurements = {left["measurement_ref"], right["measurement_ref"]}
    ordered = sorted((left, right), key=lambda entry: str(entry["observation_id"]))
    record: dict[str, Any] = {
        "conflict_id": _conflict_id(
            str(ordered[0]["observation_id"]),
            str(ordered[1]["observation_id"]),
        ),
        "differing_conditions": differing,
        "left_direction": str(ordered[0]["direction"]),
        "left_observation_id": str(ordered[0]["observation_id"]),
        "right_direction": str(ordered[1]["direction"]),
        "right_observation_id": str(ordered[1]["observation_id"]),
    }
    if not differing:
        if None in measurements and len(measurements) > 1:
            record["conflict_type"] = ConflictType.UNCLASSIFIED.value
            record["rationale"] = (
                "conditions match but only one side declares a measurement, so the "
                "disagreement cannot be attributed"
            )
        elif len(measurements) > 1:
            record["conflict_type"] = ConflictType.MEASUREMENT_DIFFERENCE.value
            record["rationale"] = (
                "identical conditions measured differently; the disagreement may be "
                "an artefact of the instrument rather than of the world"
            )
        else:
            record["conflict_type"] = ConflictType.DIRECT_CONTRADICTION.value
            record["rationale"] = (
                "the same conditions and the same measurement yield opposite directions"
            )
    elif nesting is not None:
        record["conflict_type"] = ConflictType.SCOPE_NESTED.value
        record["rationale"] = (
            "one observation's conditions are a strict refinement of the other's, so "
            f"the narrower may be a boundary case ({nesting})"
        )
    else:
        record["conflict_type"] = ConflictType.CONDITION_DIFFERENCE.value
        record["rationale"] = (
            "the observations differ on at least one condition, so the disagreement "
            "is not yet a contradiction"
        )
    return record


def classify_conflicts(
    observations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Every conflicting pair, typed, in deterministic order."""

    ordered = sorted(observations, key=lambda entry: str(entry["observation_id"]))
    conflicts: list[dict[str, Any]] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            record = classify_conflict(left, right)
            if record is not None:
                conflicts.append(record)
    return sorted(conflicts, key=lambda entry: str(entry["conflict_id"]))


def _validate_explanation(
    value: object, index: int, conflict_ids: frozenset[str]
) -> dict[str, Any]:
    explanation = _mapping(value, f"explanations[{index}]")
    _exact_fields(explanation, EXPLANATION_FIELDS, f"explanations[{index}]")
    explanation_id = _text(explanation["explanation_id"], "explanation_id")
    kind = _text(explanation["explanation_kind"], "explanation_kind")
    if kind not in EXPLANATION_KINDS:
        _fail(
            "EXPLANATION_KIND_INVALID",
            "explanation_kind must be a canonical kind",
            {"explanation_id": explanation_id, "value": kind},
        )
    status = _text(explanation["status"], "status")
    if status not in EXPLANATION_STATUSES:
        _fail(
            "INPUT_INVALID",
            "explanation status is not canonical",
            {"explanation_id": explanation_id},
        )
    covers = sorted(
        {
            _text(entry, "covered conflict id")
            for entry in _sequence(explanation["covers"], "covers")
        }
    )
    if not covers:
        _fail(
            "EXPLANATION_UNATTACHED",
            "an explanation must name the conflicts it explains",
            {"explanation_id": explanation_id},
        )
    unknown = sorted(set(covers) - conflict_ids)
    if unknown:
        _fail(
            "EXPLANATION_UNATTACHED",
            "an explanation may only cover classified conflicts",
            {"conflict_ids": unknown, "explanation_id": explanation_id},
        )
    tests = sorted(
        {
            _text(entry, "discriminating test")
            for entry in _sequence(
                explanation["discriminating_tests"], "discriminating_tests"
            )
        }
    )
    if not tests:
        _fail(
            "EXPLANATION_UNDISCRIMINATING",
            "an explanation with no discriminating test cannot compete",
            {"explanation_id": explanation_id},
        )
    refuted_by = sorted(
        {
            _text(entry, "refuting evidence id")
            for entry in _sequence(
                explanation["refuted_by_evidence_ids"], "refuted_by_evidence_ids"
            )
        }
    )
    if status == ExplanationStatus.REFUTED.value and not refuted_by:
        _fail(
            "REFUTATION_UNSUPPORTED",
            "an explanation may only be refuted with cited evidence",
            {"explanation_id": explanation_id},
        )
    if status == ExplanationStatus.STANDING.value and refuted_by:
        _fail(
            "INPUT_INVALID",
            "a standing explanation must not cite refuting evidence",
            {"explanation_id": explanation_id},
        )
    return {
        "covers": covers,
        "discriminating_tests": tests,
        "explanation_id": explanation_id,
        "explanation_kind": kind,
        "refuted_by_evidence_ids": refuted_by,
        "statement": _text(explanation["statement"], "statement"),
        "status": status,
    }


def competing_kinds(
    conflict_id: str, explanations: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Distinct standing explanation kinds offered for one conflict.

    Diversity is counted over kinds rather than over rows, because two
    restatements of the same story are not competing accounts.
    """

    return sorted(
        {
            str(explanation["explanation_kind"])
            for explanation in explanations
            if conflict_id in explanation["covers"]
            and explanation["status"] == ExplanationStatus.STANDING.value
        }
    )


def _aporia_id(payload: Mapping[str, Any]) -> str:
    return "AP-" + _hex_digest(
        {
            "conflicts": payload["conflicts"],
            "created_at": payload["created_at"],
            "explanations": payload["explanations"],
            "observation_ids": payload["observation_ids"],
            "subject_id": payload["subject_id"],
        }
    )


def build_aporia_record(
    observations: Sequence[Mapping[str, Any]],
    explanations: Sequence[Mapping[str, Any]],
    *,
    subject_id: str,
    created_at: str,
) -> SealedArtifact:
    """Classify every conflict and seal the surviving competing explanations."""

    subject_id = _text(subject_id, "subject_id")
    created_at = _timestamp(created_at, "created_at")
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(observations):
        observation = _validate_observation(entry, index)
        if observation["observation_id"] in seen:
            _fail(
                "DUPLICATE_OBSERVATION",
                "observation ids must be unique",
                {"observation_id": observation["observation_id"]},
            )
        seen.add(observation["observation_id"])
        validated.append(observation)

    conflicts = classify_conflicts(validated)
    unclassified = sorted(
        entry["conflict_id"]
        for entry in conflicts
        if entry["conflict_type"] == ConflictType.UNCLASSIFIED.value
    )
    if unclassified:
        _fail(
            "CONFLICT_UNCLASSIFIED",
            "every conflict must be typed before the record can be sealed",
            {"conflict_ids": unclassified},
        )
    conflict_ids = frozenset(entry["conflict_id"] for entry in conflicts)

    validated_explanations: list[dict[str, Any]] = []
    explanation_ids: set[str] = set()
    for index, entry in enumerate(explanations):
        explanation = _validate_explanation(entry, index, conflict_ids)
        if explanation["explanation_id"] in explanation_ids:
            _fail(
                "DUPLICATE_EXPLANATION",
                "explanation ids must be unique",
                {"explanation_id": explanation["explanation_id"]},
            )
        explanation_ids.add(explanation["explanation_id"])
        validated_explanations.append(explanation)
    validated_explanations.sort(key=lambda entry: entry["explanation_id"])

    kind_counts: dict[str, list[str]] = {}
    monoculture: list[dict[str, Any]] = []
    for conflict in conflicts:
        kinds = competing_kinds(conflict["conflict_id"], validated_explanations)
        kind_counts[conflict["conflict_id"]] = kinds
        if len(kinds) < MINIMUM_COMPETING_EXPLANATIONS:
            monoculture.append(
                {"conflict_id": conflict["conflict_id"], "standing_kinds": kinds}
            )
    if monoculture:
        _fail(
            "EXPLANATION_MONOCULTURE",
            "each conflict needs at least two competing kinds of explanation",
            {"conflicts": monoculture, "required": MINIMUM_COMPETING_EXPLANATIONS},
        )

    payload: dict[str, Any] = {
        "adjudication_owner": ADJUDICATION_OWNER,
        "conflicts": conflicts,
        "created_at": created_at,
        "explanation_kind_counts": kind_counts,
        "explanations": validated_explanations,
        "observation_ids": sorted(seen),
        "selected_explanation_id": None,
        "status": (
            AporiaStatus.OPEN.value if conflicts else AporiaStatus.NO_CONFLICT.value
        ),
        "subject_id": subject_id,
        "unexplained_conflict_ids": [],
    }
    payload["aporia_id"] = _aporia_id(payload)
    payload["aporia_hash"] = _hash_excluding(payload, "aporia_hash")
    return validate_aporia_record(payload)


def validate_aporia_record(payload: Mapping[str, Any]) -> SealedArtifact:
    """Validate one aporia record shape, vocabulary, and self-hash."""

    value = _mapping(payload, "AporiaRecord")
    _exact_fields(value, APORIA_FIELDS, "AporiaRecord")
    _text(value["aporia_id"], "aporia_id")
    _text(value["subject_id"], "subject_id")
    _timestamp(value["created_at"], "created_at")
    if value["status"] not in tuple(entry.value for entry in AporiaStatus):
        _fail("INPUT_INVALID", "status must be a canonical aporia status")
    if value["adjudication_owner"] != ADJUDICATION_OWNER:
        _fail(
            "ADJUDICATION_FORBIDDEN",
            "R03 may not take adjudication authority",
            {"adjudication_owner": value["adjudication_owner"]},
        )
    if value["selected_explanation_id"] is not None:
        _fail(
            "ADJUDICATION_FORBIDDEN",
            "R03 proposes and preserves explanations but never selects one",
            {"selected_explanation_id": value["selected_explanation_id"]},
        )
    observation_values = _sequence(value["observation_ids"], "observation_ids")
    observation_ids = [
        _text(entry, "observation_id") for entry in observation_values
    ]
    if observation_ids != sorted(observation_ids) or len(observation_ids) != len(
        set(observation_ids)
    ):
        _fail("INPUT_INVALID", "observation_ids must be unique and sorted ascending")
    observation_set = set(observation_ids)

    conflicts = _sequence(value["conflicts"], "conflicts")
    conflict_ids: list[str] = []
    for index, entry in enumerate(conflicts):
        conflict = _mapping(entry, f"conflicts[{index}]")
        _exact_fields(conflict, _CONFLICT_FIELDS, f"conflicts[{index}]")
        if conflict["conflict_type"] not in CONFLICT_TYPES:
            _fail("INPUT_INVALID", "conflict_type is not canonical")
        if conflict["conflict_type"] == ConflictType.UNCLASSIFIED.value:
            _fail(
                "CONFLICT_UNCLASSIFIED",
                "a sealed record may not carry an unclassified conflict",
                {"conflict_id": conflict["conflict_id"]},
            )
        conflict_id = _text(conflict["conflict_id"], "conflict_id")
        left_id = _text(conflict["left_observation_id"], "left_observation_id")
        right_id = _text(conflict["right_observation_id"], "right_observation_id")
        if left_id == right_id:
            _fail(
                "INPUT_INVALID",
                "a conflict must reference two distinct observations",
                {"conflict_id": conflict_id},
            )
        if (left_id, right_id) != tuple(sorted((left_id, right_id))):
            _fail(
                "INPUT_INVALID",
                "conflict observation endpoints must be sorted ascending",
                {"conflict_id": conflict_id},
            )
        unknown_observations = sorted({left_id, right_id} - observation_set)
        if unknown_observations:
            _fail(
                "OBSERVATION_UNRESOLVED",
                "conflict endpoints must resolve to recorded observations",
                {"conflict_id": conflict_id, "observation_ids": unknown_observations},
            )
        expected_conflict_id = _conflict_id(left_id, right_id)
        if conflict_id != expected_conflict_id:
            _fail(
                "CONFLICT_ID_MISMATCH",
                "conflict_id is not the content address of its observation pair",
                {"actual": conflict_id, "expected": expected_conflict_id},
            )
        left_direction = _text(conflict["left_direction"], "left_direction")
        right_direction = _text(conflict["right_direction"], "right_direction")
        if (
            left_direction not in DIRECTION_ORDER
            or right_direction not in DIRECTION_ORDER
        ):
            _fail("DIRECTION_INVALID", "conflict directions must be canonical")
        if not directions_conflict(left_direction, right_direction):
            _fail(
                "DIRECTION_INVALID",
                "a recorded conflict must carry genuinely conflicting directions",
                {"conflict_id": conflict_id},
            )
        differing_values = _sequence(
            conflict["differing_conditions"], "differing_conditions"
        )
        differing_conditions = [
            _text(item, "differing condition") for item in differing_values
        ]
        if differing_conditions != sorted(set(differing_conditions)):
            _fail(
                "INPUT_INVALID",
                "differing_conditions must be unique and sorted ascending",
                {"conflict_id": conflict_id},
            )
        if conflict["conflict_type"] in (
            ConflictType.DIRECT_CONTRADICTION.value,
            ConflictType.MEASUREMENT_DIFFERENCE.value,
        ) and differing_conditions:
            _fail(
                "INPUT_INVALID",
                "same-condition conflict types cannot list differing conditions",
                {"conflict_id": conflict_id},
            )
        if conflict["conflict_type"] in (
            ConflictType.CONDITION_DIFFERENCE.value,
            ConflictType.SCOPE_NESTED.value,
        ) and not differing_conditions:
            _fail(
                "INPUT_INVALID",
                "condition-bound conflict types must name a differing condition",
                {"conflict_id": conflict_id},
            )
        _text(conflict["rationale"], "rationale")
        conflict_ids.append(conflict_id)
    if conflict_ids != sorted(conflict_ids) or len(conflict_ids) != len(
        set(conflict_ids)
    ):
        _fail("INPUT_INVALID", "conflicts must be unique and sorted ascending")
    expected_status = (
        AporiaStatus.OPEN.value if conflict_ids else AporiaStatus.NO_CONFLICT.value
    )
    if value["status"] != expected_status:
        _fail(
            "STATUS_MISMATCH",
            "aporia status must reflect whether classified conflicts remain",
            {"actual": value["status"], "expected": expected_status},
        )

    explanation_values = _sequence(value["explanations"], "explanations")
    explanations: list[dict[str, Any]] = []
    for index, entry in enumerate(explanation_values):
        original = _mapping(entry, f"explanations[{index}]")
        normalized = _validate_explanation(original, index, frozenset(conflict_ids))
        if original != normalized:
            _fail(
                "INPUT_INVALID",
                "explanations must use their canonical sorted projection",
                {"explanation_id": normalized["explanation_id"]},
            )
        explanations.append(normalized)
    explanation_ids = [entry["explanation_id"] for entry in explanations]
    if explanation_ids != sorted(explanation_ids) or len(explanation_ids) != len(
        set(explanation_ids)
    ):
        _fail("INPUT_INVALID", "explanations must be unique and sorted ascending")
    counts = _mapping(value["explanation_kind_counts"], "explanation_kind_counts")
    if sorted(counts) != sorted(conflict_ids):
        _fail(
            "INPUT_INVALID",
            "explanation_kind_counts must cover every conflict exactly once",
        )
    for conflict_id in conflict_ids:
        kinds = _sequence(counts[conflict_id], "explanation kinds")
        recomputed = competing_kinds(conflict_id, explanations)
        if list(kinds) != recomputed:
            _fail(
                "EXPLANATION_COUNT_MISMATCH",
                "the recorded competing kinds differ from the explanations",
                {"conflict_id": conflict_id},
            )
        if len(recomputed) < MINIMUM_COMPETING_EXPLANATIONS:
            _fail(
                "EXPLANATION_MONOCULTURE",
                "a sealed conflict must keep at least two competing kinds",
                {"conflict_id": conflict_id, "standing_kinds": recomputed},
            )
    if _sequence(value["unexplained_conflict_ids"], "unexplained_conflict_ids"):
        _fail(
            "CONFLICT_UNEXPLAINED",
            "a sealed record may not carry an unexplained conflict",
        )
    expected_aporia_id = _aporia_id(value)
    if value["aporia_id"] != expected_aporia_id:
        _fail(
            "APORIA_ID_MISMATCH",
            "aporia_id is not the content address of the recorded aporia",
            {"actual": value["aporia_id"], "expected": expected_aporia_id},
        )
    if _hash_excluding(value, "aporia_hash") != value["aporia_hash"]:
        _fail("APORIA_HASH_MISMATCH", "aporia_hash does not match its content")
    return SealedArtifact("AporiaRecord", _canonical_json(value))
