#!/usr/bin/env python3
"""Run the U02-0001 dashboard shell, auth and health-state acceptance checks.

Required checks from ``manifests/development_manifest.yaml`` (U02):
``ui_security_test`` and ``degraded_state_test``.  U02 is a Node/Web package —
the manifest lists exactly these two checks (not the standard five), so there is
no Python targeted suite and no Ruff gate here.

Each required check maps onto whole U02 Node test modules run from ``web/`` with
``node --test --test-concurrency=1 --test-reporter=junit``:

``ui_security_test``
    ``src/app/shell-schema.test.mjs`` (the frozen local security posture,
    credential-field vocabulary and auth machine the shell reads), plus the two
    adversarial security suites ``src/app/shell-adversarial.test.mjs`` and
    ``src/app/app-adversarial.test.mjs`` (credential material, undeclared auth
    states/transitions and unauthenticated access all refuse).  This is the
    ``loopback auth/CSRF/CSP`` exit criterion.

``degraded_state_test``
    ``src/features/health/health-states.test.mjs`` and
    ``src/app/shell-contract.test.mjs`` (DEGRADED/UNKNOWN as first-class states,
    ``EMPTY_CONFIRMED`` distinct from ``UNAVAILABLE``), plus
    ``src/app/app-contract.test.mjs`` which carries the
    ``EMPTY_CONFIRMED is distinct from UNAVAILABLE`` contract test.  This is the
    ``EMPTY differs from UNAVAILABLE`` exit criterion.

``full-node-suite`` runs the whole repository Node inventory under
``packages/``, ``tests/`` and ``web/`` from the repository root.  Its absolute
total is a repository-wide, integration-owned number that other in-flight
packages move; this attempt captures the JUnit it observes and records the live
inventory in ``node-test-inventory.json`` rather than pinning a hardcoded total
in the runner.  The frozen JUnit is what the evidence builder gates and
re-derives against, so the sealed count is deterministic once captured.

``git-diff-check`` and ``write-scope-verification`` complete the gate.  The
write-scope check hashes only the two approved product trees.
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
ATTEMPT = ROOT / "artifacts/work_packages/U02/attempts/0001"
ATTEMPT_ID = "U02-0001"
ATTEMPT_DIR = "artifacts/work_packages/U02/attempts/0001"
WEB = ROOT / "web"

#: The two required checks map to whole U02 Node modules, addressed relative to
#: ``web/`` because they run from that working directory.
UI_SECURITY_FILES = (
    "src/app/shell-schema.test.mjs",
    "src/app/shell-adversarial.test.mjs",
    "src/app/app-adversarial.test.mjs",
)
DEGRADED_STATE_FILES = (
    "src/features/health/health-states.test.mjs",
    "src/app/shell-contract.test.mjs",
    "src/app/app-contract.test.mjs",
)
#: The whole-repository Node inventory roots for the regression suite.
NODE_INVENTORY_ROOTS = ("packages", "tests", "web")
#: The approved write scope; the write-scope check hashes only these trees.
PRODUCT_ROOTS = ("web/src/app", "web/src/features/health")


def write_run_result(name: str, command: list[str], exit_code: int) -> None:
    value = {
        "attempt_id": ATTEMPT_ID,
        "check": name,
        "command": command,
        "exit_code": exit_code,
        "status": "PASS" if exit_code == 0 else "FAIL",
    }
    (ATTEMPT / f"{name}.run.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run(
    name: str,
    command: list[str],
    *,
    cwd: Path = ROOT,
    junit_from_stdout: Path | None = None,
) -> int:
    process = subprocess.run(
        command,
        cwd=cwd,
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


def _node_web(name: str, files: tuple[str, ...]) -> int:
    """Run whole U02 Node modules from ``web/`` with the JUnit reporter."""
    ordered = sorted(set(files))
    for relative in ordered:
        if not (WEB / relative).is_file():
            write_run_result(name, ["node", "--test", relative, "<missing>"], 2)
            print(f"{name}: missing Node test file web/{relative}", file=sys.stderr)
            return 2
    node = shutil.which("node")
    if node is None:
        write_run_result(name, ["node", "--test", *ordered], 127)
        return 127
    return run(
        name,
        [node, "--test", "--test-concurrency=1", "--test-reporter=junit", *ordered],
        cwd=WEB,
        junit_from_stdout=ATTEMPT / f"{name}.junit.xml",
    )


def ui_security_test() -> int:
    return _node_web("ui-security-test", UI_SECURITY_FILES)


def degraded_state_test() -> int:
    return _node_web("degraded-state-test", DEGRADED_STATE_FILES)


def full_node_suite() -> int:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / name for name in NODE_INVENTORY_ROOTS)
        if base.is_dir()
        for path in base.rglob("*.test.mjs")
        if path.is_file()
    )
    (ATTEMPT / "node-test-inventory.json").write_text(
        json.dumps(
            {
                "attempt_id": ATTEMPT_ID,
                "count": len(files),
                "files": files,
                "roots": list(NODE_INVENTORY_ROOTS),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    # The six U02 modules must be present; the absolute total is owned by the
    # integrating session and moves as other packages land, so it is recorded,
    # not pinned, here.
    required = {f"web/{name}" for name in (*UI_SECURITY_FILES, *DEGRADED_STATE_FILES)}
    if not required.issubset(files):
        write_run_result("full-node-suite", ["node", "--test", "<u02-missing>"], 2)
        print("full-node-suite: U02 modules absent from inventory", file=sys.stderr)
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


def git_diff_check() -> int:
    return run("git-diff-check", ["git", "diff", "--check"])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_scope_verification() -> int:
    name = "write-scope-verification"
    relatives = sorted(
        path.relative_to(ROOT).as_posix()
        for root in PRODUCT_ROOTS
        for path in (ROOT / root).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if not relatives:
        write_run_result(name, ["python", "<hash-product-files>", "<empty>"], 2)
        print(f"{name}: no product files under {PRODUCT_ROOTS}", file=sys.stderr)
        return 2
    record = {
        "approved_scope": ["web/src/app/**", "web/src/features/health/**"],
        "attempt_id": ATTEMPT_ID,
        "product_file_hashes": {
            relative: "sha256:" + sha256(ROOT / relative) for relative in relatives
        },
        "product_roots": list(PRODUCT_ROOTS),
        "status": "PASS",
    }
    (ATTEMPT / f"{name}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    write_run_result(name, ["python", "-B", "<hash-product-files>", *relatives], 0)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    checks = {
        "ui-security-test": ui_security_test,
        "degraded-state-test": degraded_state_test,
        "full-node-suite": full_node_suite,
        "git-diff-check": git_diff_check,
        "write-scope-verification": write_scope_verification,
    }
    parser.add_argument("check", choices=tuple(checks))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return checks[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
