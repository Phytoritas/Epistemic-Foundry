"""P02 auditor verdicts, promotion ceilings, and the method veto.

Four auditors examine a candidate from different angles.  Each returns the
highest promotion level its own findings support; this module combines those
into one ceiling and does so deterministically, so the same audits always cap
the candidate at the same level.

Two things are enforced rather than trusted.

The combined ceiling is derived.  It is the lowest ceiling any auditor set, and
a sustained method veto drops it to the floor of the ladder.  No auditor can
raise it, and a declared ceiling above the derived one is refused rather than
recorded.

Method-incompatible evidence is never pooled.  An observational correlation
averaged with a randomized trial produces a number describing neither, so the
method auditor reports one ceiling per method stratum and the component ceiling
is the strongest stratum, never a blend.  A single pooled figure spanning more
than one stratum is refused.
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
#: The passport schema is the declaring source of the promotion ladder.
PASSPORT_SCHEMA_PATH: Final = "schemas/hypothesis-passport.schema.json"


class Auditor(str, Enum):
    """The four P02 audit angles."""

    METHOD = "method_auditor"
    SCOPE = "scope_auditor"
    CAUSAL = "causal_auditor"
    NOVELTY = "novelty_examiner"


class VetoStatus(str, Enum):
    """A veto is raised, then either sustained or withdrawn with a reason."""

    NONE = "NONE"
    SUSTAINED = "SUSTAINED"
    WITHDRAWN = "WITHDRAWN"


AUDITORS: Final = tuple(entry.value for entry in Auditor)
VETO_STATUSES: Final = tuple(entry.value for entry in VetoStatus)
#: Only the method auditor may stop a promotion outright.
VETO_CAPABLE_AUDITORS: Final = (Auditor.METHOD.value,)
#: Typed reasons an auditor may lower a ceiling; silence is not one of them.
FINDING_CODES: Final = (
    "CONSTRUCT_MISMATCH",
    "IDENTIFICATION_UNSUPPORTED",
    "MEASUREMENT_INVALID",
    "PRIOR_ART_UNSEARCHED",
    "SAMPLE_INSUFFICIENT",
    "SCOPE_EXTRAPOLATED",
    "STATISTICS_UNSOUND",
)

VERDICT_FIELDS: Final = frozenset(
    {
        "auditor",
        "ceiling",
        "findings",
        "stratum_ceilings",
        "veto_status",
        "veto_reason",
        "provenance_ref",
    }
)
_FINDING_FIELDS: Final = frozenset({"code", "statement", "evidence_ids"})
AUDIT_FIELDS: Final = frozenset(
    {
        "audit_id",
        "subject_id",
        "run_id",
        "created_at",
        "combined_ceiling",
        "declared_ceiling",
        "auditor_ceilings",
        "verdicts",
        "veto",
        "stratification",
        "audit_hash",
    }
)


class AuditorContractError(ValueError):
    """Typed fail-closed P02 contract error."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context) if context is not None else {}


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    raise AuditorContractError(code, message, context)


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


def _derive_audit_id(
    combined_ceiling: str,
    created_at: str,
    run_id: str,
    subject_id: str,
    verdicts: Sequence[Mapping[str, Any]],
) -> str:
    return "PA-" + _hex_digest(
        {
            "combined_ceiling": combined_ceiling,
            "created_at": created_at,
            "run_id": run_id,
            "subject_id": subject_id,
            "verdicts": verdicts,
        }
    )


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


@lru_cache(maxsize=4)
def promotion_ladder(repository_root: str) -> tuple[str, ...]:
    """The canonical promotion ladder, read from the passport schema.

    The ladder is never re-spelled here: a level added to the schema appears
    automatically, and a level this component invents would not resolve.
    """

    schema = json.loads(
        (Path(repository_root) / PASSPORT_SCHEMA_PATH).read_text(encoding="utf-8")
    )
    declared = schema.get("properties", {}).get("promotion_level", {}).get("enum")
    if not isinstance(declared, list) or not declared:
        _fail(
            "LADDER_UNREADABLE",
            "the passport schema declares no promotion_level enum",
        )
    return tuple(str(entry) for entry in declared)  # type: ignore[union-attr]


def ladder_rank(repository_root: Path, level: str) -> int:
    """Position of one level on the ladder; an unknown level fails closed."""

    ladder = promotion_ladder(str(repository_root))
    text = _text(level, "promotion level")
    if text not in ladder:
        _fail(
            "LEVEL_UNKNOWN",
            "a promotion level must be a canonical ladder level",
            {"allowed": list(ladder), "value": text},
        )
    return ladder.index(text)


def _validate_finding(value: object, index: int, auditor: str) -> dict[str, Any]:
    finding = _mapping(value, f"{auditor}.findings[{index}]")
    _exact_fields(finding, _FINDING_FIELDS, f"{auditor}.findings[{index}]")
    code = _text(finding["code"], "code")
    if code not in FINDING_CODES:
        _fail(
            "FINDING_CODE_INVALID",
            "a finding must carry a canonical reason code",
            {"auditor": auditor, "value": code},
        )
    return {
        "code": code,
        "evidence_ids": sorted(
            {
                _text(entry, "evidence_id")
                for entry in _sequence(finding["evidence_ids"], "evidence_ids")
            }
        ),
        "statement": _text(finding["statement"], "statement"),
    }


def validate_verdict(
    repository_root: Path, value: object, index: int = 0
) -> dict[str, Any]:
    """Validate one auditor verdict, including who may veto and how."""

    verdict = _mapping(value, f"verdicts[{index}]")
    _exact_fields(verdict, VERDICT_FIELDS, f"verdicts[{index}]")
    auditor = _text(verdict["auditor"], "auditor")
    if auditor not in AUDITORS:
        _fail(
            "AUDITOR_UNKNOWN",
            "a verdict must come from a canonical auditor",
            {"allowed": list(AUDITORS), "value": auditor},
        )
    ceiling = _text(verdict["ceiling"], "ceiling")
    ladder_rank(repository_root, ceiling)
    veto_status = _text(verdict["veto_status"], "veto_status")
    if veto_status not in VETO_STATUSES:
        _fail("VETO_STATUS_INVALID", f"{auditor} declares a non-canonical veto status")
    if veto_status != VetoStatus.NONE.value and auditor not in VETO_CAPABLE_AUDITORS:
        _fail(
            "VETO_UNAUTHORIZED",
            "only the method auditor may veto a promotion",
            {"auditor": auditor},
        )
    veto_reason = verdict["veto_reason"]
    if veto_status == VetoStatus.NONE.value:
        if veto_reason is not None:
            _fail(
                "VETO_REASON_UNEXPECTED",
                "a verdict with no veto must not carry a veto reason",
                {"auditor": auditor},
            )
    else:
        veto_reason = _text(veto_reason, "veto_reason")
    findings = [
        _validate_finding(entry, position, auditor)
        for position, entry in enumerate(_sequence(verdict["findings"], "findings"))
    ]
    findings.sort(key=lambda entry: (entry["code"], entry["statement"]))
    strata = _mapping(verdict["stratum_ceilings"], "stratum_ceilings")
    normalized_strata: dict[str, str] = {}
    for stratum in sorted(strata):
        level = _text(strata[stratum], f"stratum_ceilings.{stratum}")
        ladder_rank(repository_root, level)
        normalized_strata[_text(stratum, "stratum")] = level
    if auditor == Auditor.METHOD.value:
        if not normalized_strata:
            _fail(
                "METHOD_STRATA_MISSING",
                "the method auditor must report a ceiling per method stratum",
            )
        strongest = max(
            normalized_strata.values(),
            key=lambda level: ladder_rank(repository_root, level),
        )
        if ceiling != strongest:
            _fail(
                "METHOD_POOLED",
                "the method ceiling must be the strongest stratum, never a blend",
                {
                    "declared": ceiling,
                    "strongest_stratum": strongest,
                    "strata": normalized_strata,
                },
            )
    elif normalized_strata:
        _fail(
            "STRATA_UNEXPECTED",
            "only the method auditor stratifies by method",
            {"auditor": auditor},
        )
    return {
        "auditor": auditor,
        "ceiling": ceiling,
        "findings": findings,
        "provenance_ref": _text(verdict["provenance_ref"], "provenance_ref"),
        "stratum_ceilings": normalized_strata,
        "veto_reason": veto_reason,
        "veto_status": veto_status,
    }


def combined_ceiling(
    repository_root: Path, verdicts: Sequence[Mapping[str, Any]]
) -> tuple[str, dict[str, Any]]:
    """The lowest ceiling any auditor set, floored by a sustained veto.

    No auditor can raise the ceiling: agreement from three angles does not
    overrule the one that found the measurement cannot support the claim.
    """

    ladder = promotion_ladder(str(repository_root))
    if not verdicts:
        _fail("AUDIT_INCOMPLETE", "an audit needs at least one auditor verdict")
    ceilings = {
        str(verdict["auditor"]): str(verdict["ceiling"]) for verdict in verdicts
    }
    lowest = min(
        ceilings.values(), key=lambda level: ladder_rank(repository_root, level)
    )
    sustained = sorted(
        str(verdict["auditor"])
        for verdict in verdicts
        if verdict["veto_status"] == VetoStatus.SUSTAINED.value
    )
    veto = {
        "floor_applied": bool(sustained),
        "sustained_by": sustained,
        "withdrawn_by": sorted(
            str(verdict["auditor"])
            for verdict in verdicts
            if verdict["veto_status"] == VetoStatus.WITHDRAWN.value
        ),
    }
    ceiling = ladder[0] if sustained else lowest
    return ceiling, veto


def evaluate_audit(
    repository_root: Path,
    verdicts: Sequence[Mapping[str, Any]],
    *,
    subject_id: str,
    run_id: str,
    created_at: str,
    declared_ceiling: str | None = None,
) -> SealedArtifact:
    """Combine four auditor verdicts into one sealed, derived ceiling."""

    subject_id = _text(subject_id, "subject_id")
    run_id = _text(run_id, "run_id")
    created_at = _timestamp(created_at, "created_at")

    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(verdicts):
        verdict = validate_verdict(repository_root, entry, index)
        if verdict["auditor"] in seen:
            _fail(
                "AUDITOR_DUPLICATED",
                "each auditor contributes exactly one verdict",
                {"auditor": verdict["auditor"]},
            )
        seen.add(verdict["auditor"])
        validated.append(verdict)
    missing = sorted(set(AUDITORS) - seen)
    if missing:
        _fail(
            "AUDIT_INCOMPLETE",
            "every canonical auditor must return a verdict",
            {"auditors": missing},
        )
    validated.sort(key=lambda verdict: verdict["auditor"])

    ceiling, veto = combined_ceiling(repository_root, validated)
    declared = declared_ceiling if declared_ceiling is not None else ceiling
    ladder_rank(repository_root, declared)
    if ladder_rank(repository_root, declared) > ladder_rank(repository_root, ceiling):
        _fail(
            "CEILING_OVERCLAIM",
            "the declared ceiling exceeds what the audits support",
            {"declared": declared, "derived": ceiling},
        )

    method = next(
        verdict for verdict in validated if verdict["auditor"] == Auditor.METHOD.value
    )
    stratification = {
        "pooled": False,
        "strata": method["stratum_ceilings"],
        "stratum_count": len(method["stratum_ceilings"]),
        "strongest_stratum_ceiling": method["ceiling"],
    }

    payload: dict[str, Any] = {
        "auditor_ceilings": {
            verdict["auditor"]: verdict["ceiling"] for verdict in validated
        },
        "combined_ceiling": ceiling,
        "created_at": created_at,
        "declared_ceiling": declared,
        "run_id": run_id,
        "stratification": stratification,
        "subject_id": subject_id,
        "verdicts": validated,
        "veto": veto,
    }
    payload["audit_id"] = _derive_audit_id(
        ceiling, created_at, run_id, subject_id, validated
    )
    payload["audit_hash"] = _hash_excluding(payload, "audit_hash")
    return validate_audit(repository_root, payload)


def validate_audit(repository_root: Path, payload: Mapping[str, Any]) -> SealedArtifact:
    """Validate one audit record's shape, derived ceiling, and self-hash."""

    value = _mapping(payload, "ParliamentAudit")
    _exact_fields(value, AUDIT_FIELDS, "ParliamentAudit")
    _text(value["audit_id"], "audit_id")
    subject_id = _text(value["subject_id"], "subject_id")
    run_id = _text(value["run_id"], "run_id")
    created_at = _timestamp(value["created_at"], "created_at")
    verdicts = [
        validate_verdict(repository_root, entry, index)
        for index, entry in enumerate(_sequence(value["verdicts"], "verdicts"))
    ]
    auditors = [verdict["auditor"] for verdict in verdicts]
    if sorted(auditors) != sorted(AUDITORS) or auditors != sorted(auditors):
        _fail(
            "AUDIT_INCOMPLETE",
            "an audit must carry exactly one sorted verdict per auditor",
            {"auditors": auditors},
        )
    ceilings = _mapping(value["auditor_ceilings"], "auditor_ceilings")
    if ceilings != {verdict["auditor"]: verdict["ceiling"] for verdict in verdicts}:
        _fail(
            "CEILING_MISMATCH",
            "the recorded auditor ceilings differ from the verdicts",
        )
    derived, veto = combined_ceiling(repository_root, verdicts)
    if value["combined_ceiling"] != derived:
        _fail(
            "CEILING_MISMATCH",
            "the combined ceiling is not the one the verdicts derive",
            {"derived": derived, "recorded": value["combined_ceiling"]},
        )
    if _mapping(value["veto"], "veto") != veto:
        _fail("VETO_MISMATCH", "the recorded veto state differs from the verdicts")
    if ladder_rank(repository_root, str(value["declared_ceiling"])) > ladder_rank(
        repository_root, derived
    ):
        _fail(
            "CEILING_OVERCLAIM",
            "the declared ceiling exceeds the derived one",
            {"declared": value["declared_ceiling"], "derived": derived},
        )
    stratification = _mapping(value["stratification"], "stratification")
    if stratification["pooled"] is not False:
        _fail(
            "METHOD_POOLED",
            "a sealed audit may not record pooled method evidence",
        )
    method = next(
        verdict for verdict in verdicts if verdict["auditor"] == Auditor.METHOD.value
    )
    if (
        _mapping(stratification["strata"], "strata") != method["stratum_ceilings"]
        or stratification["stratum_count"] != len(method["stratum_ceilings"])
        or stratification["strongest_stratum_ceiling"] != method["ceiling"]
    ):
        _fail(
            "STRATIFICATION_MISMATCH",
            "the recorded stratification differs from the method verdict",
        )
    if _hash_excluding(value, "audit_hash") != value["audit_hash"]:
        _fail("AUDIT_HASH_MISMATCH", "audit_hash does not match its content")
    derived_audit_id = _derive_audit_id(
        derived, created_at, run_id, subject_id, verdicts
    )
    if value["audit_id"] != derived_audit_id:
        _fail(
            "INPUT_INVALID",
            "audit_id does not match the audit's derived identity",
            {"derived": derived_audit_id, "recorded": value["audit_id"]},
        )
    return SealedArtifact("ParliamentAudit", _canonical_json(value))
