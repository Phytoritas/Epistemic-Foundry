"""Container-backed PostgreSQL harness for the D05 evolution store.

The repository forbids mock-only PostgreSQL tests (D02's fixture fails closed
rather than substituting a fake), so this harness runs the migration against a
real server in the pinned image D04 already qualified.  Nothing here simulates
PostgreSQL: every assertion in the D05 suite is the real engine's answer.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[5]
MIGRATION: Final = ROOT / "migrations/v4_d05/0001_evolution_store.sql"
#: The same image digest the sealed D04 recovery gate qualified.
POSTGRES_IMAGE: Final = (
    "pgvector/pgvector@sha256:"
    "7d400e340efb42f4d8c9c12c6427adb253f726881a9985d2a471bf0eed824dff"
)
DATABASE: Final = "ef_d05"
SUPERUSER: Final = "postgres"
#: The runtime principal, deliberately created without any DELETE privilege.
RUNTIME_ROLE: Final = "ef_d05_runtime"
READY_TIMEOUT_SECONDS: Final = 90


class HarnessError(RuntimeError):
    """The container or the migration could not be brought up."""


@dataclass(frozen=True)
class PostgresContainer:
    name: str

    def sql(
        self,
        statement: str,
        *,
        user: str = SUPERUSER,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        return _docker_exec(
            self.name,
            ["psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", DATABASE],
            input_bytes=statement.encode("utf-8"),
            check=check,
        )

    def query(self, statement: str, *, user: str = SUPERUSER) -> list[Any]:
        """One JSON row set, so results cross the boundary without parsing."""

        wrapped = (
            "SELECT coalesce(json_agg(row_to_json(query_result)), '[]'::json) "
            f"FROM ({statement}) AS query_result;"
        )
        result = _docker_exec(
            self.name,
            [
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-t",
                "-A",
                "-U",
                user,
                "-d",
                DATABASE,
            ],
            input_bytes=wrapped.encode("utf-8"),
            check=True,
        )
        return json.loads(result.stdout.decode("utf-8").strip() or "[]")

    def refuses(self, statement: str, *, user: str = SUPERUSER) -> str:
        """Run a statement that must fail, and return the server's message."""

        result = self.sql(statement, user=user, check=False)
        if result.returncode == 0:
            raise AssertionError(f"statement was accepted: {statement}")
        return result.stderr.decode("utf-8", errors="replace")


def _run(
    arguments: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    check: bool = True,
    timeout: int = 120,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(arguments),
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=timeout,
    )


def _docker_exec(
    container: str,
    arguments: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    command = ["docker", "exec"]
    if input_bytes is not None:
        command.append("-i")
    command.append(container)
    command.extend(arguments)
    return _run(command, input_bytes=input_bytes, check=check)


def docker_is_available() -> bool:
    if shutil.which("docker") is None:
        return False
    if _run(["docker", "info"], check=False).returncode != 0:
        return False
    return (
        _run(["docker", "image", "inspect", POSTGRES_IMAGE], check=False).returncode
        == 0
    )


def start_container() -> PostgresContainer:
    """Start the pinned server, wait for readiness, and apply the migration."""

    if not MIGRATION.is_file():
        raise HarnessError(f"missing migration: {MIGRATION}")

    name = f"ef_d05_{uuid.uuid4().hex[:10]}"
    _run(
        [
            "docker",
            "run",
            "--rm",
            "--detach",
            "--name",
            name,
            "--env",
            "POSTGRES_PASSWORD=ef-d05-ephemeral",
            "--env",
            f"POSTGRES_DB={DATABASE}",
            POSTGRES_IMAGE,
        ]
    )

    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    ready = False
    while time.monotonic() < deadline:
        probe = _docker_exec(
            name,
            ["pg_isready", "-U", SUPERUSER, "-d", DATABASE],
            check=False,
        )
        if probe.returncode == 0:
            ready = True
            break
        time.sleep(1)
    if not ready:
        stop_container(PostgresContainer(name))
        raise HarnessError("the PostgreSQL container never became ready")

    container = PostgresContainer(name)
    try:
        container.sql(MIGRATION.read_text(encoding="utf-8"))
        # A runtime principal with no DELETE anywhere: the store's guarantees
        # must hold for the role that actually uses it, not only for a
        # superuser that could bypass anything.
        container.sql(
            f"""
            CREATE ROLE {RUNTIME_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS
                PASSWORD 'ef-d05-ephemeral';
            GRANT USAGE ON SCHEMA epistemic_foundry_evolution TO {RUNTIME_ROLE};
            GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA
                epistemic_foundry_evolution TO {RUNTIME_ROLE};
            GRANT EXECUTE ON FUNCTION
                epistemic_foundry_evolution.evict_archive_entry(text, text)
                TO {RUNTIME_ROLE};
            GRANT EXECUTE ON FUNCTION
                epistemic_foundry_evolution.seal_checkpoint(
                    text, text, integer, text, text, text, text, text, text,
                    text, text
                )
                TO {RUNTIME_ROLE};
            """
        )
    except subprocess.CalledProcessError as error:
        stop_container(container)
        raise HarnessError(
            "the migration did not apply: "
            + error.stderr.decode("utf-8", errors="replace")
        ) from error
    return container


def stop_container(container: PostgresContainer) -> None:
    _run(
        ["docker", "stop", "--time", "5", container.name],
        check=False,
        timeout=45,
    )


def seed(container: PostgresContainer) -> None:
    """A minimal run: one evaluator binding, three candidates, one island."""

    container.sql(
        """
        INSERT INTO epistemic_foundry_evolution.evolution_runs
            (run_id, evaluator_bundle_hash, holdout_manifest_hash)
        VALUES ('RUN-1', 'sha256:"""
        + "a" * 64
        + """',
                'sha256:"""
        + "b" * 64
        + """');

        INSERT INTO epistemic_foundry_evolution.candidate_lineage
            (candidate_id, run_id, parent_candidate_id, generation,
             genome_hash, operator_id)
        VALUES
            ('CAND-0', 'RUN-1', NULL, 0, 'sha256:"""
        + "c" * 64
        + """', 'OP-SEED'),
            ('CAND-1', 'RUN-1', 'CAND-0', 1, 'sha256:"""
        + "d" * 64
        + """', 'OP-MUTATE'),
            ('CAND-2', 'RUN-1', 'CAND-0', 1, 'sha256:"""
        + "e" * 64
        + """', 'OP-MUTATE');

        INSERT INTO epistemic_foundry_evolution.island_states
            (island_id, run_id, specialization, state_hash)
        VALUES ('ISL-1', 'RUN-1', 'MECHANISM', 'sha256:"""
        + "f" * 64
        + """');

        INSERT INTO epistemic_foundry_evolution.island_membership
            (island_id, candidate_id)
        VALUES ('ISL-1', 'CAND-1');

        INSERT INTO epistemic_foundry_evolution.epistemic_niches
            (niche_id, run_id, descriptor_hash)
        VALUES ('NICHE-1', 'RUN-1', 'sha256:"""
        + "1" * 64
        + """');

        INSERT INTO epistemic_foundry_evolution.archive_entries
            (entry_id, run_id, candidate_id, niche_id, fitness_vector_hash,
             combined_score, protection_reason)
        VALUES
            ('AE-STRONG', 'RUN-1', 'CAND-1', 'NICHE-1',
             'sha256:"""
        + "2" * 64
        + """', 0.91, NULL),
            ('AE-WEAK', 'RUN-1', 'CAND-2', 'NICHE-1',
             'sha256:"""
        + "3" * 64
        + """', 0.04, NULL),
            ('AE-NULL', 'RUN-1', 'CAND-0', 'NICHE-1',
             'sha256:"""
        + "4" * 64
        + """', 0.01, 'NULL_RESULT');
        """
    )
