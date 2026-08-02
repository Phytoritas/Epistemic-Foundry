#!/usr/bin/env python3
"""Prove the T05 adapter is discoverable by the project's own packaging config.

Unlike S05, this package needed a new marker: ``src/epistemic_foundry/adapters``
did not previously ship, and its ``__init__.py`` was authorized as a scope
decision under HD-EF4-T05-SCOPE-20260802-001.  Both the new parent package and
the versioned subpackage are checked, because a missing marker at either level
would let the adapter import from a checkout while being absent from the wheel.
The discovery mode is read from pyproject rather than assumed, so a change
there fails here.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EXPECTED = (
    "epistemic_foundry.adapters",
    "epistemic_foundry.adapters.v4_t05",
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
                        "the adapter would import from a checkout but be absent "
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
