#!/usr/bin/env python3
"""Migration lint: one transaction, no PUBLIC grant, one deterministic file.

D05 proved these properties inside its schema suite, which means they were only
ever checked when a Docker daemon was available.  A migration that is not a
single transaction is broken whether or not a container can be started, so the
same reading is implemented once here — comment-filtered, exactly as D05 filters
it — and used from two places: this script is the named ``migration-lint``
check, and the D06 schema suite imports :func:`lint` rather than restating it.

Every finding names the property that failed, because "lint failed" tells the
reader nothing about which guarantee they lost.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[5]
DEFAULT_MIGRATION: Final = ROOT / "migrations/v4_d06/0001_archive_migration_gate.sql"
GRANT_TO_PUBLIC: Final = re.compile(r"GRANT\s+[^;]*TO\s+PUBLIC", re.IGNORECASE)


class MigrationLintError(RuntimeError):
    """Typed refusal: the migration file cannot be read at all."""


def statements(text: str) -> list[str]:
    """The non-blank, non-comment lines, in order.

    This is D05's reading: a leading ``--`` line is commentary, so a licence
    header or a rationale block cannot be mistaken for a statement.
    """

    return [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]


def lint(path: Path) -> list[str]:
    """Return one finding per violated property; an empty list is a pass."""

    if not path.is_file():
        raise MigrationLintError(f"missing migration: {path}")
    raw = path.read_bytes()
    text = raw.decode("utf-8")

    findings: list[str] = []
    body = statements(text)
    if not body:
        return ["the migration declares no statements at all"]

    if body[0] != "BEGIN;":
        findings.append(f"the migration does not open with BEGIN; ({body[0]!r})")
    if body[-1] != "COMMIT;":
        findings.append(f"the migration does not end with COMMIT; ({body[-1]!r})")
    if body.count("BEGIN;") != 1:
        findings.append(
            f"the migration opens {body.count('BEGIN;')} transactions, not one"
        )
    if body.count("COMMIT;") != 1:
        findings.append(
            f"the migration commits {body.count('COMMIT;')} times, not once"
        )
    # A migration that can undo part of itself is not one transaction: the
    # server's own abort is the only undo this file is allowed to rely on.
    if "ROLLBACK" in text:
        findings.append("the migration names an explicit undo path")
    if GRANT_TO_PUBLIC.search(text):
        findings.append("the migration grants a privilege to PUBLIC")
    if "REVOKE ALL ON SCHEMA" not in text:
        findings.append("the migration does not revoke its schema from PUBLIC")

    # Determinism of the artifact itself: the file is hashed into receipts, so
    # invisible bytes are part of the contract.
    if not text.endswith("COMMIT;\n"):
        findings.append("the migration does not end with a single COMMIT; line")
    if b"\r" in raw:
        findings.append("the migration carries carriage returns")
    if b"\t" in raw:
        findings.append("the migration carries tab characters")
    if any(byte > 0x7F for byte in raw):
        findings.append("the migration carries non-ASCII bytes")
    trailing = [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if line != line.rstrip()
    ]
    if trailing:
        findings.append(f"the migration has trailing whitespace on lines {trailing}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "migration",
        nargs="?",
        default=str(DEFAULT_MIGRATION),
        help="path to the migration to lint",
    )
    arguments = parser.parse_args()
    try:
        findings = lint(Path(arguments.migration))
    except MigrationLintError as error:
        print(str(error), file=sys.stderr)
        return 2
    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        return 1
    print(f"migration-lint: {len(findings)} findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
