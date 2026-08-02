"""One real PostgreSQL server for the whole D06 recovery-gate suite.

The server is D05's: its harness starts the pinned image and applies the
evolution store, and this package applies the D06 gate on top of it.  Starting
the container is the expensive part, so it is session-scoped and each test gets
a clean slate through a truncate-and-reseed.  Mock substitution is refused
outright — a gate that has only ever been proved against a fake is not a gate.

The migration journal is deliberately not truncated between tests: it is the
record of what was applied to this database, and a per-test reset of provenance
would be a per-test rewrite of history.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from fixtures import GATE_SCHEMA, STORE_SCHEMA, apply_gate
from pg_harness import (
    PostgresContainer,
    docker_is_available,
    seed,
    start_container,
    stop_container,
)


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    if not docker_is_available():
        pytest.fail(
            "D06 requires the pinned PostgreSQL image and a running Docker "
            "daemon; mock-only PostgreSQL tests are forbidden"
        )
    container = start_container()
    try:
        apply_gate(container)
        yield container
    finally:
        stop_container(container)


@pytest.fixture()
def gate(postgres: PostgresContainer) -> PostgresContainer:
    """A freshly seeded store with the gate applied and no open attempt."""

    postgres.sql(
        f"""
        TRUNCATE TABLE
            {GATE_SCHEMA}.checkpoint_attempts,
            {STORE_SCHEMA}.evolution_checkpoints,
            {STORE_SCHEMA}.archive_entries,
            {STORE_SCHEMA}.epistemic_niches,
            {STORE_SCHEMA}.island_membership,
            {STORE_SCHEMA}.island_states,
            {STORE_SCHEMA}.candidate_lineage,
            {STORE_SCHEMA}.evolution_runs
        RESTART IDENTITY CASCADE;
        """
    )
    seed(postgres)
    return postgres
