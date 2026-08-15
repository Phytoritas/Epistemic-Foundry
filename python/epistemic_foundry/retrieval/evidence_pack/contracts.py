"""O03 deterministic dependency-cluster and Evidence Pack assembly contracts.

The component does not retrieve and does not judge evidence strength.  It
resolves already-retrieved evidence units into typed dependency clusters so
shared samples, datasets, publication families, and derived analyses are never
counted as independent votes (EF4-I08), and it assembles a schema-exact
EvidencePack whose counter, null, boundary, and method lanes stay visible and
truthful (EF4-I06).  Every derived value is a pure function of validated
inputs; retrieval results can be excluded only through typed, visible reasons.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Final

from ..planning.contracts import (
    Lane,
    SearchState,
    validate_search_completeness_certificate,
)
from ..planning.contracts import SealedArtifact as PlanningSealedArtifact

SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
RFC3339_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)


class DependencyType(str, Enum):
    SAME_DATASET = "SAME_DATASET"
    SAME_EXPERIMENT = "SAME_EXPERIMENT"
    SAME_COHORT = "SAME_COHORT"
    PREPRINT_JOURNAL_VERSION = "PREPRINT_JOURNAL_VERSION"
    REVIEW_PRIMARY_CHAIN = "REVIEW_PRIMARY_CHAIN"
    SAME_TEAM_SERIES = "SAME_TEAM_SERIES"
    MODEL_OR_CODE_REUSE = "MODEL_OR_CODE_REUSE"
    CITATION_DEPENDENCY = "CITATION_DEPENDENCY"
    UNKNOWN = "UNKNOWN"


class PeerReviewStatus(str, Enum):
    PUBLISHED = "PUBLISHED"
    PREPRINT = "PREPRINT"
    REPORT = "REPORT"
    REVIEW = "REVIEW"


class UnresolvedReason(str, Enum):
    METADATA_ONLY = "METADATA_ONLY"
    GROUNDING_FAILED = "GROUNDING_FAILED"
    DUPLICATE_SUPERSEDED = "DUPLICATE_SUPERSEDED"
    LICENSE_RESTRICTED = "LICENSE_RESTRICTED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


DEPENDENCY_TYPE_ORDER: Final = tuple(entry.value for entry in DependencyType)
_TYPE_RANK: Final = {value: index for index, value in enumerate(DEPENDENCY_TYPE_ORDER)}

# Fixed default confidence that a detected dependency link truly removes
# statistical independence.  These are contract defaults for deterministic
# adjustment, not scientific claims about any particular corpus.
LINK_CONFIDENCE: Final = MappingProxyType(
    {
        DependencyType.SAME_DATASET.value: 0.95,
        DependencyType.SAME_EXPERIMENT.value: 0.95,
        DependencyType.SAME_COHORT.value: 0.9,
        DependencyType.PREPRINT_JOURNAL_VERSION.value: 0.95,
        DependencyType.REVIEW_PRIMARY_CHAIN.value: 0.9,
        DependencyType.SAME_TEAM_SERIES.value: 0.7,
        DependencyType.MODEL_OR_CODE_REUSE.value: 0.8,
        DependencyType.CITATION_DEPENDENCY.value: 0.6,
        DependencyType.UNKNOWN.value: 0.5,
    }
)

_PEER_REVIEW_RANK: Final = MappingProxyType(
    {
        PeerReviewStatus.PUBLISHED.value: 0,
        PeerReviewStatus.PREPRINT.value: 1,
        PeerReviewStatus.REPORT.value: 2,
        PeerReviewStatus.REVIEW.value: 3,
    }
)

EVIDENCE_UNIT_FIELDS: Final = frozenset(
    {
        "evidence_id",
        "source_span_id",
        "canonical_source_key",
        "source_version",
        "peer_review_status",
        "publication_family_id",
        "team_series_id",
        "dataset_ids",
        "cohort_ids",
        "experiment_ids",
        "reused_artifact_ids",
        "review_of_evidence_ids",
        "derived_from_evidence_ids",
        "origin_result_ids",
        "provenance_refs",
    }
)

_DECLARED_LINK_FIELDS: Final = frozenset(
    {"source_evidence_id", "target_evidence_id", "dependency_type", "provenance_ref"}
)

_UNRESOLVED_FIELDS: Final = frozenset({"result_id", "reason"})

CLUSTER_FIELDS: Final = frozenset(
    {
        "cluster_id",
        "run_id",
        "evidence_ids",
        "dependency_types",
        "representative_evidence_ids",
        "independent_unit_count",
        "independence_confidence",
        "rationale",
        "support_count_raw",
        "support_count_adjusted",
        "provenance_refs",
        "created_at",
        "cluster_hash",
    }
)

PACK_FIELDS: Final = frozenset(
    {
        "pack_id",
        "insight_id",
        "corpus_snapshot_hash",
        "supporting_ids",
        "counter_ids",
        "null_ids",
        "boundary_ids",
        "method_ids",
        "alternative_ids",
        "dependency_clusters",
        "unsearched_scopes",
        "retrieval_manifest_id",
        "completeness",
        "retrieval_run_id",
        "search_lane_receipt_ids",
        "effective_independent_count",
        "bias_risk_register_id",
        "role_quota_report",
        "completeness_certificate_hash",
        "stale",
    }
)

_COMPLETENESS_FIELDS: Final = frozenset(
    {
        "support_lane_complete",
        "counter_lane_complete",
        "null_lane_complete",
        "boundary_lane_complete",
        "method_lane_complete",
        "novelty_lane_complete",
    }
)

PACK_ROLES: Final = (
    "supporting",
    "counter",
    "null",
    "boundary",
    "method",
    "alternative",
)
EVIDENCE_BEARING_ROLES: Final = ("supporting", "counter", "null", "boundary", "method")
_ROLE_FIELD: Final = MappingProxyType({role: f"{role}_ids" for role in PACK_ROLES})

SUPPORT_GROUP_LANES: Final = (
    Lane.LEXICAL.value,
    Lane.SEMANTIC.value,
    Lane.CITATION.value,
    Lane.ENTITY_VARIABLE.value,
    Lane.MECHANISM.value,
    Lane.TEMPORAL.value,
)
_COMPLETED_STATES: Final = frozenset(
    {SearchState.SEARCHED_NONE.value, SearchState.SEARCHED_WITH_RESULTS.value}
)


class EvidencePackContractError(ValueError):
    """Typed fail-closed O03 contract error."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.run_status = "FAIL"
        self.details = MappingProxyType(dict(details)) if details is not None else None


def _fail(
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> None:
    raise EvidencePackContractError(code, message, details)


@dataclass(frozen=True, slots=True)
class SealedArtifact:
    """Immutable canonical JSON snapshot with a fresh projection on access."""

    artifact_type: str
    _canonical_bytes: bytes

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    @property
    def payload(self) -> dict[str, object]:
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
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise EvidencePackContractError(
            "CANONICAL_JSON_INVALID",
            "value must be finite canonical UTF-8 JSON",
        ) from error


def _json_snapshot(
    value: object,
    label: str,
    memo: dict[int, object],
    active: set[int],
) -> object:
    """Detach one composite caller input through base JSON primitives."""

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return str.__str__(value)
    if isinstance(value, int):
        if type(value) is not int:
            _fail("INPUT_INVALID", f"{label} contains a numeric subclass")
        return value
    if isinstance(value, float):
        if type(value) is not float:
            _fail("INPUT_INVALID", f"{label} contains a numeric subclass")
        number = value
        if not (number == number and abs(number) != float("inf")):
            _fail("INPUT_INVALID", f"{label} contains a non-finite number")
        return number
    if isinstance(value, (bytes, bytearray, memoryview)):
        _fail("INPUT_INVALID", f"{label} contains a byte-like value")
    identity = id(value)
    if identity in active:
        _fail("INPUT_INVALID", f"{label} contains a cycle")
    if identity in memo:
        return memo[identity]
    if isinstance(value, (SealedArtifact, PlanningSealedArtifact)):
        active.add(identity)
        try:
            detached = _json_snapshot(value.payload, label, memo, active)
        finally:
            active.remove(identity)
        memo[identity] = detached
        return detached
    if isinstance(value, Mapping):
        detached_mapping: dict[str, object] = {}
        memo[identity] = detached_mapping
        active.add(identity)
        try:
            for key, entry in value.items():
                if not isinstance(key, str):
                    _fail("INPUT_INVALID", f"{label} keys must be strings")
                plain_key = str.__str__(key)
                if plain_key in detached_mapping:
                    _fail("INPUT_INVALID", f"{label} keys must be unique")
                detached_mapping[plain_key] = _json_snapshot(
                    entry,
                    f"{label}.{plain_key}",
                    memo,
                    active,
                )
        finally:
            active.remove(identity)
        return detached_mapping
    if isinstance(value, Sequence):
        detached_sequence: list[object] = []
        memo[identity] = detached_sequence
        active.add(identity)
        try:
            for index, entry in enumerate(value):
                detached_sequence.append(
                    _json_snapshot(entry, f"{label}[{index}]", memo, active)
                )
        finally:
            active.remove(identity)
        return detached_sequence
    _fail("INPUT_INVALID", f"{label} contains a non-JSON value")


def _snapshot_composite(
    values: Mapping[str, object], label: str
) -> dict[str, object]:
    detached = _json_snapshot(values, label, {}, set())
    if type(detached) is not dict:  # pragma: no cover - internal root invariant
        raise AssertionError("composite snapshot root is not an object")
    _canonical_json(detached)
    return detached


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _digest(value: object) -> str:
    return _digest_bytes(_canonical_json(value))


def _hex_digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _hash_excluding(payload: Mapping[str, object], field: str) -> str:
    return _digest({key: value for key, value in payload.items() if key != field})


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be an object")
    result: dict[str, object] = {}
    for key, entry in value.items():
        if type(key) is not str or not key or "\x00" in key:
            _fail("INPUT_INVALID", f"{label} keys must be non-empty strings")
        result[key] = entry
    _canonical_json(result)
    return result


def _exact_fields(
    payload: Mapping[str, object], expected: frozenset[str], label: str
) -> None:
    missing = sorted(expected - set(payload))
    unknown = sorted(set(payload) - expected)
    if missing or unknown:
        _fail(
            "FIELD_SET_INVALID",
            f"{label} field set is not canonical",
            {"missing": missing, "unknown": unknown},
        )


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value.strip() or "\x00" in value:
        _fail("INPUT_INVALID", f"{label} must be a non-empty NUL-free string")
    return value


def _nullable_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _hash(value: object, label: str) -> str:
    if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
        _fail("HASH_FORMAT_INVALID", f"{label} must be sha256:<64 lowercase hex>")
    return value


def _timestamp(value: object, label: str) -> str:
    if type(value) is not str or RFC3339_PATTERN.fullmatch(value) is None:
        _fail("TIMESTAMP_INVALID", f"{label} must be RFC 3339 with an explicit offset")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidencePackContractError(
            "TIMESTAMP_INVALID", f"{label} is not a real timestamp"
        ) from error
    return value


def _strings(value: object, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail("INPUT_INVALID", f"{label} must be an array")
    result = [_text(entry, f"{label}[]") for entry in value]
    if not allow_empty and not result:
        _fail("INPUT_INVALID", f"{label} must not be empty")
    if len(result) != len(set(result)):
        _fail("DUPLICATE_VALUE", f"{label} must not contain duplicates")
    return result


def _bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        _fail("INPUT_INVALID", f"{label} must be a boolean")
    return value


def _dependency_type(value: object, label: str) -> str:
    if type(value) is not str:
        _fail("DEPENDENCY_TYPE_UNKNOWN", f"{label} must be a canonical dependency type")
    try:
        return DependencyType(value).value
    except ValueError as error:
        raise EvidencePackContractError(
            "DEPENDENCY_TYPE_UNKNOWN", f"{value!r} is not a canonical dependency type"
        ) from error


def _peer_review_status(value: object, label: str) -> str:
    if type(value) is not str:
        _fail("PEER_REVIEW_STATUS_INVALID", f"{label} must be a canonical status")
    try:
        return PeerReviewStatus(value).value
    except ValueError as error:
        raise EvidencePackContractError(
            "PEER_REVIEW_STATUS_INVALID",
            f"{value!r} is not a canonical peer-review status",
        ) from error


def _sealed(artifact_type: str, payload: Mapping[str, object]) -> SealedArtifact:
    return SealedArtifact(artifact_type, _canonical_json(dict(payload)))


def _artifact_payload(
    value: Mapping[str, object] | SealedArtifact | PlanningSealedArtifact, label: str
) -> dict[str, object]:
    if isinstance(value, (SealedArtifact, PlanningSealedArtifact)):
        return value.payload
    return _mapping(value, label)


# ---------------------------------------------------------------------------
# Evidence units
# ---------------------------------------------------------------------------


def _validate_unit(value: object, index: int) -> dict[str, object]:
    unit = _mapping(value, f"units[{index}]")
    _exact_fields(unit, EVIDENCE_UNIT_FIELDS, f"units[{index}]")
    result: dict[str, object] = {
        "evidence_id": _text(unit["evidence_id"], "evidence_id"),
        "source_span_id": _nullable_text(unit["source_span_id"], "source_span_id"),
        "canonical_source_key": _text(
            unit["canonical_source_key"], "canonical_source_key"
        ),
        "source_version": _text(unit["source_version"], "source_version"),
        "peer_review_status": _peer_review_status(
            unit["peer_review_status"], "peer_review_status"
        ),
        "publication_family_id": _nullable_text(
            unit["publication_family_id"], "publication_family_id"
        ),
        "team_series_id": _nullable_text(unit["team_series_id"], "team_series_id"),
        "dataset_ids": _strings(unit["dataset_ids"], "dataset_ids"),
        "cohort_ids": _strings(unit["cohort_ids"], "cohort_ids"),
        "experiment_ids": _strings(unit["experiment_ids"], "experiment_ids"),
        "reused_artifact_ids": _strings(
            unit["reused_artifact_ids"], "reused_artifact_ids"
        ),
        "review_of_evidence_ids": _strings(
            unit["review_of_evidence_ids"], "review_of_evidence_ids"
        ),
        "derived_from_evidence_ids": _strings(
            unit["derived_from_evidence_ids"], "derived_from_evidence_ids"
        ),
        "origin_result_ids": _strings(
            unit["origin_result_ids"], "origin_result_ids", allow_empty=False
        ),
        "provenance_refs": _strings(
            unit["provenance_refs"], "provenance_refs", allow_empty=False
        ),
    }
    return result


def _validate_units(units: object) -> dict[str, dict[str, object]]:
    if not isinstance(units, Sequence) or isinstance(units, (str, bytes, bytearray)):
        _fail("INPUT_INVALID", "units must be an array")
    by_id: dict[str, dict[str, object]] = {}
    for index, value in enumerate(units):
        unit = _validate_unit(value, index)
        evidence_id = str(unit["evidence_id"])
        if evidence_id in by_id:
            _fail("EVIDENCE_ID_DUPLICATE", f"duplicate evidence_id {evidence_id}")
        by_id[evidence_id] = unit
    return by_id


# ---------------------------------------------------------------------------
# Dependency clusters
# ---------------------------------------------------------------------------


def _validate_declared_links(
    declared_links: object,
    units: Mapping[str, Mapping[str, object]],
) -> list[tuple[str, str, str, str]]:
    if not isinstance(declared_links, Sequence) or isinstance(
        declared_links, (str, bytes, bytearray)
    ):
        _fail("INPUT_INVALID", "declared_links must be an array")
    edges: list[tuple[str, str, str, str]] = []
    for index, value in enumerate(declared_links):
        link = _mapping(value, f"declared_links[{index}]")
        _exact_fields(link, _DECLARED_LINK_FIELDS, f"declared_links[{index}]")
        source = _text(link["source_evidence_id"], "source_evidence_id")
        target = _text(link["target_evidence_id"], "target_evidence_id")
        dependency = _dependency_type(link["dependency_type"], "dependency_type")
        provenance = _text(link["provenance_ref"], "provenance_ref")
        if source == target:
            _fail(
                "LINK_SELF_REFERENCE", "declared link cannot connect an item to itself"
            )
        for endpoint in (source, target):
            if endpoint not in units:
                _fail(
                    "LINK_TARGET_UNKNOWN",
                    f"declared link references unknown evidence {endpoint}",
                )
        edges.append((source, target, dependency, provenance))
    return edges


def _derived_edges(
    units: Mapping[str, Mapping[str, object]],
) -> list[tuple[str, str, str]]:
    edges: list[tuple[str, str, str]] = []
    group_specs = (
        ("dataset_ids", DependencyType.SAME_DATASET.value),
        ("experiment_ids", DependencyType.SAME_EXPERIMENT.value),
        ("cohort_ids", DependencyType.SAME_COHORT.value),
        ("reused_artifact_ids", DependencyType.MODEL_OR_CODE_REUSE.value),
    )
    for field, dependency in group_specs:
        groups: dict[str, list[str]] = {}
        for evidence_id in sorted(units):
            for key in units[evidence_id][field]:  # type: ignore[index]
                groups.setdefault(str(key), []).append(evidence_id)
        for members in groups.values():
            for left, right in zip(members, members[1:], strict=False):
                edges.append((left, right, dependency))
    scalar_specs = (
        ("publication_family_id", DependencyType.PREPRINT_JOURNAL_VERSION.value),
        ("team_series_id", DependencyType.SAME_TEAM_SERIES.value),
    )
    for field, dependency in scalar_specs:
        groups = {}
        for evidence_id in sorted(units):
            key = units[evidence_id][field]  # type: ignore[index]
            if key is not None:
                groups.setdefault(str(key), []).append(evidence_id)
        for members in groups.values():
            for left, right in zip(members, members[1:], strict=False):
                edges.append((left, right, dependency))
    reference_specs = (
        (
            "review_of_evidence_ids",
            DependencyType.REVIEW_PRIMARY_CHAIN.value,
            "REVIEW_TARGET_UNKNOWN",
        ),
        (
            "derived_from_evidence_ids",
            DependencyType.CITATION_DEPENDENCY.value,
            "CITATION_TARGET_UNKNOWN",
        ),
    )
    for field, dependency, error_code in reference_specs:
        for evidence_id in sorted(units):
            for target in units[evidence_id][field]:  # type: ignore[index]
                if str(target) == evidence_id:
                    _fail(
                        "LINK_SELF_REFERENCE",
                        f"{field} cannot reference its own record",
                    )
                if str(target) not in units:
                    _fail(
                        error_code,
                        f"{evidence_id} references unknown evidence {target}",
                    )
                edges.append((evidence_id, str(target), dependency))
    return edges


class _UnionFind:
    def __init__(self, keys: Sequence[str]) -> None:
        self._parent = {key: key for key in keys}

    def find(self, key: str) -> str:
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            first, second = sorted((left_root, right_root))
            self._parent[second] = first


def build_dependency_clusters(
    units: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    created_at: str,
    declared_links: Sequence[Mapping[str, object]] = (),
) -> tuple[SealedArtifact, ...]:
    """Deterministically cluster dependent evidence units (EF4-I08)."""

    snapshot = _snapshot_composite(
        {
            "created_at": created_at,
            "declared_links": declared_links,
            "run_id": run_id,
            "units": units,
        },
        "build_dependency_clusters",
    )
    return _build_dependency_clusters_from_snapshot(
        snapshot["units"],
        run_id=snapshot["run_id"],
        created_at=snapshot["created_at"],
        declared_links=snapshot["declared_links"],
    )


def _build_dependency_clusters_from_snapshot(
    units: object,
    *,
    run_id: object,
    created_at: object,
    declared_links: object,
) -> tuple[SealedArtifact, ...]:
    """Build clusters from an already detached composite snapshot."""

    run_id = _text(run_id, "run_id")
    created_at = _timestamp(created_at, "created_at")
    by_id = _validate_units(units)
    declared = _validate_declared_links(declared_links, by_id)
    edges = _derived_edges(by_id)
    edges.extend(
        (source, target, dependency) for source, target, dependency, _ in declared
    )

    finder = _UnionFind(sorted(by_id))
    for source, target, _ in edges:
        finder.union(source, target)

    members: dict[str, list[str]] = {}
    for evidence_id in sorted(by_id):
        members.setdefault(finder.find(evidence_id), []).append(evidence_id)
    component_types: dict[str, set[str]] = {root: set() for root in members}
    for source, _target, dependency in edges:
        component_types[finder.find(source)].add(dependency)

    link_provenance: dict[str, list[str]] = {}
    for source, _target, _dependency, provenance in declared:
        link_provenance.setdefault(finder.find(source), []).append(provenance)

    clusters: list[SealedArtifact] = []
    for root in sorted(members):
        evidence_ids = members[root]
        if len(evidence_ids) < 2:
            continue
        types = sorted(component_types[root], key=_TYPE_RANK.__getitem__)
        if not types:  # pragma: no cover - multi-member components always have edges
            raise AssertionError("multi-member component without dependency edges")
        representative = min(
            evidence_ids,
            key=lambda evidence_id: (
                _PEER_REVIEW_RANK[str(by_id[evidence_id]["peer_review_status"])],
                evidence_id,
            ),
        )
        provenance: set[str] = set(link_provenance.get(root, ()))
        for evidence_id in evidence_ids:
            provenance.update(by_id[evidence_id]["provenance_refs"])  # type: ignore[arg-type]
        confidence = min(LINK_CONFIDENCE[dependency] for dependency in types)
        payload: dict[str, object] = {
            "cluster_id": "EDC-"
            + _hex_digest({"run_id": run_id, "evidence_ids": evidence_ids}),
            "run_id": run_id,
            "evidence_ids": evidence_ids,
            "dependency_types": types,
            "representative_evidence_ids": [representative],
            "independent_unit_count": 1,
            "independence_confidence": confidence,
            "rationale": (
                f"{len(evidence_ids)} evidence records share "
                f"{', '.join(types)} dependencies and count as 1 independent unit."
            ),
            "support_count_raw": len(evidence_ids),
            "support_count_adjusted": 1.0,
            "provenance_refs": sorted(provenance),
            "created_at": created_at,
        }
        payload["cluster_hash"] = _hash_excluding(payload, "cluster_hash")
        clusters.append(_sealed("EvidenceDependencyCluster", payload))
    return tuple(clusters)


def validate_evidence_dependency_cluster_shape(
    payload: Mapping[str, object],
) -> SealedArtifact:
    """Validate structure and self-hash, not source-graph authority."""

    snapshot = _snapshot_composite(
        {"payload": payload}, "validate_evidence_dependency_cluster_shape"
    )
    return _validate_evidence_dependency_cluster_shape_from_snapshot(
        snapshot["payload"]
    )


def validate_evidence_dependency_cluster(
    payload: Mapping[str, object],
) -> SealedArtifact:
    """Compatibility shape check; it grants no independence authority."""

    snapshot = _snapshot_composite(
        {"payload": payload}, "validate_evidence_dependency_cluster"
    )
    return _validate_evidence_dependency_cluster_shape_from_snapshot(
        snapshot["payload"]
    )


def _validate_evidence_dependency_cluster_shape_from_snapshot(
    payload: object,
) -> SealedArtifact:
    """Validate one cluster already detached from caller-owned state."""

    value = _mapping(payload, "EvidenceDependencyCluster")
    _exact_fields(value, CLUSTER_FIELDS, "EvidenceDependencyCluster")
    _text(value["cluster_id"], "cluster_id")
    _text(value["run_id"], "run_id")
    evidence_ids = _strings(value["evidence_ids"], "evidence_ids", allow_empty=False)
    if evidence_ids != sorted(evidence_ids):
        _fail("EVIDENCE_ORDER_INVALID", "evidence_ids must be sorted ascending")
    types = value["dependency_types"]
    if (
        not isinstance(types, Sequence)
        or isinstance(types, (str, bytes, bytearray))
        or not types
    ):
        _fail("INPUT_INVALID", "dependency_types must be a non-empty array")
    canonical_types = [_dependency_type(entry, "dependency_types[]") for entry in types]
    if len(canonical_types) != len(set(canonical_types)):
        _fail("DUPLICATE_VALUE", "dependency_types must not contain duplicates")
    if canonical_types != sorted(canonical_types, key=_TYPE_RANK.__getitem__):
        _fail(
            "DEPENDENCY_TYPE_ORDER_INVALID", "dependency_types must use canonical order"
        )
    representatives = _strings(
        value["representative_evidence_ids"],
        "representative_evidence_ids",
        allow_empty=False,
    )
    if not set(representatives) <= set(evidence_ids):
        _fail("REPRESENTATIVE_NOT_MEMBER", "representatives must be cluster members")
    count = value["independent_unit_count"]
    if type(count) is not int or count < 1:
        _fail("INPUT_INVALID", "independent_unit_count must be an integer >= 1")
    if count > len(evidence_ids):
        _fail("INDEPENDENT_COUNT_INVALID", "independent units cannot exceed members")
    confidence = value["independence_confidence"]
    if type(confidence) not in (int, float) or isinstance(confidence, bool):
        _fail("INPUT_INVALID", "independence_confidence must be a number")
    if not 0.0 <= float(confidence) <= 1.0:
        _fail("INPUT_INVALID", "independence_confidence must be within [0, 1]")
    _text(value["rationale"], "rationale")
    raw = value["support_count_raw"]
    if type(raw) is not int or raw < 0:
        _fail("INPUT_INVALID", "support_count_raw must be an integer >= 0")
    adjusted = value["support_count_adjusted"]
    if (
        type(adjusted) not in (int, float)
        or isinstance(adjusted, bool)
        or float(adjusted) < 0.0
    ):
        _fail("INPUT_INVALID", "support_count_adjusted must be a number >= 0")
    if float(adjusted) > raw:
        _fail("ADJUSTED_COUNT_INVALID", "adjusted support cannot exceed the raw count")
    _strings(value["provenance_refs"], "provenance_refs", allow_empty=False)
    _timestamp(value["created_at"], "created_at")
    asserted = _hash(value["cluster_hash"], "cluster_hash")
    if asserted != _hash_excluding(value, "cluster_hash"):
        _fail("CLUSTER_HASH_MISMATCH", "cluster_hash does not match canonical content")
    return _sealed("EvidenceDependencyCluster", value)


def validate_evidence_dependency_clusters_from_sources(
    clusters: Sequence[Mapping[str, object]],
    *,
    units: Sequence[Mapping[str, object]],
    run_id: str,
    created_at: str,
    declared_links: Sequence[Mapping[str, object]] = (),
) -> tuple[SealedArtifact, ...]:
    """Rebuild the complete cluster set from sources and require exact identity."""

    snapshot = _snapshot_composite(
        {
            "clusters": clusters,
            "created_at": created_at,
            "declared_links": declared_links,
            "run_id": run_id,
            "units": units,
        },
        "validate_evidence_dependency_clusters_from_sources",
    )
    supplied = snapshot["clusters"]
    if not isinstance(supplied, Sequence) or isinstance(
        supplied, (str, bytes, bytearray)
    ):
        _fail("INPUT_INVALID", "clusters must be an array")
    asserted = tuple(
        _validate_evidence_dependency_cluster_shape_from_snapshot(entry)
        for entry in supplied
    )
    rebuilt = _build_dependency_clusters_from_snapshot(
        snapshot["units"],
        run_id=snapshot["run_id"],
        created_at=snapshot["created_at"],
        declared_links=snapshot["declared_links"],
    )
    if [entry.canonical_bytes for entry in asserted] != [
        entry.canonical_bytes for entry in rebuilt
    ]:
        _fail(
            "CLUSTER_RECONSTRUCTION_MISMATCH",
            "cluster records are not the deterministic assembly of their source inputs",
        )
    return rebuilt


# ---------------------------------------------------------------------------
# Evidence Pack assembly
# ---------------------------------------------------------------------------


def _validate_unresolved(
    unresolved_results: object,
) -> dict[str, str]:
    if not isinstance(unresolved_results, Sequence) or isinstance(
        unresolved_results, (str, bytes, bytearray)
    ):
        _fail("INPUT_INVALID", "unresolved_results must be an array")
    result: dict[str, str] = {}
    for index, value in enumerate(unresolved_results):
        entry = _mapping(value, f"unresolved_results[{index}]")
        _exact_fields(entry, _UNRESOLVED_FIELDS, f"unresolved_results[{index}]")
        result_id = _text(entry["result_id"], "result_id")
        reason = entry["reason"]
        if type(reason) is not str:
            _fail("UNRESOLVED_REASON_INVALID", "reason must be a typed string")
        try:
            reason_value = UnresolvedReason(reason).value
        except ValueError as error:
            raise EvidencePackContractError(
                "UNRESOLVED_REASON_INVALID",
                f"{reason!r} is not a typed unresolved reason",
            ) from error
        if result_id in result:
            _fail("DUPLICATE_VALUE", f"unresolved result {result_id} listed twice")
        result[result_id] = reason_value
    return result


def _validate_lane_assignments(
    lane_assignments: object,
    units: Mapping[str, Mapping[str, object]],
) -> dict[str, list[str]]:
    mapping = _mapping(lane_assignments, "lane_assignments")
    unknown = sorted(set(mapping) - set(PACK_ROLES))
    missing = sorted(set(PACK_ROLES) - set(mapping))
    if unknown or missing:
        _fail(
            "ROLE_SET_INVALID",
            "lane_assignments must cover exactly the six pack roles",
            {"missing": missing, "unknown": unknown},
        )
    assigned: dict[str, str] = {}
    result: dict[str, list[str]] = {}
    for role in PACK_ROLES:
        ids = sorted(_strings(mapping[role], f"lane_assignments.{role}"))
        for evidence_id in ids:
            if evidence_id not in units:
                _fail(
                    "EVIDENCE_UNKNOWN",
                    f"{role} references evidence {evidence_id} without a unit record",
                )
            if evidence_id in assigned:
                _fail(
                    "ROLE_ASSIGNMENT_CONFLICT",
                    f"evidence {evidence_id} is assigned to both {assigned[evidence_id]} and {role}",
                )
            assigned[evidence_id] = role
        result[role] = ids
    unaccounted = sorted(set(units) - set(assigned))
    if unaccounted:
        _fail(
            "EVIDENCE_UNACCOUNTED",
            "every evidence unit must hold exactly one pack role",
            {"unaccounted": unaccounted},
        )
    return result


def _reconciled_states(certificate: Mapping[str, object]) -> dict[str, str]:
    states: dict[str, str] = {}
    for row in certificate["lane_reconciliations"]:  # type: ignore[union-attr]
        states[str(row["lane"])] = str(row["reconciled_state"])  # type: ignore[index]
    return states


def _group_complete(
    lanes: Sequence[str],
    required: frozenset[str],
    states: Mapping[str, str],
) -> bool:
    selected = [lane for lane in lanes if lane in required]
    if not selected:
        return False
    return all(states[lane] in _COMPLETED_STATES for lane in selected)


def assemble_evidence_pack(
    units: Sequence[Mapping[str, object]],
    *,
    insight_id: str,
    corpus_snapshot_hash: str,
    retrieval_manifest_id: str,
    bias_risk_register_id: str,
    lane_assignments: Mapping[str, Sequence[str]],
    query_plan: Mapping[str, object] | SealedArtifact,
    receipts: Sequence[Mapping[str, object] | SealedArtifact],
    certificate: Mapping[str, object] | SealedArtifact,
    created_at: str,
    declared_links: Sequence[Mapping[str, object]] = (),
    unresolved_results: Sequence[Mapping[str, object]] = (),
    role_quotas: Mapping[str, int] | None = None,
    stale: bool = False,
) -> tuple[SealedArtifact, tuple[SealedArtifact, ...]]:
    """Assemble a schema-exact EvidencePack bound to its completeness certificate."""

    snapshot = _snapshot_composite(
        {
            "bias_risk_register_id": bias_risk_register_id,
            "certificate": certificate,
            "corpus_snapshot_hash": corpus_snapshot_hash,
            "created_at": created_at,
            "declared_links": declared_links,
            "insight_id": insight_id,
            "lane_assignments": lane_assignments,
            "query_plan": query_plan,
            "receipts": receipts,
            "retrieval_manifest_id": retrieval_manifest_id,
            "role_quotas": role_quotas,
            "stale": stale,
            "units": units,
            "unresolved_results": unresolved_results,
        },
        "assemble_evidence_pack",
    )
    units = snapshot["units"]  # type: ignore[assignment]
    insight_id = _text(snapshot["insight_id"], "insight_id")
    corpus_snapshot_hash = _hash(
        snapshot["corpus_snapshot_hash"], "corpus_snapshot_hash"
    )
    retrieval_manifest_id = _text(
        snapshot["retrieval_manifest_id"], "retrieval_manifest_id"
    )
    bias_risk_register_id = _text(
        snapshot["bias_risk_register_id"], "bias_risk_register_id"
    )
    lane_assignments = snapshot["lane_assignments"]  # type: ignore[assignment]
    query_plan = snapshot["query_plan"]  # type: ignore[assignment]
    receipts = snapshot["receipts"]  # type: ignore[assignment]
    certificate = snapshot["certificate"]  # type: ignore[assignment]
    created_at = snapshot["created_at"]  # type: ignore[assignment]
    declared_links = snapshot["declared_links"]  # type: ignore[assignment]
    unresolved_results = snapshot["unresolved_results"]  # type: ignore[assignment]
    role_quotas = snapshot["role_quotas"]  # type: ignore[assignment]
    stale = _bool(snapshot["stale"], "stale")

    certificate_value = _artifact_payload(certificate, "certificate")
    sealed_certificate = validate_search_completeness_certificate(
        query_plan, receipts, certificate_value
    )
    certificate_value = sealed_certificate.payload
    if str(certificate_value["subject_ref"]) != insight_id:
        _fail(
            "PACK_SUBJECT_MISMATCH",
            "certificate subject_ref must bind the pack insight_id",
        )
    run_id = str(certificate_value["run_id"])
    required = frozenset(str(lane) for lane in certificate_value["required_lanes"])  # type: ignore[union-attr]
    states = _reconciled_states(certificate_value)

    by_id = _validate_units(units)
    roles = _validate_lane_assignments(lane_assignments, by_id)
    unresolved = _validate_unresolved(unresolved_results)

    metadata_only = sorted(
        evidence_id
        for evidence_id, unit in by_id.items()
        if unit["source_span_id"] is None
    )
    if metadata_only:
        _fail(
            "METADATA_ONLY_EVIDENCE",
            "metadata-only candidates cannot enter an Evidence Pack lane",
            {"evidence_ids": metadata_only},
        )

    all_result_ids: set[str] = set()
    for receipt in receipts:
        value = _artifact_payload(receipt, "receipts[]")
        if value.get("receipt_kind") != "EXECUTION":
            continue
        snapshot = value.get("corpus_snapshot_hash")
        if snapshot is not None and snapshot != corpus_snapshot_hash:
            _fail(
                "STALE_RETRIEVAL_SNAPSHOT",
                "pack corpus snapshot differs from an execution receipt snapshot",
            )
        result_ids = value.get("result_ids")
        if isinstance(result_ids, Sequence) and not isinstance(
            result_ids, (str, bytes)
        ):
            all_result_ids.update(str(entry) for entry in result_ids)

    result_owners: dict[str, str] = {}
    for evidence_id in sorted(by_id):
        origin_result_ids = sorted(
            str(result_id)
            for result_id in by_id[evidence_id]["origin_result_ids"]  # type: ignore[union-attr]
        )
        for result_id in origin_result_ids:
            if result_id not in all_result_ids:
                _fail(
                    "EVIDENCE_NOT_RETRIEVED",
                    f"evidence {evidence_id} claims origin {result_id} outside the sealed run",
                )
        for result_id in origin_result_ids:
            existing_owner = result_owners.get(result_id)
            if existing_owner is not None and existing_owner != evidence_id:
                _fail(
                    "DUPLICATE_VALUE",
                    f"retrieval result {result_id} is claimed by multiple evidence units",
                    {
                        "result_id": result_id,
                        "evidence_ids": [existing_owner, evidence_id],
                    },
                )
            result_owners[result_id] = evidence_id

    resolved_result_ids = set(result_owners)

    conflicting = sorted(resolved_result_ids & set(unresolved))
    if conflicting:
        _fail(
            "UNRESOLVED_CONTRADICTION",
            "a resolved retrieval result cannot also be typed unresolved",
            {"result_ids": conflicting},
        )
    unknown_unresolved = sorted(set(unresolved) - all_result_ids)
    if unknown_unresolved:
        _fail(
            "UNRESOLVED_UNKNOWN_RESULT",
            "typed unresolved entries must reference sealed run results",
            {"result_ids": unknown_unresolved},
        )
    silently_dropped = sorted(all_result_ids - resolved_result_ids - set(unresolved))
    if silently_dropped:
        _fail(
            "RESULT_SILENTLY_DROPPED",
            "every retrieval result must resolve to evidence or a typed unresolved reason",
            {"result_ids": silently_dropped},
        )

    clusters = build_dependency_clusters(
        units,
        run_id=run_id,
        created_at=created_at,
        declared_links=declared_links,
    )
    cluster_payloads = [cluster.payload for cluster in clusters]
    cluster_membership = [list(payload["evidence_ids"]) for payload in cluster_payloads]  # type: ignore[arg-type]

    evidence_bearing: set[str] = set()
    for role in EVIDENCE_BEARING_ROLES:
        evidence_bearing.update(roles[role])
    clustered: set[str] = set()
    effective = 0.0
    for payload in cluster_payloads:
        member_ids = [str(entry) for entry in payload["evidence_ids"]]  # type: ignore[union-attr]
        clustered.update(member_ids)
        if any(member in evidence_bearing for member in member_ids):
            effective += float(payload["support_count_adjusted"])  # type: ignore[arg-type]
    effective += sum(
        1.0 for evidence_id in sorted(evidence_bearing) if evidence_id not in clustered
    )

    if role_quotas is None:
        quotas: dict[str, object] = {}
    elif type(role_quotas) is dict:
        quotas = _mapping(role_quotas, "role_quotas")
    else:
        _fail("INPUT_INVALID", "role_quotas must be null or an object")
    unknown_quota_roles = sorted(set(quotas) - set(PACK_ROLES))
    if unknown_quota_roles:
        _fail(
            "ROLE_SET_INVALID",
            "role_quotas may only target canonical pack roles",
            {"unknown": unknown_quota_roles},
        )
    role_quota_report: dict[str, dict[str, object]] = {}
    for role in PACK_ROLES:
        target = quotas.get(role, 0)
        if type(target) is not int or target < 0:
            _fail("INPUT_INVALID", f"role_quotas.{role} must be an integer >= 0")
        ids = roles[role]
        independent = sum(1.0 for evidence_id in ids if evidence_id not in clustered)
        independent += sum(
            float(payload["support_count_adjusted"])  # type: ignore[arg-type]
            for payload in cluster_payloads
            if any(str(entry) in ids for entry in payload["evidence_ids"])  # type: ignore[union-attr]
        )
        role_quota_report[role] = {
            "required": target,
            "found": len(ids),
            "independent_units": independent,
        }

    completeness = {
        "support_lane_complete": _group_complete(SUPPORT_GROUP_LANES, required, states),
        "counter_lane_complete": _group_complete(
            (Lane.COUNTEREVIDENCE.value,), required, states
        ),
        "null_lane_complete": _group_complete((Lane.NULL.value,), required, states),
        "boundary_lane_complete": _group_complete(
            (Lane.BOUNDARY.value,), required, states
        ),
        "method_lane_complete": _group_complete((Lane.METHOD.value,), required, states),
        "novelty_lane_complete": _group_complete(
            (Lane.EXTERNAL_NOVELTY.value,), required, states
        ),
    }

    pack: dict[str, object] = {
        "insight_id": insight_id,
        "corpus_snapshot_hash": corpus_snapshot_hash,
        "supporting_ids": roles["supporting"],
        "counter_ids": roles["counter"],
        "null_ids": roles["null"],
        "boundary_ids": roles["boundary"],
        "method_ids": roles["method"],
        "alternative_ids": roles["alternative"],
        "dependency_clusters": cluster_membership,
        "unsearched_scopes": list(certificate_value["unsearched_scope"]),  # type: ignore[arg-type]
        "retrieval_manifest_id": retrieval_manifest_id,
        "completeness": completeness,
        "retrieval_run_id": run_id,
        "search_lane_receipt_ids": list(certificate_value["lane_receipt_ids"]),  # type: ignore[arg-type]
        "effective_independent_count": effective,
        "bias_risk_register_id": bias_risk_register_id,
        "role_quota_report": role_quota_report,
        "completeness_certificate_hash": str(certificate_value["certificate_hash"]),
        "stale": stale,
    }
    pack["pack_id"] = "EP-" + _hex_digest(
        {
            "insight_id": insight_id,
            "retrieval_run_id": run_id,
            "completeness_certificate_hash": pack["completeness_certificate_hash"],
            "supporting_ids": roles["supporting"],
            "counter_ids": roles["counter"],
            "null_ids": roles["null"],
            "boundary_ids": roles["boundary"],
            "method_ids": roles["method"],
            "alternative_ids": roles["alternative"],
            "dependency_clusters": cluster_membership,
        }
    )
    return _validate_pack_shape(pack), clusters


def _validate_pack_shape(payload: Mapping[str, object]) -> SealedArtifact:
    value = _mapping(payload, "EvidencePack")
    _exact_fields(value, PACK_FIELDS, "EvidencePack")
    _text(value["pack_id"], "pack_id")
    _text(value["insight_id"], "insight_id")
    _hash(value["corpus_snapshot_hash"], "corpus_snapshot_hash")
    for role in PACK_ROLES:
        ids = _strings(value[_ROLE_FIELD[role]], _ROLE_FIELD[role])
        if ids != sorted(ids):
            _fail(
                "EVIDENCE_ORDER_INVALID",
                f"{_ROLE_FIELD[role]} must be sorted ascending",
            )
    clusters = value["dependency_clusters"]
    if not isinstance(clusters, Sequence) or isinstance(
        clusters, (str, bytes, bytearray)
    ):
        _fail("INPUT_INVALID", "dependency_clusters must be an array")
    for index, member_ids in enumerate(clusters):
        _strings(member_ids, f"dependency_clusters[{index}]", allow_empty=False)
    _strings(value["unsearched_scopes"], "unsearched_scopes")
    _text(value["retrieval_manifest_id"], "retrieval_manifest_id")
    completeness = _mapping(value["completeness"], "completeness")
    _exact_fields(completeness, _COMPLETENESS_FIELDS, "completeness")
    for field in sorted(_COMPLETENESS_FIELDS):
        _bool(completeness[field], f"completeness.{field}")
    _text(value["retrieval_run_id"], "retrieval_run_id")
    _strings(
        value["search_lane_receipt_ids"], "search_lane_receipt_ids", allow_empty=False
    )
    effective = value["effective_independent_count"]
    if (
        type(effective) not in (int, float)
        or isinstance(effective, bool)
        or float(effective) < 0.0
    ):
        _fail("INPUT_INVALID", "effective_independent_count must be a number >= 0")
    _text(value["bias_risk_register_id"], "bias_risk_register_id")
    report = _mapping(value["role_quota_report"], "role_quota_report")
    for key, entry in report.items():
        _mapping(entry, f"role_quota_report.{key}")
    _hash(value["completeness_certificate_hash"], "completeness_certificate_hash")
    _bool(value["stale"], "stale")
    return _sealed("EvidencePack", value)


def validate_evidence_pack(
    pack: Mapping[str, object],
    clusters: Sequence[Mapping[str, object]],
    *,
    units: Sequence[Mapping[str, object]],
    lane_assignments: Mapping[str, Sequence[str]],
    query_plan: Mapping[str, object] | SealedArtifact,
    receipts: Sequence[Mapping[str, object] | SealedArtifact],
    certificate: Mapping[str, object] | SealedArtifact,
    created_at: str,
    declared_links: Sequence[Mapping[str, object]] = (),
    unresolved_results: Sequence[Mapping[str, object]] = (),
    role_quotas: Mapping[str, int] | None = None,
) -> tuple[SealedArtifact, tuple[SealedArtifact, ...]]:
    """Recompute the pack from its bound inputs and require exact identity."""

    snapshot = _snapshot_composite(
        {
            "certificate": certificate,
            "clusters": clusters,
            "created_at": created_at,
            "declared_links": declared_links,
            "lane_assignments": lane_assignments,
            "pack": pack,
            "query_plan": query_plan,
            "receipts": receipts,
            "role_quotas": role_quotas,
            "units": units,
            "unresolved_results": unresolved_results,
        },
        "validate_evidence_pack",
    )
    pack = snapshot["pack"]  # type: ignore[assignment]
    clusters = snapshot["clusters"]  # type: ignore[assignment]
    units = snapshot["units"]  # type: ignore[assignment]
    lane_assignments = snapshot["lane_assignments"]  # type: ignore[assignment]
    query_plan = snapshot["query_plan"]  # type: ignore[assignment]
    receipts = snapshot["receipts"]  # type: ignore[assignment]
    certificate = snapshot["certificate"]  # type: ignore[assignment]
    created_at = snapshot["created_at"]  # type: ignore[assignment]
    declared_links = snapshot["declared_links"]  # type: ignore[assignment]
    unresolved_results = snapshot["unresolved_results"]  # type: ignore[assignment]
    role_quotas = snapshot["role_quotas"]  # type: ignore[assignment]
    asserted_pack = _validate_pack_shape(_mapping(pack, "EvidencePack"))
    asserted_clusters = [
        _validate_evidence_dependency_cluster_shape_from_snapshot(entry)
        for entry in clusters
    ]
    rebuilt_pack, rebuilt_clusters = assemble_evidence_pack(
        units,
        insight_id=_text(asserted_pack.payload["insight_id"], "insight_id"),
        corpus_snapshot_hash=_hash(
            asserted_pack.payload["corpus_snapshot_hash"], "corpus_snapshot_hash"
        ),
        retrieval_manifest_id=_text(
            asserted_pack.payload["retrieval_manifest_id"], "retrieval_manifest_id"
        ),
        bias_risk_register_id=_text(
            asserted_pack.payload["bias_risk_register_id"], "bias_risk_register_id"
        ),
        lane_assignments=lane_assignments,
        query_plan=query_plan,
        receipts=receipts,
        certificate=certificate,
        created_at=created_at,
        declared_links=declared_links,
        unresolved_results=unresolved_results,
        role_quotas=role_quotas,
        stale=_bool(asserted_pack.payload["stale"], "stale"),
    )
    if rebuilt_pack.canonical_bytes != asserted_pack.canonical_bytes:
        _fail(
            "PACK_RECONSTRUCTION_MISMATCH",
            "EvidencePack is not the deterministic assembly of its bound inputs",
        )
    rebuilt_bytes = [entry.canonical_bytes for entry in rebuilt_clusters]
    asserted_bytes = [entry.canonical_bytes for entry in asserted_clusters]
    if rebuilt_bytes != asserted_bytes:
        _fail(
            "CLUSTER_RECONSTRUCTION_MISMATCH",
            "cluster records are not the deterministic assembly of their bound inputs",
        )
    return rebuilt_pack, rebuilt_clusters
