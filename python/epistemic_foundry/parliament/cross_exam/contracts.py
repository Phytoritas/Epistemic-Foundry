"""P03 cross-examination grounding and Minority Report preservation.

Two failure modes are what this component exists to prevent.

An attack that cites nothing.  A challenge phrased as disagreement, naming no
assertion and no evidence, cannot be answered or resolved; it only adds
apparent scrutiny.  So every cross-examination must name a target brief, an
assertion inside that brief, and at least one evidence id the attacker's own
context actually contained.  Citing evidence withheld from the attacker is
refused with the same force as inventing it.

A dissent that quietly disappears.  The value of a minority report is highest
exactly when the majority is comfortable, so the report with the greatest
expected information gain is required rather than optional: it may be marked
superseded only by cited new evidence, and never simply dropped.  Every report
supplied is retained with its status; nothing is pruned for being inconvenient.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
RFC3339_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
#: The canonical schemas are the declaring source of both vocabularies.
CROSS_EXAM_SCHEMA_PATH: Final = "schemas/cross-examination.schema.json"
MINORITY_SCHEMA_PATH: Final = "schemas/minority-report.schema.json"


class ResolutionStatus(str, Enum):
    """How a challenge ended.  ``UNANSWERED`` is an open obligation."""

    UNANSWERED = "unanswered"
    ANSWERED = "answered"
    SUSTAINED = "sustained"
    OVERRULED = "overruled"
    PARTIALLY_SUSTAINED = "partially_sustained"


class Preservation(str, Enum):
    """What must happen to a minority report."""

    REQUIRED = "required"
    PRESERVED = "preserved"
    SUPERSEDED = "superseded_by_new_evidence"


#: Statuses that mean the attacker received an actual reply.
ANSWERED_STATUSES: Final = (
    ResolutionStatus.ANSWERED.value,
    ResolutionStatus.SUSTAINED.value,
    ResolutionStatus.OVERRULED.value,
    ResolutionStatus.PARTIALLY_SUSTAINED.value,
)
#: The one status that leaves the challenge open.
OPEN_STATUS: Final = ResolutionStatus.UNANSWERED.value
#: Statuses under which the dissent survives into the record.
SURVIVING_PRESERVATION: Final = (
    Preservation.REQUIRED.value,
    Preservation.PRESERVED.value,
)

CROSS_EXAM_FIELDS: Final = frozenset(
    {
        "cross_exam_id",
        "run_id",
        "attacker_role",
        "target_brief_id",
        "target_assertion_id",
        "attack_type",
        "challenge",
        "evidence_ids",
        "resolution_condition",
        "response",
        "resolution_status",
        "created_at",
        "record_hash",
    }
)
MINORITY_FIELDS: Final = frozenset(
    {
        "minority_report_id",
        "run_id",
        "author_role",
        "minority_claim",
        "evidence_ids",
        "why_majority_may_be_wrong",
        "unresolved_test",
        "expected_information_gain",
        "preservation_status",
        "created_at",
        "report_hash",
    }
)
ROUND_FIELDS: Final = frozenset(
    {
        "cross_exam_round_id",
        "run_id",
        "round",
        "created_at",
        "cross_examinations",
        "minority_reports",
        "grounding",
        "dissent",
        "round_hash",
    }
)


class CrossExamError(ValueError):
    """Typed fail-closed P03 contract error."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context) if context is not None else {}


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    raise CrossExamError(code, message, context)


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


def _timestamp(value: object, label: str) -> str:
    text = _text(value, label)
    if RFC3339_PATTERN.fullmatch(text) is None:
        _fail("INPUT_INVALID", f"{label} must be an RFC3339 timestamp")
    return text


@lru_cache(maxsize=8)
def _schema_enum(repository_root: str, relative: str, field: str) -> tuple[str, ...]:
    schema = json.loads((Path(repository_root) / relative).read_text(encoding="utf-8"))
    declared = schema.get("properties", {}).get(field, {}).get("enum")
    if not isinstance(declared, list) or not declared:
        _fail(
            "VOCABULARY_UNREADABLE",
            f"{relative} declares no {field} enum",
        )
    return tuple(str(entry) for entry in declared)  # type: ignore[union-attr]


def attack_types(repository_root: Path) -> tuple[str, ...]:
    """Canonical attack vocabulary, read from the cross-examination schema."""

    return _schema_enum(str(repository_root), CROSS_EXAM_SCHEMA_PATH, "attack_type")


def resolution_statuses(repository_root: Path) -> tuple[str, ...]:
    """Canonical resolution vocabulary, read from the declaring schema."""

    return _schema_enum(
        str(repository_root), CROSS_EXAM_SCHEMA_PATH, "resolution_status"
    )


def preservation_statuses(repository_root: Path) -> tuple[str, ...]:
    """Canonical preservation vocabulary, read from the declaring schema."""

    return _schema_enum(
        str(repository_root), MINORITY_SCHEMA_PATH, "preservation_status"
    )


def _brief_index(briefs: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for entry in briefs:
        brief = _mapping(entry, "brief")
        brief_id = _text(brief["brief_id"], "brief_id")
        assertions = {
            _text(_mapping(item, "assertion")["assertion_id"], "assertion_id")
            for item in _sequence(brief["assertions"], "assertions")
        }
        index[brief_id] = {
            "assertion_ids": assertions,
            "brief_id": brief_id,
            "role": _text(brief["role"], "role"),
        }
    return index


def validate_cross_examination(
    repository_root: Path,
    value: object,
    briefs: Mapping[str, Mapping[str, Any]],
    contexts: Mapping[str, Mapping[str, Any]],
    index: int = 0,
) -> dict[str, Any]:
    """Validate one challenge and prove it is grounded in real ids."""

    record = _mapping(value, f"cross_examinations[{index}]")
    _exact_fields(record, CROSS_EXAM_FIELDS, f"cross_examinations[{index}]")
    exam_id = _text(record["cross_exam_id"], "cross_exam_id")
    attacker = _text(record["attacker_role"], "attacker_role")
    attack_type = _text(record["attack_type"], "attack_type")
    if attack_type not in attack_types(repository_root):
        _fail(
            "ATTACK_TYPE_INVALID",
            "an attack must use a canonical attack type",
            {"cross_exam_id": exam_id, "value": attack_type},
        )
    status = _text(record["resolution_status"], "resolution_status")
    if status not in resolution_statuses(repository_root):
        _fail(
            "RESOLUTION_STATUS_INVALID",
            "a challenge must carry a canonical resolution status",
            {"cross_exam_id": exam_id, "value": status},
        )
    target_brief = _text(record["target_brief_id"], "target_brief_id")
    target_assertion = _text(record["target_assertion_id"], "target_assertion_id")
    brief = briefs.get(target_brief)
    if brief is None:
        _fail(
            "ATTACK_TARGET_UNRESOLVED",
            "an attack must name a brief this round carries",
            {"cross_exam_id": exam_id, "target_brief_id": target_brief},
        )
    if target_assertion not in brief["assertion_ids"]:
        _fail(
            "ATTACK_ASSERTION_UNRESOLVED",
            "an attack must name an assertion inside the brief it targets",
            {
                "cross_exam_id": exam_id,
                "target_assertion_id": target_assertion,
                "target_brief_id": target_brief,
            },
        )
    if brief["role"] == attacker:
        _fail(
            "SELF_ATTACK_FORBIDDEN",
            "a role may not cross-examine its own brief",
            {"cross_exam_id": exam_id, "role": attacker},
        )
    evidence = sorted(
        {
            _text(entry, "evidence_id")
            for entry in _sequence(record["evidence_ids"], "evidence_ids")
        }
    )
    if not evidence:
        _fail(
            "ATTACK_UNGROUNDED",
            "an attack must cite at least one evidence id",
            {"cross_exam_id": exam_id},
        )
    context = contexts.get(attacker)
    if context is None:
        _fail(
            "ATTACKER_CONTEXT_MISSING",
            "an attacker must have been given a context this round",
            {"cross_exam_id": exam_id, "role": attacker},
        )
    permitted = set(context["included_evidence_ids"])
    ungrounded = sorted(set(evidence) - permitted)
    if ungrounded:
        withheld = sorted(set(ungrounded) & set(context["withheld_evidence_ids"]))
        _fail(
            "ATTACK_EVIDENCE_UNGROUNDED",
            "an attack may only cite evidence its own context contained",
            {
                "cited_withheld": withheld,
                "cross_exam_id": exam_id,
                "evidence_ids": ungrounded,
                "role": attacker,
            },
        )
    response = record["response"]
    if status == OPEN_STATUS:
        if response is not None:
            _fail(
                "RESPONSE_UNEXPECTED",
                "an unanswered challenge must not carry a response",
                {"cross_exam_id": exam_id},
            )
    else:
        response = _text(response, "response")
    return {
        "attack_type": attack_type,
        "attacker_role": attacker,
        "challenge": _text(record["challenge"], "challenge"),
        "created_at": _timestamp(record["created_at"], "created_at"),
        "cross_exam_id": exam_id,
        "evidence_ids": evidence,
        "record_hash": _text(record["record_hash"], "record_hash"),
        "resolution_condition": _text(
            record["resolution_condition"], "resolution_condition"
        ),
        "resolution_status": status,
        "response": response,
        "run_id": _text(record["run_id"], "run_id"),
        "target_assertion_id": target_assertion,
        "target_brief_id": target_brief,
    }


def validate_minority_report(
    repository_root: Path, value: object, index: int = 0
) -> dict[str, Any]:
    """Validate one minority report, including how it may be set aside."""

    record = _mapping(value, f"minority_reports[{index}]")
    _exact_fields(record, MINORITY_FIELDS, f"minority_reports[{index}]")
    report_id = _text(record["minority_report_id"], "minority_report_id")
    preservation = _text(record["preservation_status"], "preservation_status")
    if preservation not in preservation_statuses(repository_root):
        _fail(
            "PRESERVATION_STATUS_INVALID",
            "a minority report must carry a canonical preservation status",
            {"minority_report_id": report_id, "value": preservation},
        )
    gain = record["expected_information_gain"]
    if type(gain) not in (int, float) or isinstance(gain, bool) or float(gain) < 0.0:
        _fail(
            "INFORMATION_GAIN_INVALID",
            "expected_information_gain must be a number >= 0",
            {"minority_report_id": report_id},
        )
    evidence = sorted(
        {
            _text(entry, "evidence_id")
            for entry in _sequence(record["evidence_ids"], "evidence_ids")
        }
    )
    if preservation == Preservation.SUPERSEDED.value and not evidence:
        _fail(
            "SUPERSESSION_UNSUPPORTED",
            "a dissent may only be superseded by cited new evidence",
            {"minority_report_id": report_id},
        )
    return {
        "author_role": _text(record["author_role"], "author_role"),
        "created_at": _timestamp(record["created_at"], "created_at"),
        "evidence_ids": evidence,
        "expected_information_gain": float(gain),  # type: ignore[arg-type]
        "minority_claim": _text(record["minority_claim"], "minority_claim"),
        "minority_report_id": report_id,
        "preservation_status": preservation,
        "report_hash": _text(record["report_hash"], "report_hash"),
        "run_id": _text(record["run_id"], "run_id"),
        "unresolved_test": _text(record["unresolved_test"], "unresolved_test"),
        "why_majority_may_be_wrong": _text(
            record["why_majority_may_be_wrong"], "why_majority_may_be_wrong"
        ),
    }


def strongest_dissent(reports: Sequence[Mapping[str, Any]]) -> str | None:
    """The report with the greatest expected information gain, ties by id.

    Returned rather than assumed so both the seal and a caller agree on which
    dissent may not be dropped.
    """

    if not reports:
        return None
    ranked = sorted(
        reports,
        key=lambda entry: (
            -float(entry["expected_information_gain"]),
            str(entry["minority_report_id"]),
        ),
    )
    return str(ranked[0]["minority_report_id"])


def seal_cross_exam_round(
    repository_root: Path,
    briefs: Sequence[Mapping[str, Any]],
    contexts: Sequence[Mapping[str, Any]],
    cross_examinations: Sequence[Mapping[str, Any]],
    minority_reports: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    round_number: int,
    created_at: str,
) -> SealedArtifact:
    """Check grounding and dissent preservation, then seal the round."""

    run_id = _text(run_id, "run_id")
    created_at = _timestamp(created_at, "created_at")
    if type(round_number) is not int or round_number < 2:
        _fail(
            "ROUND_INVALID",
            "cross-examination begins after the blind first round",
            {"round": round_number},
        )

    brief_index = _brief_index(briefs)
    context_index = {
        _text(_mapping(entry, "context")["role"], "role"): _mapping(entry, "context")
        for entry in contexts
    }

    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(cross_examinations):
        record = validate_cross_examination(
            repository_root, entry, brief_index, context_index, index
        )
        if record["cross_exam_id"] in seen:
            _fail(
                "DUPLICATE_CROSS_EXAM",
                "cross-examination ids must be unique within one round",
                {"cross_exam_id": record["cross_exam_id"]},
            )
        seen.add(record["cross_exam_id"])
        if record["run_id"] != run_id:
            _fail(
                "ROUND_INCOHERENT",
                "every challenge must belong to this run",
                {"cross_exam_id": record["cross_exam_id"]},
            )
        validated.append(record)
    validated.sort(key=lambda record: record["cross_exam_id"])

    reports: list[dict[str, Any]] = []
    report_ids: set[str] = set()
    for index, entry in enumerate(minority_reports):
        report = validate_minority_report(repository_root, entry, index)
        if report["minority_report_id"] in report_ids:
            _fail(
                "DUPLICATE_MINORITY_REPORT",
                "minority report ids must be unique within one round",
                {"minority_report_id": report["minority_report_id"]},
            )
        report_ids.add(report["minority_report_id"])
        if report["run_id"] != run_id:
            _fail(
                "ROUND_INCOHERENT",
                "every minority report must belong to this run",
                {"minority_report_id": report["minority_report_id"]},
            )
        reports.append(report)
    reports.sort(key=lambda report: report["minority_report_id"])

    strongest = strongest_dissent(reports)
    if strongest is not None:
        record = next(
            report for report in reports if report["minority_report_id"] == strongest
        )
        if record["preservation_status"] not in SURVIVING_PRESERVATION:
            if record["preservation_status"] != Preservation.SUPERSEDED.value:
                _fail(
                    "DISSENT_DROPPED",
                    "the strongest dissent must survive into the record",
                    {"minority_report_id": strongest},
                )

    grounding = {
        "attack_count": len(validated),
        "attacks_citing_evidence": sum(
            1 for record in validated if record["evidence_ids"]
        ),
        "open_challenge_ids": sorted(
            record["cross_exam_id"]
            for record in validated
            if record["resolution_status"] == OPEN_STATUS
        ),
        "targeted_assertion_ids": sorted(
            {record["target_assertion_id"] for record in validated}
        ),
        "targeted_brief_ids": sorted(
            {record["target_brief_id"] for record in validated}
        ),
    }
    dissent = {
        "preserved_report_ids": sorted(
            report["minority_report_id"]
            for report in reports
            if report["preservation_status"] in SURVIVING_PRESERVATION
        ),
        "report_count": len(reports),
        "strongest_report_id": strongest,
        "superseded_report_ids": sorted(
            report["minority_report_id"]
            for report in reports
            if report["preservation_status"] == Preservation.SUPERSEDED.value
        ),
    }

    payload: dict[str, Any] = {
        "created_at": created_at,
        "cross_examinations": validated,
        "dissent": dissent,
        "grounding": grounding,
        "minority_reports": reports,
        "round": round_number,
        "run_id": run_id,
    }
    payload["cross_exam_round_id"] = "CX-" + _hex_digest(
        {
            "created_at": created_at,
            "cross_examinations": validated,
            "minority_reports": reports,
            "round": round_number,
            "run_id": run_id,
        }
    )
    payload["round_hash"] = _hash_excluding(payload, "round_hash")
    return validate_cross_exam_round(repository_root, payload)


def validate_cross_exam_round(
    repository_root: Path, payload: Mapping[str, Any]
) -> SealedArtifact:
    """Validate one sealed round's shape, grounding, dissent, and self-hash."""

    value = _mapping(payload, "CrossExamRound")
    _exact_fields(value, ROUND_FIELDS, "CrossExamRound")
    _text(value["cross_exam_round_id"], "cross_exam_round_id")
    _text(value["run_id"], "run_id")
    _timestamp(value["created_at"], "created_at")
    if type(value["round"]) is not int or value["round"] < 2:
        _fail("ROUND_INVALID", "cross-examination begins after the blind first round")

    records = _sequence(value["cross_examinations"], "cross_examinations")
    ids = [str(_mapping(entry, "challenge")["cross_exam_id"]) for entry in records]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        _fail("INPUT_INVALID", "challenges must be unique and sorted ascending")
    for entry in records:
        record = _mapping(entry, "challenge")
        if not _sequence(record["evidence_ids"], "evidence_ids"):
            _fail(
                "ATTACK_UNGROUNDED",
                "a sealed round may not carry an attack that cites nothing",
                {"cross_exam_id": record["cross_exam_id"]},
            )
        for field in ("target_brief_id", "target_assertion_id"):
            _text(record[field], field)

    grounding = _mapping(value["grounding"], "grounding")
    if grounding["attack_count"] != len(records) or grounding[
        "attacks_citing_evidence"
    ] != len(records):
        _fail(
            "GROUNDING_MISMATCH",
            "every sealed attack must be counted as citing evidence",
        )

    reports = _sequence(value["minority_reports"], "minority_reports")
    report_ids = [
        str(_mapping(entry, "minority report")["minority_report_id"])
        for entry in reports
    ]
    if report_ids != sorted(report_ids) or len(report_ids) != len(set(report_ids)):
        _fail("INPUT_INVALID", "minority reports must be unique and sorted ascending")
    dissent = _mapping(value["dissent"], "dissent")
    if dissent["report_count"] != len(reports):
        _fail(
            "DISSENT_MISMATCH",
            "the dissent count does not reconcile with the reports",
        )
    recomputed = strongest_dissent(
        [_mapping(entry, "minority report") for entry in reports]
    )
    if dissent["strongest_report_id"] != recomputed:
        _fail(
            "DISSENT_MISMATCH",
            "the recorded strongest dissent is not the one the reports derive",
            {"derived": recomputed, "recorded": dissent["strongest_report_id"]},
        )
    if recomputed is not None:
        record = next(
            _mapping(entry, "minority report")
            for entry in reports
            if str(entry["minority_report_id"]) == recomputed
        )
        surviving = (
            recomputed in dissent["preserved_report_ids"]
            or recomputed in dissent["superseded_report_ids"]
        )
        if not surviving:
            _fail(
                "DISSENT_DROPPED",
                "the strongest dissent must appear in the sealed record",
                {"minority_report_id": recomputed},
            )
        if (
            record["preservation_status"] == Preservation.SUPERSEDED.value
            and not record["evidence_ids"]
        ):
            _fail(
                "SUPERSESSION_UNSUPPORTED",
                "a superseded dissent must cite the evidence that superseded it",
                {"minority_report_id": recomputed},
            )
    if _hash_excluding(value, "round_hash") != value["round_hash"]:
        _fail("ROUND_HASH_MISMATCH", "round_hash does not match its content")
    return SealedArtifact("CrossExamRound", _canonical_json(value))


def seal_record(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    """Stamp a cross-examination or minority report with its content hash."""

    value = _mapping(payload, "record")
    value[field] = _hash_excluding(value, field)
    return value
