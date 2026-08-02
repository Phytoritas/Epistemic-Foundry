#!/usr/bin/env python3
"""compatibility-matrix-lint for Z01-0001.

Fail-closed lint of ``manifests/compatibility_matrix.yaml``: the file must parse
as YAML, declare exactly the Z01 sealed-dependency provenance set, and every
declared host row must cite at least one sealed dependency through
``establishing_evidence`` (an uncited row, or a citation that is not a sealed
dependency, is a lint failure).  It reuses the Z01 harness so the lint and the
required-check gates share a single source of truth.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "tests" / "install"))

import z01_matrix_harness as harness  # noqa: E402


def main() -> int:
    matrix = harness.load_matrix()

    declared = {
        dep["package"]: dep["attempt_id"] for dep in matrix["sealed_dependencies"]
    }
    if declared != harness.EXPECTED_SEALED_DEPENDENCIES:
        print(
            "FAIL: sealed_dependencies do not match the declared Z01 dependency set",
            file=sys.stderr,
        )
        print(f"  declared={declared}", file=sys.stderr)
        print(f"  expected={harness.EXPECTED_SEALED_DEPENDENCIES}", file=sys.stderr)
        return 1

    report = harness.row_citation_report(matrix)
    failures = 0
    for host in report["hosts"]:
        if not host["cited_attempts"]:
            print(
                f"FAIL: host '{host['host']}' cites no sealed evidence", file=sys.stderr
            )
            failures += 1
        for entry in host["refusals"]:
            print(
                f"FAIL: host '{host['host']}' citation refused: {entry['code']}",
                file=sys.stderr,
            )
            failures += 1

    if failures:
        print(f"compatibility-matrix-lint: {failures} failure(s)", file=sys.stderr)
        return 1

    print(
        "compatibility-matrix-lint OK: "
        f"{len(matrix['hosts'])} host rows, "
        f"{len(matrix['sealed_dependencies'])} sealed dependencies, "
        "every row sealed-cited"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
