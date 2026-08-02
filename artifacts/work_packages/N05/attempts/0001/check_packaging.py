#!/usr/bin/env python3
"""Prove the N05 scheduler is discoverable by the project's own packaging config.

Without ``src/epistemic_foundry/scheduler/__init__.py`` the scheduler imports
from a source checkout but is silently absent from the built wheel, because
pyproject discovers packages with ``find_packages`` rather than the namespace
variant.  That marker was authorized separately
(HD-EF4-N05-SCOPE-20260802-001); this check proves it is present and effective
rather than assuming it, and reads the discovery mode from pyproject so a change
there fails here.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EXPECTED = ("epistemic_foundry.scheduler", "epistemic_foundry.scheduler.v4_n05")


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
                        "the scheduler would import from a checkout but be "
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

    binding = ROOT / "src/epistemic_foundry/scheduler/v4_n05/lane-phase-binding.json"
    if not binding.is_file():
        print(
            json.dumps(
                {
                    "code": "PACKAGE_DATA_MISSING",
                    "missing": [binding.relative_to(ROOT).as_posix()],
                    "note": (
                        "the lane phase binding is data the scheduler reads at "
                        "runtime; a wheel without it fails closed on first use"
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
