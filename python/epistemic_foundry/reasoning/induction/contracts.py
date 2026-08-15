"""R01 deterministic inductive synthesis and heterogeneity contracts.

The engine synthesizes direction, heterogeneity, dependency structure, and
moderators over an already-assembled EvidencePack.  It never retrieves, never
invents evidence, and never promotes an association to a causal claim: causal
identification belongs to R04 and is reported here as ``NOT_ASSESSED``.

Two properties are load-bearing and are enforced structurally rather than by
convention.

Independence adjustment.  Every finding carries the independence weight of its
O03 dependency cluster (``support_count_adjusted / support_count_raw``), so
members of one cluster can never be counted as that many independent votes.
The recomputed effective independent count is cross-checked against the pack's
own declared value and a mismatch fails closed.  The same weights enter the
inverse-variance statistics, so dependent findings cannot inflate precision.

Moderator and null retention.  Every moderator name and level observed in the
input survives into the output, candidate or not, and every null finding the
pack declares must be present and counted.  Dropping either fails closed.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Final

from epistemic_foundry.retrieval.evidence_pack.contracts import (
    EVIDENCE_BEARING_ROLES,
    PACK_ROLES,
    validate_evidence_dependency_cluster,
)

SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
RFC3339_PATTERN: Final = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})[Tt]"
    r"(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.[0-9]+)?(?P<zone>[Zz]|(?P<offset_sign>[+-])"
    r"(?P<offset_hour>[0-9]{2}):(?P<offset_minute>[0-9]{2}))$"
)


class Direction(str, Enum):
    """Canonical claim direction vocabulary (schemas/claim-card.schema.json)."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NULL = "null"
    NONMONOTONIC = "nonmonotonic"
    MIXED = "mixed"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class Heterogeneity(str, Enum):
    """Cochrane I-squared bands, plus an explicit undetermined state."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    SUBSTANTIAL = "SUBSTANTIAL"
    CONSIDERABLE = "CONSIDERABLE"
    UNDETERMINED = "UNDETERMINED"


class SynthesisStatus(str, Enum):
    """Whether the synthesis may be read as a complete inductive summary."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class ModeratorStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    NOT_DISCRIMINATING = "NOT_DISCRIMINATING"
    UNDERDETERMINED = "UNDERDETERMINED"


#: Causal identification is out of scope for R01 by construction.
CAUSAL_IDENTIFICATION: Final = "NOT_ASSESSED"
#: R01 may only ever describe association strength, never causation.
RELATION_KIND: Final = "ASSOCIATION"

DIRECTION_ORDER: Final = tuple(entry.value for entry in Direction)
#: Directions that assert an effect the synthesis can weigh against each other.
CONTENTFUL_DIRECTIONS: Final = (
    Direction.POSITIVE.value,
    Direction.NEGATIVE.value,
    Direction.NULL.value,
    Direction.NONMONOTONIC.value,
)
#: Directions that carry no positional claim and are counted but never win.
NON_CONTENTFUL_DIRECTIONS: Final = (
    Direction.MIXED.value,
    Direction.NOT_APPLICABLE.value,
    Direction.UNKNOWN.value,
)

#: Upper bounds of the Cochrane I-squared bands.
HETEROGENEITY_BANDS: Final = (
    (0.25, Heterogeneity.LOW.value),
    (0.50, Heterogeneity.MODERATE.value),
    (0.75, Heterogeneity.SUBSTANTIAL.value),
)
#: Fewer quantitative findings than this cannot yield a heterogeneity estimate.
MINIMUM_QUANTITATIVE_FINDINGS: Final = 2

COMPLETENESS_FIELDS: Final = frozenset(
    {
        "support_lane_complete",
        "counter_lane_complete",
        "null_lane_complete",
        "boundary_lane_complete",
        "method_lane_complete",
        "novelty_lane_complete",
    }
)

FINDING_FIELDS: Final = frozenset(
    {
        "evidence_id",
        "direction",
        "effect_size",
        "standard_error",
        "sample_size",
        "moderator_levels",
        "scope_id",
        "provenance_ref",
    }
)
SYNTHESIS_FIELDS: Final = frozenset(
    {
        "synthesis_id",
        "insight_id",
        "pack_id",
        "corpus_snapshot_hash",
        "created_at",
        "status",
        "relation_kind",
        "causal_identification",
        "direction_summary",
        "dominant_direction",
        "direction_agreement",
        "heterogeneity",
        "moderators",
        "null_evidence_ids",
        "counter_evidence_ids",
        "boundary_evidence_ids",
        "independence",
        "unsearched_scopes",
        "completeness",
        "stale",
        "degradation_reasons",
        "synthesis_hash",
    }
)
_MODERATOR_FIELDS: Final = frozenset(
    {"moderator", "status", "levels", "distinct_dominant_direction_count"}
)
_LEVEL_FIELDS: Final = frozenset(
    {
        "level",
        "evidence_ids",
        "adjusted_weight",
        "dominant_direction",
        "direction_summary",
    }
)
_INDEPENDENCE_FIELDS: Final = frozenset(
    {
        "adjusted_finding_weight",
        "clustered_evidence_count",
        "effective_independent_count",
        "raw_finding_count",
    }
)
_DIRECTION_SUMMARY_FIELDS: Final = frozenset({"adjusted_weight", "raw_count"})
_ROLE_FIELD: Final = MappingProxyType({role: f"{role}_ids" for role in PACK_ROLES})


class InductiveSynthesisError(ValueError):
    """Typed fail-closed R01 contract error."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context) if context is not None else {}


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    raise InductiveSynthesisError(code, message, context)


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
    result = {}
    for key, entry in value.items():  # type: ignore[union-attr]
        if not isinstance(key, str):
            _fail("INPUT_INVALID", f"{label} keys must be strings")
        result[key] = entry
    return result


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


def _hash(value: object, label: str) -> str:
    text = _text(value, label)
    if SHA256_PATTERN.fullmatch(text) is None:
        _fail("INPUT_INVALID", f"{label} must be a sha256 digest")
    return text


def _timestamp(value: object, label: str) -> str:
    text = _text(value, label)
    match = RFC3339_PATTERN.fullmatch(text)
    if match is None:
        _fail("INPUT_INVALID", f"{label} must be an RFC3339 timestamp")
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second"))
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
    if match.group("zone") not in {"Z", "z"}:
        offset_hour = int(match.group("offset_hour"))
        offset_minute = int(match.group("offset_minute"))
        if offset_hour > 23 or offset_minute > 59:
            _fail("INPUT_INVALID", f"{label} must be a real RFC3339 timestamp")
        offset_minutes = offset_hour * 60 + offset_minute
        if match.group("offset_sign") == "-":
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


def _number(value: object, label: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        _fail("INPUT_INVALID", f"{label} must be a number")
    result = float(value)  # type: ignore[arg-type]
    if not math.isfinite(result):
        _fail("INPUT_INVALID", f"{label} must be finite")
    return result


def _round(value: float) -> float:
    """Fixed precision so identical inputs seal byte-identical artifacts."""

    return round(value + 0.0, 10)


def _direction(value: object, label: str) -> str:
    text = _text(value, label)
    if text not in DIRECTION_ORDER:
        _fail(
            "DIRECTION_INVALID",
            f"{label} must be a canonical claim direction",
            {"allowed": list(DIRECTION_ORDER), "value": text},
        )
    return text


def _validate_finding(value: object, index: int) -> dict[str, Any]:
    finding = _mapping(value, f"finding[{index}]")
    _exact_fields(finding, FINDING_FIELDS, f"finding[{index}]")
    evidence_id = _text(finding["evidence_id"], "evidence_id")
    direction = _direction(finding["direction"], "direction")
    effect_size = finding["effect_size"]
    standard_error = finding["standard_error"]
    if effect_size is not None:
        effect_size = _number(effect_size, "effect_size")
        if standard_error is None:
            _fail(
                "QUANTITATIVE_INCONSISTENT",
                "an effect size without a standard error cannot be weighted",
                {"evidence_id": evidence_id},
            )
    if standard_error is not None:
        standard_error = _number(standard_error, "standard_error")
        if standard_error <= 0.0:
            _fail(
                "QUANTITATIVE_INCONSISTENT",
                "standard_error must be strictly positive",
                {"evidence_id": evidence_id},
            )
        if effect_size is None:
            _fail(
                "QUANTITATIVE_INCONSISTENT",
                "a standard error without an effect size describes nothing",
                {"evidence_id": evidence_id},
            )
    sample_size = finding["sample_size"]
    if sample_size is not None:
        if type(sample_size) is not int or sample_size < 1:
            _fail(
                "INPUT_INVALID",
                "sample_size must be an integer >= 1 or null",
                {"evidence_id": evidence_id},
            )
    levels = _mapping(finding["moderator_levels"], "moderator_levels")
    normalized_levels: dict[str, str] = {}
    for moderator, level in sorted(levels.items()):
        normalized_levels[_text(moderator, "moderator name")] = _text(
            level, f"moderator level for {moderator}"
        )
    return {
        "direction": direction,
        "effect_size": effect_size,
        "evidence_id": evidence_id,
        "moderator_levels": normalized_levels,
        "provenance_ref": _text(finding["provenance_ref"], "provenance_ref"),
        "sample_size": sample_size,
        "scope_id": _text(finding["scope_id"], "scope_id"),
        "standard_error": standard_error,
    }


def _pack_roles(pack: Mapping[str, Any]) -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {}
    for role in PACK_ROLES:
        field = _ROLE_FIELD[role]
        ids = pack.get(field)
        if not isinstance(ids, Sequence) or isinstance(
            ids, (str, bytes, bytearray)
        ):
            _fail("PACK_INVALID", f"EvidencePack.{field} must be an array")
        roles[role] = [_text(entry, field) for entry in ids]  # type: ignore[union-attr]
    return roles


def _pack_status_inputs(
    pack: Mapping[str, Any],
) -> tuple[dict[str, bool], bool, list[str]]:
    completeness = _mapping(pack.get("completeness"), "completeness")
    _exact_fields(completeness, COMPLETENESS_FIELDS, "completeness")
    normalized_completeness: dict[str, bool] = {}
    for field in sorted(COMPLETENESS_FIELDS):
        value = completeness[field]
        if type(value) is not bool:
            _fail(
                "PACK_INVALID",
                f"EvidencePack.completeness.{field} must be a boolean",
            )
        normalized_completeness[field] = value

    stale = pack.get("stale")
    if type(stale) is not bool:
        _fail("PACK_INVALID", "EvidencePack.stale must be a boolean")

    unsearched = pack.get("unsearched_scopes")
    if not isinstance(unsearched, Sequence) or isinstance(
        unsearched, (str, bytes, bytearray)
    ):
        _fail("PACK_INVALID", "EvidencePack.unsearched_scopes must be an array")
    normalized_unsearched: list[str] = []
    for entry in unsearched:
        if not isinstance(entry, str):
            _fail(
                "PACK_INVALID",
                "EvidencePack.unsearched_scopes entries must be strings",
            )
        normalized_unsearched.append(entry)
    return normalized_completeness, stale, normalized_unsearched


def independence_weights(
    pack: Mapping[str, Any],
    clusters: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    """Per-evidence independence weight derived from the O03 clusters.

    A cluster of ``k`` members whose adjusted support is ``a`` gives each member
    ``a / k``, so the cluster contributes exactly ``a`` independent units rather
    than ``k``.  Evidence in no cluster is a singleton and weighs 1.
    """

    declared = pack.get("dependency_clusters")
    if not isinstance(declared, Sequence) or isinstance(
        declared, (str, bytes, bytearray)
    ):
        _fail("PACK_INVALID", "EvidencePack.dependency_clusters must be an array")
    declared_membership: list[tuple[str, ...]] = []
    for index, group in enumerate(declared):  # type: ignore[union-attr]
        if not isinstance(group, Sequence) or isinstance(
            group, (str, bytes, bytearray)
        ):
            _fail(
                "PACK_INVALID",
                f"EvidencePack.dependency_clusters[{index}] must be an array",
            )
        members = tuple(
            sorted(_text(entry, "dependency cluster member") for entry in group)
        )
        if not members:
            _fail(
                "PACK_INVALID",
                f"EvidencePack.dependency_clusters[{index}] must not be empty",
            )
        declared_membership.append(members)
    declared_membership.sort()
    weights: dict[str, float] = {}
    cluster_membership: list[tuple[str, ...]] = []
    for index, cluster in enumerate(clusters):
        payload = validate_evidence_dependency_cluster(
            _mapping(cluster, f"cluster[{index}]")
        ).payload
        members = [str(entry) for entry in payload["evidence_ids"]]  # type: ignore[union-attr]
        cluster_membership.append(tuple(sorted(members)))
        raw = float(payload["support_count_raw"])  # type: ignore[arg-type]
        adjusted = float(payload["support_count_adjusted"])  # type: ignore[arg-type]
        if raw <= 0.0:
            _fail(
                "CLUSTER_INVALID",
                "a cluster must carry a positive raw support count",
                {"cluster_id": payload["cluster_id"]},
            )
        share = adjusted / raw
        for member in members:
            if member in weights:
                _fail(
                    "CLUSTER_INVALID",
                    "an evidence unit may belong to at most one cluster",
                    {"evidence_id": member},
                )
            weights[member] = share
    if sorted(cluster_membership) != declared_membership:
        _fail(
            "CLUSTER_MISMATCH",
            "the supplied clusters do not match the pack's declared membership",
        )
    return weights


def _effective_independent_count(
    roles: Mapping[str, Sequence[str]],
    weights: Mapping[str, float],
    clusters: Sequence[Mapping[str, Any]],
) -> float:
    """Recompute the pack's effective independent count from the clusters."""

    evidence_bearing: set[str] = set()
    for role in EVIDENCE_BEARING_ROLES:
        evidence_bearing.update(roles[role])
    clustered = set(weights)
    effective = 0.0
    for cluster in clusters:
        payload = _mapping(cluster, "cluster")
        members = [str(entry) for entry in payload["evidence_ids"]]  # type: ignore[union-attr]
        if any(member in evidence_bearing for member in members):
            effective += float(payload["support_count_adjusted"])  # type: ignore[arg-type]
    effective += sum(
        1.0 for evidence_id in sorted(evidence_bearing) if evidence_id not in clustered
    )
    return effective


def _direction_summary(
    findings: Sequence[Mapping[str, Any]],
    weights: Mapping[str, float],
) -> dict[str, dict[str, float]]:
    """Raw and independence-adjusted counts for every canonical direction."""

    summary = {
        direction: {"adjusted_weight": 0.0, "raw_count": 0.0}
        for direction in DIRECTION_ORDER
    }
    for finding in findings:
        entry = summary[str(finding["direction"])]
        entry["raw_count"] += 1.0
        entry["adjusted_weight"] += weights.get(str(finding["evidence_id"]), 1.0)
    return {
        direction: {
            "adjusted_weight": _round(entry["adjusted_weight"]),
            "raw_count": entry["raw_count"],
        }
        for direction, entry in summary.items()
    }


def _dominant_direction(
    summary: Mapping[str, Mapping[str, float]],
) -> tuple[str, float]:
    """The single best-supported contentful direction, or ``mixed`` on a tie.

    Only contentful directions can win.  ``mixed``, ``unknown``, and
    ``not_applicable`` are counted and reported but assert nothing, so they
    never become the synthesis verdict.
    """

    contentful = {
        direction: float(summary[direction]["adjusted_weight"])
        for direction in CONTENTFUL_DIRECTIONS
    }
    total = sum(
        float(summary[direction]["adjusted_weight"]) for direction in DIRECTION_ORDER
    )
    best = max(contentful.values(), default=0.0)
    if best <= 0.0:
        return Direction.UNKNOWN.value, 0.0
    winners = sorted(
        direction for direction, weight in contentful.items() if weight == best
    )
    agreement = _round(best / total) if total > 0.0 else 0.0
    if len(winners) > 1:
        return Direction.MIXED.value, agreement
    return winners[0], agreement


def heterogeneity_report(
    findings: Sequence[Mapping[str, Any]],
    weights: Mapping[str, float],
) -> dict[str, Any]:
    """Independence-weighted Cochran Q, I-squared, and DerSimonian-Laird tau².

    The inverse-variance weight of each finding is scaled by its independence
    weight, so a cluster of dependent replications cannot present itself as
    that many precise, independent measurements.  Fewer than two quantitative
    findings yields ``UNDETERMINED`` with a stated reason rather than a
    reassuring ``LOW``.
    """

    quantitative = [
        finding
        for finding in findings
        if finding["effect_size"] is not None and finding["standard_error"] is not None
    ]
    included = sorted(str(finding["evidence_id"]) for finding in quantitative)
    if len(quantitative) < MINIMUM_QUANTITATIVE_FINDINGS:
        return {
            "classification": Heterogeneity.UNDETERMINED.value,
            "degrees_of_freedom": max(len(quantitative) - 1, 0),
            "i_squared": None,
            "included_evidence_ids": included,
            "pooled_effect": None,
            "q_statistic": None,
            "quantitative_finding_count": len(quantitative),
            "reason": "fewer than two quantitative findings",
            "tau_squared": None,
        }
    entries = []
    for finding in quantitative:
        standard_error = float(finding["standard_error"])
        weight = weights.get(str(finding["evidence_id"]), 1.0) / (standard_error**2)
        if weight <= 0.0:
            return {
                "classification": Heterogeneity.UNDETERMINED.value,
                "degrees_of_freedom": len(quantitative) - 1,
                "i_squared": None,
                "included_evidence_ids": included,
                "pooled_effect": None,
                "q_statistic": None,
                "quantitative_finding_count": len(quantitative),
                "reason": "a finding carries no positive independence weight",
                "tau_squared": None,
            }
        entries.append((float(finding["effect_size"]), weight))
    total_weight = sum(weight for _, weight in entries)
    pooled = sum(effect * weight for effect, weight in entries) / total_weight
    q_statistic = sum(weight * (effect - pooled) ** 2 for effect, weight in entries)
    degrees_of_freedom = len(entries) - 1
    i_squared = (
        max(0.0, (q_statistic - degrees_of_freedom) / q_statistic)
        if q_statistic > 0.0
        else 0.0
    )
    sum_squares = sum(weight**2 for _, weight in entries)
    denominator = total_weight - (sum_squares / total_weight)
    tau_squared = (
        max(0.0, (q_statistic - degrees_of_freedom) / denominator)
        if denominator > 0.0
        else 0.0
    )
    classification = Heterogeneity.CONSIDERABLE.value
    for ceiling, band in HETEROGENEITY_BANDS:
        if i_squared < ceiling:
            classification = band
            break
    return {
        "classification": classification,
        "degrees_of_freedom": degrees_of_freedom,
        "i_squared": _round(i_squared),
        "included_evidence_ids": included,
        "pooled_effect": _round(pooled),
        "q_statistic": _round(q_statistic),
        "quantitative_finding_count": len(quantitative),
        "reason": None,
        "tau_squared": _round(tau_squared),
    }


def moderator_report(
    findings: Sequence[Mapping[str, Any]],
    weights: Mapping[str, float],
) -> list[dict[str, Any]]:
    """Every observed moderator and level, retained whether discriminating or not.

    Nothing is pruned: a moderator whose levels agree is reported as
    ``NOT_DISCRIMINATING`` rather than dropped, because its absence from the
    output would be indistinguishable from never having been examined.
    """

    observed: dict[str, dict[str, list[Mapping[str, Any]]]] = {}
    for finding in findings:
        for moderator, level in finding["moderator_levels"].items():
            observed.setdefault(moderator, {}).setdefault(level, []).append(finding)
    report: list[dict[str, Any]] = []
    for moderator in sorted(observed):
        levels = []
        dominants: set[str] = set()
        for level in sorted(observed[moderator]):
            stratum = observed[moderator][level]
            summary = _direction_summary(stratum, weights)
            dominant, _ = _dominant_direction(summary)
            dominants.add(dominant)
            levels.append(
                {
                    "adjusted_weight": _round(
                        sum(
                            weights.get(str(finding["evidence_id"]), 1.0)
                            for finding in stratum
                        )
                    ),
                    "direction_summary": summary,
                    "dominant_direction": dominant,
                    "evidence_ids": sorted(
                        str(finding["evidence_id"]) for finding in stratum
                    ),
                    "level": level,
                }
            )
        discriminating = {
            direction for direction in dominants if direction != Direction.UNKNOWN.value
        }
        if len(levels) < 2:
            status = ModeratorStatus.UNDERDETERMINED.value
        elif len(discriminating) > 1:
            status = ModeratorStatus.CANDIDATE.value
        else:
            status = ModeratorStatus.NOT_DISCRIMINATING.value
        report.append(
            {
                "distinct_dominant_direction_count": len(dominants),
                "levels": levels,
                "moderator": moderator,
                "status": status,
            }
        )
    return report


def _degradation_reasons(
    completeness: Mapping[str, bool],
    stale: bool,
    unsearched_scopes: Sequence[str],
    finding_count: int,
    heterogeneity: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if stale:
        reasons.append("pack_stale")
    for field in sorted(completeness):
        if completeness[field] is not True:
            reasons.append(f"incomplete:{field}")
    if unsearched_scopes:
        reasons.append("unsearched_scopes_present")
    if heterogeneity["classification"] == Heterogeneity.UNDETERMINED.value:
        reasons.append("heterogeneity_undetermined")
    if finding_count == 0:
        reasons.append("no_findings_supplied")
    return sorted(set(reasons))


def synthesize(
    pack: Mapping[str, Any],
    clusters: Sequence[Mapping[str, Any]],
    findings: Sequence[Mapping[str, Any]],
    *,
    created_at: str,
) -> SealedArtifact:
    """Seal a deterministic inductive synthesis over one EvidencePack."""

    pack_value = _mapping(pack, "EvidencePack")
    created_at = _timestamp(created_at, "created_at")
    pack_id = _text(pack_value.get("pack_id"), "pack_id")
    insight_id = _text(pack_value.get("insight_id"), "insight_id")
    corpus_snapshot_hash = _hash(
        pack_value.get("corpus_snapshot_hash"), "corpus_snapshot_hash"
    )
    completeness, stale, unsearched_scopes = _pack_status_inputs(pack_value)
    roles = _pack_roles(pack_value)
    weights = independence_weights(pack_value, clusters)

    recomputed = _effective_independent_count(roles, weights, clusters)
    declared_effective = _number(
        pack_value.get("effective_independent_count"), "effective_independent_count"
    )
    if _round(recomputed) != _round(declared_effective):
        _fail(
            "INDEPENDENCE_MISMATCH",
            "the recomputed effective independent count differs from the pack",
            {"declared": declared_effective, "recomputed": recomputed},
        )

    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    evidence_bearing: set[str] = set()
    for role in EVIDENCE_BEARING_ROLES:
        evidence_bearing.update(roles[role])
    for index, entry in enumerate(findings):
        finding = _validate_finding(entry, index)
        evidence_id = finding["evidence_id"]
        if evidence_id in seen:
            _fail(
                "DUPLICATE_FINDING",
                "each evidence unit may carry at most one finding",
                {"evidence_id": evidence_id},
            )
        if evidence_id not in evidence_bearing:
            _fail(
                "UNKNOWN_EVIDENCE",
                "a finding must reference evidence the pack carries in a bearing role",
                {"evidence_id": evidence_id},
            )
        seen.add(evidence_id)
        validated.append(finding)

    declared_nulls = sorted(set(roles["null"]))
    covered_nulls = sorted(seen & set(declared_nulls))
    if covered_nulls != declared_nulls:
        _fail(
            "NULL_EVIDENCE_DROPPED",
            "every null result the pack declares must carry a finding",
            {"missing": sorted(set(declared_nulls) - seen)},
        )

    summary = _direction_summary(validated, weights)
    dominant, agreement = _dominant_direction(summary)
    heterogeneity = heterogeneity_report(validated, weights)
    moderators = moderator_report(validated, weights)

    observed_moderators = sorted(
        {
            moderator
            for finding in validated
            for moderator in finding["moderator_levels"]
        }
    )
    if [entry["moderator"] for entry in moderators] != observed_moderators:
        _fail(
            "MODERATOR_DROPPED",
            "every observed moderator must be retained in the synthesis",
        )

    reasons = _degradation_reasons(
        completeness, stale, unsearched_scopes, len(validated), heterogeneity
    )
    if not validated:
        status = SynthesisStatus.INSUFFICIENT.value
    elif reasons:
        status = SynthesisStatus.PARTIAL.value
    else:
        status = SynthesisStatus.COMPLETE.value

    payload: dict[str, Any] = {
        "boundary_evidence_ids": sorted(set(roles["boundary"])),
        "causal_identification": CAUSAL_IDENTIFICATION,
        "completeness": completeness,
        "corpus_snapshot_hash": corpus_snapshot_hash,
        "counter_evidence_ids": sorted(set(roles["counter"])),
        "created_at": created_at,
        "degradation_reasons": reasons,
        "direction_agreement": agreement,
        "direction_summary": summary,
        "dominant_direction": dominant,
        "heterogeneity": heterogeneity,
        "independence": {
            "adjusted_finding_weight": _round(
                sum(weights.get(finding["evidence_id"], 1.0) for finding in validated)
            ),
            "clustered_evidence_count": len(weights),
            "effective_independent_count": _round(recomputed),
            "raw_finding_count": len(validated),
        },
        "insight_id": insight_id,
        "moderators": moderators,
        "null_evidence_ids": declared_nulls,
        "pack_id": pack_id,
        "relation_kind": RELATION_KIND,
        "stale": stale,
        "status": status,
        "unsearched_scopes": sorted(set(unsearched_scopes)),
    }
    payload["synthesis_id"] = _synthesis_id(payload)
    payload["synthesis_hash"] = _hash_excluding(payload, "synthesis_hash")
    return validate_synthesis(payload)


def _synthesis_id(payload: Mapping[str, Any]) -> str:
    """Content-addressed id over the conclusions the synthesis actually made."""

    return "IS-" + _hex_digest(
        {
            "created_at": payload["created_at"],
            "direction_summary": payload["direction_summary"],
            "heterogeneity": payload["heterogeneity"],
            "insight_id": payload["insight_id"],
            "moderators": payload["moderators"],
            "pack_id": payload["pack_id"],
        }
    )


def validate_synthesis(payload: Mapping[str, Any]) -> SealedArtifact:
    """Validate one synthesis record shape, vocabulary, and self-hash."""

    value = _mapping(payload, "InductiveSynthesis")
    _exact_fields(value, SYNTHESIS_FIELDS, "InductiveSynthesis")
    _text(value["synthesis_id"], "synthesis_id")
    _text(value["insight_id"], "insight_id")
    _text(value["pack_id"], "pack_id")
    _hash(value["corpus_snapshot_hash"], "corpus_snapshot_hash")
    _timestamp(value["created_at"], "created_at")
    if value["status"] not in tuple(entry.value for entry in SynthesisStatus):
        _fail("INPUT_INVALID", "status must be a canonical synthesis status")
    if value["relation_kind"] != RELATION_KIND:
        _fail(
            "CAUSAL_PROMOTION_FORBIDDEN",
            "R01 may only describe association; causal identification is R04",
            {"relation_kind": value["relation_kind"]},
        )
    if value["causal_identification"] != CAUSAL_IDENTIFICATION:
        _fail(
            "CAUSAL_PROMOTION_FORBIDDEN",
            "R01 must report causal identification as NOT_ASSESSED",
            {"causal_identification": value["causal_identification"]},
        )
    summary = _mapping(value["direction_summary"], "direction_summary")
    if sorted(summary) != sorted(DIRECTION_ORDER):
        _fail(
            "DIRECTION_INVALID",
            "direction_summary must cover every canonical direction exactly once",
        )
    summary_raw_count = 0
    summary_adjusted_weight = 0.0
    for direction in DIRECTION_ORDER:
        entry = _mapping(summary[direction], direction)
        _exact_fields(entry, _DIRECTION_SUMMARY_FIELDS, direction)
        raw_count = _number(entry["raw_count"], f"{direction}.raw_count")
        adjusted_weight = _number(
            entry["adjusted_weight"], f"{direction}.adjusted_weight"
        )
        if raw_count < 0.0 or not raw_count.is_integer():
            _fail(
                "INPUT_INVALID",
                f"{direction}.raw_count must be an integer-valued number >= 0",
            )
        if adjusted_weight < 0.0:
            _fail(
                "INPUT_INVALID",
                f"{direction}.adjusted_weight must be >= 0",
            )
        summary_raw_count += int(raw_count)
        summary_adjusted_weight += adjusted_weight
    _direction(value["dominant_direction"], "dominant_direction")
    if value["dominant_direction"] in NON_CONTENTFUL_DIRECTIONS:
        for direction in CONTENTFUL_DIRECTIONS:
            weight = _number(
                _mapping(summary[direction], direction)["adjusted_weight"], direction
            )
            if weight > 0.0 and value["dominant_direction"] != Direction.MIXED.value:
                _fail(
                    "DIRECTION_INVALID",
                    "a contentful direction carries weight but was not reported",
                )
    heterogeneity = _mapping(value["heterogeneity"], "heterogeneity")
    if heterogeneity["classification"] not in tuple(
        entry.value for entry in Heterogeneity
    ):
        _fail("INPUT_INVALID", "heterogeneity classification is not canonical")
    if (
        heterogeneity["classification"] == Heterogeneity.UNDETERMINED.value
        and heterogeneity["reason"] is None
    ):
        _fail(
            "HETEROGENEITY_UNEXPLAINED",
            "an undetermined heterogeneity estimate must state its reason",
        )
    completeness, stale, unsearched_scopes = _pack_status_inputs(value)
    if unsearched_scopes != sorted(set(unsearched_scopes)):
        _fail(
            "INPUT_INVALID",
            "unsearched_scopes must be unique and sorted ascending",
        )
    independence = _mapping(value["independence"], "independence")
    _exact_fields(independence, _INDEPENDENCE_FIELDS, "independence")
    raw_finding_count = independence["raw_finding_count"]
    clustered_evidence_count = independence["clustered_evidence_count"]
    if type(raw_finding_count) is not int or raw_finding_count < 0:
        _fail("INPUT_INVALID", "raw_finding_count must be an integer >= 0")
    if type(clustered_evidence_count) is not int or clustered_evidence_count < 0:
        _fail("INPUT_INVALID", "clustered_evidence_count must be an integer >= 0")
    for field in ("adjusted_finding_weight", "effective_independent_count"):
        if _number(independence[field], field) < 0.0:
            _fail("INPUT_INVALID", f"{field} must be >= 0")
    if raw_finding_count != summary_raw_count:
        _fail(
            "INDEPENDENCE_MISMATCH",
            "raw_finding_count differs from the direction summary",
            {"independence": raw_finding_count, "summary": summary_raw_count},
        )
    adjusted_finding_weight = _number(
        independence["adjusted_finding_weight"], "adjusted_finding_weight"
    )
    # Each direction and the aggregate are sealed after independent 10-place
    # rounding, so their reconstructed sum may differ by a few final-place ulps.
    if not math.isclose(
        adjusted_finding_weight,
        summary_adjusted_weight,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        _fail(
            "INDEPENDENCE_MISMATCH",
            "adjusted_finding_weight differs from the direction summary",
            {
                "independence": adjusted_finding_weight,
                "summary": _round(summary_adjusted_weight),
            },
        )
    degradation_reasons = value["degradation_reasons"]
    if not isinstance(degradation_reasons, Sequence) or isinstance(
        degradation_reasons, (str, bytes, bytearray)
    ):
        _fail("INPUT_INVALID", "degradation_reasons must be an array")
    recorded_reasons = [
        _text(entry, "degradation reason") for entry in degradation_reasons
    ]
    if recorded_reasons != sorted(set(recorded_reasons)):
        _fail(
            "INPUT_INVALID",
            "degradation_reasons must be unique and sorted ascending",
        )
    expected_reasons = _degradation_reasons(
        completeness,
        stale,
        unsearched_scopes,
        raw_finding_count,
        heterogeneity,
    )
    if recorded_reasons != expected_reasons:
        _fail(
            "DEGRADATION_MISMATCH",
            "degradation_reasons do not match the recorded synthesis inputs",
            {"actual": recorded_reasons, "expected": expected_reasons},
        )
    expected_status = (
        SynthesisStatus.INSUFFICIENT.value
        if raw_finding_count == 0
        else (
            SynthesisStatus.PARTIAL.value
            if expected_reasons
            else SynthesisStatus.COMPLETE.value
        )
    )
    if value["status"] != expected_status:
        _fail(
            "STATUS_MISMATCH",
            "synthesis status does not match its degradation state",
            {"actual": value["status"], "expected": expected_status},
        )
    moderators = value["moderators"]
    if not isinstance(moderators, Sequence) or isinstance(moderators, (str, bytes)):
        _fail("INPUT_INVALID", "moderators must be an array")
    names = []
    for index, entry in enumerate(moderators):  # type: ignore[arg-type]
        moderator = _mapping(entry, f"moderators[{index}]")
        _exact_fields(moderator, _MODERATOR_FIELDS, f"moderators[{index}]")
        names.append(_text(moderator["moderator"], "moderator"))
        if moderator["status"] not in tuple(entry.value for entry in ModeratorStatus):
            _fail("INPUT_INVALID", "moderator status is not canonical")
        levels = moderator["levels"]
        if not isinstance(levels, Sequence) or isinstance(levels, (str, bytes)):
            _fail("INPUT_INVALID", "moderator levels must be an array")
        if not levels:
            _fail(
                "MODERATOR_LEVEL_DROPPED",
                "a retained moderator must keep at least one level",
                {"moderator": moderator["moderator"]},
            )
        for level in levels:  # type: ignore[union-attr]
            _exact_fields(_mapping(level, "moderator level"), _LEVEL_FIELDS, "level")
    if names != sorted(names) or len(names) != len(set(names)):
        _fail("INPUT_INVALID", "moderators must be unique and sorted ascending")
    for field in ("null_evidence_ids", "counter_evidence_ids", "boundary_evidence_ids"):
        ids = value[field]
        if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
            _fail("INPUT_INVALID", f"{field} must be an array")
        listed = [_text(entry, field) for entry in ids]  # type: ignore[union-attr]
        if listed != sorted(listed) or len(listed) != len(set(listed)):
            _fail("INPUT_INVALID", f"{field} must be unique and sorted ascending")
    # Checked before the self-hash: rehashing a tampered record repairs the
    # hash but cannot repair an id derived from the conclusions themselves.
    if _synthesis_id(value) != value["synthesis_id"]:
        _fail(
            "SYNTHESIS_ID_MISMATCH",
            "synthesis_id is not the content address of the recorded conclusions",
        )
    if _hash_excluding(value, "synthesis_hash") != value["synthesis_hash"]:
        _fail("SYNTHESIS_HASH_MISMATCH", "synthesis_hash does not match its content")
    return SealedArtifact("InductiveSynthesis", _canonical_json(value))
