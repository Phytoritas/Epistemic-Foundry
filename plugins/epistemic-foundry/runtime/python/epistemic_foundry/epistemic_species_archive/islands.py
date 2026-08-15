"""Semantic islands and compatibility-gated migration (EF4-I50).

Contract source: `schemas/island-state.schema.json`.

"Islands specialize by typed mechanism, scope, method or evidence state;
migration requires compatibility and preserves source/target history."

Three properties follow, and each has a distinct failure it prevents:

* *Typed specialization.* An island declares which axis it specializes on, drawn
  from a closed vocabulary. Free-text specialization would make two islands
  nominally different and functionally identical, so the population would look
  diverse while searching one region.
* *Compatibility-gated migration.* A migrant moves only between islands whose
  specializations are comparable on the same axis. Moving a candidate into an
  island specialized on a different mechanism does not diversify that island; it
  contaminates the specialization the island exists to maintain.
* *Preserved history.* Migration appends to the source's `outgoing_migrant_ids`
  and the target's `incoming_migrant_ids` in one operation. Recording only the
  arrival would make a candidate appear native to the island it migrated into,
  and its lineage would then read as independent evidence from that niche.

`stagnation_rounds` is carried but never resets on migration alone: receiving a
migrant is not progress, and letting an inbound copy clear the counter would hide
a dead island behind traffic.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id

#: Axes an island may specialize on, from the invariant text. An island declares
#: exactly one so that comparability is decidable.
SPECIALIZATION_AXES: tuple[str, ...] = ("mechanism", "scope", "method", "evidence_state")


class IslandPolicyViolation(ValueError):
    """An island or migration violates the island policy."""


class MigrationRefused(RuntimeError):
    """A migration was attempted between incompatible islands."""


def specialization(axis: str, value: str) -> str:
    """Compose the typed `semantic_specialization` string `<axis>:<value>`.

    Composition is centralized so the axis is always recoverable from the stored
    string. A free-text specialization cannot be compared for compatibility, and
    an uncomparable specialization makes the migration gate unenforceable.
    """
    if axis not in SPECIALIZATION_AXES:
        raise IslandPolicyViolation(
            f"specialization axis {axis!r} is not typed; expected one of {SPECIALIZATION_AXES}"
        )
    if not value.strip():
        raise IslandPolicyViolation(f"axis {axis} needs a non-empty specialization value")
    return f"{axis}:{value.strip()}"


def specialization_axis(island: Mapping[str, Any]) -> str:
    """Recover the declared axis, refusing an untyped specialization string."""
    raw = str(island.get("semantic_specialization", ""))
    axis, _, value = raw.partition(":")
    if axis not in SPECIALIZATION_AXES or not value:
        raise IslandPolicyViolation(
            f"island {island.get('island_id')} carries untyped specialization {raw!r}; "
            "compatibility cannot be decided against an untyped island"
        )
    return axis


def build_island_state(
    *,
    evolution_run_id: str,
    axis: str,
    value: str,
    candidate_ids: Sequence[str],
    archive_entry_ids: Sequence[str],
    generation: int,
    migration_policy: str,
    incoming_migrant_ids: Sequence[str] = (),
    outgoing_migrant_ids: Sequence[str] = (),
    stagnation_rounds: int = 0,
    island_id: str | None = None,
) -> dict[str, Any]:
    """Seal an island whose specialization is typed and whose migrants are named.

    A migrant listed as outgoing but still present in `candidate_ids` is refused:
    the island would count a candidate it has given away, inflating both its own
    occupancy and the target's.
    """
    if not migration_policy.strip():
        raise IslandPolicyViolation(
            "an island must declare a migration policy; an island that migrates under no "
            "stated rule cannot be audited for contamination"
        )
    if generation < 0 or stagnation_rounds < 0:
        raise IslandPolicyViolation("generation and stagnation_rounds cannot be negative")

    outgoing = list(dict.fromkeys(outgoing_migrant_ids))
    residents = list(dict.fromkeys(candidate_ids))
    still_present = sorted(set(outgoing) & set(residents))
    if still_present:
        raise IslandPolicyViolation(
            f"candidates {still_present} are recorded as outgoing migrants while still listed "
            "as residents; one candidate would be counted on two islands"
        )

    island: dict[str, Any] = {
        "island_id": island_id or new_id("ISL"),
        "evolution_run_id": evolution_run_id,
        "semantic_specialization": specialization(axis, value),
        "candidate_ids": residents,
        "archive_entry_ids": list(dict.fromkeys(archive_entry_ids)),
        "generation": generation,
        "migration_policy": migration_policy,
        "incoming_migrant_ids": list(dict.fromkeys(incoming_migrant_ids)),
        "outgoing_migrant_ids": outgoing,
        "stagnation_rounds": stagnation_rounds,
    }
    island["state_hash"] = hash_excluding(island, "state_hash")
    validate_artifact("island-state", island)
    return island


def migration_blockers(
    source: Mapping[str, Any], target: Mapping[str, Any], *, candidate_id: str
) -> list[str]:
    """Every reason this migration is refused, reported together.

    All blockers are returned at once so a caller fixes the whole condition rather
    than discovering the next one after each retry.
    """
    blockers: list[str] = []
    if source.get("island_id") == target.get("island_id"):
        blockers.append("source and target are the same island")
    if source.get("evolution_run_id") != target.get("evolution_run_id"):
        blockers.append(
            "islands belong to different evolution runs; a cross-run migrant would import "
            "a candidate evaluated under another evaluator bundle"
        )
    if candidate_id not in source.get("candidate_ids", []):
        blockers.append(f"candidate {candidate_id} is not resident on the source island")
    if specialization_axis(source) != specialization_axis(target):
        blockers.append(
            "islands specialize on different axes, so their specializations are not comparable"
        )
    elif source.get("semantic_specialization") == target.get("semantic_specialization"):
        blockers.append(
            "islands share one specialization, so migration would not diversify the target"
        )
    return blockers


def migrate_candidate(
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    *,
    candidate_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Move one candidate, returning both updated islands.

    Both sides are returned from a single call so a caller cannot persist the
    arrival without the departure. Applying one half of a migration is what makes
    a migrant look native to its new island.
    """
    blockers = migration_blockers(source, target, candidate_id=candidate_id)
    if blockers:
        raise MigrationRefused(
            f"refusing to migrate {candidate_id} from {source.get('island_id')} to "
            f"{target.get('island_id')}: " + "; ".join(blockers)
        )

    source_axis, _, source_value = str(source["semantic_specialization"]).partition(":")
    target_axis, _, target_value = str(target["semantic_specialization"]).partition(":")

    new_source = build_island_state(
        island_id=str(source["island_id"]),
        evolution_run_id=str(source["evolution_run_id"]),
        axis=source_axis,
        value=source_value,
        candidate_ids=[cid for cid in source["candidate_ids"] if cid != candidate_id],
        archive_entry_ids=source["archive_entry_ids"],
        generation=int(source["generation"]),
        migration_policy=str(source["migration_policy"]),
        incoming_migrant_ids=source["incoming_migrant_ids"],
        outgoing_migrant_ids=[*source["outgoing_migrant_ids"], candidate_id],
        stagnation_rounds=int(source["stagnation_rounds"]),
    )
    new_target = build_island_state(
        island_id=str(target["island_id"]),
        evolution_run_id=str(target["evolution_run_id"]),
        axis=target_axis,
        value=target_value,
        candidate_ids=[*target["candidate_ids"], candidate_id],
        archive_entry_ids=target["archive_entry_ids"],
        generation=int(target["generation"]),
        migration_policy=str(target["migration_policy"]),
        incoming_migrant_ids=[*target["incoming_migrant_ids"], candidate_id],
        outgoing_migrant_ids=target["outgoing_migrant_ids"],
        # Receiving a migrant is not progress, so the target's stagnation counter
        # carries forward unchanged.
        stagnation_rounds=int(target["stagnation_rounds"]),
    )
    return new_source, new_target


def migration_history_preserved(
    source: Mapping[str, Any], target: Mapping[str, Any], *, candidate_id: str
) -> bool:
    """True only when both sides record the same migration.

    Checked as a pair because a one-sided record is the specific corruption this
    invariant names: the candidate appears native to the target.
    """
    return (
        candidate_id in source.get("outgoing_migrant_ids", [])
        and candidate_id in target.get("incoming_migrant_ids", [])
        and candidate_id not in source.get("candidate_ids", [])
        and candidate_id in target.get("candidate_ids", [])
    )
