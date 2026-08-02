#!/usr/bin/env python3
"""Prove the K05 boundaries are discoverable by the project's own packaging config.

Unlike S05 and L05, this package introduced a *new* top-level surface:
``src/epistemic_foundry/evidence`` gained its package marker under
HD-EF4-K05-SCOPE-20260802-001, and ``evidence/v4_k05`` is new here.  A missing
marker at either level would let the boundaries import from a checkout while
being absent from the wheel, so both levels are checked rather than assumed.
The discovery mode itself is read from pyproject instead of hardcoded, so a
change there fails here.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EXPECTED = (
    "epistemic_foundry.evidence",
    "epistemic_foundry.evidence.v4_k05",
)


def discoverable(where: Path, dotted: str) -> bool:
    """``find_packages``' rule: every level must carry an ``__init__.py``.

    The rule is applied directly rather than by importing setuptools, which is
    a build requirement and is absent from the locked runtime environment. The
    discovery mode itself is still read from pyproject rather than assumed.
    """

    current = where
    for part in dotted.split("."):
        current = current / part
        if not (current / "__init__.py").is_file():
            return False
    return True


def main() -> int:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    find = config["tool"]["setuptools"]["packages"]["find"]
    if "where" not in find or list(find["where"]) != ["src"]:
        print(
            json.dumps(
                {
                    "code": "DISCOVERY_CONFIG_CHANGED",
                    "find": find,
                    "status": "FAIL",
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    missing = sorted(
        dotted for dotted in EXPECTED if not discoverable(ROOT / "src", dotted)
    )
    if missing:
        print(
            json.dumps(
                {
                    "code": "PACKAGE_NOT_DISCOVERED",
                    "missing": missing,
                    "note": (
                        "the boundaries would import from a checkout but be "
                        "absent from the wheel"
                    ),
                    "status": "FAIL",
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {"discovered": list(EXPECTED), "status": "PASS"}, indent=2, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
