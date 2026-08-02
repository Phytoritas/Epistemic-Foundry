#!/usr/bin/env python3
"""Build and verify T01-0002 MCP read/planning evidence.

T01-0002 implements the frozen 13-tool MCP surface under
HD-EF4-T01-SG001-20260730-001: canonical catalog and envelope contracts,
provider-neutral Python handlers, stateless STDIO/HTTP framing, plugin-host
adapters, and the declared tests.  This builder verifies the executed checks
and emits the immutable attempt evidence; it never modifies product files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/T01/attempts/0002"
ATTEMPT_ID = "T01-0002"
WORK_PACKAGE_ID = "T01"
RECORDED_AT = "2026-07-31T13:40:00.000Z"

EXPECTED_TARGETED_PYTHON_COUNT = 41
EXPECTED_TARGETED_NODE_COUNT = 15
EXPECTED_PYTHON_COUNT = 1156
EXPECTED_NODE_COUNT = 834
EXPECTED_NODE_FILE_COUNT = 82

DECISION_ID = "HD-EF4-T01-SG001-20260730-001"
DECISION_PATH = (
    ROOT / "artifacts/authority_decisions/HD-EF4-T01-SG001-20260730-001.human-decision.json"
)
EXPECTED_DECISION_HASH = (
    "sha256:1af7bc9c3ed201a81dc5a91790ccad5823abaf063fc7e16ada92e37828b65657"
)
MANIFEST_PATH = ROOT / "manifests/development_manifest.yaml"
EXPECTED_MANIFEST_HASH = (
    "sha256:6ccf07571c34c9010a10605ba201ba698a09f6343a281565520d392e4c77e063"
)
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/E04/report.json": (
        "841dcf60989cfc7ab0eff7be95e1ae721ae18ac513cae653ab6ac8a44942f6c1"
    ),
    "artifacts/work_packages/G04/report.json": (
        "3abe50fc722255bb8f8c2196f133b94425a0b11318423cb756fab614026cf1ea"
    ),
    "artifacts/work_packages/S04/attempts/0005/report.json": (
        "9f088632a014740e6790127e485262013aac823fb6d58c96d3320f378e20a723"
    ),
}
APPROVED_SCOPE_PREFIXES = (
    "contracts/mcp/t01/",
    "plugins/epistemic-foundry/.mcp.json",
    "src/epistemic_foundry/application/",
    "packages/plugin-host/src/mcp/",
    "docs/mcp_transport_contract.md",
    "tests/fixtures/t01_mcp/",
    "tests/mcp/test_t01_",
    "tests/node/t01-",
    "artifacts/work_packages/T01/",
)
SCOPE_DECISION_ID = "HD-EF4-T01-0002-SCOPE-20260731-001"
SCOPE_DECISION_PATH = (
    "artifacts/authority_decisions/"
    "HD-EF4-T01-0002-SCOPE-20260731-001.human-decision.json"
)
EXPECTED_AUTHORIZED_EXTRA_HASHES = {
    "tests/test_wire_literal_discipline.py": (
        "b435c1744d4e939e638329560a883afda991991ed0af7989b1ef6326dfb3ebf6"
    ),
    SCOPE_DECISION_PATH: (
        "96a128f3ca166017aff5aaa5e0bc0923422c3c5df890af9e70d4eb9279a1093e"
    ),
}
REQUIRED_CHECKS = (
    "mcp_schema_test",
    "read_side_effect_test",
    "mcp_tool_catalog_exact_13",
    "mcp_transport_framing_test",
    "mcp_authorization_and_confidentiality_test",
    "mcp_planning_artifact_receipt_test",
    "mcp_schema_resolution_test",
)

JUNIT_PATHS = {
    "targeted_mcp_python": ATTEMPT / "targeted-mcp-python.junit.xml",
    "targeted_mcp_node": ATTEMPT / "targeted-mcp-node.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset({"targeted_mcp_node", "full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "targeted-mcp-python",
    "targeted-mcp-node",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_t01_0002_checks.py",
    "build_t01_0002_evidence.py",
    "t01_0002_rah_seal.py",
    "product-hashes.json",
    "dependency-status.json",
    "t01-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "targeted-mcp-python.junit.xml",
    "targeted-mcp-node.junit.xml",
    "full-python-suite.junit.xml",
    "full-node-suite.junit.xml",
    "commands.jsonl",
    "review.md",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def canonical_hash_excluding(payload: dict[str, Any], field: str) -> str:
    reduced = {key: value for key, value in payload.items() if key != field}
    return sha256_bytes(
        json.dumps(
            reduced,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read JSON {path}: {error}") from error
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
        actual = sha256(path) if path.is_file() else "MISSING"
        if actual != wanted:
            raise SystemExit(f"sealed input changed: {relative}: {actual} != {wanted}")


def check_run(name: str) -> dict[str, Any]:
    value = read_json(ATTEMPT / f"{name}.run.json")
    if (
        value.get("attempt_id") != ATTEMPT_ID
        or value.get("check") != name
        or value.get("exit_code") != 0
        or value.get("status") != "PASS"
        or not isinstance(value.get("command"), list)
    ):
        raise SystemExit(f"required check did not pass: {name}: {value}")
    return value


def semantic_junit_signature(text: str) -> list[tuple[Any, ...]]:
    root = ET.fromstring(text)
    rows: list[tuple[Any, ...]] = []
    prefixes = (str(ROOT) + "\\", str(ROOT).replace("\\", "/") + "/")
    roots = (str(ROOT), str(ROOT).replace("\\", "/"))
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        message = problem.get("message", "") if problem is not None else ""
        body = (problem.text or "") if problem is not None else ""
        for prefix in prefixes:
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


def verify_junit_portability() -> None:
    roots = (str(ROOT), str(ROOT).replace("\\", "/"))
    for name, path in JUNIT_PATHS.items():
        text = path.read_text(encoding="utf-8")
        if any(root in text for root in roots):
            raise SystemExit(f"JUnit contains absolute repository path: {name}")
        if name in _NODE_JUNITS:
            if "duration_ms" in text:
                raise SystemExit(f"Node JUnit retains volatile duration_ms: {name}")
        elif re.search(r'\s+(?:hostname|timestamp|time)="', text):
            raise SystemExit(f"pytest JUnit retains volatile attributes: {name}")


def normalize_junits() -> dict[str, Any]:
    record_path = ATTEMPT / "junit-normalization-verification.json"
    if record_path.is_file():
        record = read_json(record_path)
        for name, path in JUNIT_PATHS.items():
            if record.get("files", {}).get(name, {}).get("normalized_sha256") != sha256_id(
                path
            ):
                raise SystemExit(f"normalized JUnit changed: {name}")
        verify_junit_portability()
        return record

    files: dict[str, Any] = {}
    root_backslash = str(ROOT) + "\\"
    root_slash = str(ROOT).replace("\\", "/") + "/"
    for name, path in JUNIT_PATHS.items():
        before_bytes = path.read_bytes()
        before = before_bytes.decode("utf-8")
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
        if name in _NODE_JUNITS:
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
            raise SystemExit(f"JUnit normalization changed semantics: {name}")
        path.write_text(normalized, encoding="utf-8", newline="\n")
        files[name] = {
            "normalized_sha256": sha256_id(path),
            "raw_sha256": sha256_bytes(before_bytes),
            "removed": removed,
            "semantic_signature_preserved": True,
            "testcase_count": len(signature),
        }
    record = {
        "attempt_id": ATTEMPT_ID,
        "files": files,
        "preserved": [
            "testcase identity and result state",
            "failure type, message, and body after path normalization",
            "Node semantic footer counters",
        ],
        "recorded_at_utc": RECORDED_AT,
        "status": "PASS",
    }
    write_json("junit-normalization-verification.json", record)
    verify_junit_portability()
    return record


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
    result["passed"] = (
        result["collected"] - result["errors"] - result["failed"] - result["skipped"]
    )
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
        raise SystemExit("Node JUnit semantic footer is incomplete")
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


def regression_evidence() -> dict[str, Any]:
    targeted_python = pytest_summary(JUNIT_PATHS["targeted_mcp_python"])
    targeted_node = node_summary(JUNIT_PATHS["targeted_mcp_node"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if (
        targeted_python["collected"],
        targeted_python["passed"],
        targeted_python["failed"],
        targeted_python["errors"],
        targeted_python["skipped"],
    ) != (EXPECTED_TARGETED_PYTHON_COUNT, EXPECTED_TARGETED_PYTHON_COUNT, 0, 0, 0):
        raise SystemExit(f"targeted T01 Python gate failed: {targeted_python}")
    if (
        targeted_node["collected"],
        targeted_node["passed"],
        targeted_node["failed"],
        targeted_node["cancelled"],
        targeted_node["skipped"],
        targeted_node["todo"],
    ) != (EXPECTED_TARGETED_NODE_COUNT, EXPECTED_TARGETED_NODE_COUNT, 0, 0, 0, 0):
        raise SystemExit(f"targeted T01 Node gate failed: {targeted_node}")
    if (
        python["collected"],
        python["passed"],
        python["failed"],
        python["errors"],
        python["skipped"],
    ) != (EXPECTED_PYTHON_COUNT, EXPECTED_PYTHON_COUNT, 0, 0, 0):
        raise SystemExit(f"full Python gate failed: {python}")
    if (
        node["collected"],
        node["passed"],
        node["failed"],
        node["cancelled"],
        node["skipped"],
        node["todo"],
        node["xml_error_count"],
        node["xml_failure_count"],
        node_inventory.get("count"),
    ) != (
        EXPECTED_NODE_COUNT,
        EXPECTED_NODE_COUNT,
        0,
        0,
        0,
        0,
        0,
        0,
        EXPECTED_NODE_FILE_COUNT,
    ):
        raise SystemExit(f"full Node gate failed: {node}; inventory={node_inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "baseline_attempt": "O03-0001",
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 819, "full_python": 1115},
        "status": "PASS",
        "targeted_mcp_node": targeted_node,
        "targeted_mcp_python": targeted_python,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }


def authority_contract() -> dict[str, Any]:
    decision = read_json(DECISION_PATH)
    if (
        decision.get("decision_id") != DECISION_ID
        or decision.get("subject_id") != "T01-SG001"
        or decision.get("authority_role") != "product_owner"
        or decision.get("decision_hash") != EXPECTED_DECISION_HASH
        or canonical_hash_excluding(decision, "decision_hash") != EXPECTED_DECISION_HASH
    ):
        raise SystemExit("T01-SG001 HumanDecision identity or self-hash mismatch")
    if sha256_id(MANIFEST_PATH) != EXPECTED_MANIFEST_HASH:
        raise SystemExit("development manifest changed after T01-0002 authorization")
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    packages = manifest if isinstance(manifest, list) else manifest["work_packages"]
    row = next(entry for entry in packages if entry["id"] == "T01")
    if row.get("depends_on") != ["E04", "G04", "S04"]:
        raise SystemExit("T01 manifest dependencies changed")
    if not set(REQUIRED_CHECKS).issubset(set(row.get("required_checks", []))):
        raise SystemExit("T01 manifest required checks changed")
    scope = set(row.get("write_scope", []))
    for required in (
        "contracts/mcp/t01/tool-catalog.yaml",
        "src/epistemic_foundry/application/mcp_common/**",
        "packages/plugin-host/src/mcp/generated/**",
        "plugins/epistemic-foundry/.mcp.json",
        "docs/mcp_transport_contract.md",
        "artifacts/work_packages/T01/**",
    ):
        if required not in scope:
            raise SystemExit(f"T01 manifest write scope lost {required}")
    return {
        "decision_file_sha256": sha256_id(DECISION_PATH),
        "decision_hash": EXPECTED_DECISION_HASH,
        "decision_id": DECISION_ID,
        "manifest_sha256": EXPECTED_MANIFEST_HASH,
        "package_count": len(packages),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    dependencies: dict[str, Any] = {}
    for package, relative, attempt in (
        ("E04", "artifacts/work_packages/E04/report.json", "E04-0001"),
        ("G04", "artifacts/work_packages/G04/report.json", "G04-0001"),
        ("S04", "artifacts/work_packages/S04/attempts/0005/report.json", "S04-0005"),
    ):
        report = read_json(ROOT / relative)
        status = report.get("package_status") or report.get("status")
        if status != "PASS":
            raise SystemExit(f"{package} dependency is not PASS")
        dependencies[package] = {
            "attempt_id": report.get("attempt_id") or attempt,
            "report": relative,
            "report_sha256": sha256_id(ROOT / relative),
            "status": "PASS",
        }
    return {
        "attempt_id": ATTEMPT_ID,
        "authority": authority_contract(),
        "dependencies": dependencies,
        "next_action": "SEAL_T01_0002_THEN_CONTINUE_DAG",
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    product_hashes = read_json(ATTEMPT / "product-hashes.json")
    if len(product_hashes) != 38:
        raise SystemExit("T01 product hash table cardinality changed")
    for relative, wanted in product_hashes.items():
        if not relative.startswith(APPROVED_SCOPE_PREFIXES):
            raise SystemExit(f"product file outside the approved scope: {relative}")
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else "MISSING"
        if actual != wanted:
            raise SystemExit(f"product file changed: {relative}: {actual} != {wanted}")
    porcelain = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            "contracts/",
            "src/epistemic_foundry/application",
            "packages/plugin-host/src/mcp",
            "plugins/epistemic-foundry/.mcp.json",
            "docs/mcp_transport_contract.md",
            "tests/mcp",
            "tests/fixtures/t01_mcp",
            "tests/node",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    collapsed_roots = ("contracts/", "tests/mcp/", "tests/node/")
    for line in porcelain:
        status, _, path_value = line.partition(" ")
        clean = path_value.strip().strip('"')
        if status.strip() != "??":
            raise SystemExit(f"tracked file modified inside T01 scope roots: {line!r}")
        if not clean.startswith(APPROVED_SCOPE_PREFIXES) and clean not in collapsed_roots:
            raise SystemExit(f"unexpected untracked entry in T01 scope roots: {line!r}")
    for stray in (ROOT / "contracts").rglob("*"):
        if stray.is_file():
            relative = stray.relative_to(ROOT).as_posix()
            if not relative.startswith("contracts/mcp/t01/"):
                raise SystemExit(f"unexpected file inside contracts/: {relative}")
    for stray in (ROOT / "tests" / "mcp").iterdir():
        if stray.is_file() and not (
            stray.name.startswith("test_t01_") and stray.suffix == ".py"
        ):
            raise SystemExit(f"unexpected file inside tests/mcp/: {stray.name}")
    for stray in (ROOT / "tests" / "node").iterdir():
        if stray.is_file() and not (
            stray.name.endswith(".test.mjs")
            and stray.name.startswith(("t01-", "j02-"))
        ):
            raise SystemExit(f"unexpected file inside tests/node/: {stray.name}")
    assert_hashes(EXPECTED_AUTHORIZED_EXTRA_HASHES)
    decision = read_json(ROOT / SCOPE_DECISION_PATH)
    if (
        decision.get("decision_id") != SCOPE_DECISION_ID
        or decision.get("authority_role") != "product_owner"
        or canonical_hash_excluding(decision, "decision_hash")
        != decision.get("decision_hash")
    ):
        raise SystemExit("T01-0002 scope decision identity or self-hash mismatch")
    return {
        "approved_scope_prefixes": list(APPROVED_SCOPE_PREFIXES),
        "attempt_id": ATTEMPT_ID,
        "authorized_out_of_scope_edit": {
            "decision_id": SCOPE_DECISION_ID,
            "decision_sha256": "sha256:"
            + EXPECTED_AUTHORIZED_EXTRA_HASHES[SCOPE_DECISION_PATH],
            "file": "tests/test_wire_literal_discipline.py",
            "file_sha256": "sha256:"
            + EXPECTED_AUTHORIZED_EXTRA_HASHES["tests/test_wire_literal_discipline.py"],
            "nature": "DECLARING_MODULES registry addition only; no guard weakening",
        },
        "git_scope_root_entries": porcelain,
        "product_file_count": len(product_hashes),
        "product_hash_table": "artifacts/work_packages/T01/attempts/0002/product-hashes.json",
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def t01_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "catalog_facts": {
            "planning_tool_count": 4,
            "protocol_version": "2026-07-28",
            "read_tool_count": 9,
            "stateless": True,
            "tool_count": 13,
            "transports": ["stdio", "streamable-http-post-/mcp"],
        },
        "exit_criteria": {
            "authorization_confidentiality_receipts_idempotency_fail_closed": {
                "evidence": [
                    "tests/mcp/test_t01_authorization.py",
                    "tests/mcp/test_t01_planning_artifacts.py",
                    "tests/mcp/test_t01_error_contract.py",
                ],
                "status": "PASS",
            },
            "exact_nine_read_four_planning_tools": {
                "evidence": [
                    "tests/mcp/test_t01_shared_handlers.py",
                    "tests/node/t01-tool-catalog.test.mjs",
                ],
                "status": "PASS",
            },
            "read_tools_side_effect_free": {
                "evidence": ["tests/mcp/test_t01_read_side_effects.py"],
                "status": "PASS",
            },
            "stdio_and_http_share_handlers_and_envelopes": {
                "evidence": [
                    "tests/mcp/test_t01_shared_handlers.py",
                    "tests/node/t01-transport-framing.test.mjs",
                ],
                "status": "PASS",
            },
            "tool_schemas_canonical": {
                "evidence": [
                    "tests/node/t01-schema-resolution.test.mjs",
                    "tests/mcp/test_t01_shared_handlers.py",
                ],
                "status": "PASS",
            },
        },
        "required_checks": {
            "mcp_authorization_and_confidentiality_test": {
                "module": "tests/mcp/test_t01_authorization.py",
                "status": "PASS",
            },
            "mcp_planning_artifact_receipt_test": {
                "module": "tests/mcp/test_t01_planning_artifacts.py",
                "status": "PASS",
            },
            "mcp_schema_resolution_test": {
                "module": "tests/node/t01-schema-resolution.test.mjs",
                "status": "PASS",
            },
            "mcp_schema_test": {
                "module": "tests/mcp/test_t01_shared_handlers.py",
                "status": "PASS",
            },
            "mcp_tool_catalog_exact_13": {
                "module": "tests/node/t01-tool-catalog.test.mjs",
                "status": "PASS",
            },
            "mcp_transport_framing_test": {
                "module": "tests/node/t01-transport-framing.test.mjs",
                "status": "PASS",
            },
            "read_side_effect_test": {
                "module": "tests/mcp/test_t01_read_side_effects.py",
                "status": "PASS",
            },
        },
        "status": "PASS",
        "targeted_test_counts": {
            "node": regression["targeted_mcp_node"]["collected"],
            "python": regression["targeted_mcp_python"]["collected"],
        },
    }


def command_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in RUN_RESULTS:
        value = read_json(ATTEMPT / f"{name}.run.json")
        records.append(
            {
                "attempt_id": ATTEMPT_ID,
                "command": value["command"],
                "exit_code": value["exit_code"],
                "recorded_at_utc": RECORDED_AT,
                "status": value["status"],
                "step": name,
            }
        )
    records.append(
        {
            "attempt_id": ATTEMPT_ID,
            "command": [
                "python",
                "-B",
                "artifacts/work_packages/T01/attempts/0002/build_t01_0002_evidence.py",
                "build",
            ],
            "exit_code": 0,
            "recorded_at_utc": RECORDED_AT,
            "status": "PASS",
            "step": "evidence-build",
        }
    )
    return records


def commands_text() -> str:
    return (
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True)
            for record in command_records()
        )
        + "\n"
    )


def review_text() -> str:
    return (
        "# T01-0002 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- Wire-literal authority (EF4-I22): the thirteen tool names, classes,\n"
        "  capabilities, and schema bindings exist once, in\n"
        "  contracts/mcp/t01/tool-catalog.yaml.  The Python registry loads it,\n"
        "  the plugin-host descriptor table is a generated projection guarded\n"
        "  by a Python parity test, and Node tests resolve every reference to\n"
        "  the exact canonical files.\n"
        "- Frozen decision fidelity: protocol 2026-07-28; stateless STDIO and\n"
        "  Streamable HTTP POST /mcp with no SSE fallback and no session\n"
        "  state; nine PURE_READ plus four DURABLE_PLAN_ARTIFACT tools; exact\n"
        "  shared result/error envelopes self-validated on every call.\n"
        "- Authorization order is enforced and tested: protocol, input schema,\n"
        "  authentication, workspace isolation (EF4-I19), capability, then\n"
        "  confidentiality concealment where denied visibility and absence are\n"
        "  indistinguishable NOT_FOUND answers.\n"
        "- Read honesty (EF4-I23): provider failure maps to UNAVAILABLE and\n"
        "  can never be rendered EMPTY_CONFIRMED; dishonest provider states\n"
        "  (READY without data, EMPTY_CONFIRMED with data or reason) fail\n"
        "  closed as INTERNAL.\n"
        "- Read purity: nine read tools produce zero writes, receipts, or\n"
        "  provider-state drift, including on every failure path; envelope\n"
        "  mutation cannot reach the provider.\n"
        "- Planning integrity: compilation is delegated to domain-owned ports\n"
        "  (no duplicated business logic); artifacts must validate against the\n"
        "  exact canonical schema before persisting; receipts address the\n"
        "  stored canonical bytes; idempotent replay returns the original\n"
        "  receipt and key reuse with a new request conflicts; nothing\n"
        "  executes.\n"
        "- Finding (resolved): the initial descriptor helper required a full\n"
        "  service; it now derives from the catalog alone so generation and\n"
        "  parity checking share one projection.\n"
        "- Finding (resolved): the repository wire-literal guard correctly\n"
        "  failed until the three new contract modules were registered as\n"
        "  declaring sites, and the invariant-label guard rejected a\n"
        "  duplicated EF4 citation in a runtime message.  The registry\n"
        "  addition is the exact edit authorized by\n"
        "  HD-EF4-T01-0002-SCOPE-20260731-001; no guard token, threshold, or\n"
        "  assertion changed, and the citation moved out of the message.\n"
        "- Residual limitations: the Node-to-Python process bridge and the\n"
        "  dispatcher `mcp serve` route are T03 scope, so the registered\n"
        "  .mcp.json entry fails closed at startup; no live read-model,\n"
        "  artifact-store, or compiler binding to production stores is\n"
        "  claimed; this review is not external actor-independent\n"
        "  certification.\n"
    )


def report_document(
    regression: dict[str, Any],
    dependencies: dict[str, Any],
    write_scope: dict[str, Any],
    verification: dict[str, Any],
    *,
    rah_state: dict[str, Any] | None,
) -> dict[str, Any]:
    output_names = [
        name
        for name in OUTPUT_NAMES
        if name != "report.json" and (ATTEMPT / name).is_file()
    ]
    if rah_state is not None:
        output_names.append("rah-core-integrity.json")
    artifacts = [
        {
            "byte_size": (ATTEMPT / name).stat().st_size,
            "path": f"artifacts/work_packages/T01/attempts/0002/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "T01_MCP_READ_PLANNING_IMPLEMENTATION_UNDER_HD_EF4_T01_SG001",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "authorization_workspace_confidentiality_receipts_idempotency_fail_closed": "PASS",
            "exact_nine_read_four_planning_tools_on_protocol_2026_07_28": "PASS",
            "read_tools_side_effect_free": "PASS",
            "stdio_and_http_share_provider_neutral_handlers_and_exact_envelopes": "PASS",
            "tool_schemas_canonical": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "W01-0001",
        "not_claimed": [
            "dispatcher mcp serve route and Node-to-Python bridge (T03 scope)",
            "live read-model, artifact-store, or compiler production bindings",
            "T02 mutating MCP tools",
            "actor-independent certification of this implementation review",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "regression": regression,
        "required_checks": verification["required_checks"],
        "review": {
            "actor_independence": False,
            "assurance_limitation": (
                "Primary-session separate review; not external actor-independent "
                "certification."
            ),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW",
            "status": "PASS",
        },
        "spec_gap_resolution": {
            "authorizing_decision": DECISION_ID,
            "resolved_spec_gap_id": "T01-SG001",
            "t01_0001_preserved_as_immutable_history": True,
        },
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
        "write_scope": write_scope,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = t01_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("t01-verification.json", verification)
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(review_text(), encoding="utf-8", newline="\n")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=None
    )
    write_json("report.json", report)
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "834/834",
        "full_python": "1156/1156",
        "next_action": "SEAL_T01_0002_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_mcp_node": "15/15",
        "targeted_mcp_python": "41/41",
    }


def bind_rah_state(
    *,
    core_generation: str,
    core_evidence_id: str,
    final_closeout_evidence_id: str,
) -> None:
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    stored = read_json(ATTEMPT / "report.json")
    if "rah_state" in stored:
        raise SystemExit("T01-0002 report is already RAH-bound")
    if integrity.get("current_generation") != core_generation:
        raise SystemExit("rah-core-integrity does not match the core generation")
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
    regression = regression_evidence()
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    verification = read_json(ATTEMPT / "t01-verification.json")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=rah_state
    )
    write_json("report.json", report)


def verify() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    stored = read_json(ATTEMPT / "report.json")
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope_live = write_scope_verification()
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    if write_scope_live != write_scope:
        raise SystemExit("write-scope verification drifted from the sealed record")
    verification = read_json(ATTEMPT / "t01-verification.json")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("commands.jsonl differs from deterministic command records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text():
        raise SystemExit("review.md differs from the recorded review")
    expected = report_document(
        regression,
        dependencies,
        write_scope,
        verification,
        rah_state=stored.get("rah_state"),
    )
    if render(expected) != render(stored):
        raise SystemExit("stored T01-0002 report is not the deterministic document")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "834/834",
        "full_python": "1156/1156",
        "next_action": "SEAL_T01_0002_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_mcp_node": "15/15",
        "targeted_mcp_python": "41/41",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = {"build": build, "verify": verify}[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
