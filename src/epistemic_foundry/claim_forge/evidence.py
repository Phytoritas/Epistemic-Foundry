"""Evidence-node construction with typed roles.

Contract source: `schemas/evidence-node.schema.json`.

Invariant EF4-I06 (adversarial retrieval): counter, null, boundary, method,
leakage, and OOD lanes stay visible. The `role` field is therefore never
defaulted to `support` — an untyped evidence item would let a counter-example be
silently filed as agreement.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..contracts import validate_artifact
from ..domain.ids import new_id

#: Roles that argue against or bound a claim. Their visibility is the whole
#: point of adversarial retrieval, so they are named rather than inferred.
DISSENTING_ROLES = frozenset({"counter", "null", "boundary", "limitation"})


def build_evidence_node(
    *,
    claim_ids: Sequence[str],
    source_spans: Sequence[dict[str, Any]],
    experiment_id: str | None,
    role: str,
    scope: dict[str, Any],
    method_ids: Sequence[str],
    dataset_family_id: str,
    quality: dict[str, Any],
    provenance_manifest_id: str,
    evidence_class: str,
    source_integrity_report_id: str,
    dependency_cluster_ids: Sequence[str] = (),
    bias_flags: Sequence[str] = (),
    status: str = "candidate",
    validity_status: str = "active",
    lifecycle_event_ids: Sequence[str] = (),
    evidence_id: str | None = None,
) -> dict[str, Any]:
    """Build an evidence node bound to at least one claim and one span.

    An evidence node with no span is unfalsifiable: nothing anchors it to a
    document, so it is refused rather than stored as weak support.
    """
    if not claim_ids:
        raise ValueError("evidence must reference at least one claim")
    if not source_spans:
        raise ValueError("evidence must carry at least one source span; unanchored evidence is refused")
    node: dict[str, Any] = {
        "evidence_id": evidence_id or new_id("EV"),
        "claim_ids": list(claim_ids),
        "source_spans": [dict(span) for span in source_spans],
        "experiment_id": experiment_id,
        "role": role,
        "scope": scope,
        "method_ids": list(method_ids),
        "dataset_family_id": dataset_family_id,
        "quality": quality,
        "status": status,
        "provenance_manifest_id": provenance_manifest_id,
        "evidence_class": evidence_class,
        "dependency_cluster_ids": list(dependency_cluster_ids),
        "bias_flags": list(bias_flags),
        "validity_status": validity_status,
        "source_integrity_report_id": source_integrity_report_id,
        "lifecycle_event_ids": list(lifecycle_event_ids),
    }
    validate_artifact("evidence-node", node)
    return node


def supporting_evidence(nodes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Active support only.

    Stale, invalidated, and quarantined evidence is excluded: an invalidated
    item must stop counting as support the moment it is invalidated.
    """
    return [
        node
        for node in nodes
        if node.get("role") == "support" and node.get("validity_status") == "active"
    ]


def dissenting_evidence(nodes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Counter, null, boundary, and limitation lanes that remain visible."""
    return [node for node in nodes if node.get("role") in DISSENTING_ROLES]
