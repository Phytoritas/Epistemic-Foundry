#!/usr/bin/env python3
"""Prove the U05 Evolution Chamber console is discoverable by the packaging config.

``src/epistemic_foundry/console`` and ``console/v4_u05`` are new package markers:
``console`` is created here because the console tree did not exist before U05, and
``console.v4_u05`` is the package the U05 write scope authorizes. A marker that
never reached the wheel would let the console import from a checkout and vanish
from an installed distribution, so the discovery mode is read from pyproject
instead of assumed and every level is checked for its ``__init__.py``.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EXPECTED = ("epistemic_foundry.console", "epistemic_foundry.console.v4_u05")


def discoverable(where: Path, dotted: str) -> bool:
    """``find_packages``' rule: every level must carry an ``__init__.py``."""
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
                        "the console would import from a checkout but be absent "
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
