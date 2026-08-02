"""Fixtures for the L05 retention suites.

The archive entries and lineage records here validate against their canonical
schemas on construction, because the engine itself validates every input: a
fixture the schema would refuse tests nothing but the fixture.  Entry classes
are taken from the archive module's own partition rather than typed out, so a
vocabulary change breaks these fixtures instead of letting them drift.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.epistemic_species_archive.archive import (
    EVICTABLE_ENTRY_CLASSES,
    PROTECTED_ENTRY_CLASSES,
)
from epistemic_foundry.memory.policy import build_memory_policy
from epistemic_foundry.memory.v4_l05 import LineageMemory

#: One deterministic representative of each side of the partition.
AN_EVICTABLE_CLASS = sorted(EVICTABLE_ENTRY_CLASSES)[0]
A_PROTECTED_CLASS = sorted(PROTECTED_ENTRY_CLASSES)[0]

RECORDED_AT = "2026-08-02T00:00:00.000Z"
WORKSPACE = "WS-L05-1"
AUTHORITY = {
    "authority_id": "AUT-L05-1",
    "approved_by": "workspace-governor",
    "ground": "workspace_purge",
}


def lineage_record(
    candidate_id: str, parent_ids: list[str], generation: int
) -> dict[str, Any]:
    return {
        "lineage_id": f"LIN-{candidate_id}",
        "candidate_id": candidate_id,
        "parent_ids": list(parent_ids),
        "inspiration_ids": [],
        "mutation_operator_ids": ["MO-POINT-1"],
        "crossover_parent_ids": [],
        "generation": generation,
        "island_id": "IS-1",
        "ancestor_hashes": ["sha256:" + "a" * 64],
        "created_at": RECORDED_AT,
    }


def archive_entry(candidate_id: str, entry_class: str) -> dict[str, Any]:
    return {
        "archive_entry_id": f"AE-{candidate_id}",
        "candidate_id": candidate_id,
        "entry_class": entry_class,
        "niche_id": "NI-1",
        "fitness_vector_id": f"FV-{candidate_id}",
        "lineage_id": f"LIN-{candidate_id}",
        "retention_reason": "kept for the search record",
        "replacement_policy": "never_for_capacity",
        "artifact_hash": "sha256:" + "b" * 64,
        "archived_at": RECORDED_AT,
    }


def chain_memory() -> LineageMemory:
    """C1 -> C2 -> C3 -> C4, one child each."""
    return LineageMemory(
        [
            lineage_record("C1", [], 1),
            lineage_record("C2", ["C1"], 2),
            lineage_record("C3", ["C2"], 3),
            lineage_record("C4", ["C3"], 4),
        ]
    )


def chain_entries() -> list[dict[str, Any]]:
    return [
        archive_entry("C1", "elite"),
        archive_entry("C2", "null"),
        archive_entry("C3", "diverse"),
        archive_entry("C4", "superseded"),
    ]


def evidence_rule(**overrides: Any) -> dict[str, Any]:
    rule = {
        "class": "EVIDENCE",
        "retention_days": 365,
        "requires_consent": True,
        "external_sync": "ALLOW_REDACTED",
        "redaction_profile": "evidence-default",
    }
    rule.update(overrides)
    return rule


def workspace_policy(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "workspace_id": WORKSPACE,
        "allowed_classes": ["WORKSPACE", "EVIDENCE"],
        "default_retention_days": 90,
        "class_rules": [evidence_rule()],
        "effective_at": "2026-01-01T00:00:00.000Z",
        "policy_id": "MP-L05-1",
    }
    keywords.update(overrides)
    return build_memory_policy(**keywords)


def export_arguments(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "entries": chain_entries(),
        "lineage": chain_memory(),
        "policy": workspace_policy(),
        "workspace_id": WORKSPACE,
        "memory_classes": ["EVIDENCE"],
        "purpose": "workspace audit export",
        "consent_id": "CN-L05-1",
        "exported_at": "2026-08-02T02:00:00.000Z",
        "manifest_id": "EEM-L05-1",
    }
    arguments.update(overrides)
    return arguments
