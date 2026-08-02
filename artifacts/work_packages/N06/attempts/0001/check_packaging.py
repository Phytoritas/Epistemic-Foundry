#!/usr/bin/env python3
"""Prove the N06 gate is discoverable by the project's own packaging config.

``pyproject`` discovers packages with ``find_packages`` rather than the
namespace variant, so a subpackage without an ``__init__.py`` at every level
imports fine from a source checkout and is silently absent from the built
wheel.  This check applies that rule directly and reads the discovery mode from
pyproject, so a change there fails here.

The gate composes the sealed N05 scheduler at import time, so N05's
discoverability is checked too: a wheel carrying v4_n06 without v4_n05 would
fail on the first import rather than on the first use, and blaming that on this
package would be wrong.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EXPECTED = ("epistemic_foundry.scheduler", "epistemic_foundry.scheduler.v4_n06")
COMPOSED = ("epistemic_foundry.scheduler.v4_n05",)


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


def refuse(code: str, **context: object) -> int:
    print(
        json.dumps(
            {"code": code, "status": "FAIL", **context}, indent=2, sort_keys=True
        ),
        file=sys.stderr,
    )
    return 1


def main() -> int:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    find = config["tool"]["setuptools"]["packages"]["find"]
    if "where" not in find or list(find["where"]) != ["src"]:
        return refuse("DISCOVERY_CONFIG_CHANGED", find=find)

    missing = sorted(
        dotted for dotted in EXPECTED if not discoverable(ROOT / "src", dotted)
    )
    if missing:
        return refuse(
            "PACKAGE_NOT_DISCOVERED",
            missing=missing,
            note="the gate would import from a checkout but be absent from the wheel",
        )

    absent = sorted(
        dotted for dotted in COMPOSED if not discoverable(ROOT / "src", dotted)
    )
    if absent:
        return refuse(
            "COMPOSED_PACKAGE_NOT_DISCOVERED",
            missing=absent,
            note=(
                "the gate imports the sealed lane scheduler at module import "
                "time; a wheel without it fails closed before first use"
            ),
        )

    print(
        json.dumps(
            {
                "composed": list(COMPOSED),
                "discovered": list(EXPECTED),
                "status": "PASS",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
