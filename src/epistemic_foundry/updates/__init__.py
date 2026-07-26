"""Migration safety and downstream invalidation.

* EF4-I31: breaking schema/plugin changes require compatibility, dry-run, backup,
  rollback, and hook re-trust. A breaking migration with no reverse transform is
  a one-way door.
* EF4-I38: corrections, retractions, parser fixes, policy/ontology changes, and
  new evidence invalidate dependent projections and Passports. A correction that
  leaves dependents untouched has not been applied.
"""

from __future__ import annotations

from .migration import MigrationRefused, build_schema_migration, migration_is_reversible
from .impact import build_impact_report, dependent_closure

__all__ = [
    "MigrationRefused",
    "build_impact_report",
    "build_schema_migration",
    "dependent_closure",
    "migration_is_reversible",
]
