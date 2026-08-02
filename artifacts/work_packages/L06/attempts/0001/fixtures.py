"""Fixtures for the L06 integration gate suites.

The archive entries and lineage records validate against their canonical
schemas on construction, because L05 — which this gate composes — validates
every input: a fixture the schema would refuse tests nothing but the fixture.
Entry classes come from the archive module's own partition and forget grounds
from L05, so a vocabulary change breaks these fixtures rather than letting them
drift.

Two plan builders exist on purpose.  ``forget_plan`` produces a real L05 plan,
which is what a healthy runtime executes.  ``forged_plan`` hand-builds a
plan-shaped record with a correctly re-derived hash, because the sweep audit
exists to catch exactly the plans a healthy engine would never have produced.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.epistemic_species_archive.archive import (
    EVICTABLE_ENTRY_CLASSES,
    PROTECTED_ENTRY_CLASSES,
)
from epistemic_foundry.memory.policy import MEMORY_CLASSES
from epistemic_foundry.memory.v4_l05 import LineageMemory, plan_forget
from epistemic_foundry.memory.v4_l06 import place_legal_hold

#: One deterministic representative of each side of the partition.
AN_EVICTABLE_CLASS = sorted(EVICTABLE_ENTRY_CLASSES)[0]
A_PROTECTED_CLASS = sorted(PROTECTED_ENTRY_CLASSES)[0]

#: A memory class taken from the policy vocabulary rather than typed out.
A_MEMORY_CLASS = MEMORY_CLASSES[0]
ANOTHER_MEMORY_CLASS = MEMORY_CLASSES[1]

RECORDED_AT = "2026-08-03T00:00:00.000Z"
EXECUTED_AT = "2026-08-03T01:00:00.000Z"
VERIFIED_AT = "2026-08-03T02:00:00.000Z"
WORKSPACE = "WS-L06-1"

#: The ground a hold must outrank even while it is being executed.  Its
#: membership in L05's vocabulary is asserted by the schema-and-type suite.
REGULATED_ERASURE = "regulated_erasure"

FORGET_AUTHORITY = {
    "authority_id": "AUT-L06-1",
    "approved_by": "workspace-governor",
    "ground": "workspace_purge",
}
HOLD_AUTHORITY = {
    "approved_by": "records-custodian",
    "hold_authority_id": "LHA-L06-1",
    "legal_matter_id": "MATTER-L06-7",
}
OTHER_MATTER_AUTHORITY = {
    "approved_by": "records-custodian",
    "hold_authority_id": "LHA-L06-2",
    "legal_matter_id": "MATTER-L06-9",
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


#: C1 -> C2 -> C3 -> C4, one child each.  C2 carries protected knowledge, so a
#: whole-chain forget erases C3 and C4 and tombstones C1 and C2.
CHAIN = ("C1", "C2", "C3", "C4")


def chain_records() -> list[dict[str, Any]]:
    return [
        lineage_record("C1", [], 1),
        lineage_record("C2", ["C1"], 2),
        lineage_record("C3", ["C2"], 3),
        lineage_record("C4", ["C3"], 4),
    ]


def chain_memory() -> LineageMemory:
    return LineageMemory(chain_records())


def chain_entries() -> list[dict[str, Any]]:
    return [
        archive_entry("C1", "elite"),
        archive_entry("C2", A_PROTECTED_CLASS),
        archive_entry("C3", "diverse"),
        archive_entry("C4", "superseded"),
    ]


def forget_plan(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "entries": chain_entries(),
        "lineage": chain_memory(),
        "candidate_ids": list(CHAIN),
        "authority": dict(FORGET_AUTHORITY),
        "requested_at": RECORDED_AT,
        "plan_id": "EFP-L06-1",
    }
    arguments.update(overrides)
    return plan_forget(**arguments)


def tombstone(candidate_id: str, entry_class: str, code: str) -> dict[str, Any]:
    """A tombstone in the shape L05 produces, for hand-built plans."""
    return {
        "archive_entry_id": f"AE-{candidate_id}",
        "artifact_hash": "sha256:" + "b" * 64,
        "candidate_id": candidate_id,
        "code": code,
        "entry_class": entry_class,
        "generation": CHAIN.index(candidate_id) + 1,
        "lineage_id": f"LIN-{candidate_id}",
        "reason": "recorded by the plan that produced this tombstone",
        "retention_reason": "kept for the search record",
    }


def forged_plan(
    *,
    erased: list[str],
    tombstoned: list[dict[str, Any]] | None = None,
    plan_id: str = "EFP-L06-FORGED",
) -> dict[str, Any]:
    """A plan-shaped record whose hash re-derives but whose outcomes are wrong.

    A healthy L05 plan never strands ancestry; the sweep audit is what notices
    when the record of what was executed says it did.
    """
    rows = list(tombstoned or [])
    plan: dict[str, Any] = {
        "authority": {
            "approved_by": str(FORGET_AUTHORITY["approved_by"]),
            "authority_id": str(FORGET_AUTHORITY["authority_id"]),
            "ground": str(FORGET_AUTHORITY["ground"]),
        },
        "counts": {
            "erased": len(erased),
            "refused": 0,
            "requested": len(erased) + len(rows),
            "tombstoned": len(rows),
        },
        "erased": sorted(erased),
        "plan_id": plan_id,
        "refusals": [],
        "requested": sorted(erased) + [row["candidate_id"] for row in rows],
        "requested_at": RECORDED_AT,
        "tombstoned": rows,
    }
    plan["plan_hash"] = hash_excluding(plan, "plan_hash")
    return plan


def execution(**overrides: Any) -> dict[str, Any]:
    """The report a runtime returns after acting on the whole-chain plan."""
    report: dict[str, Any] = {
        "executed_at": EXECUTED_AT,
        "erased": ["C3", "C4"],
        "tombstoned": ["C1", "C2"],
        "not_executed": [],
    }
    report.update(overrides)
    return report


def hold(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "hold_id": "LH-L06-1",
        "authority": dict(HOLD_AUTHORITY),
        "placed_at": RECORDED_AT,
        "candidate_ids": ["C4"],
    }
    arguments.update(overrides)
    return place_legal_hold(**arguments)


def sweep_arguments(**overrides: Any) -> dict[str, Any]:
    """A healthy sweep: the whole-chain plan, executed, audited afterwards.

    C3 and C4 are gone from both the archive and the lineage; C1 and C2 keep
    their lineage records because they were tombstoned, and their tombstone
    facts are held in the ledger.
    """
    plan = forget_plan()
    arguments: dict[str, Any] = {
        "entries": [],
        "lineage_records": [
            lineage_record("C1", [], 1),
            lineage_record("C2", ["C1"], 2),
        ],
        "executed_plans": [plan],
        "tombstones": [dict(row) for row in plan["tombstoned"]],
        "audited_at": VERIFIED_AT,
        "audit_id": "ERS-L06-1",
    }
    arguments.update(overrides)
    return arguments
