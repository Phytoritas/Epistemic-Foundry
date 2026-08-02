"""P04 judge adjudication and the independent attestation gate.

The judge writes the verdict, but the verdict is not what decides promotion.
Two separations keep it that way.

A majority cannot promote.  Agreement among briefs is recorded and carries no
weight: the recommendation is bounded above by the deterministic P02 ceiling,
a sustained veto or any unanswered challenge forces ``BLOCK``, and the judge may
narrow the result but never raise it.  An attempt to override a deterministic
gate is recorded and then refused, so the attempt is visible rather than
absorbed.

The attestor sees a structured pack, not a transcript.  Persuasion is exactly
what an independent reviewer must not receive, so the pack carries ids, hashes,
statuses, ceilings, and counts, and any field carrying brief or challenge prose
is refused.  The attestor must be a different actor from the judge, must state
its independence, and must attest to exactly the pack it was given.
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
#: The canonical schemas are the declaring source of every vocabulary here.
ADJUDICATION_SCHEMA_PATH: Final = "schemas/adjudication.schema.json"
ATTESTATION_SCHEMA_PATH: Final = "schemas/attestation.schema.json"
#: The recommendation that stops a promotion outright.
BLOCK: Final = "BLOCK"


class AttestorType(str, Enum):
    HUMAN = "human"
    MODEL = "model"
    SERVICE = "service"
    FORMAL_VERIFIER = "formal_verifier"


#: Field names that carry persuasion rather than structure.  A pack containing
#: any of them has become a transcript and is refused.
PERSUASIVE_FIELDS: Final = (
    "challenge",
    "minority_claim",
    "rationale",
    "response",
    "statement",
    "strongest_counterargument",
    "text",
    "why_majority_may_be_wrong",
)

ADJUDICATION_FIELDS: Final = frozenset(
    {
        "adjudication_id",
        "run_id",
        "hypothesis_id",
        "gate_decision_ids",
        "brief_ids",
        "cross_examination_ids",
        "minority_report_ids",
        "verdict",
        "scope_narrowing",
        "strongest_support_id",
        "strongest_counterevidence_id",
        "unresolved_issue_ids",
        "promotion_recommendation",
        "rationale",
        "deterministic_gate_override_attempted",
        "created_at",
        "adjudication_hash",
    }
)
PACK_FIELDS: Final = frozenset(
    {
        "attestation_pack_id",
        "run_id",
        "hypothesis_id",
        "adjudication_id",
        "adjudication_hash",
        "audit_id",
        "combined_ceiling",
        "veto_sustained_by",
        "cross_exam_round_id",
        "open_challenge_ids",
        "strongest_dissent_id",
        "brief_ids",
        "gate_decision_ids",
        "promotion_recommendation",
        "verdict",
        "created_at",
        "pack_hash",
    }
)
#: Canonical shape of one attestation check (schemas/attestation.schema.json).
_CHECK_FIELDS: Final = frozenset({"check_id", "status", "reason"})
ATTESTATION_FIELDS: Final = frozenset(
    {
        "attestation_id",
        "run_id",
        "subject_artifact_id",
        "attestor_id",
        "attestor_type",
        "input_artifact_ids",
        "checks",
        "overall_status",
        "independence_statement",
        "model_or_identity_version",
        "created_at",
        "attestation_hash",
        "signature",
    }
)
GATE_FIELDS: Final = frozenset(
    {
        "adjudication",
        "attestation",
        "attestation_pack",
        "created_at",
        "gate_id",
        "hypothesis_id",
        "independence",
        "majority",
        "promotion_bound",
        "run_id",
        "gate_hash",
    }
)


class AdjudicationError(ValueError):
    """Typed fail-closed P04 contract error."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context) if context is not None else {}


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    raise AdjudicationError(code, message, context)


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


def _ids(value: object, label: str) -> list[str]:
    return sorted({_text(entry, label) for entry in _sequence(value, label)})


@lru_cache(maxsize=8)
def _schema_enum(repository_root: str, relative: str, field: str) -> tuple[str, ...]:
    schema = json.loads((Path(repository_root) / relative).read_text(encoding="utf-8"))
    declared = schema.get("properties", {}).get(field, {}).get("enum")
    if not isinstance(declared, list) or not declared:
        _fail("VOCABULARY_UNREADABLE", f"{relative} declares no {field} enum")
    return tuple(str(entry) for entry in declared)  # type: ignore[union-attr]


def verdicts(repository_root: Path) -> tuple[str, ...]:
    """Canonical verdict vocabulary, read from the adjudication schema."""

    return _schema_enum(str(repository_root), ADJUDICATION_SCHEMA_PATH, "verdict")


def recommendations(repository_root: Path) -> tuple[str, ...]:
    """Canonical promotion recommendations, weakest first, ``BLOCK`` lowest."""

    return _schema_enum(
        str(repository_root), ADJUDICATION_SCHEMA_PATH, "promotion_recommendation"
    )


def attestation_statuses(repository_root: Path) -> tuple[str, ...]:
    """Canonical attestation outcomes, read from the attestation schema."""

    return _schema_enum(str(repository_root), ATTESTATION_SCHEMA_PATH, "overall_status")


def recommendation_rank(repository_root: Path, value: str) -> int:
    """Position on the recommendation ladder; an unknown value fails closed."""

    ladder = recommendations(repository_root)
    text = _text(value, "promotion recommendation")
    if text not in ladder:
        _fail(
            "RECOMMENDATION_UNKNOWN",
            "a recommendation must be canonical",
            {"allowed": list(ladder), "value": text},
        )
    return ladder.index(text)


def assert_structured(value: object, label: str = "attestation pack") -> None:
    """Refuse any nested field that carries persuasion rather than structure."""

    if isinstance(value, Mapping):
        for key, entry in value.items():
            if str(key) in PERSUASIVE_FIELDS:
                _fail(
                    "PERSUASIVE_TRANSCRIPT_INCLUDED",
                    "an attestation pack may not carry brief or challenge prose",
                    {"field": str(key), "label": label},
                )
            assert_structured(entry, label)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for entry in value:
            assert_structured(entry, label)


def majority_verdict(
    repository_root: Path, brief_verdicts: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """What the briefs collectively said, recorded but never load-bearing.

    Reported so a reader can see that the majority existed and did not decide
    anything; the recommendation is bounded elsewhere.
    """

    canonical = verdicts(repository_root)
    counts: dict[str, int] = {}
    for entry in brief_verdicts:
        record = _mapping(entry, "brief verdict")
        verdict = _text(record["verdict_candidate"], "verdict_candidate")
        if verdict not in canonical:
            _fail(
                "VERDICT_INVALID",
                "a brief verdict must be canonical",
                {"value": verdict},
            )
        counts[verdict] = counts.get(verdict, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return {
            "brief_count": 0,
            "is_unanimous": False,
            "majority_verdict": None,
            "verdict_counts": {},
        }
    best = max(counts.values())
    winners = sorted(verdict for verdict, count in counts.items() if count == best)
    return {
        "brief_count": total,
        "is_unanimous": len(counts) == 1,
        "majority_verdict": winners[0] if len(winners) == 1 else None,
        "verdict_counts": dict(sorted(counts.items())),
    }


def promotion_bound(
    repository_root: Path,
    *,
    combined_ceiling: str,
    veto_sustained_by: Sequence[str],
    open_challenge_ids: Sequence[str],
) -> dict[str, Any]:
    """The highest recommendation the deterministic gates leave available.

    A sustained veto or an unanswered challenge forces ``BLOCK``: an objection
    nobody answered is not a detail the judge may weigh against a majority.
    """

    ceiling = _text(combined_ceiling, "combined_ceiling")
    recommendation_rank(repository_root, ceiling)
    vetoes = _ids(veto_sustained_by, "veto_sustained_by")
    open_ids = _ids(open_challenge_ids, "open_challenge_ids")
    reasons: list[str] = []
    if vetoes:
        reasons.append("a method veto is sustained")
    if open_ids:
        reasons.append("a cross-examination is unanswered")
    bound = BLOCK if reasons else ceiling
    return {
        "audit_ceiling": ceiling,
        "block_reasons": sorted(reasons),
        "maximum_recommendation": bound,
        "open_challenge_ids": open_ids,
        "veto_sustained_by": vetoes,
    }


def validate_adjudication(
    repository_root: Path, payload: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate one adjudication record's shape and vocabulary."""

    value = _mapping(payload, "Adjudication")
    _exact_fields(value, ADJUDICATION_FIELDS, "Adjudication")
    verdict = _text(value["verdict"], "verdict")
    if verdict not in verdicts(repository_root):
        _fail("VERDICT_INVALID", "the verdict is not canonical", {"value": verdict})
    recommendation = _text(
        value["promotion_recommendation"], "promotion_recommendation"
    )
    recommendation_rank(repository_root, recommendation)
    override = value["deterministic_gate_override_attempted"]
    if type(override) is not bool:
        _fail(
            "INPUT_INVALID", "deterministic_gate_override_attempted must be a boolean"
        )
    return {
        "adjudication_hash": _text(value["adjudication_hash"], "adjudication_hash"),
        "adjudication_id": _text(value["adjudication_id"], "adjudication_id"),
        "brief_ids": _ids(value["brief_ids"], "brief_ids"),
        "created_at": _timestamp(value["created_at"], "created_at"),
        "cross_examination_ids": _ids(
            value["cross_examination_ids"], "cross_examination_ids"
        ),
        "deterministic_gate_override_attempted": override,
        "gate_decision_ids": _ids(value["gate_decision_ids"], "gate_decision_ids"),
        "hypothesis_id": _text(value["hypothesis_id"], "hypothesis_id"),
        "minority_report_ids": _ids(
            value["minority_report_ids"], "minority_report_ids"
        ),
        "promotion_recommendation": recommendation,
        "rationale": _text(value["rationale"], "rationale"),
        "run_id": _text(value["run_id"], "run_id"),
        "scope_narrowing": _text(value["scope_narrowing"], "scope_narrowing"),
        "strongest_counterevidence_id": _text(
            value["strongest_counterevidence_id"], "strongest_counterevidence_id"
        ),
        "strongest_support_id": _text(
            value["strongest_support_id"], "strongest_support_id"
        ),
        "unresolved_issue_ids": _ids(
            value["unresolved_issue_ids"], "unresolved_issue_ids"
        ),
        "verdict": verdict,
    }


def build_attestation_pack(
    repository_root: Path,
    adjudication: Mapping[str, Any],
    *,
    audit_id: str,
    combined_ceiling: str,
    veto_sustained_by: Sequence[str],
    cross_exam_round_id: str,
    open_challenge_ids: Sequence[str],
    strongest_dissent_id: str | None,
    created_at: str,
) -> SealedArtifact:
    """Assemble the structured pack an independent attestor may read."""

    record = validate_adjudication(repository_root, adjudication)
    payload: dict[str, Any] = {
        "adjudication_hash": record["adjudication_hash"],
        "adjudication_id": record["adjudication_id"],
        "audit_id": _text(audit_id, "audit_id"),
        "brief_ids": record["brief_ids"],
        "combined_ceiling": _text(combined_ceiling, "combined_ceiling"),
        "created_at": _timestamp(created_at, "created_at"),
        "cross_exam_round_id": _text(cross_exam_round_id, "cross_exam_round_id"),
        "gate_decision_ids": record["gate_decision_ids"],
        "hypothesis_id": record["hypothesis_id"],
        "open_challenge_ids": _ids(open_challenge_ids, "open_challenge_ids"),
        "promotion_recommendation": record["promotion_recommendation"],
        "run_id": record["run_id"],
        "strongest_dissent_id": (
            None if strongest_dissent_id is None else _text(strongest_dissent_id, "id")
        ),
        "verdict": record["verdict"],
        "veto_sustained_by": _ids(veto_sustained_by, "veto_sustained_by"),
    }
    assert_structured(payload)
    payload["attestation_pack_id"] = "AP-" + _hex_digest(payload)
    payload["pack_hash"] = _hash_excluding(payload, "pack_hash")
    return validate_attestation_pack(payload)


def validate_attestation_pack(payload: Mapping[str, Any]) -> SealedArtifact:
    """Validate the pack's field set, structure-only content, and self-hash."""

    value = _mapping(payload, "AttestationPack")
    _exact_fields(value, PACK_FIELDS, "AttestationPack")
    assert_structured(value)
    _text(value["attestation_pack_id"], "attestation_pack_id")
    _text(value["run_id"], "run_id")
    _timestamp(value["created_at"], "created_at")
    if not SHA256_PATTERN.fullmatch(str(value["pack_hash"])):
        _fail("FIELD_SET_INVALID", "pack_hash must be a sha256 digest")
    if _hash_excluding(value, "pack_hash") != value["pack_hash"]:
        _fail("PACK_HASH_MISMATCH", "pack_hash does not match its content")
    return SealedArtifact("AttestationPack", _canonical_json(value))


def validate_attestation(
    repository_root: Path,
    payload: Mapping[str, Any],
    pack: Mapping[str, Any],
    *,
    judge_id: str,
) -> dict[str, Any]:
    """Validate one attestation, including that it is genuinely independent."""

    value = _mapping(payload, "Attestation")
    _exact_fields(value, ATTESTATION_FIELDS, "Attestation")
    attestor = _text(value["attestor_id"], "attestor_id")
    if attestor == _text(judge_id, "judge_id"):
        _fail(
            "ATTESTOR_NOT_INDEPENDENT",
            "the judge may not attest to its own adjudication",
            {"attestor_id": attestor},
        )
    attestor_type = _text(value["attestor_type"], "attestor_type")
    if attestor_type not in tuple(entry.value for entry in AttestorType):
        _fail(
            "ATTESTOR_TYPE_INVALID",
            "attestor_type is not canonical",
            {"value": attestor_type},
        )
    status = _text(value["overall_status"], "overall_status")
    if status not in attestation_statuses(repository_root):
        _fail(
            "ATTESTATION_STATUS_INVALID",
            "overall_status is not canonical",
            {"value": status},
        )
    subject = _text(value["subject_artifact_id"], "subject_artifact_id")
    if subject != pack["adjudication_id"]:
        _fail(
            "ATTESTATION_SUBJECT_MISMATCH",
            "an attestation must name the adjudication its pack describes",
            {"subject_artifact_id": subject},
        )
    inputs = _ids(value["input_artifact_ids"], "input_artifact_ids")
    if inputs != [str(pack["attestation_pack_id"])]:
        _fail(
            "ATTESTATION_INPUT_MISMATCH",
            "an attestation must rest on exactly the pack it was given",
            {"expected": [pack["attestation_pack_id"]], "input_artifact_ids": inputs},
        )
    checks = _sequence(value["checks"], "checks")
    if not checks:
        _fail(
            "ATTESTATION_UNCHECKED",
            "an attestation must record the checks it actually ran",
            {"attestation_id": value["attestation_id"]},
        )
    assert_structured(checks, "attestation checks")
    for index, entry in enumerate(checks):
        _exact_fields(_mapping(entry, f"checks[{index}]"), _CHECK_FIELDS, "check")
    return {
        "attestation_hash": _text(value["attestation_hash"], "attestation_hash"),
        "attestation_id": _text(value["attestation_id"], "attestation_id"),
        "attestor_id": attestor,
        "attestor_type": attestor_type,
        "checks": [_mapping(entry, "check") for entry in checks],
        "created_at": _timestamp(value["created_at"], "created_at"),
        "independence_statement": _text(
            value["independence_statement"], "independence_statement"
        ),
        "input_artifact_ids": inputs,
        "model_or_identity_version": _text(
            value["model_or_identity_version"], "model_or_identity_version"
        ),
        "overall_status": status,
        "run_id": _text(value["run_id"], "run_id"),
        "signature": _text(value["signature"], "signature"),
        "subject_artifact_id": subject,
    }


def seal_judgment(
    repository_root: Path,
    adjudication: Mapping[str, Any],
    attestation: Mapping[str, Any],
    brief_verdicts: Sequence[Mapping[str, Any]],
    *,
    judge_id: str,
    audit_id: str,
    combined_ceiling: str,
    veto_sustained_by: Sequence[str],
    cross_exam_round_id: str,
    open_challenge_ids: Sequence[str],
    strongest_dissent_id: str | None,
    created_at: str,
) -> SealedArtifact:
    """Bound the recommendation, build the pack, and seal the attested gate."""

    record = validate_adjudication(repository_root, adjudication)
    created_at = _timestamp(created_at, "created_at")
    if record["deterministic_gate_override_attempted"]:
        _fail(
            "GATE_OVERRIDE_ATTEMPTED",
            "a judge may not override a deterministic gate",
            {"adjudication_id": record["adjudication_id"]},
        )
    bound = promotion_bound(
        repository_root,
        combined_ceiling=combined_ceiling,
        open_challenge_ids=open_challenge_ids,
        veto_sustained_by=veto_sustained_by,
    )
    if recommendation_rank(
        repository_root, record["promotion_recommendation"]
    ) > recommendation_rank(repository_root, bound["maximum_recommendation"]):
        _fail(
            "MAJORITY_CANNOT_PROMOTE",
            "the recommendation exceeds what the deterministic gates allow",
            {
                "maximum": bound["maximum_recommendation"],
                "recommendation": record["promotion_recommendation"],
                "reasons": bound["block_reasons"],
            },
        )
    missing = sorted(
        set(bound["open_challenge_ids"]) - set(record["unresolved_issue_ids"])
    )
    if missing:
        _fail(
            "UNRESOLVED_ISSUE_DROPPED",
            "every unanswered challenge must appear as an unresolved issue",
            {"cross_exam_ids": missing},
        )
    if (
        strongest_dissent_id is not None
        and strongest_dissent_id not in record["minority_report_ids"]
    ):
        _fail(
            "DISSENT_UNCITED",
            "the adjudication must cite the strongest dissent it decided against",
            {"minority_report_id": strongest_dissent_id},
        )

    pack = build_attestation_pack(
        repository_root,
        adjudication,
        audit_id=audit_id,
        combined_ceiling=combined_ceiling,
        created_at=created_at,
        cross_exam_round_id=cross_exam_round_id,
        open_challenge_ids=open_challenge_ids,
        strongest_dissent_id=strongest_dissent_id,
        veto_sustained_by=veto_sustained_by,
    ).payload
    attested = validate_attestation(
        repository_root, attestation, pack, judge_id=judge_id
    )
    if attested["run_id"] != record["run_id"]:
        _fail(
            "GATE_INCOHERENT",
            "the attestation belongs to a different run",
            {"attestation_id": attested["attestation_id"]},
        )
    majority = majority_verdict(repository_root, brief_verdicts)

    payload: dict[str, Any] = {
        "adjudication": record,
        "attestation": attested,
        "attestation_pack": pack,
        "created_at": created_at,
        "hypothesis_id": record["hypothesis_id"],
        "independence": {
            "attestor_id": attested["attestor_id"],
            "attestor_is_judge": False,
            "judge_id": _text(judge_id, "judge_id"),
        },
        "majority": {
            **majority,
            "majority_influenced_recommendation": False,
        },
        "promotion_bound": bound,
        "run_id": record["run_id"],
    }
    payload["gate_id"] = "PJ-" + _hex_digest(
        {
            "adjudication_id": record["adjudication_id"],
            "attestation_id": attested["attestation_id"],
            "created_at": created_at,
            "promotion_bound": bound,
            "run_id": record["run_id"],
        }
    )
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")
    return validate_judgment(repository_root, payload)


def validate_judgment(
    repository_root: Path, payload: Mapping[str, Any]
) -> SealedArtifact:
    """Validate one sealed gate: bound, independence, citations, self-hash."""

    value = _mapping(payload, "ParliamentJudgment")
    _exact_fields(value, GATE_FIELDS, "ParliamentJudgment")
    _text(value["gate_id"], "gate_id")
    _text(value["run_id"], "run_id")
    _timestamp(value["created_at"], "created_at")
    adjudication = _mapping(value["adjudication"], "adjudication")
    if adjudication["deterministic_gate_override_attempted"]:
        _fail(
            "GATE_OVERRIDE_ATTEMPTED",
            "a sealed gate may not record a successful override attempt",
        )
    bound = _mapping(value["promotion_bound"], "promotion_bound")
    if recommendation_rank(
        repository_root, str(adjudication["promotion_recommendation"])
    ) > recommendation_rank(repository_root, str(bound["maximum_recommendation"])):
        _fail(
            "MAJORITY_CANNOT_PROMOTE",
            "the sealed recommendation exceeds the deterministic bound",
        )
    if bound["veto_sustained_by"] or bound["open_challenge_ids"]:
        if bound["maximum_recommendation"] != BLOCK:
            _fail(
                "PROMOTION_BOUND_MISMATCH",
                "a veto or an unanswered challenge must bound the gate at BLOCK",
            )
    missing = sorted(
        set(bound["open_challenge_ids"]) - set(adjudication["unresolved_issue_ids"])
    )
    if missing:
        _fail(
            "UNRESOLVED_ISSUE_DROPPED",
            "a sealed gate may not omit an unanswered challenge",
            {"cross_exam_ids": missing},
        )
    independence = _mapping(value["independence"], "independence")
    if (
        independence["attestor_id"] == independence["judge_id"]
        or independence["attestor_is_judge"]
    ):
        _fail(
            "ATTESTOR_NOT_INDEPENDENT",
            "a sealed gate may not record the judge as its own attestor",
        )
    majority = _mapping(value["majority"], "majority")
    if majority["majority_influenced_recommendation"] is not False:
        _fail(
            "MAJORITY_CANNOT_PROMOTE",
            "a sealed gate may not record the majority as load-bearing",
        )
    validate_attestation_pack(_mapping(value["attestation_pack"], "attestation_pack"))
    if _hash_excluding(value, "gate_hash") != value["gate_hash"]:
        _fail("GATE_HASH_MISMATCH", "gate_hash does not match its content")
    return SealedArtifact("ParliamentJudgment", _canonical_json(value))


def seal_record(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    """Stamp an adjudication or attestation with its content hash."""

    value = _mapping(payload, "record")
    value[field] = _hash_excluding(value, field)
    return value
