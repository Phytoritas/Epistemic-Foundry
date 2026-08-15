"""Schema migration safety (EF4-I31).

Contract source: `schemas/schema-migration.schema.json`.

A `breaking` migration must carry a reverse transform and a human approval. The
reverse transform is the load-bearing requirement: without it the migration is a
one-way door, and discovering a defect after the fact leaves no path back to the
prior data shape. When the migration can lose data, the approval is required
regardless of compatibility class, because "reversible in principle" does not
recover a field the transform dropped.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id

#: Compatibility classes that change how existing readers interpret data.
BREAKING_COMPATIBILITY: frozenset[str] = frozenset({"breaking"})

#: `schema-migration.schema.json` types approval_record_id as a string, so "no
#: approval was required" cannot be encoded as null. An explicit sentinel keeps
#: the record schema-valid while still reading as absent; inventing a
#: plausible-looking approval id would fabricate the artifact the gate checks for.
NO_APPROVAL_REQUIRED = "NOT-REQUIRED-compatible-migration"


class MigrationRefused(ValueError):
    """A migration lacks the safety evidence its compatibility class requires."""


def build_schema_migration(
    *,
    schema_name: str,
    from_version: str,
    to_version: str,
    compatibility: str,
    transform_entrypoint: str,
    reverse_transform_entrypoint: str | None,
    preconditions: Sequence[str],
    postconditions: Sequence[str],
    fixture_artifact_ids: Sequence[str],
    data_loss_possible: bool,
    approval_record_id: str | None,
    migration_id: str | None = None,
) -> dict[str, Any]:
    """Record a migration, refusing an unsafe one.

    Fixtures are required for every class, not just breaking ones: a migration
    with no fixture has never been executed against data, so its postconditions
    are claims rather than observations.
    """
    breaking = compatibility in BREAKING_COMPATIBILITY

    if breaking and not reverse_transform_entrypoint:
        raise MigrationRefused(
            f"breaking migration of {schema_name} has no reverse transform; a one-way door "
            "leaves no path back when a defect is found after the fact"
        )
    if (breaking or data_loss_possible) and not approval_record_id:
        reason = "breaking" if breaking else "data-lossy"
        raise MigrationRefused(
            f"{reason} migration of {schema_name} requires a human approval record"
        )
    if not fixture_artifact_ids:
        raise MigrationRefused(
            f"migration of {schema_name} has no fixture artifacts; its postconditions are "
            "claims rather than observations until it runs against data"
        )
    if not postconditions:
        raise MigrationRefused(
            f"migration of {schema_name} declares no postconditions, so success cannot be checked"
        )
    if from_version == to_version:
        raise MigrationRefused(
            f"migration of {schema_name} does not change version ({from_version}); a no-op "
            "migration hides whether the transform ran"
        )

    migration: dict[str, Any] = {
        "migration_id": migration_id or new_id("SM"),
        "schema_name": schema_name,
        "from_version": from_version,
        "to_version": to_version,
        "compatibility": compatibility,
        "transform_entrypoint": transform_entrypoint,
        "reverse_transform_entrypoint": reverse_transform_entrypoint,
        "preconditions": list(preconditions),
        "postconditions": list(postconditions),
        "fixture_artifact_ids": list(fixture_artifact_ids),
        "data_loss_possible": bool(data_loss_possible),
        "approval_record_id": approval_record_id or NO_APPROVAL_REQUIRED,
    }
    migration["migration_hash"] = hash_excluding(migration, "migration_hash")
    validate_artifact("schema-migration", migration)
    return migration


def migration_is_reversible(migration: Mapping[str, Any]) -> bool:
    """True only when a reverse transform exists and no data is lost.

    A reverse entrypoint alone is not enough: if the forward transform drops a
    field, running the reverse cannot restore it.
    """
    return bool(migration.get("reverse_transform_entrypoint")) and not migration.get(
        "data_loss_possible"
    )


def requires_hook_retrust(migration: Mapping[str, Any]) -> bool:
    """Whether a breaking change must invalidate existing hook trust."""
    return str(migration.get("compatibility")) in BREAKING_COMPATIBILITY


def has_human_approval(migration: Mapping[str, Any]) -> bool:
    """True only when a real approval record backs this migration."""
    return str(migration.get("approval_record_id")) != NO_APPROVAL_REQUIRED
