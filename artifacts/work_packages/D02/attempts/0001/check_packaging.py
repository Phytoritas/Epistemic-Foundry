#!/usr/bin/env python3
"""Prove the D02 PostgreSQL team-store component's packaging posture is intentional.

Unlike the ``src/`` gates that must reach the built wheel, D02 ships under the
standalone ``python/`` component tree.  That tree is deliberately *outside* the
distribution: ``[tool.setuptools.packages.find] where = ["src"]`` never sweeps
``python/``, so the component is consumed as an in-tree component and must never
leak into the wheel.  This check proves four things rather than assuming them,
and fails closed on any drift:

1. the discovery mode is still ``where = ["src"]`` (read from pyproject, not
   assumed), so a change there is caught here (DISCOVERY_CONFIG_CHANGED);
2. the component carries its ``postgres`` package marker under ``python`` yet is
   genuinely absent from ``src`` -- it must never be shipped
   (COMPONENT_PACKAGING_DRIFT otherwise);
3. the intermediate parents ``epistemic_foundry`` and
   ``epistemic_foundry/storage`` stay marker-free so the component resolves as
   the namespace-package path ``epistemic_foundry.storage.postgres`` rooted at
   ``python`` -- exactly as its own test modules import it with
   ``PYTHONPATH=<repo>/python`` (COMPONENT_PACKAGING_DRIFT otherwise); and
4. the import is exercised for real from that root and the public entrypoint
   ``open_postgres_state_store`` must resolve (COMPONENT_NOT_IMPORTABLE
   otherwise).  The adapter imports the standard library alone, so this import
   pulls in no PostgreSQL driver.
"""

from __future__ import annotations

import importlib
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
COMPONENT_REL = "python/epistemic_foundry/storage/postgres"
IMPORT_ROOT = ROOT / "python"
PACKAGE = "epistemic_foundry.storage.postgres"
ENTRYPOINT = "open_postgres_state_store"
#: Parents that must stay marker-free so the component resolves as the namespace
#: path ``epistemic_foundry.storage.postgres`` rooted at ``python`` (as pytest
#: and the tests resolve it with ``PYTHONPATH=<repo>/python``).
MARKER_FREE_PARENTS = (
    "python",
    "python/epistemic_foundry",
    "python/epistemic_foundry/storage",
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
                      "note": "postgres package marker missing"})
    # It must not have leaked into the shipped src tree.
    if (ROOT / "src/epistemic_foundry/storage/postgres").exists():
        return _fail({"code": "COMPONENT_PACKAGING_DRIFT",
                      "note": "component must not be shipped under src"})
    # Intermediate parents must stay marker-free so the import root is python/.
    leaked = sorted(
        parent for parent in MARKER_FREE_PARENTS
        if (ROOT / parent / "__init__.py").is_file()
    )
    if leaked:
        return _fail({"code": "COMPONENT_PACKAGING_DRIFT",
                      "note": "unexpected package marker on parent", "parents": leaked})

    # Exercise the import exactly as the tests do with PYTHONPATH=<repo>/python.
    inserted = str(IMPORT_ROOT)
    sys.path.insert(0, inserted)
    try:
        module = importlib.import_module(PACKAGE)
    except Exception as error:  # noqa: BLE001 - report any import failure as FAIL
        return _fail({"code": "COMPONENT_NOT_IMPORTABLE", "error": repr(error)})
    finally:
        if sys.path and sys.path[0] == inserted:
            sys.path.pop(0)

    if not callable(getattr(module, ENTRYPOINT, None)):
        return _fail({"code": "COMPONENT_NOT_IMPORTABLE",
                      "note": f"{ENTRYPOINT} is not exported"})

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
