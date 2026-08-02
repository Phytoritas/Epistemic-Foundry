"""Fixtures and the D06 apply helper for the recovery-gate suites.

The container harness is D05's, imported rather than copied: the pinned image,
the readiness probe, the runtime principal and the D05 migration all stay
declared in one place, so this package cannot drift from the store it extends.
What is added here is the part D05 does not own — applying the D06 gate on top
of the store D05 already built, granting the runtime principal the gate's entry
points, and probing the database inside a transaction that is never committed
so a tamper test can observe drift without leaving any behind.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Final

from pg_harness import DATABASE, RUNTIME_ROLE, SUPERUSER, PostgresContainer

ROOT: Final = Path(__file__).resolve().parents[5]
MIGRATION: Final = ROOT / "migrations/v4_d06/0001_archive_migration_gate.sql"
D05_MIGRATION: Final = ROOT / "migrations/v4_d05/0001_evolution_store.sql"

STORE_SCHEMA: Final = "epistemic_foundry_evolution"
GATE_SCHEMA: Final = "epistemic_foundry_recovery"
STORE_JOURNAL_ID: Final = "v4_d05/0001_evolution_store"
GATE_JOURNAL_ID: Final = "v4_d06/0001_archive_migration_gate"

#: A stand-in content address, valid under D05's sha256 domain.
SEALED: Final = "sha256:" + "9" * 64
#: The evaluator the seeded run is bound to (pg_harness.seed).
RUN_EVALUATOR: Final = "sha256:" + "a" * 64
#: The seeded lineage holds CAND-1 and CAND-2 at generation 1.
SEEDED_GENERATION: Final = 1
SEEDED_CANDIDATE_COUNT: Final = 2

#: The preflight block the migration opens with, located by its dollar tag.
PREFLIGHT_TAG: Final = "$preflight$"


class GateMigrationError(RuntimeError):
    """Typed refusal: the D06 gate could not be applied on top of D05."""


class GateProbeError(RuntimeError):
    """Typed refusal: a probe statement failed for a reason the test did not
    ask for, so its result cannot be read as an answer."""


def apply_gate(container: PostgresContainer) -> None:
    """Apply the D06 migration to a container that already carries D05.

    Fails closed on a missing file or a refused migration rather than letting
    a half-configured database reach a test, and grants the runtime principal
    exactly the gate entry points it needs: no INSERT, UPDATE or DELETE on any
    recovery table, so every write still goes through a guarded function.
    """

    if not MIGRATION.is_file():
        raise GateMigrationError(f"missing migration: {MIGRATION}")

    applied = container.sql(MIGRATION.read_text(encoding="utf-8"), check=False)
    if applied.returncode != 0:
        raise GateMigrationError(
            "the D06 migration did not apply: "
            + applied.stderr.decode("utf-8", errors="replace")
        )

    granted = container.sql(
        f"""
        GRANT USAGE ON SCHEMA {GATE_SCHEMA} TO {RUNTIME_ROLE};
        GRANT SELECT ON ALL TABLES IN SCHEMA {GATE_SCHEMA} TO {RUNTIME_ROLE};
        GRANT EXECUTE ON FUNCTION
            {GATE_SCHEMA}.open_checkpoint_attempt(text, text, integer, integer)
            TO {RUNTIME_ROLE};
        GRANT EXECUTE ON FUNCTION
            {GATE_SCHEMA}.seal_and_close_attempt(
                text, text, text, text, text, text, text, text, text, text)
            TO {RUNTIME_ROLE};
        GRANT EXECUTE ON FUNCTION
            {GATE_SCHEMA}.abandon_checkpoint_attempt(text, text)
            TO {RUNTIME_ROLE};
        GRANT EXECUTE ON FUNCTION
            {GATE_SCHEMA}.verify_migration_journal() TO {RUNTIME_ROLE};
        GRANT EXECUTE ON FUNCTION
            {GATE_SCHEMA}.require_intact_migration_journal()
            TO {RUNTIME_ROLE};
        GRANT EXECUTE ON FUNCTION
            {GATE_SCHEMA}.schema_digest(text) TO {RUNTIME_ROLE};
        """,
        check=False,
    )
    if granted.returncode != 0:
        raise GateMigrationError(
            "the gate entry points could not be granted: "
            + granted.stderr.decode("utf-8", errors="replace")
        )


def preflight_block() -> str:
    """Return the migration's preflight block, located rather than restated.

    The block is extracted from the file so the dependency refusal can be
    exercised against a database without D05 without a second copy of the
    check drifting from the one that actually runs.
    """

    text = MIGRATION.read_text(encoding="utf-8")
    opened = text.find(f"DO {PREFLIGHT_TAG}")
    if opened < 0:
        raise GateMigrationError("the migration declares no preflight block")
    closed = text.find(f"{PREFLIGHT_TAG};", opened + len(f"DO {PREFLIGHT_TAG}"))
    if closed < 0:
        raise GateMigrationError("the preflight block is not terminated")
    return text[opened : closed + len(PREFLIGHT_TAG) + 1]


def open_attempt_call(
    attempt_id: str = "AT-1",
    run_id: str = "RUN-1",
    generation: int = SEEDED_GENERATION,
    expected: int = SEEDED_CANDIDATE_COUNT,
) -> str:
    return (
        f"SELECT {GATE_SCHEMA}.open_checkpoint_attempt("
        f"'{attempt_id}', '{run_id}', {generation}, {expected}) AS ok"
    )


def seal_and_close_call(
    attempt_id: str = "AT-1",
    checkpoint_id: str = "CP-1",
    evaluator: str = RUN_EVALUATOR,
) -> str:
    return (
        f"SELECT {GATE_SCHEMA}.seal_and_close_attempt("
        f"'{attempt_id}', '{checkpoint_id}', "
        f"'{SEALED}', '{SEALED}', '{SEALED}', '{SEALED}', '{SEALED}', "
        f"'{SEALED}', '{evaluator}', '{SEALED}') AS ok"
    )


def store_seal_call(
    checkpoint_id: str = "CP-DIRECT",
    run_id: str = "RUN-1",
    generation: int = SEEDED_GENERATION,
    evaluator: str = RUN_EVALUATOR,
) -> str:
    """D05's own seal, called around the gate rather than through it."""

    return (
        f"SELECT {STORE_SCHEMA}.seal_checkpoint("
        f"'{checkpoint_id}', '{run_id}', {generation}, "
        f"'{SEALED}', '{SEALED}', '{SEALED}', '{SEALED}', '{SEALED}', "
        f"'{SEALED}', '{evaluator}', '{SEALED}') AS ok"
    )


def lineage_insert(candidate_id: str, generation: int = 1) -> str:
    parent = "'CAND-0'" if generation > 0 else "NULL"
    return (
        f"INSERT INTO {STORE_SCHEMA}.candidate_lineage "
        "(candidate_id, run_id, parent_candidate_id, generation, "
        "genome_hash, operator_id) VALUES "
        f"('{candidate_id}', 'RUN-1', {parent}, {generation}, "
        f"'{SEALED}', 'OP-MUTATE');"
    )


def probe_in_aborted_transaction(
    container: PostgresContainer,
    *,
    statements: tuple[str, ...],
    query: str,
    user: str = SUPERUSER,
) -> list[Any]:
    """Run statements and one query in a transaction that is never committed.

    PostgreSQL keeps DDL transactional, so a tamper can be applied, observed
    and discarded without a second container and without leaving residue for
    the next test.  The harness's own query helper wraps a single statement,
    which cannot express "tamper, then ask"; only the psql invocation is
    restated here, and the container, database and superuser come from the
    harness.
    """

    wrapped = (
        "SELECT coalesce(json_agg(row_to_json(probe_result)), '[]'::json) "
        f"FROM ({query}) AS probe_result;"
    )
    script = "BEGIN;\n" + "\n".join(statements) + "\n" + wrapped + "\n"
    process = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container.name,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-q",
            "-t",
            "-A",
            "-U",
            user,
            "-d",
            DATABASE,
        ],
        input=script.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )
    if process.returncode != 0:
        raise GateProbeError(
            "the probe transaction failed: "
            + process.stderr.decode("utf-8", errors="replace")
        )
    lines = [
        line for line in process.stdout.decode("utf-8").splitlines() if line.strip()
    ]
    if not lines:
        raise GateProbeError("the probe transaction returned no rows")
    return json.loads(lines[-1])


def journal_rows(container: PostgresContainer) -> dict[str, dict[str, Any]]:
    rows = container.query(
        "SELECT migration_id, digest_scope, content_hash "
        f"FROM {GATE_SCHEMA}.migration_journal"
    )
    return {row["migration_id"]: row for row in rows}


def verification(container: PostgresContainer) -> dict[str, dict[str, Any]]:
    rows = container.query(f"SELECT * FROM {GATE_SCHEMA}.verify_migration_journal()")
    return {row["journalled_migration_id"]: row for row in rows}


def pending(container: PostgresContainer) -> list[dict[str, Any]]:
    return container.query(
        f"SELECT * FROM {GATE_SCHEMA}.pending_recovery ORDER BY attempt_id"
    )
