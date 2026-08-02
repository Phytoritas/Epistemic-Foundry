#!/usr/bin/env python3
"""Prove the S06 governance-integration gate is discoverable by packaging.

``src/epistemic_foundry/security`` is an existing package marker (S05 ships
under it) and ``security.v4_s06`` is the new marker this package adds, so there
is a scope decision to prove rather than assume: a marker that never reached the
wheel would let the gate import from a checkout and vanish from an installed
distribution. The discovery mode is read from pyproject instead of assumed, so a
change there fails here.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EXPECTED = ("epistemic_foundry.security", "epistemic_foundry.security.v4_s06")


def discoverable(where: Path, dotted: str) -> bool:
    """``find_packages``' rule: every level must carry an ``__init__.py``.

    The rule is applied directly rather than by importing setuptools, which is a
    build requirement and is absent from the locked runtime environment. The
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
                {"code": "DISCOVERY_CONFIG_CHANGED", "find": find, "status": "FAIL"},
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
                        "the gate would import from a checkout but be absent "
                        "from the wheel"
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
