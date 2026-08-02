#!/usr/bin/env python3
"""Prove the W05 workflow is discoverable by the project's own packaging config.

``src/epistemic_foundry/recovery`` is a new top-level package for this phase: the
marker was authorized under HD-EF4-W05-SCOPE-20260802-001 and ``v4_w05`` is added
beneath it.  A package that imports from a checkout but is absent from the wheel
fails only at install time, so both levels are checked here rather than assumed.
The discovery mode itself is read from pyproject, so a change there fails here.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EXPECTED = ("epistemic_foundry.recovery", "epistemic_foundry.recovery.v4_w05")


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
                        "the workflow would import from a checkout but be "
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
