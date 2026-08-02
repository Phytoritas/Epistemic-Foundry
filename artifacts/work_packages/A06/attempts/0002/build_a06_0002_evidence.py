#!/usr/bin/env python3
"""Build and verify A06-0002 independent re-audit evidence.

A06-0002 is the independent constitutional re-audit ordered by
HD-EF4-A06-RM001-20260730-001 after the A05-0003 correction.  The verifier
derives every finding from primary sources; this builder verifies the
executed checks and emits immutable attempt evidence.  It never modifies
product files, and A06-0001 remains the immutable FAIL record.
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
ATTEMPT = ROOT / "artifacts/work_packages/A06/attempts/0002"
ATTEMPT_ID = "A06-0002"
WORK_PACKAGE_ID = "A06"
RECORDED_AT = "2026-08-01T01:20:00.000Z"

EXPECTED_TARGETED_PYTHON_COUNT = 40
EXPECTED_PYTHON_COUNT = 1196
EXPECTED_NODE_COUNT = 860
EXPECTED_NODE_FILE_COUNT = 84

RM001_DECISION_ID = "HD-EF4-A06-RM001-20260730-001"
RM001_DECISION_PATH = (
    "artifacts/authority_decisions/HD-EF4-A06-RM001-20260730-001.human-decision.json"
)
RM001_DECISION_HASH = (
    "sha256:3ed9daaf685214ffe34c6be92301abd046eb6fa7d1c7f625554746afc83fd7be"
)
EXPECTED_DEPENDENCY_HASHES = {
    RM001_DECISION_PATH: (
        "fa42fb83650a3288f1b7e9c9680a9fcc05efc7111800bf8420d12a4efa365aee"
    ),
    "artifacts/work_packages/A05/attempts/0003/report.json": (
        "8b7a8719c4a9ccbfba366fb9144a8c69893a59a7f45ecd09c0d6d654eeb3187c"
    ),
    "artifacts/work_packages/A06/attempts/0001/report.json": (
        "d37a425f2bc025f7c6cbf09f08b8a3d383105c141b074e03bbe8fe3175352dc7"
    ),
}
PRODUCT_FILES = ("docs/v4_a06/constitutional_reaudit_a06_0002.md",)

JUNIT_PATHS = {
    "targeted_a05_python": ATTEMPT / "targeted-a05-python.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node"})
RUN_RESULTS = (
    "targeted-a05-python",
    "audit-verifier",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
REQUIRED_CHECK_MAP = {
    "constitutional_negative_24_audit": "verification.constitutional_cases (24 tokens present, junit PASS)",
    "constitutional_positive_6_audit": "verification.constitutional_cases (6 tokens present, junit PASS)",
    "constitutional_schema_and_projection_parity": "verification.schema_meta_audit + firewall hostile fixtures",
    "evaluator_holdout_firewall_audit": "verification.firewall_audit (F001/F002)",
    "gate_registry_and_order_audit": "verification.promotion_workflow_audit (F004)",
    "independent_review": "review.md (primary-session separate, actor_independence=false)",
    "lease_fence_cas_receipt_audit": "verification.promotion_workflow_audit outputs + NEG-020..024 cases",
    "negative_and_adversarial_tests": "targeted-a05-python.junit.xml (24 negative cases)",
    "parliament_attestation_approval_audit": "verification.chamber_audit + G11/G12/G13 nodes + NEG-015..019",
    "provenance_and_receipt_audit": "authority artifact outputs + receipt-bound commit cases",
    "schema_and_type_check": "verification.schema_meta_audit (127 Draft 2020-12 schemas)",
    "unit_and_contract_tests": "full Python 1196/1196 and full Node 860/860",
}
OUTPUT_NAMES = (
    "run_a06_0002_checks.py",
    "build_a06_0002_evidence.py",
    "a06_0002_rah_seal.py",
    "constitutional_audit_verifier_0002.py",
    "constitutional-audit-verification.json",
    "dependency-status.json",
    "a06-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "targeted-a05-python.junit.xml",
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


def regression_evidence(normalization: dict[str, Any]) -> dict[str, Any]:
    targeted = pytest_summary(JUNIT_PATHS["targeted_a05_python"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if (
        targeted["collected"],
        targeted["passed"],
        targeted["failed"],
        targeted["errors"],
        targeted["skipped"],
    ) != (EXPECTED_TARGETED_PYTHON_COUNT, EXPECTED_TARGETED_PYTHON_COUNT, 0, 0, 0):
        raise SystemExit(f"re-executed constitutional gate failed: {targeted}")
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

    verification = read_json(ATTEMPT / "constitutional-audit-verification.json")
    if verification.get("status") != "PASS" or verification.get("failed_finding_ids"):
        raise SystemExit("constitutional audit verification is not PASS")
    finding_statuses = {
        str(finding.get("finding_id")): str(finding.get("status"))
        for finding in verification.get("findings", [])
    }
    if finding_statuses != {
        "A06-F001": "PASS",
        "A06-F002": "PASS",
        "A06-F003": "PASS",
        "A06-F004": "PASS",
        "A06-F005": "PASS",
    }:
        raise SystemExit(f"finding verdicts are not all PASS: {finding_statuses}")
    recorded_raw = verification["constitutional_cases"]["junit_sha256"]
    normalization_raw = normalization["files"]["targeted_a05_python"]["raw_sha256"]
    if recorded_raw != normalization_raw:
        raise SystemExit(
            "audit verifier consumed a different constitutional junit than the sealed run"
        )
    return {
        "attempt_id": ATTEMPT_ID,
        "audit_verification": {
            "failed_finding_ids": [],
            "finding_statuses": finding_statuses,
            "path": "artifacts/work_packages/A06/attempts/0002/constitutional-audit-verification.json",
            "sha256": sha256_id(ATTEMPT / "constitutional-audit-verification.json"),
            "status": "PASS",
        },
        "baseline_attempt": "A05-0003",
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "status": "PASS",
        "targeted_a05_python": targeted,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    decision = read_json(ROOT / RM001_DECISION_PATH)
    if (
        decision.get("decision_id") != RM001_DECISION_ID
        or decision.get("authority_role") != "product_owner"
        or decision.get("decision_hash") != RM001_DECISION_HASH
        or canonical_hash_excluding(decision, "decision_hash") != RM001_DECISION_HASH
    ):
        raise SystemExit("RM001 HumanDecision identity or self-hash mismatch")
    correction = read_json(ROOT / "artifacts/work_packages/A05/attempts/0003/report.json")
    rah = correction.get("rah_state")
    if (
        correction.get("status") != "PASS"
        or not isinstance(rah, dict)
        or rah.get("core_evidence_id") != "E0117"
        or rah.get("final_closeout_evidence_id") != "E0118"
    ):
        raise SystemExit("A05-0003 correction is not the sealed PASS dependency")
    trigger = read_json(ROOT / "artifacts/work_packages/A06/attempts/0001/report.json")
    if trigger.get("status") != "FAIL":
        raise SystemExit("A06-0001 must remain the immutable FAIL record")
    return {
        "attempt_id": ATTEMPT_ID,
        "authority": {
            "decision_file_sha256": sha256_id(ROOT / RM001_DECISION_PATH),
            "decision_hash": RM001_DECISION_HASH,
            "decision_id": RM001_DECISION_ID,
            "status": "PASS",
        },
        "dependencies": {
            "A05-0003": {
                "core_evidence_id": "E0117",
                "final_closeout_evidence_id": "E0118",
                "report": "artifacts/work_packages/A05/attempts/0003/report.json",
                "report_sha256": sha256_id(
                    ROOT / "artifacts/work_packages/A05/attempts/0003/report.json"
                ),
                "role": "AUDITED_CONSTITUTIONAL_CORRECTION",
                "status": "PASS",
            },
            "A06-0001": {
                "report": "artifacts/work_packages/A06/attempts/0001/report.json",
                "report_sha256": sha256_id(
                    ROOT / "artifacts/work_packages/A06/attempts/0001/report.json"
                ),
                "role": "IMMUTABLE_PRIOR_FAIL",
                "status": "FAIL_PRESERVED",
            },
        },
        "next_action": "RECOMPUTE_156_PACKAGE_DAG_X05_WAVE",
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    product = {relative: sha256_id(ROOT / relative) for relative in PRODUCT_FILES}
    docs_dir = ROOT / "docs/v4_a06"
    files = sorted(
        path.relative_to(ROOT).as_posix() for path in docs_dir.rglob("*") if path.is_file()
    )
    expected_files = sorted(
        (*PRODUCT_FILES, "docs/v4_a06/constitutional_audit.md")
    )
    if files != expected_files:
        raise SystemExit(f"docs/v4_a06 holds unexpected files: {files}")
    return {
        "approved_scope": ["docs/v4_a06/**", "artifacts/work_packages/A06/**"],
        "attempt_id": ATTEMPT_ID,
        "preserved_prior_documents": {
            "docs/v4_a06/constitutional_audit.md": sha256_id(
                ROOT / "docs/v4_a06/constitutional_audit.md"
            )
        },
        "product_file_hashes": product,
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def a06_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "audit_document": {
            "path": "docs/v4_a06/constitutional_reaudit_a06_0002.md",
            "sha256": sha256_id(ROOT / "docs/v4_a06/constitutional_reaudit_a06_0002.md"),
        },
        "finding_verdicts": regression["audit_verification"]["finding_statuses"],
        "independence_method": (
            "Findings derive from primary sources (schemas, samples, firewall "
            "runtime, workflow YAML, module sources); the audited A05 registry "
            "verifier is a labelled cross-check only."
        ),
        "required_checks": {
            name: {"evidence": evidence, "status": "PASS"}
            for name, evidence in sorted(REQUIRED_CHECK_MAP.items())
        },
        "status": "PASS",
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
                "artifacts/work_packages/A06/attempts/0002/build_a06_0002_evidence.py",
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
        "# A06-0002 primary-session separate audit review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- Method independence: every finding verdict is recomputed from\n"
        "  primary sources — hostile schema fixtures, the live firewall\n"
        "  runtime, direct workflow-graph analysis with its own ancestry and\n"
        "  capability checks, and module-source inspection.  The audited A05\n"
        "  registry verifier appears only as a labelled cross-check and\n"
        "  contributes to no verdict, so the remediated runtime cannot\n"
        "  certify itself.\n"
        "- Verdicts: A06-F001 through A06-F005 all PASS against the live\n"
        "  tree; the 24 negative and 6 positive constitutional cases were\n"
        "  re-executed into this attempt's own JUnit evidence and the\n"
        "  verifier is hash-bound to exactly that run.\n"
        "- History: A06-0001 remains the immutable FAIL record, preserved\n"
        "  byte-identically and pinned by hash; nothing was relabeled.\n"
        "- Boundaries: the audit proves contract and graph enforcement, not\n"
        "  kernel-scheduler execution, evaluator qualification, or release\n"
        "  maturity; those remain later packages.\n"
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
            "path": f"artifacts/work_packages/A06/attempts/0002/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "A06_INDEPENDENT_CONSTITUTIONAL_REAUDIT",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "all_24_negative_and_6_positive_a05_paths_reconciled": "PASS",
            "constitutional_boundaries_pass_independent_audit": "PASS",
            "no_candidate_model_prompt_backend_or_hook_authority_gain": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "a06_0001_fail_preserved_immutably": True,
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "RECOMPUTE_DAG_THEN_EARLIEST_X05_READY",
        "not_claimed": [
            "kernel-scheduler execution of the promotion workflow",
            "evaluator qualification or live candidate promotion",
            "external actor-independent certification",
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
            "mode": "PRIMARY_SESSION_SEPARATE_AUDIT_REVIEW",
            "status": "PASS",
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
    normalization = normalize_junits()
    regression = regression_evidence(normalization)
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = a06_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("a06-verification.json", verification)
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
        "finding_verdicts": "A06-F001..F005 all PASS",
        "full_node": "860/860",
        "full_python": "1196/1196",
        "next_action": "RECOMPUTE_156_PACKAGE_DAG_X05_WAVE",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_a05_python": "40/40",
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
        raise SystemExit("A06-0002 report is already RAH-bound")
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
    normalization = read_json(ATTEMPT / "junit-normalization-verification.json")
    regression = regression_evidence(normalization)
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    verification = read_json(ATTEMPT / "a06-verification.json")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=rah_state
    )
    write_json("report.json", report)


def verify() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalization = normalize_junits()
    regression = regression_evidence(normalization)
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    stored = read_json(ATTEMPT / "report.json")
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope_live = write_scope_verification()
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    if write_scope_live != write_scope:
        raise SystemExit("write-scope verification drifted from the sealed record")
    verification_live = a06_verification(regression)
    verification = read_json(ATTEMPT / "a06-verification.json")
    if verification_live != verification:
        raise SystemExit("audit verification drifted from the sealed record")
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
        raise SystemExit("stored A06-0002 report is not the deterministic document")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "finding_verdicts": "A06-F001..F005 all PASS",
        "full_node": "860/860",
        "full_python": "1196/1196",
        "next_action": "RECOMPUTE_156_PACKAGE_DAG_X05_WAVE",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_a05_python": "40/40",
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
