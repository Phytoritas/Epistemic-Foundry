#!/usr/bin/env python3
"""Run the D02-0001 PostgreSQL team-store and tenant-isolation checks.

Required checks from manifests/development_manifest.yaml (D02):
``postgres_contract_test`` and ``tenant_isolation_test``.  Each maps to one
component test module under ``python/epistemic_foundry/storage/postgres``:
``postgres_contract_test`` -> ``test_postgres_contract.py`` and
``tenant_isolation_test`` -> ``test_tenant_isolation.py``.  Together the two
modules are the whole component's test surface (there is no third module), so
they are the targeted coverage rather than a subset of it.

Both required checks are real-server executions.  The component test harness
(``conftest.py``) provisions an ephemeral database and dedicated NOSUPERUSER
NOBYPASSRLS runtime roles from an administrator DSN it reads from the
environment variable ``EF_D02_POSTGRES_ADMIN_DSN``; a mock-only run is refused
by the fixture itself.  This runner therefore *requires* that variable to be
present in the environment and passes it through unchanged.  It never prints,
records, or hardcodes the DSN or its password -- the throwaway credential lives
only in the environment, and the receipts record only that each DB check ran
and passed.  The absolute import ``epistemic_foundry.storage.postgres`` resolves
with ``PYTHONPATH=<repo>/python`` (the python/ component tree as root), which the
runner sets for the two DB checks, and each DB check pulls its driver in with
``uv run --with 'psycopg[binary]'``.

The component sits under the standalone ``python/`` tree, carries its own
``postgres`` package marker with namespace-package parents, and lies outside the
repository ``testpaths`` (``tests``), so the repository-wide ``pytest tests``
collection is unchanged by this package; ``packaging-discovery`` proves that
posture is intentional rather than accidental.  ``wire-literal-discipline``
re-runs the repository EF4-I22 literal-drift gate, and ``full-python-suite``,
``full-node-suite`` and ``git-diff-check`` reproduce the repository gate as the
regression surface.

D02 depends on D01 at the manifest layer only; the PostgreSQL adapter imports
the standard library alone (no driver, no D01 code), so there is no
cross-component code surface to regress and the full suites are the honest
regression here.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/D02/attempts/0001"
ATTEMPT_ID = "D02-0001"
COMPONENT = "python/epistemic_foundry/storage/postgres"
ATTEMPT_DIR = "artifacts/work_packages/D02/attempts/0001"
WIRE_LITERAL_TEST = "tests/test_wire_literal_discipline.py"
#: The admin DSN environment variable the D02 fixture reads to provision the
#: ephemeral database and roles.  Required to be present; never hardcoded here.
ADMIN_DSN_ENV = "EF_D02_POSTGRES_ADMIN_DSN"
#: The python/ component tree is the import root for ``epistemic_foundry.*``.
PYTHON_IMPORT_ROOT = ROOT / "python"
# The Node implementation and its ``*.test.mjs`` suites are working-tree content
# swept from the same five bases the sealed python-component templates use; the
# count is measured and pinned so a change to the Node surface is caught here.
EXPECTED_NODE_FILE_COUNT = 136
NODE_BASES = ("adapters", "packages", "plugin_blueprint", "tests", "web")


def write_run_result(name: str, command: list[str], exit_code: int) -> None:
    value = {
        "attempt_id": ATTEMPT_ID,
        "check": name,
        "command": command,
        "exit_code": exit_code,
        "status": "PASS" if exit_code == 0 else "FAIL",
    }
    (ATTEMPT / f"{name}.run.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run(
    name: str,
    command: list[str],
    *,
    junit_from_stdout: Path | None = None,
    env: dict[str, str] | None = None,
) -> int:
    process = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
    )
    (ATTEMPT / f"{name}.stdout.log").write_bytes(process.stdout)
    (ATTEMPT / f"{name}.stderr.log").write_bytes(process.stderr)
    if junit_from_stdout is not None:
        junit_from_stdout.write_bytes(process.stdout)
    write_run_result(name, command, process.returncode)
    return process.returncode


def _pytest(name: str, *targets: str) -> int:
    return run(
        name,
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            *targets,
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / f'{name}.junit.xml'}",
        ],
    )


def _db_pytest(name: str, target: str) -> int:
    """Run a real-server D02 check against the environment-provided admin DSN.

    The DSN is read from ``EF_D02_POSTGRES_ADMIN_DSN`` in the environment and
    passed through unchanged; it is never placed on the command line, printed,
    or written to any receipt.  ``PYTHONPATH`` is set to the python/ component
    tree so the ``epistemic_foundry.storage.postgres`` absolute import resolves,
    and the psycopg driver is supplied transiently with ``--with``.
    """
    if not os.environ.get(ADMIN_DSN_ENV):
        write_run_result(
            name,
            ["uv", "run", "--with", "psycopg[binary]", "python", "-m", "pytest", target],
            3,
        )
        print(
            f"{ADMIN_DSN_ENV} is required in the environment for {name}; "
            "mock-only D02 execution is forbidden",
            file=sys.stderr,
        )
        return 3
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    root = str(PYTHON_IMPORT_ROOT)
    env["PYTHONPATH"] = root if not existing else root + os.pathsep + existing
    return run(
        name,
        [
            "uv",
            "run",
            "--with",
            "psycopg[binary]",
            "python",
            "-B",
            "-m",
            "pytest",
            target,
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / f'{name}.junit.xml'}",
        ],
        env=env,
    )


def postgres_contract_test() -> int:
    return _db_pytest(
        "postgres-contract-test", f"{COMPONENT}/test_postgres_contract.py"
    )


def tenant_isolation_test() -> int:
    return _db_pytest(
        "tenant-isolation-test", f"{COMPONENT}/test_tenant_isolation.py"
    )


def ruff_check() -> int:
    return run(
        "ruff-check", ["uv", "run", "--locked", "ruff", "check", COMPONENT, ATTEMPT_DIR]
    )


def wire_literal_discipline() -> int:
    return _pytest("wire-literal-discipline", WIRE_LITERAL_TEST)


def packaging_discovery() -> int:
    return run(
        "packaging-discovery",
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            f"{ATTEMPT_DIR}/check_packaging.py",
        ],
    )


def python_full() -> int:
    return run(
        "full-python-suite",
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            "tests",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / 'full-python-suite.junit.xml'}",
        ],
    )


def node_full() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / name for name in NODE_BASES)
        if base.is_dir()
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    (ATTEMPT / "node-test-inventory.json").write_text(
        json.dumps(
            {
                "attempt_id": ATTEMPT_ID,
                "count": len(files),
                "expected": EXPECTED_NODE_FILE_COUNT,
                "files": files,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if len(files) != EXPECTED_NODE_FILE_COUNT:
        write_run_result(
            "full-node-suite", ["node", "--test", "<inventory-rejected>"], 2
        )
        print(
            f"expected {EXPECTED_NODE_FILE_COUNT} Node test files, found {len(files)}",
            file=sys.stderr,
        )
        return 2
    node = shutil.which("node")
    if node is None:
        write_run_result("full-node-suite", ["node", "--test", *files], 127)
        return 127
    return run(
        "full-node-suite",
        [node, "--test", "--test-concurrency=1", "--test-reporter=junit", *files],
        junit_from_stdout=ATTEMPT / "full-node-suite.junit.xml",
    )


def diff_check() -> int:
    return run("git-diff-check", ["git", "diff", "--check"])


def main() -> int:
    parser = argparse.ArgumentParser()
    checks = {
        "postgres-contract-test": postgres_contract_test,
        "tenant-isolation-test": tenant_isolation_test,
        "ruff-check": ruff_check,
        "wire-literal-discipline": wire_literal_discipline,
        "packaging-discovery": packaging_discovery,
        "full-python-suite": python_full,
        "full-node-suite": node_full,
        "git-diff-check": diff_check,
    }
    parser.add_argument("check", choices=tuple(checks))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return checks[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
