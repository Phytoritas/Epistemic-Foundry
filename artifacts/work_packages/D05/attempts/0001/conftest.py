"""One real PostgreSQL server for the whole D05 suite.

The container is session-scoped because starting it is the expensive part, and
each test gets a clean slate through a transactional truncate-and-reseed rather
than a fresh server.  Mock substitution is refused outright: if the pinned
image or the Docker daemon is unavailable the suite fails rather than passing
against something that is not PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pg_harness import PostgresContainer, docker_is_available, seed, start_container
from pg_harness import stop_container


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    if not docker_is_available():
        pytest.fail(
            "D05 requires the pinned PostgreSQL image and a running Docker "
            "daemon; mock-only PostgreSQL tests are forbidden"
        )
    container = start_container()
    try:
        yield container
    finally:
        stop_container(container)


@pytest.fixture()
def store(postgres: PostgresContainer) -> PostgresContainer:
    """A freshly seeded store; append-only guards make TRUNCATE the only reset."""

    postgres.sql(
        """
        TRUNCATE TABLE
            epistemic_foundry_evolution.evolution_checkpoints,
            epistemic_foundry_evolution.archive_entries,
            epistemic_foundry_evolution.epistemic_niches,
            epistemic_foundry_evolution.island_membership,
            epistemic_foundry_evolution.island_states,
            epistemic_foundry_evolution.candidate_lineage,
            epistemic_foundry_evolution.evolution_runs
        RESTART IDENTITY CASCADE;
        """
    )
    seed(postgres)
    return postgres
