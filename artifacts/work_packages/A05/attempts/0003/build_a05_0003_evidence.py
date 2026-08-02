#!/usr/bin/env python3
"""Build and verify A05-0003 constitutional-correction evidence.

A05-0003 executes the runtime half of HD-EF4-A06-RM001-20260730-001: the
G00-G14 gate registry and node bindings in
``src/epistemic_foundry/governance/evolution_authority``, the canonical
23-node ``evolution_promotion`` workflow, the chamber delegation swap, the
derived MASTER_SPEC/J02/tool-pin cascade authorized by
HD-EF4-A05-0003-SCOPE-20260801-001, and the 24 negative / 6 positive
constitutional cases.  This builder verifies the executed checks and emits
immutable attempt evidence; it never modifies product files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/A05/attempts/0003"
ATTEMPT_ID = "A05-0003"
WORK_PACKAGE_ID = "A05"
RECORDED_AT = "2026-08-01T00:30:00.000Z"

sys.path.insert(0, str(ROOT / "src"))

EXPECTED_TARGETED_PYTHON_COUNT = 40
EXPECTED_TARGETED_NODE_COUNT = 25
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
SCOPE_DECISION_ID = "HD-EF4-A05-0003-SCOPE-20260801-001"
SCOPE_DECISION_PATH = (
    "artifacts/authority_decisions/HD-EF4-A05-0003-SCOPE-20260801-001.human-decision.json"
)
SCOPE_DECISION_HASH = (
    "sha256:70eb67d99c5c55b48b7b2e9e53034b11e0aec511e89153edbec04b5cbe6d412c"
)
EXPECTED_DEPENDENCY_HASHES = {
    RM001_DECISION_PATH: (
        "fa42fb83650a3288f1b7e9c9680a9fcc05efc7111800bf8420d12a4efa365aee"
    ),
    SCOPE_DECISION_PATH: (
        "2ff628c718f319e047c7cbea44555e3019d6afa0d5a9840a9054ec7a68075f3a"
    ),
    "artifacts/work_packages/A05/attempts/0002/report.json": (
        "c9c550de22f55d32898f0d33489bc9b0480de6eef4bca7baeb09fcf047c6062c"
    ),
    "artifacts/work_packages/A06/attempts/0001/report.json": (
        "d37a425f2bc025f7c6cbf09f08b8a3d383105c141b074e03bbe8fe3175352dc7"
    ),
    "artifacts/work_packages/W01/attempts/0001/report.json": (
        "637ac0a9d737e1ea3cc588fae35d60d05ed367228bbf88f322b4cefc8a46e490"
    ),
}
RM001_SCOPE_FILES = frozenset(
    {
        "src/epistemic_foundry/governance/evolution_authority/__init__.py",
        "src/epistemic_foundry/governance/evolution_authority/registry.py",
        "src/epistemic_foundry/governance/evolution_authority/nodes.py",
        "workflows/evolution_promotion.workflow.yaml",
        "tests/governance/__init__.py",
        "tests/governance/a05/__init__.py",
        "tests/governance/a05/test_a05_gate_registry.py",
        "tests/governance/a05/test_a05_negative_cases.py",
        "tests/governance/a05/test_a05_positive_cases.py",
    }
)
CASCADE_SCOPE_FILES = frozenset(
    {
        "workflows/evolution_chamber_cycle.workflow.yaml",
        "MASTER_SPEC.md",
        "tools/validate_spec_bundle.py",
        "plugins/epistemic-foundry/skills/skill-inventory.json",
        "tests/fixtures/j02/skill-inventory.expected.json",
        "tests/fixtures/j02/reference-selection-cases.json",
        "tests/test_wire_literal_discipline.py",
    }
)

JUNIT_PATHS = {
    "targeted_a05_python": ATTEMPT / "targeted-a05-python.junit.xml",
    "targeted_j02_node": ATTEMPT / "targeted-j02-node.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset({"targeted_j02_node", "full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "targeted-a05-python",
    "targeted-j02-node",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_a05_0003_checks.py",
    "build_a05_0003_evidence.py",
    "a05_0003_rah_seal.py",
    "product-hashes.json",
    "dependency-status.json",
    "a05-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "targeted-a05-python.junit.xml",
    "targeted-j02-node.junit.xml",
    "full-python-suite.junit.xml",
    "full-node-suite.junit.xml",
    "commands.jsonl",
    "review.md",
)

NEGATIVE_CASE_IDS = tuple(f"A05-NEG-{index:03d}" for index in range(1, 25))
POSITIVE_CASE_IDS = tuple(f"A05-POS-{index:03d}" for index in range(1, 7))


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


def _case_names(path: Path) -> set[str]:
    root = ET.parse(path).getroot()
    return {str(case.get("name")) for case in root.findall(".//testcase")}


def regression_evidence() -> dict[str, Any]:
    targeted_python = pytest_summary(JUNIT_PATHS["targeted_a05_python"])
    targeted_node = node_summary(JUNIT_PATHS["targeted_j02_node"])
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
        raise SystemExit(f"targeted A05 gate failed: {targeted_python}")
    if (
        targeted_node["collected"],
        targeted_node["passed"],
        targeted_node["failed"],
        targeted_node["cancelled"],
        targeted_node["skipped"],
        targeted_node["todo"],
    ) != (EXPECTED_TARGETED_NODE_COUNT, EXPECTED_TARGETED_NODE_COUNT, 0, 0, 0, 0):
        raise SystemExit(f"targeted J02 rebind gate failed: {targeted_node}")
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

    names = _case_names(JUNIT_PATHS["targeted_a05_python"])
    missing_negative = [
        case_id
        for case_id in NEGATIVE_CASE_IDS
        if not any(case_id.lower().replace("-", "_") in name for name in names)
    ]
    missing_positive = [
        case_id
        for case_id in POSITIVE_CASE_IDS
        if not any(case_id.lower().replace("-", "_") in name for name in names)
    ]
    if missing_negative or missing_positive:
        raise SystemExit(
            "constitutional case registry incomplete: "
            f"negative={missing_negative} positive={missing_positive}"
        )
    return {
        "attempt_id": ATTEMPT_ID,
        "baseline_attempt": "W01-0001",
        "constitutional_cases": {
            "negative_case_count": len(NEGATIVE_CASE_IDS),
            "negative_case_ids": list(NEGATIVE_CASE_IDS),
            "positive_case_count": len(POSITIVE_CASE_IDS),
            "positive_case_ids": list(POSITIVE_CASE_IDS),
        },
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 860, "full_python": 1156},
        "status": "PASS",
        "targeted_a05_python": targeted_python,
        "targeted_j02_node": targeted_node,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }


def _verify_decision(relative: str, decision_id: str, decision_hash: str) -> dict[str, Any]:
    decision = read_json(ROOT / relative)
    if (
        decision.get("decision_id") != decision_id
        or decision.get("authority_role") != "product_owner"
        or decision.get("decision_hash") != decision_hash
        or canonical_hash_excluding(decision, "decision_hash") != decision_hash
    ):
        raise SystemExit(f"{decision_id} identity or self-hash mismatch")
    return {
        "decision_file_sha256": sha256_id(ROOT / relative),
        "decision_hash": decision_hash,
        "decision_id": decision_id,
        "path": relative,
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    base = read_json(ROOT / "artifacts/work_packages/A05/attempts/0002/report.json")
    if (base.get("package_status") or base.get("status")) != "PASS":
        raise SystemExit("A05-0002 base contract is not PASS")
    trigger = read_json(ROOT / "artifacts/work_packages/A06/attempts/0001/report.json")
    if trigger.get("status") != "FAIL":
        raise SystemExit("A06-0001 remediation trigger must remain the immutable FAIL")
    baseline = read_json(ROOT / "artifacts/work_packages/W01/attempts/0001/report.json")
    rah = baseline.get("rah_state")
    if (
        baseline.get("status") != "PASS"
        or not isinstance(rah, dict)
        or rah.get("core_evidence_id") != "E0115"
        or rah.get("final_closeout_evidence_id") != "E0116"
    ):
        raise SystemExit("W01-0001 regression baseline is not the sealed PASS attempt")
    return {
        "attempt_id": ATTEMPT_ID,
        "authority": {
            "cascade_scope_decision": _verify_decision(
                SCOPE_DECISION_PATH, SCOPE_DECISION_ID, SCOPE_DECISION_HASH
            ),
            "remediation_decision": _verify_decision(
                RM001_DECISION_PATH, RM001_DECISION_ID, RM001_DECISION_HASH
            ),
        },
        "dependencies": {
            "A05-0002": {
                "report": "artifacts/work_packages/A05/attempts/0002/report.json",
                "report_sha256": sha256_id(
                    ROOT / "artifacts/work_packages/A05/attempts/0002/report.json"
                ),
                "role": "CANONICAL_CHARTER_BASE",
                "status": "PASS",
            },
            "A06-0001": {
                "report": "artifacts/work_packages/A06/attempts/0001/report.json",
                "report_sha256": sha256_id(
                    ROOT / "artifacts/work_packages/A06/attempts/0001/report.json"
                ),
                "role": "IMMUTABLE_REMEDIATION_TRIGGER",
                "status": "FAIL_PRESERVED",
            },
            "W01-0001": {
                "core_evidence_id": "E0115",
                "final_closeout_evidence_id": "E0116",
                "report": "artifacts/work_packages/W01/attempts/0001/report.json",
                "report_sha256": sha256_id(
                    ROOT / "artifacts/work_packages/W01/attempts/0001/report.json"
                ),
                "role": "REGRESSION_BASELINE",
                "status": "PASS",
            },
        },
        "next_action": "SEAL_A05_0003_THEN_RUN_A06_0002",
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    product_hashes = read_json(ATTEMPT / "product-hashes.json")
    if set(product_hashes) != (RM001_SCOPE_FILES | CASCADE_SCOPE_FILES):
        raise SystemExit("A05-0003 product file set drifted from the authorized scope")
    for relative, wanted in product_hashes.items():
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else "MISSING"
        if actual != wanted:
            raise SystemExit(f"product file changed: {relative}: {actual} != {wanted}")
    component = ROOT / "src/epistemic_foundry/governance/evolution_authority"
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in component.rglob("*.py")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if component_files != sorted(
        name for name in RM001_SCOPE_FILES if name.startswith("src/")
    ):
        raise SystemExit(f"evolution_authority holds unexpected files: {component_files}")
    return {
        "attempt_id": ATTEMPT_ID,
        "authorized_scope": {
            "cascade_paths_decision": SCOPE_DECISION_ID,
            "cascade_paths": sorted(CASCADE_SCOPE_FILES),
            "remediation_decision": RM001_DECISION_ID,
            "remediation_paths": sorted(RM001_SCOPE_FILES),
        },
        "notes": [
            "tests/governance/__init__.py is the required parent package marker "
            "for the RM001 tests/governance/a05 test path grant.",
            "MASTER_SPEC.md and workflows/evolution_chamber_cycle.workflow.yaml "
            "received only the exact deltas enumerated by the cascade decision; "
            "their remaining dirty-worktree content is preserved unchanged.",
        ],
        "product_file_count": len(product_hashes),
        "product_hash_table": "artifacts/work_packages/A05/attempts/0003/product-hashes.json",
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def constitutional_verification(regression: dict[str, Any]) -> dict[str, Any]:
    from epistemic_foundry.governance.evolution_authority import (
        EXPECTED_PROMOTION_NODE_COUNT,
        GATE_APPLICABILITY,
        PROMOTION_WORKFLOW_STEPS,
        REQUIRED_RESOLVED_REF_KEYS,
        RESOLVED_REF_TUPLE_FIELDS,
        verify_evolution_chamber_binding,
        verify_promotion_workflow_binding,
    )

    promotion = yaml.safe_load(
        (ROOT / "workflows/evolution_promotion.workflow.yaml").read_text(
            encoding="utf-8"
        )
    )
    chamber = yaml.safe_load(
        (ROOT / "workflows/evolution_chamber_cycle.workflow.yaml").read_text(
            encoding="utf-8"
        )
    )
    promotion_binding = verify_promotion_workflow_binding(promotion)
    chamber_binding = verify_evolution_chamber_binding(chamber)
    if len(chamber.get("nodes", [])) != 26:
        raise SystemExit("evolution_chamber_cycle no longer holds 26 nodes")

    spec_text = (ROOT / "MASTER_SPEC.md").read_text(encoding="utf-8")
    if "Total: **23 workflows / 350 nodes**." not in spec_text:
        raise SystemExit("MASTER_SPEC workflow totals not updated to 23/350")
    if "| `evolution_promotion` | 23 |" not in spec_text:
        raise SystemExit("MASTER_SPEC lacks the evolution_promotion table row")
    workflow_files = sorted((ROOT / "workflows").glob("*.workflow.yaml"))
    node_total = sum(
        len(yaml.safe_load(path.read_text(encoding="utf-8"))["nodes"])
        for path in workflow_files
    )
    if len(workflow_files) != 23 or node_total != 350:
        raise SystemExit(
            f"workflow corpus is {len(workflow_files)} files / {node_total} nodes, not 23/350"
        )

    return {
        "attempt_id": ATTEMPT_ID,
        "chamber_binding": chamber_binding,
        "charter_obligations": {
            "applicability_matrix_gate_count": len(GATE_APPLICABILITY),
            "gate_node_count": EXPECTED_PROMOTION_NODE_COUNT,
            "promotion_workflow_step_count": len(PROMOTION_WORKFLOW_STEPS),
            "resolved_reference_key_count": len(REQUIRED_RESOLVED_REF_KEYS),
            "resolved_reference_tuple_field_count": len(RESOLVED_REF_TUPLE_FIELDS),
        },
        "finding_remediation": {
            "A06-F001": {
                "owner": "C01 shared correction (already live)",
                "status": "OUT_OF_A05_SCOPE_PRESENT_LIVE",
            },
            "A06-F002": {
                "owner": "C01/runtime correction (already live)",
                "status": "OUT_OF_A05_SCOPE_PRESENT_LIVE",
            },
            "A06-F003": {
                "evidence": "chamber promotion node is a deterministic subworkflow delegation",
                "status": "REMEDIATED",
            },
            "A06-F004": {
                "evidence": (
                    "evolution_promotion graph-enforces G00-G14 order, advisory-only llm "
                    "outputs, one promotion:commit holder, and all authority artifact outputs"
                ),
                "status": "REMEDIATED",
            },
            "A06-F005": {
                "evidence": (
                    "all 21 deterministic/policy/human_gate nodes bind "
                    "epistemic_foundry.governance.evolution_authority.nodes, which delegates "
                    "to decide_promotion and PromotionCommitter"
                ),
                "status": "REMEDIATED",
            },
        },
        "independent_audit_note": (
            "Finding closure is claimed for implementation only; the independent "
            "constitutional re-audit is A06-0002 and is not claimed here."
        ),
        "master_spec_workflow_corpus": {"node_total": 350, "workflow_count": 23},
        "promotion_binding": promotion_binding,
        "status": "PASS",
        "targeted_case_count": regression["targeted_a05_python"]["collected"],
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
                "artifacts/work_packages/A05/attempts/0003/build_a05_0003_evidence.py",
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
        "# A05-0003 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.  A05 does not\n"
        "  certify its own constitutional compliance: the independent re-audit\n"
        "  remains A06-0002.\n"
        "- Authority fidelity: every write is bound to\n"
        "  HD-EF4-A06-RM001-20260730-001 or to the exact-path cascade decision\n"
        "  HD-EF4-A05-0003-SCOPE-20260801-001, both verified by self-hash; the\n"
        "  A06-0001 FAIL report is preserved byte-identically as the trigger.\n"
        "- Registry integrity (EF4-I22): gate identifiers are imported from the\n"
        "  bounded decider, the charter 4.2 applicability matrix is proven\n"
        "  consistent with the decider's NOT_REQUIRED ceilings by test, and the\n"
        "  new modules were registered in the wire-literal guard without\n"
        "  changing any token, threshold, or assertion.\n"
        "- Workflow authority: the 23-node evolution_promotion graph enforces\n"
        "  strict G00-G14 ancestry, emits GateDecision/Adjudication/Attestation/\n"
        "  ApprovalRecord/CapabilityLease/ActionIntent/EffectReceipt/\n"
        "  PromotionDecision artifacts, restricts llm nodes to advisory\n"
        "  outputs, and grants promotion:commit to exactly one deterministic\n"
        "  node; tampered variants fail closed in tests.\n"
        "- Chamber delegation: the former provider-nondeterministic llm\n"
        "  promotion node now delegates to the canonical subworkflow and can\n"
        "  no longer emit a PromotionDecision; the chamber keeps 26 nodes.\n"
        "- Constitutional cases: all 24 negative/adversarial registry cases and\n"
        "  6 positive boundary controls execute against the real decider,\n"
        "  committer, firewall, and registry, each asserting typed outcomes.\n"
        "- Cascade honesty: the MASTER_SPEC table, spec-bundle pins, and J02\n"
        "  authority inventory were updated to the new factual totals with the\n"
        "  17 source hashes and inventory_hash recomputed under the loader's\n"
        "  own canonical-JSON rule, and the full Node suite re-proves the\n"
        "  inventory identity.\n"
        "- Finding (recorded procedure deviation): re-running the sealed\n"
        "  A06-0001 verifier during scoping regenerated its attempt-local\n"
        "  verification JSON in place; the report hash pin proves the sealed\n"
        "  report itself is unchanged, and A06-0002 will use a fresh verifier.\n"
        "- Residual limitations: runtime orchestration of the promotion\n"
        "  workflow inside the kernel scheduler, evaluator qualification, and\n"
        "  the independent A06 re-audit are not claimed.\n"
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
            "path": f"artifacts/work_packages/A05/attempts/0003/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "A05_CONSTITUTIONAL_RUNTIME_CORRECTION_UNDER_HD_EF4_A06_RM001",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "g00_g14_registry_and_23_node_workflow_implemented": "PASS",
            "twenty_four_negative_and_six_positive_cases_pass": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "a06_0001_fail_preserved_as_immutable_trigger": True,
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "A06-0002",
        "not_claimed": [
            "independent constitutional re-audit (A06-0002 scope)",
            "runtime orchestration of evolution_promotion inside the kernel scheduler",
            "evaluator qualification or live promotion of any real candidate",
            "actor-independent certification of this implementation review",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "regression": regression,
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
    verification = constitutional_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("a05-verification.json", verification)
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
        "constitutional_cases": "24 negative + 6 positive PASS",
        "full_node": "860/860",
        "full_python": "1196/1196",
        "next_action": "SEAL_A05_0003_THEN_RUN_A06_0002",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_a05_python": "40/40",
        "targeted_j02_node": "25/25",
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
        raise SystemExit("A05-0003 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "a05-verification.json")
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
    verification_live = constitutional_verification(regression)
    verification = read_json(ATTEMPT / "a05-verification.json")
    if verification_live != verification:
        raise SystemExit("constitutional verification drifted from the sealed record")
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
        raise SystemExit("stored A05-0003 report is not the deterministic document")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "constitutional_cases": "24 negative + 6 positive PASS",
        "full_node": "860/860",
        "full_python": "1196/1196",
        "next_action": "SEAL_A05_0003_THEN_RUN_A06_0002",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_a05_python": "40/40",
        "targeted_j02_node": "25/25",
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
