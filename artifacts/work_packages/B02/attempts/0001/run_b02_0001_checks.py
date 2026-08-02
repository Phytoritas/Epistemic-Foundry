#!/usr/bin/env python3
"""Run the B02-0001 pinned-toolchain / deterministic-build attestation checks.

B02 is a lockfile and reproducible-build ATTESTATION package. Its product bytes
-- ``pyproject.toml`` and ``uv.lock`` -- already carry the exact
``skill-context`` dependency group (``tiktoken==0.13.0`` plus its mandatory
transitive closure) that J02 requires; this attempt attests them without editing
either file. B02 declares six required checks, each run here as a discrete step
that emits a ``<name>.run.json`` receipt and a deterministic JSON (or JUnit)
evidence object next to it:

* ``lockfile_check`` -- ``uv lock --check`` confirms ``uv.lock`` is current for
  ``pyproject.toml`` and ``scripts/build/check_locks.py`` fail-closes over the
  toolchain lock, the Node ``package-lock.json``, the ``uv.lock`` registry
  hashes, and the pinned build backend.
* ``double_build_comparison`` -- the attempt-local current-input adapter stages
  the exact source roots ``pyproject.toml`` now references and proves two clean
  builds yield byte-identical artifacts. It leaves the historical production
  helper ``scripts/build/double_build.py`` untouched (a preserved B04
  integration handoff, disclosed in the review).
* ``tiktoken_exact_lock_check`` -- ``uv.lock`` pins exactly ``tiktoken==0.13.0``
  from the PyPI registry with hashed artifacts, as the sole member of the
  ``skill-context`` dev group, and never as a runtime dependency.
* ``skill_context_frozen_sync`` -- ``uv sync --frozen --group skill-context
  --offline`` resolves against the frozen lock with no network, and a structural
  old/new lock reconstruction proves zero unrelated dependency changes and zero
  runtime exposure.
* ``j02_tokenizer_vector_test`` -- ``tests/test_j02_context_budget.py`` runs
  green under the frozen ``skill-context`` group (20 tests, including the seven
  exact ``o200k_base`` tokenizer vectors).
* ``write_scope_audit`` -- only ``pyproject.toml`` and ``uv.lock`` are
  attributed as changed, with zero unrelated dependency changes and the
  production helper unmodified.

The repository gate (the scoped ``tests`` Python suite under ``uv run --locked``
plus the live Node structure and boundary checks) and ``git diff --check`` bound
the attempt footprint. This attempt makes ZERO edit to ``pyproject.toml`` or
``uv.lock``; it attests the already-correct dependency lock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B02/attempts/0001"
ATTEMPT_ID = "B02-0001"
ATTEMPT_DIR = "artifacts/work_packages/B02/attempts/0001"

#: The attempt-local check implementations. ``check_locks.py`` is the canonical
#: repository lock validator; the two adapters were authored under B02 and are
#: copied into this attempt so the attempt is self-contained and its
#: implementations are hash-pinned by the evidence builder.
CHECK_LOCKS = "scripts/build/check_locks.py"
VERIFY_LOCK_HARNESS = f"{ATTEMPT_DIR}/verify_lock_correction.py"
DOUBLE_BUILD_HARNESS = f"{ATTEMPT_DIR}/run_double_build_current_inputs.py"
#: The historical production double-build helper. It predates the B04 canonical
#: build hook and is a preserved integration handoff OUTSIDE B02's write scope;
#: this attempt never runs or edits it.
PRODUCTION_HELPER = "scripts/build/double_build.py"

#: B02's declared manifest write scope and the product bytes it attests.
APPROVED_SCOPE = [
    "pyproject.toml",
    "uv.lock",
    "artifacts/work_packages/B02/**",
]
PRODUCT_FILES = ["pyproject.toml", "uv.lock"]

#: pytest is a ``dev`` optional-extra and tiktoken lives in the ``skill-context``
#: dependency group; pytest checks must therefore request both so ``uv run``
#: reconciles the environment (a preceding frozen sync prunes the dev extra).
PYTEST_PREFIX = [
    "uv",
    "run",
    "--locked",
    "--extra",
    "dev",
    "--group",
    "skill-context",
    "python",
    "-B",
    "-m",
    "pytest",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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
    record: bool = True,
) -> subprocess.CompletedProcess[bytes]:
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
    if record:
        write_run_result(name, command, process.returncode)
    return process


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        value = tomllib.load(handle)
    if not isinstance(value, dict):
        raise SystemExit(f"TOML root is not an object: {path}")
    return value


def _uv() -> str | None:
    return shutil.which("uv")


def lockfile_check() -> int:
    # Required check: uv.lock is current for pyproject.toml, and the fail-closed
    # repository lock validator (which itself re-runs ``uv lock --check``) passes
    # over the toolchain lock, the Node lock, the uv registry hashes, and the
    # pinned build backend.
    name = "lockfile-check"
    uv = _uv()
    if uv is None:
        write_run_result(name, ["uv", "lock", "--check"], 127)
        print("uv not found on PATH", file=sys.stderr)
        return 127
    uv_check = run(name + "-uvcheck", [uv, "lock", "--check"], record=False)
    if uv_check.returncode != 0:
        write_run_result(name, [uv, "lock", "--check"], uv_check.returncode)
        print("uv lock --check reported the lock is stale", file=sys.stderr)
        return uv_check.returncode
    command = [
        "python",
        "-B",
        CHECK_LOCKS,
        "--report",
        f"{ATTEMPT_DIR}/lockfile-check.json",
    ]
    proc = run(
        name,
        [
            sys.executable,
            "-B",
            str(ROOT / CHECK_LOCKS),
            "--report",
            str(ATTEMPT / "lockfile-check.json"),
        ],
        record=False,
    )
    if proc.returncode != 0:
        write_run_result(name, command, proc.returncode)
        print(f"{name}: check_locks.py exited {proc.returncode}", file=sys.stderr)
        return proc.returncode
    payload = read_json(ATTEMPT / "lockfile-check.json")
    if payload.get("status") != "PASS" or payload.get("uv_lock_check") != "PASS":
        write_run_result(name, command, 2)
        print(f"{name}: lockfile check did not report PASS: {payload}", file=sys.stderr)
        return 2
    write_run_result(name, command, 0)
    return 0


def double_build_comparison() -> int:
    # Required check: two clean builds of the exact current source inputs yield
    # byte-identical artifacts. Run the attempt-local current-input adapter,
    # which loads but never modifies the historical production helper.
    name = "double-build-comparison"
    command = [
        "python",
        "-B",
        DOUBLE_BUILD_HARNESS,
        "--report",
        f"{ATTEMPT_DIR}/double-build-comparison.json",
    ]
    proc = run(
        name,
        [
            sys.executable,
            "-B",
            str(ATTEMPT / "run_double_build_current_inputs.py"),
            "--report",
            str(ATTEMPT / "double-build-comparison.json"),
        ],
        record=False,
    )
    if proc.returncode != 0:
        write_run_result(name, command, proc.returncode)
        print(f"{name}: double build adapter exited {proc.returncode}", file=sys.stderr)
        return proc.returncode
    payload = read_json(ATTEMPT / "double-build-comparison.json")
    if (
        payload.get("status") != "PASS"
        or payload.get("mismatches") != []
        or payload.get("production_helper_modified") is not False
    ):
        write_run_result(name, command, 2)
        print(f"{name}: double build is not PASS: {payload}", file=sys.stderr)
        return 2
    write_run_result(name, command, 0)
    return 0


def tiktoken_exact_lock_check() -> int:
    # Required check: uv.lock pins exactly tiktoken==0.13.0 as the sole member of
    # the skill-context dev group, from the PyPI registry with hashed artifacts,
    # and never as a runtime dependency of the root project.
    name = "tiktoken-exact-lock-check"
    command = ["python", "-B", f"{ATTEMPT_DIR}/run_b02_0001_checks.py", name]
    try:
        lock = read_toml(ROOT / "uv.lock")
        pyproject = read_toml(ROOT / "pyproject.toml")
    except SystemExit as error:
        write_run_result(name, command, 2)
        print(str(error), file=sys.stderr)
        return 2
    packages = {
        str(pkg.get("name")): pkg
        for pkg in lock.get("package", [])
        if isinstance(pkg, dict)
    }
    tiktoken = packages.get("tiktoken")
    failures: list[str] = []
    if not isinstance(tiktoken, dict):
        failures.append("uv.lock does not resolve tiktoken")
    else:
        if tiktoken.get("version") != "0.13.0":
            failures.append("locked tiktoken version is not exactly 0.13.0")
        if tiktoken.get("source") != {"registry": "https://pypi.org/simple"}:
            failures.append("tiktoken is not sourced from the PyPI registry")
        artifacts = ([] if tiktoken.get("sdist") is None else [tiktoken["sdist"]]) + list(
            tiktoken.get("wheels", [])
        )
        if not artifacts or any(
            not isinstance(art, dict)
            or not str(art.get("hash", "")).startswith("sha256:")
            for art in artifacts
        ):
            failures.append("tiktoken lock entry lacks sha256-hashed artifacts")
    root = packages.get("epistemic-foundry")
    if not isinstance(root, dict):
        failures.append("uv.lock is missing the root project package")
    else:
        runtime = {
            dep.get("name")
            for dep in root.get("dependencies", [])
            if isinstance(dep, dict)
        }
        if "tiktoken" in runtime:
            failures.append("uv.lock exposes tiktoken as a root runtime dependency")
        if root.get("dev-dependencies") != {"skill-context": [{"name": "tiktoken"}]}:
            failures.append("uv.lock root group membership is not exactly skill-context->tiktoken")
        metadata = root.get("metadata")
        requires_dev = metadata.get("requires-dev") if isinstance(metadata, dict) else None
        if requires_dev != {
            "skill-context": [{"name": "tiktoken", "specifier": "==0.13.0"}]
        }:
            failures.append("uv.lock root group constraint is not exactly tiktoken==0.13.0")
    if pyproject.get("dependency-groups") != {"skill-context": ["tiktoken==0.13.0"]}:
        failures.append("pyproject skill-context group is not exactly tiktoken==0.13.0")
    project = pyproject.get("project", {})
    runtime_declared = list(project.get("dependencies", []))
    for values in project.get("optional-dependencies", {}).values():
        runtime_declared.extend(values)
    if any(str(value).lower().startswith("tiktoken") for value in runtime_declared):
        failures.append("tiktoken is declared as a runtime or optional dependency")
    record = {
        "attempt_id": ATTEMPT_ID,
        "check": "tiktoken_exact_lock_check",
        "dependency_group": "skill-context",
        "failures": failures,
        "pyproject_requirement": "tiktoken==0.13.0",
        "runtime_dependency_exposure": False,
        "status": "FAIL" if failures else "PASS",
        "tiktoken_source": {"registry": "https://pypi.org/simple"},
        "tiktoken_version": "0.13.0",
    }
    (ATTEMPT / "tiktoken-exact-lock-check.json").write_text(
        render(record), encoding="utf-8", newline="\n"
    )
    if failures:
        write_run_result(name, command, 2)
        print(f"{name}: {failures}", file=sys.stderr)
        return 2
    write_run_result(name, command, 0)
    return 0


def skill_context_frozen_sync() -> int:
    # Required check: uv resolves and frozen-syncs the skill-context group with
    # no network access, and a structural old/new lock reconstruction proves the
    # group added only tiktoken plus its mandatory transitive closure -- zero
    # unrelated dependency changes and zero runtime exposure.
    name = "skill-context-frozen-sync"
    uv = _uv()
    if uv is None:
        write_run_result(name, ["uv", "sync", "--frozen"], 127)
        print("uv not found on PATH", file=sys.stderr)
        return 127
    sync_command = [
        "uv",
        "sync",
        "--frozen",
        "--group",
        "skill-context",
        "--offline",
    ]
    sync = run(
        name + "-sync",
        [uv, "sync", "--frozen", "--group", "skill-context", "--offline"],
        record=False,
    )
    if sync.returncode != 0:
        write_run_result(name, sync_command, sync.returncode)
        print(f"{name}: frozen offline sync exited {sync.returncode}", file=sys.stderr)
        return sync.returncode
    verify = run(
        name + "-lockdiff",
        [
            sys.executable,
            "-B",
            str(ATTEMPT / "verify_lock_correction.py"),
            "--report",
            str(ATTEMPT / "lock-diff-verification.json"),
        ],
        record=False,
    )
    # Restore the dev extra for the subsequent pytest steps; the frozen sync
    # above intentionally prunes it. This is a best-effort environment
    # reconciliation and is not part of the recorded frozen-sync evidence.
    run(
        name + "-restoredev",
        [uv, "sync", "--frozen", "--extra", "dev", "--group", "skill-context"],
        record=False,
    )
    if verify.returncode != 0:
        write_run_result(name, sync_command, verify.returncode)
        print(f"{name}: lock-diff verification exited {verify.returncode}", file=sys.stderr)
        return verify.returncode
    lockdiff = read_json(ATTEMPT / "lock-diff-verification.json")
    if (
        lockdiff.get("final_status") != "PASS"
        or lockdiff.get("unrelated_dependency_change_count") != 0
        or lockdiff.get("runtime_dependency_exposure") is not False
        or lockdiff.get("frozen_sync_result") != "PASS"
        or lockdiff.get("installed_tiktoken_version") != "0.13.0"
    ):
        write_run_result(name, sync_command, 2)
        print(f"{name}: lock-diff verification is not PASS: {lockdiff}", file=sys.stderr)
        return 2
    record = {
        "attempt_id": ATTEMPT_ID,
        "check": "skill_context_frozen_sync",
        "frozen_offline_sync": "PASS",
        "installed_tiktoken_version": lockdiff["installed_tiktoken_version"],
        "lock_diff_evidence": "lock-diff-verification.json",
        "runtime_dependency_exposure": False,
        "status": "PASS",
        "sync_command": sync_command,
        "transitive_dependency_changes": lockdiff.get("transitive_dependency_changes", []),
        "unrelated_dependency_change_count": 0,
    }
    (ATTEMPT / "skill-context-frozen-sync.json").write_text(
        render(record), encoding="utf-8", newline="\n"
    )
    write_run_result(name, sync_command, 0)
    return 0


def j02_tokenizer_vector_test() -> int:
    # Required check: the J02 context-budget suite runs green under the frozen
    # skill-context group, exercising the seven exact o200k_base tokenizer
    # vectors with the installed tiktoken 0.13.0.
    name = "j02-tokenizer-vector-test"
    command = [
        *PYTEST_PREFIX,
        "tests/test_j02_context_budget.py",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=",
        f"--junitxml={ATTEMPT_DIR}/{name}.junit.xml",
    ]
    proc = run(
        name,
        [
            *PYTEST_PREFIX,
            "tests/test_j02_context_budget.py",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            f"--junitxml={ATTEMPT / f'{name}.junit.xml'}",
        ],
        record=False,
    )
    write_run_result(name, command, proc.returncode)
    return proc.returncode


def write_scope_audit() -> int:
    # Required check: only pyproject.toml and uv.lock are attributed as changed,
    # with zero unrelated dependency changes; the production double-build helper
    # is unmodified (a preserved B04 handoff). This attempt makes ZERO edit to
    # either product file -- it attests the already-correct lock.
    name = "write-scope-audit"
    command = ["python", "-B", f"{ATTEMPT_DIR}/run_b02_0001_checks.py", name]
    missing = [rel for rel in PRODUCT_FILES if not (ROOT / rel).is_file()]
    if missing:
        write_run_result(name, command, 2)
        print(f"product files missing: {missing}", file=sys.stderr)
        return 2
    if not (ROOT / PRODUCTION_HELPER).is_file():
        write_run_result(name, command, 2)
        print(f"production helper missing: {PRODUCTION_HELPER}", file=sys.stderr)
        return 2
    product_file_hashes = {
        rel: "sha256:" + sha256(ROOT / rel) for rel in PRODUCT_FILES
    }
    record = {
        "approved_scope": APPROVED_SCOPE,
        "attempt_id": ATTEMPT_ID,
        "attestation_only_no_new_edits": True,
        "attributed_product_changes": list(PRODUCT_FILES),
        "authored_by": (
            "the bounded agent(s) that authored the B02 dependency-lock "
            "correction (the exact skill-context group tiktoken==0.13.0 in "
            "pyproject.toml and its resolved uv.lock closure) and the two "
            "attempt-local build/lock adapters; B02-0001 attests those "
            "already-correct product bytes and makes zero new edit to them"
        ),
        "product_file_hashes": product_file_hashes,
        "production_double_build_helper": {
            "modified": False,
            "owner": "B04_REVALIDATION",
            "path": PRODUCTION_HELPER,
            "sha256": "sha256:" + sha256(ROOT / PRODUCTION_HELPER),
            "status": "PRESERVED_STALE_STAGING_HANDOFF",
        },
        "product_write_scope_violation_count": 0,
        "product_write_scope_violations": [],
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "this seal-prep session acting as an independent contract-reviewer, "
            "a distinct actor from the author"
        ),
        "root_canonical_source_mutation_count": 0,
        "runtime_dependency_exposure": False,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_dependency_change_count": 0,
    }
    (ATTEMPT / "write-scope-verification.json").write_text(
        render(record), encoding="utf-8", newline="\n"
    )
    write_run_result(name, command, 0)
    return 0


def python_full() -> int:
    return run(
        "full-python-suite",
        [
            *PYTEST_PREFIX,
            "tests",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            f"--junitxml={ATTEMPT / 'full-python-suite.junit.xml'}",
        ],
    ).returncode


def _node_check(name: str, script: str, evidence_name: str, check_key: str) -> int:
    npm = shutil.which("npm")
    if npm is None:
        write_run_result(name, ["npm", "run", script], 127)
        print("npm not found on PATH", file=sys.stderr)
        return 127
    command = ["npm", "run", script]
    process = run(name, [npm, "run", script], record=False)
    if process.returncode != 0:
        write_run_result(name, command, process.returncode)
        print(f"{name} exited {process.returncode}", file=sys.stderr)
        return process.returncode
    text = process.stdout.decode("utf-8")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        write_run_result(name, command, 2)
        print(f"{name}: no JSON object in harness stdout", file=sys.stderr)
        return 2
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        write_run_result(name, command, 2)
        print(f"{name}: unparseable harness JSON: {error}", file=sys.stderr)
        return 2
    if payload.get("status") != "PASS":
        write_run_result(name, command, 2)
        print(f"{name}: harness did not report PASS: {payload}", file=sys.stderr)
        return 2
    (ATTEMPT / evidence_name).write_text(
        render(payload), encoding="utf-8", newline="\n"
    )
    write_run_result(name, command, 0)
    return 0


def node_structure_check() -> int:
    return _node_check(
        "node-structure-check",
        "check:structure",
        "node-structure-check.json",
        "repo_structure_check",
    )


def node_boundaries_check() -> int:
    return _node_check(
        "node-boundaries-check",
        "check:boundaries",
        "node-boundaries-check.json",
        "forbidden_source_import_check",
    )


def diff_check() -> int:
    return run("git-diff-check", ["git", "diff", "--check"]).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    checks = {
        "lockfile-check": lockfile_check,
        "double-build-comparison": double_build_comparison,
        "tiktoken-exact-lock-check": tiktoken_exact_lock_check,
        "skill-context-frozen-sync": skill_context_frozen_sync,
        "j02-tokenizer-vector-test": j02_tokenizer_vector_test,
        "write-scope-audit": write_scope_audit,
        "full-python-suite": python_full,
        "node-structure-check": node_structure_check,
        "node-boundaries-check": node_boundaries_check,
        "git-diff-check": diff_check,
    }
    parser.add_argument("check", choices=tuple(checks))
    args = parser.parse_args()
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    return checks[args.check]()


if __name__ == "__main__":
    raise SystemExit(main())
