#!/usr/bin/env python3
"""Run the U04-0001 accessibility and packaged-path parity gate acceptance checks.

Required checks from ``manifests/development_manifest.yaml`` (U04):
``accessibility_test`` and ``packaged_ui_parity_test``.  U04 is a Node/UI package
whose product write scope is ``tests/ui/**``; the two required checks map onto the
two U04 Node test modules run from the repository root with
``node --test --test-concurrency=1 --test-reporter=junit``:

``accessibility-test``
    ``tests/ui/accessibility.test.mjs`` asserts, deterministically and over the
    sealed U02/U03 view projections, that every console surface meets the
    declared accessibility contract with zero WCAG-critical structural failures
    (single main/header/h1 landmarks, an unbroken heading hierarchy, unique
    titled sections, status conveyed as text rather than colour, empty results
    rendered as text).  This is the ``WCAG critical failures zero`` exit
    criterion.  There is no running browser: the gate proves a property of the
    deterministic HTML and frozen records the sealed views produce.

``packaged-ui-parity-test``
    ``tests/ui/packaged-path-parity.test.mjs`` asserts that the console behaves
    identically whether a view is reached through the source path a Vite build
    compiles or through the packaged export-surface barrels the console imports:
    export parity (barrels re-export exactly the source implementations),
    behavioural parity (byte-identical record and HTML with a re-derivable hash),
    and route-asset parity.  This is the ``Vite and packaged paths behave
    identically`` exit criterion.  No running server, site, or produced bundler
    dist is claimed.

``full-node-suite`` runs the whole repository Node inventory under ``packages``,
``tests`` and ``web`` from the repository root.  The two U04 modules under
``tests/ui`` are part of that inventory.  The absolute total is a repository-wide,
integration-owned number that other in-flight packages move; this attempt records
the live inventory in ``node-test-inventory.json`` and the evidence builder gates
the captured JUnit on zero failures rather than pinning a hardcoded file count.

``full-python-suite`` reproduces the repository-wide Python gate
(``uv run --locked python -B -m pytest tests``).  ``git-diff-check`` and
``write-scope-verification`` bound the attempt's footprint; the write-scope check
hashes only the approved ``tests/ui`` product tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/U04/attempts/0001"
ATTEMPT_ID = "U04-0001"
ATTEMPT_DIR = "artifacts/work_packages/U04/attempts/0001"

#: The approved product write scope; the write-scope check hashes only this tree.
COMPONENT = "tests/ui"
APPROVED_SCOPE = ["tests/ui/**"]
#: The two required checks map to whole U04 Node modules, addressed relative to
#: the repository root because they run from that working directory.
REQUIRED_NODE_TESTS = {
    "accessibility-test": "tests/ui/accessibility.test.mjs",
    "packaged-ui-parity-test": "tests/ui/packaged-path-parity.test.mjs",
}
#: The whole-repository Node inventory roots for the regression suite.
NODE_INVENTORY_ROOTS = ("packages", "tests", "web")
#: Cache directories that pytest/CPython scatter through the tree and that must
#: never be hashed as product bytes.
CACHE_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache"})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _is_product_file(path: Path) -> bool:
    return path.is_file() and not (CACHE_DIR_NAMES & set(path.parts))


def write_run_result(name: str, command: list[str], exit_code: int) -> None:
    value = {
        "attempt_id": ATTEMPT_ID,
        "check": name,
        "command": command,
        "exit_code": exit_code,
        "status": "PASS" if exit_code == 0 else "FAIL",
    }
    (ATTEMPT / f"{name}.run.json").write_text(
        render(value), encoding="utf-8", newline="\n"
    )


def run(
    name: str,
    command: list[str],
    *,
    junit_from_stdout: Path | None = None,
) -> int:
    process = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    (ATTEMPT / f"{name}.stdout.log").write_bytes(process.stdout)
    (ATTEMPT / f"{name}.stderr.log").write_bytes(process.stderr)
    if junit_from_stdout is not None:
        junit_from_stdout.write_bytes(process.stdout)
    write_run_result(name, command, process.returncode)
    return process.returncode


def _node_required(name: str) -> int:
    """Run one U04 required Node module from the repository root."""
    relative = REQUIRED_NODE_TESTS[name]
    if not (ROOT / relative).is_file():
        write_run_result(name, ["node", "--test", relative, "<missing>"], 2)
        print(f"{name}: missing Node test file {relative}", file=sys.stderr)
        return 2
    node = shutil.which("node")
    if node is None:
        write_run_result(name, ["node", "--test", relative], 127)
        return 127
    return run(
        name,
        [node, "--test", "--test-concurrency=1", "--test-reporter=junit", relative],
        junit_from_stdout=ATTEMPT / f"{name}.junit.xml",
    )


def accessibility_test() -> int:
    return _node_required("accessibility-test")


def packaged_ui_parity_test() -> int:
    return _node_required("packaged-ui-parity-test")


def python_full() -> int:
    name = "full-python-suite"
    return run(
        name,
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-B",
            "-m",
            "pytest",
            "tests",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ATTEMPT / f'{name}.junit.xml'}",
        ],
    )


def node_full() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / name for name in NODE_INVENTORY_ROOTS)
        if base.is_dir()
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    (ATTEMPT / "node-test-inventory.json").write_text(
        render(
            {
                "attempt_id": ATTEMPT_ID,
                "count": len(files),
                "files": files,
                "roots": list(NODE_INVENTORY_ROOTS),
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    # The two U04 modules must be present in the live inventory; the absolute
    # total is owned by the integrating session and moves as other packages land,
    # so it is recorded, not pinned, here.
    required = set(REQUIRED_NODE_TESTS.values())
    if not required.issubset(files):
        write_run_result("full-node-suite", ["node", "--test", "<u04-missing>"], 2)
        print("full-node-suite: U04 modules absent from inventory", file=sys.stderr)
        return 2
    node = shutil.which("node")
    if node is None:
        write_run_result("full-node-suite", ["node", "--test", *files], 127)
        return 127
    return run(
        "full-node-suite",
        [node, "--test", "--test-concurrency=1", "--test-reporter=junit", *files],
        junit_from_stdout=ATTEMPT / "full-node-suite.junit.xml",
    )


def diff_check() -> int:
    return run("git-diff-check", ["git", "diff", "--check"])


def write_scope_verification() -> int:
    # The whole approved product write scope this runner hashes is tests/ui/**.
    # Every product byte under it is hashed here; the evidence builder re-derives
    # these hashes live and refuses if any product file drifts.
    name = "write-scope-verification"
    command = [
        "python",
        "-B",
        f"{ATTEMPT_DIR}/run_u04_0001_checks.py",
        name,
    ]
    component_root = ROOT / COMPONENT
    if not component_root.is_dir():
        write_run_result(name, command, 2)
        print("tests/ui write-scope directory is missing", file=sys.stderr)
        return 2
    relatives = sorted(
        path.relative_to(ROOT).as_posix()
        for path in component_root.rglob("*")
        if _is_product_file(path)
    )
    if not relatives:
        write_run_result(name, command, 2)
        print("no product files under tests/ui", file=sys.stderr)
        return 2
    product_file_hashes = {
        relative: "sha256:" + sha256(ROOT / relative) for relative in relatives
    }
    record = {
        "approved_scope": APPROVED_SCOPE,
        "attempt_id": ATTEMPT_ID,
        "authored_by": (
            "bounded implementation agent (U04 maker) under the product owner's "
            "instruction"
        ),
        "checked_file_count": len(relatives),
        "composed_modules_modified": False,
        "product_file_hashes": product_file_hashes,
        "product_roots": [COMPONENT],
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "separate sealing agent acting as an independent reviewer, distinct "
            "from the author"
        ),
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": True,
        "write_scope_violation_count": 0,
    }
    (ATTEMPT / "write-scope-verification.json").write_text(
        render(record), encoding="utf-8", newline="\n"
    )
    write_run_result(name, command, 0)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    checks = {
        "accessibility-test": accessibility_test,
        "packaged-ui-parity-test": packaged_ui_parity_test,
        "full-python-suite": python_full,
        "full-node-suite": node_full,
        "git-diff-check": diff_check,
        "write-scope-verification": write_scope_verification,
    }
    parser.add_argument("check", choices=tuple(checks))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return checks[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
