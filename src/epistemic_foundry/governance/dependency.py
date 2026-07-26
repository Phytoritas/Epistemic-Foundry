"""Evidence-dependency correction.

Contract source: `schemas/evidence-dependency-cluster.schema.json`.

Invariant EF4-I08: counting correlated evidence items as independent support
inflates confidence. Five papers reanalyzing one dataset are one independent
unit, not five, so the adjusted count is the number of clusters rather than the
number of evidence ids.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso


def adjusted_support_count(clusters: Iterable[Sequence[str]]) -> int:
    """Independent units = non-empty clusters.

    Evidence sharing a dataset, cohort, author group, or pipeline belongs to one
    cluster and contributes one unit of support.
    """
    return sum(1 for cluster in clusters if list(cluster))


def build_dependency_cluster(
    *,
    run_id: str,
    evidence_ids: Sequence[str],
    dependency_types: Sequence[str],
    representative_evidence_ids: Sequence[str],
    independence_confidence: float,
    rationale: str,
    provenance_refs: Sequence[str],
    independent_unit_count: int | None = None,
    support_count_adjusted: int | None = None,
    cluster_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Record one dependency cluster with raw and adjusted support counts.

    `support_count_raw` is always the evidence count; the adjusted count
    defaults to the independent-unit count so the corrected value cannot be
    silently inflated back to the raw one.
    """
    if not evidence_ids:
        raise ValueError("a dependency cluster must reference at least one evidence id")
    units = independent_unit_count if independent_unit_count is not None else 1
    if units < 1:
        raise ValueError("independent_unit_count must be >= 1 for a non-empty cluster")
    adjusted = support_count_adjusted if support_count_adjusted is not None else units
    if adjusted > len(evidence_ids):
        raise ValueError(
            f"support_count_adjusted {adjusted} exceeds raw evidence count {len(evidence_ids)}: "
            "dependency correction may only reduce support"
        )
    cluster: dict[str, Any] = {
        "cluster_id": cluster_id or new_id("EDC"),
        "run_id": run_id,
        "evidence_ids": list(evidence_ids),
        "dependency_types": list(dependency_types),
        "representative_evidence_ids": list(representative_evidence_ids),
        "independent_unit_count": units,
        "independence_confidence": float(independence_confidence),
        "rationale": rationale,
        "support_count_raw": len(evidence_ids),
        "support_count_adjusted": adjusted,
        "provenance_refs": list(provenance_refs),
        "created_at": created_at or utc_now_iso(),
    }
    cluster["cluster_hash"] = hash_excluding(cluster, "cluster_hash")
    validate_artifact("evidence-dependency-cluster", cluster)
    return cluster


def corrected_support(clusters: Sequence[Mapping[str, Any]]) -> int:
    """Total dependency-corrected support across clusters."""
    return sum(int(cluster["support_count_adjusted"]) for cluster in clusters)
