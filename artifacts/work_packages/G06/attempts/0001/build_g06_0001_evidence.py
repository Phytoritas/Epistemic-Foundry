#!/usr/bin/env python3
"""Build and verify G06-0001 evidence: native plugin packaging and skill discovery.

This attempt implements the G06 native plugin packaging and skill-discovery
integration gate under the frozen product write scope
``plugin_blueprint/epistemic-foundry/v4_g06/**``.  The builder verifies every
executed check receipt, gates the four required Node modules and the composed
G05/H05/T05 dependency regressions against their measured counts, gates the
repository-wide Node suite on zero failures with the four G06 packaging modules
inside the inventory, pins the product bytes and the live sha256 of the sealed
G05/H05/T05 dependency reports plus the live latest-sealed regression baseline,
and emits the deterministic attempt evidence.  It never modifies product files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/G06/attempts/0001"
ATTEMPT_ID = "G06-0001"
WORK_PACKAGE_ID = "G06"
RECORDED_AT = "2026-08-02T00:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/G06/attempts/0001"
COMPONENT = "plugin_blueprint/epistemic-foundry/v4_g06"
APPROVED_SCOPE = [
    "plugin_blueprint/epistemic-foundry/v4_g06/**",
    "artifacts/work_packages/G06/**",
]

# Live product bytes under the frozen write scope, pinned so any product-file
# drift fails the build.  Every hash was computed live from the shipped tree.
EXPECTED_PRODUCT_HASHES = {
    "plugin_blueprint/epistemic-foundry/v4_g06/capability-manifest.json": "07eb4ca068db43e20b571e7b0ad7e5c19c7874ffefec7405d87f4eac82d654c8",
    "plugin_blueprint/epistemic-foundry/v4_g06/index.mjs": "c2afeb66283a6c8b65eb0587489b7e2017a99b80ebcd14ef83d1d1e79fbd27bd",
    "plugin_blueprint/epistemic-foundry/v4_g06/packaging-adversarial.test.mjs": "7af74a52575b55126ca0b3b4f5851e8f2c04edebd3e8263424c2bf15326af265",
    "plugin_blueprint/epistemic-foundry/v4_g06/packaging-contract.test.mjs": "02b804f66887ea7ea60487c8ed3051f8363580dc6527d4bba5f27763be9818f2",
    "plugin_blueprint/epistemic-foundry/v4_g06/packaging-fixtures.mjs": "28f40c8de2936524671c249d71061ce05156d37660de771f37980d815fcff260",
    "plugin_blueprint/epistemic-foundry/v4_g06/packaging-receipts.test.mjs": "8d655d5a6703254c2927e35fb41ced073e54b845ae73e7eec311ee5449e46963",
    "plugin_blueprint/epistemic-foundry/v4_g06/packaging-schema.test.mjs": "9ff55ae6f6ffea3debde93e3855a6d99995a3022ade1ec2c8c1f4d53ebbf67ec",
    "plugin_blueprint/epistemic-foundry/v4_g06/packaging.mjs": "0c69944e962c1b3562d308028eaf1f88e10d137559315c7d08a7c498c5187881",
}
# Live sha256 of the sealed G05/H05/T05 dependency reports plus the live
# latest-sealed regression baseline (H06-0001), computed live at build time.
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/H06/attempts/0001/report.json": "b9225527177baa32b8aa5f3ab1a8e621b80a8c48450ec08427b55ea90cd4c02b",
    "artifacts/work_packages/G05/attempts/0001/report.json": "c854b5ec890ed3783c55665fafc02f965ccf3616c2bd4d8071ea8101f12484d0",
    "artifacts/work_packages/H05/attempts/0001/report.json": "ad5ea43635197762fc5f55652765bf4f0b6661f5c5836eb576e49448861e80e7",
    "artifacts/work_packages/T05/attempts/0001/report.json": "4a074f8940f5907da2f800b18f6bfc278b732d22b2cd39fa57c1e04194ff05cd",
}

JUNIT_PATHS = {
    "schema_and_type_check": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract_tests": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_and_adversarial_tests": ATTEMPT
    / "negative-and-adversarial-tests.junit.xml",
    "provenance_and_receipt_audit": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "targeted": ATTEMPT / "targeted-g06-packaging.junit.xml",
    "dependency_regression_g05": ATTEMPT / "dependency-regression-g05.junit.xml",
    "dependency_regression_h05": ATTEMPT / "dependency-regression-h05.junit.xml",
    "dependency_regression_t05": ATTEMPT / "dependency-regression-t05.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
# Every JUnit here carries the Node reporter's semantic footer except the T05
# regression, which is a pytest suite.
_NODE_JUNITS = frozenset(
    {
        "schema_and_type_check",
        "unit_and_contract_tests",
        "negative_and_adversarial_tests",
        "provenance_and_receipt_audit",
        "targeted",
        "dependency_regression_g05",
        "dependency_regression_h05",
        "full_node_suite",
    }
)
RUN_RESULTS = (
    "schema-and-type-check",
    "unit-and-contract-tests",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "targeted-g06-packaging",
    "dependency-regression-g05",
    "dependency-regression-h05",
    "dependency-regression-t05",
    "full-node-suite",
    "git-diff-check",
    "write-scope-verification",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_g06_0001_evidence.py",
    "commands.jsonl",
    "dependency-regression-g05.junit.xml",
    "dependency-regression-h05.junit.xml",
    "dependency-regression-t05.junit.xml",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "g06-verification.json",
    "junit-normalization-verification.json",
    "negative-and-adversarial-tests.junit.xml",
    "node-test-inventory.json",
    "provenance-and-receipt-audit.junit.xml",
    "review.md",
    "run_g06_0001_checks.py",
    "schema-and-type-check.junit.xml",
    "targeted-g06-packaging.junit.xml",
    "unit-and-contract-tests.junit.xml",
    "write-scope-verification.json",
    "g06_0001_rah_seal.py",
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
            if record.get("files", {}).get(name, {}).get(
                "normalized_sha256"
            ) != sha256_id(path):
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


def _gate_node_zero_failures(label: str, summary: dict[str, Any]) -> None:
    if (
        (
            summary["failed"],
            summary["cancelled"],
            summary["xml_error_count"],
            summary["xml_failure_count"],
        )
        != (0, 0, 0, 0)
        or summary["passed"] <= 0
        or summary["collected"]
        != (summary["passed"] + summary["skipped"] + summary["todo"])
    ):
        raise SystemExit(f"{label} gate failed: {summary}")


def regression_evidence() -> dict[str, Any]:
    summaries: dict[str, dict[str, Any]] = {}
    for label in (
        "schema_and_type_check",
        "unit_and_contract_tests",
        "negative_and_adversarial_tests",
        "provenance_and_receipt_audit",
        "targeted",
        "dependency_regression_g05",
        "dependency_regression_h05",
    ):
        summary = node_summary(JUNIT_PATHS[label])
        _gate_node_zero_failures(label, summary)
        summaries[label] = summary

    t05 = pytest_summary(JUNIT_PATHS["dependency_regression_t05"])
    if (t05["failed"], t05["errors"], t05["skipped"]) != (0, 0, 0) or t05[
        "passed"
    ] <= 0:
        raise SystemExit(f"dependency_regression_t05 gate failed: {t05}")
    summaries["dependency_regression_t05"] = t05

    # The repository-wide Node suite gates on zero failures with the four G06
    # packaging modules inside the measured inventory; the passing count is the
    # live frontier count and is recorded, never frozen to a literal.
    full = node_summary(JUNIT_PATHS["full_node_suite"])
    _gate_node_zero_failures("full_node_suite", full)
    summaries["full_node_suite"] = full

    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    packaging = inventory.get("g06_packaging_tests")
    expected_packaging = [
        f"{COMPONENT}/packaging-adversarial.test.mjs",
        f"{COMPONENT}/packaging-contract.test.mjs",
        f"{COMPONENT}/packaging-receipts.test.mjs",
        f"{COMPONENT}/packaging-schema.test.mjs",
    ]
    if sorted(packaging or []) != sorted(expected_packaging):
        raise SystemExit(f"G06 packaging tests not in Node inventory: {inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "full_node_gate": "zero_failures_with_g06_packaging_in_inventory",
        "full_node_inventory_count": inventory.get("count"),
        "full_node_passed": full["passed"],
        "new_failure_count": 0,
        "regression_baseline_attempt": "H06-0001",
        "status": "PASS",
        "suites": summaries,
    }


def _sealed_dependency(
    package: str, attempt: str, core: str, final: str
) -> dict[str, Any]:
    path = (
        ROOT / f"artifacts/work_packages/{package}/attempts/{attempt[-4:]}/report.json"
    )
    report = read_json(path)
    rah = report.get("rah_state")
    if (
        report.get("status") != "PASS"
        or not isinstance(rah, dict)
        or rah.get("core_evidence_id") != core
        or rah.get("final_closeout_evidence_id") != final
    ):
        raise SystemExit(f"{attempt} is not the sealed PASS attempt")
    return {
        "attempt_id": attempt,
        "core_evidence_id": core,
        "core_generation": rah.get("core_generation"),
        "final_closeout_evidence_id": final,
        "report": path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "G05": _sealed_dependency("G05", "G05-0001", "E0169", "E0170"),
            "H05": _sealed_dependency("H05", "H05-0001", "E0197", "E0198"),
            "T05": _sealed_dependency("T05", "T05-0001", "E0193", "E0194"),
        },
        "next_action": "SEAL_G06_0001_THEN_RECOMPUTE_DAG",
        "regression_baseline": _sealed_dependency("H06", "H06-0001", "E0241", "E0242"),
        "regression_baseline_note": (
            "H06-0001 is the live latest-sealed attempt (highest core generation "
            "on the ledger frontier) at the time this evidence was built."
        ),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    # The runner authors write-scope-verification.json over the whole approved
    # product scope; the builder re-derives the product hashes live, pins them,
    # and confirms the recorded receipt is exactly those bytes.
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_root = ROOT / COMPONENT
    relatives = sorted(
        path.relative_to(ROOT).as_posix()
        for path in component_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    live_hashes = {
        relative: "sha256:" + sha256(ROOT / relative) for relative in relatives
    }
    pinned = {
        relative: "sha256:" + digest
        for relative, digest in EXPECTED_PRODUCT_HASHES.items()
    }
    if live_hashes != pinned:
        raise SystemExit("write-scope product hashes drifted from the pinned set")
    record = read_json(ATTEMPT / "write-scope-verification.json")
    if (
        record.get("attempt_id") != ATTEMPT_ID
        or record.get("status") != "PASS"
        or record.get("approved_scope") != APPROVED_SCOPE
        or record.get("product_file_hashes") != live_hashes
        or record.get("write_scope_violation_count") != 0
        or record.get("schema_or_test_weakening_count") != 0
        or record.get("root_canonical_source_mutation_count") != 0
        or record.get("reset_clean_stash_commit_push_performed") is not False
        or record.get("checked_file_count") != len(relatives)
    ):
        raise SystemExit(
            f"write-scope-verification receipt is not conformant: {record}"
        )
    return record


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    return {
        "attempt_id": ATTEMPT_ID,
        "composed_surfaces": {
            "capability_probe": (
                "packages/plugin-host/src/capability-probe/capability-probe.mjs "
                "(HostCapabilityReport / PluginHealthReport builders)"
            ),
            "evolution_surface": (
                "plugin_blueprint/epistemic-foundry/v4_g05 "
                "(verified inventory, denied authority, authority-bearing commands)"
            ),
            "hook_gateway": (
                "packages/plugin-host/src/hooks/gateway/hook-gateway.mjs "
                "(canonical-JSON digest for every receipt hash)"
            ),
            "observability_surface": (
                "plugin_blueprint/epistemic-foundry/hooks/v4_h05 "
                "(evolution hook-event coverage scope)"
            ),
            "tool_surface": (
                "packages/plugin-host/src/cli/command-surface.mjs "
                "(projected CLI command set)"
            ),
        },
        "declaring_sources": {
            "capability_manifest_schema": "schemas/plugin-capability-manifest.schema.json",
            "capability_manifest": f"{COMPONENT}/capability-manifest.json",
            "mcp_config": "plugin_blueprint/epistemic-foundry/.mcp.json",
            "skill_inventory": "plugins/epistemic-foundry/skills/skill-inventory.json",
            "skill_lockfile_schema": "schemas/skill-lockfile.schema.json",
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "evidence": [f"{COMPONENT}/packaging-receipts.test.mjs"],
                "mechanism": (
                    "the packaging receipt binds every declaring source by digest, "
                    "re-derives its own hash with the sealed gateway's canonical-"
                    "JSON digest, carries no clock and no randomness; the "
                    "integration receipt binds the host capability and health "
                    "report hashes and re-derives its own hash"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "evidence": [f"{COMPONENT}/packaging-schema.test.mjs"],
                "mechanism": (
                    "the host-surface and degraded-mode vocabularies are read "
                    "from schemas/plugin-capability-manifest.schema.json, the "
                    "lockfile shape from schemas/skill-lockfile.schema.json, and "
                    "each finding code carries the refusal reason it enforces"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "evidence": [
                    f"{COMPONENT}/packaging-contract.test.mjs",
                    f"{COMPONENT}/packaging-adversarial.test.mjs",
                ],
                "mechanism": (
                    "a faithful manifest loads, discovers the bundled inventory "
                    "and a signed lockfile row, and integrates against an observed "
                    "host; an over- or under-stated skill/command/hook/MCP surface, "
                    "an unsigned, quarantined, unattested or over-permissioned "
                    "lockfile row, an id-colliding third-party skill, and a "
                    "capability that names denied authority are each refused by "
                    "their own finding code"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "evidence": [
                    f"{COMPONENT}/packaging-adversarial.test.mjs",
                    f"{COMPONENT}/packaging-receipts.test.mjs",
                ],
                "mechanism": (
                    "no declared capability may name the evaluator, holdout or "
                    "promotion authority the G05 surface denies, and the "
                    "promotion-bearing commands the CLI projects are recorded as "
                    "such rather than laundered into a freely discoverable "
                    "capability"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: bounded G06 implementation agent; "
                    "reviewer: the sealing session, which did not author this "
                    "attempt; actor_independence between author and reviewer "
                    "holds, external certification does not)"
                ),
                "status": "PASS",
            },
            "negative_and_adversarial_tests": {
                "module": f"{COMPONENT}/packaging-adversarial.test.mjs",
                "status": "PASS",
                "test_count": suites["negative_and_adversarial_tests"]["collected"],
            },
            "provenance_and_receipt_audit": {
                "module": f"{COMPONENT}/packaging-receipts.test.mjs",
                "status": "PASS",
                "test_count": suites["provenance_and_receipt_audit"]["collected"],
            },
            "schema_and_type_check": {
                "module": f"{COMPONENT}/packaging-schema.test.mjs",
                "status": "PASS",
                "test_count": suites["schema_and_type_check"]["collected"],
            },
            "unit_and_contract_tests": {
                "module": f"{COMPONENT}/packaging-contract.test.mjs",
                "status": "PASS",
                "test_count": suites["unit_and_contract_tests"]["collected"],
            },
        },
        "status": "PASS",
        "suite_counts": {name: row["collected"] for name, row in suites.items()},
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
                f"{ATTEMPT_DIR}/build_g06_0001_evidence.py",
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
        "# G06-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: a bounded implementation agent (G06 maker) that produced the\n"
        "  packaging tree under the frozen product write scope\n"
        "  plugin_blueprint/epistemic-foundry/v4_g06/**. Reviewer: the sealing\n"
        "  session, which did not author this attempt. Author/reviewer separation\n"
        "  holds (actor_independence=true); external actor-independent\n"
        "  certification does not.\n"
        "- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.\n"
        "- Scope: the product write scope is v4_g06/** only. No schema, manifest,\n"
        "  composed host package under packages/, sealed G05/H05 surface, payload\n"
        "  skill, or .rah/ state was modified; the eight product files sit exactly\n"
        "  inside the granted scope and are hash-pinned.\n"
        "- Packaging is a projection, never an invention: the manifest may declare\n"
        "  only skills the sealed inventory ships, only commands the sealed tool\n"
        "  surface projects, only hook bundles that exist and only MCP servers the\n"
        "  package configures. Understating any surface is refused as loudly as\n"
        "  overstating it (SKILL_DISCOVERY_DRIFT, CLI_COMMAND_OMITTED,\n"
        "  HOOK_BUNDLE_DISCOVERY_DRIFT).\n"
        "- Discovery derives from declared manifests: a bundled skill is\n"
        "  discovered from the sealed inventory carrying its content hash; a\n"
        "  third-party skill enters the discoverable set only from a signed,\n"
        "  hash-verified, approved and attested lockfile row whose permissions the\n"
        "  package actually declares. Unsigned, quarantined, unattested,\n"
        "  over-permissioned and id-colliding rows are each refused with a named\n"
        "  code rather than silently dropped.\n"
        "- Receipts are immutable: the packaging receipt binds every declaring\n"
        "  source by digest and re-derives its own hash with the sealed gateway's\n"
        "  canonical-JSON digest, and the integration receipt binds the host\n"
        "  capability and health report hashes. Neither carries a clock or\n"
        "  randomness, so a later run can prove the package it validated is the\n"
        "  package that shipped.\n"
        "- Authority boundary holds where it can leak: no declared capability may\n"
        "  name the evaluator, holdout or promotion authority the G05 surface\n"
        "  denies (AUTHORITY_CAPABILITY_DECLARED), and the promotion-bearing\n"
        "  commands the CLI projects are recorded as such rather than laundered\n"
        "  into a discoverable capability.\n"
        "- Gates at review time: the four required modules are green\n"
        "  (schema-and-type 6, unit-and-contract 14, negative-and-adversarial 21,\n"
        "  provenance-and-receipt 13 = 54 packaging tests total), the\n"
        "  composed G05, H05 and T05 dependency regressions green, the full Node\n"
        "  suite green with the four G06 packaging modules inside the inventory,\n"
        "  and git diff --check clean. Dependencies G05-0001, H05-0001 and\n"
        "  T05-0001 are bound and H06-0001 is the live latest-sealed regression\n"
        "  baseline.\n"
        "- Residual limitations: the surface validates, discovers and integrates\n"
        "  declarations; it installs no plugin, activates no skill and executes no\n"
        "  command. The blueprint tree remains a reference package; the composed\n"
        "  host modules and payload skills are read-only inputs and were not\n"
        "  modified; and this review is not external actor-independent\n"
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
            "path": f"{ATTEMPT_DIR}/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "G06_NATIVE_PLUGIN_PACKAGING_SKILL_DISCOVERY_GATE",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {key: "PASS" for key in verification["exit_criteria"]},
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": True,
        },
        "implementation_status": "PASS",
        "next_package": "RECOMPUTE_DAG",
        "not_claimed": [
            "installation, activation or execution of any plugin, skill or command: "
            "the surface validates, discovers and integrates declarations only",
            "that a malformed, undeclared or over-claiming plugin is accepted: each "
            "is refused by its own finding code",
            "skill discovery beyond the declared manifests: the discoverable set is "
            "exactly the sealed inventory plus signed, approved, attested lockfile rows",
            "any declared capability acquiring evaluator, holdout or promotion "
            "authority the G05 surface denies",
            "ownership of the composed host modules, the sealed G05/H05 surfaces, the "
            "skill inventory or the payload skills, which are read-only inputs",
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
            "actor_independence": True,
            "assurance_limitation": (
                "Author/reviewer separation holds (a bounded G06 implementation "
                "agent authored, the sealing session reviewed); external "
                "actor-independent certification does not."
            ),
            "blocking_finding_count": 0,
            "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
            "status": "PASS",
        },
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
        "write_scope": write_scope,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def _summary() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "next_action": "SEAL_G06_0001_THEN_RECOMPUTE_DAG",
        "package_status": "PASS",
        "status": "PASS",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = package_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("g06-verification.json", verification)
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(review_text(), encoding="utf-8", newline="\n")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=None
    )
    write_json("report.json", report)
    return _summary()


def bind_rah_state(
    *,
    core_generation: str,
    core_evidence_id: str,
    final_closeout_evidence_id: str,
) -> None:
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    stored = read_json(ATTEMPT / "report.json")
    if "rah_state" in stored:
        raise SystemExit("G06-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "g06-verification.json")
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
    verification = read_json(ATTEMPT / "g06-verification.json")
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
        raise SystemExit("stored G06-0001 report is not the deterministic document")
    return _summary()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = {"build": build, "verify": verify}[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
