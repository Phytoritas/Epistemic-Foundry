"""PostgreSQL TEAM-profile canonical state store.

The adapter intentionally imports no driver. Callers inject a dedicated
DB-API-compatible PostgreSQL connection factory; D02 contract tests use a
pinned Psycopg 3 environment against a real PostgreSQL server.
"""

from .store import (
    POSTGRES_STORE_MODE,
    PostgresStateStore,
    PostgresStateStoreError,
    open_postgres_state_store,
)

__all__ = [
    "POSTGRES_STORE_MODE",
    "PostgresStateStore",
    "PostgresStateStoreError",
    "open_postgres_state_store",
]
