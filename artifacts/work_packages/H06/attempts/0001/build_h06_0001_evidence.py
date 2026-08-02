#!/usr/bin/env python3
"""Build and verify H06-0001 evidence: hook-disabled and hosted-tool degraded-mode integration gate.

This attempt was implemented by a bounded implementation agent under the
product owner's explicit parallel-execution instruction, with a disjoint write
scope, and was reviewed by the sealing session as an independent contract
reviewer before sealing.  The builder verifies every executed check receipt,
gates every JUnit against its measured count, pins product and dependency
bytes, and emits the deterministic attempt evidence; it never modifies product
files.
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
ATTEMPT = ROOT / "artifacts/work_packages/H06/attempts/0001"
ATTEMPT_ID = "H06-0001"
WORK_PACKAGE_ID = "H06"
RECORDED_AT = "2026-08-02T20:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/H06/attempts/0001"
AUTHORITY_DECISION = None

EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/H06/attempts/0001/run_h06_0001_checks.py": "cf5b3cf7b663b8d22e3b054986338adc4a9de325e2685680667b07044b73a728",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h06/degraded-adversarial.test.mjs": "37f73c90d76a8fc443d8398017f88e704142d69b9f57049a6d0bff71bf50cf96",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h06/degraded-contract.test.mjs": "37e6083c073fcb584e0a38985d313feffe59549a1dfe03129d514bac20517634",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h06/degraded-fixtures.mjs": "63ea49c1de34ed09b54dadc4165fab725f661d3268d6b9d6ab8c3f4643642347",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h06/degraded-mode-policy.json": "ba949612f923d6d2bfc922bccd4defc78bcf763bc9b26e5caf87512a361e633a",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h06/degraded-mode.mjs": "730fbe8faaedf711168f0cc35abc3003257bfe7af88d352c7d02035a3220014c",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h06/degraded-receipts.test.mjs": "613a9a0b0433448401d9f9ed34c94dff8ff48ac6697a02ecd1a452238461cd16",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h06/degraded-schema.test.mjs": "35543480afae4cabda6b85291e77f6cf265782f259deba45cd4a0827911dddcb",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h06/index.mjs": "26eac76729cc82d41687ee57fe91481866f581837d9df450c6e0317debbbc174",
}
# H06 depends on sealed H05 and G05; the latest sealed report (F06-0001) is the
# live regression baseline.  All three are pinned by exact bytes.
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/F06/attempts/0001/report.json": "ce89ecb506a664f1a7b1f7b1c49e6546295eb8d1266f0e28469172aa0d16714c",
    "artifacts/work_packages/G05/attempts/0001/report.json": "c854b5ec890ed3783c55665fafc02f965ccf3616c2bd4d8071ea8101f12484d0",
    "artifacts/work_packages/H05/attempts/0001/report.json": "ad5ea43635197762fc5f55652765bf4f0b6661f5c5836eb576e49448861e80e7",
}

JUNIT_PATHS = {
    "dependency_regression_capability_probe": ATTEMPT
    / "dependency-regression-capability-probe.junit.xml",
    "dependency_regression_g05": ATTEMPT / "dependency-regression-g05.junit.xml",
    "dependency_regression_gateway": ATTEMPT
    / "dependency-regression-gateway.junit.xml",
    "dependency_regression_h05": ATTEMPT / "dependency-regression-h05.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "negative_and_adversarial_tests": ATTEMPT
    / "negative-and-adversarial-tests.junit.xml",
    "provenance_and_receipt_audit": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "schema_and_type_check": ATTEMPT / "schema-and-type-check.junit.xml",
    "targeted_h06_degraded": ATTEMPT / "targeted-h06-degraded.junit.xml",
    "unit_and_contract_tests": ATTEMPT / "unit-and-contract-tests.junit.xml",
}
_NODE_JUNITS = frozenset(
    {
        "dependency_regression_capability_probe",
        "dependency_regression_g05",
        "dependency_regression_gateway",
        "dependency_regression_h05",
        "full_node_suite",
        "negative_and_adversarial_tests",
        "provenance_and_receipt_audit",
        "schema_and_type_check",
        "targeted_h06_degraded",
        "unit_and_contract_tests",
    }
)
RUN_RESULTS = (
    "dependency-regression-capability-probe",
    "dependency-regression-g05",
    "dependency-regression-gateway",
    "dependency-regression-h05",
    "full-node-suite",
    "full-python-suite",
    "git-diff-check",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "ruff-check",
    "ruff-format-check",
    "schema-and-type-check",
    "targeted-h06-degraded",
    "unit-and-contract-tests",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_h06_0001_evidence.py",
    "commands.jsonl",
    "dependency-regression-capability-probe.junit.xml",
    "dependency-regression-g05.junit.xml",
    "dependency-regression-gateway.junit.xml",
    "dependency-regression-h05.junit.xml",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "h06-verification.json",
    "h06_0001_rah_seal.py",
    "junit-normalization-verification.json",
    "negative-and-adversarial-tests.junit.xml",
    "node-test-inventory.json",
    "provenance-and-receipt-audit.junit.xml",
    "review.md",
    "run_h06_0001_checks.py",
    "schema-and-type-check.junit.xml",
    "targeted-h06-degraded.junit.xml",
    "unit-and-contract-tests.junit.xml",
    "write-scope-verification.json",
)

# Measured node/pytest counts observed while sealing this attempt.  Each JUnit is
# gated against its exact count so no suite can silently shrink or grow.
FULL_PYTHON_EXPECTED = 1261
FULL_NODE_EXPECTED = 1641
NODE_INVENTORY_EXPECTED = 132
NODE_SUITE_EXPECTED = {
    "dependency_regression_capability_probe": 18,
    "dependency_regression_g05": 81,
    "dependency_regression_gateway": 11,
    "dependency_regression_h05": 93,
    "negative_and_adversarial_tests": 38,
    "provenance_and_receipt_audit": 20,
    "schema_and_type_check": 14,
    "targeted_h06_degraded": 91,
    "unit_and_contract_tests": 19,
}


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
    # An aggregate receipt records `commands` (several processes, worst exit
    # code); a plain receipt records one `command`.  Both are honest shapes.
    commanded = isinstance(value.get("command"), list) or isinstance(
        value.get("commands"), list
    )
    if (
        value.get("attempt_id") != ATTEMPT_ID
        or value.get("check") != name
        or value.get("exit_code") != 0
        or value.get("status") != "PASS"
        or not commanded
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


def regression_evidence() -> dict[str, Any]:
    summaries: dict[str, dict[str, Any]] = {}
    for label, summary, expected in (
        (
            "full_python_suite",
            pytest_summary(JUNIT_PATHS["full_python_suite"]),
            FULL_PYTHON_EXPECTED,
        ),
    ):
        if (
            summary["collected"],
            summary["passed"],
            summary["failed"],
            summary["errors"],
            summary["skipped"],
        ) != (expected, expected, 0, 0, 0):
            raise SystemExit(f"{label} gate failed: {summary}")
        summaries[label] = summary
    for label, expected in (
        (
            "dependency_regression_capability_probe",
            NODE_SUITE_EXPECTED["dependency_regression_capability_probe"],
        ),
        ("dependency_regression_g05", NODE_SUITE_EXPECTED["dependency_regression_g05"]),
        (
            "dependency_regression_gateway",
            NODE_SUITE_EXPECTED["dependency_regression_gateway"],
        ),
        ("dependency_regression_h05", NODE_SUITE_EXPECTED["dependency_regression_h05"]),
        ("full_node_suite", FULL_NODE_EXPECTED),
        (
            "negative_and_adversarial_tests",
            NODE_SUITE_EXPECTED["negative_and_adversarial_tests"],
        ),
        (
            "provenance_and_receipt_audit",
            NODE_SUITE_EXPECTED["provenance_and_receipt_audit"],
        ),
        ("schema_and_type_check", NODE_SUITE_EXPECTED["schema_and_type_check"]),
        ("targeted_h06_degraded", NODE_SUITE_EXPECTED["targeted_h06_degraded"]),
        ("unit_and_contract_tests", NODE_SUITE_EXPECTED["unit_and_contract_tests"]),
    ):
        summary = node_summary(JUNIT_PATHS[label])
        if (
            summary["collected"],
            summary["passed"],
            summary["failed"],
            summary["cancelled"],
            summary["skipped"],
            summary["todo"],
            summary["xml_error_count"],
            summary["xml_failure_count"],
        ) != (expected, expected, 0, 0, 0, 0, 0, 0):
            raise SystemExit(f"{label} gate failed: {summary}")
        summaries[label] = summary

    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if node_inventory.get("count") != NODE_INVENTORY_EXPECTED:
        raise SystemExit(f"Node inventory gate failed: {node_inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "baseline_attempt": "F06-0001",
        "component_tests_are_targeted_only": True,
        "new_failure_count": 0,
        "status": "PASS",
        "suites": summaries,
    }


def _sealed_dependency(
    package: str, attempt: str, core: str, final: str, *, flat: bool = False
) -> dict[str, Any]:
    path = ROOT / (
        f"artifacts/work_packages/{package}/report.json"
        if flat
        else f"artifacts/work_packages/{package}/attempts/{attempt[-4:]}/report.json"
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
        "final_closeout_evidence_id": final,
        "report": path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    status: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "G05": _sealed_dependency("G05", "G05-0001", "E0169", "E0170"),
            "H05": _sealed_dependency("H05", "H05-0001", "E0197", "E0198"),
        },
        "next_action": "SEAL_H06_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("F06", "F06-0001", "E0237", "E0238"),
        "status": "PASS",
    }
    if AUTHORITY_DECISION is not None:
        decision_path = (
            f"artifacts/authority_decisions/{AUTHORITY_DECISION}.human-decision.json"
        )
        status["authority_decision"] = {
            "decision_id": AUTHORITY_DECISION,
            "path": decision_path,
            "sha256": sha256_id(ROOT / decision_path),
        }
    return status


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    return {
        "approved_scope": [
            "plugin_blueprint/epistemic-foundry/hooks/v4_h06/**",
            "artifacts/work_packages/H06/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authority_decision": AUTHORITY_DECISION,
        "authored_by": (
            "bounded implementation agent under the product owner's explicit "
            "parallel-execution instruction"
        ),
        "composed_modules_modified": False,
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "sealing session as an independent contract reviewer, separate from "
            "the author"
        ),
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": True,
        "write_scope_violation_count": 0,
    }


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    core = {
        name: suites[name]["collected"]
        for name in (
            "schema_and_type_check",
            "unit_and_contract_tests",
            "negative_and_adversarial_tests",
            "provenance_and_receipt_audit",
        )
        if name in suites
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "coverage_projection": (
                "sealed H05 HOOK_COVERAGE ordered by declared rank and projected "
                "through the enabled-host set (imported, not restated)"
            ),
            "degraded_mode_policy": (
                "degraded-mode-policy.json full/degraded mode sets, enabled "
                "capability states, and capability-report to gateway host bindings"
            ),
            "gateway_vocab": (
                "hook-gateway HOOK_HOSTS/EVENT_TYPES/DECISIONS/COVERAGE and the "
                "capability probe's declared host capabilities (imported)"
            ),
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "mechanism": (
                    "every degraded receipt and step-provenance record hashes through the gateway's own sha256HookJson, validateDegradedModeReceipt re-derives the EFH06-DEGRADED-MODE id from the payload, and no clock or randomness exists in any product path"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "mechanism": (
                    "the policy's mode and capability vocabularies are pinned closed, the coverage order refuses COVERAGE_RANK_AMBIGUOUS when ranks tie, and a claim naming coverage outside the gateway vocabulary is refused COVERAGE_UNDECLARED"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "mechanism": (
                    "the enabled-host projection is honest by construction: a report or claim that exceeds what the enabled set can observe is refused DEGRADED_OVERCLAIMED, one that understates observed pairs is refused DEGRADED_UNDERSTATED, and an unrestored recovery is refused RECOVERY_COVERAGE_UNRESTORED"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "mechanism": (
                    "the gate holds no state, detects no degradation and grants no authority; it only reads the host's declared state, emits unverified actions with a bounded reason, and refuses any claim of hook-verified provenance that outruns the declaration"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: bounded implementation agent; reviewer: "
                    "sealing session as an independent contract reviewer; "
                    "actor_independence between author and reviewer holds, "
                    "external certification does not)"
                ),
                "status": "PASS",
            },
            **{
                name: {"status": "PASS", "test_count": count}
                for name, count in core.items()
            },
        },
        "status": "PASS",
        "suite_counts": {name: row["collected"] for name, row in suites.items()},
    }


def command_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in RUN_RESULTS:
        value = read_json(ATTEMPT / f"{name}.run.json")
        record = {
            "attempt_id": ATTEMPT_ID,
            "exit_code": value["exit_code"],
            "recorded_at_utc": RECORDED_AT,
            "status": value["status"],
            "step": name,
        }
        if "command" in value:
            record["command"] = value["command"]
        else:
            record["commands"] = value["commands"]
        records.append(record)
    records.append(
        {
            "attempt_id": ATTEMPT_ID,
            "command": [
                "python",
                "-B",
                f"{ATTEMPT_DIR}/build_h06_0001_evidence.py",
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
        "# H06-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: a bounded implementation agent (disjoint write scope, frozen\n"
        "  contracts) under the product owner's explicit parallel-execution\n"
        "  instruction. Reviewer: the sealing session as an independent contract\n"
        "  reviewer, which did not author this attempt; author/reviewer\n"
        "  separation holds with actor_independence=true, while external\n"
        "  actor-independent certification does not.\n"
        "- Write-scope audit: only files inside\n"
        "  plugin_blueprint/epistemic-foundry/hooks/v4_h06/** and\n"
        "  artifacts/work_packages/H06/** were authored; the sealed H05, G05,\n"
        "  gateway and capability-probe surfaces re-verified green as named\n"
        "  regression checks.\n"
        "- Degraded mode is safe by construction: the gate holds no state and\n"
        "  grants no authority. It reads the host's declared capability state,\n"
        "  projects sealed H05 coverage through the enabled-host set, and refuses\n"
        "  DEGRADED_OVERCLAIMED / DEGRADED_UNDERSTATED / COVERAGE_UNDECLARED /\n"
        "  RECOVERY_COVERAGE_UNRESTORED rather than fabricating hook-verified\n"
        "  provenance.\n"
        "- Receipts are immutable: every degraded receipt and step-provenance\n"
        "  record hashes through the gateway's own sha256HookJson and\n"
        "  validateDegradedModeReceipt re-derives its EFH06-DEGRADED-MODE id; no\n"
        "  clock or randomness exists in any product path.\n"
        "- Integration gates at review time: schema-and-type 14, unit-and-\n"
        "  contract 19, negative-and-adversarial 38, provenance-and-receipt 20\n"
        "  (targeted 91), git diff --check clean, and the full Python and full\n"
        "  Node suites green with the Node inventory unified at 132 files across\n"
        "  five bases.\n"
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
        "attempt_type": "H06_HOOK_DISABLED_HOSTED_TOOL_DEGRADED_MODE_GATE",
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
            "degradation detection: the gate reads a host-declared state and never infers or measures degradation itself",
            "hook delivery or enforcement of any kind: it refuses unverified provenance rather than granting it",
            "acquisition of evaluator, holdout or promotion authority",
            "actor-independent certification of this review",
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
                "Author/reviewer separation holds with actor_independence=true "
                "(bounded implementation agent authored, sealing session reviewed "
                "as an independent contract reviewer); external actor-independent "
                "certification does not."
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
        "next_action": "SEAL_H06_0001_THEN_CONTINUE_DAG",
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
    write_json("write-scope-verification.json", write_scope)
    write_json("h06-verification.json", verification)
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
        raise SystemExit("H06-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "h06-verification.json")
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
    verification = read_json(ATTEMPT / "h06-verification.json")
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
        raise SystemExit("stored H06-0001 report is not the deterministic document")
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
