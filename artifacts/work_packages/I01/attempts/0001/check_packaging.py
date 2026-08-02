#!/usr/bin/env python3
"""Prove the I01 bounded-Interview component's packaging posture is intentional.

Unlike the ``src/`` gates that must reach the built wheel, I01 ships under the
standalone ``python/`` component tree.  That tree is deliberately *outside* the
distribution: ``[tool.setuptools.packages.find] where = ["src"]`` never sweeps
``python/``, so the component is consumed as an in-tree component and must never
leak into the wheel.  This check proves three things rather than assuming them,
and fails closed on any drift:

1. the discovery mode is still ``where = ["src"]`` (read from pyproject, not
   assumed), so a change there is caught here (DISCOVERY_CONFIG_CHANGED);
2. the component is genuinely absent from ``src`` (it must not be shipped) yet
   present under ``python`` (COMPONENT_PACKAGING_DRIFT otherwise); and
3. the component imports exactly as its own test modules consume it -- the
   ``interview`` package marker exists while no intermediate parent carries an
   ``__init__.py``, so pytest's prepend import mode roots the package at
   ``interview`` with ``intake/`` on ``sys.path``; the import is exercised for
   real and the public entrypoint ``build_interview_plan`` must resolve
   (COMPONENT_NOT_IMPORTABLE otherwise).
"""

from __future__ import annotations

import importlib
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
COMPONENT_REL = "python/epistemic_foundry/intake/interview"
IMPORT_ROOT = ROOT / "python/epistemic_foundry/intake"
PACKAGE = "interview"
#: Parents that must stay marker-free so the component's import root is
#: ``intake/`` and the package is exactly ``interview`` (as pytest resolves it).
MARKER_FREE_PARENTS = (
    "python",
    "python/epistemic_foundry",
    "python/epistemic_foundry/intake",
)


def _fail(payload: dict[str, object]) -> int:
    print(json.dumps({**payload, "status": "FAIL"}, indent=2, sort_keys=True),
          file=sys.stderr)
    return 1


def main() -> int:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    find = config["tool"]["setuptools"]["packages"]["find"]
    if "where" not in find or list(find["where"]) != ["src"]:
        return _fail({"code": "DISCOVERY_CONFIG_CHANGED", "find": find})

    component = ROOT / COMPONENT_REL
    if not (component / "__init__.py").is_file():
        return _fail({"code": "COMPONENT_PACKAGING_DRIFT",
                      "note": "interview package marker missing"})
    # It must not have leaked into the shipped src tree.
    if (ROOT / "src/epistemic_foundry/intake/interview").exists():
        return _fail({"code": "COMPONENT_PACKAGING_DRIFT",
                      "note": "component must not be shipped under src"})
    # Intermediate parents must stay marker-free so the import root is intake/.
    leaked = sorted(
        parent for parent in MARKER_FREE_PARENTS
        if (ROOT / parent / "__init__.py").is_file()
    )
    if leaked:
        return _fail({"code": "COMPONENT_PACKAGING_DRIFT",
                      "note": "unexpected package marker on parent", "parents": leaked})

    # Exercise the import exactly as pytest's prepend mode does for this tree.
    inserted = str(IMPORT_ROOT)
    sys.path.insert(0, inserted)
    try:
        module = importlib.import_module(PACKAGE)
    except Exception as error:  # noqa: BLE001 - report any import failure as FAIL
        return _fail({"code": "COMPONENT_NOT_IMPORTABLE", "error": repr(error)})
    finally:
        if sys.path and sys.path[0] == inserted:
            sys.path.pop(0)

    if not callable(getattr(module, "build_interview_plan", None)):
        return _fail({"code": "COMPONENT_NOT_IMPORTABLE",
                      "note": "build_interview_plan is not exported"})

    print(json.dumps(
        {
            "component": COMPONENT_REL,
            "import_root": IMPORT_ROOT.relative_to(ROOT).as_posix(),
            "package": PACKAGE,
            "shipped_in_wheel": False,
            "status": "PASS",
        },
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
