#!/usr/bin/env python3
"""Build and verify deterministic C02-0004 generated-contract evidence.

C02-0004 projects the active 127 canonical schemas into Python, TypeScript,
and UI artifacts.  The wider Python suite is intentionally not reported as
green: its exact seventeen failures must remain the sealed B04-0009 canonical
projection debt already recorded by C01-0009.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/C02/attempts/0004"
C01_ATTEMPT = ROOT / "artifacts/work_packages/C01/attempts/0009"
ATTEMPT_ID = "C02-0004"
RECORDED_AT = "2026-07-31T09:42:43.358Z"
VERIFICATION = ATTEMPT / "c02-contract-codegen-verification.json"
PYTHON_JUNIT = ATTEMPT / "full-python-regression.junit.xml"
NODE_JUNIT = ATTEMPT / "full-node-regression.junit.xml"
JUNIT_PATHS = {"full_python": PYTHON_JUNIT, "full_node": NODE_JUNIT}
RAW_JUNIT_HASHES = {
    "full_python": "4e2aa15c97911cfae99d6b903dd122d9cb848ee152a2ec9f4fb5b559413ee237",
    "full_node": "b73c0867baa84521eb105c42a2d9b30453937dc985f21af7e6686c7166fed932",
}
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
EXPECTED_SOURCE_HASHES = {
    "packages/contracts/package.json": "faceda59bc5539bc75d13dbc2bb11ba04220164a92e0fb98fc8752f47c108c1b",
    "packages/contracts/codegen/generate.py": "76a1a37e54c3dcb9edab3dfe79f493c475ca779f0d8afeae7409ce894ce8d6b1",
    "packages/contracts/codegen/verify.py": "bb238b970b181382afa820ce98c1e6eca1a409ab87dac10e145dd0c738b054fc",
    "packages/contracts/codegen/cross_language_fixture.mjs": "395344864b15057c8acd16e2b4535e01ba5fa0bcaa1582606804a7ff120b8dff",
    "package.json": "ac644f31a8cec26becb5ddc8402b59895ebb1c73ef06a522c8176ba5aab1d772",
    "package-lock.json": "32d30423475de0cadc8d5fe04802b0833f396d9bb36f78ee156d5a4306f2616a",
}
EXPECTED_GENERATED_HASHES = {
    "packages/contracts/src/generated/contract-manifest.json": "5208eb39b70ab43cd099ee867fa391fc2c218c559302e68a682b1558f6d94ce3",
    "packages/contracts/src/generated/models.d.ts": "36991360e707daa9926bee89fc4b764f74f5925340b133c2fabdf7e537b7e73d",
    "packages/contracts/src/generated/registry.mjs": "df0e395f9f74e5faf18f7d0dd87172694c31e76489dd54b228f3e693ecfee0a4",
    "python/epistemic_foundry/contracts/__init__.py": "29a58cf958579f9a2165222059603ea1c4898d85379473b00872ce237dd92095",
    "python/epistemic_foundry/contracts/contract-manifest.json": "5208eb39b70ab43cd099ee867fa391fc2c218c559302e68a682b1558f6d94ce3",
    "python/epistemic_foundry/contracts/models.py": "3f4207c2c45f7eb10164c570e2a7abd188b513611c0c7fa139cdb4045b59ab7e",
    "python/epistemic_foundry/contracts/py.typed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "web/src/generated/contract-manifest.json": "5208eb39b70ab43cd099ee867fa391fc2c218c559302e68a682b1558f6d94ce3",
    "web/src/generated/contracts.ts": "97c132d169c5385d2af2efc73f0a82683219187ffce7351e15ebcdeb5aa59864",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/C01/attempts/0009/report.json": "48797e915d6a9916bd56710b4b85b65e6cbcd5b6733eb0c9244f0f06162577ed",
    "artifacts/work_packages/C01/attempts/0009/c01-verification.artifact-receipt.json": "5e3bede34ab885cc59a199e32a67daf528d539a67f5d934787e1a8cacbdd1668",
    "manifests/development_manifest.yaml": "6ccf07571c34c9010a10605ba201ba698a09f6343a281565520d392e4c77e063",
}
STALE_FILES_REPAIRED = [
    "packages/contracts/src/generated/contract-manifest.json",
    "packages/contracts/src/generated/models.d.ts",
    "packages/contracts/src/generated/registry.mjs",
    "python/epistemic_foundry/contracts/contract-manifest.json",
    "python/epistemic_foundry/contracts/models.py",
    "web/src/generated/contract-manifest.json",
    "web/src/generated/contracts.ts",
]
PRODUCT_FILES_MODIFIED = ["packages/contracts/codegen/verify.py", *STALE_FILES_REPAIRED]
EVIDENCE_NAMES = (
    "c02-contract-codegen-verification.json",
    "full-regression-impact.json",
    "preexisting-debt-reconciliation.json",
    "dependency-status.json",
    "write-scope-verification.json",
    "junit-normalization-verification.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(name: str, value: dict[str, Any]) -> Path:
    path = ATTEMPT / name
    path.write_text(render(value), encoding="utf-8", newline="\n")
    return path


def assert_hashes(expected: dict[str, str]) -> None:
    for relative, wanted in expected.items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"required C02-0004 file is missing: {relative}")
        actual = sha256(path)
        if actual != wanted:
            raise SystemExit(f"C02-0004 hash mismatch for {relative}: {actual} != {wanted}")


def semantic_junit_signature(text: str) -> list[tuple[Any, ...]]:
    root = ET.fromstring(text)
    rows: list[tuple[Any, ...]] = []
    root_prefixes = (str(ROOT) + "\\", str(ROOT).replace("\\", "/") + "/")
    roots = (str(ROOT), str(ROOT).replace("\\", "/"))
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        message = problem.get("message", "") if problem is not None else ""
        body = (problem.text or "") if problem is not None else ""
        for prefix in root_prefixes:
            message = message.replace(prefix, "")
            body = body.replace(prefix, "")
        for value in roots:
            message = message.replace(value, ".")
            body = body.replace(value, ".")
        rows.append(
            (
                case.get("classname", ""),
                case.get("name", ""),
                problem.tag if problem is not None else "",
                problem.get("type", "") if problem is not None else "",
                message,
                body,
                case.find("skipped") is not None,
            )
        )
    return rows


def normalize_junits() -> dict[str, Any]:
    record_path = ATTEMPT / "junit-normalization-verification.json"
    if record_path.is_file():
        record = read_json(record_path)
        for name, path in JUNIT_PATHS.items():
            if record.get("files", {}).get(name, {}).get("normalized_sha256") != sha256_id(path):
                raise SystemExit(f"normalized JUnit changed after recording: {name}")
        verify_junit_portability()
        return record

    files: dict[str, Any] = {}
    root_backslash = str(ROOT) + "\\"
    root_slash = str(ROOT).replace("\\", "/") + "/"
    for name, path in JUNIT_PATHS.items():
        if sha256(path) != RAW_JUNIT_HASHES[name]:
            raise SystemExit(f"raw JUnit hash mismatch: {name}")
        before = path.read_text(encoding="utf-8")
        signature = semantic_junit_signature(before)
        normalized = before
        removed = {
            "duration_comments": 0,
            "hostname_attributes": 0,
            "repository_prefixes": 0,
            "time_attributes": 0,
            "timestamp_attributes": 0,
        }
        for prefix in (root_backslash, root_slash):
            count = normalized.count(prefix)
            normalized = normalized.replace(prefix, "")
            removed["repository_prefixes"] += count
        for value in (str(ROOT), str(ROOT).replace("\\", "/")):
            count = normalized.count(value)
            normalized = normalized.replace(value, ".")
            removed["repository_prefixes"] += count
        if name == "full_node":
            normalized, removed["duration_comments"] = re.subn(
                r"\s*<!-- duration_ms [^>]+ -->", "", normalized
            )
        else:
            normalized, removed["timestamp_attributes"] = re.subn(
                r'\s+timestamp="[^"]*"', "", normalized
            )
            normalized, removed["hostname_attributes"] = re.subn(
                r'\s+hostname="[^"]*"', "", normalized
            )
            normalized, removed["time_attributes"] = re.subn(
                r'(<(?:testsuite|testcase)\b[^>]*?)\s+time="[^"]*"', r"\1", normalized
            )
        if semantic_junit_signature(normalized) != signature:
            raise SystemExit(f"JUnit semantic signature changed: {name}")
        path.write_text(normalized, encoding="utf-8", newline="\n")
        files[name] = {
            "raw_sha256": "sha256:" + RAW_JUNIT_HASHES[name],
            "normalized_sha256": sha256_id(path),
            "removed": removed,
            "semantic_signature_preserved": True,
            "testcase_count": len(signature),
        }
    record = {
        "attempt_id": ATTEMPT_ID,
        "files": files,
        "normalization_scope": [
            "remove pytest hostname, timestamp, and suite/testcase time attributes",
            "remove absolute repository prefixes",
            "remove Node duration_ms while retaining authoritative footer counters",
        ],
        "preserved": [
            "testcase identity",
            "failure, error, and skip state",
            "failure type, message, and body after repository-path normalization",
            "Node footer counters",
        ],
        "recorded_at_utc": RECORDED_AT,
        "status": "PASS",
    }
    write_json("junit-normalization-verification.json", record)
    verify_junit_portability()
    return record


def verify_junit_portability() -> None:
    roots = (str(ROOT), str(ROOT).replace("\\", "/"))
    for name, path in JUNIT_PATHS.items():
        text = path.read_text(encoding="utf-8")
        if any(root in text for root in roots):
            raise SystemExit(f"JUnit contains an absolute repository path: {name}")
        if name == "full_node":
            if "duration_ms" in text:
                raise SystemExit("Node JUnit retains volatile duration_ms")
        elif re.search(r'\s+(?:hostname|timestamp|time)="', text):
            raise SystemExit("Python JUnit retains volatile host/time fields")


def pytest_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    cases = list(root.findall(".//testcase"))
    result = {
        "collected": sum(int(row.get("tests", "0")) for row in suites),
        "errors": sum(int(row.get("errors", "0")) for row in suites),
        "failed": sum(int(row.get("failures", "0")) for row in suites),
        "skipped": sum(int(row.get("skipped", "0")) for row in suites),
        "xml_testcase_count": len(cases),
    }
    result["passed"] = result["collected"] - result["errors"] - result["failed"] - result["skipped"]
    result.update(
        {
            "junit": path.relative_to(ROOT).as_posix(),
            "junit_sha256": sha256_id(path),
            "semantic_counter_authority": "pytest_testsuite_attributes",
        }
    )
    return result


def node_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    cases = list(root.findall(".//testcase"))
    footer = {
        key.decode("ascii"): int(value)
        for key, value in NODE_FOOTER_PATTERN.findall(path.read_bytes())
    }
    if set(footer) != {"tests", "pass", "fail", "cancelled", "skipped", "todo"}:
        raise SystemExit("Node JUnit footer is incomplete")
    return {
        "cancelled": footer["cancelled"],
        "collected": footer["tests"],
        "failed": footer["fail"],
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": footer["pass"],
        "semantic_counter_authority": "node_test_footer",
        "skipped": footer["skipped"],
        "todo": footer["todo"],
        "xml_error_count": sum(case.find("error") is not None for case in cases),
        "xml_failure_count": sum(case.find("failure") is not None for case in cases),
        "xml_testcase_count": len(cases),
    }


def normalize_problem(value: str) -> str:
    normalized = value.replace(str(ROOT), "<REPO>").replace(
        str(ROOT).replace("\\", "/"), "<REPO>"
    )
    normalized = re.sub(
        r"[A-Za-z]:[/\\][^\n\r'\"]*?(?=(?:[/\\]tests|[/\\]scripts|\n|\r|'|\"))",
        "<ABSOLUTE_PATH>",
        normalized,
    )
    return re.sub(r"\s+", " ", normalized).strip()


def failure_records(path: Path) -> list[dict[str, Any]]:
    root = ET.parse(path).getroot()
    records: list[dict[str, Any]] = []
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        if problem is None:
            continue
        normalized = {
            "message": normalize_problem(problem.get("message", "")),
            "node_id": f"{case.get('classname', '')}::{case.get('name', '')}",
            "problem_type": problem.get("type", ""),
        }
        records.append({**normalized, "normalized_failure_fingerprint": canonical_hash(normalized)})
    return records


def sorted_failure_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda row: (
            row["node_id"], row["message"], row["problem_type"], row["normalized_failure_fingerprint"]
        ),
    )


def regression_evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    python = pytest_summary(PYTHON_JUNIT)
    node = node_summary(NODE_JUNIT)
    if (
        python["collected"], python["passed"], python["failed"],
        python["errors"], python["skipped"], python["xml_testcase_count"],
    ) != (1073, 1056, 17, 0, 0, 1073):
        raise SystemExit(f"full Python counters changed: {python}")
    if (
        node["collected"], node["passed"], node["failed"], node["cancelled"],
        node["skipped"], node["todo"], node["xml_failure_count"], node["xml_error_count"],
    ) != (819, 819, 0, 0, 0, 0, 0, 0):
        raise SystemExit(f"full Node counters changed: {node}")

    current = failure_records(PYTHON_JUNIT)
    baseline_rows = read_json(C01_ATTEMPT / "full-regression-impact.json")["python_failures"]
    baseline = [
        {
            "message": row["message"],
            "node_id": row["node_id"],
            "normalized_failure_fingerprint": row["normalized_failure_fingerprint"],
            "problem_type": row["problem_type"],
        }
        for row in baseline_rows
    ]
    if len(current) != len(baseline) or sorted_failure_records(current) != sorted_failure_records(baseline):
        raise SystemExit("C02-0004 Python failures differ from sealed C01-0009 baseline")
    failures = [
        {
            **row,
            "affected_runtime_path": "scripts/build/canonical_registry/materialize.py",
            "classification": "EXPECTED_B04_0009_PROJECTION_DEBT",
            "owner": "B04",
            "resolving_attempt": "B04-0009",
        }
        for row in current
    ]
    regression = {
        "attempt_id": ATTEMPT_ID,
        "baseline_attempt": "C01-0009",
        "full_node": node,
        "full_python": python,
        "new_c02_failure_count": 0,
        "python_failures": failures,
        "python_projection_debt_failure_count": len(failures),
        "status": "PASS_WITH_AUTHORIZED_B04_0009_PROJECTION_DEBT",
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }
    debt = {
        "attempt_id": ATTEMPT_ID,
        "c02_owned_failure_count": 0,
        "debts": [
            {
                "classification": "EXPECTED_B04_0009_PROJECTION_DEBT",
                "debt_id": "B04-0009-CANONICAL-PROJECTION-COUNT",
                "exact_failure_record_match": True,
                "failure_count": 17,
                "multiplicity_preserved": True,
                "order_independent_comparison": True,
                "owner": "B04",
                "resolving_attempt": "B04-0009",
            }
        ],
        "repository_fully_green": False,
        "skip_or_xfail_used": False,
        "status": "AUTHORIZED_DOWNSTREAM_DEBT_RECONCILED",
    }
    return regression, debt


def run_json_command(command: list[str]) -> tuple[int, dict[str, Any], str]:
    process = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False,
    )
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"command did not emit JSON: {command}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"command JSON is not an object: {command}")
    return process.returncode, value, process.stderr.strip()


def verify_live_codegen() -> tuple[dict[str, Any], dict[str, Any]]:
    stored = read_json(VERIFICATION)
    with tempfile.TemporaryDirectory(prefix="ef-c02-0004-verify-") as directory:
        output = Path(directory) / "verification.json"
        process = subprocess.run(
            [sys.executable, "-B", "packages/contracts/codegen/verify.py", "--output", str(output)],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        if process.returncode != 0:
            raise SystemExit("live C02 verifier failed: " + process.stdout + process.stderr)
        live = read_json(output)
    if live != stored:
        raise SystemExit("stored C02 verification differs from live inputs")
    if (
        stored.get("status") != "PASS"
        or (stored.get("schema_count"), stored.get("example_count")) != (127, 127)
        or stored.get("generated_file_count") != 9
        or stored.get("codegen_clean_diff", {}).get("status") != "PASS"
        or stored.get("legacy_promotion_value_hits") != []
    ):
        raise SystemExit("C02 verification does not satisfy the 127-contract gate")

    check_exit, check, check_stderr = run_json_command(
        [sys.executable, "-B", "packages/contracts/codegen/generate.py", "--check"]
    )
    fixture_exit, fixture, fixture_stderr = run_json_command(
        ["node", "packages/contracts/codegen/cross_language_fixture.mjs"]
    )
    if check_exit or check.get("status") != "PASS" or check.get("failures") != []:
        raise SystemExit(f"generator clean check failed: {check}; {check_stderr}")
    if fixture_exit or fixture.get("status") != "PASS" or fixture.get("failures") != []:
        raise SystemExit(f"cross-language fixture failed: {fixture}; {fixture_stderr}")
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if npx is None:
        raise SystemExit("npx executable is unavailable")
    tsc = subprocess.run(
        [
            npx, "--yes", "--package", "typescript@5.9.3", "tsc", "--noEmit", "--strict",
            "--target", "ES2022", "--module", "NodeNext", "--moduleResolution", "NodeNext",
            "packages/contracts/src/generated/models.d.ts", "web/src/generated/contracts.ts",
        ],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if tsc.returncode != 0:
        raise SystemExit("TypeScript strict compile failed: " + tsc.stdout + tsc.stderr)
    return stored, {
        "codegen_clean_diff": "PASS",
        "cross_language_fixture_parity": "PASS",
        "typescript_5_9_3_strict_nodenext": "PASS",
    }


def manifest_contract() -> dict[str, Any]:
    raw = yaml.safe_load((ROOT / "manifests/development_manifest.yaml").read_text(encoding="utf-8"))
    packages = raw if isinstance(raw, list) else raw["work_packages"]
    by_id = {row["id"]: row for row in packages}
    c02 = by_id["C02"]
    if len(packages) != 156 or c02["depends_on"] != ["C01"]:
        raise SystemExit("C02 dependency or 156-package manifest cardinality changed")
    expected_scope = [
        "packages/contracts/**", "python/epistemic_foundry/contracts/**", "web/src/generated/**"
    ]
    if c02["write_scope"] != expected_scope:
        raise SystemExit("C02 exact write scope changed")
    if "generated_contract_127_parity" not in c02["required_checks"]:
        raise SystemExit("C02 127-contract required check is missing")
    return {
        "package_count": len(packages),
        "C02": {
            "depends_on": c02["depends_on"],
            "write_scope": c02["write_scope"],
            "required_checks": c02["required_checks"],
            "exit_criteria": c02["exit_criteria"],
        },
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    c01 = read_json(C01_ATTEMPT / "report.json")
    receipt = read_json(C01_ATTEMPT / "c01-verification.artifact-receipt.json")
    if c01.get("status") != "PASS" or receipt.get("status") != "PASS":
        raise SystemExit("C01-0009 dependency is not sealed PASS")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "C01": {
                "attempt_id": "C01-0009",
                "report_sha256": sha256_id(C01_ATTEMPT / "report.json"),
                "receipt_hash": receipt["receipt_hash"],
                "status": "PASS",
            }
        },
        "next_state": {
            "C02-0004": "PASS",
            "B04-0009": "DEPENDENCY_READY",
            "O02-0002": "WAITING_ON_B04_0009",
            "C04-0004": "WAITING_ON_O02_0002_AND_FRESH_PROJECTION",
            "B04-final": "WAITING_ON_C04_0004",
        },
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    allowed = ("packages/contracts/", "python/epistemic_foundry/contracts/", "web/src/generated/")
    violations = [path for path in PRODUCT_FILES_MODIFIED if not path.startswith(allowed)]
    return {
        "approved_scope": [
            "packages/contracts/**", "python/epistemic_foundry/contracts/**",
            "web/src/generated/**", "artifacts/work_packages/C02/** (manifest evidence)",
        ],
        "attempt_id": ATTEMPT_ID,
        "canonical_schema_or_example_change_count": 0,
        "derived_package_snapshot_change_count": 0,
        "dirty_worktree_preserved": True,
        "generated_outputs_changed_only_by_generator": True,
        "product_change_count": len(PRODUCT_FILES_MODIFIED),
        "product_files_modified_by_attempt": PRODUCT_FILES_MODIFIED,
        "reset_clean_stash_commit_push_performed": False,
        "schema_or_test_weakening_count": 0,
        "status": "PASS" if not violations else "FAIL",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": len(violations),
    }


def receipt_document() -> dict[str, Any]:
    names = (
        *EVIDENCE_NAMES,
        "full-python-regression.junit.xml",
        "full-node-regression.junit.xml",
    )
    bindings = {name: sha256_id(ATTEMPT / name) for name in names}
    preimage = {
        "attempt_id": ATTEMPT_ID,
        "artifact_hashes": bindings,
        "dependency_receipt_hash": "sha256:e81903ff8f4fd44c902b7caab028623758a80be90f0175552932be6894c27703",
        "receipt_type": "C02_GENERATED_CONTRACT_PROJECTION",
    }
    return {
        "artifact_hashes": bindings,
        "attempt_id": ATTEMPT_ID,
        "dependency_receipt_hash": preimage["dependency_receipt_hash"],
        "receipt_hash": canonical_hash(preimage),
        "receipt_id": "AR-C02-0004-GENERATED-CONTRACT-PROJECTION",
        "receipt_type": preimage["receipt_type"],
        "status": "PASS",
    }


def review_text(regression: dict[str, Any]) -> str:
    return f"""# C02-0004 generated-contract projection review

Package recommendation: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Assurance limitation: `actor_independence=false`. Fleet and subagents are
forbidden by the active product-owner execution contract, so this is a
procedurally separate primary-session review.

## Contract and generated projection

- The canonical generator projects exactly 127 schemas and 127 matching
  examples into nine generated artifacts across Python, TypeScript, and UI.
- All seven previously stale generated files now match deterministic replay.
  The three manifests are byte-identical, Python exposes 127 models, the
  Node/Python fixture check passes, TypeScript 5.9.3 strict compilation
  passes, and active legacy promotion values are absent.
- Root schemas and examples were not modified by C02-0004. Generated outputs
  were produced by the canonical generator rather than hand editing.

## Regression and boundary

- Full Node: {regression['full_node']['passed']}/{regression['full_node']['collected']}
  PASS with no failure, skip, todo, or cancellation.
- Full Python: {regression['full_python']['passed']} passed and
  {regression['full_python']['failed']} failed. The complete sorted failure
  records, including multiplicity, exactly match sealed C01-0009. They are
  the authorized B04-0009 projection-count debt; C02-owned and new failures
  are zero. The earlier `uv run pytest` collection result was diagnostic-only
  and was replaced by the repository-authoritative `python -B -m pytest` run.

Blocking C02-owned findings: 0. Write-scope violations: 0. C02-0004 may PASS
and B04-0009 becomes dependency-ready. This does not establish fresh package
projection, O02-0002, C04 conformance, final packaging, repository-wide green
status, release readiness, or product completion. `implementation_gate=fail`
and `completion_ready=false` remain.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect C02-0004 scope, C01-0009 dependency, generated outputs, and RAH tail", 0, "PASS"),
        ("C002", "python -B packages/contracts/codegen/generate.py --write", 0, "PASS: seven stale generated projections refreshed"),
        ("C003", "python -B packages/contracts/codegen/generate.py --check", 0, "PASS: nine generated artifacts current"),
        ("C004", "python -B packages/contracts/codegen/verify.py --output <attempt>/c02-contract-codegen-verification.json", 0, "PASS: 127/127 deterministic projection"),
        ("C005", "node packages/contracts/codegen/cross_language_fixture.mjs", 0, "PASS: 127/127 cross-language parity"),
        ("C006", "TypeScript 5.9.3 strict NodeNext compilation", 0, "PASS"),
        ("C007", "complete sorted serial Node suite with JUnit", 0, "PASS: 819/819"),
        ("D001", "uv run --locked pytest --junitxml=<attempt>/full-python-regression.junit.xml", 2, "DIAGNOSTIC_ONLY: console-script import path caused five collection errors; result replaced"),
        ("C008", "python -B -m pytest --junitxml=<attempt>/full-python-regression.junit.xml", 1, "EXPECTED_B04_0009_PROJECTION_DEBT: 1056 passed; exact 17 baseline failure records"),
        ("C009", "Normalize JUnit portability while preserving semantic signatures", 0, "PASS"),
        ("C010", "Primary-session separate adversarial contract review", 0, "PASS: C02-owned blocking findings 0; actor_independence=false"),
        ("C011", "git diff --check", 0, "PASS: whitespace errors 0; existing line-ending advisories only"),
        ("C012", "python -B <attempt>/build_c02_0004_evidence.py build", 0, "PASS when deterministic build completes"),
    ]
    return [
        {
            "command": command,
            "command_id": f"{ATTEMPT_ID}-{identifier}",
            "exit_code": exit_code,
            "recorded_at_utc": RECORDED_AT,
            "result": result,
            "scope": ATTEMPT_ID,
        }
        for identifier, command, exit_code, result in rows
    ]


def artifact_inventory() -> list[dict[str, Any]]:
    names = [
        *EVIDENCE_NAMES,
        "c02-verification.artifact-receipt.json",
        "full-python-regression.junit.xml",
        "full-node-regression.junit.xml",
        "commands.jsonl",
        "review.md",
        "build_c02_0004_evidence.py",
        "c02_0004_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    return [
        {
            "byte_size": (ATTEMPT / name).stat().st_size,
            "path": (ATTEMPT / name).relative_to(ROOT).as_posix(),
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in names
        if (ATTEMPT / name).is_file()
    ]


def report_document(
    verification: dict[str, Any], regression: dict[str, Any], debt: dict[str, Any],
    dependency: dict[str, Any], scope: dict[str, Any], live_checks: dict[str, Any],
    *, rah_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "GENERATED_CONTRACT_PROJECTION_127",
        "canonical_contract": {
            "example_bundle_sha256": verification["example_bundle_sha256"],
            "example_count": 127,
            "schema_bundle_sha256": verification["schema_bundle_sha256"],
            "schema_count": 127,
            "schema_example_one_to_one": True,
            "status": "PASS",
        },
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependency,
        "generated_projection": {
            **live_checks,
            "generated_artifact_hashes": verification["generated_artifact_hashes"],
            "generated_file_count": 9,
            "manifest_parity": verification["manifest_parity"],
            "python_model_count": verification["python_models"]["model_count"],
            "repaired_stale_file_count": len(STALE_FILES_REPAIRED),
            "repaired_stale_files": STALE_FILES_REPAIRED,
            "status": "PASS",
        },
        "global_implementation_gate": "fail",
        "historical_preservation": {
            "C01_0009_preserved": True,
            "C02_0001_through_C02_0003_preserved": True,
            "dirty_worktree_preserved": True,
            "prior_RAH_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "B04-0009",
        "not_claimed": [
            "B04-0009 canonical projection freshness", "O02-0002 PASS",
            "C04-0004 conformance", "final packaging or release readiness",
            "repository-wide green status", "actor-independent certification",
            "completion_ready=true",
        ],
        "output_artifacts": artifact_inventory(),
        "package_status": "PASS",
        "preexisting_debt": debt,
        "regression": regression,
        "review": {
            "actor_independence": False,
            "assurance_limitation": "Primary-session separate review; not external actor-independent certification.",
            "blocking_c02_owned_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "PASS",
        },
        "status": "PASS",
        "work_package_id": "C02",
        "write_scope": scope,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def live_documents() -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    assert_hashes(EXPECTED_SOURCE_HASHES)
    assert_hashes(EXPECTED_GENERATED_HASHES)
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    normalization = normalize_junits()
    verification, live_checks = verify_live_codegen()
    regression, debt = regression_evidence()
    dependency = dependency_status()
    scope = write_scope_verification()
    if scope["status"] != "PASS":
        raise SystemExit("C02-0004 write scope is not PASS")
    manifest_contract()
    documents = {
        "c02-contract-codegen-verification.json": verification,
        "full-regression-impact.json": regression,
        "preexisting-debt-reconciliation.json": debt,
        "dependency-status.json": dependency,
        "write-scope-verification.json": scope,
        "junit-normalization-verification.json": normalization,
    }
    return documents, live_checks, debt


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    documents, live_checks, debt = live_documents()
    for name, document in documents.items():
        if name not in {"c02-contract-codegen-verification.json", "junit-normalization-verification.json"}:
            write_json(name, document)
    receipt = receipt_document()
    write_json("c02-verification.artifact-receipt.json", receipt)
    regression = documents["full-regression-impact.json"]
    (ATTEMPT / "commands.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in command_records()),
        encoding="utf-8", newline="\n",
    )
    (ATTEMPT / "review.md").write_text(review_text(regression), encoding="utf-8", newline="\n")
    write_json(
        "report.json",
        report_document(
            documents["c02-contract-codegen-verification.json"], regression, debt,
            documents["dependency-status.json"], documents["write-scope-verification.json"], live_checks,
        ),
    )
    return verify()


def bind_rah_state(
    *, core_generation: str, core_evidence_id: str, final_closeout_evidence_id: str
) -> dict[str, Any]:
    documents, live_checks, debt = live_documents()
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    rah_state = {
        "completion_ready": False,
        "core_evidence_id": core_evidence_id,
        "core_generation": core_generation,
        "final_closeout_evidence_id": final_closeout_evidence_id,
        "flat_snapshot_content_matches": integrity["flat_snapshot_content_matches"],
        "flat_snapshot_stamps_verified": integrity["flat_snapshot_stamps_verified"],
        "generation_file_hashes_verified": integrity["generation_file_hashes_verified"],
        "implementation_gate": "fail",
        "retained_generation_count": integrity["retained_generation_count"],
        "status": "active",
    }
    write_json(
        "report.json",
        report_document(
            documents["c02-contract-codegen-verification.json"],
            documents["full-regression-impact.json"], debt,
            documents["dependency-status.json"], documents["write-scope-verification.json"],
            live_checks, rah_state=rah_state,
        ),
    )
    return verify()


def verify() -> dict[str, Any]:
    documents, live_checks, debt = live_documents()
    for name, expected in documents.items():
        if read_json(ATTEMPT / name) != expected:
            raise SystemExit(f"stored C02-0004 evidence differs from live inputs: {name}")
    receipt = receipt_document()
    if read_json(ATTEMPT / "c02-verification.artifact-receipt.json") != receipt:
        raise SystemExit("C02-0004 ArtifactReceipt differs from live evidence")
    commands = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in command_records()
    )
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands:
        raise SystemExit("C02-0004 commands differ from deterministic records")
    regression = documents["full-regression-impact.json"]
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(regression):
        raise SystemExit("C02-0004 review differs from deterministic review")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    expected_report = report_document(
        documents["c02-contract-codegen-verification.json"], regression, debt,
        documents["dependency-status.json"], documents["write-scope-verification.json"],
        live_checks, rah_state=rah_state if isinstance(rah_state, dict) else None,
    )
    if report != expected_report:
        raise SystemExit("C02-0004 report differs from live evidence")
    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_contract": "127/127",
        "full_node": "819/819",
        "full_python": "1056 passed; exact 17 B04-0009 debts",
        "generated_file_count": 9,
        "receipt_hash": receipt["receipt_hash"],
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = build() if args.mode == "build" else verify()
    print(render(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
